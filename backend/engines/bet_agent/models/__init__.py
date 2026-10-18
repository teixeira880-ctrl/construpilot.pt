"""Modelos Pydantic do BET-PT Agent — ver sub-módulos.

Importar directamente:
    from engines.bet_agent.models.building import BuildingModel, Floor, Wall, ...
    from engines.bet_agent.models.brief import UserBrief
    from engines.bet_agent.models.summary import Summary, Anomaly, Severity
"""
from __future__ import annotations

from engines.bet_agent.models.brief import UserBrief
from engines.bet_agent.models.building import (
    BuildingModel,
    ElementSource,
    Floor,
    Opening,
    Room,
    Roof,
    SlabOpening,
    Stair,
    StructuralElement,
    Wall,
)
from engines.bet_agent.models.summary import (
    Anomaly,
    AnomalySeverity,
    GlobalStatus,
    HypothesisUsed,
    Summary,
)

__all__ = [
    "UserBrief",
    "BuildingModel",
    "ElementSource",
    "Floor",
    "Wall",
    "StructuralElement",
    "Opening",
    "Stair",
    "Roof",
    "Room",
    "SlabOpening",
    "Summary",
    "Anomaly",
    "AnomalySeverity",
    "GlobalStatus",
    "HypothesisUsed",
]
