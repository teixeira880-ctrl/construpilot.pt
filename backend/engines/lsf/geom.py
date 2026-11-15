"""Geometria base do motor LSF — unidades mm, eixo Z vertical. Sem dependências."""
from __future__ import annotations

import math

EPS = 1e-6


def r1(x: float) -> float:
    """Arredonda a 0,1 mm (comprimentos de corte)."""
    return math.floor(x * 10 + 0.5) / 10


def add(a, b):
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def mul(a, k):
    return [a[0] * k, a[1] * k, a[2] * k]


def section_outline(p: dict) -> list[tuple[float, float]]:
    """Contorno real da secção de parede fina (espessura t, cantos vivos). (u, v): v ao longo da alma (0..h),
    u ao longo dos banzos (0..b); alma em u = 0..t."""
    h, t = p["h"], p["t"]
    b = p.get("b", 0)
    c = p.get("c") or 0
    if p["tipo"] == "C" and c > 0:
        return [(b, c), (b, 0), (0, 0), (0, h), (b, h), (b, h - c), (b - t, h - c), (b - t, h - t), (t, h - t), (t, t), (b - t, t), (b - t, c)]
    if p["tipo"] in ("C", "U"):
        return [(b, 0), (0, 0), (0, h), (b, h), (b, h - t), (t, h - t), (t, t), (b, t)]
    if p["tipo"] == "F":
        return [(0, 0), (t, 0), (t, h), (0, h)]
    raise ValueError(f"Tipo de perfil desconhecido: {p['tipo']}")


def poly_area(pts) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def _f(x) -> str:
    s = f"{x:g}"
    return s.replace(".", ",")


def profile_name(p: dict) -> str:
    if p["tipo"] == "F":
        return f"Fita {_f(p['h'])}×{_f(p['t'])}"
    if p["tipo"] == "C" and p.get("c"):
        return f"C{_f(p['h'])}×{_f(p['b'])}×{_f(p['c'])}×{_f(p['t'])}"
    return f"{p['tipo']}{_f(p['h'])}×{_f(p['b'])}×{_f(p['t'])}"


def kg_per_m(p: dict, dens: float = 7850) -> float:
    """Massa linear (kg/m) pela área real da secção modelada."""
    return poly_area(section_outline(p)) * 1e-6 * dens


def member_bbox(o, u, v, w, b, h, L):
    mn = [math.inf] * 3
    mx = [-math.inf] * 3
    for a in (0, b):
        for c in (0, h):
            for d in (0, L):
                p = [o[i] + u[i] * a + v[i] * c + w[i] * d for i in range(3)]
                for i in range(3):
                    mn[i] = min(mn[i], p[i])
                    mx[i] = max(mx[i], p[i])
    return {"min": mn, "max": mx}


def subtract_intervals(a: float, b: float, cuts) -> list[list[float]]:
    segs = [[a, b]]
    for c0, c1 in cuts:
        nxt = []
        for s0, s1 in segs:
            if c1 <= s0 + EPS or c0 >= s1 - EPS:
                nxt.append([s0, s1])
                continue
            if c0 > s0 + EPS:
                nxt.append([s0, c0])
            if c1 < s1 - EPS:
                nxt.append([c1, s1])
        segs = nxt
    return [s for s in segs if s[1] - s[0] > EPS]


def subtract_rects(r: dict, holes) -> list[dict]:
    """Retângulo menos retângulos → sub-retângulos disjuntos (decomposição em grelha, faixas fundidas)."""
    hs = []
    for h in holes:
        q = {"x0": max(r["x0"], h["x0"]), "x1": min(r["x1"], h["x1"]), "z0": max(r["z0"], h["z0"]), "z1": min(r["z1"], h["z1"])}
        if q["x1"] - q["x0"] > EPS and q["z1"] - q["z0"] > EPS:
            hs.append(q)
    if not hs:
        return [dict(r)]
    xs = sorted({r["x0"], r["x1"], *[v for h in hs for v in (h["x0"], h["x1"])]})
    zs = sorted({r["z0"], r["z1"], *[v for h in hs for v in (h["z0"], h["z1"])]})
    out = []
    for j in range(len(zs) - 1):
        cur = None
        for i in range(len(xs) - 1):
            cx, cz = (xs[i] + xs[i + 1]) / 2, (zs[j] + zs[j + 1]) / 2
            inside = any(h["x0"] < cx < h["x1"] and h["z0"] < cz < h["z1"] for h in hs)
            if inside:
                if cur:
                    out.append(cur)
                    cur = None
                continue
            if cur:
                cur["x1"] = xs[i + 1]
            else:
                cur = {"x0": xs[i], "x1": xs[i + 1], "z0": zs[j], "z1": zs[j + 1]}
        if cur:
            out.append(cur)
    return out


