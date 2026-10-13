"""Iter-85 HR module backend tests: workers CRUD, clock-in/out, timesheets, dashboard, notes, selfie ACL."""
import base64
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PASSWORD = "Construpilot2026!"
WORKER_DEMO_EMAIL = "ouvrier@construpilot.fr"
WORKER_DEMO_PASSWORD = "Ouvrier2026!"
CLIENT_EMAIL = "client@construpilot.fr"
CLIENT_PASSWORD = "Client2026!"

# 1x1 PNG transparent
PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)
SELFIE_DATAURL = f"data:image/png;base64,{PNG_1X1}"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def client_token():
    return _login(CLIENT_EMAIL, CLIENT_PASSWORD)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def client_headers(client_token):
    return {"Authorization": f"Bearer {client_token}"}


@pytest.fixture(scope="module")
def created_worker(admin_headers):
    """Create a fresh test worker (unique email)."""
    email = f"test_worker_{uuid.uuid4().hex[:8]}@construpilot.fr"
    pwd = "TestWorker2026!"
    r = requests.post(f"{BASE_URL}/api/hr/workers", headers=admin_headers, json={
        "name": "TEST Worker Iter85", "email": email, "password": pwd,
        "poste": "Maçon", "hourly_rate": 22.5,
    }, timeout=30)
    assert r.status_code == 200, f"create worker: {r.status_code} {r.text}"
    data = r.json()
    assert data["email"] == email
    assert data["poste"] == "Maçon"
    return {"worker_id": data["worker_id"], "email": email, "password": pwd, "name": data["name"]}


@pytest.fixture(scope="module")
def worker_token(created_worker):
    return _login(created_worker["email"], created_worker["password"])


@pytest.fixture(scope="module")
def worker_headers(worker_token):
    return {"Authorization": f"Bearer {worker_token}"}


# ---------- Paywall / role gating ----------

