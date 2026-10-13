"""Oblique / dashed vector dimensions (Arche-style rebar plans): rotated numeric labels along panel edges or bar runs.

A label « 240 » is confirmed when a collinear chain of segments (dashes merged) runs parallel to the text right next to it and the
distance between the two tick marks bracketing the label (or, failing ticks, the chain extent) equals the printed value at the
declared scale. Nothing is inferred from text alone; unmatched labels are reported as such.
"""
import math
import re
from collections import defaultdict

NUM = re.compile(r"^\d{2,4}$")
ANGLE_STEP = 1.0     # degrees, direction buckets
OFFSET_TOL = 1.2     # pt, collinearity
GAP_TOL = 14.0       # pt, max gap between dashes of one chain
TICK_MIN, TICK_MAX = 4.0, 13.0


def _segments(page):
    out = []
    for d in page.get_drawings():
        for it in d.get("items", []):
            if it[0] == "l":
                a, b = it[1], it[2]
                L = math.hypot(b.x - a.x, b.y - a.y)
                if L >= 0.8:
                    out.append((a.x, a.y, b.x, b.y, L))
            elif it[0] == "re":
                r = it[1]
                pts = [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)]
                for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
                    L = math.hypot(x2 - x1, y2 - y1)
                    if L >= 0.8:
                        out.append((x1, y1, x2, y2, L))
    return out


def _angle_key(dx, dy):
    a = math.degrees(math.atan2(dy, dx)) % 180.0
    return round(a / ANGLE_STEP) % int(180 / ANGLE_STEP)


def build_chains(segments):
    """Merge collinear, near-touching segments into chains: {(angle_key, offset_key): [(along0, along1, x0,y0,x1,y1)]}."""
    groups = defaultdict(list)
    for x1, y1, x2, y2, L in segments:
        k = _angle_key(x2 - x1, y2 - y1)
        ang = math.radians(k * ANGLE_STEP)
        ux, uy = math.cos(ang), math.sin(ang)
        off = x1 * uy - y1 * ux
        a0, a1 = sorted((x1 * ux + y1 * uy, x2 * ux + y2 * uy))
        groups[(k, round(off / OFFSET_TOL))].append((a0, a1))
    chains = []
    for (k, offk), spans in groups.items():
        spans.sort()
        cur = list(spans[0])
        ang = math.radians(k * ANGLE_STEP)
        for a0, a1 in spans[1:]:
            if a0 - cur[1] <= GAP_TOL:
                cur[1] = max(cur[1], a1)
            else:
                chains.append((k, offk * OFFSET_TOL, cur[0], cur[1], ang))
                cur = [a0, a1]
        chains.append((k, offk * OFFSET_TOL, cur[0], cur[1], ang))
    return chains


def _ticks(segments):
    return [((x1 + x2) / 2, (y1 + y2) / 2, math.atan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2, L in segments if TICK_MIN <= L <= TICK_MAX]


def numeric_labels(page, exclude_rects=()):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            dx, dy = line["dir"]
            for s in line["spans"]:
                t = s["text"].strip()
                if not NUM.match(t):
                    continue
                x0, y0, x1, y1 = s["bbox"]
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                if any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in exclude_rects):
                    continue
                out.append({"text": t, "value_m": int(t) / 100, "cx": cx, "cy": cy, "dir": (dx, dy), "size": s["size"], "bbox": [round(v, 1) for v in s["bbox"]]})
    return out


def _candidates(lab, by_key, ticks, pt_per_m):
    """Every parallel chain next to the label with its measured length (ticks bracketing the label, else chain extent)."""
    dx, dy = lab["dir"]
    k = _angle_key(dx, dy)  # line["dir"] is already in page space (y down)
    ang = math.radians(k * ANGLE_STEP)
    ux, uy = math.cos(ang), math.sin(ang)
    off = lab["cx"] * uy - lab["cy"] * ux
    along = lab["cx"] * ux + lab["cy"] * uy
    reach = 3.2 * lab["size"]
    out = []
    for kk in (k, (k - 1) % 180, (k + 1) % 180):
        for c in by_key.get(kk, []):
            perp = abs(c[1] - off)
            if perp > reach or not (c[2] - reach <= along <= c[3] + reach) or c[3] - c[2] < 4:
                continue
            on = []
            for tx, ty, ta in ticks:
                if abs((tx * uy - ty * ux) - c[1]) <= 2.0:
                    a = tx * ux + ty * uy
                    if c[2] - 3 <= a <= c[3] + 3 and abs(math.sin(ta - ang)) > 0.5:
                        on.append(a)
            left = max((a for a in on if a < along), default=None)
            right = min((a for a in on if a > along), default=None)
            if left is not None and right is not None:
                length_pt, bounds, src = right - left, (left, right), "ticks"
            else:
                length_pt, bounds, src = c[3] - c[2], (c[2], c[3]), "chain"
            out.append({"perp": perp, "length_pt": length_pt, "bounds": bounds, "src": src, "chain": c, "ang": ang, "ux": ux, "uy": uy})
    return out


