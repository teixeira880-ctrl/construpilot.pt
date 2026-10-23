"""Geometria estrutural derivada do levantamento : apoios, vigas automáticas, painéis de laje e áreas de influência.

- Vigas de bordadura em todo o contorno (troços entre apoios ; o troço coincidente com uma parede é substituído pela parede).
- Vigas interiores por « raios » : a partir de cada pilar de fachada (para o interior), de cada pilar interior (4 direções) e de cada
  extremo de parede (perpendicular à parede), até ao primeiro apoio encontrado (pilar, parede, face de núcleo) a ≤ 8,5 m ;
  um raio que só encontra a viga de fachada oposta cria uma viga secundária se ≤ 6,0 m.
- Painéis : regiões de laje delimitadas por vigas, paredes, núcleos e contorno (rasterização a 5 cm e preenchimento) ; as regiões
  não retangulares são decompostas em retângulos (bordo livre na linha de corte, a favor da segurança).
- Áreas de influência : cada ponto da laje (e das varandas) é atribuído ao elemento vertical mais próximo.
"""
from __future__ import annotations

import math
from collections import deque

import numpy as np

from .modelo import Spec

STEP = 0.05
TOL_HIT = 0.35        # tolerância lateral para um raio « encontrar » um apoio (m)
MAX_BEAM = 8.5
MAX_SECONDARY = 6.0
MIN_BEAM = 1.0


# ------------------------------------------------------------------ apoios
def absorbed(S: Spec, c) -> dict | None:
    """Parede que absorve o pilar (pilar no alinhamento e dentro da extensão da parede)."""
    for w in S.walls:
        if w["axis"] == "Y" and abs(c["x"] - w["x0"]) <= w["t"] / 2 + 0.06 and w["y0"] - 0.06 <= c["y"] <= w["y1"] + 0.06:
            return w
        if w["axis"] == "X" and abs(c["y"] - w["y0"]) <= w["t"] / 2 + 0.06 and w["x0"] - 0.06 <= c["x"] <= w["x1"] + 0.06:
            return w
    return None


def free_columns(S: Spec) -> list[dict]:
    return [c for c in S.columns if absorbed(S, c) is None]


def core_faces(c) -> list[tuple]:
    x0, y0, x1, y1 = c["box"]
    return [((x0, y0), (x1, y0)), ((x0, y1), (x1, y1)), ((x0, y0), (x0, y1)), ((x1, y0), (x1, y1))]


def supports(S: Spec, garage=False) -> list[dict]:
    """Elementos verticais para as áreas de influência : pilares (não absorvidos), paredes (segmento), faces de núcleo."""
    els = [{"id": c["id"], "kind": "pilar", "x": c["x"], "y": c["y"], "seg": None} for c in free_columns(S)]
    for w in S.walls:
        els.append({"id": w["id"], "kind": "parede", "x": (w["x0"] + w["x1"]) / 2, "y": (w["y0"] + w["y1"]) / 2,
                    "seg": ((w["x0"], w["y0"]), (w["x1"], w["y1"]))})
    for c in S.cores:
        for seg in core_faces(c):
            els.append({"id": c["id"], "kind": "nucleo", "x": (seg[0][0] + seg[1][0]) / 2, "y": (seg[0][1] + seg[1][1]) / 2, "seg": seg})
    if garage:
        els += [{"id": c["id"], "kind": "pilar_cave", "x": c["x"], "y": c["y"], "seg": None} for c in S.bcols]
        for w in S.bwalls:
            a, b = S.bpoly[w["i0"]], S.bpoly[w["i1"]]
            els.append({"id": w["name"], "kind": "muro", "x": (a[0] + b[0]) / 2, "y": (a[1] + b[1]) / 2, "seg": (a, b)})
    return els


def dist_el(px, py, e) -> float:
    if e["seg"] is None:
        return math.hypot(px - e["x"], py - e["y"])
    return dist_seg(px, py, *e["seg"])


