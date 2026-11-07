"""Terreno: polígono do prédio, referencial da frente (o mesmo do editor de volumes) e topografia indicativa.

Referencial do editor de volumes (engines.urbanismo_pt.volumes): origem no canto frente-esquerda do terreno visto da via,
x ao longo da frente (para a direita), y para o tardoz. Aqui construímos esse referencial a partir da via mais próxima
(OpenStreetMap) e da posição da morada, para que os desenhos, o 3D e a orientação solar usem exatamente a mesma geometria.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

FRENTE_PADRAO_M = 20.0
AREA_PADRAO_M2 = 600.0


class Local:
    """Projeção local equirretangular (erro < 1 cm a 100 m): (lat, lon) ↔ (este, norte) em metros."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111_320.0 * math.cos(math.radians(lat0))
        self.ky = 111_320.0

    def xy(self, lat: float, lon: float) -> Tuple[float, float]:
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky

    def ll(self, e: float, n: float) -> Tuple[float, float]:
        return self.lat0 + n / self.ky, self.lon0 + e / self.kx


def _unit(v):
    L = math.hypot(*v) or 1.0
    return v[0] / L, v[1] / L


def azimute(v) -> float:
    """Azimute (graus, 0 = norte, 90 = este) de um vetor (este, norte)."""
    return (math.degrees(math.atan2(v[0], v[1])) + 360.0) % 360.0


class Referencial:
    """Referencial da frente: origem = canto frente-esquerda; ex = ao longo da frente; ey = para o tardoz (em EN)."""

    def __init__(self, origem_en: Tuple[float, float], ey: Tuple[float, float]):
        self.o = origem_en
        self.ey = _unit(ey)
        self.ex = (self.ey[1], -self.ey[0])   # direita de quem olha da via para o terreno

    def para_local(self, e: float, n: float) -> Tuple[float, float]:
        dx, dy = e - self.o[0], n - self.o[1]
        return dx * self.ex[0] + dy * self.ex[1], dx * self.ey[0] + dy * self.ey[1]

    def para_en(self, x: float, y: float) -> Tuple[float, float]:
        return self.o[0] + x * self.ex[0] + y * self.ey[0], self.o[1] + x * self.ex[1] + y * self.ey[1]

    def azimute_fachada(self, lado: str) -> float:
        """Azimute da normal exterior de uma fachada: frente (para a via), tardoz, esquerda, direita."""
        v = {"frente": (-self.ey[0], -self.ey[1]), "tardoz": self.ey,
             "esquerda": (-self.ex[0], -self.ex[1]), "direita": self.ex}[lado]
        return azimute(v)


def _area(pts) -> float:
    a = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def construir_terreno(geo: Dict[str, Any], via: Optional[Dict[str, Any]], cad: Optional[Dict[str, Any]],
                      area_m2: Optional[float] = None, frente_m: Optional[float] = None) -> Dict[str, Any]:
    """Polígono do terreno no referencial da frente + metadados de origem (oficial / indicado / hipótese)."""
    lat, lon = geo["lat"], geo["lon"]
    loc = Local(lat, lon)
    pressupostos: List[str] = []
    # direção da via e normal para o terreno
    if via and via.get("ok"):
        a, b = via["data"]["a"], via["data"]["b"]
        ae, be = loc.xy(*a), loc.xy(*b)
        u = _unit((be[0] - ae[0], be[1] - ae[1]))
        # pé da perpendicular da morada (0,0) sobre a via
        t = -(ae[0] * u[0] + ae[1] * u[1])
        foot = (ae[0] + t * u[0], ae[1] + t * u[1])
        nvec = (-foot[0], -foot[1])
        if math.hypot(*nvec) < 0.5:          # morada sobre o eixo da via: o terreno fica do lado esquerdo do sentido da via
            nvec = (-u[1], u[0])
        ey = _unit(nvec)
        dist_via = math.hypot(*foot)
        fonte_frente = f"via mais próxima ({via['data'].get('nome') or via['data'].get('tipo') or 'OSM'})"
    else:
        ey, foot, dist_via = (0.0, 1.0), (0.0, -6.0), 6.0
        fonte_frente = "hipótese (frente virada a sul)"
        pressupostos.append("Não foi possível identificar a via de acesso: assumiu-se a frente do terreno virada a sul.")

    if cad and cad.get("ok"):
        ring_en = [loc.xy(la, lo) for lo, la in cad["data"]["anel_lonlat"]]
        if ring_en[0] == ring_en[-1]:
            ring_en = ring_en[:-1]
        # frente = vértice mais próximo da via define a origem; referencial alinhado com a via
        ref0 = Referencial((0.0, 0.0), ey)
        loc_pts = [ref0.para_local(*p) for p in ring_en]
        min_x = min(p[0] for p in loc_pts)
        min_y = min(p[1] for p in loc_pts)
        ref = Referencial(ref0.para_en(min_x, min_y), ey)
        poly = [ref.para_local(*p) for p in ring_en]
        origem_area = cad["fonte"]
        area = _area(poly)
        if area_m2 and abs(area_m2 - area) / max(area, 1) > 0.1:
            pressupostos.append(f"A área indicada ({area_m2:.0f} m²) difere da área cadastral ({area:.0f} m²): usou-se a cadastral; "
                                "confirmar com a certidão predial.")
    else:
        F = float(frente_m or 0) or FRENTE_PADRAO_M
        A = float(area_m2 or 0) or AREA_PADRAO_M2
        if not frente_m:
            F = min(max(math.sqrt(A / 1.5), 12.0), 40.0) if area_m2 else FRENTE_PADRAO_M
        D = A / F
        # limite frontal: a 1 m da via (ou na morada se esta estiver longe da via), centrado na morada
        recuo = max(1.0, min(dist_via - 2.0, 6.0)) if dist_via > 3 else 1.0
        front_mid = (foot[0] + ey[0] * recuo, foot[1] + ey[1] * recuo)
        ex = (ey[1], -ey[0])
        origem = (front_mid[0] - ex[0] * F / 2, front_mid[1] - ex[1] * F / 2)
        ref = Referencial(origem, ey)
        poly = [(0.0, 0.0), (F, 0.0), (F, D), (0.0, D)]
        area = F * D
        if area_m2:
            origem_area = "indicada pelo requerente"
            pressupostos.append(f"Forma do terreno assumida retangular ({F:.1f} m de frente × {D:.1f} m de profundidade) com a área "
                                "indicada: confirmar no levantamento topográfico.")
        else:
            origem_area = "hipótese"
            pressupostos.append(f"Sem cadastro geométrico nem área indicada: assumiu-se um terreno de {A:.0f} m² "
                                f"({F:.0f} m de frente × {D:.0f} m). Indique a área da caderneta para afinar.")

    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    plot_l, plot_w = max(xs) - min(xs), max(ys) - min(ys)
    poly_ll = [loc.ll(*ref.para_en(x, y)) for x, y in poly]
    return {
        "poligono_m": [(round(x, 3), round(y, 3)) for x, y in poly],
        "poligono_latlon": [(round(a, 7), round(b, 7)) for a, b in poly_ll],
        "area_m2": round(area, 2), "area_origem": origem_area,
        "plot_l_m": round(plot_l, 2), "plot_w_m": round(plot_w, 2),
        "retangular": abs(area - plot_l * plot_w) < 0.02 * area,
        "frente_fonte": fonte_frente,
        "azimute_frente": round(ref.azimute_fachada("frente"), 1),
        "azimutes": {k: round(ref.azimute_fachada(k), 1) for k in ("frente", "tardoz", "esquerda", "direita")},
        "_ref": ref, "_local": loc,
        "pressupostos": pressupostos,
    }


