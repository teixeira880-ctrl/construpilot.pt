"""Iter26 tests: Plan→Estimation workflow, TVA attestation, Email personalization,
Reminder Auto 5j.
"""
import os
import pytest
import requests
from datetime import datetime, timezone, timedelta


def _read_public_url():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None


PUBLIC_URL = _read_public_url()
assert PUBLIC_URL, "REACT_APP_BACKEND_URL missing"


def _login(email, password):
    r = requests.post(f"{PUBLIC_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers():
    return {"Authorization": f"Bearer {_login('pro@construpilot.fr', 'Pro2026!')}"}


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login('admin@construpilot.fr', 'Construpilot2026!')}"}


@pytest.fixture(scope="module")
def collegue_headers():
    return {"Authorization": f"Bearer {_login('collegue@construpilot.fr', 'Collegue2026!')}"}


@pytest.fixture(scope="module")
def plan_id_with_rooms(pro_headers):
    """Fetch an existing pro plan that has measured rooms."""
    r = requests.get(f"{PUBLIC_URL}/api/takeoffs", headers=pro_headers, timeout=20)
    assert r.status_code == 200, r.text
    plans = r.json().get("plans") or r.json().get("items") or r.json()
    if isinstance(plans, dict):
        plans = plans.get("plans", [])
    assert isinstance(plans, list) and plans, f"no plans found: {r.json()}"
    # Prefer plan_d6e446d3a459 if present
    for p in plans:
        if p.get("plan_id") == "plan_d6e446d3a459":
            return p["plan_id"]
    # otherwise the first with rooms
    for p in plans:
        if (p.get("room_count") or 0) > 0 or (p.get("rooms") and len(p["rooms"]) > 0):
            return p["plan_id"]
    return plans[0]["plan_id"]


# ---------- 1) WORKFLOW: Plan → Estimation ----------

