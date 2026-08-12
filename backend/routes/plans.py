"""Routes ConstruPilot PLAN — takeoff 2D.

- POST /api/plans/upload          : upload PDF/JPG/PNG/WEBP (+ project_id optionnel)
- GET  /api/plans                  : liste des plans de l'utilisateur
- GET  /api/plans/{plan_id}        : détail (métadonnées + pages sans image_b64)
- GET  /api/plans/{plan_id}/page/{i} : image PNG b64 d'une page + vecteurs
- POST /api/plans/{plan_id}/calibrate : enregistre pixels_per_meter (par page)
- POST /api/plans/{plan_id}/analyze : lance analyse IA sur 1 page
- POST /api/plans/{plan_id}/rooms   : upsert d'une pièce (polygone)
- DELETE /api/plans/{plan_id}/rooms/{room_id}
- POST /api/plans/{plan_id}/measure : mesure ponctuelle (distance / polyline / polygon)
- GET  /api/plans/{plan_id}/takeoff : métré complet (agrégé)
- POST /api/plans/{plan_id}/materials : calc matériaux (peinture/plinthes/placo/sol) sur pièces
- POST /api/plans/{plan_id}/estimate : envoie le takeoff vers /estimation/compute
- DELETE /api/plans/{plan_id}
"""
from __future__ import annotations

import base64
import logging
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import geometry as G
from engines.plan_processor import process_upload, auto_calibration_from_pdf_scale
from engines.plan_ai import analyze_plan_image
from engines.plan_cv import detect_walls, flood_fill_room
from engines.pdf_takeoff import build_takeoff_pdf

logger = logging.getLogger(__name__)
router = APIRouter(tags=["plans"], prefix="/takeoffs")

MAX_UPLOAD_MB = 20
ALLOWED_MIMES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp",
                 "application/dxf", "image/vnd.dxf", "application/acad", "image/vnd.dwg"}


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _snapshot(plan_id: str, user_id: str, action: str, meta: dict | None = None):
    """Sauvegarde un instantané du plan avant/après une mutation (auto-history)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "rooms": 1, "calibrations": 1, "pages.level_index": 1,
         "pages.level_label": 1, "pages.index": 1}
    )
    if not p:
        return
    snap = {
        "snapshot_id": "snap_" + secrets.token_hex(6),
        "plan_id": plan_id, "user_id": user_id,
        "action": action, "meta": meta or {},
        "created_at": _now(),
        "rooms": p.get("rooms") or [],
        "calibrations": p.get("calibrations") or {},
        "page_levels": [{"index": pg.get("index"),
                         "level_index": pg.get("level_index"),
                         "level_label": pg.get("level_label")} for pg in (p.get("pages") or [])],
    }
    await db.plans_takeoff_history.insert_one(snap)
    # Cap : garde les 50 derniers snapshots par plan
    old = await db.plans_takeoff_history.find(
        {"plan_id": plan_id, "user_id": user_id}, {"_id": 1}
    ).sort("created_at", -1).skip(50).to_list(200)
    if old:
        await db.plans_takeoff_history.delete_many({"_id": {"$in": [o["_id"] for o in old]}})


def _plan_summary(p: dict) -> dict:
    """Enlève les image_png_b64 pour un payload léger (list & detail)."""
    pages_light = [
        {k: v for k, v in pg.items() if k != "image_png_b64"}
        for pg in (p.get("pages") or [])
    ]
    return {
        "plan_id": p["plan_id"],
        "filename": p.get("filename"),
        "kind": p.get("kind"),
        "page_count": p.get("page_count"),
        "detected_scale_denominator": p.get("detected_scale_denominator"),
        "calibrations": p.get("calibrations", {}),
        "rooms": p.get("rooms", []),
        "ai_analysis": p.get("ai_analysis"),
        "project_id": p.get("project_id"),
        "pages": pages_light,
        "created_at": p.get("created_at"),
        "updated_at": p.get("updated_at"),
    }


# ============ UPLOAD ============

@router.post("/upload")
async def upload_plan(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    deskew: bool = Form(False),
    user=Depends(current_user),
):
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Fichier trop volumineux (>{MAX_UPLOAD_MB} Mo)")

    mime = (file.content_type or "").lower()
    lower_name = (file.filename or "").lower()
    is_cad = lower_name.endswith((".dxf", ".dwg"))
    if mime and mime not in ALLOWED_MIMES and not is_cad:
        if mime != "application/octet-stream":
            raise HTTPException(415, f"Format non supporté : {mime}")

    try:
        parsed = process_upload(data, file.filename or "plan", mime, deskew=deskew)
    except Exception as e:
        logger.exception("plan process failed")
        raise HTTPException(422, f"Impossible de lire le fichier : {e}")

    plan_id = "plan_" + secrets.token_hex(6)
    # Auto-calibration initiale par page si échelle détectée
    calibrations = {}
    scale = parsed.get("detected_scale_denominator")
    if scale:
        for pg in parsed["pages"]:
            ppm = auto_calibration_from_pdf_scale(scale, pg.get("dpi", 150))
            if ppm:
                calibrations[str(pg["index"])] = {
                    "pixels_per_meter": ppm,
                    "method": "auto_pdf_scale",
                    "scale_denominator": scale,
                    "confidence": 0.75,
                    "created_at": _now(),
                }

    doc = {
        "plan_id": plan_id,
        "user_id": user["user_id"],
        "project_id": project_id,
        "filename": file.filename,
        "size_bytes": len(data),
        "kind": parsed["kind"],
        "page_count": parsed["page_count"],
        "detected_scale_denominator": scale,
        "pages": parsed["pages"],
        "calibrations": calibrations,
        "rooms": [],
        "measurements": [],
        "ai_analysis": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.plans_takeoff.insert_one(doc)
    return _plan_summary(doc)


# ============ LIST / GET / DELETE ============

@router.get("")
async def list_plans(user=Depends(current_user)):
    docs = await db.plans_takeoff.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "pages.image_png_b64": 0}
    ).sort("created_at", -1).to_list(100)
    return {"plans": docs}


@router.get("/{plan_id}")
async def get_plan(plan_id: str, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    return _plan_summary(p)


@router.get("/{plan_id}/page/{page_index}")
async def get_plan_page(plan_id: str, page_index: int, user=Depends(current_user)):
    """Renvoie l'image PNG (base64) + vecteurs de la page demandée."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    return pages[page_index]


