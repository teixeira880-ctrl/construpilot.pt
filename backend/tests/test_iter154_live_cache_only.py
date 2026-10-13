"""Iter154 live cache-only DWG import verification (no new Autodesk workitem allowed)."""
import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pymongo
import pytest
import requests
from dotenv import load_dotenv

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD")
EXPECTED_USER_ID = "user_1d2b550f454f"
FIXTURE_PATH = Path("/app/integration/revision3/fixtures/public-line-2013.dwg")
FIXTURE_SHA256 = "3815af3bfe9a0d45c1ce764a37871104eff791dd95cd095b338cc24863baa66f"
FIXTURE_SIZE = 16331


def _frontend_base_url() -> str:
    env_path = Path("/app/frontend/.env")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().rstrip("/")
    raise AssertionError("REACT_APP_BACKEND_URL missing in frontend/.env")


def _mongo_db():
    if not os.environ.get("MONGO_URL") or not os.environ.get("DB_NAME"):
        load_dotenv("/app/backend/.env")
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    assert mongo_url and db_name, "MONGO_URL/DB_NAME must be configured"
    client = pymongo.MongoClient(mongo_url)
    return client, client[db_name]


def _rebuild_cad_bytes(collection, plan_id: str, user_id: str, source_kind: str) -> bytes:
    chunks = list(collection.find(
        {"plan_id": plan_id, "user_id": user_id, "source_kind": source_kind},
        {"_id": 0, "index": 1, "chunk_count": 1, "data_b64": 1, "size_bytes": 1, "sha256": 1},
    ).sort("index", 1))
    assert chunks, f"Missing plan_cad_sources chunks for {plan_id}/{source_kind}"
    expected = int(chunks[0].get("chunk_count") or len(chunks))
    assert [c["index"] for c in chunks] == list(range(expected)), "Chunk index gap/duplicate"
    payload = b"".join(base64.b64decode(c["data_b64"]) for c in chunks)
    assert len(payload) == chunks[0]["size_bytes"]
    assert hashlib.sha256(payload).hexdigest() == chunks[0]["sha256"]
    return payload


def _auth_headers(base_url: str) -> dict:
    assert ADMIN_EMAIL and ADMIN_PASSWORD, "TEST_ADMIN_EMAIL and TEST_ADMIN_PASSWORD are required for opted-in live tests"
    login = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Admin login failed: {login.status_code}"
    token = login.json().get("token")
    assert token and isinstance(token, str)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.skipif(os.environ.get("RUN_APS_CACHE_ONLY_TEST") != "1", reason="Live import requires explicit opt-in and an unexpired existing cache")
def test_live_upload_reuses_existing_autodesk_cache_without_new_workitem():
    assert ADMIN_EMAIL and ADMIN_PASSWORD, "Live test credentials must come from environment"
    base_url = _frontend_base_url()
    fixture = FIXTURE_PATH.read_bytes()
    assert len(fixture) == FIXTURE_SIZE
    assert hashlib.sha256(fixture).hexdigest() == FIXTURE_SHA256

    mongo_client, db = _mongo_db()
    try:
        admin = db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "user_id": 1})
        assert admin and admin.get("user_id") == EXPECTED_USER_ID

        job_key = hashlib.sha256(f"{EXPECTED_USER_ID}:dwg-to-dxf:{FIXTURE_SHA256}".encode()).hexdigest()
        before = db.cad_conversion_jobs.find_one({"_id": job_key}, {"_id": 0})
        assert before, "Existing Autodesk job missing"
        assert before.get("status") == "success", f"Unexpected pre-status: {before.get('status')}"
        assert before.get("cache_id"), "Missing cache_id in precondition"
        assert before.get("cleanup_pending") is False

        exp = before.get("cache_expires_at")
        assert exp is not None, "cache_expires_at missing"
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        assert exp > datetime.now(timezone.utc) + timedelta(minutes=10), "STOP: cache near expiry; no live upload allowed"

        pre_workitem_id = before.get("workitem_id")
        pre_attempt_id = before.get("attempt_id")
        pre_job_id = before.get("job_id")
        pre_count = db.cad_conversion_jobs.count_documents({"_id": job_key})
        assert pre_count == 1

        cached_dxf = _rebuild_cad_bytes(db.plan_cad_sources, before["cache_id"], EXPECTED_USER_ID, "converted_dxf")
        assert hashlib.sha256(cached_dxf).hexdigest() == before["provenance"]["output_sha256"]

        headers = _auth_headers(base_url)
        files = {"file": ("iter154-cache-only-upload.dwg", fixture, "application/acad")}
        upload = requests.post(
            f"{base_url}/api/takeoffs/upload",
            headers=headers,
            files=files,
            timeout=120,
        )
        assert upload.status_code == 200, f"Upload failed: {upload.status_code} {upload.text[:600]}"
        payload = upload.json()

        assert payload["kind"] == "dxf"
        conv = (payload.get("cad_import") or {}).get("conversion") or {}
        assert conv.get("provider") == "autodesk"
        assert conv.get("cached") is True
        assert conv.get("job_id") == pre_job_id
        assert conv.get("format_version") == "AC1032"
        assert conv.get("units_code") == 4

        plan_id = payload["plan_id"]
        assert plan_id and isinstance(plan_id, str)

        plan = requests.get(f"{base_url}/api/takeoffs/{plan_id}", headers=headers, timeout=60)
        assert plan.status_code == 200
        plan_data = plan.json()
        assert plan_data.get("kind") == "dxf"
        page = requests.get(f"{base_url}/api/takeoffs/{plan_id}/page/0", headers=headers, timeout=60)
        assert page.status_code == 200
        page_data = page.json()
        png_b64 = page_data.get("image_png_b64")
        assert png_b64 and len(png_b64) > 100
        assert base64.b64decode(png_b64)

        calib = (plan_data.get("calibrations") or {}).get("0") or {}
        assert float(calib.get("pixels_per_meter", 0)) > 0

        post_original = _rebuild_cad_bytes(db.plan_cad_sources, plan_id, EXPECTED_USER_ID, "original")
        post_converted = _rebuild_cad_bytes(db.plan_cad_sources, plan_id, EXPECTED_USER_ID, "converted_dxf")
        assert hashlib.sha256(post_original).hexdigest() == FIXTURE_SHA256
        assert hashlib.sha256(post_converted).hexdigest() == before["provenance"]["output_sha256"]

        after = db.cad_conversion_jobs.find_one({"_id": job_key}, {"_id": 0})
        assert after
        assert after.get("attempt_id") == pre_attempt_id
        assert after.get("workitem_id") == pre_workitem_id
        assert after.get("job_id") == pre_job_id
        assert db.cad_conversion_jobs.count_documents({"_id": job_key}) == pre_count

        joined = json.dumps({"upload": payload, "plan": plan_data, "page": page_data})
        forbidden = ["APS_CLIENT_ID", "APS_CLIENT_SECRET", "uploadKey", "signeds3", "Bearer "]
        assert not any(token in joined for token in forbidden), "Sensitive marker leaked in API response"
    finally:
        mongo_client.close()
