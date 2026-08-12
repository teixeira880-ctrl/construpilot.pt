"""Iter21 — Team/Organization system, Snapshot naming, Walls compare diff, PDF Devis (quote-pdf).

Covers:
- Team CRUD via /api/organizations/* (create/get/join/leave/invite/remove-member)
- Branding priority (user vs org) via /api/users/me/branding
- Snapshot label via PUT /api/takeoffs/{plan_id}/history/{snap_id}/label
- Walls diff structure in POST /api/takeoffs/compare
- PDF Devis via GET /api/takeoffs/{plan_id}/quote-pdf
"""
import os
import time
import secrets
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
ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}


# ---------- Fixtures ----------

def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _register(email, name="Test User", password="TestPass2026!"):
    r = requests.post(
        f"{API}/auth/register",
        json={"email": email, "name": name, "password": password},
        timeout=30,
    )
    assert r.status_code == 200, f"register failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]["user_id"]


def _leave_if_in_org(auth):
    r = requests.get(f"{API}/organizations/me", headers=auth, timeout=15)
    if r.status_code == 200 and r.json().get("in_org"):
        # Owner? Remove all other members first
        me = r.json()
        if me.get("role") == "owner":
            for m in me.get("members", []):
                mid = m.get("user_id")
                if mid:
                    requests.delete(f"{API}/organizations/members/{mid}",
                                    headers=auth, timeout=15)
        requests.post(f"{API}/organizations/leave", headers=auth, timeout=15)


@pytest.fixture(scope="module")
def owner_auth():
    a = _login(DEMO)
    _leave_if_in_org(a)
    yield a
    _leave_if_in_org(a)


@pytest.fixture(scope="module")
def member_auth():
    # Fresh test user for join flow
    email = f"TEST_iter21_{secrets.token_hex(4)}@example.com"
    a, uid = _register(email)
    yield a
    _leave_if_in_org(a)


# ---------- 1) TEAM / ORGANIZATION SYSTEM ----------

