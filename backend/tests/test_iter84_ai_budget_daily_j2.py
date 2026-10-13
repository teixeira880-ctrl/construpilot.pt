"""Tests for iter 84: AI daily bucket + AI budget alert + J+2 prospect reminders + admin multilingual.

Covers:
- GET /api/admin/ai-usage-daily?days=N (shape, gap-filled, clamped 1..90)
- GET/PUT /api/admin/ai-budget (persistence, alert lock reset)
- Real AI call increments today's daily bucket
- engines.ai.check_ai_budget runs without exception when threshold exceeded
- routes.leads.run_prospect_reminders sets j2_reminded=true on aged landing lead
"""
import os
import asyncio
import uuid
import pytest
import requests
from datetime import datetime, timezone, timedelta

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        for line in open("/app/frontend/.env"):
            if line.startswith("REACT_APP_BACKEND_URL"):
                v = line.split("=", 1)[1].strip()
                break
    return v.rstrip("/")

BASE_URL = _load_backend_url()

def _load_env_val(key):
    for line in open("/app/backend/.env"):
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None
ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PASS = "Construpilot2026!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ---- AI daily usage endpoint ----
class TestAiUsageDaily:
    def test_default_shape(self, h):
        r = requests.get(f"{BASE_URL}/api/admin/ai-usage-daily", headers=h, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j.keys()) >= {"days", "series", "total"}
        assert j["days"] == 30
        assert len(j["series"]) == 30
        assert all(set(p.keys()) == {"date", "calls"} for p in j["series"])
        assert all(isinstance(p["calls"], int) for p in j["series"])
        # dates sorted asc, last == today
        today = datetime.now(timezone.utc).date().isoformat()
        assert j["series"][-1]["date"] == today
        assert j["total"] == sum(p["calls"] for p in j["series"])

    def test_days_param(self, h):
        r = requests.get(f"{BASE_URL}/api/admin/ai-usage-daily?days=7", headers=h, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["days"] == 7 and len(j["series"]) == 7

    def test_days_clamped_low_and_high(self, h):
        r1 = requests.get(f"{BASE_URL}/api/admin/ai-usage-daily?days=0", headers=h, timeout=15)
        assert r1.status_code == 200 and r1.json()["days"] == 1
        r2 = requests.get(f"{BASE_URL}/api/admin/ai-usage-daily?days=500", headers=h, timeout=15)
        assert r2.status_code == 200 and r2.json()["days"] == 90


# ---- AI budget GET/PUT ----
class TestAiBudget:
    def test_get_shape(self, h):
        r = requests.get(f"{BASE_URL}/api/admin/ai-budget", headers=h, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j.keys()) >= {"threshold", "alert_email", "month",
                                 "month_calls", "alert_sent_this_month"}
        assert j["month"] == datetime.now(timezone.utc).strftime("%Y-%m")
        assert isinstance(j["month_calls"], int)
        assert isinstance(j["alert_sent_this_month"], bool)

    def test_put_persists_and_resets_lock(self, h):
        payload = {"threshold": 5, "alert_email": "admin@construpilot.fr"}
        r = requests.put(f"{BASE_URL}/api/admin/ai-budget", headers=h,
                         json=payload, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["threshold"] == 5
        assert j["alert_email"] == "admin@construpilot.fr"
        assert j["alert_sent_this_month"] is False  # lock reset

        # GET reflects new values
        r2 = requests.get(f"{BASE_URL}/api/admin/ai-budget", headers=h, timeout=15)
        j2 = r2.json()
        assert j2["threshold"] == 5
        assert j2["alert_email"] == "admin@construpilot.fr"


# ---- Real AI call increments today's daily bucket ----
class TestAiDailyIncrement:
    def test_analyse_increments_today(self, h):
        # get baseline
        r0 = requests.get(f"{BASE_URL}/api/admin/ai-usage-daily?days=1", headers=h, timeout=15)
        assert r0.status_code == 200
        baseline = r0.json()["series"][0]["calls"]
        base_total = r0.json()["total"]
        today = datetime.now(timezone.utc).date().isoformat()

        # trigger real AI call
        body = {"description": "Rénovation d'une salle de bain de 6 m² avec douche à l'italienne",
                "surface": 6, "city": "Paris"}
        r1 = requests.post(f"{BASE_URL}/api/estimation/analyse",
                           headers=h, json=body, timeout=120)
        assert r1.status_code == 200, f"analyse failed: {r1.status_code} {r1.text[:400]}"

        # check today bucket >= baseline+1
        r2 = requests.get(f"{BASE_URL}/api/admin/ai-usage-daily?days=1", headers=h, timeout=15)
        assert r2.status_code == 200
        today_bucket = r2.json()["series"][0]
        assert today_bucket["date"] == today
        assert today_bucket["calls"] >= baseline + 1, \
            f"expected today calls >= {baseline+1}, got {today_bucket['calls']}"
        assert r2.json()["total"] >= base_total + 1


# ---- engines.ai.check_ai_budget doesn't crash ----
class TestCheckAiBudget:
    def test_check_runs(self, h):
        # ensure threshold=1 so it triggers
        requests.put(f"{BASE_URL}/api/admin/ai-budget", headers=h,
                     json={"threshold": 1, "alert_email": "admin@construpilot.fr"}, timeout=15)
        # month_calls >= 1 verified via GET
        rg = requests.get(f"{BASE_URL}/api/admin/ai-budget", headers=h, timeout=15).json()
        assert rg["month_calls"] >= 1, f"expected month_calls>=1, got {rg}"

        # invoke check function in-process
        import sys
        sys.path.insert(0, "/app/backend")
        from engines import ai as ai_engine
        # Should not raise
        asyncio.get_event_loop().run_until_complete(ai_engine.check_ai_budget()) \
            if False else asyncio.new_event_loop().run_until_complete(ai_engine.check_ai_budget())
        # Second call should be a no-op (lock set); still no raise
        asyncio.new_event_loop().run_until_complete(ai_engine.check_ai_budget())


# ---- Prospect J+2 reminders ----
class TestProspectJ2:
    def _run(self, coro_fn):
        """Run an async fn in a fresh loop with a fresh motor client bound to it."""
        import sys
        sys.path.insert(0, "/app/backend")
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            # Patch modules to use a client bound to *this* loop
            from motor.motor_asyncio import AsyncIOMotorClient
            mongo_url = os.environ.get("MONGO_URL") or _load_env_val("MONGO_URL")
            db_name = os.environ.get("DB_NAME") or _load_env_val("DB_NAME")
            client = AsyncIOMotorClient(mongo_url, io_loop=loop)
            local_db = client[db_name]
            # monkeypatch db in both modules
            import server as _server
            from routes import leads as leads_mod
            orig_server_db = _server.db
            orig_leads_db = leads_mod.db
            _server.db = local_db
            leads_mod.db = local_db
            try:
                return loop.run_until_complete(coro_fn(local_db, leads_mod))
            finally:
                _server.db = orig_server_db
                leads_mod.db = orig_leads_db
                client.close()
        finally:
            loop.close()
            asyncio.set_event_loop(asyncio.new_event_loop())

    def test_recent_lead_not_reminded(self):
        """Lead created just now must NOT be reminded."""
        email = f"test_j2_recent_{uuid.uuid4().hex[:6]}@example.com"
        r = requests.post(f"{BASE_URL}/api/leads", json={
            "email": email, "name": "Recent Test",
            "source": "landing-hero-test",
        }, timeout=15)
        assert r.status_code == 200, r.text
        lead_id = r.json()["lead_id"]

        async def check(db_local, leads_mod):
            await leads_mod.run_prospect_reminders()
            doc = await db_local.leads.find_one({"lead_id": lead_id},
                                                {"_id": 0, "j2_reminded": 1})
            await db_local.leads.delete_one({"lead_id": lead_id})
            return doc

        doc = self._run(check)
        assert not (doc or {}).get("j2_reminded"), \
            f"recent lead should not be reminded: {doc}"

    def test_aged_lead_reminded(self):
        """Landing lead aged 3 days with no estimation must be reminded (j2_reminded=true)."""
        email = f"delivered+j2_aged_{uuid.uuid4().hex[:6]}@resend.dev"
        r = requests.post(f"{BASE_URL}/api/leads", json={
            "email": email, "name": "Aged Test",
            "source": "landing-hero-test",
        }, timeout=15)
        assert r.status_code == 200, r.text
        lead_id = r.json()["lead_id"]

        aged_iso = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()

        async def flow(db_local, leads_mod):
            await db_local.leads.update_one({"lead_id": lead_id},
                                            {"$set": {"created_at": aged_iso}})
            count = await leads_mod.run_prospect_reminders()
            doc = await db_local.leads.find_one({"lead_id": lead_id}, {"_id": 0})
            # second call: should NOT re-flag or send again for our lead
            count2 = await leads_mod.run_prospect_reminders()
            doc2 = await db_local.leads.find_one({"lead_id": lead_id},
                                                 {"_id": 0, "j2_reminded": 1})
            await db_local.leads.delete_one({"lead_id": lead_id})
            return count, doc, count2, doc2

        count, doc, count2, doc2 = self._run(flow)
        # Flag must be set on first pass (email best-effort may fail if Resend not configured)
        assert doc.get("j2_reminded") is True, f"lead should be flagged: {doc}"
        # idempotency: doc2 still has j2_reminded=true (guard prevents re-processing)
        assert doc2.get("j2_reminded") is True
        # count is number of *successfully sent* emails; expect >=1 when Resend is available.
        # If not available, at least the flag mechanic works.
        print(f"[j2] first_run_sent={count} second_run_sent={count2}")
