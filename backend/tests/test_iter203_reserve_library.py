"""Tests iter203: Feature 1 (levée de réserves portail), Feature 2 (filtre library source),
Feature 3 (library duplicates + merge). E2E via BASE_URL.
"""
import os
import time
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"
REF = "CP-PTST-0001"
CHANTIER_ID = "cht_portaltest01"


@pytest.fixture(scope="module")
def pro_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": PRO_EMAIL, "password": PRO_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def seeded_token():
    """Re-run the seed script to get a fresh invitation token."""
    import subprocess
    out = subprocess.check_output(
        ["python", "/app/backend/scripts/seed_portal_sprint3.py"],
        env={**os.environ, "PYTHONPATH": "/app/backend"},
        timeout=60,
    ).decode()
    token = None
    for line in out.splitlines():
        if line.startswith("TOKEN="):
            token = line.split("=", 1)[1].strip()
    assert token, f"seed failed to output TOKEN: {out}"
    return token


@pytest.fixture(scope="module")
def portal_session(seeded_token):
    """Accept invite → get participant_session cookie."""
    s = requests.Session()
    r = s.post(f"{BASE}/api/portal/accept/{seeded_token}", timeout=30)
    assert r.status_code == 200, f"accept failed: {r.status_code} {r.text}"
    assert s.cookies.get("participant_session"), "cookie not set"
    return s


# ---------- Feature 1: levée de réserves ----------

@pytest.fixture(scope="module")
def published_pv(pro_session):
    """Créer un PV avec 2 réserves et le publier."""
    # cleanup old
    r = pro_session.get(f"{BASE}/api/chantiers/{CHANTIER_ID}/receptions", timeout=30)
    if r.status_code == 200:
        for old in r.json():
            pro_session.delete(f"{BASE}/api/chantiers/receptions/{old['pv_id']}", timeout=30)
    r = pro_session.post(
        f"{BASE}/api/chantiers/{CHANTIER_ID}/receptions",
        json={"decision": "avec_reserve",
              "reserves": [
                  {"lot": "Peinture", "description": "Retouche peinture salon"},
                  {"lot": "Plomberie", "description": "Joint douche à refaire"},
              ]},
        timeout=30,
    )
    assert r.status_code == 201, r.text
    pv = r.json()
    assert len(pv["reserves"]) == 2
    pr = pro_session.post(f"{BASE}/api/chantiers/receptions/{pv['pv_id']}/publish", timeout=30)
    assert pr.status_code == 200
    return pv


