"""Reviewed vector take-off for the supplied Home A PDF revision.

The reviewed vector selections and independent scale references apply only to
this exact file. Wall runs come from the magenta CLT outlines and from CLT
hatching that has no outline. Structural wall heights come from the section:
finished ceiling height plus the floor build-up and the suspended ceiling zone,
both measured on the section vectors.
"""
import re

import fitz
from shapely import union_all
from shapely.geometry import Polygon, box

SOURCE_SHA256 = "0320687a95e44a63dfe8e28c702ccd38ec4b46563b5bf44166b0e946b93a761d"
FLOORS = {1: "Piso −1 (fora do âmbito)", 2: "Rés do chão", 3: "Primeiro piso", 4: "Pormenor construtivo"}
# Reviewed quadrilaterals of the magenta CLT outlines, excluding legend and
# duplicate paths. Source references are PyMuPDF drawing sequence numbers.
OUTLINES = {
    2: (2892, 2893, 2894, 2895, 2896, 2897, 2898, 2899, 2900, 2901, 2902, 2903,
        2904, 2905, 2906, 2907, 2908, 2909, 2915, 2916, 2918, 2921, 2922),
    3: (0, 1, 707, 708, 709, 710, 711, 813, 894, 895, 898, 1054, 1872, 1873, 1884, 1968),
}


def _rectangle(page, points):
    x, y, X, Y = points
    return [round(x / page.rect.width, 6), round(y / page.rect.height, 6),
            round(X / page.rect.width, 6), round(Y / page.rect.height, 6)]


def _clt_footprints(page):
    metre_per_point, markers, polygons = _wall_geometry(page)
    area = union_all(polygons).area * metre_per_point ** 2
    return area, markers


def _wall_geometry(page):
    number = page.number + 1
    drawing = {path["seqno"]: path for path in page.get_drawings()}
    rect = lambda id: drawing[id]["rect"] * page.rotation_matrix
    if number == 2:
        scale_span = rect(4569).x0 - rect(4568).x0
        metres, scale_label = 2.410, "Cota horizontal de 2 410 mm"
        scale_box = (rect(4568) | rect(4569) | rect(4570))
    else:
        scale_box = rect(2515)
        scale_span = scale_box.height
        metres, scale_label = 5.010, "Cota vertical de 5 010 mm"
    if abs(scale_span / metres - 72 / .0254 / 50) / (72 / .0254 / 50) > .002:
        raise ValueError("A calibração vetorial diverge da escala 1:50 indicada.")
    metre_per_point = metres / scale_span
    markers, polygons = [], []
    for id in OUTLINES[number]:
        path = drawing[id]
        if len(path["items"]) != 1 or path["items"][0][0] != "qu":
            raise ValueError("Contorno vetorial não reconhecido na revisão conferida.")
        quad = path["items"][0][1]
        points = [vertex * page.rotation_matrix for vertex in (quad.ul, quad.ur, quad.lr, quad.ll)]
        polygon = Polygon([(point.x, point.y) for point in points])
        bounds = polygon.bounds
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        thickness = min(width, height) * metre_per_point
        if not polygon.is_valid or min(abs(thickness - nominal) for nominal in (.100, .160)) > .003:
            raise ValueError("Espessura gráfica incompatível com a legenda CLT.")
        polygons.append(polygon)
        length = max(width, height) * metre_per_point
        markers.append({"id": f"clt-{id}", "rect": _rectangle(page, bounds), "status": "measured",
                        "length_m": length, "drawing_width_mm": thickness * 1000,
                        "plan_area_m2": polygon.area * metre_per_point ** 2,
                        "label": f"Troço CLT {id} · {length:.3f} m"})
    markers.extend(_hatched_runs(page, metre_per_point, polygons, markers))
    polygons.extend(Polygon(m.pop("_polygon")) for m in markers if "_polygon" in m)
    markers.append({"id": "scale", "status": "measured", "label": scale_label,
                    "rect": _rectangle(page, (scale_box.x0 - 3, scale_box.y0 - 3, scale_box.x1 + 3, scale_box.y1 + 3))})
    return metre_per_point, markers, polygons


HATCH_TOLERANCE_M = .003
CLT_SECTION = (0.0, 1.0, 1.0)
PLASTERBOARD_SECTION = (0.722, 0.0, 0.0)


def _single_lines(page):
    return [path for path in page.get_drawings()
            if path["type"] == "s" and path.get("color") and len(path["items"]) == 1 and path["items"][0][0] == "l"]


