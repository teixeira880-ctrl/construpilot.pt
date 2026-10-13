"""AI/CV analysis + rooms + measurements + takeoff + materials + history + compare.

Refactor iter53 : extrait de `routes/plans.py`.
"""
from __future__ import annotations

import json
import logging
import secrets
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import ai as ai_engine
from engines import geometry as G
from engines.plan_quantities import (
    recompute_room as _recompute_room, recompute_linear_sets as _recompute_linear_sets,
    _measure_gross_m,
)
from engines import plan_texts as T
from engines.plan_ai import analyze_plan_image
from engines.plan_cv import detect_all_rooms, detect_walls, flood_fill_room
from engines.plan_structure import detect_structure_tiled, refine_structure
from engines.plan_processor import auto_calibration_from_pdf_scale

from routes.plans_common import (
    _diff_rooms, _now, _snapshot, _resolve_branding, _apply_new_calibration, router,
)

logger = logging.getLogger(__name__)


# ============ RÉGLAGES BÉTON PAR DÉFAUT (entreprise) ============

_BETON_DEFAULTS = {"wall_height": 2.5, "dalle_ep": 0.20, "voile_ep": 0.20,
                   "poutre_l": 0.20, "poutre_h": 0.40, "acier_price_kg": 0.0,
                   "beton_price_m3": 0.0, "labor_price_m3": 0.0, "margin_pct": 0.0,
                   "proprete_ep": 0.05, "beton_prices": {},
                   "last_preset": ""}

# Prix indicatifs marché FR — repli quand l'utilisateur n'a rien configuré,
# afin que le chiffrage se fasse toujours automatiquement après l'analyse.
_FALLBACK_BETON_PRICE_M3 = 130.0   # BPE livré
_FALLBACK_ACIER_PRICE_KG = 1.30    # acier HA façonné/posé
_FALLBACK_LABOR_PRICE_M3 = 400.0   # coffrage + coulage + ferraillage
_FALLBACK_MARGIN_PCT = 15.0        # marge commerciale


def _with_default_prices(beton_price_m3: float, acier_price_kg: float,
                         labor_price_m3: float, margin_pct: float,
                         margins_set: bool = False):
    """Applique des prix indicatifs si aucun n'est renseigné (valeur <= 0)."""
    if not beton_price_m3 or beton_price_m3 <= 0:
        beton_price_m3 = _FALLBACK_BETON_PRICE_M3
    if not acier_price_kg or acier_price_kg <= 0:
        acier_price_kg = _FALLBACK_ACIER_PRICE_KG
    if not labor_price_m3 or labor_price_m3 <= 0:
        labor_price_m3 = _FALLBACK_LABOR_PRICE_M3
    if (not margin_pct or margin_pct <= 0) and not margins_set:
        margin_pct = _FALLBACK_MARGIN_PCT
    return beton_price_m3, acier_price_kg, labor_price_m3, margin_pct

# Presets intégrés proposés par type de chantier
_BETON_BUILTIN_PRESETS = [
    {"name": "Maison", "builtin": True, "wall_height": 2.5, "dalle_ep": 0.16,
     "voile_ep": 0.20, "poutre_l": 0.20, "poutre_h": 0.40, "acier_price_kg": 0.0, "beton_price_m3": 0.0,
     "acier_ratios": {"semelles": 40, "poteaux": 110, "poutres": 120, "dalles": 80, "voiles": 55}},
    {"name": "Immeuble", "builtin": True, "wall_height": 2.7, "dalle_ep": 0.20,
     "voile_ep": 0.20, "poutre_l": 0.25, "poutre_h": 0.50, "acier_price_kg": 0.0, "beton_price_m3": 0.0,
     "acier_ratios": {"semelles": 45, "poteaux": 140, "poutres": 150, "dalles": 90, "voiles": 70}},
]


@router.get("/settings/beton-defaults")
async def get_beton_defaults(user=Depends(current_user)) -> dict:
    """Réglages béton préférés de l'entreprise (ratios aciers + sections poutres + épaisseurs)."""
    d = await db.beton_defaults.find_one({"user_id": user["user_id"]}, {"_id": 0, "user_id": 0})
    if not d:
        return {**_BETON_DEFAULTS, "acier_ratios": dict(ACIER_RATIOS)}
    d.setdefault("acier_price_kg", 0.0)
    d.setdefault("beton_price_m3", 0.0)
    d.setdefault("labor_price_m3", 0.0)
    d.setdefault("margin_pct", 0.0)
    d.setdefault("proprete_ep", 0.05)
    d.setdefault("beton_prices", {})
    d.setdefault("plancher_type", "auto")
    d.setdefault("plancher_price_m2", 0.0)
    d.setdefault("last_preset", "")
    return d


class BetonDefaultsIn(BaseModel):
    wall_height: float = 2.5
    dalle_ep: float = 0.20
    voile_ep: float = 0.20
    poutre_l: float = 0.20
    poutre_h: float = 0.40
    acier_price_kg: float = 0.0
    beton_price_m3: float = 0.0
    labor_price_m3: float = 0.0
    margin_pct: float = 0.0
    proprete_ep: float = 0.05
    plancher_type: str = "auto"
    plancher_price_m2: float = 0.0
    beton_prices: dict = Field(default_factory=dict)
    acier_ratios: dict = Field(default_factory=dict)


@router.put("/settings/beton-defaults")
async def set_beton_defaults(body: BetonDefaultsIn, user=Depends(current_user)) -> dict:
    ar = {k: float(body.acier_ratios.get(k, ACIER_RATIOS[k])) for k in ACIER_RATIOS}
    _elems = ("semelles", "proprete", "poteaux", "poutres", "dalles", "voiles")
    bp = {k: max(0.0, float(body.beton_prices.get(k) or 0)) for k in _elems if body.beton_prices.get(k) is not None}
    payload = {"wall_height": body.wall_height, "dalle_ep": body.dalle_ep,
               "voile_ep": body.voile_ep, "poutre_l": body.poutre_l,
               "poutre_h": body.poutre_h, "acier_price_kg": max(0.0, body.acier_price_kg),
               "beton_price_m3": max(0.0, body.beton_price_m3),
               "labor_price_m3": max(0.0, body.labor_price_m3),
               "margin_pct": max(0.0, body.margin_pct),
               "proprete_ep": max(0.0, body.proprete_ep), "beton_prices": bp,
               "plancher_type": (body.plancher_type if body.plancher_type in ("auto", "dalle_pleine", "poutrelles_hourdis") else "auto"),
               "plancher_price_m2": max(0.0, body.plancher_price_m2),
               "acier_ratios": ar}
    await db.beton_defaults.update_one(
        {"user_id": user["user_id"]},
        {"$set": {**payload, "user_id": user["user_id"]}}, upsert=True)
    return {"ok": True, **payload}


class LastPresetIn(BaseModel):
    name: str = ""


@router.put("/settings/beton-last-preset")
async def set_beton_last_preset(body: LastPresetIn, user=Depends(current_user)) -> dict:
    await db.beton_defaults.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "last_preset": (body.name or "").strip()[:40]}},
        upsert=True)
    return {"ok": True}


@router.get("/settings/beton-presets")
async def list_beton_presets(user=Depends(current_user)) -> dict:
    """Jeux de réglages béton nommés (intégrés + personnalisés) à choisir selon le projet."""
    saved = await db.beton_presets.find(
        {"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).to_list(100)
    return {"presets": [*_BETON_BUILTIN_PRESETS, *saved]}


class BetonPresetIn(BaseModel):
    name: str
    wall_height: float = 2.5
    dalle_ep: float = 0.20
    voile_ep: float = 0.20
    poutre_l: float = 0.20
    poutre_h: float = 0.40
    acier_price_kg: float = 0.0
    beton_price_m3: float = 0.0
    labor_price_m3: float = 0.0
    margin_pct: float = 0.0
    acier_ratios: dict = Field(default_factory=dict)


@router.put("/settings/beton-presets")
async def save_beton_preset(body: BetonPresetIn, user=Depends(current_user)) -> dict:
    name = (body.name or "").strip()[:40]
    if not name:
        raise HTTPException(400, "Nom du réglage requis")
    if name.lower() in ("maison", "immeuble"):
        raise HTTPException(400, "Ce nom est réservé — choisissez-en un autre")
    ar = {k: float(body.acier_ratios.get(k, ACIER_RATIOS[k])) for k in ACIER_RATIOS}
    payload = {"name": name, "wall_height": body.wall_height, "dalle_ep": body.dalle_ep,
               "voile_ep": body.voile_ep, "poutre_l": body.poutre_l, "poutre_h": body.poutre_h,
               "acier_price_kg": max(0.0, body.acier_price_kg),
               "beton_price_m3": max(0.0, body.beton_price_m3),
               "labor_price_m3": max(0.0, body.labor_price_m3),
               "margin_pct": max(0.0, body.margin_pct), "acier_ratios": ar}
    await db.beton_presets.update_one(
        {"user_id": user["user_id"], "name": name},
        {"$set": {**payload, "user_id": user["user_id"]}}, upsert=True)
    return {"ok": True, **payload}


@router.delete("/settings/beton-presets/{name}")
async def delete_beton_preset(name: str, user=Depends(current_user)) -> dict:
    await db.beton_presets.delete_one({"user_id": user["user_id"], "name": name})
    return {"ok": True}


# ============ ANALYSE IA ============

@router.post("/{plan_id}/analyze")
async def analyze_plan(plan_id: str, page_index: int = 0, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    img = pages[page_index].get("image_png_b64")
    if not img:
        raise HTTPException(500, "Image manquante")
    _b = await _resolve_branding(user["user_id"]) or {}
    analysis = await analyze_plan_image(img, "pt" if (_b.get("country") or "").upper() == "PT" else "fr")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"ai_analysis": {**analysis, "page_index": page_index,
                                  "analyzed_at": _now()}, "updated_at": _now()}}
    )
    return analysis


# ============ CALIBRATION PAR COTES & TEXTES (iter62) ============

def _ai_dim_zones(ai: dict | None, page_index: int, page: dict) -> list[dict]:
    """Convertit les bbox normalisées des cotes IA en segments pixels."""
    if not ai or ai.get("page_index") not in (None, page_index):
        return []
    w = page.get("width_px") or 0
    h = page.get("height_px") or 0
    if not w or not h:
        return []
    zones = []
    for d in ai.get("dimension_lines") or []:
        bbox = d.get("bbox_norm")
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            zones.append({"x1": bbox[0] * w, "y1": bbox[1] * h,
                          "x2": bbox[2] * w, "y2": bbox[3] * h})
    return zones








class PageIn(BaseModel):
    page_index: int = Field(default=0, ge=0)


@router.post("/{plan_id}/calibrate/from-cotes")
async def calibrate_from_cotes(plan_id: str, body: PageIn, user=Depends(current_user)) -> dict:
    """Calibration automatique par les traits de cote lus par l'IA (médiane robuste).

    Recalcule immédiatement les surfaces de toutes les pièces de la page.
    """
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages.width_px": 1, "pages.height_px": 1, "ai_analysis": 1, "rooms": 1},
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if body.page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    ai = p.get("ai_analysis") or {}
    if not ai or ai.get("error"):
        raise HTTPException(400, "Lancez d'abord l'Analyse IA du plan")
    if ai.get("page_index") not in (None, body.page_index):
        raise HTTPException(400, "L'Analyse IA porte sur une autre page — relancez-la sur cette page")
    page = pages[body.page_index]
    calib = T.calibration_from_dimension_lines(
        ai.get("dimension_lines") or [],
        page.get("width_px") or 0, page.get("height_px") or 0)
    if not calib:
        raise HTTPException(422, "Aucune cote exploitable sur le plan (valeur + position requises)")
    payload = {
        "pixels_per_meter": calib["pixels_per_meter"],
        "meters_per_pixel": calib["meters_per_pixel"],
        "method": "auto_cotes",
        "confidence": calib["confidence"],
        "samples_used": calib["samples_used"],
        "samples_total": calib["samples_total"],
        "spread_pct": calib["spread_pct"],
        "created_at": _now(),
    }
    rooms_updated = await _apply_new_calibration(plan_id, user["user_id"], body.page_index, payload)
    await _snapshot(plan_id, user["user_id"], "calibrate_auto_cotes",
                    {"page": body.page_index, "ppm": payload["pixels_per_meter"],
                     "samples": calib["samples_used"]})
    return {"ok": True, "page_index": body.page_index, "calibration": payload,
            "rooms_recomputed": rooms_updated, "samples": calib["samples"]}


class ReconcileIn(BaseModel):
    page_index: int = Field(default=0, ge=0)
    apply: bool = False


@router.post("/{plan_id}/calibrate/reconcile")
async def reconcile_surfaces(plan_id: str, body: ReconcileIn, user=Depends(current_user)) -> dict:
    """Contrôle croisé surfaces mesurées ↔ surfaces ÉCRITES sur le plan (IA).

    apply=false : renvoie le diagnostic (écart médian, ppm proposé).
    apply=true : recale l'échelle et recalcule les pièces de la page.
    """
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "calibrations": 1, "ai_analysis": 1, "rooms": 1},
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    if not calib:
        raise HTTPException(400, "Page non calibrée")
    ai = p.get("ai_analysis") or {}
    if not ai or ai.get("error"):
        raise HTTPException(400, "Lancez d'abord l'Analyse IA du plan")
    page_rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == body.page_index]
    if not page_rooms:
        raise HTTPException(400, "Aucune pièce mesurée sur cette page")
    result = T.reconcile_written_surfaces(page_rooms, ai.get("rooms") or [],
                                          calib["pixels_per_meter"])
    if not body.apply or not result.get("can_reconcile"):
        return {"applied": False, **result}
    payload = {
        "pixels_per_meter": result["proposed_ppm"],
        "meters_per_pixel": round(1.0 / result["proposed_ppm"], 8),
        "method": "reconcile_surfaces",
        "confidence": 0.9,
        "based_on_matches": len(result["matches"]),
        "created_at": _now(),
    }
    rooms_updated = await _apply_new_calibration(plan_id, user["user_id"], body.page_index, payload)
    await _snapshot(plan_id, user["user_id"], "calibrate_reconcile",
                    {"page": body.page_index, "ppm": payload["pixels_per_meter"]})
    return {"applied": True, "rooms_recomputed": rooms_updated,
            "calibration": payload, **result}


@router.post("/{plan_id}/apply-ai-texts")
async def apply_ai_texts(plan_id: str, body: PageIn, user=Depends(current_user)):
    """Applique les textes lus sur le plan aux pièces mesurées :
    noms de pièces, matériaux de sol, hauteurs sous plafond, échelle écrite.
    Un snapshot est pris AVANT application (annulable via l'historique).
    """
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages.width_px": 1, "pages.height_px": 1, "pages.dpi": 1,
         "ai_analysis": 1, "rooms": 1, "calibrations": 1},
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    ai = p.get("ai_analysis") or {}
    if not ai or ai.get("error"):
        raise HTTPException(400, "Lancez d'abord l'Analyse IA du plan")

    summary: dict = {"renamed": [], "materials_set": [], "heights_updated": [],
                     "calibration_set": False, "surface_flags": []}
    rooms = p.get("rooms") or []
    page_rooms = [r for r in rooms if r.get("page_index") == body.page_index]
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    ppm = calib.get("pixels_per_meter") if calib else None

    await _snapshot(plan_id, user["user_id"], "apply_ai_texts", {"page": body.page_index})

    pairs = T.match_ai_rooms(page_rooms, ai.get("rooms") or [])
    for pr in pairs:
        room, ai_room = pr["room"], pr["ai"]
        ai_name = (ai_room.get("name") or "").strip()
        if ai_name and T.is_generic_name(room.get("name")):
            summary["renamed"].append({"room_id": room["room_id"],
                                       "from": room.get("name"), "to": ai_name[:60]})
            room["name"] = ai_name[:60]
        mat = ai_room.get("floor_material")
        if mat and not room.get("floor_material"):
            room["floor_material"] = mat
            if ai_room.get("floor_note_text"):
                room["floor_note_text"] = str(ai_room["floor_note_text"])[:120]
            summary["materials_set"].append({"room_id": room["room_id"],
                                             "room_name": room["name"], "material": mat})
        try:
            ai_h = float(ai_room.get("ceiling_height_m") or 0)
        except (TypeError, ValueError):
            ai_h = 0
        cur_h = float(room.get("ceiling_height_m") or 2.5)
        if 1.8 <= ai_h <= 6.0 and abs(ai_h - cur_h) > 0.01 and cur_h == 2.5:
            room["ceiling_height_m"] = ai_h
            if ppm:
                _recompute_room(room, ppm)
            summary["heights_updated"].append({"room_id": room["room_id"],
                                               "room_name": room["name"],
                                               "from": cur_h, "to": ai_h})
        try:
            written = float(ai_room.get("surface_written_m2") or 0)
        except (TypeError, ValueError):
            written = 0
        measured = float(room.get("surface_m2") or 0)
        if written > 0 and measured > 0:
            delta_pct = round((written / measured - 1) * 100, 1)
            room["surface_written_m2"] = written
            room["surface_delta_pct"] = delta_pct
            if abs(delta_pct) > 5:
                summary["surface_flags"].append({"room_id": room["room_id"],
                                                 "room_name": room["name"],
                                                 "measured_m2": round(measured, 2),
                                                 "written_m2": written,
                                                 "delta_pct": delta_pct})

    updates: dict = {"rooms": rooms, "updated_at": _now()}

    # Échelle écrite (« 1:100 ») → calibration si la page n'en a pas
    if not calib and ai.get("detected_scale"):
        from engines.plan_processor import _detect_scale_from_text
        detected_scale = _detect_scale_from_text(str(ai["detected_scale"]))
        pages = p.get("pages") or []
        if detected_scale and body.page_index < len(pages) and not pages[body.page_index].get("auto_calibration_blocked"):
            dpi = pages[body.page_index].get("dpi") or 150
            ppm_scale = auto_calibration_from_pdf_scale(detected_scale, dpi)
            if ppm_scale:
                updates[f"calibrations.{body.page_index}"] = {
                    "pixels_per_meter": ppm_scale,
                    "method": "ai_scale_text",
                    "scale_denominator": detected_scale,
                    "confidence": 0.7, "created_at": _now(),
                }
                summary["calibration_set"] = True

    await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": updates})
    summary["ok"] = True
    summary["rooms_matched"] = len(pairs)
    return summary


# ============ COMPUTER VISION (Phase B) ============

class RoomAutofillIn(BaseModel):
    page_index: int
    seed_x: int = Field(ge=0)
    seed_y: int = Field(ge=0)
    tolerance: int = Field(default=25, ge=1, le=100)


@router.post("/{plan_id}/detect-walls")
async def detect_walls_route(plan_id: str, page_index: int = 0,
                              orthogonal_only: bool = False,
                              user=Depends(current_user)):
    """Détecte automatiquement les segments de murs sur une page via OpenCV Hough.

    Iter62 : filtre les traits de cote (zones cotes IA + zones de texte PDF +
    traits fins isolés) pour ne garder que les vrais murs.
    """
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1, "ai_analysis": 1},
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    page = pages[page_index]
    img = page.get("image_png_b64")
    if not img:
        raise HTTPException(500, "Image manquante")
    dim_zones = _ai_dim_zones(p.get("ai_analysis"), page_index, page)
    text_zones = [t for t in (page.get("text_blocks") or [])
                  if all(k in t for k in ("x", "y", "w", "h"))]
    try:
        result = detect_walls(img, dim_zones=dim_zones, text_zones=text_zones,
                               orthogonal_only=orthogonal_only)
    except Exception as e:
        logger.exception("wall detection failed")
        raise HTTPException(500, f"Détection murs impossible : {e}")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"cv_walls.{page_index}": {**result, "detected_at": _now()},
                  "updated_at": _now()}},
    )
    return result


def _page_dims(page: dict) -> tuple[int, int]:
    w = int(page.get("width_px") or 0)
    h = int(page.get("height_px") or 0)
    if w and h:
        return w, h
    import base64 as _b64
    import io as _io
    from PIL import Image as _Image
    img = _Image.open(_io.BytesIO(_b64.b64decode(page["image_png_b64"])))
    return int(img.width), int(img.height)


@router.post("/{plan_id}/detect-structure")
async def detect_structure_route(plan_id: str, page_index: int = 0,
                                 plan_kind: str | None = None,
                                 user=Depends(current_user)):
    """Détection IA de la structure : murs (rouge) + ouvertures portes/fenêtres.

    Produit un rendu sémantique propre, contrairement à /detect-walls (OpenCV brut).
    plan_kind ("gros_oeuvre"|"maison"|"auto") : force le type d'analyse choisi par l'utilisateur.
    """
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    page = pages[page_index]
    img = page.get("image_png_b64")
    if not img:
        raise HTTPException(500, "Image manquante")
    w, h = _page_dims(page)
    _force = {"gros_oeuvre": "coffrage", "immeuble": "coffrage", "coffrage": "coffrage",
              "maison": "habitation", "habitation": "habitation"}.get((plan_kind or "").lower())
    result = await detect_structure_tiled(img, w, h, force_kind=_force)
    _assign_column_refs(result.get("columns") or [])
    _assign_beam_refs(result.get("beams") or [])
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"structure.{page_index}": {**result, "detected_at": _now()},
                  "updated_at": _now()}})
    return result


class StructureIn(BaseModel):
    walls: list[dict] = Field(default_factory=list)
    openings: list[dict] = Field(default_factory=list)
    beams: list[dict] = Field(default_factory=list)
    floors: list[dict] = Field(default_factory=list)
    columns: list[dict] = Field(default_factory=list)
    footings: list[dict] = Field(default_factory=list)
    reservations: list[dict] = Field(default_factory=list)
    image_width: int | None = None
    image_height: int | None = None


@router.put("/{plan_id}/structure/{page_index}")
async def save_structure_route(plan_id: str, page_index: int, body: StructureIn,
                               user=Depends(current_user)):
    """Sauvegarde la structure éditée manuellement (murs/ouvertures/poutres/planchers)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "plan_id": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    _assign_column_refs(body.columns or [])
    _assign_beam_refs(body.beams or [])
    payload = {
        "walls": body.walls, "openings": body.openings, "beams": body.beams,
        "floors": body.floors, "columns": body.columns, "footings": body.footings,
        "wall_count": len(body.walls), "opening_count": len(body.openings),
        "beam_count": len(body.beams), "floor_count": len(body.floors),
        "column_count": len(body.columns), "footing_count": len(body.footings),
        "image_width": body.image_width, "image_height": body.image_height,
        "edited_at": _now(),
    }
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"structure.{page_index}": payload, "updated_at": _now()}})
    return {"ok": True, **payload}


# ===== ANALYSE COMPLÈTE : descriptif chiffré (planchers, murs, ouvertures, poutres) =====

def _seg_len_px(it: dict) -> float:
    import math
    return math.hypot(it.get("x2", 0) - it.get("x1", 0), it.get("y2", 0) - it.get("y1", 0))


def _assign_column_refs(columns: list) -> list:
    """Numérote les poteaux P1, P2… de haut en bas puis de gauche à droite."""
    def cy(c):
        return (c.get("y1", 0) + c.get("y2", 0)) / 2, (c.get("x1", 0) + c.get("x2", 0)) / 2
    for i, c in enumerate(sorted(columns, key=cy), start=1):
        c["ref"] = f"P{i}"
    return columns


def _assign_beam_refs(beams: list) -> list:
    """Numérote les poutres B1, B2… de haut en bas puis de gauche à droite."""
    def cy(b):
        return (b.get("y1", 0) + b.get("y2", 0)) / 2, (b.get("x1", 0) + b.get("x2", 0)) / 2
    for i, b in enumerate(sorted(beams, key=cy), start=1):
        b["ref"] = f"B{i}"
    return beams


def _polygon_area_px(points: list) -> float:
    """Aire d'un polygone (formule du lacet / shoelace), en pixels²."""
    n = len(points)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = points[i][0], points[i][1]
        x2, y2 = points[(i + 1) % n][0], points[(i + 1) % n][1]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def _page_ppm(p: dict, page_index: int) -> float | None:
    calib = (p.get("calibrations") or {}).get(str(page_index)) or {}
    ppm = calib.get("pixels_per_meter")
    return float(ppm) if ppm else None


# Ratios moyens de ferraillage (kg d'acier par m³ de béton) par type d'élément.
ACIER_RATIOS = {
    "semelles": 40.0,
    "poteaux": 130.0,
    "poutres": 140.0,
    "dalles": 85.0,
    "voiles": 60.0,
}


# Hauteurs usuelles des baies quand le plan ne les donne pas (déduction des vides dans les voiles).
OPENING_DEFAULT_H = {"porte": 2.15, "fenetre": 1.35, "baie": 2.15}


def _point_seg_dist(px: float, py: float, s: dict) -> float:
    import math
    x1, y1, x2, y2 = s.get("x1", 0), s.get("y1", 0), s.get("x2", 0), s.get("y2", 0)
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _host_wall(opening: dict, walls: list) -> dict | None:
    """Mur porteur de l'ouverture : segment le plus proche du milieu de l'ouverture."""
    if not walls:
        return None
    mx = (opening.get("x1", 0) + opening.get("x2", 0)) / 2
    my = (opening.get("y1", 0) + opening.get("y2", 0)) / 2
    return min(walls, key=lambda w: _point_seg_dist(mx, my, w))


def _is_embedded_beam(b: dict, poutre_h: float, dalle_ep: float) -> bool:
    """Bande / poutre noyée : marquée comme telle, ou hauteur ≤ épaisseur de dalle (pas de retombée)."""
    kind = str(b.get("type") or b.get("kind") or "").lower()
    if kind in ("bande_noyee", "noyee", "poutre_noyee", "bn"):
        return True
    h = b.get("height_m") or poutre_h
    return float(h) <= float(dalle_ep) + 1e-9


