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

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user, admin_user
from engines import geometry as G
from engines.plan_processor import process_upload, auto_calibration_from_pdf_scale
from engines.plan_ai import analyze_plan_image
from engines.plan_cv import detect_walls, flood_fill_room, detect_all_rooms
from engines.pdf_takeoff import build_takeoff_pdf

logger = logging.getLogger(__name__)
router = APIRouter(tags=["plans"], prefix="/takeoffs")
# Sub-router for non-plan-scoped routes (templates, tracking, notifs, public sign, multi)
quote_router = APIRouter(tags=["quotes"], prefix="/quotes")

MAX_UPLOAD_MB = 20
ALLOWED_MIMES = {"application/pdf", "image/png", "image/jpeg", "image/jpg", "image/webp",
                 "application/dxf", "image/vnd.dxf", "application/acad", "image/vnd.dwg"}

# ID prefixes (not secrets — pass through to caller for prefix-based routing)
SIG_TOKEN_PREFIX = "sig_"  # noqa: S105  identifier prefix, entropy provided by token_urlsafe
QUOTE_SEND_PREFIX = "qs_"  # noqa: S105  identifier prefix, entropy provided by token_hex


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _snapshot(plan_id: str, user_id: str, action: str, meta: dict | None = None,
                    label: str | None = None):
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
        "label": (label or "").strip()[:80] or None,
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


# ============ AI 3D RENDER (Nano Banana / Gemini image-to-image) ============

class Render3DIn(BaseModel):
    page_index: int = 0
    style: str = "photoreal"  # photoreal | isometric | axonometric | interior
    include_furniture: bool = True
    extra_prompt: str | None = None


_STYLE_PROMPTS = {
    "photoreal": "photorealistic 3D architectural render, natural daylight, "
                  "realistic materials (wood floor, painted walls, ceramic tiles), "
                  "shallow depth of field, high detail",
    "isometric": "clean isometric 3D architectural rendering, 45° angle, no "
                  "perspective distortion, soft ambient lighting, colored floors "
                  "per room type, blueprint aesthetic",
    "axonometric": "axonometric cutaway 3D render showing walls in section, "
                    "colored floor tiles per room, precise architectural style, "
                    "white walls, cool ambient lighting",
    "interior": "photorealistic interior view of the largest living room in this "
                 "floor plan, modern French residential style, warm daylight through "
                 "windows, natural materials",
}


@router.post("/{plan_id}/render-3d")
async def render_3d(plan_id: str, body: Render3DIn, user=Depends(current_user)):
    """Convertit la page du plan 2D en rendu 3D via Gemini Nano Banana.

    Retourne une image PNG base64 stockée sur le plan (permet re-render sans coût).
    """
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1, "filename": 1, "rooms": 1, "ai_analysis": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if body.page_index < 0 or body.page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    img_b64 = pages[body.page_index].get("image_png_b64")
    if not img_b64:
        raise HTTPException(500, "Image du plan manquante")

    generated_b64, mime, prompt = await _gemini_render_3d(
        plan_id=plan_id, page_index=body.page_index, page_img_b64=img_b64,
        rooms=p.get("rooms") or [], ai_analysis=p.get("ai_analysis") or {},
        style=body.style,
        include_furniture=body.include_furniture, extra_prompt=body.extra_prompt,
    )

    render_id = "r3d_" + secrets.token_hex(5)
    render_doc = {
        "render_id": render_id, "style": body.style,
        "include_furniture": body.include_furniture,
        "page_index": body.page_index,
        "created_at": _now(),
        "image_b64": generated_b64, "mime_type": mime,
        "prompt": prompt[:800],
    }
    # Append to plan.renders_3d (cap 10 dernières)
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$push": {"renders_3d": {"$each": [render_doc], "$slice": -10}}}
    )
    return {"ok": True, "render_id": render_id, "style": body.style,
            "mime_type": mime, "image_b64": generated_b64,
            "prompt_used": prompt[:400]}


