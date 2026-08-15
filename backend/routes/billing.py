"""Routes monétisation ConstruPilot : plans publics, checkout, webhook, statut, mon abo."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.db import db
from core.security import current_user
from engines import monetization

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


# ---------- Public : liste des plans ----------

@router.get("/plans")
async def list_plans(audience: str | None = None) -> dict:
    q = {"active": True}
    if audience:
        q["audience"] = audience
    plans = await db.plans.find(q, {"_id": 0}).sort("sort_order", 1).to_list(50)
    flags = await db.feature_flags.find_one({"_id": "global"}, {"_id": 0}) or {}
    return {"plans": plans, "flags": {
        "trial_enabled": flags.get("trial_enabled", True),
        "trial_days": flags.get("trial_days", 7),
        "paywall_mode": flags.get("paywall_mode", "soft"),
        "promo_codes_enabled": flags.get("promo_codes_enabled", True),
    }}


# ---------- Checkout ----------

class CheckoutIn(BaseModel):
    plan_id: str
    origin_url: str
    promo_code: str | None = None


@router.post("/billing/checkout")
async def checkout(body: CheckoutIn, user=Depends(current_user)):
    plan = await db.plans.find_one({"plan_id": body.plan_id, "active": True}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Plan introuvable")
    if plan["kind"] == "free":
        raise HTTPException(status_code=400, detail="Le plan gratuit ne nécessite pas de paiement")
    try:
        result = await monetization.create_checkout(user, plan, body.origin_url, body.promo_code)
    except Exception as e:
        logger.exception("Checkout error")
        raise HTTPException(status_code=502, detail=f"Stripe indisponible: {e}")
    return result


@router.get("/billing/status/{session_id}")
async def payment_status(session_id: str) -> dict:
    try:
        rec = await monetization.sync_status(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Session inconnue")
    return {"session_id": rec["session_id"],
            "status": rec["status"],
            "payment_status": rec["payment_status"],
            "plan_id": rec["plan_id"],
            "mode": rec["mode"]}


@router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        result = await monetization.handle_webhook(payload, sig)
    except Exception as e:
        logger.exception("Webhook error")
        raise HTTPException(status_code=400, detail=str(e))
    return result


# ---------- Portail utilisateur ----------

@router.get("/billing/me")
async def my_billing(user=Depends(current_user)) -> dict:
    active = await monetization.user_active_plan(user["user_id"])
    tier = await monetization.user_tier(user["user_id"])
    history = await db.payment_transactions.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return {"tier": tier, "active": active, "history": history}


@router.get("/billing/credits-3d")
async def credits_3d(user=Depends(current_user)) -> dict:
    """Résumé des droits 3D (rendus offerts restants + crédits achetés + tarifs)."""
    return await monetization.credits_3d_summary(user)


class PortalIn(BaseModel):
    return_url: str


@router.post("/billing/portal")
async def customer_portal(body: PortalIn, user=Depends(current_user)) -> dict:
    import stripe
    if not user.get("stripe_customer_id"):
        raise HTTPException(status_code=404, detail="Aucun compte de facturation")
    session = stripe.billing_portal.Session.create(
        customer=user["stripe_customer_id"],
        return_url=body.return_url)
    return {"url": session.url}


# ---------- Feature flags publics ----------

@router.get("/billing/flags")
async def public_flags() -> dict:
    flags = await db.feature_flags.find_one({"_id": "global"}, {"_id": 0}) or {}
    return {"trial_enabled": flags.get("trial_enabled", True),
            "trial_days": flags.get("trial_days", 7),
            "paywall_mode": flags.get("paywall_mode", "soft"),
            "marketplace_enabled": flags.get("marketplace_enabled", False),
            "affiliate_enabled": flags.get("affiliate_enabled", False)}
