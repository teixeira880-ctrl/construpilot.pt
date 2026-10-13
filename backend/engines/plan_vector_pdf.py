"""Extraction vectorielle des cotes d'un PDF (traits + textes exacts, sans passer par les pixels).

Principe : chaque texte numérique de cote (« 5.20 », « 0.13 ») est rattaché à sa ligne de cote
(trait parallèle au texte le plus proche), puis la longueur réelle est mesurée entre les deux lignes
d'attache (traits perpendiculaires) qui encadrent le texte. Résultat en points PDF → mètres via
l'échelle (déclarée ou auto-calibrée sur la médiane des ratios, quasi exacte sur un dessin CAO).
"""
from __future__ import annotations

import re
import math
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
    """Primitives PDF en points, y compris rectangles/quadrilatères fermés.

    Conserver le style : un axe pointillé et une hachure de remplissage ne sont
    pas des faces de mur. Un quadrilatère n'est pas une boîte englobante : ses
    quatre arêtes réelles sont utilisées, même si le dessin est oblique.
    """
    out = []
    for path_id, d in enumerate(page.get_drawings()):
        style = {"path_id": path_id, "paint_type": d.get("type"),
                 "stroke_width_pt": d.get("width"), "dashes": d.get("dashes"), "stroke_color": d.get("color")}
        first, last = None, None
        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                out.append({**style, "type": "line", "p1": [p1.x, p1.y], "p2": [p2.x, p2.y]})
                if first is None or (last is not None and abs(last - p1) > .01):
                    first = p1
                last = p2
            elif item[0] == "re":
                r = item[1]
                out.append({**style, "type": "rect", "x": r.x0, "y": r.y0, "w": r.width, "h": r.height})
            elif item[0] == "qu":
                q = item[1]
                out.append({**style, "type": "quad", "points": [[p.x, p.y] for p in (q.ul, q.ur, q.lr, q.ll)]})
        if (d.get("closePath") and all(item[0] == "l" for item in d.get("items", []))
                and first is not None and last is not None and abs(first - last) > 0.01):
            out.append({**style, "type": "line", "p1": [last.x, last.y], "p2": [first.x, first.y]})
    if page.rotation:
        import pymupdf
        matrix = page.rotation_matrix
        def point(p):
            q = pymupdf.Point(*p) * matrix
            return [q.x, q.y]
        for v in out:
            if v["type"] == "line":
                v["p1"], v["p2"] = point(v["p1"]), point(v["p2"])
            elif v["type"] == "quad":
                v["points"] = [point(p) for p in v["points"]]
            elif v["type"] == "rect":
                r = pymupdf.Rect(v["x"], v["y"], v["x"]+v["w"], v["y"]+v["h"]) * matrix
                v.update(x=r.x0, y=r.y0, w=r.width, h=r.height)
    return out


def pdf_text_blocks(page) -> list[dict]:
    """Textes en points dans le même repère affiché que pdf_lines/get_pixmap."""
    import pymupdf
    out = []
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0: continue
        for line in b.get("lines", []):
            # CAD area labels often split "6,1 m" and superscript "2" into
            # separate spans. Never reinterpret the first span as a length.
            joined = "".join(sp.get("text", "") for sp in line.get("spans", []))
            area_ranges = [m.span() for m in re.finditer(r"\d+(?:[.,]\d+)?\s*m\s*[²³23](?![\d.,])", joined, re.I)]
            offset = 0
            for sp in line.get("spans", []):
                start, offset = offset, offset + len(sp.get("text", ""))
                if not sp.get("text", "").strip(): continue
                r = pymupdf.Rect(sp["bbox"]) * page.rotation_matrix
                direction = line.get("dir", (1, 0))
                origin = pymupdf.Point(0, 0) * page.rotation_matrix
                endpoint = pymupdf.Point(*direction) * page.rotation_matrix
                out.append({"text": sp["text"].strip(), "x": r.x0, "y": r.y0, "w": r.width, "h": r.height,
                            "direction": [endpoint.x-origin.x, endpoint.y-origin.y], "color": sp.get("color"),
                            "non_dimension": any(start < end and offset > begin for begin, end in area_ranges)})
    return out


