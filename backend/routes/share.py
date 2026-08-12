"""Partage public d'estimation (WhatsApp/SMS/email) via lien signé.

- `POST /api/projects/{id}/share` (auth) : token public + expiry optionnel.
- `GET  /api/public/estimation/{token}` : vue lecture seule + tracking d'ouverture.
- `GET  /api/projects/{id}/share/stats` (auth) : nb d'ouvertures + dernier accès.
- `POST /api/projects/{id}/share/sms` (auth) : envoi SMS Twilio (si crédentials présents).
"""
import os
import logging
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["share"])

TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM_NUMBER", "")


def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat()


def _public_url(token: str) -> str:
    base = os.environ.get("PUBLIC_APP_URL") or "https://cmrenov-ai.preview.emergentagent.com"
    return f"{base.rstrip('/')}/e/{token}"


class ShareIn(BaseModel):
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


@router.post("/projects/{project_id}/share")
async def create_share_link(project_id: str, body: ShareIn | None = None,
                            user=Depends(current_user)):
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]})
    if not p:
        raise HTTPException(404, "Projet introuvable")
    token = p.get("share_token")
    if not token:
        token = secrets.token_urlsafe(16)
    days = (body.expires_in_days if body else None)
    expires_at = _iso(_now() + timedelta(days=days)) if days else None
    upd = {"share_token": token, "share_created_at": _iso()}
    if expires_at:
        upd["share_expires_at"] = expires_at
    else:
        # remove old expiry if user picks "never"
        await db.projects.update_one({"project_id": project_id},
                                     {"$unset": {"share_expires_at": ""}})
    await db.projects.update_one({"project_id": project_id}, {"$set": upd})
    return {"token": token, "url": _public_url(token), "project_id": project_id,
            "expires_at": expires_at}


@router.delete("/projects/{project_id}/share")
async def revoke_share_link(project_id: str, user=Depends(current_user)):
    res = await db.projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"$unset": {"share_token": "", "share_created_at": "", "share_expires_at": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Projet introuvable")
    return {"ok": True}


@router.get("/projects/{project_id}/share/stats")
async def share_stats(project_id: str, user=Depends(current_user)):
    p = await db.projects.find_one(
        {"project_id": project_id, "user_id": user["user_id"]},
        {"_id": 0, "share_token": 1, "share_opens": 1, "share_last_open_at": 1,
         "share_created_at": 1, "share_expires_at": 1, "share_events": 1},
    )
    if not p:
        raise HTTPException(404, "Projet introuvable")
    token = p.get("share_token")
    return {
        "token": token,
        "url": _public_url(token) if token else None,
        "opens": p.get("share_opens", 0),
        "last_open_at": p.get("share_last_open_at"),
        "created_at": p.get("share_created_at"),
        "expires_at": p.get("share_expires_at"),
        "recent_events": (p.get("share_events") or [])[-10:],
    }


@router.get("/public/estimation/{token}")
async def public_estimation(token: str, request: Request):
    p = await db.projects.find_one({"share_token": token},
                                   {"_id": 0, "user_id": 0})
    if not p:
        raise HTTPException(404, "Lien invalide ou expiré")
    # Expiry check
    expires_at = p.get("share_expires_at")
    if expires_at and expires_at < _iso():
        raise HTTPException(410, "Ce lien de partage a expiré")

    # Analytics — increment atomically, keep last 100 events
    now_iso = _iso()
    ua = (request.headers.get("user-agent") or "")[:180]
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or "?"
    event = {"at": now_iso, "ua": ua, "ip": ip}
    try:
        await db.projects.update_one(
            {"share_token": token},
            {"$inc": {"share_opens": 1},
             "$set": {"share_last_open_at": now_iso},
             "$push": {"share_events": {"$each": [event], "$slice": -100}}},
        )
    except Exception as e:
        logger.warning(f"Share analytics update failed: {e}")

    est = p.get("estimation") or {}
    return {
        "project": {
            "name": p.get("name"),
            "city": p.get("city"),
            "surface": p.get("surface"),
            "region": p.get("region"),
            "description": (p.get("description") or "")[:500],
            "created_at": p.get("created_at"),
        },
        "estimation": {
            "project_type_name": est.get("project_type_name"),
            "finish_level_name": est.get("finish_level_name"),
            "surface": est.get("surface"),
            "region": est.get("region"),
            "coef_region": est.get("coef_region"),
            "total_min": est.get("total_min"),
            "total_avg": est.get("total_avg"),
            "total_max": est.get("total_max"),
            "labor_hours": est.get("labor_hours"),
            "lots": est.get("lots") or [],
            "unit_price_avg": est.get("unit_price_avg"),
        },
        "shared_at": p.get("share_created_at"),
    }


# ============ SMS SHARING (Twilio) ============

class SmsShareIn(BaseModel):
    to: str = Field(min_length=6, max_length=20)
    message: str = Field(min_length=1, max_length=800)


@router.get("/share/sms/config")
async def sms_config():
    """Renvoie l'état de configuration Twilio (sans exposer les clés)."""
    return {
        "twilio_enabled": bool(TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM),
        "sid_configured": bool(TWILIO_SID),
        "token_configured": bool(TWILIO_TOKEN),
        "from_configured": bool(TWILIO_FROM),
        "native_fallback_available": True,
    }


@router.post("/projects/{project_id}/share/sms")
async def send_sms(project_id: str, body: SmsShareIn, user=Depends(current_user)):
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]},
                                   {"_id": 0, "share_token": 1})
    if not p:
        raise HTTPException(404, "Projet introuvable")

    if not (TWILIO_SID and TWILIO_TOKEN and TWILIO_FROM):
        raise HTTPException(503, "Twilio non configuré : utilisez le lien SMS natif")

    # Normalize E.164 : garde le +, retire espaces / tirets
    to = "".join(ch for ch in body.to if ch.isdigit() or ch == "+")
    if not to.startswith("+"):
        raise HTTPException(422, "Le numéro doit être au format international (+33…)")

    try:
        from twilio.rest import Client
        from twilio.base.exceptions import TwilioRestException
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        msg = client.messages.create(to=to, from_=TWILIO_FROM, body=body.message)
        # log analytics
        await db.projects.update_one(
            {"project_id": project_id},
            {"$inc": {"sms_sent_count": 1},
             "$push": {"sms_events": {"$each": [{"at": _iso(), "to": to[:-4] + "…",
                                                 "sid": msg.sid, "status": msg.status}],
                                      "$slice": -100}}}
        )
        return {"ok": True, "message_sid": msg.sid, "status": msg.status}
    except Exception as e:
        # TwilioRestException also catched here
        code = getattr(e, "code", None)
        logger.warning(f"Twilio SMS failed code={code}: {e}")
        raise HTTPException(502, f"Envoi SMS refusé par Twilio (code {code or 'inconnu'})")
