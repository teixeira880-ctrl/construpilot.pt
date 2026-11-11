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

from bim_studio.clt_walls import Floor, analyse, connect, rectangles_to_axes

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


HEAD_RE = re.compile(r"(?<!\d)(\d{3,4})\s*[xX×]\s*(\d{4})\s*H?(?!\d)")
STANDARD_HEAD_M = 2.10  # door head when the sheet prints no "LxH" opening label (standard, editable)


def opening_head(page):
    """Door head height in metres: the most common H of the "900x2300H" labels on the sheet, else the standard."""
    heights = Counter(int(h) for _w, h in HEAD_RE.findall(page.get_text()) if 1800 <= int(h) <= 2800)
    if heights:
        h, n = heights.most_common(1)[0]
        return h / 1000, f"altura dos vãos {h} mm lida em {n} cota(s) da folha"
    return STANDARD_HEAD_M, f"altura dos vãos standard {STANDARD_HEAD_M:.2f} m (a folha não cota alturas; editável)"


def _dashed(page, gap_pt=4.0):
    """Straight dashed lines, by colour and width: drawn with a dash pattern or as runs of short collinear strokes."""
    M, groups = page.rotation_matrix, {}
    for path in page.get_drawings():
        colour = _hex(path.get("color"))
        if not colour:
            continue
        dashed = (path.get("dashes") or "[] 0").strip() not in ("[] 0", "[] 0.0", "")
        for item in path["items"]:
            if item[0] != "l":
                continue
            a, b = item[1] * M, item[2] * M
            if abs(a.y - b.y) < .3:
                key = (colour, round(path.get("width") or 0, 2), "h", round((a.y + b.y) / 2, 1))
                groups.setdefault(key, []).append((min(a.x, b.x), max(a.x, b.x), dashed))
            elif abs(a.x - b.x) < .3:
                key = (colour, round(path.get("width") or 0, 2), "v", round((a.x + b.x) / 2, 1))
                groups.setdefault(key, []).append((min(a.y, b.y), max(a.y, b.y), dashed))
    lines = []
    for key, spans in groups.items():
        spans.sort()
        start, end, strokes, flagged = spans[0][0], spans[0][1], 1, spans[0][2]
        for a, b, d in spans[1:] + [(float("inf"), float("inf"), False)]:
            if a <= end + gap_pt:
                end, strokes, flagged = max(end, b), strokes + 1, flagged or d
                continue
            if flagged or strokes >= 3:  # a dash pattern, or at least three strokes in a row
                lines.append((*key, start, end))
            start, end, strokes, flagged = a, b, 1, d
    return lines


def lintels(page, factor, walls_m, *, nominal_mm=NOMINAL_MM, tolerance_mm=5.0, colour=None, min_span_m=0.3):
    """CLT lintels drawn as two parallel dashed lines at a nominal CLT thickness over a gap between walls.

    A band is kept only when it touches the walls and crosses at least min_span_m of plan without wall (the opening).
    Windows and steel beams are often drawn the same way in another colour, so the bands are used as lintels only for
    the colour given, or when a single colour qualifies; otherwise every colour is returned for the user to choose.
    walls_m: the wall footprints in metres (x right, y up). Returns (lintels, candidate colours)."""
    from shapely import union_all
    from shapely.geometry import box

    drawn = union_all(walls_m) if walls_m else None
    lines = [ln for ln in _dashed(page) if (ln[5] - ln[4]) * factor >= min_span_m]
    bands, used = [], set()
    for i, (col, width, axis, off, a, b) in enumerate(lines):
        if i in used:
            continue
        mates = []
        for j, (c2, w2, ax2, o2, c, d) in enumerate(lines):
            if j == i or j in used or (c2, w2, ax2) != (col, width, axis):
                continue
            gap_mm = abs(o2 - off) * factor * 1000
            if min(abs(gap_mm - t) for t in nominal_mm) <= tolerance_mm and min(b, d) - max(a, c) > .5 * min(b - a, d - c):
                mates.append((abs(o2 - off), j))
        if not mates:
            continue
        _, j = min(mates)
        used.update((i, j))
        o2, c, d = lines[j][3], lines[j][4], lines[j][5]
        lo, hi, s0, e0 = min(off, o2) * factor, max(off, o2) * factor, min(a, c) * factor, max(b, d) * factor
        # page points (y down) to metres (y up), like the wall rectangles
        rect = box(s0, -hi, e0, -lo) if axis == "h" else box(lo, -e0, hi, -s0)
        thick = round((hi - lo) * 1000)
        if drawn is None or not rect.buffer(0.02).intersects(drawn):
            continue
        span = rect.difference(drawn).area / ((hi - lo) or 1)
        if span < min_span_m:
            continue
        bands.append((col, rect, min(nominal_mm, key=lambda t: abs(t - thick)), span))
    colours = Counter(b[0] for b in bands)
    chosen = colour.lower() if colour else (next(iter(colours)) if len(colours) == 1 else None)
    out = [{"ref": f"L{n}", "rect_m": [round(v, 4) for v in r.bounds], "thickness_mm": t, "vao_livre_m": round(sp, 3),
            "cor": c, "estado": "detetado, por confirmar"}
           for n, (c, r, t, sp) in enumerate((b for b in bands if b[0] == chosen), 1)]
    return out, [{"cor": c, "bandas": k, "usada": c == chosen} for c, k in colours.most_common(6)]


def _sides(poly):
    c = list(poly.minimum_rotated_rectangle.exterior.coords)
    return sorted(((c[i][0] - c[i + 1][0]) ** 2 + (c[i][1] - c[i + 1][1]) ** 2) ** .5 for i in range(2))


def detect(data: bytes, page_number: int, *, scale: int | None = None, height_m: float, layers: int = 5,
           colour: str | None = None, tolerance_mm: float = 3.0, nominal_mm=NOMINAL_MM, min_length_m: float = 0.1,
           lintel_colour: str | None = None):
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
        found_lintels, lintel_colours = lintels(page, factor, [Polygon(r) for r in rects], nominal_mm=nominal_mm,
                                               colour=lintel_colour)
        head_m, head_source = opening_head(page)
        for li in found_lintels:
            li["head_m"], li["origem_altura"] = head_m, head_source
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
              "paredes": [w.model_dump() for w in walls], "marcadores": wall_markers,
              "linteis": found_lintels, "cores_linteis": lintel_colours}
    if walls:
        healed, network = connect(walls, lintels=found_lintels)
        result["rede"] = network
        result["analise"] = analyse(Floor(name=f"Página {page_number}", walls=healed))
    return result
