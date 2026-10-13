"""Bibliothèque perso — ouvrages & matériaux avec prix définis par l'entreprise.

- Catalogue de départ pré-rempli (seed une seule fois par utilisateur).
- Réutilisable dans l'éditeur de devis (étape suivante).
- CRUD complet ; chaque nouvel ouvrage saisi est enregistré dans la bibliothèque perso.
"""
from __future__ import annotations

import re
import secrets
import unicodedata
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user

router = APIRouter(tags=["library"], prefix="/library")

UNITS = ["u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L"]

# Catalogue de départ (prix HT indicatifs FR, modifiables par l'entreprise).
STARTER_CATALOGUE: list[dict] = [
    # --- Gros œuvre / Maçonnerie ---
    {"type": "ouvrage", "category": "Gros œuvre", "designation": "Démolition cloison", "unit": "m²", "unit_price_ht": 25, "vat_rate": 10},
    {"type": "ouvrage", "category": "Gros œuvre", "designation": "Ouverture mur porteur + pose IPN", "unit": "forfait", "unit_price_ht": 1800, "vat_rate": 10},
    {"type": "ouvrage", "category": "Gros œuvre", "designation": "Chape de ravoirage", "unit": "m²", "unit_price_ht": 35, "vat_rate": 10},
    {"type": "ouvrage", "category": "Gros œuvre", "designation": "Dalle béton armé", "unit": "m²", "unit_price_ht": 90, "vat_rate": 10},
    {"type": "ouvrage", "category": "Gros œuvre", "designation": "Mur en parpaing 20 cm", "unit": "m²", "unit_price_ht": 75, "vat_rate": 10},
    # --- Plâtrerie / Isolation ---
    {"type": "ouvrage", "category": "Plâtrerie / Isolation", "designation": "Cloison BA13 sur ossature métallique", "unit": "m²", "unit_price_ht": 45, "vat_rate": 10},
    {"type": "ouvrage", "category": "Plâtrerie / Isolation", "designation": "Doublage isolant laine de verre", "unit": "m²", "unit_price_ht": 42, "vat_rate": 10},
    {"type": "ouvrage", "category": "Plâtrerie / Isolation", "designation": "Faux plafond BA13", "unit": "m²", "unit_price_ht": 48, "vat_rate": 10},
    {"type": "ouvrage", "category": "Plâtrerie / Isolation", "designation": "Enduit de lissage sur mur", "unit": "m²", "unit_price_ht": 18, "vat_rate": 10},
    {"type": "ouvrage", "category": "Plâtrerie / Isolation", "designation": "Isolation combles laine soufflée", "unit": "m²", "unit_price_ht": 25, "vat_rate": 10},
    # --- Électricité ---
    {"type": "ouvrage", "category": "Électricité", "designation": "Point lumineux (fourniture + pose)", "unit": "u", "unit_price_ht": 85, "vat_rate": 10},
    {"type": "ouvrage", "category": "Électricité", "designation": "Prise de courant 16A", "unit": "u", "unit_price_ht": 65, "vat_rate": 10},
    {"type": "ouvrage", "category": "Électricité", "designation": "Interrupteur va-et-vient", "unit": "u", "unit_price_ht": 70, "vat_rate": 10},
    {"type": "ouvrage", "category": "Électricité", "designation": "Tableau électrique équipé", "unit": "u", "unit_price_ht": 950, "vat_rate": 10},
    {"type": "ouvrage", "category": "Électricité", "designation": "Mise aux normes NF C 15-100", "unit": "forfait", "unit_price_ht": 1500, "vat_rate": 10},
    # --- Plomberie / Sanitaire ---
    {"type": "ouvrage", "category": "Plomberie", "designation": "Alimentation + évacuation point d'eau", "unit": "u", "unit_price_ht": 180, "vat_rate": 10},
    {"type": "ouvrage", "category": "Plomberie", "designation": "Pose WC suspendu (bâti-support)", "unit": "u", "unit_price_ht": 350, "vat_rate": 10},
    {"type": "ouvrage", "category": "Plomberie", "designation": "Création douche à l'italienne", "unit": "ens", "unit_price_ht": 1200, "vat_rate": 10},
    {"type": "ouvrage", "category": "Plomberie", "designation": "Pose lavabo / vasque", "unit": "u", "unit_price_ht": 220, "vat_rate": 10},
    {"type": "ouvrage", "category": "Plomberie", "designation": "Chauffe-eau thermodynamique", "unit": "u", "unit_price_ht": 2200, "vat_rate": 10},
    # --- Menuiserie ---
    {"type": "ouvrage", "category": "Menuiserie", "designation": "Fenêtre PVC double vitrage", "unit": "u", "unit_price_ht": 550, "vat_rate": 10},
    {"type": "ouvrage", "category": "Menuiserie", "designation": "Porte-fenêtre aluminium", "unit": "u", "unit_price_ht": 950, "vat_rate": 10},
    {"type": "ouvrage", "category": "Menuiserie", "designation": "Porte intérieure (bloc-porte)", "unit": "u", "unit_price_ht": 280, "vat_rate": 10},
    {"type": "ouvrage", "category": "Menuiserie", "designation": "Volet roulant électrique", "unit": "u", "unit_price_ht": 480, "vat_rate": 10},
    {"type": "ouvrage", "category": "Menuiserie", "designation": "Placard sur mesure", "unit": "ml", "unit_price_ht": 350, "vat_rate": 10},
    # --- Peinture / Revêtements ---
    {"type": "ouvrage", "category": "Peinture / Revêtements", "designation": "Peinture murs 2 couches", "unit": "m²", "unit_price_ht": 28, "vat_rate": 10},
    {"type": "ouvrage", "category": "Peinture / Revêtements", "designation": "Peinture plafond 2 couches", "unit": "m²", "unit_price_ht": 30, "vat_rate": 10},
    {"type": "ouvrage", "category": "Peinture / Revêtements", "designation": "Pose parquet flottant", "unit": "m²", "unit_price_ht": 38, "vat_rate": 10},
    {"type": "ouvrage", "category": "Peinture / Revêtements", "designation": "Pose carrelage sol", "unit": "m²", "unit_price_ht": 55, "vat_rate": 10},
    {"type": "ouvrage", "category": "Peinture / Revêtements", "designation": "Pose faïence murale", "unit": "m²", "unit_price_ht": 60, "vat_rate": 10},
    # --- Toiture / Extérieur ---
    {"type": "ouvrage", "category": "Toiture / Extérieur", "designation": "Réfection couverture tuiles", "unit": "m²", "unit_price_ht": 110, "vat_rate": 10},
    {"type": "ouvrage", "category": "Toiture / Extérieur", "designation": "Zinguerie / gouttières", "unit": "ml", "unit_price_ht": 45, "vat_rate": 10},
    {"type": "ouvrage", "category": "Toiture / Extérieur", "designation": "Ravalement de façade", "unit": "m²", "unit_price_ht": 65, "vat_rate": 10},
    # --- Matériaux (fournitures) ---
    {"type": "materiau", "category": "Matériaux", "designation": "Sac de ciment 35 kg", "unit": "u", "unit_price_ht": 8.5, "vat_rate": 20},
    {"type": "materiau", "category": "Matériaux", "designation": "Plaque de plâtre BA13", "unit": "u", "unit_price_ht": 6.5, "vat_rate": 20},
    {"type": "materiau", "category": "Matériaux", "designation": "Laine de verre 100 mm", "unit": "m²", "unit_price_ht": 9, "vat_rate": 20},
    {"type": "materiau", "category": "Matériaux", "designation": "Peinture acrylique blanche 10 L", "unit": "u", "unit_price_ht": 65, "vat_rate": 20},
    {"type": "materiau", "category": "Matériaux", "designation": "Carrelage grès cérame 60x60", "unit": "m²", "unit_price_ht": 32, "vat_rate": 20},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LibraryItemIn(BaseModel):
    type: str = "ouvrage"
    category: str = ""
    designation: str = ""
    unit: str = "u"
    unit_price_ht: float = Field(default=0.0, ge=0)
    cost_price_ht: float = Field(default=0.0, ge=0)
    vat_rate: float = Field(default=10.0, ge=0, le=100)
    notes: str = ""


def _clean(body: LibraryItemIn) -> dict:
    t = body.type if body.type in ("ouvrage", "materiau") else "ouvrage"
    return {
        "type": t,
        "category": (body.category or "").strip()[:80],
        "designation": (body.designation or "").strip()[:200],
        "unit": (body.unit or "u").strip()[:12],
        "unit_price_ht": round(float(body.unit_price_ht or 0), 2),
        "cost_price_ht": round(float(body.cost_price_ht or 0), 2),
        "vat_rate": float(body.vat_rate if body.vat_rate is not None else 10.0),
        "notes": (body.notes or "").strip()[:500],
    }


async def _seed_if_needed(user: dict) -> None:
    """Insère le catalogue de départ une seule fois par utilisateur."""
    if user.get("library_seeded"):
        return
    now = _now()
    docs = [{
        "item_id": "lib_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        **item,
        "unit_price_ht": round(float(item["unit_price_ht"]), 2),
        "vat_rate": float(item["vat_rate"]),
        "notes": "",
        "source": "starter",
        "created_at": now,
        "updated_at": now,
    } for item in STARTER_CATALOGUE]
    if docs:
        await db.library_items.insert_many(docs)
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$set": {"library_seeded": True}})


SOURCE_LABELS = {"starter": "Catalogue", "devis": "Devis", "dpgf": "DPGF",
                 "import_devis": "Imports", "manual": "Saisie",
                 "assistant_devis": "Assistant IA"}


@router.get("")
async def list_items(q: str = "", type: str = "", category: str = "", source: str = "",
                     user=Depends(current_user)) -> dict:
    await _seed_if_needed(user)
    uid = user["user_id"]
    query: dict = {"user_id": uid}
    if type in ("ouvrage", "materiau"):
        query["type"] = type
    if category.strip():
        query["category"] = category.strip()
    if source.strip():
        query["source"] = source.strip()
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"designation": rx}, {"category": rx}]
    items = await db.library_items.find(query, {"_id": 0}).sort("designation", 1).to_list(5000)
    # Facettes calculées sur TOUTE la bibliothèque (indépendantes des filtres courants).
    meta = await db.library_items.find({"user_id": uid}, {"_id": 0, "category": 1, "source": 1}).to_list(10000)
    cats = sorted({(i.get("category") or "Autre") for i in meta})
    src_counts: dict = {}
    for i in meta:
        s = i.get("source") or "manual"
        src_counts[s] = src_counts.get(s, 0) + 1
    sources = [{"key": k, "label": SOURCE_LABELS.get(k, k.title()), "count": v}
               for k, v in sorted(src_counts.items(), key=lambda x: -x[1])]
    return {"items": items, "count": len(items), "categories": cats, "sources": sources}


