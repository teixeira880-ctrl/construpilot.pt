"""Contrôle des cotes : cote indiquée ↔ longueur mesurée sur le plan + chaînes de cotes.

Entrée : liste de cotes en pixels image {x1,y1,x2,y2,value_m,confidence,location,source}
(lues par l'IA — bbox_norm converti — ou extraites d'un DXF avec `measured_m` exact).
"""
from __future__ import annotations

import math

STATUS_ORDER = {"ko": 0, "warn": 1, "ok": 2}


def _length_px(d: dict) -> float:
    return math.hypot(d["x2"] - d["x1"], d["y2"] - d["y1"])


def _orientation(d: dict) -> str:
    dx, dy = abs(d["x2"] - d["x1"]), abs(d["y2"] - d["y1"])
    if dx >= 4 * dy:
        return "h"
    if dy >= 4 * dx:
        return "v"
    return "o"


def dims_from_ai(dimension_lines: list[dict], img_w: int, img_h: int) -> list[dict]:
    """Cotes IA (bbox_norm 0-1) → segments pixels."""
    out = []
    for d in dimension_lines or []:
        bbox = d.get("bbox_norm")
        try:
            value = float(d.get("value_m") or 0)
        except (TypeError, ValueError):
            continue
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4) or value <= 0:
            continue
        out.append({"x1": bbox[0] * img_w, "y1": bbox[1] * img_h,
                    "x2": bbox[2] * img_w, "y2": bbox[3] * img_h,
                    "value_m": value, "raw_text": d.get("raw_text"),
                    "confidence": float(d.get("confidence") or 0.5),
                    "location": d.get("location"), "source": "ai"})
    return out


def dims_from_dxf(dxf_dimensions: list[dict]) -> list[dict]:
    return [{**d, "confidence": 1.0, "source": "dxf"} for d in dxf_dimensions or []
            if d.get("value_m") and d.get("measured_m")]


def _status(delta_m: float, tol_m: float) -> str:
    a = abs(delta_m)
    if a <= 0.6 * tol_m:
        return "ok"
    return "warn" if a <= tol_m else "ko"


def _niveau_mm(delta_mm: float) -> str:
    """Classification ConstruPilot : VERT ≤2 mm · BLEU ≤10 · JAUNE ≤30 · ORANGE ≤100 · ROUGE >100."""
    a = abs(delta_mm)
    return "VERT" if a <= 2 else "BLEU" if a <= 10 else "JAUNE" if a <= 30 else "ORANGE" if a <= 100 else "ROUGE"


def _tol_m(value_m: float, tol_pct: float, tol_cm: float) -> float:
    return max(value_m * tol_pct / 100.0, tol_cm / 100.0)


def _axis(d: dict, orient: str) -> tuple[float, float, float]:
    """(début, fin, position perpendiculaire) le long de l'axe de la cote."""
    if orient == "h":
        return min(d["x1"], d["x2"]), max(d["x1"], d["x2"]), (d["y1"] + d["y2"]) / 2
    return min(d["y1"], d["y2"]), max(d["y1"], d["y2"]), (d["x1"] + d["x2"]) / 2


def _find_chains(items: list[dict], tol_pct: float, tol_cm: float, img_side: float) -> list[dict]:
    """Une cote 'totale' doit être égale à la somme des cotes partielles contiguës qu'elle couvre."""
    tol_px = max(6.0, img_side * 0.015)
    band_px = max(10.0, img_side * 0.02)
    chains = []
    for total in items:
        o = total["orientation"]
        if o == "o":
            continue
        a1, a2, _ = _axis(total, o)
        cands = [it for it in items if it is not total and it["orientation"] == o]
        cands = [it for it in cands
                 if _axis(it, o)[0] >= a1 - tol_px and _axis(it, o)[1] <= a2 + tol_px
                 and _axis(it, o)[1] - _axis(it, o)[0] < (a2 - a1) - tol_px]
        if len(cands) < 2:
            continue
        bands: dict[int, list[dict]] = {}
        for it in cands:
            bands.setdefault(int(round(_axis(it, o)[2] / band_px)), []).append(it)
        best = None
        for group in bands.values():
            group.sort(key=lambda it: _axis(it, o)[0])
            if len(group) < 2 or abs(_axis(group[0], o)[0] - a1) > tol_px:
                continue
            cursor, ok = a1, True
            for it in group:
                s, e, _ = _axis(it, o)
                if abs(s - cursor) > tol_px:
                    ok = False
                    break
                cursor = e
            if ok and abs(cursor - a2) <= tol_px and (best is None or len(group) > len(best)):
                best = group
        if not best:
            continue
        sum_m = sum(it["indicated_m"] for it in best)
        delta = sum_m - total["indicated_m"]
        tol = _tol_m(total["indicated_m"], tol_pct, tol_cm)
        chains.append({"total_index": total["index"], "total_m": total["indicated_m"],
                       "part_indexes": [it["index"] for it in best],
                       "parts_m": [it["indicated_m"] for it in best],
                       "sum_m": round(sum_m, 3), "delta_m": round(delta, 3),
                       "delta_cm": round(delta * 100, 1), "status": _status(delta, tol)})
    return chains


