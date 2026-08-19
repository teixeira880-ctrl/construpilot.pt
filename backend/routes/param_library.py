"""Bibliothèque paramétrique (admin) : import, visualisation, calcul déboursé sec.

Tables éditables : taux horaires par métier, coefficients régionaux, prix matériaux.
"""
from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel

from core.db import db
from core.security import current_user, admin_user
from engines.param_import import (
    parse_param_library, eval_formula, DEFAULT_LABOR_RATES, DEFAULT_REGIONAL_COEFS,
    DEFAULT_VARIABLES, DEFAULT_MATERIALS,
)

admin_router = APIRouter(prefix="/admin/param-library", tags=["admin"],
                         dependencies=[Depends(admin_user)])
router = APIRouter(prefix="/param-library", tags=["param-library"])

_LVL = {"bas": "low", "moyen": "mid", "haut": "high"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(s: str) -> str:
    s = (s or "").replace("œ", "oe")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


# ---------------- seed helpers ----------------

async def _ensure_defaults():
    if await db.labor_rates.count_documents({}) == 0:
        await db.labor_rates.insert_many([dict(x) for x in DEFAULT_LABOR_RATES])
    if await db.regional_coefs.count_documents({}) == 0:
        await db.regional_coefs.insert_many([dict(x) for x in DEFAULT_REGIONAL_COEFS])
    if await db.material_prices.count_documents({}) == 0:
        await db.material_prices.insert_many([
            {"mat_id": "mat_" + secrets.token_hex(5), **m} for m in DEFAULT_MATERIALS])


# ---------------- IMPORT ----------------

@admin_router.post("/import")
async def import_param(file: UploadFile = File(...)) -> dict:
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "Fichier trop volumineux (max 20 Mo).")
    try:
        parsed = parse_param_library(content, file.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    now = _now()
    await db.param_recipe_lines.delete_many({})
    docs = [{"line_id": "prl_" + secrets.token_hex(6), **ln} for ln in parsed["lines"]]
    # insert par lots
    for i in range(0, len(docs), 500):
        await db.param_recipe_lines.insert_many(docs[i:i + 500])
    await db.app_settings.update_one(
        {"key": "param_library_meta"},
        {"$set": {"key": "param_library_meta", "count_ouvrages": parsed["count_ouvrages"],
                  "count_lines": parsed["count_lines"], "reference": parsed["reference"],
                  "imported_at": now, "last_file": file.filename}}, upsert=True)
    await _ensure_defaults()
    return {"ok": True, "ouvrages": parsed["count_ouvrages"], "lines": parsed["count_lines"]}


@admin_router.delete("")
async def clear_param() -> dict:
    await db.param_recipe_lines.delete_many({})
    await db.app_settings.delete_one({"key": "param_library_meta"})
    return {"ok": True}


async def _ouvrage_list(q: str = "", limit: int = 1000) -> list[dict]:
    match = {}
    if q.strip():
        match = {"$or": [{"famille": {"$regex": q.strip(), "$options": "i"}},
                         {"base_code": {"$regex": q.strip(), "$options": "i"}},
                         {"metier_mo": {"$regex": q.strip(), "$options": "i"}}]}
    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {"$group": {"_id": "$base_code", "famille": {"$first": "$famille"},
                    "metier_mo": {"$first": "$metier_mo"},
                    "variables_entree": {"$first": "$variables_entree"},
                    "heures_mo_unite": {"$first": "$heures_mo_unite"},
                    "lines": {"$sum": 1}}},
        {"$sort": {"famille": 1}}, {"$limit": limit},
    ]
    out = await db.param_recipe_lines.aggregate(pipeline).to_list(limit)
    return [{"base_code": o["_id"], "famille": o["famille"], "metier_mo": o["metier_mo"],
             "variables_entree": o["variables_entree"], "heures_mo_unite": o["heures_mo_unite"],
             "lines": o["lines"]} for o in out]


@admin_router.get("/ouvrages")
async def admin_ouvrages(q: str = "") -> dict:
    total = await db.param_recipe_lines.count_documents({})
    meta = await db.app_settings.find_one({"key": "param_library_meta"}, {"_id": 0, "reference": 0}) or {}
    return {"ouvrages": await _ouvrage_list(q), "total_lines": total, "meta": meta}


# ---------------- CALCUL déboursé sec ----------------

async def _material_index() -> list[tuple[set, dict]]:
    mats = await db.material_prices.find({}, {"_id": 0}).to_list(5000)
    return [(set(_norm(m.get("name", "")).split()), m) for m in mats]


def _match_material(name: str, index) -> dict | None:
    toks = set(_norm(name).split())
    best, ov = None, 0
    for mtoks, m in index:
        o = len(toks & mtoks)
        if o > ov:
            best, ov = m, o
    return best if ov >= 1 else None