def _dedup_key(designation: str, unit: str) -> str:
    """Clé de rapprochement : désignation sans accents/ponctuation/casse + unité."""
    s = unicodedata.normalize("NFKD", (designation or "")).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    s = re.sub(r"\s+", " ", s)
    u = re.sub(r"[^a-z0-9]+", "", (unit or "").lower())
    return f"{s}|{u}"


@router.get("/duplicates")
async def find_duplicates(user=Depends(current_user)) -> dict:
    """Repère les postes très proches (même désignation normalisée + unité) à fusionner."""
    items = await db.library_items.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(10000)
    groups: dict = {}
    for it in items:
        groups.setdefault(_dedup_key(it.get("designation", ""), it.get("unit", "")), []).append(it)
    out = []
    for key, grp in groups.items():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
        out.append({
            "key": key,
            "items": [{"item_id": g["item_id"], "designation": g.get("designation"),
                       "unit": g.get("unit"), "unit_price_ht": g.get("unit_price_ht"),
                       "category": g.get("category"), "source": g.get("source"),
                       "updated_at": g.get("updated_at") or g.get("created_at")} for g in grp],
        })
    out.sort(key=lambda x: len(x["items"]), reverse=True)
    return {"groups": out[:200], "group_count": len(out),
            "duplicate_count": sum(len(g["items"]) - 1 for g in out)}


