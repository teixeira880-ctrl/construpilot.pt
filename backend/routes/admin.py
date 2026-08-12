from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.db import db
from core.security import admin_user
from engines.catalog import LOTS, REGIONS
from engines import price_search

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_user)])


@router.get("/stats")
async def stats():
    users = await db.users.count_documents({})
    projects = await db.projects.count_documents({})
    leads = await db.leads.count_documents({})
    quotes = await db.quote_analyses.count_documents({})
    top = await db.search_stats.find({}, {"_id": 0}).sort("count", -1).to_list(10)
    plans = await db.users.aggregate([{"$group": {"_id": "$plan", "count": {"$sum": 1}}}]).to_list(10)
    projs = await db.projects.find({}, {"_id": 0, "estimation.total_avg": 1}).to_list(1000)
    volume = round(sum((p.get("estimation") or {}).get("total_avg", 0) for p in projs), 2)
    return {"users": users, "projects": projects, "leads": leads, "quote_analyses": quotes,
            "top_searches": top, "plans": [{"plan": p["_id"] or "free", "count": p["count"]} for p in plans],
            "estimated_volume": volume}


@router.get("/prices")
async def prices():
    overrides = {d["key"]: d async for d in db.price_reference.find({}, {"_id": 0})}
    return [{**l, **overrides.get(l["key"], {}), "overridden": l["key"] in overrides} for l in LOTS]


class PriceIn(BaseModel):
    mat_eco: float | None = None
    mat_std: float | None = None
    mat_premium: float | None = None
    labour: float | None = None
    hours: float | None = None


@router.put("/prices/{key}")
async def update_price(key: str, body: PriceIn):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.price_reference.update_one(
        {"key": key}, {"$set": {**updates, "key": key,
                                "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    from engines.catalog import LOTS_BY_KEY
    if key in LOTS_BY_KEY:
        LOTS_BY_KEY[key].update(updates)
    return {"key": key, **updates}


@router.delete("/prices/{key}")
async def reset_price(key: str):
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


@router.put("/users/{user_id}")
async def update_user(user_id: str, body: UserIn):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await db.users.update_one({"user_id": user_id}, {"$set": updates})
    return await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})


@router.get("/projects")
async def all_projects():
    return await db.projects.find({}, {"_id": 0, "estimation.lots": 0}) \
        .sort("created_at", -1).to_list(300)


@router.get("/leads")
async def all_leads():
    return await db.leads.find({}, {"_id": 0}).sort("created_at", -1).to_list(300)


class LeadStatusIn(BaseModel):
    status: str


@router.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadStatusIn):
    await db.leads.update_one({"lead_id": lead_id}, {"$set": {"status": body.status}})
    return await db.leads.find_one({"lead_id": lead_id}, {"_id": 0})


@router.get("/suppliers")
async def suppliers():
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
async def delete_supplier(key: str):
    await db.suppliers.delete_one({"key": key})
    return {"ok": True}
