"""Iter 82 — Correctifs auth (admin secondaire, set-password Google, forgot Google)
et facturation 3D à l'unité (Project Pass 50€ + crédits render/video/mockup).
"""
import os
import uuid
import hashlib
import pytest
import requests
from datetime import datetime, timezone, timedelta

from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

# Mongo direct (pour créer un compte Google factice, poser un token, etc.)
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
_mongo = MongoClient(MONGO_URL)
_db = _mongo[DB_NAME]


# ---------- Helpers ----------

def _login(email: str, pwd: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    return r


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def admin_token() -> str:
    r = _login("admin@construpilot.fr", "Construpilot2026!")
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_token() -> str:
    r = _login("pro@construpilot.fr", "Pro2026!")
    assert r.status_code == 200, f"Pro login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def client_token() -> str:
    r = _login("client@construpilot.fr", "Client2026!")
    assert r.status_code == 200, f"Client login failed: {r.status_code} {r.text}"
    return r.json()["token"]


# ============================================================
# AUTH — Admin secondaire info@construpilot.fr
# ============================================================

class TestSecondAdmin:
    def test_login_second_admin(self):
        r = _login("info@construpilot.fr", "CP-Admin-2026!")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["role"] == "admin"
        assert data["user"].get("must_change_password") is True
        assert isinstance(data.get("token"), str) and len(data["token"]) > 10


# ============================================================
# AUTH — Set password compte Google + forgot Google
# ============================================================

@pytest.fixture
def google_user():
    """Crée un utilisateur Google sans password_hash. Cleanup après test."""
    uid = "test-google-" + uuid.uuid4().hex[:12]
    email = f"test.google.{uid}@example.com"
    _db.users.insert_one({
        "user_id": uid, "email": email, "name": "Google Test",
        "role": "user", "plan": "free", "auth_provider": "google",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # session pour Bearer
    session = "st_test_" + uuid.uuid4().hex
    _db.user_sessions.insert_one({
        "user_id": uid, "session_token": session,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=1),
        "created_at": datetime.now(timezone.utc),
    })
    yield {"user_id": uid, "email": email, "token": session}
    _db.users.delete_many({"user_id": uid})
    _db.user_sessions.delete_many({"user_id": uid})
    _db.password_reset_tokens.delete_many({"user_id": uid})


class TestGoogleSetPassword:
    def test_set_password_no_current(self, google_user):
        """Google user sans password_hash → change-password sans current_password → 200."""
        new_pwd = "NewGooglePwd123!"
        r = requests.post(f"{API}/auth/change-password",
                          json={"new_password": new_pwd},
                          headers=_auth_headers(google_user["token"]), timeout=15)
        assert r.status_code == 200, r.text
        # Ensuite : login email/password fonctionne
        r2 = _login(google_user["email"], new_pwd)
        assert r2.status_code == 200, r2.text
        assert r2.json()["user"]["email"] == google_user["email"]

    def test_change_password_with_password_requires_current(self, google_user):
        """Après avoir défini un mot de passe, un current_password vide → 401."""
        # 1) set initial password
        pwd1 = "InitPwd123!"
        r = requests.post(f"{API}/auth/change-password",
                          json={"new_password": pwd1},
                          headers=_auth_headers(google_user["token"]), timeout=15)
        assert r.status_code == 200
        # 2) essayer de le rechanger sans current_password → 401
        r2 = requests.post(f"{API}/auth/change-password",
                           json={"new_password": "AnotherPwd456!"},
                           headers=_auth_headers(google_user["token"]), timeout=15)
        assert r2.status_code == 401, r2.text


class TestForgotPasswordGoogle:
    def test_forgot_password_creates_token_for_google(self, google_user):
        """POST /auth/forgot-password pour compte Google → 200 + token créé en DB."""
        _db.password_reset_tokens.delete_many({"email": google_user["email"]})
        r = requests.post(f"{API}/auth/forgot-password",
                          json={"email": google_user["email"]}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        # Un token doit exister
        cnt = _db.password_reset_tokens.count_documents({"email": google_user["email"]})
        assert cnt >= 1, "Aucun token de reset créé pour un compte Google"

    def test_reset_password_valid_token(self, google_user):
        # Créer un token
        raw = "raw_token_" + uuid.uuid4().hex
        _db.password_reset_tokens.insert_one({
            "token_hash": hashlib.sha256(raw.encode()).hexdigest(),
            "email": google_user["email"], "user_id": google_user["user_id"],
            "used": False,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
        })
        r = requests.post(f"{API}/auth/reset-password",
                          json={"token": raw, "new_password": "ResetPwd2026!"}, timeout=15)
        assert r.status_code == 200, r.text
        # Login avec le nouveau password OK
        r2 = _login(google_user["email"], "ResetPwd2026!")
        assert r2.status_code == 200

    def test_reset_password_invalid_token(self):
        r = requests.post(f"{API}/auth/reset-password",
                          json={"token": "nonexistent_token_zzz", "new_password": "Abcdef12"},
                          timeout=15)
        assert r.status_code == 400, r.text


# ============================================================
# TARIFS — GET /api/plans
# ============================================================

class TestPlans:
    def test_prices_migrated(self):
        r = requests.get(f"{API}/plans", timeout=15)
        assert r.status_code == 200
        plans = {p["plan_id"]: p for p in r.json()["plans"]}
        expected = {
            "premium_monthly": 1900,
            "premium_yearly": 19000,
            "pro_monthly": 19900,
            "pro_yearly": 210000,
            "pro_business_monthly": 35000,
            "pro_business_yearly": 350000,
            "project_pass": 5000,
        }
        for pid, cents in expected.items():
            assert pid in plans, f"Plan {pid} manquant"
            assert plans[pid]["amount_cents"] == cents, (
                f"{pid}: expected {cents} got {plans[pid]['amount_cents']}")
        # project_pass a bien free_renders_3d=3
        pp_quotas = plans["project_pass"].get("quotas", {})
        assert pp_quotas.get("free_renders_3d") == 3, f"quotas={pp_quotas}"

    def test_addons_credits_3d_present(self):
        r = requests.get(f"{API}/plans", timeout=15)
        plans = {p["plan_id"]: p for p in r.json()["plans"]}
        for pid, cents in [("render_credit_3d", 500),
                           ("video_credit_3d", 1000),
                           ("mockup_credit_3d", 500)]:
            assert pid in plans, f"{pid} manquant"
            assert plans[pid]["amount_cents"] == cents
            assert plans[pid]["audience"] == "addon"


# ============================================================
# 3D — credits-3d summary
# ============================================================

class TestCredits3D:
    def test_free_user_summary(self, client_token):
        r = requests.get(f"{API}/billing/credits-3d",
                         headers=_auth_headers(client_token), timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["unlimited"] is False
        assert data["tier"] == "free"
        assert data.get("free_render_remaining") in (0, None)
        # Tous les crédits sont 0
        assert data["credits"] == {"render": 0, "video": 0, "mockup": 0}
        # Prix corrects
        assert data["prices_cents"]["render"] == 500
        assert data["prices_cents"]["video"] == 1000
        assert data["prices_cents"]["mockup"] == 500

    def test_pro_user_unlimited(self, pro_token):
        r = requests.get(f"{API}/billing/credits-3d",
                         headers=_auth_headers(pro_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["unlimited"] is True
        assert data["tier"] == "pro_business"

    def test_admin_unlimited(self, admin_token):
        r = requests.get(f"{API}/billing/credits-3d",
                         headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code == 200
        assert r.json()["unlimited"] is True


# ============================================================
# 3D Gating — 402 credit_required pour free
# ============================================================

class TestGating3D:
    def test_free_render_3d_gated(self, client_token):
        """POST /takeoffs/{any}/render-3d en free → 402 credit_required."""
        r = requests.post(f"{API}/takeoffs/fake_plan_id_xyz/render-3d",
                          json={}, headers=_auth_headers(client_token), timeout=15)
        assert r.status_code == 402, f"Expected 402, got {r.status_code}: {r.text}"
        detail = r.json().get("detail") or {}
        assert isinstance(detail, dict), f"detail not dict: {detail}"
        assert detail.get("error") == "credit_required"
        assert detail.get("kind") == "render"
        assert detail.get("price_cents") == 500
        assert detail.get("credit_plan_id") == "render_credit_3d"
        assert "message" in detail

    def test_admin_not_gated(self, admin_token):
        """Admin → pas de 402 (mais peut être 404 plan inexistant)."""
        r = requests.post(f"{API}/takeoffs/fake_plan_id_xyz/render-3d",
                          json={}, headers=_auth_headers(admin_token), timeout=15)
        assert r.status_code != 402, f"Admin got 402: {r.text}"

    def test_pro_not_gated(self, pro_token):
        r = requests.post(f"{API}/takeoffs/fake_plan_id_xyz/render-3d",
                          json={}, headers=_auth_headers(pro_token), timeout=15)
        assert r.status_code != 402, f"Pro got 402: {r.text}"


# ============================================================
# 3D — Checkout (URL Stripe uniquement, pas de paiement complet)
# ============================================================

class TestCheckout3DCredit:
    def test_checkout_render_credit_returns_url(self, client_token):
        r = requests.post(f"{API}/billing/checkout",
                          json={"plan_id": "render_credit_3d",
                                "origin_url": BASE_URL},
                          headers=_auth_headers(client_token), timeout=20)
        assert r.status_code == 200, f"{r.status_code}: {r.text}"
        data = r.json()
        assert "url" in data and data["url"].startswith("http"), data
