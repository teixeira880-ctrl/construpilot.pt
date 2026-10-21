"""Iteration 92 tests: Métré béton (m³) + repérage poteaux P1..Pn + zones tiled.

- GET /analysis/0?wall_height=2.7 -> descriptif contains beton_total_m3>0 and beton_poteaux/poutres/dalles/voiles_m3
- Each column has a unique ref P1, P2...
- POST /structure/0/quote?wall_height=2.7 contains 'Poteaux béton' (u) AND 'Béton coulé' (m³)
- PUT /structure/0 with added column -> refs recomputed
- Non-régression: plan_da91364b9bc7 also has beton_total_m3 (small)
"""
import os
import re
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


class TestBetonDescriptif:
    def test_analysis_returns_beton_totals(self, auth):
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/analysis/0",
                     params={"wall_height": 2.7})
        assert r.status_code == 200, r.text
        data = r.json()
        desc = data.get("descriptif") or {}
        # Basic sanity
        assert (desc.get("poteaux") or 0) > 0, f"poteaux={desc.get('poteaux')}"
        # Beton totals
        total = desc.get("beton_total_m3")
        assert total is not None, f"beton_total_m3 missing. desc keys={list(desc.keys())}"
        assert float(total) > 0, f"beton_total_m3={total}"
        # Detail
        for key in ("beton_poteaux_m3", "beton_poutres_m3",
                    "beton_dalles_m3", "beton_voiles_m3"):
            assert key in desc, f"missing detail key {key}"
            assert float(desc.get(key) or 0) >= 0
        # Sum roughly matches
        s = (float(desc.get("beton_poteaux_m3") or 0) +
             float(desc.get("beton_poutres_m3") or 0) +
             float(desc.get("beton_dalles_m3") or 0) +
             float(desc.get("beton_voiles_m3") or 0))
        assert abs(s - float(total)) < 1.0, f"sum={s} vs total={total}"


class TestColumnRefs:
    def test_columns_have_unique_p_refs(self, auth):
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/analysis/0")
        assert r.status_code == 200
        cols = (r.json().get("structure") or {}).get("columns") or []
        assert len(cols) > 0
        refs = [c.get("ref") for c in cols]
        assert all(r for r in refs), f"Some columns missing ref: {refs}"
        # Pattern P<number>
        pat = re.compile(r"^P\d+$")
        assert all(pat.match(r) for r in refs), f"Bad refs: {refs}"
        # unique
        assert len(set(refs)) == len(refs), f"Duplicated refs: {refs}"

    def test_put_structure_renumbers_refs(self, auth):
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/analysis/0")
        s = r.json().get("structure") or {}
        cols = list(s.get("columns") or [])
        n0 = len(cols)
        new_col = {"column_id": "TEST_col_iter92", "x1": 50.0, "y1": 50.0, "x2": 90.0, "y2": 90.0}
        cols.append(new_col)
        payload = {
            "walls": s.get("walls") or [],
            "openings": s.get("openings") or [],
            "beams": s.get("beams") or [],
            "columns": cols,
            "floors": s.get("floors") or [],
            "plan_kind": s.get("plan_kind"),
        }
        r2 = auth.put(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/structure/0", json=payload)
        assert r2.status_code == 200, r2.text
        # Re-fetch and check refs recomputed and unique
        r3 = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/analysis/0")
        cols_after = (r3.json().get("structure") or {}).get("columns") or []
        assert len(cols_after) == n0 + 1
        refs = [c.get("ref") for c in cols_after]
        assert all(r and re.match(r"^P\d+$", r) for r in refs), refs
        assert len(set(refs)) == len(refs), refs
        # Numbers should be 1..N contiguous
        nums = sorted(int(r[1:]) for r in refs)
        assert nums == list(range(1, len(refs) + 1)), nums
        # Cleanup
        payload["columns"] = [c for c in cols_after if c.get("column_id") != "TEST_col_iter92" and c.get("id") != "TEST_col_iter92"]
        rc = auth.put(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/structure/0", json=payload)
        assert rc.status_code == 200


class TestQuoteBeton:
    def test_quote_contains_poteaux_and_beton(self, auth):
        r = auth.post(f"{BASE_URL}/api/takeoffs/{PLAN_COFFRAGE}/structure/0/quote",
                      params={"wall_height": 2.7}, json={})
        assert r.status_code == 200, r.text
        j = r.json()
        lines = j.get("lines") or []
        desigs = [(l.get("designation") or "").lower() for l in lines]
        # Poteaux béton (u)
        pot = [l for l in lines if "poteau" in (l.get("designation") or "").lower()]
        assert pot, f"no Poteaux line. desigs={desigs}"
        assert (pot[0].get("unit") or "").lower() in ("u", "un", "unite", "unité")
        # Béton coulé (m³)
        beton = [l for l in lines if "béton coulé" in (l.get("designation") or "").lower()
                 or "beton coule" in (l.get("designation") or "").lower()]
        assert beton, f"no Beton coule line. desigs={desigs}"
        unit = (beton[0].get("unit") or "").lower()
        assert "m3" in unit or "m³" in unit, f"unit={unit}"
        assert float(beton[0].get("qty") or 0) > 0


class TestResidBeton:
    def test_resid_has_beton_field(self, auth):
        r = auth.get(f"{BASE_URL}/api/takeoffs/{PLAN_RESID}/analysis/0",
                     params={"wall_height": 2.7})
        assert r.status_code == 200
        desc = r.json().get("descriptif") or {}
        assert "beton_total_m3" in desc
        assert float(desc.get("beton_total_m3") or 0) >= 0
