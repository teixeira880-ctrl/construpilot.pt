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
from core.uploads import validate_upload, ALLOWED_IMPORT, ALLOWED_OFFICE
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
    file = await validate_upload(
        file, ALLOWED_IMPORT + ALLOWED_OFFICE, max_mb=20)
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(400, "Ficheiro demasiado volumoso (máx. 20 MB).")
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
        raise HTTPException(404, "Elemento não encontrado")
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
        raise HTTPException(404, "Material não encontrado")
    return {"ok": True}


@admin_router.delete("/materials/{mat_id}")
async def delete_material(mat_id: str) -> dict:
    await db.material_prices.delete_one({"mat_id": mat_id})
    return {"ok": True}


@admin_router.post("/materials/prefill")
async def prefill_material_prices() -> dict:
    """Pré-remplit une estimation de prix (marché 2026) pour les matériaux à 0,
    selon l'unité et des mots-clés. Valeurs à ajuster ensuite."""
    by_unit = {"m3": 150, "m³": 150, "m2": 30, "m²": 30, "ml": 8, "kg": 2,
               "l": 7, "u": 15, "ens": 200, "forfait": 200}
    kw = [("beton", 150), ("acier", 1.6), ("armature", 9), ("isol", 12), ("placo", 6.5),
          ("plaque", 6.5), ("tuile", 1.1), ("membrane", 18), ("etanch", 20),
          ("fenetre", 320), ("porte", 280), ("carrelage", 32), ("parquet", 25),
          ("peinture", 6.5), ("cable", 1.2), ("tube", 4.5), ("vmc", 22),
          ("chauffe", 120), ("pac", 3500), ("enduit", 12), ("bois", 8), ("charpente", 45)]
    mats = await db.material_prices.find({"price": {"$lte": 0}}, {"_id": 0}).to_list(20000)
    updated = 0
    for m in mats:
        n = _norm(m.get("name", ""))
        price = next((v for k, v in kw if k in n), None)
        if price is None:
            price = by_unit.get((m.get("unit") or "u").lower().strip(), 15)
        await db.material_prices.update_one({"mat_id": m["mat_id"]}, {"$set": {"price": float(price)}})
        updated += 1
    return {"ok": True, "updated": updated}


@admin_router.post("/materials/generate-missing")
async def generate_missing_materials() -> dict:
    """Crée une entrée (prix 0, à compléter) pour chaque composant de recette
    non encore présent/apparié dans la table matériaux."""
    await _ensure_defaults()
    index = await _material_index()
    existing_norm = {frozenset(t) for t, _ in index}
    lines = await db.param_recipe_lines.find(
        {}, {"_id": 0, "composant": 1, "unite_composant": 1}).to_list(20000)
    seen = set()
    to_add = []
    for ln in lines:
        name = (ln.get("composant") or "").strip()
        if not name:
            continue
        key = _norm(name)
        if key in seen:
            continue
        seen.add(key)
        if _match_material(name, index):
            continue  # déjà apparié à un matériau existant
        to_add.append({"mat_id": "mat_" + secrets.token_hex(5), "name": name[:200],
                       "unit": (ln.get("unite_composant") or "u")[:16], "price": 0.0})
    if to_add:
        await db.material_prices.insert_many(to_add)
    return {"ok": True, "added": len(to_add),
            "total": await db.material_prices.count_documents({})}


@admin_router.post("/materials/import")
async def import_materials(file: UploadFile = File(...)) -> dict:
    """Import CSV de prix matériaux (Nom;Unite;Prix) — upsert par nom."""
    import csv as _csv
    import io as _io
    file = await validate_upload(file, ALLOWED_IMPORT, max_mb=20)
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    delim = ";" if text[:2000].count(";") >= text[:2000].count(",") else ","
    rows = list(_csv.reader(_io.StringIO(text), delimiter=delim))
    updated = 0
    for r in rows[1:] if rows else []:
        if len(r) < 2 or not (r[0] or "").strip():
            continue
        name = r[0].strip()
        unit = (r[1].strip() if len(r) > 1 else "u") or "u"
        price_raw = (r[2] if len(r) > 2 else r[1]) or "0"
        try:
            price = float(str(price_raw).replace(",", ".").replace("€", "").strip() or 0)
        except ValueError:
            price = 0.0
        res = await db.material_prices.update_one(
            {"name": {"$regex": f"^{re.escape(name)}$", "$options": "i"}},
            {"$set": {"unit": unit, "price": round(price, 2)}})
        if not res.matched_count:
            await db.material_prices.insert_one(
                {"mat_id": "mat_" + secrets.token_hex(5), "name": name[:200],
                 "unit": unit[:16], "price": round(price, 2)})
        updated += 1
    return {"ok": True, "processed": updated,
            "total": await db.material_prices.count_documents({})}


# ---------------- Consultation Pro Business ----------------

@router.get("/ouvrages")
async def list_ouvrages(q: str = "", user=Depends(current_user)) -> dict:
    from engines.monetization import user_tier
    if user.get("role") != "admin" and (await user_tier(user["user_id"])) != "pro_business":
        raise HTTPException(402, "Biblioteca paramétrica reservada ao plano Pro Business.")
    return {"ouvrages": await _ouvrage_list(q),
            "total_lines": await db.param_recipe_lines.count_documents({})}


class QuoteLineIn(BaseModel):
    base_code: str
    level: str = "moyen"
    region: str = "standard"
    margin_pct: float = 25.0
    quantity: float = 1.0
    variables: dict | None = None


@router.post("/quote-line")
async def ouvrage_to_quote_line(body: QuoteLineIn, user=Depends(current_user)) -> dict:
    """Calcule un ouvrage composé et renvoie une ligne de devis prête à insérer.
    Si `variables` est fourni (mesures du plan), la quantité = variable directrice
    mesurée et le prix unitaire = prix de vente / quantité."""
    from engines.monetization import user_tier
    if user.get("role") != "admin" and (await user_tier(user["user_id"])) != "pro_business":
        raise HTTPException(402, "Reservado ao plano Pro Business.")
    r = await compute_ouvrage(body.base_code, body.level, body.region, body.margin_pct,
                              variables=body.variables)
    dv = r.get("driving_var")
    unit = "m²" if dv in ("surface_m2", "surface_nette_m2", "surface_toiture_m2") \
        else "ml" if dv in ("longueur_ml", "perimetre_ml", "longueur_reseau_ml") else "u"
    if body.variables and (r.get("driving_val") or 0) > 0:
        qty = round(float(r["driving_val"]), 2)
        unit_price = round(r["prix_vente"] / qty, 2)
    else:
        qty = max(body.quantity or 1, 0.01)
        unit_price = r["prix_vente"]
    return {"line": {
        "designation": r["famille"], "description": f"Trabalho composto {r['base_code']} · {r['metier']}",
        "unit": unit, "qty": qty, "unit_price_ht": unit_price, "vat_rate": 6,
        "category": r.get("famille", "Trabalho composto")},
        "detail": r}