def dist_seg(px, py, a, b) -> float:
    (ax, ay), (bx, by) = a, b
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - ax - t * vx, py - ay - t * vy)


# ------------------------------------------------------------------ vigas
def _on_facade(S, x, y, tol=0.06):
    return [s for s, ok in (("y0", abs(y) < tol), ("y1", abs(y - S.B) < tol), ("x0", abs(x) < tol), ("x1", abs(x - S.L) < tol)) if ok]


def _ray_hit(S: Spec, x, y, dx, dy, src_id):
    """Primeiro apoio encontrado por um raio : → (distância, ponto, tipo) ou None."""
    best = None

    def take(d, p, kind):
        nonlocal best
        if d > 0.3 and (best is None or d < best[0]):
            best = (d, p, kind)
    for c in S.columns:
        if c["id"] == src_id:
            continue
        rx, ry = c["x"] - x, c["y"] - y
        along = rx * dx + ry * dy
        lat = abs(rx * dy - ry * dx)
        if along > 0.3 and lat <= TOL_HIT:
            take(along, (c["x"] if dx == 0 else c["x"], c["y"] if dy == 0 else c["y"]), "pilar")
    for w in S.walls:
        if w["id"] == src_id:
            continue
        segs = [((w["x0"], w["y0"]), (w["x1"], w["y1"]))]
        for a, b in segs:
            d = _ray_seg(x, y, dx, dy, a, b)
            if d is not None:
                take(d[0], d[1], "parede")
    for c in S.cores:
        for a, b in core_faces(c):
            d = _ray_seg(x, y, dx, dy, a, b)
            if d is not None:
                take(d[0], d[1], "nucleo")
    # fachada oposta (viga de bordadura)
    for val, axis in ((0.0, "x"), (S.L, "x"), (0.0, "y"), (S.B, "y")):
        if axis == "x" and dx != 0:
            d = (val - x) / dx
            if d > 0.3:
                take(d + 1e-3, (val, y), "fachada")
        if axis == "y" and dy != 0:
            d = (val - y) / dy
            if d > 0.3:
                take(d + 1e-3, (x, val), "fachada")
    return best


def _ray_seg(x, y, dx, dy, a, b):
    """Interseção de um raio axial com um segmento axial (com tolerância TOL_HIT nos extremos)."""
    (ax, ay), (bx, by) = a, b
    if dx != 0:              # raio horizontal (y constante)
        if abs(ax - bx) < 1e-6:          # segmento vertical
            lo, hi = sorted((ay, by))
            if lo - TOL_HIT <= y <= hi + TOL_HIT:
                d = (ax - x) / dx
                if d > 0:
                    return d, (ax, min(max(y, lo), hi) if lo <= y <= hi else y)
        else:                             # segmento horizontal colinear (extremo)
            if abs(ay - y) <= TOL_HIT:
                for px in (ax, bx):
                    d = (px - x) / dx
                    if d > 0:
                        return d, (px, y)
        return None
    if abs(ay - by) < 1e-6:              # raio vertical × segmento horizontal
        lo, hi = sorted((ax, bx))
        if lo - TOL_HIT <= x <= hi + TOL_HIT:
            d = (ay - y) / dy
            if d > 0:
                return d, (x, ay)
    else:
        if abs(ax - x) <= TOL_HIT:
            for py in (ay, by):
                d = (py - y) / dy
                if d > 0:
                    return d, (x, py)
    return None


def _inside_core(S, x, y, margin=0.05):
    for c in S.cores:
        x0, y0, x1, y1 = c["box"]
        if x0 + margin < x < x1 - margin and y0 + margin < y < y1 - margin:
            return True
    return False