def _segments(vectors: list[dict]) -> tuple[list[tuple], list[tuple], list[tuple]]:
    """→ (horizontaux [(y, xa, xb)], verticaux [(x, ya, yb)], courts obliques [(cx, cy, len)])."""
    hs, vs, ticks = [], [], []
    expanded = []
    for v in vectors or []:
        if v.get("type") == "rect":
            x, y, w, h = v["x"], v["y"], v["w"], v["h"]
            if w < 0.8 and h >= 2:
                vs.append((x + w / 2, y, y + h))
            elif h < 0.8 and w >= 2:
                hs.append((y + h / 2, x, x + w))
            else:
                pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                expanded.extend({"type": "line", "p1": a, "p2": b} for a, b in zip(pts, pts[1:] + pts[:1]))
            continue
        if v.get("type") == "quad":
            pts = v["points"]
            expanded.extend({"type": "line", "p1": a, "p2": b} for a, b in zip(pts, pts[1:] + pts[:1]))
        else:
            expanded.append(v)
    for v in expanded:
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
    """Read each text in its own drawing orientation, returning displayed coordinates.

    CAD exports can place buildings a fraction of a degree off the page axes.
    Use the PDF's text baseline, never the numeric dimension, to rectify them.
    Non-black dimension ink can separate leaders from hatch/furniture lines.
    """
    text_blocks = [t for t in text_blocks if not t.get("non_dimension")]
    if not any(t.get("direction") for t in text_blocks):
        return _extract_axis_dimensions(vectors, text_blocks, px_per_pt, pt_per_m)
    groups = {}
    for t in text_blocks:
        if _value_m(t.get("text") or "") is None:
            continue
        direction = t.get("direction") or [1, 0]
        angle = (math.degrees(math.atan2(direction[1], direction[0])) + 45) % 90 - 45
        angle = round(angle, 2)
        color = t.get("color")
        groups.setdefault((angle, color), []).append(t)
    dimensions, scales, numeric_count, candidates = [], [], 0, 0
    for (angle, color), texts in groups.items():
        selected = vectors
        if color not in (None, 0):
            rgb = ((color >> 16) & 255, (color >> 8) & 255, color & 255)
            same_ink = [v for v in vectors if v.get("stroke_color") is not None
                        and len(v["stroke_color"]) == 3
                        and all(abs(a * 255-b) <= 2 for a,b in zip(v["stroke_color"], rgb))]
            # A numeric label without matching line ink is not a proven cote.
            if len(same_ink) < 3:
                continue
            selected = same_ink
        rad = math.radians(angle)
        c, sn = math.cos(rad), math.sin(rad)
        def rotate(p):
            return [c*p[0]+sn*p[1], -sn*p[0]+c*p[1]]
        def unrotate(p):
            return [c*p[0]-sn*p[1], sn*p[0]+c*p[1]]
        rectified = []
        for v in vectors:
            if v["type"] == "line":
                rectified.append({**v, "p1": rotate(v["p1"]), "p2": rotate(v["p2"])})
            elif v["type"] in ("quad", "rect"):
                if v["type"] == "rect":
                    x,y,w,h = v["x"],v["y"],v["w"],v["h"]
                    points = [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]
                else:
                    points = v["points"]
                rectified.append({**v, "type":"quad", "points":[rotate(p) for p in points]})
        transformed_texts = []
        for t in texts:
            x,y,w,h = t["x"],t["y"],t["w"],t["h"]
            points = [rotate(p) for p in [[x,y],[x+w,y],[x+w,y+h],[x,y+h]]]
            left,top = min(p[0] for p in points),min(p[1] for p in points)
            transformed_texts.append({**t,"x":left,"y":top,"w":max(p[0] for p in points)-left,"h":max(p[1] for p in points)-top})
        all_rectified = rectified
        if selected is not vectors:
            rectified = [v for v in rectified if v.get("stroke_color") is not None
                         and len(v["stroke_color"]) == 3
                         and all(abs(a * 255-b) <= 2 for a,b in zip(v["stroke_color"], rgb))]
        result = _extract_axis_dimensions(rectified, transformed_texts, px_per_pt, pt_per_m,
                                          anchor_vectors=all_rectified)
        numeric_count += result.get("texts_numeric", 0)
        candidates += result.get("candidate_matches", result.get("matched", 0))
        if result.get("pt_per_m"):
            scales.append(result)
        for d in result["dimensions"]:
            a,b = unrotate([d["x1"],d["y1"]]),unrotate([d["x2"],d["y2"]])
            dimensions.append({**d,"x1":round(a[0],2),"y1":round(a[1],2),"x2":round(b[0],2),"y2":round(b[1],2),
                               "drawing_rotation_degrees":angle})
    # All groups must describe the same physical page scale before automatic use.
    values = [r["pt_per_m"] for r in scales]
    consensus = statistics.median(values) if values else pt_per_m
    conflict = bool(values and max(values) / min(values) > 1.02)
    source = "declared" if pt_per_m else "vector_consensus"
    return {"dimensions": [] if conflict else dimensions, "pt_per_m": None if conflict else consensus,
            "self_calibrated": bool(consensus and not pt_per_m), "scale_source": source,
            "declared_pt_per_m": pt_per_m, "scale_conflict": conflict,
            "texts_numeric": numeric_count, "matched": 0 if conflict else len(dimensions), "candidate_matches": candidates}


