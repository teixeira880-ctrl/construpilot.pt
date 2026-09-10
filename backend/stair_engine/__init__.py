"""STAIRPILOT — Moteur de calcul déterministe d'escaliers béton (Phase 0).

Module 100% déterministe, aucune IA. Toutes les cotes en millimètres.
Angles en degrés dans la sortie.
"""

from .models import (
    Alert,
    AlertLevel,
    QuarterTurnBottomInput,
    StairInput,
    StairResult,
    TreadDetail,
)
from .norms_fr import DTU_36_3_FR, StairNorms
from .straight import compute_straight
from .quarter_turn import compute_quarter_turn_bottom
from .blondel import blondel_value, optimal_giron_mm

__all__ = [
    "Alert",
    "AlertLevel",
    "StairInput",
    "QuarterTurnBottomInput",
    "StairResult",
    "TreadDetail",
    "DTU_36_3_FR",
    "StairNorms",
    "compute_straight",
    "compute_quarter_turn_bottom",
    "blondel_value",
    "optimal_giron_mm",
]
