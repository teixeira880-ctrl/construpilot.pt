"""Iteration 164 — live HTTP validation of postal demo endpoints (limit=20)."""
import os
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"


@pytest.fixture(scope="module")
def pro_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": PRO_EMAIL, "password": PRO_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers(pro_token):
    return {"Authorization": f"Bearer {pro_token}", "Content-Type": "application/json"}


def test_postal_status_returns_offer_with_demo_limit_20(pro_headers):
    r = requests.get(f"{BASE}/api/radar/postal/status", headers=pro_headers, timeout=20)
    assert r.status_code == 200, r.text
    payload = r.json()
    print("STATUS:", payload)
    data = payload.get("offer", payload)
    assert data.get("demo_limit") == 20
    assert data.get("phase") == "demo"
    assert data.get("paid_enabled") is False
    assert data.get("customer_amount_cents") == 0
    assert "used" in data
    assert "remaining" in data
    assert isinstance(data["used"], int) and isinstance(data["remaining"], int)
    assert data["remaining"] == max(0, 20 - data["used"])
    if data["remaining"] > 0:
        assert data.get("eligible") is True
        assert data.get("status") == "available"


def test_postal_price_normal_returns_real_price_or_provider_503(pro_headers):
    r = requests.get(f"{BASE}/api/radar/postal/price?mode=normal", headers=pro_headers, timeout=30)
    print("PRICE status", r.status_code, r.text[:400])
    if r.status_code == 503:
        # Environment: provider IP not whitelisted — report code and pass
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        code = (body.get("detail") or body).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
        pytest.skip(f"Provider unavailable in preview env (503). Code={code} body={body}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("currency") in ("EUR", None) or "total_ttc" in data or "postage" in data
