"""Clé LLM par usage : les traitements « études » (plans, cotes, métrés, PC, matériaux, devis) utilisent la clé
OpenAI de l'entreprise (OPENAI_API_KEY) quand elle est présente ET active, sinon la clé universelle Emergent.

Disjoncteur : dès qu'OpenAI répond « crédit épuisé / quota / clé invalide », la clé d'entreprise est désactivée
(persisté dans app_settings), l'admin est alerté (cloche + e-mail) et tout bascule sur la clé Emergent
jusqu'à réactivation manuelle depuis Admin → IA."""
import logging
import os
import secrets
from datetime import datetime, timezone

from core.db import db

logger = logging.getLogger(__name__)

_SETTINGS_ID = "openai_key"
_STATE: dict = {"loaded": False, "disabled": False, "reason": None, "since": None, "alerted": False}

_CREDIT_MARKERS = ("no credits", "insufficient_quota", "insufficient quota", "exceeded your current quota",
                   "billing", "invalid_api_key", "incorrect api key", "account_deactivated", "credit balance")


def openai_direct_active() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY")) and not _STATE["disabled"]


def studies_key(provider: str = "openai") -> str | None:
    if provider == "openai" and openai_direct_active():
        return os.environ["OPENAI_API_KEY"]
    return os.environ.get("EMERGENT_LLM_KEY")


def key_source(provider: str = "openai") -> str:
    return "openai_direct" if provider == "openai" and openai_direct_active() else "emergent"


def is_credit_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    code = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    return any(m in msg for m in _CREDIT_MARKERS) or code in (401, 402) or (code == 429 and "quota" in msg)


async def load_state() -> dict:
    doc = await db.app_settings.find_one({"_id": _SETTINGS_ID}) or {}
    _STATE.update({"loaded": True, "disabled": bool(doc.get("disabled")), "reason": doc.get("reason"),
                   "since": doc.get("since"), "alerted": bool(doc.get("alerted"))})
    return status()


def status() -> dict:
    return {"configured": bool(os.environ.get("OPENAI_API_KEY")), "active": openai_direct_active(),
            "disabled": _STATE["disabled"], "reason": _STATE["reason"], "since": _STATE["since"],
            "fallback": "Chave LLM universal Emergent"}


async def note_openai_error(exc: BaseException) -> bool:
    """À appeler dans un except après un appel OpenAI direct. Déclenche le disjoncteur si l'erreur
    est un problème de crédit/clé. Retourne True si la bascule vient d'être activée (→ réessayer)."""
    if not openai_direct_active() or not is_credit_error(exc):
        return False
    await load_state()  # état partagé (autre worker / réactivation récente) avant de décider
    if _STATE["disabled"]:
        return True
    await disable_openai(str(exc)[:300], alert=True)
    return True


async def disable_openai(reason: str, alert: bool = True) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    _STATE.update({"disabled": True, "reason": reason, "since": now})
    await db.app_settings.update_one({"_id": _SETTINGS_ID},
                                     {"$set": {"disabled": True, "reason": reason, "since": now}, "$setOnInsert": {"alerted": False}},
                                     upsert=True)
    logger.error("OpenAI direct key disabled (fallback Emergent): %s", reason)
    if alert:
        await _alert_admins(reason, now)
    return status()


async def _alert_admins(reason: str, since: str) -> None:
    claimed = await db.app_settings.update_one({"_id": _SETTINGS_ID, "alerted": {"$ne": True}}, {"$set": {"alerted": True}})
    if not claimed.modified_count:
        return
    _STATE["alerted"] = True
    admins = await db.users.find({"role": "admin"}, {"_id": 0, "user_id": 1, "email": 1}).to_list(20)
    ai_doc = await db.app_settings.find_one({"_id": "ai"}) or {}
    emails = {a["email"] for a in admins if a.get("email")}
    if ai_doc.get("budget_email"):
        emails.add(ai_doc["budget_email"])
    url = f"{(os.environ.get('FRONTEND_URL') or '').rstrip('/')}/admin?tab=ai"
    msg = ("Chave OpenAI da empresa desativada (crédito esgotado ou chave inválida). A IA funciona com a chave universal Emergent. Recarregue o crédito e depois reative a chave em Admin → IA.")
    for a in admins:
        try:
            await db.notifications.insert_one({
                "notif_id": "n_" + secrets.token_hex(5), "user_id": a["user_id"], "type": "openai_key_disabled",
                "message": msg, "url": "/admin?tab=ai",
                "created_at": since, "read": False})
        except Exception:
            pass
    try:
        from engines.emailer import send_email
        html = (f"<p>Olá,</p><p>A chave OpenAI da empresa foi <b>desativada automaticamente</b> em {since[:16].replace('T', ' à ')} UTC.</p><p><b>Motivo devolvido pela OpenAI:</b> {reason}</p><p>Todas as funções IA (orçamentos ditados, relatórios, coach, análises) funcionam agora com a <b>chave LLM universal Emergent</b>: nenhuma interrupção para os seus utilizadores.</p><p>Para voltar à sua chave OpenAI:</p><ol><li>Recarregue o crédito em <a href='https://platform.openai.com/settings/organization/billing'>platform.openai.com → Billing</a></li><li>Abra <a href='{url}'>Admin → IA</a> e clique em «Reativar a chave OpenAI» (é efetuado um teste de ligação antes da reativação).</li></ol><p>— ConstruPilot</p>")
        for e in emails:
            await send_email(e, "⚠️ Chave OpenAI desativada — recurso à chave Emergent", html)
    except Exception as e:
        logger.warning("openai key alert email failed: %s", e)


async def reactivate_openai() -> dict:
    """Test réel (mini-requête) puis remise en service. Lève ValueError si OpenAI refuse encore."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise ValueError("Nenhuma chave OpenAI configurada no servidor (OPENAI_API_KEY)")
    from openai import AsyncOpenAI
    try:
        client = AsyncOpenAI(api_key=key, timeout=30)
        await client.responses.create(model=os.environ.get("STUDIES_MODEL_LIGHT", "gpt-5.4-mini"),
                                      input="ping", max_output_tokens=16)
    except Exception as e:
        raise ValueError(f'A OpenAI continua a recusar a chave: {str(e)[:200]}') from None
    _STATE.update({"disabled": False, "reason": None, "since": None, "alerted": False})
    await db.app_settings.update_one({"_id": _SETTINGS_ID},
                                     {"$set": {"disabled": False, "reason": None, "since": None, "alerted": False,
                                               "reactivated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    logger.info("OpenAI direct key reactivated by admin")
    return status()