async def _gemini_render_3d(*, plan_id: str, page_index: int, page_img_b64: str,
                             rooms: list, style: str, include_furniture: bool,
                             ai_analysis: dict | None = None,
                             extra_prompt: str | None = None) -> tuple[str, str, str]:
    """Core Gemini Nano Banana call — returns (b64_out, mime, prompt_used).

    Extracted so it can be reused by the multi-style video endpoint.
    """
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent

    api_key = os.getenv("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(500, "EMERGENT_LLM_KEY manquant")

    style_prompt = _STYLE_PROMPTS.get(style, _STYLE_PROMPTS["photoreal"])
    room_hint = ""
    if rooms:
        room_labels = ", ".join(sorted({r.get("name", "") for r in rooms if r.get("name")}))
        if room_labels:
            room_hint = f"\nDetected room labels: {room_labels}."

    # Inject AI gros œuvre analysis for a more faithful 3D render
    ai_hint = ""
    ai = ai_analysis or {}
    ai_bits: list[str] = []
    facades = ai.get("facade_walls") or []
    if facades:
        f_parts = []
        for f in facades[:6]:
            orient = f.get("orientation") or "?"
            mat = f.get("material_guess") or "?"
            wt = f.get("wall_type") or "?"
            f_parts.append(f"{orient} facade ({wt} {mat} wall)")
        ai_bits.append("Facades: " + ", ".join(f_parts))
    stairs = ai.get("stairwells") or []
    if stairs:
        s_parts = []
        for s in stairs[:3]:
            typ = s.get("type") or "straight"
            steps = s.get("steps") or "?"
            lvls = " to ".join(s.get("connects_levels") or [])
            s_parts.append(f"{typ} staircase {steps} steps {lvls}")
        ai_bits.append("Stairs: " + "; ".join(s_parts))
    op = ai.get("openings") or {}
    if op.get("doors_visible") or op.get("windows_visible") or op.get("bays_visible"):
        ai_bits.append(
            f"Openings: {op.get('doors_visible', 0)} doors, "
            f"{op.get('windows_visible', 0)} windows, {op.get('bays_visible', 0)} bay windows"
        )
    floors = ai.get("floors") or {}
    if floors.get("floor_type"):
        ai_bits.append(f"Floor structure: {floors['floor_type']} "
                       f"(slab {floors.get('slab_thickness_m', 0.2)}m thick)")
    if ai_bits:
        ai_hint = "\nDetailed gros-œuvre context (respect exactly): " + " · ".join(ai_bits)

    furniture = ("with realistic furniture" if include_furniture
                  else "empty, no furniture")
    extra = f"\nAdditional instructions: {extra_prompt}" if extra_prompt else ""
    prompt = (
        f"Convert this 2D architectural floor plan into a {style_prompt}, "
        f"{furniture}. Preserve the room layout, walls, doors, windows and "
        f"staircases EXACTLY as shown — do not invent structure. Do NOT return "
        f"a 2D plan — generate a full 3D visualization."
        f"{room_hint}{ai_hint}{extra}"
    )

    try:
        chat = (LlmChat(api_key=api_key,
                        session_id=f"render3d_{plan_id}_{page_index}_{style}",
                        system_message="You are an architectural visualization AI.")
                .with_model("gemini", "gemini-2.5-flash-image"))
        message = UserMessage(text=prompt,
                              file_contents=[ImageContent(image_base64=page_img_b64)])
        _text_out, images = await chat.send_message_multimodal_response(message)
    except Exception as e:
        logger.error(f"_gemini_render_3d LLM error: {type(e).__name__} {e}")
        raise HTTPException(502, f"Génération 3D échouée : {type(e).__name__}") from e

    if not images:
        raise HTTPException(502,
            "Le modèle n'a pas renvoyé d'image (essayez un autre style).")
    return images[0].get("data"), images[0].get("mime_type", "image/png"), prompt


@router.get("/{plan_id}/renders-3d")
async def list_renders_3d(plan_id: str, user=Depends(current_user)):
    """Liste les rendus 3D déjà générés pour ce plan (sans les images b64 pour rester léger)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "renders_3d": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    renders = p.get("renders_3d") or []
    # Renvoie meta uniquement (pas image_b64 lourd)
    return {"plan_id": plan_id, "renders": [
        {"render_id": r.get("render_id"), "style": r.get("style"),
         "page_index": r.get("page_index"), "created_at": r.get("created_at"),
         "include_furniture": r.get("include_furniture")}
        for r in renders
    ]}


@router.get("/{plan_id}/renders-3d/{render_id}")
async def get_render_3d(plan_id: str, render_id: str, user=Depends(current_user)):
    """Récupère l'image d'un rendu 3D précédemment généré."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "renders_3d": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    for r in p.get("renders_3d") or []:
        if r.get("render_id") == render_id:
            return {"render_id": render_id, "style": r.get("style"),
                    "mime_type": r.get("mime_type", "image/png"),
                    "image_b64": r.get("image_b64"),
                    "created_at": r.get("created_at")}
    raise HTTPException(404, "Rendu 3D introuvable")



# ============ VIDEO TOUR 3D (multi-styles Nano Banana → MP4) ============

class RenderVideoIn(BaseModel):
    page_index: int = 0
    include_furniture: bool = True
    # Styles used in order (each = 5s clip). Default = the "wow" sequence.
    styles: list[str] = Field(default_factory=lambda:
        ["isometric", "photoreal", "axonometric", "interior"])
    # Extras (all default ON for max wow)
    add_watermark: bool = True   # overlay the pro's brand logo
    add_music: bool = True       # soft ambient background audio


@router.post("/{plan_id}/render-video")
async def render_video_tour(plan_id: str, body: RenderVideoIn, user=Depends(current_user)):
    """Génère 4 rendus IA du plan avec des styles différents et les assemble
    en un tour vidéo MP4 (Ken Burns + crossfade + filigrane logo + musique)
    à joindre au devis.

    Réutilise `_gemini_render_3d` pour chaque style. Prévoir 60-180s d'exécution.
    """
    import base64 as _b64
    from engines.video_tour import build_video_tour, VIDEO_CACHE_DIR  # noqa: F401

    if not body.styles or len(body.styles) < 2:
        raise HTTPException(400, "Au moins 2 styles requis pour un tour vidéo")
    if len(body.styles) > 6:
        raise HTTPException(400, "6 styles max par vidéo")
    unknown = [s for s in body.styles if s not in _STYLE_PROMPTS]
    if unknown:
        raise HTTPException(400, f"Style(s) inconnu(s) : {', '.join(unknown)}")

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1, "rooms": 1, "ai_analysis": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if body.page_index < 0 or body.page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    img_b64 = pages[body.page_index].get("image_png_b64")
    if not img_b64:
        raise HTTPException(500, "Image du plan manquante")
    rooms = p.get("rooms") or []
    ai_analysis = p.get("ai_analysis") or {}

    # 1) Generate one PNG per style (sequential — Gemini rate limits)
    frames_b64: list[str] = []
    for style in body.styles:
        b64_out, _mime, _prompt = await _gemini_render_3d(
            plan_id=plan_id, page_index=body.page_index, page_img_b64=img_b64,
            rooms=rooms, ai_analysis=ai_analysis,
            style=style, include_furniture=body.include_furniture,
        )
        frames_b64.append(b64_out)

    # 2) Load branding logo bytes (if user opted in AND has one)
    logo_bytes: bytes | None = None
    if body.add_watermark:
        branding = await _resolve_branding(user["user_id"]) or {}
        logo_b64 = branding.get("logo_b64")
        if logo_b64:
            try:
                logo_bytes = _b64.b64decode(logo_b64)
            except Exception as e:
                logger.warning(f"invalid brand logo b64: {e}")
                logo_bytes = None

    # 3) Assemble MP4 (ffmpeg)
    try:
        mp4_path, meta = build_video_tour(
            frames_b64, styles=body.styles,
            logo_bytes=logo_bytes, add_audio=body.add_music,
        )
    except Exception as e:
        logger.error(f"video_tour build failed: {type(e).__name__} {e}")
        raise HTTPException(502, f"Assemblage vidéo échoué : {type(e).__name__}") from e

    # 4) Save meta doc (video file kept on disk)
    doc = {
        "video_id": meta["video_id"],
        "plan_id": plan_id,
        "user_id": user["user_id"],
        "page_index": body.page_index,
        "styles": body.styles,
        "include_furniture": body.include_furniture,
        "duration_s": meta["duration_s"],
        "size_bytes": meta["size_bytes"],
        "filename": mp4_path.name,
        "has_watermark": meta["has_watermark"],
        "has_audio": meta["has_audio"],
        "created_at": _now(),
    }
    await db.plan_videos_3d.insert_one(doc)
    return {"ok": True, **{k: v for k, v in doc.items() if k != "_id"}}


@router.get("/{plan_id}/videos-3d")
async def list_videos_3d(plan_id: str, user=Depends(current_user)):
    """Liste les tours vidéo 3D générés pour ce plan (meta uniquement)."""
    cursor = db.plan_videos_3d.find(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "video_id": 1, "styles": 1, "duration_s": 1,
         "size_bytes": 1, "created_at": 1, "page_index": 1},
    ).sort("created_at", -1).limit(20)
    videos = await cursor.to_list(length=20)
    return {"plan_id": plan_id, "videos": videos}


@router.get("/{plan_id}/videos-3d/{video_id}/mp4")
async def get_video_3d_mp4(plan_id: str, video_id: str, user=Depends(current_user)):
    """Stream le MP4 depuis le disque (FileResponse)."""
    from fastapi.responses import FileResponse
    from engines.video_tour import get_video_path

    doc = await db.plan_videos_3d.find_one(
        {"plan_id": plan_id, "video_id": video_id, "user_id": user["user_id"]},
        {"_id": 0, "filename": 1},
    )
    if not doc:
        raise HTTPException(404, "Vidéo introuvable")
    path = get_video_path(video_id)
    if not path:
        raise HTTPException(404, "Fichier vidéo manquant sur le disque")
    return FileResponse(str(path), media_type="video/mp4",
                        filename=f"tour-3d-{plan_id}.mp4")



