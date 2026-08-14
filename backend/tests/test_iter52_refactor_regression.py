"""Iter52 — Refactor regression tests.

Verifies that refactoring in engines/plan_ai.py, engines/plan_cv.py,
engines/alerting.py, routes/plans.py, routes/errors.py, routes/emails.py,
routes/admin.py did not break any behaviour.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PRO_EMAIL = "pro@construpilot.fr"
PRO_PWD = "Pro2026!"
ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PWD = "Construpilot2026!"
CLIENT_EMAIL = "client@construpilot.fr"
CLIENT_PWD = "Client2026!"

PDF_PATH = "/app/test_metre.pdf"


# -------- Fixtures --------

@pytest.fixture(scope="module")
def pro_token():
    r = requests.post(f"{API}/auth/login", json={"email": PRO_EMAIL, "password": PRO_PWD}, timeout=20)
    assert r.status_code == 200, f"pro login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def free_token():
    r = requests.post(f"{API}/auth/login", json={"email": CLIENT_EMAIL, "password": CLIENT_PWD}, timeout=20)
    if r.status_code != 200:
        pytest.skip(f"free/client login unavailable: {r.status_code}")
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


# -------- Auth --------

class TestAuth:
    def test_pro_login(self, pro_token):
        assert isinstance(pro_token, str) and len(pro_token) > 20

    def test_admin_login(self, admin_token):
        assert isinstance(admin_token, str) and len(admin_token) > 20

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": PRO_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401


# -------- Plan Upload + Analyze + detect-all-rooms (Pro Business gate) --------

@pytest.fixture(scope="module")
def uploaded_plan_id(admin_token):
    with open(PDF_PATH, "rb") as f:
        r = requests.post(f"{API}/takeoffs/upload",
                          headers=_h(admin_token),
                          files={"file": ("test.pdf", f, "application/pdf")},
                          timeout=60)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text[:400]}"
    data = r.json()
    assert "plan_id" in data
    assert "calibrations" in data
    return data["plan_id"]


class TestPlanUpload:
    def test_upload_returns_plan_id_and_calibrations(self, uploaded_plan_id):
        assert uploaded_plan_id.startswith("plan_")

    def test_analyze_ai_structure(self, admin_token, uploaded_plan_id):
        # AI call — allow generous timeout
        r = requests.post(f"{API}/takeoffs/{uploaded_plan_id}/analyze?page_index=0",
                          headers=_h(admin_token), timeout=180)
        assert r.status_code == 200, f"analyze failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        # Verify refactored structure preserved
        expected_keys = {"rooms", "facade_walls", "stairwells", "totals_gros_oeuvre", "floors", "interior_walls"}
        missing = expected_keys - set(data.keys())
        assert not missing, f"missing keys in analyze response: {missing} | got: {list(data.keys())}"

    def test_detect_all_rooms_structure(self, admin_token, uploaded_plan_id):
        r = requests.post(f"{API}/takeoffs/{uploaded_plan_id}/detect-all-rooms?page_index=0",
                          headers=_h(admin_token), timeout=60)
        assert r.status_code == 200, f"detect failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert "image_width" in data
        assert "image_height" in data
        assert "rooms" in data
        assert isinstance(data["rooms"], list)


# -------- Pro Business gate --------

class TestProBusinessGate:
    def test_free_user_upload_402(self, free_token):
        if not free_token:
            pytest.skip("no free user")
        with open(PDF_PATH, "rb") as f:
            r = requests.post(f"{API}/takeoffs/upload",
                              headers=_h(free_token),
                              files={"file": ("test.pdf", f, "application/pdf")},
                              timeout=30)
        # Expected: 402 Payment Required for non pro_business
        assert r.status_code == 402, f"expected 402 for free user, got {r.status_code} {r.text[:200]}"

    def test_admin_upload_200(self, uploaded_plan_id):
        # If uploaded_plan_id fixture succeeded, admin can upload → gate bypass OK
        assert uploaded_plan_id.startswith("plan_")

    def test_free_render3d_402(self, free_token):
        if not free_token:
            pytest.skip("no free user")
        r = requests.post(f"{API}/takeoffs/plan_fake123/render-3d",
                          headers=_h(free_token), json={"page_index": 0, "style": "photoreal"},
                          timeout=15)
        assert r.status_code == 402, f"expected 402 for free render-3d, got {r.status_code}"

    def test_free_render_video_402(self, free_token):
        if not free_token:
            pytest.skip("no free user")
        r = requests.post(f"{API}/takeoffs/plan_fake123/render-video",
                          headers=_h(free_token),
                          json={"page_index": 0, "styles": ["photoreal", "isometric"]},
                          timeout=15)
        assert r.status_code == 402


# -------- Price alerts (alerting.py refactor) --------

class TestPriceAlerts:
    def test_create_and_list_alert(self, pro_token):
        payload = {"query": "TEST_placo BA13", "target_price": 5.0, "product": "TEST_placo"}
        r = requests.post(f"{API}/prices/alerts", headers=_h(pro_token), json=payload, timeout=15)
        assert r.status_code == 200, f"create alert failed: {r.status_code} {r.text[:200]}"
        created = r.json()
        assert created["query"] == payload["query"]
        assert created["target_price"] == 5.0
        alert_id = created["alert_id"]

        r = requests.get(f"{API}/prices/alerts", headers=_h(pro_token), timeout=15)
        assert r.status_code == 200
        alerts = r.json()
        assert any(a["alert_id"] == alert_id for a in alerts)
        found = next(a for a in alerts if a["alert_id"] == alert_id)
        # Fields enriched in list route
        assert "best_price" in found
        assert "triggered" in found

        # cleanup
        requests.delete(f"{API}/prices/alerts/{alert_id}", headers=_h(pro_token), timeout=10)

    def test_check_now_uses_refactored_helpers(self, pro_token):
        # This exercises _best_offer, _should_notify, _push_alert
        r = requests.post(f"{API}/prices/alerts/check-now", headers=_h(pro_token), timeout=30)
        assert r.status_code == 200
        assert "notified" in r.json()


# -------- Admin Inbox + Leads --------

class TestAdminEndpoints:
    def test_admin_inbox(self, admin_token):
        r = requests.get(f"{API}/admin/inbox?hours=168", headers=_h(admin_token), timeout=20)
        assert r.status_code == 200, f"admin inbox failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        for k in ("counts", "leads", "new_users", "recent_sends", "recent_errors"):
            assert k in data, f"missing key {k} in inbox response"

    def test_admin_update_lead(self, admin_token):
        # Seed a lead directly via API if possible; else skip
        # Create via public leads endpoint if exists
        seed = requests.post(f"{API}/leads",
                             json={"name": "TEST_lead", "email": "test_lead@example.com",
                                   "phone": "0600000000", "project_type": "renovation",
                                   "surface": 50, "message": "test"},
                             timeout=15)
        if seed.status_code not in (200, 201):
            pytest.skip(f"cannot seed lead: {seed.status_code}")
        lead = seed.json()
        lead_id = lead.get("lead_id")
        if not lead_id:
            pytest.skip("no lead_id returned")
        r = requests.put(f"{API}/admin/leads/{lead_id}",
                         headers=_h(admin_token), json={"status": "handled"}, timeout=15)
        assert r.status_code == 200
        updated = r.json()
        assert updated.get("status") == "handled"


# -------- Client Portal --------

class TestClientPortal:
    def test_invalid_token(self):
        r = requests.get(f"{API}/quotes/client-portal/badtoken", timeout=15)
        assert r.status_code == 400

    def test_valid_token_no_quotes(self):
        # Generate via importing the helper — but we're an external client so we
        # test by hitting the server: use an email that surely has no quotes
        # We need a token; compute it exactly like build_client_portal_token
        import base64, hmac, hashlib
        secret = (os.environ.get("JWT_SECRET") or os.environ.get("SECRET_KEY") or "dev").encode()
        email = "test_noquotes@example.com"
        sig = hmac.new(secret, email.lower().encode(), hashlib.sha256).hexdigest()[:24]
        email_b64 = base64.urlsafe_b64encode(email.lower().encode()).decode()
        token = f"{email_b64}.{sig}"
        r = requests.get(f"{API}/quotes/client-portal/{token}", timeout=15)
        # If JWT_SECRET differs between test env and server, this may 400 — accept and log
        if r.status_code == 400:
            pytest.skip("JWT_SECRET mismatch between test env & backend; token verification skipped")
        assert r.status_code == 200, f"portal failed: {r.status_code} {r.text[:300]}"
        data = r.json()
        assert data["email"] == email
        assert "count" in data
        assert "quotes" in data


# -------- Errors client-log + emails unsubscribe --------

class TestErrorsAndEmails:
    def test_client_log_persists(self, admin_token):
        # Send with a unique message to avoid dedup
        unique_msg = f"TEST_iter52_{int(time.time())}"
        r = requests.post(f"{API}/errors/client-log",
                          json={"message": unique_msg, "url": "https://x", "user_agent": "pytest"},
                          timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") == True
        # Verify visible in admin list
        r2 = requests.get(f"{API}/errors/admin/list?hours=1&limit=200", headers=_h(admin_token), timeout=15)
        assert r2.status_code == 200
        items = r2.json().get("items", [])
        assert any(unique_msg in (i.get("message") or "") for i in items), \
            "logged client error not visible in admin list"

    def test_unsubscribe_bad_token(self):
        r = requests.get(f"{API}/emails/unsubscribe/badtoken", timeout=15, allow_redirects=False)
        assert r.status_code == 400
        assert "text/html" in r.headers.get("content-type", "").lower()
        assert "ConstruPilot" in r.text


# -------- Landing page --------

class TestLanding:
    def test_landing_200(self):
        r = requests.get(f"{BASE_URL}/", timeout=15)
        assert r.status_code == 200
        assert "<div" in r.text or "<html" in r.text.lower()
