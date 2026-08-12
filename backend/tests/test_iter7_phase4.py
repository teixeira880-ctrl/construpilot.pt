"""Iter 7 (Phase 4) — API commerciale, KYC pros, Portail pro, Affiliation."""
import os
import uuid
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or "https://cmrenov-ai.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}


def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(creds):
    s = _sess()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _register():
    s = _sess()
    email = f"iter7_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register",
               json={"name": "Iter7 User", "email": email, "password": "Passw0rd!"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"email": email, "token": r.json()["token"], "user": r.json()["user"]}


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def user():
    return _register()


@pytest.fixture(scope="module")
def user2():
    return _register()


# =============== 1. Plans regression (11 plans) ===============
def test_plans_include_api():
    r = requests.get(f"{API}/plans", timeout=15)
    assert r.status_code == 200
    plans = r.json()
    if isinstance(plans, dict):
        plans = plans.get("plans", [])
    ids = {p["plan_id"] for p in plans}
    assert {"api_starter", "api_business", "api_scale"}.issubset(ids)
    # 11 total (8 + 3)
    assert len(plans) >= 11, f"expected >=11 plans got {len(plans)} : {ids}"


# =============== 2. API Keys (admin bypass, user 402, CRUD) ===============
def test_api_key_user_without_entitlement_402(user):
    r = requests.post(f"{API}/api-keys",
                      json={"plan_id": "api_starter", "name": "X"},
                      headers=_h(user["token"]), timeout=15)
    assert r.status_code == 402, r.text