@router.post("/{plan_id}/detect-all-rooms")
async def detect_all_rooms_route(plan_id: str, page_index: int = 0, user=Depends(current_user)):
    """Auto-détection de TOUTES les pièces closes d'une page via findContours.

    Retourne les polygones simplifiés + surface_m2 (si calibré). Utilisé par le
    bouton "Importer ces pièces" côté frontend pour matcher les pièces IA avec
    des contours réels au lieu d'un carré approximatif.
    """
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
    floor_thickness_m: float | None = Field(default=0.15, ge=0.02, le=1.0)
    openings: list[dict] = Field(default_factory=list)
    room_id: str | None = None


class PlanDefaultsIn(BaseModel):
    ceiling_h_m: float = Field(ge=1.5, le=6.0)
    floor_thickness_m: float = Field(ge=0.02, le=1.0)


class OpeningIn(BaseModel):
    kind: str = Field(default="fenetre", max_length=20)   # porte / fenetre / baie
    width_m: float = Field(ge=0.05, le=10.0)
    height_m: float = Field(ge=0.05, le=6.0)
    count: int = Field(default=1, ge=1, le=100)
    label: str | None = Field(default=None, max_length=40)


@router.patch("/{plan_id}/defaults")
async def update_plan_defaults(plan_id: str, body: PlanDefaultsIn, user=Depends(current_user)):
    """Défauts globaux du plan (hauteur murs, épaisseur plancher).

    Appliqués à toutes les futures pièces créées via le canvas / auto-import IA.
    """
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


@router.post("/{plan_id}/rooms/{room_id}/openings")
async def add_opening(plan_id: str, room_id: str, body: OpeningIn, user=Depends(current_user)):
    """Ajoute une ouverture (porte/fenêtre/baie) à une pièce.

    La surface (width × height × count) est déduite des murs nets automatiquement.
    """
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

    m = G.room_measurements(body.points, calib["pixels_per_meter"], body.ceiling_height_m or 2.5)
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


class CompareIn(BaseModel):
    before_plan_id: str
    after_plan_id: str
    surface_tolerance_pct: float = Field(default=5.0, ge=0, le=100)


def _diff_rooms(rooms_b: list[dict], rooms_a: list[dict], tol: float = 5.0) -> dict:
    """Diff pur entre 2 listes de rooms — utilisé par plans-compare & snapshot-compare."""
    import re
    def _norm(name: str) -> str:
        return re.sub(r"\s+", " ", (name or "").strip().lower())

    by_name_b = {}
    for r in rooms_b:
        by_name_b.setdefault(_norm(r.get("name")), []).append(r)
    matched_after_names = set()

    added, removed, modified, unchanged = [], [], [], []
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
    for lst in by_name_b.values():
        for rb in lst:
            removed.append({"name": rb.get("name"), "surface_m2": rb.get("surface_m2", 0),
                            "perimeter_m": rb.get("perimeter_m", 0)})
    for ra in rooms_a:
        if id(ra) not in matched_after_names:
            added.append({"name": ra.get("name"), "surface_m2": ra.get("surface_m2", 0),
                          "perimeter_m": ra.get("perimeter_m", 0)})

    total_b = sum(r.get("surface_m2", 0) for r in rooms_b)
    total_a = sum(r.get("surface_m2", 0) for r in rooms_a)
    return {
        "delta_surface_m2": round(total_a - total_b, 2),
        "delta_surface_pct": round((total_a - total_b) / total_b * 100, 2) if total_b else 0,
        "added": added, "removed": removed,
        "modified": modified, "unchanged": unchanged,
        "surface_tolerance_pct": tol,
        "total_before_m2": round(total_b, 2), "total_after_m2": round(total_a, 2),
    }


@router.post("/compare")
async def compare_plans(body: CompareIn, user=Depends(current_user)):
    """Compare 2 plans (avant/après) et renvoie les pièces ajoutées, supprimées, modifiées."""
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

    # ============ WALLS DIFF (compare vecteurs) ============
    def _walls_of(cv_walls: dict | None) -> list[dict]:
        """Aplati cv_walls (par page) en une liste de segments."""
        if not cv_walls:
            return []
        segs = []
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

    def _seg_dir(s: dict) -> tuple[str, int, int]:
        """Renvoie ('h' ou 'v' ou 'o', mid_a, mid_b) pour un segment.
        h=horizontal (dy~0), v=vertical (dx~0), o=oblique (rare pour un plan).
        """
        dx = s["x2"] - s["x1"]
        dy = s["y2"] - s["y1"]
        if abs(dy) <= max(3, abs(dx) * 0.1):  # horizontal
            y_mid = int(round((s["y1"] + s["y2"]) / 2))
            x_min = int(round(min(s["x1"], s["x2"])))
            x_max = int(round(max(s["x1"], s["x2"])))
            return ("h", y_mid, (x_min, x_max))
        if abs(dx) <= max(3, abs(dy) * 0.1):  # vertical
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
            if o_orient != t_orient:
                continue
            if abs(o_mid - t_mid) > tol:
                continue
            # Chevauchement des ranges
            overlap = max(0, min(t_range[1], o_range[1]) - max(t_range[0], o_range[0]))
            length = max(1, t_range[1] - t_range[0])
            if overlap / length >= 0.6:  # au moins 60% de recouvrement
                return i
        return -1

    walls_b = _walls_of(before.get("cv_walls"))
    walls_a = _walls_of(after.get("cv_walls"))
    walls_removed, walls_added, walls_unchanged = [], [], []
    remaining_a = list(walls_a)
    for wb in walls_b:
        idx = _match_seg(wb, remaining_a)
        if idx >= 0:
            walls_unchanged.append(wb)
            remaining_a.pop(idx)
        else:
            walls_removed.append(wb)
    walls_added.extend(remaining_a)

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
        "walls": {
            "before_count": len(walls_b), "after_count": len(walls_a),
            "added": walls_added, "removed": walls_removed,
            "unchanged": walls_unchanged,
        },
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

    branding = await _resolve_branding(user["user_id"])

    pdf_bytes = build_takeoff_pdf(plan_light, takeoff, materials, branding=branding)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="metre-{plan_id}.pdf"'}
    )


# ============ PDF DEVIS (Full quote with labor + materials) ============

