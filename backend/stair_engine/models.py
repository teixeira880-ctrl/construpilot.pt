"""Modèles Pydantic pour input/output du moteur STAIRPILOT."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


AlertLevel = Literal["red", "orange", "green"]
StairDirection = Literal["left", "right"]
BalancingMode = Literal["straight", "balanced"]
TreadType = Literal["straight", "winder"]


class Alert(BaseModel):
    """Alerte structurée émise par le moteur."""

    model_config = ConfigDict(extra="forbid")

    level: AlertLevel
    code: str
    message: str = ""       # message FR peuplé automatiquement depuis message_fr si vide
    message_fr: str
    metric: Optional[str] = None
    value: Optional[float] = None
    threshold: Optional[float] = None
    tread_index: Optional[int] = None  # utilisé pour HEADROOM et winders

    @model_validator(mode="after")
    def _fill_message(self) -> "Alert":
        if not self.message:
            # Pydantic v2: setattr bypass frozen; ok here (not frozen)
            object.__setattr__(self, "message", self.message_fr)
        return self


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

    floor_height_mm: float = Field(..., gt=0, le=8000, description="Altura de pavimento acabado a pavimento acabado (mm)")
    available_length_mm: float = Field(..., gt=0, le=30000, description="Desenvolvimento disponível (mm)")
    available_width_mm: float = Field(..., gt=0, le=30000)
    stair_width_mm: float = Field(..., gt=0, le=5000, description="Largura de escada pretendida (mm)")
    stairwell_length_mm: Optional[float] = Field(default=None, gt=0, le=30000)
    stairwell_width_mm: Optional[float] = Field(default=None, gt=0, le=30000)
    stairwell_offset_mm: Optional[float] = Field(
        default=None,
        description=(
            "Distância horizontal do focinho do 1.º degrau ao bordo próximo da abertura do lado da subida. Se None, assume-se a abertura encostada ao topo da escada."
        ),
    )
    slab_thickness_mm: float = Field(default=200, gt=0, le=1000)
    ceiling_height_mm: Optional[float] = Field(
        default=None,
        gt=0,
        le=8000,
        description="Altura do pavimento inferior à face inferior da laje superior (mm)",
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
    num_winders: Union[int, Literal["auto"]] = "auto"
    walkline_offset_mm: float = Field(default=500, gt=0, le=2000)
    inner_radius_mm: float = Field(default=0, ge=0, le=1000)

    @field_validator("num_winders")
    @classmethod
    def _check_num_winders(cls, v):
        if isinstance(v, str):
            if v != "auto":
                raise ValueError("num_winders deve ser um int ou \'auto\'")
            return v
        if not (2 <= v <= 9):
            raise ValueError("num_winders deve estar entre 2 e 9")
        return v


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
    is_geometrically_possible: bool = True
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
