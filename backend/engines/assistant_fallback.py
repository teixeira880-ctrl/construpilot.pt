"""Automatic fallback OpenAI → universal key (Claude) when the account's OpenAI key fails on credits, quota or authentication.
The degraded state is remembered (DB) so following turns go straight to the fallback until the cooldown expires."""
import os
from datetime import datetime, timedelta, timezone

from core.db import db

BILLING_MARKERS = ("no credits", "credits remaining", "insufficient_quota", "billing", "quota", "payment", "invalid_api_key", "incorrect api key",
                   "authentication", "402", "account is not active", "deactivated",
                   "budget", "budget has been exceeded", "exceeded", "current cost", "max budget")
RATE_MARKERS = ("rate limit", "ratelimit", "429", "too many requests", "overloaded", "capacity")
COOLDOWN_MIN = 30


def is_billing_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    code = getattr(exc, "status_code", None)
    if any(m in msg for m in BILLING_MARKERS):
        return True
    return code in (401, 402) or (code == 429 and "rate" not in msg)


def is_rate_error(exc: Exception) -> bool:
    """Limite de débit transitoire (hors dépassement de budget)."""
    msg = str(exc).lower()
    if any(m in msg for m in BILLING_MARKERS):
        return False
    return getattr(exc, "status_code", None) == 429 or any(m in msg for m in RATE_MARKERS)


def should_failover(exc: Exception) -> bool:
    return is_billing_error(exc) or is_rate_error(exc)


def friendly_error(exc: Exception) -> str:
    """Message clair pour l'utilisateur, sans aucun détail technique (clé, coût, fournisseur, litellm)."""
    msg = str(exc).lower()
    if any(m in msg for m in ("budget", "exceeded", "current cost", "max budget", "quota", "no credits", "credits remaining", "insufficient", "payment", "billing")):
        return ("O assistente atingiu o seu limite de utilização por agora. Tente novamente dentro de alguns minutos.")
    if is_rate_error(exc):
        return ("O assistente está muito solicitado neste momento. Tente novamente dentro de instantes.")
    return "O assistente está momentaneamente indisponível. Tente novamente dentro de instantes."


def primary_provider() -> str:
    return os.environ.get("ASSISTANT_PROVIDER", "openai")


def fallback_available() -> bool:
    return bool(os.environ.get("EMERGENT_LLM_KEY") and os.environ.get("ASSISTANT_CLAUDE_MODEL_FAST"))


def gemini_fallback_available() -> bool:
    """Dernier recours du chat : Gemini (clé Google directe ou clé universelle) quand Claude a échoué lui aussi."""
    return bool((os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_GEMINI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY"))
                and os.environ.get("ASSISTANT_GEMINI_MODEL_FAST"))


async def openai_degraded() -> dict | None:
    """Active degradation record (or None). Missing OpenAI key counts as degraded."""
    if not os.environ.get("OPENAI_API_KEY"):
        return {"reason": "chave OpenAI ausente", "until": None}
    rec = await db.assistant_runtime.find_one({"key": "openai_degraded"}, {"_id": 0})
    if rec and rec.get("until") and rec["until"] > datetime.now(timezone.utc).isoformat():
        return rec
    return None


async def mark_openai_degraded(exc: Exception) -> dict:
    from engines.openai_studies import _safe_error
    rec = {"key": "openai_degraded", "reason": _safe_error(exc), "since": datetime.now(timezone.utc).isoformat(),
           "until": (datetime.now(timezone.utc) + timedelta(minutes=COOLDOWN_MIN)).isoformat()}
    await db.assistant_runtime.update_one({"key": "openai_degraded"}, {"$set": rec}, upsert=True)
    return rec


async def clear_openai_degraded() -> None:
    await db.assistant_runtime.delete_one({"key": "openai_degraded"})


async def use_fallback_now() -> tuple[bool, str | None]:
    """(fallback?, reason) for a new turn."""
    if primary_provider() == "anthropic":
        return True, "fornecedor principal: chave universal"
    if not fallback_available():
        return False, None
    rec = await openai_degraded()
    return (True, f"chave OpenAI indisponível ({rec['reason']}) — recurso à chave universal") if rec else (False, None)
