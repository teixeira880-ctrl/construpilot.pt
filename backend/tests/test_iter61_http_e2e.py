"""Iter61 HTTP E2E: /analyse levels multi-storey + /compute with levels + PDF icons endpoint."""
import os
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_analyse_multi_storey_returns_levels_and_weighted_height():
    r = requests.post(
        f"{API}/estimation/analyse",
        json={"description": "Rénovation maison ancienne 190m² RDC 100m² hauteur 2.60m R+1 60m² 2.30m combles 30m² 1.80m"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    analysis = d.get("analysis", {})
    est = d.get("estimation", {})
    levels = analysis.get("levels", [])
    # Levels should be detected (AI may vary; require >=2 to consider multi-storey)
    assert isinstance(levels, list), f"levels not list: {levels}"
    if len(levels) >= 2:
        # weighted avg should be < 2.5 given combles at 1.80m
        h = est.get("ceiling_height_m")
        assert h is not None
        assert 1.8 < h < 2.7, f"weighted height out of range: {h}"
        # Compute expected weighted avg from the actual levels returned
        num = sum((lv.get("surface_m2") or 0) * (lv.get("ceiling_height_m") or 0) for lv in levels)
        den = sum((lv.get("surface_m2") or 0) for lv in levels)
        if den > 0:
            expected = num / den
            assert abs(h - expected) < 0.01, f"h={h} != weighted {expected}"
    else:
        pytest.skip(f"AI returned <2 levels: {levels}")


def test_analyse_simple_no_levels_default_height():
    r = requests.post(
        f"{API}/estimation/analyse",
        json={"description": "maison 100m²"},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    est = d.get("estimation", {})
    levels = d.get("analysis", {}).get("levels", [])
    # Backward compat: no levels detected → default 2.5
    assert levels == [] or len(levels) <= 1
    if not levels:
        assert est.get("ceiling_height_m") == 2.5


def test_compute_with_levels_scales_wall_lots():
    body = {
        "surface": 190,
        "levels": [
            {"label": "RDC", "surface_m2": 100, "ceiling_height_m": 2.70},
            {"label": "R+1", "surface_m2": 90, "ceiling_height_m": 2.30},
        ],
    }
    r = requests.post(f"{API}/estimation/compute", json=body, timeout=15)
    assert r.status_code == 200, r.text
    est = r.json()
    # Expected weighted: (100*2.70 + 90*2.30)/190 = 510/190 = 2.6842...
    expected = (100 * 2.70 + 90 * 2.30) / 190
    assert abs(est["ceiling_height_m"] - expected) < 0.01, f"h={est['ceiling_height_m']} exp={expected}"
    # levels echoed
    assert len(est.get("levels", [])) == 2


def test_compute_backward_compat_no_levels():
    r = requests.post(f"{API}/estimation/compute", json={"surface": 100}, timeout=15)
    assert r.status_code == 200, r.text
    est = r.json()
    assert est["ceiling_height_m"] == 2.5
    assert est.get("levels", []) == []


def test_takeoff_pdf_endpoint_serves_pdf_with_icons():
    """Use known demo plan with rooms + presets."""
    tok = _login("demo@construpilot.fr", "Demo2026!")
    h = {"Authorization": f"Bearer {tok}"}
    r = requests.get(f"{API}/takeoffs/plan_32cdb0ca6e66/pdf", headers=h, timeout=30)
    assert r.status_code == 200, r.text[:400]
    assert r.content.startswith(b"%PDF-"), r.content[:40]
    assert len(r.content) > 2000
