"""Iter153 Autodesk DWG/DXF isolated regressions (network mocked, no billable workitem)."""
import copy
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pymongo.errors import DuplicateKeyError

from engines import (
    autodesk_activity,
    autodesk_client,
    autodesk_dwg,
    autodesk_storage,
    autodesk_validation,
)
from engines.autodesk_client import AutodeskError


class Resp:
    """Minimal http response double for isolated tests."""

    def __init__(self, body=None, status_code=200, is_success=True):
        self._body = body if body is not None else {}
        self.status_code = status_code
        self.is_success = is_success

    def json(self):
        return self._body


@pytest.fixture
def aps_env(monkeypatch):
    monkeypatch.setenv("APS_CLIENT_ID", "iter153-client")
    monkeypatch.setenv("APS_CLIENT_SECRET", "iter153-secret")
    monkeypatch.setenv("APS_TOKEN_URL", "https://developer.api.autodesk.com/authentication/v2/token")
    monkeypatch.setenv("APS_AUTOMATION_BASE_URL", "https://developer.api.autodesk.com/da")
    monkeypatch.setenv("APS_AUTOMATION_REGION", "us-east")
    monkeypatch.setenv("APS_OSS_BASE_URL", "https://developer.api.autodesk.com/oss/v2")
    monkeypatch.setenv("APS_ENGINE", "Autodesk.AutoCAD+26_0")
    monkeypatch.setenv("APS_ACTIVITY_ID", "ConstruPilotDwgToDxfV1")
    monkeypatch.setenv("APS_ACTIVITY_ALIAS", "prod")
    monkeypatch.setenv("APS_ACTIVITY_QUALIFIED", "ns.ConstruPilotDwgToDxfV1+prod")
    monkeypatch.setenv("APS_BUCKET_KEY", "iter153-bucket")
    monkeypatch.setenv("APS_DWG_TIMEOUT_SECONDS", "20")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def isolated_db(monkeypatch):
    """Faithful async in-memory DB to avoid motor/loop coupling in isolated tests."""

    def _matches(doc, query):
        for key, value in query.items():
            if key == "$or":
                if not any(_matches(doc, q) for q in value):
                    return False
                continue
            current = doc.get(key)
            if isinstance(value, dict):
                if "$ne" in value and current == value["$ne"]:
                    return False
                if "$lt" in value and not (current is not None and current < value["$lt"]):
                    return False
                if "$exists" in value and ((key in doc) != value["$exists"]):
                    return False
            elif current != value:
                return False
        return True

    def _project(doc, projection):
        if not projection:
            return copy.deepcopy(doc)
        result = copy.deepcopy(doc)
        if projection.get("_id") == 0:
            result.pop("_id", None)
        return result

    class Cursor:
        def __init__(self, rows):
            self.rows = list(rows)

        def sort(self, key, direction):
            self.rows.sort(key=lambda r: r.get(key, 0), reverse=direction < 0)
            return self

        def limit(self, n):
            self.rows = self.rows[:n]
            return self

        def __aiter__(self):
            async def gen():
                for row in self.rows:
                    yield copy.deepcopy(row)
            return gen()

    class Collection:
        def __init__(self):
            self.rows = []

        async def insert_one(self, doc):
            if any(r.get("_id") == doc.get("_id") for r in self.rows if "_id" in doc):
                raise DuplicateKeyError("duplicate _id")
            self.rows.append(copy.deepcopy(doc))

        async def find_one(self, query, projection=None):
            row = next((r for r in self.rows if _matches(r, query)), None)
            return _project(row, projection) if row else None

        def find(self, query, projection=None):
            filtered = [_project(r, projection) for r in self.rows if _matches(r, query)]
            return Cursor(filtered)

        async def update_one(self, query, update):
            row = next((r for r in self.rows if _matches(r, query)), None)
            if not row:
                class Result:
                    modified_count = 0
                    matched_count = 0
                return Result()
            for key, value in update.get("$set", {}).items():
                row[key] = value
            for key in update.get("$unset", {}):
                row.pop(key, None)
            class Result:
                modified_count = 1
                matched_count = 1
            return Result()

        async def update_many(self, query, update):
            matched = 0
            for row in self.rows:
                if _matches(row, query):
                    matched += 1
                    for key, value in update.get("$set", {}).items():
                        row[key] = value
            class Result:
                modified_count = matched
                matched_count = matched
            return Result()

        async def delete_many(self, query):
            before = len(self.rows)
            self.rows = [r for r in self.rows if not _matches(r, query)]
            class Result:
                deleted_count = before - len(self.rows)
            return Result()

    class Namespace:
        cad_conversion_jobs = Collection()
        plan_cad_sources = Collection()
        plan_sources = Collection()
        plan_source_chunks = Collection()

    monkeypatch.setattr(autodesk_dwg, "db", Namespace)
    yield Namespace


