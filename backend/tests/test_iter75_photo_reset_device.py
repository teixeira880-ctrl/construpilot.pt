"""Iter 75 — Photo de profil, mot de passe oublié, alerte admin nouvel appareil."""
import os
import base64
import hashlib
import secrets
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from io import BytesIO

import requests
from PIL import Image
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
    from tests.creds import DEMO_EMAIL, DEMO_PWD, ADMIN_EMAIL, ADMIN_PWD
except ImportError:
    from creds import DEMO_EMAIL, DEMO_PWD, ADMIN_EMAIL, ADMIN_PWD


def _login(email, pwd, ua=None):
    headers = {"User-Agent": ua} if ua else {}
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd},
                      headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _img_b64():
    img = Image.new("RGB", (400, 400), (30, 120, 60))
    b = BytesIO()
    img.save(b, format="PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


def _run(coro):
    asyncio.run(coro)


# ---------- Photo de profil ----------

def test_profile_photo_upload_and_delete():
    h = _login(DEMO_EMAIL, DEMO_PWD)
    r = requests.post(f"{API}/auth/profile-photo", json={"image_b64": _img_b64()},
                      headers=h, timeout=30)
    assert r.status_code == 200, r.text
    pic = r.json()["user"]["picture"]
    assert pic.startswith("data:image/jpeg;base64,")
    assert len(pic) < 200_000  # redimensionnée 256px
    me = requests.get(f"{API}/auth/me", headers=h, timeout=15).json()
    assert me["picture"] == pic
    r = requests.delete(f"{API}/auth/profile-photo", headers=h, timeout=15)
    assert r.status_code == 200
    assert r.json()["user"]["picture"] is None


def test_profile_photo_rejects_garbage():
    h = _login(DEMO_EMAIL, DEMO_PWD)
    r = requests.post(f"{API}/auth/profile-photo", json={"image_b64": "cGFzdW5laW1hZ2U="},
                      headers=h, timeout=15)
    assert r.status_code == 400


# ---------- Mot de passe oublié ----------

def test_forgot_password_no_enumeration():
    r1 = requests.post(f"{API}/auth/forgot-password",
                       json={"email": DEMO_EMAIL}, timeout=15)
    r2 = requests.post(f"{API}/auth/forgot-password",
                       json={"email": f"inconnu-{uuid.uuid4().hex[:8]}@test.fr"}, timeout=15)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json() == {"ok": True}


def test_reset_password_full_flow():
    email = f"reset-{uuid.uuid4().hex[:8]}@test.fr"
    r = requests.post(f"{API}/auth/register",
                      json={"name": "Reset Flow", "email": email, "password": "AncienMdp2026!"},
                      timeout=30)
    assert r.status_code == 200, r.text
    user_id = r.json()["user"]["user_id"]

    token = secrets.token_urlsafe(32)

    async def _insert():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        await db.password_reset_tokens.insert_one({
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "email": email, "user_id": user_id, "used": False,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1)})
    _run(_insert())

    # mdp trop court
    r = requests.post(f"{API}/auth/reset-password",
                      json={"token": token, "new_password": "court"}, timeout=15)
    assert r.status_code == 400
    # reset OK
    r = requests.post(f"{API}/auth/reset-password",
                      json={"token": token, "new_password": "NouveauReset2026!"}, timeout=15)
    assert r.status_code == 200, r.text
    # token à usage unique
    r = requests.post(f"{API}/auth/reset-password",
                      json={"token": token, "new_password": "Encore2026!"}, timeout=15)
    assert r.status_code == 400
    # ancien mdp rejeté, nouveau accepté
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": "AncienMdp2026!"}, timeout=15)
    assert r.status_code == 401
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": "NouveauReset2026!"}, timeout=15)
    assert r.status_code == 200

    async def _cleanup():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        await db.users.delete_one({"email": email})
        await db.password_reset_tokens.delete_many({"email": email})
        await db.login_attempts.delete_many({"identifier": {"$regex": email}})
    _run(_cleanup())


def test_reset_password_invalid_token():
    r = requests.post(f"{API}/auth/reset-password",
                      json={"token": "nimportequoi", "new_password": "Valide2026!"}, timeout=15)
    assert r.status_code == 400


# ---------- Alerte admin nouvel appareil ----------

def test_admin_login_registers_new_device():
    ua = f"PytestDevice/{uuid.uuid4().hex[:6]}"
    _login(ADMIN_EMAIL, ADMIN_PWD, ua=ua)

    async def _check():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        u = await db.users.find_one({"email": ADMIN_EMAIL})
        dev = await db.known_devices.find_one({"user_id": u["user_id"], "user_agent": ua})
        assert dev, "device non enregistré"
        # re-login même appareil → pas de doublon
        before = await db.known_devices.count_documents({"user_id": u["user_id"]})
        return before
    before = None

    async def _count():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        u = await db.users.find_one({"email": ADMIN_EMAIL})
        return await db.known_devices.count_documents({"user_id": u["user_id"]})

    _run(_check())
    before = asyncio.run(_count())
    _login(ADMIN_EMAIL, ADMIN_PWD, ua=ua)
    after = asyncio.run(_count())
    assert after == before, "doublon d'appareil créé"

    async def _cleanup():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        await db.known_devices.delete_many({"user_agent": {"$regex": "^PytestDevice/"}})
    _run(_cleanup())


def test_non_admin_login_no_device_tracking():
    ua = f"PytestUserDevice/{uuid.uuid4().hex[:6]}"
    _login(DEMO_EMAIL, DEMO_PWD, ua=ua)

    async def _check():
        db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
        dev = await db.known_devices.find_one({"user_agent": ua})
        assert dev is None, "les non-admins ne doivent pas être trackés"
    _run(_check())