def _hatched_runs(page, metre_per_point, outlined, outline_markers):
    """CLT walls drawn only with the hatch pattern, without a magenta outline.

    The nominal thickness of each hatch colour is learnt from the outlined runs
    on the same sheet. A remaining hatched band is a wall run only when its
    drawn width matches that nominal within 3 mm. Other bands are reported as
    pending, except the swatches inside the sheet key.
    """
    M = page.rotation_matrix
    nominal_by_marker = {m["id"]: round(m["drawing_width_mm"] / 10) / 100 for m in outline_markers}
    outlined_ids = [m["id"] for m in outline_markers]
    keys = [path["rect"] * M for path in page.get_drawings()
            if path["type"] == "s" and (path["rect"] * M).width > page.rect.width * .6
            and (path["rect"] * M).height < page.rect.height * .03]
    hatch = {}
    for path in _single_lines(page):
        colour = tuple(round(c, 3) for c in path["color"])
        if round(path.get("width") or 0, 2) == .36:
            hatch.setdefault(colour, []).append(path["rect"] * M)
    covered = union_all(outlined).buffer(.05, join_style=2)
    runs = []
    for colour, rects in hatch.items():
        region = union_all([box(*r) for r in rects]).buffer(.25, join_style=2).buffer(-.25, join_style=2)
        tally = {}
        for id, polygon in zip(outlined_ids, outlined):
            if polygon.intersection(region).area > polygon.area * .8:
                tally[nominal_by_marker[id]] = tally.get(nominal_by_marker[id], 0) + polygon.area
        if not tally or max(tally.values()) < sum(tally.values()) * .75:
            continue
        nominal = max(tally, key=tally.get)
        rest = region.difference(covered)
        for part in getattr(rest, "geoms", [rest]):
            x, y, X, Y = part.bounds
            width, height = (X - x) * metre_per_point, (Y - y) * metre_per_point
            length, thickness = max(width, height), min(width, height)
            if length < .15 or any(k.contains(fitz.Rect(x, y, X, Y)) for k in keys):
                continue
            id = f"hatch-{len(runs) + 1}"
            if abs(thickness - nominal) > HATCH_TOLERANCE_M or part.area < (X - x) * (Y - y) * .9:
                runs.append({"id": id, "rect": _rectangle(page, (x, y, X, Y)), "status": "pending",
                             "label": f"Tracejado CLT sem contorno · {length:.3f} m · largura {thickness * 1000:.0f} mm por confirmar"})
                continue
            runs.append({"id": id, "rect": _rectangle(page, (x, y, X, Y)), "status": "measured",
                         "length_m": length, "drawing_width_mm": thickness * 1000,
                         "plan_area_m2": part.area * metre_per_point ** 2, "source": "hatch",
                         "label": f"Troço CLT só tracejado · {length:.3f} m", "_polygon": part})
    return runs


