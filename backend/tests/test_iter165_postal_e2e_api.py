"""Iter 165 — E2E API tests for postal payment/tracking (backend live)."""
import os
import re
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")

PRO_EMAIL = os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr")
PRO_PW = os.environ.get("TEST_PRO_PASSWORD", "Pro2026!")


@pytest.fixture(scope="module")
def pro_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": PRO_EMAIL, "password": PRO_PW})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(pro_token):
    return {"Authorization": f"Bearer {pro_token}"}


# -------- postal status --------
def test_postal_status_contract(h):
    r = requests.get(f"{BASE_URL}/api/radar/postal/status", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("configured") is True
    offer = data.get("offer") or {}
    print("STATUS offer:", offer)
    assert offer.get("phase") == "demo"
    assert offer.get("demo_limit") == 20
    assert "demo_remaining" in offer
    assert "credits" in offer
    assert offer.get("next_kind") == "demo"
    assert offer.get("customer_amount_cents") == 0
    assert offer.get("unit_price_net_cents") == 2000
    assert offer.get("unit_price_gross_cents") == 2400
    assert offer.get("paid_enabled") is True
    packs = offer.get("packs") or []
    assert len(packs) == 2
    ids = {p.get("pack_id") or p.get("id"): p for p in packs}
    assert ids["pack5"].get("amount_net_cents", ids["pack5"].get("price_net_cents")) == 10000
    assert ids["pack5"].get("amount_gross_cents", ids["pack5"].get("price_gross_cents")) == 12000
    assert ids["pack10"].get("amount_net_cents", ids["pack10"].get("price_net_cents")) == 20000
    assert ids["pack10"].get("amount_gross_cents", ids["pack10"].get("price_gross_cents")) == 24000


# -------- credits checkout --------
def test_credits_checkout_pack5(h):
    r = requests.post(
        f"{BASE_URL}/api/radar/postal/credits/checkout",
        headers=h,
        json={"pack_id": "pack5", "origin_url": f"{BASE_URL}/radar"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    print("CHECKOUT pack5:", {k: data.get(k) for k in ("url", "session_id", "amount_cents")})
    assert data.get("amount_cents") == 12000
    assert data.get("session_id", "").startswith("cs_test_")
    assert "stripe" in (data.get("url") or "")
    pytest.session_id_pack5 = data["session_id"]
    pytest.checkout_url_pack5 = data["url"]


def test_credits_checkout_invalid_pack(h):
    r = requests.post(
        f"{BASE_URL}/api/radar/postal/credits/checkout",
        headers=h,
        json={"pack_id": "packX", "origin_url": f"{BASE_URL}/radar"},
    )
    assert r.status_code == 400, r.text


# -------- payment view --------
def test_payment_view_pending(h):
    sid = getattr(pytest, "session_id_pack5", None)
    if not sid:
        pytest.skip("no session id from previous test")
    r = requests.get(f"{BASE_URL}/api/radar/postal/payment/{sid}", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    print("PAYMENT VIEW pending:", data)
    assert data.get("type") == "postal_credits"
    assert data.get("payment_status") == "pending"
    assert data.get("fulfillment") == "pending"
    assert "offer" in data


def test_payment_view_unknown(h):
    r = requests.get(f"{BASE_URL}/api/radar/postal/payment/cs_test_unknown_xxxxx", headers=h)
    assert r.status_code == 404


# -------- postal sends & tracking refresh --------
def test_postal_sends_list(h):
    r = requests.get(f"{BASE_URL}/api/radar/postal/sends", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "sends" in data and isinstance(data["sends"], list)
    print("SENDS count:", len(data["sends"]))


def test_postal_tracking_refresh(h):
    r = requests.post(f"{BASE_URL}/api/radar/postal/tracking/refresh", headers=h)
    assert r.status_code == 200, r.text
    data = r.json()
    print("REFRESH:", data)
    assert "refreshed" in data and "errors" in data


# -------- prospection postal checkout (409 postal_free_available) --------
def test_prospection_postal_checkout_conflict(h):
    # find an existing campaign token
    r = requests.get(f"{BASE_URL}/api/radar/campaigns", headers=h)
    if r.status_code != 200:
        pytest.skip(f"no campaigns endpoint accessible: {r.status_code}")
    try:
        camps = r.json()
        camps = camps.get("campaigns", camps) if isinstance(camps, dict) else camps
    except Exception:
        pytest.skip("cannot parse campaigns")
    if not camps:
        pytest.skip("no campaign for pro")
    token = None
    for c in camps:
        token = c.get("token") or c.get("share_token") or c.get("public_token")
        if token:
            break
    if not token:
        pytest.skip("no campaign token available")
    # request quote
    qr = requests.post(
        f"{BASE_URL}/api/radar/prospection/{token}/postal/quote",
        headers=h, json={"mode": "normal"}
    )
    if qr.status_code != 200:
        pytest.skip(f"quote endpoint returned {qr.status_code}: {qr.text[:200]}")
    quote = qr.json()
    quote_id = quote.get("quote_id") or quote.get("id")
    if not quote_id:
        pytest.skip("no quote_id from quote endpoint")
    r2 = requests.post(
        f"{BASE_URL}/api/radar/prospection/{token}/postal/checkout",
        headers=h, json={"quote_id": quote_id, "origin_url": f"{BASE_URL}/radar"}
    )
    print("PROSPECTION CHECKOUT:", r2.status_code, r2.text[:200])
    assert r2.status_code == 409
    body = r2.json()
    assert (body.get("detail") or {}).get("code") == "postal_free_available" or body.get("code") == "postal_free_available"