def fixture_bytes(name: str) -> bytes:
    return (Path("/app/integration/revision3/fixtures") / name).read_bytes()


def test_signed_url_allowlist_and_validation():
    autodesk_client.check_signed_url("https://signed.s3.amazonaws.com/object")
    autodesk_client.check_signed_url("https://cdn.autodesk.com/file")
    autodesk_client.check_signed_url("https://example.cloudfront.net/asset")
    with pytest.raises(AutodeskError):
        autodesk_client.check_signed_url("http://signed.s3.amazonaws.com/object")
    with pytest.raises(AutodeskError):
        autodesk_client.check_signed_url("https://evil.example.net/object")
    with pytest.raises(AutodeskError):
        autodesk_client.check_signed_url("https://user:pass@s3.amazonaws.com/object")


def test_validation_accepts_reference_dxf_and_keeps_units():
    info = autodesk_validation.inspect_dxf(fixture_bytes("public-line-reference.dxf"))
    assert info["units_code"] == 4
    assert info["entity_count"] == 1
    assert info["layer_count"] >= 2
    assert info["format_version"].startswith("AC")


@pytest.mark.anyio
async def test_storage_upload_complete_and_signed_download_flow(aps_env, monkeypatch):
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/signeds3upload") and method == "GET":
            return Resp({"urls": ["https://bucket.s3.amazonaws.com/in"], "uploadKey": "up-1"})
        if url.endswith("/signeds3upload") and method == "POST":
            return Resp({"status": "ok"})
        if url.endswith("/signeds3download"):
            return Resp({"status": "complete", "url": "https://bucket.s3.amazonaws.com/out"})
        if url.endswith("/details"):
            return Resp({"policyKey": "transient"})
        raise AssertionError(f"Unexpected request {method} {url}")

    put = AsyncMock()
    download = AsyncMock(return_value=b"DXF")
    monkeypatch.setattr(autodesk_storage, "request", fake_request)
    monkeypatch.setattr(autodesk_storage, "signed_put", put)
    monkeypatch.setattr(autodesk_storage, "signed_download", download)

    input_signed_url = await autodesk_storage.upload_input("jobs/j1/input.dwg", b"AC1032bytes")
    assert input_signed_url == "https://bucket.s3.amazonaws.com/out"
    put.assert_awaited_once()

    output = await autodesk_storage.read_output("jobs/j1/result.dxf", "up-1")
    assert output == b"DXF"
    download.assert_awaited_once()
    assert any(m == "POST" and u.endswith("/signeds3upload") for m, u, _ in calls)