def auto_beams(S: Spec) -> list[dict]:
    """Linhas de vigas [{id, a, b, facade side|None}] (eixos)."""
    lines = []
    # 1. bordadura : 4 linhas completas (os troços sob paredes / núcleos são retirados em segments())
    for side, a, b in (("y0", (0.0, 0.0), (S.L, 0.0)), ("y1", (0.0, S.B), (S.L, S.B)), ("x0", (0.0, 0.0), (0.0, S.B)), ("x1", (S.L, 0.0), (S.L, S.B))):
        lines.append({"a": a, "b": b, "facade": side})
    # 2. interiores
    sources = []
    for c in S.columns:
        if absorbed(S, c):
            continue
        fac = _on_facade(S, c["x"], c["y"])
        if len(fac) >= 2:
            continue                                   # pilar de canto : só vigas de bordadura
        if fac:
            d = {"y0": (0, 1), "y1": (0, -1), "x0": (1, 0), "x1": (-1, 0)}[fac[0]]
            sources.append((c["x"], c["y"], d, c["id"], False))
        else:
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                sources.append((c["x"], c["y"], d, c["id"], True))
    for w in S.walls:
        dirs = ((1, 0), (-1, 0)) if w["axis"] == "Y" else ((0, 1), (0, -1))
        for (px, py) in ((w["x0"], w["y0"]), (w["x1"], w["y1"])):
            for d in dirs:
                sources.append((px, py, d, w["id"], True))
    for x, y, (dx, dy), sid, secondary_ok in sources:
        hit = _ray_hit(S, x, y, dx, dy, sid)
        if not hit:
            continue
        dist, p, kind = hit
        if dist < MIN_BEAM:
            continue
        if kind == "fachada" and (not secondary_ok or dist > MAX_SECONDARY):
            continue
        if dist > MAX_BEAM:
            continue
        # o raio não pode atravessar um núcleo
        mid_ok = all(not _inside_core(S, x + dx * dist * f, y + dy * dist * f) for f in (0.25, 0.5, 0.75))
        if not mid_ok:
            continue
        # o ponto de chegada no núcleo/parede fica na linha do raio
        q = (p[0], y) if dx != 0 else (x, p[1])
        # beam already along a facade line → skip (bordadura)
        if dx != 0 and (abs(y) < 0.06 or abs(y - S.B) < 0.06):
            continue
        if dy != 0 and (abs(x) < 0.06 or abs(x - S.L) < 0.06):
            continue
        lines.append({"a": (round(x, 3), round(y, 3)), "b": (round(q[0], 3), round(q[1], 3)), "facade": None})
    # deduplicação (mesmo segmento nos dois sentidos, ou contido noutro colinear)
    out = []
    for ln in lines:
        a, b = sorted([ln["a"], ln["b"]])
        dup = False
        for o in out:
            oa, ob = o["a"], o["b"]
            if _collinear_overlap(a, b, oa, ob) >= 0.95 * math.dist(a, b):
                dup = True
                break
        if not dup:
            out.append({"a": a, "b": b, "facade": ln["facade"]})
    return out


def _collinear_overlap(a, b, c, d, tol=0.05) -> float:
    if abs(a[1] - b[1]) < 1e-6 and abs(c[1] - d[1]) < 1e-6 and abs(a[1] - c[1]) < tol:
        lo, hi = max(min(a[0], b[0]), min(c[0], d[0])), min(max(a[0], b[0]), max(c[0], d[0]))
        return max(0.0, hi - lo)
    if abs(a[0] - b[0]) < 1e-6 and abs(c[0] - d[0]) < 1e-6 and abs(a[0] - c[0]) < tol:
        lo, hi = max(min(a[1], b[1]), min(c[1], d[1])), min(max(a[1], b[1]), max(c[1], d[1]))
        return max(0.0, hi - lo)
    return 0.0


