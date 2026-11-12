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


FAST_ENGINES = "emergent,gemini_image3_pro,gpt_image_2,gen4_image"  # como na conta CLT: Nano Banana primeiro (~15 s)
UPGRADE_ENGINES = "openai"                                          # depois, em segundo plano: OpenAI GPT Image (melhor, mais lento)


def _engines(var: str, default: str) -> list[str]:
    import os
    return [m.strip() for m in (os.environ.get(var) or default).split(",") if m.strip()]


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


async def _pass(base: dict[str, bytes], verifier, engines: list[str], timeout: float, style: bytes | None = None,
                only: list[str] | None = None) -> dict[str, tuple[bytes, str]]:
    """Uma passagem de fotos: a principal primeiro, as outras em paralelo alinhadas nela. Só entram fotos verificadas."""
    from engines import photoreal as PR
    out: dict[str, tuple[bytes, str]] = {}
    keys = only or list(base)
    if "main" in keys:
        r = await PR.render(base["main"], PHOTO_PROMPT, feature="quote_house_render", session_id="quote_house",
                            engines=engines, verify=verifier("main"), timeout=timeout)
        if r:
            out["main"] = r
            style = r[0]
    if style is None:
        return out
    others = [k for k in keys if k != "main"]
    res = await asyncio.gather(*((PR.render(base[k], CUT_PROMPT, feature="quote_house_render", session_id="quote_house",
                                            engines=engines, verify=verifier(k), timeout=timeout)
                                  if k.startswith("cut_") else
                                  PR.render(base[k], PHOTO_PROMPT + VIEW_HINT.get(k, "") + MATCH_HINT, style_ref=style,
                                            feature="quote_house_render", session_id="quote_house", engines=engines,
                                            verify=verifier(k), timeout=timeout)) for k in others), return_exceptions=True)
    for k, r in zip(others, res):
        if isinstance(r, tuple) and r:
            out[k] = r
    return out


async def _save(db, key: str, base: dict[str, bytes], got: dict, quality: str, previous: dict | None = None) -> dict:
    views_ = dict(previous or {k: v for k, v in base.items()})
    for k, (img, _eng) in got.items():
        views_[k] = _jpeg(img)
    await db.house_renders.update_one({"key": key}, {"$set": {
        "key": key, "photoreal": True, "geometry_checked": True, "quality": quality,
        "engine": (got.get("main") or (None, ""))[1] or quality, "updated_at": datetime.now(timezone.utc).isoformat(),
        "views": {k: base64.b64encode(v).decode() for k, v in views_.items()}}}, upsert=True)
    return views_


