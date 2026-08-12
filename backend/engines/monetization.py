"""Stripe integration + entitlement helpers pour ConstruPilot Revenue Engine.

- Setup catalog idempotent (Products + Prices via lookup_key)
- Checkout Session (subscription + one-time)
- Webhook handler
- Entitlement resolution : quel plan l'utilisateur possède ?
"""
import os
import logging
from datetime import datetime, timezone

import stripe

from core.db import db

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def ensure_stripe_catalog():
    """Crée/synchronise les Products et Prices Stripe à partir des plans DB."""
    if not stripe.api_key:
        logger.warning("STRIPE_SECRET_KEY manquant — Stripe désactivé")
        return

    plans = await db.plans.find({"active": True,
                                 "kind": {"$in": ["subscription", "one_time"]}},
                                {"_id": 0}).to_list(50)
    # Charger les produits Stripe existants UNE fois (indexés par plan_id metadata)
    existing_products = {}
    for prod in stripe.Product.list(limit=100).auto_paging_iter():
        pid = (prod.get("metadata") or {}).get("plan_id")
        if pid:
            existing_products[pid] = prod

    for plan in plans:
        lookup = plan.get("lookup_key")
        if not lookup:
            continue
        prod = existing_products.get(plan["plan_id"])
        if not prod:
            prod = stripe.Product.create(
                name=f"ConstruPilot {plan['name']}",
                metadata={"managed_by": "construpilot", "plan_id": plan["plan_id"]},
                tax_code="txcd_10103001",
            )
            existing_products[plan["plan_id"]] = prod
        prices = stripe.Price.list(lookup_keys=[lookup], active=True, limit=1).data
        p = prices[0] if prices else None
        if p and (p.unit_amount != plan["amount_cents"] or p.currency != plan["currency"]):
            stripe.Price.modify(p.id, active=False)
            p = None
        if not p:
            kwargs = dict(product=prod.id,
                          unit_amount=plan["amount_cents"],
                          currency=plan["currency"],
                          lookup_key=lookup,
                          transfer_lookup_key=True,
                          metadata={"plan_id": plan["plan_id"]})
            if plan.get("interval"):
                kwargs["recurring"] = {"interval": plan["interval"]}
            p = stripe.Price.create(**kwargs)
        await db.plans.update_one({"plan_id": plan["plan_id"]},
                                  {"$set": {"stripe_product_id": prod.id,
                                            "stripe_price_id": p.id,
                                            "synced_at": now_iso()}})
    logger.info(f"Stripe catalog synced ({len(plans)} plans)")


async def get_or_create_customer(user: dict) -> str:
    if user.get("stripe_customer_id"):
        return user["stripe_customer_id"]
    cust = stripe.Customer.create(
        email=user["email"], name=user.get("name"),
        metadata={"user_id": user["user_id"]})
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"stripe_customer_id": cust.id}})
    return cust.id


async def create_checkout(user: dict, plan: dict, origin_url: str,
                          promo_code: str | None = None) -> dict:
    """Crée une Checkout Session Stripe pour le plan donné."""
    if not stripe.api_key:
        raise RuntimeError("Stripe non configuré")
    lookup = plan.get("lookup_key")
    if not lookup:
        raise ValueError(f"Plan {plan.get('plan_id')} sans lookup_key")

    prices = stripe.Price.list(lookup_keys=[lookup], active=True, limit=1).data
    if not prices:
        await ensure_stripe_catalog()
        prices = stripe.Price.list(lookup_keys=[lookup], active=True, limit=1).data
    if not prices:
        raise RuntimeError(f"Prix Stripe introuvable pour {lookup}")
    price = prices[0]

    customer_id = await get_or_create_customer(user)
    is_sub = plan["kind"] == "subscription"

    flags = await db.feature_flags.find_one({"_id": "global"}, {"_id": 0}) or {}
    trial_enabled = flags.get("trial_enabled", True)
    trial_days = plan.get("trial_days") or flags.get("trial_days") or 0

    kwargs = dict(
        customer=customer_id,
        line_items=[{"price": price.id, "quantity": 1}],
        mode="subscription" if is_sub else "payment",
        success_url=f"{origin_url}/paiement/succes?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin_url}/paiement/annule",
        metadata={"user_id": user["user_id"], "plan_id": plan["plan_id"],
                  "lookup_key": lookup},
        allow_promotion_codes=True,
    )
    if is_sub and trial_enabled and trial_days > 0:
        kwargs["subscription_data"] = {"trial_period_days": trial_days,
                                       "metadata": {"user_id": user["user_id"],
                                                    "plan_id": plan["plan_id"]}}
    if promo_code:
        # promo_code = code humain; on résout en promotion_code Stripe
        promos = stripe.PromotionCode.list(code=promo_code, active=True, limit=1).data
        if promos:
            kwargs.pop("allow_promotion_codes", None)
            kwargs["discounts"] = [{"promotion_code": promos[0].id}]

    session = stripe.checkout.Session.create(**kwargs)

    await db.payment_transactions.insert_one({
        "session_id": session.id, "user_id": user["user_id"],
        "plan_id": plan["plan_id"], "lookup_key": lookup,
        "amount_cents": price.unit_amount, "currency": price.currency,
        "mode": kwargs["mode"], "status": "initiated", "payment_status": "pending",
        "created_at": now_iso(), "updated_at": now_iso(),
    })
    return {"url": session.url, "session_id": session.id}


