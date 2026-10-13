"""Iter154 Autodesk guard + routing coverage (APS/Cloud transport MOCKED only)."""
import asyncio
import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# Register shared fixtures without importing names shadowed by pytest parameters.
import test_iter153_autodesk_isolated as shared_fixtures

from engines import autodesk_dwg, dwg_convert
from engines.autodesk_client import AutodeskError
from engines.plan_sources import load_cad_source, save_cad_source

Resp = shared_fixtures.Resp
aps_env = shared_fixtures.aps_env
isolated_db = shared_fixtures.isolated_db


def _fixture_bytes(name: str) -> bytes:
    return (Path("/app/integration/revision3/fixtures") / name).read_bytes()


@pytest.mark.anyio
async def test_update_never_overwrites_success_with_unknown_or_failed(aps_env, isolated_db, monkeypatch):
    dwg_data = _fixture_bytes("public-line-2013.dwg")
    digest = hashlib.sha256(dwg_data).hexdigest()
    key = hashlib.sha256(f"iter154-user:dwg-to-dxf:{digest}".encode()).hexdigest()

    job = {
        "_id": key,
        "key": key,
        "attempt_id": "attempt-success",
        "job_id": "aps_success",
        "user_id": "iter154-user",
        "input_sha256": digest,
        "status": "success",
        "cache_id": "aps-cache-existing",
        "provenance": {"provider": "autodesk", "job_id": "aps_success", "engine": "Autodesk.AutoCAD+26_0", "activity": "x", "format_version": "AC1032", "units_code": 4, "input_sha256": digest, "output_sha256": "abc", "output_size_bytes": 10, "entity_count": 1, "layer_count": 2},
        "cache_expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "engine": os.environ["APS_ENGINE"],
        "activity": os.environ["APS_ACTIVITY_ID"],
    }
    await isolated_db.cad_conversion_jobs.insert_one(job)

    local = {"key": key, "attempt_id": "attempt-success", "status": "success"}
    await autodesk_dwg.update(local, status="unknown", error_code="status_unavailable")
    after_unknown = await isolated_db.cad_conversion_jobs.find_one({"_id": key}, {"_id": 0})
    assert after_unknown["status"] == "success"

    await autodesk_dwg.update(local, status="failed", error_code="failed")
    after_failed = await isolated_db.cad_conversion_jobs.find_one({"_id": key}, {"_id": 0})
    assert after_failed["status"] == "success"


@pytest.mark.anyio
async def test_concurrent_same_user_same_bytes_gather_issues_single_post(aps_env, isolated_db, monkeypatch):
    dwg_data = _fixture_bytes("public-line-2013.dwg")
    dxf_data = _fixture_bytes("public-line-reference.dxf")
    post_calls = {"count": 0}

    async def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/workitems"):
            post_calls["count"] += 1
            await asyncio.sleep(0.03)
            return Resp({"id": "work_iter154_1234", "status": "pending"})
        if method == "GET" and "/workitems/" in url:
            return Resp({"status": "success"})
        raise AssertionError(f"Unexpected {method} {url}")

    monkeypatch.setattr(autodesk_dwg, "request", fake_request)
    monkeypatch.setattr(autodesk_dwg.storage, "upload_input", AsyncMock(return_value="https://bucket.s3.amazonaws.com/in"))
    monkeypatch.setattr(autodesk_dwg.storage, "signed_upload", AsyncMock(return_value={"urls": ["https://bucket.s3.amazonaws.com/out"], "uploadKey": "up-1"}))
    monkeypatch.setattr(autodesk_dwg.storage, "read_output", AsyncMock(return_value=dxf_data))
    monkeypatch.setattr(autodesk_dwg.storage, "delete_objects", AsyncMock(return_value=True))

    results = await asyncio.gather(
        autodesk_dwg.convert(dwg_data, user_id="iter154-concurrent"),
        autodesk_dwg.convert(dwg_data, user_id="iter154-concurrent"),
        return_exceptions=True,
    )

    assert post_calls["count"] == 1
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], AutodeskError)
    assert failures[0].code == "conversion_pending"
    out, meta = successes[0]
    assert out == dxf_data
    assert meta["provider"] == "autodesk"


