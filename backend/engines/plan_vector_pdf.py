"""Extraction vectorielle des cotes d'un PDF (traits + textes exacts, sans passer par les pixels).

Principe : chaque texte numérique de cote (« 5.20 », « 0.13 ») est rattaché à sa ligne de cote
(trait parallèle au texte le plus proche), puis la longueur réelle est mesurée entre les deux lignes
d'attache (traits perpendiculaires) qui encadrent le texte. Résultat en points PDF → mètres via
l'échelle (déclarée ou auto-calibrée sur la médiane des ratios, quasi exacte sur un dessin CAO).
"""
from __future__ import annotations

import re
import statistics

_NUM_RE = re.compile(r"^(\d{1,4})(?:[.,](\d{1,3}))?\s*(m|cm|mm)?$")
PT_PER_MM = 72 / 25.4


def _value_m(text: str) -> float | None:
    m = _NUM_RE.match(text.strip())
    if not m:
        return None
    whole, dec, unit = m.group(1), m.group(2), m.group(3)
    v = float(f"{whole}.{dec or 0}")
    if unit == "mm":
        return v / 1000
    if unit == "cm":
        return v / 100
    if unit == "m" or dec is not None:
        return v if 0.05 <= v <= 500 else None
    if v >= 1000:
        return v / 1000
    if v >= 20:
        return v / 100
    return None


def pdf_lines(page) -> list[dict]:
    """Segments d'un objet page PyMuPDF (points PDF)."""
    out = []
    for d in page.get_drawings():
        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                out.append({"type": "line", "p1": [p1.x, p1.y], "p2": [p2.x, p2.y]})
            elif item[0] == "re":
                r = item[1]
                out.append({"type": "rect", "x": r.x0, "y": r.y0, "w": r.width, "h": r.height})
    return out


def _segments(vectors: list[dict]) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """→ (horizontaux [(y, xa, xb)], verticaux [(x, ya, yb)], courts obliques [(cx, cy, len)])."""
    hs, vs, ticks = [], [], []
    for v in vectors or []:
        if v.get("type") == "rect":
            x, y, w, h = v["x"], v["y"], v["w"], v["h"]
            if w < 0.8 and h >= 2:
                vs.append((x + w / 2, y, y + h))
            elif h < 0.8 and w >= 2:
                hs.append((y + h / 2, x, x + w))
            continue
        if v.get("type") != "line":
            continue
        (x1, y1), (x2, y2) = v["p1"], v["p2"]
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dy < 0.6 and dx >= 1:
            hs.append(((y1 + y2) / 2, min(x1, x2), max(x1, x2)))
        elif dx < 0.6 and dy >= 1:
            vs.append(((x1 + x2) / 2, min(y1, y2), max(y1, y2)))
        elif 3 <= max(dx, dy) <= 12 and min(dx, dy) >= 0.4 * max(dx, dy):
            ticks.append(((x1 + x2) / 2, (y1 + y2) / 2, max(dx, dy)))
    return hs, vs, ticks


def _nearest_parallel(par: list[tuple], c_along: float, c_perp: float, reach: float, margin: float):
    best = None
    for pos, a, b in par:
        if a - margin <= c_along <= b + margin and abs(pos - c_perp) <= reach:
            if best is None or abs(pos - c_perp) < abs(best[0] - c_perp):
                best = (pos, a, b)
    return best


def _clusters(marks: list[tuple[float, float]]) -> list[float]:
    """Regroupe les positions proches (disques/points d'extrémité dessinés par petits traits) →
    une position par repère : celle du trait long (ligne d'attache) sinon le centre du groupe."""
    marks.sort()
    out, group = [], []
    for pos, ln in marks:
        if group and pos - group[-1][0] > 1.2:
            out.append(group)
            group = []
        group.append((pos, ln))
    if group:
        out.append(group)
    res = []
    for g in out:
        longest = max(g, key=lambda m: m[1])
        if longest[1] >= 6:
            res.append(longest[0])
        else:
            tot = sum(m[1] for m in g) or 1
            res.append(sum(m[0] * m[1] for m in g) / tot)
    return res


def _bounds(perp: list[tuple], ticks_along: list[float], line_pos: float, c_along: float,
            half_text: float, tol: float) -> tuple[float, float] | None:
    marks = [(p, b - a) for p, a, b in perp if a - tol <= line_pos <= b + tol]
    marks += [(p, 5.0) for p in ticks_along]
    xs = _clusters(marks)
    left = [x for x in xs if x < c_along - half_text * 0.3]
    right = [x for x in xs if x > c_along + half_text * 0.3]
    if not left or not right:
        return None
    return max(left), min(right)


