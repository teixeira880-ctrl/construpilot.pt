"""AK.4 — Notificações por email ao cliente em mudança de estado.

Resolve locale PT/FR, aplica rate-limit (10 min por activity), honra opt-out
(`activity.no_email`). Fail-soft: nunca propaga exceção.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.db import db
from engines.activity_crm.models import COLLECTION

logger = logging.getLogger("activity_crm.email")

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "emails" / "activity"

RATE_LIMIT_MINUTES = int(os.environ.get("ACTIVITY_EMAIL_RATE_LIMIT_MIN", "10"))

_STATE_SUBJECTS = {
    "pt": {
        "em_curso": "O seu pedido está em análise — ConstruPilot",
        "respondido": "Respondemos ao seu pedido — ConstruPilot",
        "fechado": "O seu pedido foi concluído — ConstruPilot",
    },
    "fr": {
        "em_curso": "Votre demande est en cours d'analyse — ConstruPilot",
        "respondido": "Nous avons répondu à votre demande — ConstruPilot",
        "fechado": "Votre demande a été clôturée — ConstruPilot",
    },
}


def _load_template(state: str, locale: str) -> str | None:
    path = TEMPLATES_DIR / f"state_{state}.{locale}.html"
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _render(tmpl: str, ctx: dict[str, Any]) -> str:
    # Substituição mínima estilo Jinja2 básico — evita dep adicional.
    out = tmpl
    for k, v in ctx.items():
        out = out.replace("{{" + k + "}}", str(v or ""))
    return out


async def _within_rate_limit(activity: dict) -> bool:
    """True se já foi enviado email recente (< RATE_LIMIT_MINUTES)."""
    last = activity.get("last_email_at")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return False
    delta = datetime.now(timezone.utc) - last_dt
    return delta < timedelta(minutes=RATE_LIMIT_MINUTES)


async def maybe_send_state_email(
    activity: dict,
    *,
    new_state: str | None = None,
    force: bool = False,
    custom_text: str | None = None,
) -> dict:
    """Envia email se tudo bater certo. Devolve dict com {sent, reason, locale}.

    Fail-soft: nunca levanta — reason explica o skip.
    """
    result = {"sent": False, "reason": "", "locale": None}
    try:
        if not activity:
            result["reason"] = "activity vazia"
            return result
        if activity.get("no_email"):
            result["reason"] = "opt-out (no_email=True)"
            return result
        state = new_state or activity.get("state")
        if state not in {"em_curso", "respondido", "fechado"}:
            result["reason"] = f"estado '{state}' não notificável"
            return result
        if not force and await _within_rate_limit(activity):
            result["reason"] = "rate-limit activo"
            return result

        locale = "fr" if activity.get("is_fr_project") else "pt"
        result["locale"] = locale
        tmpl = _load_template(state, locale)
        if not tmpl:
            result["reason"] = f"template em falta: state_{state}.{locale}.html"
            return result
        subject = _STATE_SUBJECTS[locale][state]
        html = _render(tmpl, {
            "nome": activity.get("user_name") or "",
            "email": activity.get("user_email") or "",
            "tipo": activity.get("kind") or "",
            "summary": activity.get("summary") or "",
            "custom_text": custom_text or "",
        })
        to = activity.get("user_email")
        if not to:
            result["reason"] = "sem email destinatário"
            return result

        from engines.emailer import send_email
        await send_email(to, subject, html)

        now = datetime.now(timezone.utc).isoformat()
        await db[COLLECTION].update_one(
            {"_id": activity["_id"]},
            {"$set": {"last_email_at": now, "updated_at": now}},
        )
        result["sent"] = True
        result["reason"] = "ok"
        logger.info("activity_crm email sent state=%s locale=%s to=%s",
                    state, locale, (to[:1] + "***"))
    except Exception as exc:  # noqa: BLE001 — fail-soft
        result["reason"] = f"erro: {type(exc).__name__}"
        logger.warning("activity_crm email fail state=%s: %s",
                       new_state, exc)
    return result
