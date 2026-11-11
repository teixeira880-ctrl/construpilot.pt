"""Reviewed vector take-off for the supplied Home A PDF revision.

The reviewed vector selections and independent scale references apply only to
this exact file. There are no assumed panel heights or finish assignments.
"""
from shapely import union_all
from shapely.geometry import Polygon

SOURCE_SHA256 = "0320687a95e44a63dfe8e28c702ccd38ec4b46563b5bf44166b0e946b93a761d"
FLOORS = {1: "Piso −1", 2: "Rés do chão", 3: "Primeiro piso", 4: "Pormenor construtivo"}
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
    markers.append({"id": "scale", "status": "measured", "label": scale_label,
                    "rect": _rectangle(page, (scale_box.x0 - 3, scale_box.y0 - 3, scale_box.x1 + 3, scale_box.y1 + 3))})
    area = union_all(polygons).area * metre_per_point ** 2
    return area, markers


def review_page(page, evidence):
    number = page.number + 1
    result = {"floor": FLOORS[number], "clt_plan_m2": None, "clt_volume_m3": None,
              "interior_base_m2": None, "finish_area_m2": None, "finish_volume_m3": None,
              "notes": [], "markers": []}
    if number in OUTLINES:
        result["clt_plan_m2"], result["markers"] = _clt_footprints(page)
        result["notes"].append("Área ocupada em planta pelos troços assinalados. Não corresponde à área da face vertical nem à área das lajes.")
    if number == 1:
        declared = [r for r in evidence if r["kind"] == "declared_area"]
        room_names = {40.45: "Sala de máquinas", 12.80: "Arrumos técnicos",
                      47.80: "Ginásio", 19.60: "Arrumos"}
        result["interior_base_m2"] = round(sum(r["values"][0] for r in declared), 2)
        result["notes"].append("Subtotal declarado de quatro divisões: sala de máquinas, arrumos técnicos, ginásio e arrumos. Exclui hall, IS e escada; acabamento não atribuído.")
        for item in declared:
            area = item["values"][0]
            result["markers"].append({"id": item["id"], "rect": item["rect"], "status": "declared",
                                      "label": f"{room_names.get(area, 'Área indicada')} · {area:.2f} m²"})
    if number == 2:
        result["notes"].append("O terraço coberto de 26,50 m² está excluído dos acabamentos interiores.")
    if number != 4:
        result["notes"].extend((
            "CLT: confirmar alturas estruturais por troço, correspondência dos vãos, lajes e limites de cada painel.",
            "Revestimentos: confirmar faces a revestir, altura de aplicação, demãos/camadas e descontos por vão.",
        ))
    else:
        result["notes"].append("O corte identifica CLT e placas de gesso. Confirmar a aplicação de cada composição por elemento e piso.")
    for item in evidence:
        if item["kind"] in ("ceiling_height", "opening_dimensions", "material_note"):
            result["markers"].append({"id": item["id"], "rect": item["rect"], "status": "pending",
                                      "label": item["text"]})
    return result
