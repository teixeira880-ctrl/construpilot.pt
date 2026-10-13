"""Escalier demi-tournant DANS UNE CAGE donnée — solveur géométrique complet (déterministe).

Contrairement aux solveurs « type » (giron optimal imposé puis contrôle d'encombrement), ce module part de
la cage réelle (longueur × largeur, noyau / jour central) et cherche le giron qui la remplit :

  • Ligne de foulée (LdF) : à `walkline_offset` du jour (défaut min(500 ; emmarchement/2), NF P01-012 / DTU 36.3),
    droite le long de chaque volée, demi-cercle autour de l'extrémité du noyau.
  • Mode « balanced » (balancement) : giron CONSTANT sur la LdF = longueur LdF / nombre de marches.
    Balancement par proportionnalité : dans la zone tournante élargie de k marches de part et d'autre,
    les positions sur la ligne intérieure (jour) sont réparties linéairement → giron intérieur ≥ cible.
  • Mode « landing » : deux volées droites + palier demi-tournant (escaliers à peu de marches, ex. sous-sol).
  • Départ décalé : la volée de départ peut commencer `e` marches AVANT le bord de trémie (sous la dalle haute),
    la volée d'arrivée débouche toujours sur le bord de trémie.

Repère local (mm) : x ∈ [0, W] largeur de cage, y = 0 au bord de trémie côté départ/arrivée, y = L au mur de fond.
Volée de départ côté x > W/2 (start_side="right"), volée d'arrivée côté x < W/2. Noyau centré, de y = 0 à y_n.

Sorties : marches (polygones, hauteurs, girons LdF / intérieur / extérieur), contrôles DTU (alertes du moteur),
fonctions « ligne des nez » et « sous-face » le long de la LdF pour vérifier l'échappée entre escaliers superposés.
Pré-dimensionnement : à valider (plans de l'architecte, menuisier / BET).
"""
from __future__ import annotations

import math
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from . import alerts as A
from .blondel import find_optimal_num_steps
from .models import Alert
from .norms_fr import DTU_36_3_FR, StairNorms

VERSION = "cage-halfturn-0.1.0"
Pt = Tuple[float, float]


class CageStairInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floor_height_mm: float = Field(..., gt=0, le=8000)
    cage_length_mm: float = Field(..., gt=500, le=10000, description="Bordo da abertura → parede de fundo")
    cage_width_mm: float = Field(..., gt=500, le=6000)
    jour_mm: float = Field(default=100, ge=0, le=1500, description="Núcleo / vazio central")
    turn: Literal["balanced", "landing", "auto"] = "auto"
    max_start_extension: int = Field(default=3, ge=0, le=6, description="Degraus de arranque fora da abertura")
    start_free_length_mm: Optional[float] = Field(
        default=None, ge=0, le=5000,
        description="Comprimento máximo disponível diante da abertura para os degraus de arranque (folga deduzida)")
    walkline_offset_mm: Optional[float] = Field(default=None, gt=100, le=1000)
    inner_giron_target_mm: float = Field(default=120, gt=0, le=300)
    slab_thickness_mm: float = Field(default=220, gt=0, le=600, description="Laje superior no bordo da abertura")
    flight_thickness_mm: float = Field(default=150, gt=50, le=400, description="Laje da escada (perpendicular)")
    num_risers: Optional[int] = Field(default=None, ge=3, le=40)


class CageTread(BaseModel):
    index: int
    kind: Literal["straight", "winder", "landing"]
    surface_mm: float                    # niveau du dessus de marche / palier
    s0_mm: float                         # position début sur la LdF (σ, depuis le bord de trémie)
    s1_mm: float
    giron_walkline_mm: float
    giron_inner_mm: float
    giron_outer_mm: float
    polygon: List[Pt]


class CageStairResult(BaseModel):
    version: str = VERSION
    mode: Literal["balanced", "landing"]
    num_risers: int
    riser_mm: float
    giron_mm: float
    blondel_mm: float
    slope_deg: float
    start_extension: int
    flight_width_mm: float
    walkline_offset_mm: float
    walkline_length_mm: float
    y_noyau_mm: float
    balancing_k: int
    min_inner_giron_mm: float
    headroom_trémie_mm: float
    treads: List[CageTread]
    alerts: List[Alert]
    is_buildable: bool
    dtu_compliant: bool
    inputs: CageStairInput


# --------------------------------------------------------------------------- géométrie des chemins

