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
    // POTEAUX (plan de coffrage) : petits carrés/rectangles/cercles PLEINS (souvent hachurés
    // en croix / trame serrée), disposés sur une TRAME structurelle régulière, souvent
    // repérés "P1", "P2"… ou cotés (ex "20x20", "Ø30"). Donne les DEUX coins opposés.
    // NE COMPTE PAS comme poteau : les réservations/trémies (Ø de gaines, EU/EP/VB/élec),
    // les intersections de poutres, les symboles de descente de charge, les cercles de
    // canalisation. En cas de doute (petit cercle annoté Ø ou d'un repère fluide) → c'est une
    // RÉSERVATION, pas un poteau. Reste réaliste : un niveau courant a typiquement 15 à 35
    // poteaux, rarement plus — ne gonfle pas le compte avec des trémies.
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
  "footings": [
    // SEMELLES / fondations (souvent surlignées en JAUNE) : rectangle d'emprise.
    // Donne les DEUX coins opposés. Coordonnées normalisées 0-1.
    {"x1": 0.18, "y1": 0.28, "x2": 0.26, "y2": 0.36}
  ],
  "floors": [
    // SURFACES DE SOL / DALLES / PLANCHERS (souvent surlignés en VERT) : un polygone fermé.
    // IMPORTANT : relève le CONTOUR COMPLET de la dalle/plancher (toute l'emprise du niveau,
    // pas seulement une pièce). S'il y a une seule grande dalle, renvoie UN grand polygone.
    // Reprends la cote NGF (ex "NGF 53.69") et l'épaisseur (ex "ep 20 cm" -> 20) si annotées.
    {"name": "Dalle" | "Séjour" | ...,
     "points": [[0.12, 0.14], [0.48, 0.14], [0.48, 0.50], [0.12, 0.50]],
     "ngf": 53.69, "thickness_cm": 20}
  ],
  "reservations": [
    // RÉSERVATIONS / TRÉMIES dans le plancher (petits rectangles/cercles annotés Ø, dims
    // type "40x20", repères Elec/VB/PLB/EU/EP, cote "Ai:"). Un point central suffit.
    {"x": 0.55, "y": 0.42, "kind": "elec" | "plomberie" | "ventilation" | "trémie" | null,
     "size": "40x20" | "Ø200" | null}
  ],
  "plan_kind": "habitation" | "coffrage",
  "confidence": 0.0-1.0
}

CODE COULEUR (si le plan est colorisé, respecte-le STRICTEMENT) :
- ORANGE = murs / voiles porteurs (walls, type "porteur")
- ROUGE = poutres (beams)
- JAUNE = semelles / fondations (footings)
- VERT = planchers / dalles (floors) — relève la cote NGF et l'épaisseur en cm si présentes

RÈGLES :
- Respecte le code couleur ci-dessus en priorité. Sinon : murs = traits épais, poutres = pointillés.
- Poteaux = petits éléments PLEINS isolés sur une trame, cotés/repérés "Px" — voir la définition
  détaillée dans "columns". Distingue-les STRICTEMENT des réservations/trémies.
