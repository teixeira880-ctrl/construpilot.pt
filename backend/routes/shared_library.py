"""Bibliothèque partagée ConstruPilot.

- L'admin importe une bibliothèque complète (CSV/Excel) avec prix bas/médian/haut.
- Les entreprises Pro Business y ont accès automatiquement (consultation + usage IA).
- Chaque entreprise choisit une gamme de prix (bas/moyen/haut), par défaut « moyen »,
  avec possibilité de surcharger par devis.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from core.db import db
from core.security import current_user, admin_user
from engines.library_import import parse_shared_library, CSV_TEMPLATE

router = APIRouter(prefix="/shared-library", tags=["shared-library"])
admin_router = APIRouter(prefix="/admin/shared-library", tags=["admin"],
                         dependencies=[Depends(admin_user)])

LEVELS = ("bas", "moyen", "haut")
_LEVEL_FIELD = {"bas": "price_low", "moyen": "price_mid", "haut": "price_high"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _is_pro_business(user: dict) -> bool:
    if (user or {}).get("role") == "admin":
        return True
    from engines.monetization import user_tier
    return (await user_tier(user.get("user_id"))) == "pro_business"


# ------------------------- ADMIN : import / gestion -------------------------

@admin_router.get("/template", response_class=PlainTextResponse)
async def download_template() -> str:
    return CSV_TEMPLATE


@admin_router.post("/import")
async def import_library(file: UploadFile = File(...), replace: bool = True) -> dict:
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop volumineux (max 15 Mo).")
    try:
        parsed = parse_shared_library(content, file.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    rows = parsed["rows"]
    if not rows:
        raise HTTPException(400, "Aucun ouvrage valide détecté dans le fichier.")
    now = _now()
    docs = [{"item_id": "shl_" + secrets.token_hex(6), **r,
             "created_at": now, "updated_at": now} for r in rows]
    if replace:
        await db.shared_library_items.delete_many({})
    await db.shared_library_items.insert_many(docs)
    total = await db.shared_library_items.count_documents({})
    await db.app_settings.update_one(
        {"key": "shared_library_meta"},
        {"$set": {"key": "shared_library_meta", "count": total,
                  "imported_at": now, "columns": parsed["columns"],
                  "last_file": file.filename}}, upsert=True)
    return {"ok": True, "imported": len(docs), "total": total,
            "columns_detected": parsed["columns"],
            "sample": rows[:5]}


@admin_router.get("")
async def admin_list(q: str = "", limit: int = 200) -> dict:
    query: dict = {}
    if q.strip():
        query["$or"] = [{"designation": {"$regex": q.strip(), "$options": "i"}},
                        {"category": {"$regex": q.strip(), "$options": "i"}}]
    items = await db.shared_library_items.find(query, {"_id": 0}).sort("category", 1).limit(limit).to_list(limit)
    total = await db.shared_library_items.count_documents({})
    meta = await db.app_settings.find_one({"key": "shared_library_meta"}, {"_id": 0}) or {}
    cats = await db.shared_library_items.distinct("category")
    return {"items": items, "total": total, "meta": meta, "categories": sorted(cats)}


@admin_router.delete("")
async def admin_clear() -> dict:
    await db.shared_library_items.delete_many({})
    await db.app_settings.delete_one({"key": "shared_library_meta"})
    return {"ok": True}


# ------------------------- ENTREPRISE : consultation -------------------------

@router.get("/level")
async def get_price_level(user=Depends(current_user)) -> dict:
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "price_level": 1})
    level = (u or {}).get("price_level")
    return {"level": level if level in LEVELS else "moyen"}


class LevelIn(BaseModel):
    level: str


@router.put("/level")
async def set_price_level(body: LevelIn, user=Depends(current_user)) -> dict:
    if body.level not in LEVELS:
        raise HTTPException(400, "Niveau invalide (bas, moyen ou haut).")
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"price_level": body.level}})
    return {"level": body.level}


@router.get("")
async def list_shared(q: str = "", category: str = "", limit: int = 500,
                      user=Depends(current_user)) -> dict:
    if not await _is_pro_business(user):
        raise HTTPException(402, "La bibliothèque partagée est réservée au plan Pro Business.")
    query: dict = {}
    if category.strip():
        query["category"] = category.strip()
    if q.strip():
        query["designation"] = {"$regex": q.strip(), "$options": "i"}
    items = await db.shared_library_items.find(query, {"_id": 0}).sort("category", 1).limit(limit).to_list(limit)
    total = await db.shared_library_items.count_documents({})
    cats = await db.shared_library_items.distinct("category")
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "price_level": 1})
    level = (u or {}).get("price_level")
    return {"items": items, "total": total, "count": len(items),
            "categories": sorted(cats), "level": level if level in LEVELS else "moyen"}


# ------------------------- Usage IA -------------------------

async def get_shared_items_for_level(level: str) -> list[dict]:
    """Retourne [{designation, unit, unit_price_ht, vat_rate}] au niveau demandé."""
    field = _LEVEL_FIELD.get(level, "price_mid")
    docs = await db.shared_library_items.find(
        {}, {"_id": 0, "designation": 1, "unit": 1, "vat_rate": 1, field: 1}).to_list(20000)
    out = []
    for d in docs:
        price = d.get(field)
        if price:
            out.append({"designation": d.get("designation", ""), "unit": d.get("unit", "u"),
                        "unit_price_ht": price, "vat_rate": d.get("vat_rate")})
    return out


async def resolve_price_level(user_id: str, override: str | None = None) -> str:
    if override in LEVELS:
        return override
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "price_level": 1})
    lvl = (u or {}).get("price_level")
    return lvl if lvl in LEVELS else "moyen"
