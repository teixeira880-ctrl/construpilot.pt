"""3D render (Nano Banana / Gemini image-to-image) + Video tour MP4.

Refactor iter53 : extrait de `routes/plans.py`.
"""
from __future__ import annotations

import logging
import os
import secrets

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines.monetization import require_3d_access, consume_3d, user_tier

from routes.plans_common import _now, _resolve_branding, router

logger = logging.getLogger(__name__)


class Render3DIn(BaseModel):
    page_index: int = 0
    style: str = "photoreal"  # photoreal | isometric | axonometric | interior
    include_furniture: bool = True
    extra_prompt: str | None = None


_STYLE_PROMPTS = {
    "photoreal": "photorealistic 3D DOLLHOUSE render (roof removed) seen from a high "
                  "35° bird's-eye angle, every wall extruded vertically with real "
                  "thickness, realistic materials (wood floor, painted walls, ceramic "
                  "tiles), natural daylight, soft shadows, clear depth and perspective",
    "isometric": "clean ISOMETRIC 3D dollhouse rendering (roof removed), ~35° bird's-eye "
                  "angle, walls extruded vertically with visible thickness, colored floors "
                  "per room type, soft ambient occlusion shadows, architectural model look",
    "axonometric": "axonometric 3D CUTAWAY render showing extruded walls in section, "
                    "colored floor tiles per room, white walls with real height, cool "
                    "ambient lighting, strong sense of volume and depth",
    "interior": "photorealistic interior 3D view of the largest living room in this "
                 "floor plan, modern French residential style, warm daylight through "
                 "windows, natural materials, real perspective",
}


def _room_context_hint(rooms: list[dict]) -> str:
    """Compile room labels + measured openings hint for the render prompt."""
    if not rooms:
        return ""
    labels = ", ".join(sorted({r.get("name", "") for r in rooms if r.get("name")}))
    hint = f"\nDetected room labels: {labels}." if labels else ""
    ops_parts: list[str] = []
    for r in rooms:
        ops = r.get("openings") or []
        if not ops:
            continue
        parts = [f"{op.get('count', 1)}× {op.get('kind', 'opening')} "
                 f"{op.get('width_m')}×{op.get('height_m')}m"
                 for op in ops[:5]]
        if parts:
            ops_parts.append(f"{r.get('name', 'room')}: " + ", ".join(parts))
    if ops_parts:
        hint += "\nRoom openings measured: " + " | ".join(ops_parts)
    return hint


def _ai_context_hint(ai: dict) -> str:
    """Compile the AI gros œuvre context (facades, stairs, openings, floors)."""
    bits: list[str] = []
    facades = ai.get("facade_walls") or []
    if facades:
        parts = [f"{f.get('orientation') or '?'} facade "
                 f"({f.get('wall_type') or '?'} {f.get('material_guess') or '?'} wall)"
                 for f in facades[:6]]
        bits.append("Facades: " + ", ".join(parts))
    stairs = ai.get("stairwells") or []
    if stairs:
        parts = [f"{s.get('type') or 'straight'} staircase {s.get('steps') or '?'} steps "
                 f"{' to '.join(s.get('connects_levels') or [])}" for s in stairs[:3]]
        bits.append("Stairs: " + "; ".join(parts))
    op = ai.get("openings") or {}
    if op.get("doors_visible") or op.get("windows_visible") or op.get("bays_visible"):
        bits.append(
            f"Openings: {op.get('doors_visible', 0)} doors, "
            f"{op.get('windows_visible', 0)} windows, {op.get('bays_visible', 0)} bay windows"
        )
    floors = ai.get("floors") or {}
    if floors.get("floor_type"):
        bits.append(f"Floor structure: {floors['floor_type']} "
                    f"(slab {floors.get('slab_thickness_m', 0.2)}m thick)")
    return ("\nDetailed gros-œuvre context (respect exactly): " + " · ".join(bits)) if bits else ""


