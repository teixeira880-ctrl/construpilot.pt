"""Tests publics /api/dossier/generate via URL Expo backend."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://escalier-pro.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")


@pytest.fixture(scope="module")
def stair_ctx():
    """Calcule un escalier droit via /api/calculate/straight pour obtenir stair_result & input."""
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 4500,
        "available_width_mm": 2000,
        "stair_width_mm": 900,
        "trémie_length_mm": 2000,
        "stairwell_length_mm": 2000,
        "stairwell_width_mm": 900,
        "ceiling_height_mm": 2500,
        "slab_thickness_mm": 200,
    }
    # be tolerant: send known keys used by backend model
    body = {
        "floor_height_mm": 2800,
        "available_length_mm": 4500,
        "available_width_mm": 2000,
        "stair_width_mm": 900,
        "ceiling_height_mm": 2500,
        "slab_thickness_mm": 200,
        "stairwell_length_mm": 2000,
        "stairwell_width_mm": 900,
    }
    r = requests.post(f"{BASE_URL}/api/calculate/straight", json=body, timeout=30)
    assert r.status_code == 200, f"calculate/straight failed: {r.status_code} {r.text[:300]}"
    result = r.json()
    assert "num_steps" in result and result["num_steps"] > 0
    return {"input": body, "result": result}


def test_dossier_generate_minimal(stair_ctx):
    """POST /api/dossier/generate sans concrete → 200 + PDF > 3KB."""
    body = {
        "project_name": "TEST_dossier_min",
        "stair_input": stair_ctx["input"],
        "stair_result": stair_ctx["result"],
    }
    r = requests.post(f"{BASE_URL}/api/dossier/generate", json=body, timeout=30)
    assert r.status_code == 200, f"dossier/generate: {r.status_code} {r.text[:300]}"
    ct = r.headers.get("content-type", "")
    assert "application/pdf" in ct, f"content-type={ct}"
    assert r.content[:4] == b"%PDF", f"magic={r.content[:4]!r}"
    assert len(r.content) > 3000, f"pdf too small: {len(r.content)} bytes"


def test_dossier_generate_with_concrete(stair_ctx):
    """POST /api/dossier/generate avec concrete_analysis → 200 + PDF > 10KB, plus gros que sans."""
    ca_body = {
        "stair_result": stair_ctx["result"],
        "stair_type": "straight",
        "concrete_class": "C25/30",
        "steel_grade": "B500B",
        "exposure_class": "XC1",
        "live_load_kN_m2": 2.5,
    }
    rc = requests.post(f"{BASE_URL}/api/concrete/analyze", json=ca_body, timeout=30)
    assert rc.status_code == 200, f"concrete/analyze failed: {rc.status_code} {rc.text[:300]}"
    concrete = rc.json()

    body = {
        "project_name": "TEST_dossier_full",
        "stair_input": stair_ctx["input"],
        "stair_result": stair_ctx["result"],
        "concrete_analysis": concrete,
        "author": "BE TEST",
    }
    r = requests.post(f"{BASE_URL}/api/dossier/generate", json=body, timeout=30)
    assert r.status_code == 200, f"dossier/generate: {r.status_code} {r.text[:300]}"
    assert "application/pdf" in r.headers.get("content-type", "")
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 10_000, f"pdf too small avec concrete: {len(r.content)} bytes"

    # verify significantly bigger than minimal
    body_min = {
        "project_name": "TEST_dossier_ref",
        "stair_input": stair_ctx["input"],
        "stair_result": stair_ctx["result"],
    }
    r2 = requests.post(f"{BASE_URL}/api/dossier/generate", json=body_min, timeout=30)
    assert r2.status_code == 200
    assert len(r.content) > len(r2.content)


def test_dossier_content_disposition(stair_ctx):
    """Header Content-Disposition doit contenir un filename .pdf."""
    body = {
        "project_name": "Projet École — Réf #42",
        "stair_input": stair_ctx["input"],
        "stair_result": stair_ctx["result"],
    }
    r = requests.post(f"{BASE_URL}/api/dossier/generate", json=body, timeout=30)
    assert r.status_code == 200
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd.lower() and ".pdf" in cd.lower(), f"cd={cd}"