@router.delete("/{plan_id}")
async def delete_plan(plan_id: str, user=Depends(current_user)):
    res = await db.plans_takeoff.delete_one({"plan_id": plan_id, "user_id": user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Plan introuvable")
    return {"ok": True}


# ============ CALIBRATION ============

class CalibIn(BaseModel):
    page_index: int
    p1: tuple[float, float]
    p2: tuple[float, float]
    real_distance_m: float = Field(gt=0, le=10000)
    method: Literal["two_points", "known_dimension"] = "two_points"


@router.post("/{plan_id}/calibrate")
async def calibrate_plan(plan_id: str, body: CalibIn, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    try:
        calib = G.compute_calibration(body.p1, body.p2, body.real_distance_m)
    except ValueError as e:
        raise HTTPException(422, str(e))
    payload = {**calib, "method": body.method, "confidence": 0.95,
               "p1": list(body.p1), "p2": list(body.p2), "created_at": _now()}
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"calibrations.{body.page_index}": payload, "updated_at": _now()}}
    )
    await _snapshot(plan_id, user["user_id"], "calibrate",
                    {"page": body.page_index, "ppm": payload["pixels_per_meter"]})
    return {"ok": True, "page_index": body.page_index, "calibration": payload}


class CalibCheckIn(BaseModel):
    page_index: int
    p1: tuple[float, float]
    p2: tuple[float, float]
    expected_m: float = Field(gt=0)


@router.post("/{plan_id}/calibrate/check")
async def calibrate_check(plan_id: str, body: CalibCheckIn, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "calibrations": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    if not calib:
        raise HTTPException(400, "Page non calibrée")
    measured = G.distance_m(body.p1, body.p2, calib["pixels_per_meter"])
    return G.calibration_check(measured, body.expected_m)


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
    # Persist le résultat (utile pour re-render / debug)
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"cv_walls.{page_index}": {**result, "detected_at": _now()},
                  "updated_at": _now()}},
    )
    return result


@router.post("/{plan_id}/room-autofill")
async def room_autofill(plan_id: str, body: RoomAutofillIn, user=Depends(current_user)):
    """À partir d'un point cliqué à l'intérieur d'une pièce, extrait le polygone
    de son contour via flood fill. NB : le calcul de surface reste géré par le
    Geometry Engine — cette route ne renvoie QUE le polygone en pixels image.
    """
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

    # Si la page est calibrée, renvoie aussi la surface/périmètre calculés
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
        return {"kind": "distance", "value_m": round(G.distance_m(body.points[0], body.points[1], ppm), 3)}
    if body.kind == "polyline":
        return {"kind": "polyline", "length_m": round(G.polyline_length_m(body.points, ppm), 3)}
    # polygon
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
    openings: list[dict] = Field(default_factory=list)
    room_id: str | None = None


