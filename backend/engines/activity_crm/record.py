"""Helper fail-soft para registar actividade de cliente externo.

Nunca levanta — se Mongo falha, loga aviso e devolve `None`. CRM lite não deve
quebrar fluxos de negócio.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

from core.db import db

from .models import (
    COLLECTION,
    ActivityCreate,
    AttachmentRef,
    Kind,
    mask_email,
    utc_now_iso,
)

logger = logging.getLogger("activity_crm")


async def record_activity(
    kind: Kind,
    user_email: str,
    user_name: str = "",
    summary: str = "",
    *,
    user_phone: str | None = None,
    source_url: str | None = None,
    payload: dict[str, Any] | None = None,
    attachments: list[AttachmentRef | dict] | None = None,
    is_fr_project: bool = False,
    no_email: bool = False,
) -> str | None:
    """Insere entrada no CRM lite. Devolve o id novo ou `None` em caso de falha.

    Fail-soft: nunca propaga exceção; apenas regista no logger.
    """
    try:
        atts: list[AttachmentRef] = []
        for a in attachments or []:
            if isinstance(a, AttachmentRef):
                atts.append(a)
            elif isinstance(a, dict):
                atts.append(AttachmentRef(**a))
        model = ActivityCreate(
            kind=kind,
            user_email=user_email,
            user_name=user_name or "",
            user_phone=user_phone,
            summary=(summary or "").strip()[:400] or kind,
            payload=payload or {},
            source_url=source_url,
            attachments=atts,
            is_fr_project=is_fr_project,
        )
        now = utc_now_iso()
        doc = {
            "created_at": now,
            "updated_at": now,
            "kind": model.kind,
            "user_email": model.user_email.lower(),
            "user_name": model.user_name,
            "user_phone": model.user_phone,
            "summary": model.summary,
            "payload": model.payload,
            "source_url": model.source_url,
            "attachments": [a.model_dump() for a in model.attachments],
            "state": "novo",
            "assigned_to": None,
            "internal_notes": [],
            "state_history": [],
            "is_fr_project": model.is_fr_project,
            "no_email": no_email,
            "last_email_at": None,
            # Chave externa auxiliar (não é _id — _id é Mongo ObjectId)
            "ext_id": "act_" + secrets.token_hex(6),
        }
        res = await db[COLLECTION].insert_one(doc)
        logger.info("activity_crm recorded kind=%s email=%s id=%s",
                    kind, mask_email(user_email), doc["ext_id"])
        return str(res.inserted_id)
    except Exception as exc:  # noqa: BLE001 — fail-soft
        logger.warning("activity_crm skipped (kind=%s email=%s): %s",
                       kind, mask_email(user_email), exc)
        return None