def snap_dims_to_image(image_b64: str, dims: list[dict], max_shift_frac: float = 0.03) -> int:
    """Recale les extrémités des cotes IA sur les traits d'attache réellement dessinés.

    Pour une cote horizontale, on cherche dans une bande autour de y la colonne sombre
    (trait vertical traversant la bande) la plus proche de chaque extrémité ; idem en vertical.
    Renvoie le nombre d'extrémités recalées.
    """
    import base64
    import io

    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("L")
    dark = np.asarray(img) < 140
    H, W = dark.shape
    moved = 0

    def _snap(profile: np.ndarray, pos: float, window: float) -> float | None:
        lo, hi = int(max(0, pos - window)), int(min(len(profile) - 1, pos + window))
        if hi <= lo:
            return None
        idx = np.nonzero(profile[lo:hi + 1] >= 0.6)[0]
        if idx.size == 0:
            return None
        cols = idx + lo
        return float(cols[np.argmin(np.abs(cols - pos))])

    for d in dims:
        if d.get("source") != "ai":
            continue
        o = _orientation(d)
        if o == "h":
            y = (d["y1"] + d["y2"]) / 2
            bh = max(4, int(0.012 * H))
            band = dark[max(0, int(y) - bh):min(H, int(y) + bh), :]
            prof = band.mean(axis=0) if band.size else None
            if prof is None:
                continue
            for k in ("x1", "x2"):
                nx = _snap(prof, d[k], max(6.0, max_shift_frac * W))
                if nx is not None and abs(nx - d[k]) > 1:
                    d[k] = nx
                    moved += 1
            d["y1"] = d["y2"] = y
        elif o == "v":
            x = (d["x1"] + d["x2"]) / 2
            bw = max(4, int(0.012 * W))
            band = dark[:, max(0, int(x) - bw):min(W, int(x) + bw)]
            prof = band.mean(axis=1) if band.size else None
            if prof is None:
                continue
            for k in ("y1", "y2"):
                ny = _snap(prof, d[k], max(6.0, max_shift_frac * H))
                if ny is not None and abs(ny - d[k]) > 1:
                    d[k] = ny
                    moved += 1
            d["x1"] = d["x2"] = x
        if moved:
            d["snapped"] = True
    return moved


def items_to_dims(items: list[dict]) -> list[dict]:
    """Rapport stocké → cotes réutilisables pour un recalcul sans relire le plan."""
    return [{"x1": it["x1"], "y1": it["y1"], "x2": it["x2"], "y2": it["y2"],
             "value_m": it["indicated_m"], "measured_m": it.get("measured_exact_m"),
             "source": it.get("source", "ai"), "confidence": it.get("confidence", 0.5),
             "location": it.get("location"), "raw_text": it.get("raw_text"),
             "override": it.get("override"), "ignored": it.get("ignored", False),
             "edited": it.get("edited", False), "original_m": it.get("original_m")}
            for it in items]


def check_dimensions(dims: list[dict], ppm: float, tol_pct: float, tol_cm: float,
                     img_w: int, img_h: int) -> dict:
    items = []
    for i, d in enumerate(dims):
        px = _length_px(d)
        exact = d.get("measured_m") if d.get("source") == "dxf" else None
        measured = exact if exact is not None else px / ppm
        indicated = float(d["value_m"])
        delta = measured - indicated
        tol = _tol_m(indicated, tol_pct, tol_cm)
        items.append({
            "index": i + 1, "x1": round(d["x1"], 1), "y1": round(d["y1"], 1),
            "x2": round(d["x2"], 1), "y2": round(d["y2"], 1),
            "orientation": _orientation(d), "location": d.get("location"),
            "raw_text": d.get("raw_text"), "source": d.get("source", "ai"),
            "confidence": round(float(d.get("confidence") or 0.5), 2),
            "indicated_m": round(indicated, 3), "measured_m": round(measured, 3),
            "measured_exact_m": exact, "pixel_length": round(px, 1),
            "delta_m": round(delta, 3), "delta_cm": round(delta * 100, 1),
            "delta_pct": round(delta / indicated * 100, 2) if indicated else None,
            "tolerance_cm": round(tol * 100, 1),
            "status": "ignored" if d.get("ignored") else _status(delta, tol),
            "niveau": _niveau_mm(delta * 1000),
            "override": bool(d.get("override")), "ignored": bool(d.get("ignored")),
            "edited": bool(d.get("edited")), "original_m": d.get("original_m"),
        })
    active = [it for it in items if not it["ignored"]]
    chains = _find_chains(active, tol_pct, tol_cm, float(max(img_w, img_h)))
    for it in items:
        it["chain_status"] = None
    for c in chains:
        if c["status"] != "ok":
            for idx in [c["total_index"], *c["part_indexes"]]:
                items[idx - 1]["chain_status"] = c["status"]
    counts = {s: sum(1 for it in active if it["status"] == s) for s in ("ok", "warn", "ko")}
    chain_counts = {s: sum(1 for c in chains if c["status"] == s) for s in ("ok", "warn", "ko")}
    worst = max((abs(it["delta_cm"]) for it in active), default=0.0)
    return {
        "items": items, "chains": chains,
        "summary": {"total": len(active), "ignored": len(items) - len(active), **counts,
                    "chains_total": len(chains),
                    "chains_ko": chain_counts["ko"], "chains_warn": chain_counts["warn"],
                    "max_delta_cm": round(worst, 1),
                    "verdict": ("ko" if counts["ko"] or chain_counts["ko"]
                                else "warn" if counts["warn"] or chain_counts["warn"] else "ok")},
        "tolerance": {"pct": tol_pct, "cm": tol_cm},
    }