class TestPaywall:
    def test_client_cannot_list_workers(self, client_headers):
        r = requests.get(f"{BASE_URL}/api/hr/workers", headers=client_headers, timeout=30)
        assert r.status_code in (402, 403)

    def test_client_cannot_hit_dashboard(self, client_headers):
        r = requests.get(f"{BASE_URL}/api/hr/dashboard", headers=client_headers, timeout=30)
        assert r.status_code in (402, 403)

    def test_admin_can_list_workers(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/hr/workers", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)


# ---------- Worker CRUD ----------

class TestWorkerCRUD:
    def test_worker_appears_in_list(self, admin_headers, created_worker):
        r = requests.get(f"{BASE_URL}/api/hr/workers", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        ids = [w["worker_id"] for w in r.json()]
        assert created_worker["worker_id"] in ids

    def test_duplicate_email_rejected(self, admin_headers, created_worker):
        r = requests.post(f"{BASE_URL}/api/hr/workers", headers=admin_headers, json={
            "name": "Dup", "email": created_worker["email"], "password": "AnyPwd12!",
        }, timeout=30)
        assert r.status_code == 409

    def test_reset_password(self, admin_headers, created_worker):
        r = requests.post(
            f"{BASE_URL}/api/hr/workers/{created_worker['worker_id']}/reset-password",
            headers=admin_headers, json={"password": created_worker["password"]}, timeout=30,
        )
        assert r.status_code == 200 and r.json().get("ok") is True


# ---------- Worker projects/status ----------

class TestWorkerContext:
    def test_worker_projects_returns_list(self, worker_headers):
        r = requests.get(f"{BASE_URL}/api/hr/me/projects", headers=worker_headers, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_worker_status_initially_open_null(self, worker_headers):
        r = requests.get(f"{BASE_URL}/api/hr/me/status", headers=worker_headers, timeout=30)
        assert r.status_code == 200
        # may be null or an existing open ts (there was prior smoke test); accept both shapes
        assert "open" in r.json()

    def test_admin_cannot_call_worker_endpoints(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/hr/me/projects", headers=admin_headers, timeout=30)
        assert r.status_code == 403


# ---------- Clock-in / clock-out flow ----------

@pytest.fixture(scope="module")
def admin_project_id(admin_headers, worker_headers):
    # Use worker's employer projects list (the admin employer). Create one if empty.
    r = requests.get(f"{BASE_URL}/api/hr/me/projects", headers=worker_headers, timeout=30)
    assert r.status_code == 200
    rows = r.json()
    if rows:
        return rows[0]["project_id"]
    # create a project as admin
    r2 = requests.post(f"{BASE_URL}/api/projects", headers=admin_headers, json={
        "name": "TEST Chantier Iter85", "address": "1 rue de Test"
    }, timeout=30)
    assert r2.status_code in (200, 201), r2.text
    return r2.json()["project_id"]


@pytest.fixture(scope="module")
def clean_open_ts(worker_headers):
    """Close any pre-existing open timesheet so tests start fresh."""
    r = requests.get(f"{BASE_URL}/api/hr/me/status", headers=worker_headers, timeout=30)
    if r.status_code == 200 and r.json().get("open"):
        requests.post(f"{BASE_URL}/api/hr/clock-out", headers=worker_headers,
                      json={"selfie": SELFIE_DATAURL}, timeout=30)


class TestClockFlow:
    def test_clock_in_requires_selfie(self, worker_headers, admin_project_id, clean_open_ts):
        r = requests.post(f"{BASE_URL}/api/hr/clock-in", headers=worker_headers, json={
            "project_id": admin_project_id, "selfie": ""
        }, timeout=30)
        assert r.status_code == 400

    def test_clock_in_bad_project(self, worker_headers):
        r = requests.post(f"{BASE_URL}/api/hr/clock-in", headers=worker_headers, json={
            "project_id": "does_not_exist", "selfie": SELFIE_DATAURL
        }, timeout=30)
        assert r.status_code == 404

    def test_full_clock_in_out_and_hours(self, worker_headers, admin_project_id):
        # clock-in
        r = requests.post(f"{BASE_URL}/api/hr/clock-in", headers=worker_headers, json={
            "project_id": admin_project_id, "selfie": SELFIE_DATAURL,
            "lat": 48.8566, "lng": 2.3522, "accuracy": 12.0,
        }, timeout=30)
        assert r.status_code == 200, r.text
        entry = r.json()
        assert entry["status"] == "open" and entry["selfie_in"]
        entry_id = entry["entry_id"]

        # duplicate clock-in blocked
        r2 = requests.post(f"{BASE_URL}/api/hr/clock-in", headers=worker_headers, json={
            "project_id": admin_project_id, "selfie": SELFIE_DATAURL
        }, timeout=30)
        assert r2.status_code == 409

        # clock-out
        r3 = requests.post(f"{BASE_URL}/api/hr/clock-out", headers=worker_headers, json={
            "selfie": SELFIE_DATAURL
        }, timeout=30)
        assert r3.status_code == 200, r3.text
        out = r3.json()
        assert out["entry_id"] == entry_id
        assert out["status"] == "pending"
        assert out["hours"] is not None and out["hours"] >= 0

        # appears in /me/timesheets
        r4 = requests.get(f"{BASE_URL}/api/hr/me/timesheets", headers=worker_headers, timeout=30)
        assert r4.status_code == 200
        assert any(t["entry_id"] == entry_id for t in r4.json())

        # store for validation test
        pytest.hr_last_entry_id = entry_id
        pytest.hr_last_selfie_path = out["selfie_in"]

    def test_clock_out_without_open_fails(self, worker_headers):
        r = requests.post(f"{BASE_URL}/api/hr/clock-out", headers=worker_headers,
                          json={"selfie": SELFIE_DATAURL}, timeout=30)
        assert r.status_code == 404


# ---------- Selfie ACL ----------

class TestSelfieACL:
    def test_employer_can_fetch(self, admin_headers):
        path = getattr(pytest, "hr_last_selfie_path", None)
        if not path:
            pytest.skip("no selfie path")
        r = requests.get(f"{BASE_URL}/api/hr/selfie", headers=admin_headers,
                         params={"path": path}, timeout=30)
        assert r.status_code == 200
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_worker_owner_can_fetch(self, worker_headers):
        path = getattr(pytest, "hr_last_selfie_path", None)
        if not path:
            pytest.skip("no selfie path")
        r = requests.get(f"{BASE_URL}/api/hr/selfie", headers=worker_headers,
                         params={"path": path}, timeout=30)
        assert r.status_code == 200

    def test_other_user_forbidden(self, client_headers):
        path = getattr(pytest, "hr_last_selfie_path", None)
        if not path:
            pytest.skip("no selfie path")
        r = requests.get(f"{BASE_URL}/api/hr/selfie", headers=client_headers,
                         params={"path": path}, timeout=30)
        assert r.status_code == 403


# ---------- Employer timesheets + validation ----------

class TestValidation:
    def test_list_and_validate(self, admin_headers):
        entry_id = getattr(pytest, "hr_last_entry_id", None)
        assert entry_id
        r = requests.get(f"{BASE_URL}/api/hr/timesheets", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        assert any(t["entry_id"] == entry_id for t in r.json())

        r2 = requests.post(f"{BASE_URL}/api/hr/timesheets/{entry_id}/validate",
                           headers=admin_headers, json={"status": "validated"}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["status"] == "validated"

    def test_invalid_status(self, admin_headers):
        entry_id = getattr(pytest, "hr_last_entry_id", None)
        r = requests.post(f"{BASE_URL}/api/hr/timesheets/{entry_id}/validate",
                          headers=admin_headers, json={"status": "wtf"}, timeout=30)
        assert r.status_code == 400


# ---------- Dashboard ----------

class TestDashboard:
    def test_dashboard_shape(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/hr/dashboard", headers=admin_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_hours", "entries", "pending", "by_worker", "by_project"):
            assert k in d
        assert isinstance(d["by_worker"], list) and isinstance(d["by_project"], list)


# ---------- Site notes ----------

class TestSiteNotes:
    def test_worker_create_and_employer_reply(self, worker_headers, admin_headers):
        msg = f"TEST doute {uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/api/hr/site-notes", headers=worker_headers, json={
            "type": "question", "message": msg
        }, timeout=30)
        assert r.status_code == 200
        note_id = r.json()["note_id"]

        # employer lists
        r2 = requests.get(f"{BASE_URL}/api/hr/site-notes", headers=admin_headers, timeout=30)
        assert r2.status_code == 200
        assert any(n["note_id"] == note_id for n in r2.json())

        # reply
        r3 = requests.post(f"{BASE_URL}/api/hr/site-notes/{note_id}/reply",
                           headers=admin_headers, json={"reply": "Reçu, ok."}, timeout=30)
        assert r3.status_code == 200
        assert r3.json()["status"] == "answered"
        assert r3.json()["reply"] == "Reçu, ok."

        # worker sees the reply
        r4 = requests.get(f"{BASE_URL}/api/hr/me/site-notes", headers=worker_headers, timeout=30)
        assert r4.status_code == 200
        note = next((n for n in r4.json() if n["note_id"] == note_id), None)
        assert note and note["reply"] == "Reçu, ok."

    def test_empty_message_rejected(self, worker_headers):
        r = requests.post(f"{BASE_URL}/api/hr/site-notes", headers=worker_headers, json={
            "type": "comment", "message": "   "
        }, timeout=30)
        assert r.status_code == 400


# ---------- Cleanup ----------

def test_zz_deactivate_worker(admin_headers, created_worker):
    r = requests.delete(f"{BASE_URL}/api/hr/workers/{created_worker['worker_id']}",
                        headers=admin_headers, timeout=30)
    assert r.status_code == 200
    r2 = requests.get(f"{BASE_URL}/api/hr/workers", headers=admin_headers, timeout=30)
    w = next((x for x in r2.json() if x["worker_id"] == created_worker["worker_id"]), None)
    assert w and w["active"] is False
