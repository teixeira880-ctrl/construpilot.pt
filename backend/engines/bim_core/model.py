"""Modelo de edifício neutro, em METROS, construído a partir da planta lida pelo módulo Plantas.

A leitura IA (`engines/plan_structure.py`) e a deteção de divisões (`plan_cv`) guardam a geometria em
PÍXEIS da imagem da página, com o eixo y para baixo. Este módulo converte tudo para um modelo métrico
(eixo y para cima, origem no canto inferior esquerdo do conjunto), associa cada vão à parede que o
contém e regista avisos em vez de inventar o que falta. Nenhum valor é gerado por IA aqui.

O modelo é a entrada do construtor IFC (`ifc_builder.py`) e será a mesma entrada dos motores de
cálculo quando estes passarem a ler o modelo BIM.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Valores por omissão (prática corrente em habitação PT/FR) — todos alteráveis pelo profissional.
DEFAULTS = {
    "wall_height": 2.70,       # pé-direito estrutural (m)
    "voile_ep": 0.20,          # parede resistente (m)
    "cloison_ep": 0.10,        # divisória (m)
    "dalle_ep": 0.20,          # laje (m)
    "poutre_l": 0.20,          # largura de viga (m)
    "poutre_h": 0.40,          # altura de viga (m)
    "semelle_h": 0.40,         # altura de sapata (m)
    "door_height": 2.10,
    "window_sill": 0.90,
    "window_height": 1.20,
    "baie_height": 2.20,
}

# Um vão só é associado a uma parede se estiver a menos desta distância do eixo da parede (m)
# e quase paralelo a ela.
OPENING_SNAP_M = 0.35
PARALLEL_TOL = 0.12  # |sin(ângulo)| máximo entre o vão e a parede


class ModelError(ValueError):
    """Dados insuficientes para construir um modelo (ex.: planta não calibrada)."""


@dataclass
class Wall:
    source_id: str
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float
    height: float
    load_bearing: bool

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def angle(self) -> float:
        return math.atan2(self.y2 - self.y1, self.x2 - self.x1)


@dataclass
class Opening:
    source_id: str
    kind: str              # porte | fenetre | baie
    wall_id: str
    offset: float          # distância desde o início da parede até ao início do vão (m)
    width: float
    sill: float
    height: float


@dataclass
class Slab:
    source_id: str
    name: str
    points: list[tuple[float, float]]
    thickness: float
    elevation_ngf: float | None

    @property
    def area(self) -> float:
        return abs(_shoelace(self.points))


@dataclass
class Column:
    source_id: str
    cx: float
    cy: float
    dx: float
    dy: float
    height: float
    ref: str = ""


@dataclass
class Beam:
    source_id: str
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    depth: float

    @property
    def length(self) -> float:
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)


@dataclass
class Footing:
    source_id: str
    cx: float
    cy: float
    dx: float
    dy: float
    depth: float


@dataclass
class Space:
    source_id: str
    name: str
    points: list[tuple[float, float]]
    height: float

    @property
    def area(self) -> float:
        return abs(_shoelace(self.points))


@dataclass
class BuildingModel:
    plan_id: str
    page_index: int
    storey_name: str
    params: dict
    walls: list[Wall] = field(default_factory=list)
    openings: list[Opening] = field(default_factory=list)
    slabs: list[Slab] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    beams: list[Beam] = field(default_factory=list)
    footings: list[Footing] = field(default_factory=list)
    spaces: list[Space] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    ifc_guids: bool = False      # True: source_id já é o GlobalId do IFC de origem
    origin: tuple = (0.0, 0.0)   # deslocamento aplicado às coordenadas do IFC importado (m)

    def counts(self) -> dict:
        return {"walls": len(self.walls), "openings": len(self.openings), "slabs": len(self.slabs),
                "columns": len(self.columns), "beams": len(self.beams),
                "footings": len(self.footings), "spaces": len(self.spaces)}


def _shoelace(pts) -> float:
    s = 0.0
    for i, (x1, y1) in enumerate(pts):
        x2, y2 = pts[(i + 1) % len(pts)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _num(v, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) and f > 0 else default


def _rect(it: dict):
    try:
        x1, y1, x2, y2 = (float(it[k]) for k in ("x1", "y1", "x2", "y2"))
    except (KeyError, TypeError, ValueError):
        return None
    return x1, y1, x2, y2


def from_takeoff(structure: dict, ppm: float | None, *, rooms: list | None = None,
                 plan_id: str = "", page_index: int = 0, storey_name: str = "Piso 0",
                 params: dict | None = None) -> BuildingModel:
    """Converte a estrutura de uma página (píxeis) num `BuildingModel` métrico.

    `structure` tem o formato devolvido por `plan_structure._to_px` (paredes, vãos, vigas, lajes,
    pilares, sapatas). `rooms` são as divisões medidas (`points` em píxeis). Exige uma calibração
    (`ppm` = píxeis por metro) — sem ela as dimensões seriam inventadas.
    """
    if not ppm or float(ppm) <= 0:
        raise ModelError("Planta não calibrada: defina a escala antes de gerar o modelo BIM.")
    ppm = float(ppm)
    p = {**DEFAULTS, **{k: v for k, v in (params or {}).items() if v is not None}}
    for k in DEFAULTS:
        p[k] = _num(p[k], DEFAULTS[k])
    structure = structure or {}
    rooms = rooms or []

    # Origem: canto inferior esquerdo de toda a geometria, para o modelo ficar perto de (0, 0).
    xs, ys = [], []
    # (os vãos não entram: um vão isolado, sem parede, não deve deslocar a origem)
    for key in ("walls", "beams", "columns", "footings"):
        for it in structure.get(key) or []:
            r = _rect(it) if isinstance(it, dict) else None
            if r:
                xs += [r[0], r[2]]
                ys += [r[1], r[3]]
    for f in (structure.get("floors") or []) + list(rooms):
        for pt in (f.get("points") or []) if isinstance(f, dict) else []:
            if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                xs.append(float(pt[0]))
                ys.append(float(pt[1]))
    if not xs:
        raise ModelError("A planta não tem geometria lida: execute primeiro a deteção da estrutura.")
    ox, oy = min(xs), max(ys)

    def X(px):
        return round((float(px) - ox) / ppm, 4)

    def Y(py):
        return round((oy - float(py)) / ppm, 4)

    m = BuildingModel(plan_id=plan_id, page_index=page_index, storey_name=storey_name, params=p)

    for it in structure.get("walls") or []:
        r = _rect(it) if isinstance(it, dict) else None
        if not r:
            continue
        lb = it.get("type") == "porteur"
        w = Wall(source_id=str(it.get("wall_id") or f"w{len(m.walls)}"),
                 x1=X(r[0]), y1=Y(r[1]), x2=X(r[2]), y2=Y(r[3]),
                 thickness=_num(it.get("thickness_m"), p["voile_ep"] if lb else p["cloison_ep"]),
                 height=p["wall_height"], load_bearing=lb)
        if w.length < 0.05:
            m.warnings.append({"code": "wall_too_short", "source_id": w.source_id})
            continue
        m.walls.append(w)

    for it in structure.get("openings") or []:
        r = _rect(it) if isinstance(it, dict) else None
        if not r:
            continue
        sid = str(it.get("opening_id") or f"o{len(m.openings)}")
        a = (X(r[0]), Y(r[1]))
        b = (X(r[2]), Y(r[3]))
        host = _host_wall(m.walls, a, b)
        if host is None:
            m.warnings.append({"code": "opening_without_wall", "source_id": sid})
            continue
        wall, t0, t1 = host
        kind = it.get("kind") if it.get("kind") in ("porte", "fenetre", "baie") else "fenetre"
        if kind == "porte":
            sill, h = 0.0, p["door_height"]
        elif kind == "baie":
            sill, h = 0.0, p["baie_height"]
        else:
            sill, h = p["window_sill"], p["window_height"]
        h = min(h, wall.height - sill - 0.05)
        width = t1 - t0
        if width < 0.30 or h <= 0.3:
            m.warnings.append({"code": "opening_too_small", "source_id": sid})
            continue
        m.openings.append(Opening(source_id=sid, kind=kind, wall_id=wall.source_id,
                                  offset=round(t0, 4), width=round(width, 4), sill=sill, height=h))

    for it in structure.get("floors") or []:
        if not isinstance(it, dict):
            continue
        pts = [(X(pt[0]), Y(pt[1])) for pt in it.get("points") or []
               if isinstance(pt, (list, tuple)) and len(pt) >= 2]
        pts = _clean_polygon(pts)
        sid = str(it.get("floor_id") or f"f{len(m.slabs)}")
        if len(pts) < 3 or abs(_shoelace(pts)) < 0.5:
            m.warnings.append({"code": "slab_degenerate", "source_id": sid})
            continue
        th = it.get("thickness_cm")
        m.slabs.append(Slab(source_id=sid, name=str(it.get("name") or "Laje")[:60], points=pts,
                            thickness=_num(th, p["dalle_ep"] * 100) / 100.0,
                            elevation_ngf=_float_or_none(it.get("ngf"))))

    for it in structure.get("columns") or []:
        r = _rect(it) if isinstance(it, dict) else None
        if not r:
            continue
        dx, dy = abs(r[2] - r[0]) / ppm, abs(r[3] - r[1]) / ppm
        sid = str(it.get("column_id") or f"c{len(m.columns)}")
        if min(dx, dy) < 0.08 or max(dx, dy) > 2.0:
            m.warnings.append({"code": "column_section_suspicious", "source_id": sid,
                               "section_m": [round(dx, 3), round(dy, 3)]})
            continue
        m.columns.append(Column(source_id=sid, cx=X((r[0] + r[2]) / 2), cy=Y((r[1] + r[3]) / 2),
                                dx=round(dx, 4), dy=round(dy, 4), height=p["wall_height"],
                                ref=str(it.get("ref") or "")))

    for it in structure.get("beams") or []:
        r = _rect(it) if isinstance(it, dict) else None
        if not r:
            continue
        bm = Beam(source_id=str(it.get("beam_id") or f"b{len(m.beams)}"),
                  x1=X(r[0]), y1=Y(r[1]), x2=X(r[2]), y2=Y(r[3]),
                  width=_num(it.get("width_m"), p["poutre_l"]),
                  depth=_num(it.get("height_m"), p["poutre_h"]))
        if bm.length < 0.2:
            m.warnings.append({"code": "beam_too_short", "source_id": bm.source_id})
            continue
        m.beams.append(bm)

    for it in structure.get("footings") or []:
        r = _rect(it) if isinstance(it, dict) else None
        if not r:
            continue
        dx, dy = abs(r[2] - r[0]) / ppm, abs(r[3] - r[1]) / ppm
        sid = str(it.get("footing_id") or f"ft{len(m.footings)}")
        if min(dx, dy) < 0.2:
            m.warnings.append({"code": "footing_too_small", "source_id": sid})
            continue
        m.footings.append(Footing(source_id=sid, cx=X((r[0] + r[2]) / 2), cy=Y((r[1] + r[3]) / 2),
                                  dx=round(dx, 4), dy=round(dy, 4), depth=p["semelle_h"]))

    for i, rm in enumerate(rooms):
        if not isinstance(rm, dict):
            continue
        pts = _clean_polygon([(X(pt[0]), Y(pt[1])) for pt in rm.get("points") or []
                              if isinstance(pt, (list, tuple)) and len(pt) >= 2])
        sid = str(rm.get("room_id") or rm.get("id") or f"r{i}")
        if len(pts) < 3 or abs(_shoelace(pts)) < 0.5:
            continue
        m.spaces.append(Space(source_id=sid, name=str(rm.get("name") or rm.get("label") or "Divisão")[:60],
                              points=pts, height=p["wall_height"]))

    if not (m.walls or m.slabs or m.columns or m.beams or m.footings):
        raise ModelError("Nenhum elemento construtivo utilizável na planta.")
    return m


def _float_or_none(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _clean_polygon(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Retira pontos repetidos, fecha implicitamente e orienta no sentido anti-horário."""
    out: list[tuple[float, float]] = []
    for pt in pts:
        if not out or math.hypot(pt[0] - out[-1][0], pt[1] - out[-1][1]) > 1e-3:
            out.append(pt)
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= 1e-3:
        out.pop()
    if len(out) >= 3 and _shoelace(out) < 0:
        out.reverse()
    return out