def section_heights(page):
    """Offsets between finished levels and CLT wall ends, from the section vectors.

    Platform construction: the RDC wall stands on the ground slab and stops under
    the 240 mm CLT slab; the +1 wall stands on that slab and stops under the
    140 mm CLT roof. The scale comes from the two CLT layer stacks, whose
    thickness is printed in their labels (Panel240-7s, Panel140-5s); both
    stacks must give the same scale within 1%. Returns metres.
    """
    M = page.rotation_matrix
    labels = {}
    for x0, y0, x1, y1, word, *_ in page.get_text("words"):
        match = re.fullmatch(r"Panel(\d{3})-(\d)s", word)
        if match:
            labels[int(match[1])] = (fitz.Rect(x0, y0, x1, y1) * M, int(match[2]))
    rows, verticals = {}, []
    for path in page.get_drawings():
        colour = tuple(round(c, 3) for c in (path.get("color") or ()))
        for item in path["items"]:
            if item[0] != "l":
                continue
            a, b = item[1] * M, item[2] * M
            if abs(a.y - b.y) < .05 and abs(a.x - b.x) > 100:
                rows.setdefault(colour, set()).add(round(a.y, 2))
            elif abs(a.x - b.x) < .05 and colour == CLT_SECTION:
                verticals.append(max(a.y, b.y))
    stacks = []
    for y in sorted(rows.get(CLT_SECTION, ())):
        if stacks and y - stacks[-1][-1] <= 10:
            stacks[-1].append(y)
        else:
            stacks.append([y])
    found = {}
    for thickness, (rect, layers) in labels.items():
        found.update({thickness: stack for stack in stacks
                      if stack[0] <= rect.y0 and rect.y1 <= stack[-1] and len(stack) == layers + 1})
    if 240 not in found or 140 not in found:
        raise ValueError("Não foi possível localizar a laje de 240 mm e a cobertura de 140 mm no corte.")
    slab, roof = found[240], found[140]
    scale = .240 / (slab[-1] - slab[0])
    if abs(.140 / (roof[-1] - roof[0]) - scale) / scale > .01:
        raise ValueError("As espessuras da laje e da cobertura dão escalas diferentes no corte.")
    ceilings = sorted(rows.get(PLASTERBOARD_SECTION, ()))
    finished = sorted(rows.get((0.0, 0.0, 0.0), ()))

    def ceiling_face(underside):
        board = [y for y in ceilings if underside < y < underside + 60]
        if len(board) < 2 or board[1] - board[0] > 5:
            raise ValueError("Teto em placa sob o painel CLT não identificado no corte.")
        return board[1]

    def floor_level(base):
        levels = [y for y in finished if base - 40 < y < base - 2]
        if not levels:
            raise ValueError("Pavimento acabado não identificado no corte.")
        return max(levels)

    wall_base = max(verticals)
    return {
        "scale_mm_per_point": scale * 1000,
        "panels": {"laje": {"thickness_mm": 240, "layers": labels[240][1]},
                   "cobertura": {"thickness_mm": 140, "layers": labels[140][1]}},
        "RDC": {"floor_buildup_m": (wall_base - floor_level(wall_base)) * scale,
                "ceiling_zone_m": (ceiling_face(slab[-1]) - slab[-1]) * scale},
        "+1": {"floor_buildup_m": (slab[0] - floor_level(slab[0])) * scale,
               "ceiling_zone_m": (ceiling_face(roof[-1]) - roof[-1]) * scale},
    }


# Plan symbols without a colour swatch in the key: the key lists "CLT lintel"
# and "Steel beam" as text only. Red dashed bands are read as CLT lintels and
# blue dashed bands as steel beams; both readings are reported for confirmation.
LINTEL = (1.0, 0.0, 0.0)
STEEL_BEAM = (0.0, 0.498, 1.0)
DOOR = (0.431, 0.541, 0.867)
# Outer line of the RDC roof edge, drawn in violet on the +1 sheet. The right
# side is the party wall, so the outline is closed along it.
ROOF_EDGE = (931, 1869, 1871)
# Floor plate of the +1, bounded by the outer faces of these measured walls.
UPPER_PLATE = {"left_a": ("clt-1054", 0), "top": ("clt-708", 1), "right": ("clt-711", 2),
               "bottom": ("clt-1872", 3), "left_b": ("clt-709", 0), "top_b": ("clt-1968", 1)}
# Stair opening in the 240 mm slab: between the wall clt-1873 and the party
# wall, from the face of clt-1968 to the face of clt-1872.
STAIR_VOID = {"left": ("clt-1873", 2), "right": ("clt-710", 0), "top": ("clt-1968", 3), "bottom": ("clt-1872", 1)}


def _dashed_lines(page, colour, gap=4.0):
    M, lines = page.rotation_matrix, {}
    for path in page.get_drawings():
        if tuple(round(c, 3) for c in (path.get("color") or ())) != colour or round(path.get("width") or 0, 2) != .6:
            continue
        for item in path["items"]:
            if item[0] != "l":
                continue
            a, b = item[1] * M, item[2] * M
            if abs(a.y - b.y) < .3:
                lines.setdefault(("h", round((a.y + b.y) / 2, 1)), []).append((min(a.x, b.x), max(a.x, b.x)))
            elif abs(a.x - b.x) < .3:
                lines.setdefault(("v", round((a.x + b.x) / 2, 1)), []).append((min(a.y, b.y), max(a.y, b.y)))
    merged = []
    for (axis, offset), spans in lines.items():
        spans.sort()
        start, end = spans[0]
        for a, b in spans[1:]:
            if a <= end + gap:
                end = max(end, b)
            else:
                merged.append((axis, offset, start, end))
                start, end = a, b
        merged.append((axis, offset, start, end))
    return merged