def _compute_descriptif(structure: dict, ppm: float | None, rooms: list,
                        wall_height: float = 2.5, dalle_ep: float = 0.20,
                        voile_ep: float = 0.20, poutre_l: float = 0.20,
                        poutre_h: float = 0.40, acier_ratios: dict | None = None,
                        floors_only: bool = False, proprete_ep: float = 0.05,
                        arase_inf: float | None = None, arase_sup: float | None = None,
                        semelle_h: float = 0.40) -> dict:
    """Métré gros œuvre selon les règles usuelles du métreur :
    - poutres sous dalle : seule la RETOMBÉE (h − ép. dalle) est comptée, la partie dans la dalle
      est déjà dans le volume de dalle ; bandes noyées (h ≤ ép. dalle) : ml seulement, pas de m³ ;
    - voiles : vides des baies portées par les murs porteurs déduits (largeur × hauteur de baie) ;
    - ratio d'acier affiché = moyenne PONDÉRÉE par les volumes (acier total / béton armé)."""
    from collections import Counter
    # Hauteur des éléments verticaux (voiles/poteaux) : si les arases NGF sont
    # fournies, hauteur = arase supérieure (AS) - arase inférieure (AI) — méthode métreur.
    height_source = "etage"
    if arase_inf not in (None, "") and arase_sup not in (None, "") \
            and float(arase_sup) > float(arase_inf):
        wall_height = round(float(arase_sup) - float(arase_inf), 3)
        height_source = "arases"
    walls = structure.get("walls") or []
    openings = structure.get("openings") or []
    beams = structure.get("beams") or []
    footings = structure.get("footings") or []
    murs_ml = round(sum(_seg_len_px(w) for w in walls) / ppm, 2) if ppm else 0.0
    embedded = [b for b in beams if _is_embedded_beam(b, poutre_h, dalle_ep)]
    dropped = [b for b in beams if not _is_embedded_beam(b, poutre_h, dalle_ep)]
    poutres_ml = round(sum(_seg_len_px(b) for b in dropped) / ppm, 2) if ppm else 0.0
    bandes_ml = round(sum(_seg_len_px(b) for b in embedded) / ppm, 2) if ppm else 0.0
    ouv_ml = round(sum(_seg_len_px(o) for o in openings) / ppm, 2) if ppm else 0.0
    kinds = Counter((o.get("kind") or "fenetre") for o in openings)
    # Planchers : priorité aux polygones de sol détectés par l'IA (sans tracer à la main),
    # sinon repli sur les pièces mesurées manuellement.
    floors = structure.get("floors") or []
    if floors and ppm:
        planchers = round(sum(_polygon_area_px(f.get("points") or []) for f in floors) / (ppm * ppm), 2)
        planchers_source = "auto"
    elif floors_only:
        # Gros œuvre : la surface se réfère UNIQUEMENT aux planchers détectés (pas de repli pièces)
        planchers = 0.0
        planchers_source = "floors_only"
    else:
        planchers = round(sum(r.get("surface_m2", 0) or 0 for r in rooms), 2)
        planchers_source = "rooms"
    porteur_ml = round(sum(_seg_len_px(w) for w in walls if w.get("type") == "porteur") / ppm, 2) if ppm else 0.0
    cloison_ml = round(murs_ml - porteur_ml, 2)
    # ===== Métré BÉTON (m³) — épaisseurs/sections paramétrables =====
    columns = structure.get("columns") or []
    poteaux_table, beams_table = [], []
    if ppm:
        beton_poteaux = 0.0
        for c in columns:
            if not isinstance(c, dict):
                continue
            wm = abs(c.get("x2", 0) - c.get("x1", 0)) / ppm
            dm = abs(c.get("y2", 0) - c.get("y1", 0)) / ppm
            vol = round(wm * dm * wall_height, 3)
            beton_poteaux += vol
            poteaux_table.append({"ref": c.get("ref", ""), "section": f"{wm:.2f}×{dm:.2f} m",
                                  "hauteur_m": round(wall_height, 2), "volume_m3": vol})
        beton_poteaux = round(beton_poteaux, 2)
        beton_poutres = 0.0
        # Une dalle est coulée sur les poutres dès qu'un plancher est métré : on ne compte alors que
        # la retombée (sinon double comptage du volume commun poutre/dalle).
        has_slab = bool(floors) or planchers > 0
        for b in beams:
            spanm = round(_seg_len_px(b) / ppm, 2)
            bw = float(b.get("width_m") or poutre_l)
            bh = float(b.get("height_m") or poutre_h)
            emb = _is_embedded_beam(b, poutre_h, dalle_ep)
            h_count = 0.0 if emb else (max(bh - dalle_ep, 0.0) if has_slab else bh)
            vol = round(spanm * bw * h_count, 3)
            beton_poutres += vol
            beams_table.append({"ref": b.get("ref", ""), "portee_m": spanm, "volume_m3": vol,
                                "type": "bande noyée" if emb else "poutre",
                                "hauteur_comptee_m": round(h_count, 3)})
        beton_poutres = round(beton_poutres, 2)
        # Dalles : épaisseur par dalle si annotée (thickness_cm), sinon dalle_ep global
        beton_dalles = 0.0
        for f in floors:
            area = _polygon_area_px(f.get("points") or []) / (ppm * ppm)
            ep = (f.get("thickness_cm") / 100.0) if f.get("thickness_cm") else dalle_ep
            beton_dalles += area * ep
        beton_dalles = round(beton_dalles if floors else planchers * dalle_ep, 2)
        # Voiles : vides des baies situées dans un mur porteur déduits (largeur × hauteur de baie).
        voiles_vides_m2 = 0.0
        for o in openings:
            host = _host_wall(o, walls)
            if host is None or host.get("type") != "porteur":
                continue
            w_m = _seg_len_px(o) / ppm
            h_m = float(o.get("height_m") or OPENING_DEFAULT_H.get(o.get("kind") or "fenetre", 1.35))
            voiles_vides_m2 += w_m * min(h_m, wall_height)
        voiles_vides_m2 = round(voiles_vides_m2, 2)
        beton_voiles = round(max(porteur_ml * wall_height - voiles_vides_m2, 0.0) * voile_ep, 2)
        semelles = len(footings)
        beton_semelles = round(sum(
            (abs(ft.get("x2", 0) - ft.get("x1", 0)) / ppm) * (abs(ft.get("y2", 0) - ft.get("y1", 0)) / ppm)
            * float(ft.get("height_m") or semelle_h)
            for ft in footings if isinstance(ft, dict)), 2)
        # Béton de propreté sous semelles (épaisseur réglable, non armé)
        beton_proprete = round(sum(
            (abs(ft.get("x2", 0) - ft.get("x1", 0)) / ppm) * (abs(ft.get("y2", 0) - ft.get("y1", 0)) / ppm) * proprete_ep
            for ft in footings if isinstance(ft, dict)), 2)
    else:
        beton_poteaux = beton_poutres = beton_dalles = beton_voiles = beton_semelles = 0.0
        beton_proprete = 0.0
        voiles_vides_m2 = 0.0
        semelles = len(footings)
    beton_total = round(beton_poteaux + beton_poutres + beton_dalles + beton_voiles + beton_semelles, 2)
    # ===== Aciers (ferraillage) — ratios moyens kg/m³ par élément (ajustables) =====
    _ar = {**ACIER_RATIOS, **{k: float(v) for k, v in (acier_ratios or {}).items()
                              if k in ACIER_RATIOS and v is not None}}
    acier_semelles = round(beton_semelles * _ar["semelles"], 1)
    acier_poteaux = round(beton_poteaux * _ar["poteaux"], 1)
    acier_poutres = round(beton_poutres * _ar["poutres"], 1)
    acier_dalles = round(beton_dalles * _ar["dalles"], 1)
    acier_voiles = round(beton_voiles * _ar["voiles"], 1)
    acier_total = round(acier_semelles + acier_poteaux + acier_poutres + acier_dalles + acier_voiles, 1)
    acier_ratio_moyen = round(acier_total / beton_total, 1) if beton_total > 0 else None
    ngf_list = sorted({f.get("ngf") for f in floors if f.get("ngf") is not None})
    return {
        "wall_height_m": round(float(wall_height), 2),
        "height_source": height_source,
        "arase_inf_m": float(arase_inf) if height_source == "arases" else None,
        "arase_sup_m": float(arase_sup) if height_source == "arases" else None,
        "planchers_m2": planchers,
        "planchers_source": planchers_source,
        "planchers_count": len(floors),
        "planchers_ngf": ngf_list,
        "murs_ml": murs_ml, "murs_porteurs_ml": porteur_ml, "cloisons_ml": max(cloison_ml, 0.0),
        "murs_surface_m2": round(murs_ml * wall_height, 2),
        "portes": int(kinds.get("porte", 0)),
        "fenetres": int(kinds.get("fenetre", 0)),
        "baies": int(kinds.get("baie", 0)),
        "ouvertures_total": len(openings),
        "ouvertures_largeur_ml": ouv_ml,
        "huisseries": len(openings),
        "reservations": len(structure.get("reservations") or []),
        "bandes_noyees_ml": bandes_ml,
        "poutres_ml": poutres_ml,
        "voiles_vides_deduits_m2": voiles_vides_m2,
        "acier_ratio_moyen_kg_m3": acier_ratio_moyen,
        "semelle_h_m": round(float(semelle_h), 3),
        "poteaux": len(columns),
        "semelles": semelles,
        "poteaux_table": poteaux_table,
        "beams_table": beams_table,
        "beton_poteaux_m3": beton_poteaux, "beton_poutres_m3": beton_poutres,
        "beton_dalles_m3": beton_dalles, "beton_voiles_m3": beton_voiles,
        "beton_semelles_m3": beton_semelles,
        "beton_proprete_m3": beton_proprete,
        "beton_proprete_ep_m": round(proprete_ep, 3),
        "beton_total_m3": beton_total,
        "acier_semelles_kg": acier_semelles, "acier_poteaux_kg": acier_poteaux,
        "acier_poutres_kg": acier_poutres, "acier_dalles_kg": acier_dalles,
        "acier_voiles_kg": acier_voiles, "acier_total_kg": acier_total,
        "acier_ratios": _ar,
        "beton_dalle_ep_m": round(dalle_ep, 3), "beton_voile_ep_m": round(voile_ep, 3),
        "beton_poutre_section": f"{poutre_l:.2f}×{poutre_h:.2f} m",
        "plan_kind": structure.get("plan_kind") or "habitation",
        "calibrated": bool(ppm),
    }