@router.post("/{plan_id}/rooms")
async def upsert_room(plan_id: str, body: RoomIn, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "calibrations": 1, "rooms": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    if not calib:
        raise HTTPException(400, "Page non calibrée")

    m = G.room_measurements(body.points, calib["pixels_per_meter"], body.ceiling_height_m or 2.5)
    net = G.subtract_openings(m["wall_area_gross_m2"], body.openings)

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


class CompareIn(BaseModel):
    before_plan_id: str
    after_plan_id: str
    surface_tolerance_pct: float = Field(default=5.0, ge=0, le=100)


@router.post("/compare")
async def compare_plans(body: CompareIn, user=Depends(current_user)):
    """Compare 2 plans (avant/après) et renvoie les pièces ajoutées, supprimées, modifiées."""
    before = await db.plans_takeoff.find_one(
        {"plan_id": body.before_plan_id, "user_id": user["user_id"]},
        {"_id": 0, "rooms": 1, "filename": 1}
    )
    after = await db.plans_takeoff.find_one(
        {"plan_id": body.after_plan_id, "user_id": user["user_id"]},
        {"_id": 0, "rooms": 1, "filename": 1}
    )
    if not before or not after:
        raise HTTPException(404, "Un des deux plans est introuvable")
    if body.before_plan_id == body.after_plan_id:
        raise HTTPException(400, "Sélectionnez deux plans différents")

    def _norm(name: str) -> str:
        import re
        return re.sub(r"\s+", " ", (name or "").strip().lower())

    rooms_b = before.get("rooms") or []
    rooms_a = after.get("rooms") or []
    by_name_b = {}
    for r in rooms_b:
        by_name_b.setdefault(_norm(r.get("name")), []).append(r)
    matched_after_names = set()

    added, removed, modified, unchanged = [], [], [], []
    tol = body.surface_tolerance_pct

    # Passe 1 : pour chaque room APRÈS, cherche un match dans AVANT (nom identique)
    for ra in rooms_a:
        name_norm = _norm(ra.get("name"))
        if name_norm in by_name_b and by_name_b[name_norm]:
            rb = by_name_b[name_norm].pop(0)
            matched_after_names.add(id(ra))
            sb = rb.get("surface_m2", 0)
            sa = ra.get("surface_m2", 0)
            delta_pct = abs(sa - sb) / sb * 100 if sb else 100
            entry = {
                "name": ra.get("name"),
                "surface_before_m2": sb, "surface_after_m2": sa,
                "delta_m2": round(sa - sb, 2),
                "delta_pct": round(delta_pct, 1),
                "perimeter_before_m": rb.get("perimeter_m", 0),
                "perimeter_after_m": ra.get("perimeter_m", 0),
            }
            (unchanged if delta_pct <= tol else modified).append(entry)

    # Rooms restantes dans AVANT non matchées → supprimées
    for lst in by_name_b.values():
        for rb in lst:
            removed.append({"name": rb.get("name"), "surface_m2": rb.get("surface_m2", 0),
                            "perimeter_m": rb.get("perimeter_m", 0)})

    # Rooms d'APRÈS non matchées → ajoutées
    for ra in rooms_a:
        if id(ra) not in matched_after_names:
            added.append({"name": ra.get("name"), "surface_m2": ra.get("surface_m2", 0),
                          "perimeter_m": ra.get("perimeter_m", 0)})

    total_b = sum(r.get("surface_m2", 0) for r in rooms_b)
    total_a = sum(r.get("surface_m2", 0) for r in rooms_a)
    return {
        "before": {"plan_id": body.before_plan_id, "filename": before.get("filename"),
                   "room_count": len(rooms_b), "total_surface_m2": round(total_b, 2)},
        "after": {"plan_id": body.after_plan_id, "filename": after.get("filename"),
                  "room_count": len(rooms_a), "total_surface_m2": round(total_a, 2)},
        "delta_surface_m2": round(total_a - total_b, 2),
        "delta_surface_pct": round((total_a - total_b) / total_b * 100, 2) if total_b else 0,
        "added": added, "removed": removed,
        "modified": modified, "unchanged": unchanged,
        "surface_tolerance_pct": tol,
    }


# ============ TAKEOFF AGRÉGÉ ============

class PageLevelIn(BaseModel):
    level_index: int | None = None
    level_label: str | None = None


@router.patch("/{plan_id}/pages/{page_index}/level")
async def set_page_level(plan_id: str, page_index: int, body: PageLevelIn,
                        user=Depends(current_user)):
    """Assigne un niveau (RDC / R+1 / R+2 / Sous-sol) à une page."""
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "pages": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    if page_index < 0 or page_index >= len(p.get("pages") or []):
        raise HTTPException(404, "Page inconnue")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"pages.{page_index}.level_index": body.level_index,
                  f"pages.{page_index}.level_label": body.level_label,
                  "updated_at": _now()}}
    )
    return {"ok": True, "page_index": page_index,
            "level_index": body.level_index, "level_label": body.level_label}