def _build_render_prompt(style: str, include_furniture: bool, rooms: list[dict],
                         ai_analysis: dict, extra_prompt: str | None) -> str:
    style_prompt = _STYLE_PROMPTS.get(style, _STYLE_PROMPTS["photoreal"])
    furniture = "Add simple realistic furniture per room." if include_furniture else "Leave rooms empty (no furniture)."
    extra = f"\nAdditional instructions: {extra_prompt}" if extra_prompt else ""
    return (
        f"Transform this 2D architectural floor plan into a {style_prompt}.\n"
        f"CRITICAL — the output MUST be clearly THREE-DIMENSIONAL with depth, height, "
        f"perspective and shadows. Extrude every wall vertically to a realistic ~2.7 m "
        f"ceiling height with visible thickness; add floor slabs. Show it as a dollhouse / "
        f"cutaway (roof removed) viewed from above at an angle. NEVER output a flat "
        f"top-down 2D line drawing — if the result looks like the original plan, it is wrong.\n"
        f"IGNORE and DO NOT reproduce any of these 2D-drawing elements: dimension lines and "
        f"measurement numbers, text labels and room-area annotations (m²), hatching/filling "
        f"patterns, the north arrow, the title block, surrounding site/garden/tree drawings, "
        f"and any red/pink/colored annotation lines. Reproduce ONLY the building itself "
        f"(walls, doors, windows, stairs) as real 3D geometry — preserve the room layout and "
        f"wall positions EXACTLY, do not invent or remove rooms. {furniture}"
        f"{_room_context_hint(rooms)}{_ai_context_hint(ai_analysis or {})}{extra}"
    )