def _norm_tokens(s: str) -> set:
    import re
    import unicodedata
    s = unicodedata.normalize("NFKD", (s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    stop = {"sur", "des", "les", "de", "la", "le", "et", "en", "pose", "fourniture", "un", "une", "avec"}
    out = set()
    for w in re.split(r"[^a-z0-9]+", s):
        if len(w) >= 3 and w not in stop:
            if len(w) >= 5 and w.endswith("s"):
                w = w[:-1]  # normalise le pluriel (murs->mur, cloisons->cloison)
            out.add(w)
    return out


def _unit_family(unit: str) -> str:
    u = (unit or "").strip().lower()
    if u in ("m²", "m2", "m^2"):
        return "area"
    if u in ("ml", "m", "mètre", "metre", "ml."):
        return "length"
    if u in ("u", "unité", "unite", "pièce", "piece", "pc", "ens", "ensemble", "forfait", "ft", "global", "pt"):
        return "count"
    return u or "?"


_GENERIC = {"complet", "complete", "existant", "existante", "general", "generale", "ensemble", "maison",
            "logement", "interieur", "interieure", "exterieur", "exterieure", "type", "compris", "toute", "tout"}


def _build_index(items: list[dict]) -> dict:
    """Index pondéré (IDF) : les mots très fréquents dans la bibliothèque pèsent moins."""
    import math
    docs = [(_norm_tokens(it.get("designation", "")) - _GENERIC, it) for it in items]
    df: dict[str, int] = {}
    for toks, _ in docs:
        for t in toks:
            df[t] = df.get(t, 0) + 1
    n = max(1, len(docs))
    w = {t: 1.0 + math.log(n / c) for t, c in df.items()}
    return {"docs": docs, "w": w, "default_w": 1.0 + math.log(n)}


def _score(line_toks: set, it_toks: set, idx: dict) -> float:
    import math
    if not line_toks or not it_toks:
        return 0.0
    w = idx["w"]; dw = idx["default_w"]
    inter = sum(w.get(t, dw) for t in line_toks & it_toks)
    if not inter:
        return 0.0
    return inter / math.sqrt(sum(w.get(t, dw) for t in line_toks) * sum(w.get(t, dw) for t in it_toks))


def _candidates(line: dict, idx: dict, same_unit: bool = True, k: int = 6) -> list[tuple[float, dict]]:
    toks = _norm_tokens(line.get("designation", "")) - _GENERIC
    fam = _unit_family(line.get("unit"))
    out = []
    for it_toks, it in idx["docs"]:
        if not it.get("unit_price_ht"):
            continue
        if same_unit and _unit_family(it.get("unit")) != fam:
            continue
        sc = _score(toks, it_toks, idx)
        if sc > 0.15:
            out.append((sc, it))
    out.sort(key=lambda x: -x[0])
    return out[:k]


def _apply(ln: dict, it: dict, source: str) -> None:
    ln["unit_price_ht"] = it["unit_price_ht"]
    if it.get("vat_rate") is not None:
        ln["vat_rate"] = it["vat_rate"]
    if it.get("cost_price_ht"):
        ln["cost_price_ht"] = round(float(it["cost_price_ht"]), 2)
    ln["price_source"] = source
    ln["price_match"] = it.get("designation", "")


async def _ai_pick(pending: list[tuple[dict, list[tuple[float, dict]]]]) -> dict[int, int]:
    """Demande à l'IA de choisir, pour chaque ligne, l'ouvrage de bibliothèque équivalent (ou aucun)."""
    from engines.ai import _complete, _json
    payload = []
    for i, (ln, cands) in enumerate(pending):
        payload.append({"i": i, "ligne": ln.get("designation"), "unite": ln.get("unit"),
                        "candidats": [{"c": j, "designation": it["designation"], "unite": it.get("unit")}
                                      for j, (_, it) in enumerate(cands)]})
    system = ("Tu es un économiste de la construction. Pour chaque ligne de devis, choisis l'ouvrage de la "
              "bibliothèque de prix qui correspond à la MÊME prestation (même nature de travaux et unité compatible). "
              "Si aucun candidat n'est équivalent, réponds -1. Ne choisis jamais un ouvrage d'un autre corps d'état.")
    prompt = ("Lignes et candidats :\n" + json.dumps(payload, ensure_ascii=False)
              + '\n\nRetourne UNIQUEMENT ce JSON : {"choix": [{"i": 0, "c": 2}, ...]} (c = -1 si aucun).')
    data = _json(await _complete(system, prompt, feature="library_match"), {"choix": []})
    out = {}
    for ch in data.get("choix") or []:
        try:
            i, c = int(ch.get("i")), int(ch.get("c"))
        except Exception:
            continue
        if 0 <= i < len(pending) and 0 <= c < len(pending[i][1]):
            out[i] = c
    return out


async def library_hints_for_user(user_id: str) -> list[str]:
    """Désignations « designation (unité) » des bibliothèques actives, pour guider la génération IA."""
    from routes.shared_library import get_shared_items_for_level, resolve_price_level
    u = await db.users.find_one({"user_id": user_id},
                                {"_id": 0, "price_library_mode": 1, "lang": 1, "brand_country": 1}) or {}
    mode = u.get("price_library_mode") or "shared_first"
    is_pt = (u.get("lang") == "pt") or (str(u.get("brand_country") or "").upper() == "PT")
    company = await db.library_items.find({"user_id": user_id}, {"_id": 0, "designation": 1, "unit": 1}).to_list(400)
    shared: list[dict] = []
    if mode != "company_only":
        try:
            shared = await get_shared_items_for_level(await resolve_price_level(user_id), lang="pt" if is_pt else "fr")
        except Exception:  # noqa: BLE001
            shared = []
    ordered = (company + shared) if mode == "company_first" else (shared + company)
    seen, out = set(), []
    for it in ordered:
        d = (it.get("designation") or "").strip()
        if d and d.lower() not in seen:
            seen.add(d.lower())
            out.append(f"{d} ({it.get('unit') or 'u'})")
    return out[:450]


async def _apply_library_prices(user_id: str, lines: list[dict],
                                level_override: str | None = None) -> tuple[list[dict], int]:
    """Chiffre les lignes depuis les bibliothèques de prix.

    Ordre selon `users.price_library_mode` : `shared_first` (défaut : bibliothèque ConstruPilot puis
    bibliothèque entreprise), `company_first`, `company_only`. Matching pondéré (IDF) + même famille
    d'unité ; les lignes restantes sont arbitrées par l'IA parmi les meilleurs candidats.
    """
    from routes.shared_library import get_shared_items_for_level, resolve_price_level
    u = await db.users.find_one({"user_id": user_id},
                                {"_id": 0, "price_library_mode": 1, "lang": 1, "brand_country": 1}) or {}
    mode = u.get("price_library_mode") or "shared_first"
    is_pt = (u.get("lang") == "pt") or (str(u.get("brand_country") or "").upper() == "PT")

    company = await db.library_items.find(
        {"user_id": user_id}, {"_id": 0, "designation": 1, "unit": 1, "unit_price_ht": 1,
                               "vat_rate": 1, "cost_price_ht": 1}).to_list(5000)
    shared: list[dict] = []
    level = None
    if mode != "company_only":
        try:
            level = await resolve_price_level(user_id, level_override)
            shared = await get_shared_items_for_level(level, lang="pt" if is_pt else "fr")
        except Exception as e:  # noqa: BLE001
            logger.warning("Bibliothèque partagée indisponible (%s): %s", user_id, e)

    sources = [("bibliotheque", _build_index(company)), (f"bibliotheque_partagee_{level}", _build_index(shared))]
    if mode == "shared_first":
        sources.reverse()
    sources = [(name, idx) for name, idx in sources if idx["docs"]]

    matched = 0
    for name, idx in sources:
        for ln in lines:
            if ln.get("price_source") or ln.get("unit_price_ht"):
                continue
            cands = _candidates(ln, idx)
            if cands and cands[0][0] >= 0.6:
                _apply(ln, cands[0][1], name)
                matched += 1

    pending = []
    for ln in lines:
        if ln.get("price_source") or ln.get("unit_price_ht"):
            continue
        merged = []
        for name, idx in sources:
            merged += [(sc, it, name) for sc, it in _candidates(ln, idx, same_unit=True, k=5)]
            if _unit_family(ln.get("unit")) == "count" and float(ln.get("qty") or 1) == 1:
                merged += [(sc, it, name) for sc, it in _candidates(ln, idx, same_unit=False, k=3)]
        seen, cands = set(), []
        for sc, it, name in sorted(merged, key=lambda x: -x[0]):
            key = (it.get("designation"), it.get("unit"))
            if key not in seen:
                seen.add(key)
                cands.append((sc, {**it, "_src": name}))
        if cands:
            pending.append((ln, cands[:6]))
    if pending:
        try:
            picks = await _ai_pick(pending)
        except Exception as e:  # noqa: BLE001
            logger.warning("Arbitrage IA bibliothèque indisponible: %s", e)
            picks = {}
        for i, c in picks.items():
            ln, cands = pending[i]
            it = cands[c][1]
            if _unit_family(it.get("unit")) != _unit_family(ln.get("unit")):
                # Unités incompatibles (ex. « 1 forfait » ↔ prix au m²) : changer l'unité sans
                # convertir la quantité chiffrerait 1 m² au lieu de la surface réelle. On ne
                # chiffre pas : on propose l'ouvrage, à valider avec la bonne quantité.
                ln["price_suggestion"] = {"designation": it.get("designation", ""),
                                          "unit": it.get("unit"), "unit_price_ht": it.get("unit_price_ht"),
                                          "source": it["_src"]}
                ln["price_review_reason"] = (f"Unité différente ({ln.get('unit')} → {it.get('unit')}) : "
                                             "saisir la quantité dans la bonne unité.")
                continue
            _apply(ln, it, it["_src"])
            matched += 1
    return lines, matched


def _plancher_price_m2_bareme(ep_m: float | None) -> float:
    """Prix plancher au m² selon l'épaisseur de dalle (barème indicatif 120–160 €/m²)."""
    cm = (ep_m or 0.20) * 100
    if cm <= 16:
        return 120.0
    if cm <= 20:
        return 140.0
    return 160.0


def _beton_line_items(d: dict, plancher: dict | None = None) -> list[dict]:
    """Lignes GROS ŒUVRE / BÉTON uniquement : murs (voiles), poteaux, poutres,
    planchers (dalles), semelles + aciers. Sans pièces ni second œuvre.
    La surface se réfère aux planchers détectés uniquement."""
    lines = []
    _default_pu = {"bn": 38.0, "reservations": 45.0, "huisseries": 90.0}

    def add(desig, qty, unit, elem=None, cat="Gros œuvre — béton"):
        if qty and qty > 0:
            ln = {"designation": desig, "unit": unit, "qty": round(qty, 2),
                  "unit_price_ht": _default_pu.get(elem, 0), "vat_rate": 20, "category": cat}
            if elem:
                ln["elem"] = elem
            lines.append(ln)
    add(f"Béton — semelles / fondations ({d.get('semelles', 0)} u)", d.get("beton_semelles_m3"), "m³", elem="semelles")
    add(f"Béton de propreté (sous semelles, ép. {round((d.get('beton_proprete_ep_m') or 0.05) * 100)} cm)", d.get("beton_proprete_m3"), "m³", elem="proprete")
    add(f"Béton — poteaux ({d.get('poteaux', 0)} u)", d.get("beton_poteaux_m3"), "m³", elem="poteaux")
    add(f"Béton — poutres / linteaux ({d.get('poutres_ml', 0)} ml)", d.get("beton_poutres_m3"), "m³", elem="poutres")
    if plancher:
        # Plancher chiffré au m² (prix all-in : béton + aciers + main d'œuvre du plancher)
        cm = round((d.get("beton_dalle_ep_m") or 0.20) * 100)
        add(f"Plancher béton — {plancher.get('label', 'dalle pleine BA')} ({d.get('planchers_m2', 0)} m² · ép. {cm} cm)",
            d.get("planchers_m2"), "m²", elem="dalles")
    else:
        add(f"Béton — dalles / planchers ({d.get('planchers_m2', 0)} m²)", d.get("beton_dalles_m3"), "m³", elem="dalles")
    add(f"Béton — voiles / murs porteurs ({d.get('murs_porteurs_ml', 0)} ml)", d.get("beton_voiles_m3"), "m³", elem="voiles")
    add(f"Bandes noyées / poutres noyées ({d.get('bandes_noyees_ml', 0)} ml)", d.get("bandes_noyees_ml"), "ml", elem="bn")
    add(f"Réservations (traçage + coffrage) — {d.get('reservations', 0)} u", d.get("reservations"), "u", elem="reservations")
    add(f"Huisseries — pré-cadres / réservations de baies ({d.get('huisseries', 0)} u)", d.get("huisseries"), "u", elem="huisseries")
    _ratio_moy = _ratio_label(d)
    _acier_kg = d.get("acier_total_kg")
    if plancher:
        # Les aciers du plancher sont inclus dans le prix au m² → on les retire de la ligne aciers
        _acier_kg = round((_acier_kg or 0) - (d.get("acier_dalles_kg") or 0), 2)
    add(f"Aciers HA (ferraillage — env. {_ratio_moy} kg/m³)", _acier_kg, "kg")
    return lines


def _descriptif_line_items(d: dict) -> list[dict]:
    lines = []

    def add(desig, qty, unit, cat="Depuis analyse plan"):
        if qty and qty > 0:
            lines.append({"designation": desig, "unit": unit, "qty": round(qty, 2),
                          "unit_price_ht": 0, "vat_rate": 10, "category": cat})
    add("Plancher / sol (surface au sol)", d.get("planchers_m2"), "m²")
    add("Murs porteurs (maçonnerie)", d.get("murs_porteurs_ml"), "ml")
    add("Cloisons", d.get("cloisons_ml"), "ml")
    add(f"Murs — enduit/peinture (h={d.get('wall_height_m')} m)", d.get("murs_surface_m2"), "m²")
    add("Fournitures et pose — Portes", d.get("portes"), "u")
    add("Fournitures et pose — Fenêtres", d.get("fenetres"), "u")
    add("Fournitures et pose — Baies vitrées", d.get("baies"), "u")
    add("Réservations (traçage + coffrage)", d.get("reservations"), "u")
    # Béton : UNE ligne par élément (m³). Les anciennes lignes « Poteaux (u) », « Poutres (ml) »,
    # « Semelles (u) » + « Béton coulé total (m³) » faisaient payer deux fois les mêmes ouvrages une
    # fois chiffrées depuis la bibliothèque. Les voiles sont exclus : les murs porteurs sont déjà
    # comptés en maçonnerie ci-dessus.
    for desig, key in (("Béton — semelles / fondations", "beton_semelles_m3"),
                       ("Béton — poteaux", "beton_poteaux_m3"),
                       ("Béton — poutres (retombées)", "beton_poutres_m3"),
                       ("Béton — dalles / planchers", "beton_dalles_m3")):
        add(desig, d.get(key), "m³")
    add("Bandes noyées / poutres noyées", d.get("bandes_noyees_ml"), "ml")
    acier = round(sum(float(d.get(k) or 0) for k in ("acier_semelles_kg", "acier_poteaux_kg",
                                                      "acier_poutres_kg", "acier_dalles_kg")), 1)
    add(f"Aciers HA (fer à béton armé — env. {_ratio_label(d)} kg/m³)", acier, "kg")
    return lines


def _ratio_label(d: dict) -> int:
    """Ratio moyen d'acier PONDÉRÉ par les volumes (et non moyenne arithmétique des ratios)."""
    r = d.get("acier_ratio_moyen_kg_m3")
    if r:
        return round(r)
    _ar = d.get("acier_ratios") or {}
    return round(sum(_ar.values()) / len(_ar)) if _ar else 100


@router.get("/{plan_id}/analysis/{page_index}")
async def get_analysis(plan_id: str, page_index: int, wall_height: float = 2.5,
                       dalle_ep: float = 0.20, voile_ep: float = 0.20,
                       poutre_l: float = 0.20, poutre_h: float = 0.40,
                       acier_semelles: float | None = None, acier_poteaux: float | None = None,
                       acier_poutres: float | None = None, acier_dalles: float | None = None,
                       acier_voiles: float | None = None,
                       proprete_ep: float = 0.05,
                       arase_inf: float | None = None, arase_sup: float | None = None,
                       user=Depends(current_user)) -> dict:
    """Renvoie la structure + le descriptif chiffré (nécessite une calibration)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages.image_png_b64": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    ppm = _page_ppm(p, page_index)
    structure = (p.get("structure") or {}).get(str(page_index)) or {}
    rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    ar = {"semelles": acier_semelles, "poteaux": acier_poteaux, "poutres": acier_poutres,
          "dalles": acier_dalles, "voiles": acier_voiles}
    descriptif = _compute_descriptif(structure, ppm, rooms, wall_height, dalle_ep, voile_ep,
                                     poutre_l, poutre_h, acier_ratios=ar, proprete_ep=proprete_ep,
                                     arase_inf=arase_inf, arase_sup=arase_sup)
    return {"structure": structure, "descriptif": descriptif,
            "calibrated": bool(ppm), "pixels_per_meter": ppm}


@router.get("/{plan_id}/structure/{page_index}/beton-xlsx")
async def export_beton_xlsx(plan_id: str, page_index: int, wall_height: float = 2.5,
                            dalle_ep: float = 0.20, voile_ep: float = 0.20,
                            poutre_l: float = 0.20, poutre_h: float = 0.40,
                            acier_semelles: float | None = None, acier_poteaux: float | None = None,
                            acier_poutres: float | None = None, acier_dalles: float | None = None,
                            acier_voiles: float | None = None,
                            beton_price_m3: float = 0.0, acier_price_kg: float = 0.0,
                            beton_price_semelles: float | None = None,
                            beton_price_proprete: float | None = None,
                            beton_price_poteaux: float | None = None,
                            beton_price_poutres: float | None = None,
                            beton_price_dalles: float | None = None,
                            beton_price_voiles: float | None = None,
                            proprete_ep: float = 0.05,
                            user=Depends(current_user)):
    """Export Excel du métré béton (poteaux, poutres, dalles, voiles, semelles + coûts)."""
    from io import BytesIO
    from fastapi.responses import Response
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structure": 1, "calibrations": 1, "rooms": 1, "filename": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    ppm = _page_ppm(p, page_index)
    structure = (p.get("structure") or {}).get(str(page_index)) or {}
    rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    ar = {"semelles": acier_semelles, "poteaux": acier_poteaux, "poutres": acier_poutres,
          "dalles": acier_dalles, "voiles": acier_voiles}
    d = _compute_descriptif(structure, ppm, rooms, wall_height, dalle_ep, voile_ep,
                            poutre_l, poutre_h, acier_ratios=ar, proprete_ep=proprete_ep)

    header_font = Font(bold=True, color="FFFFFF", size=10)
    header_fill = PatternFill("solid", fgColor="1F2733")
    bold = Font(bold=True)

    def sheet_header(ws, headers: list, widths: list) -> None:
        ws.append(headers)
        for col, w in enumerate(widths, start=1):
            cell = ws.cell(row=1, column=col)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
            ws.column_dimensions[cell.column_letter].width = w

    wb = Workbook()
    ws = wb.active
    ws.title = "Métré béton"
    sheet_header(ws, ["Poste", "Détail", "Volume (m³)", "Ratio acier (kg/m³)", "Aciers (kg)",
                      "Prix béton (€/m³)", "Coût béton (€)", "Coût aciers (€)", "Coût total (€)"],
                 [26, 38, 12, 15, 12, 15, 14, 14, 14])
    r = d.get("acier_ratios") or {}
    # Prix : repli sur valeurs marché si non renseignés
    bp, akg, _lab, _mg = _with_default_prices(beton_price_m3, acier_price_kg, 0.0, 0.0)
    price_by_elem = {"semelles": beton_price_semelles, "proprete": beton_price_proprete,
                     "poteaux": beton_price_poteaux, "poutres": beton_price_poutres,
                     "dalles": beton_price_dalles, "voiles": beton_price_voiles}

    def pe(elem):
        v = price_by_elem.get(elem)
        return float(v) if (v and v > 0) else bp

    tot_cb = tot_ca = 0.0

    def poste_row(label, detail, vol, elem, acier_kg):
        nonlocal tot_cb, tot_ca
        vol = vol or 0
        acier_kg = acier_kg or 0
        prix = pe(elem)
        cb = round(vol * prix, 2)
        ca = round(acier_kg * akg, 2)
        tot_cb += cb
        tot_ca += ca
        ws.append([label, detail, vol, r.get(elem if elem != "proprete" else "semelles") if elem != "proprete" else "",
                   acier_kg, prix, cb, ca, round(cb + ca, 2)])
    poste_row("Semelles / fondations", f"{d.get('semelles', 0)} u", d.get("beton_semelles_m3"),
              "semelles", d.get("acier_semelles_kg"))
    poste_row("Béton de propreté", f"sous semelles · ép. {round((d.get('beton_proprete_ep_m') or 0.05) * 100)} cm", d.get("beton_proprete_m3"),
              "proprete", 0)
    poste_row("Poteaux", f"{d.get('poteaux', 0)} u", d.get("beton_poteaux_m3"),
              "poteaux", d.get("acier_poteaux_kg"))
    poste_row("Poutres / linteaux",
              f"{d.get('poutres_ml', 0)} ml · section {d.get('beton_poutre_section', '')}",
              d.get("beton_poutres_m3"), "poutres", d.get("acier_poutres_kg"))
    poste_row("Dalles / planchers", f"{d.get('planchers_m2', 0)} m² · ép. {d.get('beton_dalle_ep_m', 0)} m",
              d.get("beton_dalles_m3"), "dalles", d.get("acier_dalles_kg"))
    poste_row("Voiles (murs porteurs)",
              f"{d.get('murs_porteurs_ml', 0)} ml · ép. {d.get('beton_voile_ep_m', 0)} m · h {d.get('wall_height_m', 0)} m",
              d.get("beton_voiles_m3"), "voiles", d.get("acier_voiles_kg"))
    ws.append([])
    beton_avec_proprete = round((d.get("beton_total_m3", 0) or 0) + (d.get("beton_proprete_m3", 0) or 0), 2)
    ws.append(["TOTAL BÉTON", "", beton_avec_proprete, "", d.get("acier_total_kg", 0),
               "", round(tot_cb, 2), round(tot_ca, 2), round(tot_cb + tot_ca, 2)])
    for cell in ws[ws.max_row]:
        cell.font = bold

    ws2 = wb.create_sheet("Poteaux")
    sheet_header(ws2, ["Repère", "Section", "Hauteur (m)", "Volume (m³)"], [12, 18, 13, 14])
    for c in d.get("poteaux_table") or []:
        ws2.append([c.get("ref"), c.get("section"), c.get("hauteur_m"), c.get("volume_m3")])

    ws3 = wb.create_sheet("Poutres")
    sheet_header(ws3, ["Repère", "Portée (m)", "Volume (m³)"], [12, 14, 14])
    for b in d.get("beams_table") or []:
        ws3.append([b.get("ref"), b.get("portee_m"), b.get("volume_m3")])

    buf = BytesIO()
    wb.save(buf)
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="metre-beton-{plan_id}.xlsx"'})


@router.get("/{plan_id}/structure/{page_index}/beton-pdf")
async def export_beton_pdf(plan_id: str, page_index: int, wall_height: float = 2.5,
                           dalle_ep: float = 0.20, voile_ep: float = 0.20,
                           poutre_l: float = 0.20, poutre_h: float = 0.40,
                           acier_semelles: float | None = None, acier_poteaux: float | None = None,
                           acier_poutres: float | None = None, acier_dalles: float | None = None,
                           acier_voiles: float | None = None,
                           beton_price_m3: float = 0.0, acier_price_kg: float = 0.0,
                           labor_price_m3: float = 0.0, margin_pct: float = 0.0,
                           proprete_ep: float = 0.05,
                           user=Depends(current_user)):
    """PDF de synthèse du métré béton (volumes + aciers + poteaux + poutres)."""
    from io import BytesIO
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from engines.pdf_takeoff import _styles, _table, _story_header_branding, DARK, LIGHT_GREY, ORANGE
    from engines.pdf_i18n import pdf_labels

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structure": 1, "calibrations": 1, "rooms": 1, "filename": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    branding = await _resolve_branding(user["user_id"])
    ppm = _page_ppm(p, page_index)
    structure = (p.get("structure") or {}).get(str(page_index)) or {}
    rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    ar = {"semelles": acier_semelles, "poteaux": acier_poteaux, "poutres": acier_poutres,
          "dalles": acier_dalles, "voiles": acier_voiles}
    d = _compute_descriptif(structure, ppm, rooms, wall_height, dalle_ep, voile_ep,
                            poutre_l, poutre_h, acier_ratios=ar, proprete_ep=proprete_ep)

    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    story: list = []
    _story_header_branding(story, branding, S)
    story += [
        Paragraph("MÉTRÉ BÉTON — SYNTHÈSE", S["kicker"]),
        Paragraph(p.get("filename") or "Plan", S["h1"]),
        Paragraph(f"Hauteur murs {d.get('wall_height_m')} m · ep. dalle {d.get('beton_dalle_ep_m')} m · "
                  f"ep. voile {d.get('beton_voile_ep_m')} m · poutre {d.get('beton_poutre_section')}", S["muted"]),
        Spacer(1, 10),
    ]
    if not d.get("beton_total_m3"):
        story.append(Paragraph("Plan non calibre ou sans structure detectee - quantites indisponibles.", S["body"]))
    r = d.get("acier_ratios") or {}
    rows = [["Poste", "Detail", "Volume (m3)", "Ratio (kg/m3)", "Aciers (kg)"],
            ["Poteaux", f"{d.get('poteaux', 0)} u", d.get("beton_poteaux_m3", 0), r.get("poteaux", ""), d.get("acier_poteaux_kg", 0)],
            ["Poutres / linteaux", f"{d.get('poutres_ml', 0)} ml", d.get("beton_poutres_m3", 0), r.get("poutres", ""), d.get("acier_poutres_kg", 0)],
            ["Dalles / planchers", f"{d.get('planchers_m2', 0)} m2", d.get("beton_dalles_m3", 0), r.get("dalles", ""), d.get("acier_dalles_kg", 0)],
            ["Voiles (murs porteurs)", f"{d.get('murs_porteurs_ml', 0)} ml", d.get("beton_voiles_m3", 0), r.get("voiles", ""), d.get("acier_voiles_kg", 0)],
            ["Semelles / fondations", f"{d.get('semelles', 0)} u", d.get("beton_semelles_m3", 0), r.get("semelles", ""), d.get("acier_semelles_kg", 0)],
            ["TOTAL", "", d.get("beton_total_m3", 0), "", d.get("acier_total_kg", 0)]]
    t = _table([[str(c) for c in row] for row in rows],
               [46 * mm, 30 * mm, 26 * mm, 26 * mm, 26 * mm],
               style_extras=[
                   ("BACKGROUND", (0, 0), (-1, 0), DARK),
                   ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                   ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                   ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#F0E9DF")),
                   ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
                   ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
               ])
    story += [t, Spacer(1, 14)]

    # Coûts estimés (matière + main d'œuvre + marge) — prix de repli si non renseignés
    bt = d.get("beton_total_m3", 0) or 0
    at = d.get("acier_total_kg", 0) or 0
    beton_price_m3, acier_price_kg, labor_price_m3, margin_pct = _with_default_prices(
        beton_price_m3, acier_price_kg, labor_price_m3, margin_pct)
    if bt or at:
        cost_beton = bt * beton_price_m3
        cost_acier = at * acier_price_kg
        cost_labor = bt * labor_price_m3
        matiere = cost_beton + cost_acier
        sous_total = matiere + cost_labor
        pv = sous_total * (1 + (margin_pct or 0) / 100)
        crows = [["Chiffrage estime", "Montant"],
                 [f"Beton ({bt} m3 x {beton_price_m3:.0f} EUR/m3)", f"{cost_beton:,.0f} EUR".replace(",", " ")],
                 [f"Aciers ({at} kg x {acier_price_kg:.2f} EUR/kg)", f"{cost_acier:,.0f} EUR".replace(",", " ")],
                 ["Cout matiere", f"{matiere:,.0f} EUR".replace(",", " ")],
                 [f"Main d'oeuvre ({bt} m3 x {labor_price_m3:.0f} EUR/m3)", f"{cost_labor:,.0f} EUR".replace(",", " ")],
                 [f"Prix de vente estime (marge {margin_pct:.0f}%)", f"{pv:,.0f} EUR".replace(",", " ")]]
        story += [_table([[str(c) for c in row] for row in crows], [110 * mm, 44 * mm],
                         style_extras=[("BACKGROUND", (0, 0), (-1, 0), DARK),
                                       ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                       ("FONTNAME", (0, 3), (-1, 3), "Helvetica-Bold"),
                                       ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                                       ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8F3EC")),
                                       ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
                                       ("ALIGN", (1, 0), (1, -1), "RIGHT")]), Spacer(1, 14)]

    if d.get("poteaux_table"):
        story.append(Paragraph("Tableau des poteaux", S["h2"]))
        prows = [["Repere", "Section", "Hauteur (m)", "Volume (m3)"]]
        prows += [[c.get("ref"), c.get("section"), c.get("hauteur_m"), c.get("volume_m3")] for c in d["poteaux_table"]]
        story += [_table([[str(c) for c in row] for row in prows], [30 * mm, 40 * mm, 34 * mm, 34 * mm],
                         style_extras=[("BACKGROUND", (0, 0), (-1, 0), ORANGE),
                                       ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                       ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY)]), Spacer(1, 12)]
    if d.get("beams_table"):
        story.append(Paragraph("Tableau des poutres", S["h2"]))
        brows = [["Repere", "Portee (m)", "Volume (m3)"]]
        brows += [[b.get("ref"), b.get("portee_m"), b.get("volume_m3")] for b in d["beams_table"]]
        story += [_table([[str(c) for c in row] for row in brows], [40 * mm, 48 * mm, 48 * mm],
                         style_extras=[("BACKGROUND", (0, 0), (-1, 0), ORANGE),
                                       ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                       ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY)])]
    story += [Spacer(1, 16), Paragraph(pdf_labels(None).get("footer", ""), S["muted"])]
    pdf.build(story)
    return Response(
        content=buf.getvalue(), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="metre-beton-{plan_id}.pdf"'})


@router.get("/{plan_id}/cotes-pdf")
async def export_cotes_pdf(plan_id: str, user=Depends(current_user)):
    """PDF du relevé des cotes mémorisées (distances / surfaces / périmètres) avec le nom du projet."""
    from io import BytesIO
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
    from engines.pdf_takeoff import _styles, _table, _story_header_branding, DARK, LIGHT_GREY, ORANGE
    from engines.pdf_i18n import pdf_labels

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "filename": 1, "project_name": 1, "measurements": 1,
         "pages.image_png_b64": 1, "pages.width_px": 1, "pages.height_px": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    branding = await _resolve_branding(user["user_id"])
    measures = p.get("measurements") or []
    pages = p.get("pages") or []
    project = p.get("project_name") or p.get("filename") or "Plan"

    def _render_overlay(page, page_measures):
        """Image du plan avec surfaces/murs coloriés (filtre translucide + traits)."""
        import base64
        from PIL import Image as PILImage, ImageDraw
        b64 = page.get("image_png_b64")
        if not b64 or not page_measures:
            return None
        try:
            base = PILImage.open(BytesIO(base64.b64decode(b64))).convert("RGBA")
        except Exception:
            return None
        overlay = PILImage.new("RGBA", base.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)

        def rgba(hexc, a):
            h = (hexc or "#0d9488").lstrip("#")
            h = h if len(h) == 6 else "0d9488"
            try:
                return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)
            except Exception:
                return (13, 148, 136, a)
        lw = max(2, base.size[0] // 400)

        def _draw_openings(mm):
            for op in (mm.get("openings") or []):
                opp = op.get("points")
                if opp and len(opp) == 2:
                    d.line([(float(opp[0][0]), float(opp[0][1])),
                            (float(opp[1][0]), float(opp[1][1]))],
                           fill=(255, 255, 255, 255), width=lw + 2)

        for m in page_measures:
            col = m.get("color") or "#0d9488"
            if m.get("kind") == "cumulative":
                for seg in (m.get("segments") or []):
                    sp = [(float(x), float(y)) for x, y in seg if x is not None]
                    if len(sp) >= 2:
                        d.line(sp, fill=rgba(col, 255), width=lw)
                _draw_openings(m)
                continue
            if m.get("kind") == "cumulative_area":
                for poly in (m.get("polygons") or []):
                    pp = [(float(x), float(y)) for x, y in poly if x is not None]
                    if len(pp) >= 3:
                        d.polygon(pp, fill=rgba(col, 70), outline=rgba(col, 255))
                continue
            pts = [(float(x), float(y)) for x, y in (m.get("points") or []) if x is not None]
            if len(pts) < 2:
                continue
            if m.get("kind") == "polygon":
                d.polygon(pts, fill=rgba(col, 70), outline=rgba(col, 255))
            else:
                d.line(pts, fill=rgba(col, 255), width=lw)
                _draw_openings(m)
        out = PILImage.alpha_composite(base, overlay).convert("RGB")
        b = BytesIO()
        out.save(b, format="JPEG", quality=80)
        b.seek(0)
        return b, out.size

    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    story: list = []
    _story_header_branding(story, branding, S)
    story += [
        Paragraph("RELEVÉ DES COTES", S["kicker"]),
        Paragraph(str(project), S["h1"]),
        Paragraph(f"{len(measures)} cote(s) mémorisée(s)", S["muted"]),
        Spacer(1, 10),
    ]
    if not measures:
        story.append(Paragraph("Aucune cote mémorisée sur ce plan.", S["body"]))
    else:
        # Plan(s) colorié(s) : une image par page ayant des cotes
        by_page: dict = {}
        for m in measures:
            by_page.setdefault(int(m.get("page_index") or 0), []).append(m)
        for pidx in sorted(by_page.keys()):
            if pidx < 0 or pidx >= len(pages):
                continue
            rendered = _render_overlay(pages[pidx], by_page[pidx])
            if not rendered:
                continue
            img_buf, (iw, ih) = rendered
            draw_w = 174 * mm
            draw_h = draw_w * (ih / iw) if iw else draw_w
            if draw_h > 205 * mm:
                draw_h = 205 * mm
                draw_w = draw_h * (iw / ih) if ih else draw_w
            story += [RLImage(img_buf, width=draw_w, height=draw_h), Spacer(1, 12)]

        # Tableau des cotes, trié par famille (libellé)
        smeasures = sorted(measures, key=lambda x: (x.get("label") or "\uffff").lower())
        rows = [["", "#", "Désignation", "Type", "Valeur"]]
        color_styles = []
        detail_rows = []  # indices des lignes de détail d'ouverture (style atténué)
        fam: dict = {}
        tot_dist = tot_area = tot_perim = 0.0
        for i, m in enumerate(smeasures, 1):
            kind = m.get("kind")
            label = m.get("label") or "(sans nom)"
            f = fam.setdefault(label, {"dist": 0.0, "area": 0.0, "perim": 0.0, "n": 0})
            f["n"] += 1
            if kind == "distance":
                v = float(m.get("value_m") or m.get("length_m") or 0)
                val, ktxt = f"{v} m", "Distance"
                tot_dist += v; f["dist"] += v
            elif kind == "polyline":
                v = float(m.get("length_m") or 0)
                val, ktxt = f"{v} m", "Périmètre/ligne"
                tot_dist += v; f["dist"] += v
            elif kind == "cumulative":
                v = float(m.get("value_m") or m.get("length_m") or 0)
                nseg = len(m.get("segments") or [])
                nop = len(m.get("openings") or [])
                extra = f" − {nop} ouv." if nop else ""
                val = f"{v} m"
                ktxt = f"Mur cumulé ({nseg} tronçon{'s' if nseg > 1 else ''}{extra})"
                tot_dist += v; f["dist"] += v
            elif kind == "polygon":
                a = float(m.get("area_m2") or 0)
                pr = float(m.get("perimeter_m") or 0)
                val, ktxt = f"{a} m² · {pr} m", "Surface"
                tot_area += a; tot_perim += pr; f["area"] += a; f["perim"] += pr
            elif kind == "cumulative_area":
                a = float(m.get("area_m2") or 0)
                pr = float(m.get("perimeter_m") or 0)
                npz = len(m.get("polygons") or [])
                val = f"{a} m²"
                ktxt = f"Surface cumulée ({npz} zone{'s' if npz > 1 else ''})"
                tot_area += a; tot_perim += pr; f["area"] += a; f["perim"] += pr
            else:
                val, ktxt = "—", (kind or "—")
            rpos = len(rows)
            rows.append(["", str(i), str(label), ktxt, val])
            c = (m.get("color") or "").strip()
            if c.startswith("#"):
                try:
                    color_styles.append(("BACKGROUND", (0, rpos), (0, rpos), colors.HexColor(c)))
                except Exception:
                    pass
            # Détail hauteur/surface du mur + ouvertures déduites (largeur × hauteur × nb)
            ops = m.get("openings") or []
            wh = m.get("wall_height_m")
            gross = m.get("gross_m")
            net_area = m.get("wall_area_net_m2")
            if ops or wh:
                if gross is not None and ops:
                    detail_rows.append(len(rows))
                    rows.append(["", "", "     brut (avant ouvertures)", "", f"{round(float(gross), 3)} m"])
                if wh:
                    base_len = float(gross if gross is not None else (m.get("value_m") or m.get("length_m") or 0))
                    detail_rows.append(len(rows))
                    rows.append(["", "", f"     mur brut ({round(base_len, 2)} m × {wh} m)", "",
                                 f"{round(base_len * float(wh), 2)} m²"])
                for op in ops:
                    w = float(op.get("width_m") or 0)
                    cnt = int(op.get("count") or 1)
                    h = op.get("height_m")
                    oplabel = op.get("label") or "Ouverture"
                    dims = f"{w:g} m" + (f" × {float(h):g} m" if h else "") + (f" × {cnt}" if cnt > 1 else "")
                    txt = f"      - {oplabel} ({dims})"
                    detail_rows.append(len(rows))
                    val = f"− {round(w * float(h) * cnt, 3)} m²" if h else f"− {round(w * cnt, 3)} m"
                    rows.append(["", "", txt, "déduite", val])
                if wh and net_area is not None:
                    detail_rows.append(len(rows))
                    rows.append(["", "", "     mur net (surface, ouvertures déduites)", "",
                                 f"{round(float(net_area), 2)} m²"])
        detail_styles = []
        for r in detail_rows:
            detail_styles += [("TEXTCOLOR", (0, r), (-1, r), colors.grey),
                              ("FONTSIZE", (0, r), (-1, r), 7),
                              ("FONTNAME", (2, r), (2, r), "Helvetica-Oblique")]
        story += [
            _table([[str(c) for c in r] for r in rows],
                   [10 * mm, 10 * mm, 68 * mm, 34 * mm, 42 * mm],
                   style_extras=[("BACKGROUND", (0, 0), (-1, 0), DARK),
                                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                 ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
                                 ("ALIGN", (4, 0), (4, -1), "RIGHT")] + color_styles + detail_styles),
            Spacer(1, 12),
        ]
        # Sous-totaux par famille
        frows = [["Famille", "Cotes", "Longueur", "Surface"]]
        for label in sorted(fam.keys()):
            f = fam[label]
            frows.append([label, str(f["n"]),
                          f"{round(f['dist'], 2)} m" if f["dist"] else "—",
                          f"{round(f['area'], 2)} m²" if f["area"] else "—"])
        story += [
            Paragraph("Sous-totaux par famille", S["kicker"]),
            _table([[str(c) for c in r] for r in frows], [90 * mm, 18 * mm, 33 * mm, 33 * mm],
                   style_extras=[("BACKGROUND", (0, 0), (-1, 0), DARK),
                                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                 ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
                                 ("ALIGN", (1, 0), (-1, -1), "RIGHT")]),
            Spacer(1, 12),
        ]
        srows = [["Récapitulatif général", "Total"],
                 ["Longueurs cumulées", f"{round(tot_dist, 3)} m"],
                 ["Surfaces cumulées", f"{round(tot_area, 3)} m²"],
                 ["Périmètres cumulés", f"{round(tot_perim, 3)} m"]]
        story += [
            _table([[str(c) for c in r] for r in srows], [110 * mm, 44 * mm],
                   style_extras=[("BACKGROUND", (0, 0), (-1, 0), ORANGE),
                                 ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                 ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
                                 ("ALIGN", (1, 0), (1, -1), "RIGHT")]),
        ]
    story += [Spacer(1, 16), Paragraph(pdf_labels(None).get("footer", ""), S["muted"])]
    pdf.build(story)
    return Response(
        content=buf.getvalue(), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="cotes-{plan_id}.pdf"'})





class AiRefineIn(BaseModel):
    message: str
    history: list[str] = Field(default_factory=list)


@router.post("/{plan_id}/structure/{page_index}/ai-refine")
async def ai_refine_structure(plan_id: str, page_index: int, body: AiRefineIn,
                              user=Depends(current_user)) -> dict:
    """Assistant IA : applique une consigne en langage naturel pour corriger la détection."""
    if not (body.message or "").strip():
        raise HTTPException(400, "Consigne vide")
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1, "structure": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    page = pages[page_index]
    img = page.get("image_png_b64")
    if not img:
        raise HTTPException(500, "Image manquante")
    w, h = _page_dims(page)
    current = (p.get("structure") or {}).get(str(page_index)) or {}
    result = await refine_structure(img, w, h, body.message, current, body.history)
    reply = result.pop("reply", None)
    has_content = bool(result.get("walls") or result.get("columns") or result.get("beams")
                       or result.get("openings") or result.get("footings") or result.get("floors"))
    if result.get("error") and not has_content:
        return {"ok": False, "reply": reply or "L'IA n'a pas pu appliquer la consigne.",
                "error": result.get("error"), "structure": current}
    _assign_column_refs(result.get("columns") or [])
    _assign_beam_refs(result.get("beams") or [])
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"structure.{page_index}": {**result, "refined_at": _now()},
                  "updated_at": _now()}})
    return {"ok": True, "reply": reply, "structure": result}


@router.post("/{plan_id}/detect-structure-all", status_code=202)
async def detect_structure_all(plan_id: str, user=Depends(current_user)) -> dict:
    """Détection IA sur TOUTES les pages, en tâche de fond (plusieurs minutes sur un PDF multi-niveaux) ; suivre via /takeoffs/upload-jobs/{job_id}."""
    import asyncio
    import secrets
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "page_count": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    job_id = "pjob_" + secrets.token_hex(6)
    await db.plan_upload_jobs.insert_one({"job_id": job_id, "user_id": user["user_id"], "kind": "detect_structure_all", "plan_id": plan_id, "status": "processing",
                                          "progress": 0, "total": p.get("page_count") or 0, "created_at": _now(), "updated_at": _now()})
    asyncio.create_task(_detect_structure_all_job(job_id, plan_id, user["user_id"]))
    return {"job_id": job_id, "status": "processing"}


async def _detect_structure_all_job(job_id: str, plan_id: str, user_id: str) -> None:
    try:
        p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user_id}, {"_id": 0, "pages": 1})
        pages = (p or {}).get("pages") or []
        results = []
        for idx, page in enumerate(pages):
            img = page.get("image_png_b64")
            if not img:
                results.append({"page_index": idx, "error": "image manquante"})
                continue
            w, h = _page_dims(page)
            res = await detect_structure_tiled(img, w, h)
            _assign_column_refs(res.get("columns") or [])
            _assign_beam_refs(res.get("beams") or [])
            await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {f"structure.{idx}": {**res, "detected_at": _now()}}})
            results.append({"page_index": idx, "wall_count": res.get("wall_count", 0), "opening_count": res.get("opening_count", 0),
                            "beam_count": res.get("beam_count", 0), "error": res.get("error")})
            await db.plan_upload_jobs.update_one({"job_id": job_id}, {"$set": {"progress": idx + 1, "updated_at": _now()}})
        await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {"updated_at": _now()}})
        await db.plan_upload_jobs.update_one({"job_id": job_id}, {"$set": {"status": "done", "result": {"pages": results, "page_count": len(pages)}, "updated_at": _now()}})
    except Exception as e:  # noqa: BLE001
        logger.exception("detect-structure-all job failed")
        await db.plan_upload_jobs.update_one({"job_id": job_id}, {"$set": {"status": "error", "status_code": 500, "detail": f"Analyse multi-pages impossible : {type(e).__name__}", "updated_at": _now()}})


@router.post("/{plan_id}/structure/{page_index}/pdf")
async def annotated_plan_pdf(plan_id: str, page_index: int, wall_height: float = 2.5,
                             user=Depends(current_user)):
    """PDF du plan annoté (murs rouges / fenêtres jaunes / portes violettes / poutres)
    + légende + tableau descriptif — à joindre au devis client."""
    from fastapi.responses import Response
    from engines.plan_annot_pdf import build_annotated_plan_pdf
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    structure = (p.get("structure") or {}).get(str(page_index)) or {}
    if not (structure.get("walls") or structure.get("openings")):
        raise HTTPException(400, "Lancez d'abord « Analyser le plan ».")
    ppm = _page_ppm(p, page_index)
    rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    descriptif = _compute_descriptif(structure, ppm, rooms, wall_height)
    branding = await _resolve_branding(user["user_id"])
    pdf = build_annotated_plan_pdf(pages[page_index]["image_png_b64"], structure,
                                   descriptif, p.get("filename") or "plan", branding)
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="plan-annote-{plan_id}.pdf"'})


class QuoteFromStructureIn(BaseModel):
    snapshot_png: str | None = None


@router.post("/{plan_id}/structure/{page_index}/quote")
async def structure_to_quote(plan_id: str, page_index: int, wall_height: float = 2.5,
                             dalle_ep: float = 0.20, voile_ep: float = 0.20,
                             poutre_l: float = 0.20, poutre_h: float = 0.40,
                             acier_semelles: float | None = None, acier_poteaux: float | None = None,
                             acier_poutres: float | None = None, acier_dalles: float | None = None,
                             acier_voiles: float | None = None,
                             acier_price_kg: float = 0.0,
                             beton_price_m3: float = 0.0, labor_price_m3: float = 0.0,
                             beton_price_semelles: float | None = None,
                             beton_price_proprete: float | None = None,
                             beton_price_poteaux: float | None = None,
                             beton_price_poutres: float | None = None,
                             beton_price_dalles: float | None = None,
                             beton_price_voiles: float | None = None,
                             proprete_ep: float = 0.05,
                             plancher_type: str = "auto",
                             plancher_price_m2: float | None = None,
                             margin_pct: float = 0.0,
                             margin_beton: float | None = None, margin_acier: float | None = None,
                             margin_labor: float | None = None,
                             client_id: str | None = None,
                             beton_only: bool = False,
                             price_level: str | None = None,
                             arase_inf: float | None = None, arase_sup: float | None = None,
                             body: QuoteFromStructureIn | None = None,
                             user=Depends(current_user)) -> dict:
    """Crée un devis brouillon à partir du descriptif (planchers, murs, ouvertures, poutres, aciers)."""
    import secrets
    from routes.documents import _client_snapshot, _compute_totals
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages.image_png_b64": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    ppm = _page_ppm(p, page_index)
    if not ppm:
        raise HTTPException(400, "Calibrez d'abord le plan avant de générer le devis.")
    structure = (p.get("structure") or {}).get(str(page_index)) or {}
    rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    ar = {"semelles": acier_semelles, "poteaux": acier_poteaux, "poutres": acier_poutres,
          "dalles": acier_dalles, "voiles": acier_voiles}
    descriptif = _compute_descriptif(structure, ppm, rooms, wall_height, dalle_ep, voile_ep,
                                     poutre_l, poutre_h, acier_ratios=ar, floors_only=beton_only, proprete_ep=proprete_ep,
                                     arase_inf=arase_inf, arase_sup=arase_sup)
    plancher_opt = None
    if beton_only:
        _pt = plancher_type
        if _pt == "auto":
            # Gros œuvre : immeuble = dalle pleine BA (défaut) ; maison = poutrelles-hourdis.
            _pt = "poutrelles_hourdis" if (structure.get("plan_kind") == "maison") else "dalle_pleine"
        _label = "dalle pleine BA" if _pt == "dalle_pleine" else "poutrelles-hourdis"
        plancher_opt = {"label": _label,
                        "price_m2": (float(plancher_price_m2) if (plancher_price_m2 and plancher_price_m2 > 0)
                                     else _plancher_price_m2_bareme(dalle_ep))}
    lines = _beton_line_items(descriptif, plancher=plancher_opt) if beton_only else _descriptif_line_items(descriptif)
    if not lines:
        raise HTTPException(400, "Aucune quantité à chiffrer — analysez le plan d'abord.")
    # Prix indicatifs de repli si l'utilisateur n'a rien configuré → chiffrage automatique
    _margins_set = any(m is not None for m in (margin_beton, margin_acier, margin_labor))
    beton_price_m3, acier_price_kg, labor_price_m3, margin_pct = _with_default_prices(
        beton_price_m3, acier_price_kg, labor_price_m3, margin_pct, margins_set=_margins_set)
    lines, priced = await _apply_library_prices(user["user_id"], lines, level_override=price_level)
    # Plancher au m² (prix all-in selon épaisseur) — PRIORITAIRE sur la bibliothèque
    if plancher_opt:
        for ln in lines:
            if ln.get("elem") == "dalles" and ln.get("unit") == "m²":
                ln["unit_price_ht"] = round(float(plancher_opt["price_m2"]), 2)
                ln["price_source"] = "bareme_plancher"
                if ln.get("vat_rate") is None:
                    ln["vat_rate"] = 20
                priced += 1
    # Prix acier au kg (chiffrage instantané de la ligne « Aciers HA » si non chiffrée par la bibliothèque)
    if acier_price_kg and acier_price_kg > 0:
        for ln in lines:
            if "acier" in (ln.get("designation") or "").lower() and not ln.get("unit_price_ht"):
                ln["unit_price_ht"] = round(float(acier_price_kg), 2)
                priced += 1
    # Prix béton au m³ — global ou par poste (semelle, dalle, voile…) pour un chiffrage plus fin
    beton_price_by_elem = {
        "semelles": beton_price_semelles, "proprete": beton_price_proprete,
        "poteaux": beton_price_poteaux, "poutres": beton_price_poutres,
        "dalles": beton_price_dalles, "voiles": beton_price_voiles,
    }
    if beton_price_m3 and beton_price_m3 > 0:
        for ln in lines:
            desig = (ln.get("designation") or "").lower()
            is_beton = ("béton coulé" in desig) or (desig.startswith("béton") and "main d'œuvre" not in desig)
            if is_beton and not ln.get("unit_price_ht"):
                pe = beton_price_by_elem.get(ln.get("elem"))
                ln["unit_price_ht"] = round(float(pe if (pe and pe > 0) else beton_price_m3), 2)
                priced += 1
    # Main d'œuvre béton (au m³) — hors dalles si plancher chiffré au m² (main d'œuvre incluse dans le prix/m²)
    beton_total = descriptif.get("beton_total_m3") or 0
    if plancher_opt:
        beton_total = round(beton_total - (descriptif.get("beton_dalles_m3") or 0), 2)
    if labor_price_m3 and labor_price_m3 > 0 and beton_total > 0:
        lines.append({"designation": "Main d'œuvre béton (coffrage, coulage, ferraillage)",
                      "unit": "m³", "qty": round(beton_total, 2),
                      "unit_price_ht": round(float(labor_price_m3), 2), "vat_rate": 20,
                      "category": "Depuis analyse plan"})
        priced += 1
    # Marge commerciale par poste (béton / aciers / main d'œuvre) — repli sur la marge globale
    m_beton = margin_beton if margin_beton is not None else margin_pct
    m_acier = margin_acier if margin_acier is not None else margin_pct
    m_labor = margin_labor if margin_labor is not None else margin_pct
    for ln in lines:
        desig = (ln.get("designation") or "").lower()
        if not ln.get("unit_price_ht"):
            continue
        if ln.get("price_source") == "bareme_plancher":
            continue  # prix plancher/m² déjà all-in (pas de marge additionnelle)
        if "main d'œuvre" in desig and m_labor:
            ln["unit_price_ht"] = round(ln["unit_price_ht"] * (1 + m_labor / 100), 2)
        elif "acier" in desig and m_acier:
            ln["unit_price_ht"] = round(ln["unit_price_ht"] * (1 + m_acier / 100), 2)
        elif "béton" in desig and m_beton:
            ln["unit_price_ht"] = round(ln["unit_price_ht"] * (1 + m_beton / 100), 2)
    snap = (body.snapshot_png if body else None) or None
    if snap and snap.startswith("data:"):
        snap = snap.split(",", 1)[-1]
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"], "doc_type": "quote", "number": None,
        "title": f"Devis — {p.get('filename') or 'plan'}",
        "client_id": client_id, "client": await _client_snapshot(client_id, user),
        "status": "draft", "lines": lines, "notes": "",
        "payment_terms": "", "deposit_pct": 0,
        "attachment_image_b64": snap,
        "totals": _compute_totals(lines, 0),
        "issue_date": None, "due_date": None,
        "source": "plan_structure", "plan_id": plan_id,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["priced_lines"] = priced
    return doc


class WallTypeIn(BaseModel):
    wall_type: str  # porteur | cloison | doublage
@router.patch("/{plan_id}/walls/{page_index}/{wall_id}/type")
async def update_wall_type(plan_id: str, page_index: int, wall_id: str,
                           body: WallTypeIn, user=Depends(current_user)) -> dict:
    """Reclasse manuellement un mur détecté (porteur / cloison / doublage)."""
    if body.wall_type not in ("porteur", "cloison", "doublage"):
        raise HTTPException(400, "wall_type invalide (porteur|cloison|doublage)")
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, f"cv_walls.{page_index}.segments": 1},
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    segs = ((p.get("cv_walls") or {}).get(str(page_index))
            or (p.get("cv_walls") or {}).get(page_index) or {}).get("segments") or []
    idx = next((i for i, s in enumerate(segs) if s.get("wall_id") == wall_id), -1)
    if idx < 0:
        raise HTTPException(404, "Mur introuvable")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {f"cv_walls.{page_index}.segments.{idx}.wall_type": body.wall_type,
                   f"cv_walls.{page_index}.segments.{idx}.type_source": "manual"}}
    )
    return {"ok": True, "wall_id": wall_id, "wall_type": body.wall_type}


# ============ P3 — Assistant IA d'édition du plan (aperçu + appliquer) ============

class AiCommandIn(BaseModel):
    command: str = Field(min_length=1, max_length=500)
    page_index: int = 0
    history: list[dict] = Field(default_factory=list)


class AiApplyIn(BaseModel):
    action: str
    params: dict = Field(default_factory=dict)
    page_index: int = 0


async def _load_plan_for_ai(plan_id: str, user_id: str, page_index: int):
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "rooms": 1, "cv_walls": 1, "calibrations": 1, "measurements": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = [r for r in (p.get("rooms") or []) if r.get("page_index", 0) == page_index]
    cv = (p.get("cv_walls") or {}).get(str(page_index)) or (p.get("cv_walls") or {}).get(page_index) or {}
    walls = cv.get("segments") or []
    meas = [m for m in (p.get("measurements") or []) if m.get("page_index", 0) == page_index]
    return p, rooms, walls, meas


def _build_manual_measurement(prm: dict, page_index: int) -> tuple[dict, str]:
    """Construit une cote manuelle (surface / linear / rampant) de façon déterministe.
    Renvoie (record, libellé_humain). Lève HTTPException si les valeurs sont invalides."""
    import math
    mtype = (prm.get("measure_type") or "").strip().lower()
    label = (prm.get("label") or "").strip()[:80] or None
    poste = (prm.get("poste") or "").strip()[:40] or None
    rec = {"measurement_id": f"mes_{secrets.token_hex(6)}", "page_index": page_index,
           "points": [], "color": None, "poste": poste, "label": label,
           "source": "assistant", "created_at": _now()}
    if mtype == "surface":
        try:
            area = round(float(prm.get("area_m2")), 3)
        except (TypeError, ValueError):
            raise HTTPException(422, "Surface (m²) invalide")
        if area <= 0 or area > 100000:
            raise HTTPException(422, "Surface hors bornes (0–100000 m²)")
        rec.update({"kind": "manual_area", "area_m2": area})
        return rec, f"{area:.2f} m²"
    if mtype == "rampant":
        try:
            proj = float(prm.get("projected_area_m2"))
            slope = float(prm.get("slope_pct") or 0)
        except (TypeError, ValueError):
            raise HTTPException(422, "Surface au sol (m²) ou pente (%) invalide")
        if proj <= 0 or proj > 100000:
            raise HTTPException(422, "Surface au sol hors bornes")
        if slope < 0 or slope > 300:
            raise HTTPException(422, "Pente hors bornes (0–300 %)")
        factor = math.sqrt(1 + (slope / 100.0) ** 2)
        real = round(proj * factor, 3)
        if not label:
            label = f"Sous-plafond rampant {slope:.0f}%"
        rec.update({"kind": "manual_area", "area_m2": real, "label": label[:80],
                    "projected_area_m2": round(proj, 3), "slope_pct": slope,
                    "slope_factor": round(factor, 4)})
        return rec, f"{real:.2f} m² (sol {proj:.2f} m² × {factor:.4f})"
    if mtype == "linear":
        try:
            ln = round(float(prm.get("length_m")), 3)
        except (TypeError, ValueError):
            raise HTTPException(422, "Linéaire (ml) invalide")
        if ln <= 0 or ln > 100000:
            raise HTTPException(422, "Linéaire hors bornes")
        rec.update({"kind": "manual_linear", "value_m": ln, "length_m": ln, "gross_m": ln})
        wh = prm.get("wall_height_m")
        if wh not in (None, ""):
            try:
                h = float(wh)
            except (TypeError, ValueError):
                h = 0.0
            if 0 < h <= 20:
                rec["wall_height_m"] = h
                rec.update(_recompute_linear_sets(rec))
        return rec, f"{ln:.2f} ml"
    raise HTTPException(422, "Type de mesure inconnu (surface / linear / rampant)")


@router.post("/{plan_id}/ai-command")
async def ai_command_preview(plan_id: str, body: AiCommandIn,
                             user=Depends(current_user)) -> dict:
    """Interprète une commande en langage naturel et renvoie l'action proposée (SANS appliquer)."""
    _, rooms, walls, meas = await _load_plan_for_ai(plan_id, user["user_id"], body.page_index)
    action = await ai_engine.plan_command(rooms, walls, body.command, measurements=meas,
                                          history=body.history or [])
    if action.get("action") == "web_answer":
        q = (action.get("params") or {}).get("query") or body.command
        res = await ai_engine.web_answer(q)
        return {"action": "answer",
                "summary": action.get("summary") or "Réponse (recherche web)",
                "answer": res.get("answer") or res.get("error") or "Aucune réponse trouvée.",
                "sources": res.get("sources") or [],
                "price_suggestion": res.get("price_suggestion"),
                "page_index": body.page_index}
    action["page_index"] = body.page_index
    return action


@router.post("/{plan_id}/ai-command/apply")
async def ai_command_apply(plan_id: str, body: AiApplyIn,
                           user=Depends(current_user)) -> dict:
    """Applique l'action validée par l'utilisateur puis renvoie l'état à jour."""
    p, _, _, meas_page = await _load_plan_for_ai(plan_id, user["user_id"], body.page_index)
    action = body.action
    prm = body.params or {}
    rooms = p.get("rooms") or []
    pi = body.page_index

    def _find_room(rid):
        return next((r for r in rooms if r.get("room_id") == rid and r.get("page_index", 0) == pi), None)

    if action == "rename_room":
        room = _find_room(prm.get("room_id"))
        if not room:
            raise HTTPException(404, "Pièce introuvable")
        new_name = (prm.get("new_name") or "").strip()[:60]
        if not new_name:
            raise HTTPException(422, "Nom invalide")
        room["name"] = new_name
        await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {"rooms": rooms, "updated_at": _now()}})
        return {"ok": True, "applied": "rename_room", "room_id": room["room_id"], "name": new_name}

    if action == "delete_room":
        room = _find_room(prm.get("room_id"))
        if not room:
            raise HTTPException(404, "Pièce introuvable")
        rooms = [r for r in rooms if r.get("room_id") != prm.get("room_id")]
        await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {"rooms": rooms, "updated_at": _now()}})
        return {"ok": True, "applied": "delete_room", "room_id": prm.get("room_id")}

    if action == "set_room_surface":
        room = _find_room(prm.get("room_id"))
        if not room:
            raise HTTPException(404, "Pièce introuvable")
        try:
            surf = round(float(prm.get("surface_m2")), 2)
        except (TypeError, ValueError):
            raise HTTPException(422, "Surface invalide")
        if surf <= 0 or surf > 100000:
            raise HTTPException(422, "Surface hors bornes")
        room["surface_m2"] = surf
        room["surface_written_m2"] = surf
        room["surface_delta_pct"] = None
        room["surface_source"] = "manual"
        await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {"rooms": rooms, "updated_at": _now()}})
        return {"ok": True, "applied": "set_room_surface", "room_id": room["room_id"], "surface_m2": surf}

    if action == "set_room_height":
        room = _find_room(prm.get("room_id"))
        if not room:
            raise HTTPException(404, "Pièce introuvable")
        try:
            h = float(prm.get("height_m"))
        except (TypeError, ValueError):
            raise HTTPException(422, "Hauteur invalide")
        if h <= 0 or h > 20:
            raise HTTPException(422, "Hauteur hors bornes")
        room["ceiling_height_m"] = h
        calib = (p.get("calibrations") or {}).get(str(room.get("page_index", 0)))
        _recompute_room(room, (calib or {}).get("pixels_per_meter") or 0)
        await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {"rooms": rooms, "updated_at": _now()}})
        return {"ok": True, "applied": "set_room_height", "room_id": room["room_id"], "height_m": h}

    if action == "reclassify_wall":
        new_type = prm.get("new_type")
        if new_type not in ("porteur", "cloison", "doublage"):
            raise HTTPException(422, "Type de mur invalide")
        wid = prm.get("wall_id")
        segs = ((p.get("cv_walls") or {}).get(str(pi)) or (p.get("cv_walls") or {}).get(pi) or {}).get("segments") or []
        idx = next((i for i, s in enumerate(segs) if (s.get("wall_id") or s.get("id")) == wid), -1)
        if idx < 0:
            raise HTTPException(404, "Mur introuvable")
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id},
            {"$set": {f"cv_walls.{pi}.segments.{idx}.wall_type": new_type,
                      f"cv_walls.{pi}.segments.{idx}.type_source": "ai", "updated_at": _now()}})
        return {"ok": True, "applied": "reclassify_wall", "wall_id": wid, "wall_type": new_type}

    if action == "add_note":
        text = (prm.get("text") or "").strip()[:200]
        if not text:
            raise HTTPException(422, "Texte de note vide")
        note = {"id": "note_" + secrets.token_hex(4), "text": text,
                "x": int(prm.get("x") or 60), "y": int(prm.get("y") or 60)}
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id},
            {"$push": {f"annotations.{pi}.notes": note}, "$set": {"updated_at": _now()}})
        return {"ok": True, "applied": "add_note", "note": note}

    # ---- Actions sur les MESURES (cotes) ----
    def _find_meas(mid):
        return next((m for m in meas_page if m.get("measurement_id") == mid), None)

    if action == "rename_measurement":
        mid = prm.get("measurement_id")
        if not _find_meas(mid):
            raise HTTPException(404, "Mesure introuvable")
        new_label = (prm.get("new_label") or "").strip()[:80]
        if not new_label:
            raise HTTPException(422, "Libellé invalide")
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"], "measurements.measurement_id": mid},
            {"$set": {"measurements.$.label": new_label, "updated_at": _now()}})
        return {"ok": True, "applied": "rename_measurement", "measurement_id": mid, "label": new_label}

    if action == "delete_measurement":
        mid = prm.get("measurement_id")
        if not _find_meas(mid):
            raise HTTPException(404, "Mesure introuvable")
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            {"$pull": {"measurements": {"measurement_id": mid}}, "$set": {"updated_at": _now()}})
        return {"ok": True, "applied": "delete_measurement", "measurement_id": mid}

    if action == "set_measurement_height":
        mid = prm.get("measurement_id")
        m = _find_meas(mid)
        if not m:
            raise HTTPException(404, "Mesure introuvable")
        try:
            h = float(prm.get("wall_height_m"))
        except (TypeError, ValueError):
            raise HTTPException(422, "Hauteur invalide")
        if h < 0 or h > 20:
            raise HTTPException(422, "Hauteur hors bornes (0–20 m)")
        m["gross_m"] = round(_measure_gross_m(m), 3)
        m["wall_height_m"] = h or 0
        sets = _recompute_linear_sets(m)
        await _persist_linear(plan_id, user["user_id"], mid, sets)
        return {"ok": True, "applied": "set_measurement_height", "measurement_id": mid,
                "wall_height_m": h, **sets}

    if action == "set_measurement_poste":
        from engines import corps_etat
        mid = prm.get("measurement_id")
        poste = (prm.get("poste") or "").strip()
        if not _find_meas(mid):
            raise HTTPException(404, "Mesure introuvable")
        if poste not in corps_etat.POSTES:
            raise HTTPException(422, f"Poste inconnu : {poste}")
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"], "measurements.measurement_id": mid},
            {"$set": {"measurements.$.poste": poste, "updated_at": _now()}})
        return {"ok": True, "applied": "set_measurement_poste", "measurement_id": mid, "poste": poste}

    if action == "set_measurements_height_bulk":
        try:
            h = float(prm.get("wall_height_m"))
        except (TypeError, ValueError):
            raise HTTPException(422, "Hauteur invalide")
        if h < 0 or h > 20:
            raise HTTPException(422, "Hauteur hors bornes (0–20 m)")
        kw = (prm.get("filter") or "").strip().lower()
        facade_kw = ("façade", "facade", "extérieur", "exterieur", "ext ", "mur ext", "périphérique", "peripherique")
        is_facade = kw in ("__facade__",) or any(f.strip() == kw for f in facade_kw)
        linear_kinds = ("distance", "cumulative", "polyline", "manual_linear")
        bbox = _facade_bbox([m for m in meas_page if m.get("kind") in linear_kinds]) if is_facade else None
        count = 0
        for m in meas_page:
            if m.get("kind") not in linear_kinds:
                continue
            lbl = (m.get("label") or "").lower()
            if is_facade:
                # détection par POSITION (périmètre) OU par libellé
                if not (_measure_is_facade(m, bbox) or any(f in lbl for f in facade_kw)):
                    continue
            elif kw and kw not in lbl:
                continue
            m["gross_m"] = round(_measure_gross_m(m), 3)
            m["wall_height_m"] = h or 0
            sets = _recompute_linear_sets(m)
            await _persist_linear(plan_id, user["user_id"], m["measurement_id"], sets)
            count += 1
        return {"ok": True, "applied": "set_measurements_height_bulk",
                "wall_height_m": h, "filter": kw, "updated": count}

    if action == "create_measurement":
        rec, human = _build_manual_measurement(prm, pi)
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            {"$push": {"measurements": rec}, "$set": {"updated_at": _now()}})
        return {"ok": True, "applied": "create_measurement",
                "measurement_id": rec["measurement_id"], "label": rec.get("label"), "value": human}

    if action == "create_measurements_bulk":
        items = prm.get("items")
        if not isinstance(items, list) or not items:
            raise HTTPException(422, "Aucune mesure à créer")
        if len(items) > 50:
            raise HTTPException(422, "Trop de mesures (max 50)")
        recs, created = [], []
        for it in items:
            if not isinstance(it, dict):
                continue
            rec, human = _build_manual_measurement(it, pi)
            recs.append(rec)
            created.append({"measurement_id": rec["measurement_id"], "label": rec.get("label"), "value": human})
        if not recs:
            raise HTTPException(422, "Aucune mesure valide à créer")
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            {"$push": {"measurements": {"$each": recs}}, "$set": {"updated_at": _now()}})
        return {"ok": True, "applied": "create_measurements_bulk", "created": created,
                "count": len(created)}

    if action == "set_measurement_surface":
        mid = prm.get("measurement_id")
        m = _find_meas(mid)
        if not m:
            raise HTTPException(404, "Mesure introuvable")
        try:
            surf = round(float(prm.get("surface_m2")), 3)
        except (TypeError, ValueError):
            raise HTTPException(422, "Surface (m²) invalide")
        if surf <= 0 or surf > 100000:
            raise HTTPException(422, "Surface hors bornes (0–100000 m²)")
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"], "measurements.measurement_id": mid},
            {"$set": {"measurements.$.area_m2": surf, "measurements.$.surface_source": "manual",
                      "updated_at": _now()}})
        return {"ok": True, "applied": "set_measurement_surface", "measurement_id": mid, "surface_m2": surf}

    if action == "adjust_measurement_surface":
        mid = prm.get("measurement_id")
        m = _find_meas(mid)
        if not m:
            raise HTTPException(404, "Mesure introuvable")
        cur = m.get("area_m2")
        if cur is None:
            cur = m.get("wall_area_net_m2")
        if cur is None:
            raise HTTPException(422, "Cette cote n'a pas de surface à ajuster")
        try:
            delta = round(float(prm.get("delta_m2")), 3)
        except (TypeError, ValueError):
            raise HTTPException(422, "Variation (m²) invalide")
        new_surf = round(float(cur) + delta, 3)
        if new_surf <= 0:
            raise HTTPException(422, f"Surface résultante invalide ({new_surf:.2f} m²)")
        if new_surf > 100000:
            raise HTTPException(422, "Surface hors bornes")
        log = {"delta_m2": delta, "from_m2": round(float(cur), 3), "to_m2": new_surf, "at": _now()}
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"], "measurements.measurement_id": mid},
            {"$set": {"measurements.$.area_m2": new_surf, "measurements.$.surface_source": "manual",
                      "updated_at": _now()},
             "$push": {"measurements.$.surface_adjustments": log}})
        return {"ok": True, "applied": "adjust_measurement_surface", "measurement_id": mid,
                "from_m2": log["from_m2"], "delta_m2": delta, "surface_m2": new_surf}

    if action == "deduct_measurement_areas":
        mid = prm.get("measurement_id")
        m = _find_meas(mid)
        if not m:
            raise HTTPException(404, "Mesure introuvable")
        cur = m.get("area_m2")
        if cur is None:
            cur = m.get("wall_area_net_m2")
        if cur is None:
            raise HTTPException(422, "Cette cote n'a pas de surface à ajuster")
        raw = prm.get("areas")
        if not isinstance(raw, list) or not raw:
            raise HTTPException(422, "Aucune trémie à déduire")
        if len(raw) > 100:
            raise HTTPException(422, "Trop de déductions (max 100)")
        areas = []
        for a in raw:
            try:
                v = float(a)
            except (TypeError, ValueError):
                raise HTTPException(422, "Surface de trémie invalide")
            if v <= 0 or v > 100000:
                raise HTTPException(422, "Surface de trémie hors bornes")
            areas.append(round(v, 3))
        total = round(sum(areas), 3)
        new_surf = round(float(cur) - total, 3)
        if new_surf <= 0:
            raise HTTPException(422, f"Surface résultante invalide ({new_surf:.2f} m²)")
        log = {"deltas_m2": areas, "total_m2": total, "from_m2": round(float(cur), 3),
               "to_m2": new_surf, "at": _now()}
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"], "measurements.measurement_id": mid},
            {"$set": {"measurements.$.area_m2": new_surf, "measurements.$.surface_source": "manual",
                      "updated_at": _now()},
             "$push": {"measurements.$.surface_adjustments": log}})
        return {"ok": True, "applied": "deduct_measurement_areas", "measurement_id": mid,
                "from_m2": log["from_m2"], "count": len(areas), "total_deducted_m2": total,
                "surface_m2": new_surf}

    if action == "set_measurement_length":
        mid = prm.get("measurement_id")
        m = _find_meas(mid)
        if not m:
            raise HTTPException(404, "Mesure introuvable")
        try:
            ln = round(float(prm.get("length_m")), 3)
        except (TypeError, ValueError):
            raise HTTPException(422, "Linéaire (ml) invalide")
        if ln <= 0 or ln > 100000:
            raise HTTPException(422, "Linéaire hors bornes")
        m["gross_m"] = ln
        sets = _recompute_linear_sets(m) if m.get("wall_height_m") else {
            "gross_m": ln, "value_m": ln, "length_m": ln}
        await _persist_linear(plan_id, user["user_id"], mid, sets)
        return {"ok": True, "applied": "set_measurement_length", "measurement_id": mid,
                "length_m": ln, **sets}

    if action == "duplicate_measurement":
        import copy
        mid = prm.get("measurement_id")
        src = _find_meas(mid)
        if not src:
            raise HTTPException(404, "Mesure introuvable")
        dup = copy.deepcopy(src)
        dup["measurement_id"] = f"mes_{secrets.token_hex(6)}"
        dup["label"] = ((src.get("label") or "Mesure") + " (copie)")[:80]
        dup["created_at"] = _now()
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            {"$push": {"measurements": dup}, "$set": {"updated_at": _now()}})
        return {"ok": True, "applied": "duplicate_measurement",
                "measurement_id": dup["measurement_id"], "label": dup["label"]}


    if action == "restore_measurement":
        meas = prm.get("measurement")
        if not isinstance(meas, dict) or not meas.get("measurement_id"):
            raise HTTPException(422, "Mesure à restaurer invalide")
        # évite un doublon si déjà présente
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            {"$pull": {"measurements": {"measurement_id": meas["measurement_id"]}}})
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            {"$push": {"measurements": meas}, "$set": {"updated_at": _now()}})
        return {"ok": True, "applied": "restore_measurement", "measurement_id": meas["measurement_id"]}

    if action == "estimate_page":
        prefs = await _load_ce_prefs(user)
        margin = float(prm.get("margin_pct", 0) or 0)
        assigned = 0
        grand_ht = grand_ttc = 0.0
        chiffres = 0
        for m in meas_page:
            poste = m.get("poste")
            q = _measure_chiffrage_qty(m)
            if q <= 0:
                continue
            if not poste:
                poste = _suggest_poste(m)
                if poste:
                    await db.plans_takeoff.update_one(
                        {"plan_id": plan_id, "user_id": user["user_id"],
                         "measurements.measurement_id": m.get("measurement_id")},
                        {"$set": {"measurements.$.poste": poste, "updated_at": _now()}})
                    assigned += 1
            if not poste or not _known_poste(poste, prefs.get("custom_postes")):
                continue
            est = _estimate_poste(poste, q, {"margin_pct": margin, "prices": prefs["prices"],
                                             "ratios": prefs["ratios"]}, prefs.get("custom_postes"))
            grand_ht += est["totals"]["ht_with_margin"]
            grand_ttc += est["totals"]["ttc"]
            chiffres += 1
        return {"ok": True, "applied": "estimate_page", "assigned": assigned,
                "priced_measures": chiffres,
                "totals": {"ht_with_margin": round(grand_ht, 2), "ttc": round(grand_ttc, 2)}}

    if action == "assign_all_postes":
        from engines import corps_etat
        count = 0
        for m in meas_page:
            if m.get("poste"):
                continue
            if _measure_chiffrage_qty(m) <= 0:
                continue
            poste = _suggest_poste(m)
            if poste not in corps_etat.POSTES:
                continue
            await db.plans_takeoff.update_one(
                {"plan_id": plan_id, "user_id": user["user_id"],
                 "measurements.measurement_id": m.get("measurement_id")},
                {"$set": {"measurements.$.poste": poste, "updated_at": _now()}})
            count += 1
        return {"ok": True, "applied": "assign_all_postes", "assigned": count}

    raise HTTPException(400, f"Action non supportée : {action}")


