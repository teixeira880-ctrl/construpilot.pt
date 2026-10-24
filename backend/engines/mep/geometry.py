"""Géométrie 2D pure (mètres, repère du plan : x vers la droite, y vers le bas).

Aucune dépendance externe : le moteur MEP doit rester testable sans shapely/numpy.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Pt = tuple[float, float]


def area(poly: Sequence[Pt]) -> float:
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def perimeter(poly: Sequence[Pt]) -> float:
    return sum(dist(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def dist(a: Pt, b: Pt) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def manhattan(a: Pt, b: Pt) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def point_in_polygon(p: Pt, poly: Sequence[Pt]) -> bool:
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xin = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
            if x < xin:
                inside = not inside
    return inside


def centroid(poly: Sequence[Pt]) -> Pt:
    """Centroïde surfacique ; si le centroïde tombe hors d'un polygone concave,
    on prend le point intérieur le plus proche le long d'une grille fine."""
    a = 0.0
    cx = cy = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        c = x1 * y2 - x2 * y1
        a += c
        cx += (x1 + x2) * c
        cy += (y1 + y2) * c
    if abs(a) < 1e-9:
        xs, ys = zip(*poly)
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    c = (cx / (3 * a), cy / (3 * a))
    if point_in_polygon(c, poly):
        return c
    return interior_point_near(c, poly)


def interior_point_near(target: Pt, poly: Sequence[Pt], step: float = 0.1) -> Pt:
    xs, ys = zip(*poly)
    best, bd = None, 1e18
    x = min(xs) + step / 2
    while x < max(xs):
        y = min(ys) + step / 2
        while y < max(ys):
            if point_in_polygon((x, y), poly) and min_dist_to_boundary((x, y), poly) > 0.3:
                d = dist((x, y), target)
                if d < bd:
                    best, bd = (x, y), d
            y += step
        x += step
    return best or (sum(xs) / len(xs), sum(ys) / len(ys))


def edges(poly: Sequence[Pt]) -> list[tuple[Pt, Pt]]:
    return [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]


def project_on_segment(p: Pt, a: Pt, b: Pt) -> tuple[float, float]:
    """Renvoie (t, distance) : paramètre 0-1 du projeté sur [a,b] et distance au segment."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return 0.0, dist(p, a)
    t = ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2
    tc = max(0.0, min(1.0, t))
    q = (ax + tc * dx, ay + tc * dy)
    return t, dist(p, q)


def min_dist_to_boundary(p: Pt, poly: Sequence[Pt]) -> float:
    return min(project_on_segment(p, a, b)[1] for a, b in edges(poly))


def lerp(a: Pt, b: Pt, t: float) -> Pt:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def inward_normal(a: Pt, b: Pt, poly: Sequence[Pt]) -> Pt:
    """Normale unitaire du segment [a,b] orientée vers l'intérieur du polygone."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    n = (-dy / L, dx / L)
    mid = lerp(a, b, 0.5)
    test = (mid[0] + n[0] * 0.05, mid[1] + n[1] * 0.05)
    if point_in_polygon(test, poly):
        return n
    return (-n[0], -n[1])


def offset_into(poly: Sequence[Pt], a: Pt, b: Pt, t: float, d: float) -> Pt:
    p = lerp(a, b, t)
    n = inward_normal(a, b, poly)
    return (p[0] + n[0] * d, p[1] + n[1] * d)


def bbox(points: Iterable[Pt]) -> tuple[float, float, float, float]:
    pts = list(points)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def translate(poly: Sequence[Pt], dx: float, dy: float) -> list[Pt]:
    return [(x + dx, y + dy) for x, y in poly]


def rect_footprint(center: Pt, w: float, h: float) -> list[Pt]:
    cx, cy = center
    return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]


def dist_point_to_rect(p: Pt, rect: Sequence[Pt]) -> float:
    if point_in_polygon(p, rect):
        return 0.0
    return min_dist_to_boundary(p, rect)


def manhattan_path(a: Pt, b: Pt, horizontal_first: bool = True) -> list[Pt]:
    if horizontal_first:
        return [a, (b[0], a[1]), b]
    return [a, (a[0], b[1]), b]


def path_length(path: Sequence[Pt]) -> float:
    return sum(dist(path[i], path[i + 1]) for i in range(len(path) - 1))