class MergeIn(BaseModel):
    keep_id: str
    remove_ids: list[str] = []


@router.post("/merge")
async def merge_items(body: MergeIn, user=Depends(current_user)) -> dict:
    """Fusionne un groupe de doublons : conserve un poste, supprime les autres."""
    uid = user["user_id"]
    keep = await db.library_items.find_one({"user_id": uid, "item_id": body.keep_id}, {"_id": 0, "item_id": 1})
    if not keep:
        raise HTTPException(404, "Poste conservé introuvable")
    to_remove = [i for i in body.remove_ids if i != body.keep_id][:200]
    res = await db.library_items.delete_many({"user_id": uid, "item_id": {"$in": to_remove}})
    return {"ok": True, "removed": res.deleted_count}


@router.post("/merge-all")
async def merge_all_duplicates(user=Depends(current_user)) -> dict:
    """Fusion automatique de tous les groupes : garde le poste le plus récent de chaque groupe."""
    uid = user["user_id"]
    items = await db.library_items.find({"user_id": uid}, {"_id": 0}).to_list(10000)
    groups: dict = {}
    for it in items:
        groups.setdefault(_dedup_key(it.get("designation", ""), it.get("unit", "")), []).append(it)
    remove: list[str] = []
    for grp in groups.values():
        if len(grp) < 2:
            continue
        grp.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)
        remove += [g["item_id"] for g in grp[1:]]
    if not remove:
        return {"ok": True, "removed": 0}
    res = await db.library_items.delete_many({"user_id": uid, "item_id": {"$in": remove}})
    return {"ok": True, "removed": res.deleted_count}

