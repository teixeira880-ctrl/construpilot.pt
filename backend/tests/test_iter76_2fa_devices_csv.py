"""Iter 76 — 2FA email admin, appareils connectés, logout-others, export CSV, pro sur page sign."""
import os
import hashlib
import uuid
import asyncio

import requests
from motor.motor_asyncio import AsyncIOMotorClient

def _fe_env():
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip()
    except Exception:
        return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe_env() or "").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

try:
    from tests.creds import DEMO_EMAIL, DEMO_PWD
except ImportError:
    from creds import DEMO_EMAIL, DEMO_PWD


def _db():
    return AsyncIOMotorClient(MONGO_URL)[DB_NAME]


def _login(email, pwd, ua="pytest-iter76"):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd},
                      headers={"User-Agent": ua}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _make_throwaway(role: str = "user"):
    """Compte jetable — évite de muter les comptes partagés (demo/admin)
    pendant que d'autres tests les utilisent en parallèle (xdist)."""
    email = f"jetable76-{uuid.uuid4().hex[:8]}@test.fr"
    r = requests.post(f"{API}/auth/register",
                      json={"name": "Jetable 76", "email": email, "password": "Jetable2026!"},
                      timeout=30)
    assert r.status_code == 200, r.text
    if role == "admin":
        async def _promote():
            await _db().users.update_one({"email": email}, {"$set": {"role": "admin"}})
        asyncio.run(_promote())
    return email, "Jetable2026!"


def _drop_throwaway(email: str):
    async def _rm():
        await _db().users.delete_many({"email": email})
        u = None
        await _db().known_devices.delete_many({"user_agent": {"$regex": "^PyDev"}})
        await _db().two_fa_codes.delete_many({})
        return u
    asyncio.run(_rm())


def test_2fa_full_flow_admin():
    """Flux 2FA complet sur un compte admin JETABLE (jamais le compte partagé)."""
    email, pwd = _make_throwaway(role="admin")
    try:
        d = _login(email, pwd)
        h = {"Authorization": f"Bearer {d['token']}"}
        r = requests.put(f"{API}/auth/2fa", json={"enabled": True}, headers=h, timeout=15)
        assert r.status_code == 200 and r.json()["user"]["two_fa_enabled"] == True

        # Login → 2FA exigée, aucun jeton délivré
        r = requests.post(f"{API}/auth/login",
                          json={"email": email, "password": pwd}, timeout=30)
        assert r.status_code == 200, r.text
        d2 = r.json()
        assert d2.get("two_fa_required") == True
        assert "token" not in d2 and "user" not in d2
        pending = d2["pending_token"]

        # Code forcé en DB (le vrai part par email) — vérif hash only
        async def _force():
            rec = await _db().two_fa_codes.find_one({"pending_token": pending})
            assert rec and "code" not in rec, "le code ne doit jamais être stocké en clair"
            await _db().two_fa_codes.update_one(
                {"pending_token": pending},
                {"$set": {"code_hash": hashlib.sha256(b"424242").hexdigest()}})
        asyncio.run(_force())

        # Mauvais code → 401 ; bon code → user + token ; réutilisation → 401
        r = requests.post(f"{API}/auth/verify-2fa",
                          json={"pending_token": pending, "code": "111111"}, timeout=15)
        assert r.status_code == 401
        r = requests.post(f"{API}/auth/verify-2fa",
                          json={"pending_token": pending, "code": "424242"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["user"]["email"] == email and r.json().get("token")
        r = requests.post(f"{API}/auth/verify-2fa",
                          json={"pending_token": pending, "code": "424242"}, timeout=15)
        assert r.status_code == 401

        # Désactivation : mdp requis
        r = requests.put(f"{API}/auth/2fa", json={"enabled": False}, headers=h, timeout=15)
        assert r.status_code == 401
        r = requests.put(f"{API}/auth/2fa",
                         json={"enabled": False, "current_password": pwd},
                         headers=h, timeout=15)
        assert r.status_code == 200 and r.json()["user"]["two_fa_enabled"] == False
    finally:
        _drop_throwaway(email)


def test_2fa_toggle_forbidden_for_non_admin():
    d = _login(DEMO_EMAIL, DEMO_PWD)
    h = {"Authorization": f"Bearer {d['token']}"}
    r = requests.put(f"{API}/auth/2fa", json={"enabled": True}, headers=h, timeout=15)
    assert r.status_code == 403


def test_devices_list_delete_and_logout_others():
    email, pwd = _make_throwaway()
    try:
        ua_a = f"PyDevA/{uuid.uuid4().hex[:6]}"
        ua_b = f"PyDevB/{uuid.uuid4().hex[:6]}"
        tok_a = _login(email, pwd, ua=ua_a)["token"]
        _login(email, pwd, ua=ua_b)
        h_a = {"Authorization": f"Bearer {tok_a}", "User-Agent": ua_a}

        r = requests.get(f"{API}/auth/devices", headers=h_a, timeout=15)
        assert r.status_code == 200
        devs = r.json()["devices"]
        uas = {d["user_agent"]: d for d in devs}
        assert ua_a in uas and uas[ua_a]["current"] == True
        assert ua_b in uas and uas[ua_b]["current"] == False

        # Suppression de l'appareil B
        r = requests.delete(f"{API}/auth/devices/{uas[ua_b]['device_key']}",
                            headers=h_a, timeout=15)
        assert r.status_code == 200
        devs = requests.get(f"{API}/auth/devices", headers=h_a, timeout=15).json()["devices"]
        assert all(d["user_agent"] != ua_b for d in devs)

        # logout-others : ancien jeton mort, nouveau vivant
        r = requests.post(f"{API}/auth/logout-others", headers=h_a, timeout=15)
        assert r.status_code == 200
        new_tok = r.json()["token"]
        assert requests.get(f"{API}/auth/me",
                            headers={"Authorization": f"Bearer {tok_a}"}, timeout=15).status_code == 401
        assert requests.get(f"{API}/auth/me",
                            headers={"Authorization": f"Bearer {new_tok}"}, timeout=15).status_code == 200
    finally:
        _drop_throwaway(email)


def test_export_csv():
    d = _login(DEMO_EMAIL, DEMO_PWD)
    r = requests.get(f"{API}/quotes/export.csv",
                     headers={"Authorization": f"Bearer {d['token']}"}, timeout=30)
    assert r.status_code == 200
    assert "text/csv" in r.headers.get("content-type", "")
    assert "attachment" in r.headers.get("content-disposition", "")
    body = r.content.decode("utf-8")
    assert body.startswith("\ufeff")
    assert "Type;Date d'envoi;Client" in body


def test_export_csv_requires_auth():
    r = requests.get(f"{API}/quotes/export.csv", timeout=15)
    assert r.status_code == 401


def test_sign_page_exposes_pro_block():
    async def _token():
        p = await _db().plans_takeoff.find_one({"sent_reports.kind": "pc_study"},
                                                {"sent_reports": 1})
        if not p:
            return None
        return next((s["sign_token"] for s in p["sent_reports"]
                     if s.get("kind") == "pc_study" and s.get("sign_token")), None)
    loop = asyncio.new_event_loop()
    tok = loop.run_until_complete(_token())
    loop.close()
    if not tok:
        import pytest
        pytest.skip("aucune étude PC envoyée en base")
    r = requests.get(f"{API}/pc/sign/{tok}", timeout=15)
    assert r.status_code == 200
    pro = r.json().get("pro")
    assert pro is not None and "name" in pro and "photo" in pro and "phone" in pro
