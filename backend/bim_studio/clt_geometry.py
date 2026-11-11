"""Auditable quantities for prismatic CLT panels and planar finishing faces."""
from __future__ import annotations

import math

from shapely import get_num_coordinates, union_all
from shapely.geometry import Polygon, box, mapping, shape


def closed_polygon(points):
    if len(points) < 4 or points[0] != points[-1]:
        raise ValueError("O contorno deve estar explicitamente fechado.")
    if any(len(p) != 2 or not all(map(math.isfinite, p)) for p in points):
        raise ValueError("Coordenadas 2D inválidas.")
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError("O contorno cruza-se ou não tem área.")
    return polygon


def panel_quantities(outline, openings, thickness_mm):
    """Metres in the local panel plane. Openings are through-cuts."""
    if not math.isfinite(thickness_mm) or thickness_mm <= 0:
        raise ValueError("A espessura do painel tem de estar confirmada.")
    gross = closed_polygon(outline)
    holes = [closed_polygon(ring) for ring in openings]
    if any(not gross.covers(hole) for hole in holes):
        raise ValueError("Um recorte não está inteiramente dentro do painel.")
    cutout = union_all(holes)
    if sum(hole.area for hole in holes) - cutout.area > 1e-9:
        raise ValueError("Há recortes sobrepostos.")
    net = gross.difference(cutout)
    if net.is_empty or net.geom_type != "Polygon" or not net.is_valid:
        raise ValueError("Os recortes removem ou dividem o painel.")
    return {
        "gross_area_m2": gross.area,
        "cutout_area_m2": gross.area - net.area,
        "net_area_m2": net.area,
        "gross_volume_m3": gross.area * thickness_mm / 1000,
        "net_volume_m3": net.area * thickness_mm / 1000,
        "face": mapping(net),
    }


def face_profile(triangles, axis):
    """Project a single vertical plane, preserving voids in its triangulation."""
    if len(triangles) == 0 or len(triangles) > 4096:
        return None
    # Work in a local system to avoid cancellation on georeferenced models.
    points = triangles - triangles[0, 0]
    distances = points[:, :, :2] @ axis
    if distances.max() - distances.min() > 1e-5:
        return None
    horizontal = points[:, :, 0] * -axis[1] + points[:, :, 1] * axis[0]
    polygons = [
        Polygon(zip(x, z + triangles[0, 0, 2]))
        for x, z in zip(horizontal, points[:, :, 2])
    ]
    if any(not polygon.is_valid or polygon.area <= 0 for polygon in polygons):
        return None
    profile = union_all(polygons)
    if (not profile.is_valid or get_num_coordinates(profile) > 512
            or profile.geom_type not in ("Polygon", "MultiPolygon")
            or abs(sum(p.area for p in polygons) - profile.area) > 1e-7 * max(1, profile.area)):
        return None
    return mapping(profile)


def band_area(profile, lower_m, upper_m):
    polygon = shape(profile)
    left, _, right, _ = polygon.bounds
    return polygon.intersection(box(left, lower_m, right, upper_m)).area


def reconciliation(value, reference, *, zero_tolerance=0):
    if any(not math.isfinite(x) or x < 0 for x in (value, reference, zero_tolerance)):
        raise ValueError("Medição, referência ou tolerância inválida.")
    error = abs(value - reference)
    limit = reference * 0.02 if reference else zero_tolerance
    return {"difference": error, "limit": limit,
            "error_percent": error / reference * 100 if reference else None,
            "passed": error <= limit or math.isclose(error, limit, rel_tol=1e-12, abs_tol=1e-12)}
