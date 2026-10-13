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


def _norm(s: str) -> str:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").replace("œ", "oe"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


async def _is_pro_business(user: dict) -> bool:
    if (user or {}).get("role") == "admin":
        return True
    from engines.monetization import user_tier
    return (await user_tier(user.get("user_id"))) == "pro_business"


# ------------------------- ADMIN : import / gestion -------------------------

@admin_router.get("/template", response_class=PlainTextResponse)
async def download_template() -> str:
    return CSV_TEMPLATE


async def _merge_import(content: bytes, filename: str, update_prices: bool = False) -> dict:
    """Fusion FR : conserve tout l'existant, ajoute uniquement les ouvrages absents (clé désignation+unité).

    Ne touche jamais aux entrées marquées lang/country PT. Les ajouts sont tagués lang=fr / country=FR.
    """
    from engines.library_import import parse_constructpilot_gammes
    try:
        rows = parse_constructpilot_gammes(content)
    except Exception:  # noqa: BLE001
        rows = []
    if not rows:
        try:
            rows = [dict(r, lang="fr", country="FR") for r in parse_shared_library(content, filename)["rows"]]
        except ValueError as e:
            raise HTTPException(400, str(e))
    if not rows:
        raise HTTPException(400, "Aucun ouvrage valide détecté dans le fichier.")
    existing = await db.shared_library_items.find(
        {"$nor": [{"lang": "pt"}, {"country": "PT"}]},
        {"_id": 0, "designation": 1, "unit": 1, "item_id": 1, "price_low": 1, "price_mid": 1, "price_high": 1}).to_list(50000)
    by_key = {(_norm(e.get("designation", "")), (e.get("unit") or "").strip().lower()): e.get("item_id") for e in existing}
    by_id = {e.get("item_id"): e for e in existing}
    history = []
    seen = set(by_key)
    now = _now()
    docs = []
    updated = 0
    PRICE_FIELDS = ("price_low", "price_mid", "price_high", "mat_low", "mat_mid", "mat_high",
                    "labor_low", "labor_mid", "labor_high", "hours_mid", "source", "ref_date", "code")
    for r in rows:
        key = (_norm(r["designation"]), (r.get("unit") or "").strip().lower())
        if key in seen:
            if update_prices and by_key.get(key):
                upd = {k: r[k] for k in PRICE_FIELDS if r.get(k) is not None}
                if upd:
                    upd["updated_at"] = now
                    old = by_id.get(by_key[key]) or {}
                    if any(old.get(f) != upd.get(f) for f in ("price_low", "price_mid", "price_high") if f in upd):
                        history.append({"hist_id": "slh_" + secrets.token_hex(6), "item_id": by_key[key],
                                        "designation": old.get("designation"), "unit": old.get("unit"), "at": now, "file": filename,
                                        "old": {f: old.get(f) for f in ("price_low", "price_mid", "price_high")},
                                        "new": {f: upd.get(f, old.get(f)) for f in ("price_low", "price_mid", "price_high")}})
                    await db.shared_library_items.update_one({"item_id": by_key[key]}, {"$set": upd})
                    updated += 1
            continue
        seen.add(key)
        docs.append({"item_id": "shl_" + secrets.token_hex(6), **r, "created_at": now, "updated_at": now})
    sample = [{k: v for k, v in d.items()} for d in docs[:5]]
    if history:
        await db.shared_library_price_history.insert_many(history)
    if docs:
        await db.shared_library_items.insert_many(docs)
    total = await db.shared_library_items.count_documents({})
    total_fr = await db.shared_library_items.count_documents({"$nor": [{"lang": "pt"}, {"country": "PT"}]})
    await db.app_settings.update_one(
        {"key": "shared_library_meta"},
        {"$set": {"key": "shared_library_meta", "count": total, "count_fr": total_fr,
                  "imported_at": now, "last_file": filename, "last_mode": "merge"}}, upsert=True)
    return {"ok": True, "mode": "merge+prices" if update_prices else "merge", "in_file": len(rows), "added": len(docs),
            "updated_prices": updated, "kept_existing": len(existing), "skipped_duplicates": len(rows) - len(docs),
            "total": total, "total_fr": total_fr, "sample": sample}



@admin_router.post("/import")
async def import_library(file: UploadFile = File(...), replace: bool = True, merge: bool = False,
                         update_prices: bool = False) -> dict:
    content = await file.read()
    if len(content) > 15 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop volumineux (max 15 Mo).")
    if merge:
        return await _merge_import(content, file.filename or "", update_prices=update_prices)
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


@router.get("/public-count")
async def public_count() -> dict:
    """Compteur public (page d'accueil) : nb d'ouvrages FR de la bibliothèque partagée."""
    fr = await db.shared_library_items.count_documents({"$nor": [{"lang": "pt"}, {"country": "PT"}]})
    return {"count_fr": fr, "count_total": await db.shared_library_items.count_documents({})}



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

