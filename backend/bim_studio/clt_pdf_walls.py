"""Generic CLT wall detection on any vector PDF plan.

The Home A take-off (home_a_takeoff) uses reviewed path numbers for one exact
file. This reader works on a new drawing: it collects every rectangle drawn
as vectors, converts it to metres with the drawing scale, and keeps the bands
whose drawn width matches a nominal CLT thickness. Everything it returns is
marked "detetado, por confirmar" until a person accepts the walls.

Scale: given by the user, or read from a single "1:N" label on the sheet.
When the sheet carries more than one scale the user must choose.
"""
from __future__ import annotations

import re
from collections import Counter

import fitz
from shapely.geometry import Polygon

from bim_studio.clt_walls import Floor, analyse, rectangles_to_axes

POINT_MM = 25.4 / 72
SCALE_RE = re.compile(r"(?<![\d.,])1\s*[:/]\s*(\d{2,3})(?![\d.,])")
NOMINAL_MM = (60, 80, 90, 100, 120, 140, 160, 180, 200, 220, 240, 260, 280, 300)


def scales_on_page(page):
    return sorted({int(m) for m in SCALE_RE.findall(page.get_text())} & {20, 25, 50, 75, 100, 200})


def _hex(colour):
    if not colour:
        return None
    return "#" + "".join(f"{round(c * 255):02x}" for c in colour[:3])


def _quads(page):
    """Every 4-corner shape drawn as a rectangle, quad or closed 4-line path."""
    M = page.rotation_matrix
    for path in page.get_drawings():
        colour = _hex(path.get("fill")) or _hex(path.get("color"))
        items = path["items"]
        if all(i[0] == "re" for i in items):
            for i in items:
                r = i[1] * M
                yield [(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)], colour
        elif all(i[0] == "qu" for i in items):
            for i in items:
                q = i[1]
                yield [tuple(v * M) for v in (q.ul, q.ur, q.lr, q.ll)], colour
        elif len(items) in (3, 4) and all(i[0] == "l" for i in items):
            pts = [tuple(i[1] * M) for i in items] + [tuple(items[-1][2] * M)]
            if len(items) == 4 and abs(pts[0][0] - pts[-1][0]) + abs(pts[0][1] - pts[-1][1]) > 0.5:
                continue
            yield pts[:4], colour


def _sides(poly):
    c = list(poly.minimum_rotated_rectangle.exterior.coords)
    return sorted(((c[i][0] - c[i + 1][0]) ** 2 + (c[i][1] - c[i + 1][1]) ** 2) ** .5 for i in range(2))


def detect(data: bytes, page_number: int, *, scale: int | None = None, height_m: float, layers: int = 5,
           colour: str | None = None, tolerance_mm: float = 3.0, nominal_mm=NOMINAL_MM, min_length_m: float = 0.1):
    with fitz.open(stream=data, filetype="pdf") as doc:
        if not 1 <= page_number <= len(doc):
            raise ValueError("Página inexistente no PDF.")
        page = doc[page_number - 1]
        found = scales_on_page(page)
        if scale is None:
            if len(found) != 1:
                raise ValueError("Indique a escala: a folha tem " + (
                    f"várias escalas ({', '.join(f'1:{s}' for s in found)})." if found else "nenhuma escala legível."))
            scale, scale_source = found[0], f"escala 1:{found[0]} lida na folha"
        else:
            scale_source = f"escala 1:{scale} indicada pelo utilizador" + (
                "" if not found or scale in found else f" (a folha indica {', '.join(f'1:{s}' for s in found)})")
        factor = POINT_MM * scale / 1000  # metres per point
        width_pt, height_pt = page.rect.width, page.rect.height
        candidates, colours = [], Counter()
        for pts, col in _quads(page):
            poly = Polygon(pts)
            if not poly.is_valid or poly.area <= 0:
                continue
            rect = poly.minimum_rotated_rectangle
            c = list(rect.exterior.coords)
            sides = sorted(((c[i][0] - c[i + 1][0]) ** 2 + (c[i][1] - c[i + 1][1]) ** 2) ** .5 for i in range(2))
            thick, length = sides[0] * factor * 1000, sides[1] * factor
            if length < min_length_m or length <= thick / 1000:
                continue
            if min(abs(thick - t) for t in nominal_mm) > tolerance_mm:
                continue
            if poly.area < 0.98 * rect.area:
                continue
            candidates.append((poly, col))
            colours[col] += 1
        if colour:
            chosen = colour.lower()
        elif colours:
            chosen = colours.most_common(1)[0][0]
        else:
            chosen = None
        kept = []
        for poly, col in candidates:
            if col != chosen:
                continue
            if any(poly.intersection(k).area > 0.9 * min(poly.area, k.area) for k in kept):
                continue  # the same band drawn twice (fill and stroke)
            kept.append(poly)
        # Walls drawn only with the CLT hatch and no outline (the Home A +1 case):
        # the hatch reader learns each hatch colour's thickness from the outlined
        # walls on the same sheet and accepts a band only when it matches.
        from bim_studio.home_a_takeoff import _hatched_runs

        outline_markers = [{"id": f"o{i}", "drawing_width_mm": min(
            _sides(p)) * factor * 1000} for i, p in enumerate(kept)]
        hatched = _hatched_runs(page, factor, kept, outline_markers) if kept else []
        pending = [{k: v for k, v in m.items() if k != "_polygon"} for m in hatched if m["status"] != "measured"]
        kept += [m["_polygon"].minimum_rotated_rectangle for m in hatched if m["status"] == "measured"]
        rects = [[(x * factor, -y * factor) for x, y in list(p.exterior.coords)[:4]] for p in kept]
        markers = [{"rect": [round(v, 6) for v in (p.bounds[0] / width_pt, p.bounds[1] / height_pt,
                                                   p.bounds[2] / width_pt, p.bounds[3] / height_pt)]} for p in kept]
    walls, rejected = rectangles_to_axes(rects, height_m=height_m, layers=layers, nominal_mm=nominal_mm,
                                         tolerance_mm=tolerance_mm, prefix=f"P{page_number}-",
                                         source=f"PDF p.{page_number}, {scale_source}")
    wall_markers = []
    for w in walls:
        index = int(w.id.rsplit("-", 1)[1]) - 1  # rectangles_to_axes numbers walls from 1 by input order
        wall_markers.append({**markers[index], "id": w.id, "status": "detetado",
                             "label": f"{w.id} · {w.length:.3f} m · {w.thickness_mm:g} mm"})
    result = {"pagina": page_number, "escala": scale, "origem_escala": scale_source,
              "cores_candidatas": [{"cor": c, "bandas": n} for c, n in colours.most_common(8)],
              "cor_usada": chosen, "rejeitados": rejected, "tracejados_por_confirmar": pending,
              "tracejados_medidos": sum(1 for m in hatched if m["status"] == "measured"), "estado": "detetado, por confirmar",
              "paredes": [w.model_dump() for w in walls], "marcadores": wall_markers}
    if walls:
        result["analise"] = analyse(Floor(name=f"Página {page_number}", walls=walls))
    return result