class _Path:
    """Chemin droite (+y) / demi-cercle (autour du noyau) / droite (−y), paramétré par sa longueur."""

    def __init__(self, x_right: float, x_left: float, y_start: float, y_n: float, cx: float, r: float):
        self.xr, self.xl, self.y0, self.yn, self.cx, self.r = x_right, x_left, y_start, y_n, cx, r
        self.l1 = y_n - y_start
        self.la = math.pi * r
        self.l2 = y_n

    @property
    def length(self) -> float:
        return self.l1 + self.la + self.l2

    def point(self, s: float) -> Pt:
        if s <= self.l1:
            return (self.xr, self.y0 + s)
        s -= self.l1
        if s <= self.la:
            th = s / self.r if self.r > 0 else math.pi * s / max(self.la, 1e-9)
            return (self.cx + self.r * math.cos(th), self.yn + self.r * math.sin(th))
        s -= self.la
        return (self.xl, self.yn - min(s, self.l2))


def _ray_exit(p: Pt, d: Pt, box: Tuple[float, float, float, float]) -> Pt:
    """Sortie du rayon p + t·d (t > 0) du rectangle box = (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    ts = []
    for k, (lo, hi) in enumerate(((x0, x1), (y0, y1))):
        dk = d[k]
        if abs(dk) < 1e-12:
            continue
        for b in (lo, hi):
            t = (b - p[k]) / dk
            if t > 1e-9:
                q = (p[0] + t * d[0], p[1] + t * d[1])
                if x0 - 1e-6 <= q[0] <= x1 + 1e-6 and y0 - 1e-6 <= q[1] <= y1 + 1e-6:
                    ts.append(t)
    t = min(ts) if ts else 0.0
    return (p[0] + t * d[0], p[1] + t * d[1])


def _outer_param(q: Pt, W: float, L: float, y_start: float) -> float:
    """Abscisse curviligne sur le contour extérieur : (W, y_start) → (W, L) → (0, L) → (0, 0)."""
    x, y = q
    if abs(x - W) < 1e-6 and y <= L + 1e-6:
        return y - y_start
    if abs(y - L) < 1e-6:
        return (L - y_start) + (W - x)
    return (L - y_start) + W + (L - y)


def _outer_corners(W: float, L: float, y_start: float):
    return [((L - y_start), (W, L)), ((L - y_start) + W, (0.0, L))]


# --------------------------------------------------------------------------- solveur

def _checks(h: float, g: float, width: float, inner_min: float, norms: StairNorms) -> List[Alert]:
    out: List[Alert] = []
    for fn, arg in ((A.check_riser, h), (A.check_tread, g), (A.check_blondel, 2 * h + g),
                    (A.check_slope, math.degrees(math.atan2(h, g))), (A.check_stair_width, width)):
        a = fn(arg, norms)
        if a:
            out.append(a)
    if inner_min < norms.winder_inner_min_mm:
        out.append(Alert(level="red", code="BALANCING_INNER_TOO_SMALL",
                         message_fr=f'Cobertor interior {inner_min:.0f} mm < {norms.winder_inner_min_mm:.0f} mm.',
                         metric="giron_inner_mm", value=inner_min, threshold=norms.winder_inner_min_mm))
    return out


def _score(h: float, g: float, e: int, norms: StairNorms) -> float:
    b = 2 * h + g
    pen = abs(b - 630) + 2 * max(0.0, norms.tread_depth_acceptable_min_mm - g) + 15 * abs(e) + 2 * abs(h - 170)
    if not (norms.blondel_acceptable_min_mm <= b <= norms.blondel_acceptable_max_mm):
        pen += 1000
    if math.degrees(math.atan2(h, g)) > norms.slope_acceptable_max_deg:
        pen += 500
    return pen


def solve_cage(inp: CageStairInput, norms: StairNorms = DTU_36_3_FR,
               above: Optional[Tuple["CageStairResult", float]] = None) -> CageStairResult:
    """`above` = (escalier supérieur dans la même cage, hauteur d'étage de CET escalier) : les configurations
    sont essayées par score croissant jusqu'à obtenir l'échappée minimale sous l'escalier supérieur."""
    W, L, j = inp.cage_width_mm, inp.cage_length_mm, inp.jour_mm
    b = (W - j) / 2                                   # emmarchement de chaque volée
    if b < 500:
        raise ValueError("Caixa demasiado estreita: largura do degrau < 0,50 m")
    y_n = L - W / 2                                   # extrémité du noyau (zone tournante = demi-largeur)
    if y_n <= 0:
        raise ValueError("Caixa demasiado curta para uma meia volta")
    off = inp.walkline_offset_mm or min(500.0, b / 2)
    if inp.num_risers:
        n_list = [inp.num_risers]
    else:
        n0, _, _ = find_optimal_num_steps(inp.floor_height_mm, norms)
        n_list = [m for m in (n0 - 1, n0, n0 + 1)
                  if m >= 3 and norms.riser_height_acceptable_min_mm <= inp.floor_height_mm / m
                  <= norms.riser_height_acceptable_max_mm] or [n0]
    cx = W / 2
    r_w = j / 2 + off
    r_i = j / 2
    walk_core = 2 * y_n + math.pi * r_w               # LdF de y = 0 (départ) à y = 0 (arrivée)

    cands = []
    modes = ("balanced", "landing") if inp.turn == "auto" else (inp.turn,)
    for n in n_list:
      h = inp.floor_height_mm / n
      for mode in modes:
        for e in range(-2 if mode == "landing" else 0, inp.max_start_extension + 1):
            if mode == "balanced":
                g = (walk_core) / (n - 1 - e) if n - 1 - e > 0 else 0
                if g <= 0:
                    continue
                if inp.start_free_length_mm is not None and e * g > inp.start_free_length_mm + 1e-6:
                    continue
                cands.append((_score(h, g, e, norms), mode, e, g, None, n))
            else:
                for n1 in range(2, n - 1):
                    n2 = n - n1
                    if n2 < 2:
                        continue
                    g = y_n / (n2 - 1)                       # volée d'arrivée remplit y ∈ [0, y_n]
                    if abs((n1 - 1) * g - (y_n + e * g)) > 1e-6 * g and (n1 - 1) * g < y_n + e * g - 1e-6:
                        continue
                    e_eff = ((n1 - 1) * g - y_n) / g
                    if abs(e_eff - e) > 1e-6:
                        continue
                    if inp.start_free_length_mm is not None and e * g > inp.start_free_length_mm + 1e-6:
                        continue
                    cands.append((_score(h, g, e, norms) + 5, mode, e, g, n1, n))
    if not cands:
        raise ValueError("Nenhuma configuração geométrica")
    cands.sort(key=lambda c: c[0])
    best = None
    for c in cands:
        _, mode, e, g, n1, n = c
        res = _build(inp, norms, mode, e, g, n1, n, W, L, j, b, y_n, off, cx, r_w, r_i)
        if above is None:
            return res
        hr = stacked_headroom(res, above[0], above[1], shift_mm=above[2] if len(above) > 2 else 0.0)["min_headroom_mm"]
        if hr >= norms.headroom_min_mm:
            res.alerts.append(Alert(level="green", code="STACKED_HEADROOM_OK",
                                    message_fr=f'Altura livre sob a escada superior {hr:.0f} mm ≥ {norms.headroom_min_mm:.0f} mm.'))
            return res
        if best is None:
            best = (res, hr)
    res, hr = best
    res.alerts.append(Alert(level="red", code="HEADROOM_INSUFFICIENT",
                            message_fr=f'Altura livre sob a escada superior {hr:.0f} mm < {norms.headroom_min_mm:.0f} mm.',
                            metric="headroom_mm", value=hr, threshold=norms.headroom_min_mm))
    res.is_buildable = False
    res.dtu_compliant = False
    return res


def _build(inp, norms, mode, e, g, n1, n, W, L, j, b, y_n, off, cx, r_w, r_i) -> CageStairResult:
    h = inp.floor_height_mm / n
    y_start = -e * g

    walk = _Path(cx + j / 2 + off, cx - j / 2 - off, y_start, y_n, cx, r_w)
    inner = _Path(cx + j / 2, cx - j / 2, y_start, y_n, cx, r_i)
    box = (0.0, min(0.0, y_start), W, L)
    n_t = n - 1

    def inner_of(s: float, k: int) -> float:
        """Position sur la ligne intérieure correspondant à s sur la LdF (balancement, zone ±k marches)."""
        S0, S1 = walk.l1 - k * g, walk.l1 + walk.la + k * g
        T0, T1 = inner.l1 - k * g, inner.l1 + inner.la + k * g
        if s <= S0:
            return s
        if s >= S1:
            return s - walk.la + inner.la
        return T0 + (s - S0) * (T1 - T0) / (S1 - S0)

    treads: List[CageTread] = []
    k_used = 0
    if mode == "balanced":
        k_max = int(min(walk.l1, walk.l2) // g)
        for k in range(1, k_max + 1):
            gi = g * ((inner.la + 2 * k * g) / (walk.la + 2 * k * g))
            k_used = k
            if gi >= inp.inner_giron_target_mm:
                break
        bounds = [i * g for i in range(n_t + 1)]

        def line(s):
            pi_ = inner.point(inner_of(s, k_used))
            pw = walk.point(s)
            d = (pw[0] - pi_[0], pw[1] - pi_[1])
            if math.hypot(*d) < 1e-9:
                d = (1.0, 0.0)
            return pi_, _ray_exit(pi_, d, box)
        lines = [line(s) for s in bounds]
        for i in range(n_t):
            (pa, qa), (pb, qb) = lines[i], lines[i + 1]
            ua, ub = _outer_param(qa, W, L, y_start), _outer_param(qb, W, L, y_start)
            poly = [pa, qa] + [c for u, c in _outer_corners(W, L, y_start) if ua < u < ub] + [qb, pb]
            ta, tb = inner_of(bounds[i], k_used), inner_of(bounds[i + 1], k_used)
            # points intermédiaires sur le noyau (arc intérieur)
            mids = []
            for m in range(1, 8):
                t = tb - (tb - ta) * m / 8
                if inner.l1 < t < inner.l1 + inner.la:
                    mids.append(inner.point(t))
            poly += mids
            in_turn = not (bounds[i + 1] <= walk.l1 - 1e-6 or bounds[i] >= walk.l1 + walk.la + 1e-6)
            g_in = tb - ta
            g_out = ub - ua
            treads.append(CageTread(index=i + 1, kind="winder" if abs(g_in - g) > 1 else "straight",
                                    surface_mm=round((i + 1) * h, 1), s0_mm=round(bounds[i] + y_start, 1),
                                    s1_mm=round(bounds[i + 1] + y_start, 1), giron_walkline_mm=round(g, 1),
                                    giron_inner_mm=round(g_in, 1), giron_outer_mm=round(g_out, 1),
                                    polygon=[(round(x, 1), round(y, 1)) for x, y in poly]))
    else:
        # volée 1 : n1−1 marches droites de y_start à y_n ; palier ; volée 2 : n2−1 marches de y_n à 0
        n2 = n - n1
        xr0, xr1, xl0, xl1 = cx + j / 2, W, 0.0, cx - j / 2
        idx = 0
        for i in range(n1 - 1):
            y0_, y1_ = y_start + i * g, y_start + (i + 1) * g
            idx += 1
            treads.append(CageTread(index=idx, kind="straight", surface_mm=round(idx * h, 1), s0_mm=round(y0_, 1),
                                    s1_mm=round(y1_, 1), giron_walkline_mm=round(g, 1), giron_inner_mm=round(g, 1),
                                    giron_outer_mm=round(g, 1),
                                    polygon=[(xr0, y0_), (xr1, y0_), (xr1, y1_), (xr0, y1_)]))
        idx += 1
        s_land0 = y_n
        treads.append(CageTread(index=idx, kind="landing", surface_mm=round(idx * h, 1), s0_mm=round(s_land0, 1),
                                s1_mm=round(s_land0 + walk.la, 1), giron_walkline_mm=round(walk.la, 1),
                                giron_inner_mm=round(inner.la, 1), giron_outer_mm=round(W + 2 * (L - y_n), 1),
                                polygon=[(0.0, y_n), (W, y_n), (W, L), (0.0, L)]))
        for i in range(n2 - 1):
            y1_, y0_ = y_n - i * g, y_n - (i + 1) * g
            idx += 1
            treads.append(CageTread(index=idx, kind="straight", surface_mm=round(idx * h, 1),
                                    s0_mm=round(y_n + walk.la + i * g, 1), s1_mm=round(y_n + walk.la + (i + 1) * g, 1),
                                    giron_walkline_mm=round(g, 1), giron_inner_mm=round(g, 1), giron_outer_mm=round(g, 1),
                                    polygon=[(xl0, y1_), (xl1, y1_), (xl1, y0_), (xl0, y0_)]))
    inner_min = min(t.giron_inner_mm for t in treads if t.kind != "landing")
    alerts = _checks(h, g, b, inner_min, norms)
    # échappée au bord de trémie (volée de départ sous la dalle haute) : ligne des nez à y = 0
    z_nose_0 = h + (-y_start) * h / g
    head_tremie = (inp.floor_height_mm - inp.slab_thickness_mm) - z_nose_0
    if e > 0:
        ha = A.check_headroom(head_tremie, None, norms)
        if ha:
            alerts.append(ha)
    is_buildable = A.compute_is_buildable(alerts)
    dtu = not any(a.level == "red" for a in alerts)
    if mode == "balanced":
        alerts.append(Alert(level="green", code="CAGE_BALANCED",
                            message_fr=f'Meia volta com degraus em leque na caixa: {n} alturas de {h:.1f} mm, cobertor {g:.0f} mm na linha de passo, cobertor interior mínimo {inner_min:.0f} mm (balancement k={k_used}).'))
    return CageStairResult(mode=mode, num_risers=n, riser_mm=round(h, 2), giron_mm=round(g, 1),
                           blondel_mm=round(2 * h + g, 1), slope_deg=round(math.degrees(math.atan2(h, g)), 2),
                           start_extension=e, flight_width_mm=round(b, 1), walkline_offset_mm=round(off, 1),
                           walkline_length_mm=round(walk.length, 1), y_noyau_mm=round(y_n, 1), balancing_k=k_used,
                           min_inner_giron_mm=round(inner_min, 1),
                           headroom_trémie_mm=round(head_tremie, 1) if e > 0 else -1,
                           treads=treads, alerts=A.summarize(alerts) if hasattr(A, "summarize") else alerts,
                           is_buildable=is_buildable, dtu_compliant=dtu, inputs=inp)


# --------------------------------------------------------------------------- escaliers superposés

def nosing_line(res: CageStairResult, sigma: float) -> Optional[float]:
    """Hauteur de la ligne des nez (relative au départ de CET escalier) à la position σ de la LdF."""
    h, g = res.riser_mm, res.giron_mm
    s = sigma - res.treads[0].s0_mm
    if s < 0:
        return None
    if res.mode == "balanced":
        return h + s * h / g if s <= (res.num_risers - 1) * g else None
    for t in res.treads:
        if t.s0_mm - 1e-6 <= sigma <= t.s1_mm + 1e-6:
            if t.kind == "landing":
                return t.surface_mm
            return t.surface_mm + (sigma - t.s0_mm) * h / g
    return None


def soffit(res: CageStairResult, sigma: float) -> Optional[float]:
    """Sous-face de la paillasse (relative au départ) : ligne des rentrants − e/cos α ; palier : niveau − e."""
    z = nosing_line(res, sigma)
    if z is None:
        return None
    t_p = res.inputs.flight_thickness_mm
    for t in res.treads:
        if t.kind == "landing" and t.s0_mm - 1e-6 <= sigma <= t.s1_mm + 1e-6:
            return z - t_p
    return z - res.riser_mm - t_p / math.cos(math.radians(res.slope_deg))


def stacked_headroom(lower: CageStairResult, upper: CageStairResult, storey_mm: float, step: float = 25.0,
                     shift_mm: float = 0.0) -> dict:
    """Échappée minimale de l'escalier `lower` sous l'escalier `upper` (même cage, même tracé de LdF),
    `upper` démarrant à `storey_mm` au-dessus du départ de `lower`. Au-delà du départ de `upper`
    (σ < départ), l'obstacle est la dalle de l'étage (sous-face = storey − épaisseur).
    `shift_mm` = y0(lower) − y0(upper) : décalage des bords de trémie (même fond de cage, même tracé de LdF)."""
    worst = (float("inf"), None)
    s_end = lower.treads[-1].s1_mm
    sigma = lower.treads[0].s0_mm
    while sigma <= s_end:
        zl = nosing_line(lower, sigma)
        if zl is not None:
            su = sigma + shift_mm
            sf = soffit(upper, su)
            if sf is not None:
                top = storey_mm + sf
            elif su < upper.treads[0].s0_mm:
                top = storey_mm - upper.inputs.slab_thickness_mm
            else:
                top = None
            if top is not None and top - zl < worst[0]:
                worst = (top - zl, sigma)
        sigma += step
    return {"min_headroom_mm": round(worst[0], 1), "at_sigma_mm": worst[1]}
