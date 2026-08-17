"""Stripe integration + entitlement helpers pour ConstruPilot Revenue Engine.

- Setup catalog idempotent (Products + Prices via lookup_key)
- Checkout Session (subscription + one-time)
- Webhook handler (dispatch table)
- Entitlement resolution : quel plan l'utilisateur possède ?

Refactor iter53 : `ensure_stripe_catalog` et `create_checkout` explosées en
helpers privés pour ramener la complexité cyclomatique < 10 et éliminer les
nesting depth > 2.
"""
import os
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import stripe

from core.db import db

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

PARTICULIER_PAID = {"project_pass", "premium_monthly", "premium_yearly"}
PRO_PAID = {"pro_monthly", "pro_yearly", "pro_business_monthly", "pro_business_yearly"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- Stripe catalog sync (idempotent) ----------

def _index_existing_products() -> dict:
    """Return {plan_id: Product} using Stripe metadata; one API round-trip."""
    products = {}
    for prod in stripe.Product.list(limit=100).auto_paging_iter():
        pid = (prod.get("metadata") or {}).get("plan_id")
        if pid:
            products[pid] = prod
    return products


def _upsert_product(plan: dict, existing: dict):
    """Get existing Stripe Product for plan or create a new one."""
    prod = existing.get(plan["plan_id"])
    if prod:
        return prod
    prod = stripe.Product.create(
        name=f"ConstruPilot {plan['name']}",
        metadata={"managed_by": "construpilot", "plan_id": plan["plan_id"]},
        tax_code="txcd_10103001",
    )
    existing[plan["plan_id"]] = prod
    return prod


def _price_matches(price, plan: dict) -> bool:
    return (price.unit_amount == plan["amount_cents"]
            and price.currency == plan["currency"])


def _upsert_price(plan: dict, prod):
    """Ensure the Price for `plan` exists & is active with correct amount."""
    lookup = plan["lookup_key"]
    prices = stripe.Price.list(lookup_keys=[lookup], active=True, limit=1).data
    price = prices[0] if prices else None
    if price and not _price_matches(price, plan):
        stripe.Price.modify(price.id, active=False)
        price = None
    if price:
        return price
    kwargs = {
        "product": prod.id,
        "unit_amount": plan["amount_cents"],
        "currency": plan["currency"],
        "lookup_key": lookup,
        "transfer_lookup_key": True,
        "metadata": {"plan_id": plan["plan_id"]},
    }
    if plan.get("interval"):
        kwargs["recurring"] = {"interval": plan["interval"]}
    return stripe.Price.create(**kwargs)


async def _persist_stripe_ids(plan: dict, prod, price) -> None:
    await db.plans.update_one(
        {"plan_id": plan["plan_id"]},
        {"$set": {"stripe_product_id": prod.id,
                  "stripe_price_id": price.id,
                  "synced_at": now_iso()}},
    )


async def ensure_stripe_catalog() -> None:
    """Crée/synchronise les Products et Prices Stripe à partir des plans DB."""
    if not stripe.api_key:
        logger.warning("STRIPE_SECRET_KEY manquant — Stripe désactivé")
        return

    plans = await db.plans.find(
        {"active": True, "kind": {"$in": ["subscription", "one_time"]}},
        {"_id": 0},
    ).to_list(50)
    existing = _index_existing_products()

    for plan in plans:
        if not plan.get("lookup_key"):
            continue
        prod = _upsert_product(plan, existing)
        price = _upsert_price(plan, prod)
        await _persist_stripe_ids(plan, prod, price)
    logger.info(f"Stripe catalog synced ({len(plans)} plans)")


# ---------- Customer & Checkout ----------

async def get_or_create_customer(user: dict) -> str:
    if user.get("stripe_customer_id"):
        return user["stripe_customer_id"]
    cust = stripe.Customer.create(
        email=user["email"], name=user.get("name"),
        metadata={"user_id": user["user_id"]})
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"stripe_customer_id": cust.id}})
    return cust.id