def calibrate(labels, by_key, ticks, declared_pt_per_m: float) -> dict:
    """Actual print scale from labels whose adjacent line is within ±4 % of the printed value (fit-to-page exports shrink the sheet)."""
    ratios = []
    for lab in labels:
        for cand in _candidates(lab, by_key, ticks, declared_pt_per_m):
            r = cand["length_pt"] / (lab["value_m"] or 1)
            if lab["value_m"] >= 0.5 and abs(r / declared_pt_per_m - 1) <= 0.04:
                ratios.append(r)
    if len(ratios) < 5:
        return {"pt_per_m": declared_pt_per_m, "samples": len(ratios), "self_calibrated": False}
    ratios.sort()
    med = ratios[len(ratios) // 2]
    core = [r for r in ratios if abs(r / med - 1) <= 0.006]
    used = sum(core) / len(core) if core else med
    return {"pt_per_m": used, "samples": len(core), "self_calibrated": abs(used / declared_pt_per_m - 1) > 0.003,
            "print_ratio": round(used / declared_pt_per_m, 4)}


def match_labels(page, pt_per_m: float, *, exclude_rects=(), tol_m: float = 0.01) -> dict:
    segs = _segments(page)
    chains = build_chains(segs)
    ticks = _ticks(segs)
    by_key = defaultdict(list)
    for c in chains:
        by_key[c[0]].append(c)
    labels = numeric_labels(page, exclude_rects)
    cal = calibrate(labels, by_key, ticks, pt_per_m)
    declared, pt_per_m = pt_per_m, cal["pt_per_m"]
    dims, unmatched = [], []
    for lab in labels:
        best = None
        for cand in _candidates(lab, by_key, ticks, pt_per_m):
            measured = cand["length_pt"] / pt_per_m
            err = abs(measured - lab["value_m"])
            key = (err, cand["perp"])
            if best is None or key < best[0]:
                best = (key, measured, cand)
        if best and best[0][0] <= max(tol_m, 0.004 * lab["value_m"]):
            _, measured, cand = best
            c, ux, uy, ang = cand["chain"], cand["ux"], cand["uy"], cand["ang"]
            a0, a1 = cand["bounds"]
            ox, oy = c[1] * uy, -c[1] * ux
            dims.append({"raw_text": lab["text"], "value_m": lab["value_m"], "measured_m": round(measured, 4), "difference_mm": round((measured - lab["value_m"]) * 1000, 1),
                         "x1": round(ox + a0 * ux, 2), "y1": round(oy + a0 * uy, 2), "x2": round(ox + a1 * ux, 2), "y2": round(oy + a1 * uy, 2),
                         "angle_deg": round(math.degrees(ang), 1), "bounds_source": cand["src"], "label_bbox": lab["bbox"],
                         "location": "cota oblíqua (texto + linha paralela)", "state": "confirmed"})
        else:
            unmatched.append({"raw_text": lab["text"], "value_m": lab["value_m"], "label_bbox": lab["bbox"],
                              "nearest_measured_m": round(best[1], 3) if best else None, "state": "indeterminate"})
    return {"pt_per_m": round(pt_per_m, 4), "declared_pt_per_m": round(declared, 4), "calibration": cal, "labels": len(labels), "dimensions": dims, "unmatched": unmatched,
            "note": ("Cota confirmada = texto numérico + linha paralela adjacente cujo comprimento entre marcas (ticks) ou extensão vale o valor impresso (±1 cm ou 0,4 %) à escala real da impressão (autocalibrada nas próprias cotas). Nenhum valor deduzido apenas do texto.")}
