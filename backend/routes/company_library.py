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


async def remember_prices(user_id: str, items: list[dict], origin: str = "DPGF") -> int:
    """Archive les prix retenus dans la bibliothèque de l'entreprise (mémoire des prix).

    Une désignation + unité identique est mise à jour, jamais dupliquée. La provenance
    (bibliothèque, IA, sous-traitant, saisie) est conservée pour tracer l'origine du prix.
    Les prix validés sont AUSSI repris dans la bibliothèque générale ConstruPilot
    (``library_items``) pour être proposés directement dans l'éditeur de devis.
    """
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    for it in items or []:
        desig = (it.get("designation") or "").strip()
        price = float(it.get("unit_price") or 0)
        if len(desig) < 3 or price <= 0:
            continue
        await db.company_price_libraries.update_one(
            {"user_id": user_id, "designation": desig, "unit": it.get("unit") or ""},
            {"$set": {"unit_price": round(price, 2), "price_source": it.get("price_source") or "",
                      "source_file": origin, "updated_at": now},
             "$setOnInsert": {"item_id": "pl_" + uuid.uuid4().hex[:12], "ref": "",
                              "created_at": now}},
            upsert=True)
        saved += 1

    # Reprise dans la bibliothèque générale (postes proposés dans l'éditeur de devis).
    try:
        from routes.library import auto_save_from_lines
        await auto_save_from_lines(user_id, [
            {"designation": (it.get("designation") or "").strip(),
             "unit": it.get("unit") or "u",
             "unit_price_ht": float(it.get("unit_price") or 0),
             "vat_rate": it.get("vat_rate") if it.get("vat_rate") is not None else 10,
             "category": (it.get("category") or it.get("lot") or "").strip() or "A partir do mapa de quantidades"}
            for it in (items or [])
            if (it.get("designation") or "").strip() and float(it.get("unit_price") or 0) > 0
        ], source="dpgf")
    except Exception:  # noqa: BLE001 — la reprise en bibliothèque générale ne doit pas bloquer
        import logging
        logging.getLogger(__name__).warning("remember_prices: feed library_items failed", exc_info=True)
    return saved


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
            raise HTTPException(400, "Formato não suportado (.xlsx ou .pdf esperado).")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Ficheiro ilegível (.xlsx ou .pdf esperado).")

    if not lines:
        raise HTTPException(422, "Nenhuma linha de preço detetada no ficheiro.")

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
    cur = db.company_price_libraries.find({"user_id": user["user_id"]}, {"_id": 0})
    items = await cur.to_list(5000)
    items.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
    return {"total": len(items), "items": items}


@router.delete("/{item_id}")
async def delete_line(item_id: str, user=Depends(current_user)) -> dict:
    res = await db.company_price_libraries.delete_one(
        {"item_id": item_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Linha não encontrada.")
    return {"deleted": 1}


@router.delete("")
async def clear_library(user=Depends(current_user)) -> dict:
    res = await db.company_price_libraries.delete_many({"user_id": user["user_id"]})
    return {"deleted": res.deleted_count}