async def _resolve_price(lookup: str):
    """Fetch active Price for `lookup`; sync catalog once on cache miss."""
    prices = stripe.Price.list(lookup_keys=[lookup], active=True, limit=1).data
    if prices:
        return prices[0]
    await ensure_stripe_catalog()
    prices = stripe.Price.list(lookup_keys=[lookup], active=True, limit=1).data
    if not prices:
        raise RuntimeError(f"Prix Stripe introuvable pour {lookup}")
    return prices[0]


def _plan_is_pro_tier(plan: dict) -> bool:
    return plan.get("audience") == "pro" or plan["plan_id"].startswith("pro")


async def _compute_trial_days(user: dict, plan: dict, is_sub: bool) -> tuple[int, int]:
    """Return (total_trial_days, bonus_days_consumed)."""
    if not is_sub:
        return 0, 0
    flags = await db.feature_flags.find_one({"_id": "global"}, {"_id": 0}) or {}
    base_days = plan.get("trial_days") or flags.get("trial_days") or 0
    base = base_days if flags.get("trial_enabled", True) else 0
    bonus = 0
    user_bonus = int(user.get("referral_bonus_days", 0) or 0)
    if user_bonus > 0 and _plan_is_pro_tier(plan):
        bonus = user_bonus
    return base + bonus, bonus


def _resolve_promo_discount(promo_code: str | None) -> list | None:
    """Return Stripe `discounts` payload for a human-friendly code, or None."""
    if not promo_code:
        return None
    promos = stripe.PromotionCode.list(code=promo_code, active=True, limit=1).data
    if not promos:
        return None
    return [{"promotion_code": promos[0].id}]


@dataclass
class CheckoutContext:
    """Contexte d'une session Checkout (évite une signature à 9 paramètres)."""
    user: dict
    plan: dict
    price: object
    customer_id: str
    origin_url: str
    is_sub: bool
    total_trial_days: int = 0
    bonus_days_consumed: int = 0
    promo_discount: list | None = None


def _build_checkout_kwargs(ctx: CheckoutContext) -> dict:
    kwargs = {
        "customer": ctx.customer_id,
        "line_items": [{"price": ctx.price.id, "quantity": 1}],
        "mode": "subscription" if ctx.is_sub else "payment",
        "success_url": f"{ctx.origin_url}/paiement/succes?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{ctx.origin_url}/paiement/annule",
        "metadata": {"user_id": ctx.user["user_id"], "plan_id": ctx.plan["plan_id"],
                     "lookup_key": ctx.plan["lookup_key"]},
        "allow_promotion_codes": True,
    }
    if ctx.is_sub and ctx.total_trial_days > 0:
        kwargs["subscription_data"] = {
            "trial_period_days": ctx.total_trial_days,
            "metadata": {"user_id": ctx.user["user_id"],
                         "plan_id": ctx.plan["plan_id"],
                         "bonus_days_consumed": str(ctx.bonus_days_consumed)},
        }
    if ctx.promo_discount is not None:
        kwargs.pop("allow_promotion_codes", None)
        kwargs["discounts"] = ctx.promo_discount
    return kwargs


async def _record_payment_transaction(session, price, plan: dict, user: dict,
                                       mode: str, bonus_days_consumed: int) -> None:
    await db.payment_transactions.insert_one({
        "session_id": session.id, "user_id": user["user_id"],
        "plan_id": plan["plan_id"], "lookup_key": plan["lookup_key"],
        "amount_cents": price.unit_amount, "currency": price.currency,
        "mode": mode, "status": "initiated", "payment_status": "pending",
        "bonus_days_consumed": bonus_days_consumed,
        "created_at": now_iso(), "updated_at": now_iso(),
    })


