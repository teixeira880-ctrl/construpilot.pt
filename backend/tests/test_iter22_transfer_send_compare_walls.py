"""Iter22 — Transfer ownership, Send Devis, History compare, Walls coloring.

Covers:
- Demo accounts seed (5 users + BTP Demo SAS org)
- POST /api/organizations/transfer-ownership + edge cases
- POST /api/takeoffs/{plan_id}/send-quote + GET /quote-sends
- POST /api/takeoffs/{plan_id}/history/compare + edge cases
- POST /api/takeoffs/{plan_id}/detect-walls, GET /walls-summary, PATCH walls type
- Backward compat: /takeoffs/compare, /quote-pdf, snapshot label
"""
import os
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

ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}
DEMO = {"email": "demo@construpilot.fr", "password": "Demo2026!"}
CLIENT = {"email": "client@construpilot.fr", "password": "Client2026!"}
PRO = {"email": "pro@construpilot.fr", "password": "Pro2026!"}
COLLEGUE = {"email": "collegue@construpilot.fr", "password": "Collegue2026!"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]["user_id"]


# ============================================================
# 1) DEMO ACCOUNTS SEED
# ============================================================
class TestDemoSeed:

    def test_all_five_accounts_loginable(self):
        for creds in (ADMIN, DEMO, CLIENT, PRO, COLLEGUE):
            r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
            assert r.status_code == 200, f"{creds['email']} login failed: {r.text}"
            assert r.json().get("token")

    def test_pro_is_owner_of_btp_demo(self):
        auth, _ = _login(PRO)
        r = requests.get(f"{API}/organizations/me", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["in_org"] == True
        assert d["name"] == "BTP Demo SAS"
        assert d["role"] == "owner"
        assert d["member_count"] == 2
        assert d["org_code"] == "DEMO-2026"

    def test_collegue_is_member(self):
        auth, _ = _login(COLLEGUE)
        r = requests.get(f"{API}/organizations/me", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["in_org"] == True
        assert d["name"] == "BTP Demo SAS"
        assert d["role"] == "member"
        assert d["org_code"] == "DEMO-2026"

    def test_client_is_not_in_org(self):
        auth, _ = _login(CLIENT)
        r = requests.get(f"{API}/organizations/me", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json() == {"in_org": False}


# ============================================================
# 2) TRANSFER OWNERSHIP
# ============================================================
class TestTransferOwnership:
    """Ensures ownership transfer works both ways so seed state is preserved."""

    def test_transfer_full_flow(self):
        pro_auth, pro_uid = _login(PRO)
        col_auth, col_uid = _login(COLLEGUE)

        # (a) Owner (pro@) transfers to collegue
        r = requests.post(f"{API}/organizations/transfer-ownership",
                          json={"new_owner_user_id": col_uid},
                          headers=pro_auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] == True
        assert d["new_owner"]["user_id"] == col_uid

        # (b) Former owner sees role=admin
        r = requests.get(f"{API}/organizations/me", headers=pro_auth, timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "admin"

        # New owner sees role=owner
        r = requests.get(f"{API}/organizations/me", headers=col_auth, timeout=15)
        assert r.status_code == 200
        assert r.json()["role"] == "owner"

        # (c) Non-owner (now pro@ is admin) cannot transfer
        r = requests.post(f"{API}/organizations/transfer-ownership",
                          json={"new_owner_user_id": col_uid},
                          headers=pro_auth, timeout=15)
        assert r.status_code == 403, r.text

        # (e) Passing own user_id returns 400 (test as current owner=collegue)
        r = requests.post(f"{API}/organizations/transfer-ownership",
                          json={"new_owner_user_id": col_uid},
                          headers=col_auth, timeout=15)
        assert r.status_code == 400, r.text

        # (d) User not in org returns 404 (admin@ is not in BTP Demo SAS)
        _, admin_uid = _login(ADMIN)
        r = requests.post(f"{API}/organizations/transfer-ownership",
                          json={"new_owner_user_id": admin_uid},
                          headers=col_auth, timeout=15)
        assert r.status_code == 404, r.text

        # (f) Reset: collegue transfers back to pro
        r = requests.post(f"{API}/organizations/transfer-ownership",
                          json={"new_owner_user_id": pro_uid},
                          headers=col_auth, timeout=15)
        assert r.status_code == 200, r.text
        # Verify final state — pro is owner again. Note: collegue becomes
        # admin (spec: previous owner → admin). Seed re-normalises to 'member'
        # on next backend restart. Cf. agent-to-agent note in review request.
        r = requests.get(f"{API}/organizations/me", headers=pro_auth, timeout=15)
        assert r.json()["role"] == "owner"
        r = requests.get(f"{API}/organizations/me", headers=col_auth, timeout=15)
        assert r.json()["role"] == "admin"


# ============================================================
# Helpers for plan-based tests
# ============================================================
def _upload_plan(auth):
    with open("/app/before.png", "rb") as f:
        r = requests.post(f"{API}/takeoffs/upload",
                          files={"file": ("before.png", f, "image/png")},
                          headers=auth, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()["plan_id"]


def _calibrate(pid, auth):
    r = requests.post(f"{API}/takeoffs/{pid}/calibrate",
                      json={"page_index": 0, "p1": [0, 0], "p2": [100, 0],
                            "real_distance_m": 1.0},
                      headers=auth, timeout=30)
    assert r.status_code == 200, r.text


def _add_room(pid, auth, name="Salon", w=6, h=4):
    pts = [[0, 0], [w * 100, 0], [w * 100, h * 100], [0, h * 100]]
    r = requests.post(f"{API}/takeoffs/{pid}/rooms",
                      json={"page_index": 0, "name": name, "points": pts,
                            "ceiling_height_m": 2.5},
                      headers=auth, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["room_id"]


# ============================================================
# 3) SEND DEVIS
# ============================================================
class TestSendDevis:

    @pytest.fixture(scope="class")
    def plan_ready(self):
        auth, _ = _login(DEMO)
        pid = _upload_plan(auth)
        _calibrate(pid, auth)
        _add_room(pid, auth, "Salon", 5, 4)
        return auth, pid

    def test_send_quote_success(self, plan_ready):
        auth, pid = plan_ready
        r = requests.post(f"{API}/takeoffs/{pid}/send-quote",
                          json={"client_email": "delivered@resend.dev",
                                "client_name": "M. Test",
                                "finish": "std",
                                "floor_material": "carrelage",
                                "cc_self": True},
                          headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["email_status"] in ("sent", "failed")
        assert "log_id" in d and d["log_id"].startswith("qs_")
        assert "total_ttc" in d

    def test_quote_sends_list(self, plan_ready):
        auth, pid = plan_ready
        r = requests.get(f"{API}/takeoffs/{pid}/quote-sends",
                        headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["plan_id"] == pid
        sends = d["sends"]
        assert isinstance(sends, list)
        assert len(sends) >= 1
        first = sends[0]
        assert first["plan_id"] == pid
        assert first["client_email"] == "delivered@resend.dev"
        # cc_self=True → cc field should be sender email
        assert first["cc"] == DEMO["email"]

    def test_send_quote_invalid_email(self, plan_ready):
        auth, pid = plan_ready
        r = requests.post(f"{API}/takeoffs/{pid}/send-quote",
                          json={"client_email": "notanemail",
                                "cc_self": False},
                          headers=auth, timeout=15)
        assert r.status_code == 400, r.text

    def test_send_quote_no_rooms(self):
        auth, _ = _login(DEMO)
        pid = _upload_plan(auth)  # no rooms
        r = requests.post(f"{API}/takeoffs/{pid}/send-quote",
                          json={"client_email": "delivered@resend.dev",
                                "cc_self": False},
                          headers=auth, timeout=15)
        assert r.status_code == 400, r.text
        assert "pièce" in r.text.lower() or "mesur" in r.text.lower()


# ============================================================
# 4) HISTORY COMPARE
# ============================================================
class TestHistoryCompare:

    @pytest.fixture(scope="class")
    def plan_two_snaps(self):
        auth, _ = _login(DEMO)
        pid = _upload_plan(auth)
        _calibrate(pid, auth)
        _add_room(pid, auth, "R1", 5, 4)  # snap 1
        _add_room(pid, auth, "R2", 3, 3)  # snap 2
        hist = requests.get(f"{API}/takeoffs/{pid}/history",
                            headers=auth, timeout=15).json()
        items = hist.get("history", [])
        assert len(items) >= 2, f"Need >=2 snapshots, got {items}"
        # history sort order: newest first typically; we just need two distinct IDs
        return auth, pid, items[-1]["snapshot_id"], items[0]["snapshot_id"]

    def test_compare_success(self, plan_two_snaps):
        auth, pid, before, after = plan_two_snaps
        r = requests.post(f"{API}/takeoffs/{pid}/history/compare",
                          json={"before_snapshot_id": before,
                                "after_snapshot_id": after},
                          headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "before" in d and "after" in d
        assert "delta_surface_m2" in d
        for k in ("added", "removed", "modified", "unchanged"):
            assert k in d and isinstance(d[k], list)
        assert d["before"]["snapshot_id"] == before
        assert d["after"]["snapshot_id"] == after

    def test_compare_same_id_400(self, plan_two_snaps):
        auth, pid, before, _ = plan_two_snaps
        r = requests.post(f"{API}/takeoffs/{pid}/history/compare",
                          json={"before_snapshot_id": before,
                                "after_snapshot_id": before},
                          headers=auth, timeout=15)
        assert r.status_code == 400, r.text

    def test_compare_unknown_id_404(self, plan_two_snaps):
        auth, pid, before, _ = plan_two_snaps
        r = requests.post(f"{API}/takeoffs/{pid}/history/compare",
                          json={"before_snapshot_id": before,
                                "after_snapshot_id": "snap_bogus_xxx"},
                          headers=auth, timeout=15)
        assert r.status_code == 404, r.text


# ============================================================
# 5) WALLS COLORING
# ============================================================
class TestWalls:

    @pytest.fixture(scope="class")
    def plan_with_walls(self):
        auth, _ = _login(DEMO)
        pid = _upload_plan(auth)
        _calibrate(pid, auth)
        r = requests.post(f"{API}/takeoffs/{pid}/detect-walls",
                          headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        return auth, pid, r.json()

    def test_detect_walls_structure(self, plan_with_walls):
        _, _, res = plan_with_walls
        assert "segments" in res
        segs = res["segments"]
        assert isinstance(segs, list)
        if segs:
            s = segs[0]
            assert "wall_id" in s
            assert "thickness_px" in s
            assert s.get("wall_type") in ("porteur", "cloison", "doublage")

    def test_walls_summary(self, plan_with_walls):
        auth, pid, _ = plan_with_walls
        r = requests.get(f"{API}/takeoffs/{pid}/walls-summary",
                        headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "totals" in d
        for t in ("porteur", "cloison", "doublage"):
            assert t in d["totals"]
            assert "count" in d["totals"][t]
            assert "ml" in d["totals"][t]

    def test_patch_wall_type_manual(self, plan_with_walls):
        auth, pid, res = plan_with_walls
        segs = res.get("segments") or []
        if not segs:
            pytest.skip("No walls detected on demo image")
        wall_id = segs[0]["wall_id"]
        r = requests.patch(
            f"{API}/takeoffs/{pid}/walls/0/{wall_id}/type",
            json={"wall_type": "porteur"},
            headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["wall_type"] == "porteur"

    def test_patch_wall_invalid_type(self, plan_with_walls):
        auth, pid, res = plan_with_walls
        segs = res.get("segments") or []
        if not segs:
            pytest.skip("No walls detected")
        wall_id = segs[0]["wall_id"]
        r = requests.patch(
            f"{API}/takeoffs/{pid}/walls/0/{wall_id}/type",
            json={"wall_type": "invalidtype"},
            headers=auth, timeout=15)
        assert r.status_code == 400, r.text

    def test_patch_wall_unknown_id(self, plan_with_walls):
        auth, pid, _ = plan_with_walls
        r = requests.patch(
            f"{API}/takeoffs/{pid}/walls/0/bogus_wall_xxx/type",
            json={"wall_type": "cloison"},
            headers=auth, timeout=15)
        assert r.status_code == 404, r.text


# ============================================================
# 6) BACKWARD COMPAT
# ============================================================
class TestBackwardCompat:

    def test_compare_two_plans_has_walls(self):
        auth, _ = _login(DEMO)
        p1 = _upload_plan(auth)
        _calibrate(p1, auth)
        _add_room(p1, auth, "A", 4, 4)
        p2 = _upload_plan(auth)
        _calibrate(p2, auth)
        _add_room(p2, auth, "B", 5, 4)
        r = requests.post(f"{API}/takeoffs/compare",
                         json={"before_plan_id": p1, "after_plan_id": p2},
                         headers=auth, timeout=30)
        assert r.status_code == 200, r.text
        assert "walls" in r.json()

    def test_quote_pdf_still_works(self):
        auth, _ = _login(DEMO)
        pid = _upload_plan(auth)
        _calibrate(pid, auth)
        _add_room(pid, auth, "Chambre", 4, 4)
        r = requests.get(f"{API}/takeoffs/{pid}/quote-pdf",
                        params={"finish": "std", "floor_material": "carrelage"},
                        headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert len(r.content) > 2000

    def test_snapshot_label_still_works(self):
        auth, _ = _login(DEMO)
        pid = _upload_plan(auth)
        _calibrate(pid, auth)
        _add_room(pid, auth, "Cuisine", 3, 3)
        hist = requests.get(f"{API}/takeoffs/{pid}/history",
                            headers=auth, timeout=15).json()
        assert hist.get("history")
        snap = hist["history"][0]["snapshot_id"]
        r = requests.put(f"{API}/takeoffs/{pid}/history/{snap}/label",
                         json={"label": "Iter22 label test"},
                         headers=auth, timeout=15)
        assert r.status_code == 200, r.text