@pytest.mark.anyio
async def test_poll_network_failure_after_parallel_publish_preserves_cached_success(aps_env, isolated_db, monkeypatch):
    dwg_data = _fixture_bytes("public-line-2013.dwg")
    digest = hashlib.sha256(dwg_data).hexdigest()
    key = hashlib.sha256(f"iter154-poll:dwg-to-dxf:{digest}".encode()).hexdigest()

    await isolated_db.cad_conversion_jobs.insert_one({
        "_id": key,
        "key": key,
        "attempt_id": "attempt-poll",
        "job_id": "aps_poll",
        "user_id": "iter154-poll",
        "input_sha256": digest,
        "status": "pending",
        "workitem_id": "work_poll_1234",
        "cache_id": "aps-cache-published",
        "provenance": {"provider": "autodesk", "job_id": "aps_poll", "engine": "Autodesk.AutoCAD+26_0", "activity": "x", "format_version": "AC1032", "units_code": 4, "input_sha256": digest, "output_sha256": "abc", "output_size_bytes": 10, "entity_count": 1, "layer_count": 2},
        "cache_expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "engine": os.environ["APS_ENGINE"],
        "activity": os.environ["APS_ACTIVITY_ID"],
    })

    async def fake_request(method, url, **kwargs):
        # Simulate another request publishing success right before this poll GET fails.
        await isolated_db.cad_conversion_jobs.update_one(
            {"_id": key, "attempt_id": "attempt-poll"},
            {"$set": {"status": "success", "provider_status": "success", "updated_at": datetime.now(timezone.utc)}},
        )
        raise RuntimeError("temporary network issue")

    monkeypatch.setattr(autodesk_dwg, "request", fake_request)

    job = {
        "key": key,
        "attempt_id": "attempt-poll",
        "workitem_id": "work_poll_1234",
        "status": "pending",
    }
    await autodesk_dwg.poll(job)
    current = await isolated_db.cad_conversion_jobs.find_one({"_id": key, "attempt_id": "attempt-poll"}, {"_id": 0})
    assert current["status"] == "success"


@pytest.mark.anyio
async def test_expired_lease_old_finisher_cannot_publish_or_delete_winner_cache(aps_env, isolated_db, monkeypatch):
    dwg_data = _fixture_bytes("public-line-2013.dwg")
    loser_dxf = _fixture_bytes("public-line-reference.dxf")
    winner_dxf = loser_dxf + b"\n0\nEOF\n"
    digest = hashlib.sha256(dwg_data).hexdigest()
    key = hashlib.sha256(f"iter154-lease:dwg-to-dxf:{digest}".encode()).hexdigest()
    now = datetime.now(timezone.utc)

    await isolated_db.cad_conversion_jobs.insert_one({
        "_id": key,
        "key": key,
        "attempt_id": "attempt-lease",
        "job_id": "aps_iter154_lease",
        "user_id": "iter154-lease",
        "input_sha256": digest,
        "status": "finishing",
        "workitem_id": "work_lease_1234",
        "input_key": "jobs/aps_iter154_lease/input.dwg",
        "output_key": "jobs/aps_iter154_lease/result.dxf",
        "output_upload_key": "up-lease",
        "created_at": now,
        "updated_at": now,
        "engine": os.environ["APS_ENGINE"],
        "activity": os.environ["APS_ACTIVITY_ID"],
        "finish_lease_until": now - timedelta(seconds=5),
    })

    winner_cache_id = "aps-cache-winner"
    winner_meta = {
        "provider": "autodesk",
        "status": "verified",
        "job_id": "aps_iter154_lease",
        "engine": os.environ["APS_ENGINE"],
        "activity": os.environ["APS_ACTIVITY_ID"],
        "format_version": "AC1032",
        "units_code": 4,
        "input_sha256": digest,
        "output_sha256": hashlib.sha256(winner_dxf).hexdigest(),
        "output_size_bytes": len(winner_dxf),
        "entity_count": 1,
        "layer_count": 2,
    }
    await save_cad_source(isolated_db, winner_cache_id, "iter154-lease", "converted_dxf", winner_dxf)

    async def fake_read_output(*_args, **_kwargs):
        await isolated_db.cad_conversion_jobs.update_one(
            {"_id": key, "attempt_id": "attempt-lease"},
            {
                "$set": {
                    "status": "success",
                    "cache_id": winner_cache_id,
                    "cache_expires_at": datetime.now(timezone.utc) + timedelta(hours=24),
                    "provenance": winner_meta,
                    "finish_lease_token": "newtoken",
                    "finish_lease_until": datetime.now(timezone.utc) + timedelta(minutes=5),
                }
            },
        )
        return loser_dxf

    monkeypatch.setattr(autodesk_dwg.secrets, "token_hex", lambda _n: "oldtoken")
    monkeypatch.setattr(autodesk_dwg.storage, "read_output", fake_read_output)
    monkeypatch.setattr(autodesk_dwg.storage, "delete_objects", AsyncMock(return_value=True))

    job_for_finish = await isolated_db.cad_conversion_jobs.find_one({"_id": key, "attempt_id": "attempt-lease"}, {"_id": 0})
    output, meta = await autodesk_dwg.finish(job_for_finish)
    assert output == winner_dxf
    assert meta["cached"] is True

    winner_cached = await load_cad_source(isolated_db, winner_cache_id, "iter154-lease", "converted_dxf")
    assert winner_cached == winner_dxf

    old_cache_id = "aps-cache-aps_iter154_lease-oldtoken"
    old_cached = await load_cad_source(isolated_db, old_cache_id, "iter154-lease", "converted_dxf")
    assert old_cached is None

    current = await isolated_db.cad_conversion_jobs.find_one({"_id": key, "attempt_id": "attempt-lease"}, {"_id": 0})
    assert current["finish_lease_token"] == "newtoken"