@pytest.mark.anyio
async def test_activity_provision_idempotent_namespace_alias_contract(aps_env, monkeypatch):
    expected_def = autodesk_activity.definition()
    captured_urls = []

    async def fake_request(method, url, **kwargs):
        captured_urls.append((method, url, kwargs))
        if url.endswith("/forgeapps/me"):
            return Resp("ns")
        if url.endswith("/activities/ConstruPilotDwgToDxfV1/versions"):
            return Resp({"data": [{"version": 1}]})
        if "/activities/" in url and "%2Bprod" in url and method == "GET":
            return Resp({
                "version": 1,
                "engine": expected_def["engine"],
                "commandLine": expected_def["commandLine"],
                "settings": {"script": {"value": autodesk_activity.SCRIPT}},
            })
        if url.endswith("/activities/ConstruPilotDwgToDxfV1/aliases"):
            return Resp({"data": [{"id": "prod", "version": 1}]})
        raise AssertionError(f"Unexpected request {method} {url}")

    monkeypatch.setattr(autodesk_activity, "request", fake_request)
    monkeypatch.setattr(autodesk_activity, "ensure_bucket", AsyncMock())
    result = await autodesk_activity.provision()

    assert result["created"] is False
    assert result["qualified_activity"] == "ns.ConstruPilotDwgToDxfV1+prod"
    assert any(u.endswith("/activities/ConstruPilotDwgToDxfV1/versions") for _, u, _ in captured_urls)
    assert any("ns.ConstruPilotDwgToDxfV1%2Bprod" in u for _, u, _ in captured_urls)


@pytest.mark.anyio
async def test_convert_same_user_same_bytes_one_post_and_cache_reuse(aps_env, isolated_db, monkeypatch):
    dwg_data = fixture_bytes("public-line-2013.dwg")
    dxf_data = fixture_bytes("public-line-reference.dxf")
    post_calls = {"count": 0}

    async def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/workitems"):
            post_calls["count"] += 1
            return Resp({"id": "work_12345678", "status": "pending"})
        if method == "GET" and "/workitems/" in url:
            return Resp({"status": "success"})
        raise AssertionError(f"Unexpected {method} {url}")

    monkeypatch.setattr(autodesk_dwg, "request", fake_request)
    monkeypatch.setattr(autodesk_dwg.storage, "upload_input", AsyncMock(return_value="https://bucket.s3.amazonaws.com/in"))
    monkeypatch.setattr(autodesk_dwg.storage, "signed_upload", AsyncMock(return_value={"urls": ["https://bucket.s3.amazonaws.com/out"], "uploadKey": "up-1"}))
    monkeypatch.setattr(autodesk_dwg.storage, "read_output", AsyncMock(return_value=dxf_data))
    monkeypatch.setattr(autodesk_dwg.storage, "delete_objects", AsyncMock(return_value=True))

    first_output, first_meta = await autodesk_dwg.convert(dwg_data, user_id="iter153-user-a")
    second_output, second_meta = await autodesk_dwg.convert(dwg_data, user_id="iter153-user-a")

    assert post_calls["count"] == 1
    assert first_output == second_output
    assert first_meta["provider"] == "autodesk"
    assert second_meta["cached"] is True
    assert "uploadKey" not in str(first_meta)
    assert "Bearer" not in str(first_meta)


@pytest.mark.anyio
async def test_convert_distinct_users_do_not_share_job_cache(aps_env, isolated_db, monkeypatch):
    dwg_data = fixture_bytes("public-line-2013.dwg")
    dxf_data = fixture_bytes("public-line-reference.dxf")
    post_calls = {"count": 0}

    async def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/workitems"):
            post_calls["count"] += 1
            return Resp({"id": f"work_{post_calls['count']}123456", "status": "pending"})
        if method == "GET" and "/workitems/" in url:
            return Resp({"status": "success"})
        raise AssertionError(f"Unexpected {method} {url}")

    monkeypatch.setattr(autodesk_dwg, "request", fake_request)
    monkeypatch.setattr(autodesk_dwg.storage, "upload_input", AsyncMock(return_value="https://bucket.s3.amazonaws.com/in"))
    monkeypatch.setattr(autodesk_dwg.storage, "signed_upload", AsyncMock(return_value={"urls": ["https://bucket.s3.amazonaws.com/out"], "uploadKey": "up-1"}))
    monkeypatch.setattr(autodesk_dwg.storage, "read_output", AsyncMock(return_value=dxf_data))
    monkeypatch.setattr(autodesk_dwg.storage, "delete_objects", AsyncMock(return_value=True))

    out_a, meta_a = await autodesk_dwg.convert(dwg_data, user_id="iter153-user-a")
    out_b, meta_b = await autodesk_dwg.convert(dwg_data, user_id="iter153-user-b")

    assert post_calls["count"] == 2
    assert out_a == out_b
    assert meta_a["job_id"] != meta_b["job_id"]