@router.get("/{plan_id}/walls-summary")
async def walls_summary(plan_id: str, ppm: float | None = Query(None, gt=0),
                        user=Depends(current_user)) -> dict:
    """Résumé des murs détectés par type + ML total pour lien avec l'estimation.

    `ppm` (pixels/mètre) optionnel : échelle affichée côté client, utilisée en repli
    quand aucune calibration n'est enregistrée (corrige l'affichage « 0 ml »)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "cv_walls": 1, "calibrations": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    cv_walls = p.get("cv_walls") or {}
    calibs = p.get("calibrations") or {}
    scales = []
    for c in calibs.values():
        mpp = c.get("meters_per_pixel") or (
            1.0 / c["pixels_per_meter"] if c.get("pixels_per_meter") else None)
        if mpp:
            scales.append(mpp)
    scale = sum(scales) / len(scales) if scales else None
    if not scale and ppm:
        scale = 1.0 / ppm

    totals = {"porteur": {"count": 0, "ml": 0.0},
              "cloison": {"count": 0, "ml": 0.0},
              "doublage": {"count": 0, "ml": 0.0}}
    for _, entry in cv_walls.items():
        for s in (entry or {}).get("segments") or []:
            wt = s.get("wall_type") or "cloison"
            if wt not in totals:
                wt = "cloison"
            totals[wt]["count"] += 1
            length_m = (s.get("length_px", 0) * scale) if scale else 0
            totals[wt]["ml"] += length_m
    for t in totals.values():
        t["ml"] = round(t["ml"], 2)
    return {"plan_id": plan_id, "scale_m_per_px": scale, "totals": totals}


# ============ Room autofill / detect all ============

@router.post("/{plan_id}/detect-all-rooms")
async def detect_all_rooms_route(plan_id: str, page_index: int = 0, user=Depends(current_user)):
    """Auto-détection de TOUTES les pièces closes d'une page via findContours."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1, "calibrations": 1},
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    img = pages[page_index].get("image_png_b64")
    if not img:
        raise HTTPException(500, "Image manquante")
    try:
        result = detect_all_rooms(img)
    except Exception as e:
        logger.exception("detect_all_rooms failed")
        raise HTTPException(500, f"Détection impossible : {e}")

    calib = (p.get("calibrations") or {}).get(str(page_index))
    if calib:
        ppm = calib["pixels_per_meter"]
        for r in result.get("rooms", []):
            if len(r.get("points", [])) >= 3:
                r["surface_m2"] = round(G.polygon_area_m2(r["points"], ppm), 3)
                r["perimeter_m"] = round(G.polygon_perimeter_m(r["points"], ppm), 3)
    return result