@pytest.fixture(scope="module")
def admin_api_key(admin_token):
    r = requests.post(f"{API}/api-keys",
                      json={"plan_id": "api_starter", "name": "TEST_iter7"},
                      headers=_h(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["key"].startswith("ckp_live_")
    assert d["prefix"].startswith("ckp_live_")
    return d


def test_admin_can_create_key(admin_api_key):
    assert admin_api_key["plan_id"] == "api_starter"
    assert admin_api_key["active"] is True


def test_list_keys_masked(admin_token, admin_api_key):
    r = requests.get(f"{API}/api-keys", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    keys = r.json()
    assert isinstance(keys, list) and len(keys) >= 1
    found = [k for k in keys if k["prefix"] == admin_api_key["prefix"]]
    assert found, "created key not in list"
    k = found[0]
    assert "key_masked" in k
    assert "key" not in k  # full key not exposed


# =============== 3. Public API (X-API-Key) ===============
def test_public_estimation_no_header():
    r = requests.post(f"{API}/v1/public/estimation",
                      json={"project_type": "renovation_complete", "surface": 60},
                      timeout=15)
    assert r.status_code == 401


def test_public_estimation_bad_key():
    r = requests.post(f"{API}/v1/public/estimation",
                      json={"project_type": "renovation_complete", "surface": 60},
                      headers={"X-API-Key": "wrong"}, timeout=15)
    assert r.status_code == 401


def test_public_estimation_ok(admin_api_key):
    r = requests.post(f"{API}/v1/public/estimation",
                      json={"project_type": "renovation_complete", "surface": 60},
                      headers={"X-API-Key": admin_api_key["key"]}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "data" in d and "meta" in d
    assert d["meta"]["plan_id"] == "api_starter"


def test_public_prices_ok(admin_api_key):
    r = requests.post(f"{API}/v1/public/prices",
                      json={"query": "carrelage", "limit": 3},
                      headers={"X-API-Key": admin_api_key["key"]}, timeout=60)
    assert r.status_code == 200, r.text
    assert "data" in r.json()


def test_public_calculators_ok(admin_api_key):
    r = requests.post(f"{API}/v1/public/calculators",
                      json={"kind": "paint", "params": {"length": 4, "width": 3, "height": 2.5}},
                      headers={"X-API-Key": admin_api_key["key"]}, timeout=15)
    assert r.status_code == 200, r.text
    assert "data" in r.json()


def test_usage_incremented(admin_token, admin_api_key):
    r = requests.get(f"{API}/api-keys", headers=_h(admin_token), timeout=15)
    key = next(k for k in r.json() if k["prefix"] == admin_api_key["prefix"])
    assert key.get("monthly_usage"), f"monthly_usage empty: {key}"
    # Some month bucket should be >0
    total = sum(int(v) for v in key["monthly_usage"].values())
    assert total >= 3


# =============== 4. Rotate + Revoke ===============
def test_rotate_key(admin_token, admin_api_key):
    r = requests.post(f"{API}/api-keys/{admin_api_key['prefix']}/rotate",
                      headers=_h(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["prefix"] != admin_api_key["prefix"]
    assert new["key"].startswith("ckp_live_")
    admin_api_key["prefix"] = new["prefix"]  # for downstream
    admin_api_key["key"] = new["key"]


def test_revoke_key(admin_token, admin_api_key):
    r = requests.delete(f"{API}/api-keys/{admin_api_key['prefix']}",
                        headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    # After revoke, calls should 401
    r2 = requests.post(f"{API}/v1/public/estimation",
                       json={"project_type": "renovation_complete", "surface": 60},
                       headers={"X-API-Key": admin_api_key["key"]}, timeout=15)
    assert r2.status_code == 401


# =============== 5. KYC ===============
def test_kyc_invalid_siren(user):
    r = requests.post(f"{API}/marketplace/kyc",
                      json={"siren": "12345", "company_name": "TestCo"},
                      headers=_h(user["token"]), timeout=15)
    assert r.status_code == 400


def test_kyc_submit_ok(user):
    r = requests.post(f"{API}/marketplace/kyc",
                      json={"siren": "814152528", "company_name": "TEST_Iter7Pro",
                            "rc_pro_insurer": "AXA", "rc_pro_number": "RC123",
                            "decennale_insurer": "MAAF", "decennale_number": "DEC456",
                            "trades": ["plomberie"], "zones": ["75"], "years_experience": 8},
                      headers=_h(user["token"]), timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"


def test_kyc_me(user):
    r = requests.get(f"{API}/marketplace/kyc/me",
                     headers=_h(user["token"]), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "pending"
    assert d["company_name"] == "TEST_Iter7Pro"


def test_kyc_admin_list(admin_token):
    r = requests.get(f"{API}/admin/kyc?status=pending",
                     headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_kyc_admin_approve(admin_token, user):
    r = requests.post(f"{API}/admin/kyc/review",
                      json={"user_id": user["user"]["user_id"], "approve": True},
                      headers=_h(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "verified"
    # Verify persistence
    r2 = requests.get(f"{API}/marketplace/kyc/me",
                      headers=_h(user["token"]), timeout=15)
    d = r2.json()
    assert d["verified"] is True
    assert d["badge"] == "ConstruPilot Verified"


# =============== 6. Pro Portal ===============
def test_pro_me_unregistered(user2):
    r = requests.get(f"{API}/pro/me", headers=_h(user2["token"]), timeout=15)
    assert r.status_code == 200
    assert r.json()["registered"] is False


def test_pro_me_verified(user):
    r = requests.get(f"{API}/pro/me", headers=_h(user["token"]), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["registered"] is True
    assert d["verified"] is True
    assert d["badge"] == "ConstruPilot Verified"
    assert d["credits_cents"] == 0
    assert d["leads_bought"] == []


def test_pro_credits_checkout_unverified(user2):
    r = requests.post(f"{API}/pro/credits/checkout",
                      json={"amount_cents": 5000, "origin_url": BASE_URL},
                      headers=_h(user2["token"]), timeout=30)
    assert r.status_code == 403


@pytest.mark.parametrize("amount,expected_bonus", [
    (5000, 0),
    (25000, 1250),
    (50000, 5000),
])
def test_pro_credits_checkout_amounts(user, amount, expected_bonus):
    r = requests.post(f"{API}/pro/credits/checkout",
                      json={"amount_cents": amount, "origin_url": BASE_URL},
                      headers=_h(user["token"]), timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["url"].startswith("https://checkout.stripe.com")
    assert d["session_id"]
    assert d["bonus_cents"] == expected_bonus


def test_marketplace_leads_buy_insufficient_credits(user):
    # Create a lead as anon
    lead_payload = {"name": "TEST Buyer",
                    "email": f"lead_{uuid.uuid4().hex[:6]}@example.com",
                    "phone": "+33612345678",
                    "description": "Rénovation salle de bain 8m2 urgente",
                    "budget": 20000, "address": "Paris 75011"}
    lr = requests.post(f"{API}/marketplace/leads", json=lead_payload, timeout=15)
    # Endpoint may be public — accept 200 or 401 depending on impl
    if lr.status_code == 200:
        r = requests.post(f"{API}/marketplace/leads/buy",
                          json={"lead_id": lr.json().get("lead_id", "any")},
                          headers=_h(user["token"]), timeout=15)
        assert r.status_code in (402, 400, 404), r.text
    else:
        pytest.skip(f"marketplace/leads create returned {lr.status_code}")


# =============== 7. Affiliate ===============
def test_affiliate_click():
    r = requests.post(f"{API}/affiliate/click",
                      json={"supplier_key": "leroymerlin",
                            "product_url": "https://www.leroymerlin.fr/produit/x",
                            "query": "laine de verre"}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("click_id")


def test_affiliate_redirect_lm():
    r = requests.get(f"{API}/r/aff/leroymerlin",
                     params={"url": "https://www.leroymerlin.fr/p/xyz"},
                     allow_redirects=False, timeout=15)
    assert r.status_code == 302
    loc = r.headers.get("location", "")
    assert "track.awin.com" in loc, f"loc={loc}"


def test_admin_affiliate_configs(admin_token):
    r = requests.get(f"{API}/admin/affiliate/configs",
                     headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    cfgs = r.json()
    keys = {c["supplier_key"] for c in cfgs}
    assert {"leroymerlin", "manomano", "castorama"}.issubset(keys)


def test_admin_affiliate_config_update(admin_token):
    r = requests.post(f"{API}/admin/affiliate/configs",
                      json={"supplier_key": "castorama", "affiliate_enabled": False,
                            "commission_rate": 0.02, "cookie_duration": 30},
                      headers=_h(admin_token), timeout=15)
    assert r.status_code == 200


def test_admin_affiliate_stats(admin_token):
    r = requests.get(f"{API}/admin/affiliate/stats?days=30",
                     headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert "totals" in d and "by_supplier" in d and "revenue_eur" in d


def test_prices_search_enriched():
    r = requests.post(f"{API}/prices/search",
                      json={"query": "laine de verre", "limit": 20}, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data if isinstance(data, list) else data.get("results") or data.get("offers") or data.get("items") or []
    if not items:
        pytest.skip(f"no items returned: {data}")
    by_supplier = {}
    for it in items:
        by_supplier.setdefault(it.get("supplier_key"), []).append(it)
    # Leroy Merlin and ManoMano should be affiliate=True with tracking_url
    for key in ("leroymerlin", "manomano"):
        if key in by_supplier:
            sample = by_supplier[key][0]
            assert sample.get("is_affiliate") is True, f"{key} not affiliate: {sample}"
            assert sample.get("tracking_url")
            assert sample.get("affiliate_disclosure")
    if "castorama" in by_supplier:
        assert by_supplier["castorama"][0].get("is_affiliate") is False


# =============== 8. Regression ===============
def test_regression_login_admin(admin_token):
    r = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_regression_estimation_compute():
    r = requests.post(f"{API}/estimation/compute",
                      json={"project_type": "renovation_complete", "surface": 80,
                            "finish_level": "standard"}, timeout=30)
    assert r.status_code == 200
    assert r.json()["total_avg"] > 0