def _bands(page, colour, metre_per_point):
    """Pairs of parallel dashed lines 80 to 250 mm apart, as plan rectangles."""
    lines = [l for l in _dashed_lines(page, colour) if (l[3] - l[2]) * metre_per_point > .3]
    bands, used = [], set()
    for i, (axis, offset, a, b) in enumerate(lines):
        if i in used:
            continue
        mates = [(abs(o - offset), j) for j, (ax, o, c, d) in enumerate(lines)
                 if j != i and j not in used and ax == axis and .08 <= abs(o - offset) * metre_per_point <= .25
                 and min(b, d) - max(a, c) > .5 * min(b - a, d - c)]
        if not mates:
            continue
        _, j = min(mates)
        used.update((i, j))
        o2, c, d = lines[j][1], lines[j][2], lines[j][3]
        lo, hi, s, e = min(offset, o2), max(offset, o2), min(a, c), max(b, d)
        bands.append(box(s, lo, e, hi) if axis == "h" else box(lo, s, hi, e))
    return bands


def _openings(page, metre_per_point, walls, evidence):
    """Lintels, steel beams and doors in CLT walls, with the clear span over each opening."""
    wall_union = union_all(walls)
    width_pt, height_pt = page.rect.width, page.rect.height
    nominal = lambda w: min((.100, .160, .200), key=lambda n: abs(n - w))
    lintels, beams, doors = [], [], []
    lintel_bands = _bands(page, LINTEL, metre_per_point)
    for band in lintel_bands:
        x0, y0, x1, y1 = band.bounds
        width = min(x1 - x0, y1 - y0) * metre_per_point
        clear = band.difference(wall_union).area / min(x1 - x0, y1 - y0) * metre_per_point
        lintels.append({"length_m": max(x1 - x0, y1 - y0) * metre_per_point, "clear_span_m": clear,
                        "thickness_mm": round(nominal(width) * 1000), "rect": _rectangle(page, band.bounds)})
    for band in _bands(page, STEEL_BEAM, metre_per_point):
        x0, y0, x1, y1 = band.bounds
        beams.append({"length_m": max(x1 - x0, y1 - y0) * metre_per_point,
                      "drawing_width_mm": round(min(x1 - x0, y1 - y0) * metre_per_point * 1000),
                      "rect": _rectangle(page, band.bounds)})
    labels = []
    for item in evidence:
        if item["kind"] == "opening_dimensions":
            x0, y0, x1, y1 = item["rect"]
            labels.append(((x0 + x1) / 2 * width_pt, (y0 + y1) / 2 * height_pt, item["values"]))
    M, paths = page.rotation_matrix, page.get_drawings()
    for k, path in enumerate(paths):
        colour = tuple(round(c, 3) for c in (path.get("color") or ()))
        if colour != DOOR or path["items"][0][0] != "c" or k == 0 or k + 1 >= len(paths):
            continue
        leaf = [paths[k - 1], paths[k + 1]]
        if any(tuple(round(c, 3) for c in (q.get("color") or ())) != DOOR or q["items"][0][0] != "l" for q in leaf):
            continue
        segments = [box(*(q["rect"] * M)).buffer(.01) for q in leaf]
        if min(s.distance(wall_union) for s in segments) * metre_per_point > .2:
            continue
        cx, cy = union_all(segments).centroid.coords[0]
        near = sorted(((cx - x) ** 2 + (cy - y) ** 2, values) for x, y, values in labels)
        covered = any(band.distance(union_all(segments)) * metre_per_point < .3 for band in lintel_bands)
        drawn = max(max(s.bounds[2] - s.bounds[0], s.bounds[3] - s.bounds[1]) for s in segments) * metre_per_point
        if near and near[0][0] ** .5 * metre_per_point < 2.5:
            w, h = near[0][1]
            doors.append({"width_m": w / 1000, "height_m": h / 1000, "source": "cotado", "under_lintel": covered})
        else:
            doors.append({"width_m": round(drawn, 2), "height_m": None, "source": "desenhado", "under_lintel": covered})
    return lintels, beams, doors


