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
from engines.plan_processor import auto_calibration_from_pdf_scale

from routes.plans_common import (
    _diff_rooms, _now, _snapshot, router,
)

logger = logging.getLogger(__name__)


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
    """Recalcule surface / périmètre / murs / volume d'une pièce avec un nouveau ppm."""
    pts = room.get("points") or []
    if len(pts) < 3 or not ppm or ppm <= 0:
        return room
    height = float(room.get("ceiling_height_m") or 2.5)
    m = G.room_measurements(pts, ppm, height)
    net = G.subtract_openings(m["wall_area_gross_m2"], room.get("openings") or [])
    room.update({
        "surface_m2": m["surface_m2"], "perimeter_m": m["perimeter_m"],
        "ceiling_area_m2": m["ceiling_area_m2"],
        "wall_area_gross_m2": m["wall_area_gross_m2"],
        "wall_area_net_m2": net["wall_area_net_m2"],
        "openings_area_m2": net["openings_area_m2"],
        "volume_m3": round(m["surface_m2"] * height, 3),
    })
    written = room.get("surface_written_m2")
    if written and m["surface_m2"] > 0:
        room["surface_delta_pct"] = round((float(written) / m["surface_m2"] - 1) * 100, 1)
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
