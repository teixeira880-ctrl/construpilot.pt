"""Referral program : parrainage 5€/5€.

- Chaque user reçoit un `referral_code` unique à la première demande.
- Un filleul entre le code au signup ou avant un checkout → il obtient une remise
  (via un promotion_code Stripe généré à la volée).
- Après le premier paiement du filleul, le parrain reçoit 5 € de crédit.
"""
import os
import secrets
import string
from datetime import datetime, timezone

import stripe

from core.db import db

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")

REFEREE_DISCOUNT_CENTS = 500  # 5€ pour le filleul
REFERRER_CREDIT_CENTS = 500   # 5€ pour le parrain


def _generate_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "CP-" + "".join(secrets.choice(alphabet) for _ in range(6))


async def get_or_create_code(user: dict) -> str:
    existing = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "referral_code": 1})
    code = (existing or {}).get("referral_code")
    if code:
        return code
    # unicité
    for _ in range(8):
        candidate = _generate_code()
        if not await db.users.find_one({"referral_code": candidate}, {"_id": 1}):
            code = candidate
            break
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"referral_code": code}})
    return code


async def stats(user_id: str) -> dict:
    doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "referral_code": 1,
                                                          "referral_credit_cents": 1}) or {}
    referrals = await db.referrals.find({"referrer_id": user_id}, {"_id": 0}).to_list(500)
    return {
        "code": doc.get("referral_code"),
        "credit_cents": doc.get("referral_credit_cents", 0),
        "credit_eur": round((doc.get("referral_credit_cents", 0)) / 100, 2),
        "invited": len(referrals),
        "converted": sum(1 for r in referrals if r.get("status") == "converted"),
        "pending": sum(1 for r in referrals if r.get("status") == "pending"),
    }


async def apply_code_at_signup(new_user_id: str, code: str) -> bool:
    if not code:
        return False
    parrain = await db.users.find_one({"referral_code": code.strip().upper()}, {"_id": 0})
    if not parrain or parrain["user_id"] == new_user_id:
        return False
    await db.referrals.insert_one({
        "referrer_id": parrain["user_id"], "referee_id": new_user_id,
        "code": code.strip().upper(),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return True


async def generate_referee_coupon(user_id: str) -> str | None:
    """Génère un promotion_code Stripe 5€ pour un filleul (usage unique)."""
    ref = await db.referrals.find_one({"referee_id": user_id, "status": "pending"}, {"_id": 0})
    if not ref:
        return None
    if ref.get("stripe_promotion_code_id"):
        promo = stripe.PromotionCode.retrieve(ref["stripe_promotion_code_id"])
        return promo.code
    coupon = stripe.Coupon.create(
        amount_off=REFEREE_DISCOUNT_CENTS, currency="eur",
        duration="once", max_redemptions=1,
        name="Bem-vindo ao ConstruPilot (referência)",
        metadata={"referee_id": user_id, "referrer_id": ref["referrer_id"]})
    code_str = f'BEMVINDO-{secrets.token_hex(3).upper()}'
    promo = stripe.PromotionCode.create(
        promotion={"type": "coupon", "coupon": coupon.id},
        code=code_str, active=True, max_redemptions=1,
        metadata={"referee_id": user_id})
    await db.referrals.update_one({"referrer_id": ref["referrer_id"], "referee_id": user_id},
                                  {"$set": {"stripe_coupon_id": coupon.id,
                                            "stripe_promotion_code_id": promo.id,
                                            "referee_code": code_str}})
    return code_str


async def credit_referrer_on_first_payment(referee_id: str) -> None:
    """Appelé depuis le webhook checkout.session.completed."""
    ref = await db.referrals.find_one({"referee_id": referee_id, "status": "pending"}, {"_id": 0})
    if not ref:
        return
    await db.referrals.update_one({"referrer_id": ref["referrer_id"], "referee_id": referee_id},
                                  {"$set": {"status": "converted",
                                            "converted_at": datetime.now(timezone.utc).isoformat()}})
    await db.users.update_one({"user_id": ref["referrer_id"]},
                              {"$inc": {"referral_credit_cents": REFERRER_CREDIT_CENTS}})