def upper_plate(page, markers):
    """+1 floor plate, stair opening and RDC roof outline, in m²."""
    by_id = {m["id"]: m for m in markers}
    W, H = page.rect.width, page.rect.height
    face = lambda ref: by_id[ref[0]]["rect"][ref[1]] * (W if ref[1] in (0, 2) else H)
    p = {k: face(v) for k, v in UPPER_PLATE.items()}
    plate = Polygon([(p["left_a"], p["top"]), (p["right"], p["top"]), (p["right"], p["bottom"]),
                     (p["left_b"], p["bottom"]), (p["left_b"], p["top_b"]), (p["left_a"], p["top_b"])])
    v = {k: face(r) for k, r in STAIR_VOID.items()}
    void = box(v["left"], v["top"], v["right"], v["bottom"])
    M = page.rotation_matrix
    drawing = {path["seqno"]: path for path in page.get_drawings()}
    points = []
    for seqno in ROOF_EDGE:
        for item in drawing[seqno]["items"]:
            points.append(((item[1] * M).x, (item[1] * M).y))
            points.append(((item[2] * M).x, (item[2] * M).y))
    xs, ys = [x for x, _ in points], [y for _, y in points]
    notch_x = min(x for x, y in points if y == max(ys) and x > min(xs))
    notch_y = min(y for x, y in points if abs(x - notch_x) < .5)
    outline = Polygon([(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), notch_y), (notch_x, notch_y),
                       (notch_x, max(ys)), (min(xs), max(ys))])
    return plate, void, outline


def review_page(page, evidence):
    number = page.number + 1
    result = {"floor": FLOORS[number], "clt_plan_m2": None, "clt_volume_m3": None,
              "interior_base_m2": None, "finish_area_m2": None, "finish_volume_m3": None,
              "notes": [], "markers": [], "in_scope": number in OUTLINES}
    if number in OUTLINES:
        metre_per_point, markers, polygons = _wall_geometry(page)
        result["clt_plan_m2"] = union_all(polygons).area * metre_per_point ** 2
        result["markers"] = markers
        result["notes"].append("Área ocupada em planta pelos troços assinalados. Não corresponde à área da face vertical nem à área das lajes.")
        lintels, beams, doors = _openings(page, metre_per_point, polygons, evidence)
        result["openings"] = {"lintels": lintels, "steel_beams": beams, "doors_in_clt": doors}
        for n, item in enumerate(lintels):
            result["markers"].append({"id": f"lintel-{n + 1}", "rect": item["rect"], "status": "pending",
                                      "label": f"Lintel CLT {item['thickness_mm']} mm · vão livre {item['clear_span_m']:.2f} m"})
        for n, item in enumerate(beams):
            result["markers"].append({"id": f"beam-{n + 1}", "rect": item["rect"], "status": "pending",
                                      "label": f"Viga de aço · {item['length_m']:.2f} m · perfil não indicado"})
        result["notes"].append("Lintéis (tracejado vermelho) e vigas de aço (tracejado azul): a legenda não tem amostra de cor; confirmar a leitura.")
        result["rooms"] = rooms(page, metre_per_point)
        result["metre_per_point"] = metre_per_point
        result["interior_doors"] = len(set(re.findall(r"Dv\s?(\d\.\s?\d)", page.get_text())))
        if number == 2:
            x0, _, x1, y1 = union_all(polygons).bounds
            terrace_wall = min(m["rect"][1] for m in markers if m["id"] == "clt-2905") * page.rect.height
            envelope = box(x0, terrace_wall, x1, y1)
        else:
            envelope = upper_plate(page, markers)[0]
        result["openings"]["exterior"] = exterior_openings(page, metre_per_point, polygons, envelope)
        if number == 3:
            plate, void, outline = upper_plate(page, markers)
            k2 = metre_per_point ** 2
            result["plates"] = {
                "upper_plate_m2": plate.area * k2, "stair_void_m2": void.area * k2,
                "rdc_outline_m2": outline.area * k2, "rdc_roof_only_m2": outline.difference(plate).area * k2,
            }
            result["notes"].append(
                f"Laje do +1: {plate.area * k2:.2f} m² pelas faces exteriores das paredes, menos a abertura da escada "
                f"({void.area * k2:.2f} m², a confirmar). Cobertura do RDC (contorno violeta): {outline.area * k2:.2f} m².")
    if number == 1:
        result["notes"].append("Folha fora do âmbito da casa: o Home A tem só RDC e +1, por indicação do cliente.")
        return result
    if number == 2:
        result["notes"].append("O terraço coberto de 26,50 m² está excluído dos acabamentos interiores.")
    if number != 4:
        result["notes"].extend((
            "CLT: confirmar alturas estruturais por troço, correspondência dos vãos, lajes e limites de cada painel.",
            "Revestimentos: confirmar faces a revestir, altura de aplicação, demãos/camadas e descontos por vão.",
        ))
    else:
        result["notes"].append("O corte identifica CLT e placas de gesso. Confirmar a aplicação de cada composição por elemento e piso.")
        offsets = section_heights(page)
        result["structural_offsets"] = offsets
        for floor, values in offsets.items():
            if floor in ("RDC", "+1"):
                result["notes"].append(
                    f"{floor}: altura estrutural da parede = pé-direito acabado + {values['floor_buildup_m'] * 1000:.0f} mm "
                    f"de pavimento + {values['ceiling_zone_m'] * 1000:.0f} mm de teto falso, medidos no corte.")
    for item in evidence:
        if item["kind"] in ("ceiling_height", "opening_dimensions", "material_note"):
            result["markers"].append({"id": item["id"], "rect": item["rect"], "status": "pending",
                                      "label": item["text"]})
    return result


