"""Interprétation textes & cotes — calibration auto et application des textes IA.

Fonctions PURES (pas de DB, pas de LLM) :
- calibration_from_dimension_lines : échelle px/m depuis les traits de cote lus par l'IA
- reconcile_written_surfaces : recalage d'échelle via les surfaces écrites sur le plan
- match_ai_rooms : appariement pièces mesurées ↔ pièces IA (nom puis surface)
"""
from __future__ import annotations

import math
import re
import unicodedata

GENERIC_NAME_RE = re.compile(r"^(pi[eè]ce|room|auto|zone)[\s\d_.-]*$", re.IGNORECASE)


def _norm_name(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").strip().lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def is_generic_name(name: str | None) -> bool:
    """« Pièce 01 », « Room 2 », « Auto »… = nom générique renommable par l'IA."""
    return bool(GENERIC_NAME_RE.match((name or "").strip()))


def _median(values: list[float]) -> float:
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def calibration_from_dimension_lines(dimension_lines: list[dict], img_w: int, img_h: int,
                                     min_value_m: float = 0.4,
                                     min_px: float = 25.0,
                                     inlier_tol: float = 0.12) -> dict | None:
    """Échelle pixels/mètre robuste depuis les traits de cote détectés par l'IA.

    Chaque cote = {value_m, bbox_norm [x1,y1,x2,y2] normalisé 0-1, confidence}.
    Médiane des ratios px/m puis rejet des outliers à ±inlier_tol de la médiane.
    Retourne None si aucune cote exploitable.
    """
    if not img_w or not img_h:
        return None
    candidates: list[dict] = []
    for d in dimension_lines or []:
        bbox = d.get("bbox_norm")
        try:
            value = float(d.get("value_m") or 0)
        except (TypeError, ValueError):
            continue
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4) or value < min_value_m:
            continue
        px = math.hypot((bbox[2] - bbox[0]) * img_w, (bbox[3] - bbox[1]) * img_h)
        if px < min_px:
            continue
        conf = float(d.get("confidence") or 0.5)
        if conf < 0.3:
            continue
        candidates.append({"value_m": value, "pixel_length": round(px, 1),
                           "ppm": px / value, "confidence": conf,
                           "location": d.get("location")})
    if not candidates:
        return None
    med = _median([c["ppm"] for c in candidates])
    inliers = [c for c in candidates if abs(c["ppm"] - med) / med <= inlier_tol]
    if not inliers:
        return None
    final = _median([c["ppm"] for c in inliers])
    spreads = [abs(c["ppm"] - final) / final for c in inliers]
    spread_pct = round(max(spreads) * 100, 1) if len(inliers) > 1 else 0.0
    confidence = max(0.3, min(0.95, 0.55 + 0.1 * min(len(inliers), 4) - spread_pct / 100))
    for c in candidates:
        c["inlier"] = abs(c["ppm"] - final) / final <= inlier_tol
        c["ppm"] = round(c["ppm"], 2)
    return {
        "pixels_per_meter": round(final, 4),
        "meters_per_pixel": round(1.0 / final, 8),
        "samples_total": len(candidates),
        "samples_used": len(inliers),
        "spread_pct": spread_pct,
        "confidence": round(confidence, 2),
        "samples": candidates,
    }


def match_ai_rooms(measured_rooms: list[dict], ai_rooms: list[dict],
                   surface_tol: float = 0.35) -> list[dict]:
    """Apparie pièces mesurées ↔ pièces IA.

    1er passage par nom normalisé (accents/casse ignorés), 2e passage par
    proximité de surface (greedy, écart relatif ≤ surface_tol).
    Retourne [{room, ai, method}].
    """
    remaining = list(range(len(ai_rooms or [])))
    pairs: list[dict] = []
    for room in measured_rooms or []:
        rn = _norm_name(room.get("name"))
        if not rn or is_generic_name(room.get("name")):
            continue
        for i in list(remaining):
            an = _norm_name(ai_rooms[i].get("name"))
            if an and (an == rn or an in rn or rn in an):
                pairs.append({"room": room, "ai": ai_rooms[i], "method": "name"})
                remaining.remove(i)
                break
    matched_ids = {id(p["room"]) for p in pairs}
    for room in measured_rooms or []:
        if id(room) in matched_ids:
            continue
        surf = float(room.get("surface_m2") or 0)
        if surf <= 0:
            continue
        best, best_delta = -1, None
        for i in remaining:
            written = ai_rooms[i].get("surface_written_m2") or ai_rooms[i].get("estimated_surface_m2")
            try:
                written = float(written or 0)
            except (TypeError, ValueError):
                continue
            if written <= 0:
                continue
            delta = abs(written - surf) / max(written, surf)
            if delta <= surface_tol and (best_delta is None or delta < best_delta):
                best, best_delta = i, delta
        if best >= 0:
            pairs.append({"room": room, "ai": ai_rooms[best], "method": "surface"})
            remaining.remove(best)
    return pairs


def reconcile_written_surfaces(measured_rooms: list[dict], ai_rooms: list[dict],
                               current_ppm: float) -> dict:
    """Compare surfaces mesurées vs surfaces ÉCRITES sur le plan.

    Si les surfaces écrites sont la référence, la nouvelle échelle est
    ppm_new = ppm_cur × √(mesuré / écrit) — la surface varie en 1/ppm².
    """
    pairs = match_ai_rooms(measured_rooms, ai_rooms)
    matches: list[dict] = []
    ratios: list[float] = []
    for p in pairs:
        try:
            written = float(p["ai"].get("surface_written_m2") or 0)
        except (TypeError, ValueError):
            continue
        measured = float(p["room"].get("surface_m2") or 0)
        if written <= 0 or measured <= 0:
            continue
        ratio = written / measured
        ratios.append(ratio)
        matches.append({
            "room_id": p["room"].get("room_id"),
            "room_name": p["room"].get("name"),
            "ai_name": p["ai"].get("name"),
            "measured_m2": round(measured, 2),
            "written_m2": round(written, 2),
            "delta_pct": round((ratio - 1) * 100, 1),
            "match_method": p["method"],
        })
    if not ratios:
        return {"matches": [], "can_reconcile": False,
                "reason": "Aucune pièce appariée avec une surface écrite sur le plan"}
    med_ratio = _median(ratios)
    deviation_pct = round(abs(med_ratio - 1) * 100, 1)
    proposed_ppm = round(current_ppm * math.sqrt(1.0 / med_ratio), 4)
    return {
        "matches": matches,
        "can_reconcile": True,
        "median_ratio": round(med_ratio, 4),
        "deviation_pct": deviation_pct,
        "needs_recalib": deviation_pct > 5.0,
        "current_ppm": round(current_ppm, 4),
        "proposed_ppm": proposed_ppm,
    }
