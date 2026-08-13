"""Iter 58 — HTTP roundtrip tests for /api/tool-presets + PATCH /rooms/{id}.

Uses live REACT_APP_BACKEND_URL and admin@construpilot.fr credentials.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PASS = "Construpilot2026!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ============ Tool Presets CRUD ============

def test_list_presets_returns_dict_with_presets_array(h):
    r = requests.get(f"{BASE_URL}/api/tool-presets", headers=h, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "presets" in body
    assert isinstance(body["presets"], list)


def test_create_preset_returns_full_object(h):
    payload = {"name": "TEST_iter58 mur", "kind": "wall", "unit": "m²",
               "color": "#123456", "price_per_unit": 42.5,
               "params": {"thickness_mm": 100}, "notes": "  test  "}
    r = requests.post(f"{BASE_URL}/api/tool-presets", headers=h, json=payload, timeout=10)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["preset_id"].startswith("tpr_")
    assert doc["name"] == "TEST_iter58 mur"
    assert doc["kind"] == "wall"
    assert doc["unit"] == "m²"
    assert doc["color"] == "#123456"
    assert doc["price_per_unit"] == 42.5
    assert doc["notes"] == "test"  # trimmed
    assert "user_id" in doc
    assert "created_at" in doc

    # Cleanup: delete
    dr = requests.delete(f"{BASE_URL}/api/tool-presets/{doc['preset_id']}",
                         headers=h, timeout=10)
    assert dr.status_code == 200


def test_create_normalizes_invalid_kind_to_other(h):
    r = requests.post(f"{BASE_URL}/api/tool-presets", headers=h,
                      json={"name": "TEST_iter58 x", "kind": "INVALID_KIND"}, timeout=10)
    assert r.status_code == 200
    doc = r.json()
    assert doc["kind"] == "other"
    assert doc["color"] == "#f97316"  # default
    assert doc["unit"] == "u"  # default
    # cleanup
    requests.delete(f"{BASE_URL}/api/tool-presets/{doc['preset_id']}", headers=h, timeout=10)


def test_patch_preset_updates_fields(h):
    # create
    r = requests.post(f"{BASE_URL}/api/tool-presets", headers=h,
                      json={"name": "TEST_iter58 to_update", "kind": "wall"}, timeout=10)
    pid = r.json()["preset_id"]
    # patch
    pr = requests.patch(f"{BASE_URL}/api/tool-presets/{pid}", headers=h,
                        json={"name": "TEST_iter58 updated", "kind": "floor",
                              "unit": "m²", "price_per_unit": 99.0}, timeout=10)
    assert pr.status_code == 200
    updated = pr.json()
    assert updated["name"] == "TEST_iter58 updated"
    assert updated["kind"] == "floor"
    assert updated["price_per_unit"] == 99.0
    # cleanup
    requests.delete(f"{BASE_URL}/api/tool-presets/{pid}", headers=h, timeout=10)


def test_patch_unknown_preset_404(h):
    r = requests.patch(f"{BASE_URL}/api/tool-presets/tpr_doesnotexist", headers=h,
                       json={"name": "x"}, timeout=10)
    assert r.status_code == 404


def test_delete_unknown_preset_404(h):
    r = requests.delete(f"{BASE_URL}/api/tool-presets/tpr_ghost", headers=h, timeout=10)
    assert r.status_code == 404


def test_seed_defaults_idempotent_for_admin(h):
    """Admin already has presets seeded — seed-defaults must be idempotent."""
    r = requests.post(f"{BASE_URL}/api/tool-presets/seed-defaults", headers=h, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["created"] == 0
    assert body.get("already_had", 0) >= 6


def test_seed_defaults_new_user_creates_6():
    """Create a new user then call seed-defaults twice."""
    import secrets
    email = f"test_iter58_{secrets.token_hex(4)}@construpilot.fr"
    reg = requests.post(f"{BASE_URL}/api/auth/register",
                        json={"email": email, "password": "Testpass2026!",
                              "name": "Iter58 Seed Test"}, timeout=10)
    if reg.status_code != 200:
        pytest.skip(f"Registration failed: {reg.status_code} {reg.text}")
    token = reg.json().get("token")
    if not token:
        # some register endpoints just return ok — login
        lg = requests.post(f"{BASE_URL}/api/auth/login",
                           json={"email": email, "password": "Testpass2026!"}, timeout=10)
        token = lg.json()["token"]
    nh = {"Authorization": f"Bearer {token}"}

    # First call — creates 6
    r1 = requests.post(f"{BASE_URL}/api/tool-presets/seed-defaults", headers=nh, timeout=10)
    assert r1.status_code == 200, r1.text
    b1 = r1.json()
    assert b1["ok"] is True
    assert b1["created"] == 6
    assert len(b1["presets"]) == 6
    kinds = [p["kind"] for p in b1["presets"]]
    assert "wall" in kinds and "floor" in kinds and "paint" in kinds and "insulation" in kinds

    # Second call — idempotent (created 0)
    r2 = requests.post(f"{BASE_URL}/api/tool-presets/seed-defaults", headers=nh, timeout=10)
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["created"] == 0
    assert b2["already_had"] == 6


# ============ PATCH /rooms/{room_id} ============

def test_patch_room_404_when_room_not_exist(h):
    # Find any admin plan
    lst = requests.get(f"{BASE_URL}/api/takeoffs", headers=h, timeout=10)
    assert lst.status_code == 200
    plans = lst.json().get("plans", [])
    if not plans:
        pytest.skip("No admin plans available")
    plan_id = plans[0]["plan_id"]
    r = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/rooms/nonexistent_room",
                       headers=h, json={"name": "X"}, timeout=10)
    assert r.status_code == 404


def test_patch_room_422_empty_name(h):
    lst = requests.get(f"{BASE_URL}/api/takeoffs", headers=h, timeout=10)
    plans = lst.json().get("plans", [])
    if not plans:
        pytest.skip("No admin plans available")
    plan_id = plans[0]["plan_id"]
    r = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/rooms/whatever",
                       headers=h, json={"name": "   "}, timeout=10)
    assert r.status_code == 422


def test_patch_room_422_bad_height(h):
    lst = requests.get(f"{BASE_URL}/api/takeoffs", headers=h, timeout=10)
    plans = lst.json().get("plans", [])
    if not plans:
        pytest.skip("No admin plans available")
    plan_id = plans[0]["plan_id"]
    for bad in [0, -1, 25]:
        r = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/rooms/x",
                           headers=h, json={"height_m": bad}, timeout=10)
        assert r.status_code == 422, f"height_m={bad} should be 422 got {r.status_code}"


def test_patch_room_422_no_fields(h):
    lst = requests.get(f"{BASE_URL}/api/takeoffs", headers=h, timeout=10)
    plans = lst.json().get("plans", [])
    if not plans:
        pytest.skip("No admin plans available")
    plan_id = plans[0]["plan_id"]
    r = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/rooms/x",
                       headers=h, json={}, timeout=10)
    assert r.status_code == 422