OPENING_HEAD_M = 2.30  # door head printed on the plans (Opening 900x2300H); used for lintels over glazing too
WALL_LAYERS = {100: 5, 160: 5}  # key: 100 mm 5 layers; 80+80 mm = two 3-layer panels, 4 glued joints


def estimate_extras(pages):
    """Slab, roof, lintels, panels over doors, ceilings and steel beams per floor, from the reviewed sheets."""
    reviews = {p["page"]: p.get("review") or {} for p in pages}
    section = reviews.get(4, {}).get("structural_offsets")
    plates = reviews.get(3, {}).get("plates")
    if not section or not plates:
        return None
    heights = {}
    for number, key in ((2, "RDC"), (3, "+1")):
        ceilings = [e["values"][0] / 1000 for e in next(p for p in pages if p["page"] == number)["evidence"]
                    if e["kind"] == "ceiling_height"]
        heights[key] = max(ceilings) + section[key]["floor_buildup_m"] + section[key]["ceiling_zone_m"]
    slab, roof = section["panels"]["laje"], section["panels"]["cobertura"]
    out, notes = {}, []
    for number, key in ((2, "RDC"), (3, "+1")):
        review, height = reviews[number], heights[key]
        depth = height - OPENING_HEAD_M
        panels = []
        for item in review["openings"]["lintels"]:
            panels.append({"kind": "lintel", "label": f"Lintel {item['thickness_mm']} mm, vão {item['clear_span_m']:.2f} m",
                           "thickness_mm": item["thickness_mm"], "layers": WALL_LAYERS.get(item["thickness_mm"], 5),
                           "area_m2": round(item["clear_span_m"] * depth, 3)})
        for door in review["openings"]["doors_in_clt"]:
            if door["under_lintel"] or not door["height_m"]:
                continue
            panels.append({"kind": "parede", "label": f"Painel sobre porta {door['width_m'] * 1000:.0f}x{door['height_m'] * 1000:.0f}",
                           "thickness_mm": 100, "layers": WALL_LAYERS[100],
                           "area_m2": round(door["width_m"] * (height - door["height_m"]), 3)})
        beams = sum(b["length_m"] for b in review["openings"]["steel_beams"])
        # suspended ceiling = the rooms, to their finished faces: the roof outline also covers the open entrance porch
        ceiling = sum(r["area_m2"] for r in review["rooms"] if r.get("tipo") != "exterior")
        if key == "RDC":
            roof_area = plates["rdc_roof_only_m2"]
            panels.append({"kind": "cobertura", "label": f"Cobertura do RDC fora do +1 (CLT {roof['thickness_mm']})",
                           "thickness_mm": roof["thickness_mm"], "layers": roof["layers"], "area_m2": round(roof_area, 3)})
            extras = {"ceiling_m2": ceiling, "roof_buildup_m2": roof_area, "slab_buildup_m2": 0}
        else:
            slab_area = plates["upper_plate_m2"] - plates["stair_void_m2"]
            panels.append({"kind": "laje", "label": f"Laje do +1 (CLT {slab['thickness_mm']}), sem a abertura da escada",
                           "thickness_mm": slab["thickness_mm"], "layers": slab["layers"], "area_m2": round(slab_area, 3)})
            panels.append({"kind": "cobertura", "label": f"Cobertura do +1 (CLT {roof['thickness_mm']})",
                           "thickness_mm": roof["thickness_mm"], "layers": roof["layers"],
                           "area_m2": round(plates["upper_plate_m2"], 3)})
            extras = {"ceiling_m2": ceiling, "roof_buildup_m2": plates["upper_plate_m2"], "slab_buildup_m2": slab_area}
        page = next(p for p in pages if p["page"] == number)
        to_m = lambda r: [round(r[0] * page["width"] * review["metre_per_point"], 3), round(r[1] * page["height"] * review["metre_per_point"], 3),
                          round(r[2] * page["width"] * review["metre_per_point"], 3), round(r[3] * page["height"] * review["metre_per_point"], 3)]
        room_list = [{**{k: v for k, v in r.items() if k != "rect"}, "rect_m": to_m(r["rect"])} for r in review["rooms"]]
        riser = next((r for r in room_list if r["nome"] == "Nicho técnico"), None)
        ceilings = [e["values"][0] / 1000 for e in page["evidence"] if e["kind"] == "ceiling_height"]
        out[key] = {"height_m": round(height, 3), "panels": panels, "steel_beam_m": round(beams, 3),
                    "rooms": room_list, "windows": [{k: v for k, v in w.items() if k != "rect"} for w in review["openings"]["exterior"]],
                    "interior_doors": review["interior_doors"], "ceiling_height_m": max(ceilings),
                    "riser_m": [round((riser["rect_m"][0] + riser["rect_m"][2]) / 2, 3), round((riser["rect_m"][1] + riser["rect_m"][3]) / 2, 3)] if riser else None,
                    **{k: round(v, 2) for k, v in extras.items()}}
    notes.extend((
        "A cobertura do RDC fora do +1 usa a composição da cobertura do corte (CLT 140, 5 camadas). Confirmar no projeto de estruturas.",
        f"Altura dos lintéis = altura estrutural do piso − {OPENING_HEAD_M:.2f} m (topo das portas cotadas). Nas janelas o topo não está cotado.",
        "Teto falso = soma das divisões revistas (faces acabadas). O alpendre de entrada sob a cobertura do RDC fica fora do teto interior.",
        "Abertura da escada na laje medida entre as paredes da escada; confirmar o comprimento real do vão.",
        "Teto falso: área da cobertura ou laje menos a planta das paredes CLT; o terraço coberto fica de fora.",
        "Fundações, laje térrea e caixilharia não fazem parte do fornecimento CLT e não estão no total.",
    ))
    return {"floors": out, "notes": notes}


