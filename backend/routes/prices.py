from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import current_user, optional_user
from engines import price_search, affiliate
from routes.phase6 import promote as promote_sponsored

router = APIRouter(prefix="/prices", tags=["prices"])


@router.get("/suppliers")
async def suppliers():
    extra = await db.suppliers.find({}, {"_id": 0}).to_list(200)
    return price_search.SUPPLIERS + extra


class SearchIn(BaseModel):
    query: str
    limit: int = 10


@router.post("/search")
async def search(body: SearchIn, user=Depends(optional_user)):
    if len(body.query.strip()) < 2:
        raise HTTPException(status_code=400, detail="Requête trop courte")
    await db.search_stats.update_one({"query": body.query.lower()},
                                     {"$inc": {"count": 1},
                                      "$set": {"last_at": datetime.now(timezone.utc).isoformat()}},
                                     upsert=True)
    result = await price_search.search(body.query, body.limit)
    enriched = await affiliate.enrich_prices(result.get("results") or [])
    result["results"] = await promote_sponsored(enriched, body.query)
    return result


@router.get("/history")
async def history(query: str):
    return await price_search.history(query)


class CartIn(BaseModel):
    items: list[dict]


@router.post("/optimize")
async def optimize(body: CartIn):
    if not body.items:
        raise HTTPException(status_code=400, detail="Panier vide")
    return price_search.optimize_cart(body.items)


@router.get("/stores")
async def stores(lat: float, lng: float, radius_km: int = 20):
    return {"radius_km": radius_km, "stores": price_search.stores_nearby(lat, lng, radius_km)}


class AlertIn(BaseModel):
    query: str
    target_price: float
    product: str | None = None
    channels: list[str] = ["email"]  # "email" et/ou "sms"
    phone: str | None = None  # requis si "sms" dans channels (format E.164 +33…)


@router.post("/alerts")
async def create_alert(body: AlertIn, user=Depends(current_user)):
    channels = [c for c in (body.channels or ["email"]) if c in ("email", "sms")]
    if not channels:
        channels = ["email"]
    if "sms" in channels:
        if not body.phone:
            raise HTTPException(422, "Numéro requis pour recevoir les alertes SMS")
        normalized = "".join(ch for ch in body.phone if ch.isdigit() or ch == "+")
        if not normalized.startswith("+") or len(normalized) < 8:
            raise HTTPException(422, "Numéro invalide : utilisez le format +33…")
    doc = {"alert_id": f"al_{datetime.now(timezone.utc).timestamp():.0f}",
           "user_id": user["user_id"], "query": body.query, "target_price": body.target_price,
           "product": body.product or body.query, "active": True,
           "channels": channels,
           "phone": ("".join(ch for ch in body.phone if ch.isdigit() or ch == "+")
                     if "sms" in channels and body.phone else None),
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.price_alerts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/alerts")
async def list_alerts(user=Depends(current_user)):
    alerts = await db.price_alerts.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(200)
    for a in alerts:
        offers = price_search.demo_search(a["query"], 10)
        best = min((o["price"] for o in offers), default=None)
        a["best_price"] = best
        a["triggered"] = bool(best and best <= a["target_price"])
    return alerts


@router.post("/alerts/check-now")
async def check_alerts_now(user=Depends(current_user)):
    """Force la vérification immédiate des alertes de l'utilisateur + envoi email des déclenchées."""
    from engines import alerting
    sent = await alerting.check_user_alerts(user["user_id"])
    return {"ok": True, "notified": sent}


@router.delete("/alerts/{alert_id}")
async def delete_alert(alert_id: str, user=Depends(current_user)):
    await db.price_alerts.delete_one({"alert_id": alert_id, "user_id": user["user_id"]})
    return {"ok": True}