async def get_shared_items_for_level(level: str, lang: str | None = None) -> list[dict]:
    """Retourne [{designation, unit, unit_price_ht, vat_rate, cost_price_ht}] au niveau demandé.

    `lang="pt"` → entrées PT uniquement (repli FR si aucune) ; `lang="fr"` → hors PT."""
    field = _LEVEL_FIELD.get(level, "price_mid")
    suffix = {"price_low": "low", "price_mid": "mid", "price_high": "high"}[field]
    pt_q = {"$or": [{"lang": "pt"}, {"country": "PT"}]}
    fr_q = {"$nor": [{"lang": "pt"}, {"country": "PT"}]}
    query = pt_q if lang == "pt" else (fr_q if lang == "fr" else {})
    proj = {"_id": 0, "designation": 1, "unit": 1, "vat_rate": 1, field: 1,
            f"mat_{suffix}": 1, f"labor_{suffix}": 1, "cost_price_ht": 1}
    docs = await db.shared_library_items.find(query, proj).to_list(20000)
    if not docs and lang == "pt":
        docs = await db.shared_library_items.find(fr_q, proj).to_list(20000)
    out = []
    for d in docs:
        price = d.get(field)
        if price:
            cost = d.get("cost_price_ht") or ((d.get(f"mat_{suffix}") or 0) + (d.get(f"labor_{suffix}") or 0)) or None
            out.append({"designation": d.get("designation", ""), "unit": d.get("unit", "u"),
                        "unit_price_ht": price, "vat_rate": d.get("vat_rate"), "cost_price_ht": cost})
    return out


async def resolve_price_level(user_id: str, override: str | None = None) -> str:
    if override in LEVELS:
        return override
    u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "price_level": 1})
    lvl = (u or {}).get("price_level")
    return lvl if lvl in LEVELS else "moyen"


async def global_auto_items(min_contrib: int = 2) -> list[dict]:
    """Pool global auto-appris (prix médians inter-comptes) — repli de dernier recours.

    Exige ``min_contrib`` contributions minimum pour écarter le bruit d'un seul compte.
    Alimenté automatiquement par ``routes.library.auto_save_from_lines``.
    """
    docs = await db.library_global_auto.find(
        {"contributions": {"$gte": min_contrib}},
        {"_id": 0, "designation": 1, "unit": 1, "unit_price_ht": 1}).to_list(20000)
    return [{"designation": d["designation"], "unit": d.get("unit", "u"),
             "unit_price_ht": d["unit_price_ht"], "vat_rate": None, "cost_price_ht": None}
            for d in docs if d.get("unit_price_ht")]


@admin_router.get("/export.xlsx")
async def export_library_xlsx():
    """Export FR au format 3 gammes (identique au fichier d'import ConstruPilot_FR_Bibliotheque)."""
    import io
    from fastapi.responses import StreamingResponse
    from openpyxl import Workbook
    items = await db.shared_library_items.find(
        {"$nor": [{"lang": "pt"}, {"country": "PT"}]}, {"_id": 0}).sort([("category", 1), ("designation", 1)]).to_list(50000)
    wb = Workbook()
    ws = wb.active
    ws.title = "BIBLIOTHEQUE_PRIX"
    ws.append(["Code", "Lot / Famille", "Désignation ouvrage", "Gamme", "Unité", "Mode de prix", "Prix bas",
               "Prix médian référence", "Prix haut", "Matériaux", "Main-d'œuvre", "Matériel / engins",
               "Coefficient entreprise", "Prix calculé", "Heures MO", "Zone de référence", "Date prix",
               "Base fiscale", "Source", "URL source", "Observations"])
    gammes = (("Économique", "low", "ECO"), ("Standard", "mid", "STD"), ("Premium", "high", "PRE"))
    for i, it in enumerate(items, start=1):
        code = it.get("code") or f"CP-{i:04d}"
        for label, lvl, suf in gammes:
            p = it.get(f"price_{lvl}") or it.get("price_mid")
            ws.append([f"{code}-{suf}", it.get("category"), it.get("designation"), label, it.get("unit"),
                       "Prix médian", it.get("price_low"), p, it.get("price_high"),
                       it.get(f"mat_{lvl}") or it.get("mat_mid"), it.get(f"labor_{lvl}") or it.get("labor_mid"),
                       None, 1.0, p, it.get("hours_mid") if lvl == "mid" else None, "France",
                       it.get("ref_date") or "", "HT", it.get("source") or "ConstruPilot", "", ""])
    ws2 = wb.create_sheet("README")
    ws2.append(["Export bibliothèque FR ConstruPilot — 3 lignes par ouvrage (Économique/Standard/Premium)."])
    ws2.append(["Modifiez les prix puis réimportez via Admin → Bibliothèque partagée → « Fusionner + actualiser les prix »."])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": 'attachment; filename="ConstruPilot_FR_Bibliotheque_export.xlsx"'})


@admin_router.get("/price-history")
async def price_history(item_id: str = "", limit: int = 100, user=Depends(admin_user)) -> dict:
    """Historique des variations de prix (après chaque import Excel « actualiser les prix »)."""
    q = {"item_id": item_id} if item_id else {}
    rows = await db.shared_library_price_history.find(q, {"_id": 0}).sort("at", -1).to_list(max(1, min(limit, 1000)))
    for r in rows:
        o, n = (r.get("old") or {}).get("price_mid"), (r.get("new") or {}).get("price_mid")
        r["delta_pct"] = round((n - o) / o * 100, 1) if o and n is not None else None
    return {"items": rows, "count": len(rows)}