def beam_lines(S: Spec) -> list[dict]:
    if S.beams_in:
        lines = []
        for b in S.beams_in:
            a, c = sorted([b["a"], b["b"]])
            fac = None
            for side in ("y0", "y1", "x0", "x1"):
                on = _on_facade(S, *a)
                if side in on and side in _on_facade(S, *c):
                    fac = side
            lines.append({"a": a, "b": c, "facade": fac, "id": b["id"]})
    else:
        lines = auto_beams(S)
    names = {"y0": "VF1", "y1": "VF2", "x0": "VE1", "x1": "VE2"}
    k = 0
    for ln in lines:
        if ln.get("id"):
            continue
        if ln["facade"]:
            ln["id"] = names[ln["facade"]]
        else:
            k += 1
            ln["id"] = f"VI{k}"
    return lines


def _support_points_on(S, a, b, lines):
    """Pontos de apoio ao longo de uma linha de viga : pilares, extremos de paredes, faces de núcleos, outras vigas."""
    pts = {a, b}
    horiz = abs(a[1] - b[1]) < 1e-6

    def on(p, tol=0.06):
        return dist_seg(p[0], p[1], a, b) <= tol
    for c in S.columns:
        if on((c["x"], c["y"]), 0.15):
            pts.add((c["x"], a[1]) if horiz else (a[0], c["y"]))
    for w in S.walls:
        for p in ((w["x0"], w["y0"]), (w["x1"], w["y1"])):
            if on(p, w["t"] / 2 + 0.06):
                pts.add((p[0], a[1]) if horiz else (a[0], p[1]))
    for c in S.cores:
        x0, y0, x1, y1 = c["box"]
        for p in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
            if on(p, 0.4):
                pts.add((p[0], a[1]) if horiz else (a[0], p[1]))
    for o in lines:
        for p in (o["a"], o["b"]):
            if on(p, 0.06):
                pts.add(p)
    return sorted(pts, key=lambda p: (p[0], p[1]))


def _covered(S, p, q) -> str | None:
    """Troço coberto por uma parede ou por um núcleo (→ a viga não existe nesse troço)."""
    m = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    for w in S.walls:
        if dist_seg(m[0], m[1], (w["x0"], w["y0"]), (w["x1"], w["y1"])) <= w["t"] / 2 + 0.06:
            return w["id"]
    for c in S.cores:
        x0, y0, x1, y1 = c["box"]
        if x0 - 0.05 <= m[0] <= x1 + 0.05 and y0 - 0.05 <= m[1] <= y1 + 0.05:
            return c["id"]
    return None


def beam_segments(S: Spec, lines: list[dict]) -> list[dict]:
    """Troços de viga entre apoios : [{name, line, a, b, L, facade, cont}]."""
    out = []
    for ln in lines:
        pts = _support_points_on(S, ln["a"], ln["b"], lines)
        segs = []
        for p, q in zip(pts, pts[1:]):
            if math.dist(p, q) < 0.30 or _covered(S, p, q):
                continue
            segs.append((p, q))
        for k, (p, q) in enumerate(segs):
            out.append({"name": f"{ln['id']}.{k + 1}" if len(segs) > 1 else ln["id"], "line": ln["id"], "a": p, "b": q,
                        "L": round(math.dist(p, q), 2), "facade": ln["facade"], "cont": len(segs) > 1})
    return out


# ------------------------------------------------------------------ rasterização e painéis
class Raster:
    def __init__(self, x0, y0, x1, y1, step=STEP):
        self.x0, self.y0, self.step = x0, y0, step
        self.nx = int(math.ceil((x1 - x0) / step))
        self.ny = int(math.ceil((y1 - y0) / step))
        xs = x0 + (np.arange(self.nx) + 0.5) * step
        ys = y0 + (np.arange(self.ny) + 0.5) * step
        self.X, self.Y = np.meshgrid(xs, ys, indexing="ij")

    def seg_mask(self, a, b, half):
        (ax, ay), (bx, by) = a, b
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy or 1e-9
        t = np.clip(((self.X - ax) * vx + (self.Y - ay) * vy) / L2, 0, 1)
        return np.hypot(self.X - ax - t * vx, self.Y - ay - t * vy) <= half

    def box_mask(self, x0, y0, x1, y1):
        return (self.X > x0) & (self.X < x1) & (self.Y > y0) & (self.Y < y1)

    def ij(self, x, y):
        return int((x - self.x0) / self.step), int((y - self.y0) / self.step)