@pytest.mark.anyio
async def test_autodesk_convert_rejects_missing_user_and_bad_input_without_api_calls(aps_env, isolated_db, monkeypatch):
    request = AsyncMock(side_effect=AssertionError("APS API must not be called"))
    monkeypatch.setattr(autodesk_dwg, "request", request)

    with pytest.raises(AutodeskError) as missing_user:
        await autodesk_dwg.convert(_fixture_bytes("public-line-2013.dwg"), user_id=None)
    assert missing_user.value.code == "missing_owner"

    with pytest.raises(AutodeskError) as bad_input:
        await autodesk_dwg.convert(b"not-a-valid-dwg", user_id="iter154-user")
    assert bad_input.value.code == "invalid_input"
    request.assert_not_awaited()


@pytest.mark.anyio
async def test_dwg_routing_prefers_oda_even_when_aps_enabled(monkeypatch):
    monkeypatch.setenv("ODA_FILE_CONVERTER", "/configured/oda")
    monkeypatch.setenv("APS_DWG_ENABLED", "true")
    monkeypatch.setenv("APS_ACTIVITY_QUALIFIED", "ns.activity+prod")
    monkeypatch.setenv("CLOUDCONVERT_API_KEY", "dummy")

    monkeypatch.setattr(dwg_convert, "_local_dwg_to_dxf", lambda _b: b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n")
    aps_convert = AsyncMock(side_effect=AssertionError("APS path must not run when ODA is configured"))
    monkeypatch.setattr("engines.autodesk_dwg.convert", aps_convert)

    out = await dwg_convert.dwg_to_dxf(_fixture_bytes("public-line-2013.dwg"), user_id="iter154-user")
    assert b"SECTION" in out
    aps_convert.assert_not_awaited()


@pytest.mark.anyio
async def test_dwg_routing_unknown_autodesk_error_never_falls_back_to_cloudconvert(monkeypatch):
    monkeypatch.setenv("ODA_FILE_CONVERTER", "")
    monkeypatch.setenv("APS_DWG_ENABLED", "true")
    monkeypatch.setenv("APS_DWG_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("APS_ACTIVITY_QUALIFIED", "ns.activity+prod")
    monkeypatch.setenv("CLOUDCONVERT_API_KEY", "dummy")

    monkeypatch.setattr(
        "engines.autodesk_dwg.convert",
        AsyncMock(side_effect=AutodeskError("conversion_pending", "pending", fallback_safe=False)),
    )

    async_client = AsyncMock(side_effect=AssertionError("CloudConvert fallback must not run for unknown Autodesk status"))
    monkeypatch.setattr(dwg_convert.httpx, "AsyncClient", async_client)

    with pytest.raises(AutodeskError) as exc:
        await dwg_convert.dwg_to_dxf(_fixture_bytes("public-line-2013.dwg"), user_id="iter154-user")
    assert exc.value.code == "conversion_pending"


@pytest.mark.anyio
async def test_dwg_routing_terminal_failure_falls_back_only_when_flag_true(monkeypatch):
    monkeypatch.setenv("ODA_FILE_CONVERTER", "")
    monkeypatch.setenv("APS_DWG_ENABLED", "true")
    monkeypatch.setenv("APS_ACTIVITY_QUALIFIED", "ns.activity+prod")
    monkeypatch.setenv("CLOUDCONVERT_API_KEY", "dummy")
    monkeypatch.setattr(
        "engines.autodesk_dwg.convert",
        AsyncMock(side_effect=AutodeskError("terminal_failure", "failed", fallback_safe=True)),
    )

    monkeypatch.setenv("APS_DWG_FALLBACK_ENABLED", "false")
    with pytest.raises(AutodeskError) as blocked:
        await dwg_convert.dwg_to_dxf(_fixture_bytes("public-line-2013.dwg"), user_id="iter154-user")
    assert blocked.value.code == "terminal_failure"

    create = SimpleNamespace(
        status_code=200,
        is_success=True,
        json=lambda: {
            "data": {
                "id": "job_fallback",
                "tasks": [{"name": "upload-dwg", "result": {"form": {"url": "https://example.invalid/upload", "parameters": {}}}}],
            }
        },
    )
    upload = SimpleNamespace(status_code=200, is_success=True)
    waited = SimpleNamespace(
        status_code=200,
        is_success=True,
        json=lambda: {
            "data": {
                "status": "finished",
                "tasks": [{"name": "export-dxf", "result": {"files": [{"url": "https://example.invalid/result"}]}}],
            }
        },
    )

    class _Stream:
        is_success = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_bytes(self):
            yield b"0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n"

    client = SimpleNamespace(
        post=AsyncMock(side_effect=[create, upload]),
        get=AsyncMock(return_value=waited),
        delete=AsyncMock(),
        stream=lambda *_args, **_kwargs: _Stream(),
    )
    cm = AsyncMock()
    cm.__aenter__.return_value = client

    monkeypatch.setenv("APS_DWG_FALLBACK_ENABLED", "true")
    monkeypatch.setattr(dwg_convert.httpx, "AsyncClient", lambda **_kwargs: cm)

    result = await dwg_convert.dwg_to_dxf(_fixture_bytes("public-line-2013.dwg"), user_id="iter154-user")
    assert b"SECTION" in result
    client.delete.assert_awaited_once()
