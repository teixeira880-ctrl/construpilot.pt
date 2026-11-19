"""Pré-dimensionamento estrutural sobre GEOMETRIA REAL (polígonos e paredes em qualquer ângulo).

Princípio: o código calcula, nenhum número estrutural vem de um LLM.

1. Linhas de apoio = contorno da laje (fachadas, pátios) + paredes interiores relevantes.
2. Pilares nos nós (cantos convexos/reentrantes, cruzamentos, extremos) + intermédios se o
   vão exceder o máximo. Vigas entre pilares consecutivos.
3. Painéis de laje = faces do polígono da laje recortado pelas vigas (qualquer forma).
4. Áreas de influência por proximidade: cada ponto da laje (malha de 0,20 m) descarrega na
   viga mais próxima — válido para qualquer polígono (equivale às regras dos trapézios num
   retângulo). Vão equivalente do painel = 2 × maior distância a um apoio.
5. Lajes (EC2), vigas (flexão + esforço transverso), pilares (compressão), sapatas isoladas
   (tensão admissível), vigas de fundação (paredes), muros de suporte (impulso K0), laje térrea.

Normas: NP EN 1990/1991/1992 (Anexos Nacionais PT). Pré-dimensionamento: a validar e
assinar por engenheiro civil (projeto de estabilidade).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import polygonize, unary_union

from .model import Building

# ----------------------------------------------------------------------------- materiais / ações
FCK, FCD, FCTM = 30.0, 20.0, 2.9           # C30/37 (MPa)
FYK, FYD = 500.0, 435.0                    # A500 NR
GAMMA_C = 25.0                             # kN/m³
STEEL_KG_M3 = 7850.0
GRID = 0.20                                # m — malha de áreas de influência

DEFAULTS = {
    "roof_finishes_kN_m2": 2.5,     # cobertura invertida c/ seixo, XPS, membrana, forma de pendentes
    "roof_live_kN_m2": 0.4,         # categoria H (não acessível) — NP EN 1991-1-1
    "snow_kN_m2": 0.4,              # majorante para altitudes < 500 m (confirmar zona NP EN 1991-1-3)
    "parapet_kN_m": 2.0,            # platibanda BA 0,15 × 0,50 + capeamento
    "ground_finishes_kN_m2": 1.5,   # betonilha + pavimento (laje térrea)
    "ground_live_kN_m2": 2.0,       # habitação, categoria A
    "sigma_adm_kPa": 200.0,         # tensão admissível do terreno (HIPÓTESE — confirmar por estudo geotécnico)
    "soil_gamma_kN_m3": 19.0,
    "soil_K0": 0.5,                 # impulso em repouso (muro travado pela laje)
    "surcharge_kN_m2": 10.0,
    "max_span_m": 6.0,              # vão máximo entre pilares
    "cantilever_free_m": 1.6,       # palas até esta profundidade = consolas (sem pilares)
    "masonry_kN_m2": {0.11: 1.6, 0.15: 2.0, 0.20: 2.6, 0.25: 3.2},
}
ULS_G, ULS_Q = 1.35, 1.5


def _r(x, step=0.05, up=True):
    f = math.ceil if up else math.floor
    return round(f(x / step - 1e-9) * step, 3)


def _bars_slab(as_cm2_m: float) -> dict:
    best = None
    for phi in (8, 10, 12, 16):
        a1 = math.pi * (phi / 10) ** 2 / 4
        for s in (0.20, 0.175, 0.15, 0.125, 0.10):
            prov = a1 / s
            if prov >= as_cm2_m and (best is None or prov < best["as_prov"]):
                best = {"phi": phi, "s": s, "as_prov": round(prov, 2), "label": f"Ø{phi}//{s:.3g}".replace(".", ",")}
    return best or {"phi": 16, "s": 0.10, "as_prov": 20.1, "label": "Ø16//0,10 (insuficiente — aumentar espessura)"}


def _bars_n(as_cm2: float, nmin=2, nmax=8) -> dict:
    best = None
    for phi in (12, 16, 20, 25):
        a1 = math.pi * (phi / 10) ** 2 / 4
        n = max(nmin, math.ceil(as_cm2 / a1 - 1e-9))
        if n <= nmax:
            prov = n * a1
            if best is None or prov < best["as_prov"]:
                best = {"n": n, "phi": phi, "as_prov": round(prov, 2), "label": f"{n}Ø{phi}"}
    return best or {"n": nmax, "phi": 25, "as_prov": round(nmax * 4.91, 2), "label": f"{nmax}Ø25 (insuficiente)"}


def _kg(as_cm2: float, length_m: float) -> float:
    return as_cm2 * 1e-4 * length_m * STEEL_KG_M3


# ----------------------------------------------------------------------------- resultado
@dataclass
class Result:
    columns: list[dict] = field(default_factory=list)
    beams: list[dict] = field(default_factory=list)
    panels: list[dict] = field(default_factory=list)
    footings: list[dict] = field(default_factory=list)
    tie_beams: list[dict] = field(default_factory=list)
    retaining: list[dict] = field(default_factory=list)
    ground_slab: dict = field(default_factory=dict)
    slab: dict = field(default_factory=dict)
    loads: dict = field(default_factory=dict)
    quantities: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: list[dict] = field(default_factory=list)


# ----------------------------------------------------------------------------- 1-2. linhas de apoio, pilares, vigas
def _boundary_lines(poly) -> list[LineString]:
    out = []
    polys = getattr(poly, "geoms", [poly])
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            cs = list(ring.simplify(0.05).coords)
            out += [LineString([cs[i], cs[i + 1]]) for i in range(len(cs) - 1) if math.dist(cs[i], cs[i + 1]) > 0.05]
    return out


def support_lines(b: Building, prm: dict) -> tuple[list[LineString], list[Polygon]]:
    """Linhas de vigas + palas em consola (zonas da laje sem pilares)."""
    slab = b.roof_slab
    lines = _boundary_lines(b.footprint)
    cantilevers = []
    for c in b.covered:
        depth = max((Point(p).distance(b.footprint) for p in c.exterior.coords), default=0.0)
        if depth <= prm["cantilever_free_m"]:
            cantilevers.append(c)                      # consola: bordo livre, sem vigas/pilares
        else:
            lines += [ln for ln in _boundary_lines(c) if ln.distance(b.footprint.exterior) > 0.05
                      or not ln.within(b.footprint.exterior.buffer(0.05))]
    fp_edges = unary_union(lines)
    for w in sorted(b.walls, key=lambda w: -w.length):
        if w.exterior or w.t < 0.14 or w.length < 1.0:
            continue
        ln = w.line
        if _parallel_near(ln, lines, 1.2):              # já há uma linha de apoio paralela a < 1,2 m
            continue
        # prolongar até à linha de apoio mais próxima (≤ 0,8 m) em cada extremo
        coords = list(ln.coords)
        ux, uy = coords[1][0] - coords[0][0], coords[1][1] - coords[0][1]
        n = math.hypot(ux, uy)
        ux, uy = ux / n, uy / n
        ext = LineString([(coords[0][0] - ux * 0.8, coords[0][1] - uy * 0.8),
                          (coords[1][0] + ux * 0.8, coords[1][1] + uy * 0.8)])
        hit = ext.intersection(fp_edges)
        pts = [ln.interpolate(0), ln.interpolate(ln.length)]
        if not hit.is_empty:
            hs = [g for g in getattr(hit, "geoms", [hit]) if g.geom_type == "Point"]
            proj = sorted(hs, key=lambda p: ext.project(p))
            if proj:
                if ext.project(proj[0]) <= 0.8 + 0.05:
                    pts[0] = proj[0]
                if ext.project(proj[-1]) >= ext.length - 0.8 - 0.05:
                    pts[1] = proj[-1]
        seg = LineString([pts[0], pts[1]]).intersection(slab)
        for g in getattr(seg, "geoms", [seg]):
            if g.geom_type == "LineString" and g.length > 1.0:
                lines.append(g)
    # fundir colineares sobrepostas (paredes paralelas muito próximas → uma viga)
    merged = unary_union(lines)
    lines = [g for g in getattr(merged, "geoms", [merged]) if g.length > 0.3]
    for _ in range(3):                                  # prolongamentos podem criar novos encontros
        lines = _dedupe(lines, b.footprint, 0.6)
        lines = _close_dangles(lines, slab, 3 * prm["max_span_m"])
    return lines, cantilevers


def _dedupe(lines: list[LineString], fp, dist: float) -> list[LineString]:
    """Duas linhas quase coincidentes (< 0,6 m, paralelas) = uma só viga: fica a do contorno ou a mais longa."""
    edge = fp.boundary.buffer(0.05)
    pieces = unary_union(lines)
    segs = [g for g in getattr(pieces, "geoms", [pieces]) if g.length > 0.05]
    segs.sort(key=lambda g: (not g.within(edge), -g.length))
    kept: list[LineString] = []
    for g in segs:
        if _parallel_near(g, kept, dist) and not g.within(edge):
            continue
        kept.append(g)
    out = unary_union(kept)
    return [g for g in getattr(out, "geoms", [out]) if g.length > 0.05]


def _parallel_near(ln: LineString, lines: list[LineString], dist: float) -> bool:
    (ax, ay), (bx, by) = ln.coords[0], ln.coords[-1]
    a1 = math.atan2(by - ay, bx - ax) % math.pi
    for o in lines:
        (cx, cy), (dx, dy) = o.coords[0], o.coords[-1]
        a2 = math.atan2(dy - cy, dx - cx) % math.pi
        if min(abs(a1 - a2), math.pi - abs(a1 - a2)) > math.radians(5):
            continue
        if o.distance(ln) < dist and ln.buffer(dist, cap_style=2).intersection(o).length > 0.5 * ln.length:
            return True
    return False


def _close_dangles(lines: list[LineString], slab, reach: float) -> list[LineString]:
    """Uma viga não acaba no meio da laje: prolonga-a na sua direção até à linha de apoio seguinte."""
    net = unary_union(lines)
    extra = []
    for ln in lines:
        cs = list(ln.coords)
        for p0, p1 in ((cs[0], cs[1]), (cs[-1], cs[-2])):
            P = Point(p0)
            others = net.difference(ln.buffer(0.02))
            if others.is_empty or P.distance(others) < 0.05:
                continue
            ux, uy = p0[0] - p1[0], p0[1] - p1[1]
            n = math.hypot(ux, uy)
            if n < 1e-9:
                continue
            ray = LineString([p0, (p0[0] + ux / n * reach, p0[1] + uy / n * reach)])
            hit = ray.intersection(others)
            if hit.is_empty:
                continue
            pts = [g for g in getattr(hit, "geoms", [hit]) if g.geom_type == "Point"] or \
                  [Point(c) for g in getattr(hit, "geoms", [hit]) for c in getattr(g, "coords", [])]
            if not pts:
                continue
            q = min(pts, key=lambda g: P.distance(g))
            seg = LineString([p0, (q.x, q.y)])
            if seg.length > 0.05 and seg.within(slab.buffer(0.05)):
                extra.append(seg)
    out = unary_union(lines + extra)
    return [g for g in getattr(out, "geoms", [out]) if g.length > 0.05]


def place_columns(lines: list[LineString], prm: dict, walls=None, warnings=None):
    """Pilares nos nós + intermédios; devolve pilares e vãos (vigas) por linha."""
    noded = unary_union(lines)                        # parte as linhas em todos os cruzamentos
    segs = [g for g in getattr(noded, "geoms", [noded]) if g.length > 0.05]
    # grau de cada nó
    deg: dict[tuple, int] = {}
    vec: dict[tuple, list] = {}
    for s in segs:
        a, b = s.coords[0], s.coords[-1]
        for p, q in ((a, b), (b, a)):
            k = (round(p[0], 2), round(p[1], 2))
            deg[k] = deg.get(k, 0) + 1
            vec.setdefault(k, []).append(math.atan2(q[1] - p[1], q[0] - p[0]))
    nodes = []
    for k, d in deg.items():
        angs = vec[k]
        straight = d == 2 and abs(abs(angs[0] - angs[1]) - math.pi) < math.radians(8)
        if not straight:                               # canto, T, cruzamento ou extremo
            nodes.append(k)
    # nós muito próximos (recortes do contorno, encontros de paredes) → um só pilar
    nodes.sort(key=lambda k: -deg[k])
    rep_of: dict[tuple, tuple] = {}
    reps: list[tuple] = []
    for k in nodes:
        r = next((q for q in reps if math.dist(q, k) < 0.9), None)
        if r is None:
            reps.append(k)
            r = k
        rep_of[k] = r
    # cadeias retas entre nós → vãos; subdividir vãos longos
    node_set = set(nodes)
    cols = {k: {"x": k[0], "y": k[1]} for k in reps}
    spans = []
    used = set()
    adj: dict[tuple, list] = {}
    for i, s in enumerate(segs):
        a = (round(s.coords[0][0], 2), round(s.coords[0][1], 2))
        b = (round(s.coords[-1][0], 2), round(s.coords[-1][1], 2))
        adj.setdefault(a, []).append((i, b))
        adj.setdefault(b, []).append((i, a))
    for start in nodes:
        for i, nxt in adj.get(start, []):
            if i in used:
                continue
            chain = [start]
            cur, ci = nxt, i
            used.add(ci)
            while cur not in node_set:
                chain.append(cur)
                options = [(j, q) for j, q in adj.get(cur, []) if j not in used]
                if not options:
                    break
                ci, q = options[0]
                used.add(ci)
                cur = q
            chain.append(cur)
            if cur not in node_set:
                node_set.add(cur)
                rep_of[cur] = next((q for q in reps if math.dist(q, cur) < 0.9), cur)
                if rep_of[cur] == cur:
                    reps.append(cur)
                    cols[cur] = {"x": cur[0], "y": cur[1]}
            # a geometria da viga fica no eixo real; a reação vai ao pilar do grupo (≤ 0,9 m)
            line = LineString(chain)
            if line.length < 0.5:
                continue
            L = line.length
            # pilares intermédios só onde há parede (nunca a meio de um envidraçado):
            # avança até ao ponto de parede mais afastado a ≤ vão máximo; um envidraçado até
            # max_span_no_wall é vencido por viga (invertida na platibanda); acima disso, pilar com aviso
            cuts = [0.0]
            on_wall = [float(t) for t in np.arange(0.5, L - 0.5 + 1e-9, 0.05)
                       if walls is not None and walls.contains(line.interpolate(float(t)))]
            span_max, span_glass = prm["max_span_m"], prm.get("max_span_no_wall_m", 10.0)
            pos = 0.0
            while L - pos > span_max:
                nxt = [t for t in on_wall if pos + 1.0 <= t <= pos + span_max]
                if not nxt:
                    nxt = [t for t in on_wall if pos + 1.0 <= t <= pos + span_glass + 0.25]
                if nxt:
                    pos = max(nxt)
                elif L - pos <= span_glass + 0.25:
                    break
                else:
                    pos = pos + span_max
                    if warnings is not None:
                        q = line.interpolate(pos)
                        warnings.append(f"Pilar intermédio sem parede em ({q.x:.2f}; {q.y:.2f}) — vão envidraçado "
                                        f"> {span_glass:.0f} m: confirmar a posição com a arquitetura.")
                cuts.append(pos)
            cuts.append(L)
            pts = [line.interpolate(t) for t in cuts]
            for q in pts[1:-1]:
                k = (round(q.x, 2), round(q.y, 2))
                cols.setdefault(k, {"x": k[0], "y": k[1]})
            for j in range(len(pts) - 1):
                spans.append(LineString([pts[j], pts[j + 1]]))
    return list(cols.values()), spans


def _support_every_end(columns: list[dict], spans: list[LineString]) -> list[dict]:
    """Regra de equilíbrio: cada extremo de viga apoia num pilar (≤ 0,9 m) ou a meio de outra viga.
    Um extremo sem apoio recebe um pilar — para qualquer forma de edifício."""
    cols = list(columns)
    for i, s in enumerate(spans):
        for end in (Point(s.coords[0]), Point(s.coords[-1])):
            if any(math.hypot(c["x"] - end.x, c["y"] - end.y) <= 0.9 for c in cols):
                continue
            on_other = any(j != i and o.distance(end) < 0.03 and
                           min(end.distance(Point(o.coords[0])), end.distance(Point(o.coords[-1]))) > 0.3
                           for j, o in enumerate(spans))
            if not on_other:
                cols.append({"x": round(end.x, 2), "y": round(end.y, 2)})
    return cols


# ----------------------------------------------------------------------------- 3-4. painéis e áreas de influência
def _grid(poly, step=GRID):
    x0, y0, x1, y1 = poly.bounds
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    X, Y = np.meshgrid(xs, ys)
    pts = np.c_[X.ravel(), Y.ravel()]
    from shapely import contains_xy
    keep = contains_xy(poly, pts[:, 0], pts[:, 1])
    return pts[keep]


def _seg_dist(pts, segs):
    """Distância de cada ponto a cada segmento (vetorizado). Devolve (dist_min, índice)."""
    A = np.array([s.coords[0] for s in segs])
    B = np.array([s.coords[-1] for s in segs])
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    P = pts[:, None, :]
    t = np.clip(((P - A[None]) * AB[None]).sum(2) / L2[None], 0, 1)
    proj = A[None] + t[..., None] * AB[None]
    d = np.sqrt(((P - proj) ** 2).sum(2))
    return d.min(1), d.argmin(1)


def design(b: Building, params: dict | None = None) -> Result:
    prm = {**DEFAULTS, **(params or {}), **{k: v for k, v in (b.hypotheses or {}).items() if k in DEFAULTS}}
    R = Result()
    slab = b.roof_slab
    H = b.storey_height
    lines, cantis = support_lines(b, prm)
    walls_zone = unary_union([w.line.buffer(w.t / 2 + 0.05, cap_style=2) for w in b.walls]) if b.walls else None
    columns, spans = place_columns(lines, prm, walls_zone, R.warnings)
    columns = _support_every_end(columns, spans)

    # ---- painéis
    faces = [f for f in polygonize(unary_union([*_boundary_lines(slab), *spans]))
             if slab.buffer(0.01).contains(f.representative_point()) and f.area > 0.3]
    q_roof_g = prm["roof_finishes_kN_m2"]
    q_roof_q = max(prm["roof_live_kN_m2"], prm["snow_kN_m2"])

    # espessura única da laje (prática de obra) a partir do painel mais exigente
    pts_all = _grid(slab)
    dmin, idx = _seg_dist(pts_all, spans)
    lx_need = []
    panel_info = []
    from shapely import contains_xy
    for i, f in enumerate(faces):
        inside = contains_xy(f, pts_all[:, 0], pts_all[:, 1])
        if not inside.any():
            continue
        d = dmin[inside]
        mrr = f.minimum_rotated_rectangle
        cs = list(mrr.exterior.coords)
        e1, e2 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        lx_rect, ly = min(e1, e2), max(e1, e2)
        # consola: painel cujo contorno não é suportado em > 60 %
        supported = f.exterior.intersection(unary_union(spans).buffer(0.03)).length / max(f.exterior.length, 1e-9)
        is_canti = any(f.intersection(c).area > 0.6 * f.area for c in cantis) or supported < 0.35
        if is_canti:
            lc = float(d.max())
            lx = lc
        else:
            lx = min(2 * float(d.max()), lx_rect) if lx_rect > 0 else 2 * float(d.max())
        lam = ly / max(lx, 1e-6)
        panel_info.append((i, f, lx, ly, lam, is_canti, supported))
        lx_need.append(lx * (3.0 if is_canti else 1.0))   # consola: L/d ≈ 10 vs ≈ 30 contínua (EC2 7.4.2, K = 1,5)
    lx_gov = max(lx_need) if lx_need else 4.0
    h_slab = max(0.18, _r(lx_gov / 30 + 0.035, 0.01))
    d_slab = h_slab - 0.035
    g_slab = h_slab * GAMMA_C
    q_ed = ULS_G * (g_slab + q_roof_g) + ULS_Q * q_roof_q
    q_sls = g_slab + q_roof_g + q_roof_q
    R.loads = {"g_laje": round(g_slab, 2), "g_revestimentos": q_roof_g, "q_sobrecarga": q_roof_q,
               "p_Ed_laje": round(q_ed, 2), "p_sls_laje": round(q_sls, 2), "pe_direito": H}
    R.slab = {"h": h_slab, "area": round(slab.area, 2), "concreto_m3": round(slab.area * h_slab, 2)}

    as_min = max(0.26 * FCTM / FYK, 0.0013) * 100 * d_slab * 100       # cm²/m
    for i, f, lx, ly, lam, canti, sup in panel_info:
        if canti:
            m_x = q_ed * lx ** 2 / 2
            m_neg, m_pos = m_x, 0.0
            kind = "consola"
        else:
            ax = min(1.0, lam ** 4 / (1 + lam ** 4))          # Rankine–Grashof: parcela na direção curta
            m_pos = ax * q_ed * lx ** 2 / 10
            m_neg = ax * q_ed * lx ** 2 / 10
            regular = f.area > 0.85 * f.minimum_rotated_rectangle.area
            if not regular:
                ax = 1.0                                       # painel irregular: tudo no vão equivalente (a favor da segurança)
            m_pos = ax * q_ed * lx ** 2 / 10
            m_neg = ax * q_ed * lx ** 2 / 10
            kind = ("duas direções" if lam < 2 else "uma direção") if regular else "irregular (vão equivalente)"
        def as_req(m):
            if m <= 0:
                return 0.0
            mu = m / (1.0 * d_slab ** 2 * FCD * 1000)
            z = d_slab * min(0.95, 0.5 * (1 + math.sqrt(max(1 - 2 * mu, 0.01))))
            return m / (z * FYD * 1000) * 1e4
        a_pos = max(as_req(m_pos), as_min)
        a_neg = max(as_req(m_neg), as_min)
        R.panels.append({
            "id": f"L{len(R.panels) + 1}", "area": round(f.area, 2), "tipo": kind,
            "Lx_eq": round(lx, 2), "Ly": round(ly, 2), "m_pos": round(m_pos, 1), "m_neg": round(m_neg, 1),
            "inf": _bars_slab(a_pos), "sup": _bars_slab(a_neg) if m_neg > 0 else None,
            "geom": f,
        })

    # ---- cargas nas vigas por áreas de influência
    w_area = GRID * GRID
    loads_span = np.zeros(len(spans))
    np.add.at(loads_span, idx, w_area)
    perim = unary_union(_boundary_lines(slab)).buffer(0.05)
    k_mult = 1.15                                       # continuidade (reação no apoio intermédio)
    col_loads: dict[tuple, dict] = {(round(c["x"], 2), round(c["y"], 2)): {"N_Ed": 0.0, "N_sls": 0.0} for c in columns}

    def _nearest_col(p):
        k = min(col_loads, key=lambda c: (c[0] - p[0]) ** 2 + (c[1] - p[1]) ** 2)
        return k

    for j, s in enumerate(spans):
        L = s.length
        area = float(loads_span[j])
        parapet = prm["parapet_kN_m"] if s.within(perim) else 0.0
        bw = 0.20
        for w in b.walls:
            if w.line.distance(s) < 0.15 and w.t > bw:
                bw = min(0.30, _r(w.t, 0.05))
        hb = max(0.40, _r(L / 12, 0.05), h_slab + 0.15)
        for _ in range(4):
            gb = bw * (hb - h_slab) * GAMMA_C
            w_ed = (area * q_ed / max(L, 1e-6)) + ULS_G * (gb + parapet)
            w_sls = (area * q_sls / max(L, 1e-6)) + gb + parapet
            m_ed = w_ed * L ** 2 / 9.0
            d_b = hb - 0.05
            mu = m_ed / (bw * d_b ** 2 * FCD * 1000)
            if mu <= 0.25:
                break
            hb = _r(hb + 0.05, 0.05)
        z = d_b * 0.5 * (1 + math.sqrt(max(1 - 2 * mu, 0.01)))
        as_b = max(m_ed / (z * FYD * 1000) * 1e4, 0.26 * FCTM / FYK * bw * d_b * 1e4)
        v_ed = 0.6 * w_ed * L
        rho_w = 0.08 * math.sqrt(FCK) / FYK
        asw_s = max(v_ed / (0.9 * d_b * FYD * 1000 * 2.5) * 1e4, rho_w * bw * 1e4)    # cm²/m
        legs = 2 * math.pi * 0.8 ** 2 / 4
        s_st = min(0.75 * d_b, 0.30, legs / asw_s)
        s_st = max(0.075, math.floor(s_st / 0.025) * 0.025)
        if hb >= 0.60:
            R.warnings.append(f"Viga V{len(R.beams) + 1}: vão {L:.2f} m sem pilar intermédio (envidraçado) → h = {hb:.2f} m; "
                              "prever viga invertida na platibanda para não baixar a padieira.")
        R.beams.append({
            "id": f"V{len(R.beams) + 1}", "L": round(L, 2), "b": bw, "h": hb,
            "w_Ed": round(w_ed, 1), "M_Ed": round(m_ed, 1), "V_Ed": round(v_ed, 1),
            "inf": _bars_n(as_b), "sup": _bars_n(as_b * 0.8),
            "estribos": f"Ø8//{s_st:.3g}".replace(".", ","), "s_st": s_st,
            "geom": s, "parapeito": parapet > 0,
        })
        for end in (s.coords[0], s.coords[-1]):
            k = _nearest_col(end)
            col_loads[k]["N_Ed"] += 0.5 * w_ed * L * k_mult
            col_loads[k]["N_sls"] += 0.5 * w_sls * L * k_mult

    # ---- pilares
    for n, c in enumerate(columns):
        k = (round(c["x"], 2), round(c["y"], 2))
        side = 0.20
        for w in b.walls:
            if w.line.distance(Point(c["x"], c["y"])) < 0.2:
                side = max(side, min(0.30, _r(w.t, 0.05)))
        for _ in range(6):
            n_ed = col_loads[k]["N_Ed"] + ULS_G * side * side * H * GAMMA_C
            ac_need = n_ed / (0.8 * 0.85 * FCD * 1000 + 0.01 * FYD * 1000)
            if side * side >= ac_need:
                break
            side = _r(side + 0.05, 0.05)
        n_sls = col_loads[k]["N_sls"] + side * side * H * GAMMA_C
        as_c = max(0.1 * n_ed / (FYD * 1000) * 1e4, 0.002 * side * side * 1e4)
        bars = _bars_n(as_c, nmin=4)
        if bars["phi"] < 12:
            bars = _bars_n(4.52, nmin=4)
        R.columns.append({"id": f"P{n + 1}", "x": c["x"], "y": c["y"], "a": side, "b": side,
                          "N_Ed": round(n_ed, 1), "N_sls": round(n_sls, 1), "armadura": bars,
                          "estribos": "Ø6//0,15", "H": H})

    # ---- sapatas isoladas
    sig = prm["sigma_adm_kPa"]
    for c in R.columns:
        n_sls = c["N_sls"] * 1.10
        B = max(0.80, _r(math.sqrt(n_sls / sig), 0.05))
        hs = max(0.40, _r((B - c["a"]) / 4 + 0.05, 0.05))
        sig_ed = c["N_Ed"] / (B * B)
        cant = (B - c["a"]) / 2
        m = sig_ed * B * cant ** 2 / 2
        d_s = hs - 0.06
        as_s = max(m / (0.9 * d_s * FYD * 1000) * 1e4, 0.0013 * B * d_s * 1e4)
        bars = _bars_slab(as_s / B)
        R.footings.append({"id": f"S{c['id'][1:]}", "pilar": c["id"], "x": c["x"], "y": c["y"],
                           "B": B, "h": hs, "sigma_sls": round(n_sls / (B * B), 1), "armadura": bars["label"] + " (2 dir.)",
                           "as_m": bars["as_prov"]})

    # ---- vigas de fundação (sob vigas de cobertura/paredes) com peso de alvenaria
    masonry = prm["masonry_kN_m2"]
    for j, s in enumerate(spans):
        wall_load = 0.0
        for w in b.walls:
            ov = w.line.intersection(s.buffer(0.15))
            if ov.length > 0.3:
                tt = min(masonry, key=lambda t: abs(t - max(w.t - 0.03, 0.11)))
                wall_load = max(wall_load, masonry[tt] * (H - 0.4))
        bw, hb = 0.30, 0.40
        L = s.length
        w_ed = ULS_G * (wall_load + bw * hb * GAMMA_C)
        m = w_ed * L ** 2 / 10
        d_b = hb - 0.05
        as_b = max(m / (0.9 * d_b * FYD * 1000) * 1e4, 0.26 * FCTM / FYK * bw * d_b * 1e4)
        R.tie_beams.append({"id": f"VF{j + 1}", "L": round(L, 2), "b": bw, "h": hb, "w_Ed": round(w_ed, 1),
                            "inf": _bars_n(as_b), "sup": _bars_n(as_b), "estribos": "Ø8//0,20", "geom": s})

    # ---- muros de suporte
    for w in b.walls:
        if w.retained_height <= 0:
            continue
        Hr, K, g, qs = w.retained_height, prm["soil_K0"], prm["soil_gamma_kN_m3"], prm["surcharge_kN_m2"]
        m_ed = ULS_G * K * g * Hr ** 3 / 6 + ULS_Q * K * qs * Hr ** 2 / 2
        t = 0.25
        for _ in range(8):
            d_w = t - 0.05
            if m_ed / (1.0 * d_w ** 2 * FCD * 1000) <= 0.20:
                break
            t = _r(t + 0.05, 0.05)
        as_w = max(m_ed / (0.9 * d_w * FYD * 1000) * 1e4, 0.002 * t * 1e4 / 2)
        Bf = max(1.0, _r(0.6 * Hr + t, 0.05))
        R.retaining.append({"id": f"M{len(R.retaining) + 1}", "L": round(w.length, 2), "H_terras": Hr, "t": t,
                            "M_Ed": round(m_ed, 1), "vertical_terras": _bars_slab(as_w)["label"],
                            "vertical_outra": _bars_slab(max(0.002 * t * 1e4 / 2, 2.5))["label"],
                            "horizontal": _bars_slab(max(0.25 * as_w, 0.002 * t * 1e4 / 2))["label"],
                            "sapata_B": Bf, "sapata_h": 0.40, "geom": w.line})
        R.warnings.append(f"Muro de suporte {R.retaining[-1]['id']} (terras {Hr:.2f} m): drenagem e impermeabilização obrigatórias; "
                          "verificar deslizamento e derrube com os parâmetros geotécnicos reais.")

    # ---- laje térrea
    fp = b.footprint
    R.ground_slab = {"area": round(fp.area, 2), "h": 0.15, "armadura": "malha A500 Ø8//0,15 (#)",
                     "concreto_m3": round(fp.area * 0.15, 2), "tout_venant_m3": round(fp.area * 0.20, 2)}

    _quantities(b, R, h_slab)
    _sanity(b, R)
    if prm["sigma_adm_kPa"] == DEFAULTS["sigma_adm_kPa"]:
        R.warnings.append("Tensão admissível do terreno assumida em 200 kPa (sem estudo geotécnico no processo): "
                          "as sapatas devem ser revistas com o relatório geotécnico.")
    R.warnings.append("Ação sísmica (NP EN 1998-1) não verificada neste pré-dimensionamento: a confirmar no projeto de estabilidade.")
    return R


# ----------------------------------------------------------------------------- quantidades
def _quantities(b: Building, R: Result, h_slab: float):
    Q = []

    def add(lote, item, un, qtd, kg=0.0, nota=""):
        Q.append({"lote": lote, "item": item, "un": un, "qtd": round(qtd, 2), "aco_kg": round(kg, 1), "nota": nota})

    # laje de cobertura: armadura inf + sup nas duas direções (média ponderada dos painéis)
    kg_slab = 0.0
    for p in R.panels:
        a_inf = p["inf"]["as_prov"]
        a_sup = p["sup"]["as_prov"] if p["sup"] else 0.0
        kg_slab += (2 * a_inf + 2 * 0.6 * a_sup) * 1e-4 * p["area"] * STEEL_KG_M3 * 1.12
    add("Estrutura", f"Laje maciça de cobertura C30/37, e = {h_slab:.2f} m".replace(".", ","), "m³",
        R.slab["concreto_m3"], kg_slab)
    add("Estrutura", "Cofragem de laje", "m²", R.slab["area"])
    kg_v, vol_v, cof_v = 0.0, 0.0, 0.0
    for v in R.beams:
        hb = v["h"] - h_slab
        vol_v += v["b"] * hb * v["L"]
        cof_v += (2 * hb + v["b"]) * v["L"]
        legs = 2 * (v["b"] + v["h"]) * _kg(0.503, 1.0) * v["L"] / v["s_st"]
        kg_v += (_kg(v["inf"]["as_prov"], v["L"]) + _kg(v["sup"]["as_prov"], v["L"])) * 1.15 + legs
    add("Estrutura", "Vigas de cobertura C30/37 (abaixo da laje)", "m³", vol_v, kg_v)
    add("Estrutura", "Cofragem de vigas", "m²", cof_v)
    kg_p, vol_p = 0.0, 0.0
    for c in R.columns:
        vol_p += c["a"] * c["b"] * c["H"]
        kg_p += _kg(c["armadura"]["as_prov"], c["H"] + 0.8) * 1.1 + 4 * c["a"] * _kg(0.283, 1.0) * c["H"] / 0.15
    add("Estrutura", "Pilares C30/37", "m³", vol_p, kg_p)
    add("Estrutura", "Cofragem de pilares", "m²", sum(4 * c["a"] * c["H"] for c in R.columns))
    kg_s, vol_s, exc = 0.0, 0.0, 0.0
    for s in R.footings:
        vol_s += s["B"] ** 2 * s["h"]
        exc += (s["B"] + 0.4) ** 2 * (s["h"] + 0.6)
        kg_s += 2 * _kg(s["as_m"] * s["B"], s["B"]) * 1.2
    add("Fundações", "Sapatas isoladas C30/37", "m³", vol_s, kg_s)
    add("Fundações", "Betão de limpeza C12/15 (0,10 m)", "m³", sum((s["B"] + 0.1) ** 2 * 0.10 for s in R.footings))
    kg_vf, vol_vf = 0.0, 0.0
    for v in R.tie_beams:
        vol_vf += v["b"] * v["h"] * v["L"]
        exc += (v["b"] + 0.4) * (v["h"] + 0.3) * v["L"]
        kg_vf += (_kg(v["inf"]["as_prov"], v["L"]) + _kg(v["sup"]["as_prov"], v["L"])) * 1.15 + \
            2 * (v["b"] + v["h"]) * _kg(0.503, 1.0) * v["L"] / 0.20
    add("Fundações", "Vigas de fundação C30/37", "m³", vol_vf, kg_vf)
    for m in R.retaining:
        vol = m["t"] * m["H_terras"] * m["L"] + m["sapata_B"] * m["sapata_h"] * m["L"]
        kg = vol * 95.0
        add("Fundações", f"Muro de suporte {m['id']} C30/37 (parede + sapata)", "m³", vol, kg, "taxa 95 kg/m³ a confirmar no pormenor")
        add("Fundações", f"Impermeabilização + drenagem do muro {m['id']}", "m²", m["H_terras"] * m["L"])
        exc += (m["sapata_B"] + 1.0) * (m["H_terras"] + 0.5) * m["L"]
    add("Movimento de terras", "Escavação para fundações", "m³", exc)
    add("Pavimento térreo", "Laje térrea C25/30 e = 0,15 m", "m³", R.ground_slab["concreto_m3"],
        R.ground_slab["area"] * 3.95 * 1.15, "malha Ø8//0,15 (#) = 3,95 kg/m² + 15 % sobreposições")
    add("Pavimento térreo", "Enrocamento / tout-venant compactado 0,20 m", "m³", R.ground_slab["tout_venant_m3"])
    add("Cobertura", "Impermeabilização e isolamento de cobertura invertida", "m²", R.slab["area"])
    H = b.storey_height
    by_t: dict[float, float] = {}
    ext_len = 0.0
    for w in b.walls:
        if w.retained_height > 0:
            continue
        tt = min((0.11, 0.15, 0.20, 0.25), key=lambda t: abs(t - max(w.t - 0.03, 0.11)))
        by_t[tt] = by_t.get(tt, 0.0) + w.length
        if w.exterior:
            ext_len += w.length
    for tt, L in sorted(by_t.items()):
        add("Alvenarias", f"Alvenaria de tijolo/bloco {int(tt * 100)} cm (comprimento real lido × pé-direito)", "m²",
            L * max(H - 0.40, 2.4))
    add("Revestimentos", "ETICS em paredes exteriores (cheios lidos)", "m²", ext_len * H)
    R.quantities = Q


def _sanity(b: Building, R: Result):
    """Confrontação com rácios de referência por elemento (2.ª fonte, independente do cálculo).

    Referências indicativas de moradias com laje maciça (não substituem a revisão do projetista).
    """
    def q(pred):
        return [x for x in R.quantities if pred(x["item"])]

    slab_area = max(R.slab.get("area", 0.0), 1e-9)
    sup = q(lambda t: t.startswith(("Laje maciça", "Vigas de cobertura", "Pilares")))
    fnd = q(lambda t: t.startswith(("Sapatas", "Vigas de fundação", "Muro de suporte")))
    v_sup = sum(x["qtd"] for x in sup)
    kg_sup = sum(x["aco_kg"] for x in sup)
    v_fnd = sum(x["qtd"] for x in fnd)
    kg_all = kg_sup + sum(x["aco_kg"] for x in fnd)
    rows = [
        ("espessura equivalente da cobertura (laje + vigas + pilares)", v_sup / slab_area, "m³/m²", 0.20, 0.32),
        ("betão de fundações por m² de implantação", v_fnd / max(b.footprint.area, 1e-9), "m³/m²", 0.06, 0.25),
        ("aço da superestrutura por m² de laje", kg_sup / slab_area, "kg/m²", 15.0, 40.0),
        ("taxa média de armadura (estrutura + fundações)", kg_all / max(v_sup + v_fnd, 1e-9), "kg/m³", 45.0, 110.0),
    ]
    for item, val, un, lo, hi in rows:
        ok = lo <= val <= hi
        R.checks.append({"item": item, "valor": round(val, 3), "un": un,
                         "referencia": f"{lo:g}–{hi:g}".replace(".", ","), "ok": ok})
        if not ok:
            R.warnings.append(f"Rácio fora da referência — {item}: {val:.3f} {un} (ref. {lo:g}–{hi:g}). Rever.")
