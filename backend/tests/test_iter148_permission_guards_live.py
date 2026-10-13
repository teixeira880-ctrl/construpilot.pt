"""Iter148 live permission guards: pro/member/particulier/worker access policy checks."""
import os
import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


if not BASE_URL:
    pytest.skip("REACT_APP_BACKEND_URL not set", allow_module_level=True)


ACCOUNTS = {
    name: (os.environ[f"TEST_{name.upper()}_EMAIL"], os.environ[f"TEST_{name.upper()}_PASSWORD"])
    for name in ("pro", "member", "particulier", "worker")
}


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    resp = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=25)
    assert resp.status_code == 200, f"login failed for {email}: {resp.status_code}"
    body = resp.json()
    assert "user" in body
    assert ("token" in body and body["token"]) or s.cookies.get("session_token")
    return s


@pytest.fixture(scope="module")
def sessions():
    return {name: _login(*creds) for name, creds in ACCOUNTS.items()}


def test_member_company_permissions_contract(sessions):
    r = sessions["member"].get(f"{BASE_URL}/api/company/me", timeout=25)
    assert r.status_code == 200
    data = r.json()
    assert data["role"] == "member"
    assert data["active"] is True
    assert data["permissions"]["dashboard"] is True
    assert data["permissions"]["devis"] is True
    assert data["permissions"]["factures"] is False
    assert data["permissions"]["situations"] is False
    assert data["permissions"]["rh"] is False


@pytest.mark.parametrize(
    "path",
    [
        "/api/company/dashboard",
        "/api/company/activity",
        "/api/hr/workers",
        "/api/einvoicing/status",
        "/api/situations/marches",
        "/api/pro/profitability",
    ],
)
def test_member_forbidden_on_sensitive_features(sessions, path):
    r = sessions["member"].get(f"{BASE_URL}{path}", timeout=25)
    assert r.status_code == 403


def test_member_documents_invoice_forbidden_quote_allowed(sessions):
    member = sessions["member"]
    invoice = member.get(f"{BASE_URL}/api/documents", params={"doc_type": "invoice"}, timeout=25)
    assert invoice.status_code == 403

    quote = member.get(f"{BASE_URL}/api/documents", params={"doc_type": "quote"}, timeout=25)
    assert quote.status_code == 200
    payload = quote.json()
    assert isinstance(payload.get("documents"), list)

    default_list = member.get(f"{BASE_URL}/api/documents", timeout=25)
    assert default_list.status_code == 200
    docs = default_list.json().get("documents", [])
    assert all(d.get("doc_type") != "invoice" for d in docs)


@pytest.mark.parametrize(
    "path",
    [
        "/api/company/me",
        "/api/documents",
        "/api/hr/workers",
        "/api/einvoicing/status",
        "/api/situations/marches",
        "/api/pro/profitability",
    ],
)
def test_particulier_fail_closed_on_pro_routes(sessions, path):
    r = sessions["particulier"].get(f"{BASE_URL}{path}", timeout=25)
    assert r.status_code == 403


def test_worker_own_pointage_allowed_but_hr_admin_denied(sessions):
    worker = sessions["worker"]
    status = worker.get(f"{BASE_URL}/api/hr/me/status", timeout=25)
    assert status.status_code == 200
    assert "open" in status.json()

    list_workers = worker.get(f"{BASE_URL}/api/hr/workers", timeout=25)
    assert list_workers.status_code == 403


def test_owner_company_routes_and_member_doc_isolation(sessions):
    pro = sessions["pro"]
    member = sessions["member"]

    me = pro.get(f"{BASE_URL}/api/company/me", timeout=25)
    assert me.status_code == 200
    assert me.json()["permissions"]["factures"] is True

    activity = pro.get(f"{BASE_URL}/api/company/activity", timeout=25)
    assert activity.status_code == 200
    assert isinstance(activity.json(), list)

    pro_docs = pro.get(f"{BASE_URL}/api/documents", params={"doc_type": "quote"}, timeout=25)
    assert pro_docs.status_code == 200
    docs = pro_docs.json().get("documents", [])
    if not docs:
        pytest.skip("No pro quote found to validate ownership isolation")

    foreign_doc_id = docs[0]["doc_id"]
    member_get = member.get(f"{BASE_URL}/api/documents/{foreign_doc_id}", timeout=25)
    assert member_get.status_code == 404


def test_owner_hr_tier_behavior_observed(sessions):
    r = sessions["pro"].get(f"{BASE_URL}/api/hr/workers", timeout=25)
    assert r.status_code in (200, 402, 403)
