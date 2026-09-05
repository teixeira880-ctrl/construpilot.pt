"""Routes Savings Engine + Referral + Marketplace + Promo Codes."""
import os
import logging
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import current_user, optional_user, admin_user
from engines import savings, referral, lead_scoring

logger = logging.getLogger(__name__)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY")

router = APIRouter(tags=["revenue"])


# ============ SAVINGS ============

class SavingsIn(BaseModel):
    estimation: dict


@router.post("/savings/analyse")
async def analyse_savings(body: SavingsIn):
    if not body.estimation or not body.estimation.get("lots"):
        raise HTTPException(status_code=400, detail="Estimation requise")
    return savings.compute(body.estimation)


@router.get("/projects/{project_id}/savings")
async def project_savings(project_id: str, user=Depends(current_user)):
    p = await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]},
                                   {"_id": 0, "estimation": 1})
    if not p:
        raise HTTPException(status_code=404, detail="Projet introuvable")
    return savings.compute(p["estimation"])


# ============ REFERRAL ============

@router.get("/referral/me")
async def my_referral(user=Depends(current_user)) -> dict:
    code = await referral.get_or_create_code(user)
    stats = await referral.stats(user["user_id"])
    return {"code": code, "share_url": f"?ref={code}", **stats}


class ReferralApplyIn(BaseModel):
    code: str


@router.post("/referral/apply")
async def apply_referral(body: ReferralApplyIn, user=Depends(current_user)) -> dict:
    ok = await referral.apply_code_at_signup(user["user_id"], body.code)
    if not ok:
        raise HTTPException(status_code=400, detail="Code invalide ou inutilisable")
    promo = await referral.generate_referee_coupon(user["user_id"])
    return {"ok": True, "referee_code": promo}


# ============ MARKETPLACE ============

class ProfessionalIn(BaseModel):
    company_name: str
    siren: str | None = None
    trades: list[str] = []
    zones: list[str] = []
    phone: str | None = None
    email: str
    website: str | None = None
    description: str | None = None


async def _flags():
    return await db.feature_flags.find_one({"_id": "global"}, {"_id": 0}) or {}


@router.post("/marketplace/register")
async def register_pro(body: ProfessionalIn, user=Depends(current_user)) -> dict:
    flags = await _flags()
    if not flags.get("marketplace_enabled"):
        raise HTTPException(status_code=403, detail="Marketplace bientôt disponible")
    doc = body.model_dump()
    doc.update({"user_id": user["user_id"], "verified": False, "badge": None,
                "credits_cents": 0,
                "created_at": datetime.now(timezone.utc).isoformat()})
    await db.marketplace_pros.update_one({"user_id": user["user_id"]},
                                         {"$set": doc}, upsert=True)
    return {"ok": True, "verified": False,
            "message": "Inscription reçue — vérification sous 48h."}


@router.get("/marketplace/pros")
async def list_pros(zone: str | None = None, trade: str | None = None) -> dict:
    q = {"verified": True}
    if zone:
        q["zones"] = zone
    if trade:
        q["trades"] = trade
    pros = await db.marketplace_pros.find(q, {"_id": 0, "email": 0, "phone": 0, "credits_cents": 0}
                                          ).to_list(200)
    return {"pros": pros, "count": len(pros)}


class LeadCreateIn(BaseModel):
    name: str
    email: str
    phone: str | None = None
    address: str | None = None
    budget: float | None = None
    surface: float | None = None
    delay_days: int | None = None
    description: str
    trade: str | None = None
    project_id: str | None = None
    photos_count: int = 0