def rect_area(r) -> float:
    return (r["x1"] - r["x0"]) * (r["z1"] - r["z0"])


def ffd(lengths, bar: float, kerf: float = 0):
    """First-Fit Decreasing — corte de barras comerciais."""
    bars, too_long = [], []
    for L in sorted(lengths, reverse=True):
        if L > bar:
            too_long.append(L)
            continue
        for b in bars:
            need = L + (kerf if b["pieces"] else 0)
            if b["free"] >= need - EPS:
                b["pieces"].append(L)
                b["free"] -= need
                break
        else:
            bars.append({"pieces": [L], "free": bar - L})
    return {"bars": bars, "too_long": too_long}


def plano_corte(pieces, W: float, H: float, kerf: float = 3, rodar: bool = True):
    """Plano de corte 2D (MaxRects, melhor encaixe pelo lado curto) com espessura de corte.
    pieces: [{w, h, ref}] → {"folhas": [[peça posicionada…]], "fora": [...]}"""
    ps = sorted(({**p, "i": i} for i, p in enumerate(pieces)), key=lambda p: (-(p["w"] * p["h"]), -max(p["w"], p["h"])))
    sheets, fora = [], []
    for p in ps:
        cand = [(p["w"], p["h"], False)]
        if rodar and abs(p["w"] - p["h"]) > EPS:
            cand.append((p["h"], p["w"], True))
        if not any(w <= W + EPS and h <= H + EPS for w, h, _ in cand):
            fora.append(p)
            continue
        best = None

        def try_in(s):
            nonlocal best
            for f in s["free"]:
                for w0, h0, rot in cand:
                    if w0 > f["w"] + EPS or h0 > f["h"] + EPS:
                        continue
                    wf, hf = min(w0 + kerf, f["w"]), min(h0 + kerf, f["h"])
                    ss, ls = min(f["w"] - wf, f["h"] - hf), max(f["w"] - wf, f["h"] - hf)
                    if best is None or ss < best["ss"] - EPS or (abs(ss - best["ss"]) < EPS and ls < best["ls"]):
                        best = {"s": s, "f": f, "w": wf, "h": hf, "w0": w0, "h0": h0, "rot": rot, "ss": ss, "ls": ls}

        for s in sheets:
            try_in(s)
        if best is None:
            s = {"free": [{"x": 0, "y": 0, "w": W, "h": H}], "pecas": []}
            sheets.append(s)
            try_in(s)
        s, f = best["s"], best["f"]
        r = {"x": f["x"], "y": f["y"], "w": best["w"], "h": best["h"]}
        s["pecas"].append({**p, "x": f["x"], "y": f["y"], "w": best["w0"], "h": best["h0"], "rodada": best["rot"]})
        nf = []
        for fr in s["free"]:
            if r["x"] >= fr["x"] + fr["w"] - EPS or r["x"] + r["w"] <= fr["x"] + EPS or r["y"] >= fr["y"] + fr["h"] - EPS or r["y"] + r["h"] <= fr["y"] + EPS:
                nf.append(fr)
                continue
            if r["x"] > fr["x"] + EPS:
                nf.append({"x": fr["x"], "y": fr["y"], "w": r["x"] - fr["x"], "h": fr["h"]})
            if r["x"] + r["w"] < fr["x"] + fr["w"] - EPS:
                nf.append({"x": r["x"] + r["w"], "y": fr["y"], "w": fr["x"] + fr["w"] - r["x"] - r["w"], "h": fr["h"]})
            if r["y"] > fr["y"] + EPS:
                nf.append({"x": fr["x"], "y": fr["y"], "w": fr["w"], "h": r["y"] - fr["y"]})
            if r["y"] + r["h"] < fr["y"] + fr["h"] - EPS:
                nf.append({"x": fr["x"], "y": r["y"] + r["h"], "w": fr["w"], "h": fr["y"] + fr["h"] - r["y"] - r["h"]})

        def contido(a, b):
            return a["x"] >= b["x"] - EPS and a["y"] >= b["y"] - EPS and a["x"] + a["w"] <= b["x"] + b["w"] + EPS and a["y"] + a["h"] <= b["y"] + b["h"] + EPS

        keep = []
        for i, a in enumerate(nf):
            dominated = False
            for j, b in enumerate(nf):
                if i == j or not contido(a, b):
                    continue
                igual = contido(b, a)
                if not igual or j < i:
                    dominated = True
                    break
            if not dominated:
                keep.append(a)
        s["free"] = keep
    return {"folhas": [s["pecas"] for s in sheets], "fora": fora}