def grelha_pontos(ter: Dict[str, Any], n: int = 9, margem: float = 6.0) -> List[Tuple[float, float, float, float]]:
    """Pontos (x, y, lat, lon) de uma grelha n×n sobre o terreno (+ margem), no referencial da frente."""
    ref, loc = ter["_ref"], ter["_local"]
    L, W = ter["plot_l_m"], ter["plot_w_m"]
    out = []
    for j in range(n):
        for i in range(n):
            x = -margem + (L + 2 * margem) * i / (n - 1)
            y = -margem + (W + 2 * margem) * j / (n - 1)
            la, lo = loc.ll(*ref.para_en(x, y))
            out.append((round(x, 3), round(y, 3), la, lo))
    return out


def topografia(pts: List[Tuple[float, float, float, float]], z: List[Optional[float]], fonte: str,
               nota: Optional[str]) -> Dict[str, Any]:
    """Plano médio z = a + b·x + c·y (mínimos quadrados), declive, sentido de descida e grelha para o 3D."""
    data = [(p[0], p[1], zz) for p, zz in zip(pts, z) if zz is not None]
    if len(data) < 3:
        return {"ok": False}
    n = len(data)
    sx = sum(d[0] for d in data); sy = sum(d[1] for d in data); sz = sum(d[2] for d in data)
    sxx = sum(d[0] ** 2 for d in data); syy = sum(d[1] ** 2 for d in data); sxy = sum(d[0] * d[1] for d in data)
    sxz = sum(d[0] * d[2] for d in data); syz = sum(d[1] * d[2] for d in data)
    # sistema normal 3×3
    M = [[n, sx, sy], [sx, sxx, sxy], [sy, sxy, syy]]
    r = [sz, sxz, syz]
    a, b, c = _solve3(M, r)
    resid = [d[2] - (a + b * d[0] + c * d[1]) for d in data]
    rms = math.sqrt(sum(e * e for e in resid) / n)
    declive = math.hypot(b, c) * 100.0
    zs = [d[2] for d in data]
    return {"ok": True, "fonte": fonte, "nota": nota, "z_min": round(min(zs), 2), "z_max": round(max(zs), 2),
            "z_medio": round(sz / n, 2), "plano": {"a": a, "b": b, "c": c}, "rms_m": round(rms, 2),
            "declive_pct": round(declive, 1),
            "descida": ("frente" if c > 0 else "tardoz") if abs(c) >= abs(b) else ("esquerda" if b > 0 else "direita"),
            "grelha": [{"x": d[0], "y": d[1], "z": round(d[2], 2)} for d in data]}


def _solve3(M, r):
    import copy
    A = copy.deepcopy(M)
    v = list(r)
    for i in range(3):
        p = max(range(i, 3), key=lambda k: abs(A[k][i]))
        A[i], A[p] = A[p], A[i]
        v[i], v[p] = v[p], v[i]
        piv = A[i][i] or 1e-12
        for k in range(i + 1, 3):
            f = A[k][i] / piv
            for j in range(i, 3):
                A[k][j] -= f * A[i][j]
            v[k] -= f * v[i]
    x = [0.0, 0.0, 0.0]
    for i in (2, 1, 0):
        x[i] = (v[i] - sum(A[i][j] * x[j] for j in range(i + 1, 3))) / (A[i][i] or 1e-12)
    return x


def cota(topo: Dict[str, Any], x: float, y: float) -> Optional[float]:
    if not topo or not topo.get("ok"):
        return None
    p = topo["plano"]
    return p["a"] + p["b"] * x + p["c"] * y