def test_portal_receptions_lists_pv(portal_session, published_pv):
    r = portal_session.get(f"{BASE}/api/portal/{REF}/receptions", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["can_sign"] is True
    pv = next((x for x in data["receptions"] if x["pv_id"] == published_pv["pv_id"]), None)
    assert pv is not None
    assert pv["reserve_count"] == 2
    assert pv["reserve_lifted"] == 0
    assert len(pv["reserves"]) == 2
    for r_ in pv["reserves"]:
        assert r_["lifted_at"] is None


def test_portal_lift_reserve_resolved(portal_session, published_pv):
    reserve_id = published_pv["reserves"][0]["id"]
    r = portal_session.post(
        f"{BASE}/api/portal/{REF}/reception/{published_pv['pv_id']}/reserve/{reserve_id}/lift",
        json={"resolved": True}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is True
    assert j["reserve_id"] == reserve_id
    assert j["lifted_at"] is not None
    assert j["lifted_by"] == "Sophie Test"
    assert j["reserve_lifted"] == 1
    assert j["reserve_count"] == 2

    # Persistance: relire
    r2 = portal_session.get(f"{BASE}/api/portal/{REF}/receptions", timeout=30)
    pv = next(x for x in r2.json()["receptions"] if x["pv_id"] == published_pv["pv_id"])
    assert pv["reserve_lifted"] == 1
    lifted = next(x for x in pv["reserves"] if x["id"] == reserve_id)
    assert lifted["lifted_at"] is not None
    assert lifted["lifted_by"] == "Sophie Test"


def test_portal_lift_reserve_notification_created(pro_session, published_pv):
    """La notif 'reserve_lifted' doit être créée côté pro."""
    r = pro_session.get(f"{BASE}/api/notifications", timeout=30)
    if r.status_code != 200:
        pytest.skip(f"notifications endpoint unavailable: {r.status_code}")
    notifs = r.json() if isinstance(r.json(), list) else r.json().get("notifications", [])
    reserve_notifs = [n for n in notifs if n.get("type") == "reserve_lifted"]
    assert len(reserve_notifs) >= 1, "notif reserve_lifted absente"


def test_portal_lift_reserve_toggle_off(portal_session, published_pv):
    reserve_id = published_pv["reserves"][0]["id"]
    r = portal_session.post(
        f"{BASE}/api/portal/{REF}/reception/{published_pv['pv_id']}/reserve/{reserve_id}/lift",
        json={"resolved": False}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["lifted_at"] is None
    assert j["lifted_by"] is None
    assert j["reserve_lifted"] == 0


def test_portal_lift_reserve_404_unknown(portal_session, published_pv):
    r = portal_session.post(
        f"{BASE}/api/portal/{REF}/reception/{published_pv['pv_id']}/reserve/deadbeef/lift",
        json={"resolved": True}, timeout=30)
    assert r.status_code == 404


def test_portal_lift_reserve_requires_session(published_pv):
    r = requests.post(
        f"{BASE}/api/portal/{REF}/reception/{published_pv['pv_id']}/reserve/{published_pv['reserves'][0]['id']}/lift",
        json={"resolved": True}, timeout=30)
    assert r.status_code == 401


# ---------- Feature 2: filtre library source ----------

def test_library_list_returns_sources(pro_session):
    r = pro_session.get(f"{BASE}/api/library", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "items" in j and "sources" in j
    assert isinstance(j["sources"], list)


def test_library_source_filter_narrows(pro_session):
    r = pro_session.get(f"{BASE}/api/library", timeout=30)
    j = r.json()
    if not j["sources"]:
        pytest.skip("no sources available")
    # Choose first source key with count > 0
    src = j["sources"][0]
    key = src["key"]
    expected = src["count"]
    r2 = pro_session.get(f"{BASE}/api/library?source={key}", timeout=30)
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert len(items) == expected, f"source={key}: got {len(items)}, expected {expected}"
    for it in items:
        assert (it.get("source") or "manual") == key


# ---------- Feature 3: library duplicates + merge (petit groupe seulement) ----------

def test_library_duplicates_endpoint(pro_session):
    r = pro_session.get(f"{BASE}/api/library/duplicates", timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert "groups" in j
    assert "group_count" in j
    assert "duplicate_count" in j


def test_library_merge_single_group_created_via_test_items(pro_session):
    """Créer 2 items TEST_ identiques, vérifier duplicates, fusionner, vérifier suppression."""
    payload = {
        "type": "materiau",
        "category": "TEST_iter203",
        "designation": "TEST_iter203_dupe_item_xyz",
        "unit": "u",
        "unit_price_ht": 12.5,
        "cost_price_ht": 0,
        "vat_rate": 20,
        "notes": "test",
    }
    r1 = pro_session.post(f"{BASE}/api/library", json=payload, timeout=30)
    assert r1.status_code in (200, 201), r1.text
    id1 = r1.json().get("item_id") or r1.json().get("item", {}).get("item_id")
    r2 = pro_session.post(f"{BASE}/api/library", json=payload, timeout=30)
    assert r2.status_code in (200, 201)
    id2 = r2.json().get("item_id") or r2.json().get("item", {}).get("item_id")
    assert id1 and id2 and id1 != id2

    dup = pro_session.get(f"{BASE}/api/library/duplicates", timeout=30).json()
    grp = next((g for g in dup["groups"] if any(i["item_id"] in (id1, id2) for i in g["items"])), None)
    assert grp is not None, "duplicate group not detected"
    assert {i["item_id"] for i in grp["items"]} >= {id1, id2}

    # merge — keep id1, remove id2
    m = pro_session.post(f"{BASE}/api/library/merge",
                         json={"keep_id": id1, "remove_ids": [id2]}, timeout=30)
    assert m.status_code == 200, m.text
    assert m.json()["removed"] == 1

    # Vérif: id1 présent, id2 absent
    r = pro_session.get(f"{BASE}/api/library?q=TEST_iter203_dupe_item_xyz", timeout=30)
    ids = {i["item_id"] for i in r.json()["items"]}
    assert id1 in ids
    assert id2 not in ids

    # cleanup
    pro_session.delete(f"{BASE}/api/library/{id1}", timeout=30)
