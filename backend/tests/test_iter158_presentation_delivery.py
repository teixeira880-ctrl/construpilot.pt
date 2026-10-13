"""Iter158 — presentation download delivery tests.

Coverage:
- Public metadata endpoint /api/presentation/videos (read-only contract)
- byte_range and video_response range/etag behavior
- cached_asset hydration and failure handling with isolated fake DB/storage
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

import pytest
import requests
from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, "/app/backend")
from engines import presentation_assets as pa


def _mk_request(method: str = "GET", headers: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": "/api/presentation/videos/long-horizontal.mp4",
        "raw_path": b"/api/presentation/videos/long-horizontal.mp4",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 443),
    }
    return Request(scope)


async def _read_streaming_response(resp) -> bytes:
    chunks: list[bytes] = []
    async for item in resp.body_iterator:
        chunks.append(item)
    return b"".join(chunks)


@pytest.fixture()
def sample_video_file(tmp_path: Path):
    content = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"  # 36 bytes
    fp = tmp_path / "sample.mp4"
    fp.write_bytes(content)
    record = {
        "variant": "long-horizontal",
        "byte_size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    return fp, content, record


@pytest.mark.parametrize(
    "header,expected",
    [
        (None, (0, 35, False)),
        ("bytes=0-0", (0, 0, True)),
        ("bytes=5-10", (5, 10, True)),
        ("bytes=30-", (30, 35, True)),
        ("bytes=-5", (31, 35, True)),
        ("bytes=-999", (0, 35, True)),
        ("bytes=34-999", (34, 35, True)),
    ],
)
def test_byte_range_valid_cases(header, expected):
    assert pa.byte_range(header, 36) == expected


@pytest.mark.parametrize(
    "header",
    [
        "bytes=",  # empty range
        "bytes=0-1,2-3",  # multi-range unsupported
        "bytes=abc-def",  # malformed
        "bytes=36-40",  # start out of bounds
        "bytes=20-10",  # reversed
        "bytes=-0",  # zero suffix
        "bytes= - ",  # malformed spaces
        "bytes=" + ("1" * 100) + "-2",  # oversized header (>90)
    ],
)
def test_byte_range_invalid_cases(header):
    with pytest.raises(ValueError):
        pa.byte_range(header, 36)


@pytest.mark.anyio
async def test_video_response_get_200_full(sample_video_file):
    fp, content, record = sample_video_file
    resp = pa.video_response(_mk_request("GET"), record, fp)
    assert resp.status_code == 200
    assert resp.headers["Content-Length"] == str(len(content))
    body = await _read_streaming_response(resp)
    assert body == content


@pytest.mark.anyio
async def test_video_response_head_200_no_body(sample_video_file):
    fp, content, record = sample_video_file
    resp = pa.video_response(_mk_request("HEAD"), record, fp)
    assert resp.status_code == 200
    assert resp.headers["Content-Length"] == str(len(content))
    assert getattr(resp, "body", b"") in (b"", None)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "range_header,expected_slice,expected_content_range",
    [
        ("bytes=2-7", slice(2, 8), "bytes 2-7/36"),
        ("bytes=32-", slice(32, 36), "bytes 32-35/36"),
        ("bytes=-6", slice(30, 36), "bytes 30-35/36"),
        ("bytes=-999", slice(0, 36), "bytes 0-35/36"),
        ("bytes=33-99", slice(33, 36), "bytes 33-35/36"),
    ],
)
async def test_video_response_get_206_ranges(sample_video_file, range_header, expected_slice,
                                             expected_content_range):
    fp, content, record = sample_video_file
    resp = pa.video_response(_mk_request("GET", {"range": range_header}), record, fp)
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == expected_content_range
    body = await _read_streaming_response(resp)
    assert body == content[expected_slice]


def test_video_response_head_206_empty_with_range(sample_video_file):
    fp, _, record = sample_video_file
    resp = pa.video_response(_mk_request("HEAD", {"range": "bytes=3-5"}), record, fp)
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == "bytes 3-5/36"
    assert getattr(resp, "body", b"") in (b"", None)


@pytest.mark.parametrize(
    "header",
    ["bytes=", "bytes=999-1000", "bytes=8-4", "bytes=-0", "bytes=1-2,4-5", "bytes=a-b"],
)
def test_video_response_416_invalid_ranges(sample_video_file, header):
    fp, _, record = sample_video_file
    resp = pa.video_response(_mk_request("GET", {"range": header}), record, fp)
    assert resp.status_code == 416
    assert resp.headers["Content-Range"] == "bytes */36"


@pytest.mark.anyio
async def test_video_response_etag_304_and_if_range_behavior(sample_video_file):
    fp, content, record = sample_video_file
    etag = '"' + record["sha256"] + '"'

    not_modified = pa.video_response(_mk_request("GET", {"if-none-match": etag}), record, fp)
    assert not_modified.status_code == 304

    mismatch_if_range = pa.video_response(
        _mk_request("GET", {"range": "bytes=1-4", "if-range": '"mismatch"'}),
        record,
        fp,
    )
    assert mismatch_if_range.status_code == 200
    full = await _read_streaming_response(mismatch_if_range)
    assert full == content

    match_if_range = pa.video_response(
        _mk_request("GET", {"range": "bytes=1-4", "if-range": etag}),
        record,
        fp,
    )
    assert match_if_range.status_code == 206
    partial = await _read_streaming_response(match_if_range)
    assert partial == content[1:5]


class _FakeCollection:
    def __init__(self, doc):
        self._doc = doc
        self.calls = 0

    async def find_one(self, query, projection):
        self.calls += 1
        if self._doc and query.get("variant") == self._doc.get("variant") and query.get("published"):
            return dict(self._doc)
        return None


class _FakeDB:
    def __init__(self, doc):
        self.presentation_assets = _FakeCollection(doc)


@pytest.mark.anyio
async def test_cached_asset_missing_or_unpublished_404(monkeypatch, tmp_path):
    monkeypatch.setattr(pa, "db", _FakeDB(None))
    monkeypatch.setattr(pa, "CACHE", tmp_path)
    with pytest.raises(HTTPException) as exc:
        await pa.cached_asset("long-horizontal")
    assert exc.value.status_code == 404


@pytest.mark.anyio
async def test_cached_asset_invalid_metadata_503(monkeypatch, tmp_path):
    bad = {"variant": "long-horizontal", "published": True, "sha256": "bad", "byte_size": 1,
           "parts": ["a"]}
    monkeypatch.setattr(pa, "db", _FakeDB(bad))
    monkeypatch.setattr(pa, "CACHE", tmp_path)
    with pytest.raises(HTTPException) as exc:
        await pa.cached_asset("long-horizontal")
    assert exc.value.status_code == 503


@pytest.mark.anyio
async def test_cached_asset_hydrates_and_validates_hash_size(monkeypatch, tmp_path):
    blob = b"abc123" * 100
    digest = hashlib.sha256(blob).hexdigest()
    doc = {
        "variant": "short-horizontal",
        "published": True,
        "sha256": digest,
        "byte_size": len(blob),
        "parts": ["p1", "p2"],
    }

    class _Storage:
        @staticmethod
        def get_object(path):
            return (blob[:200] if path == "p1" else blob[200:]), "application/octet-stream"

    monkeypatch.setattr(pa, "db", _FakeDB(doc))
    monkeypatch.setattr(pa, "CACHE", tmp_path)
    monkeypatch.setattr(pa, "storage", _Storage)

    record, out = await pa.cached_asset("short-horizontal")
    assert record["sha256"] == digest
    assert out.exists()
    assert out.read_bytes() == blob
    assert out.name == f"{digest}.mp4"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "doc,exc_msg",
    [
        ({"variant": "long-vertical", "published": True, "sha256": "a" * 64, "byte_size": 10,
          "parts": []}, "invalid parts"),
        ({"variant": "long-vertical", "published": True, "sha256": "b" * 64, "byte_size": 10,
          "parts": [f"p{i}" for i in range(25)]}, "too many parts"),
    ],
)
async def test_cached_asset_invalid_part_count_503(monkeypatch, tmp_path, doc, exc_msg):
    class _Storage:
        @staticmethod
        def get_object(_path):
            return b"x", "application/octet-stream"

    monkeypatch.setattr(pa, "db", _FakeDB(doc))
    monkeypatch.setattr(pa, "CACHE", tmp_path)
    monkeypatch.setattr(pa, "storage", _Storage)

    with pytest.raises(HTTPException) as exc:
        await pa.cached_asset(doc["variant"])
    assert exc.value.status_code == 503
    target = tmp_path / f"{doc['sha256']}.mp4"
    assert not target.exists(), f"partial cache leaked for {exc_msg}"


@pytest.mark.anyio
async def test_cached_asset_corruption_or_missing_object_503_no_partial_cache(monkeypatch, tmp_path):
    doc = {
        "variant": "short-vertical",
        "published": True,
        "sha256": "c" * 64,
        "byte_size": 12,
        "parts": ["ok", "missing"],
    }

    class _Storage:
        @staticmethod
        def get_object(path):
            if path == "missing":
                raise RuntimeError("not found")
            return b"123456", "application/octet-stream"

    monkeypatch.setattr(pa, "db", _FakeDB(doc))
    monkeypatch.setattr(pa, "CACHE", tmp_path)
    monkeypatch.setattr(pa, "storage", _Storage)

    with pytest.raises(HTTPException) as exc:
        await pa.cached_asset("short-vertical")
    assert exc.value.status_code == 503
    assert not (tmp_path / ("c" * 64 + ".mp4")).exists()


@pytest.mark.anyio
async def test_cached_asset_uses_existing_cache_without_storage_call(monkeypatch, tmp_path):
    blob = b"z" * 42
    digest = hashlib.sha256(blob).hexdigest()
    doc = {
        "variant": "long-horizontal",
        "published": True,
        "sha256": digest,
        "byte_size": len(blob),
        "parts": ["unused"],
    }
    target = tmp_path / f"{digest}.mp4"
    target.write_bytes(blob)

    class _Storage:
        @staticmethod
        def get_object(_path):
            raise AssertionError("storage.get_object should not be called when cache is valid")

    monkeypatch.setattr(pa, "db", _FakeDB(doc))
    monkeypatch.setattr(pa, "CACHE", tmp_path)
    monkeypatch.setattr(pa, "storage", _Storage)

    _, out = await pa.cached_asset("long-horizontal")
    assert out == target


@pytest.mark.anyio
async def test_cached_asset_concurrent_same_variant_single_hydration(monkeypatch, tmp_path):
    blob = b"K" * 4096
    digest = hashlib.sha256(blob).hexdigest()
    doc = {
        "variant": "long-vertical",
        "published": True,
        "sha256": digest,
        "byte_size": len(blob),
        "parts": ["p1"],
    }
    calls = {"count": 0}

    def _fake_download_parts(record, target):
        calls["count"] += 1
        target.write_bytes(blob)

    monkeypatch.setattr(pa, "db", _FakeDB(doc))
    monkeypatch.setattr(pa, "CACHE", tmp_path)
    monkeypatch.setattr(pa, "download_parts", _fake_download_parts)
    pa._locks.pop("long-vertical", None)

    out1, out2 = await asyncio.gather(
        pa.cached_asset("long-vertical"),
        pa.cached_asset("long-vertical"),
    )
    assert calls["count"] == 1
    assert out1[1] == out2[1]
    assert out1[1].read_bytes() == blob


def test_public_videos_endpoint_contract_readonly():
    base_url = os.environ.get("REACT_APP_BACKEND_URL")
    if not base_url:
        pytest.skip("REACT_APP_BACKEND_URL missing")
    r = requests.get(f"{base_url.rstrip('/')}/api/presentation/videos", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    allowed = {
        "variant", "title", "duration", "width", "height", "byte_size",
        "audio_language", "voice_disclosure", "file_url",
    }
    variants = {"long-horizontal", "long-vertical", "short-horizontal", "short-vertical"}
    for item in data:
        assert set(item.keys()) == allowed
        assert item["variant"] in variants
        assert item["file_url"] == f"/api/presentation/videos/{item['variant']}.mp4"
        assert "parts" not in item and "_id" not in item
        assert "storage" not in str(item).lower() and "key" not in item