def label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """Componentes conexas (4-vizinhança) sem scipy."""
    lab = np.zeros(mask.shape, dtype=np.int32)
    n = 0
    nx, ny = mask.shape
    for i0, j0 in zip(*np.nonzero(mask)):
        if lab[i0, j0]:
            continue
        n += 1
        lab[i0, j0] = n
        dq = deque([(i0, j0)])
        while dq:
            i, j = dq.popleft()
            for a, b in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= a < nx and 0 <= b < ny and mask[a, b] and not lab[a, b]:
                    lab[a, b] = n
                    dq.append((a, b))
    return lab, n


def _decompose(cells: np.ndarray, depth=0) -> list[tuple[int, int, int, int]]:
    """Região (máscara booleana) → retângulos (i0, j0, i1, j1) com taxa de preenchimento ≥ 0,85."""
    ii, jj = np.nonzero(cells)
    if not len(ii):
        return []
    i0, i1, j0, j1 = ii.min(), ii.max() + 1, jj.min(), jj.max() + 1
    sub = cells[i0:i1, j0:j1]
    fill = sub.sum() / sub.size
    if fill >= 0.85 or sub.sum() < 400 or depth > 6:
        return [(i0, j0, i1, j1)]
    best = None
    for axis in (0, 1):
        prof = sub.sum(axis=1 - axis).astype(float)
        for k in range(1, len(prof)):
            if prof[k - 1] == 0 or abs(prof[k] - prof[k - 1]) / max(prof[k], prof[k - 1]) < 0.15:
                continue
            A = sub[:k, :] if axis == 0 else sub[:, :k]
            Bm = sub[k:, :] if axis == 0 else sub[:, k:]
            waste = 0
            for part in (A, Bm):
                pi, pj = np.nonzero(part)
                if len(pi):
                    waste += (pi.max() - pi.min() + 1) * (pj.max() - pj.min() + 1) - part.sum()
            if best is None or waste < best[0]:
                best = (waste, axis, k)
    if best is None:
        return [(i0, j0, i1, j1)]
    _, axis, k = best
    m1 = np.zeros_like(cells)
    m2 = np.zeros_like(cells)
    if axis == 0:
        m1[i0:i0 + k, j0:j1] = sub[:k, :]
        m2[i0 + k:i1, j0:j1] = sub[k:, :]
    else:
        m1[i0:i1, j0:j0 + k] = sub[:, :k]
        m2[i0:i1, j0 + k:j1] = sub[:, k:]
    return _decompose(m1, depth + 1) + _decompose(m2, depth + 1)


def _edge_type(R: Raster, lab, region_id, barrier, i0, j0, i1, j1, side, slab_mask):
    """Tipo do bordo de um retângulo : rive (apoio sem laje do outro lado), continu (apoio com laje contígua), libre (corte)."""
    if side == "x0":
        cells = [(i0 - 1, j) for j in range(j0, j1)]
        nxt = [(i0 - 4, j) for j in range(j0, j1)]
    elif side == "x1":
        cells = [(i1, j) for j in range(j0, j1)]
        nxt = [(i1 + 3, j) for j in range(j0, j1)]
    elif side == "y0":
        cells = [(i, j0 - 1) for i in range(i0, i1)]
        nxt = [(i, j0 - 4) for i in range(i0, i1)]
    else:
        cells = [(i, j1) for i in range(i0, i1)]
        nxt = [(i, j1 + 3) for i in range(i0, i1)]
    votes = {"rive": 0, "continu": 0, "libre": 0}
    for (a, b), (c, d) in zip(cells, nxt):
        inb = 0 <= a < R.nx and 0 <= b < R.ny
        if inb and lab[a, b] == region_id:
            votes["libre"] += 1
            continue
        beyond = 0 <= c < R.nx and 0 <= d < R.ny and slab_mask[c, d]
        votes["continu" if beyond else "rive"] += 1
    return max(votes, key=votes.get)