async def _resolve_branding(user_id: str) -> dict | None:
    """Récupère branding : prefer org branding si user en fait partie."""
    u = await db.users.find_one({"user_id": user_id},
                                 {"_id": 0, "organization_id": 1,
                                  "brand_company_name": 1, "brand_contact_line": 1,
                                  "brand_logo_b64": 1})
    if not u:
        return None
    if u.get("organization_id"):
        org = await db.organizations.find_one({"org_id": u["organization_id"]},
                                                {"_id": 0, "brand_company_name": 1,
                                                 "brand_contact_line": 1, "brand_logo_b64": 1})
        if org and any(org.get(k) for k in ("brand_company_name", "brand_contact_line",
                                              "brand_logo_b64")):
            return {"company_name": org.get("brand_company_name"),
                    "contact_line": org.get("brand_contact_line"),
                    "logo_b64": org.get("brand_logo_b64")}
    if any(u.get(k) for k in ("brand_company_name", "brand_contact_line", "brand_logo_b64")):
        return {"company_name": u.get("brand_company_name"),
                "contact_line": u.get("brand_contact_line"),
                "logo_b64": u.get("brand_logo_b64")}
    return None


async def _build_quote_and_pdf(plan_id: str, user_id: str, finish: str,
                                floor_material: str, include_paint: bool,
                                include_placo: bool, include_floor: bool,
                                include_skirting: bool) -> tuple[dict, bytes]:
    """Construit le quote (dict) + le PDF bytes. Réutilisé par download & send-quote."""
    from engines.pdf_takeoff import build_quote_pdf
    from engines.catalog import LOTS_BY_KEY

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"_id": 0, "pages.image_png_b64": 0}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    if not rooms:
        raise HTTPException(400, "Aucune pièce mesurée sur ce plan.")

    total_floor = sum(r.get("surface_m2", 0) for r in rooms)
    total_ceiling = sum(r.get("ceiling_area_m2", 0) for r in rooms)
    total_walls_net = sum(r.get("wall_area_net_m2", 0) for r in rooms)
    total_perim = sum(r.get("perimeter_m", 0) for r in rooms)

    mat_key = ("mat_eco" if finish == "eco"
                else "mat_premium" if finish == "premium" else "mat_std")

    line_items: list[dict] = []

    def add(name: str, qty: float, unit: str, mat_unit_eur: float, labour_unit_eur: float):
        if qty <= 0:
            return
        mat_total = round(qty * mat_unit_eur, 2)
        lab_total = round(qty * labour_unit_eur, 2)
        line_items.append({
            "name": name, "quantity": round(qty, 2), "unit": unit,
            "unit_material": mat_unit_eur, "unit_labour": labour_unit_eur,
            "material_total": mat_total, "labour_total": lab_total,
            "total": round(mat_total + lab_total, 2),
        })

    if include_placo:
        placo = LOTS_BY_KEY.get("placo")
        if placo:
            add("Plâtrerie / Placo (murs + plafonds)", total_walls_net + total_ceiling, "m²",
                placo.get(mat_key, 17), placo.get("labour", 26))
    if include_paint:
        peint = LOTS_BY_KEY.get("peinture")
        if peint:
            add("Peinture (murs + plafonds)", total_walls_net + total_ceiling, "m²",
                peint.get(mat_key, 8), peint.get("labour", 16))
    if include_floor:
        lot_key = "carrelage" if floor_material.lower() in ("carrelage", "tile") else "parquet"
        lot = LOTS_BY_KEY.get(lot_key)
        if lot:
            add(f"Sol : {lot['name']}", total_floor, "m²",
                lot.get(mat_key, 35), lot.get("labour", 26))
    if include_skirting:
        add("Plinthes (ml)", total_perim - 1.8 * sum(
            len([o for o in r.get("openings", [])
                 if o.get("type", "").lower().startswith("port")]) for r in rooms),
            "ml", 5.0, 6.0)

    subtotal_mat = round(sum(li["material_total"] for li in line_items), 2)
    subtotal_lab = round(sum(li["labour_total"] for li in line_items), 2)
    subtotal = round(subtotal_mat + subtotal_lab, 2)
    tva_rate = 0.10
    tva = round(subtotal * tva_rate, 2)
    ttc = round(subtotal + tva, 2)

    quote = {
        "plan_id": plan_id, "filename": p.get("filename"), "finish": finish,
        "floor_material": floor_material,
        "totals": {"floor_m2": round(total_floor, 2),
                    "ceiling_m2": round(total_ceiling, 2),
                    "walls_net_m2": round(total_walls_net, 2),
                    "perimeter_m": round(total_perim, 2)},
        "line_items": line_items,
        "subtotal_material": subtotal_mat,
        "subtotal_labour": subtotal_lab,
        "subtotal_ht": subtotal,
        "tva_rate": tva_rate, "tva": tva, "total_ttc": ttc,
    }
    branding = await _resolve_branding(user_id)
    pdf_bytes = build_quote_pdf(quote, branding=branding)
    return quote, pdf_bytes


@router.get("/{plan_id}/quote-pdf")
async def export_quote_pdf(plan_id: str, finish: str = "std",
                            floor_material: str = "carrelage",
                            include_paint: bool = True, include_placo: bool = True,
                            include_floor: bool = True, include_skirting: bool = True,
                            user=Depends(current_user)):
    """Génère un PDF Devis complet : main d'œuvre + matériaux pré-remplis depuis le takeoff."""
    from fastapi.responses import Response
    _q, pdf_bytes = await _build_quote_and_pdf(
        plan_id, user["user_id"], finish, floor_material,
        include_paint, include_placo, include_floor, include_skirting)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="devis-{plan_id}.pdf"'}
    )


class SendQuoteIn(BaseModel):
    client_email: str
    client_name: str | None = None
    client_address: str | None = None  # requis si include_tva_attestation
    work_address: str | None = None    # adresse des travaux (fallback : client_address)
    message: str | None = None
    subject: str | None = None
    intro: str | None = None
    finish: str = "std"
    floor_material: str = "carrelage"
    include_paint: bool = True
    include_placo: bool = True
    include_floor: bool = True
    include_skirting: bool = True
    cc_self: bool = True
    include_tva_attestation: bool = False  # ajoute l'attestation TVA 10 %
    attach_latest_video: bool = False       # attach the most recent 3D tour MP4


