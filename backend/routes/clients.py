"""CRM Clients — fiches clients réutilisables dans les devis et factures.

Inclut la création automatique d'une fiche depuis le cartouche / permis de construire
détecté par l'analyse IA d'un plan (endpoint /from-plan/{plan_id}).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.db import db
from core.security import current_user, pro_required

router = APIRouter(tags=["clients"], prefix="/clients", dependencies=[Depends(pro_required)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClientIn(BaseModel):
    first_name: str = ""
    last_name: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""
    address: str = ""
    postal_code: str = ""
    city: str = ""
    siret: str = ""
    notes: str = ""


def _clean(body: ClientIn) -> dict:
    d = body.model_dump()
    return {k: (v or "").strip()[:200] for k, v in d.items()}


@router.post("")
async def create_client(body: ClientIn, user=Depends(current_user)) -> dict:
    data = _clean(body)
    if not (data["first_name"] or data["last_name"] or data["company"] or data["email"]):
        raise HTTPException(400, "Renseignez au moins un nom, une société ou un email")
    doc = {
        "client_id": "cli_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        **data,
        "source": "manual",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.clients.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_clients(q: str = "", user=Depends(current_user)) -> dict:
    query: dict = {"user_id": user["user_id"]}
    if q.strip():
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"first_name": rx}, {"last_name": rx}, {"company": rx},
                        {"email": rx}, {"city": rx}, {"phone": rx}]
    docs = await db.clients.find(query, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    return {"clients": docs, "count": len(docs)}


@router.get("/{client_id}")
async def get_client(client_id: str, user=Depends(current_user)) -> dict:
    doc = await db.clients.find_one(
        {"client_id": client_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Client introuvable")
    return doc


@router.put("/{client_id}")
async def update_client(client_id: str, body: ClientIn,
                        user=Depends(current_user)) -> dict:
    res = await db.clients.update_one(
        {"client_id": client_id, "user_id": user["user_id"]},
        {"$set": {**_clean(body), "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Client introuvable")
    return await get_client(client_id, user)


@router.delete("/{client_id}")
async def delete_client(client_id: str, user=Depends(current_user)) -> dict:
    exists = await db.clients.find_one(
        {"client_id": client_id, "user_id": user["user_id"]}, {"_id": 0, "client_id": 1})
    if not exists:
        raise HTTPException(404, "Client introuvable")
    n_docs = await db.pro_documents.count_documents(
        {"client_id": client_id, "user_id": user["user_id"]})
    if n_docs:
        raise HTTPException(
            400, f"Ce client a {n_docs} document(s) lié(s). Supprimez d'abord ses devis/factures.")
    from routes.trash import trash_record
    client = await db.clients.find_one({"client_id": client_id, "user_id": user["user_id"]}, {"_id": 0})
    res = await trash_record("client", client, user["user_id"])
    await db.clients.delete_one({"client_id": client_id, "user_id": user["user_id"]})
    return res


@router.post("/from-plan/{plan_id}")
async def client_from_plan(plan_id: str, user=Depends(current_user)) -> dict:
    """Crée une fiche client depuis le cartouche / PC détecté par l'analyse IA du plan."""
    plan = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "ai_analysis": 1})
    if not plan:
        raise HTTPException(404, "Plan introuvable")
    ci = ((plan.get("ai_analysis") or {}).get("client_info")) or {}
    has_data = any(ci.get(k) for k in ("first_name", "last_name", "company", "address"))
    if not (ci.get("detected") and has_data):
        raise HTTPException(
            400, "Aucune information client détectée sur ce plan. Lancez d'abord l'analyse IA.")

    last = (ci.get("last_name") or "").strip()
    addr = (ci.get("address") or "").strip()
    if last or addr:
        existing = await db.clients.find_one(
            {"user_id": user["user_id"], "last_name": last, "address": addr}, {"_id": 0})
        if existing:
            return {**existing, "duplicate": True}

    doc = {
        "client_id": "cli_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "first_name": (ci.get("first_name") or "").strip()[:80],
        "last_name": last[:80],
        "company": (ci.get("company") or "").strip()[:120],
        "email": (ci.get("email") or "").strip()[:160],
        "phone": (ci.get("phone") or "").strip()[:40],
        "address": addr[:200],
        "postal_code": (ci.get("postal_code") or "").strip()[:16],
        "city": (ci.get("city") or "").strip()[:80],
        "siret": "",
        "notes": f"Fiche créée automatiquement depuis le plan {plan_id}.",
        "source": "ai_plan",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.clients.insert_one(dict(doc))
    doc.pop("_id", None)
    return {**doc, "duplicate": False}
