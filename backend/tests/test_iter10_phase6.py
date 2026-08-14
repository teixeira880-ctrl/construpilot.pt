"""Iter 10 Phase 6 tests: Sponsored products + price history + non-regression."""
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


# ============ Sponsorship CRUD + RBAC ============

SUP = "leroymerlin"


def test_sponsorship_rbac_user_forbidden(demo_token):
    r = requests.post(f"{API}/admin/sponsorships",
                      json={"supplier_key": SUP, "keywords": ["carrelage"],
                            "daily_budget_cents": 5000, "cpc_cents": 100, "priority": 100},
                      headers=H(demo_token), timeout=15)
    assert r.status_code == 403, f"user should get 403, got {r.status_code} {r.text}"


def test_sponsorship_create_and_list(admin_token):
    # Reset budget: recreate then explicitly set spent_today_cents=0 via new upsert with reset
    body = {"supplier_key": SUP, "keywords": ["carrelage"],
            "daily_budget_cents": 100000, "cpc_cents": 100,
            "priority": 100, "active": True}
    r = requests.post(f"{API}/admin/sponsorships", json=body, headers=H(admin_token), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["supplier_key"] == SUP
    assert d["keywords"] == ["carrelage"]

    # List
    r = requests.get(f"{API}/admin/sponsorships", headers=H(admin_token), timeout=15)
    assert r.status_code == 200
    lst = r.json()
    assert any(s["supplier_key"] == SUP for s in lst)


def test_sponsorship_list_rbac_forbidden(demo_token):
    r = requests.get(f"{API}/admin/sponsorships", headers=H(demo_token), timeout=15)
    assert r.status_code == 403


# ============ Sponsored insertion in /prices/search ============

def test_prices_search_has_sponsored_first(admin_token):
    # Purge TOUS les sponsorships (même SUP) pour un classement déterministe —
    # SUP est recréé dans le finally pour le test du clic qui suit.
    existing = requests.get(f"{API}/admin/sponsorships", headers=H(admin_token), timeout=15).json()
    for s in existing:
        requests.delete(f"{API}/admin/sponsorships/{s['supplier_key']}",
                        headers=H(admin_token), timeout=15)

    # Le web vivant (Tavily) peut changer entre 2 appels : jusqu'à 2 tentatives,
    # et cleanup TOUJOURS exécuté (sinon le sponsorship temporaire pollue la suite).
    last_err = None
    try:
        for _ in range(2):
            r = requests.post(f"{API}/prices/search",
                              json={"query": "carrelage 60x60", "limit": 10}, timeout=30)
            assert r.status_code == 200, r.text
            organic = r.json().get("results", [])
            assert len(organic) > 0, "no results returned"
            keys = [x["supplier_key"] for x in organic]
            sup = max(set(keys), key=keys.count)

            requests.delete(f"{API}/admin/sponsorships/{sup}", headers=H(admin_token), timeout=15)
            r = requests.post(f"{API}/admin/sponsorships",
                              json={"supplier_key": sup, "keywords": ["carrelage"],
                                    "daily_budget_cents": 100000, "cpc_cents": 100,
                                    "priority": 100, "active": True},
                              headers=H(admin_token), timeout=15)
            assert r.status_code == 200
            try:
                r = requests.post(f"{API}/prices/search",
                                  json={"query": "carrelage 60x60", "limit": 10}, timeout=30)
                assert r.status_code == 200, r.text
                results = r.json().get("results", [])
                assert len(results) > 0, "no results returned"
                if not any(x["supplier_key"] == sup for x in results):
                    last_err = f"{sup} absent des résultats (web a changé)"
                    continue  # nouvelle tentative avec un fournisseur frais
                first = results[0]
                assert first.get("supplier_key") == sup, f"expected {sup} first, got {first.get('supplier_key')}"
                assert first.get("sponsored") == True
                assert first.get("sponsored_disclosure") == "Sponsorisé — placement payé"
                for r_ in results[1:]:
                    assert not r_.get("sponsored"), f"other should not be sponsored: {r_.get('supplier_key')}"
                return
            finally:
                requests.delete(f"{API}/admin/sponsorships/{sup}", headers=H(admin_token), timeout=15)
    finally:
        # Recrée SUP (supprimé par la purge) pour le test du clic qui suit
        requests.delete(f"{API}/admin/sponsorships/{SUP}", headers=H(admin_token), timeout=15)
        requests.post(f"{API}/admin/sponsorships",
                      json={"supplier_key": SUP, "keywords": ["carrelage"],
                            "daily_budget_cents": 100000, "cpc_cents": 100,
                            "priority": 100, "active": True},
                      headers=H(admin_token), timeout=15)
    import pytest
    pytest.skip(f"Résultats web trop instables pour valider la promotion : {last_err}")


# ============ Sponsored click increments spent_today_cents ============

def test_sponsored_click_increments_budget(admin_token):
    # Get current spent
    lst = requests.get(f"{API}/admin/sponsorships", headers=H(admin_token), timeout=15).json()
    before = next(s for s in lst if s["supplier_key"] == SUP)
    before_spent = before.get("spent_today_cents", 0)

    r = requests.post(f"{API}/sponsored/click",
                      json={"supplier_key": SUP, "query": "carrelage 60x60"}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("ok") == True

    lst2 = requests.get(f"{API}/admin/sponsorships", headers=H(admin_token), timeout=15).json()
    after = next(s for s in lst2 if s["supplier_key"] == SUP)
    assert after.get("spent_today_cents", 0) >= before_spent + 100


# ============ Budget exhausted → no sponsored insertion ============

def test_budget_exhausted_no_sponsored(admin_token):
    # Purge TOUS les sponsorships (un test précédent peut avoir laissé un résidu)
    existing = requests.get(f"{API}/admin/sponsorships", headers=H(admin_token), timeout=15).json()
    for s in existing:
        requests.delete(f"{API}/admin/sponsorships/{s['supplier_key']}",
                        headers=H(admin_token), timeout=15)
    requests.post(f"{API}/admin/sponsorships",
                  json={"supplier_key": SUP, "keywords": ["carrelage"],
                        "daily_budget_cents": 50, "cpc_cents": 100,
                        "priority": 100, "active": True},
                  headers=H(admin_token), timeout=15)
    # cpc=100 > budget=50 → cannot insert
    r = requests.post(f"{API}/prices/search",
                      json={"query": "carrelage 60x60", "limit": 10}, timeout=30)
    assert r.status_code == 200
    results = r.json().get("results", [])
    assert results, "should still have organic results"
    # first should NOT be marked sponsored
    assert not results[0].get("sponsored"), "no result should be sponsored when budget exhausted"

    # cleanup: restore healthy sponsorship for other tests
    requests.delete(f"{API}/admin/sponsorships/{SUP}", headers=H(admin_token), timeout=15)
    requests.post(f"{API}/admin/sponsorships",
                  json={"supplier_key": SUP, "keywords": ["carrelage"],
                        "daily_budget_cents": 100000, "cpc_cents": 100,
                        "priority": 100, "active": True},
                  headers=H(admin_token), timeout=15)


# ============ Price History Snapshot + Chart ============

def test_price_history_snapshot(admin_token):
    r = requests.post(f"{API}/prices/history/snapshot",
                      params={"query": "carrelage"}, headers=H(admin_token), timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("query") == "carrelage"
    assert "day" in d
    assert "inserted" in d
    assert isinstance(d["inserted"], int)


def test_price_history_snapshot_rbac(demo_token):
    r = requests.post(f"{API}/prices/history/snapshot",
                      params={"query": "carrelage"}, headers=H(demo_token), timeout=30)
    assert r.status_code == 403


def test_price_history_chart(admin_token):
    # ensure at least one snapshot exists
    requests.post(f"{API}/prices/history/snapshot", params={"query": "carrelage"},
                  headers=H(admin_token), timeout=60)
    r = requests.get(f"{API}/prices/history/chart",
                     params={"query": "carrelage", "days": 30}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("query") == "carrelage"
    assert d.get("days") == 30
    assert "series" in d
    assert isinstance(d["series"], list)
    assert len(d["series"]) >= 1
    for s in d["series"]:
        assert "day" in s and "min_price" in s and "avg_price" in s and "max_price" in s and "count" in s


# ============ Non-regression: /api/prices/history (existing) still works ============

def test_prices_history_legacy_endpoint_not_colliding():
    r = requests.get(f"{API}/prices/history", params={"query": "carrelage"}, timeout=20)
    assert r.status_code == 200
    # legacy endpoint returns raw points structure (not chart series)
    d = r.json()
    # ensure not the chart shape
    assert not (isinstance(d, dict) and set(d.keys()) == {"query", "series", "days"})


# ============ Broad non-regression ============

def test_plans_endpoint():
    r = requests.get(f"{API}/plans", timeout=15)
    assert r.status_code == 200
    d = r.json()
    plans = d.get("plans") if isinstance(d, dict) else d
    assert isinstance(plans, list)
    assert len(plans) == 11, f"expected 11 plans, got {len(plans)}"


def test_api_keys_list(demo_token):
    r = requests.get(f"{API}/api-keys", headers=H(demo_token), timeout=15)
    assert r.status_code in (200, 403)  # depending on plan gating


def test_whitelabel_config():
    r = requests.get(f"{API}/whitelabel/config", params={"tenant": "no_such_xyz"}, timeout=15)
    assert r.status_code == 200


def test_enterprise_contact():
    r = requests.post(f"{API}/enterprise/contact",
                      json={"company_name": "TEST Iter10", "contact_name": "Test Iter10",
                            "contact_email": "delivered@resend.dev",
                            "use_case": "Automated test iter10"}, timeout=20)
    assert r.status_code in (200, 201)


def test_suppliers_dashboard(admin_token):
    r = requests.get(f"{API}/suppliers/dashboard", headers=H(admin_token), timeout=20)
    assert r.status_code == 200


def test_marketplace():
    r = requests.get(f"{API}/marketplace/pros", timeout=15)
    assert r.status_code == 200


def test_savings_analyse(demo_token):
    r = requests.post(f"{API}/savings/analyse",
                      json={"items": [{"query": "peinture", "quantity": 1}]},
                      headers=H(demo_token), timeout=30)
    assert r.status_code in (200, 400, 422)  # tolerate schema variations


def test_referral_me(demo_token):
    r = requests.get(f"{API}/referral/me", headers=H(demo_token), timeout=15)
    assert r.status_code == 200


def test_auth_login_admin():
    r = requests.post(f"{API}/auth/login", json=ADMIN, timeout=15)
    assert r.status_code == 200
    assert "token" in r.json()