@router.post("/{plan_id}/send-quote")
async def send_quote(plan_id: str, body: SendQuoteIn, user=Depends(current_user)):
    """Envoie le PDF Devis directement au client par email + copie au sender + log."""
    import re
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", body.client_email or ""):
        raise HTTPException(400, "Email client invalide.")

    quote, pdf_bytes = await _build_quote_and_pdf(
        plan_id, user["user_id"], body.finish, body.floor_material,
        body.include_paint, body.include_placo, body.include_floor, body.include_skirting)

    if body.include_tva_attestation and not (body.client_address or "").strip():
        raise HTTPException(
            400,
            "Adresse client requise pour joindre l'attestation TVA."
        )

    # Récupère nom société pour email
    branding = await _resolve_branding(user["user_id"]) or {}
    sender_u = await db.users.find_one({"user_id": user["user_id"]},
                                         {"_id": 0, "name": 1, "email": 1})
    company = branding.get("company_name") or (sender_u or {}).get("name") or "ConstruPilot"
    contact = branding.get("contact_line") or ""

    ttc = quote.get("total_ttc", 0)
    finish_label = {"eco": "Éco", "std": "Standard", "premium": "Premium"}.get(
        body.finish, "Standard")

    # Email HTML (avec tracking pixel pour open notification)
    from engines.emailer import send_email_with_pdf, wrap_html
    hello = f"Bonjour {body.client_name}," if body.client_name else "Bonjour,"
    intro_html = (f"<p>{body.intro}</p>" if body.intro
                   else "<p>Veuillez trouver ci-joint votre <b>devis estimatif</b>"
                        f" ({finish_label}) élaboré depuis votre plan.</p>")
    custom = f"<p>{body.message}</p>" if body.message else ""
    log_id = QUOTE_SEND_PREFIX + secrets.token_hex(6)
    backend_public = os.getenv("PUBLIC_BACKEND_URL") or os.getenv("FRONTEND_URL") or ""
    pixel_tag = ""
    if backend_public:
        pixel_tag = (f'<img src="{backend_public}/api/quotes/track/open/{log_id}" '
                     f'width="1" height="1" alt="" style="display:block" />')
    inner = (
        f"<p>{hello}</p>"
        f"{intro_html}"
        f"{custom}"
        f"<div style='background:#FF5A00;color:white;padding:16px 22px;border-radius:6px;"
        f"font-size:18px;font-weight:700;text-align:center;letter-spacing:1px'>"
        f"Total TTC : {ttc:,.2f} €</div>"
        f"<p style='margin-top:16px'>Ce document est un devis estimatif indicatif "
        f"(TVA 10 % rénovation logement &gt; 2 ans). Nous restons à votre disposition "
        f"pour toute question ou visite technique.</p>"
        f"<p style='color:#666;font-size:12px;margin-top:24px'>"
        f"{company}<br/>{contact}</p>"
        f"{pixel_tag}"
    )
    subject = (body.subject or "").strip()[:180] or f"Devis · {company}"
    html = wrap_html(subject, inner)

    # ---- Attestation TVA optionnelle (rénovation logement > 2 ans) ----
    extra_attachments = []
    tva_pdf_bytes = None
    if body.include_tva_attestation:
        from engines.pdf_takeoff import build_tva_attestation_pdf
        # Description travaux : reprend les postes sélectionnés
        work_desc_parts = [li["name"] for li in quote.get("line_items", [])]
        work_desc = " ; ".join(work_desc_parts) if work_desc_parts else "Travaux de rénovation"
        client_addr = (body.client_address or "").strip()
        work_addr = (body.work_address or client_addr or "").strip()
        tva_pdf_bytes = build_tva_attestation_pdf(
            client_name=body.client_name or "",
            client_address=client_addr,
            work_address=work_addr,
            work_description=work_desc,
            company_name=company,
            company_address=contact or "",
            branding=branding, tva_rate=quote.get("tva_rate", 0.10),
        )
        extra_attachments.append({
            "filename": f"attestation-tva-{plan_id}.pdf",
            "content": tva_pdf_bytes,
            "content_type": "application/pdf",
        })
        # Mention supplémentaire dans le message
        inner_with_att = inner.replace(
            "Ce document est un devis estimatif indicatif",
            "Vous trouverez également jointe l'<b>attestation TVA à taux réduit</b> "
            "à nous retourner signée avant la facturation. Ce document est un "
            "devis estimatif indicatif"
        )
        html = wrap_html(subject, inner_with_att)

    # ---- Auto-attach latest 3D tour MP4 (if pro opted in) ----
    attached_video_id: str | None = None
    if body.attach_latest_video:
        latest = await db.plan_videos_3d.find_one(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            sort=[("created_at", -1)],
        )
        if latest:
            from engines.video_tour import get_video_path
            vpath = get_video_path(latest.get("video_id", ""))
            if vpath:
                try:
                    mp4_bytes = vpath.read_bytes()
                    # Cap at 20 MB to avoid Resend rejection
                    if len(mp4_bytes) <= 20 * 1024 * 1024:
                        extra_attachments.append({
                            "filename": f"tour-3d-{plan_id}.mp4",
                            "content": mp4_bytes,
                            "content_type": "video/mp4",
                        })
                        attached_video_id = latest["video_id"]
                        # Enrich email body with a video mention
                        html = html.replace(
                            "Total TTC :",
                            "<p style='margin:0 0 12px;font-size:13px;color:#FF5A00;"
                            "font-weight:700'>🎬 Un tour vidéo 3D de votre projet est "
                            "joint à cet email — regardez-le pour visualiser votre "
                            "chantier avant travaux.</p>Total TTC :",
                            1,
                        )
                    else:
                        logger.warning(
                            f"video too large to attach: {len(mp4_bytes)} bytes"
                        )
                except Exception as e:
                    logger.warning(f"failed to attach video: {e}")

    email_status = "sent"; email_id = None
    error = None
    try:
        cc = (sender_u or {}).get("email") if body.cc_self else None
        res = await send_email_with_pdf(body.client_email, subject,
                                          html, pdf_bytes,
                                          filename=f"devis-{plan_id}.pdf", cc=cc,
                                          extra_attachments=extra_attachments)
        email_id = res.get("id")
    except Exception as e:
        logger.warning(f"Send quote email failed: {e}")
        email_status = "failed"; error = str(e)

    # Log l'envoi en base
    log = {
        "log_id": log_id,
        "plan_id": plan_id, "user_id": user["user_id"],
        "client_email": body.client_email, "client_name": body.client_name,
        "client_address": body.client_address, "work_address": body.work_address,
        "cc": (sender_u or {}).get("email") if body.cc_self else None,
        "total_ttc": ttc, "finish": body.finish, "floor_material": body.floor_material,
        "subject": subject, "intro": body.intro, "message": body.message,
        "include_tva_attestation": body.include_tva_attestation,
        "attach_latest_video": body.attach_latest_video,
        "attached_video_id": attached_video_id,
        "email_status": email_status, "email_id": email_id, "error": error,
        "created_at": _now(),
        "opened": False, "open_count": 0,
        "signed": False,
        "reminder_sent": False,
    }
    await db.quote_sends.insert_one(log)
    return {"ok": email_status == "sent", "email_status": email_status,
            "email_id": email_id, "log_id": log["log_id"], "total_ttc": ttc}