async def create_checkout(user: dict, plan: dict, origin_url: str,
                          promo_code: str | None = None) -> dict:
    """Crée une Checkout Session Stripe pour le plan donné.

    Refactor iter53 : orchestration only — logique déléguée à des helpers.
    """
    if not stripe.api_key:
        raise RuntimeError("Stripe non configuré")
    if not plan.get("lookup_key"):
        raise ValueError(f"Plan {plan.get('plan_id')} sans lookup_key")

    price = await _resolve_price(plan["lookup_key"])
    customer_id = await get_or_create_customer(user)
    is_sub = plan["kind"] == "subscription"
    total_trial_days, bonus_days_consumed = await _compute_trial_days(user, plan, is_sub)
    promo_discount = _resolve_promo_discount(promo_code)

    kwargs = _build_checkout_kwargs(CheckoutContext(
        user=user, plan=plan, price=price, customer_id=customer_id,
        origin_url=origin_url, is_sub=is_sub,
        total_trial_days=total_trial_days,
        bonus_days_consumed=bonus_days_consumed,
        promo_discount=promo_discount,
    ))
    session = stripe.checkout.Session.create(**kwargs)
    await _record_payment_transaction(session, price, plan, user,
                                       kwargs["mode"], bonus_days_consumed)
    return {"url": session.url, "session_id": session.id,
            "bonus_days_applied": bonus_days_consumed}


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


async def _consume_referral_bonus(user_id: str, consumed: int) -> None:
    if consumed <= 0:
        return
    await db.users.update_one(
        {"user_id": user_id, "referral_bonus_days": {"$gte": consumed}},
        {"$inc": {"referral_bonus_days": -consumed},
         "$set": {"referral_bonus_last_consumed_at": now_iso()}},
    )
    logger.info(f"Referral bonus consumed: user={user_id} days=-{consumed}")


async def _credit_referrer_safe(user_id: str) -> None:
    """Fire-and-forget referral credit — never propagate errors upstream."""
    try:
        from engines import referral
        await referral.credit_referrer_on_first_payment(user_id)
    except Exception as e:
        logger.warning(f"Referral credit failed: {e}")


async def _apply_pro_credit_topup(rec: dict) -> None:
    total = rec.get("amount_cents", 0) + rec.get("bonus_cents", 0)
    await db.marketplace_pros.update_one(
        {"user_id": rec["user_id"]},
        {"$inc": {"credits_cents": total}},
    )
    logger.info(f"Pro credits +{total} cents pour {rec['user_id']}")


async def _mark_paid(session_id: str, s) -> None:
    upd = await db.payment_transactions.update_one(
        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
        {"$set": {"status": "completed", "payment_status": "paid",
                  "stripe_subscription_id": s.get("subscription"),
                  "stripe_payment_intent_id": s.get("payment_intent"),
                  "updated_at": now_iso()}})
    if upd.modified_count == 0:
        return
    rec = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})

    if rec.get("type") == "pc_deposit":
        from routes.plans_pc import _apply_pc_deposit
        await _apply_pc_deposit(rec)
        return

    if rec.get("type") == "pc_situation":
        from routes.plans_pc import _apply_pc_situation
        await _apply_pc_situation(rec)
        return

    if rec.get("type") == "pro_credit_topup":
        await _apply_pro_credit_topup(rec)
        return

    plan = await db.plans.find_one({"plan_id": rec["plan_id"]}, {"_id": 0})
    if not plan:
        return
    credit_kind = (plan.get("quotas") or {}).get("credit_kind")
    if credit_kind:
        qty = int((plan.get("quotas") or {}).get("credit_qty", 1) or 1)
        await db.users.update_one(
            {"user_id": rec["user_id"]},
            {"$inc": {f"credits_3d.{credit_kind}": qty}})
        logger.info(f"3D credit +{qty} {credit_kind} pour {rec['user_id']}")
        return
    if (plan.get("quotas") or {}).get("addon") == "invoicing":
        await db.users.update_one(
            {"user_id": rec["user_id"]},
            {"$set": {"invoicing_addon": True,
                      "invoicing_addon_sub": rec.get("stripe_subscription_id")}})
        logger.info(f"Option Facturation activée pour {rec['user_id']}")
        return
    await grant_entitlement(rec["user_id"], plan, rec)
    await _consume_referral_bonus(rec["user_id"],
                                   int(rec.get("bonus_days_consumed", 0) or 0))
    await _credit_referrer_safe(rec["user_id"])


