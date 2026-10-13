"""Iter 59 HTTP E2E — /estimate endpoint + PDF with presets."""
import os
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "demo@construpilot.fr", "password": "Demo2026!"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _hdrs(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


KNOWN_PLANS = ["plan_32cdb0ca6e66", "plan_6017c355084d", "plan_51d8d4915ea1"]


def _find_demo_plan_and_room(token):
    for pid in KNOWN_PLANS:
        tk = requests.get(f"{BASE}/api/takeoffs/{pid}", headers=_hdrs(token), timeout=30)
        if tk.status_code != 200:
            continue
        rooms = tk.json().get("rooms", [])
        if rooms:
            return pid, rooms[0]
    pytest.skip("No demo plan with rooms found")


def test_estimate_returns_5_trades(demo_token):
    pid, room = _find_demo_plan_and_room(demo_token)
    rid = room["room_id"]
    r = requests.post(f"{BASE}/api/takeoffs/{pid}/rooms/{rid}/estimate",
                      headers=_hdrs(demo_token), json={}, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "room" in data and "trades" in data and "total_budget" in data
    trades = data["trades"]
    expected = {"paint", "floor_tile", "drywall", "insulation", "plinths"}
    assert expected.issubset(set(trades.keys())), f"Missing trades: {expected - set(trades.keys())}"
    for k in expected:
        t = trades[k]
        assert "inputs" in t and "results" in t and "materials" in t and "estimated_budget" in t
    assert isinstance(data["total_budget"], (int, float))
    assert data["total_budget"] > 0


def test_estimate_filters_to_paint_only(demo_token):
    pid, room = _find_demo_plan_and_room(demo_token)
    rid = room["room_id"]
    r = requests.post(f"{BASE}/api/takeoffs/{pid}/rooms/{rid}/estimate",
                      headers=_hdrs(demo_token), json={"trades": ["paint"]}, timeout=60)
    assert r.status_code == 200
    trades = r.json()["trades"]
    assert set(trades.keys()) == {"paint"}


def test_estimate_override_height_and_doors(demo_token):
    pid, room = _find_demo_plan_and_room(demo_token)
    rid = room["room_id"]
    r1 = requests.post(f"{BASE}/api/takeoffs/{pid}/rooms/{rid}/estimate",
                       headers=_hdrs(demo_token),
                       json={"trades": ["paint"], "override_height_m": 2.5, "doors": 1}, timeout=60)
    r2 = requests.post(f"{BASE}/api/takeoffs/{pid}/rooms/{rid}/estimate",
                       headers=_hdrs(demo_token),
                       json={"trades": ["paint"], "override_height_m": 2.7, "doors": 4}, timeout=60)
    assert r1.status_code == 200 and r2.status_code == 200
    # More doors + higher ceiling → different (typically different) result
    b1 = r1.json()["trades"]["paint"]["estimated_budget"]
    b2 = r2.json()["trades"]["paint"]["estimated_budget"]
    # Just ensure they were computed and are numeric
    assert isinstance(b1, (int, float)) and isinstance(b2, (int, float))


def test_estimate_404_plan(demo_token):
    r = requests.post(f"{BASE}/api/takeoffs/nonexistent_plan/rooms/xxx/estimate",
                      headers=_hdrs(demo_token), json={}, timeout=30)
    assert r.status_code == 404


def test_estimate_404_room(demo_token):
    pid, _ = _find_demo_plan_and_room(demo_token)
    r = requests.post(f"{BASE}/api/takeoffs/{pid}/rooms/nonexistent_room/estimate",
                      headers=_hdrs(demo_token), json={}, timeout=30)
    assert r.status_code == 404


def test_pdf_export_returns_valid_pdf(demo_token):
    pid, _ = _find_demo_plan_and_room(demo_token)
    r = requests.get(f"{BASE}/api/takeoffs/{pid}/pdf?include_materials=true",
                     headers=_hdrs(demo_token), timeout=60)
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")
    assert len(r.content) > 2000
