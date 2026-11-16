"""Use an independently dimensioned native PDF contour in place of a nearby detected slab."""
from __future__ import annotations

from collections import defaultdict
import math
import re

from shapely.geometry import LineString, Point, Polygon

_AREA = re.compile(r"(?<![\d.,])(\d{1,5}(?:[.,]\d+)?)\s*m[²2]\s*(?:por piso|par niveau|per floor)\b", re.I)
_FRAME = ("x1", "y1", "x2", "y2")

# Deliberately omit the rendered images when the BIM route loads the PDF metadata.
PAGE_FIELDS = ("dpi", "width_px", "height_px", "vectors", "vectors_truncated", "text_blocks.text",
               "detected_scale_denominator", "pdf_dimensions", "auto_calibration_blocked",
               "geometry_coordinate_space", "view_kind")


def _reference(page, ppm):
    if (page.get("auto_calibration_blocked") or page.get("vectors_truncated")
        or page.get("geometry_coordinate_space") == "image_px"
        or page.get("view_kind") not in (None, "unknown", "floor_plan")):
        return None
    areas = {float(m.replace(",", ".")) for t in page.get("text_blocks") or [] for m in _AREA.findall(t.get("text") or "")}
    scale, dpi = page.get("detected_scale_denominator"), page.get("dpi")
    if len(areas) != 1 or not scale or not dpi or not ppm or not math.isclose(ppm, dpi / (0.0254 * scale), rel_tol=.001):
        return None
    area = areas.pop()
    paths = defaultdict(list)
    for v in page.get("vectors") or []:
        if v.get("paint_type") in ("fs", "f") and v.get("type") == "line" and v.get("path_id") is not None:
            paths[v["path_id"]].append((tuple(v["p1"]), tuple(v["p2"])))
    scale_m_per_pt = 0.0254 * scale / 72
    dims = [(d.get("orientation"), d.get("value_m")) for d in page.get("pdf_dimensions") or []
            if not d.get("unverified") and d.get("value_m") and d.get("measured_m") is not None
            and math.isclose(d["value_m"], d["measured_m"], abs_tol=.01)]
    if len(dims) < 3:
        return None
    matches = []
    for edges in paths.values():
        if len(edges) != 6 or any(math.dist(b, edges[(i+1) % 6][0]) > .01 for i, (_, b) in enumerate(edges)):
            continue
        x0, y0 = min(a[0] for a, _ in edges), max(a[1] for a, _ in edges)
        points_m = [(round((x-x0)*scale_m_per_pt, 3), round((y0-y)*scale_m_per_pt, 3)) for (x, y), _ in edges]
        outline = Polygon(points_m)
        if not outline.is_valid or not math.isclose(outline.area, area, abs_tol=.005):
            continue
        recess = outline.envelope.difference(outline)
        if recess.is_empty or not recess.equals(recess.envelope):
            continue
        sides = []
        for a, b in zip(points_m, points_m[1:]+points_m[:1]):
            if (a[0] == b[0]) == (a[1] == b[1]):
                break
            length = math.dist(a, b)
            along = "h" if a[1] == b[1] else "v"
            if not any(direction == along and math.isclose(length, dim, abs_tol=.002) for direction, dim in dims):
                break
            sides.append(round(length, 3))
        if len(sides) != 6:
            continue
        origin_x, origin_y = x0*ppm*scale_m_per_pt, y0*ppm*scale_m_per_pt
        px = [[origin_x+x*ppm, origin_y-y*ppm] for x,y in points_m]
        _, _, width, depth = outline.bounds
        a, b, c, d = recess.bounds
        matches.append((px, {"source": "pdf_vector_dimensions", "area_m2": round(outline.area, 3),
                             "width_m": width, "depth_m": depth, "recess_m": [round(c-a, 3), round(d-b, 3)],
                             "sides_m": sides, "perimeter_m": round(sum(sides), 3)}))
    return matches[0] if len(matches) == 1 else None


def _aligned_structure(structure, points, outline, ppm):
    floor, = structure["floors"]
    try:
        traced = Polygon(floor.get("points") or [])
    except (TypeError, ValueError):
        return structure
    exact = Polygon(points)
    if not traced.is_valid or traced.is_empty or exact.intersection(traced).area / exact.union(traced).area < .90:
        return structure
    if structure.get("edited_at"):
        return {**structure, "verified_outline": outline} if traced.equals_exact(exact, tolerance=.02, normalize=True) else structure
    edges = list(zip(points, points[1:] + points[:1]))
    tolerance = .20 * ppm
    replacements = []
    walls = [dict(wall) for wall in structure.get("walls") or []]
    for wall in walls:
        if not wall.get("wall_id") or wall.get("type") != "porteur" or not all(isinstance(wall.get(k), (float, int)) for k in _FRAME):
            continue
        a = (wall["x1"], wall["y1"])
        b = (wall["x2"], wall["y2"])
        choices = [(c, d) for edge in edges for c, d in (edge, edge[::-1])
                   if max(math.dist(a, c), math.dist(b, d)) <= tolerance]
        if len(choices) == 1:
            c, d = choices[0]
            replacements.append((wall["wall_id"], LineString((a, b)), LineString((c, d))))
    by_id = {ident: (old, new) for ident, old, new in replacements}
    for wall in walls:
        if wall.get("wall_id") in by_id:
            _, new = by_id[wall["wall_id"]]
            wall.update(zip(_FRAME, (*new.coords[0], *new.coords[1])))
        else:
            for k, l in (("x1", "y1"), ("x2", "y2")):
                if not all(isinstance(wall.get(name), (float, int)) for name in (k, l)):
                    continue
                p = Point(wall[k], wall[l])
                connections = [new for _, old, new in replacements if old.distance(p) <= .02 * ppm]
                if len(connections) == 1:
                    line = connections[0]
                    q = line.interpolate(line.project(p))
                    wall.update({k: q.x, l: q.y})

    openings = [dict(opening) for opening in structure.get("openings") or []]
    for opening in openings:
        if not all(isinstance(opening.get(k), (float, int)) for k in _FRAME):
            continue
        a, b = Point(opening["x1"], opening["y1"]), Point(opening["x2"], opening["y2"])
        host = [new for _, old, new in replacements if max(old.distance(a), old.distance(b)) <= .04 * ppm]
        if len(host) == 1:
            new = host[0]
            p, q = (new.interpolate(new.project(point)) for point in (a, b))
            if p.distance(q) >= .3 * ppm:
                opening.update(zip(_FRAME, (p.x, p.y, q.x, q.y)))
    return {**structure, "walls": walls, "openings": openings, "floors": [{**floor, "points": points}],
            "verified_outline": outline}


def verified_structure(plan, index):
    """Shared by the Editor and BIM. Preserve deliberately edited or ambiguous geometry."""
    key = str(index)
    structure = (plan.get("structure") or {}).get(key) or {}
    pages = plan.get("pages") or []
    if plan.get("kind") != "pdf" or not 0 <= index < len(pages) or len(structure.get("floors") or []) != 1:
        return structure
    page = pages[index]
    if any(structure.get(k) != page.get(p) or not page.get(p) for k,p in (("image_width", "width_px"), ("image_height", "height_px"))):
        return structure
    ppm = ((plan.get("calibrations") or {}).get(key) or {}).get("pixels_per_meter")
    ref = _reference(page, ppm)
    return _aligned_structure(structure, *ref, ppm) if ref else structure
