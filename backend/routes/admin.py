from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.db import db
from core.security import admin_user
from engines.catalog import LOTS, REGIONS
from engines import price_search

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/inbox")
async def admin_inbox(hours: int = 168) -> dict:
    """Boîte de réception admin — vue consolidée des demandes et incidents récents.

    Renvoie leads récents + nouveaux users + devis envoyés + erreurs client
    pour permettre à l'équipe de tout suivre depuis une seule page.
    """
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    since_iso = since.isoformat()

    # Leads (contact form / lead gen)
    leads_cur = db.leads.find({"created_at": {"$gte": since_iso}},
                                {"_id": 0}).sort("created_at", -1).limit(50)
    leads = await leads_cur.to_list(50)

    # Nouveaux utilisateurs (>= depuis N heures)
    users_cur = db.users.find({"created_at": {"$gte": since_iso}},
                                {"_id": 0, "user_id": 1, "email": 1, "name": 1,
                                 "role": 1, "plan": 1, "created_at": 1}
                                ).sort("created_at", -1).limit(50)
    new_users = await users_cur.to_list(50)

    # Devis envoyés (activité pros)
    sends_cur = db.quote_sends.find({"sent_at": {"$gte": since_iso}},
                                     {"_id": 0, "log_id": 1, "user_id": 1,
                                      "client_email": 1, "client_name": 1,
                                      "total_ttc": 1, "sent_at": 1,
                                      "signed": 1, "opened_at": 1}
                                     ).sort("sent_at", -1).limit(50)
    sends = await sends_cur.to_list(50)

    # Erreurs client
    errs_cur = db.client_errors.find({"created_at": {"$gte": since}},
                                       {"_id": 0}).sort("created_at", -1).limit(30)
    errs = await errs_cur.to_list(30)

    # Devis signés dans la fenêtre (à célébrer)
    signed_count = sum(1 for s in sends if s.get("signed"))
    open_count = sum(1 for s in sends if s.get("opened_at") and not s.get("signed"))

    return {
        "hours": hours,
        "counts": {
            "new_leads": len(leads),
            "new_users": len(new_users),
            "quotes_sent": len(sends),
            "quotes_signed": signed_count,
            "quotes_opened": open_count,
            "client_errors": len(errs),
        },
        "leads": leads,
        "new_users": new_users,
        "recent_sends": sends,
        "recent_errors": [
            {"created_at": (e.get("created_at").isoformat()
                             if hasattr(e.get("created_at"), "isoformat")
                             else e.get("created_at_iso")),
             "message": e.get("message"), "url": e.get("url"),
             "user_id": e.get("user_id")}
            for e in errs
        ],
    }


@router.get("/stats")
async def stats() -> dict:
    users = await db.users.count_documents({})
    projects = await db.projects.count_documents({})
    leads = await db.leads.count_documents({})
    quotes = await db.quote_analyses.count_documents({})
    top = await db.search_stats.find({}, {"_id": 0}).sort("count", -1).to_list(10)
    plans = await db.users.aggregate([{"$group": {"_id": "$plan", "count": {"$sum": 1}}}]).to_list(10)
    agg = await db.projects.aggregate([
        {"$group": {"_id": None,
                    "volume": {"$sum": {"$ifNull": ["$estimation.total_avg", 0]}}}},
    ]).to_list(1)
    volume = round((agg[0]["volume"] if agg else 0) or 0, 2)
    return {"users": users, "projects": projects, "leads": leads, "quote_analyses": quotes,
            "top_searches": top, "plans": [{"plan": p["_id"] or "free", "count": p["count"]} for p in plans],
            "estimated_volume": volume}


@router.get("/prices")
async def prices() -> list:
    overrides = {d["key"]: d async for d in db.price_reference.find({}, {"_id": 0})}
    return [{**l, **overrides.get(l["key"], {}), "overridden": l["key"] in overrides} for l in LOTS]


