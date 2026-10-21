"""Iter 57 HTTP tests — PATCH /takeoffs/{plan_id}/annotations roundtrip."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Read from frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break

ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PWD = "Construpilot2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def plan_id(headers):
    r = requests.get(f"{BASE_URL}/api/takeoffs", headers=headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    plans = data.get("plans", data) if isinstance(data, dict) else data
    assert len(plans) > 0, "Admin must have at least 1 plan"
    return plans[0]["plan_id"]


def test_patch_annotations_roundtrip(headers, plan_id):
    payload = {
        "page_index": 0,
        "counters": [{
            "id": "c-test-1", "label": "Prises", "color": "#f97316", "unit": "u",
            "markers": [{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 40.0}]
        }],
        "notes": [{"id": "n-test-1", "x": 5.0, "y": 5.0, "text": "TEST Mur porteur"}],
        "angles": [{"id": "a-test-1", "vx": 0.0, "vy": 0.0,
                    "ax": 100.0, "ay": 0.0, "bx": 0.0, "by": 100.0, "degrees": 90.0}],
        "pitched_surfaces": [{"id": "p-test-1",
                              "points": [[0, 0], [100, 0], [100, 100], [0, 100]],
                              "projected_area_m2": 100.0, "pitch_degrees": 30.0,
                              "real_area_m2": 115.47}],
    }
    r = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/annotations",
                       headers=headers, json=payload, timeout=30)
    assert r.status_code == 200, r.text

    # GET roundtrip
    g = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=30)
    assert g.status_code == 200, g.text
    plan = g.json()
    ann = plan.get("annotations", {})
    assert "0" in ann, f"expected key '0' in annotations, got keys={list(ann.keys())}"
    page0 = ann["0"]
    assert len(page0["counters"]) >= 1
    counter = next(c for c in page0["counters"] if c["id"] == "c-test-1")
    assert len(counter["markers"]) == 2
    assert counter["markers"][0]["x"] == 10.0
    assert any(n["id"] == "n-test-1" for n in page0["notes"])
    assert any(a["id"] == "a-test-1" for a in page0["angles"])
    assert any(p["id"] == "p-test-1" for p in page0["pitched_surfaces"])


def test_patch_invalid_page_index(headers, plan_id):
    r = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/annotations",
                       headers=headers,
                       json={"page_index": 999, "counters": [], "notes": [],
                             "angles": [], "pitched_surfaces": []}, timeout=30)
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"


def test_patch_nonexistent_plan(headers):
    r = requests.patch(f"{BASE_URL}/api/takeoffs/plan_xxxxxxxxxxxx/annotations",
                       headers=headers,
                       json={"page_index": 0, "counters": [], "notes": [],
                             "angles": [], "pitched_surfaces": []}, timeout=30)
    assert r.status_code == 404


def test_patch_defaults_empty_lists(headers, plan_id):
    # Reset annotations to empty
    r = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/annotations",
                       headers=headers, json={"page_index": 0}, timeout=30)
    assert r.status_code == 200
    g = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=30)
    ann = g.json().get("annotations", {})
    if "0" in ann:
        # Should be reset to empty arrays
        assert ann["0"].get("counters", []) == []
        assert ann["0"].get("notes", []) == []
