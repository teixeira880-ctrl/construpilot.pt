"""Geometry Engine — calculs mathématiques purs pour les mesures de plan.

Toutes les fonctions travaillent en unités RÉELLES (mètres), après application
d'une calibration `pixels_per_meter`. Les entrées sont des listes de points
[(x, y), ...] en pixels ou coordonnées calibrées selon la fonction.

Ces fonctions sont intentionnellement PURES et testables — aucun accès DB, aucun
appel LLM. C'est ici que la précision se joue.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = tuple[float, float]


# ============ CALIBRATION ============

def compute_calibration(p1_px: Point, p2_px: Point, real_meters: float) -> dict:
    """À partir de 2 points en pixels et de la distance réelle connue en mètres,
    renvoie le ratio pixels_per_meter (et son inverse).
    """
    if not math.isfinite(real_meters) or real_meters <= 0:
        raise ValueError("A distância real deve ser > 0")
    dx = p2_px[0] - p1_px[0]
    dy = p2_px[1] - p1_px[1]
    pixel_dist = math.hypot(dx, dy)
    if not math.isfinite(pixel_dist) or pixel_dist < 1e-6:
        raise ValueError("Os dois pontos devem ser distintos")
    ppm = pixel_dist / real_meters
    if round(ppm, 6) <= 0 or not math.isfinite(ppm):
        raise ValueError("Escala inválida: escolha uma referência mais longa")
    return {
        "pixels_per_meter": round(ppm, 6),
        "meters_per_pixel": round(1.0 / ppm, 8),
        "reference_pixel_distance": round(pixel_dist, 3),
        "reference_real_distance_m": real_meters,
    }


def px_to_m(dist_px: float, pixels_per_meter: float) -> float:
    """Convertit une distance pixel en mètres."""
    if pixels_per_meter <= 0:
        return 0.0
    return dist_px / pixels_per_meter


# ============ MESURES LINÉAIRES ============

def distance_m(p1: Point, p2: Point, pixels_per_meter: float) -> float:
    """Distance euclidienne entre 2 points (pixels) → mètres."""
    return px_to_m(math.hypot(p2[0] - p1[0], p2[1] - p1[1]), pixels_per_meter)


def polyline_length_m(points: Sequence[Point], pixels_per_meter: float) -> float:
    """Longueur totale d'une polyligne (somme des segments)."""
    if len(points) < 2:
        return 0.0
    total_px = sum(
        math.hypot(points[i + 1][0] - points[i][0], points[i + 1][1] - points[i][1])
        for i in range(len(points) - 1)
    )
    return px_to_m(total_px, pixels_per_meter)


# ============ POLYGONES (SURFACES) ============

