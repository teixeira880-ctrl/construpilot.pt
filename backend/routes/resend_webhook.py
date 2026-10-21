"""Webhook Resend — suivi des ouvertures d'e-mails (devis, relances, campagnes).

Resend signe ses webhooks via Svix (headers svix-id/svix-timestamp/svix-signature).
On vérifie la signature sur le corps BRUT avant tout parsing JSON, puis on met à jour
`quote_sends` (opened / open_count) en faisant correspondre `data.email_id` au champ
`email_id` stocké à l'envoi. Idempotent via un index unique sur `svix_id`.
"""
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from core.db import db

logger = logging.getLogger("resend_webhook")
router = APIRouter(tags=["webhooks"])

_TRACKED = {"email.opened", "email.delivered", "email.bounced"}


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _mark_opened(email_id: str, when: str) -> int:
    """Marque tout envoi (devis/relance) portant cet email_id comme ouvert."""
    res = await db.quote_sends.update_many(
        {"email_id": email_id},
        {"$set": {"opened": True, "last_opened_at": when},
         "$inc": {"open_count": 1},
         "$min": {"opened_at": when}})
    return res.matched_count


@router.post("/webhooks/resend")
async def resend_webhook(request: Request):
    secret = os.environ.get("RESEND_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Webhook Resend não configurado (RESEND_WEBHOOK_SECRET em falta)")

    raw = await request.body()
    svix_id = request.headers.get("svix-id")
    svix_ts = request.headers.get("svix-timestamp")
    svix_sig = request.headers.get("svix-signature")
    if not all((svix_id, svix_ts, svix_sig)):
        raise HTTPException(400, "Cabeçalhos Svix em falta")

    from svix.webhooks import Webhook, WebhookVerificationError
    try:
        Webhook(secret).verify(
            raw, {"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": svix_sig})
    except WebhookVerificationError:
        logger.warning("Signature webhook Resend invalide")
        raise HTTPException(400, "Assinatura inválida")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Erreur vérification webhook Resend")
        raise HTTPException(400, "Webhook inválido")

    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Corpo JSON inválido")

    event_type = event.get("type")
    data = event.get("data") or {}
    email_id = data.get("email_id")
    if not event_type or not email_id:
        raise HTTPException(400, "Evento Resend mal formado")
    if event_type not in _TRACKED:
        return {"received": True, "ignored": True}

    # Déduplication (Resend livre au moins une fois, avec retries).
    try:
        await db.resend_webhook_events.insert_one(
            {"svix_id": svix_id, "event_type": event_type,
             "email_id": email_id, "received_at": _now()})
    except DuplicateKeyError:
        return {"received": True, "duplicate": True}

    now = _now()
    if event_type == "email.opened":
        matched = await _mark_opened(email_id, now)
        if matched:
            send = await db.quote_sends.find_one({"email_id": email_id}, {"_id": 0})
            if send and send.get("user_id"):
                await db.notifications.insert_one({
                    "user_id": send["user_id"], "type": "quote_opened",
                    "email_id": email_id, "doc_id": send.get("doc_id"),
                    "client_email": send.get("client_email"),
                    "message": f"O seu e-mail foi aberto por {send.get('client_email') or 'o destinatário'}",
                    "read": False, "created_at": now})
    elif event_type == "email.delivered":
        await db.quote_sends.update_many(
            {"email_id": email_id}, {"$set": {"delivered": True, "delivered_at": now}})
    elif event_type == "email.bounced":
        await db.quote_sends.update_many(
            {"email_id": email_id},
            {"$set": {"bounced": True, "bounced_at": now, "bounce": data.get("bounce")}})

    return {"received": True, "type": event_type}