@router.post("/marketplace/leads")
async def submit_lead(body: LeadCreateIn, user=Depends(optional_user)):
    """Génère un lead scoré, prêt à être vendu aux pros vérifiés."""
    lead_dict = body.model_dump()
    scoring = lead_scoring.score(lead_dict)
    lead_id = f"ld_{int(datetime.now(timezone.utc).timestamp()*1000)}"
    doc = {
        "lead_id": lead_id,
        "user_id": user["user_id"] if user else None,
        **lead_dict,
        "score": scoring["score"], "rating": scoring["rating"],
        "tier": scoring["tier"], "scoring_detail": scoring["detail"],
        "price_cents": lead_scoring.lead_price_cents(scoring["tier"]),
        "status": "new",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.marketplace_leads.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/marketplace/leads")
async def list_available_leads(user=Depends(current_user)) -> dict:
    """Un pro voit les leads correspondant à ses trades/zones."""
    pro = await db.marketplace_pros.find_one({"user_id": user["user_id"], "verified": True},
                                             {"_id": 0})
    if not pro:
        raise HTTPException(status_code=403, detail="Réservé aux professionnels vérifiés")
    q = {"status": "new"}
    leads = await db.marketplace_leads.find(q, {"_id": 0, "email": 0, "phone": 0}
                                            ).sort("created_at", -1).to_list(50)
    return {"leads": leads, "pro_credits_cents": pro.get("credits_cents", 0)}


class BuyLeadIn(BaseModel):
    lead_id: str


@router.post("/marketplace/leads/buy")
async def buy_lead(body: BuyLeadIn, user=Depends(current_user)) -> dict:
    pro = await db.marketplace_pros.find_one({"user_id": user["user_id"], "verified": True},
                                             {"_id": 0})
    if not pro:
        raise HTTPException(status_code=403, detail="Réservé aux professionnels vérifiés")
    lead = await db.marketplace_leads.find_one({"lead_id": body.lead_id}, {"_id": 0})
    if not lead or lead.get("status") != "new":
        raise HTTPException(status_code=404, detail="Lead indisponible")
    price = lead["price_cents"]
    if pro.get("credits_cents", 0) < price:
        raise HTTPException(status_code=402, detail="Crédits insuffisants")
    await db.marketplace_pros.update_one({"user_id": user["user_id"]},
                                         {"$inc": {"credits_cents": -price}})
    await db.marketplace_leads.update_one(
        {"lead_id": body.lead_id, "status": "new"},
        {"$set": {"status": "sold", "sold_to": user["user_id"],
                  "sold_at": datetime.now(timezone.utc).isoformat(),
                  "sold_price_cents": price}})
    lead["status"] = "sold"
    return {"ok": True, "lead": lead, "credits_remaining_cents": pro["credits_cents"] - price}


# ============ PROMO CODES (admin only) ============

class PromoIn(BaseModel):
    code: str
    percent_off: int | None = None
    amount_off_cents: int | None = None
    currency: str = "eur"
    duration: str = "once"  # once | forever | repeating
    duration_in_months: int | None = None
    max_redemptions: int | None = None
    expires_at: str | None = None  # ISO
    active: bool = True
    name: str | None = None


@router.post("/admin/promo-codes")
async def create_promo(body: PromoIn, user=Depends(admin_user)):
    if not body.percent_off and not body.amount_off_cents:
        raise HTTPException(status_code=400, detail="percent_off ou amount_off_cents requis")
    coupon_kwargs = {"duration": body.duration, "name": body.name or body.code}
    if body.percent_off:
        coupon_kwargs["percent_off"] = body.percent_off
    if body.amount_off_cents:
        coupon_kwargs["amount_off"] = body.amount_off_cents
        coupon_kwargs["currency"] = body.currency
    if body.max_redemptions:
        coupon_kwargs["max_redemptions"] = body.max_redemptions
    if body.duration == "repeating" and body.duration_in_months:
        coupon_kwargs["duration_in_months"] = body.duration_in_months
    coupon = stripe.Coupon.create(**coupon_kwargs)
    promo_kwargs = {"promotion": {"type": "coupon", "coupon": coupon.id},
                    "code": body.code.upper(),
                    "active": body.active}
    if body.max_redemptions:
        promo_kwargs["max_redemptions"] = body.max_redemptions
    if body.expires_at:
        try:
            dt = datetime.fromisoformat(body.expires_at.replace("Z", "+00:00"))
            promo_kwargs["expires_at"] = int(dt.timestamp())
        except Exception:
            pass
    promo = stripe.PromotionCode.create(**promo_kwargs)
    doc = {"code": promo.code, "stripe_coupon_id": coupon.id,
           "stripe_promotion_code_id": promo.id,
           "percent_off": body.percent_off, "amount_off_cents": body.amount_off_cents,
           "currency": body.currency, "max_redemptions": body.max_redemptions,
           "expires_at": body.expires_at, "active": body.active, "name": body.name,
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.promo_codes.update_one({"code": promo.code}, {"$set": doc}, upsert=True)
    return doc


@router.get("/admin/promo-codes")
async def list_promo(user=Depends(admin_user)):
    return await db.promo_codes.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)


@router.patch("/admin/promo-codes/{code}")
async def toggle_promo(code: str, active: bool, user=Depends(admin_user)) -> dict:
    doc = await db.promo_codes.find_one({"code": code.upper()}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Code inconnu")
    stripe.PromotionCode.modify(doc["stripe_promotion_code_id"], active=active)
    await db.promo_codes.update_one({"code": code.upper()}, {"$set": {"active": active}})
    return {"code": code.upper(), "active": active}