class PriceIn(BaseModel):
    mat_eco: float | None = None
    mat_std: float | None = None
    mat_premium: float | None = None
    labour: float | None = None
    hours: float | None = None


@router.put("/prices/{key}")
async def update_price(key: str, body: PriceIn) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.price_reference.update_one(
        {"key": key}, {"$set": {**updates, "key": key,
                                "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    from engines.catalog import LOTS_BY_KEY
    if key in LOTS_BY_KEY:
        LOTS_BY_KEY[key].update(updates)
    return {"key": key, **updates}


@router.delete("/prices/{key}")
async def reset_price(key: str) -> dict:
    await db.price_reference.delete_one({"key": key})
    return {"ok": True}


@router.get("/regions")
async def regions():
    docs = await db.regions.find({}, {"_id": 0}).to_list(500)
    return docs or REGIONS


class RegionIn(BaseModel):
    country: str
    region: str
    coef: float


@router.put("/regions")
async def upsert_region(body: RegionIn):
    from engines.catalog import REGIONS as R
    existing = next((r for r in R if r["country"] == body.country and r["region"] == body.region), None)
    if existing:
        existing["coef"] = body.coef
    else:
        R.append(body.model_dump())
    await db.regions.delete_many({})
    await db.regions.insert_many([dict(r) for r in R])
    return body.model_dump()


@router.get("/users")
async def users():
    return await db.users.find({}, {"_id": 0, "password_hash": 0}).sort("created_at", -1).to_list(500)


class UserIn(BaseModel):
    role: str | None = None
    plan: str | None = None
    two_fa_enabled: bool | None = None
    two_fa_email: str | None = None


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserIn):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "two_fa_email" in updates:
        updates["two_fa_email"] = updates["two_fa_email"].strip().lower() or None
    await db.users.update_one({"user_id": user_id}, {"$set": updates})
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


@router.get("/projects")
async def all_projects():
    return await db.projects.find({}, {"_id": 0, "estimation.lots": 0}) \
        .sort("created_at", -1).to_list(300)


@router.get("/leads")
async def all_leads():
    return await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


@router.get("/leads/stats")
async def leads_stats() -> dict:
    total = await db.leads.count_documents({})
    particulier = await db.leads.count_documents({"source": {"$regex": "particulier$"}})
    pro = await db.leads.count_documents({"source": {"$regex": "pro$"}})
    landing = await db.leads.count_documents({"source": {"$regex": "^landing"}})
    nouveau = await db.leads.count_documents({"status": "nouveau"})
    gagne = await db.leads.count_documents({"status": "gagné"})
    return {"total": total, "particulier": particulier, "pro": pro,
            "landing": landing, "nouveau": nouveau, "gagne": gagne}


class LeadStatusIn(BaseModel):
    status: str


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadStatusIn):
    await db.leads.update_one({"lead_id": lead_id}, {"$set": {"status": body.status}})
    return await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})


@router.get("/suppliers")
async def suppliers() -> dict:
    extra = await db.suppliers.find({}, {"_id": 0}).to_list(200)
    return {"builtin": price_search.SUPPLIERS, "custom": extra}


class SupplierIn(BaseModel):
    key: str
    name: str
    domain: str
    shipping: float = 30
    free_from: float = 300
    min_order: float = 0
    delivery_days: int = 4
    rating: float = 4.0
    stores: int = 0


@router.post("/suppliers")
async def add_supplier(body: SupplierIn):
    doc = body.model_dump()
    await db.suppliers.update_one({"key": doc["key"]}, {"$set": doc}, upsert=True)
    if not any(s["key"] == doc["key"] for s in price_search.SUPPLIERS):
        price_search.SUPPLIERS.append(doc)
        price_search.SUPPLIERS_BY_KEY[doc["key"]] = doc
    return doc


@router.delete("/suppliers/{key}")
async def delete_supplier(key: str) -> dict:
    await db.suppliers.delete_one({"key": key})
    return {"ok": True}



# ---------- Plans & Monétisation ----------

