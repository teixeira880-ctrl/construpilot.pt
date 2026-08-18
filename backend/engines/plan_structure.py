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