def _nearest_support_point(S: Spec, p, max_d=0.45):
    """Ponto mais próximo de um apoio (pilar, parede, contorno de núcleo) a ≤ max_d : fecha a ligação viga-apoio na rasterização."""
    best = None
    cands = [(c["x"], c["y"]) for c in S.columns]
    for w in S.walls:
        a, b = (w["x0"], w["y0"]), (w["x1"], w["y1"])
        vx, vy = b[0] - a[0], b[1] - a[1]
        L2 = vx * vx + vy * vy or 1e-9
        u = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2))
        cands.append((a[0] + u * vx, a[1] + u * vy))
    for c in S.cores:
        x0, y0, x1, y1 = c["box"]
        cands.append((min(max(p[0], x0), x1), min(max(p[1], y0), y1)))
    for q in cands:
        d = math.dist(p, q)
        if 0.02 < d <= max_d and (best is None or d < best[0]):
            best = (d, q)
    return best[1] if best else None


def panels(S: Spec, segs: list[dict], garage=False) -> list[dict]:
    """Painéis retangulares de laje [{name, x0, y0, x1, y1, edges, area_region}] — edifício ou laje sobre a cave (garage=True)."""
    if garage:
        if not S.basement or not S.bpoly:
            return []
        xs = [p[0] for p in S.bpoly]
        ys = [p[1] for p in S.bpoly]
        R = Raster(min(xs) - 0.2, min(ys) - 0.2, max(xs) + 0.2, max(ys) + 0.2)
        inside = _in_poly_grid(R.X, R.Y, S.bpoly)
        dom = inside & ~R.box_mask(-0.02, -0.02, S.L + 0.02, S.B + 0.02)
        barrier = np.zeros_like(dom)
        for c in S.bcols:
            barrier |= R.seg_mask((c["x"], c["y"]), (c["x"], c["y"]), 0.10)
        for b in garage_beams(S):
            barrier |= R.seg_mask(b["a"], b["b"], 0.06)
        slab_mask = dom.copy()
    else:
        R = Raster(-0.2, -0.2, S.L + 0.2, S.B + 0.2)
        dom = R.box_mask(0.0, 0.0, S.L, S.B)
        barrier = np.zeros_like(dom)
        for s in segs:
            barrier |= R.seg_mask(s["a"], s["b"], 0.06)
            for p in (s["a"], s["b"]):
                q = _nearest_support_point(S, p)
                if q is not None:
                    barrier |= R.seg_mask(p, q, 0.06)
        for w in S.walls:
            barrier |= R.seg_mask((w["x0"], w["y0"]), (w["x1"], w["y1"]), max(0.06, w["t"] / 2))
        for c in S.cores:
            x0, y0, x1, y1 = c["box"]
            barrier |= R.box_mask(x0 - 0.03, y0 - 0.03, x1 + 0.03, y1 + 0.03)
        slab_mask = dom.copy()
        for c in S.cores:
            slab_mask &= ~R.box_mask(*c["box"])
    free = dom & ~barrier
    lab, n = label(free)
    out = []
    for rid in range(1, n + 1):
        cells = lab == rid
        if cells.sum() * STEP * STEP < 1.0:
            continue
        ri, rj = np.nonzero(cells)
        region = (R.x0 + ri.min() * STEP, R.y0 + rj.min() * STEP, R.x0 + (ri.max() + 1) * STEP, R.y0 + (rj.max() + 1) * STEP)
        for (i0, j0, i1, j1) in _decompose(cells):
            part = cells[i0:i1, j0:j1]
            if part.sum() * STEP * STEP < 0.8 or min(i1 - i0, j1 - j0) * STEP < 0.6:
                continue
            x0 = R.x0 + i0 * STEP
            x1 = R.x0 + i1 * STEP
            y0 = R.y0 + j0 * STEP
            y1 = R.y0 + j1 * STEP
            # alargar até ao eixo dos apoios (metade da largura da barreira)
            x0, y0, x1, y1 = round(x0 - 0.06, 2), round(y0 - 0.06, 2), round(x1 + 0.06, 2), round(y1 + 0.06, 2)
            edges = {s: _edge_type(R, lab, rid, barrier, i0, j0, i1, j1, s, slab_mask) for s in ("x0", "x1", "y0", "y1")}
            out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "edges": edges, "area": round(float(part.sum()) * STEP * STEP, 2),
                        "region": tuple(round(v, 2) for v in region)})
    out.sort(key=lambda p: (round(p["y0"] / 2), p["x0"]))
    pre = "LG" if garage else "L"
    for k, p in enumerate(out):
        p["name"] = f"{pre}{k + 1}"
    return out


