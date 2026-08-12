"""Iter 9 Phase 5 tests: WhiteLabel + Suppliers + Enterprise + non-regression."""
import os
import requests
import pytest

def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.strip().startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}
DEMO = {"email": "demo@construpilot.fr", "password": "Demo2026!"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login {creds['email']} => {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def demo_token():
    return _login(DEMO)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============ WHITE LABEL ============

TSLUG = "testtenant_iter9"


def test_whitelabel_config_default_when_missing():
    r = requests.get(f"{API}/whitelabel/config", params={"tenant": "no_such_tenant_xyz"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("default") is True
    assert d.get("tenant_slug") is None


def test_whitelabel_rbac_forbidden_for_standard_user(demo_token):
    r = requests.get(f"{API}/admin/whitelabel", headers=H(demo_token), timeout=15)
    assert r.status_code == 403


def test_whitelabel_admin_upsert_and_public_read(admin_token):
    payload = {
        "tenant_slug": TSLUG,
        "partner_name": "Test Tenant",
        "primary_color": "#00AAFF",
        "logo_url": "https://example.com/logo.png",
        "hero_title": "Bienvenue",
        "hero_subtitle": "sub",
        "active": True,
    }
    r = requests.post(f"{API}/admin/whitelabel", json=payload, headers=H(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["tenant_slug"] == TSLUG
    assert j["primary_color"] == "#00AAFF"

    # public config now returns doc
    r2 = requests.get(f"{API}/whitelabel/config", params={"tenant": TSLUG}, timeout=15)
    assert r2.status_code == 200
    d = r2.json()
    assert d.get("tenant_slug") == TSLUG
    assert d.get("primary_color") == "#00AAFF"
    assert d.get("hero_title") == "Bienvenue"

    # admin list contains it
    r3 = requests.get(f"{API}/admin/whitelabel", headers=H(admin_token), timeout=15)
    assert r3.status_code == 200
    assert any(t["tenant_slug"] == TSLUG for t in r3.json())


def test_whitelabel_admin_delete(admin_token):
    r = requests.delete(f"{API}/admin/whitelabel/{TSLUG}", headers=H(admin_token), timeout=15)
    assert r.status_code == 200
    r2 = requests.get(f"{API}/whitelabel/config", params={"tenant": TSLUG}, timeout=15)
    assert r2.json().get("default") is True


# ============ SUPPLIERS ============


def test_suppliers_claim_creates_pending(demo_token):
    body = {
        "supplier_key": "leroymerlin",
        "contact_name": "TEST User",
        "contact_email": "test_iter9@example.com",
    }
    r = requests.post(f"{API}/suppliers/claim", json=body, headers=H(demo_token), timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("status") == "pending"


def test_suppliers_dashboard_unverified_user_returns_verified_false(demo_token):
    # demo claim is pending (not verified) → verified: False
    r = requests.get(f"{API}/suppliers/dashboard", headers=H(demo_token), timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("verified") is False


def test_suppliers_dashboard_admin_fallback(admin_token):
    r = requests.get(f"{API}/suppliers/dashboard", params={"days": 30}, headers=H(admin_token), timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("verified") is True
    assert d.get("supplier_key") == "leroymerlin"
    for k in ("clicks", "redirects", "conversions", "gmv_eur", "commission_eur"):
        assert k in d, f"missing {k}"
    assert isinstance(d.get("top_products"), list)
    assert isinstance(d.get("top_queries"), list)


def test_admin_supplier_claims_list(admin_token):
    r = requests.get(f"{API}/admin/suppliers/claims", headers=H(admin_token), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ============ ENTERPRISE ============


def test_enterprise_contact_public_creates_lead():
    body = {
        "company_name": "TEST Corp Iter9",
        "contact_name": "Jane Doe",
        "contact_email": "delivered@resend.dev",
        "company_size": "200-1000",
        "use_case": "We want to integrate ConstruPilot API for our 12000 buildings renovation program with SSO and SLA guarantees for our large enterprise deployment.",
        "sso_required": True,
        "sla_required": False,
    }
    r = requests.post(f"{API}/enterprise/contact", json=body, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("ok") is True
    assert isinstance(j.get("lead_id"), str) and j["lead_id"].startswith("ent_")


def test_enterprise_leads_admin(admin_token):
    r = requests.get(f"{API}/admin/enterprise/leads", headers=H(admin_token), timeout=15)
    assert r.status_code == 200
    leads = r.json()
    assert isinstance(leads, list) and len(leads) >= 1
    top = leads[0]
    assert "score" in top and top["score"] > 0
    # descending order
    if len(leads) >= 2:
        assert leads[0]["created_at"] >= leads[1]["created_at"]


def test_enterprise_leads_rbac_user_forbidden(demo_token):
    r = requests.get(f"{API}/admin/enterprise/leads", headers=H(demo_token), timeout=15)
    assert r.status_code == 403


# ============ NON REGRESSION ============


def test_plans_public():
    r = requests.get(f"{API}/plans", timeout=15)
    assert r.status_code == 200
    plans = r.json()
    # plans may be either list or dict with "plans" key
    if isinstance(plans, dict):
        plans = plans.get("plans", [])
    assert isinstance(plans, list) and len(plans) == 11, f"expected 11 plans got {len(plans)}"


def test_api_keys_endpoint(demo_token):
    r = requests.get(f"{API}/api-keys", headers=H(demo_token), timeout=15)
    assert r.status_code in (200, 403)  # depends on plan


def test_prices_search():
    r = requests.post(f"{API}/prices/search", json={"query": "carrelage", "limit": 3}, timeout=45)
    assert r.status_code == 200


def test_marketplace_list():
    r = requests.get(f"{API}/marketplace/pros", timeout=15)
    assert r.status_code == 200


def test_referral_me(demo_token):
    r = requests.get(f"{API}/referral/me", headers=H(demo_token), timeout=15)
    assert r.status_code == 200


def test_projects_list(demo_token):
    r = requests.get(f"{API}/projects", headers=H(demo_token), timeout=15)
    assert r.status_code == 200
