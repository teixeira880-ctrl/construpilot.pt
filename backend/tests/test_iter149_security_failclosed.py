"""iter149: fail-closed permission/site security validation (live + isolated unit checks)."""

import asyncio
import os
import sys
from io import BytesIO
from pathlib import Path

import pytest
import requests
from fastapi import HTTPException

sys.path.append(str(Path(__file__).resolve().parents[1]))

from routes import site as site_routes
from core.permissions import FEATURES, permissions_for, require_feature
from core.security import pro_required


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


def _required_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        pytest.skip(f"Missing {name}")
    return v


def _login(env_prefix: str) -> requests.Session:
    email = _required_env(f"TEST_{env_prefix}_EMAIL")
    password = _required_env(f"TEST_{env_prefix}_PASSWORD")
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {env_prefix}: {r.status_code} {r.text[:300]}"
    body = r.json()
    assert "user" in body
    assert body.get("token") or s.cookies.get("session_token")
    return s


@pytest.fixture(scope="module")
def sessions():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL missing")
    return {
        "pro": _login("PRO"),
        "member": _login("MEMBER"),
        "particulier": _login("PARTICULIER"),
    }


# --- Live endpoint matrix: /api/site requires chantier feature ---
def test_site_reports_access_matrix(sessions):
    noauth = requests.get(f"{BASE_URL}/api/site/reports", timeout=30)
    assert noauth.status_code == 401

    owner = sessions["pro"].get(f"{BASE_URL}/api/site/reports", timeout=30)
    assert owner.status_code == 200
    assert isinstance(owner.json(), list)

    member = sessions["member"].get(f"{BASE_URL}/api/site/reports", timeout=30)
    assert member.status_code == 403

    particulier = sessions["particulier"].get(f"{BASE_URL}/api/site/reports", timeout=30)
    assert particulier.status_code == 403


def test_site_file_unregistered_path_returns_404_for_owner(sessions):
    r = sessions["pro"].get(
        f"{BASE_URL}/api/site/file",
        params={"path": "construpilot/site/non-existent/iter149-missing.jpg"},
        timeout=30,
    )
    assert r.status_code == 404


# --- Live check: invoice creation forbidden before write for member ---
def test_member_doc_access_post_invoice_forbidden_before_writes(sessions):
    member = sessions["member"]
    before = member.get(f"{BASE_URL}/api/documents", timeout=30)
    assert before.status_code == 200
    docs_before = before.json().get("documents", [])
    ids_before = {d.get("doc_id") for d in docs_before}

    forbidden = member.post(
        f"{BASE_URL}/api/documents",
        json={
            "doc_type": "invoice",
            "title": "TEST_ITER149_MEMBER_FORBIDDEN_INVOICE",
            "client": {"name": "Blocked Member"},
            "items": [{"label": "Line", "qty": 1, "unit_price": 10}],
        },
        timeout=30,
    )
    assert forbidden.status_code == 403

    after = member.get(f"{BASE_URL}/api/documents", timeout=30)
    assert after.status_code == 200
    docs_after = after.json().get("documents", [])
    ids_after = {d.get("doc_id") for d in docs_after}
    assert ids_after == ids_before
    assert all(d.get("title") != "TEST_ITER149_MEMBER_FORBIDDEN_INVOICE" for d in docs_after)


# --- Unit policy matrix: unknown roles, inactive workers, deny guards ---
def test_permissions_for_unknown_org_role_is_fail_closed():
    user = {
        "account_type": "pro",
        "organization_id": "org_x",
        "org_role": "mystery_role",
        "company_active": True,
        "active": True,
    }
    perms = permissions_for(user)
    assert set(perms.keys()) == set(FEATURES)
    assert all(v is False for v in perms.values())


def test_permissions_for_inactive_worker_is_fail_closed():
    user = {"role": "worker", "account_type": "pro", "active": False}
    perms = permissions_for(user)
    assert all(v is False for v in perms.values())


def test_pro_required_denies_unknown_org_role_and_inactive_worker():
    with pytest.raises(HTTPException) as unknown_role:
        asyncio.run(pro_required({
            "user_id": "u_unknown",
            "account_type": "pro",
            "organization_id": "org_1",
            "org_role": "ghost",
            "company_active": True,
            "active": True,
            "role": "user",
        }))
    assert unknown_role.value.status_code == 403

    with pytest.raises(HTTPException) as inactive_worker:
        asyncio.run(pro_required({
            "user_id": "w_1",
            "role": "worker",
            "account_type": "pro",
            "active": False,
        }))
    assert inactive_worker.value.status_code == 403


def test_require_feature_blocks_sensitive_company_hr_routes_for_unknown_role():
    user = {
        "user_id": "u_unknown",
        "organization_id": "org_1",
        "org_role": "ghost",
        "account_type": "pro",
        "active": True,
        "company_active": True,
    }
    with pytest.raises(HTTPException) as company_guard:
        require_feature(user, "entreprise")
    assert company_guard.value.status_code == 403

    with pytest.raises(HTTPException) as hr_guard:
        require_feature(user, "rh")
    assert hr_guard.value.status_code == 403


# --- Isolated unit fixture: owned site image retrieval without external providers ---
class _FakeCollection:
    def __init__(self, owned_path: str, key: str):
        self._owned_path = owned_path
        self._key = key

    async def find_one(self, query, projection=None):
        if query.get("photos") == self._owned_path and query.get("user_id") == "owner_u":
            return {self._key: "rec_1"}
        return None


class _FakeDB:
    def __init__(self, owned_path: str):
        self.site_reports = _FakeCollection(owned_path, "report_id")
        self.site_reserves = _FakeCollection(owned_path, "reserve_id")


def _read_streaming_response(resp) -> bytes:
    chunks = []

    async def _collect():
        async for chunk in resp.body_iterator:
            chunks.append(chunk)

    asyncio.run(_collect())
    return b"".join(chunks)


def test_site_file_owned_image_returns_private_no_store(monkeypatch):
    path = "construpilot/site/owner_u/reports/photo.jpg"
    monkeypatch.setattr(site_routes, "db", _FakeDB(path))

    class _Storage:
        @staticmethod
        def get_object(_path):
            assert _path == path
            return (b"image-bytes", "image/jpeg")

    monkeypatch.setattr(site_routes, "storage", _Storage)
    resp = asyncio.run(site_routes.serve_file(path=path, user={"user_id": "owner_u"}))
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "private, no-store"
    assert _read_streaming_response(resp) == b"image-bytes"


def test_site_file_other_or_unregistered_photo_returns_404(monkeypatch):
    path = "construpilot/site/owner_u/reports/photo.jpg"
    monkeypatch.setattr(site_routes, "db", _FakeDB(path))

    class _Storage:
        @staticmethod
        def get_object(_path):
            return (BytesIO(b"unused").getvalue(), "image/jpeg")

    monkeypatch.setattr(site_routes, "storage", _Storage)
    with pytest.raises(HTTPException) as not_found:
        asyncio.run(site_routes.serve_file(path="construpilot/site/other/photo.jpg", user={"user_id": "owner_u"}))
    assert not_found.value.status_code == 404
