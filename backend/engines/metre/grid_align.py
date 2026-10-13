"""Plan (PDF) ↔ model (DXF) registration through the grid axes both documents carry (bubbles « X1 », « Y3 »… and their axis lines).
A similarity transform (scale, rotation, translation) is fitted on the intersections of the axes present in BOTH files and its scale is
checked against the declared drawing scale. Without at least two common intersections, nothing is registered."""
import math
import re
from collections import Counter

AXIS_LABEL = re.compile(r"^[A-Z]{1,2}\d{1,2}$")


def _center(r):
    return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)


def pdf_grid_axes(page) -> dict:
    """Bubbles = circle-like stroked paths (4 béziers, 25–60 pt) containing exactly one axis label; axis direction = dominant direction of the
    line items whose supporting line passes through the bubble centre (the dash-dot axis line)."""
    words = page.get_text("words")
    drawings = page.get_drawings()
    bubbles = []
    for d in drawings:
        types = "".join(it[0] for it in d["items"])
        r = d["rect"]
        if not types.startswith("cccc") or not (25 <= r.width <= 60) or abs(r.width - r.height) > 2:
            continue
        inside = [w[4] for w in words if r.x0 <= (w[0] + w[2]) / 2 <= r.x1 and r.y0 <= (w[1] + w[3]) / 2 <= r.y1]
        if len(inside) == 1 and AXIS_LABEL.match(inside[0]):
            bubbles.append({"label": inside[0], "cx": (r.x0 + r.x1) / 2, "cy": (r.y0 + r.y1) / 2, "r": r.width / 2})
    segs = [(it[1], it[2]) for d in drawings for it in d["items"] if it[0] == "l"]
    axes = {}
    for b in bubbles:
        dirs = Counter()
        for a, c in segs:
            L = math.hypot(c.x - a.x, c.y - a.y)
            if L < 12:
                continue
            ux, uy = (c.x - a.x) / L, (c.y - a.y) / L
            dist_line = abs((b["cx"] - a.x) * uy - (b["cy"] - a.y) * ux)
            near = min(math.hypot(a.x - b["cx"], a.y - b["cy"]), math.hypot(c.x - b["cx"], c.y - b["cy"]))
            if dist_line <= 1.5 and b["r"] - 2 <= near <= 600:
                ang = round(math.degrees(math.atan2(uy, ux)) % 180, 1)
                dirs[ang] += L
        if dirs:
            ang = dirs.most_common(1)[0][0]
            axes.setdefault(b["label"], []).append({"point": (b["cx"], b["cy"]), "angle_deg": ang})
    lines = {}
    for label, items in axes.items():
        if len(items) >= 2:
            (x0, y0), (x1, y1) = items[0]["point"], items[1]["point"]
            ang = math.degrees(math.atan2(y1 - y0, x1 - x0)) % 180
        else:
            (x0, y0), ang = items[0]["point"], items[0]["angle_deg"]
        lines[label] = {"point": (x0, y0), "angle_deg": ang, "bubbles": len(items)}
    return {"bubbles": bubbles, "axes": lines}


def dxf_grid_axes(msp, unit_to_m: float) -> dict:
    """S-GRID lines labelled by the nearest grid-identifier text to one of their ends (layer names containing GRID)."""
    lines, labels = [], []
    for e in msp:
        lay = e.dxf.layer.upper()
        if "GRID" not in lay and "QUADRILLAGE" not in lay and "AXE" not in lay:
            continue
        t = e.dxftype()
        if t == "LINE":
            lines.append(((e.dxf.start.x * unit_to_m, e.dxf.start.y * unit_to_m), (e.dxf.end.x * unit_to_m, e.dxf.end.y * unit_to_m)))
        elif t in ("TEXT", "MTEXT"):
            txt = (e.dxf.text if t == "TEXT" else e.plain_text()).strip()
            if AXIS_LABEL.match(txt):
                labels.append((txt, (e.dxf.insert.x * unit_to_m, e.dxf.insert.y * unit_to_m)))
    axes = {}
    for a, b in lines:
        best = None
        for txt, p in labels:
            d = min(math.hypot(p[0] - a[0], p[1] - a[1]), math.hypot(p[0] - b[0], p[1] - b[1]))
            if best is None or d < best[0]:
                best = (d, txt)
        if best and best[0] <= 1.5:
            axes[best[1]] = {"point": a, "angle_deg": math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180, "end": b}
    return {"axes": axes}


