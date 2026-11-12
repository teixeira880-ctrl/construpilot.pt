"""Moradia do orçamento: modelo do edifício (lido nas plantas pelo Estudo BET), vistas 3D com a geometria REAL e
versão fotorrealista — o mesmo circuito que a conta CLT (render calculado → fotorrealismo GPT Image 2 / Nano Banana /
Runway com a geometria bloqueada), agora para todas as contas.

  model_for_quote(db, doc, uid)  → modelo bet_core do mesmo processo (conversa) ou dos mesmos documentos ;
  views(db, raw, uid, wait)      → {vista: JPEG}: fotorrealistas em cache, senão as vistas calculadas (instantâneas)
                                   e o fotorrealismo é lançado em segundo plano (uma vez por geometria) ;
  enrich(db, doc, uid, wait)     → cópia do orçamento com _building_model e _house_views para o PDF.
Nunca bloqueia: sem modelo, o orçamento sai como antes.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger("quote_building")

VIEW_KEYS = ("main", "side", "rear", "aerial")
_PENDING: set[str] = set()

PHOTO_PROMPT = (
    "Turn this into a real photograph of the finished house — indistinguishable from a professional real-estate photo taken "
    "with a full-frame camera and a 24 mm tilt-shift lens, natural late-afternoon sun, true-to-life exposure and colour. "
    "STRICT GEOMETRY: this is the exact building; keep the same footprint, proportions, number of storeys, roof shape, pitch and "
    "overhang, and every window and door at exactly the same position, size and count; keep the same camera position, "
    "framing and perspective so the photo overlays the input pixel for pixel. Do not add or remove storeys, wings, balconies, "
    "dormers, chimneys, windows or doors. Real materials: finely textured rendered masonry walls in warm off-white with "
    "subtle weathering, real clay roof tiles with individual tiles and ridge caps (or a flat roof with parapet and coping if "
    "shown), slim anthracite aluminium frames with reflective double glazing showing sky and interior depth, stone sills, "
    "concrete or stone paving, a planted garden with mown lawn, shrubs and mature trees kept beside — never in front of — the "
    "facades, soft contact shadows and ambient occlusion. No CGI look, no plastic surfaces, no text, no watermark, no people.")
VIEW_HINT = {"side": " Side perspective of the same house.", "rear": " Rear perspective of the same house.",
             "aerial": " Elevated drone photograph of the same house."}
MATCH_HINT = " Keep exactly the same materials, colours, garden and light as @style."


def _ids_in(doc: dict) -> set[str]:
    txt = json.dumps([doc.get("lines"), doc.get("title"), doc.get("notes")], ensure_ascii=False)
    return set(re.findall(r"doc_[0-9a-f]{8,}", txt))


async def model_for_quote(db, doc: dict, uid: str) -> dict | None:
    if isinstance(doc.get("building_model"), dict):
        return doc["building_model"]
    try:
        proj = {"_id": 0, "model": 1, "created_at": 1}
        conv = doc.get("assistant_conversation_id")
        if conv:
            j = await db.bet_study_jobs.find_one({"user_id": uid, "conversation_id": conv, "model": {"$type": "object"}}, proj,
                                                 sort=[("created_at", -1)])
            if j and j.get("model"):
                return j["model"]
        ids = list(_ids_in(doc))
        if ids:
            j = await db.bet_study_jobs.find_one({"user_id": uid, "document_ids": {"$in": ids}, "model": {"$type": "object"}}, proj,
                                                 sort=[("created_at", -1)])
            if j and j.get("model"):
                return j["model"]
    except Exception:  # noqa: BLE001
        log.warning("quote building model lookup failed", exc_info=True)
    return None


def geometry_key(raw: dict) -> str:
    g = {k: raw.get(k) for k in ("envelope", "sides", "levels", "roof", "openings")}
    return hashlib.sha1(json.dumps(g, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _jpeg(png: bytes, side: int = 1600) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.thumbnail((side, side), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=86)
    return b.getvalue()


CUT_PROMPT = (
    "Real-photo-quality 3D floor-plan cutaway of this exact floor (keep every wall exactly where it is, same thicknesses, "
    "same openings, same camera so it overlays the input pixel for pixel): same walls, same rooms, same wall thicknesses, door and "
    "window positions and the same camera angle; walls cut at the same height, warm oak floors, light furniture suggesting "
    "each room's use (sofa in the living room, kitchen units in the kitchen, beds in bedrooms, sanitary ware in bathrooms), "
    "soft daylight, clean white background, high-end architectural presentation. Do not move, add or remove walls; no text.")


QUOTE_ENGINES = "openai,gpt_image_2,gemini_image3_pro,emergent"   # OpenAI primeiro; QUOTE_PHOTOREAL_MODELS altera


def _engines() -> list[str]:
    import os
    return [m.strip() for m in (os.environ.get("QUOTE_PHOTOREAL_MODELS") or QUOTE_ENGINES).split(",") if m.strip()]


def computed_masks(raw: dict) -> dict[str, bytes]:
    """Máscaras de geometria (mesma câmara que as vistas) para verificar as fotos (engines.geometry_lock)."""
    from engines import house3d
    return {k: house3d.render_png(raw, 1600, 900, k, mask=True) for k in VIEW_KEYS}


def computed_views(raw: dict) -> dict[str, bytes]:
    from engines import house3d
    out = {k: _jpeg(house3d.render_png(raw, 1600, 900, k)) for k in VIEW_KEYS}
    for i, f in enumerate(house3d.takeoff(raw)):
        if not f.get("error"):
            out[f"cut_{i}"] = _jpeg(house3d.cutaway_png(raw, f, 1600, 1000))
    return out


async def _photoreal_all(db, key: str, base: dict[str, bytes], masks: dict[str, bytes] | None = None) -> None:
    """Fotos ao nível OpenAI, mas só aceites se respeitarem a geometria calculada (alinhamento + verificação das arestas
    de paredes, cobertura e vãos). Vista recusada por todos os motores → fica a vista calculada (nunca uma casa diferente)."""
    from engines import geometry_lock as G
    from engines import photoreal as PR
    masks = masks or {}

    def verifier(k):
        m = masks.get(k) or G.mask_from_render(base[k])
        return lambda img: G.check(img, base[k], m)
    try:
        eng = _engines()
        main = await PR.render(base["main"], PHOTO_PROMPT, feature="quote_house_render", session_id="quote_house",
                               engines=eng, verify=verifier("main"))
        if not main:
            log.info("house renders %s: no engine respected the geometry — computed views kept", key[:10])
            return
        out = {"main": _jpeg(main[0])}
        others = [k for k in base if k != "main"]
        res = await asyncio.gather(*((PR.render(base[k], CUT_PROMPT, feature="quote_house_render", session_id="quote_house",
                                                engines=eng, verify=verifier(k))
                                      if k.startswith("cut_") else
                                      PR.render(base[k], PHOTO_PROMPT + VIEW_HINT.get(k, "") + MATCH_HINT, style_ref=main[0],
                                                feature="quote_house_render", session_id="quote_house", engines=eng,
                                                verify=verifier(k))) for k in others),
                                   return_exceptions=True)
        for k, r in zip(others, res):
            out[k] = _jpeg(r[0]) if isinstance(r, tuple) and r else base[k]
        await db.house_renders.update_one({"key": key}, {"$set": {
            "key": key, "photoreal": True, "engine": main[1], "geometry_checked": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "views": {k: base64.b64encode(v).decode() for k, v in out.items()}}}, upsert=True)
        log.info("house renders %s: photoreal %s", key[:10], main[1])
    except Exception:  # noqa: BLE001 — o fotorrealismo embeleza, nunca bloqueia
        log.warning("house photoreal failed", exc_info=True)
    finally:
        _PENDING.discard(key)


async def views(db, raw: dict, wait: float = 0) -> dict[str, bytes]:
    key = geometry_key(raw)
    try:
        hit = await db.house_renders.find_one({"key": key}, {"_id": 0})
    except Exception:  # noqa: BLE001
        hit = None
    if hit and hit.get("photoreal") and hit.get("geometry_checked") and hit.get("views"):
        return {k: base64.b64decode(v) for k, v in hit["views"].items()}
    base = await asyncio.to_thread(computed_views, raw)
    masks = await asyncio.to_thread(computed_masks, raw)
    if key not in _PENDING:
        _PENDING.add(key)
        task = asyncio.get_running_loop().create_task(_photoreal_all(db, key, base, masks))
        if wait > 0:
            try:
                await asyncio.wait_for(asyncio.shield(task), wait)
                hit = await db.house_renders.find_one({"key": key}, {"_id": 0})
                if hit and hit.get("views"):
                    return {k: base64.b64decode(v) for k, v in hit["views"].items()}
            except Exception:  # noqa: BLE001 — tempo esgotado: vistas calculadas agora, fotos na próxima vez
                pass
    return base


async def enrich(db, doc: dict, uid: str, wait: float = 0) -> dict:
    """Cópia do orçamento com o modelo do edifício e as vistas 3D (para pdf_docs / pdf_premium)."""
    if (doc or {}).get("doc_type") != "quote":
        return doc
    raw = await model_for_quote(db, doc, uid)
    if not raw:
        return doc
    try:
        v = await views(db, raw, wait)
    except Exception:  # noqa: BLE001
        log.warning("house views failed", exc_info=True)
        v = {}
    return {**doc, "_building_model": raw, "_house_views": v}
