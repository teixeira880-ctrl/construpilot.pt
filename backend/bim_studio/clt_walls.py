"""CLT wall network: junctions, production pieces and cross-checked quantities.

Each wall is an axis segment in metres with a confirmed thickness and height.
The engine resolves the junctions so that no volume is counted twice, splits
pieces that exceed the press format, and checks the result with three
independent measurements:

1. sum of the drawn axis lengths (what a manual take-off does);
2. union of the plan footprints divided by the thickness (Shapely/GEOS);
3. sum of the production pieces after junction resolution.

Methods 2 and 3 must agree within 2 %. Method 1 differs only by the overlap
at the junctions, which the result reports as the double count avoided.
"""
from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator
from shapely import union_all
from shapely.geometry import LineString, Point, Polygon

from bim_studio.clt_geometry import reconciliation

Metres = Annotated[float, Field(ge=0, le=10_000, allow_inf_nan=False)]

# Rezult technical characteristics (clt-rezult.com/en/technical-characteristics,
# read 2026-11-11): length ≤ 18.00 m, width ≤ 3.50 m, thickness 60 to 360 mm.
REZULT_FORMAT = {"max_length_m": 18.0, "max_width_m": 3.5, "min_thickness_mm": 60, "max_thickness_mm": 360,
                 "source": "Rezult, características técnicas (clt-rezult.com/en/technical-characteristics), lido em 2026-11-11"}
SNAP_M = 0.005


class Opening(BaseModel):
    offset_m: Metres = Field(description="Distância do início do eixo ao lado esquerdo do vão")
    width_m: Annotated[float, Field(gt=0, le=100, allow_inf_nan=False)]
    sill_m: Metres = 0.0
    height_m: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)]
    kind: Literal["janela", "porta", "vao"] = "janela"
    label: str = Field(default="", max_length=60)


