"""Bibliothèque de prix propre à l'entreprise (Pro Business).

Chaque entreprise importe son propre bordereau de prix (Excel ou PDF). Ces prix
sont utilisés en priorité lors du remplissage d'un DPGF (avant l'estimation IA).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from core.db import db
from core.security import current_user
from engines import ai, price_library

router = APIRouter(prefix="/pro/price-library", tags=["price-library"])


async def get_user_library(user_id: str) -> list[dict]:
    """Retourne les lignes de prix de l'entreprise (pour le remplissage DPGF)."""
    cur = db.company_price_libraries.find(
        {"user_id": user_id},
        {"_id": 0, "designation": 1, "unit": 1, "unit_price": 1, "ref": 1})
    return await cur.to_list(5000)


@router.post("/upload")
async def upload_library(file: UploadFile = File(...), user=Depends(current_user)) -> dict:
    raw = await file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            lines = price_library.parse_excel(raw)
        elif name.endswith(".pdf"):
            images = price_library.pdf_to_images_b64(raw)
            lines = await ai.extract_price_library(images)
        else:
            raise HTTPException(400, "Format non supporté (.xlsx ou .pdf attendu).")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Fichier illisible (.xlsx ou .pdf attendu).")

    if not lines:
        raise HTTPException(422, "Aucune ligne tarifaire détectée dans le fichier.")

    now = datetime.now(timezone.utc).isoformat()
    docs = [{
        "item_id": "pl_" + uuid.uuid4().hex[:12],
        "user_id": user["user_id"],
        "designation": x["designation"],
        "unit": x.get("unit", ""),
        "unit_price": x["unit_price"],
        "ref": x.get("ref", ""),
        "source_file": file.filename,
        "created_at": now,
    } for x in lines]
    await db.company_price_libraries.insert_many(docs)
    total = await db.company_price_libraries.count_documents({"user_id": user["user_id"]})
    return {"imported": len(docs), "total": total, "source_file": file.filename}


@router.get("")
async def list_library(user=Depends(current_user)) -> dict:
    cur = db.company_price_libraries.find(
        {"user_id": user["user_id"]}, {"_id": 0}).sort("created_at", -1)
    items = await cur.to_list(5000)
    return {"total": len(items), "items": items}


@router.delete("/{item_id}")
async def delete_line(item_id: str, user=Depends(current_user)) -> dict:
    res = await db.company_price_libraries.delete_one(
        {"item_id": item_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Ligne introuvable.")
    return {"deleted": 1}


@router.delete("")
async def clear_library(user=Depends(current_user)) -> dict:
    res = await db.company_price_libraries.delete_many({"user_id": user["user_id"]})
    return {"deleted": res.deleted_count}