@router.post("/{plan_id}/room-autofill")
async def room_autofill(plan_id: str, body: RoomAutofillIn, user=Depends(current_user)):
    """À partir d'un point cliqué à l'intérieur d'une pièce, extrait le polygone via flood fill."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1, "calibrations": 1},
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if body.page_index < 0 or body.page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    img = pages[body.page_index].get("image_png_b64")
    if not img:
        raise HTTPException(500, "Image manquante")
    try:
        cv_res = flood_fill_room(img, body.seed_x, body.seed_y, body.tolerance)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.exception("flood fill failed")
        raise HTTPException(500, f"Détection contour impossible : {e}")

    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    if calib and len(cv_res["points"]) >= 3:
        ppm = calib["pixels_per_meter"]
        cv_res["surface_m2"] = round(G.polygon_area_m2(cv_res["points"], ppm), 3)
        cv_res["perimeter_m"] = round(G.polygon_perimeter_m(cv_res["points"], ppm), 3)
    return cv_res


# ============ MESURE PONCTUELLE ============

class MeasureIn(BaseModel):
    page_index: int
    kind: Literal["distance", "polyline", "polygon", "cumulative", "cumulative_area"]
    points: list[tuple[float, float]] = Field(min_length=2)
    # Cumul mur : liste de tronçons (chacun >= 2 points) — les « trous »
    # (fenêtres/portes) entre tronçons ne sont PAS comptés dans le total.
    segments: list[list[tuple[float, float]]] | None = None
    # Cumul surface : liste de zones (chacune >= 3 points) additionnées en m².
    polygons: list[list[tuple[float, float]]] | None = None
    label: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=9)
    poste: str | None = Field(default=None, max_length=40)


@router.post("/{plan_id}/measure")
async def measure(plan_id: str, body: MeasureIn, user=Depends(current_user)):
    """Calcule ET persiste la mesure — historique effaçable du volet Objets (iter65)."""
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "calibrations": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    if not calib:
        raise HTTPException(400, "Page non calibrée")
    ppm = calib["pixels_per_meter"]

    if body.kind == "distance":
        if len(body.points) != 2:
            raise HTTPException(422, "distance = exactement 2 points")
        dist = round(G.distance_m(body.points[0], body.points[1], ppm), 3)
        result = {"kind": "distance", "value_m": dist, "length_m": dist}
    elif body.kind == "cumulative":
        segs = [s for s in (body.segments or []) if len(s) >= 2]
        if not segs:
            raise HTTPException(422, "cumulative requiert au moins 1 tronçon (2 points)")
        total = round(sum(G.polyline_length_m(s, ppm) for s in segs), 3)
        result = {"kind": "cumulative", "value_m": total, "length_m": total,
                  "segments": [[list(pt) for pt in s] for s in segs]}
    elif body.kind == "cumulative_area":
        polys = [pp for pp in (body.polygons or []) if len(pp) >= 3]
        if not polys:
            raise HTTPException(422, "cumulative_area requiert au moins 1 zone (3 points)")
        area = round(sum(G.polygon_area_m2(pp, ppm) for pp in polys), 3)
        perim = round(sum(G.polygon_perimeter_m(pp, ppm) for pp in polys), 3)
        result = {"kind": "cumulative_area", "area_m2": area, "perimeter_m": perim,
                  "polygons": [[list(pt) for pt in pp] for pp in polys]}
    elif body.kind == "polyline":
        result = {"kind": "polyline",
                  "length_m": round(G.polyline_length_m(body.points, ppm), 3)}
    else:
        if len(body.points) < 3:
            raise HTTPException(422, "polygon >= 3 points")
        result = {"kind": "polygon",
                  "area_m2": round(G.polygon_area_m2(body.points, ppm), 3),
                  "perimeter_m": round(G.polygon_perimeter_m(body.points, ppm), 3)}

    record = {"measurement_id": f"mes_{secrets.token_hex(6)}",
              "page_index": body.page_index,
              "points": [list(pt) for pt in body.points],
              "label": (body.label or "").strip()[:80] or None,
              "color": (body.color or "").strip()[:9] or None,
              "poste": (body.poste or "").strip()[:40] or None,
              "created_at": _now(), **result}
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$push": {"measurements": {"$each": [record]}},
         "$set": {"updated_at": _now()}})
    return record


class CorpsEtatIn(BaseModel):
    poste: str = Field(max_length=40)
    quantity: float = Field(gt=0)
    params: dict | None = None


@router.get("/corps-etat/catalog")
async def corps_etat_catalog(user=Depends(current_user)) -> dict:
    """Catalogue des postes chiffrables (corps d'état standard + ouvrages personnalisés)."""
    from engines import corps_etat
    p = await _load_ce_prefs(user)
    return {"postes": corps_etat.catalog() + list(p["custom_postes"])}


async def _load_ce_prefs(user) -> dict:
    doc = await db.corps_etat_prefs.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"prices": (doc or {}).get("prices") or {},
            "ratios": (doc or {}).get("ratios") or {},
            "custom_postes": (doc or {}).get("custom_postes") or [],
            "default_wall_height": float((doc or {}).get("default_wall_height") or 2.5)}


def _known_poste(poste: str, custom: list | None) -> bool:
    from engines import corps_etat
    return poste in corps_etat.POSTES or any((c.get("key") == poste) for c in (custom or []))


def _estimate_poste(poste: str, qty: float, params: dict, custom: list | None) -> dict:
    """Chiffrage d'un poste standard OU personnalisé (prix unitaire artisan tout compris)."""
    from engines import corps_etat
    if poste in corps_etat.POSTES:
        return corps_etat.estimate(poste, qty, params)
    cp = next((c for c in (custom or []) if c.get("key") == poste), None)
    if not cp:
        raise ValueError(f"Poste inconnu: {poste}")
    q = round(float(qty or 0), 3)
    if q <= 0:
        raise ValueError("Quantité invalide")
    pu = float(cp.get("pu") or 0)
    ht = round(q * pu, 2)
    margin = float(params.get("margin_pct", 0) or 0)
    ht_m = round(ht * (1 + margin / 100.0), 2)
    tva_rate = float(params.get("tva_rate", 0.20) or 0.20)
    tva = round(ht_m * tva_rate, 2)
    unit = cp.get("unit", "m2")
    return {"poste": poste, "label": cp.get("label", poste), "unit": unit,
            "family": cp.get("family", "area"), "color": cp.get("color", "#64748b"),
            "quantity": q, "custom": True,
            "lines": [{"designation": cp.get("label", poste), "detail": "Prix unitaire artisan (fourniture + pose)",
                       "unit": unit, "qty": q, "pu": round(pu, 2), "total": ht}],
            "totals": {"ht": ht, "margin_pct": margin, "ht_with_margin": ht_m,
                       "tva_rate": tva_rate, "tva": tva, "ttc": round(ht_m + tva, 2)},
            "params": {k: v for k, v in params.items() if k not in ("prices", "ratios")}}


class CustomPosteIn(BaseModel):
    key: str | None = None
    label: str = Field(min_length=1, max_length=60)
    unit: str = "m2"           # m2 | ml | u
    pu: float = Field(ge=0, le=1_000_000)
    color: str = "#64748b"


@router.get("/corps-etat/custom")
async def corps_etat_list_custom(user=Depends(current_user)) -> dict:
    p = await _load_ce_prefs(user)
    return {"custom_postes": p["custom_postes"]}


@router.post("/corps-etat/custom")
async def corps_etat_save_custom(body: CustomPosteIn, user=Depends(current_user)) -> dict:
    """Crée ou met à jour un ouvrage personnalisé de l'artisan (prix unitaire tout compris)."""
    import re
    unit = body.unit if body.unit in ("m2", "ml", "u") else "m2"
    family = {"m2": "area", "ml": "length", "u": "count"}[unit]
    key = (body.key or "").strip()
    if not key:
        slug = re.sub(r"[^a-z0-9]+", "_", body.label.lower()).strip("_")[:28] or "poste"
        key = f"custom_{slug}"
    poste = {"key": key, "label": body.label.strip()[:60], "unit": unit,
             "family": family, "color": (body.color or "#64748b")[:9], "pu": round(float(body.pu), 2),
             "custom": True}
    doc = await db.corps_etat_prefs.find_one({"user_id": user["user_id"]}, {"_id": 0, "custom_postes": 1})
    customs = (doc or {}).get("custom_postes") or []
    customs = [c for c in customs if c.get("key") != key]
    customs.append(poste)
    await db.corps_etat_prefs.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "custom_postes": customs, "updated_at": _now()}}, upsert=True)
    return {"ok": True, "poste": poste}


@router.delete("/corps-etat/custom/{key}")
async def corps_etat_delete_custom(key: str, user=Depends(current_user)) -> dict:
    await db.corps_etat_prefs.update_one(
        {"user_id": user["user_id"]},
        {"$pull": {"custom_postes": {"key": key}}, "$set": {"updated_at": _now()}})
    return {"ok": True}


@router.get("/corps-etat/prefs")
async def corps_etat_get_prefs(user=Depends(current_user)) -> dict:
    """Bibliothèque de l'artisan : prix unitaires + ratios (défaut + valeurs enregistrées)."""
    from engines import corps_etat
    p = await _load_ce_prefs(user)
    return {"prices": corps_etat.price_schema(p["prices"]),
            "ratios": corps_etat.ratio_schema(p["ratios"]),
            "default_wall_height": p["default_wall_height"]}


class CePrefsIn(BaseModel):
    prices: dict | None = None
    ratios: dict | None = None
    default_wall_height: float | None = None


@router.put("/corps-etat/prefs")
async def corps_etat_put_prefs(body: CePrefsIn, user=Depends(current_user)) -> dict:
    """Enregistre les prix et ratios personnalisés (réutilisés dans chaque chiffrage)."""
    def _clean(d):
        out = {}
        for k, v in (d or {}).items():
            try:
                out[str(k)[:40]] = float(v)
            except (TypeError, ValueError):
                continue
        return out
    prices, ratios = _clean(body.prices), _clean(body.ratios)
    payload = {"user_id": user["user_id"], "prices": prices, "ratios": ratios, "updated_at": _now()}
    if body.default_wall_height is not None:
        payload["default_wall_height"] = max(0.0, min(10.0, float(body.default_wall_height)))
    await db.corps_etat_prefs.update_one(
        {"user_id": user["user_id"]}, {"$set": payload}, upsert=True)
    return {"ok": True, **{k: v for k, v in payload.items() if k not in ("user_id", "updated_at")}}


@router.put("/corps-etat/default-height")
async def corps_etat_set_default_height(body: dict, user=Depends(current_user)) -> dict:
    """Mémorise la hauteur sous-plafond par défaut du chantier (presets & mur net m²)."""
    h = max(0.0, min(10.0, float(body.get("default_wall_height") or 0)))
    await db.corps_etat_prefs.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "default_wall_height": h, "updated_at": _now()}},
        upsert=True)
    return {"ok": True, "default_wall_height": h}


# --------------------------------------------------------------------------
# PRESET PIÈCE — chiffrer en un clic sol + plinthes + peinture murs + plafond
# --------------------------------------------------------------------------
class RoomPresetIn(BaseModel):
    area_m2: float = Field(gt=0, le=100000)
    perimeter_m: float = Field(default=0, ge=0, le=100000)
    height_m: float | None = None
    door_deduction_m: float = Field(default=0, ge=0, le=1000)
    margin_pct: float = 0
    couches: int = 2
    sol_poste: str = "carrelage"      # carrelage | parquet | chape
    plafond_poste: str = "peinture"   # peinture (peinture plafond) | plafond (placo)
    include: dict | None = None       # {sol, plinthes, peinture_murs, plafond}


@router.post("/corps-etat/room-preset")
async def corps_etat_room_preset(body: RoomPresetIn, user=Depends(current_user)) -> dict:
    """Ensemble type d'une pièce : sol + plinthes + peinture murs + plafond, calculé
    déterministiquement depuis (aire + périmètre + hauteur). La hauteur par défaut du
    chantier est utilisée si non fournie."""
    from engines import corps_etat
    prefs = await _load_ce_prefs(user)
    height = float(body.height_m) if body.height_m else prefs["default_wall_height"]
    inc = body.include or {"sol": True, "plinthes": True, "peinture_murs": True, "plafond": True}
    perim_net = max(0.0, float(body.perimeter_m) - float(body.door_deduction_m))
    base_params = {"margin_pct": body.margin_pct, "prices": prefs["prices"], "ratios": prefs["ratios"]}

    sol_poste = body.sol_poste if body.sol_poste in ("carrelage", "parquet", "chape") else "carrelage"
    plafond_poste = body.plafond_poste if body.plafond_poste in ("peinture", "plafond") else "peinture"

    plan = []  # (key label, poste, qty, extra params)
    if inc.get("sol") and body.area_m2 > 0:
        plan.append(("Sol", sol_poste, body.area_m2, {}))
    if inc.get("plinthes") and perim_net > 0:
        plan.append(("Plinthes", "plinthes", perim_net, {}))
    if inc.get("peinture_murs") and perim_net > 0 and height > 0:
        plan.append(("Peinture murs", "peinture", round(perim_net * height, 3), {"couches": max(1, int(body.couches or 2))}))
    if inc.get("plafond") and body.area_m2 > 0:
        extra = {"couches": max(1, int(body.couches or 2))} if plafond_poste == "peinture" else {}
        plan.append(("Plafond", plafond_poste, body.area_m2, extra))

    items, grand_ht, grand_ttc = [], 0.0, 0.0
    for slot, poste, qty, extra in plan:
        if qty <= 0:
            continue
        est = corps_etat.estimate(poste, qty, {**base_params, **extra})
        items.append({"slot": slot, **est})
        grand_ht += est["totals"]["ht_with_margin"]
        grand_ttc += est["totals"]["ttc"]
    return {
        "items": items, "count": len(items),
        "inputs": {"area_m2": body.area_m2, "perimeter_m": body.perimeter_m,
                   "perimeter_net_m": round(perim_net, 3), "height_m": height,
                   "sol_poste": sol_poste, "plafond_poste": plafond_poste},
        "totals": {"ht_with_margin": round(grand_ht, 2), "ttc": round(grand_ttc, 2)},
    }


# --------------------------------------------------------------------------
# BIBLIOTHÈQUE D'OUVRAGES — compositions complètes réutilisables par chantier
# --------------------------------------------------------------------------
class OuvrageIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    poste: str = Field(max_length=40)
    params: dict | None = None
    margin_pct: float = 0
    shared: bool = False


@router.get("/corps-etat/ouvrages")
async def corps_etat_list_ouvrages(user=Depends(current_user)) -> dict:
    """Ouvrages perso + ceux partagés par l'équipe (même organisation)."""
    org_id = user.get("organization_id")
    query = {"$or": [{"user_id": user["user_id"]}]}
    if org_id:
        query["$or"].append({"organization_id": org_id, "shared": True})
    rows = await db.corps_etat_ouvrages.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    for r in rows:
        r["is_mine"] = r.get("user_id") == user["user_id"]
        r["is_shared"] = bool(r.get("shared"))
        r.pop("user_id", None)
        r.pop("organization_id", None)
    return {"ouvrages": rows}


@router.post("/corps-etat/ouvrages")
async def corps_etat_save_ouvrage(body: OuvrageIn, user=Depends(current_user)) -> dict:
    """Enregistre une composition complète (poste + options + marge) réutilisable.
    Si `shared` et l'utilisateur appartient à une organisation, l'ouvrage est visible
    par toute l'équipe."""
    from engines import corps_etat
    if body.poste not in corps_etat.POSTES:
        raise HTTPException(422, f"Poste inconnu: {body.poste}")
    org_id = user.get("organization_id")
    shared = bool(body.shared and org_id)
    ov = {
        "ouvrage_id": secrets.token_hex(8),
        "user_id": user["user_id"],
        "organization_id": org_id if shared else None,
        "owner_name": user.get("company") or user.get("name") or "",
        "shared": shared,
        "name": body.name.strip()[:80],
        "poste": body.poste,
        "params": {k: v for k, v in (body.params or {}).items()
                   if k not in ("prices", "ratios")},
        "margin_pct": float(body.margin_pct or 0),
        "created_at": _now(),
    }
    await db.corps_etat_ouvrages.insert_one(dict(ov))
    ov.pop("_id", None)
    ov.pop("user_id", None); ov.pop("organization_id", None)
    return {"ok": True, "ouvrage": {**ov, "is_mine": True, "is_shared": shared}}


@router.delete("/corps-etat/ouvrages/{ouvrage_id}")
async def corps_etat_delete_ouvrage(ouvrage_id: str, user=Depends(current_user)) -> dict:
    """Suppression réservée au propriétaire de l'ouvrage."""
    await db.corps_etat_ouvrages.delete_one(
        {"user_id": user["user_id"], "ouvrage_id": ouvrage_id})
    return {"ok": True}


# --------------------------------------------------------------------------
# PROJETS MULTI-NIVEAUX — regrouper des plans (Fondations/RDC/R+1…) + consolidé
# --------------------------------------------------------------------------
class PlanGroupLevel(BaseModel):
    plan_id: str
    level_label: str = Field(default="", max_length=40)


class PlanGroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    chantier_id: str | None = None
    levels: list[PlanGroupLevel] = []


async def _consolidate_plan(plan_doc: dict, prefs: dict, margin: float) -> dict:
    """Métré (m² / ml / u) + chiffrage corps d'état de toutes les mesures d'un plan."""
    from engines import corps_etat
    from engines.plan_quote_scope import positive_quantity, finite_nonnegative
    area_m2 = length_ml = count_u = 0.0
    ht = ttc = 0.0
    priced = 0
    for m in (plan_doc.get("measurements") or []):
        q = positive_quantity(m, _measure_chiffrage_qty)
        if q is None:
            continue
        if m.get("area_m2") is not None:
            area_m2 += finite_nonnegative(m.get("area_m2"))
        elif m.get("length_m") is not None:
            length_ml += finite_nonnegative(m.get("length_m"))
        if m.get("kind") == "count":
            count_u += q
        poste = m.get("poste")
        if poste and _known_poste(poste, prefs.get("custom_postes")) and q > 0:
            est = _estimate_poste(poste, q, {"margin_pct": margin,
                                             "prices": prefs["prices"], "ratios": prefs["ratios"]},
                                  prefs.get("custom_postes"))
            ht += est["totals"]["ht_with_margin"]
            ttc += est["totals"]["ttc"]
            priced += 1
    return {
        "metre": {"area_m2": round(area_m2, 2), "length_ml": round(length_ml, 2),
                  "count_u": round(count_u, 0), "measures": len(plan_doc.get("measurements") or [])},
        "chiffrage": {"ht_with_margin": round(ht, 2), "ttc": round(ttc, 2), "priced_measures": priced},
    }


