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
    # Accès Plan ouvert à tous les utilisateurs connectés (rendus 3D payants à l'unité)
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
async def list_plans(user=Depends(current_user)) -> dict:
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
async def delete_plan(plan_id: str, user=Depends(current_user)) -> dict:
    res = await db.plans_takeoff.delete_one({"plan_id": plan_id, "user_id": user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Plan introuvable")
    return {"ok": True}


def _duplicate_filename(name: str) -> str:
    """Ajoute un suffixe '(copie)' avant l'extension, ou '(copie N)' si déjà présent."""
    base = name or "plan"
    dot = base.rfind(".")
    stem, ext = (base[:dot], base[dot:]) if dot > 0 else (base, "")
    if "(copie" in stem:
        return f"{stem.rsplit('(copie', 1)[0].rstrip()} (copie 2){ext}"
    return f"{stem} (copie){ext}"


@router.post("/{plan_id}/duplicate")
async def duplicate_plan(plan_id: str, user=Depends(current_user)) -> dict:
    """Clone un plan (pages, rooms, ouvertures, calibrations, defaults) sous un
    nouveau plan_id. Utile pour tester des variantes (finitions, cloisons différentes).

    Ne copie PAS : les rendus 3D, les vidéos, les snapshots d'historique — le duplicata
    démarre propre. Le fichier PDF/image d'origine (pages avec image_png_b64) est bien
    conservé pour que le duplicata soit exploitable sans réimport.
    """
    # Accès Plan ouvert à tous les utilisateurs connectés (rendus 3D payants à l'unité)
    src = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not src:
        raise HTTPException(404, "Plan introuvable")

    new_id = "plan_" + secrets.token_hex(6)
    dup = {
        "plan_id": new_id,
        "user_id": user["user_id"],
        "project_id": src.get("project_id"),
        "filename": _duplicate_filename(src.get("filename") or "plan"),
        "size_bytes": src.get("size_bytes"),
        "kind": src.get("kind"),
        "page_count": src.get("page_count"),
        "detected_scale_denominator": src.get("detected_scale_denominator"),
        "pages": src.get("pages") or [],
        "calibrations": dict(src.get("calibrations") or {}),
        "rooms": [dict(r) for r in (src.get("rooms") or [])],
        "measurements": list(src.get("measurements") or []),
        "ai_analysis": src.get("ai_analysis"),
        "plan_defaults": src.get("plan_defaults"),
        "walls_detected": src.get("walls_detected"),
        "created_at": _now(),
        "updated_at": _now(),
        "duplicated_from": plan_id,
    }
    await db.plans_takeoff.insert_one(dup)
    return {"ok": True, "plan_id": new_id, "duplicated_from": plan_id,
            "filename": dup["filename"], "rooms": len(dup["rooms"])}


# ============ CALIBRATION ============

class CalibIn(BaseModel):
    page_index: int
    p1: tuple[float, float]
    p2: tuple[float, float]
    real_distance_m: float = Field(gt=0, le=10000)
    method: Literal["two_points", "known_dimension"] = "two_points"


@router.post("/{plan_id}/calibrate")
async def calibrate_plan(plan_id: str, body: CalibIn, user=Depends(current_user)) -> dict:
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
async def update_plan_defaults(plan_id: str, body: PlanDefaultsIn, user=Depends(current_user)) -> dict:
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
                        user=Depends(current_user)) -> dict:
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


# ============ ANNOTATIONS (Counter / Notes / Angles / Roof pitch surfaces) ============
# Inspiré de QuoterPlan : outils de traçage plan persistés par page dans plan.annotations

class CounterMarker(BaseModel):
    x: float
    y: float


class CounterAnnotation(BaseModel):
    id: str
    label: str = "Compteur"
    color: str = "#f97316"  # orange par défaut (ConstruPilot palette)
    unit: str = "u"          # u / prises / spots / radiateurs / m² / etc.
    markers: list[CounterMarker] = []


class NoteAnnotation(BaseModel):
    id: str
    x: float
    y: float
    text: str = ""


class AngleAnnotation(BaseModel):
    id: str
    # 3 points : sommet + 2 branches
    vx: float
    vy: float
    ax: float
    ay: float
    bx: float
    by: float
    degrees: float
    label: str | None = None  # ex: "Pente toiture ouest"


class PitchSurfaceAnnotation(BaseModel):
    id: str
    points: list[list[float]]       # polygone en pixels
    projected_area_m2: float         # aire vue en plan
    pitch_degrees: float             # inclinaison (0 = à plat)
    real_area_m2: float              # aire réelle = projected / cos(pitch)
    label: str | None = None


class AnnotationsIn(BaseModel):
    page_index: int = 0
    counters: list[CounterAnnotation] = []
    notes: list[NoteAnnotation] = []
    angles: list[AngleAnnotation] = []
    pitched_surfaces: list[PitchSurfaceAnnotation] = []


@router.patch("/{plan_id}/annotations")
async def save_annotations(plan_id: str, body: AnnotationsIn, user=Depends(current_user)) -> dict:
    """Persiste les 4 types d'annotations QuoterPlan-like par page (compteur / note / angle / pente).

    Le document plan stocke `annotations` = { "<page_index>": { counters, notes, angles, pitched_surfaces } }.
    """
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages": 1, "annotations": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    if body.page_index < 0 or body.page_index >= len(p.get("pages") or []):
        raise HTTPException(404, "Page inconnue")

    page_key = str(body.page_index)
    payload = {
        "counters": [c.model_dump() for c in body.counters],
        "notes": [n.model_dump() for n in body.notes],
        "angles": [a.model_dump() for a in body.angles],
        "pitched_surfaces": [s.model_dump() for s in body.pitched_surfaces],
    }
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"annotations.{page_key}": payload, "updated_at": _now()}}
    )
    total_counter_items = sum(len(c["markers"]) for c in payload["counters"])
    return {"ok": True, "page_index": body.page_index,
            "totals": {"counters": len(payload["counters"]),
                       "counter_items": total_counter_items,
                       "notes": len(payload["notes"]),
                       "angles": len(payload["angles"]),
                       "pitched_surfaces": len(payload["pitched_surfaces"])}}
