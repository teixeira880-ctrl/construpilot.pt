"""Iteration 91 tests: Coffrage plan structure with columns (poteaux).

- GET /api/takeoffs/{plan}/analysis/0 -> plan_kind=coffrage, poteaux>0, poutres_ml>0, planchers_m2>0
- POST /api/takeoffs/{plan}/structure/0/quote -> ligne 'Poteaux beton' (u) present
- POST /api/takeoffs/{plan}/structure/0/pdf -> 200 application/pdf
- PUT /api/takeoffs/{plan}/structure/0 with new column persists
- Non-regression residentiel plan_da91364b9bc7: analysis toujours OK, plan_kind != coffrage
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
DEMO_EMAIL = "demo@construpilot.fr"
DEMO_PWD = "Demo2026!"
PLAN_COFFRAGE = "plan_c56da42f0331"
PLAN_RESID = "plan_da91364b9bc7"


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
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="session")
def auth(api_client, token):
    api_client.headers.update({"Authorization": f"Bearer {token}"})
    return api_client


class TestCoffrageAnalysis:
    def test_analysis_coffrage_has_columns(self, auth):
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/analysis/0")
        assert r.status_code == 200, r.text
        data = r.json()
        desc = data.get("descriptif") or {}
        assert desc.get("plan_kind") == "coffrage", f"plan_kind={desc.get('plan_kind')}"
        assert (desc.get("poteaux") or 0) > 0, f"poteaux={desc.get('poteaux')}"
        assert (desc.get("poutres_ml") or 0) > 0
        assert (desc.get("planchers_m2") or 0) > 0
        assert (desc.get("murs_ml") or 0) > 0
        structure = data.get("structure") or {}
        assert len(structure.get("columns") or []) > 0
        assert len(structure.get("beams") or []) > 0


class TestCoffrageQuote:
    def test_structure_to_quote_includes_poteaux(self, auth):
        r = auth.post(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/structure/0/quote", json={})
        assert r.status_code == 200, r.text
        j = r.json()
        assert "doc_id" in j
        assert j.get("doc_type") == "quote"
        lines = j.get("lines") or []
        assert isinstance(lines, list) and len(lines) > 0
        found = [l for l in lines if "poteau" in (l.get("designation") or "").lower()]
        assert len(found) > 0, f"Aucune ligne Poteaux dans le devis. designations={[l.get('designation') for l in lines]}"
        line = found[0]
        assert (line.get("unit") or "").lower() in ("u", "un", "unite", "unité")
        assert float(line.get("qty") or 0) > 0


class TestCoffragePdf:
    def test_annotated_pdf_200(self, auth):
        r = auth.post(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/structure/0/pdf")
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("content-type", "")
        assert "pdf" in ct.lower(), ct
        assert len(r.content) > 1000


class TestCoffrageEditColumns:
    def test_add_column_and_persist(self, auth):
        # get current structure via analysis (only reader available)
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/analysis/0")
        assert r.status_code == 200
        s = r.json().get("structure") or {}
        cols = list(s.get("columns") or [])
        walls = s.get("walls") or []
        openings = s.get("openings") or []
        beams = s.get("beams") or []
        floors = s.get("floors") or []
        n0 = len(cols)
        new_col = {"id": "TEST_col_iter91", "p1": [100.0, 100.0], "p2": [140.0, 140.0]}
        cols.append(new_col)
        payload = {
            "walls": walls, "openings": openings,
            "beams": beams, "columns": cols, "floors": floors,
            "plan_kind": s.get("plan_kind"),
        }
        r2 = auth.put(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/structure/0", json=payload)
        assert r2.status_code == 200, r2.text
        # verify persistence
        r3 = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/analysis/0")
        s2 = r3.json().get("structure") or {}
        cols_after = s2.get("columns") or []
        assert len(cols_after) == n0 + 1
        assert any((c.get("id") == "TEST_col_iter91") for c in cols_after)
        # cleanup
        payload["columns"] = [c for c in cols_after if c.get("id") != "TEST_col_iter91"]
        rc = auth.put(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/structure/0", json=payload)
        assert rc.status_code == 200


class TestResidNoRegression:
    def test_resid_analysis_ok(self, auth):
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_RESID}/analysis/0")
        assert r.status_code == 200
        desc = r.json().get("descriptif") or {}
        assert (desc.get("planchers_m2") or 0) > 0
        assert desc.get("plan_kind") != "coffrage"
