"""CRUD & calibration routes du module plans (upload, list, get, delete,
calibrate, plan defaults, page level).

Refactor iter53 : extrait de `routes/plans.py`.
"""
from __future__ import annotations

import logging
import secrets
from typing import Literal

from fastapi import Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import geometry as G
from engines.monetization import require_pro_business
from engines.plan_processor import auto_calibration_from_pdf_scale, process_upload

from routes.plans_common import (
    ALLOWED_MIMES, MAX_UPLOAD_MB, _now, _plan_summary, _snapshot, router,
)

logger = logging.getLogger(__name__)


# ============ UPLOAD ============

@router.post("/upload")
async def upload_plan(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    deskew: bool = Form(False),
    user=Depends(current_user),
):
    await require_pro_business(user)
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
    calibrations = _auto_calibrate_pages(parsed)

    doc = {
        "plan_id": plan_id,
        "user_id": user["user_id"],
        "project_id": project_id,
        "filename": file.filename,
        "size_bytes": len(data),
        "kind": parsed["kind"],
        "page_count": parsed["page_count"],
        "detected_scale_denominator": parsed.get("detected_scale_denominator"),
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


def _auto_calibrate_pages(parsed: dict) -> dict:
    """Try to derive an initial pixels_per_meter per page from the detected scale."""
    scale = parsed.get("detected_scale_denominator")
    if not scale:
        return {}
    calibs: dict = {}
    for pg in parsed["pages"]:
        ppm = auto_calibration_from_pdf_scale(scale, pg.get("dpi", 150))
        if ppm:
            calibs[str(pg["index"])] = {
                "pixels_per_meter": ppm,
                "method": "auto_pdf_scale",
                "scale_denominator": scale,
                "confidence": 0.75,
                "created_at": _now(),
            }
    return calibs


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


# ============ PLAN DEFAULTS & PAGE LEVEL ============

class PlanDefaultsIn(BaseModel):
    ceiling_h_m: float = Field(ge=1.5, le=6.0)
    floor_thickness_m: float = Field(ge=0.02, le=1.0)


@router.patch("/{plan_id}/defaults")
async def update_plan_defaults(plan_id: str, body: PlanDefaultsIn, user=Depends(current_user)):
    """Défauts globaux du plan (hauteur murs, épaisseur plancher)."""
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"plan_defaults": {"ceiling_h_m": body.ceiling_h_m,
                                     "floor_thickness_m": body.floor_thickness_m},
                   "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Plan introuvable")
    return {"ok": True,
            "plan_defaults": {"ceiling_h_m": body.ceiling_h_m,
                              "floor_thickness_m": body.floor_thickness_m}}


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