async def _group_payload(g: dict, user, with_consolidation: bool, margin: float = 0.0) -> dict:
    from engines.plan_quote_scope import unique_levels, group_coverage
    levels = g.get("levels") or []
    plan_ids = [lv["plan_id"] for lv in levels]
    plans = await db.plans_takeoff.find(
        {"plan_id": {"$in": plan_ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "filename": 1, "page_count": 1, "measurements": 1}).to_list(200)
    by_id = {p["plan_id"]: p for p in plans}
    prefs = await _load_ce_prefs(user) if with_consolidation else None
    out_levels, tot_ht, tot_ttc, tot_area, tot_len = [], 0.0, 0.0, 0.0, 0.0
    for lv in unique_levels(levels):
        pd = by_id.get(lv["plan_id"])
        row = {"plan_id": lv["plan_id"], "level_label": lv.get("level_label", ""),
               "filename": (pd or {}).get("filename"), "missing": pd is None}
        if with_consolidation and pd:
            cons = await _consolidate_plan(pd, prefs, margin)
            row["consolidated"] = cons
            tot_ht += cons["chiffrage"]["ht_with_margin"]
            tot_ttc += cons["chiffrage"]["ttc"]
            tot_area += cons["metre"]["area_m2"]
            tot_len += cons["metre"]["length_ml"]
        out_levels.append(row)
    payload = {"group_id": g["group_id"], "name": g["name"], "chantier_id": g.get("chantier_id"),
               "levels": out_levels, "updated_at": g.get("updated_at"), "created_at": g.get("created_at")}
    if with_consolidation:
        payload["totals"] = {"ht_with_margin": round(tot_ht, 2), "ttc": round(tot_ttc, 2),
                             "area_m2": round(tot_area, 2), "length_ml": round(tot_len, 2)}
        payload["coverage"] = group_coverage(levels, by_id, _measure_chiffrage_qty,
                                             lambda poste: _known_poste(poste, prefs.get("custom_postes")))
        payload["totals"]["scope"] = "recorded_measurements_only"
    return payload


@router.get("/multilevel/groups")
async def list_plan_groups(user=Depends(current_user)) -> dict:
    rows = await db.plan_groups.find({"user_id": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    groups = [await _group_payload(g, user, with_consolidation=False) for g in rows]
    return {"groups": groups}


@router.post("/multilevel/groups")
async def create_plan_group(body: PlanGroupIn, user=Depends(current_user)) -> dict:
    """Regroupe des plans existants en niveaux (Fondations/RDC/R+1…). Si un chantier est
    fourni, chaque plan y est rattaché."""
    plan_ids = [lv.plan_id for lv in body.levels]
    if plan_ids:
        found = await db.plans_takeoff.count_documents(
            {"plan_id": {"$in": plan_ids}, "user_id": user["user_id"]})
        if found != len(set(plan_ids)):
            raise HTTPException(422, "Un ou plusieurs plans sont introuvables pour ce compte")
    g = {
        "group_id": "grp_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "name": body.name.strip()[:120],
        "chantier_id": body.chantier_id,
        "levels": [{"plan_id": lv.plan_id, "level_label": (lv.level_label or "").strip()[:40]} for lv in body.levels],
        "created_at": _now(), "updated_at": _now(),
    }
    await db.plan_groups.insert_one(dict(g))
    if body.chantier_id:
        for pid in plan_ids:
            try:
                await db.chantiers.update_one(
                    {"chantier_id": body.chantier_id, "user_id": user["user_id"]},
                    {"$addToSet": {"attachments": {"kind": "plan", "ref_id": pid}}})
            except Exception:
                pass
    return {"ok": True, "group": await _group_payload(g, user, with_consolidation=False)}


@router.get("/multilevel/groups/{group_id}")
async def get_plan_group(group_id: str, margin_pct: float = Query(0.0), user=Depends(current_user)) -> dict:
    g = await db.plan_groups.find_one({"group_id": group_id, "user_id": user["user_id"]}, {"_id": 0})
    if not g:
        raise HTTPException(404, "Projet multi-niveaux introuvable")
    return await _group_payload(g, user, with_consolidation=True, margin=margin_pct)


@router.put("/multilevel/groups/{group_id}")
async def update_plan_group(group_id: str, body: PlanGroupIn, user=Depends(current_user)) -> dict:
    upd = {"name": body.name.strip()[:120], "chantier_id": body.chantier_id, "updated_at": _now(),
           "levels": [{"plan_id": lv.plan_id, "level_label": (lv.level_label or "").strip()[:40]} for lv in body.levels]}
    res = await db.plan_groups.update_one(
        {"group_id": group_id, "user_id": user["user_id"]}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Projet multi-niveaux introuvable")
    return {"ok": True}


@router.delete("/multilevel/groups/{group_id}")
async def delete_plan_group(group_id: str, user=Depends(current_user)) -> dict:
    await db.plan_groups.delete_one({"group_id": group_id, "user_id": user["user_id"]})
    return {"ok": True}


@router.post("/multilevel/groups/{group_id}/to-quote")
async def plan_group_to_quote(group_id: str, body: dict | None = None, user=Depends(current_user)) -> dict:
    """Crée un devis partiel : les mesures enregistrées de chaque plan disponible,
    regroupées par étage (catégorie = libellé du niveau)."""
    from engines import corps_etat
    from routes.documents import DocIn, DocLine, create_document
    from engines.plan_quote_scope import unique_levels, group_coverage, positive_quantity
    g = await db.plan_groups.find_one({"group_id": group_id, "user_id": user["user_id"]}, {"_id": 0})
    if not g:
        raise HTTPException(404, "Projet multi-niveaux introuvable")
    try:
        margin = float((body or {}).get("margin_pct") or 0)
    except (TypeError, ValueError):
        raise HTTPException(422, "Marge invalide") from None
    if not 0 <= margin <= 1000:
        raise HTTPException(422, "La marge doit être comprise entre 0 et 1 000 %")
    prefs = await _load_ce_prefs(user)
    plan_ids = [lv["plan_id"] for lv in (g.get("levels") or [])]
    plans = await db.plans_takeoff.find(
        {"plan_id": {"$in": plan_ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "measurements": 1}).to_list(200)
    by_id = {p["plan_id"]: p for p in plans}
    coverage = group_coverage(g.get("levels"), by_id, _measure_chiffrage_qty,
                              lambda poste: _known_poste(poste, prefs.get("custom_postes")))
    lines = []
    for lv in unique_levels(g.get("levels")):
        pd = by_id.get(lv["plan_id"])
        if not pd:
            continue
        cat = lv.get("level_label") or "Niveau"
        for m in (pd.get("measurements") or []):
            poste = m.get("poste")
            q = positive_quantity(m, _measure_chiffrage_qty)
            if q is None:
                continue
            if poste and _known_poste(poste, prefs.get("custom_postes")):
                est = _estimate_poste(poste, q, {"margin_pct": margin, "prices": prefs["prices"], "ratios": prefs["ratios"]}, prefs.get("custom_postes"))
                for l in est["lines"]:
                    lines.append(DocLine(kind="line", line_kind="ouvrage", designation=l["designation"],
                                         description=f"{cat} · {est['label']} — {l.get('detail', '')}",
                                         unit=("m2" if l["unit"] == "m²" else ("m3" if l["unit"] == "m³" else l["unit"])),
                                         qty=l["qty"], unit_price_ht=round(l["pu"] * (1 + margin / 100), 6),
                                         cost_price_ht=l["pu"], price_source="plan_chiffrage", price_estimated=True, category=cat))
            else:
                # Mesure non chiffrée : on la descend quand même comme ligne à 0 € à compléter
                is_area = m.get("wall_area_net_m2") is not None or m.get("area_m2") is not None
                unit = "m2" if is_area else "ml"
                lines.append(DocLine(kind="line", line_kind="ouvrage",
                                     designation=(m.get("label") or ("Surface" if is_area else "Linéaire")),
                                     description=f"{cat} · à chiffrer",
                                     unit=("u" if m.get("kind") == "count" else unit), qty=round(q, 2), unit_price_ht=0.0, price_missing=True, category=cat))
    if not lines:
        raise HTTPException(422, "Aucune mesure dans ce projet — tracez des cotes sur les plans d'abord")
    doc = DocIn(doc_type="quote", title=f"Devis partiel — {g['name']}"[:160],
                chantier_id=g.get("chantier_id"), lines=lines, status="draft",
                notes="\n".join(coverage["warnings"]))
    created = await create_document(doc, user)
    # Mémorise les infos de page de garde (réutilisées dans le PDF du devis)
    try:
        cover_meta = {"group_id": group_id, "project_name": f"Estimation partielle — {g['name']}",
                      "levels_count": coverage["plans_count"],
                      "reference": _group_reference(group_id),
                      "client": await _group_cover_client(g, user)}
        doc_id = created.get("doc_id") if isinstance(created, dict) else None
        if doc_id:
            await db.pro_documents.update_one(
                {"doc_id": doc_id, "user_id": user["user_id"]},
                {"$set": {"cover_meta": cover_meta, "takeoff_coverage": coverage}})
    except Exception:
        pass
    return {**created, "coverage": coverage}


def _group_reference(group_id: str) -> str:
    """Référence dossier lisible et stable à partir du group_id (CP-PROJ-XXXX)."""
    tail = (group_id.split("_")[-1] or group_id)[:6].upper()
    return f"CP-PROJ-{tail}"


async def _group_cover_client(g: dict, user: dict) -> dict:
    """Pré-remplit les coordonnées client depuis le chantier rattaché au projet."""
    chantier_id = g.get("chantier_id")
    if not chantier_id:
        return {}
    cht = await db.chantiers.find_one(
        {"chantier_id": chantier_id, "user_id": user["user_id"]},
        {"_id": 0, "client_id": 1, "client_name": 1, "address": 1, "postal_code": 1, "city": 1})
    if not cht:
        return {}
    client = {"name": cht.get("client_name") or "",
              "address": cht.get("address") or "",
              "city": " ".join(x for x in [cht.get("postal_code"), cht.get("city")] if x),
              "email": "", "phone": "", "company": ""}
    if cht.get("client_id"):
        c = await db.clients.find_one({"client_id": cht["client_id"], "user_id": user["user_id"]},
                                      {"_id": 0})
        if c:
            full = " ".join(x for x in [c.get("first_name"), c.get("last_name")] if x)
            client["name"] = c.get("company") or full or client["name"]
            client["company"] = c.get("company") or ""
            client["address"] = c.get("address") or client["address"]
            client["city"] = " ".join(x for x in [c.get("postal_code"), c.get("city")] if x) or client["city"]
            client["email"] = c.get("email") or ""
            client["phone"] = c.get("phone") or ""
    return {k: v for k, v in client.items() if v}


@router.get("/multilevel/groups/{group_id}/cover-info")
async def plan_group_cover_info(group_id: str, user=Depends(current_user)) -> dict:
    """Infos pour la page de garde : référence auto + client pré-rempli (chantier)."""
    g = await db.plan_groups.find_one({"group_id": group_id, "user_id": user["user_id"]}, {"_id": 0})
    if not g:
        raise HTTPException(404, "Projet multi-niveaux introuvable")
    return {"reference": _group_reference(group_id),
            "client": await _group_cover_client(g, user)}


@router.get("/multilevel/groups/{group_id}/pdf")
async def plan_group_pdf(group_id: str, margin_pct: float = Query(0.0),
                         metre_only: bool = Query(False),
                         client_name: str = Query(""), client_company: str = Query(""),
                         client_address: str = Query(""), client_city: str = Query(""),
                         client_email: str = Query(""), client_phone: str = Query(""),
                         user=Depends(current_user)):
    """Rapport PDF consolidé : page de garde pro + métré + chiffrage de tous les niveaux."""
    from io import BytesIO
    from xml.sax.saxutils import escape
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from engines.pdf_takeoff import _styles, DARK, LIGHT_GREY, ORANGE, build_cover_story, make_logo_watermark

    g = await db.plan_groups.find_one({"group_id": group_id, "user_id": user["user_id"]}, {"_id": 0})
    if not g:
        raise HTTPException(404, "Projet multi-niveaux introuvable")
    payload = await _group_payload(g, user, with_consolidation=True, margin=margin_pct)

    # Page de garde : branding « Identité pro » + client (override UI ou chantier)
    branding = await _resolve_branding(user["user_id"])
    overrides = {"name": client_name.strip(), "company": client_company.strip(),
                 "address": client_address.strip(), "city": client_city.strip(),
                 "email": client_email.strip(), "phone": client_phone.strip()}
    overrides = {k: v for k, v in overrides.items() if v}
    client = overrides or await _group_cover_client(g, user)
    levels = payload.get("levels") or []
    totals = payload.get("totals") or {}

    buf = BytesIO()
    docp = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                             topMargin=16 * mm, bottomMargin=16 * mm)
    st = _styles()
    story = []
    # The cover must not promote a partial measured subtotal to a project total.
    cover_ttc = None
    story += build_cover_story(
        branding,
        {"name": f"Relevé partiel — {g['name']}", "levels_count": len(levels), "total_ttc": cover_ttc},
        client, _group_reference(group_id), st)
    if metre_only:
        story.append(Paragraph("MÉTRÉ PROJET MULTI-NIVEAUX (SANS PRIX)", st["kicker"]))
    else:
        story.append(Paragraph("RAPPORT DE PROJET MULTI-NIVEAUX", st["kicker"]))
    story.append(Paragraph(f"<b>{g['name']}</b>", st["h1"]))
    sub = f"{len(payload.get('levels') or [])} niveau(x)"
    if not metre_only:
        sub += f" · marge {margin_pct:.0f}%"
    story.append(Paragraph(sub, st["muted"]))
    for warning in (payload.get("coverage") or {}).get("warnings", []):
        story.append(Paragraph(escape(warning), st["muted"]))
    story.append(Spacer(1, 8 * mm))

    if metre_only:
        rows = [["Niveau", "Plan", "Surface (m²)", "Linéaire (ml)", "Mesures"]]
        for lv in (payload.get("levels") or []):
            c = lv.get("consolidated") or {}
            me = c.get("metre") or {}
            rows.append([
                lv.get("level_label") or "—",
                (lv.get("filename") or "")[:34],
                f"{me.get('area_m2', 0):.2f}", f"{me.get('length_ml', 0):.2f}",
                str(me.get("measures", 0)),
            ])
        tot = payload.get("totals") or {}
        rows.append(["SOUS-TOTAL", "", f"{tot.get('area_m2', 0):.2f}",
                     f"{tot.get('length_ml', 0):.2f}", ""])
        tbl = Table(rows, colWidths=[30 * mm, 56 * mm, 32 * mm, 32 * mm, 26 * mm])
    else:
        rows = [["Niveau", "Plan", "Surface (m²)", "Linéaire (ml)", "Mesures", "HT (€)", "TTC (€)"]]
        for lv in (payload.get("levels") or []):
            c = lv.get("consolidated") or {}
            me = c.get("metre") or {}
            ch = c.get("chiffrage") or {}
            rows.append([
                lv.get("level_label") or "—",
                (lv.get("filename") or "")[:28],
                f"{me.get('area_m2', 0):.2f}", f"{me.get('length_ml', 0):.2f}",
                str(me.get("measures", 0)),
                f"{ch.get('ht_with_margin', 0):.2f}" if ch.get("priced_measures") else "N/C",
                f"{ch.get('ttc', 0):.2f}" if ch.get("priced_measures") else "N/C",
            ])
        tot = payload.get("totals") or {}
        has_priced = any((lv.get("consolidated") or {}).get("chiffrage", {}).get("priced_measures") for lv in levels)
        rows.append(["SOUS-TOTAL", "", f"{tot.get('area_m2', 0):.2f}", f"{tot.get('length_ml', 0):.2f}",
                     "", f"{tot.get('ht_with_margin', 0):.2f}" if has_priced else "N/C",
                     f"{tot.get('ttc', 0):.2f}" if has_priced else "N/C"])
        tbl = Table(rows, colWidths=[26 * mm, 40 * mm, 22 * mm, 22 * mm, 18 * mm, 24 * mm, 24 * mm])

    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), ORANGE),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.Color(0.96, 0.96, 0.96)]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6 * mm))

    # Détail des cotes par niveau (comme le relevé mono-plan, pour chaque étage)
    lvl_plan_ids = [lv.get("plan_id") for lv in (g.get("levels") or [])]
    detail_docs = await db.plans_takeoff.find(
        {"plan_id": {"$in": lvl_plan_ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "measurements": 1}).to_list(50)
    detail_by_id = {d["plan_id"]: d for d in detail_docs}
    for lv in levels:
        pd = detail_by_id.get(lv.get("plan_id"))
        if not pd:
            continue
        story.append(Paragraph(f"DÉTAIL DES COTES — {lv.get('level_label') or 'Niveau'}", st["kicker"]))
        thumb = await _ensure_level_thumb(lv.get("plan_id"), user["user_id"])
        sub = _detail_cotes_flowables(pd.get("measurements") or [], st, thumb_b64=thumb)
        if sub:
            story += sub
        else:
            story.append(Paragraph("Aucune cote détaillée sur ce niveau.", st["muted"]))
        story.append(Spacer(1, 4 * mm))

    if metre_only:
        story.append(Paragraph("Métré déterministe — ConstruPilot. Relevé de quantités (surfaces, linéaires) sans prix.", st["muted"]))
    else:
        story.append(Paragraph("Métré et chiffrage déterministes — ConstruPilot. Document non contractuel.", st["muted"]))
    wm = make_logo_watermark((branding or {}).get("logo_b64"))
    if wm:
        docp.build(story, onFirstPage=wm, onLaterPages=wm)
    else:
        docp.build(story)
    pdf = buf.getvalue(); buf.close()
    safe = "".join(ch if ch.isalnum() else "_" for ch in g["name"])[:40] or "projet"
    prefix = "metre_projet" if metre_only else "projet"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{prefix}_{safe}.pdf"'})


def _plan_metre_only(pd: dict) -> dict:
    """Agrège le métré (m² / ml) des mesures déjà calculées d'un plan + détail ligne à ligne."""
    area = length = 0.0
    items = []
    for m in (pd.get("measurements") or []):
        lbl = m.get("label") or m.get("kind") or "Mesure"
        if m.get("area_m2") is not None:
            v = float(m.get("area_m2") or 0); area += v
            items.append((lbl, v, "m²"))
        elif m.get("length_m") is not None:
            v = float(m.get("length_m") or 0); length += v
            items.append((lbl, v, "ml"))
        elif m.get("count") is not None:
            items.append((lbl, float(m.get("count") or 0), "u"))
    return {"area_m2": round(area, 2), "length_ml": round(length, 2),
            "measures": len(pd.get("measurements") or []), "items": items}


class MetreMultiIn(BaseModel):
    plan_ids: list[str] = Field(default_factory=list)
    project_name: str | None = None


@router.post("/metre-multi-pdf")
async def metre_multi_pdf(body: MetreMultiIn, user=Depends(current_user)):
    """UN seul PDF de MÉTRÉ (cotes déjà calculées) pour plusieurs plans — sans prix ni TVA."""
    from io import BytesIO
    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from engines.pdf_takeoff import (_styles, DARK, LIGHT_GREY, ORANGE,
                                      build_cover_story, make_logo_watermark)
    import secrets

    if len(body.plan_ids) < 1:
        raise HTTPException(400, "Sélectionnez au moins 1 plan")
    plans = await db.plans_takeoff.find(
        {"plan_id": {"$in": body.plan_ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "filename": 1, "measurements": 1}).to_list(200)
    by_id = {p["plan_id"]: p for p in plans}
    rows_data, tot_area, tot_len, tot_meas = [], 0.0, 0.0, 0
    for pid in body.plan_ids:  # conserve l'ordre de sélection
        pd = by_id.get(pid)
        if not pd:
            continue
        me = _plan_metre_only(pd)
        rows_data.append((pd.get("filename") or pid, me))
        tot_area += me["area_m2"]; tot_len += me["length_ml"]; tot_meas += me["measures"]
    if not rows_data:
        raise HTTPException(400, "Aucun plan trouvé")

    branding = await _resolve_branding(user["user_id"])
    buf = BytesIO()
    docp = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                             topMargin=16 * mm, bottomMargin=16 * mm)
    st = _styles()
    name = (body.project_name or "Métré groupé").strip() or "Métré groupé"
    reference = f"METRE-{secrets.token_hex(3).upper()}"
    story = build_cover_story(
        branding,
        {"name": name, "levels_count": len(rows_data), "total_ttc": None},
        {}, reference, st)
    story.append(Paragraph("MÉTRÉ GROUPÉ MULTI-PLANS (SANS PRIX)", st["kicker"]))
    story.append(Paragraph(f"<b>{name}</b>", st["h1"]))
    story.append(Paragraph(f"{len(rows_data)} plan(s) · cotes déjà calculées", st["muted"]))
    story.append(Spacer(1, 8 * mm))

    # Tableau récapitulatif projet
    rows = [["Plan", "Surface (m²)", "Linéaire (ml)", "Mesures"]]
    for fn, me in rows_data:
        rows.append([fn[:46], f"{me['area_m2']:.2f}", f"{me['length_ml']:.2f}", str(me["measures"])])
    rows.append(["TOTAL PROJET", f"{round(tot_area, 2):.2f}", f"{round(tot_len, 2):.2f}", str(tot_meas)])
    tbl = Table(rows, colWidths=[78 * mm, 34 * mm, 34 * mm, 28 * mm])
    recap_style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), ORANGE),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.Color(0.96, 0.96, 0.96)]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    tbl.setStyle(TableStyle(recap_style))
    story.append(tbl)

    # Détail pièce par pièce (ligne à ligne) sous chaque plan
    for fn, me in rows_data:
        story.append(Paragraph(f"Détail — {fn}", st["h2"]))
        if not me["items"]:
            story.append(Paragraph("Aucune mesure sur ce plan.", st["muted"]))
            continue
        drows = [["Désignation", "Quantité", "Unité"]]
        for lbl, qty, unit in me["items"]:
            drows.append([str(lbl)[:60], f"{qty:.2f}", unit])
        drows.append([f"Sous-total {fn[:30]}",
                      f"{me['area_m2']:.2f} m² · {me['length_ml']:.2f} ml", ""])
        dt = Table(drows, colWidths=[104 * mm, 44 * mm, 22 * mm])
        dt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.4, LIGHT_GREY),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BACKGROUND", (0, -1), (-1, -1), colors.Color(0.93, 0.93, 0.93)),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.Color(0.97, 0.97, 0.97)]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(dt)

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Métré déterministe — ConstruPilot. Relevé de quantités (surfaces, linéaires) sans prix.",
        st["muted"]))
    wm = make_logo_watermark((branding or {}).get("logo_b64"))
    if wm:
        docp.build(story, onFirstPage=wm, onLaterPages=wm)
    else:
        docp.build(story)
    pdf = buf.getvalue(); buf.close()
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'attachment; filename="metre_groupe_{secrets.token_hex(3)}.pdf"'})


# --------------------------------------------------------------------------
# MÉTRÉ COMPARÉ — versions (snapshots) d'un niveau + diff avant/après
# --------------------------------------------------------------------------
async def _metre_summary(plan_doc: dict, prefs: dict, margin: float) -> dict:
    from engines import corps_etat
    area = length = 0.0
    ht = 0.0
    by_poste: dict = {}
    for m in (plan_doc.get("measurements") or []):
        if m.get("area_m2") is not None:
            area += float(m.get("area_m2") or 0)
        elif m.get("length_m") is not None:
            length += float(m.get("length_m") or 0)
        poste = m.get("poste")
        q = _measure_chiffrage_qty(m)
        if poste and _known_poste(poste, prefs.get("custom_postes")) and q > 0:
            est = _estimate_poste(poste, q, {"margin_pct": margin, "prices": prefs["prices"], "ratios": prefs["ratios"]}, prefs.get("custom_postes"))
            row = by_poste.setdefault(poste, {"qty": 0.0, "ht": 0.0})
            row["qty"] += q
            row["ht"] += est["totals"]["ht_with_margin"]
            ht += est["totals"]["ht_with_margin"]
    return {"area_m2": round(area, 2), "length_ml": round(length, 2),
            "measures": len(plan_doc.get("measurements") or []),
            "ht": round(ht, 2), "by_poste": {k: {"qty": round(v["qty"], 2), "ht": round(v["ht"], 2)} for k, v in by_poste.items()}}


@router.post("/metre-versions")
async def create_metre_version(body: dict, user=Depends(current_user)) -> dict:
    """Fige l'état actuel du métré d'un plan (niveau) comme version comparable."""
    plan_id = (body or {}).get("plan_id")
    pd = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "measurements": 1, "filename": 1})
    if not pd:
        raise HTTPException(404, "Plan introuvable")
    prefs = await _load_ce_prefs(user)
    v = {"version_id": "mv_" + secrets.token_hex(6), "user_id": user["user_id"], "plan_id": plan_id,
         "label": (str((body or {}).get("label") or "").strip()[:60]) or _now()[:16].replace("T", " "),
         "summary": await _metre_summary(pd, prefs, float((body or {}).get("margin_pct") or 0)),
         "created_at": _now()}
    await db.metre_versions.insert_one(dict(v))
    v.pop("_id", None); v.pop("user_id", None)
    return {"ok": True, "version": v}


@router.get("/metre-versions/compare")
async def compare_metre_versions(a: str = Query(...), b: str = Query(...), user=Depends(current_user)) -> dict:
    """Compare deux versions d'un même niveau : deltas globaux + par poste."""
    va = await db.metre_versions.find_one({"version_id": a, "user_id": user["user_id"]}, {"_id": 0, "user_id": 0})
    vb = await db.metre_versions.find_one({"version_id": b, "user_id": user["user_id"]}, {"_id": 0, "user_id": 0})
    if not va or not vb:
        raise HTTPException(404, "Version introuvable")
    sa, sb = va["summary"], vb["summary"]
    postes = sorted(set(sa["by_poste"]) | set(sb["by_poste"]))
    by_poste = []
    for p in postes:
        qa = sa["by_poste"].get(p, {}).get("qty", 0); qb = sb["by_poste"].get(p, {}).get("qty", 0)
        ha = sa["by_poste"].get(p, {}).get("ht", 0); hb = sb["by_poste"].get(p, {}).get("ht", 0)
        by_poste.append({"poste": p, "qty_a": qa, "qty_b": qb, "qty_delta": round(qb - qa, 2),
                         "ht_a": ha, "ht_b": hb, "ht_delta": round(hb - ha, 2)})
    return {
        "a": {"version_id": a, "label": va["label"], "summary": sa},
        "b": {"version_id": b, "label": vb["label"], "summary": sb},
        "delta": {"area_m2": round(sb["area_m2"] - sa["area_m2"], 2),
                  "length_ml": round(sb["length_ml"] - sa["length_ml"], 2),
                  "measures": sb["measures"] - sa["measures"],
                  "ht": round(sb["ht"] - sa["ht"], 2)},
        "by_poste": by_poste,
    }


@router.get("/metre-versions/{plan_id}")
async def list_metre_versions(plan_id: str, user=Depends(current_user)) -> dict:
    rows = await db.metre_versions.find({"plan_id": plan_id, "user_id": user["user_id"]},
                                        {"_id": 0, "user_id": 0}).sort("created_at", -1).to_list(100)
    return {"versions": rows}


@router.delete("/metre-versions/{version_id}")
async def delete_metre_version(version_id: str, user=Depends(current_user)) -> dict:
    await db.metre_versions.delete_one({"version_id": version_id, "user_id": user["user_id"]})
    return {"ok": True}


@router.post("/corps-etat/estimate")
async def corps_etat_estimate(body: CorpsEtatIn, user=Depends(current_user)) -> dict:
    """Chiffrage déterministe d'un poste (compositions + prix/ratios de l'artisan),
    même principe que le gros œuvre, appliqué à une quantité mesurée sur le plan."""
    from engines import corps_etat
    prefs = await _load_ce_prefs(user)
    params = dict(body.params or {})
    params["prices"] = {**prefs["prices"], **(params.get("prices") or {})}
    params["ratios"] = {**prefs["ratios"], **(params.get("ratios") or {})}
    try:
        return _estimate_poste(body.poste, body.quantity, params, prefs["custom_postes"])
    except ValueError as e:
        raise HTTPException(422, str(e))


def _measure_chiffrage_qty(m: dict) -> float:
    if m.get("wall_area_net_m2") is not None:
        return float(m["wall_area_net_m2"])
    if m.get("area_m2") is not None:
        return float(m["area_m2"])
    return float(m.get("value_m") if m.get("value_m") is not None else (m.get("length_m") or 0))


class CePageIn(BaseModel):
    page_index: int | None = None
    margin_pct: float = 0


@router.post("/{plan_id}/corps-etat/estimate-page")
async def corps_etat_estimate_page(plan_id: str, body: CePageIn,
                                   user=Depends(current_user)) -> dict:
    """Chiffre d'un coup toutes les mesures d'une page ayant un poste défini."""
    from engines import corps_etat
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "measurements": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    prefs = await _load_ce_prefs(user)
    ms = p.get("measurements") or []
    if body.page_index is not None:
        ms = [m for m in ms if m.get("page_index") == body.page_index]
    items, grand_ht, grand_ttc, skipped = [], 0.0, 0.0, 0
    for m in ms:
        poste = m.get("poste")
        q = _measure_chiffrage_qty(m)
        if not poste or not _known_poste(poste, prefs.get("custom_postes")) or q <= 0:
            skipped += 1
            continue
        est = _estimate_poste(poste, q, {"margin_pct": body.margin_pct,
                                         "prices": prefs["prices"], "ratios": prefs["ratios"]},
                              prefs.get("custom_postes"))
        items.append({"measurement_id": m.get("measurement_id"), "label": m.get("label"), **est})
        grand_ht += est["totals"]["ht_with_margin"]
        grand_ttc += est["totals"]["ttc"]
    return {"items": items, "count": len(items), "skipped": skipped,
            "totals": {"ht_with_margin": round(grand_ht, 2), "ttc": round(grand_ttc, 2)}}


