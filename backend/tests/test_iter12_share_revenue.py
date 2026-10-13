"""Iteration 12 backend tests — Revenue Cockpit + Share Analytics/Expiry + SMS Twilio stub."""
import os
import time
import requests
import pytest
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

from pathlib import Path
def _load_env(path):
    if not Path(path).exists(): return
    for line in Path(path).read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))
_load_env("/app/frontend/.env")
_load_env("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PWD = "Construpilot2026!"
USER_EMAIL = "demo@construpilot.fr"
USER_PWD = "Demo2026!"


def _login(email, pwd):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def user_token():
    return _login(USER_EMAIL, USER_PWD)


@pytest.fixture(scope="module")
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ============ SANITY ============
def test_root_ok():
    r = requests.get(f"{BASE_URL}/api/", timeout=10)
    assert r.status_code == 200


def test_plans_pro_pricing():
    r = requests.get(f"{BASE_URL}/api/plans?audience=pro", timeout=10)
    assert r.status_code == 200
    plans = r.json()
    if isinstance(plans, dict):
        plans = plans.get("plans", [])
    ids = {p["plan_id"]: p.get("amount_cents") for p in plans}
    # naming: pro_monthly / pro_business_monthly
    pro = ids.get("pro") or ids.get("pro_monthly")
    prob = ids.get("pro_business") or ids.get("pro_business_monthly")
    assert pro == 9900, f"pro amount_cents={pro} — ids={ids}"
    assert prob == 19900, f"pro_business amount_cents={prob} — ids={ids}"


# ============ REVENUE COCKPIT ============
class TestRevenueCockpit:
    def test_kpis_admin(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/revenue/kpis", headers=admin_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("mrr_eur", "arr_eur", "arpu_eur", "ltv_eur", "cac_eur",
                  "paying_subs", "trialing_subs", "revenue_this_month_eur", "funnel_30d"):
            assert k in d, f"missing key {k}"
        f = d["funnel_30d"]
        for k in ("signups", "trials_started", "paid_transactions", "leads"):
            assert k in f
        assert f["signups"] > 0, f"expected signups>0 got {f['signups']}"
        assert f["leads"] > 0, f"expected leads>0 got {f['leads']}"

    def test_kpis_forbidden_for_user(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/admin/revenue/kpis", headers=user_headers, timeout=15)
        assert r.status_code in (401, 403)

    def test_timeseries_30_returns_31_points(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/admin/revenue/timeseries?days=30",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["days"] == 30
        assert len(d["series"]) == 31, f"got {len(d['series'])} points"
        assert "day" in d["series"][0] and "revenue_eur" in d["series"][0]


# ============ SHARE ANALYTICS ============
@pytest.fixture(scope="module")
def project_id(user_headers):
    # compute estimation
    payload = {
        "project_type": "renovation_complete",
        "finish_level": "standard",
        "surface": 55,
        "region": "ile_de_france",
        "options": {},
    }
    r = requests.post(f"{BASE_URL}/api/estimation/compute", json=payload,
                      headers=user_headers, timeout=30)
    assert r.status_code == 200, r.text
    estimation = r.json()

    proj = {
        "name": f"TEST_ITER12_{int(time.time())}",
        "city": "Paris",
        "region": "ile_de_france",
        "surface": 55,
        "project_type": "renovation_complete",
        "finish_level": "standard",
        "description": "iter12 share test",
        "estimation": estimation,
    }
    r = requests.post(f"{BASE_URL}/api/projects", json=proj,
                      headers=user_headers, timeout=15)
    assert r.status_code in (200, 201), r.text
    return r.json()["project_id"]


class TestShareAnalytics:
    def test_share_no_expiry(self, user_headers, project_id):
        r = requests.post(f"{BASE_URL}/api/projects/{project_id}/share",
                          json={}, headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["token"] and d["expires_at"] is None
        self.__class__.token = d["token"]

    def test_open_public_3_times(self, project_id):
        token = self.__class__.token
        for ua in ("UA-A/1.0", "UA-B/2.0", "UA-C/3.0"):
            r = requests.get(f"{BASE_URL}/api/public/estimation/{token}",
                             headers={"User-Agent": ua}, timeout=10)
            assert r.status_code == 200, r.text

    def test_stats_shows_3_opens(self, user_headers, project_id):
        r = requests.get(f"{BASE_URL}/api/projects/{project_id}/share/stats",
                         headers=user_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["opens"] >= 3, f"opens={d['opens']}"
        assert d["last_open_at"]
        assert len(d["recent_events"]) >= 3
        ev = d["recent_events"][-1]
        assert "at" in ev and "ua" in ev and "ip" in ev


# ============ SHARE EXPIRY ============
class TestShareExpiry:
    def test_expiry_7_days(self, user_headers, project_id):
        r = requests.post(f"{BASE_URL}/api/projects/{project_id}/share",
                          json={"expires_in_days": 7}, headers=user_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["expires_at"]
        exp = datetime.fromisoformat(d["expires_at"])
        delta_days = (exp - datetime.now(timezone.utc)).total_seconds() / 86400
        assert 6.5 < delta_days < 7.5, f"delta_days={delta_days}"

    def test_expiry_expired_returns_410(self, user_headers, project_id):
        # generate with 1 day expiry
        r = requests.post(f"{BASE_URL}/api/projects/{project_id}/share",
                          json={"expires_in_days": 1}, headers=user_headers, timeout=15)
        assert r.status_code == 200
        token = r.json()["token"]

        # Force expiry in Mongo
        async def _expire():
            client = AsyncIOMotorClient(MONGO_URL)
            db = client[DB_NAME]
            await db.projects.update_one(
                {"share_token": token},
                {"$set": {"share_expires_at": "2020-01-01T00:00:00+00:00"}},
            )
            client.close()
        asyncio.run(_expire())

        r2 = requests.get(f"{BASE_URL}/api/public/estimation/{token}", timeout=10)
        assert r2.status_code == 410, f"expected 410 got {r2.status_code}: {r2.text}"


# ============ SMS CONFIG + TWILIO STUB ============
class TestSmsShare:
    def test_sms_config_public(self):
        r = requests.get(f"{BASE_URL}/api/share/sms/config", timeout=10)
        assert r.status_code == 200
        d = r.json()
        for key in ("twilio_enabled", "sid_configured", "token_configured",
                    "from_configured", "native_fallback_available"):
            assert isinstance(d[key], bool), key
        assert d["native_fallback_available"] == True

    def test_sms_twilio_returns_503(self, user_headers, project_id):
        cfg = requests.get(f"{BASE_URL}/api/share/sms/config", timeout=10).json()
        if cfg.get("twilio_enabled"):
            pytest.skip("Twilio configuré — pas d'envoi SMS réel en test")
        r = requests.post(f"{BASE_URL}/api/projects/{project_id}/share/sms",
                          json={"to": "+33612345678", "message": "Test"},
                          headers=user_headers, timeout=15)
        assert r.status_code == 503, f"expected 503 got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Twilio non configuré" in detail, f"detail={detail}"


# ============ PHASE 7 NON-REG ============
class TestPhase7NonReg:
    def test_push_public_key(self):
        r = requests.get(f"{BASE_URL}/api/push/public-key", timeout=10)
        assert r.status_code == 200
        assert "public_key" in r.json() or "publicKey" in r.json()