def extract_vector_dimensions(vectors: list[dict], text_blocks: list[dict], px_per_pt: float,
                              pt_per_m: float | None = None) -> dict:
    """Cotes vectorielles → segments pixels image + mesure exacte.

    Renvoie {dimensions[], pt_per_m, self_calibrated, texts_numeric, matched}.
    """
    hs, vs, ticks = _segments(vectors)
    numeric = [(t, _value_m(t.get("text") or "")) for t in text_blocks or []]
    numeric = [(t, v) for t, v in numeric if v is not None and float(t.get("w") or 0) > 0 and float(t.get("h") or 0) > 0]
    with_dec = sum(1 for t, _ in numeric if re.search(r"[.,]\d", t.get("text") or ""))
    if numeric and with_dec >= 0.7 * len(numeric):  # « 24 », « 21 » = repères, pas des cotes
        numeric = [(t, v) for t, v in numeric if re.search(r"[.,]\d", t.get("text") or "")]

    def _try(orient: str, t: dict) -> dict | None:
        w, h = float(t["w"]), float(t["h"])
        cx, cy = float(t["x"]) + w / 2, float(t["y"]) + h / 2
        if orient == "h":
            fh = min(w, h)
            line = _nearest_parallel(hs, cx, cy, reach=2.5 * fh, margin=max(w, h, 3 * fh))
            if not line:
                return None
            tk = [tx for tx, ty, _ in ticks if abs(ty - line[0]) <= 2.5]
            b = _bounds(vs, tk, line[0], cx, max(w, h) / 2, tol=1.5)
            return b and {"orientation": "h", "pt_len": b[1] - b[0], "p1": (b[0], line[0]), "p2": (b[1], line[0])}
        fh = min(w, h)
        line = _nearest_parallel(vs, cy, cx, reach=2.5 * fh, margin=max(w, h, 3 * fh))
        if not line:
            return None
        tk = [ty for tx, ty, _ in ticks if abs(tx - line[0]) <= 2.5]
        b = _bounds(hs, tk, line[0], cy, max(w, h) / 2, tol=1.5)
        return b and {"orientation": "v", "pt_len": b[1] - b[0], "p1": (line[0], b[0]), "p2": (line[0], b[1])}

    pairs = []
    for t, val in numeric:
        w, h = float(t["w"]), float(t["h"])
        first, second = ("h", "v") if w >= h else ("v", "h")
        a, b = _try(first, t), _try(second, t)
        if a or b:
            pairs.append((t, val, a, b))
    # échelle de référence : mode des ratios dans l'orientation du texte (grandes cotes seulement)
    ref = _mode_ratio([a["pt_len"] / val for _, val, a, _ in pairs if a and val >= 0.5]) or pt_per_m
    raw = []
    for t, val, a, b in pairs:
        best = a or b
        if a and b and ref:
            # les épaisseurs (0.13, 0.24) sont souvent écrites tournées : on garde l'orientation plausible
            ea, eb = abs(a["pt_len"] / ref - val), abs(b["pt_len"] / ref - val)
            if ea > 0.05 * max(val, 0.5) and eb < ea:
                best = b
        raw.append({"text": t["text"], "value_m": val, **best})
    n_texts = len(numeric)
    if not raw:
        return {"dimensions": [], "pt_per_m": pt_per_m, "self_calibrated": False,
                "texts_numeric": n_texts, "matched": 0}
    self_cal = _mode_ratio([r["pt_len"] / r["value_m"] for r in raw if r["value_m"] >= 0.5])
    used = self_cal or pt_per_m
    self_calibrated = bool(self_cal) and (pt_per_m is None or abs(self_cal - pt_per_m) / pt_per_m > 0.005)
    if not used:
        return {"dimensions": [], "pt_per_m": None, "self_calibrated": False,
                "texts_numeric": n_texts, "matched": len(raw)}
    dims = []
    for r in raw:
        measured = r["pt_len"] / used
        if measured <= 0 or measured > 500 or abs(measured - r["value_m"]) > max(3.0, r["value_m"]):
            continue  # rattachement manifestement faux (ligne d'attache manquante) → on s'abstient
        dims.append({"x1": round(r["p1"][0] * px_per_pt, 2), "y1": round(r["p1"][1] * px_per_pt, 2),
                     "x2": round(r["p2"][0] * px_per_pt, 2), "y2": round(r["p2"][1] * px_per_pt, 2),
                     "value_m": round(r["value_m"], 4), "measured_m": round(measured, 4),
                     "raw_text": r["text"], "location": "cote vectorielle PDF", "orientation": r["orientation"]})
    return {"dimensions": dims, "pt_per_m": round(used, 4), "self_calibrated": self_calibrated,
            "declared_pt_per_m": round(pt_per_m, 4) if pt_per_m else None,
            "texts_numeric": n_texts, "matched": len(dims)}


def _mode_ratio(ratios: list[float]) -> float | None:
    ratios = sorted(ratios)
    if len(ratios) < 3:
        return None
    med = statistics.median(ratios)
    core = [x for x in ratios if abs(x - med) / med <= 0.02]
    return statistics.median(core) if len(core) >= max(3, len(ratios) // 2) else None


def pt_per_m_from_scale(denominator: int | None) -> float | None:
    return 1000.0 / denominator * PT_PER_MM if denominator else None
