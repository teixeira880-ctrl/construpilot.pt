"""Système d'alertes STAIRPILOT.

Codes minimum :
    - HEADROOM_INSUFFICIENT (rouge, échappée < 1.90m)
    - STAIRWELL_TOO_SMALL (rouge, trémie incompatible)
    - BLONDEL_OUT_OF_RANGE (rouge <580 ou >660, orange 580-600 ou 640-660)
    - RISER_TOO_HIGH (rouge >200, orange >180)
    - RISER_TOO_LOW (orange <150)
    - TREAD_TOO_SMALL (rouge <220, orange <250)
    - SLOPE_TOO_STEEP (rouge >40°, orange >35°)
    - STAIR_RUN_TOO_LONG (rouge, ne rentre pas dans available_length)
    - STAIR_WIDTH_TOO_SMALL (orange <700)
    - BALANCING_IMPOSSIBLE (rouge, contraintes winders incompatibles)
    - BALANCING_INNER_TOO_SMALL (orange, giron intérieur < 100)
    - BALANCING_WALKLINE_TOO_SMALL (rouge, giron ligne de foulée < 240)
    - GEOMETRY_OK (vert, tout est dans les clous)
    - OPTIMAL_CONFIG (vert, Blondel 620-640 + pente 28-33°)
"""
from __future__ import annotations

from typing import List, Optional

from .models import Alert
from .norms_fr import DTU_36_3_FR, StairNorms