def _extract_axis_dimensions(vectors: list[dict], text_blocks: list[dict], px_per_pt: float,
                              pt_per_m: float | None = None, *, anchor_vectors=None) -> dict:
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
    ref = pt_per_m or _mode_ratio([a["pt_len"] / val for _, val, a, _ in pairs if a and val >= 0.5])
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
    used = pt_per_m or self_cal
    self_calibrated = bool(self_cal) and pt_per_m is None
    if not used:
        return {"dimensions": [], "pt_per_m": None, "self_calibrated": False,
                "texts_numeric": n_texts, "matched": 0, "candidate_matches": len(raw)}
    anchor_hs, anchor_vs, _ = _segments(anchor_vectors) if anchor_vectors is not None else (hs, vs, ticks)
    long_pt = 0.4 * used  # trait « du dessin » (mur, axe, semelle) : ≥ 0,40 m
    long_v = _with_axes(sorted(x for x, a, b in anchor_vs if b - a >= long_pt), used)
    long_h = _with_axes(sorted(y for y, a, b in anchor_hs if b - a >= long_pt), used)
    dims = []
    for r in raw:
        measured = r["pt_len"] / used
        if measured <= 0 or measured > 500 or abs(measured - r["value_m"]) > max(3.0, r["value_m"]):
            continue  # rattachement manifestement faux (ligne d'attache manquante) → on s'abstient
        # rattachement : chaque extrémité de la cote doit tomber sur un trait long du dessin (face/axe de mur)
        anchors = []
        for pt in (r["p1"], r["p2"]):
            pool, coord = (long_v, pt[0]) if r["orientation"] == "h" else (long_h, pt[1])
            gap = min((abs(coord - q) for q in pool), default=None)
            anchors.append(round(gap / used * 1000, 1) if gap is not None else None)
        uncertain = abs(measured - r["value_m"]) > max(.03, .02 * r["value_m"]) or any(a is None or a > 30.5 for a in anchors)
        dims.append({"unverified": uncertain, "x1": round(r["p1"][0] * px_per_pt, 2), "y1": round(r["p1"][1] * px_per_pt, 2),
                     "x2": round(r["p2"][0] * px_per_pt, 2), "y2": round(r["p2"][1] * px_per_pt, 2),
                     "value_m": round(r["value_m"], 4), "measured_m": round(measured, 4),
                     "raw_text": r["text"], "location": "cota vetorial PDF", "orientation": r["orientation"],
                     "anchor_mm": anchors})
    return {"dimensions": dims, "pt_per_m": round(used, 4), "self_calibrated": self_calibrated,
            "scale_source": "declared" if pt_per_m else "vector_consensus",
            "declared_pt_per_m": round(pt_per_m, 4) if pt_per_m else None,
            "texts_numeric": n_texts, "matched": len(dims)}


