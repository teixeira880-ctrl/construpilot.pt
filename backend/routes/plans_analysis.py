"""AI/CV analysis + rooms + measurements + takeoff + materials + history + compare.

Refactor iter53 : extrait de `routes/plans.py`.
"""
from __future__ import annotations

import logging
import re
import secrets
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import geometry as G
from engines import plan_texts as T
from engines.plan_ai import analyze_plan_image
from engines.plan_cv import detect_all_rooms, detect_walls, flood_fill_room
from engines.plan_structure import detect_structure, detect_structure_tiled, refine_structure
from engines.plan_processor import auto_calibration_from_pdf_scale

from routes.plans_common import (
    _diff_rooms, _now, _snapshot, _resolve_branding, router,
)

logger = logging.getLogger(__name__)


# ============ RÉGLAGES BÉTON PAR DÉFAUT (entreprise) ============

_BETON_DEFAULTS = {"wall_height": 2.5, "dalle_ep": 0.20, "voile_ep": 0.20,
                   "poutre_l": 0.20, "poutre_h": 0.40, "acier_price_kg": 0.0,
                   "beton_price_m3": 0.0, "labor_price_m3": 0.0, "margin_pct": 0.0,
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
    acier_ratios: dict = Field(default_factory=dict)


@router.put("/settings/beton-defaults")
async def set_beton_defaults(body: BetonDefaultsIn, user=Depends(current_user)) -> dict:
    ar = {k: float(body.acier_ratios.get(k, ACIER_RATIOS[k])) for k in ACIER_RATIOS}
    payload = {"wall_height": body.wall_height, "dalle_ep": body.dalle_ep,
               "voile_ep": body.voile_ep, "poutre_l": body.poutre_l,
               "poutre_h": body.poutre_h, "acier_price_kg": max(0.0, body.acier_price_kg),
               "beton_price_m3": max(0.0, body.beton_price_m3),
               "labor_price_m3": max(0.0, body.labor_price_m3),
               "margin_pct": max(0.0, body.margin_pct), "acier_ratios": ar}
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
    analysis = await analyze_plan_image(img)
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


def _recompute_room(room: dict, ppm: float) -> dict:
    """Recalcule surface / périmètre / murs / volume d'une pièce avec un nouveau ppm.

    Iter68 : les déductions (trémie, escalier…) sont soustraites de la surface,
    du plafond et du volume — le périmètre et les murs restent inchangés.
    """
    pts = room.get("points") or []
    if len(pts) < 3 or not ppm or ppm <= 0:
        return room
    height = float(room.get("ceiling_height_m") or 2.5)
    m = G.room_measurements(pts, ppm, height)
    net = G.subtract_openings(m["wall_area_gross_m2"], room.get("openings") or [])
    ded = round(sum(float(d.get("area_m2") or 0)
                    for d in (room.get("deductions") or [])), 3)
    surface = max(0.0, round(m["surface_m2"] - ded, 3))
    room.update({
        "surface_m2": surface,
        "surface_gross_m2": m["surface_m2"],
        "deductions_area_m2": ded,
        "perimeter_m": m["perimeter_m"],
        "ceiling_area_m2": surface,
        "wall_area_gross_m2": m["wall_area_gross_m2"],
        "wall_area_net_m2": net["wall_area_net_m2"],
        "openings_area_m2": net["openings_area_m2"],
        "volume_m3": round(surface * height, 3),
    })
    written = room.get("surface_written_m2")
    if written and surface > 0:
        room["surface_delta_pct"] = round((float(written) / surface - 1) * 100, 1)
    return room


async def _apply_new_calibration(plan: dict, plan_id: str,
                                 page_index: int, payload: dict) -> int:
    """Sauve la calibration + recalcule toutes les pièces de la page. Retourne n pièces."""
    ppm = payload["pixels_per_meter"]
    rooms = plan.get("rooms") or []
    updated = 0
    for r in rooms:
        if r.get("page_index") == page_index and len(r.get("points") or []) >= 3:
            _recompute_room(r, ppm)
            updated += 1
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"calibrations.{page_index}": payload,
                  "rooms": rooms, "updated_at": _now()}},
    )
    return updated


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
    rooms_updated = await _apply_new_calibration(p, plan_id, body.page_index, payload)
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
    rooms_updated = await _apply_new_calibration(p, plan_id, body.page_index, payload)
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
        m = re.search(r"1\s*[:/]\s*(\d{2,4})", str(ai["detected_scale"]))
        pages = p.get("pages") or []
        if m and body.page_index < len(pages):
            dpi = pages[body.page_index].get("dpi") or 150
            ppm_scale = auto_calibration_from_pdf_scale(int(m.group(1)), dpi)
            if ppm_scale:
                updates[f"calibrations.{body.page_index}"] = {
                    "pixels_per_meter": ppm_scale,
                    "method": "ai_scale_text",
                    "scale_denominator": int(m.group(1)),
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
        result = detect_walls(img, dim_zones=dim_zones, text_zones=text_zones)
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
                                 user=Depends(current_user)):
    """Détection IA de la structure : murs (rouge) + ouvertures portes/fenêtres.

    Produit un rendu sémantique propre, contrairement à /detect-walls (OpenCV brut).
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
    result = await detect_structure_tiled(img, w, h)
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


def _compute_descriptif(structure: dict, ppm: float | None, rooms: list,
                        wall_height: float = 2.5, dalle_ep: float = 0.20,
                        voile_ep: float = 0.20, poutre_l: float = 0.20,
                        poutre_h: float = 0.40, acier_ratios: dict | None = None,
                        floors_only: bool = False) -> dict:
    from collections import Counter
    walls = structure.get("walls") or []
    openings = structure.get("openings") or []
    beams = structure.get("beams") or []
    footings = structure.get("footings") or []
    murs_ml = round(sum(_seg_len_px(w) for w in walls) / ppm, 2) if ppm else 0.0
    poutres_ml = round(sum(_seg_len_px(b) for b in beams) / ppm, 2) if ppm else 0.0
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
        for b in beams:
            spanm = round(_seg_len_px(b) / ppm, 2)
            vol = round(spanm * poutre_l * poutre_h, 3)
            beton_poutres += vol
            beams_table.append({"ref": b.get("ref", ""), "portee_m": spanm, "volume_m3": vol})
        beton_poutres = round(beton_poutres, 2)
        # Dalles : épaisseur par dalle si annotée (thickness_cm), sinon dalle_ep global
        beton_dalles = 0.0
        for f in floors:
            area = _polygon_area_px(f.get("points") or []) / (ppm * ppm)
            ep = (f.get("thickness_cm") / 100.0) if f.get("thickness_cm") else dalle_ep
            beton_dalles += area * ep
        beton_dalles = round(beton_dalles if floors else planchers * dalle_ep, 2)
        beton_voiles = round(porteur_ml * wall_height * voile_ep, 2)
        semelles = len(footings)
        beton_semelles = round(sum(
            (abs(ft.get("x2", 0) - ft.get("x1", 0)) / ppm) * (abs(ft.get("y2", 0) - ft.get("y1", 0)) / ppm) * 0.40
            for ft in footings if isinstance(ft, dict)), 2)
    else:
        beton_poteaux = beton_poutres = beton_dalles = beton_voiles = beton_semelles = 0.0
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
    ngf_list = sorted({f.get("ngf") for f in floors if f.get("ngf") is not None})
    return {
        "wall_height_m": round(float(wall_height), 2),
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
        "poutres_ml": poutres_ml,
        "poteaux": len(columns),
        "semelles": semelles,
        "poteaux_table": poteaux_table,
        "beams_table": beams_table,
        "beton_poteaux_m3": beton_poteaux, "beton_poutres_m3": beton_poutres,
        "beton_dalles_m3": beton_dalles, "beton_voiles_m3": beton_voiles,
        "beton_semelles_m3": beton_semelles,
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
    if u in ("u", "unité", "unite", "pièce", "piece", "pc", "ens", "ensemble"):
        return "count"
    if u in ("forfait", "ft", "global"):
        return "forfait"
    return u or "?"


async def _apply_library_prices(user_id: str, lines: list[dict]) -> tuple[list[dict], int]:
    """Pré-remplit unit_price_ht/vat depuis la bibliothèque (match mots-clés + MÊME
    famille d'unité pour éviter les prix aberrants). Retourne (lignes, nb_chiffrées)."""
    items = await db.library_items.find(
        {"user_id": user_id}, {"_id": 0, "designation": 1, "unit": 1,
                               "unit_price_ht": 1, "vat_rate": 1}).to_list(5000)
    if not items:
        return lines, 0
    idx = [(_norm_tokens(it.get("designation", "")), it) for it in items]
    matched = 0
    for ln in lines:
        toks = _norm_tokens(ln.get("designation", ""))
        fam = _unit_family(ln.get("unit"))
        best, best_overlap = None, 0
        for it_toks, it in idx:
            if _unit_family(it.get("unit")) != fam:
                continue  # ne pas mélanger m²/ml/u/forfait
            overlap = len(toks & it_toks)
            if overlap > best_overlap:
                best, best_overlap = it, overlap
        if best and best_overlap >= 1 and best.get("unit_price_ht"):
            ln["unit_price_ht"] = best["unit_price_ht"]
            ln["vat_rate"] = best.get("vat_rate", ln.get("vat_rate", 10))
            ln["price_source"] = "bibliotheque"
            matched += 1
    return lines, matched


def _beton_line_items(d: dict) -> list[dict]:
    """Lignes GROS ŒUVRE / BÉTON uniquement : murs (voiles), poteaux, poutres,
    planchers (dalles), semelles + aciers. Sans pièces ni second œuvre.
    La surface se réfère aux planchers détectés uniquement."""
    lines = []

    def add(desig, qty, unit, cat="Gros œuvre — béton"):
        if qty and qty > 0:
            lines.append({"designation": desig, "unit": unit, "qty": round(qty, 2),
                          "unit_price_ht": 0, "vat_rate": 20, "category": cat})
    add(f"Béton — semelles / fondations ({d.get('semelles', 0)} u)", d.get("beton_semelles_m3"), "m³")
    add(f"Béton — poteaux ({d.get('poteaux', 0)} u)", d.get("beton_poteaux_m3"), "m³")
    add(f"Béton — poutres / linteaux ({d.get('poutres_ml', 0)} ml)", d.get("beton_poutres_m3"), "m³")
    add(f"Béton — dalles / planchers ({d.get('planchers_m2', 0)} m²)", d.get("beton_dalles_m3"), "m³")
    add(f"Béton — voiles / murs porteurs ({d.get('murs_porteurs_ml', 0)} ml)", d.get("beton_voiles_m3"), "m³")
    _ar = d.get("acier_ratios") or {}
    _ratio_moy = (round(sum(_ar.values()) / len(_ar)) if _ar else 100)
    add(f"Aciers HA (ferraillage — env. {_ratio_moy} kg/m³)", d.get("acier_total_kg"), "kg")
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
    add("Poutres / linteaux", d.get("poutres_ml"), "ml")
    add("Poteaux béton", d.get("poteaux"), "u")
    add("Semelles / fondations", d.get("semelles"), "u")
    add("Béton coulé (poteaux + poutres + dalles + voiles + semelles)", d.get("beton_total_m3"), "m³")
    _ar = d.get("acier_ratios") or {}
    _ratio_moy = (round(sum(_ar.values()) / len(_ar)) if _ar else 100)
    add(f"Aciers HA (fer à béton armé — env. {_ratio_moy} kg/m³)", d.get("acier_total_kg"), "kg")
    return lines


@router.get("/{plan_id}/analysis/{page_index}")
async def get_analysis(plan_id: str, page_index: int, wall_height: float = 2.5,
                       dalle_ep: float = 0.20, voile_ep: float = 0.20,
                       poutre_l: float = 0.20, poutre_h: float = 0.40,
                       acier_semelles: float | None = None, acier_poteaux: float | None = None,
                       acier_poutres: float | None = None, acier_dalles: float | None = None,
                       acier_voiles: float | None = None,
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
                                     poutre_l, poutre_h, acier_ratios=ar)
    return {"structure": structure, "descriptif": descriptif,
            "calibrated": bool(ppm), "pixels_per_meter": ppm}


@router.get("/{plan_id}/structure/{page_index}/beton-xlsx")
async def export_beton_xlsx(plan_id: str, page_index: int, wall_height: float = 2.5,
                            dalle_ep: float = 0.20, voile_ep: float = 0.20,
                            poutre_l: float = 0.20, poutre_h: float = 0.40,
                            acier_semelles: float | None = None, acier_poteaux: float | None = None,
                            acier_poutres: float | None = None, acier_dalles: float | None = None,
                            acier_voiles: float | None = None,
                            user=Depends(current_user)):
    """Export Excel du métré béton (poteaux, poutres, dalles, voiles, semelles)."""
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
                            poutre_l, poutre_h, acier_ratios=ar)

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
    sheet_header(ws, ["Poste", "Détail", "Volume (m³)", "Ratio acier (kg/m³)", "Aciers (kg)"],
                 [30, 40, 14, 18, 14])
    r = d.get("acier_ratios") or {}
    ws.append(["Poteaux", f"{d.get('poteaux', 0)} u", d.get("beton_poteaux_m3", 0),
               r.get("poteaux"), d.get("acier_poteaux_kg", 0)])
    ws.append(["Poutres / linteaux",
               f"{d.get('poutres_ml', 0)} ml · section {d.get('beton_poutre_section', '')}",
               d.get("beton_poutres_m3", 0), r.get("poutres"), d.get("acier_poutres_kg", 0)])
    ws.append(["Dalles / planchers",
               f"{d.get('planchers_m2', 0)} m² · ép. {d.get('beton_dalle_ep_m', 0)} m",
               d.get("beton_dalles_m3", 0), r.get("dalles"), d.get("acier_dalles_kg", 0)])
    ws.append(["Voiles (murs porteurs)",
               f"{d.get('murs_porteurs_ml', 0)} ml · ép. {d.get('beton_voile_ep_m', 0)} m · h {d.get('wall_height_m', 0)} m",
               d.get("beton_voiles_m3", 0), r.get("voiles"), d.get("acier_voiles_kg", 0)])
    ws.append(["Semelles / fondations", f"{d.get('semelles', 0)} u", d.get("beton_semelles_m3", 0),
               r.get("semelles"), d.get("acier_semelles_kg", 0)])
    ws.append([])
    ws.append(["TOTAL BÉTON", "", d.get("beton_total_m3", 0), "", d.get("acier_total_kg", 0)])
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
                            poutre_l, poutre_h, acier_ratios=ar)

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


