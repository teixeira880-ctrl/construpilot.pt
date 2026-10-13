"""Tests iter6 — Savings, Referral, Marketplace, Promo Codes."""
import os
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"

ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}
DEMO = {"email": "demo@construpilot.fr", "password": "Demo2026!"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


# -------- Savings --------

@pytest.fixture(scope="module")
def sample_estimation():
    payload = {"project_type": "renovation_complete", "surface": 80,
               "finish_level": "standard", "region": "idf"}
    r = requests.post(f"{API}/estimation/compute", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_savings_analyse_public(sample_estimation):
    r = requests.post(f"{API}/savings/analyse",
                      json={"estimation": sample_estimation}, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["items"]) == 4
    keys = {i["key"] for i in d["items"]}
    assert keys == {"materials_optimization", "alternative_materials",
                    "diy_savings", "supplier_optimization"}
    assert d["total"] > 0
    assert d["pct_of_project"] > 0
    assert d["roi_multiplier"] > 0
    assert "ConstruPilot a identifié" in d["message"]


def test_savings_analyse_bad_request():
    r = requests.post(f"{API}/savings/analyse", json={"estimation": {}}, timeout=10)
    assert r.status_code == 400


def test_project_savings_404(demo_token):
    r = requests.get(f"{API}/projects/does-not-exist/savings",
                     headers=_h(demo_token), timeout=10)
    assert r.status_code == 404


# -------- Referral --------

def test_referral_me(demo_token):
    r = requests.get(f"{API}/referral/me", headers=_h(demo_token), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["code"].startswith("CP-")
    assert "credit_eur" in d and "invited" in d and "converted" in d
    assert d["share_url"].startswith("?ref=")


def test_referral_apply_invalid(demo_token):
    r = requests.post(f"{API}/referral/apply", json={"code": "CP-NOPE99"},
                      headers=_h(demo_token), timeout=15)
    assert r.status_code == 400


def test_referral_apply_with_other_user_code(demo_token, admin_token):
    admin_ref = requests.get(f"{API}/referral/me", headers=_h(admin_token), timeout=10).json()
    admin_code = admin_ref["code"]
    # Create a fresh user
    email = f"test_iter6_{int(time.time())}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "Passw0rd!", "name": "Iter6"},
                      timeout=20)
    assert r.status_code in (200, 201), r.text
    new_token = r.json().get("token") or r.json().get("access_token") or _login({"email": email, "password": "Passw0rd!"})
    r = requests.post(f"{API}/referral/apply", json={"code": admin_code},
                      headers=_h(new_token), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] == True
    assert d.get("referee_code")  # promotion_code Stripe généré


# -------- Marketplace --------

def test_marketplace_lead_high_score():
    payload = {
        "name": "Jean Dupont", "email": "jean@example.com", "phone": "0612345678",
        "address": "12 rue du Test 75011 Paris",
        "budget": 45000, "surface": 75, "delay_days": 60,
        "description": ("Rénovation complète appartement : électricité complète refaite, "
                        "plomberie, peinture, carrelage salle de bain, cuisine équipée. "
                        "Projet urgent à démarrer au plus vite."),
        "trade": "general", "photos_count": 3,
    }
    r = requests.post(f"{API}/marketplace/leads", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["score"] >= 80, d
    assert d["tier"] in ("premium", "grand")
    assert d["price_cents"] > 0


def test_marketplace_lead_low_score():
    payload = {"name": "X", "email": "x@example.com", "description": "petit truc"}
    r = requests.post(f"{API}/marketplace/leads", json=payload, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["score"] < 40, d
    assert d["tier"] == "petit"


def test_marketplace_register_gated(demo_token, admin_token):
    # Flip off first
    requests.put(f"{API}/admin/feature-flags", json={"marketplace_enabled": False},
                 headers=_h(admin_token), timeout=15)
    r = requests.post(f"{API}/marketplace/register",
                     json={"company_name": "Test SARL", "email": "pro@x.fr"},
                     headers=_h(demo_token), timeout=15)
    assert r.status_code == 403
    # Enable
    requests.put(f"{API}/admin/feature-flags", json={"marketplace_enabled": True},
                 headers=_h(admin_token), timeout=15)
    r = requests.post(f"{API}/marketplace/register",
                     json={"company_name": "Test SARL", "email": "pro@x.fr"},
                     headers=_h(demo_token), timeout=15)
    assert r.status_code == 200, r.text
    # Reset off
    requests.put(f"{API}/admin/feature-flags", json={"marketplace_enabled": False},
                 headers=_h(admin_token), timeout=15)


def test_marketplace_pros_list():
    r = requests.get(f"{API}/marketplace/pros", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert "pros" in d and "count" in d
    assert isinstance(d["count"], int) and d["count"] >= 0


def test_marketplace_buy_forbidden(demo_token):
    r = requests.post(f"{API}/marketplace/leads/buy", json={"lead_id": "ld_x"},
                      headers=_h(demo_token), timeout=10)
    assert r.status_code == 403


# -------- Promo Codes --------

def test_promo_admin_crud(admin_token):
    code = f"TESTPROMO{int(time.time())}"
    r = requests.post(f"{API}/admin/promo-codes",
                      json={"code": code, "percent_off": 10},
                      headers=_h(admin_token), timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["stripe_promotion_code_id"].startswith("promo_")
    assert d["stripe_coupon_id"]
    assert d["code"] == code.upper()

    r = requests.get(f"{API}/admin/promo-codes", headers=_h(admin_token), timeout=15)
    assert r.status_code == 200
    assert any(x["code"] == code.upper() for x in r.json())

    r = requests.patch(f"{API}/admin/promo-codes/{code}?active=false",
                       headers=_h(admin_token), timeout=15)
    assert r.status_code == 200


def test_promo_rbac(demo_token):
    for m, path in [("post", "/admin/promo-codes"),
                    ("get", "/admin/promo-codes"),
                    ("patch", "/admin/promo-codes/X?active=false")]:
        r = getattr(requests, m)(f"{API}{path}", json={"code": "X", "percent_off": 5},
                                 headers=_h(demo_token), timeout=10)
        assert r.status_code == 403, f"{m} {path} -> {r.status_code}"


# -------- Regression --------

@pytest.mark.parametrize("path", ["/plans", "/billing/flags"])
def test_regression_public(path):
    r = requests.get(f"{API}{path}", timeout=20)
    assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"


def test_regression_prices_search():
    r = requests.post(f"{API}/prices/search", json={"query": "carrelage"}, timeout=30)
    assert r.status_code == 200, r.text


def test_regression_projects(demo_token):
    r = requests.get(f"{API}/projects", headers=_h(demo_token), timeout=15)
    assert r.status_code == 200


def test_regression_login():
    r = requests.post(f"{API}/auth/login", json=DEMO, timeout=15)
    assert r.status_code == 200
