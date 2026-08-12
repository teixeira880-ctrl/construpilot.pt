"""Sponsored products + price history endpoints."""
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import admin_user

router = APIRouter(tags=["phase6"])


def _now():
    return datetime.now(timezone.utc)


# =============== SPONSORED PRODUCTS ===============

class SponsorshipIn(BaseModel):
    supplier_key: str
    keywords: list[str] = []  # ex: ['peinture','carrelage']
    daily_budget_cents: int = 5000  # 50 €/jour
    cpc_cents: int = 100  # coût par clic
    priority: int = 100  # + haut = affiché en premier
    active: bool = True


@router.post("/admin/sponsorships")
async def upsert_sponsorship(body: SponsorshipIn, admin=Depends(admin_user)):
    doc = body.model_dump()
    doc["updated_at"] = _now().isoformat()
    key = {"supplier_key": doc["supplier_key"]}
    await db.sponsorships.update_one(key, {"$set": doc,
                                           "$setOnInsert": {"created_at": _now().isoformat(),
                                                            "spent_today_cents": 0,
                                                            "reset_at": _now().isoformat()}},
                                     upsert=True)
    return doc


@router.get("/admin/sponsorships")
async def list_sponsorships(admin=Depends(admin_user)):
    return await db.sponsorships.find({}, {"_id": 0}).sort("priority", -1).to_list(200)


@router.delete("/admin/sponsorships/{supplier_key}")
async def delete_sponsorship(supplier_key: str, admin=Depends(admin_user)):
    await db.sponsorships.delete_one({"supplier_key": supplier_key})
    return {"ok": True}


async def _reset_daily_if_needed(sp: dict):
    reset_at = sp.get("reset_at")
    try:
        d = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
    except Exception:
        d = _now() - timedelta(days=2)
    if (_now() - d).total_seconds() > 86400:
        await db.sponsorships.update_one({"supplier_key": sp["supplier_key"]},
                                         {"$set": {"spent_today_cents": 0,
                                                   "reset_at": _now().isoformat()}})
        sp["spent_today_cents"] = 0


async def promote(results: list[dict], query: str) -> list[dict]:
    """Insère un résultat sponsorisé en tête si actif et budget dispo."""
    if not results:
        return results
    sponsors = await db.sponsorships.find({"active": True}, {"_id": 0}
                                          ).sort("priority", -1).to_list(20)
    q = query.lower()
    for sp in sponsors:
        if sp.get("keywords") and not any(k.lower() in q for k in sp["keywords"]):
            continue
        await _reset_daily_if_needed(sp)
        if sp.get("spent_today_cents", 0) + sp.get("cpc_cents", 100) > sp.get("daily_budget_cents", 0):
            continue
        # Trouver le résultat correspondant au fournisseur
        idx = next((i for i, r in enumerate(results) if r.get("supplier_key") == sp["supplier_key"]), None)
        if idx is None:
            continue
        chosen = dict(results[idx])
        chosen["sponsored"] = True
        chosen["sponsored_disclosure"] = "Sponsorisé — placement payé"
        # Déplacer en tête
        rest = results[:idx] + results[idx + 1:]
        return [chosen] + rest
    return results


class SponsoredClickIn(BaseModel):
    supplier_key: str
    query: str = ""


@router.post("/sponsored/click")
async def sponsored_click(body: SponsoredClickIn):
    sp = await db.sponsorships.find_one({"supplier_key": body.supplier_key, "active": True},
                                        {"_id": 0})
    if not sp:
        return {"ok": True}
    cpc = sp.get("cpc_cents", 100)
    await db.sponsorships.update_one({"supplier_key": body.supplier_key},
                                     {"$inc": {"spent_today_cents": cpc,
                                               "clicks_total": 1}})
    await db.affiliate_events.insert_one({
        "event": "sponsored_click", "supplier_key": body.supplier_key,
        "query": body.query, "cpc_cents": cpc, "at": _now().isoformat()})
    return {"ok": True, "cpc_cents": cpc}


# =============== PRICE HISTORY ===============

@router.post("/prices/history/snapshot")
async def snapshot_prices(query: str, admin=Depends(admin_user)):
    """Enregistre les prix courants d'une requête pour tracer l'historique."""
    from engines import price_search
    res = await price_search.search(query, 20)
    day = _now().date().isoformat()
    inserted = 0
    for r in res.get("results", []):
        if not r.get("price"):
            continue
        doc = {"query": query.lower(), "supplier_key": r.get("supplier_key"),
               "supplier": r.get("supplier"), "price": r.get("price"),
               "product": r.get("product"), "day": day, "at": _now().isoformat()}
        # Éviter les doublons du jour
        exists = await db.price_history_daily.find_one(
            {"query": query.lower(), "supplier_key": r.get("supplier_key"), "day": day})
        if exists:
            continue
        await db.price_history_daily.insert_one(doc)
        inserted += 1
    return {"query": query, "day": day, "inserted": inserted}


@router.get("/prices/history/chart")
async def price_history_chart(query: str, days: int = 90):
    """Retourne l'historique des prix pour graphique (agrégat journalier)."""
    since = (_now() - timedelta(days=days)).date().isoformat()
    docs = await db.price_history_daily.find(
        {"query": query.lower(), "day": {"$gte": since}},
        {"_id": 0}).sort("at", 1).to_list(2000)
    # Agrégat par jour → min/moy
    by_day: dict = {}
    for d in docs:
        day = d["day"]
        by_day.setdefault(day, []).append(d["price"])
    series = [{"day": k, "min_price": round(min(v), 2),
               "avg_price": round(sum(v) / len(v), 2),
               "max_price": round(max(v), 2), "count": len(v)}
              for k, v in sorted(by_day.items())]
    return {"query": query, "series": series, "days": days}
