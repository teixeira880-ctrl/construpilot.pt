"""Iter 231: Backend level gating defense-in-depth.
FREE/null users -> 403 on /api/doc-intel and /api/pro/dpgf; PRO -> 200.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.strip().split("=", 1)[1].rstrip("/")

ACCOUNTS = {
    "null": ("miguel_null_test@construpilot.fr", "Miguel1156."),
    "free": ("client@construpilot.fr", "Client2026!"),
    "pro": ("pro@construpilot.fr", "Pro2026!"),
}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("token") or data.get("access_token") or data.get("session_token")
    assert token, f"no token in response for {email}: {list(data.keys())}"
    return token, data.get("user", {})


@pytest.fixture(scope="module")
def tokens():
    return {k: _login(*v) for k, v in ACCOUNTS.items()}


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


def test_null_user_account_type_is_null(tokens):
    _tok, user = tokens["null"]
    assert user.get("account_type") in (None, "null"), f"expected null, got {user.get('account_type')}"


def test_doc_intel_null_forbidden(tokens):
    tok, _ = tokens["null"]
    r = requests.get(f"{BASE_URL}/api/doc-intel", headers=_h(tok), timeout=20)
    assert r.status_code == 403, f"null doc-intel expected 403, got {r.status_code}: {r.text[:200]}"


def test_doc_intel_free_forbidden(tokens):
    tok, _ = tokens["free"]
    r = requests.get(f"{BASE_URL}/api/doc-intel", headers=_h(tok), timeout=20)
    assert r.status_code == 403, f"free doc-intel expected 403, got {r.status_code}"


def test_doc_intel_pro_allowed(tokens):
    tok, _ = tokens["pro"]
    r = requests.get(f"{BASE_URL}/api/doc-intel", headers=_h(tok), timeout=20)
    assert r.status_code == 200, f"pro doc-intel expected 200, got {r.status_code}: {r.text[:200]}"


def test_dpgf_null_forbidden(tokens):
    tok, _ = tokens["null"]
    r = requests.get(f"{BASE_URL}/api/pro/dpgf", headers=_h(tok), timeout=20)
    assert r.status_code == 403, f"null dpgf expected 403, got {r.status_code}"


def test_dpgf_free_forbidden(tokens):
    tok, _ = tokens["free"]
    r = requests.get(f"{BASE_URL}/api/pro/dpgf", headers=_h(tok), timeout=20)
    assert r.status_code == 403, f"free dpgf expected 403, got {r.status_code}"


def test_dpgf_pro_allowed(tokens):
    tok, _ = tokens["pro"]
    r = requests.get(f"{BASE_URL}/api/pro/dpgf", headers=_h(tok), timeout=20)
    assert r.status_code == 200, f"pro dpgf expected 200, got {r.status_code}: {r.text[:200]}"