async def _photoreal_all(db, key: str, base: dict[str, bytes], masks: dict[str, bytes] | None = None, raw: dict | None = None) -> None:
    """Como na conta CLT: passagem RÁPIDA (Nano Banana primeiro) para o PDF não esperar; depois, em segundo plano,
    melhoria OpenAI GPT Image — cada foto só substitui a anterior se também respeitar a geometria. Em qualquer fase,
    uma vista sem foto verificada fica com a vista calculada (geometria exata), nunca uma casa diferente."""
    import os
    from engines import geometry_lock as G
    from engines import llm_keys
    masks = masks or {}

    def verifier(k):
        m = masks.get(k) or G.mask_from_render(base[k])
        return lambda img: G.check(img, base[k], m)
    try:
        # 1) Renderização FÍSICA da geometria real (Mitsuba: sol, céu, materiais) — sem IA, geometria exata por construção
        if raw is not None:
            from engines import house_pbr
            if house_pbr.available():
                got_pbr = {}
                for k in VIEW_KEYS:
                    png = await asyncio.to_thread(house_pbr.render, raw, int(os.environ.get("QUOTE_PBR_W") or 2560), int(os.environ.get("QUOTE_PBR_H") or 1440), k, int(os.environ.get("QUOTE_PBR_SPP") or 128))
                    if png:
                        got_pbr[k] = (png, "pbr_mitsuba")
                        if k == "main":
                            await _save(db, key, base, got_pbr, "pbr")       # a vista principal fica logo disponível
                if got_pbr.get("main"):
                    await _save(db, key, base, got_pbr, "pbr")
                    log.info("house renders %s: physical render %s/%d", key[:10], len(got_pbr), len(VIEW_KEYS))
                    if str(os.environ.get("QUOTE_PHOTO_AI") or "").lower() not in ("1", "true", "yes"):
                        return                                            # sem IA (pedido do Martinho): imagens reais calculadas
        fast_t = float(os.environ.get("QUOTE_PHOTO_FAST_TIMEOUT") or 60)
        got = await _pass(base, verifier, _engines("QUOTE_PHOTO_FAST", FAST_ENGINES), fast_t)
        current = await _save(db, key, base, got, "fast") if got.get("main") else None
        log.info("house renders %s: fast %s/%d", key[:10], len(got), len(base))
        up = _engines("QUOTE_PHOTO_UPGRADE", UPGRADE_ENGINES)
        if "openai" in up and not llm_keys.openai_direct_active():
            up = [e for e in up if e != "openai"]
        if up:
            better = await _pass(base, verifier, up, float(os.environ.get("QUOTE_PHOTO_UPGRADE_TIMEOUT") or 240),
                                 style=None)
            if better.get("main"):
                await _save(db, key, base, better, "openai", previous=current)
                log.info("house renders %s: upgraded %s/%d", key[:10], len(better), len(base))
        if not got.get("main"):
            log.info("house renders %s: no fast photo respected the geometry — computed views kept", key[:10])
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
        task = asyncio.get_running_loop().create_task(_photoreal_all(db, key, base, masks, raw))
        # espera só pela passagem RÁPIDA (como na conta CLT); a melhoria OpenAI continua em segundo plano
        loop = asyncio.get_running_loop()
        end = loop.time() + max(0.0, wait)
        while loop.time() < end and not task.done():
            await asyncio.sleep(min(1.0, max(0.05, end - loop.time())))
            try:
                hit = await db.house_renders.find_one({"key": key}, {"_id": 0})
            except Exception:  # noqa: BLE001
                hit = None
            if hit and hit.get("views"):
                return {k: base64.b64decode(v) for k, v in hit["views"].items()}
        if wait > 0 and task.done():
            hit = await db.house_renders.find_one({"key": key}, {"_id": 0})
            if hit and hit.get("views"):
                return {k: base64.b64decode(v) for k, v in hit["views"].items()}
    return base                                     # tempo esgotado: vistas calculadas (geometria exata) agora


PLAN_HINT = ("plan", "planta", "plantas", "pc", "permis", "projet", "projeto", "alçado", "alcado", "façade", "facade", "corte", "coupe",
             "arquitet", "architect", "rdc", "r+1", "piso", "étage", "etage", "implant")


async def _conversation_doc_ids(db, doc: dict, uid: str) -> list[str]:
    ids: list[str] = []
    conv = doc.get("assistant_conversation_id")
    if conv:
        try:
            async for m in db.assistant_msgs.find({"conversation_id": conv, "user_id": uid, "role": "user"},
                                                  {"_id": 0, "attachments": 1}).sort("created_at", 1).limit(80):
                for a in m.get("attachments") or []:
                    if a.get("doc_id") and a["doc_id"] not in ids:
                        ids.append(a["doc_id"])
            c = await db.assistant_convs.find_one({"conversation_id": conv, "user_id": uid}, {"_id": 0, "active_docs": 1}) or {}
            for d in c.get("active_docs") or []:
                if d not in ids:
                    ids.append(d)
        except Exception:  # noqa: BLE001
            log.warning("quote plan docs lookup failed", exc_info=True)
    for d in _ids_in(doc):
        if d not in ids:
            ids.append(d)
    return ids[:12]


async def _doc_bytes(db, d: dict) -> bytes | None:
    if d.get("data_b64"):
        return base64.b64decode(d["data_b64"])
    if d.get("chunk_count"):
        chunks = [c async for c in db.assistant_doc_chunks.find({"doc_id": d["doc_id"], "user_id": d.get("user_id")},
                                                                {"_id": 0}).sort("index", 1)]
        if [c["index"] for c in chunks] == list(range(d["chunk_count"])):
            return b"".join(base64.b64decode(c["data_b64"]) for c in chunks)
    return None


