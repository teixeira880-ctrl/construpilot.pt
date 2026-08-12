"""Iter19 — PDF export, auto-history snapshots, restore, compare visual backing."""
import os
import base64
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
    return v.rstrip("/")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

DEMO = {"email": "demo@construpilot.fr", "password": "Demo2026!"}


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json=DEMO, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth(token):
    return {"Authorization": f"Bearer {token}"}


def _upload_plan(auth):
    with open("/app/before.png", "rb") as f:
        r = requests.post(f"{API}/takeoffs/upload",
                          files={"file": ("before.png", f, "image/png")},
                          headers=auth, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()["plan_id"]


def _calibrate(plan_id, auth):
    body = {"page_index": 0, "p1": [0, 0], "p2": [100, 0], "real_distance_m": 1.0}
    r = requests.post(f"{API}/takeoffs/{plan_id}/calibrate", json=body, headers=auth, timeout=30)
    assert r.status_code == 200, r.text


def _add_room(plan_id, auth, name, w_m=6, h_m=4):
    # ppm=100 (100px = 1m). Rectangle w×h meters
    pts = [[0, 0], [w_m * 100, 0], [w_m * 100, h_m * 100], [0, h_m * 100]]
    body = {"page_index": 0, "name": name, "points": pts, "ceiling_height_m": 2.5}
    r = requests.post(f"{API}/takeoffs/{plan_id}/rooms", json=body, headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["room_id"]


# ---------- PDF EXPORT ----------
class TestPdfExport:
    def test_pdf_export_full(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        _add_room(plan_id, auth, "Salon", 6, 4)
        _add_room(plan_id, auth, "Cuisine", 3, 3)
        r = requests.get(f"{API}/takeoffs/{plan_id}/pdf", headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert f"metre-{plan_id}.pdf" in r.headers.get("content-disposition", "")
        assert len(r.content) > 2000
        assert r.content[:5] == b"%PDF-"

    def test_pdf_no_materials(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        _add_room(plan_id, auth, "Salon", 6, 4)
        r_full = requests.get(f"{API}/takeoffs/{plan_id}/pdf", headers=auth, timeout=60)
        r_nom = requests.get(f"{API}/takeoffs/{plan_id}/pdf",
                             params={"include_materials": "false"}, headers=auth, timeout=60)
        assert r_nom.status_code == 200
        assert r_nom.content[:5] == b"%PDF-"
        # Shorter or equal
        assert len(r_nom.content) <= len(r_full.content)

    def test_pdf_floor_material_carrelage(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        _add_room(plan_id, auth, "SDB", 3, 2)
        r = requests.get(f"{API}/takeoffs/{plan_id}/pdf",
                         params={"floor_material": "carrelage"}, headers=auth, timeout=60)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_pdf_no_rooms(self, auth):
        plan_id = _upload_plan(auth)
        r = requests.get(f"{API}/takeoffs/{plan_id}/pdf", headers=auth, timeout=60)
        assert r.status_code == 200
        assert r.content[:5] == b"%PDF-"

    def test_pdf_unknown_plan(self, auth):
        r = requests.get(f"{API}/takeoffs/plan_nope123/pdf", headers=auth, timeout=30)
        assert r.status_code == 404


# ---------- HISTORY ----------
class TestHistory:
    def test_snapshots_count_after_mutations(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)                       # snap 1
        rid1 = _add_room(plan_id, auth, "Salon", 6, 4)  # snap 2
        _add_room(plan_id, auth, "Cuisine", 3, 3)       # snap 3
        # Delete
        rd = requests.delete(f"{API}/takeoffs/{plan_id}/rooms/{rid1}", headers=auth, timeout=30)
        assert rd.status_code == 200                    # snap 4
        r = requests.get(f"{API}/takeoffs/{plan_id}/history", headers=auth, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 4
        actions = [s["action"] for s in data["history"]]
        # DESC sorted, first is most recent (room_delete)
        assert actions[0] == "room_delete"
        assert actions[-1] == "calibrate"
        # Schema check
        s0 = data["history"][0]
        for k in ("snapshot_id", "plan_id", "action", "rooms", "calibrations",
                  "page_levels", "created_at", "meta"):
            assert k in s0, f"missing key {k}"

    def test_restore_oldest_snapshot(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        _add_room(plan_id, auth, "Salon", 6, 4)
        _add_room(plan_id, auth, "Cuisine", 3, 3)
        # Snapshots are captured BEFORE each mutation:
        #   [0] room_upsert (Cuisine)  -> state has Salon + calibrations
        #   [1] room_upsert (Salon)    -> state has 0 rooms + calibrations
        #   [2] calibrate              -> state has 0 rooms + no calibrations
        # We want state with calibrations but 0 rooms -> [1] (2nd oldest)
        h = requests.get(f"{API}/takeoffs/{plan_id}/history", headers=auth, timeout=30).json()
        target = h["history"][-2]
        assert target["action"] == "room_upsert"
        assert len(target["rooms"]) == 0
        snap_id = target["snapshot_id"]
        r = requests.post(f"{API}/takeoffs/{plan_id}/history/restore/{snap_id}",
                          headers=auth, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["restored_from"] == snap_id
        # Confirm plan state
        p = requests.get(f"{API}/takeoffs/{plan_id}", headers=auth, timeout=30).json()
        assert p["rooms"] == []
        assert p["calibrations"]  # still present

    def test_restore_unknown_snap(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)
        r = requests.post(f"{API}/takeoffs/{plan_id}/history/restore/snap_nope",
                          headers=auth, timeout=30)
        assert r.status_code == 404

    def test_restore_unknown_plan(self, auth):
        r = requests.post(f"{API}/takeoffs/plan_nope999/history/restore/snap_x",
                          headers=auth, timeout=30)
        assert r.status_code == 404

    def test_history_cap_50(self, auth):
        plan_id = _upload_plan(auth)
        _calibrate(plan_id, auth)  # 1 snapshot
        # 54 more mutations upsert -> total 55
        for i in range(54):
            _add_room(plan_id, auth, f"R{i}", 2, 2)
        r = requests.get(f"{API}/takeoffs/{plan_id}/history", headers=auth, timeout=60).json()
        assert r["count"] == 50


# ---------- COMPARE VISUAL backing ----------
class TestCompareBacking:
    def test_page_image_available(self, auth):
        plan_id = _upload_plan(auth)
        r = requests.get(f"{API}/takeoffs/{plan_id}/page/0", headers=auth, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("image_png_b64")
        assert len(d["image_png_b64"]) > 100