class WallAxis(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    x1: float = Field(allow_inf_nan=False)
    y1: float = Field(allow_inf_nan=False)
    x2: float = Field(allow_inf_nan=False)
    y2: float = Field(allow_inf_nan=False)
    thickness_mm: Annotated[float, Field(gt=0, le=500, allow_inf_nan=False)]
    layers: Annotated[int, Field(ge=3, le=13)] = 5
    height_m: Annotated[float, Field(gt=0, le=20, allow_inf_nan=False)]
    base_z_m: float = Field(default=0.0, allow_inf_nan=False)
    openings: list[Opening] = Field(default_factory=list, max_length=40)
    source: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def valid(self):
        if self.length < 0.05:
            raise ValueError(f"A parede {self.id} tem menos de 5 cm de eixo.")
        for o in self.openings:
            if o.offset_m + o.width_m > self.length + 1e-6 or o.sill_m + o.height_m > self.height_m + 1e-6:
                raise ValueError(f"O vão {o.label or o.kind} sai da parede {self.id}.")
        spans = sorted((o.offset_m, o.offset_m + o.width_m) for o in self.openings)
        if any(b[0] < a[1] - 1e-9 for a, b in zip(spans, spans[1:])):
            raise ValueError(f"Há vãos sobrepostos na parede {self.id}.")
        return self

    @property
    def length(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    @property
    def thickness_m(self):
        return self.thickness_mm / 1000

    def footprint(self, extend_start=0.0, extend_end=0.0):
        ux, uy = self.direction()
        start = (self.x1 - ux * extend_start, self.y1 - uy * extend_start)
        end = (self.x2 + ux * extend_end, self.y2 + uy * extend_end)
        return LineString([start, end]).buffer(self.thickness_m / 2, cap_style="flat")

    def direction(self):
        return ((self.x2 - self.x1) / self.length, (self.y2 - self.y1) / self.length)


class Floor(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    walls: list[WallAxis] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def unique(self):
        if len({w.id for w in self.walls}) != len(self.walls):
            raise ValueError("Cada parede precisa de um identificador único.")
        return self


def footprints(walls):
    """Plan footprints. Axes that meet end to end (an L corner drawn on the
    axes) are extended by half the other wall's thickness so the outer corner
    is closed, as IFC wall joins do. Ends that stop on a face are kept."""
    out = {}
    for w in walls:
        ext = [0.0, 0.0]
        for k, end in enumerate(((w.x1, w.y1), (w.x2, w.y2))):
            for o in walls:
                if o is w:
                    continue
                cos = abs(w.direction()[0] * o.direction()[0] + w.direction()[1] * o.direction()[1])
                if cos < 0.999 and min(math.dist(end, (o.x1, o.y1)), math.dist(end, (o.x2, o.y2))) <= SNAP_M:
                    ext[k] = max(ext[k], o.thickness_m / 2)
        out[w.id] = w.footprint(*ext)
    return out


def _extent(polygon, wall):
    """Interval of a polygon projected on the wall axis, in metres from its start."""
    ux, uy = wall.direction()
    values = [(x - wall.x1) * ux + (y - wall.y1) * uy for x, y in polygon.exterior.coords]
    return min(values), max(values)


def _junctions(walls):
    """Classify each wall end that touches another wall as L, T or X."""
    out = []
    feet = footprints(walls)
    for i, a in enumerate(walls):
        for b in walls[i + 1:]:
            if not feet[a.id].buffer(SNAP_M).intersects(feet[b.id]):
                continue
            ends_a = [Point(p) for p in ((a.x1, a.y1), (a.x2, a.y2))]
            ends_b = [Point(p) for p in ((b.x1, b.y1), (b.x2, b.y2))]
            reach_a = max(a.thickness_m, b.thickness_m) + SNAP_M
            a_end = any(feet[b.id].distance(p) <= reach_a and LineString(
                [(b.x1, b.y1), (b.x2, b.y2)]).distance(p) <= reach_a for p in ends_a)
            b_end = any(feet[a.id].distance(p) <= reach_a and LineString(
                [(a.x1, a.y1), (a.x2, a.y2)]).distance(p) <= reach_a for p in ends_b)
            cos = abs(a.direction()[0] * b.direction()[0] + a.direction()[1] * b.direction()[1])
            if cos > 0.999:
                kind = "colinear"
            elif a_end and b_end:
                kind = "L"
            elif a_end or b_end:
                kind = "T"
            else:
                kind = "X"
            height = min(a.base_z_m + a.height_m, b.base_z_m + b.height_m) - max(a.base_z_m, b.base_z_m)
            out.append({"paredes": [a.id, b.id], "tipo": kind, "altura_junta_m": round(max(height, 0), 4)})
    return out


def pieces(floor: Floor, max_length_m=REZULT_FORMAT["max_length_m"]):
    """Production pieces. Longer walls win at junctions; the others are trimmed.

    The order (longest first, then id) is deterministic, so the same drawing
    always gives the same pieces. A piece longer than the press format is
    split into equal parts and each split is reported as a panel joint.
    """
    taken = []
    out, splits = [], []
    feet = footprints(floor.walls)
    for wall in sorted(floor.walls, key=lambda w: (-w.length, w.id)):
        free = feet[wall.id]
        if taken:
            free = free.difference(union_all(taken))
        taken.append(feet[wall.id])
        parts = [g for g in getattr(free, "geoms", [free]) if isinstance(g, Polygon) and g.area > 1e-6]
        for k, part in enumerate(sorted(parts, key=lambda g: _extent(g, wall)[0])):
            start, end = _extent(part, wall)
            length = end - start
            if length < 0.01:
                continue
            count = max(1, math.ceil(length / max_length_m - 1e-9))
            for n in range(count):
                s = start + length * n / count
                e = start + length * (n + 1) / count
                openings = [o for o in wall.openings if s - 1e-6 <= o.offset_m and o.offset_m + o.width_m <= e + 1e-6]
                crossing = [o for o in wall.openings if o.offset_m < e - 1e-6 and o.offset_m + o.width_m > s + 1e-6
                            and o not in openings]
                if crossing:
                    raise ValueError(f"Um vão da parede {wall.id} fica sobre uma junta; ajuste a divisão do painel.")
                cut = sum(o.width_m * o.height_m for o in openings)
                piece_id = wall.id + (f".{k + 1}" if len(parts) > 1 else "") + (f"/{n + 1}" if count > 1 else "")
                out.append({
                    "id": piece_id, "parede": wall.id, "inicio_m": round(s, 4), "fim_m": round(e, 4),
                    "comprimento_m": round(e - s, 4), "altura_m": wall.height_m, "espessura_mm": wall.thickness_mm,
                    "camadas": wall.layers, "area_bruta_m2": round((e - s) * wall.height_m, 4),
                    "area_vaos_m2": round(cut, 4), "area_liquida_m2": round((e - s) * wall.height_m - cut, 4),
                    "volume_bruto_m3": round((e - s) * wall.height_m * wall.thickness_m, 5),
                    "volume_liquido_m3": round(((e - s) * wall.height_m - cut) * wall.thickness_m, 5),
                    "vaos": [{**o.model_dump(), "offset_m": round(o.offset_m - s, 4)} for o in openings],
                    "origem": wall.source or "eixo fornecido",
                })
            if count > 1:
                splits.append({"parede": wall.id, "paineis": count,
                               "motivo": f"comprimento {length:.3f} m > {max_length_m:.2f} m do formato de prensa"})
    return out, splits


def analyse(floor: Floor, max_length_m=REZULT_FORMAT["max_length_m"]):
    if max(w.height_m for w in floor.walls) > REZULT_FORMAT["max_width_m"] + 1e-9:
        tall = [w.id for w in floor.walls if w.height_m > REZULT_FORMAT["max_width_m"]]
        raise ValueError(f"Paredes acima de {REZULT_FORMAT['max_width_m']} m de altura exigem painel vertical: {tall}.")
    production, splits = pieces(floor, max_length_m)
    drawn = sum(w.length for w in floor.walls)
    by_thickness = {}
    for w in floor.walls:
        by_thickness.setdefault(w.thickness_mm, []).append(w)
    feet = footprints(floor.walls)
    union_length = 0.0
    for t, group in by_thickness.items():
        union_length += union_all([feet[w.id] for w in group]).area / (t / 1000)
    gross_volume = sum(feet[w.id].area * w.height_m for w in floor.walls)
    footprint_volume = gross_volume - _overlap_volume(floor.walls, feet)
    piece_length = sum(p["comprimento_m"] for p in production)
    piece_volume = sum(p["volume_bruto_m3"] for p in production)
    joints = _junctions(floor.walls)
    check = reconciliation(piece_volume, footprint_volume, zero_tolerance=1e-6)
    return {
        "piso": floor.name,
        "paredes": len(floor.walls),
        "juntas": joints,
        "pecas": production,
        "divisoes_formato": splits,
        "metodos": {
            "eixos_desenhados_m": round(drawn, 4),
            "uniao_area_sobre_espessura_m": round(union_length, 4),
            "pecas_producao_m": round(piece_length, 4),
            "volume_pecas_m3": round(piece_volume, 5),
            "volume_uniao_planta_m3": round(footprint_volume, 5),
        },
        "contagem_dupla_evitada_m3": round(gross_volume - footprint_volume, 5),
        "verificacao_volume": {**check, "metodos": "peças de produção vs união das plantas (GEOS)"},
        "totais": {
            "area_bruta_m2": round(sum(p["area_bruta_m2"] for p in production), 4),
            "area_vaos_m2": round(sum(p["area_vaos_m2"] for p in production), 4),
            "area_liquida_m2": round(sum(p["area_liquida_m2"] for p in production), 4),
            "volume_bruto_m3": round(piece_volume, 5),
            "volume_liquido_m3": round(sum(p["volume_liquido_m3"] for p in production), 5),
            # An X crossing is two vertical joints, one on each side of the through wall.
            "juntas_parede_m": round(sum(j["altura_junta_m"] * (2 if j["tipo"] == "X" else 1)
                                         for j in joints if j["tipo"] != "colinear"), 4),
        },
        "formato": {**REZULT_FORMAT, "max_length_m": max_length_m},
    }


def _overlap_volume(walls, feet):
    """Volume shared by two or more footprints, counted once per extra layer.

    Overlaps are prisms with the height of the shorter wall of each pair. The
    pairwise sum is exact when no point lies inside three footprints, which is
    the case for wall networks (three walls cannot share the same plan area
    unless the drawing duplicates a wall, rejected as an overlap above 50 %).
    """
    total = 0.0
    for i, a in enumerate(walls):
        fa = feet[a.id]
        for b in walls[i + 1:]:
            shared = fa.intersection(feet[b.id]).area
            if shared <= 0:
                continue
            if shared > 0.5 * min(fa.area, feet[b.id].area):
                raise ValueError(f"As paredes {a.id} e {b.id} estão duplicadas no desenho.")
            total += shared * min(a.height_m, b.height_m)
    return total


def rectangles_to_axes(rectangles, *, height_m, layers=5, nominal_mm=(60, 80, 100, 120, 140, 160, 180, 200, 220, 240),
                       tolerance_mm=3.0, prefix="W", source=""):
    """Axis segments from wall footprints (quadrilaterals in metres).

    Thickness is the short side of the minimum rotated rectangle and must match
    a nominal CLT thickness within the tolerance; otherwise the band is
    returned as rejected with its measured width.
    """
    walls, rejected = [], []
    for n, coords in enumerate(rectangles, 1):
        poly = Polygon(coords)
        if not poly.is_valid or poly.area <= 0:
            rejected.append({"indice": n, "motivo": "contorno inválido"})
            continue
        rect = poly.minimum_rotated_rectangle
        pts = list(rect.exterior.coords)[:4]
        sides = [(pts[i], pts[(i + 1) % 4]) for i in range(4)]
        lengths = [math.dist(a, b) for a, b in sides]
        short = min(lengths)
        nominal = min(nominal_mm, key=lambda t: abs(t - short * 1000))
        if abs(nominal - short * 1000) > tolerance_mm or rect.area - poly.area > 0.02 * rect.area:
            rejected.append({"indice": n, "motivo": "espessura ou forma fora da legenda CLT",
                             "largura_mm": round(short * 1000, 1)})
            continue
        i = lengths.index(max(lengths))
        (ax, ay), (bx, by) = sides[i]
        (cx, cy), (dx, dy) = sides[(i + 2) % 4]
        start = ((ax + dx) / 2, (ay + dy) / 2)
        end = ((bx + cx) / 2, (by + cy) / 2)
        if (end[0], end[1]) < (start[0], start[1]):
            start, end = end, start
        walls.append(WallAxis(id=f"{prefix}{n}", x1=start[0], y1=start[1], x2=end[0], y2=end[1],
                              thickness_mm=nominal, layers=layers, height_m=height_m,
                              source=source or f"contorno {n}, largura desenhada {short * 1000:.1f} mm"))
    return walls, rejected