@router.get("/learned")
async def list_learned(limit: int = 100, user=Depends(current_user)) -> dict:
    """Ouvrages auto-ajoutés avec un prix ESTIMÉ (IA/web), en attente de validation."""
    uid = user["user_id"]
    rows = await db.library_items.find(
        {"user_id": uid, "estimated": True},
        {"_id": 0, "item_id": 1, "designation": 1, "unit": 1, "unit_price_ht": 1,
         "vat_rate": 1, "category": 1, "price_source": 1, "updated_at": 1},
    ).sort("updated_at", -1).to_list(max(1, min(limit, 500)))
    return {"items": rows, "count": len(rows)}


class ValidateIn(BaseModel):
    unit_price_ht: float | None = None


@router.post("/{item_id}/validate")
async def validate_learned(item_id: str, body: ValidateIn, user=Depends(current_user)) -> dict:
    """Valide un prix estimé en un clic : il devient un tarif ferme (révisable)."""
    uid = user["user_id"]
    set_fields = {"estimated": False, "price_source": "validated", "updated_at": _now()}
    if body.unit_price_ht is not None and body.unit_price_ht >= 0:
        set_fields["unit_price_ht"] = round(float(body.unit_price_ht), 2)
    res = await db.library_items.update_one(
        {"user_id": uid, "item_id": item_id}, {"$set": set_fields})
    if not res.matched_count:
        raise HTTPException(404, "Élément introuvable")
    return await db.library_items.find_one({"user_id": uid, "item_id": item_id}, {"_id": 0})