def point_in_polygon(x: float, y: float, points: Sequence[Point]) -> bool:
    """Test pair-impair (ray casting) — le point (x, y) est-il dans le polygone ?"""
    inside = False
    n = len(points)
    j = n - 1
    for i in range(n):
        xi, yi = points[i][0], points[i][1]
        xj, yj = points[j][0], points[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def polygon_area_m2(points: Sequence[Point], pixels_per_meter: float) -> float:
    """Aire d'un polygone (Shoelace / Gauss), fermé implicitement.
    Retourne toujours une valeur positive en m².
    """
    if len(points) < 3 or pixels_per_meter <= 0:
        return 0.0
    n = len(points)
    s = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    area_px2 = abs(s) / 2.0
    return area_px2 / (pixels_per_meter ** 2)


def polygon_perimeter_m(points: Sequence[Point], pixels_per_meter: float) -> float:
    """Périmètre (polygone fermé)."""
    if len(points) < 2:
        return 0.0
    closed = list(points) + [points[0]]
    return polyline_length_m(closed, pixels_per_meter)


# ============ MÉTRÉ DE PIÈCE ============

def room_measurements(points: Sequence[Point], pixels_per_meter: float,
                      ceiling_height_m: float = 2.50) -> dict:
    """Renvoie surface / périmètre / surface brute de murs pour une pièce.

    - `surface_m2` : surface au sol.
    - `perimeter_m` : périmètre.
    - `wall_area_gross_m2` : murs bruts (périmètre × hauteur), ouvertures non déduites.
    - `ceiling_area_m2` : ≈ surface sol (plafond plat).
    """
    surface = polygon_area_m2(points, pixels_per_meter)
    perimeter = polygon_perimeter_m(points, pixels_per_meter)
    walls_gross = perimeter * max(0.0, ceiling_height_m)
    return {
        "surface_m2": round(surface, 3),
        "perimeter_m": round(perimeter, 3),
        "ceiling_area_m2": round(surface, 3),
        "wall_area_gross_m2": round(walls_gross, 3),
        "ceiling_height_m": ceiling_height_m,
    }


def subtract_openings(wall_area_gross_m2: float, openings: Iterable[dict]) -> dict:
    """Soustrait les ouvertures (portes/fenêtres/baies) d'une surface brute de murs.
    Chaque opening = {"width_m": float, "height_m": float, "kind": str}
    """
    total_open = 0.0
    per_opening = []
    for o in openings or []:
        w = float(o.get("width_m", 0) or 0)
        h = float(o.get("height_m", 0) or 0)
        count = max(0, int(o.get("count", 1)))
        area = max(0.0, w) * max(0.0, h) * count
        total_open += area
        per_opening.append({**o, "area_m2": round(area, 3)})
    net = max(0.0, wall_area_gross_m2 - total_open)
    return {
        "openings": per_opening,
        "openings_area_m2": round(total_open, 3),
        "wall_area_net_m2": round(net, 3),
    }


# ============ QUANTITÉS MATÉRIAUX ============

def apply_waste(quantity: float, waste_pct: float) -> float:
    """Applique un facteur de perte (ex 7% pour parquet, 10% pour carrelage)."""
    if quantity <= 0:
        return 0.0
    return quantity * (1 + max(0.0, waste_pct) / 100.0)


def round_up_pack(quantity: float, pack_size: float) -> int:
    """Arrondit vers le haut à l'unité vendue (ex: paquet 3 m²)."""
    if pack_size <= 0:
        return int(math.ceil(quantity))
    return int(math.ceil(quantity / pack_size))


def paint_liters(surface_m2: float, coats: int = 2, yield_m2_per_liter: float = 10.0,
                 margin_pct: float = 15.0) -> dict:
    """Besoin peinture — rendement en m²/L/couche, marge de sécurité."""
    if surface_m2 <= 0 or yield_m2_per_liter <= 0:
        return {"surface_m2": 0, "liters_theoretical": 0, "liters_recommended": 0}
    theoretical = (surface_m2 * coats) / yield_m2_per_liter
    recommended = math.ceil(theoretical * (1 + margin_pct / 100.0))
    return {
        "surface_m2": round(surface_m2, 2),
        "coats": coats,
        "yield_m2_per_liter": yield_m2_per_liter,
        "liters_theoretical": round(theoretical, 2),
        "liters_recommended": recommended,
        "margin_pct": margin_pct,
    }


def placo_quantity(wall_area_m2: float, plate_size_m2: float = 3.0,
                   waste_pct: float = 5.0) -> dict:
    """Nombre de plaques BA13 (arrondi supérieur pack)."""
    if wall_area_m2 <= 0:
        return {"plates": 0, "surface_m2": 0}
    plates_theoretical = (wall_area_m2 * (1 + waste_pct / 100.0)) / plate_size_m2
    return {
        "surface_m2": round(wall_area_m2, 2),
        "plate_size_m2": plate_size_m2,
        "waste_pct": waste_pct,
        "plates_theoretical": round(plates_theoretical, 2),
        "plates": math.ceil(plates_theoretical),
    }


def floor_quantity(surface_m2: float, material: str = "parquet") -> dict:
    """Quantité de sol à commander selon le matériau (pertes appliquées)."""
    waste = {"parquet": 7.0, "carrelage": 10.0, "stratifie": 8.0,
             "vinyle": 5.0, "moquette": 5.0, "beton_cire": 0.0}.get(material, 8.0)
    q = apply_waste(surface_m2, waste)
    return {"material": material, "surface_m2": round(surface_m2, 2),
            "waste_pct": waste, "quantity_m2": round(q, 2)}


def skirting_length_m(perimeter_m: float, door_openings_m: float = 1.8,
                      waste_pct: float = 10.0) -> dict:
    """Longueur de plinthes (périmètre - largeur portes + pertes)."""
    net = max(0.0, perimeter_m - door_openings_m)
    total = apply_waste(net, waste_pct)
    return {"perimeter_m": round(perimeter_m, 2),
            "doors_deduction_m": door_openings_m,
            "net_m": round(net, 2), "quantity_m": round(total, 2)}


# ============ CALIBRATION VÉRIFICATION ============

def calibration_check(measured_m: float, expected_m: float) -> dict:
    """Compare une mesure à une valeur attendue → score cohérence."""
    if expected_m <= 0:
        return {"ok": False, "reason": "Valor esperado inválido"}
    delta = abs(measured_m - expected_m)
    pct = delta / expected_m * 100.0
    return {
        "measured_m": round(measured_m, 3),
        "expected_m": round(expected_m, 3),
        "delta_m": round(delta, 3),
        "delta_pct": round(pct, 2),
        "ok": pct < 2.0,   # tolérance 2%
        "recommendation": "Calibração coerente" if pct < 2.0
        else "Calibração a verificar" if pct < 5.0
        else "Recalibração recomendada",
    }