@router.post("/{plan_id}/detect-structure-all")
async def detect_structure_all(plan_id: str, user=Depends(current_user)) -> dict:
    """Lance la détection IA sur TOUTES les pages du plan (PDF multi-pages)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
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
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id},
            {"$set": {f"structure.{idx}": {**res, "detected_at": _now()}}})
        results.append({"page_index": idx, "wall_count": res.get("wall_count", 0),
                        "opening_count": res.get("opening_count", 0),
                        "beam_count": res.get("beam_count", 0), "error": res.get("error")})
    await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {"updated_at": _now()}})
    return {"pages": results, "page_count": len(pages)}


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
                             margin_pct: float = 0.0,
                             margin_beton: float | None = None, margin_acier: float | None = None,
                             margin_labor: float | None = None,
                             client_id: str | None = None,
                             beton_only: bool = False,
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
                                     poutre_l, poutre_h, acier_ratios=ar, floors_only=beton_only)
    lines = _beton_line_items(descriptif) if beton_only else _descriptif_line_items(descriptif)
    if not lines:
        raise HTTPException(400, "Aucune quantité à chiffrer — analysez le plan d'abord.")
    # Prix indicatifs de repli si l'utilisateur n'a rien configuré → chiffrage automatique
    _margins_set = any(m is not None for m in (margin_beton, margin_acier, margin_labor))
    beton_price_m3, acier_price_kg, labor_price_m3, margin_pct = _with_default_prices(
        beton_price_m3, acier_price_kg, labor_price_m3, margin_pct, margins_set=_margins_set)
    lines, priced = await _apply_library_prices(user["user_id"], lines)
    # Prix acier au kg (chiffrage instantané de la ligne « Aciers HA » si non chiffrée par la bibliothèque)
    if acier_price_kg and acier_price_kg > 0:
        for ln in lines:
            if "acier" in (ln.get("designation") or "").lower() and not ln.get("unit_price_ht"):
                ln["unit_price_ht"] = round(float(acier_price_kg), 2)
                priced += 1
    # Prix béton au m³ — s'applique à la ligne « Béton coulé » ou à chaque poste béton (mode gros œuvre)
    if beton_price_m3 and beton_price_m3 > 0:
        for ln in lines:
            desig = (ln.get("designation") or "").lower()
            is_beton = ("béton coulé" in desig) or (desig.startswith("béton") and "main d'œuvre" not in desig)
            if is_beton and not ln.get("unit_price_ht"):
                ln["unit_price_ht"] = round(float(beton_price_m3), 2)
                priced += 1
    # Main d'œuvre béton (au m³)
    beton_total = descriptif.get("beton_total_m3") or 0
    if labor_price_m3 and labor_price_m3 > 0 and beton_total > 0:
        lines.append({"designation": "Main d'œuvre béton (coffrage, coulage, ferraillage)",
                      "unit": "m³", "qty": round(beton_total, 2),
                      "unit_price_ht": round(float(labor_price_m3), 2), "vat_rate": 10,
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


@router.get("/{plan_id}/walls-summary")
async def walls_summary(plan_id: str, user=Depends(current_user)) -> dict:
    """Résumé des murs détectés par type + ML total pour lien avec l'estimation."""
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
    kind: Literal["distance", "polyline", "polygon"]
    points: list[tuple[float, float]] = Field(min_length=2)
    label: str | None = Field(default=None, max_length=80)


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
              "created_at": _now(), **result}
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$push": {"measurements": {"$each": [record], "$slice": -50}},
         "$set": {"updated_at": _now()}})
    return record


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
    label: str = Field(max_length=80)


@router.patch("/{plan_id}/measurements/{measurement_id}")
async def rename_measurement(plan_id: str, measurement_id: str,
                             body: MeasureLabelIn, user=Depends(current_user)) -> dict:
    """Modifie le libellé d'une mesure (ex. « murs parpaing », « murs en brique »)."""
    label = body.label.strip()[:80] or None
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"],
         "measurements.measurement_id": measurement_id},
        {"$set": {"measurements.$.label": label, "updated_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Mesure introuvable")
    return {"ok": True, "label": label}


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
        doors = sum(len([o for o in r.get("openings", [])
                          if (o.get("kind") or o.get("type") or "").lower().startswith("port")])
                    for r in rooms)
        result["skirting"] = G.skirting_length_m(perim, doors * 0.9)
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