async def sync_status(session_id: str) -> dict:
    """Récupère le statut d'une Checkout Session. Idempotent."""
    if not stripe.api_key:
        raise RuntimeError("Stripe non configuré")
    rec = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not rec:
        raise ValueError("Session inconnue")
    if rec.get("payment_status") == "paid":
        return rec
    try:
        s = stripe.checkout.Session.retrieve(session_id)
    except Exception:
        return rec
    if s.payment_status == "paid" or s.status == "complete":
        await _mark_paid(session_id, s)
    return await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})


async def _mark_paid(session_id: str, s):
    upd = await db.payment_transactions.update_one(
        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
        {"$set": {"status": "completed", "payment_status": "paid",
                  "stripe_subscription_id": s.get("subscription"),
                  "stripe_payment_intent_id": s.get("payment_intent"),
                  "updated_at": now_iso()}})
    if upd.modified_count == 0:
        return
    # Grant entitlement
    rec = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    plan = await db.plans.find_one({"plan_id": rec["plan_id"]}, {"_id": 0})
    if not plan:
        return
    await grant_entitlement(rec["user_id"], plan, rec)


async def grant_entitlement(user_id: str, plan: dict, payment_rec: dict):
    """Crée/met à jour l'entitlement de l'utilisateur suite à un paiement."""
    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id, "plan_id": plan["plan_id"], "plan_code": plan["code"],
        "audience": plan["audience"], "kind": plan["kind"],
        "status": "active", "granted_at": now.isoformat(),
        "stripe_subscription_id": payment_rec.get("stripe_subscription_id"),
        "payment_session_id": payment_rec.get("session_id"),
    }
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    doc["stripe_customer_id"] = user.get("stripe_customer_id") if user else None
    if plan["kind"] == "one_time":
        # Project Pass : validité en jours (quotas.duration_days) — par défaut 90j
        days = plan.get("quotas", {}).get("duration_days", 90)
        from datetime import timedelta
        doc["expires_at"] = (now + timedelta(days=days)).isoformat()
    await db.entitlements.update_one(
        {"user_id": user_id, "plan_id": plan["plan_id"]},
        {"$set": doc}, upsert=True)
    await db.users.update_one({"user_id": user_id},
                              {"$set": {"active_plan_id": plan["plan_id"],
                                        "active_audience": plan["audience"]}})
    logger.info(f"Entitlement granted: user={user_id} plan={plan['plan_id']}")


async def revoke_entitlement(subscription_id: str, reason: str = "cancelled"):
    await db.entitlements.update_many(
        {"stripe_subscription_id": subscription_id},
        {"$set": {"status": reason, "revoked_at": now_iso()}})


async def handle_webhook(payload: bytes, sig: str) -> dict:
    """Gère les événements Stripe."""
    event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    obj = event["data"]["object"]
    t = event["type"]
    if t == "checkout.session.completed":
        await _mark_paid(obj["id"], obj)
    elif t == "checkout.session.async_payment_succeeded":
        await _mark_paid(obj["id"], obj)
    elif t in ("customer.subscription.deleted", "customer.subscription.paused"):
        await revoke_entitlement(obj["id"], "cancelled")
    elif t == "customer.subscription.updated":
        status = obj.get("status")
        if status in ("canceled", "unpaid", "incomplete_expired"):
            await revoke_entitlement(obj["id"], status)
    elif t == "invoice.payment_failed":
        sub = obj.get("subscription")
        if sub:
            await db.entitlements.update_many(
                {"stripe_subscription_id": sub},
                {"$set": {"status": "past_due", "updated_at": now_iso()}})
    return {"received": True, "type": t}


# ---------- Entitlements resolution ----------

async def user_active_plan(user_id: str) -> dict | None:
    """Retourne le plan actif (subscription non expirée OU project_pass valide)."""
    now = datetime.now(timezone.utc).isoformat()
    ent = await db.entitlements.find_one(
        {"user_id": user_id, "status": "active",
         "$or": [{"expires_at": {"$exists": False}}, {"expires_at": {"$gt": now}}]},
        {"_id": 0},
        sort=[("granted_at", -1)])
    if not ent:
        return None
    plan = await db.plans.find_one({"plan_id": ent["plan_id"]}, {"_id": 0})
    return {"entitlement": ent, "plan": plan}


async def user_has_feature(user_id: str | None, feature: str) -> bool:
    """Est-ce que ce user a accès à `feature` ? Ex: 'unlimited_projects', 'full_price_search'."""
    if not user_id:
        return False
    active = await user_active_plan(user_id)
    if not active or not active.get("plan"):
        return False
    quotas = active["plan"].get("quotas", {})
    # Mapping simple
    mapping = {
        "unlimited_projects": quotas.get("projects") == -1,
        "unlimited_estimations": quotas.get("estimations_monthly") == -1,
        "ai_advisor_full": quotas.get("ai_advisor") == "full",
        "price_search_full": quotas.get("price_search") == "full",
    }
    return bool(mapping.get(feature, True))  # par défaut, les payants ont tout


PARTICULIER_PAID = {"project_pass", "premium_monthly", "premium_yearly"}
PRO_PAID = {"pro_monthly", "pro_yearly", "pro_business_monthly", "pro_business_yearly"}


async def user_tier(user_id: str | None) -> str:
    """Retourne 'free' | 'project_pass' | 'premium' | 'pro' | 'pro_business'."""
    if not user_id:
        return "free"
    active = await user_active_plan(user_id)
    if not active:
        return "free"
    pid = active["entitlement"]["plan_id"]
    if pid == "project_pass":
        return "project_pass"
    if pid.startswith("premium"):
        return "premium"
    if pid.startswith("pro_business"):
        return "pro_business"
    if pid.startswith("pro"):
        return "pro"
    return "free"