@router.get("/{plan_id}/takeoff")
async def takeoff(plan_id: str, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "rooms": 1, "filename": 1, "pages": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    pages = p.get("pages") or []
    # Map page_index -> level info
    page_level = {pg["index"]: {"index": pg.get("level_index"),
                                 "label": pg.get("level_label")}
                  for pg in pages}

    # Rooms enrichies avec info niveau (héritée de la page)
    def _lvl(r):
        info = page_level.get(r.get("page_index"), {"index": None, "label": None})
        return info

    # Grouped par niveau
    by_level: dict = {}
    for r in rooms:
        info = _lvl(r)
        key = f"{info['index'] if info['index'] is not None else 'none'}"
        bucket = by_level.setdefault(key, {
            "level_index": info["index"], "level_label": info["label"] or "Sans niveau",
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
    levels_sorted = sorted(by_level.values(),
                           key=lambda x: (x["level_index"] is None,
                                          x["level_index"] if x["level_index"] is not None else 99))

    total_floor = sum(r.get("surface_m2", 0) for r in rooms)
    total_ceiling = sum(r.get("ceiling_area_m2", 0) for r in rooms)
    total_walls_gross = sum(r.get("wall_area_gross_m2", 0) for r in rooms)
    total_walls_net = sum(r.get("wall_area_net_m2", 0) for r in rooms)
    total_perim = sum(r.get("perimeter_m", 0) for r in rooms)
    return {
        "plan_id": plan_id, "filename": p.get("filename"),
        "room_count": len(rooms),
        "totals": {
            "floor_m2": round(total_floor, 2),
            "ceiling_m2": round(total_ceiling, 2),
            "walls_gross_m2": round(total_walls_gross, 2),
            "walls_net_m2": round(total_walls_net, 2),
            "perimeter_m": round(total_perim, 2),
        },
        "levels": levels_sorted,
        "rooms": rooms,
    }


# ============ CALC MATÉRIAUX ============

class MaterialsIn(BaseModel):
    room_ids: list[str] | None = None   # None → toutes
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
        doors = sum(len([o for o in r.get("openings", []) if o.get("type", "").lower().startswith("port")])
                    for r in rooms)
        result["skirting"] = G.skirting_length_m(perim, doors * 0.9)
    return result


# ============ HISTORIQUE (auto-snapshots) ============

@router.get("/{plan_id}/history")
async def list_history(plan_id: str, user=Depends(current_user)):
    # Vérifie ownership
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "plan_id": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    snaps = await db.plans_takeoff_history.find(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "user_id": 0}
    ).sort("created_at", -1).to_list(100)
    return {"plan_id": plan_id, "history": snaps,
            "count": len(snaps)}


@router.post("/{plan_id}/history/restore/{snapshot_id}")
async def restore_snapshot(plan_id: str, snapshot_id: str, user=Depends(current_user)):
    snap = await db.plans_takeoff_history.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"], "snapshot_id": snapshot_id},
        {"_id": 0}
    )
    if not snap:
        raise HTTPException(404, "Snapshot introuvable")
    # snapshot du current avant restauration (pour permettre l'undo)
    await _snapshot(plan_id, user["user_id"], "before_restore",
                    {"restored_from": snapshot_id})
    # Restaure rooms + calibrations + levels
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "pages": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    updates = {"rooms": snap.get("rooms") or [],
               "calibrations": snap.get("calibrations") or {},
               "updated_at": _now()}
    # Restore page levels
    for pl in snap.get("page_levels") or []:
        idx = pl.get("index")
        if idx is not None:
            updates[f"pages.{idx}.level_index"] = pl.get("level_index")
            updates[f"pages.{idx}.level_label"] = pl.get("level_label")
    await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": updates})
    return {"ok": True, "restored_from": snapshot_id,
            "rooms": len(snap.get("rooms") or []),
            "action": snap.get("action")}


# ============ PDF EXPORT MÉTRÉ ============

@router.get("/{plan_id}/pdf")
async def export_takeoff_pdf(plan_id: str, include_materials: bool = True,
                              floor_material: str = "parquet",
                              user=Depends(current_user)):
    """Génère et renvoie le PDF de métré du plan (streaming binaire)."""
    from fastapi.responses import Response
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages.image_png_b64": 0}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")

    rooms = p.get("rooms") or []
    total_floor = sum(r.get("surface_m2", 0) for r in rooms)
    total_ceiling = sum(r.get("ceiling_area_m2", 0) for r in rooms)
    total_walls_gross = sum(r.get("wall_area_gross_m2", 0) for r in rooms)
    total_walls_net = sum(r.get("wall_area_net_m2", 0) for r in rooms)
    total_perim = sum(r.get("perimeter_m", 0) for r in rooms)

    # Reconstitue le takeoff (comme /takeoff)
    page_level = {pg.get("index"): {"index": pg.get("level_index"),
                                     "label": pg.get("level_label")}
                  for pg in (p.get("pages") or [])}
    by_level: dict = {}
    for r in rooms:
        info = page_level.get(r.get("page_index"), {"index": None, "label": None})
        key = f"{info['index'] if info['index'] is not None else 'none'}"
        bucket = by_level.setdefault(key, {
            "level_index": info["index"], "level_label": info["label"] or "Sans niveau",
            "rooms": [], "totals": {"floor_m2": 0, "walls_net_m2": 0, "perimeter_m": 0}})
        bucket["rooms"].append(r)
        bucket["totals"]["floor_m2"] += r.get("surface_m2", 0)
        bucket["totals"]["walls_net_m2"] += r.get("wall_area_net_m2", 0)
        bucket["totals"]["perimeter_m"] += r.get("perimeter_m", 0)
    for b in by_level.values():
        for k in b["totals"]:
            b["totals"][k] = round(b["totals"][k], 2)
    levels_sorted = sorted(by_level.values(),
                           key=lambda x: (x["level_index"] is None,
                                          x["level_index"] if x["level_index"] is not None else 99))

    takeoff = {
        "room_count": len(rooms), "rooms": rooms, "levels": levels_sorted,
        "totals": {"floor_m2": round(total_floor, 2),
                    "ceiling_m2": round(total_ceiling, 2),
                    "walls_gross_m2": round(total_walls_gross, 2),
                    "walls_net_m2": round(total_walls_net, 2),
                    "perimeter_m": round(total_perim, 2)},
    }

    # Matériaux (optionnel)
    materials = None
    if include_materials and rooms:
        floor_q = G.floor_quantity(total_floor, floor_material)
        paint_q = G.paint_liters(total_walls_net + total_ceiling)
        placo_q = G.placo_quantity(total_walls_net + total_ceiling)
        doors_est = 2 * len(rooms)  # heuristique
        skirt_q = G.skirting_length_m(total_perim, doors_est * 0.9)
        materials = {"floor": floor_q, "paint": paint_q,
                      "placo": placo_q, "skirting": skirt_q}

    plan_light = {"plan_id": p.get("plan_id"), "filename": p.get("filename"),
                  "page_count": p.get("page_count", 1)}

    # Branding pro personnalisé (si défini sur le user)
    user_doc = await db.users.find_one({"user_id": user["user_id"]},
                                         {"_id": 0, "brand_company_name": 1,
                                          "brand_contact_line": 1, "brand_logo_b64": 1})
    branding = None
    if user_doc:
        if any(user_doc.get(k) for k in ("brand_company_name", "brand_contact_line", "brand_logo_b64")):
            branding = {"company_name": user_doc.get("brand_company_name"),
                        "contact_line": user_doc.get("brand_contact_line"),
                        "logo_b64": user_doc.get("brand_logo_b64")}

    pdf_bytes = build_takeoff_pdf(plan_light, takeoff, materials, branding=branding)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="metre-{plan_id}.pdf"'}
    )