- PLANCHER : relève le contour COMPLET de la dalle (toute l'emprise du niveau), pas une seule pièce.
- BANDES NOYÉES (BN) / poutres noyées : traite-les comme des "beams" (repère "BN", trait renforcé dans la dalle).
- RÉSERVATIONS / trémies : liste-les TOUTES dans "reservations" (jamais dans "openings" ni "columns").
  Tout petit rectangle/cercle DANS la dalle annoté d'un Ø, d'une dimension (ex "40x20") ou d'un
  repère fluide (EU, EP, VB, Élec, PLB, gaine) = RÉSERVATION.
- COFFRAGE : sur un plan de coffrage/structure, "openings" DOIT rester VIDE ([]). Les trous dans la
  dalle sont des réservations, pas des ouvertures de mur. Ne mets JAMAIS de trémie dans "openings".
- Sois EXHAUSTIF sur murs/poutres/réservations, mais PRÉCIS sur les poteaux (pas de sur-comptage).
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
                "ngf": f.get("ngf"),
                "thickness_cm": f.get("thickness_cm"),
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
    footings = []
    for ft in structure.get("footings") or []:
        seg = _norm_seg(ft) if isinstance(ft, dict) else None
        if not seg:
            continue
        x1, y1, x2, y2 = seg
        footings.append({
            "footing_id": "sft_" + uuid.uuid4().hex[:6],
            "x1": round(x1 * w), "y1": round(y1 * h),
            "x2": round(x2 * w), "y2": round(y2 * h),
        })
    reservations = []
    for r in structure.get("reservations") or []:
        if not isinstance(r, dict):
            continue
        try:
            rx, ry = float(r.get("x")), float(r.get("y"))
        except (TypeError, ValueError):
            continue
        reservations.append({
            "reservation_id": "res_" + uuid.uuid4().hex[:6],
            "x": round(rx * w), "y": round(ry * h),
            "kind": r.get("kind"), "size": r.get("size"),
        })
    return {
        "image_width": int(w), "image_height": int(h),
        "walls": walls, "openings": openings, "beams": beams, "floors": floors,
        "columns": columns, "footings": footings, "reservations": reservations,
        "wall_count": len(walls), "opening_count": len(openings),
        "beam_count": len(beams), "floor_count": len(floors), "column_count": len(columns),
        "footing_count": len(footings), "reservation_count": len(reservations),
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


def _px_to_norm(structure: dict, w: int, h: int) -> dict:
    """Convertit une structure en pixels vers des coordonnées normalisées 0-1 (pour l'IA)."""
    if not w or not h:
        return {}

    def seg(it):
        return {"x1": round(it.get("x1", 0) / w, 3), "y1": round(it.get("y1", 0) / h, 3),
                "x2": round(it.get("x2", 0) / w, 3), "y2": round(it.get("y2", 0) / h, 3)}

    out = {"walls": [], "columns": [], "beams": [], "openings": [], "footings": [], "floors": []}
    for wseg in structure.get("walls") or []:
        out["walls"].append({**seg(wseg), "type": wseg.get("type", "cloison")})
    for c in structure.get("columns") or []:
        out["columns"].append(seg(c))
    for b in structure.get("beams") or []:
        out["beams"].append(seg(b))
    for o in structure.get("openings") or []:
        d = seg(o)
        d["kind"] = o.get("kind", "fenetre")
        out["openings"].append(d)
    for ft in structure.get("footings") or []:
        out["footings"].append(seg(ft))
    for f in structure.get("floors") or []:
        pts = [[round(p[0] / w, 3), round(p[1] / h, 3)] for p in (f.get("points") or [])]
        out["floors"].append({"name": f.get("name"), "points": pts,
                              "ngf": f.get("ngf"), "thickness_cm": f.get("thickness_cm")})
    return out


async def refine_structure(image_b64_png: str, width_px: int, height_px: int,
                           instruction: str, current: dict | None = None,
                           history: list | None = None) -> dict:
    """Relance l'analyse du plan en appliquant les consignes en langage naturel de l'utilisateur.

    L'IA reçoit l'image + la structure actuelle + la consigne, et renvoie la structure
    COMPLÈTE mise à jour + un champ "reply" (phrase FR expliquant ce qui a changé).
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent", "reply": "Clé IA absente."}
    cur_norm = _px_to_norm(current or {}, width_px, height_px)
    hist_txt = ""
    if history:
        recent = [h for h in history[-8:] if h]
        if recent:
            hist_txt = "\n\nCONSIGNES PRÉCÉDENTES (déjà appliquées) :\n" + "\n".join(f"- {h}" for h in recent)
    user_text = (
        PROMPT
        + "\n\n===== STRUCTURE ACTUELLE (à corriger — coordonnées normalisées 0-1) =====\n"
        + json.dumps(cur_norm, ensure_ascii=False)
        + hist_txt
        + "\n\n===== CONSIGNE DE L'UTILISATEUR (applique-la PRÉCISÉMENT) =====\n"
        + instruction.strip()
        + "\n\nRenvoie le JSON COMPLET mis à jour (même schéma qu'au-dessus) en appliquant la consigne. "
          "Conserve les éléments corrects existants. Ajoute EN PLUS un champ "
          "\"reply\": \"...\" contendo UMA frase em português europeu (PT-PT) a explicar o que alteraste."
    )
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        chat = LlmChat(
            api_key=api_key, session_id="plan-structure-refine",
            system_message="Tu réponds toujours en JSON strict, sans markdown.",
        ).with_model("gemini", "gemini-3-flash-preview")
        raw = await chat.send_message(UserMessage(
            text=user_text, file_contents=[ImageContent(image_base64=image_b64_png)]))
    except Exception as e:
        logger.warning(f"refine_structure AI failed: {e}")
        return {"error": f"AI call failed: {type(e).__name__}", "reply": "L'IA n'a pas pu traiter la consigne."}
    parsed = _parse_json(raw)
    reply = parsed.pop("reply", None) if isinstance(parsed, dict) else None
    result = _to_px(parsed, width_px, height_px)
    result["reply"] = reply or "Analyse mise à jour selon votre consigne."
    if parsed.get("error"):
        result["error"] = parsed["error"]
    return result


def _offset_items(res: dict, ox: int, oy: int) -> dict:
    """Décale toutes les coordonnées d'une tuile vers le repère de l'image complète."""
    for key in ("walls", "openings", "beams", "columns", "footings"):
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


def _reclassify_coffrage(res: dict) -> None:
    """Calage vérité DWG : sur un plan de COFFRAGE, les 'openings' détectées sont en réalité
    des trémies/réservations (une dalle n'a pas d'ouverture de mur). On les reverse dans
    'reservations' et on vide 'openings' pour éviter de fausser le métré (linteaux fantômes)."""
    if res.get("plan_kind") != "coffrage":
        return
    ops = res.get("openings") or []
    if ops:
        res.setdefault("reservations", [])
        for o in ops:
            cx = (o.get("x1", 0) + o.get("x2", 0)) / 2.0
            cy = (o.get("y1", 0) + o.get("y2", 0)) / 2.0
            res["reservations"].append({"x": cx, "y": cy,
                                        "kind": None, "size": o.get("size")})
        res["openings"] = []


async def detect_structure_tiled(image_b64_png: str, width_px: int, height_px: int,
                                 max_tile: int = 2200, force_kind: str | None = None) -> dict:
    """Analyse un GRAND plan (A0/A1) en le découpant en zones, puis fusionne.
    Capte beaucoup plus de poteaux/poutres qu'un seul passage sur l'image réduite.
    force_kind ("coffrage"|"habitation") : force le type de plan choisi par l'utilisateur
    (gros œuvre vs maison) au lieu de la détection automatique."""
    import base64 as _b64
    import io as _io
    import asyncio
    from PIL import Image as _Image

    big = max(width_px, height_px)
    if big <= max_tile * 1.3:
        single = await detect_structure(image_b64_png, width_px, height_px)
        if force_kind:
            single["plan_kind"] = force_kind
        _reclassify_coffrage(single)
        single["reservation_count"] = len(single.get("reservations") or [])
        single["opening_count"] = len(single.get("openings") or [])
        return single

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
              "footings": [], "reservations": [], "plan_kind": "coffrage", "confidence": None}
    kinds = []
    for t in tiles:
        if isinstance(t, Exception) or not isinstance(t, dict):
            continue
        for k in ("walls", "openings", "beams", "columns", "floors", "footings", "reservations"):
            merged[k].extend(t.get(k) or [])
        if t.get("plan_kind"):
            kinds.append(t["plan_kind"])
    diag = (width_px ** 2 + height_px ** 2) ** 0.5
    merged["columns"] = _dedupe(merged["columns"], diag * 0.010)
    merged["beams"] = _dedupe(merged["beams"], diag * 0.012)
    merged["walls"] = _dedupe(merged["walls"], diag * 0.010)
    merged["openings"] = _dedupe(merged["openings"], diag * 0.012)
    merged["footings"] = _dedupe(merged["footings"], diag * 0.010)
    if kinds:
        merged["plan_kind"] = max(set(kinds), key=kinds.count)
    # Calage : un plan avec de nombreux poteaux détectés EST un plan de coffrage,
    # même si le vote par tuile hésite (des tuiles sans poteau votent "habitation").
    if not force_kind and (len(merged["columns"]) >= 10 or (kinds.count("coffrage") >= max(2, len(kinds) // 3))):
        merged["plan_kind"] = "coffrage"
    if force_kind:
        merged["plan_kind"] = force_kind
    _reclassify_coffrage(merged)
    merged.update({
        "image_width": width_px, "image_height": height_px,
        "wall_count": len(merged["walls"]), "opening_count": len(merged["openings"]),
        "beam_count": len(merged["beams"]), "floor_count": len(merged["floors"]),
        "column_count": len(merged["columns"]), "footing_count": len(merged["footings"]),
        "reservation_count": len(merged.get("reservations") or []),
        "tiled": f"{cols}x{rows}",
    })
    return merged
