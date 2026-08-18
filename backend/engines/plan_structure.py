"""Détection IA de la STRUCTURE d'un plan 2D : murs + ouvertures (portes/fenêtres).

Contrairement à `plan_cv.detect_walls` (OpenCV Hough, bruité), ce moteur demande
au modèle vision de renvoyer directement les segments de murs NETS et les
ouvertures typées (porte / fenêtre / baie) avec leur position, pour un rendu
sémantique propre : murs = rouge, fenêtres = jaune, portes = violet.

Coordonnées renvoyées : NORMALISÉES 0-1 (converties en pixels par l'appelant).
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid

logger = logging.getLogger(__name__)

PROMPT = """Tu es un métreur / ingénieur structure expert. Analyse ce plan 2D (plan d'ARCHITECTE
d'habitation OU plan de COFFRAGE / structure béton) et extrais TOUTE la structure pour un
métré. Sois EXHAUSTIF : sur un plan de coffrage dense, il y a souvent de NOMBREUX poteaux,
poutres et dalles — liste-les TOUS. NE compte PAS les meubles, textes, cotes (traits de
mesure), légendes ni cartouche.

Rends STRICTEMENT du JSON (aucun markdown, aucun texte hors JSON) :

{
  "walls": [
    // Murs / VOILES / murs porteurs (traits pleins épais ou hachurés). Un mur = une ligne droite.
    // Décompose les murs longs en segments entre angles. Coordonnées normalisées 0-1.
    {"x1": 0.10, "y1": 0.12, "x2": 0.90, "y2": 0.12, "type": "porteur" | "cloison"}
  ],
  "columns": [
    // POTEAUX (plan de coffrage) : petits carrés/rectangles/cercles pleins, souvent répétés
    // sur une trame. Donne les DEUX coins opposés de l'emprise du poteau. Liste-les TOUS.
    {"x1": 0.20, "y1": 0.30, "x2": 0.23, "y2": 0.33}
  ],
  "beams": [
    // POUTRES / linteaux (souvent en pointillés, ou repères type "L20", "LN33"). Segment de la poutre.
    {"x1": 0.20, "y1": 0.40, "x2": 0.70, "y2": 0.40}
  ],
  "openings": [
    // Ouvertures dans les murs (plan d'habitation). Segment = largeur de l'ouverture SUR le mur.
    // kind : "porte" (arc de battement) | "fenetre" | "baie"
    {"kind": "porte" | "fenetre" | "baie",
     "x1": 0.30, "y1": 0.12, "x2": 0.40, "y2": 0.12,
     "swing": {"x": 0.40, "y": 0.20} | null}
  ],
  "floors": [
    // SURFACES DE SOL / DALLES (planchers) : un polygone fermé par pièce/panneau de dalle,
    // suivant l'intérieur des murs. 3 à 8 points (sens horaire). Coordonnées normalisées 0-1.
    {"name": "Séjour" | "Dalle" | ...,
     "points": [[0.12, 0.14], [0.48, 0.14], [0.48, 0.50], [0.12, 0.50]]}
  ],
  "plan_kind": "habitation" | "coffrage",
  "confidence": 0.0-1.0
}

RÈGLES :
- Murs extérieurs / refends épais / VOILES = "porteur". Cloisons fines = "cloison".
- Poteaux = petits éléments pleins isolés, souvent alignés en trame — liste-les TOUS même s'il y en a 20+.
- Poutres/linteaux : souvent pointillés ou repérés par un code. N'invente pas sans indice.
- Planchers/dalles : couvre TOUTE la surface bâtie (un ou plusieurs panneaux).
- Sur un plan de coffrage, il n'y a généralement PAS de portes/fenêtres → openings peut être vide.
- Sois précis sur les positions. Réponds UNIQUEMENT le JSON.
"""


def _parse_json(raw: str) -> dict:
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if not m:
            return {"walls": [], "openings": [], "error": "AI response not JSON"}
        try:
            return json.loads(m.group(0))
        except Exception as e:
            return {"walls": [], "openings": [], "error": f"JSON parse: {e}"}


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _norm_seg(o: dict) -> tuple[float, float, float, float] | None:
    try:
        return (_clamp(o["x1"]), _clamp(o["y1"]), _clamp(o["x2"]), _clamp(o["y2"]))
    except (KeyError, TypeError):
        return None


def _to_px(structure: dict, w: int, h: int) -> dict:
    """Convertit les coordonnées normalisées en pixels + ajoute des ids stables."""
    walls = []
    for wseg in structure.get("walls") or []:
        seg = _norm_seg(wseg) if isinstance(wseg, dict) else None
        if not seg:
            continue
        x1, y1, x2, y2 = seg
        wtype = wseg.get("type") if wseg.get("type") in ("porteur", "cloison") else "cloison"
        walls.append({
            "wall_id": "sw_" + uuid.uuid4().hex[:6],
            "x1": round(x1 * w), "y1": round(y1 * h),
            "x2": round(x2 * w), "y2": round(y2 * h),
            "type": wtype,
        })
    openings = []
    for op in structure.get("openings") or []:
        if not isinstance(op, dict):
            continue
        seg = _norm_seg(op)
        if not seg:
            continue
        x1, y1, x2, y2 = seg
        kind = op.get("kind") if op.get("kind") in ("porte", "fenetre", "baie") else "fenetre"
        swing = op.get("swing") if isinstance(op.get("swing"), dict) else None
        openings.append({
            "opening_id": "so_" + uuid.uuid4().hex[:6],
            "kind": kind,
            "x1": round(x1 * w), "y1": round(y1 * h),
            "x2": round(x2 * w), "y2": round(y2 * h),
            "swing": ({"x": round(_clamp(swing.get("x")) * w),
                       "y": round(_clamp(swing.get("y")) * h)} if swing else None),
        })
    beams = []
    for b in structure.get("beams") or []:
        seg = _norm_seg(b) if isinstance(b, dict) else None
        if not seg:
            continue
        x1, y1, x2, y2 = seg
        beams.append({
            "beam_id": "sb_" + uuid.uuid4().hex[:6],
            "x1": round(x1 * w), "y1": round(y1 * h),
            "x2": round(x2 * w), "y2": round(y2 * h),
        })
    floors = []
    for f in structure.get("floors") or []:
        if not isinstance(f, dict):
            continue
        pts = f.get("points") or []
        clean = []
        for p in pts:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                clean.append([round(_clamp(p[0]) * w), round(_clamp(p[1]) * h)])
        if len(clean) >= 3:
            floors.append({
                "floor_id": "sf_" + uuid.uuid4().hex[:6],
                "name": (f.get("name") or "Pièce")[:60],
                "points": clean,
            })
    columns = []
    for c in structure.get("columns") or []:
        seg = _norm_seg(c) if isinstance(c, dict) else None
        if not seg:
            continue
        x1, y1, x2, y2 = seg
        columns.append({
            "column_id": "sc_" + uuid.uuid4().hex[:6],
            "x1": round(x1 * w), "y1": round(y1 * h),
            "x2": round(x2 * w), "y2": round(y2 * h),
        })
    return {
        "image_width": int(w), "image_height": int(h),
        "walls": walls, "openings": openings, "beams": beams, "floors": floors,
        "columns": columns,
        "wall_count": len(walls), "opening_count": len(openings),
        "beam_count": len(beams), "floor_count": len(floors), "column_count": len(columns),
        "plan_kind": structure.get("plan_kind") or "habitation",
        "confidence": structure.get("confidence"),
    }


async def detect_structure(image_b64_png: str, width_px: int, height_px: int) -> dict:
    """Retourne {walls:[...], openings:[...]} en pixels. Toujours un dict."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"walls": [], "openings": [], "error": "EMERGENT_LLM_KEY absent"}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        chat = LlmChat(
            api_key=api_key, session_id="plan-structure",
            system_message="Tu réponds toujours en JSON strict, sans markdown.",
        ).with_model("gemini", "gemini-3-flash-preview")
        raw = await chat.send_message(UserMessage(
            text=PROMPT, file_contents=[ImageContent(image_base64=image_b64_png)]))
    except Exception as e:
        logger.warning(f"detect_structure AI failed: {e}")
        return {"walls": [], "openings": [], "error": f"AI call failed: {type(e).__name__}"}
    return _to_px(_parse_json(raw), width_px, height_px)


