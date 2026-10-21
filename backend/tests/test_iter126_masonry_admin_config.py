"""Iter 126 - Test masonry admin config (ratios/blocks) + block choice + facade render.

Backend features tested:
- GET /api/estimation/masonry-config (public, defaults)
- PUT /api/estimation/masonry-config (admin only; 403 for non-admin, 401 anon)
- POST /api/estimation/masonry-config/reset (admin)
- POST /api/estimation/materials with lot.block, lot.include_render, lot.bond
- POST /api/takeoffs/{plan}/rooms/{room}/estimate with masonry_block + masonry_render

Always resets config at teardown so defaults restored.
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PASS = "Construpilot2026!"
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASS = "Pro2026!"
DEMO_EMAIL = "demo@construpilot.fr"
DEMO_PASS = "Demo2026!"


@pytest.fixture(scope="module")
def api():
    # NB: use a fresh session per test to avoid httpOnly cookie leak between users
    return requests

def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(_api, email, password):
    # Use a fresh session so cookies from other users don't leak
    tmp = requests.Session()
    tmp.headers.update({"Content-Type": "application/json"})
    r = tmp.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    d = r.json()
    return d.get("access_token") or d.get("token")


@pytest.fixture(scope="module")
def admin_token(api):
    return _login(api, ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def pro_token(api):
    return _login(api, PRO_EMAIL, PRO_PASS)


@pytest.fixture(scope="module")
def demo_token(api):
    return _login(api, DEMO_EMAIL, DEMO_PASS)


def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module", autouse=True)
def _reset_config_after_all(api, admin_token):
    yield
    # Always reset defaults so we don't pollute future tests
    api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))


# ============================================================================
# 1. GET /masonry-config default shape
# ============================================================================
def test_get_masonry_config_defaults(api, admin_token):
    # Ensure defaults first
    api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))
    r = api.get(f"{BASE_URL}/api/estimation/masonry-config")
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert "ratios" in cfg and "blocks" in cfg
    ratios = cfg["ratios"]
    for k in ("loss_pct", "cement_kg_per_m2", "sand_m3_per_m2", "glue_kg_per_m2",
              "foam_m2_per_can", "render_kg_per_m2", "gobetis_kg_per_m2"):
        assert k in ratios, f"missing ratio {k}"
    assert ratios["cement_kg_per_m2"] == 7.0
    blocks = cfg["blocks"]
    assert len(blocks) == 4
    keys = {b["key"] for b in blocks}
    assert keys == {"parpaing_20", "parpaing_15", "brique_creuse_20", "brique_rouge"}
    for b in blocks:
        for f in ("label", "material", "blocks_per_m2", "price", "search"):
            assert f in b, f"missing field {f} in block {b}"


# ============================================================================
# 2. PUT auth (401 anon, 403 non-admin, 200 admin)
# ============================================================================
def test_put_masonry_config_anon_401(api):
    r = requests.put(f"{BASE_URL}/api/estimation/masonry-config",
                     json={"ratios": {"cement_kg_per_m2": 8}})
    assert r.status_code in (401, 403), r.text


def test_put_masonry_config_non_admin_403(api, pro_token):
    r = api.put(f"{BASE_URL}/api/estimation/masonry-config",
                headers=_hdr(pro_token),
                json={"ratios": {"cement_kg_per_m2": 8}})
    assert r.status_code == 403, r.text


def test_put_masonry_config_admin_updates_ratio(api, admin_token):
    r = api.put(f"{BASE_URL}/api/estimation/masonry-config",
                headers=_hdr(admin_token),
                json={"ratios": {"cement_kg_per_m2": 9}})
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["ratios"]["cement_kg_per_m2"] == 9.0
    # verify persisted with GET
    r2 = api.get(f"{BASE_URL}/api/estimation/masonry-config")
    assert r2.json()["ratios"]["cement_kg_per_m2"] == 9.0


def test_put_masonry_config_admin_adds_block(api, admin_token):
    # Get current
    cfg = api.get(f"{BASE_URL}/api/estimation/masonry-config").json()
    new_blocks = list(cfg["blocks"]) + [{
        "key": "brique_monomur", "label": "Brique monomur 50x20x30",
        "material": "brique", "blocks_per_m2": 16, "price": 2.5, "search": "brique monomur"}]
    r = api.put(f"{BASE_URL}/api/estimation/masonry-config",
                headers=_hdr(admin_token), json={"blocks": new_blocks})
    assert r.status_code == 200, r.text
    keys = {b["key"] for b in r.json()["blocks"]}
    assert "brique_monomur" in keys


# ============================================================================
# 3. POST /materials with block + include_render
# ============================================================================
def test_materials_maconnerie_parpaing_15_with_render(api, admin_token):
    # First reset so cement ratio = default 7 for predictable result
    api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))
    r = api.post(f"{BASE_URL}/api/estimation/materials", json={
        "lots": [{"key": "maconnerie", "quantity": 40, "block": "parpaing_15",
                  "include_render": True}]
    })
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    by_name = {it["name"]: it for it in items}
    # Parpaing creux 15x20x50 : 40 * 10 * 1.05 = 420 u
    assert any("Parpaing creux 15" in n for n in by_name), f"names={list(by_name)}"
    parp = next(it for n, it in by_name.items() if "Parpaing creux 15" in n)
    assert parp["quantity"] == 420, f"expected 420 parpaing, got {parp['quantity']}"
    # Ciment: ceil(40*7/35)=8 sacs
    ciment = next(it for n, it in by_name.items() if n.lower().startswith("ciment"))
    assert ciment["quantity"] == 8, f"expected 8 ciment, got {ciment['quantity']}"
    # Sable: 40*0.03=1.2 m3
    sable = next(it for n, it in by_name.items() if "sable" in n.lower())
    assert abs(sable["quantity"] - 1.2) < 0.01
    # Gobetis: ceil(40*5/25)=8
    gob = next(it for n, it in by_name.items() if "obetis" in n.lower() or "gobetis" in n.lower())
    assert gob["quantity"] == 8
    # Enduit facade: ceil(40*25/25)=40
    enduit = next(it for n, it in by_name.items() if "enduit de fa" in n.lower())
    assert enduit["quantity"] == 40


def test_materials_maconnerie_no_render_omits_gobetis(api, admin_token):
    api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))
    r = api.post(f"{BASE_URL}/api/estimation/materials", json={
        "lots": [{"key": "maconnerie", "quantity": 40, "block": "parpaing_15"}]
    })
    assert r.status_code == 200, r.text
    names = " | ".join(it["name"].lower() for it in r.json()["items"])
    assert "gobetis" not in names
    assert "enduit de fa" not in names


def test_materials_cement_reflects_admin_ratio(api, admin_token):
    # Set cement=9
    api.put(f"{BASE_URL}/api/estimation/masonry-config",
            headers=_hdr(admin_token), json={"ratios": {"cement_kg_per_m2": 9}})
    r = api.post(f"{BASE_URL}/api/estimation/materials", json={
        "lots": [{"key": "maconnerie", "quantity": 40, "block": "parpaing_15"}]
    })
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    ciment = next(it for it in items if it["name"].lower().startswith("ciment"))
    # ceil(40*9/35) = ceil(10.28) = 11
    assert ciment["quantity"] == 11, f"expected 11, got {ciment['quantity']}"
    # Reset back
    api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))


def test_materials_brique_mousse_cartouches(api):
    r = api.post(f"{BASE_URL}/api/estimation/materials", json={
        "lots": [{"key": "brique", "quantity": 40, "bond": "mousse"}]
    })
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    mousse = next(it for it in items if "mousse" in it["name"].lower())
    # ceil(40/8) = 5
    assert mousse["quantity"] == 5, f"expected 5 cartouches, got {mousse['quantity']}"


# ============================================================================
# 4. Reset restores defaults
# ============================================================================
def test_reset_restores_defaults(api, admin_token):
    # Modify first
    api.put(f"{BASE_URL}/api/estimation/masonry-config",
            headers=_hdr(admin_token),
            json={"ratios": {"cement_kg_per_m2": 12}, "blocks": []})
    # Reset
    r = api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))
    assert r.status_code == 200, r.text
    cfg = r.json()
    assert cfg["ratios"]["cement_kg_per_m2"] == 7.0
    assert len(cfg["blocks"]) == 4


def test_reset_non_admin_403(api, pro_token):
    r = api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(pro_token))
    assert r.status_code == 403


# ============================================================================
# 5. Room estimate with masonry_block + masonry_render
# ============================================================================
PLAN_ID = "plan_6017c355084d"


def _get_room_id(api, token):
    r = api.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}", headers=_hdr(token))
    if r.status_code != 200:
        pytest.skip(f"plan {PLAN_ID} not accessible: {r.status_code}")
    plan = r.json()
    rooms = plan.get("rooms") or []
    if not rooms:
        objs = plan.get("objects") or []
        rooms = [o for o in objs if o.get("type") == "room"]
    if not rooms:
        pytest.skip("no rooms in plan")
    return rooms[0].get("id") or rooms[0].get("room_id")


def test_room_estimate_parpaing_15_with_render(api, demo_token, admin_token):
    api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))
    room_id = _get_room_id(api, demo_token)
    r = api.post(
        f"{BASE_URL}/api/takeoffs/{PLAN_ID}/rooms/{room_id}/estimate",
        headers=_hdr(demo_token),
        json={"trades": ["masonry"], "masonry_material": "parpaing",
              "masonry_block": "parpaing_15", "masonry_render": True},
    )
    assert r.status_code == 200, r.text
    trades = r.json().get("trades") or {}
    assert "masonry" in trades
    m = trades["masonry"]
    names = " | ".join(x.get("name", "") for x in m.get("materials", []))
    assert "Parpaing creux 15" in names, f"missing parpaing_15 label; got: {names}"
    assert "Gobetis" in names or "gobetis" in names.lower()
    assert "Enduit de fa" in names
    assert m.get("inputs", {}).get("include_render") is True


def test_room_estimate_uses_admin_cement_ratio(api, demo_token, admin_token):
    # Baseline default cement=7
    api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))
    room_id = _get_room_id(api, demo_token)
    body = {"trades": ["masonry"], "masonry_material": "parpaing",
            "masonry_block": "parpaing_20", "masonry_render": False}
    r1 = api.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/rooms/{room_id}/estimate",
                  headers=_hdr(demo_token), json=body)
    assert r1.status_code == 200, r1.text
    ciment1 = next((x for x in r1.json()["trades"]["masonry"]["materials"]
                    if x["name"].lower().startswith("ciment")), None)
    assert ciment1 is not None, "no ciment in baseline"
    q1 = ciment1["quantity"]

    # Set admin cement=9
    api.put(f"{BASE_URL}/api/estimation/masonry-config",
            headers=_hdr(admin_token), json={"ratios": {"cement_kg_per_m2": 9}})
    r2 = api.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/rooms/{room_id}/estimate",
                  headers=_hdr(demo_token), json=body)
    assert r2.status_code == 200, r2.text
    ciment2 = next((x for x in r2.json()["trades"]["masonry"]["materials"]
                    if x["name"].lower().startswith("ciment")), None)
    q2 = ciment2["quantity"]
    assert q2 > q1, f"cement should increase with higher ratio; q1={q1}, q2={q2}"
    # Reset
    api.post(f"{BASE_URL}/api/estimation/masonry-config/reset", headers=_hdr(admin_token))
