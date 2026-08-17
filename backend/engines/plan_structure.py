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

PROMPT = """Tu es un métreur expert. Analyse ce plan d'architecture 2D et extrais UNIQUEMENT
la structure du bâti pour un rendu technique. NE compte PAS les meubles, sanitaires, textes,
cotes (traits de mesure) ni le cartouche.

Rends STRICTEMENT du JSON (aucun markdown, aucun texte hors JSON) :

{
  "walls": [
    // Chaque segment de MUR (trait plein épais / hachuré). Un mur = une ligne droite.
    // Décompose les murs longs en segments entre les angles. Coordonnées normalisées 0-1.
    {"x1": 0.10, "y1": 0.12, "x2": 0.90, "y2": 0.12, "type": "porteur" | "cloison"}
  ],
  "openings": [
    // Ouvertures dans les murs. Le segment [x1,y1]->[x2,y2] représente la LARGEUR de
    // l'ouverture, posée SUR la ligne du mur concerné. Coordonnées normalisées 0-1.
    // kind : "porte" (arc de battement visible) | "fenetre" | "baie" (grande baie vitrée)
    {"kind": "porte" | "fenetre" | "baie",
     "x1": 0.30, "y1": 0.12, "x2": 0.40, "y2": 0.12,
     "hinge": {"x": 0.30, "y": 0.12} | null,   // gond de la porte si identifiable
     "swing": {"x": 0.40, "y": 0.20} | null}    // point vers lequel la porte s'ouvre
  ],
  "confidence": 0.0-1.0
}

RÈGLES :
- Murs extérieurs (contour du bâtiment) = "porteur". Refends/murs épais intérieurs = "porteur".
  Petites cloisons fines = "cloison".
- Les ouvertures sont des TROUS dans les murs : une porte a un arc de battement (quart de cercle) ;
  une fenêtre est un rectangle/double-trait dans l'épaisseur du mur ; une baie est large.
- Aligne bien chaque ouverture sur la ligne du mur qui la contient.
- N'invente pas d'ouverture sans indice visuel. Sois précis sur les positions.
- Réponds UNIQUEMENT le JSON.
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
    return {
        "image_width": int(w), "image_height": int(h),
        "walls": walls, "openings": openings,
        "wall_count": len(walls), "opening_count": len(openings),
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
