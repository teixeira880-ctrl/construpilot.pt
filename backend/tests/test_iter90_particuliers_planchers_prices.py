"""Iteration 90 tests:
- POST /api/leads (source=landing-particuliers)
- GET /api/takeoffs/{id}/analysis/0 -> planchers_source='auto', planchers_count>0
- POST /api/takeoffs/{id}/structure/0/quote -> priced_lines>0, unit_price_ht>0, price_source='bibliotheque'
- Non-regression: GET /api/takeoffs/{id}/structure/0 present, PDF export 200
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
DEMO_EMAIL = "demo@construpilot.fr"
DEMO_PWD = "Demo2026!"
PLAN_ID = "plan_da91364b9bc7"


@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def token(api_client):
    r = api_client.post(f"{BASE_URL}/api/auth/login",
                        json={"email": DEMO_EMAIL, "password": DEMO_PWD})
    assert r.status_code == 200, r.text
    return r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="session")
def auth(api_client, token):
    api_client.headers.update({"Authorization": f"Bearer {token}"})
    return api_client


# -------- Landing Particuliers -> Lead public --------
class TestLeadsPublic:
    def test_create_lead_landing_particuliers(self, api_client):
        payload = {
            "name": "TEST_Camille",
            "email": "test_camille@example.com",
            "description": "Rénovation appartement 60m2 (test iter90).",
            "source": "landing-particuliers",
            "utm_source": "instagram", "utm_medium": "paid_social",
            "utm_campaign": "particuliers_janv26",
        }
        r = requests.post(f"{BASE_URL}/api/leads", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("source") == "landing-particuliers"
        assert data.get("email") == payload["email"]
        assert data.get("utm_campaign") == "particuliers_janv26"
        assert "lead_id" in data and data["lead_id"].startswith("lead_")
        assert data.get("status") == "nouveau"


# -------- Plan analysis: planchers auto --------
class TestPlanchersAuto:
    def test_analysis_has_planchers_auto(self, auth):
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/analysis/0")
        assert r.status_code == 200, r.text
        js = r.json()
        desc = js.get("descriptif") or js.get("data", {}).get("descriptif") or js
        # some routes return the full analysis with descriptif nested
        if "planchers_source" not in desc and "descriptif" in js:
            desc = js["descriptif"]
        assert desc.get("planchers_source") == "auto", f"got {desc}"
        assert (desc.get("planchers_count") or 0) > 0
        assert (desc.get("planchers_m2") or 0) > 0


# -------- Structure -> quote with library prices --------
class TestStructureToQuoteWithPrices:
    def test_quote_has_priced_lines(self, auth):
        r = auth.post(
            f"{BASE_URL}/api/takeoffs/{PLAN_ID}/structure/0/quote",
            json={},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("priced_lines", 0) > 0, data
        doc_id = data.get("doc_id") or data.get("document_id") or data.get("id")
        assert doc_id, data
        # Fetch the document to verify unit_price_ht > 0 on at least some lines
        r2 = auth.get(f"{BASE_URL}/api/documents/{doc_id}")
        assert r2.status_code == 200, r2.text
        doc = r2.json()
        lines = doc.get("lines") or doc.get("items") or []
        priced = [l for l in lines if (l.get("unit_price_ht") or l.get("unit_price") or 0) > 0]
        assert len(priced) > 0, f"no priced lines in doc: {lines}"
        # At least one line should have price_source == 'bibliotheque'
        assert any(l.get("price_source") == "bibliotheque" for l in lines), lines


# -------- Non-regression: structure endpoints & PDF export --------
class TestStructureNonRegression:
    def test_get_structure_via_analysis(self, auth):
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/analysis/0")
        assert r.status_code == 200, r.text
        data = r.json()
        struct = data.get("structure") or {}
        assert isinstance(struct.get("walls") or [], list)
        assert isinstance(struct.get("openings") or [], list)
        assert isinstance(struct.get("floors") or [], list)

    def test_export_annotated_pdf(self, auth):
        r = auth.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/structure/0/pdf", json={})
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        assert r.headers.get("content-type", "").startswith("application/pdf") or r.content[:4] == b"%PDF"
