"""Tool Presets — Modèles réutilisables inspirés de QuoterPlan (Vague B).

Un modèle regroupe un type d'ouvrage + ses paramètres par défaut :
- Mur extérieur porteur 20 cm
- Isolant combles laine de roche 200 mm R=6
- Cloison BA13 72/48 avec laine minérale 45 mm
- Sol carrelage grès cérame 60x60 antidérapant
- Peinture mate blanche 2 couches
- Ossature bois montant 45×145 entraxe 60 cm

L'utilisateur applique un preset lors du dessin d'une pièce / ouverture / compteur
pour pré-remplir label + unité + prix + notes techniques.
"""
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user

router = APIRouter(prefix="/tool-presets", tags=["tool-presets"])


# Types d'ouvrages canoniques — permettent au frontend de filtrer les presets
# pertinents pour l'outil en cours (mur → wall, pièce → floor/paint/ceiling, etc.).
KNOWN_PRESET_KINDS = {
    "wall", "opening", "floor", "ceiling", "paint",
    "insulation", "counter", "roof", "note", "other",
}


class ToolPresetIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: str = Field(default="other")  # wall / opening / floor / paint / insulation / …
    unit: str = Field(default="u", max_length=12)  # u / m² / m / ml / kg / L
    color: str = Field(default="#f97316")
    price_per_unit: float | None = None
    params: dict = Field(default_factory=dict)  # libre — thickness_mm, r_value, etc.
    notes: str | None = None


class ToolPreset(ToolPresetIn):
    preset_id: str
    user_id: str
    created_at: str


def _normalize(body: ToolPresetIn) -> dict:
    kind = body.kind if body.kind in KNOWN_PRESET_KINDS else "other"
    return {
        "name": body.name.strip(),
        "kind": kind,
        "unit": body.unit.strip() or "u",
        "color": body.color or "#f97316",
        "price_per_unit": body.price_per_unit,
        "params": body.params or {},
        "notes": (body.notes or "").strip() or None,
    }


@router.get("")
async def list_presets(user=Depends(current_user)) -> dict:
    """Renvoie tous les presets de l'utilisateur, triés par nom."""
    cursor = db.tool_presets.find({"user_id": user["user_id"]}, {"_id": 0}).sort("name", 1)
    return {"presets": await cursor.to_list(200)}


@router.post("")
async def create_preset(body: ToolPresetIn, user=Depends(current_user)):
    doc = {
        "preset_id": "tpr_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        **_normalize(body),
    }
    await db.tool_presets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.patch("/{preset_id}")
async def update_preset(preset_id: str, body: ToolPresetIn, user=Depends(current_user)):
    res = await db.tool_presets.update_one(
        {"preset_id": preset_id, "user_id": user["user_id"]},
        {"$set": _normalize(body)},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Modelo não encontrado")
    doc = await db.tool_presets.find_one(
        {"preset_id": preset_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    return doc


@router.delete("/{preset_id}")
async def delete_preset(preset_id: str, user=Depends(current_user)) -> dict:
    res = await db.tool_presets.delete_one(
        {"preset_id": preset_id, "user_id": user["user_id"]}
    )
    if res.deleted_count == 0:
        raise HTTPException(404, "Modelo não encontrado")
    return {"ok": True}


@router.post("/seed-defaults")
async def seed_default_presets(user=Depends(current_user)) -> dict:
    """Crée les 6 presets d'usine si l'utilisateur n'en a aucun (utile onboarding)."""
    existing = await db.tool_presets.count_documents({"user_id": user["user_id"]})
    if existing > 0:
        return {"ok": True, "created": 0, "already_had": existing}
    defaults = [
        {"name": "Parede ext. resistente 20 cm", "kind": "wall", "unit": "m²",
         "color": "#0ea5e9", "price_per_unit": 85.0,
         "params": {"thickness_mm": 200, "material": "parpaing"}},
        {"name": "Divisória em pladur 72/48 + lã 45 mm", "kind": "wall", "unit": "m²",
         "color": "#22c55e", "price_per_unit": 42.0,
         "params": {"thickness_mm": 72, "material": "placo", "insulation_r": 1.25}},
        {"name": "Isolamento do desvão em lã de rocha 200 mm", "kind": "insulation", "unit": "m²",
         "color": "#a855f7", "price_per_unit": 18.5,
         "params": {"thickness_mm": 200, "r_value": 5.0}},
        {"name": "Pavimento em grés porcelânico 60×60", "kind": "floor", "unit": "m²",
         "color": "#f97316", "price_per_unit": 55.0,
         "params": {"format_cm": "60x60", "antidérapant": True}},
        {"name": "Pintura mate branca 2 demãos", "kind": "paint", "unit": "m²",
         "color": "#eab308", "price_per_unit": 12.5,
         "params": {"coats": 2, "finish": "mate"}},
        {"name": "Estrutura de madeira 45×145 afastamento 60", "kind": "wall", "unit": "ml",
         "color": "#8b5cf6", "price_per_unit": 9.0,
         "params": {"section_mm": "45x145", "spacing_cm": 60}},
    ]
    now = datetime.now(timezone.utc).isoformat()
    docs = [{
        "preset_id": "tpr_" + secrets.token_hex(6),
        "user_id": user["user_id"], "created_at": now,
        "notes": None, **d,
    } for d in defaults]
    await db.tool_presets.insert_many(docs)
    for d in docs:
        d.pop("_id", None)
    return {"ok": True, "created": len(docs), "presets": docs}