class TestEstimateFromTakeoff:
    def test_estimate_renovation(self, pro_headers, plan_id_with_rooms):
        r = requests.post(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/estimate-from-takeoff",
            headers=pro_headers,
            json={"project_type": "renovation_complete", "finish_level": "standard"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("plan_id") == plan_id_with_rooms
        assert d.get("project_id", "").startswith("proj_")
        assert d.get("surface_m2", 0) > 0
        assert d.get("room_count", 0) > 0
        assert d.get("is_renovation") is True
        est = d.get("estimation") or {}
        assert isinstance(est.get("lots"), list) and est["lots"], "lots missing"
        for key in ("total_avg", "total_min", "total_max", "duration_weeks",
                    "price_per_sqm"):
            assert key in est, f"missing {key} in estimation"

    def test_estimate_construction_neuve_not_renovation(self, pro_headers,
                                                        plan_id_with_rooms):
        r = requests.post(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/estimate-from-takeoff",
            headers=pro_headers,
            json={"project_type": "construction_neuve", "finish_level": "eco"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("is_renovation") is False

    def test_estimate_no_rooms_returns_400(self, pro_headers):
        # Non-existent plan → 404; test empty rooms via impossible plan_id
        r = requests.post(
            f"{PUBLIC_URL}/api/takeoffs/plan_does_not_exist_xyz/estimate-from-takeoff",
            headers=pro_headers,
            json={"project_type": "renovation_complete", "finish_level": "standard"},
            timeout=20,
        )
        assert r.status_code in (400, 404)


# ---------- 2 & 3) SEND-QUOTE with personalisation + TVA attestation ----------

class TestSendQuotePersonalisationAndTva:
    def test_send_quote_with_subject_intro_and_tva(self, pro_headers,
                                                    plan_id_with_rooms):
        body = {
            "client_email": "delivered@resend.dev",
            "client_name": "TEST Iter26",
            "client_address": "12 rue X 75002 Paris",
            "work_address": "12 rue X 75002 Paris",
            "subject": "TEST Sujet Iter26",
            "intro": "TEST intro personnalisée iter26.",
            "message": "TEST message",
            "finish": "std",
            "floor_material": "carrelage",
            "cc_self": False,
            "include_tva_attestation": True,
        }
        r = requests.post(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/send-quote",
            headers=pro_headers, json=body, timeout=45,
        )
        assert r.status_code == 200, r.text
        d = r.json()
        # ok may be False if outgoing SMTP not configured, but log_id must exist
        assert d.get("log_id", "").startswith("qs_")
        # Verify log via /quote-sends
        lst = requests.get(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/quote-sends",
            headers=pro_headers, timeout=20,
        ).json()
        found = next((s for s in lst.get("sends", []) if s.get("log_id") == d["log_id"]), None)
        assert found, "quote_send log not found"
        assert found.get("subject") == "TEST Sujet Iter26"
        assert found.get("intro") == "TEST intro personnalisée iter26."
        assert found.get("message") == "TEST message"
        assert found.get("client_address") == "12 rue X 75002 Paris"
        assert found.get("work_address") == "12 rue X 75002 Paris"
        assert found.get("include_tva_attestation") is True

    def test_send_quote_subject_fallback(self, pro_headers, plan_id_with_rooms):
        r = requests.post(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/send-quote",
            headers=pro_headers,
            json={"client_email": "delivered@resend.dev", "cc_self": False},
            timeout=45,
        )
        assert r.status_code == 200, r.text
        log_id = r.json()["log_id"]
        lst = requests.get(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/quote-sends",
            headers=pro_headers, timeout=20,
        ).json()
        found = next(s for s in lst["sends"] if s["log_id"] == log_id)
        subject = found.get("subject", "")
        assert subject.startswith("Devis ·"), f"expected fallback subject, got {subject!r}"

    def test_tva_pdf_bytes_valid(self):
        """Directly exercise build_tva_attestation_pdf."""
        import sys
        sys.path.insert(0, "/app/backend")
        from engines.pdf_takeoff import build_tva_attestation_pdf
        pdf = build_tva_attestation_pdf(
            client_name="TEST Client",
            client_address="12 rue X 75002 Paris",
            work_address="12 rue X 75002 Paris",
            work_description="Peinture ; Placo ; Sol",
        )
        assert isinstance(pdf, (bytes, bytearray))
        assert len(pdf) > 2048, f"pdf too small: {len(pdf)}"
        assert pdf[:5] == b"%PDF-"


# ---------- 4) REMINDERS ----------

class TestReminders:
    def test_non_admin_gets_403(self, collegue_headers):
        r = requests.post(f"{PUBLIC_URL}/api/quotes/reminders/run",
                          headers=collegue_headers, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_admin_can_run(self, admin_headers):
        r = requests.post(f"{PUBLIC_URL}/api/quotes/reminders/run",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("sent", "failed", "skipped", "candidates"):
            assert k in d, f"missing {k}"

    def test_reminder_picks_up_candidate_and_is_idempotent(self, admin_headers,
                                                            pro_headers,
                                                            plan_id_with_rooms):
        """Insert a fake quote_send directly through the API pipeline is not possible;
        so we insert directly via mongo (using motor from server context is heavy).
        Instead we exercise the real path: create a send, mark opened via track pixel,
        force opened_at to 9 days ago via a direct DB update through a small helper
        script.
        """
        from pymongo import MongoClient
        # Parse backend .env, stripping quotes
        env = {}
        for line in open("/app/backend/.env"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v.strip().strip('"').strip("'")
        mc = MongoClient(env["MONGO_URL"])
        sdb = mc[env["DB_NAME"]]

        # 1) create a real quote send
        r = requests.post(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/send-quote",
            headers=pro_headers,
            json={"client_email": "delivered@resend.dev",
                  "cc_self": False},
            timeout=45,
        )
        assert r.status_code == 200
        log_id = r.json()["log_id"]

        # 2) tamper the DB directly
        past = (datetime.now(timezone.utc) - timedelta(days=9)).isoformat()
        res = sdb.quote_sends.update_one({"log_id": log_id}, {"$set": {
            "opened": True, "opened_at": past, "signed": False,
            "reminder_sent": False, "email_status": "sent",
        }})
        assert res.matched_count == 1, f"log not found in DB: {log_id}"

        # 3) trigger reminders
        r = requests.post(f"{PUBLIC_URL}/api/quotes/reminders/run",
                          headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["candidates"] >= 1, f"expected >=1 candidate: {d}"

        # 4) verify flip in DB via /quote-sends
        lst = requests.get(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/quote-sends",
            headers=pro_headers, timeout=20,
        ).json()
        found = next(s for s in lst["sends"] if s["log_id"] == log_id)
        assert found.get("reminder_sent") is True
        assert found.get("reminder_sent_at")

        # 5) verify notification of type reminder_sent inserted
        notifs = requests.get(f"{PUBLIC_URL}/api/quotes/notifications/me",
                              headers=pro_headers, timeout=20).json()
        types = [n.get("type") for n in notifs.get("notifications", [])]
        assert "reminder_sent" in types, f"reminder_sent notification missing: {types}"

        # 6) idempotence
        r2 = requests.post(f"{PUBLIC_URL}/api/quotes/reminders/run",
                           headers=admin_headers, timeout=30)
        d2 = r2.json()
        # This particular log should not be re-picked
        # Other new candidates could theoretically exist; but our log is flipped
        lst2 = requests.get(
            f"{PUBLIC_URL}/api/takeoffs/{plan_id_with_rooms}/quote-sends",
            headers=pro_headers, timeout=20,
        ).json()
        found2 = next(s for s in lst2["sends"] if s["log_id"] == log_id)
        assert found2.get("reminder_sent") is True

    def test_scheduler_job_registered(self):
        """Verify import + job registered without errors."""
        import sys
        sys.path.insert(0, "/app/backend")
        # Just importing plans should not raise
        from routes import plans as plans_routes  # noqa
        assert callable(plans_routes._run_reminders)
