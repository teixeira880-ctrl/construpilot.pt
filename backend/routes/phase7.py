"""Routes Phase 7 : Push notifications + Retention email + Referral share."""
import os
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import current_user, admin_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["phase7"])

VAPID_PUBLIC = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_EMAIL = os.environ.get("VAPID_CLAIM_EMAIL", "admin@construpilot.fr")


def _now():
    return datetime.now(timezone.utc).isoformat()


# =============== PUSH NOTIFICATIONS ===============

@router.get("/push/public-key")
async def push_public_key():
    return {"public_key": VAPID_PUBLIC}


class PushSubIn(BaseModel):
    endpoint: str
    keys: dict  # {p256dh, auth}


@router.post("/push/subscribe")
async def push_subscribe(body: PushSubIn, user=Depends(current_user)):
    doc = {"user_id": user["user_id"], "endpoint": body.endpoint,
           "keys": body.keys, "created_at": _now()}
    await db.push_subscriptions.update_one({"endpoint": body.endpoint},
                                           {"$set": doc}, upsert=True)
    return {"ok": True}


@router.post("/push/unsubscribe")
async def push_unsubscribe(body: PushSubIn, user=Depends(current_user)):
    await db.push_subscriptions.delete_one({"endpoint": body.endpoint,
                                            "user_id": user["user_id"]})
    return {"ok": True}


def _send_push(sub: dict, payload: dict) -> bool:
    if not VAPID_PRIVATE:
        return False
    try:
        from pywebpush import webpush, WebPushException
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": sub["keys"]},
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE,
                vapid_claims={"sub": f"mailto:{VAPID_EMAIL}"})
        return True
    except Exception as e:  # includes WebPushException
        logger.warning(f"Push failed for {sub.get('endpoint','')[:40]}: {e}")
        return False


async def notify_user(user_id: str, title: str, body: str, url: str = "/") -> int:
    subs = await db.push_subscriptions.find({"user_id": user_id}, {"_id": 0}).to_list(20)
    sent = 0
    for s in subs:
        payload = {"title": title, "body": body, "url": url,
                   "icon": "/logo192.png"}
        if _send_push(s, payload):
            sent += 1
    return sent


@router.post("/push/test")
async def push_test(user=Depends(current_user)):
    n = await notify_user(user["user_id"], "ConstruPilot",
                          "🎉 Vos notifications push sont bien activées !", "/dashboard")
    return {"ok": True, "sent": n}


# =============== RETENTION digest manual trigger ===============

@router.post("/admin/retention/send-digests")
async def send_digests_now(admin=Depends(admin_user)):
    from engines import retention
    sent = await retention.send_weekly_digests()
    return {"ok": True, "sent": sent}


# =============== USER PREFS ===============

class PrefsIn(BaseModel):
    weekly_digest: bool | None = None
    push_price_alerts: bool | None = None


@router.put("/users/me/preferences")
async def update_prefs(body: PrefsIn, user=Depends(current_user)):
    upd = {k: v for k, v in body.model_dump().items() if v is not None}
    if upd:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    fresh = await db.users.find_one({"user_id": user["user_id"]},
                                    {"_id": 0, "weekly_digest": 1, "push_price_alerts": 1})
    return fresh or {}


# =============== PDF BRANDING (Pro) ===============

class BrandingIn(BaseModel):
    company_name: str | None = None
    contact_line: str | None = None
    logo_b64: str | None = None  # data URL ou base64 brute


@router.get("/users/me/branding")
async def get_branding(user=Depends(current_user)):
    doc = await db.users.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0, "brand_company_name": 1, "brand_contact_line": 1,
         "brand_logo_b64": 1}
    ) or {}
    return {
        "company_name": doc.get("brand_company_name"),
        "contact_line": doc.get("brand_contact_line"),
        "has_logo": bool(doc.get("brand_logo_b64")),
        "logo_b64": doc.get("brand_logo_b64"),
    }


@router.put("/users/me/branding")
async def update_branding(body: BrandingIn, user=Depends(current_user)):
    upd = {}
    if body.company_name is not None:
        upd["brand_company_name"] = body.company_name.strip()[:120] or None
    if body.contact_line is not None:
        upd["brand_contact_line"] = body.contact_line.strip()[:200] or None
    if body.logo_b64 is not None:
        # Limite raisonnable : ~500 ko en base64 = 375 ko fichier
        b64_clean = body.logo_b64.split(",")[-1] if body.logo_b64 else ""
        if len(b64_clean) > 500_000:
            from fastapi import HTTPException
            raise HTTPException(413, "Logo trop volumineux (max ~375 Ko)")
        upd["brand_logo_b64"] = b64_clean or None
    if upd:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": upd})
    return await get_branding(user)