def check_blondel(blondel_mm: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if blondel_mm < norms.blondel_acceptable_min_mm or blondel_mm > norms.blondel_acceptable_max_mm:
        return Alert(
            level="red",
            code="BLONDEL_OUT_OF_RANGE",
            message_fr=(
                f"Formule de Blondel (2h+g) = {blondel_mm:.0f} mm hors plage acceptable "
                f"[{norms.blondel_acceptable_min_mm:.0f}, {norms.blondel_acceptable_max_mm:.0f}]."
            ),
            metric="blondel_mm",
            value=blondel_mm,
            threshold=norms.blondel_acceptable_min_mm,
        )
    if blondel_mm < norms.blondel_optimal_min_mm or blondel_mm > norms.blondel_optimal_max_mm:
        return Alert(
            level="orange",
            code="BLONDEL_OUT_OF_RANGE",
            message_fr=(
                f"Formule de Blondel (2h+g) = {blondel_mm:.0f} mm hors plage optimale "
                f"[{norms.blondel_optimal_min_mm:.0f}, {norms.blondel_optimal_max_mm:.0f}]."
            ),
            metric="blondel_mm",
            value=blondel_mm,
            threshold=norms.blondel_optimal_min_mm,
        )
    return None


def check_riser(h_mm: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if h_mm > norms.riser_height_max_mm:
        return Alert(
            level="red",
            code="RISER_TOO_HIGH",
            message_fr=(
                f"Hauteur de marche {h_mm:.1f} mm > {norms.riser_height_max_mm:.0f} mm "
                "(non conforme DTU 36.3)."
            ),
            metric="riser_height_mm",
            value=h_mm,
            threshold=norms.riser_height_max_mm,
        )
    if h_mm > norms.riser_height_optimal_max_mm:
        return Alert(
            level="orange",
            code="RISER_TOO_HIGH",
            message_fr=(
                f"Hauteur de marche {h_mm:.1f} mm au-delà de la plage optimale "
                f"({norms.riser_height_optimal_max_mm:.0f} mm)."
            ),
            metric="riser_height_mm",
            value=h_mm,
            threshold=norms.riser_height_optimal_max_mm,
        )
    if h_mm < norms.riser_height_optimal_min_mm - 10:  # <150
        return Alert(
            level="orange",
            code="RISER_TOO_LOW",
            message_fr=(
                f"Hauteur de marche {h_mm:.1f} mm inférieure au confort recommandé "
                f"(<{norms.riser_height_optimal_min_mm - 10:.0f} mm)."
            ),
            metric="riser_height_mm",
            value=h_mm,
            threshold=norms.riser_height_optimal_min_mm - 10,
        )
    return None


def check_tread(g_mm: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if g_mm < norms.tread_depth_hard_min_mm:
        return Alert(
            level="red",
            code="TREAD_TOO_SMALL",
            message_fr=(
                f"Giron {g_mm:.1f} mm < minimum absolu {norms.tread_depth_hard_min_mm:.0f} mm."
            ),
            metric="tread_depth_mm",
            value=g_mm,
            threshold=norms.tread_depth_hard_min_mm,
        )
    if g_mm < norms.tread_depth_optimal_min_mm:
        return Alert(
            level="orange",
            code="TREAD_TOO_SMALL",
            message_fr=(
                f"Giron {g_mm:.1f} mm inférieur à la plage optimale "
                f"({norms.tread_depth_optimal_min_mm:.0f} mm)."
            ),
            metric="tread_depth_mm",
            value=g_mm,
            threshold=norms.tread_depth_optimal_min_mm,
        )
    return None


def check_slope(slope_deg: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if slope_deg > norms.slope_hard_max_deg:
        return Alert(
            level="red",
            code="SLOPE_TOO_STEEP",
            message_fr=(
                f"Pente {slope_deg:.1f}° > {norms.slope_hard_max_deg:.0f}° "
                "(escalier trop raide, dangereux)."
            ),
            metric="slope_deg",
            value=slope_deg,
            threshold=norms.slope_hard_max_deg,
        )
    if slope_deg > norms.slope_acceptable_max_deg:
        return Alert(
            level="orange",
            code="SLOPE_TOO_STEEP",
            message_fr=(
                f"Pente {slope_deg:.1f}° au-delà de la plage confortable "
                f"({norms.slope_acceptable_max_deg:.0f}°)."
            ),
            metric="slope_deg",
            value=slope_deg,
            threshold=norms.slope_acceptable_max_deg,
        )
    return None


def check_headroom(
    headroom_mm: float,
    tread_index: Optional[int] = None,
    norms: StairNorms = DTU_36_3_FR,
) -> Optional[Alert]:
    if headroom_mm < norms.headroom_min_mm:
        tread_str = f" au niveau de la marche n°{tread_index}" if tread_index else ""
        return Alert(
            level="red",
            code="HEADROOM_INSUFFICIENT",
            message_fr=(
                f"Échappée {headroom_mm:.0f} mm{tread_str} < minimum "
                f"{norms.headroom_min_mm:.0f} mm (DTU 36.3)."
            ),
            metric="headroom_mm",
            value=headroom_mm,
            threshold=norms.headroom_min_mm,
            tread_index=tread_index,
        )
    return None


def check_stair_width(width_mm: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if width_mm < norms.stair_width_min_mm:
        return Alert(
            level="orange",
            code="STAIR_WIDTH_TOO_SMALL",
            message_fr=(
                f"Largeur d'escalier {width_mm:.0f} mm < minimum de confort "
                f"{norms.stair_width_min_mm:.0f} mm."
            ),
            metric="stair_width_mm",
            value=width_mm,
            threshold=norms.stair_width_min_mm,
        )
    return None


def check_stair_run_fits(
    required_run_mm: float, available_length_mm: float
) -> Optional[Alert]:
    if required_run_mm > available_length_mm:
        return Alert(
            level="red",
            code="STAIR_RUN_TOO_LONG",
            message_fr=(
                f"Reculement nécessaire {required_run_mm:.0f} mm > disponible "
                f"{available_length_mm:.0f} mm. L'escalier ne rentre pas."
            ),
            metric="stair_run_mm",
            value=required_run_mm,
            threshold=available_length_mm,
        )
    return None


def check_optimal(
    blondel_mm: float, slope_deg: float, norms: StairNorms = DTU_36_3_FR
) -> Optional[Alert]:
    if (
        norms.blondel_optimal_min_mm + 20 <= blondel_mm <= norms.blondel_optimal_max_mm
        and norms.slope_optimal_min_deg <= slope_deg <= norms.slope_optimal_max_deg
    ):
        return Alert(
            level="green",
            code="OPTIMAL_CONFIG",
            message_fr="Configuration optimale : Blondel et pente dans les plages idéales.",
        )
    return None


def summarize(alerts: List[Alert]) -> List[Alert]:
    """Ajoute un GEOMETRY_OK vert si aucune alerte rouge/orange n'a été émise (hors verts)."""
    non_green = [a for a in alerts if a.level != "green"]
    if not non_green:
        alerts.append(
            Alert(
                level="green",
                code="GEOMETRY_OK",
                message_fr="Géométrie conforme aux seuils DTU 36.3.",
            )
        )
    return alerts
