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
from .quarter_turn_top import QuarterTurnTopInput, compute_quarter_turn_top
from .half_turn import HalfTurnInput, compute_half_turn
from .helicoidal import HelicoidalInput, compute_helicoidal
from .optimizer import OptimizeInput, OptimizeResult, compute_optimize
from .concrete import ConcreteAnalysisInput, ConcreteAnalysisResult, compute_concrete_analysis
from .blondel import blondel_value, optimal_giron_mm

__all__ = [
    "Alert", "AlertLevel", "StairInput", "QuarterTurnBottomInput",
    "QuarterTurnTopInput", "HalfTurnInput", "HelicoidalInput",
    "OptimizeInput", "OptimizeResult",
    "ConcreteAnalysisInput", "ConcreteAnalysisResult",
    "StairResult", "TreadDetail", "DTU_36_3_FR", "StairNorms",
    "compute_straight", "compute_quarter_turn_bottom", "compute_quarter_turn_top",
    "compute_half_turn", "compute_helicoidal", "compute_optimize",
    "compute_concrete_analysis",
    "blondel_value", "optimal_giron_mm",
]