async def compute_ouvrage(base_code: str, level: str = "moyen", region: str = "standard",
                          margin_pct: float = 25.0, variables: dict | None = None) -> dict:
    lines = await db.param_recipe_lines.find({"base_code": base_code}, {"_id": 0}).sort("ordre", 1).to_list(500)
    if not lines:
        raise HTTPException(404, "Ouvrage introuvable")
    await _ensure_defaults()
    rates = {r["metier"]: r for r in await db.labor_rates.find({}, {"_id": 0}).to_list(100)}
    coefs = {c["region"]: c for c in await db.regional_coefs.find({}, {"_id": 0}).to_list(100)}
    mat_idx = await _material_index()
    lvl = _LVL.get(level, "mid")
    coef = float((coefs.get(region) or {}).get("coef", 1.0))
    vars_used = {**DEFAULT_VARIABLES, **(variables or {})}

    detail = []
    mat_total = 0.0
    for ln in lines:
        qty = eval_formula(ln.get("formule_quantite"), vars_used)
        if qty is None:
            qty = ln.get("quantite_defaut") or 0
        qty_p = round(qty * (1 + (ln.get("pertes_pct") or 0) / 100.0), 3)
        m = _match_material(ln.get("composant", ""), mat_idx)
        unit_price = float(m.get("price")) if m else 0.0
        cost = round(qty_p * unit_price, 2)
        mat_total += cost
        detail.append({"ordre": ln.get("ordre"), "composant": ln.get("composant"),
                       "unite": ln.get("unite_composant"), "formule": ln.get("formule_quantite"),
                       "quantite": qty_p, "prix_unitaire": unit_price, "cout": cost,
                       "matched": bool(m)})

    o = lines[0]
    metier = o.get("metier_mo", "")
    driving = (o.get("variables_entree") or "quantite_ouvrage").split(",")[0].strip()
    driving_val = float(vars_used.get(driving, 1) or 1)
    rate = float((rates.get(metier) or {}).get(lvl, 45))
    labor_hours = round(float(o.get("heures_mo_unite") or 0) * driving_val, 2)
    labor_cost = round(labor_hours * rate, 2)

    debourse_sec = round(mat_total + labor_cost, 2)
    prix_revient = round(debourse_sec * coef, 2)
    prix_vente = round(prix_revient * (1 + margin_pct / 100.0), 2)
    return {
        "base_code": base_code, "famille": o.get("famille"), "metier": metier,
        "level": level, "region": region, "coef": coef, "margin_pct": margin_pct,
        "driving_var": driving, "driving_val": driving_val,
        "labor_hours": labor_hours, "labor_rate": rate, "labor_cost": labor_cost,
        "materiaux_total": round(mat_total, 2), "debourse_sec": debourse_sec,
        "prix_revient": prix_revient, "prix_vente": prix_vente, "lignes": detail,
    }


@admin_router.get("/ouvrages/{base_code}")
async def admin_ouvrage_detail(base_code: str, level: str = "moyen", region: str = "standard",
                               margin_pct: float = 25.0) -> dict:
    return await compute_ouvrage(base_code, level, region, margin_pct)


# ---------------- Tables éditables (admin) ----------------

class RateIn(BaseModel):
    metier: str
    low: float
    mid: float
    high: float


class CoefIn(BaseModel):
    region: str
    label: str = ""
    coef: float


class MaterialIn(BaseModel):
    name: str
    unit: str = "u"
    price: float = 0.0


@admin_router.get("/labor-rates")
async def get_labor_rates() -> dict:
    await _ensure_defaults()
    return {"rates": await db.labor_rates.find({}, {"_id": 0}).sort("metier", 1).to_list(100)}


@admin_router.put("/labor-rates")
async def put_labor_rates(body: list[RateIn]) -> dict:
    await db.labor_rates.delete_many({})
    await db.labor_rates.insert_many([r.model_dump() for r in body])
    return {"ok": True, "count": len(body)}


@admin_router.get("/regional-coefs")
async def get_coefs() -> dict:
    await _ensure_defaults()
    return {"coefs": await db.regional_coefs.find({}, {"_id": 0}).to_list(100)}


@admin_router.put("/regional-coefs")
async def put_coefs(body: list[CoefIn]) -> dict:
    await db.regional_coefs.delete_many({})
    await db.regional_coefs.insert_many([c.model_dump() for c in body])
    return {"ok": True, "count": len(body)}


@admin_router.get("/materials")
async def get_materials(q: str = "") -> dict:
    await _ensure_defaults()
    query = {"name": {"$regex": q.strip(), "$options": "i"}} if q.strip() else {}
    items = await db.material_prices.find(query, {"_id": 0}).sort("name", 1).to_list(5000)
    return {"materials": items, "total": await db.material_prices.count_documents({})}


@admin_router.post("/materials")
async def add_material(body: MaterialIn) -> dict:
    doc = {"mat_id": "mat_" + secrets.token_hex(5), **body.model_dump()}
    await db.material_prices.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@admin_router.put("/materials/{mat_id}")
async def update_material(mat_id: str, body: MaterialIn) -> dict:
    res = await db.material_prices.update_one({"mat_id": mat_id}, {"$set": body.model_dump()})
    if not res.matched_count:
        raise HTTPException(404, "Matériau introuvable")
    return {"ok": True}


@admin_router.delete("/materials/{mat_id}")
async def delete_material(mat_id: str) -> dict:
    await db.material_prices.delete_one({"mat_id": mat_id})
    return {"ok": True}


# ---------------- Consultation Pro Business ----------------

@router.get("/ouvrages")
async def list_ouvrages(q: str = "", user=Depends(current_user)) -> dict:
    from engines.monetization import user_tier
    if user.get("role") != "admin" and (await user_tier(user["user_id"])) != "pro_business":
        raise HTTPException(402, "Bibliothèque paramétrique réservée au plan Pro Business.")
    return {"ouvrages": await _ouvrage_list(q),
            "total_lines": await db.param_recipe_lines.count_documents({})}