def _with_axes(pos: list[float], pt_per_m: float) -> list[float]:
    """Faces + axes : le milieu de deux traits longs distants de ≤ 0,50 m (épaisseur de mur) est un axe de cotation valide."""
    out = list(pos)
    for a, b in zip(pos, pos[1:]):
        if 0.05 * pt_per_m <= b - a <= 0.5 * pt_per_m:
            out.append((a + b) / 2)
    return out


def _mode_ratio(ratios: list[float]) -> float | None:
    ratios = sorted(ratios)
    if len(ratios) < 3:
        return None
    med = statistics.median(ratios)
    core = [x for x in ratios if abs(x - med) / med <= 0.02]
    return statistics.median(core) if len(core) >= max(3, len(ratios) // 2) else None


def pt_per_m_from_scale(denominator: int | None) -> float | None:
    return 1000.0 / denominator * PT_PER_MM if denominator else None


_SECTION_RE = re.compile(r"^(\d{2,3})\s*[xX×]\s*(\d{2,3})$")


def extract_elements(vectors: list[dict], text_blocks: list[dict], px_per_pt: float, pt_per_m: float) -> list[dict]:
    """Éléments dessinés (semelles, poutres, murs) étiquetés « 60x30 », « 13x13 »… : la largeur réellement dessinée
    (distance entre les deux traits parallèles qui encadrent l'étiquette) est comparée à la largeur annoncée (cm)."""
    if not pt_per_m:
        return []
    hs, vs, _ = _segments(vectors)
    out = []
    for t in text_blocks or []:
        m = _SECTION_RE.match((t.get("text") or "").strip())
        if not m:
            continue
        w_cm, h_cm = int(m.group(1)), int(m.group(2))
        tw, th = float(t.get("w") or 0), float(t.get("h") or 0)
        if tw <= 0 or th <= 0:
            continue
        cx, cy = float(t["x"]) + tw / 2, float(t["y"]) + th / 2
        want = w_cm / 100 * pt_per_m
        reach = max(2.5 * want, 3 * max(tw, th))
        # texte horizontal → bande horizontale (largeur mesurée verticalement) ; texte tourné → bande verticale
        if tw >= th:
            lines = sorted((y for y, a, b in hs if a - 1 <= cx <= b + 1 and abs(y - cy) <= reach and b - a >= 0.5 * want), key=lambda y: y)
            axis, orient = cy, "h"
        else:
            lines = sorted((x for x, a, b in vs if a - 1 <= cy <= b + 1 and abs(x - cx) <= reach and b - a >= 0.5 * want), key=lambda x: x)
            axis, orient = cx, "v"
        lines = [q for i, q in enumerate(lines) if i == 0 or q - lines[i - 1] > 0.3]
        if len(lines) < 2:
            continue
        best = None
        for i in range(len(lines)):
            for j in range(i + 1, len(lines)):
                width = lines[j] - lines[i]
                if width < 0.4 * want or width > 2.2 * want:
                    continue
                # la bande doit contenir l'étiquette ou en être très proche
                dist = 0.0 if lines[i] <= axis <= lines[j] else min(abs(axis - lines[i]), abs(axis - lines[j]))
                score = dist / want + abs(width - want) / want * 0.5
                if best is None or score < best[0]:
                    best = (score, lines[i], lines[j], width, dist)
        if not best or best[4] > 1.5 * want:
            continue
        _, q1, q2, width, _ = best
        measured = width / pt_per_m
        delta_mm = (measured - w_cm / 100) * 1000
        if orient == "h":
            seg = (cx, q1, cx, q2)
        else:
            seg = (q1, cy, q2, cy)
        out.append({"label": t["text"].strip(), "w_cm": w_cm, "h_cm": h_cm, "orientation": orient,
                    "measured_w_m": round(measured, 4), "delta_mm": round(delta_mm, 1),
                    "x1": round(seg[0] * px_per_pt, 2), "y1": round(seg[1] * px_per_pt, 2),
                    "x2": round(seg[2] * px_per_pt, 2), "y2": round(seg[3] * px_per_pt, 2),
                    "tx": round(cx * px_per_pt, 1), "ty": round(cy * px_per_pt, 1)})
    return out


def _dims_pt(dims_px: list[dict], px_per_pt: float) -> list[dict]:
    return [{"orientation": d.get("orientation"), "p1": (d["x1"] / px_per_pt, d["y1"] / px_per_pt),
             "p2": (d["x2"] / px_per_pt, d["y2"] / px_per_pt)} for d in dims_px or []]


def extract_auto_spans(vectors: list[dict], px_per_pt: float, pt_per_m: float, dims: list[dict],
                       min_span_m: float = 0.30, max_out: int = 60) -> list[dict]:
    """Cotes NON affichées : entre deux traits longs parallèles voisins (faces/axes de murs), la distance dessinée est
    mesurée automatiquement ; si aucune cote inscrite ne couvre ce tronçon (deux extrémités alignées à ≤ 10 mm),
    le tronçon est renvoyé comme « mesure automatique »."""
    if not pt_per_m:
        return []
    hs, vs, _ = _segments(vectors)
    long_pt = 0.4 * pt_per_m
    tol = 0.010 * pt_per_m
    out = []
    for orient, lines in (("h", [(x, a, b) for x, a, b in vs if b - a >= long_pt]),
                          ("v", [(y, a, b) for y, a, b in hs if b - a >= long_pt])):
        lines.sort()
        # regroupement des traits quasi confondus (double trait de mur = 2 faces distinctes si > 10 mm)
        groups: list[list[tuple]] = []
        for ln in lines:
            if groups and ln[0] - groups[-1][-1][0] <= 0.3:
                groups[-1].append(ln)
            else:
                groups.append([ln])
        pos = [(sum(g[0] for g in grp) / len(grp), min(g[1] for g in grp), max(g[2] for g in grp)) for grp in groups]
        cotes = [(min(d["p1"][0], d["p2"][0]), max(d["p1"][0], d["p2"][0])) if orient == "h"
                 else (min(d["p1"][1], d["p2"][1]), max(d["p1"][1], d["p2"][1])) for d in dims if d.get("orientation") == orient]
        for (p1, a1, b1), (p2, a2, b2) in zip(pos, pos[1:]):
            span = p2 - p1
            if span < min_span_m * pt_per_m:
                continue
            ov_a, ov_b = max(a1, a2), min(b1, b2)
            if ov_b - ov_a < 0.2 * pt_per_m:  # les deux traits ne se font pas face
                continue
            if any(abs(c1 - p1) <= tol and abs(c2 - p2) <= tol for c1, c2 in cotes):
                continue
            mid = (ov_a + ov_b) / 2
            seg = (p1, mid, p2, mid) if orient == "h" else (mid, p1, mid, p2)
            out.append({"orientation": orient, "measured_m": round(span / pt_per_m, 3),
                        "x1": round(seg[0] * px_per_pt, 2), "y1": round(seg[1] * px_per_pt, 2),
                        "x2": round(seg[2] * px_per_pt, 2), "y2": round(seg[3] * px_per_pt, 2)})
    out.sort(key=lambda s: -s["measured_m"])
    return out[:max_out]
