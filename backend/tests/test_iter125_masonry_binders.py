"""Iter 125 - Test masonry binders (liants) in materials calculator + room estimate.

Feature: adds masonry binders to cart calculator + room estimate.
- parpaing: ciment + sable (mortier traditionnel)
- brique + bond=mousse: cartouches mousse PU
- brique + bond=colle: mortier-colle joint mince 25 kg
- carrelage: adds 'Natte de désolidarisation' + 'Baguettes de finition (profilés)'
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def demo_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@construpilot.fr", "password": "Demo2026!"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json().get("access_token") or r.json().get("token")


# ==================== calculator /materials ====================

def _names(items):
    return [it.get("name", "") for it in items]


def test_materials_parpaing_includes_ciment_and_sable(api):
    r = api.post(f"{BASE_URL}/api/estimation/materials", json={
        "lots": [{"key": "parpaing", "quantity": 30}]
    })
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    names = " | ".join(_names(items)).lower()
    assert "parpaing" in names
    assert "ciment" in names, f"missing Ciment in {names}"
    assert "sable" in names, f"missing Sable in {names}"


def test_materials_brique_mousse(api):
    r = api.post(f"{BASE_URL}/api/estimation/materials", json={
        "lots": [{"key": "brique", "quantity": 15, "bond": "mousse"}]
    })
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    names = " | ".join(_names(items)).lower()
    assert "brique" in names
    assert "mousse" in names, f"missing mousse PU in {names}"


def test_materials_brique_colle(api):
    r = api.post(f"{BASE_URL}/api/estimation/materials", json={
        "lots": [{"key": "brique", "quantity": 15, "bond": "colle"}]
    })
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    names = " | ".join(_names(items)).lower()
    assert "mortier-colle" in names or "mortier colle" in names, f"missing mortier-colle in {names}"


def test_materials_carrelage_has_natte_and_baguettes(api):
    r = api.post(f"{BASE_URL}/api/estimation/materials", json={
        "lots": [{"key": "carrelage", "quantity": 25}]
    })
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    names_l = " | ".join(_names(items)).lower()
    assert "natte" in names_l, f"missing Natte de désolidarisation in {names_l}"
    assert "baguette" in names_l or "profil" in names_l, f"missing Baguettes de finition in {names_l}"


# ==================== room estimate ====================

PLAN_ID = "plan_6017c355084d"


def _get_room_id(api, token):
    r = api.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    plan = r.json()
    rooms = plan.get("rooms") or []
    if not rooms:
        # try alternative key
        objs = plan.get("objects") or []
        rooms = [o for o in objs if o.get("type") == "room"]
    assert rooms, f"no rooms in plan: keys={list(plan.keys())}"
    return rooms[0].get("id") or rooms[0].get("room_id")


def test_room_estimate_masonry_parpaing(api, demo_token):
    room_id = _get_room_id(api, demo_token)
    r = api.post(
        f"{BASE_URL}/api/takeoffs/{PLAN_ID}/rooms/{room_id}/estimate",
        headers={"Authorization": f"Bearer {demo_token}"},
        json={"trades": ["floor_tile", "masonry"], "masonry_material": "parpaing"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    trades = data.get("trades") or {}
    assert "masonry" in trades, f"trades keys: {list(trades.keys())}"
    mats = trades["masonry"].get("materials", [])
    names = " | ".join(m.get("name", "") for m in mats).lower()
    assert "parpaing" in names
    assert "ciment" in names
    assert "sable" in names


def test_room_estimate_masonry_brique_mousse(api, demo_token):
    room_id = _get_room_id(api, demo_token)
    r = api.post(
        f"{BASE_URL}/api/takeoffs/{PLAN_ID}/rooms/{room_id}/estimate",
        headers={"Authorization": f"Bearer {demo_token}"},
        json={"trades": ["masonry"], "masonry_material": "brique", "masonry_bond": "mousse"},
    )
    assert r.status_code == 200, r.text
    trades = r.json().get("trades") or {}
    assert "masonry" in trades
    names = " | ".join(m.get("name", "") for m in trades["masonry"].get("materials", [])).lower()
    assert "brique" in names
    assert "mousse" in names


def test_room_estimate_floor_tile_has_natte_baguettes(api, demo_token):
    room_id = _get_room_id(api, demo_token)
    r = api.post(
        f"{BASE_URL}/api/takeoffs/{PLAN_ID}/rooms/{room_id}/estimate",
        headers={"Authorization": f"Bearer {demo_token}"},
        json={"trades": ["floor_tile"]},
    )
    assert r.status_code == 200, r.text
    trades = r.json().get("trades") or {}
    assert "floor_tile" in trades, list(trades.keys())
    names = " | ".join(m.get("name", "") for m in trades["floor_tile"].get("materials", [])).lower()
    assert "natte" in names, f"missing natte in {names}"
    assert "baguette" in names or "profil" in names, f"missing baguettes in {names}"
