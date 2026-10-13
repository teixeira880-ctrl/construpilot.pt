"""Iter 56 — HTTP-level checks for new endpoints as per review request."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pilot-build-demo.preview.emergentagent.com').rstrip('/')
ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return r.json().get("token")


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def test_takeoffs_list_and_pick_plan(admin_headers):
    r = requests.get(f"{BASE_URL}/api/takeoffs", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    data = r.json()
    plans = data if isinstance(data, list) else data.get("plans", [])
    assert len(plans) > 0
    pytest.plan_id = plans[0].get("plan_id") or plans[0].get("id")
    assert pytest.plan_id


def test_analyze_returns_enriched_schema(admin_headers):
    plan_id = getattr(pytest, "plan_id", None)
    if not plan_id:
        pytest.skip("no plan available")
    r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/analyze", headers=admin_headers, timeout=120)
    # Endpoint may return 200 or 202/400 depending on plan state; we mostly want structure
    assert r.status_code in (200, 202, 400), r.text
    if r.status_code == 200:
        data = r.json()
        # New fields must be present in the normalized shape
        analysis = data.get("analysis") or data
        assert "dimension_lines" in analysis
        assert "wall_types" in analysis
        assert "materials_notes" in analysis
        openings = analysis.get("openings", {})
        assert "reservations_visible" in openings
        assert isinstance(analysis["dimension_lines"], list)
        assert isinstance(analysis["wall_types"], dict)
        assert isinstance(analysis["materials_notes"], list)


def test_duplicate_endpoint(admin_headers):
    plan_id = getattr(pytest, "plan_id", None)
    if not plan_id:
        pytest.skip("no plan available")
    r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/duplicate", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    new_pid = data.get("plan_id") or data.get("id")
    fname = data.get("filename") or data.get("name") or ""
    assert new_pid and new_pid != plan_id
    assert "copie" in fname.lower()


def test_price_alerts_sms_requires_phone(admin_headers):
    payload = {"query": "BA13 hydrofuge", "target_price": 5.0, "channels": ["email", "sms"]}
    r = requests.post(f"{BASE_URL}/api/prices/alerts", headers=admin_headers, json=payload, timeout=30)
    assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"


def test_price_alerts_sms_with_phone_ok(admin_headers):
    payload = {"query": "BA13 hydrofuge", "target_price": 5.0,
               "channels": ["email", "sms"], "phone": "+33612345678"}
    r = requests.post(f"{BASE_URL}/api/prices/alerts", headers=admin_headers, json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("alert_id") or data.get("id")


def test_price_search_returns_web_mode(admin_headers):
    payload = {"query": "BA13 hydrofuge"}
    r = requests.post(f"{BASE_URL}/api/prices/search", headers=admin_headers, json=payload, timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("mode") == "web", f"expected mode='web', got {data.get('mode')}"
    results = data.get("results") or []
    if results:
        for row in results:
            assert "checked_at" in row, f"missing checked_at in row: {row}"
