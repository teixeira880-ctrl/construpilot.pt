"""Iter23 — Devis Récurrents (templates), Multi-Plan PDF, Email Tracking, Signature.

Covers:
- POST/GET/DELETE /api/quotes/templates + shared-org visibility + 403/404
- POST /api/quotes/multi-pdf (bundle PDF, 400/404 edge)
- GET /api/quotes/track/open/{log_id} (GIF pixel + notification)
- POST/GET /api/quotes/notifications
- Signature flow: signature-link + public GET/POST/PDF + already-signed 400
"""
import os
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

PRO = {"email": "pro@construpilot.fr", "password": "Pro2026!"}
COLLEGUE = {"email": "collegue@construpilot.fr", "password": "Collegue2026!"}
CLIENT = {"email": "client@construpilot.fr", "password": "Client2026!"}

PIXEL_B64 = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1"
             "HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII=")


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}, r.json()["user"]["user_id"]


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


def _plan_with_room(auth):
    pid = _upload_plan(auth)
    _calibrate(pid, auth)
    _add_room(pid, auth)
    return pid


# ============================================================
# 1) QUOTE TEMPLATES
# ============================================================
class TestQuoteTemplates:

    def test_create_and_list_own_template(self):
        auth, _ = _login(PRO)
        r = requests.post(f"{API}/quotes/templates",
                          json={"name": "TEST_tpl_private",
                                "finish": "premium",
                                "floor_material": "parquet",
                                "is_shared": False},
                          headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["template_id"].startswith("qtpl_")
        assert d["finish"] == "premium"
        assert d["floor_material"] == "parquet"
        tpl_id = d["template_id"]

        # GET list — should include it
        r = requests.get(f"{API}/quotes/templates", headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        ids = [t["template_id"] for t in r.json()["templates"]]
        assert tpl_id in ids

        # cleanup
        requests.delete(f"{API}/quotes/templates/{tpl_id}",
                        headers=auth, timeout=15)

    def test_shared_template_visible_to_org_member(self):
        pro_auth, _ = _login(PRO)
        col_auth, _ = _login(COLLEGUE)

        # Pro creates a shared template
        r = requests.post(f"{API}/quotes/templates",
                          json={"name": "TEST_tpl_shared",
                                "finish": "eco", "floor_material": "vinyle",
                                "is_shared": True},
                          headers=pro_auth, timeout=15)
        assert r.status_code == 200, r.text
        tpl_id = r.json()["template_id"]

        # Collegue should see it
        r = requests.get(f"{API}/quotes/templates",
                         headers=col_auth, timeout=15)
        assert r.status_code == 200
        ids = [t["template_id"] for t in r.json()["templates"]]
        assert tpl_id in ids, "Shared template not visible to org member"

        # Client (not in org) should NOT see it
        client_auth, _ = _login(CLIENT)
        r = requests.get(f"{API}/quotes/templates",
                         headers=client_auth, timeout=15)
        assert r.status_code == 200
        ids = [t["template_id"] for t in r.json()["templates"]]
        assert tpl_id not in ids

        # Collegue tries to DELETE — must be 403
        r = requests.delete(f"{API}/quotes/templates/{tpl_id}",
                            headers=col_auth, timeout=15)
        assert r.status_code == 403, r.text

        # Creator can delete
        r = requests.delete(f"{API}/quotes/templates/{tpl_id}",
                            headers=pro_auth, timeout=15)
        assert r.status_code == 200

    def test_delete_non_existing_template_404(self):
        auth, _ = _login(PRO)
        r = requests.delete(f"{API}/quotes/templates/qtpl_doesnotexist",
                            headers=auth, timeout=15)
        assert r.status_code == 404, r.text


# ============================================================
# 2) MULTI-PLAN PDF
# ============================================================
class TestMultiPlanPdf:

    def test_multi_pdf_success_with_two_plans(self):
        auth, _ = _login(PRO)
        p1 = _plan_with_room(auth)
        p2 = _plan_with_room(auth)
        r = requests.post(f"{API}/quotes/multi-pdf",
                          json={"plan_ids": [p1, p2],
                                "project_name": "TEST_ProjetMulti",
                                "finish": "std",
                                "floor_material": "carrelage"},
                          headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert len(r.content) > 2048
        assert r.content[:4] == b"%PDF"

    def test_multi_pdf_skip_plans_without_rooms(self):
        auth, _ = _login(PRO)
        p_good = _plan_with_room(auth)
        p_empty = _upload_plan(auth)  # no rooms
        r = requests.post(f"{API}/quotes/multi-pdf",
                          json={"plan_ids": [p_good, p_empty],
                                "project_name": "TEST_Skip"},
                          headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        assert len(r.content) > 2048

    def test_multi_pdf_all_empty_returns_400(self):
        auth, _ = _login(PRO)
        p = _upload_plan(auth)  # no rooms
        r = requests.post(f"{API}/quotes/multi-pdf",
                          json={"plan_ids": [p]},
                          headers=auth, timeout=30)
        assert r.status_code == 400, r.text

    def test_multi_pdf_non_existing_plan_returns_404(self):
        auth, _ = _login(PRO)
        p_good = _plan_with_room(auth)
        r = requests.post(f"{API}/quotes/multi-pdf",
                          json={"plan_ids": [p_good, "pl_doesnotexist"]},
                          headers=auth, timeout=30)
        assert r.status_code == 404, r.text


# ============================================================
# 3) EMAIL OPEN TRACKING + NOTIFICATIONS
# ============================================================
class TestEmailTracking:

    def _send_quote(self, auth, pid):
        r = requests.post(f"{API}/takeoffs/{pid}/send-quote",
                          json={"client_email": "trackee@example.com",
                                "client_name": "Trackee",
                                "finish": "std",
                                "floor_material": "carrelage",
                                "cc_self": False},
                          headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        log_id = r.json()["log_id"]
        assert log_id.startswith("qs_")
        return log_id

    def test_tracking_pixel_flow(self):
        auth, _ = _login(PRO)
        pid = _plan_with_room(auth)
        log_id = self._send_quote(auth, pid)

        # First open
        r = requests.get(f"{API}/quotes/track/open/{log_id}", timeout=15)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/gif"
        assert r.content[:6] == b"GIF89a"

        # Second open — should NOT create duplicate notification but increment counter
        r2 = requests.get(f"{API}/quotes/track/open/{log_id}", timeout=15)
        assert r2.status_code == 200
        assert r2.content[:6] == b"GIF89a"

        # Notification present
        r = requests.get(f"{API}/quotes/notifications/me",
                         headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        matching = [n for n in d["notifications"]
                    if n.get("type") == "quote_opened" and n.get("log_id") == log_id]
        assert len(matching) == 1, f"Expected exactly 1 quote_opened notif, got {len(matching)}"
        notif_id = matching[0]["notif_id"]
        assert matching[0]["read"] is False

        # Mark as read
        r = requests.post(f"{API}/quotes/notifications/{notif_id}/read",
                          headers=auth, timeout=15)
        assert r.status_code == 200
        # Verify
        r = requests.get(f"{API}/quotes/notifications/me",
                         headers=auth, timeout=15)
        matching = [n for n in r.json()["notifications"]
                    if n["notif_id"] == notif_id]
        assert matching and matching[0]["read"] is True

        # Verify open_count in quote_sends
        r = requests.get(f"{API}/takeoffs/{pid}/quote-sends",
                         headers=auth, timeout=15)
        sends = r.json()["sends"]
        entry = next(s for s in sends if s["log_id"] == log_id)
        assert entry["opened"] is True
        assert entry.get("open_count", 0) >= 2


# ============================================================
# 4) SIGNATURE FLOW
# ============================================================
class TestSignatureFlow:

    def _prepare_send(self, auth):
        pid = _plan_with_room(auth)
        r = requests.post(f"{API}/takeoffs/{pid}/send-quote",
                          json={"client_email": "signer@example.com",
                                "client_name": "Signataire",
                                "finish": "std",
                                "floor_material": "carrelage",
                                "cc_self": False},
                          headers=auth, timeout=60)
        assert r.status_code == 200, r.text
        return pid, r.json()["log_id"]

    def test_full_signature_flow(self):
        auth, _ = _login(PRO)
        pid, log_id = self._prepare_send(auth)

        # (a) Create signature link
        r = requests.post(
            f"{API}/takeoffs/{pid}/quote-sends/{log_id}/signature-link",
            headers=auth, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["token"].startswith("sig_")
        assert d["url"].endswith(f"/sign/{d['token']}")
        token = d["token"]

        # (b) Public GET (no auth)
        r = requests.get(f"{API}/quotes/public/sign/{token}", timeout=15)
        assert r.status_code == 200, r.text
        s = r.json()
        assert s["log_id"] == log_id
        assert s["plan_id"] == pid
        assert s["client_email"] == "signer@example.com"
        assert s["signed"] is False
        assert "total_ttc" in s
        assert "company_name" in s
        assert "contact_line" in s

        # (c) POST signature (no auth)
        payload = {"signature_b64": PIXEL_B64, "signer_name": "Jean Testeur"}
        r = requests.post(f"{API}/quotes/public/sign/{token}",
                          json=payload, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        # (c-bis) Notification "quote_signed" for sender
        r = requests.get(f"{API}/quotes/notifications/me",
                         headers=auth, timeout=15)
        assert r.status_code == 200
        signed_notifs = [n for n in r.json()["notifications"]
                         if n["type"] == "quote_signed"
                         and n["log_id"] == log_id]
        assert len(signed_notifs) == 1

        # Public GET now says signed=true
        r = requests.get(f"{API}/quotes/public/sign/{token}", timeout=15)
        assert r.json()["signed"] is True

        # (d) Signing again → 400
        r = requests.post(f"{API}/quotes/public/sign/{token}",
                          json=payload, timeout=15)
        assert r.status_code == 400, r.text
        assert "déjà" in r.text or "signé" in r.text

        # (e) Signed PDF download (no auth)
        r = requests.get(f"{API}/quotes/public/sign/{token}/pdf", timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert len(r.content) > 2048
        assert r.content[:4] == b"%PDF"

    def test_public_sign_invalid_token_404(self):
        r = requests.get(f"{API}/quotes/public/sign/sig_invalidtoken", timeout=15)
        assert r.status_code == 404

    def test_signature_link_wrong_plan_404(self):
        auth, _ = _login(PRO)
        pid, log_id = self._prepare_send(auth)
        # Wrong plan_id
        r = requests.post(
            f"{API}/takeoffs/pl_wrong/quote-sends/{log_id}/signature-link",
            headers=auth, timeout=15)
        assert r.status_code == 404