def _host_wall(walls: list[Wall], a, b):
    """Parede que contém o segmento de vão [a, b] → (parede, t0, t1) ao longo da parede, ou None."""
    best = None
    ux_o, uy_o = b[0] - a[0], b[1] - a[1]
    lo = math.hypot(ux_o, uy_o)
    if lo < 1e-6:
        return None
    for w in walls:
        L = w.length
        ux, uy = (w.x2 - w.x1) / L, (w.y2 - w.y1) / L
        sin = abs(ux * uy_o / lo - uy * ux_o / lo)
        if sin > PARALLEL_TOL:
            continue
        ta = (a[0] - w.x1) * ux + (a[1] - w.y1) * uy
        tb = (b[0] - w.x1) * ux + (b[1] - w.y1) * uy
        da = abs(-(a[0] - w.x1) * uy + (a[1] - w.y1) * ux)
        db = abs(-(b[0] - w.x1) * uy + (b[1] - w.y1) * ux)
        dist = max(da, db)
        if dist > OPENING_SNAP_M:
            continue
        t0, t1 = sorted((ta, tb))
        t0, t1 = max(t0, 0.0), min(t1, L)
        if t1 - t0 < 0.5 * lo:   # menos de metade do vão sobre a parede
            continue
        if best is None or dist < best[3]:
            best = (w, t0, t1, dist)
    return best[:3] if best else None