async def grant_entitlement(user_id: str, plan: dict, payment_rec: dict) -> None:
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
        days = plan.get("quotas", {}).get("duration_days", 90)
        doc["expires_at"] = (now + timedelta(days=days)).isoformat()
    await db.entitlements.update_one(
        {"user_id": user_id, "plan_id": plan["plan_id"]},
        {"$set": doc}, upsert=True)
    await db.users.update_one({"user_id": user_id},
                              {"$set": {"active_plan_id": plan["plan_id"],
                                        "active_audience": plan["audience"]}})
    logger.info(f"Entitlement granted: user={user_id} plan={plan['plan_id']}")


async def revoke_entitlement(subscription_id: str, reason: str = "cancelled") -> None:
    await db.entitlements.update_many(
        {"stripe_subscription_id": subscription_id},
        {"$set": {"status": reason, "revoked_at": now_iso()}})


# ---------- Webhook dispatch (nesting depth 1 in `handle_webhook`) ----------

async def _webhook_mark_paid(obj: dict) -> None:
    await _mark_paid(obj["id"], obj)


async def _webhook_subscription_ended(obj: dict) -> None:
    await revoke_entitlement(obj["id"], "cancelled")


async def _webhook_subscription_updated(obj: dict) -> None:
    status = obj.get("status")
    if status in ("canceled", "unpaid", "incomplete_expired"):
        await revoke_entitlement(obj["id"], status)


async def _webhook_invoice_failed(obj: dict) -> None:
    sub = obj.get("subscription")
    if not sub:
        return
    await db.entitlements.update_many(
        {"stripe_subscription_id": sub},
        {"$set": {"status": "past_due", "updated_at": now_iso()}})


_WEBHOOK_HANDLERS = {
    "checkout.session.completed": _webhook_mark_paid,
    "checkout.session.async_payment_succeeded": _webhook_mark_paid,
    "customer.subscription.deleted": _webhook_subscription_ended,
    "customer.subscription.paused": _webhook_subscription_ended,
    "customer.subscription.updated": _webhook_subscription_updated,
    "invoice.payment_failed": _webhook_invoice_failed,
}


async def handle_webhook(payload: bytes, sig: str) -> dict:
    """Gère les événements Stripe via dispatch table."""
    event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    event_type = event["type"]
    handler = _WEBHOOK_HANDLERS.get(event_type)
    if handler:
        await handler(event["data"]["object"])
    return {"received": True, "type": event_type}


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
    mapping = {
        "unlimited_projects": quotas.get("projects") == -1,
        "unlimited_estimations": quotas.get("estimations_monthly") == -1,
        "ai_advisor_full": quotas.get("ai_advisor") == "full",
        "price_search_full": quotas.get("price_search") == "full",
    }
    return bool(mapping.get(feature, True))


async def user_tier(user_id: str | None) -> str:
    """Retourne 'free' | 'project_pass' | 'premium' | 'pro' | 'pro_business'."""
    if os.environ.get("FREE_PROMO_MODE") == "true" and user_id:
        return "pro_business"  # Phase de lancement gratuite : tout débloqué
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


async def require_pro_business(user: dict) -> None:
    """Guarantee the user has a Pro Business subscription — otherwise raise 402."""
    from fastapi import HTTPException
    if (user or {}).get("role") == "admin":
        return
    tier = await user_tier(user.get("user_id"))
    if tier != "pro_business":
        raise HTTPException(
            402,
            "Cette fonctionnalité (Plan 2D takeoff + rendu 3D) est réservée au plan "
            "Pro Business. Passez sur le plan Pro Business pour débloquer.",
        )



# ---------- Crédits 3D à l'unité (rendu / vidéo / maquette) ----------

CREDIT_KINDS = ("render", "video", "mockup")
CREDIT_UNIT_CENTS = {"render": 500, "video": 1000, "mockup": 500}
CREDIT_PLAN_ID = {"render": "render_credit_3d", "video": "video_credit_3d",
                  "mockup": "mockup_credit_3d"}
FREE_RENDERS_PROJECT_PASS = 3