# Rooms reviewed on the Home A plans. Each rectangle was placed on the sheet and every side is snapped
# to the nearest drawn wall or lining line (CLT outline, hatch, black or green 0.72 line) within 8 points.
# Sides with no line nearby keep the reviewed position and are reported as "a confirmar".
# Fixtures are the sanitary and kitchen symbols drawn in each room.
ROOM_LINES = {((0.82, 0.733, 0.463), .36), ((0.451, 0.725, 0.725), .36), ((1.0, 0.0, 1.0), .6),
              ((0.0, 0.0, 0.0), .72), ((0.0, 0.867, 0.216), .72)}
_PT = 842 / 1348  # reviewed positions were taken on a 1348-pixel-wide view of the sheet
ROOMS = {
    2: [("Sala e cozinha", "sala", (205, 480, 1185, 930), ["lava_loica", "maquina_lavar_loica"]),
        ("I.S. 2", "casa_de_banho", (215, 945, 415, 1190), ["autoclismo", "lavatorio", "chuveiro"]),
        ("I.S. 1", "casa_de_banho", (590, 940, 790, 1180), ["autoclismo", "lavatorio", "chuveiro"]),
        ("I.S. RDC", "casa_de_banho", (975, 1010, 1065, 1190), ["autoclismo", "lavatorio"]),
        ("Hall 1", "corredor", (860, 1185, 1075, 1530), []),
        ("Hall 2", "corredor", (975, 935, 1180, 1005), []),
        ("Hall 2 passagem", "corredor", (1065, 1005, 1180, 1180), []),
        ("Nicho entre I.S.", "corredor", (425, 940, 520, 1180), []),
        ("Nicho técnico", "arrumos", (800, 940, 970, 1180), ["maquina_lavar_roupa"]),
        ("Escada", "corredor", (1075, 1180, 1185, 1530), []),
        ("Roupeiro Quarto 2", "quarto", (205, 1190, 525, 1255), []),
        ("Quarto 2", "quarto", (205, 1255, 525, 1680), []),
        ("Quarto 1", "quarto", (550, 1185, 840, 1680), [])],
    3: [("I.S. 3", "casa_de_banho", (710, 475, 870, 930), ["autoclismo", "lavatorio", "lavatorio", "banheira"]),
        ("Quarto 3", "quarto", (880, 475, 1205, 935), []),
        ("Hall 3", "corredor", (705, 940, 1205, 1050), []),
        ("I.S. 4", "casa_de_banho", (565, 1060, 910, 1235), ["autoclismo", "lavatorio", "chuveiro"]),
        ("Quarto 4", "quarto", (570, 1240, 1010, 1520), []),
        ("Quarto 4 entrada", "quarto", (910, 1060, 1010, 1240), []),
        ("Quarto 4 roupeiro", "quarto", (1010, 1060, 1095, 1520), []),
        ("Escada +1", "corredor", (1095, 1055, 1205, 1520), [])],
}