async def _gemini_render_3d(*, plan_id: str, page_index: int, page_img_b64: str,
                             rooms: list, style: str, include_furniture: bool,
                             ai_analysis: dict | None = None,
                             extra_prompt: str | None = None) -> tuple[str, str, str]:
    """Core Gemini Nano Banana call — returns (b64_out, mime, prompt_used)."""
    from emergentintegrations.llm.chat import ImageContent, UserMessage

    from engines.expenses.metering import MeteredChat as LlmChat

    api_key = os.getenv("EMERGENT_LLM_KEY")
    if not api_key:
        raise HTTPException(500, "EMERGENT_LLM_KEY manquant")

    prompt = _build_render_prompt(style, include_furniture, rooms,
                                    ai_analysis or {}, extra_prompt)
    try:
        chat = (LlmChat(api_key=api_key, expense_feature="plan_3d_image",
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


@router.post("/{plan_id}/render-3d")
async def render_3d(plan_id: str, body: Render3DIn, user=Depends(current_user)) -> dict:
    """Convertit la page du plan 2D en rendu 3D via Gemini Nano Banana."""
    mode = await require_3d_access(user, "render")
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
        "render_id": render_id, "plan_id": plan_id, "user_id": user["user_id"],
        "style": body.style,
        "include_furniture": body.include_furniture,
        "page_index": body.page_index,
        "created_at": _now(),
        "image_b64": generated_b64, "mime_type": mime,
        "prompt": prompt[:800],
    }
    # Collection dédiée (les images base64 embarquées dans plans_takeoff
    # faisaient exploser la limite BSON de 16 Mo). On garde les 10 derniers.
    await db.plan_renders_3d.insert_one(render_doc)
    old = await (db.plan_renders_3d
                 .find({"plan_id": plan_id}, {"_id": 1})
                 .sort("created_at", -1).skip(10).to_list(50))
    if old:
        await db.plan_renders_3d.delete_many({"_id": {"$in": [o["_id"] for o in old]}})
    await consume_3d(user["user_id"], "render", mode)
    return {"ok": True, "render_id": render_id, "style": body.style,
            "mime_type": mime, "image_b64": generated_b64,
            "prompt_used": prompt[:400]}


@router.get("/{plan_id}/renders-3d")
async def list_renders_3d(plan_id: str, user=Depends(current_user)) -> dict:
    """Liste les rendus 3D (meta uniquement, sans image_b64 lourd)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    renders = await (db.plan_renders_3d
                     .find({"plan_id": plan_id}, {"_id": 0, "image_b64": 0, "prompt": 0})
                     .sort("created_at", 1).to_list(20))
    return {"plan_id": plan_id, "renders": [
        {"render_id": r.get("render_id"), "style": r.get("style"),
         "page_index": r.get("page_index"), "created_at": r.get("created_at"),
         "include_furniture": r.get("include_furniture")}
        for r in renders
    ]}


@router.get("/{plan_id}/renders-3d/{render_id}")
async def get_render_3d(plan_id: str, render_id: str, user=Depends(current_user)) -> dict:
    """Récupère l'image d'un rendu 3D précédemment généré."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    r = await db.plan_renders_3d.find_one(
        {"plan_id": plan_id, "render_id": render_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Rendu 3D introuvable")
    return {"render_id": render_id, "style": r.get("style"),
            "mime_type": r.get("mime_type", "image/png"),
            "image_b64": r.get("image_b64"),
            "created_at": r.get("created_at")}


# ============ VIDEO TOUR 3D ============

class RenderVideoIn(BaseModel):
    page_index: int = 0
    include_furniture: bool = True
    styles: list[str] = Field(default_factory=lambda:
        ["isometric", "photoreal", "axonometric", "interior"])
    add_watermark: bool = True
    add_music: bool = True


def _validate_video_styles(styles: list[str]) -> None:
    if not styles or len(styles) < 2:
        raise HTTPException(400, "Au moins 2 styles requis pour un tour vidéo")
    if len(styles) > 6:
        raise HTTPException(400, "6 styles max par vidéo")
    unknown = [s for s in styles if s not in _STYLE_PROMPTS]
    if unknown:
        raise HTTPException(400, f"Style(s) inconnu(s) : {', '.join(unknown)}")


async def _load_watermark_bytes(user_id: str) -> bytes | None:
    import base64 as _b64
    branding = await _resolve_branding(user_id) or {}
    logo_b64 = branding.get("logo_b64")
    if not logo_b64:
        return None
    try:
        return _b64.b64decode(logo_b64)
    except Exception as e:
        logger.warning(f"invalid brand logo b64: {e}")
        return None


@router.post("/{plan_id}/render-video")
async def render_video_tour(plan_id: str, body: RenderVideoIn, user=Depends(current_user)) -> dict:
    """Génère plusieurs rendus IA du plan avec différents styles et les assemble
    en un tour vidéo MP4 (Ken Burns + crossfade + filigrane + musique).
    """
    mode = await require_3d_access(user, "video")
    from engines.video_tour import build_video_tour

    _validate_video_styles(body.styles)

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

    frames_b64: list[str] = []
    for style in body.styles:
        b64_out, _mime, _prompt = await _gemini_render_3d(
            plan_id=plan_id, page_index=body.page_index, page_img_b64=img_b64,
            rooms=rooms, ai_analysis=ai_analysis,
            style=style, include_furniture=body.include_furniture,
        )
        frames_b64.append(b64_out)

    logo_bytes = await _load_watermark_bytes(user["user_id"]) if body.add_watermark else None

    try:
        mp4_path, meta = build_video_tour(
            frames_b64, styles=body.styles,
            logo_bytes=logo_bytes, add_audio=body.add_music,
        )
    except Exception as e:
        logger.error(f"video_tour build failed: {type(e).__name__} {e}")
        raise HTTPException(502, f"Assemblage vidéo échoué : {type(e).__name__}") from e

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
    await consume_3d(user["user_id"], "video", mode)
    return {"ok": True, **{k: v for k, v in doc.items() if k != "_id"}}


@router.post("/{plan_id}/interactive-3d")
async def unlock_interactive_3d(plan_id: str, user=Depends(current_user)) -> dict:
    """Débloque la maquette 3D interactive pour ce plan (consomme 1 crédit maquette,
    illimité pour Pro/Pro Business/admin, ré-ouverture gratuite une fois débloquée)."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    if (user or {}).get("role") == "admin":
        return {"ok": True, "mode": "unlimited"}
    tier = await user_tier(user["user_id"])
    if tier in ("pro", "pro_business"):
        return {"ok": True, "mode": "unlimited"}
    existing = await db.interactive_unlocks.find_one(
        {"user_id": user["user_id"], "plan_id": plan_id})
    if existing:
        return {"ok": True, "mode": "already_unlocked"}
    mode = await require_3d_access(user, "mockup")
    await consume_3d(user["user_id"], "mockup", mode)
    await db.interactive_unlocks.insert_one(
        {"user_id": user["user_id"], "plan_id": plan_id, "at": _now()})
    return {"ok": True, "mode": mode}


@router.get("/{plan_id}/videos-3d")
async def list_videos_3d(plan_id: str, user=Depends(current_user)) -> dict:
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
