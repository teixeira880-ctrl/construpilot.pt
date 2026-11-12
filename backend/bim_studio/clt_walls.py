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


def _ends_on(a, b, feet):
    """True when an end of a lies on b's footprint (a stops at b)."""
    return any(feet[b.id].buffer(SNAP_M).contains(Point(p)) for p in ((a.x1, a.y1), (a.x2, a.y2)))


def _yields(a, b, feet):
    """Whether wall a is cut where it overlaps wall b. At a T the stem (the wall whose end stops on the other) is cut,
    whatever its length; at an L or an X the shorter wall is cut (then the id decides)."""
    a_on_b, b_on_a = _ends_on(a, b, feet), _ends_on(b, a, feet)
    if a_on_b != b_on_a:
        return a_on_b
    return (a.length, a.id) < (b.length, b.id)


def pieces(floor: Floor, max_length_m=REZULT_FORMAT["max_length_m"]):
    """Production pieces. At a T the through wall runs on and the stem is trimmed; at an L or X the longer wall wins.

    The order (longest first, then id) is deterministic, so the same drawing
    always gives the same pieces. A piece longer than the press format is
    split into equal parts and each split is reported as a panel joint.
    """
    out, splits = [], []
    feet = footprints(floor.walls)
    for wall in sorted(floor.walls, key=lambda w: (-w.length, w.id)):
        free = feet[wall.id]
        winners = [feet[o.id] for o in floor.walls if o is not wall and feet[o.id].intersects(free) and _yields(wall, o, feet)]
        if winners:
            # opening by a micron drops the slivers that floating point leaves along a shared face
            free = free.difference(union_all(winners)).buffer(-1e-6, join_style="mitre").buffer(1e-6, join_style="mitre")
        parts = [g for g in getattr(free, "geoms", [free]) if isinstance(g, Polygon) and g.area > 1e-6]
        for k, part in enumerate(sorted(parts, key=lambda g: _extent(g, wall)[0])):
            start, end = _extent(part, wall)
            length = end - start
            if length < 0.01:
                continue
            count = max(1, math.ceil(length / max_length_m - 1e-9))
            # an opening that runs into a junction (cut at the face of the through wall) is clipped to the piece
            part_openings = [o.model_copy(update={"offset_m": max(o.offset_m, start),
                                                  "width_m": min(o.offset_m + o.width_m, end) - max(o.offset_m, start)})
                             for o in wall.openings
                             if min(o.offset_m + o.width_m, end) - max(o.offset_m, start) > 0.01]
            for n in range(count):
                s = start + length * n / count
                e = start + length * (n + 1) / count
                openings = [o for o in part_openings if s - 1e-6 <= o.offset_m and o.offset_m + o.width_m <= e + 1e-6]
                crossing = [o for o in part_openings if o.offset_m < e - 1e-6 and o.offset_m + o.width_m > s + 1e-6
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
    if len({(w.base_z_m, w.height_m) for w in floor.walls}) == 1:
        # one storey height: the exact union, also where three footprints meet at a healed corner
        footprint_volume = union_all(list(feet.values())).area * floor.walls[0].height_m
        _overlap_volume(floor.walls, feet)  # still rejects duplicated walls
    else:
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


def _line_hit(a, b):
    """Intersection of the two infinite axis lines, as (t along a from its start, t along b from its start), or None."""
    ax, ay = a.direction()
    bx, by = b.direction()
    den = ax * by - ay * bx
    if abs(den) < 1e-9:
        return None
    dx, dy = b.x1 - a.x1, b.y1 - a.y1
    return (dx * by - dy * bx) / den, (dx * ay - dy * ax) / den


def _clip_openings(openings, t0, length):
    """Openings re-measured from a new axis start t0 and clipped to the new length (a cut end can shorten an opening)."""
    out = []
    for o in openings:
        a, b = max(o.offset_m - t0, 0.0), min(o.offset_m - t0 + o.width_m, length)
        if b - a > 0.01:
            out.append(o.model_copy(update={"offset_m": a, "width_m": b - a}))
    return out


def _bridge(walls, lin, tolerance_m):
    """One piece over a drawn lintel: every collinear run the band touches, plus the band beyond them, becomes one wall
    with an opening in each gap (sill 0, height head_m). Returns (new wall, merged runs, row) or None with a reason."""
    x0, y0, x1, y1 = lin["rect_m"]
    x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    band = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    horizontal = x1 - x0 >= y1 - y0
    axis = (1.0, 0.0) if horizontal else (0.0, 1.0)
    across = (y0 + y1) / 2 if horizontal else (x0 + x1) / 2
    width = (y1 - y0) if horizontal else (x1 - x0)
    proj = lambda x, y: x * axis[0] + y * axis[1]
    side = lambda x, y: y if horizontal else x
    runs = [w for w in walls if abs(w.direction()[0 if horizontal else 1]) > 0.999
            and abs(side(w.x1, w.y1) - across) <= max(w.thickness_m, width) / 2 + tolerance_m
            and w.footprint().buffer(tolerance_m).intersects(band)]
    if not runs:
        return None, "sem parede alinhada"
    if lin.get("thickness_mm"):
        runs = [w for w in runs if abs(w.thickness_mm - float(lin["thickness_mm"])) < 1]
        if not runs:
            return None, f"lintel de {float(lin['thickness_mm']):g} mm com espessura diferente das paredes"
    ref = runs[0]
    runs = [w for w in runs if w.thickness_mm == ref.thickness_mm and w.height_m == ref.height_m and w.base_z_m == ref.base_z_m]
    head = float(lin["head_m"])
    if head >= ref.height_m - 0.05:
        return None, f"altura do vão {head:.2f} m sem lintel abaixo da altura da parede"
    spans = sorted((min(proj(w.x1, w.y1), proj(w.x2, w.y2)), max(proj(w.x1, w.y1), proj(w.x2, w.y2)), w) for w in runs)
    b0, b1 = proj(x0, y0), proj(x1, y1)
    start, end = min(b0, spans[0][0]), max(b1, spans[-1][1])
    openings, cursor = [], start
    for s0, s1, w in spans:
        if s0 - cursor > 0.05:
            openings.append((cursor, s0 - cursor))
        forward = proj(w.x2 - w.x1, w.y2 - w.y1) > 0
        for o in w.openings:
            at = (proj(w.x1, w.y1) + o.offset_m) if forward else (proj(w.x1, w.y1) - o.offset_m - o.width_m)
            openings.append((at, o.width_m, o))
        cursor = max(cursor, s1)
    if end - cursor > 0.05:
        openings.append((cursor, end - cursor))
    new_openings = []
    for item in sorted(openings, key=lambda t: t[0]):
        if len(item) == 3:
            new_openings.append(item[2].model_copy(update={"offset_m": item[0] - start}))
        else:
            new_openings.append(Opening(offset_m=item[0] - start, width_m=item[1], sill_m=0.0, height_m=head, kind="vao",
                                        label=str(lin.get("ref", "lintel"))[:60]))
    if not any(o.label == str(lin.get("ref", "lintel"))[:60] and o.kind == "vao" for o in new_openings):
        return None, "o lintel não cobre nenhum vão entre troços"
    line = side(ref.x1, ref.y1)
    p, q = ((start, line), (end, line)) if horizontal else ((line, start), (line, end))
    ids = [w.id for _s, _e, w in spans]
    new = WallAxis(id="+".join(ids)[:40], x1=p[0], y1=p[1], x2=q[0], y2=q[1], thickness_mm=ref.thickness_mm, layers=ref.layers,
                   height_m=ref.height_m, base_z_m=ref.base_z_m, openings=new_openings,
                   source=(" + ".join(w.source or w.id for w in [s[2] for s in spans]) + f" + lintel {lin.get('ref', '')}")[:200])
    gaps = sum(o.width_m for o in new_openings if o.kind == "vao" and o.label == str(lin.get("ref", "lintel"))[:60])
    row = {"lintel": lin.get("ref", ""), "paredes": ids, "peca": new.id, "vao_m": round(gaps, 4), "altura_vao_m": head,
           "volume_lintel_m3": round(gaps * (ref.height_m - head) * ref.thickness_m, 5)}
    return (new, ids, row), None


def connect(walls, *, lintels=(), tolerance_m=0.02):
    """Heal a wall network read from a drawing, where every run is its own outline.

    1. Lintels: the runs on one line under a drawn CLT lintel, and the lintel beyond them up to the next wall, become one
       production piece with each opening cut out (sill 0, height = head_m), which is how the panel is cut. The
       lintel volume is then inside the piece, so it can be compared with the separate lintel panel of the estimate.
    2. Junctions: a wall end that stops at another wall's face, or runs to its outer face, is moved along its own axis
       onto the other wall's axis (at most half the other thickness plus the tolerance). L, T and X junctions are then
       recognised by _junctions and resolved by pieces() without double count.

    lintels: [{"ref", "rect_m": [x0, y0, x1, y1], "head_m", "thickness_mm" (optional)}] in the same metres as the walls.
    Returns (walls, report) with report = {"ligacoes", "linteis", "membros": {run id: piece wall id}, "notas"}.
    """
    original = {w.id for w in walls}
    walls = list(walls)
    members = {w.id: w.id for w in walls}
    rows, notes = [], []
    for lin in lintels:
        done, why = _bridge(walls, lin, tolerance_m)
        if not done:
            notes.append(f"{lin.get('ref', 'lintel')}: {why}; fica como painel à parte.")
            continue
        new, ids, row = done
        walls = [w for w in walls if w.id not in ids] + [new]
        for run, wall in list(members.items()):
            if wall in ids:
                members[run] = new.id
        rows.append(row)
    moves, links = {}, []
    for a in walls:
        for k in (0, 1):
            best = None
            for b in walls:
                if b is a:
                    continue
                cos = abs(a.direction()[0] * b.direction()[0] + a.direction()[1] * b.direction()[1])
                hit = _line_hit(a, b)
                if cos > 0.999 or hit is None:
                    continue
                ta, tb = hit
                shift = (ta - a.length) if k else -ta          # > 0 lengthens the wall at that end
                if abs(shift) > b.thickness_m / 2 + tolerance_m:
                    continue
                if not -(a.thickness_m / 2 + tolerance_m) <= tb <= b.length + a.thickness_m / 2 + tolerance_m:
                    continue
                if best is None or abs(shift) < abs(best[0]):
                    best = (shift, ta, b.id)
            if best and abs(best[0]) > 1e-6:
                moves[(a.id, k)] = best[1]
                links.append({"parede": a.id, "extremo": "fim" if k else "início", "a": best[2], "ajuste_mm": round(best[0] * 1000, 1)})
    healed = []
    for a in walls:
        t0, t1 = moves.get((a.id, 0), 0.0), moves.get((a.id, 1), a.length)
        ux, uy = a.direction()
        if t1 - t0 < 0.05:
            healed.append(a)
            continue
        healed.append(a.model_copy(update={"x1": a.x1 + ux * t0, "y1": a.y1 + uy * t0, "x2": a.x1 + ux * t1, "y2": a.y1 + uy * t1,
                                           "openings": _clip_openings(a.openings, t0, t1 - t0)}))
    healed = [WallAxis.model_validate(w.model_dump()) for w in healed]
    return healed, {"ligacoes": links, "linteis": rows, "membros": {k: v for k, v in members.items() if k in original},
                    "notas": notes}