@pytest.mark.anyio
async def test_unknown_post_receipt_never_resubmits_same_user_bytes(aps_env, isolated_db, monkeypatch):
    dwg_data = fixture_bytes("public-line-2013.dwg")
    post_calls = {"count": 0}

    async def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/workitems"):
            post_calls["count"] += 1
            return Resp({"status": "pending"})  # malformed receipt: no id
        raise AssertionError(f"Unexpected {method} {url}")

    monkeypatch.setattr(autodesk_dwg, "request", fake_request)
    monkeypatch.setattr(autodesk_dwg.storage, "upload_input", AsyncMock(return_value="https://bucket.s3.amazonaws.com/in"))
    monkeypatch.setattr(autodesk_dwg.storage, "signed_upload", AsyncMock(return_value={"urls": ["https://bucket.s3.amazonaws.com/out"], "uploadKey": "up-1"}))
    monkeypatch.setattr(autodesk_dwg.storage, "delete_objects", AsyncMock(return_value=True))

    with pytest.raises(AutodeskError) as first:
        await autodesk_dwg.convert(dwg_data, user_id="iter153-user-unknown")
    with pytest.raises(AutodeskError) as second:
        await autodesk_dwg.convert(dwg_data, user_id="iter153-user-unknown")

    assert first.value.code == "conversion_pending"
    assert second.value.code == "conversion_pending"
    assert post_calls["count"] == 1


@pytest.mark.anyio
async def test_prepare_failure_marks_failed_before_submit_and_allows_retry(aps_env, isolated_db, monkeypatch):
    dwg_data = fixture_bytes("public-line-2013.dwg")
    dxf_data = fixture_bytes("public-line-reference.dxf")
    post_calls = {"count": 0}

    async def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/workitems"):
            post_calls["count"] += 1
            return Resp({"id": "work_retry1234", "status": "pending"})
        if method == "GET" and "/workitems/" in url:
            return Resp({"status": "success"})
        raise AssertionError(f"Unexpected {method} {url}")

    upload_input = AsyncMock(side_effect=[RuntimeError("prep failed"), "https://bucket.s3.amazonaws.com/in"])
    monkeypatch.setattr(autodesk_dwg, "request", fake_request)
    monkeypatch.setattr(autodesk_dwg.storage, "upload_input", upload_input)
    monkeypatch.setattr(autodesk_dwg.storage, "signed_upload", AsyncMock(return_value={"urls": ["https://bucket.s3.amazonaws.com/out"], "uploadKey": "up-1"}))
    monkeypatch.setattr(autodesk_dwg.storage, "read_output", AsyncMock(return_value=dxf_data))
    monkeypatch.setattr(autodesk_dwg.storage, "delete_objects", AsyncMock(return_value=True))

    with pytest.raises(AutodeskError) as failed:
        await autodesk_dwg.convert(dwg_data, user_id="iter153-user-prep")
    assert failed.value.code == "preparation_failed"

    out, meta = await autodesk_dwg.convert(dwg_data, user_id="iter153-user-prep")
    assert len(out) > 0
    assert meta["provider"] == "autodesk"
    assert post_calls["count"] == 1


