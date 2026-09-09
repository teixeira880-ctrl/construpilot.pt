"""Bibliothèque perso — ouvrages & matériaux avec prix définis par l'entreprise.

- Catalogue de départ pré-rempli (seed une seule fois par utilisateur).
- Réutilisable dans l'éditeur de devis (étape suivante).
- CRUD complet ; chaque nouvel ouvrage saisi est enregistré dans la bibliothèque perso.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
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
    # --- Piscinas (mercado PT-PT, IVA 23%) ---
    {"type": "ouvrage", "category": "Piscinas", "designation": "Escavação de piscina (movimentação de terras)", "unit": "m³", "unit_price_ht": 25, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Betão armado — paredes + fundo", "unit": "m³", "unit_price_ht": 220, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Cofragem e ferro para piscina", "unit": "m²", "unit_price_ht": 55, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Impermeabilização com betão hidrófugo", "unit": "m²", "unit_price_ht": 35, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Impermeabilização com tela armada (liner)", "unit": "m²", "unit_price_ht": 45, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Revestimento em mosaico vítreo", "unit": "m²", "unit_price_ht": 90, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Revestimento em azulejo cerâmico antiderrapante", "unit": "m²", "unit_price_ht": 55, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Skimmer com regulador de nível (fornecimento e instalação)", "unit": "u", "unit_price_ht": 180, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Retorno / bocal de aspiração", "unit": "u", "unit_price_ht": 65, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Sistema de filtração — bomba + filtro de areia (piscina até 50 m³)", "unit": "u", "unit_price_ht": 850, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Sistema de filtração — piscina 50–100 m³", "unit": "u", "unit_price_ht": 1400, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Iluminação LED subaquática (foco RGB)", "unit": "u", "unit_price_ht": 220, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Escada em inox 316L (3 degraus)", "unit": "u", "unit_price_ht": 350, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Escada em inox 316L (4 degraus)", "unit": "u", "unit_price_ht": 450, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Cobertura / manta térmica isotérmica", "unit": "m²", "unit_price_ht": 18, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Deck em madeira termotratada (pinho/afzélia)", "unit": "m²", "unit_price_ht": 95, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Deck em microcimento antiderrapante", "unit": "m²", "unit_price_ht": 70, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Bomba de calor para piscina (aquecimento)", "unit": "u", "unit_price_ht": 2200, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Sistema de tratamento salino (eletrólise)", "unit": "u", "unit_price_ht": 950, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Piscina pré-fabricada em fibra de vidro (chave na mão)", "unit": "u", "unit_price_ht": 12000, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Piscina em betão projetado (gunite/shotcrete)", "unit": "m²", "unit_price_ht": 180, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Piscina transbordante (infinity edge) — extra de execução", "unit": "ml", "unit_price_ht": 350, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Duche exterior (chuveiro solar / inox)", "unit": "u", "unit_price_ht": 380, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Casa das máquinas (construção + equipamento base)", "unit": "u", "unit_price_ht": 3500, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Alarme perimetral de segurança piscina", "unit": "u", "unit_price_ht": 550, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Vedação de segurança removível", "unit": "ml", "unit_price_ht": 85, "vat_rate": 23},
    {"type": "ouvrage", "category": "Piscinas", "designation": "Piscina biológica / natural — extra de execução", "unit": "m²", "unit_price_ht": 250, "vat_rate": 23},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LibraryItemIn(BaseModel):
    type: str = "ouvrage"
    category: str = ""
    designation: str = ""
    unit: str = "u"
    unit_price_ht: float = Field(default=0.0, ge=0)
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


@router.get("")
async def list_items(q: str = "", type: str = "", user=Depends(current_user)) -> dict:
    await _seed_if_needed(user)
    query: dict = {"user_id": user["user_id"]}
    if type in ("ouvrage", "materiau"):
        query["type"] = type
    if q.strip():
        rx = {"$regex": q.strip(), "$options": "i"}
        query["$or"] = [{"designation": rx}, {"category": rx}]
    items = await db.library_items.find(query, {"_id": 0}).sort("designation", 1).to_list(5000)
    cats = sorted({(i.get("category") or "Autre") for i in items})
    return {"items": items, "count": len(items), "categories": cats}


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



async def auto_save_from_lines(user_id: str, lines: list[dict]) -> int:
    """Enregistre/actualise automatiquement les postes d'un devis dans la bibliothèque de l'entreprise."""
    saved = 0
    for ln in lines or []:
        desig = (ln.get("designation") or "").strip()
        if len(desig) < 3:
            continue
        cat = (ln.get("category") or "").strip()
        if cat.lower().startswith("situation") or cat.lower().startswith("avancement"):
            continue  # on n'archive pas les lignes de situation
        set_fields = {
            "designation": desig,
            "type": "ouvrage",
            "category": cat or "Depuis devis",
            "unit": ln.get("unit") or "u",
            "unit_price_ht": round(float(ln.get("unit_price_ht") or 0), 2),
            "vat_rate": float(ln.get("vat_rate") or 10),
            "updated_at": _now(),
        }
        desc = (ln.get("description") or ln.get("notes") or "").strip()
        if desc:
            set_fields["notes"] = desc[:500]
        existing = await db.library_items.find_one(
            {"user_id": user_id,
             "designation": {"$regex": f"^{re.escape(desig)}$", "$options": "i"}},
            {"_id": 0, "item_id": 1})
        if existing:
            await db.library_items.update_one(
                {"user_id": user_id, "item_id": existing["item_id"]}, {"$set": set_fields})
        else:
            await db.library_items.insert_one({
                "item_id": "lib_" + secrets.token_hex(6), "user_id": user_id,
                "source": "devis", "notes": set_fields.pop("notes", ""),
                "created_at": _now(), **set_fields,
            })
        saved += 1
    return saved