class TestOrganizationSystem:

    def test_a_no_org(self, owner_auth):
        r = requests.get(f"{API}/organizations/me", headers=owner_auth, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json() == {"in_org": False}

    def test_b_create_org(self, owner_auth):
        r = requests.post(f"{API}/organizations",
                          json={"name": "BTP Test Iter21"},
                          headers=owner_auth, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["name"] == "BTP Test Iter21"
        assert data["owner_user_id"]
        code = data["org_code"]
        # Format LLLL-DDDD
        assert len(code) == 9 and code[4] == "-", f"bad code: {code}"
        assert code[:4].isalpha() and code[5:].isdigit()

    def test_c_get_me_owner(self, owner_auth):
        r = requests.get(f"{API}/organizations/me", headers=owner_auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["in_org"] is True
        assert d["role"] == "owner"
        assert d["member_count"] == 1
        assert isinstance(d["members"], list) and len(d["members"]) == 1
        assert d["org_code"] and "-" in d["org_code"]

    def test_d_invite_delivered(self, owner_auth):
        r = requests.post(f"{API}/organizations/invite",
                          json={"email": "delivered@resend.dev", "role": "member"},
                          headers=owner_auth, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert "email_status" in d
        assert d["email_status"] in ("sent", "failed", "skipped")
        assert d["org_code"]

    def test_e_member_join(self, owner_auth, member_auth):
        code = requests.get(f"{API}/organizations/me", headers=owner_auth,
                            timeout=15).json()["org_code"]
        r = requests.post(f"{API}/organizations/join",
                          json={"code": code}, headers=member_auth, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        # verify member sees in_org
        me = requests.get(f"{API}/organizations/me", headers=member_auth,
                          timeout=15).json()
        assert me["in_org"] is True
        assert me["role"] == "member"
        assert me["member_count"] == 2

    def test_f_branding_source_org(self, owner_auth, member_auth):
        # Owner: can_edit true
        r = requests.get(f"{API}/users/me/branding", headers=owner_auth, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "organization"
        assert d["can_edit"] is True
        assert d["org_role"] == "owner"

        # Member: can_edit false
        r = requests.get(f"{API}/users/me/branding", headers=member_auth, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "organization"
        assert d["can_edit"] is False
        assert d["org_role"] == "member"

    def test_g_member_cannot_put_branding(self, member_auth):
        r = requests.put(f"{API}/users/me/branding",
                         json={"company_name": "Hack Corp"},
                         headers=member_auth, timeout=15)
        assert r.status_code == 403, r.text

    def test_h_owner_can_put_and_shared(self, owner_auth, member_auth):
        r = requests.put(f"{API}/users/me/branding",
                         json={"company_name": "BTP Iter21 SARL",
                               "contact_line": "01 23 45 67 89"},
                         headers=owner_auth, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["company_name"] == "BTP Iter21 SARL"

        # member sees same branding
        m = requests.get(f"{API}/users/me/branding", headers=member_auth,
                         timeout=15).json()
        assert m["company_name"] == "BTP Iter21 SARL"
        assert m["contact_line"] == "01 23 45 67 89"

    def test_i_owner_removes_member(self, owner_auth, member_auth):
        me_owner = requests.get(f"{API}/organizations/me", headers=owner_auth,
                                timeout=15).json()
        owner_uid = me_owner["owner_user_id"]
        member = next(m for m in me_owner["members"]
                      if m["user_id"] != owner_uid)
        r = requests.delete(f"{API}/organizations/members/{member['user_id']}",
                            headers=owner_auth, timeout=15)
        assert r.status_code == 200, r.text

        # member should now be out
        m2 = requests.get(f"{API}/organizations/me", headers=member_auth,
                         timeout=15).json()
        assert m2 == {"in_org": False}

    def test_j_leave_owner_when_solo(self, owner_auth):
        r = requests.post(f"{API}/organizations/leave", headers=owner_auth, timeout=15)
        assert r.status_code == 200, r.text
        me = requests.get(f"{API}/organizations/me", headers=owner_auth,
                          timeout=15).json()
        assert me == {"in_org": False}

    def test_j2_leave_owner_blocked_when_has_members(self, owner_auth):
        """Verify 400 when owner tries to leave while members are still present."""
        # setup: create org, invite/join a second user
        requests.post(f"{API}/organizations", json={"name": "Solo Test"},
                      headers=owner_auth, timeout=15)
        code = requests.get(f"{API}/organizations/me", headers=owner_auth,
                            timeout=15).json()["org_code"]

        second_email = f"TEST_iter21_leave_{secrets.token_hex(4)}@example.com"
        second_auth, _ = _register(second_email)
        requests.post(f"{API}/organizations/join", json={"code": code},
                      headers=second_auth, timeout=15)

        r = requests.post(f"{API}/organizations/leave", headers=owner_auth, timeout=15)
        assert r.status_code == 400, r.text

        # cleanup
        requests.post(f"{API}/organizations/leave", headers=second_auth, timeout=15)
        _leave_if_in_org(owner_auth)


# ---------- Helpers for plan tests ----------

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


# ---------- 3) SNAPSHOT NAMING ----------

class TestSnapshotLabel:

    @pytest.fixture(scope="class")
    def plan_and_snap(self):
        auth = _login(DEMO)
        pid = _upload_plan(auth)
        _calibrate(pid, auth)
        _add_room(pid, auth, "Cuisine")
        hist = requests.get(f"{API}/takeoffs/{pid}/history",
                            headers=auth, timeout=15).json()
        assert len(hist.get("history", [])) >= 1
        snap_id = hist["history"][0]["snapshot_id"]
        return auth, pid, snap_id

    def test_label_snapshot(self, plan_and_snap):
        auth, pid, snap = plan_and_snap
        r = requests.put(f"{API}/takeoffs/{pid}/history/{snap}/label",
                         json={"label": "Version client"},
                         headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["label"] == "Version client"

    def test_history_returns_label(self, plan_and_snap):
        auth, pid, snap = plan_and_snap
        r = requests.get(f"{API}/takeoffs/{pid}/history",
                         headers=auth, timeout=15)
        assert r.status_code == 200
        items = r.json()["history"]
        target = next((i for i in items if i["snapshot_id"] == snap), None)
        assert target is not None
        assert target.get("label") == "Version client"

    def test_label_404_unknown(self, plan_and_snap):
        auth, pid, _ = plan_and_snap
        r = requests.put(f"{API}/takeoffs/{pid}/history/snap_bogus/label",
                         json={"label": "x"}, headers=auth, timeout=15)
        assert r.status_code == 404


# ---------- 4) COMPARE WALLS ----------

class TestCompareWalls:

    def test_walls_key_present_empty_ok(self):
        auth = _login(DEMO)
        p1 = _upload_plan(auth)
        _calibrate(p1, auth)
        _add_room(p1, auth, "Salon-A", 5, 4)
        p2 = _upload_plan(auth)
        _calibrate(p2, auth)
        _add_room(p2, auth, "Salon-B", 6, 4)

        r = requests.post(f"{API}/takeoffs/compare",
                         json={"before_plan_id": p1, "after_plan_id": p2},
                         headers=auth, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "walls" in d
        w = d["walls"]
        assert w["before_count"] == 0
        assert w["after_count"] == 0
        assert w["added"] == []
        assert w["removed"] == []
        assert w["unchanged"] == []


# ---------- 5) PDF DEVIS ----------

class TestQuotePDF:

    @pytest.fixture(scope="class")
    def plan_with_room(self):
        auth = _login(DEMO)
        pid = _upload_plan(auth)
        _calibrate(pid, auth)
        _add_room(pid, auth, "Chambre", 5, 4)
        return auth, pid

    def test_quote_pdf_std_carrelage(self, plan_with_room):
        auth, pid = plan_with_room
        r = requests.get(f"{API}/takeoffs/{pid}/quote-pdf",
                        params={"finish": "std", "floor_material": "carrelage"},
                        headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert len(r.content) > 2000
        assert r.content[:5] == b"%PDF-"

    def test_quote_pdf_eco(self, plan_with_room):
        auth, pid = plan_with_room
        r = requests.get(f"{API}/takeoffs/{pid}/quote-pdf",
                        params={"finish": "eco"}, headers=auth, timeout=60)
        assert r.status_code == 200
        assert len(r.content) > 2000

    def test_quote_pdf_premium(self, plan_with_room):
        auth, pid = plan_with_room
        r = requests.get(f"{API}/takeoffs/{pid}/quote-pdf",
                        params={"finish": "premium"}, headers=auth, timeout=60)
        assert r.status_code == 200
        assert len(r.content) > 2000

    def test_quote_pdf_no_rooms_400(self):
        auth = _login(DEMO)
        pid = _upload_plan(auth)  # no rooms added
        r = requests.get(f"{API}/takeoffs/{pid}/quote-pdf",
                        headers=auth, timeout=30)
        assert r.status_code == 400, r.text


# ---------- 6) BRANDING PRIORITY (no crash on empty personal) ----------

class TestBrandingPriority:

    def test_quote_pdf_ok_with_org_branding_only(self):
        """Owner in org with only org branding — /quote-pdf must not crash."""
        auth = _login(DEMO)
        _leave_if_in_org(auth)
        # Clear personal branding
        requests.put(f"{API}/users/me/branding",
                     json={"company_name": "", "contact_line": "", "logo_b64": ""},
                     headers=auth, timeout=15)
        # Create org and set org-level branding via owner PUT
        requests.post(f"{API}/organizations", json={"name": "Brand Prio"},
                      headers=auth, timeout=15)
        r = requests.put(f"{API}/users/me/branding",
                         json={"company_name": "Org Only SARL"},
                         headers=auth, timeout=15)
        assert r.status_code == 200

        pid = _upload_plan(auth)
        _calibrate(pid, auth)
        _add_room(pid, auth, "Salon", 4, 4)
        r = requests.get(f"{API}/takeoffs/{pid}/quote-pdf",
                        headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        assert len(r.content) > 2000

        # cleanup: leave (solo → deletes org)
        _leave_if_in_org(auth)
