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

logger = logging.getLogger(__name__)
router = APIRouter(tags=["plans"], prefix="/takeoffs")

MAX_UPLOAD_MB = 20
ALLOWED_MIMES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp"}


def _now():
    return datetime.now(timezone.utc).isoformat()


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
    user=Depends(current_user),
):
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Fichier trop volumineux (>{MAX_UPLOAD_MB} Mo)")

    mime = (file.content_type or "").lower()
    if mime and mime not in ALLOWED_MIMES:
        # tolérance : certains browsers envoient application/octet-stream
        if mime != "application/octet-stream":
            raise HTTPException(415, f"Format non supporté : {mime}")

    try:
        parsed = process_upload(data, file.filename or "plan", mime)
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
    return room


@router.delete("/{plan_id}/rooms/{room_id}")
async def delete_room(plan_id: str, room_id: str, user=Depends(current_user)):
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$pull": {"rooms": {"room_id": room_id}}, "$set": {"updated_at": _now()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Plan introuvable")
    return {"ok": True}


# ============ TAKEOFF AGRÉGÉ ============

@router.get("/{plan_id}/takeoff")
async def takeoff(plan_id: str, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "rooms": 1, "filename": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
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