@pytest.mark.anyio
async def test_provider_denied_4xx_marks_rejected_without_workitem(aps_env, isolated_db, monkeypatch):
    dwg_data = fixture_bytes("public-line-2013.dwg")

    async def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/workitems"):
            raise AutodeskError("provider_http_error", "denied", fallback_safe=True, status=403)
        raise AssertionError(f"Unexpected {method} {url}")

    monkeypatch.setattr(autodesk_dwg, "request", fake_request)
    monkeypatch.setattr(autodesk_dwg.storage, "upload_input", AsyncMock(return_value="https://bucket.s3.amazonaws.com/in"))
    monkeypatch.setattr(autodesk_dwg.storage, "signed_upload", AsyncMock(return_value={"urls": ["https://bucket.s3.amazonaws.com/out"], "uploadKey": "up-1"}))
    monkeypatch.setattr(autodesk_dwg.storage, "delete_objects", AsyncMock(return_value=True))

    with pytest.raises(AutodeskError) as denied:
        await autodesk_dwg.convert(dwg_data, user_id="iter153-user-denied")
    assert denied.value.code == "provider_http_error"

    digest = hashlib.sha256(dwg_data).hexdigest()
    key = hashlib.sha256(f"iter153-user-denied:dwg-to-dxf:{digest}".encode()).hexdigest()
    job = await isolated_db.cad_conversion_jobs.find_one({"_id": key}, {"_id": 0})
    assert job["status"] == "rejected"
    assert "workitem_id" not in job


@pytest.mark.anyio
async def test_terminal_failure_is_not_resubmitted(aps_env, isolated_db, monkeypatch):
    dwg_data = fixture_bytes("public-line-2013.dwg")
    digest = hashlib.sha256(dwg_data).hexdigest()
    key = hashlib.sha256(f"iter153-user-failed:dwg-to-dxf:{digest}".encode()).hexdigest()

    await isolated_db.cad_conversion_jobs.insert_one({
        "_id": key,
        "key": key,
        "attempt_id": "att-1",
        "job_id": "aps_old",
        "user_id": "iter153-user-failed",
        "input_sha256": digest,
        "status": "failed",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "engine": os.environ["APS_ENGINE"],
        "activity": os.environ["APS_ACTIVITY_ID"],
        "workitem_id": "work_old",
    })

    monkeypatch.setattr(autodesk_dwg, "request", AsyncMock(side_effect=AssertionError("must not call APS")))

    with pytest.raises(AutodeskError) as failed:
        await autodesk_dwg.convert(dwg_data, user_id="iter153-user-failed")
    assert failed.value.code == "terminal_failure"


@pytest.mark.anyio
async def test_finish_after_success_returns_cached_without_overwrite(aps_env, isolated_db, monkeypatch):
    dwg_data = fixture_bytes("public-line-2013.dwg")
    dxf_data = fixture_bytes("public-line-reference.dxf")

    async def fake_request(method, url, **kwargs):
        if method == "POST" and url.endswith("/workitems"):
            return Resp({"id": "work_finish1234", "status": "pending"})
        if method == "GET" and "/workitems/" in url:
            return Resp({"status": "success"})
        raise AssertionError(f"Unexpected {method} {url}")

    monkeypatch.setattr(autodesk_dwg, "request", fake_request)
    monkeypatch.setattr(autodesk_dwg.storage, "upload_input", AsyncMock(return_value="https://bucket.s3.amazonaws.com/in"))
    monkeypatch.setattr(autodesk_dwg.storage, "signed_upload", AsyncMock(return_value={"urls": ["https://bucket.s3.amazonaws.com/out"], "uploadKey": "up-1"}))
    monkeypatch.setattr(autodesk_dwg.storage, "read_output", AsyncMock(return_value=dxf_data))
    monkeypatch.setattr(autodesk_dwg.storage, "delete_objects", AsyncMock(return_value=True))

    _, meta = await autodesk_dwg.convert(dwg_data, user_id="iter153-user-finish")
    digest = hashlib.sha256(dwg_data).hexdigest()
    key = hashlib.sha256(f"iter153-user-finish:dwg-to-dxf:{digest}".encode()).hexdigest()
    job = await isolated_db.cad_conversion_jobs.find_one({"_id": key}, {"_id": 0})

    read_output = AsyncMock(side_effect=AssertionError("finish must use cache on success"))
    monkeypatch.setattr(autodesk_dwg.storage, "read_output", read_output)
    cached_bytes, cached_meta = await autodesk_dwg.finish({"key": key, "attempt_id": job["attempt_id"]})

    assert cached_bytes == dxf_data
    assert cached_meta["cached"] is True
    assert cached_meta["output_sha256"] == meta["output_sha256"]
    read_output.assert_not_awaited()