@router.delete("/{plan_id}/measurements/{measurement_id}")
async def delete_measurement(plan_id: str, measurement_id: str,
                             user=Depends(current_user)) -> dict:
    """Supprime une mesure ad-hoc (volet Objets)."""
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$pull": {"measurements": {"measurement_id": measurement_id}},
         "$set": {"updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Plan introuvable")
    return {"ok": True}


class MeasureLabelIn(BaseModel):
    label: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, max_length=9)
    poste: str | None = Field(default=None, max_length=40)


@router.patch("/{plan_id}/measurements/{measurement_id}")
async def rename_measurement(plan_id: str, measurement_id: str,
                             body: MeasureLabelIn, user=Depends(current_user)) -> dict:
    """Modifie le libellé, la couleur et/ou le poste d'une mesure."""
    sets: dict = {"updated_at": _now()}
    if body.label is not None:
        sets["measurements.$.label"] = body.label.strip()[:80] or None
    if body.color is not None:
        sets["measurements.$.color"] = body.color.strip()[:9] or None
    if body.poste is not None:
        sets["measurements.$.poste"] = body.poste.strip()[:40] or None
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"],
         "measurements.measurement_id": measurement_id},
        {"$set": sets})
    if res.matched_count == 0:
        raise HTTPException(404, "Mesure introuvable")
    return {"ok": True}


_POSTE_KEYWORDS = [
    ("plancher chauffant", "chauffage_sol"), ("chauffage au sol", "chauffage_sol"),
    ("chauffage", "chauffage_sol"), ("plancher chauff", "chauffage_sol"),
    ("ragréage", "ragreage"), ("ragreage", "ragreage"),
    ("étanchéité", "etancheite"), ("etancheite", "etancheite"), ("sel ", "etancheite"),
    ("démolition", "demolition"), ("demolition", "demolition"), ("dépose", "demolition"), ("depose", "demolition"),
    ("faux plafond", "plafond"), ("faux-plafond", "plafond"),
    ("cloison", "cloison"), ("plafond", "plafond"), ("faience", "faience"), ("faïence", "faience"),
    ("carrelage", "carrelage"), ("parquet", "parquet"), ("chape", "chape"), ("plinthe", "plinthes"),
    ("isolation", "isolation"), ("enduit", "enduit"), ("doublage", "placo"), ("placo", "placo"),
    ("peinture", "peinture"), ("plancher", "carrelage"), ("dalle", "chape"), ("sol", "carrelage"),
    ("mur", "peinture"), ("escalier", "escalier"),
]


def _suggest_poste(m: dict) -> str:
    """Devine un poste chiffrable à partir du libellé puis de la famille (déterministe)."""
    label = (m.get("label") or "").lower()
    for kw, poste in _POSTE_KEYWORDS:
        if kw in label:
            return poste
    kind = m.get("kind")
    if m.get("wall_area_net_m2") is not None:
        return "peinture"
    if kind in ("polygon", "cumulative_area") or m.get("area_m2") is not None:
        return "carrelage"
    if kind in ("distance", "cumulative", "polyline"):
        return "plinthes"
    return "peinture"


@router.post("/{plan_id}/corps-etat/suggest-postes")
async def corps_etat_suggest_postes(plan_id: str, body: CePageIn, user=Depends(current_user)) -> dict:
    """Propose un poste pour chaque mesure chiffrable de la page (auto, à valider)."""
    from engines import corps_etat
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "measurements": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    ms = p.get("measurements") or []
    if body.page_index is not None:
        ms = [m for m in ms if m.get("page_index") == body.page_index]
    rows = []
    for m in ms:
        q = _measure_chiffrage_qty(m)
        if q <= 0:
            continue
        fam = "length" if m.get("kind") in ("distance", "cumulative", "polyline") and m.get("wall_area_net_m2") is None else "area"
        rows.append({"measurement_id": m.get("measurement_id"),
                     "label": m.get("label") or ("Surface" if fam == "area" else "Linéaire"),
                     "qty": round(q, 2), "family": fam,
                     "current_poste": m.get("poste"),
                     "suggested_poste": m.get("poste") or _suggest_poste(m)})
    prefs = await _load_ce_prefs(user)
    return {"rows": rows, "postes": corps_etat.catalog() + list(prefs["custom_postes"])}


class AssignPostesIn(BaseModel):
    assignments: list[dict] = Field(default_factory=list)  # [{measurement_id, poste}]


@router.post("/{plan_id}/corps-etat/assign-postes")
async def corps_etat_assign_postes(plan_id: str, body: AssignPostesIn, user=Depends(current_user)) -> dict:
    """Affecte en masse un poste à plusieurs mesures (puis chiffrage possible)."""
    from engines import corps_etat
    prefs = await _load_ce_prefs(user)
    n = 0
    for a in body.assignments:
        mid = (a.get("measurement_id") or "").strip()
        poste = (a.get("poste") or "").strip()
        if not mid or not _known_poste(poste, prefs.get("custom_postes")):
            continue
        res = await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"], "measurements.measurement_id": mid},
            {"$set": {"measurements.$.poste": poste, "updated_at": _now()}})
        if res.modified_count:
            n += 1
    return {"ok": True, "assigned": n}


@router.delete("/{plan_id}/measurements")
async def clear_measurements(plan_id: str, page_index: int = 0,
                             user=Depends(current_user)) -> dict:
    """Efface toutes les mesures ad-hoc d'une page."""
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$pull": {"measurements": {"page_index": page_index}},
         "$set": {"updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Plan introuvable")
    return {"ok": True}


# ============ DÉDUCTION D'OUVERTURE (fenêtre/porte) sur une cote linéaire ============

class OpeningDeductIn(BaseModel):
    width_m: float | None = Field(default=None, gt=0, lt=1000)
    height_m: float | None = Field(default=None, gt=0, lt=1000)
    count: int = Field(default=1, ge=1, le=100)
    points: list[tuple[float, float]] | None = None
    label: str | None = Field(default=None, max_length=80)


def _measure_points(m: dict) -> list:
    out = []
    for p in (m.get("points") or []):
        if isinstance(p, (list, tuple)) and len(p) >= 2:
            try:
                out.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError):
                pass
    return out


def _facade_bbox(measures: list):
    xs, ys = [], []
    for m in measures:
        for x, y in _measure_points(m):
            xs.append(x); ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _measure_is_facade(m: dict, bbox) -> bool:
    """Vrai si la cote longe le périmètre extérieur du plan (détection par POSITION)."""
    if not bbox:
        return False
    minx, miny, maxx, maxy = bbox
    tol = max(22.0, 0.06 * max(maxx - minx, maxy - miny))
    pts = _measure_points(m)
    if len(pts) < 2:
        return False
    near = sum(1 for x, y in pts
               if abs(x - minx) <= tol or abs(x - maxx) <= tol
               or abs(y - miny) <= tol or abs(y - maxy) <= tol)
    return near / len(pts) >= 0.6



# Classement d'une cote par famille d'ouvrage (poste en priorité, sinon libellé).
_FAMILY_ORDER = ["Murs", "Cloisons", "Sols / Planchers", "Plafonds", "Autres"]
_POSTE_FAMILY = {
    "peinture": "Murs", "enduit": "Murs", "isolation": "Murs",
    "cloison": "Cloisons", "doublage": "Cloisons", "placo": "Cloisons", "faience": "Cloisons",
    "parquet": "Sols / Planchers", "carrelage": "Sols / Planchers", "chape": "Sols / Planchers",
    "ragreage": "Sols / Planchers", "etancheite": "Sols / Planchers", "chauffage_sol": "Sols / Planchers",
    "plafond": "Plafonds",
}


def _measure_family(m: dict) -> str:
    poste = (m.get("poste") or "").lower()
    for key, fam in _POSTE_FAMILY.items():
        if key in poste:
            return fam
    lbl = (m.get("label") or m.get("kind") or "").lower()
    if any(k in lbl for k in ["cloison", "placo", "doublage", "séparation", "separation"]):
        return "Cloisons"
    if "plafond" in lbl:
        return "Plafonds"
    if any(k in lbl for k in ["sol", "plancher", "dalle", "carrelage", "parquet", "chape", "carreau"]):
        return "Sols / Planchers"
    if any(k in lbl for k in ["mur", "façade", "facade", "parpaing"]):
        return "Murs"
    return "Autres"


def _build_thumb_image(b64, max_w_mm: float = 45):
    """Flowable Image à partir d'une vignette JPEG base64 (aperçu du plan)."""
    if not b64:
        return None
    try:
        import base64
        from io import BytesIO
        from reportlab.lib.units import mm
        from reportlab.platypus import Image as RLImage
        from PIL import Image as PILImage
        raw = base64.b64decode(b64)
        pim = PILImage.open(BytesIO(raw))
        w, h = pim.size
        max_w = max_w_mm * mm
        ratio = (h / w) if w else 1.0
        return RLImage(BytesIO(raw), width=max_w, height=max_w * ratio)
    except Exception:
        return None


def _measure_detail_rows(m: dict):
    """(rows, surface_m2, linear_ml) pour une cote, ou None si rien à afficher."""
    wh = m.get("wall_height_m")
    gross = m.get("gross_m")
    rows = [["Désignation", "Détail", "Valeur"]]
    surface = linear = 0.0
    if m.get("wall_area_gross_m2") is not None:
        rows.append(["Mur brut", f"{float(gross or 0):.2f} m × {float(wh or 0):.2f} m", f"{m['wall_area_gross_m2']:.2f} m²"])
        for o in (m.get("openings") or []):
            w = float(o.get("width_m") or 0); h = float(o.get("height_m") or 0); c = int(o.get("count", 1))
            if h > 0:
                rows.append([f"− Ouverture{(' ×' + str(c)) if c > 1 else ''}", f"{w:.2f} m × {h:.2f} m", f"− {w * h * c:.2f} m²"])
        net = float(m.get("wall_area_net_m2", 0) or 0)
        ln = float(m.get("length_m") or 0)
        rows.append(["Mur net (ouvertures déduites)", "", f"{net:.2f} m²"])
        rows.append(["Linéaire net", "", f"{ln:.2f} ml"])
        surface = net; linear = ln
    elif m.get("area_m2") is not None:
        a = float(m["area_m2"]); rows.append(["Surface", "", f"{a:.2f} m²"]); surface = a
    elif m.get("length_m") is not None or gross is not None:
        ln = float(m.get("length_m") or gross or 0); rows.append(["Linéaire", "", f"{ln:.2f} ml"]); linear = ln
    else:
        return None
    return rows, surface, linear


def _detail_cotes_flowables(measures, st, thumb_b64=None):
    """Détail des cotes regroupées par famille (Murs, Cloisons, Sols, Plafonds),
    avec vignette du plan en tête, sous-total par famille et sous-total du niveau."""
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    DARKC = colors.Color(0.12, 0.14, 0.18)
    GREYC = colors.Color(0.80, 0.82, 0.85)
    ACC = colors.Color(0.90, 0.47, 0.13)
    FAMBG = colors.Color(0.93, 0.95, 0.98)
    flow = []
    img = _build_thumb_image(thumb_b64, 45)
    if img is not None:
        flow.append(img)
        flow.append(Spacer(1, 2 * mm))

    groups: dict[str, list] = {}
    for m in (measures or []):
        res = _measure_detail_rows(m)
        if res is None:
            continue
        groups.setdefault(_measure_family(m), []).append((m, res))
    if not groups:
        return flow

    meas_style = TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARKC), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("GRID", (0, 0), (-1, -1), 0.4, GREYC),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.97, 0.97, 0.97)]),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ])

    lvl_surface = lvl_linear = 0.0
    for fam in _FAMILY_ORDER:
        if fam not in groups:
            continue
        flow.append(Paragraph(fam, st["h2"]))
        fam_surface = fam_linear = 0.0
        for m, (rows, surf, lin) in groups[fam]:
            label = m.get("label") or m.get("kind") or "Mesure"
            flow.append(Paragraph(f"<b>{label}</b>", st["body"]))
            t = Table(rows, colWidths=[72 * mm, 52 * mm, 34 * mm])
            t.setStyle(meas_style)
            flow.append(t)
            flow.append(Spacer(1, 2 * mm))
            fam_surface += surf; fam_linear += lin
        fam_row = [[f"Sous-total {fam}", f"{fam_surface:.2f} m²", f"{fam_linear:.2f} ml"]]
        ft = Table(fam_row, colWidths=[90 * mm, 34 * mm, 34 * mm])
        ft.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), FAMBG),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.4, GREYC),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        flow.append(ft)
        flow.append(Spacer(1, 4 * mm))
        lvl_surface += fam_surface; lvl_linear += fam_linear

    lvl_row = [["SOUS-TOTAL NIVEAU", f"{lvl_surface:.2f} m²", f"{lvl_linear:.2f} ml"]]
    lt = Table(lvl_row, colWidths=[90 * mm, 34 * mm, 34 * mm])
    lt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACC), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    flow.append(lt)
    return flow


async def _ensure_level_thumb(plan_id: str, user_id: str):
    """Renvoie la vignette base64 d'un plan (la génère et met en cache si absente)."""
    doc = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id}, {"_id": 0, "thumb_b64": 1})
    if doc and doc.get("thumb_b64"):
        return doc["thumb_b64"]
    full = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id}, {"_id": 0, "pages": {"$slice": 1}})
    pages = (full or {}).get("pages") or []
    img_b64 = pages[0].get("image_png_b64") if pages else None
    if not img_b64:
        return None
    try:
        import base64
        from io import BytesIO
        from PIL import Image
        im = Image.open(BytesIO(base64.b64decode(img_b64))).convert("RGB")
        im.thumbnail((240, 240))
        out = BytesIO(); im.save(out, format="JPEG", quality=70)
        b64 = base64.b64encode(out.getvalue()).decode()
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user_id}, {"$set": {"thumb_b64": b64}})
        return b64
    except Exception:
        return None









async def _persist_linear(plan_id: str, user_id: str, measurement_id: str, sets: dict) -> None:
    upd = {f"measurements.$.{k}": v for k, v in sets.items()}
    upd["updated_at"] = _now()
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user_id,
         "measurements.measurement_id": measurement_id}, {"$set": upd})


async def _find_linear_measure(plan_id: str, measurement_id: str, user_id: str):
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "calibrations": 1, "measurements": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    m = next((x for x in (p.get("measurements") or [])
              if x.get("measurement_id") == measurement_id), None)
    if not m:
        raise HTTPException(404, "Mesure introuvable")
    if m.get("kind") not in ("distance", "cumulative", "polyline", "manual_linear"):
        raise HTTPException(422, "La déduction d'ouverture s'applique aux cotes linéaires (mur, distance)")
    return p, m


@router.post("/{plan_id}/measurements/{measurement_id}/deduct-opening")
async def deduct_opening(plan_id: str, measurement_id: str,
                         body: OpeningDeductIn, user=Depends(current_user)) -> dict:
    """Soustrait la largeur d'une fenêtre/porte du total d'un mur (dessinée OU saisie)."""
    p, m = await _find_linear_measure(plan_id, measurement_id, user["user_id"])
    if body.points and len(body.points) == 2:
        calib = (p.get("calibrations") or {}).get(str(m.get("page_index", 0)))
        if not calib:
            raise HTTPException(400, "Page non calibrée")
        w = round(G.distance_m(body.points[0], body.points[1], calib["pixels_per_meter"]), 3)
        drawn = [list(body.points[0]), list(body.points[1])]
    elif body.width_m:
        w = round(float(body.width_m), 3)
        drawn = None
    else:
        raise HTTPException(422, "Dessinez la fenêtre (2 points) ou saisissez une largeur")
    if not (w > 0):
        raise HTTPException(422, "Largeur d'ouverture invalide")
    cnt = int(body.count or 1)
    opening = {"opening_id": "op_" + secrets.token_hex(4), "width_m": w, "count": cnt,
               "height_m": (round(float(body.height_m), 3) if body.height_m else None),
               "label": (body.label or "").strip()[:80] or None, "points": drawn,
               "created_at": _now()}
    m["gross_m"] = round(_measure_gross_m(m), 3)
    m["openings"] = (m.get("openings") or []) + [opening]
    sets = _recompute_linear_sets(m)
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"],
         "measurements.measurement_id": measurement_id},
        {"$set": {**{f"measurements.$.{k}": v for k, v in sets.items()}, "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Mesure introuvable")
    return {"ok": True, "value_m": sets["value_m"], "gross_m": sets["gross_m"],
            "deducted_m": round(sets["gross_m"] - sets["value_m"], 3), "opening": opening,
            "wall_area_gross_m2": sets.get("wall_area_gross_m2"),
            "openings_area_m2": sets.get("openings_area_m2"),
            "wall_area_net_m2": sets.get("wall_area_net_m2")}


class OpeningPatchIn(BaseModel):
    width_m: float | None = Field(default=None, gt=0, lt=1000)
    height_m: float | None = Field(default=None, gt=0, lt=1000)
    count: int | None = Field(default=None, ge=1, le=100)
    label: str | None = Field(default=None, max_length=80)


@router.patch("/{plan_id}/measurements/{measurement_id}/openings/{opening_id}")
async def update_opening(plan_id: str, measurement_id: str, opening_id: str,
                         body: OpeningPatchIn, user=Depends(current_user)) -> dict:
    """Corrige la largeur / la hauteur / le nombre d'une ouverture déjà déduite — recalcule le net + les m²."""
    _, m = await _find_linear_measure(plan_id, measurement_id, user["user_id"])
    openings = m.get("openings") or []
    found = False
    for o in openings:
        if o.get("opening_id") == opening_id:
            if body.width_m is not None:
                o["width_m"] = round(float(body.width_m), 3)
            if body.height_m is not None:
                o["height_m"] = round(float(body.height_m), 3)
            if body.count is not None:
                o["count"] = int(body.count)
            if body.label is not None:
                o["label"] = (body.label or "").strip()[:80] or None
            found = True
            break
    if not found:
        raise HTTPException(404, "Ouverture introuvable")
    m["openings"] = openings
    sets = _recompute_linear_sets(m)
    await _persist_linear(plan_id, user["user_id"], measurement_id, sets)
    return {"ok": True, "value_m": sets["value_m"], "gross_m": sets["gross_m"],
            "deducted_m": round(sets["gross_m"] - sets["value_m"], 3),
            "wall_area_gross_m2": sets.get("wall_area_gross_m2"),
            "openings_area_m2": sets.get("openings_area_m2"),
            "wall_area_net_m2": sets.get("wall_area_net_m2")}


@router.delete("/{plan_id}/measurements/{measurement_id}/openings/{opening_id}")
async def remove_opening(plan_id: str, measurement_id: str, opening_id: str,
                         user=Depends(current_user)) -> dict:
    """Retire une ouverture déduite — recalcule le total net du mur + les m² (réversible)."""
    _, m = await _find_linear_measure(plan_id, measurement_id, user["user_id"])
    m["openings"] = [o for o in (m.get("openings") or []) if o.get("opening_id") != opening_id]
    sets = _recompute_linear_sets(m)
    await _persist_linear(plan_id, user["user_id"], measurement_id, sets)
    return {"ok": True, "value_m": sets["value_m"], "gross_m": sets["gross_m"],
            "deducted_m": round(sets["gross_m"] - sets["value_m"], 3),
            "wall_area_gross_m2": sets.get("wall_area_gross_m2"),
            "openings_area_m2": sets.get("openings_area_m2"),
            "wall_area_net_m2": sets.get("wall_area_net_m2")}


class WallHeightIn(BaseModel):
    height_m: float | None = Field(default=None, ge=0, lt=1000)


@router.post("/{plan_id}/measurements/{measurement_id}/wall-height")
async def set_wall_height(plan_id: str, measurement_id: str,
                          body: WallHeightIn, user=Depends(current_user)) -> dict:
    """Fixe (ou retire) la hauteur d'un mur linéaire → calcule automatiquement
    la surface de mur brute, la surface d'ouvertures et la surface nette (m²)."""
    _, m = await _find_linear_measure(plan_id, measurement_id, user["user_id"])
    m["gross_m"] = round(_measure_gross_m(m), 3)
    m["wall_height_m"] = float(body.height_m) if body.height_m else 0
    sets = _recompute_linear_sets(m)
    await _persist_linear(plan_id, user["user_id"], measurement_id, sets)
    return {"ok": True, **sets}


class BulkWallHeightIn(BaseModel):
    height_m: float | None = Field(default=None, ge=0, lt=1000)
    page_index: int | None = None


@router.post("/{plan_id}/measurements/wall-height-bulk")
async def set_wall_height_bulk(plan_id: str, body: BulkWallHeightIn,
                               user=Depends(current_user)) -> dict:
    """Applique une même hauteur de mur à TOUTES les cotes linéaires (mur/distance)
    de la page indiquée (ou de tout le plan si page_index absent). Recalcule les m²."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "measurements": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    linear_kinds = ("distance", "cumulative", "polyline", "manual_linear")
    count = 0
    for m in (p.get("measurements") or []):
        if m.get("kind") not in linear_kinds:
            continue
        if body.page_index is not None and m.get("page_index") != body.page_index:
            continue
        m["gross_m"] = round(_measure_gross_m(m), 3)
        m["wall_height_m"] = float(body.height_m) if body.height_m else 0
        sets = _recompute_linear_sets(m)
        await _persist_linear(plan_id, user["user_id"], m["measurement_id"], sets)
        count += 1
    return {"ok": True, "updated": count}


# ============ FUSION DE COTES (joindre plusieurs mesures en une) ============

class MergeMeasuresIn(BaseModel):
    measurement_ids: list[str] = Field(min_length=2)


@router.post("/{plan_id}/measurements/merge")
async def merge_measurements(plan_id: str, body: MergeMeasuresIn,
                             user=Depends(current_user)) -> dict:
    """Fusionne plusieurs cotes en UNE seule (la première sélectionnée = cible).

    - Longueurs (mur/distance) → une cote cumulative : longueurs additionnées,
      tronçons et ouvertures regroupés, net + m² recalculés (hauteur de la cible).
    - Surfaces (polygone/surface cumulée) → une surface cumulée : aires additionnées.
    Ne mélange jamais longueurs et surfaces. Les cotes sources sont supprimées."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "measurements": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    ms = p.get("measurements") or []
    by_id = {m.get("measurement_id"): m for m in ms}
    chosen = [by_id[i] for i in dict.fromkeys(body.measurement_ids) if i in by_id]
    if len(chosen) < 2:
        raise HTTPException(422, "Sélectionnez au moins 2 cotes existantes à fusionner")
    if len({m.get("page_index", 0) for m in chosen}) != 1:
        raise HTTPException(422, "Les cotes à fusionner doivent appartenir à la même page")
    kinds = {m.get("kind") for m in chosen}
    linear = {"distance", "cumulative", "polyline"}
    area = {"polygon", "cumulative_area"}
    target = chosen[0]

    if kinds <= linear:
        segs: list = []
        for m in chosen:
            if m.get("segments"):
                segs += m["segments"]
            elif m.get("points"):
                segs.append(m["points"])
        openings: list = []
        for m in chosen:
            openings += (m.get("openings") or [])
        merged = {**target, "kind": "cumulative", "segments": segs,
                  "points": segs[0] if segs else target.get("points"),
                  "gross_m": round(sum(_measure_gross_m(m) for m in chosen), 3),
                  "openings": openings, "wall_height_m": target.get("wall_height_m")}
        merged.update(_recompute_linear_sets(merged))
    elif kinds <= area:
        polys: list = []
        for m in chosen:
            if m.get("polygons"):
                polys += m["polygons"]
            elif m.get("points"):
                polys.append(m["points"])
        merged = {**target, "kind": "cumulative_area", "polygons": polys,
                  "points": polys[0] if polys else target.get("points"),
                  "area_m2": round(sum(float(m.get("area_m2") or 0) for m in chosen), 3),
                  "perimeter_m": round(sum(float(m.get("perimeter_m") or 0) for m in chosen), 3)}
    else:
        raise HTTPException(422, "Ne mélangez pas des longueurs (murs) et des surfaces dans une fusion")

    merged["updated_at"] = _now()
    remaining = [m for m in ms if m.get("measurement_id") not in set(body.measurement_ids)]
    remaining.append(merged)
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"measurements": remaining, "updated_at": _now()}})
    return {"ok": True, "measurement": merged, "merged_count": len(chosen)}


# ============ SURFACE → PIÈCE & DÉDUCTIONS (iter68) ============

async def _plan_and_polygon_measure(plan_id: str, measurement_id: str, user_id: str):
    """Charge plan + mesure polygone + calibration — 404/422/400 sinon."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "calibrations": 1, "rooms": 1, "measurements": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    m = next((x for x in (p.get("measurements") or [])
              if x.get("measurement_id") == measurement_id), None)
    if not m:
        raise HTTPException(404, "Mesure introuvable")
    if m.get("kind") != "polygon" or len(m.get("points") or []) < 3:
        raise HTTPException(422, "Seule une mesure de surface (polygone) est convertible")
    calib = (p.get("calibrations") or {}).get(str(m.get("page_index", 0)))
    if not calib:
        raise HTTPException(400, "Page non calibrée")
    return p, m, calib


@router.post("/{plan_id}/measurements/{measurement_id}/to-room")
async def measurement_to_room(plan_id: str, measurement_id: str,
                              user=Depends(current_user)) -> dict:
    """Convertit une surface mesurée en pièce complète (murs et volume calculés)."""
    p, m, calib = await _plan_and_polygon_measure(plan_id, measurement_id, user["user_id"])
    rooms = p.get("rooms") or []
    room = {
        "room_id": "room_" + secrets.token_hex(4),
        "page_index": m.get("page_index", 0),
        "name": (m.get("label") or f"Pièce {len(rooms) + 1:02d}").strip()[:60],
        "points": [list(pt) for pt in m["points"]],
        "openings": [],
        "ceiling_height_m": 2.5,
        "floor_thickness_m": 0.15,
        "created_at": _now(),
    }
    _recompute_room(room, calib["pixels_per_meter"])
    rooms.append(room)
    measurements = [x for x in p.get("measurements") or []
                    if x.get("measurement_id") != measurement_id]
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"rooms": rooms, "measurements": measurements, "updated_at": _now()}})
    await _snapshot(plan_id, user["user_id"], "measure_to_room",
                    {"room_name": room["name"]})
    return {"ok": True, "room": room}


@router.post("/{plan_id}/measurements/{measurement_id}/deduct")
async def measurement_deduct(plan_id: str, measurement_id: str,
                             user=Depends(current_user)) -> dict:
    """Soustrait une surface mesurée (trémie, escalier…) de la pièce qui la contient."""
    p, m, calib = await _plan_and_polygon_measure(plan_id, measurement_id, user["user_id"])
    pts = m["points"]
    cx = sum(pt[0] for pt in pts) / len(pts)
    cy = sum(pt[1] for pt in pts) / len(pts)
    rooms = p.get("rooms") or []
    target = next(
        (r for r in rooms
         if r.get("page_index") == m.get("page_index", 0)
         and len(r.get("points") or []) >= 3
         and G.point_in_polygon(cx, cy, r["points"])),
        None)
    if not target:
        raise HTTPException(400, "Dessinez la surface à l'intérieur d'une pièce à déduire")
    deduction = {
        "deduction_id": "ded_" + secrets.token_hex(4),
        "label": m.get("label") or "Déduction",
        "area_m2": float(m.get("area_m2") or 0),
        "points": [list(pt) for pt in pts],
    }
    target.setdefault("deductions", []).append(deduction)
    _recompute_room(target, calib["pixels_per_meter"])
    measurements = [x for x in p.get("measurements") or []
                    if x.get("measurement_id") != measurement_id]
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"rooms": rooms, "measurements": measurements, "updated_at": _now()}})
    await _snapshot(plan_id, user["user_id"], "room_deduction",
                    {"room_name": target["name"], "area_m2": deduction["area_m2"]})
    return {"ok": True, "room_id": target["room_id"], "room_name": target["name"],
            "deduction": deduction, "surface_m2": target["surface_m2"]}


@router.delete("/{plan_id}/rooms/{room_id}/deductions/{deduction_id}")
async def delete_deduction(plan_id: str, room_id: str, deduction_id: str,
                           user=Depends(current_user)) -> dict:
    """Retire une déduction d'une pièce et recalcule ses surfaces."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "rooms": 1, "calibrations": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    room = next((r for r in rooms if r.get("room_id") == room_id), None)
    if not room:
        raise HTTPException(404, "Pièce introuvable")
    before = len(room.get("deductions") or [])
    room["deductions"] = [d for d in room.get("deductions") or []
                          if d.get("deduction_id") != deduction_id]
    if len(room["deductions"]) == before:
        raise HTTPException(404, "Déduction introuvable")
    calib = (p.get("calibrations") or {}).get(str(room.get("page_index", 0)))
    _recompute_room(room, (calib or {}).get("pixels_per_meter") or 0)
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"rooms": rooms, "updated_at": _now()}})
    return {"ok": True, "surface_m2": room["surface_m2"]}


