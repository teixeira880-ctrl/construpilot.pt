"""Formule de Blondel et fonctions de confort associées."""
from __future__ import annotations

from typing import Tuple

from .norms_fr import DTU_36_3_FR, StairNorms


def blondel_value(riser_height_mm: float, tread_depth_mm: float) -> float:
    """Retourne 2h + g (en mm)."""
    return 2.0 * riser_height_mm + tread_depth_mm


def optimal_giron_mm(
    riser_height_mm: float,
    norms: StairNorms = DTU_36_3_FR,
    target_blondel_mm: float = 630.0,
) -> float:
    """Calcule le giron optimal via Blondel: g = target - 2h, clampé au range acceptable."""
    g = target_blondel_mm - 2.0 * riser_height_mm
    # clamp à [220, 320] par défaut (DTU)
    if g < norms.tread_depth_hard_min_mm:
        return norms.tread_depth_hard_min_mm
    if g > norms.tread_depth_optimal_max_mm:
        return norms.tread_depth_optimal_max_mm
    return g


def find_optimal_num_steps(
    floor_height_mm: float,
    norms: StairNorms = DTU_36_3_FR,
) -> Tuple[int, float, bool]:
    """Trouve le nombre optimal de marches (risers).

    Algorithme:
        1. Chercher n tel que floor_height_mm/n ∈ [160, 180] en minimisant |h - 170|.
        2. Sinon, élargir à [155, 195].
        3. Sinon, retourner la meilleure approximation possible et flag out_of_norm=True.

    Retourne (n, h, in_acceptable_range)
    """
    if floor_height_mm <= 0:
        return (0, 0.0, False)

    best_n = 0
    best_h = 0.0
    best_dist = float("inf")

    # Recherche stricte dans [optimal_min, optimal_max]
    for n in range(1, 200):
        h = floor_height_mm / n
        if norms.riser_height_optimal_min_mm <= h <= norms.riser_height_optimal_max_mm:
            dist = abs(h - 170.0)
            if dist < best_dist:
                best_dist = dist
                best_n = n
                best_h = h

    if best_n > 0:
        return (best_n, best_h, True)

    # Élargi à acceptable
    best_dist = float("inf")
    for n in range(1, 200):
        h = floor_height_mm / n
        if norms.riser_height_acceptable_min_mm <= h <= norms.riser_height_acceptable_max_mm:
            dist = abs(h - 170.0)
            if dist < best_dist:
                best_dist = dist
                best_n = n
                best_h = h

    if best_n > 0:
        return (best_n, best_h, False)

    # Hors norme : choisir le n qui donne h le plus proche de 170
    best_dist = float("inf")
    for n in range(1, 200):
        h = floor_height_mm / n
        dist = abs(h - 170.0)
        if dist < best_dist:
            best_dist = dist
            best_n = n
            best_h = h

    return (best_n, best_h, False)
