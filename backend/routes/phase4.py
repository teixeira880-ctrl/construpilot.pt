"""Routes Phase 4 : API commerciale + KYC pros + Portail pro + Affiliation."""
from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from core.db import db
from core.security import current_user, optional_user, admin_user
from engines import api_commerciale, affiliate, estimation, calculators, price_search

router = APIRouter(tags=["phase4"])


def _now():
    return datetime.now(timezone.utc)


# =============== 1. API COMMERCIALE (interne : gestion des clés) ===============

class ApiKeyIssueIn(BaseModel):
    plan_id: str
    name: str = "Default"


@router.post("/api-keys")
async def create_api_key(body: ApiKeyIssueIn, user=Depends(current_user)):
    """Un utilisateur avec un entitlement API actif peut créer sa clé."""
    ent = await db.entitlements.find_one(
        {"user_id": user["user_id"], "status": "active", "plan_id": body.plan_id},
        {"_id": 0})
    if not ent and user.get("role") != "admin":
        raise HTTPException(status_code=402, detail="Souscrivez à un plan API avant de créer une clé")
    try:
        doc = await api_commerciale.issue_api_key(user["user_id"], body.plan_id, body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return doc


@router.get("/api-keys")
async def my_api_keys(user=Depends(current_user)):
    return await api_commerciale.list_keys_for(user["user_id"])


@router.post("/api-keys/{prefix}/rotate")
async def rotate_api_key(prefix: str, user=Depends(current_user)):
    return await api_commerciale.rotate_api_key(prefix, user["user_id"])


@router.delete("/api-keys/{prefix}")
async def revoke_api_key(prefix: str, user=Depends(current_user)) -> dict:
    await api_commerciale.revoke_api_key(prefix, user["user_id"])
    return {"ok": True}


# =============== 2. API PUBLIQUE COMMERCIALE (/api/v1/public/*) ===============

class PublicEstimateIn(BaseModel):
    project_type: str
    surface: float
    finish_level: str = "standard"
    country: str = "FR"
    region: str = "Île-de-France"
    building_type: str = "maison"
    condition: str = "bon"


@router.post("/v1/public/estimation")
async def public_estimation(body: PublicEstimateIn, key=Depends(api_commerciale.require_api_key)) -> dict:
    d = body.model_dump()
    est = estimation.estimate(project_type=d["project_type"], surface=d["surface"],
                              finish=d["finish_level"], country=d["country"],
                              region=d["region"], building_type=d["building_type"],
                              condition=d["condition"])
    return {"data": est, "meta": {"plan_id": key["plan_id"]}}


class PublicPriceIn(BaseModel):
    query: str
    limit: int = 10


@router.post("/v1/public/prices")
async def public_prices(body: PublicPriceIn, key=Depends(api_commerciale.require_api_key)) -> dict:
    res = await price_search.search(body.query, body.limit)
    return {"data": res, "meta": {"plan_id": key["plan_id"]}}


class PublicCalcIn(BaseModel):
    kind: str  # paint | tile | drywall | concrete | insulation
    params: dict


@router.post("/v1/public/calculators")
async def public_calc(body: PublicCalcIn, key=Depends(api_commerciale.require_api_key)) -> dict:
    fn_map = {"paint": calculators.paint, "tile": calculators.tile,
              "drywall": calculators.drywall, "concrete": calculators.concrete,
              "insulation": calculators.insulation}
    fn = fn_map.get(body.kind)
    if not fn:
        raise HTTPException(status_code=400, detail="Type de calculateur invalide")
    try:
        result = fn(**body.params)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Paramètres invalides: {e}")
    return {"data": result, "meta": {"plan_id": key["plan_id"]}}


# =============== 3. KYC PROS ===============

class KycSubmitIn(BaseModel):
    siren: str
    company_name: str
    rc_pro_insurer: str | None = None
    rc_pro_number: str | None = None
    decennale_insurer: str | None = None
    decennale_number: str | None = None
    trades: list[str] = []
    zones: list[str] = []
    years_experience: int | None = None
    documents: list[str] = []  # URLs / storage paths


@router.post("/marketplace/kyc")
async def submit_kyc(body: KycSubmitIn, user=Depends(current_user)) -> dict:
    siren = "".join(c for c in body.siren if c.isdigit())
    if len(siren) not in (9, 14):
        raise HTTPException(status_code=400, detail="SIREN/SIRET invalide (9 ou 14 chiffres)")
    doc = body.model_dump()
    doc["siren"] = siren
    doc["user_id"] = user["user_id"]
    doc["email"] = user.get("email")
    doc["status"] = "pending"
    doc["submitted_at"] = _now().isoformat()
    doc["verified"] = False
    doc["badge"] = None
    await db.marketplace_pros.update_one({"user_id": user["user_id"]},
                                         {"$set": doc,
                                          "$setOnInsert": {"credits_cents": 0,
                                                           "created_at": _now().isoformat()}},
                                         upsert=True)
    return {"ok": True, "status": "pending", "message": "Dossier reçu — vérification sous 48h ouvrées."}


@router.get("/marketplace/kyc/me")
async def my_kyc(user=Depends(current_user)):
    doc = await db.marketplace_pros.find_one({"user_id": user["user_id"]},
                                             {"_id": 0, "credits_cents": 1, "status": 1,
                                              "verified": 1, "badge": 1, "siren": 1,
                                              "company_name": 1, "trades": 1, "zones": 1,
                                              "submitted_at": 1, "verified_at": 1})
    return doc or {"status": "none"}


class KycAdminAction(BaseModel):
    user_id: str
    approve: bool
    reason: str | None = None


@router.post("/admin/kyc/review")
async def review_kyc(body: KycAdminAction, admin=Depends(admin_user)) -> dict:
    upd = {"status": "verified" if body.approve else "rejected",
           "verified": body.approve,
           "badge": "ConstruPilot Verified" if body.approve else None,
           "verified_at": _now().isoformat() if body.approve else None,
           "rejected_reason": None if body.approve else body.reason}
    r = await db.marketplace_pros.update_one({"user_id": body.user_id}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    return {"ok": True, "status": upd["status"]}


@router.get("/admin/kyc")
async def list_kyc(status: str | None = None, admin=Depends(admin_user)):
    q = {}
    if status:
        q["status"] = status
    return await db.marketplace_pros.find(q, {"_id": 0}
                                          ).sort("submitted_at", -1).to_list(500)


# =============== 4. PORTAIL PRO (leads, achats crédits) ===============

@router.get("/pro/me")
async def pro_dashboard(user=Depends(current_user)) -> dict:
    pro = await db.marketplace_pros.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not pro:
        return {"registered": False}
    # Leads achetés
    bought = await db.marketplace_leads.find(
        {"sold_to": user["user_id"]}, {"_id": 0}).sort("sold_at", -1).to_list(200)
    return {
        "registered": True,
        "verified": pro.get("verified", False),
        "badge": pro.get("badge"),
        "status": pro.get("status"),
        "credits_cents": pro.get("credits_cents", 0),
        "credits_eur": round(pro.get("credits_cents", 0) / 100, 2),
        "company_name": pro.get("company_name"),
        "trades": pro.get("trades", []),
        "zones": pro.get("zones", []),
        "leads_bought": bought,
        "total_spent_cents": sum(l.get("sold_price_cents", 0) for l in bought),
    }


class RechargeIn(BaseModel):
    amount_cents: int
    origin_url: str


@router.post("/pro/credits/checkout")
async def recharge_credits(body: RechargeIn, user=Depends(current_user)) -> dict:
    """Recharge crédits pros via Stripe (Checkout Session payment mode)."""
    import stripe
    pro = await db.marketplace_pros.find_one({"user_id": user["user_id"], "verified": True},
                                             {"_id": 0})
    if not pro:
        raise HTTPException(status_code=403, detail="Compte pro non vérifié")
    if body.amount_cents < 2000:
        raise HTTPException(status_code=400, detail="Montant minimum : 20 €")
    from engines.monetization import get_or_create_customer
    customer_id = await get_or_create_customer(user)
    # Bonus : +5% si >=250€, +10% si >=500€
    bonus_pct = 0.10 if body.amount_cents >= 50000 else (0.05 if body.amount_cents >= 25000 else 0.0)
    bonus_cents = int(body.amount_cents * bonus_pct)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{
            "price_data": {
                "currency": "eur",
                "product_data": {"name": f"Crédits ConstruPilot Pro {body.amount_cents/100:.0f} €"
                                  + (f" + bonus {bonus_cents/100:.0f} €" if bonus_cents else "")},
                "unit_amount": body.amount_cents,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{body.origin_url}/pro/paiement/succes?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{body.origin_url}/pro",
        metadata={"user_id": user["user_id"], "credit_topup_cents": str(body.amount_cents),
                  "credit_bonus_cents": str(bonus_cents)},
        allow_promotion_codes=True,
    )
    await db.payment_transactions.insert_one({
        "session_id": session.id, "user_id": user["user_id"],
        "plan_id": "pro_credits_topup",
        "amount_cents": body.amount_cents,
        "bonus_cents": bonus_cents,
        "currency": "eur",
        "mode": "payment", "status": "initiated", "payment_status": "pending",
        "type": "pro_credit_topup",
        "created_at": _now().isoformat(), "updated_at": _now().isoformat(),
    })
    return {"url": session.url, "session_id": session.id, "bonus_cents": bonus_cents}


# =============== 5. AFFILIATION ===============

class AffiliateClickIn(BaseModel):
    supplier_key: str
    product_url: str
    query: str = ""


@router.post("/affiliate/click")
async def affiliate_click(body: AffiliateClickIn, user=Depends(optional_user)) -> dict:
    click_id = await affiliate.record_click(
        user["user_id"] if user else None, body.supplier_key, body.product_url, body.query)
    return {"ok": True, "click_id": click_id}


@router.get("/r/aff/{supplier_key}")
async def affiliate_redirect(supplier_key: str, url: str, request: Request):
    """Redirection tracké : /api/r/aff/leroymerlin?url=https%3A%2F%2F..."""
    conf = await affiliate.config_map()
    cfg = conf.get(supplier_key)
    if not cfg:
        return RedirectResponse(url=url, status_code=302)
    await affiliate.record_redirect(None, supplier_key, url)
    if cfg.get("affiliate_enabled") and cfg.get("tracking_template"):
        target = cfg["tracking_template"].replace("{url}", quote_plus(url))
    else:
        target = url
    return RedirectResponse(url=target, status_code=302)


@router.get("/admin/affiliate/configs")
async def list_affiliate_configs(admin=Depends(admin_user)):
    return await affiliate.all_configs()


class AffiliateConfigIn(BaseModel):
    supplier_key: str
    affiliate_enabled: bool = True
    affiliate_network: str | None = None
    affiliate_id: str | None = None
    commission_rate: float = 0.03
    cookie_duration: int = 30
    tracking_template: str | None = None


@router.post("/admin/affiliate/configs")
async def upsert_affiliate_config(body: AffiliateConfigIn, admin=Depends(admin_user)) -> dict:
    await affiliate.upsert_config(body.model_dump())
    return {"ok": True}


@router.get("/admin/affiliate/stats")
async def affiliate_stats(days: int = 30, admin=Depends(admin_user)):
    return await affiliate.stats(days)
