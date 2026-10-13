"""C2 Wave PT-PT translation validation tests.

Focus:
- /api/auth/me returns country + language
- Admin PT + Admin FR logins work
- /api/estimation/compute defaults to PT country/VAT
- /api/estimation/catalog has PT lot names + 16 PT regions
- SPA routes return index.html (200) for EN/PT/FR aliases
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://construpilot-recon.preview.emergentagent.com").rstrip("/")

ADMIN_PT = {"email": "info@construpilot.pt", "password": "Ruquinha2020."}
ADMIN_FR = {"email": "admin@construpilot.io", "password": "VJAiUOI90Ss2brVH"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_pt_token(session):
    r = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_PT, timeout=30)
    assert r.status_code == 200, f"PT login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 0
    return data["token"]


@pytest.fixture(scope="module")
def admin_fr_token(session):
    r = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_FR, timeout=30)
    assert r.status_code == 200, f"FR login failed: {r.status_code} {r.text}"
    return r.json()["token"]


# --- Auth ---

class TestAuth:
    def test_login_admin_pt_returns_admin_premium(self, session):
        r = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_PT, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "token" in data
        user = data.get("user", {})
        assert user.get("role") == "admin", f"role={user.get('role')}"
        assert user.get("plan") == "premium", f"plan={user.get('plan')}"

    def test_login_admin_fr_still_works(self, session):
        r = session.post(f"{BASE_URL}/api/auth/login", json=ADMIN_FR, timeout=30)
        assert r.status_code == 200
        assert "token" in r.json()

    def test_auth_me_exposes_country_and_language(self, session, admin_pt_token):
        r = session.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {admin_pt_token}"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # payload may be flat or wrapped in user
        user = data.get("user", data)
        assert "country" in user, f"country field missing. keys={list(user.keys())}"
        assert "language" in user, f"language field missing. keys={list(user.keys())}"
        assert user["country"] == "PT", f"country={user['country']}"
        assert user["language"] == "pt", f"language={user['language']}"
        assert "timezone" in user, f"timezone missing. keys={list(user.keys())}"
        assert user["timezone"] == "Europe/Lisbon", f"timezone={user['timezone']}"


# --- Estimation ---

class TestEstimation:
    def test_compute_defaults_to_pt(self, session):
        # No country in body - should default to PT
        payload = {"surface": 100, "project_type": "renovation_complete"}
        r = session.post(f"{BASE_URL}/api/estimation/compute", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("country") == "PT", f"country={data.get('country')}"
        assert data.get("default_vat_rate") == 6.0, f"default_vat_rate={data.get('default_vat_rate')}"
        assert data.get("vat_eligible_6") is True, f"vat_eligible_6={data.get('vat_eligible_6')}"

    def test_catalog_has_pt_lots_projects_regions(self, session):
        r = session.get(f"{BASE_URL}/api/estimation/catalog", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        lots = data.get("lots", [])
        projects = data.get("project_types", [])
        finishes = data.get("finish_levels", [])
        regions = data.get("regions", [])

        assert len(lots) == 25, f"lots count={len(lots)}"
        assert len(projects) == 27, f"projects count={len(projects)}"
        assert len(finishes) == 4, f"finish levels={len(finishes)}"
        assert len(regions) == 16, f"regions count={len(regions)}"

        # PT lot names present
        lot_names = " ".join(
            (l.get("name") or l.get("label") or "") for l in lots
        )
        for expected in ["Demolição", "Alvenaria", "Fundações"]:
            assert expected in lot_names, f"Missing PT lot '{expected}'. names={lot_names}"

        # Regions should be PT only - check no known FR region names
        region_names = " ".join(
            (rg.get("name") or rg.get("label") or rg if isinstance(rg, str) else "") for rg in regions
        )
        for fr_region in ["Île-de-France", "Provence", "Nouvelle-Aquitaine", "Bretagne", "Occitanie"]:
            assert fr_region not in region_names, f"FR region '{fr_region}' leaked into catalog"


# --- SPA routes ---

SPA_ROUTES = [
    "/investors", "/investidores", "/investisseurs",
    "/calculators", "/calculadoras", "/calculateurs",
    "/prices", "/precos", "/prix",
    "/estimativa", "/funcionalidades", "/redefinir", "/registo",
]


@pytest.mark.parametrize("route", SPA_ROUTES)
def test_spa_route_returns_200(route):
    # SPA routes should be served by frontend host - all return index.html
    r = requests.get(f"{BASE_URL}{route}", timeout=30, allow_redirects=True)
    assert r.status_code == 200, f"{route} -> {r.status_code}"
    # Should be HTML (not JSON 404)
    ctype = r.headers.get("content-type", "")
    assert "html" in ctype.lower(), f"{route} content-type={ctype}"