@router.get("/{plan_id}/quote-sends")
async def list_quote_sends(plan_id: str, user=Depends(current_user)):
    """Historique des envois de devis pour ce plan."""
    docs = await db.quote_sends.find(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    return {"plan_id": plan_id, "sends": docs}


# ============ WORKFLOW : Plan → Estimation → Devis ============

class TakeoffEstimateIn(BaseModel):
    project_type: str = "renovation_complete"
    finish_level: str = "standard"
    country: str = "FR"
    region: str | None = "idf"
    building_type: str = "maison"
    condition: str = "bon"
    construction_year: int | None = None


@router.post("/{plan_id}/estimate-from-takeoff")
async def estimate_from_takeoff(plan_id: str, body: TakeoffEstimateIn,
                                 user=Depends(current_user)):
    """Envoie automatiquement la surface mesurée du plan à l'estimateur.

    Renvoie l'estimation complète (lots, prix, main d'œuvre) — prête à devenir
    un devis via `send-quote`.
    """
    from engines.estimation import estimate as estim_run

    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "rooms": 1, "filename": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    rooms = p.get("rooms") or []
    if not rooms:
        raise HTTPException(400, "Aucune pièce mesurée sur ce plan.")

    surface = round(sum(r.get("surface_m2", 0) for r in rooms), 2)
    if surface <= 0:
        raise HTTPException(400, "Surface mesurée invalide.")

    est = estim_run(
        project_type=body.project_type, surface=surface,
        finish=body.finish_level, country=body.country, region=body.region,
        building_type=body.building_type, condition=body.condition,
        construction_year=body.construction_year,
    )

    # Sauvegarde comme projet lié au plan (permet reprise ultérieure)
    proj = {
        "project_id": "proj_" + secrets.token_hex(6),
        "user_id": user["user_id"], "plan_id": plan_id,
        "name": p.get("filename") or "Projet depuis plan",
        "source": "plan_takeoff",
        "surface": surface, "room_count": len(rooms),
        "estimation": est,
        "created_at": _now(),
    }
    await db.projects.insert_one(proj)

    return {"ok": True, "project_id": proj["project_id"],
            "plan_id": plan_id, "surface_m2": surface,
            "room_count": len(rooms),
            "estimation": est,
            "is_renovation": "renovation" in body.project_type.lower()}


# ============ REMINDERS (Rappel Auto 5j) ============

REMINDER_DELAY_DAYS = 5


async def _run_reminders() -> dict:
    """Envoie un rappel aux devis ouverts mais non signés depuis > 5 jours."""
    from engines.emailer import send_email, wrap_html
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=REMINDER_DELAY_DAYS)).isoformat()
    candidates = await db.quote_sends.find(
        {"opened": True, "signed": False, "reminder_sent": {"$ne": True},
         "opened_at": {"$lte": cutoff}, "email_status": "sent"},
        {"_id": 0, "log_id": 1, "user_id": 1, "client_email": 1, "client_name": 1,
         "total_ttc": 1, "signature_token": 1, "plan_id": 1, "subject": 1}
    ).to_list(200)

    sent, failed, skipped = 0, 0, 0
    for c in candidates:
        try:
            branding = await _resolve_branding(c["user_id"]) or {}
            company = branding.get("company_name") or "ConstruPilot"
            hello = f"Bonjour {c['client_name']}," if c.get("client_name") else "Bonjour,"
            # Assure un lien de signature (si pas déjà créé)
            token = c.get("signature_token")
            if not token:
                token = SIG_TOKEN_PREFIX + secrets.token_urlsafe(18)
                await db.quote_sends.update_one({"log_id": c["log_id"]},
                    {"$set": {"signature_token": token,
                              "signature_token_created_at": _now()}})
            sign_url = f"{os.getenv('FRONTEND_URL', '')}/sign/{token}"
            inner = (
                f"<p>{hello}</p>"
                f"<p>Nous nous permettons un petit rappel : votre devis "
                f"(<b>{c.get('total_ttc', 0):,.2f} € TTC</b>) est toujours disponible "
                f"pour votre signature.</p>"
                f"<p>Il vous suffit d'un clic pour valider :</p>"
                f"<p style='text-align:center;margin:24px 0'>"
                f"<a href='{sign_url}' style='background:#FF5A00;color:white;"
                f"padding:14px 28px;border-radius:6px;text-decoration:none;"
                f"font-weight:700;font-size:16px'>Signer le devis</a></p>"
                f"<p>Nous restons à votre disposition pour toute question ou "
                f"ajustement.</p>"
                f"<p style='color:#666;font-size:12px;margin-top:24px'>"
                f"Cordialement,<br/>{company}</p>"
            )
            await send_email(c["client_email"], f"Rappel : votre devis · {company}",
                              wrap_html(f"Rappel devis · {company}", inner))
            await db.quote_sends.update_one({"log_id": c["log_id"]},
                {"$set": {"reminder_sent": True, "reminder_sent_at": _now()}})
            await db.notifications.insert_one({
                "notif_id": "n_" + secrets.token_hex(5),
                "user_id": c["user_id"], "type": "reminder_sent",
                "log_id": c["log_id"],
                "message": f"Rappel envoyé à {c['client_email']} (devis non signé "
                           f"depuis {REMINDER_DELAY_DAYS} j).",
                "created_at": _now(), "read": False,
            })
            sent += 1
        except Exception as e:
            logger.warning(f"reminder for {c.get('log_id')} failed: {e}")
            failed += 1
    return {"sent": sent, "failed": failed, "skipped": skipped,
            "candidates": len(candidates)}


@quote_router.post("/reminders/run")
async def trigger_reminders(user=Depends(admin_user)):
    """Endpoint admin pour lancer manuellement le job de rappels."""
    return await _run_reminders()


async def _reminders_scheduler():
    """Boucle asyncio interne : lance _run_reminders() toutes les 6 heures."""
    import asyncio
    await asyncio.sleep(600)  # ne démarre pas immédiatement au boot
    while True:
        try:
            res = await _run_reminders()
            if res["candidates"]:
                logger.info(f"reminders: {res}")
        except Exception as e:
            logger.warning(f"reminders_scheduler error: {e}")
        await asyncio.sleep(6 * 3600)  # toutes les 6 heures



# ============ QUOTE TEMPLATES (Devis Récurrents) ============

class QuoteTemplateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    finish: str = "std"
    floor_material: str = "carrelage"
    include_paint: bool = True
    include_placo: bool = True
    include_floor: bool = True
    include_skirting: bool = True
    is_shared: bool = False  # partagé au niveau organisation


@quote_router.post("/templates")
async def create_quote_template(body: QuoteTemplateIn, user=Depends(current_user)):
    tpl_id = "qtpl_" + secrets.token_hex(5)
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1}) or {}
    org_id = u.get("organization_id") if body.is_shared else None
    doc = {
        "template_id": tpl_id, "user_id": user["user_id"],
        "organization_id": org_id,
        "name": body.name.strip()[:80],
        "finish": body.finish, "floor_material": body.floor_material,
        "include_paint": body.include_paint, "include_placo": body.include_placo,
        "include_floor": body.include_floor, "include_skirting": body.include_skirting,
        "created_at": _now(),
    }
    await db.quote_templates.insert_one(doc)
    return {"ok": True, "template_id": tpl_id, **{k: v for k, v in doc.items() if k != "_id"}}


@quote_router.get("/templates")
async def list_quote_templates(user=Depends(current_user)):
    u = await db.users.find_one({"user_id": user["user_id"]},
                                 {"_id": 0, "organization_id": 1}) or {}
    org_id = u.get("organization_id")
    query = {"$or": [{"user_id": user["user_id"]}]}
    if org_id:
        query["$or"].append({"organization_id": org_id})
    docs = await db.quote_templates.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"templates": docs}