def garage_beams(S: Spec) -> list[dict]:
    """Vigas da laje sobre a cave (fora do edifício) : raios a partir dos pilares da cave até ao apoio mais próximo
    (pilar da cave, muro, fachada do edifício) a ≤ 8,5 m."""
    if not S.basement:
        return []
    out = []
    for c in S.bcols:
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            best = None
            for o in S.bcols + [{"id": k["id"], "x": k["x"], "y": k["y"]} for k in S.columns]:
                if o is c or o.get("id") == c["id"]:
                    continue
                rx, ry = o["x"] - c["x"], o["y"] - c["y"]
                along = rx * dx + ry * dy
                if along > 0.5 and abs(rx * dy - ry * dx) <= TOL_HIT and (best is None or along < best[0]):
                    best = (along, (o["x"], c["y"]) if dx else (c["x"], o["y"]))
            # muros e fachada do edifício
            P = S.bpoly
            for w in S.bwalls:
                a, b = P[w["i0"]], P[w["i1"]]
                d = _ray_seg(c["x"], c["y"], dx, dy, a, b)
                if d and (best is None or d[0] < best[0]):
                    best = (d[0], (a[0] if dx else c["x"], c["y"] if dx else a[1]))
            for val, axis in ((0.0, "x"), (S.L, "x"), (0.0, "y"), (S.B, "y")):
                if axis == "x" and dx and 0 <= c["y"] <= S.B:
                    d = (val - c["x"]) / dx
                    if d > 0.3 and (best is None or d < best[0]):
                        best = (d, (val, c["y"]))
                if axis == "y" and dy and 0 <= c["x"] <= S.L:
                    d = (val - c["y"]) / dy
                    if d > 0.3 and (best is None or d < best[0]):
                        best = (d, (c["x"], val))
            if best and MIN_BEAM <= best[0] <= MAX_BEAM:
                a, b = sorted([(c["x"], c["y"]), (round(best[1][0], 3), round(best[1][1], 3))])
                if not any(_collinear_overlap(a, b, o["a"], o["b"]) > 0.9 * math.dist(a, b) for o in out):
                    out.append({"a": a, "b": b, "id": f"VG{len(out) + 1}"})
    return out


# ------------------------------------------------------------------ áreas de influência
def _dist_grid(X, Y, e):
    if e["seg"] is None:
        return np.hypot(X - e["x"], Y - e["y"])
    (ax, ay), (bx, by) = e["seg"]
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy or 1e-9
    t = np.clip(((X - ax) * vx + (Y - ay) * vy) / L2, 0, 1)
    return np.hypot(X - ax - t * vx, Y - ay - t * vy)


def _nearest(X, Y, els):
    """Índice do elemento mais próximo em cada ponto (argmin incremental : memória O(grelha), não O(grelha × elementos))."""
    best = np.full(np.shape(X), np.inf)
    idx = np.zeros(np.shape(X), dtype=np.int32)
    for k, e in enumerate(els):
        d = _dist_grid(X, Y, e)
        m = d < best
        best = np.where(m, d, best)
        idx = np.where(m, k, idx)
    return idx