async def resolve_3d_access(user: dict, kind: str) -> dict:
    """Détermine comment l'utilisateur peut réaliser une action 3D (render/video/mockup).

    Retourne {"mode": "unlimited"|"free"|"credit"|"denied", ...}.
    - admin / pro / pro_business  → unlimited
    - project_pass (render only)  → free tant que free_used < 3
    - sinon                       → credit si crédits > 0, sinon denied
    """
    if (user or {}).get("role") == "admin":
        return {"mode": "unlimited"}
    uid = user.get("user_id")
    tier = await user_tier(uid)
    if tier in ("pro", "pro_business"):
        return {"mode": "unlimited"}
    full = await db.users.find_one(
        {"user_id": uid}, {"_id": 0, "render3d_free_used": 1, "credits_3d": 1}) or {}
    free_used = int(full.get("render3d_free_used", 0) or 0)
    credits = full.get("credits_3d") or {}
    cred = int(credits.get(kind, 0) or 0)
    if kind == "render" and tier == "project_pass":
        free_remaining = max(0, FREE_RENDERS_PROJECT_PASS - free_used)
        if free_remaining > 0:
            return {"mode": "free", "free_remaining": free_remaining, "credits": cred}
    if cred > 0:
        return {"mode": "credit", "credits": cred}
    return {"mode": "denied", "kind": kind,
            "price_cents": CREDIT_UNIT_CENTS.get(kind, 0),
            "credit_plan_id": CREDIT_PLAN_ID.get(kind)}


async def require_3d_access(user: dict, kind: str) -> str:
    """Vérifie l'accès à une action 3D. Lève 402 (detail structuré) si refusé.
    Retourne le mode ('unlimited'|'free'|'credit') à consommer après succès."""
    from fastapi import HTTPException
    acc = await resolve_3d_access(user, kind)
    if acc["mode"] == "denied":
        labels = {"render": "un rendu 3D", "video": "une vidéo 3D",
                  "mockup": "la maquette 3D interactive"}
        price = acc["price_cents"] / 100
        raise HTTPException(402, detail={
            "error": "credit_required", "kind": kind,
            "price_cents": acc["price_cents"], "price_eur": price,
            "credit_plan_id": acc["credit_plan_id"],
            "message": f"Pour générer {labels.get(kind, 'cette création 3D')}, "
                       f"achetez un crédit ({price:.0f} €).",
        })
    return acc["mode"]


async def consume_3d(user_id: str, kind: str, mode: str) -> None:
    """Consomme une unité après une génération réussie (rien si unlimited)."""
    if mode == "free":
        await db.users.update_one({"user_id": user_id},
                                  {"$inc": {"render3d_free_used": 1}})
    elif mode == "credit":
        await db.users.update_one(
            {"user_id": user_id, f"credits_3d.{kind}": {"$gte": 1}},
            {"$inc": {f"credits_3d.{kind}": -1}})


async def credits_3d_summary(user: dict) -> dict:
    """Résumé des droits 3D pour le compteur frontend."""
    prices = dict(CREDIT_UNIT_CENTS)
    plans = dict(CREDIT_PLAN_ID)
    if (user or {}).get("role") == "admin":
        return {"unlimited": True, "tier": "admin", "free_render_remaining": None,
                "credits": {k: 0 for k in CREDIT_KINDS},
                "prices_cents": prices, "credit_plans": plans}
    uid = user.get("user_id")
    tier = await user_tier(uid)
    unlimited = tier in ("pro", "pro_business")
    full = await db.users.find_one(
        {"user_id": uid}, {"_id": 0, "render3d_free_used": 1, "credits_3d": 1}) or {}
    free_used = int(full.get("render3d_free_used", 0) or 0)
    free_remaining = (max(0, FREE_RENDERS_PROJECT_PASS - free_used)
                      if tier == "project_pass" else 0)
    credits = full.get("credits_3d") or {}
    return {"unlimited": unlimited, "tier": tier,
            "free_render_remaining": free_remaining,
            "credits": {k: int(credits.get(k, 0) or 0) for k in CREDIT_KINDS},
            "prices_cents": prices, "credit_plans": plans}