def _room_lines(page):
    M, xs, ys = page.rotation_matrix, [], []
    for path in page.get_drawings():
        key = (tuple(round(c, 3) for c in (path.get("color") or ())), round(path.get("width") or 0, 2))
        if key not in ROOM_LINES:
            continue
        for item in path["items"]:
            if item[0] == "l":
                edges = [(item[1] * M, item[2] * M)]
            elif item[0] == "qu":
                q = [v * M for v in (item[1].ul, item[1].ur, item[1].lr, item[1].ll)]
                edges = [(q[i], q[(i + 1) % 4]) for i in range(4)]
            else:
                continue
            for a, b in edges:
                if abs(a.x - b.x) < .3 and abs(a.y - b.y) > 3:
                    xs.append((a.x, min(a.y, b.y), max(a.y, b.y)))
                elif abs(a.y - b.y) < .3 and abs(a.x - b.x) > 3:
                    ys.append((a.y, min(a.x, b.x), max(a.x, b.x)))
    return xs, ys


def rooms(page, metre_per_point):
    """Reviewed rooms with sides snapped to drawn lines; area, perimeter and fixtures."""
    xs, ys = _room_lines(page)

    def snap(value, lines, lo, hi):
        near = [l[0] for l in lines if abs(l[0] - value) < 8 and min(l[2], hi) - max(l[1], lo) > .3 * (hi - lo)]
        return min(near, key=lambda z: abs(z - value)) if near else None

    out = []
    for name, kind, rect, fixtures in ROOMS.get(page.number + 1, []):
        x0, y0, x1, y1 = (v * _PT for v in rect)
        sides = {"esquerda": snap(x0, xs, y0, y1), "topo": snap(y0, ys, x0, x1),
                 "direita": snap(x1, xs, y0, y1), "base": snap(y1, ys, x0, x1)}
        b = [sides["esquerda"] or x0, sides["topo"] or y0, sides["direita"] or x1, sides["base"] or y1]
        w, h = (b[2] - b[0]) * metre_per_point, (b[3] - b[1]) * metre_per_point
        out.append({"nome": name, "tipo": kind, "area_m2": round(w * h, 2), "perimetro_m": round(2 * (w + h), 2),
                    "comprimento_m": round(max(w, h), 2), "aparelhos": fixtures, "rect": _rectangle(page, b),
                    "lados_a_confirmar": [k for k, v in sides.items() if v is None]})
    return out


def exterior_openings(page, metre_per_point, walls, envelope):
    """Gaps in the CLT walls along the heated envelope: windows and glazed bays, with what spans them.
    A gap counts only when a reviewed room lies right behind it (within 0.5 m): an open porch is not glazing."""
    gaps = envelope.exterior.difference(union_all(walls).buffer(1.5))
    behind = union_all([box(r["rect"][0] * page.rect.width, r["rect"][1] * page.rect.height, r["rect"][2] * page.rect.width,
                            r["rect"][3] * page.rect.height) for r in rooms(page, metre_per_point)])
    bands = [(b, "lintel") for b in _bands(page, LINTEL, metre_per_point)] + \
            [(b, "viga") for b in _bands(page, STEEL_BEAM, metre_per_point)]
    out = []
    for segment in getattr(gaps, "geoms", [gaps]):
        width = segment.length * metre_per_point
        if width < .3 or not segment.buffer(.5 / metre_per_point, cap_style="flat").intersects(behind):
            continue
        over = next((kind for band, kind in bands if band.buffer(3).intersection(segment).length > .5 * segment.length), None)
        out.append({"largura_m": round(width, 2), "sobre": over, "tipo": "vao_envidracado" if over == "viga" or width > 2 else "janela",
                    "rect": _rectangle(page, segment.buffer(2).bounds)})
    return out