def _render_pages(data: bytes, mime: str, max_pages: int) -> list[bytes]:
    """Páginas das plantas em JPEG (PDF: cada página; imagem: a própria imagem)."""
    out: list[bytes] = []
    if (mime or "").startswith("image/"):
        out.append(_jpeg(data, 2000))
        return out
    import pymupdf
    pdf = pymupdf.open(stream=data, filetype="pdf")
    for i, pg in enumerate(pdf):
        if i >= max_pages:
            break
        r = pg.rect
        zoom = min(2.6, 2200 / max(r.width, r.height))
        out.append(_jpeg(pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png"), 2200))
    return out


async def plan_images(db, doc: dict, uid: str, max_pages: int = 8) -> list[tuple[str, bytes]]:
    """Plantas juntas na conversa do Assistente (ou citadas no orçamento): as páginas entram no PDF do orçamento
    (capa + « Plantas do projeto ») mesmo sem Estudo BET."""
    imgs: list[tuple[str, bytes]] = []
    try:
        ids = await _conversation_doc_ids(db, doc, uid)
        if not ids:
            return []
        me = await db.users.find_one({"user_id": uid}, {"_id": 0, "organization_id": 1}) or {}
        scope = [{"user_id": uid}] + ([{"organization_id": me["organization_id"]}] if me.get("organization_id") else [])
        docs = [d async for d in db.assistant_docs.find({"doc_id": {"$in": ids}, "$or": scope}, {"_id": 0, "text": 0})]
        docs.sort(key=lambda d: ids.index(d["doc_id"]))

        def is_plan(d):
            name = (d.get("filename") or "").lower()
            return d.get("kind") == "plan" or any(h in name for h in PLAN_HINT)
        visual = [d for d in docs if (d.get("mime") or "").startswith("image/") or (d.get("mime") or "").endswith("pdf")
                  or (d.get("filename") or "").lower().endswith(".pdf")]
        chosen = [d for d in visual if is_plan(d)] or visual          # sem nome « planta »: todos os PDF / imagens juntos
        for d in chosen:
            if len(imgs) >= max_pages:
                break
            data = await _doc_bytes(db, d)
            if not data:
                continue
            pages = await asyncio.to_thread(_render_pages, data, d.get("mime") or "application/pdf", max_pages - len(imgs))
            for i, im in enumerate(pages):
                imgs.append((f"{d.get('filename') or 'Planta'}" + (f" — p. {i + 1}" if len(pages) > 1 else ""), im))
        # plantas do módulo Plantas (plan_…) ativas na conversa ou citadas no orçamento: imagens das páginas já calculadas
        if len(imgs) < max_pages:
            plan_ids: list[str] = []
            conv = doc.get("assistant_conversation_id")
            if conv:
                c = await db.assistant_convs.find_one({"conversation_id": conv, "user_id": uid}, {"_id": 0, "active_plans": 1}) or {}
                plan_ids += [x for x in c.get("active_plans") or [] if x not in plan_ids]
            txt = json.dumps([doc.get("lines"), doc.get("title"), doc.get("notes")], ensure_ascii=False)
            plan_ids += [x for x in re.findall(r"plan_[0-9a-f]{6,}", txt) if x not in plan_ids]
            for pid in plan_ids[:4]:
                p = await db.plans_takeoff.find_one({"plan_id": pid, "user_id": uid},
                                                    {"_id": 0, "filename": 1, "pages.image_png_b64": 1}) or {}
                for i, pg in enumerate(p.get("pages") or []):
                    if len(imgs) >= max_pages:
                        break
                    if pg.get("image_png_b64"):
                        imgs.append((f"{p.get('filename') or 'Planta'} — p. {i + 1}", _jpeg(base64.b64decode(pg["image_png_b64"]), 2200)))
    except Exception:  # noqa: BLE001 — as plantas embelezam, nunca bloqueiam o orçamento
        log.warning("quote plan images failed", exc_info=True)
    return imgs


async def enrich(db, doc: dict, uid: str, wait: float = 0) -> dict:
    """Cópia do orçamento com o modelo do edifício e as vistas 3D (para pdf_docs / pdf_premium)."""
    if (doc or {}).get("doc_type") != "quote":
        return doc
    raw = await model_for_quote(db, doc, uid)
    plans = await plan_images(db, doc, uid)
    if not raw:
        if plans:                                   # sem Estudo BET: as plantas da conversa entram na capa e no PDF
            return {**doc, "_plan_images": plans, "_house_views": {"main": plans[0][1]}}
        return doc
    try:
        v = await views(db, raw, wait)
    except Exception:  # noqa: BLE001
        log.warning("house views failed", exc_info=True)
        v = {}
    return {**doc, "_building_model": raw, "_house_views": v, **({"_plan_images": plans} if plans else {})}