def _offset_items(res: dict, ox: int, oy: int) -> dict:
    """Décale toutes les coordonnées d'une tuile vers le repère de l'image complète."""
    for key in ("walls", "openings", "beams", "columns"):
        for it in res.get(key) or []:
            it["x1"] += ox; it["y1"] += oy; it["x2"] += ox; it["y2"] += oy
            if it.get("swing"):
                it["swing"]["x"] += ox; it["swing"]["y"] += oy
    for f in res.get("floors") or []:
        f["points"] = [[p[0] + ox, p[1] + oy] for p in f.get("points", [])]
    return res


def _center(it: dict) -> tuple:
    return ((it["x1"] + it["x2"]) / 2, (it["y1"] + it["y2"]) / 2)


def _dedupe(items: list, tol: float, use_center: bool = True) -> list:
    """Supprime les doublons issus du recouvrement des tuiles (proximité)."""
    import math
    out = []
    for it in items:
        cx, cy = _center(it)
        dup = False
        for kept in out:
            kx, ky = _center(kept)
            if math.hypot(cx - kx, cy - ky) < tol:
                dup = True
                break
        if not dup:
            out.append(it)
    return out


async def detect_structure_tiled(image_b64_png: str, width_px: int, height_px: int,
                                 max_tile: int = 2200) -> dict:
    """Analyse un GRAND plan (A0/A1) en le découpant en zones, puis fusionne.
    Capte beaucoup plus de poteaux/poutres qu'un seul passage sur l'image réduite."""
    import base64 as _b64
    import io as _io
    import asyncio
    from PIL import Image as _Image

    big = max(width_px, height_px)
    if big <= max_tile * 1.3:
        return await detect_structure(image_b64_png, width_px, height_px)

    cols = min(3, max(1, -(-width_px // max_tile)))   # ceil
    rows = min(3, max(1, -(-height_px // max_tile)))
    img = _Image.open(_io.BytesIO(_b64.b64decode(image_b64_png))).convert("RGB")
    tw, th = width_px // cols, height_px // rows
    ov = int(min(tw, th) * 0.08)  # recouvrement

    async def run_tile(cx, cy):
        x0 = max(0, cx * tw - ov); y0 = max(0, cy * th - ov)
        x1 = min(width_px, (cx + 1) * tw + ov); y1 = min(height_px, (cy + 1) * th + ov)
        crop = img.crop((x0, y0, x1, y1))
        buf = _io.BytesIO(); crop.save(buf, format="PNG")
        b64 = _b64.b64encode(buf.getvalue()).decode()
        res = await detect_structure(b64, crop.width, crop.height)
        return _offset_items(res, x0, y0)

    tiles = await asyncio.gather(*[run_tile(cx, cy) for cy in range(rows) for cx in range(cols)],
                                 return_exceptions=True)
    merged = {"walls": [], "openings": [], "beams": [], "columns": [], "floors": [],
              "plan_kind": "coffrage", "confidence": None}
    kinds = []
    for t in tiles:
        if isinstance(t, Exception) or not isinstance(t, dict):
            continue
        for k in ("walls", "openings", "beams", "columns", "floors"):
            merged[k].extend(t.get(k) or [])
        if t.get("plan_kind"):
            kinds.append(t["plan_kind"])
    diag = (width_px ** 2 + height_px ** 2) ** 0.5
    merged["columns"] = _dedupe(merged["columns"], diag * 0.010)
    merged["beams"] = _dedupe(merged["beams"], diag * 0.012)
    merged["walls"] = _dedupe(merged["walls"], diag * 0.010)
    merged["openings"] = _dedupe(merged["openings"], diag * 0.012)
    if kinds:
        merged["plan_kind"] = max(set(kinds), key=kinds.count)
    merged.update({
        "image_width": width_px, "image_height": height_px,
        "wall_count": len(merged["walls"]), "opening_count": len(merged["openings"]),
        "beam_count": len(merged["beams"]), "floor_count": len(merged["floors"]),
        "column_count": len(merged["columns"]),
        "tiled": f"{cols}x{rows}",
    })
    return merged