# ============ PIÈCES ============

class RoomIn(BaseModel):
    page_index: int
    name: str = Field(min_length=1, max_length=80)
    points: list[tuple[float, float]] = Field(min_length=3)
    ceiling_height_m: float | None = Field(default=2.5, ge=1.5, le=6.0)
    floor_thickness_m: float | None = Field(default=0.15, ge=0.02, le=1.0)
    openings: list[dict] = Field(default_factory=list)
    room_id: str | None = None


class OpeningIn(BaseModel):
    kind: str = Field(default="fenetre", max_length=20)
    width_m: float = Field(ge=0.05, le=10.0)
    height_m: float = Field(ge=0.05, le=6.0)
    count: int = Field(default=1, ge=1, le=100)
    label: str | None = Field(default=None, max_length=40)


@router.post("/{plan_id}/rooms/{room_id}/openings")
async def add_opening(plan_id: str, room_id: str, body: OpeningIn, user=Depends(current_user)):
    """Ajoute une ouverture (porte/fenêtre/baie) à une pièce."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "rooms": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    room = next((r for r in rooms if r["room_id"] == room_id), None)
    if not room:
        raise HTTPException(404, "Pièce introuvable")
    opening = {"opening_id": "op_" + secrets.token_hex(4),
               "kind": body.kind.lower().strip() or "fenetre",
               "width_m": body.width_m, "height_m": body.height_m,
               "count": body.count,
               "label": (body.label or "").strip() or None,
               "area_m2": round(body.width_m * body.height_m * body.count, 3),
               "created_at": _now()}
    new_openings = list(room.get("openings") or []) + [opening]
    net = G.subtract_openings(room["wall_area_gross_m2"], new_openings)
    room["openings"] = net["openings"]
    room["openings_area_m2"] = net["openings_area_m2"]
    room["wall_area_net_m2"] = net["wall_area_net_m2"]
    rooms = [r if r["room_id"] != room_id else room for r in rooms]
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id}, {"$set": {"rooms": rooms, "updated_at": _now()}}
    )
    await _snapshot(plan_id, user["user_id"], "opening_add",
                    {"room_name": room["name"], "kind": opening["kind"],
                     "area_m2": opening["area_m2"]})
    return room


@router.delete("/{plan_id}/rooms/{room_id}/openings/{opening_id}")
async def delete_opening(plan_id: str, room_id: str, opening_id: str,
                          user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "rooms": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    room = next((r for r in rooms if r["room_id"] == room_id), None)
    if not room:
        raise HTTPException(404, "Pièce introuvable")
    new_openings = [o for o in (room.get("openings") or []) if o.get("opening_id") != opening_id]
    net = G.subtract_openings(room["wall_area_gross_m2"], new_openings)
    room["openings"] = net["openings"]
    room["openings_area_m2"] = net["openings_area_m2"]
    room["wall_area_net_m2"] = net["wall_area_net_m2"]
    rooms = [r if r["room_id"] != room_id else room for r in rooms]
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id}, {"$set": {"rooms": rooms, "updated_at": _now()}}
    )
    return {"ok": True, "room": room}


@router.post("/{plan_id}/rooms")
async def upsert_room(plan_id: str, body: RoomIn, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "calibrations": 1, "rooms": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    if not calib:
        raise HTTPException(400, "Page non calibrée")

    m = G.room_measurements(body.points, calib["pixels_per_meter"],
                             body.ceiling_height_m or 2.5)
    net = G.subtract_openings(m["wall_area_gross_m2"], body.openings)
    floor_th = body.floor_thickness_m if body.floor_thickness_m is not None else 0.15
    volume_m3 = round(m["surface_m2"] * (body.ceiling_height_m or 2.5), 3)

    room = {
        "room_id": body.room_id or ("room_" + secrets.token_hex(4)),
        "page_index": body.page_index,
        "name": body.name.strip(),
        "points": [list(pt) for pt in body.points],
        "openings": net["openings"],
        "surface_m2": m["surface_m2"],
        "perimeter_m": m["perimeter_m"],
        "ceiling_area_m2": m["ceiling_area_m2"],
        "ceiling_height_m": m["ceiling_height_m"],
        "floor_thickness_m": round(floor_th, 3),
        "volume_m3": volume_m3,
        "wall_area_gross_m2": m["wall_area_gross_m2"],
        "wall_area_net_m2": net["wall_area_net_m2"],
        "openings_area_m2": net["openings_area_m2"],
        "created_at": _now(),
    }

    existing = [r for r in (p.get("rooms") or []) if r["room_id"] != room["room_id"]]
    existing.append(room)
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"rooms": existing, "updated_at": _now()}}
    )
    await _snapshot(plan_id, user["user_id"], "room_upsert", {"room_name": room["name"]})
    return room


@router.delete("/{plan_id}/rooms/{room_id}")
async def delete_room(plan_id: str, room_id: str, user=Depends(current_user)) -> dict:
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$pull": {"rooms": {"room_id": room_id}}, "$set": {"updated_at": _now()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Plan introuvable")
    await _snapshot(plan_id, user["user_id"], "room_delete", {"room_id": room_id})
    return {"ok": True}


class RoomUpdateIn(BaseModel):
    name: str | None = None
    height_m: float | None = None
    preset_id: str | None = None  # référence à un modèle appliqué (Vague B)


@router.patch("/{plan_id}/rooms/{room_id}")
async def update_room(plan_id: str, room_id: str, body: RoomUpdateIn,
                      user=Depends(current_user)) -> dict:
    """Édition inline d'une pièce depuis le Volet Objets (Vague B).

    Fix revue iter63 : la hauteur est stockée dans `ceiling_height_m` (champ
    utilisé partout) et les surfaces murs/volume sont recalculées.
    """
    # Validation d'abord (contrat iter58 : 422 avant 404)
    if body.name is None and body.height_m is None and body.preset_id is None:
        raise HTTPException(422, "Aucun champ à mettre à jour")
    if body.name is not None and not body.name.strip():
        raise HTTPException(422, "Nom invalide")
    if body.height_m is not None and (body.height_m <= 0 or body.height_m > 20):
        raise HTTPException(422, "Hauteur invalide")
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "rooms": 1, "calibrations": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    room = next((r for r in rooms if r.get("room_id") == room_id), None)
    if not room:
        raise HTTPException(404, "Pièce introuvable")
    updated = []
    if body.name is not None:
        room["name"] = body.name.strip()[:60]
        updated.append("name")
    if body.height_m is not None:
        room["ceiling_height_m"] = float(body.height_m)
        calib = (p.get("calibrations") or {}).get(str(room.get("page_index", 0)))
        _recompute_room(room, (calib or {}).get("pixels_per_meter") or 0)
        updated.append("ceiling_height_m")
    if body.preset_id is not None:
        room["preset_id"] = body.preset_id or None
        updated.append("preset_id")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"rooms": rooms, "updated_at": _now()}})
    return {"ok": True, "updated": updated, "room": room}


# ============ VAGUE C — Estimation par métier depuis une pièce ============

class RoomEstimateIn(BaseModel):
    trades: list[str] | None = None  # None = tous les métiers pertinents
    override_height_m: float | None = None
    doors: int = 1
    windows: int = 1
    masonry_material: str = "parpaing"   # "parpaing" | "brique"
    masonry_bond: str | None = None      # parpaing: "mortier" | brique: "colle" | "mousse"
    masonry_block: str | None = None     # clé de préréglage bloc (config admin)
    masonry_render: bool = False         # inclure l'enduit de façade


def _room_dimensions_for_estimator(room: dict, override_height: float | None) -> tuple[float, float, float]:
    """Derive length, width, height depuis les données d'une pièce.

    Si la pièce a un polygone fermé, on estime L/l via la bounding box du polygone
    dans l'espace pixel → conversion en mètres via `pixels_per_meter` (fourni par le plan).
    Si `surface_m2` est disponible mais pas de polygone, on approxime en carré (√S × √S).
    """
    height = override_height or float(
        room.get("ceiling_height_m") or room.get("height_m") or 2.5)
    surf = float(room.get("surface_m2") or 0)
    # Si pas de surface, impossible d'estimer
    if surf <= 0:
        return (4.0, 4.0, height)  # défaut raisonnable pièce moyenne
    perimeter = float(room.get("perimeter_m") or 0)
    if perimeter > 0:
        # Résolution système L+W = P/2, L×W = S : équation quadratique
        half = perimeter / 2
        disc = max(0.0, half * half - 4 * surf)
        length = (half + disc ** 0.5) / 2
        width = surf / length if length > 0 else half / 2
        return (round(length, 2), round(width, 2), height)
    # Fallback : carré
    side = surf ** 0.5
    return (round(side, 2), round(side, 2), height)


@router.post("/{plan_id}/rooms/{room_id}/estimate")
async def estimate_room(plan_id: str, room_id: str, body: RoomEstimateIn,
                        user=Depends(current_user)):
    """Génère les quantités par métier pour une pièce depuis calculators.py.

    Utile pour la Vague C QuoterPlan : un clic sur une pièce → devis multi-métiers.
    Résultat : dict par métier avec {results, materials, estimated_budget}.
    """
    from engines import calculators as C

    plan = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "rooms": 1}
    )
    if not plan:
        raise HTTPException(404, "Plan introuvable")
    room = next((r for r in plan.get("rooms", []) if r.get("room_id") == room_id), None)
    if not room:
        raise HTTPException(404, "Pièce introuvable")

    length, width, height = _room_dimensions_for_estimator(room, body.override_height_m)
    surface = float(room.get("surface_m2") or (length * width))
    perimeter = float(room.get("perimeter_m") or 2 * (length + width))

    # Métiers disponibles + fonction déclenchante
    trades = body.trades or ["paint", "floor_tile", "drywall", "insulation", "plinths"]
    out: dict = {"room": {"room_id": room_id, "name": room.get("name"),
                          "length_m": length, "width_m": width, "height_m": height,
                          "surface_m2": surface, "perimeter_m": perimeter},
                 "trades": {}, "total_budget": 0.0}

    if "paint" in trades:
        r = C.paint(length=length, width=width, height=height,
                    doors=body.doors, windows=body.windows, coats=2)
        out["trades"]["paint"] = r
        out["total_budget"] += r.get("estimated_budget") or 0

    if "floor_tile" in trades:
        r = C.tile(area=surface, pose="droite")
        out["trades"]["floor_tile"] = r
        out["total_budget"] += r.get("estimated_budget") or 0

    if "drywall" in trades:
        # Cloisons intérieures : surface = perimeter × height, hors ouvertures
        wall_area = max(0.0, perimeter * height - body.doors * 2.0 - body.windows * 1.5)
        r = C.drywall(area=wall_area)
        out["trades"]["drywall"] = r
        out["total_budget"] += r.get("estimated_budget") or 0

    if "insulation" in trades:
        r = C.insulation(area=surface, material="laine_de_verre", thickness_mm=100)
        out["trades"]["insulation"] = r
        out["total_budget"] += r.get("estimated_budget") or 0

    if "masonry" in trades:
        # Murs porteurs/cloisons maçonnées : surface = périmètre × hauteur, hors ouvertures
        wall_area = max(0.0, perimeter * height - body.doors * 2.0 - body.windows * 1.5)
        from routes.estimation_routes import get_masonry_config, masonry_kwargs_from_config
        mk = masonry_kwargs_from_config(
            await get_masonry_config(), area=wall_area, material=body.masonry_material,
            bond=body.masonry_bond, block_key=body.masonry_block,
            include_render=body.masonry_render)
        r = C.masonry(**mk)
        out["trades"]["masonry"] = r
        out["total_budget"] += r.get("estimated_budget") or 0

    if "plinths" in trades:
        # Plinthes = périmètre - largeur des ouvertures (portes uniquement, fenêtres au-dessus)
        plinth_length = max(0.0, perimeter - body.doors * 0.9)
        loss = 1.10  # 10% de chutes
        with_margin = plinth_length * loss
        out["trades"]["plinths"] = {
            "inputs": {"perimeter_m": perimeter, "doors": body.doors},
            "results": [
                {"label": "Périmètre net", "value": round(plinth_length, 2), "unit": "m"},
                {"label": "Plinthes (+10% chutes)", "value": round(with_margin, 2), "unit": "ml"},
            ],
            "materials": [
                {"name": "Plinthe MDF blanche 2.4m", "quantity": max(1, int(with_margin / 2.4) + 1),
                 "unit": "u", "search": "plinthe mdf blanche 2.4m"},
                {"name": "Colle plinthe cartouche", "quantity": max(1, int(with_margin / 8) + 1),
                 "unit": "u", "search": "colle plinthes cartouche"},
            ],
            "estimated_budget": round(with_margin * 3.5 + max(1, int(with_margin / 8) + 1) * 6.5, 2),
        }
        out["total_budget"] += out["trades"]["plinths"]["estimated_budget"]

    out["total_budget"] = round(out["total_budget"], 2)
    return out



# ============ COMPARE / WALLS DIFF ============

class CompareIn(BaseModel):
    before_plan_id: str
    after_plan_id: str
    surface_tolerance_pct: float = Field(default=5.0, ge=0, le=100)


def _walls_of(cv_walls: dict | None) -> list[dict]:
    """Aplati cv_walls (par page) en une liste de segments."""
    if not cv_walls:
        return []
    segs: list[dict] = []
    for page_key, entry in (cv_walls or {}).items():
        for s in (entry or {}).get("segments") or []:
            try:
                segs.append({
                    "page": int(page_key),
                    "x1": float(s["x1"]), "y1": float(s["y1"]),
                    "x2": float(s["x2"]), "y2": float(s["y2"]),
                })
            except (KeyError, TypeError, ValueError):
                continue
    return segs


def _seg_dir(s: dict) -> tuple[str, int, tuple[int, int]]:
    """Renvoie ('h' ou 'v' ou 'o', mid, (a, b)) pour un segment."""
    dx = s["x2"] - s["x1"]
    dy = s["y2"] - s["y1"]
    if abs(dy) <= max(3, abs(dx) * 0.1):
        y_mid = int(round((s["y1"] + s["y2"]) / 2))
        x_min = int(round(min(s["x1"], s["x2"])))
        x_max = int(round(max(s["x1"], s["x2"])))
        return ("h", y_mid, (x_min, x_max))
    if abs(dx) <= max(3, abs(dy) * 0.1):
        x_mid = int(round((s["x1"] + s["x2"]) / 2))
        y_min = int(round(min(s["y1"], s["y2"])))
        y_max = int(round(max(s["y1"], s["y2"])))
        return ("v", x_mid, (y_min, y_max))
    return ("o", 0, (0, 0))


def _match_seg(target: dict, others: list[dict], tol: int = 10) -> int:
    """Cherche un segment similaire dans `others`. Retourne l'index, ou -1."""
    t_orient, t_mid, t_range = _seg_dir(target)
    for i, s in enumerate(others):
        o_orient, o_mid, o_range = _seg_dir(s)
        if o_orient != t_orient or abs(o_mid - t_mid) > tol:
            continue
        overlap = max(0, min(t_range[1], o_range[1]) - max(t_range[0], o_range[0]))
        length = max(1, t_range[1] - t_range[0])
        if overlap / length >= 0.6:
            return i
    return -1


def _diff_walls(before: dict, after: dict) -> dict:
    walls_b = _walls_of(before.get("cv_walls"))
    walls_a = _walls_of(after.get("cv_walls"))
    walls_removed: list[dict] = []
    walls_unchanged: list[dict] = []
    remaining_a = list(walls_a)
    for wb in walls_b:
        idx = _match_seg(wb, remaining_a)
        if idx >= 0:
            walls_unchanged.append(wb)
            remaining_a.pop(idx)
        else:
            walls_removed.append(wb)
    return {
        "before_count": len(walls_b), "after_count": len(walls_a),
        "added": remaining_a, "removed": walls_removed,
        "unchanged": walls_unchanged,
    }


@router.post("/compare")
async def compare_plans(body: CompareIn, user=Depends(current_user)) -> dict:
    """Compare 2 plans (avant/après) et renvoie les pièces + murs différents."""
    before = await db.plans_takeoff.find_one(
        {"plan_id": body.before_plan_id, "user_id": user["user_id"]},
        {"_id": 0, "rooms": 1, "filename": 1, "cv_walls": 1}
    )
    after = await db.plans_takeoff.find_one(
        {"plan_id": body.after_plan_id, "user_id": user["user_id"]},
        {"_id": 0, "rooms": 1, "filename": 1, "cv_walls": 1}
    )
    if not before or not after:
        raise HTTPException(404, "Un des deux plans est introuvable")
    if body.before_plan_id == body.after_plan_id:
        raise HTTPException(400, "Sélectionnez deux plans différents")

    rooms_b = before.get("rooms") or []
    rooms_a = after.get("rooms") or []
    diff = _diff_rooms(rooms_b, rooms_a, body.surface_tolerance_pct)
    walls_diff = _diff_walls(before, after)

    return {
        "before": {"plan_id": body.before_plan_id, "filename": before.get("filename"),
                   "room_count": len(rooms_b), "total_surface_m2": diff["total_before_m2"]},
        "after": {"plan_id": body.after_plan_id, "filename": after.get("filename"),
                  "room_count": len(rooms_a), "total_surface_m2": diff["total_after_m2"]},
        "delta_surface_m2": diff["delta_surface_m2"],
        "delta_surface_pct": diff["delta_surface_pct"],
        "added": diff["added"], "removed": diff["removed"],
        "modified": diff["modified"], "unchanged": diff["unchanged"],
        "surface_tolerance_pct": diff["surface_tolerance_pct"],
        "walls": walls_diff,
    }


class SnapshotCompareIn(BaseModel):
    before_snapshot_id: str
    after_snapshot_id: str
    surface_tolerance_pct: float = Field(default=5.0, ge=0, le=100)


@router.post("/{plan_id}/history/compare")
async def compare_snapshots(plan_id: str, body: SnapshotCompareIn,
                             user=Depends(current_user)) -> dict:
    """Compare 2 snapshots d'historique du MÊME plan (avant/après édition)."""
    if body.before_snapshot_id == body.after_snapshot_id:
        raise HTTPException(400, "Sélectionnez deux snapshots différents.")
    sb = await db.plans_takeoff_history.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"],
         "snapshot_id": body.before_snapshot_id}, {"_id": 0}
    )
    sa = await db.plans_takeoff_history.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"],
         "snapshot_id": body.after_snapshot_id}, {"_id": 0}
    )
    if not sb or not sa:
        raise HTTPException(404, "Un des deux snapshots est introuvable.")

    diff = _diff_rooms(sb.get("rooms") or [], sa.get("rooms") or [], body.surface_tolerance_pct)
    return {
        "before": {"snapshot_id": sb["snapshot_id"],
                    "label": sb.get("label"), "action": sb.get("action"),
                    "created_at": sb.get("created_at"),
                    "room_count": len(sb.get("rooms") or []),
                    "total_surface_m2": diff["total_before_m2"]},
        "after": {"snapshot_id": sa["snapshot_id"],
                   "label": sa.get("label"), "action": sa.get("action"),
                   "created_at": sa.get("created_at"),
                   "room_count": len(sa.get("rooms") or []),
                   "total_surface_m2": diff["total_after_m2"]},
        "delta_surface_m2": diff["delta_surface_m2"],
        "delta_surface_pct": diff["delta_surface_pct"],
        "added": diff["added"], "removed": diff["removed"],
        "modified": diff["modified"], "unchanged": diff["unchanged"],
        "surface_tolerance_pct": diff["surface_tolerance_pct"],
    }


# ============ TAKEOFF AGRÉGÉ ============

def _aggregate_levels(rooms: list[dict], pages: list[dict]) -> list[dict]:
    """Group rooms by page-level index; return sorted list with per-level totals."""
    page_level = {pg["index"]: {"index": pg.get("level_index"),
                                 "label": pg.get("level_label")}
                  for pg in pages}
    by_level: dict = {}
    for r in rooms:
        info = page_level.get(r.get("page_index"), {"index": None, "label": None})
        key = f"{info['index'] if info['index'] is not None else 'none'}"
        bucket = by_level.setdefault(key, {
            "level_index": info["index"],
            "level_label": info["label"] or "Sans niveau",
            "rooms": [], "totals": {"floor_m2": 0, "ceiling_m2": 0,
                                     "walls_gross_m2": 0, "walls_net_m2": 0,
                                     "perimeter_m": 0}})
        bucket["rooms"].append(r)
        bucket["totals"]["floor_m2"] += r.get("surface_m2", 0)
        bucket["totals"]["ceiling_m2"] += r.get("ceiling_area_m2", 0)
        bucket["totals"]["walls_gross_m2"] += r.get("wall_area_gross_m2", 0)
        bucket["totals"]["walls_net_m2"] += r.get("wall_area_net_m2", 0)
        bucket["totals"]["perimeter_m"] += r.get("perimeter_m", 0)
    for b in by_level.values():
        for k in b["totals"]:
            b["totals"][k] = round(b["totals"][k], 2)
    return sorted(by_level.values(),
                  key=lambda x: (x["level_index"] is None,
                                 x["level_index"] if x["level_index"] is not None else 99))


def _sum_totals(rooms: list[dict]) -> dict:
    return {
        "floor_m2": round(sum(r.get("surface_m2", 0) for r in rooms), 2),
        "ceiling_m2": round(sum(r.get("ceiling_area_m2", 0) for r in rooms), 2),
        "walls_gross_m2": round(sum(r.get("wall_area_gross_m2", 0) for r in rooms), 2),
        "walls_net_m2": round(sum(r.get("wall_area_net_m2", 0) for r in rooms), 2),
        "perimeter_m": round(sum(r.get("perimeter_m", 0) for r in rooms), 2),
    }


@router.get("/{plan_id}/takeoff")
async def takeoff(plan_id: str, user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "rooms": 1, "filename": 1, "pages": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    pages = p.get("pages") or []
    return {
        "plan_id": plan_id, "filename": p.get("filename"),
        "room_count": len(rooms),
        "totals": _sum_totals(rooms),
        "levels": _aggregate_levels(rooms, pages),
        "rooms": rooms,
    }


# ============ CALC MATÉRIAUX ============

class MaterialsIn(BaseModel):
    room_ids: list[str] | None = None
    include: dict = Field(default_factory=lambda: {
        "paint": True, "placo": True, "floor": True, "skirting": True,
    })
    floor_material: str = "parquet"


@router.post("/{plan_id}/materials")
async def compute_materials(plan_id: str, body: MaterialsIn, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "rooms": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = [r for r in (p.get("rooms") or [])
             if not body.room_ids or r["room_id"] in body.room_ids]
    if not rooms:
        raise HTTPException(400, "Aucune pièce sélectionnée")

    floor = sum(r.get("surface_m2", 0) for r in rooms)
    ceiling = sum(r.get("ceiling_area_m2", 0) for r in rooms)
    walls_net = sum(r.get("wall_area_net_m2", 0) for r in rooms)
    perim = sum(r.get("perimeter_m", 0) for r in rooms)

    result = {"rooms_used": [r["room_id"] for r in rooms],
              "totals": {"floor_m2": floor, "ceiling_m2": ceiling,
                         "walls_net_m2": walls_net, "perimeter_m": perim}}
    if body.include.get("floor", True):
        result["floor"] = G.floor_quantity(floor, body.floor_material)
    if body.include.get("paint", True):
        result["paint"] = G.paint_liters(walls_net + ceiling)
    if body.include.get("placo", True):
        result["placo"] = G.placo_quantity(walls_net + ceiling)
    if body.include.get("skirting", True):
        doors_m = sum(float(o.get("width_m") or 0) * int(o.get("count", 1))
                      for r in rooms for o in r.get("openings", [])
                      if (o.get("kind") or o.get("type") or "").lower().startswith(("port", "door")))
        result["skirting"] = G.skirting_length_m(perim, doors_m)
    return result


# ============ HISTORIQUE (auto-snapshots) ============

@router.get("/{plan_id}/history")
async def list_history(plan_id: str, user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "plan_id": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    snaps = await db.plans_takeoff_history.find(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "user_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"plan_id": plan_id, "history": snaps, "count": len(snaps)}


@router.post("/{plan_id}/history/restore/{snapshot_id}")
async def restore_snapshot(plan_id: str, snapshot_id: str, user=Depends(current_user)) -> dict:
    snap = await db.plans_takeoff_history.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"], "snapshot_id": snapshot_id},
        {"_id": 0}
    )
    if not snap:
        raise HTTPException(404, "Snapshot introuvable")
    await _snapshot(plan_id, user["user_id"], "before_restore",
                    {"restored_from": snapshot_id})
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "pages": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    updates = {"rooms": snap.get("rooms") or [],
               "calibrations": snap.get("calibrations") or {},
               "updated_at": _now()}
    for pl in snap.get("page_levels") or []:
        idx = pl.get("index")
        if idx is not None:
            updates[f"pages.{idx}.level_index"] = pl.get("level_index")
            updates[f"pages.{idx}.level_label"] = pl.get("level_label")
    await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": updates})
    return {"ok": True, "restored_from": snapshot_id,
            "rooms": len(snap.get("rooms") or []),
            "action": snap.get("action")}


class SnapshotLabelIn(BaseModel):
    label: str = Field(default="", max_length=80)


@router.put("/{plan_id}/history/{snapshot_id}/label")
async def label_snapshot(plan_id: str, snapshot_id: str, body: SnapshotLabelIn,
                        user=Depends(current_user)) -> dict:
    """Renomme un snapshot d'historique (ex. « Version client 12/02 »)."""
    label = body.label.strip()[:80] or None
    res = await db.plans_takeoff_history.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"], "snapshot_id": snapshot_id},
        {"$set": {"label": label}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Snapshot introuvable")
    return {"ok": True, "snapshot_id": snapshot_id, "label": label}