@router.post("")
async def create_item(body: LibraryItemIn, user=Depends(current_user)) -> dict:
    data = _clean(body)
    if not data["designation"]:
        raise HTTPException(400, "La désignation est obligatoire")
    doc = {
        "item_id": "lib_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        **data,
        "source": "manual",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.library_items.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.put("/{item_id}")
async def update_item(item_id: str, body: LibraryItemIn,
                      user=Depends(current_user)) -> dict:
    data = _clean(body)
    if not data["designation"]:
        raise HTTPException(400, "La désignation est obligatoire")
    res = await db.library_items.update_one(
        {"item_id": item_id, "user_id": user["user_id"]},
        {"$set": {**data, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Élément introuvable")
    doc = await db.library_items.find_one(
        {"item_id": item_id, "user_id": user["user_id"]}, {"_id": 0})
    return doc


@router.delete("/{item_id}")
async def delete_item(item_id: str, user=Depends(current_user)) -> dict:
    res = await db.library_items.delete_one(
        {"item_id": item_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Élément introuvable")
    return {"ok": True}


@router.post("/reset-catalogue")
async def reset_catalogue(user=Depends(current_user)) -> dict:
    """Réinsère le catalogue de départ (utile si l'utilisateur a tout supprimé)."""
    await db.users.update_one({"user_id": user["user_id"]},
                              {"$unset": {"library_seeded": ""}})
    fresh = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    await _seed_if_needed(fresh or user)
    count = await db.library_items.count_documents({"user_id": user["user_id"]})
    return {"ok": True, "count": count}



def _norm_key(desig: str, unit: str) -> str:
    s = unicodedata.normalize("NFKD", (desig or "").replace("œ", "oe"))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    return f"{s}|{(unit or '').strip().lower()}"


async def _learn_global(desig: str, unit: str, price: float, estimated: bool) -> None:
    """Pool mutualisé (dé-identifié) ConstruPilot : repli de prix inter-comptes.

    Ne stocke ni user_id ni client : seulement désignation, unité et prix agrégé (médiane).
    """
    key = _norm_key(desig, unit)
    doc = await db.library_global_auto.find_one({"key": key}, {"_id": 0, "prices": 1})
    prices = ((doc or {}).get("prices") or []) + [round(float(price), 2)]
    prices = prices[-30:]
    s = sorted(prices)
    n = len(s)
    median = s[n // 2] if n % 2 else round((s[n // 2 - 1] + s[n // 2]) / 2, 2)
    await db.library_global_auto.update_one({"key": key}, {
        "$set": {"key": key, "designation": desig, "unit": unit or "u",
                 "unit_price_ht": median, "prices": prices, "updated_at": _now()},
        "$inc": {"contributions": 1, "estimated_count": 1 if estimated else 0,
                 "firm_count": 0 if estimated else 1},
        "$setOnInsert": {"created_at": _now()}}, upsert=True)


async def auto_save_from_lines(user_id: str, lines: list[dict], source: str = "devis") -> int:
    """Conserve les prix renseignés dans la seule bibliothèque de l'entreprise.

    Un devis privé n'autorise pas une publication inter-comptes. Les estimations
    IA et lignes incomplètes ne deviennent pas des références par répétition.
    """
    saved = 0
    for ln in lines or []:
        if ln.get("price_missing") or ln.get("price_estimated") or ln.get("quantity_missing"):
            continue  # aucune donnée de prix à apprendre
        price = round(float(ln.get("unit_price_ht") or 0), 2)
        if price <= 0:
            continue
        desig = (ln.get("designation") or "").strip()
        if len(desig) < 3:
            continue
        cat = (ln.get("category") or "").strip()
        if cat.lower().startswith("situation") or cat.lower().startswith("avancement"):
            continue  # on n'archive pas les lignes de situation
        estimated = bool(ln.get("price_estimated"))
        unit = ln.get("unit") or "u"
        existing = await db.library_items.find_one(
            {"user_id": user_id, "designation": {"$regex": f"^{re.escape(desig)}$", "$options": "i"}},
            {"_id": 0, "item_id": 1, "estimated": 1})
        set_fields = {
            "designation": desig, "type": "ouvrage",
            "category": cat or ("Estimé IA" if estimated else "Depuis devis"),
            "unit": unit, "unit_price_ht": price,
            "vat_rate": float(ln["vat_rate"]) if ln.get("vat_rate") is not None else None, "estimated": estimated,
            "price_source": ln.get("price_source") or ("assistant_estimate" if estimated else source),
            "updated_at": _now(),
        }
        if float(ln.get("cost_price_ht") or 0) > 0:
            set_fields["cost_price_ht"] = round(float(ln["cost_price_ht"]), 2)
        desc = (ln.get("description") or ln.get("notes") or "").strip()
        if desc:
            set_fields["notes"] = desc[:500]
        if existing:
            await db.library_items.update_one(
                {"user_id": user_id, "item_id": existing["item_id"]}, {"$set": set_fields})
        else:
            await db.library_items.insert_one({
                "item_id": "lib_" + secrets.token_hex(6), "user_id": user_id,
                "source": source, "notes": set_fields.pop("notes", ""),
                "created_at": _now(), **set_fields,
            })
        saved += 1
    return saved



# ========= Reprise d'anciens devis (PDF Tolteck, Obat, Excel→PDF…) → bibliothèque =========

@router.post("/import-pdf/preview")
async def library_import_preview(files: list[UploadFile] = File(...),
                                 user=Depends(current_user)) -> dict:
    """Étape 1 : extrait les ouvrages + prix de vos anciens devis (IA), sans rien créer."""
    from routes.documents import _extract_pdf_item
    if not files:
        raise HTTPException(400, "Aucun fichier fourni")
    existing = await db.library_items.find(
        {"user_id": user["user_id"]}, {"_id": 0, "designation": 1, "unit_price_ht": 1}).to_list(5000)
    known = {(e.get("designation") or "").strip().lower(): e.get("unit_price_ht") for e in existing}
    items: list[dict] = []
    for f in files[:20]:
        name = f.filename or "document.pdf"
        try:
            doc = await _extract_pdf_item(f)
        except Exception as e:  # noqa: BLE001
            items.append({"file": name, "ok": False, "error": str(e)[:200], "lines": []})
            continue
        lines = []
        for l in doc.get("lines") or []:
            desig = (l.get("designation") or "").strip()
            if len(desig) < 3 or float(l.get("unit_price_ht") or 0) <= 0:
                continue
            lines.append({
                "designation": desig[:200], "unit": l.get("unit") or "u",
                "unit_price_ht": round(float(l["unit_price_ht"]), 2),
                "vat_rate": float(l.get("vat_rate") or 10),
                "category": (doc.get("title") or "Repris de mes devis")[:80],
                "existing_price": known.get(desig.lower()),
            })
        items.append({"file": name, "ok": True, "number": doc.get("number") or "",
                      "issue_date": doc.get("issue_date") or "", "lines": lines})
    return {"ok": True, "items": items,
            "line_count": sum(len(i["lines"]) for i in items)}


class LibraryImportIn(BaseModel):
    lines: list[dict]
    category: str = ""


@router.post("/import-pdf/confirm")
async def library_import_confirm(body: LibraryImportIn, user=Depends(current_user)) -> dict:
    """Étape 2 : crée / met à jour les ouvrages sélectionnés à VOS prix."""
    created = updated = 0
    cat_override = (body.category or "").strip()[:80]
    for l in (body.lines or [])[:500]:
        desig = (l.get("designation") or "").strip()
        pu = float(l.get("unit_price_ht") or 0)
        if len(desig) < 3 or pu <= 0:
            continue
        fields = {
            "designation": desig[:200], "type": "ouvrage",
            "category": cat_override or (l.get("category") or "Repris de mes devis")[:80],
            "unit": (l.get("unit") or "u")[:12], "unit_price_ht": round(pu, 2),
            "vat_rate": float(l.get("vat_rate") or 10), "updated_at": _now(),
        }
        if float(l.get("cost_price_ht") or 0) > 0:
            fields["cost_price_ht"] = round(float(l["cost_price_ht"]), 2)
        existing = await db.library_items.find_one(
            {"user_id": user["user_id"],
             "designation": {"$regex": f"^{re.escape(desig)}$", "$options": "i"}},
            {"_id": 0, "item_id": 1})
        if existing:
            await db.library_items.update_one({"user_id": user["user_id"], "item_id": existing["item_id"]},
                                              {"$set": fields})
            updated += 1
        else:
            await db.library_items.insert_one({
                "item_id": "lib_" + secrets.token_hex(6), "user_id": user["user_id"],
                "source": "import_devis", "notes": "", "created_at": _now(), **fields})
            created += 1
    return {"ok": True, "created": created, "updated": updated}
