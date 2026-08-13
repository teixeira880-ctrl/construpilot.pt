"""AI/CV analysis + rooms + measurements + takeoff + materials + history + compare.

Refactor iter53 : extrait de `routes/plans.py`.
"""
from __future__ import annotations

import logging
import secrets
from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import geometry as G
from engines.plan_ai import analyze_plan_image
from engines.plan_cv import detect_all_rooms, detect_walls, flood_fill_room

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


# ============ COMPUTER VISION (Phase B) ============

class RoomAutofillIn(BaseModel):
    page_index: int
    seed_x: int = Field(ge=0)
    seed_y: int = Field(ge=0)
    tolerance: int = Field(default=25, ge=1, le=100)


@router.post("/{plan_id}/detect-walls")
async def detect_walls_route(plan_id: str, page_index: int = 0,
                              user=Depends(current_user)):
    """Détecte automatiquement les segments de murs sur une page via OpenCV Hough."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1},
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
        result = detect_walls(img)
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
                           body: WallTypeIn, user=Depends(current_user)):
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
async def walls_summary(plan_id: str, user=Depends(current_user)):
    """Résumé des murs détectés par type + ML total pour lien avec l'estimation."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "cv_walls": 1, "calibrations": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    cv_walls = p.get("cv_walls") or {}
    calibs = p.get("calibrations") or {}
    scales = [c.get("scale_m_per_px") for c in calibs.values() if c.get("scale_m_per_px")]
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


@router.post("/{plan_id}/measure")
async def measure(plan_id: str, body: MeasureIn, user=Depends(current_user)):
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
        return {"kind": "distance",
                "value_m": round(G.distance_m(body.points[0], body.points[1], ppm), 3)}
    if body.kind == "polyline":
        return {"kind": "polyline",
                "length_m": round(G.polyline_length_m(body.points, ppm), 3)}
    if len(body.points) < 3:
        raise HTTPException(422, "polygon >= 3 points")
    return {
        "kind": "polygon",
        "area_m2": round(G.polygon_area_m2(body.points, ppm), 3),
        "perimeter_m": round(G.polygon_perimeter_m(body.points, ppm), 3),
    }


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
                          user=Depends(current_user)):
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
async def delete_room(plan_id: str, room_id: str, user=Depends(current_user)):
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$pull": {"rooms": {"room_id": room_id}}, "$set": {"updated_at": _now()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Plan introuvable")
    await _snapshot(plan_id, user["user_id"], "room_delete", {"room_id": room_id})
    return {"ok": True}


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
async def compare_plans(body: CompareIn, user=Depends(current_user)):
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
                             user=Depends(current_user)):
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
async def takeoff(plan_id: str, user=Depends(current_user)):
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
                          if o.get("type", "").lower().startswith("port")])
                    for r in rooms)
        result["skirting"] = G.skirting_length_m(perim, doors * 0.9)
    return result


# ============ HISTORIQUE (auto-snapshots) ============

@router.get("/{plan_id}/history")
async def list_history(plan_id: str, user=Depends(current_user)):
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
async def restore_snapshot(plan_id: str, snapshot_id: str, user=Depends(current_user)):
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
                        user=Depends(current_user)):
    """Renomme un snapshot d'historique (ex. « Version client 12/02 »)."""
    label = body.label.strip()[:80] or None
    res = await db.plans_takeoff_history.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"], "snapshot_id": snapshot_id},
        {"$set": {"label": label}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Snapshot introuvable")
    return {"ok": True, "snapshot_id": snapshot_id, "label": label}