@router.get("/plans")
async def list_all_plans():
    return await db.plans.find({}, {"_id": 0}).sort("sort_order", 1).to_list(100)


class PlanIn(BaseModel):
    plan_id: str
    code: str
    name: str
    tagline: str | None = None
    description: str | None = None
    audience: str = "particulier"
    kind: str = "subscription"
    amount_cents: int = 0
    currency: str = "eur"
    interval: str | None = None
    lookup_key: str | None = None
    trial_days: int | None = None
    features: list[str] = []
    quotas: dict = {}
    sort_order: int = 100
    active: bool = True
    highlight: bool = False
    badge: str | None = None


@router.post("/plans")
async def upsert_plan(body: PlanIn):
    doc = body.model_dump()
    # Préserver les IDs Stripe existants (ils sont re-synchronisés par sync-stripe)
    existing = await db.plans.find_one({"plan_id": doc["plan_id"]}, {"_id": 0})
    if existing:
        for k in ("stripe_product_id", "stripe_price_id", "synced_at"):
            if existing.get(k):
                doc.setdefault(k, existing[k])
    await db.plans.update_one({"plan_id": doc["plan_id"]}, {"$set": doc}, upsert=True)
    return doc


@router.delete("/plans/{plan_id}")
async def delete_plan(plan_id: str) -> dict:
    await db.plans.delete_one({"plan_id": plan_id})
    return {"ok": True}


@router.post("/plans/sync-stripe")
async def sync_stripe() -> dict:
    from engines import monetization
    await monetization.ensure_stripe_catalog()
    return {"ok": True}


@router.get("/feature-flags")
async def get_flags():
    flags = await db.feature_flags.find_one({"_id": "global"})
    if flags:
        flags.pop("_id", None)
    return flags or {}


@router.put("/feature-flags")
async def set_flags(body: dict):
    body.pop("_id", None)
    await db.feature_flags.update_one({"_id": "global"}, {"$set": body}, upsert=True)
    return body


# ---------- Revenue dashboard (Phase 1 : basique) ----------

@router.get("/revenue")
async def revenue_dashboard() -> dict:
    paid = await db.payment_transactions.find(
        {"payment_status": "paid"}, {"_id": 0}).to_list(5000)
    from collections import defaultdict
    by_plan = defaultdict(lambda: {"count": 0, "revenue_cents": 0})
    total = 0
    for p in paid:
        by_plan[p["plan_id"]]["count"] += 1
        by_plan[p["plan_id"]]["revenue_cents"] += p.get("amount_cents", 0)
        total += p.get("amount_cents", 0)
    active_subs = await db.entitlements.count_documents(
        {"status": "active", "kind": "subscription"})
    active_passes = await db.entitlements.count_documents(
        {"status": "active", "kind": "one_time",
         "$or": [{"expires_at": {"$exists": False}},
                 {"expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}}]})
    return {
        "total_revenue_cents": total,
        "total_revenue_eur": round(total / 100, 2),
        "active_subscriptions": active_subs,
        "active_project_pass": active_passes,
        "by_plan": [{"plan_id": k, **v} for k, v in by_plan.items()],
        "transactions_count": len(paid),
    }


# ---------- Sélecteur de modèle IA ----------

class AiModelIn(BaseModel):
    tier: str


@router.get("/ai-model")
async def get_ai_model() -> dict:
    from engines import ai
    current = await ai.get_text_tier()
    return {
        "current": current,
        "options": [
            {"tier": k, "label": v["label"], "desc": v["desc"], "model": v["model"]}
            for k, v in ai.AI_TEXT_MODELS.items()
        ],
    }


@router.put("/ai-model")
async def set_ai_model(body: AiModelIn) -> dict:
    from fastapi import HTTPException
    from engines import ai
    if body.tier not in ai.AI_TEXT_MODELS:
        raise HTTPException(400, f"tier inconnu: {body.tier}")
    tier = await ai.set_text_tier(body.tier)
    return {"current": tier}