@quote_router.delete("/templates/{template_id}")
async def delete_quote_template(template_id: str, user=Depends(current_user)):
    tpl = await db.quote_templates.find_one({"template_id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(404, "Modèle introuvable")
    # Seul le créateur peut supprimer (même si partagé)
    if tpl.get("user_id") != user["user_id"]:
        raise HTTPException(403, "Réservé au créateur du modèle")
    await db.quote_templates.delete_one({"template_id": template_id})
    return {"ok": True}


# ============ MULTI-PLAN QUOTE PDF (Bundle) ============

class MultiQuoteIn(BaseModel):
    plan_ids: list[str] = Field(min_length=1, max_length=20)
    project_name: str | None = None
    finish: str = "std"
    floor_material: str = "carrelage"
    include_paint: bool = True
    include_placo: bool = True
    include_floor: bool = True
    include_skirting: bool = True


@quote_router.post("/multi-pdf")
async def export_multi_quote_pdf(body: MultiQuoteIn, user=Depends(current_user)):
    """Génère un PDF Devis projet consolidé pour plusieurs plans (multi-niveaux, extensions…)."""
    from fastapi.responses import Response
    from engines.pdf_takeoff import build_project_quote_pdf

    sub_quotes = []
    for pid in body.plan_ids:
        try:
            q, _pdf = await _build_quote_and_pdf(
                pid, user["user_id"], body.finish, body.floor_material,
                body.include_paint, body.include_placo,
                body.include_floor, body.include_skirting,
            )
            sub_quotes.append(q)
        except HTTPException as e:
            # Ignore un plan sans pièce (400) mais lève les 404
            if e.status_code == 400:
                continue
            raise
    if not sub_quotes:
        raise HTTPException(400, "Aucun plan n'a de pièce mesurée.")

    # Agrégation
    def _sum(key):
        return round(sum(q.get(key, 0) for q in sub_quotes), 2)
    project = {
        "project_name": (body.project_name or "Projet ConstruPilot").strip(),
        "plan_count": len(sub_quotes),
        "sub_quotes": sub_quotes,
        "totals": {
            "floor_m2": round(sum(q["totals"]["floor_m2"] for q in sub_quotes), 2),
            "ceiling_m2": round(sum(q["totals"]["ceiling_m2"] for q in sub_quotes), 2),
            "walls_net_m2": round(sum(q["totals"]["walls_net_m2"] for q in sub_quotes), 2),
            "perimeter_m": round(sum(q["totals"]["perimeter_m"] for q in sub_quotes), 2),
        },
        "subtotal_material": _sum("subtotal_material"),
        "subtotal_labour": _sum("subtotal_labour"),
        "subtotal_ht": _sum("subtotal_ht"),
        "tva_rate": 0.10,
        "tva": _sum("tva"),
        "total_ttc": _sum("total_ttc"),
        "finish": body.finish, "floor_material": body.floor_material,
    }
    branding = await _resolve_branding(user["user_id"])
    pdf_bytes = build_project_quote_pdf(project, branding=branding)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="devis-projet-{secrets.token_hex(3)}.pdf"'}
    )


# ============ EMAIL TRACKING (Alertes Devis) ============

@quote_router.get("/track/open/{log_id}", include_in_schema=False)
async def track_quote_open(log_id: str):
    """Pixel de tracking : marque le devis comme ouvert (idempotent)."""
    from fastapi.responses import Response
    # 1x1 transparent GIF
    pixel = b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04" \
            b"\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02" \
            b"D\x01\x00;"
    try:
        log = await db.quote_sends.find_one({"log_id": log_id}, {"_id": 0, "opened": 1,
                                                                    "user_id": 1, "client_email": 1})
        if log and not log.get("opened"):
            await db.quote_sends.update_one(
                {"log_id": log_id},
                {"$set": {"opened": True, "opened_at": _now()},
                 "$inc": {"open_count": 1}}
            )
            # Notif in-app pour le sender
            await db.notifications.insert_one({
                "notif_id": "n_" + secrets.token_hex(5),
                "user_id": log["user_id"],
                "type": "quote_opened", "log_id": log_id,
                "message": f"Le client ({log.get('client_email')}) a ouvert votre devis.",
                "created_at": _now(), "read": False,
            })
        elif log:
            await db.quote_sends.update_one({"log_id": log_id},
                                             {"$inc": {"open_count": 1},
                                              "$set": {"last_opened_at": _now()}})
    except Exception as e:
        logger.warning(f"tracking pixel fail {log_id}: {e}")
    return Response(content=pixel, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate"})


@quote_router.get("/notifications/me")
async def list_notifications(user=Depends(current_user)):
    docs = await db.notifications.find(
        {"user_id": user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)
    unread = sum(1 for d in docs if not d.get("read"))
    return {"unread": unread, "notifications": docs}


@quote_router.post("/notifications/{notif_id}/read")
async def mark_notification_read(notif_id: str, user=Depends(current_user)):
    await db.notifications.update_one(
        {"notif_id": notif_id, "user_id": user["user_id"]},
        {"$set": {"read": True, "read_at": _now()}}
    )
    return {"ok": True}


@quote_router.post("/notifications/read-all")
async def mark_all_notifications_read(user=Depends(current_user)):
    """Marque toutes les notifs comme lues."""
    res = await db.notifications.update_many(
        {"user_id": user["user_id"], "read": False},
        {"$set": {"read": True, "read_at": _now()}}
    )
    return {"ok": True, "marked": res.modified_count}


@quote_router.get("/sends/all")
async def list_all_quote_sends(user=Depends(current_user)):
    """Suivi Devis : tous les devis envoyés par l'utilisateur, plan_ids agrégés."""
    docs = await db.quote_sends.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "signature_b64": 0}  # signature_b64 lourde, on ne l'envoie pas
    ).sort("created_at", -1).limit(200).to_list(200)

    # Attache le filename du plan associé (une seule requête agrégée)
    plan_ids = list({d["plan_id"] for d in docs})
    plans = await db.plans_takeoff.find(
        {"plan_id": {"$in": plan_ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1, "filename": 1}
    ).to_list(500) if plan_ids else []
    filenames = {p["plan_id"]: p.get("filename") for p in plans}
    for d in docs:
        d["plan_filename"] = filenames.get(d["plan_id"])

    stats = {"sent": len(docs),
             "opened": sum(1 for d in docs if d.get("opened")),
             "signed": sum(1 for d in docs if d.get("signed")),
             "not_opened": sum(1 for d in docs
                                if not d.get("opened") and not d.get("signed"))}
    stats["total_ttc_signed"] = round(sum(d.get("total_ttc", 0) for d in docs
                                           if d.get("signed")), 2)
    stats["total_ttc_pipeline"] = round(sum(d.get("total_ttc", 0) for d in docs
                                              if not d.get("signed")), 2)
    return {"sends": docs, "stats": stats}



# ============ SIGNATURE CLIENT (Mode Signature) ============

@router.post("/{plan_id}/quote-sends/{log_id}/signature-link")
async def create_signature_link(plan_id: str, log_id: str, user=Depends(current_user)):
    """Génère un lien public unique pour que le client signe le devis."""
    log = await db.quote_sends.find_one(
        {"log_id": log_id, "plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not log:
        raise HTTPException(404, "Envoi de devis introuvable")
    token = SIG_TOKEN_PREFIX + secrets.token_urlsafe(18)
    await db.quote_sends.update_one(
        {"log_id": log_id},
        {"$set": {"signature_token": token, "signature_token_created_at": _now()}}
    )
    frontend_url = os.getenv("FRONTEND_URL") or ""
    return {"ok": True, "token": token,
            "url": f"{frontend_url}/sign/{token}" if frontend_url else f"/sign/{token}"}


@quote_router.get("/public/sign/{token}")
async def get_signature_page_data(token: str):
    """Endpoint public : récupère le résumé du devis à signer (sans exposer les données du sender)."""
    log = await db.quote_sends.find_one(
        {"signature_token": token},
        {"_id": 0, "plan_id": 1, "user_id": 1, "client_email": 1, "client_name": 1,
         "total_ttc": 1, "finish": 1, "floor_material": 1, "log_id": 1,
         "signed": 1, "signed_at": 1}
    )
    if not log:
        raise HTTPException(404, "Lien invalide ou expiré")
    branding = await _resolve_branding(log["user_id"]) or {}
    return {
        "log_id": log["log_id"], "plan_id": log["plan_id"],
        "client_email": log.get("client_email"), "client_name": log.get("client_name"),
        "total_ttc": log.get("total_ttc"),
        "finish": log.get("finish"), "floor_material": log.get("floor_material"),
        "signed": bool(log.get("signed")),
        "signed_at": log.get("signed_at"),
        "company_name": branding.get("company_name"),
        "contact_line": branding.get("contact_line"),
    }


class SignatureIn(BaseModel):
    signature_b64: str = Field(min_length=100, max_length=200_000)
    signer_name: str = Field(min_length=2, max_length=120)


@quote_router.post("/public/sign/{token}")
async def submit_signature(token: str, body: SignatureIn):
    """Endpoint public : le client soumet sa signature (image base64)."""
    log = await db.quote_sends.find_one({"signature_token": token},
                                          {"_id": 0, "log_id": 1, "user_id": 1,
                                           "signed": 1, "client_email": 1,
                                           "plan_id": 1, "client_name": 1,
                                           "total_ttc": 1})
    if not log:
        raise HTTPException(404, "Lien invalide")
    if log.get("signed"):
        raise HTTPException(400, "Ce devis a déjà été signé")
    b64_clean = body.signature_b64.split(",")[-1]
    signer = body.signer_name.strip()[:120]
    await db.quote_sends.update_one(
        {"log_id": log["log_id"]},
        {"$set": {"signed": True, "signed_at": _now(),
                   "signer_name": signer,
                   "signature_b64": b64_clean}}
    )
    # Notification in-app (bell)
    client_email = log.get("client_email") or ""
    await db.notifications.insert_one({
        "notif_id": "n_" + secrets.token_hex(5),
        "user_id": log["user_id"], "type": "quote_signed", "log_id": log["log_id"],
        "message": f"{signer} a signé le devis ({client_email}).",
        "created_at": _now(), "read": False,
    })
    # Push notification (best-effort)
    try:
        from routes.phase7 import notify_user
        total = log.get("total_ttc") or 0
        title = "✍️ Devis signé !"
        push_body = f"{signer} vient de signer votre devis" + (f" ({int(total):,} € TTC)".replace(",", " ") if total else "")
        await notify_user(log["user_id"], title, push_body, "/devis")
    except Exception as e:
        logger.warning(f"Push signature notify failed: {e}")
    # Email au pro (best-effort)
    try:
        from engines import emailer
        pro = await db.users.find_one({"user_id": log["user_id"]}, {"_id": 0, "email": 1, "name": 1})
        if pro and pro.get("email"):
            html = (
                f"<div style='font-family:system-ui,sans-serif;max-width:560px;margin:0 auto;padding:24px'>"
                f"<div style='background:hsl(24,96%,55%);color:white;padding:20px;border-radius:6px 6px 0 0'>"
                f"<h1 style='margin:0;font-size:22px'>✍️ Devis signé</h1></div>"
                f"<div style='border:1px solid #eee;border-top:none;padding:24px;border-radius:0 0 6px 6px'>"
                f"<p>Bonjour {pro.get('name') or ''},</p>"
                f"<p><strong>{signer}</strong> vient de signer votre devis"
                + (f" — <strong>{int(log.get('total_ttc', 0)):,} € TTC</strong>".replace(",", " ")
                   if log.get('total_ttc') else "")
                + f".</p>"
                f"<p>Client : <em>{client_email}</em><br/>"
                f"Date : {_now()[:10]}</p>"
                f"<p style='margin-top:24px'>"
                f"<a href='https://construpilot.fr/devis' "
                f"style='background:hsl(24,96%,55%);color:white;padding:12px 24px;"
                f"text-decoration:none;border-radius:4px;font-weight:600;display:inline-block'>"
                f"Voir le devis signé</a></p>"
                f"<p style='margin-top:32px;color:#888;font-size:12px'>"
                f"ConstruPilot · Estimez. Comparez. Construisez.</p>"
                f"</div></div>"
            )
            await emailer.send_email(pro["email"], f"✍️ {signer} a signé votre devis", html)
    except Exception as e:
        logger.warning(f"Email signature notify failed: {e}")
    return {"ok": True, "signed_at": _now()}


@quote_router.get("/public/sign/{token}/pdf")
async def get_signed_quote_pdf(token: str):
    """Renvoie le PDF Devis avec le bloc signature intégré."""
    from fastapi.responses import Response
    from engines.pdf_takeoff import build_quote_pdf
    log = await db.quote_sends.find_one({"signature_token": token}, {"_id": 0})
    if not log:
        raise HTTPException(404, "Lien invalide")
    plan_id = log["plan_id"]
    user_id = log["user_id"]

    quote, _pdf = await _build_quote_and_pdf(
        plan_id, user_id, log.get("finish", "std"),
        log.get("floor_material", "carrelage"),
        True, True, True, True,
    )
    branding = await _resolve_branding(user_id)
    signature = None
    if log.get("signed"):
        signature = {"b64": log.get("signature_b64"),
                     "name": log.get("signer_name"),
                     "at": log.get("signed_at"),
                     "client_email": log.get("client_email")}
    pdf_bytes = build_quote_pdf(quote, branding=branding, signature=signature)
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="devis-signe-{plan_id}.pdf"'}
    )