def _intersect(l1: dict, l2: dict):
    (x1, y1), a1 = l1["point"], math.radians(l1["angle_deg"])
    (x2, y2), a2 = l2["point"], math.radians(l2["angle_deg"])
    d1, d2 = (math.cos(a1), math.sin(a1)), (math.cos(a2), math.sin(a2))
    den = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(den) < 1e-6:
        return None
    t = ((x2 - x1) * d2[1] - (y2 - y1) * d2[0]) / den
    return (x1 + t * d1[0], y1 + t * d1[1])


def fit_similarity(src: list[tuple], dst: list[tuple]) -> dict:
    """Least-squares similarity (Umeyama, 2-D, no reflection) mapping src → dst."""
    n = len(src)
    mx, my = sum(p[0] for p in src) / n, sum(p[1] for p in src) / n
    nx, ny = sum(p[0] for p in dst) / n, sum(p[1] for p in dst) / n
    sxx = sxy = syx = syy = var = 0.0
    for (x, y), (u, v) in zip(src, dst):
        dx, dy, du, dv = x - mx, y - my, u - nx, v - ny
        sxx += dx * du; sxy += dx * dv; syx += dy * du; syy += dy * dv
        var += dx * dx + dy * dy
    ang = math.atan2(sxy - syx, sxx + syy)
    scale = ((sxx + syy) * math.cos(ang) + (sxy - syx) * math.sin(ang)) / var
    c, s = scale * math.cos(ang), scale * math.sin(ang)
    tx, ty = nx - (c * mx - s * my), ny - (s * mx + c * my)
    T = {"a": c, "b": -s, "c": s, "d": c, "tx": tx, "ty": ty, "scale": scale, "rotation_deg": round(math.degrees(ang), 3)}
    T["residual"] = round(max(math.hypot(*(apply(T, *p)[i] - q[i] for i in range(2))) for p, q in zip(src, dst)), 4)
    return T


def apply(T: dict, x: float, y: float) -> tuple:
    return (T["a"] * x + T["b"] * y + T["tx"], T["c"] * x + T["d"] * y + T["ty"])


def register(pdf_axes: dict, dxf_axes: dict, *, declared_pt_per_m: float | None, flip_y: bool = True) -> dict:
    """PDF points (y down) → DXF metres. PDF y is flipped first so the fit stays a proper rotation. Uses every pair of common axes that intersect."""
    common = sorted(set(pdf_axes) & set(dxf_axes))
    src, dst, used = [], [], []
    for i, a in enumerate(common):
        for b in common[i + 1:]:
            pa = _intersect(pdf_axes[a], pdf_axes[b])
            pd = _intersect(dxf_axes[a], dxf_axes[b])
            if pa and pd:
                src.append((pa[0], -pa[1] if flip_y else pa[1])); dst.append(pd); used.append(f"{a}∩{b}")
    if len(src) < 2:
        return {"ok": False, "common_axes": common, "error": "moins de deux intersections d'axes communes : pas de recalage plan ↔ DXF"}
    T = fit_similarity(src, dst)
    T["flip_y"] = flip_y
    out = {"ok": True, "transform": T, "common_axes": common, "intersections_used": used, "residual_m": T["residual"], "m_per_pt": round(T["scale"], 6)}
    if declared_pt_per_m:
        ratio = T["scale"] * declared_pt_per_m
        out["scale_vs_declared"] = round(ratio, 4)
        out["scale_state"] = "confirmed" if abs(ratio - 1) <= 0.02 else "to_clarify"
    return out


def to_model(reg: dict, x_pt: float, y_pt: float) -> tuple:
    T = reg["transform"]
    return apply(T, x_pt, -y_pt if T.get("flip_y") else y_pt)
