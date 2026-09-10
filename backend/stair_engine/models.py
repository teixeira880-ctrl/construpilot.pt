"""Modèles Pydantic pour input/output du moteur STAIRPILOT."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


AlertLevel = Literal["red", "orange", "green"]
StairDirection = Literal["left", "right"]
BalancingMode = Literal["straight", "balanced"]
TreadType = Literal["straight", "winder"]


class Alert(BaseModel):
    """Alerte structurée émise par le moteur."""

    model_config = ConfigDict(extra="forbid")

    level: AlertLevel
    code: str
    message_fr: str
    metric: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None
    tread_index: Optional[int] = None  # utilisé pour HEADROOM et winders


class TreadDetail(BaseModel):
    """Détail d'une marche (particulièrement utile pour QT balancé)."""

    model_config = ConfigDict(extra="forbid")

    index: int  # 1-based, marche n° 1 = première marche depuis le bas
    type: TreadType
    depth_walkline_mm: float
    depth_inner_mm: float
    depth_outer_mm: float
    angle_deg: float  # angle sous-tendu au sol (0 pour droite, 30 pour winder de 3)
    cumulative_height_mm: float  # hauteur du nez de marche depuis sol bas


class StairInput(BaseModel):
    """Input pour un escalier droit."""

    model_config = ConfigDict(extra="forbid")

    floor_height_mm: float = Field(..., gt=0, le=8000, description="Hauteur sol fini à sol fini (mm)")
    available_length_mm: float = Field(..., gt=0, le=30000, description="Reculement disponible (mm)")
    available_width_mm: float = Field(..., gt=0, le=30000)
    stair_width_mm: float = Field(..., gt=0, le=5000, description="Largeur d'escalier souhaitée (mm)")
    stairwell_length_mm: Optional[float] = Field(default=None, gt=0, le=30000)
    stairwell_width_mm: Optional[float] = Field(default=None, gt=0, le=30000)
    stairwell_offset_mm: Optional[float] = Field(
        default=None,
        description=(
            "Distance horizontale du nez de la 1ère marche au bord proche de la trémie côté montée. "
            "Si None, on suppose la trémie collée en haut de l'escalier."
        ),
    )
    slab_thickness_mm: float = Field(default=200, gt=0, le=1000)
    ceiling_height_mm: Optional[float] = Field(
        default=None,
        gt=0,
        le=8000,
        description="Hauteur du sol bas à la sous-face de la dalle haute (mm)",
    )
    tread_thickness_mm: float = 30
    has_risers: bool = True
    direction: StairDirection = "right"

    @field_validator("stair_width_mm")
    @classmethod
    def _stair_width_reasonable(cls, v: float) -> float:
        return v


class QuarterTurnBottomInput(StairInput):
    """Input pour un escalier quart tournant bas (départ tournant)."""

    balancing: BalancingMode = "balanced"

    # Mode "straight" (palier bas rectangulaire)
    landing_length_mm: Optional[float] = Field(default=None, gt=0, le=5000)
    landing_width_mm: Optional[float] = Field(default=None, gt=0, le=5000)
    steps_before_landing: int = Field(default=0, ge=0, le=10)

    # Mode "balanced" (marches balancées)
    num_winders: int = Field(default=3, ge=2, le=6)
    walkline_offset_mm: float = Field(default=500, gt=0, le=2000)
    inner_radius_mm: float = Field(default=0, ge=0, le=1000)


class StairResult(BaseModel):
    """Résultat du moteur pour tout type d'escalier."""

    model_config = ConfigDict(extra="forbid")

    stair_type: str
    num_steps: int  # nb de hauteurs (risers)
    num_treads: int  # nb de girons (marches physiques hors sol haut)
    riser_height_mm: float
    tread_depth_mm: float  # giron droit (ou giron ligne de foulée en balancé)
    blondel_value_mm: float
    slope_deg: float
    stair_run_mm: float
    stair_length_mm: float
    headroom_mm: float
    required_stairwell_mm: Dict[str, float]
    steps_per_flight: List[int]
    treads: List[TreadDetail] = Field(default_factory=list)
    alerts: List[Alert]
    is_buildable: bool
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