def tributary(S: Spec, step=0.10) -> tuple[list[dict], dict]:
    """Áreas de influência por elemento vertical : {id: {hab, balc, fac, gar}} (m², m² de varanda, ml de fachada, m² sobre a cave)."""
    els = supports(S)
    ids = sorted({e["id"] for e in els})
    area = {k: {"hab": 0.0, "balc": 0.0, "fac": 0.0, "gar": 0.0} for k in ids}
    xs = np.arange(-3.0 + step / 2, S.L + 3.0, step)
    ys = np.arange(-3.0 + step / 2, S.B + 3.0, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    inside = (X >= 0) & (X <= S.L) & (Y >= 0) & (Y <= S.B)
    for c in S.cores:
        if c["kind"] == "lift":
            x0, y0, x1, y1 = c["box"]
            inside &= ~((X > x0) & (X < x1) & (Y > y0) & (Y < y1))
    balc = np.zeros_like(inside)
    for b in S.balconies:
        s, d, f0, f1 = b["side"], b["depth"], b["from"], b["to"]
        if s == "y0":
            balc |= (Y < 0) & (Y >= -d) & (X >= f0) & (X <= f1)
        elif s == "y1":
            balc |= (Y > S.B) & (Y <= S.B + d) & (X >= f0) & (X <= f1)
        elif s == "x0":
            balc |= (X < 0) & (X >= -d) & (Y >= f0) & (Y <= f1)
        else:
            balc |= (X > S.L) & (X <= S.L + d) & (Y >= f0) & (Y <= f1)
    near = _nearest(X, Y, els)
    a1 = step * step
    for k, e in enumerate(els):
        area[e["id"]]["hab"] += float((inside & (near == k)).sum()) * a1
        area[e["id"]]["balc"] += float((balc & ~inside & (near == k)).sum()) * a1
    # fachadas : comprimento de perímetro por elemento
    n = 400
    for (ax, ay), (bx, by) in (((0, 0), (S.L, 0)), ((S.L, 0), (S.L, S.B)), ((S.L, S.B), (0, S.B)), ((0, S.B), (0, 0))):
        ln = math.hypot(bx - ax, by - ay)
        u = (np.arange(n) + 0.5) / n
        px, py = ax + u * (bx - ax), ay + u * (by - ay)
        nn = _nearest(px, py, els)
        for k, e in enumerate(els):
            area[e["id"]]["fac"] += float((nn == k).sum()) * ln / n
    if S.basement and S.bpoly:
        gels = supports(S, garage=True)
        for e in gels:
            area.setdefault(e["id"], {"hab": 0.0, "balc": 0.0, "fac": 0.0, "gar": 0.0})
        gx = [p[0] for p in S.bpoly]
        gy = [p[1] for p in S.bpoly]
        GX, GY = np.meshgrid(np.arange(min(gx) + step / 2, max(gx), step), np.arange(min(gy) + step / 2, max(gy), step), indexing="ij")
        inpoly = _in_poly_grid(GX, GY, S.bpoly) & ~((GX >= 0) & (GX <= S.L) & (GY >= 0) & (GY <= S.B))
        gn = _nearest(GX, GY, gels)
        for k, e in enumerate(gels):
            area[e["id"]]["gar"] += float((inpoly & (gn == k)).sum()) * a1
        els = gels
    return els, {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in area.items()}


def _in_poly_grid(X, Y, P):
    inside = np.zeros(X.shape, dtype=bool)
    n = len(P)
    j = n - 1
    for i in range(n):
        xi, yi = P[i]
        xj, yj = P[j]
        cond = ((yi > Y) != (yj > Y)) & (X < (xj - xi) * (Y - yi) / (yj - yi + 1e-12) + xi)
        inside ^= cond
        j = i
    return inside
