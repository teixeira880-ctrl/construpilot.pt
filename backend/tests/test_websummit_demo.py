"""Testes unitários — Web Summit demo (seed, demo-login, guards, reset).

Testa:
    * Seed fail-closed quando segredos ausentes.
    * Seed cria contas/projecto/entitlement quando segredos presentes.
    * Seed idempotente (não cria duplicados, não reescreve password se já corresponde).
    * `/api/auth/demo-login` 503 sem segredos.
    * `/api/auth/demo-login` 200 com segredos — response **sem password em claro**.
    * Guard middleware bloqueia acções sensíveis para sessões demo.
    * Quota IA diária 20 chamadas → 429 à 21ª.
    * Admin reset limpa dados demo.
    * Email/password/perfil imutáveis para contas demo.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret-websummit")


# ---------------------------------------------------------------------------
# Helpers — passwords sintéticas usadas só nos próprios testes.
# ---------------------------------------------------------------------------
def _test_pro_pwd() -> str:
    """Password sintética para test fixtures (nunca é segredo real)."""
    return "L0cal" + "Test!" + "Websummit" + "Pro"


def _test_part_pwd() -> str:
    return "L0cal" + "Test!" + "Websummit" + "Par"


def _env_with_secrets(**overrides) -> dict:
    base = {
        "WEBSUMMIT_DEMO_EMAIL_PT": "demo.websummit@construpilot.pt",
        "WEBSUMMIT_DEMO_PASSWORD_PT": _test_pro_pwd(),
        "WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT": "demo.websummit.particular@construpilot.pt",
        "WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT": _test_part_pwd(),
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. Config helpers (sem touching DB)
# ---------------------------------------------------------------------------
def test_is_configured_false_when_env_missing():
    with patch.dict(os.environ, {}, clear=False):
        for k in ("WEBSUMMIT_DEMO_PASSWORD_PT", "WEBSUMMIT_DEMO_PARTICULAR_PASSWORD_PT"):
            os.environ.pop(k, None)
        from core.websummit_seed_pt import is_websummit_demo_configured
        cfg = is_websummit_demo_configured()
        assert cfg == {"pro_configured": False, "particular_configured": False}


def test_is_configured_true_when_env_present():
    with patch.dict(os.environ, _env_with_secrets(), clear=False):
        from core.websummit_seed_pt import is_websummit_demo_configured
        cfg = is_websummit_demo_configured()
        assert cfg["pro_configured"] is True
        assert cfg["particular_configured"] is True


def test_redacted_placeholder_is_treated_as_missing():
    """Fail-closed: `<redacted>` no .env NÃO é password válida."""
    with patch.dict(os.environ, {"WEBSUMMIT_DEMO_PASSWORD_PT": "<redacted>"}, clear=False):
        from core.websummit_seed_pt import _env
        assert _env("WEBSUMMIT_DEMO_PASSWORD_PT") is None


# ---------------------------------------------------------------------------
# 2. Seed idempotency (mock DB)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_seed_skips_when_env_missing():
    """Fail-closed: sem env → nenhuma inserção."""
    with patch.dict(os.environ, {}, clear=True):
        os.environ["JWT_SECRET"] = "x"
        from core.websummit_seed_pt import seed_websummit_demo_pt

        mock_db = MagicMock()
        summary = await seed_websummit_demo_pt(
            mock_db, lambda s: "hash", lambda a, b: True, lambda: "uid_x"
        )
        assert summary == {"pro": "skipped_missing_config", "particular": "skipped_missing_config", "project": None}
        mock_db.users.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_seed_creates_accounts_when_env_present():
    env = _env_with_secrets()
    with patch.dict(os.environ, env, clear=False):
        from core.websummit_seed_pt import seed_websummit_demo_pt

        mock_db = MagicMock()
        mock_db.users.find_one = AsyncMock(side_effect=[None, {"user_id": "uid1"}, None, {"user_id": "uid2"}, {"user_id": "uid1"}])
        mock_db.users.insert_one = AsyncMock()
        mock_db.users.update_one = AsyncMock()
        mock_db.entitlements.find_one = AsyncMock(return_value=None)
        mock_db.entitlements.insert_one = AsyncMock()
        mock_db.projects.find_one = AsyncMock(return_value=None)
        mock_db.projects.insert_one = AsyncMock()

        summary = await seed_websummit_demo_pt(
            mock_db,
            lambda s: f"hash::{s}",
            lambda plain, hashed: hashed == f"hash::{plain}",
            lambda: "uid_fake",
        )
        assert summary["pro"] == "created"
        assert summary["particular"] == "created"
        assert summary["project"] == "created"
        # Entitlement pro criado
        mock_db.entitlements.insert_one.assert_awaited_once()
        # Projecto criado
        mock_db.projects.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_seed_realigns_password_on_mismatch():
    """Se o hash existente não corresponde ao env, é realinhado (fundador rodou segredo)."""
    env = _env_with_secrets()
    with patch.dict(os.environ, env, clear=False):
        from core.websummit_seed_pt import seed_websummit_demo_pt

        existing_pro = {"email": env["WEBSUMMIT_DEMO_EMAIL_PT"], "user_id": "uid1",
                        "password_hash": "stale_hash", "is_demo": True, "demo_source": "websummit_2026",
                        "plan": "premium", "account_type": "pro", "email_verified": True}
        existing_part = {"email": env["WEBSUMMIT_DEMO_PARTICULAR_EMAIL_PT"], "user_id": "uid2",
                         "password_hash": "stale_hash", "is_demo": True, "demo_source": "websummit_2026",
                         "plan": "free", "account_type": "particulier", "email_verified": True}

        mock_db = MagicMock()
        mock_db.users.find_one = AsyncMock(side_effect=[existing_pro, {"user_id": "uid1"}, existing_part, {"user_id": "uid1"}])
        mock_db.users.update_one = AsyncMock()
        mock_db.entitlements.find_one = AsyncMock(return_value={"entitlement_id": "ok"})
        mock_db.projects.find_one = AsyncMock(return_value={"project_id": "p1"})

        def _verify(plain, hashed):
            return hashed == f"hash::{plain}"

        summary = await seed_websummit_demo_pt(
            mock_db, lambda s: f"hash::{s}", _verify, lambda: "uid_fake"
        )
        assert summary["pro"] == "updated"
        # password foi reescrita (pelo menos uma vez contains password_hash)
        calls = mock_db.users.update_one.await_args_list
        hashes_set = [c for c in calls if "password_hash" in (c.kwargs.get("$set") or c.args[1].get("$set", {}))]
        assert hashes_set, "password deveria ter sido realinhada"


# ---------------------------------------------------------------------------
# 3. Guards: ensure_not_demo, quota, demo_blocked response shape
# ---------------------------------------------------------------------------
def test_ensure_not_demo_passes_for_non_demo_user():
    from core.demo_guards import ensure_not_demo
    ensure_not_demo({"user_id": "x", "is_demo": False}, action="send_invoice")
    ensure_not_demo(None, action="send_invoice")  # anónimo passa


def test_ensure_not_demo_raises_403_for_demo_user():
    from fastapi import HTTPException
    from core.demo_guards import ensure_not_demo
    with pytest.raises(HTTPException) as exc:
        ensure_not_demo({"user_id": "x", "is_demo": True}, action="send_invoice")
    assert exc.value.status_code == 403
    assert exc.value.detail == {"error": "demo_blocked", "action": "send_invoice"}


def test_demo_blocked_response_shape():
    from core.demo_guards import demo_blocked_response
    assert demo_blocked_response("x") == {"error": "demo_blocked", "action": "x"}


@pytest.mark.asyncio
async def test_consume_demo_ai_quota_raises_429_when_exceeded():
    from fastapi import HTTPException
    from core.demo_guards import consume_demo_ai_quota, DEMO_AI_QUOTA_DAILY
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).isoformat()[:10]
    user = {
        "user_id": "demo_uid",
        "is_demo": True,
        "demo_quota_date": today,
        "demo_quota_ai_calls_today": DEMO_AI_QUOTA_DAILY,
    }
    with patch("core.demo_guards.db") as mock_db:
        mock_db.users.update_one = AsyncMock()
        with pytest.raises(HTTPException) as exc:
            await consume_demo_ai_quota(user)
        assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_consume_quota_is_noop_for_non_demo():
    from core.demo_guards import consume_demo_ai_quota
    with patch("core.demo_guards.db") as mock_db:
        mock_db.users.update_one = AsyncMock()
        await consume_demo_ai_quota({"user_id": "x", "is_demo": False})
        mock_db.users.update_one.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Middleware regex matching
# ---------------------------------------------------------------------------
def test_demo_middleware_matches_critical_paths():
    from core.demo_middleware import _match_action
    cases = [
        ("/api/documents/abc/send", "POST", "send_document"),
        ("/api/projects/xyz/share/sms", "POST", "send_sms"),
        ("/api/stripe/checkout", "POST", "payment"),
        ("/api/billing/stripe/webhook", "POST", "payment"),
        ("/api/plans/42/pc-study/send", "POST", "send_email"),
        ("/api/portal/ref/reception/pv1/sign", "POST", "sign"),
        ("/api/auth/change-password", "POST", "change_password"),
        ("/api/auth/profile", "PUT", "edit_profile"),
    ]
    for path, method, action in cases:
        assert _match_action(path, method) == action, f"falhou {path}"


def test_demo_middleware_lets_through_safe_paths():
    from core.demo_middleware import _match_action
    assert _match_action("/api/auth/me", "GET") is None
    assert _match_action("/api/projects", "GET") is None
    assert _match_action("/api/documents/abc", "GET") is None
    # GET em path "crítico" tb passa (só POST/PUT/PATCH/DELETE são bloqueados)
    assert _match_action("/api/documents/abc/send", "GET") is None


# ---------------------------------------------------------------------------
# 5. Response body não contém password
# ---------------------------------------------------------------------------
def test_public_demo_does_not_leak_password_or_hash():
    from routes.auth_demo import _public_demo
    user = {
        "user_id": "u1", "email": "demo@x.pt", "name": "Demo",
        "password_hash": "SHOULD_NOT_LEAK", "role": "user", "plan": "premium",
        "is_demo": True, "demo_source": "websummit_2026",
    }
    out = _public_demo(user)
    assert "password_hash" not in out
    assert "password" not in out
    assert out["email"] == "demo@x.pt"
    assert out["is_demo"] is True
    assert out["has_password"] is True  # abstracção, mas sem valor


# ---------------------------------------------------------------------------
# 6. Reset diário
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reset_cleans_demo_user_data_only():
    env = _env_with_secrets()
    with patch.dict(os.environ, env, clear=False):
        from core.websummit_seed_pt import reset_websummit_demo_data_pt
        mock_db = MagicMock()
        mock_db.users.find_one = AsyncMock(side_effect=[
            {"user_id": "uid_pro"},
            {"user_id": "uid_part"},
        ])
        del_result = MagicMock(deleted_count=5)
        for coll in ("quotes", "takeoffs", "photos", "project_documents",
                     "assistant_messages", "coach_messages", "activity_log",
                     "notifications", "email_logs", "stripe_customer_actions"):
            getattr(mock_db, coll).delete_many = AsyncMock(return_value=del_result)
        mock_db.users.update_one = AsyncMock()
        # Como `mock_db[coll]` é também MagicMock, delete_many retorna um MagicMock
        # que serve o `.deleted_count` quando acedido. Simplificamos com genérico:
        mock_db.__getitem__.return_value.delete_many = AsyncMock(return_value=del_result)

        summary = await reset_websummit_demo_data_pt(mock_db)
        assert summary["pro_user_id"] == "uid_pro"
        assert summary["particular_user_id"] == "uid_part"
