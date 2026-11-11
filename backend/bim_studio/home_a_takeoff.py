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
    area = union_all(polygons).area * metre_per_point ** 2
    return area, markers


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
        "RDC": {"floor_buildup_m": (wall_base - floor_level(wall_base)) * scale,
                "ceiling_zone_m": (ceiling_face(slab[-1]) - slab[-1]) * scale},
        "+1": {"floor_buildup_m": (slab[0] - floor_level(slab[0])) * scale,
               "ceiling_zone_m": (ceiling_face(roof[-1]) - roof[-1]) * scale},
    }


def review_page(page, evidence):
    number = page.number + 1
    result = {"floor": FLOORS[number], "clt_plan_m2": None, "clt_volume_m3": None,
              "interior_base_m2": None, "finish_area_m2": None, "finish_volume_m3": None,
              "notes": [], "markers": [], "in_scope": number in OUTLINES}
    if number in OUTLINES:
        result["clt_plan_m2"], result["markers"] = _clt_footprints(page)
        result["notes"].append("Área ocupada em planta pelos troços assinalados. Não corresponde à área da face vertical nem à área das lajes.")
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
