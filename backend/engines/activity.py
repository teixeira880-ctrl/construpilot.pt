"""Journal d'activité (audit léger) par entreprise.

log() est best-effort : il résout l'organisation + le nom de l'acteur et
enregistre l'événement. Ne lève jamais d'exception (ne casse pas le flux métier).
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from core.db import db

logger = logging.getLogger("activity")

# action → libellé lisible
ACTIONS = {
    "quote.create": "a créé un devis",
    "quote.update": "a modifié un devis",
    "invoice.create": "a créé une facture",
    "invoice.update": "a modifié une facture",
    "invoice.issue": "a émis une facture",
    "invoice.convert": "a converti un devis en facture",
    "document.delete": "a supprimé un document",
    "situation.create": "a créé une situation de travaux",
    "employee.create": "a ajouté un employé",
    "member.update": "a modifié un accès employé",
    "clock.in": "a pointé son arrivée",
    "clock.out": "a pointé son départ",
    "retention.release": "a libéré une retenue de garantie",
}


async def log(user: dict, action: str, entity: str = "", label: str = "", meta: dict | None = None) -> None:
    try:
        u = await db.users.find_one(
            {"user_id": user["user_id"]},
            {"_id": 0, "organization_id": 1, "employer_id": 1, "name": 1, "email": 1}) or {}
        org_id = u.get("organization_id")
        if not org_id and u.get("employer_id"):
            emp = await db.users.find_one(
                {"user_id": u["employer_id"]}, {"_id": 0, "organization_id": 1})
            org_id = (emp or {}).get("organization_id") or f"solo:{u['employer_id']}"
        org_id = org_id or f"solo:{user['user_id']}"
        entry = {
            "log_id": "log_" + secrets.token_hex(6),
            "org_id": org_id,
            "actor_id": user["user_id"],
            "actor_name": u.get("name") or u.get("email") or "Utilisateur",
            "action": action,
            "action_label": ACTIONS.get(action, action),
            "entity": entity,
            "label": label,
            "meta": meta or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.activity_log.insert_one(entry)
    except Exception as exc:  # journalisation non bloquante
        logger.info("activity log skipped: %s", exc)


async def recent(org_id: str, limit: int = 100, action: str = "", actor_id: str = "") -> list[dict]:
    q: dict = {"org_id": org_id}
    if action:
        q["action"] = action
    if actor_id:
        q["actor_id"] = actor_id
    return await db.activity_log.find(q, {"_id": 0}).sort("created_at", -1).to_list(limit)
