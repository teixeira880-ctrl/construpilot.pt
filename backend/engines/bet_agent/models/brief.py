"""Modelo do briefing do utilizador (hipóteses impostas).

Regra dura: hipóteses do utilizador têm **sempre** prioridade sobre defaults.
Qualquer campo omitido pelo utilizador é preenchido com o default documentado
em `DEFAULT_HYPOTHESES` e flagged como `user_imposed=False` no `Summary`.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from engines.bet_agent.registry.deliverables_pt import DeliverableKind


class SlabType(str, Enum):
    ALIGEIRADA_VIGOTAS_ABOBADILHAS = "aligeirada_vigotas_abobadilhas"
    MACICA = "macica"
    FUNGIFORME = "fungiforme"
    PRE_FABRICADA = "pre_fabricada"


class MasonryType(str, Enum):
    TIJOLO_CERAMICO_FURADO_11 = "tijolo_ceramico_furado_11"
    TIJOLO_CERAMICO_FURADO_15 = "tijolo_ceramico_furado_15"
    TIJOLO_CERAMICO_FURADO_22 = "tijolo_ceramico_furado_22"
    BETAO_LEVE = "betao_leve"
    OUTRO = "outro"


class ConcreteClass(str, Enum):
    C20_25 = "C20/25"
    C25_30 = "C25/30"
    C30_37 = "C30/37"
    C35_45 = "C35/45"


class SteelClass(str, Enum):
    A400_NR = "A400 NR"
    A500_NR = "A500 NR"
    A500_ER = "A500 ER"


class RoofType(str, Enum):
    INCLINADA_TELHA_CERAMICA = "inclinada_telha_ceramica"
    INCLINADA_CHAPA = "inclinada_chapa"
    PLANA_ACESSIVEL = "plana_acessivel"
    PLANA_NAO_ACESSIVEL = "plana_nao_acessivel"


class SeismicInput(BaseModel):
    """Dados sísmicos — podem ser dados em bruto pelo utilizador OU
    resolvidos pelo brief a partir do município."""
    model_config = ConfigDict(extra="forbid")

    zone: Optional[str] = Field(default=None, description="Zona sísmica NP EN 1998-1 NA PT (ex: '1.3', '2.4').")
    soil_class: Optional[str] = Field(default=None, description="Classe de solo (A, B, C, D, E).")
    municipio: Optional[str] = Field(default=None, description="Município PT (nome tal como DGT).")
    codigo_postal: Optional[str] = Field(default=None, description="Código postal 4 dígitos (ex: '2735').")


class MaterialsBrief(BaseModel):
    """Materiais impostos pelo utilizador (prioridade absoluta)."""
    model_config = ConfigDict(extra="forbid")

    slab_type: Optional[SlabType] = None
    masonry_type: Optional[MasonryType] = None
    concrete_class: Optional[ConcreteClass] = None
    steel_class: Optional[SteelClass] = None
    roof_type: Optional[RoofType] = None


class UserBrief(BaseModel):
    """Briefing do utilizador — snapshot imutável antes de arrancar o pipeline."""
    model_config = ConfigDict(extra="forbid")

    materials: MaterialsBrief = Field(default_factory=MaterialsBrief)
    water_table_depth_m: Optional[float] = Field(
        default=None,
        description="Profundidade do nível freático em metros (positivo = abaixo do terreno).",
        ge=0,
    )
    seismic: SeismicInput = Field(default_factory=SeismicInput)
    room_uses: dict[str, str] = Field(
        default_factory=dict,
        description="Mapa compartimento_id → uso (ex: 'sala', 'quarto', 'wc', 'sotao_habitavel').",
    )
    requested_deliverables: set[DeliverableKind] = Field(
        default_factory=set,
        description="Entregáveis explicitamente pedidos pelo utilizador.",
    )
    notes: Optional[str] = Field(default=None, description="Notas livres do utilizador (max 2000 chars).", max_length=2000)

    @field_validator("requested_deliverables", mode="before")
    @classmethod
    def _coerce_deliverables(cls, v):
        if v is None:
            return set()
        if isinstance(v, set):
            return v
        return set(v)


# Defaults aplicados APENAS se o utilizador não especifica. Documentados aqui
# para que `Summary.hypotheses_used` possa indicar `user_imposed=False`.
DEFAULT_HYPOTHESES: dict[str, object] = {
    "slab_type": SlabType.ALIGEIRADA_VIGOTAS_ABOBADILHAS,
    "masonry_type": MasonryType.TIJOLO_CERAMICO_FURADO_15,
    "concrete_class": ConcreteClass.C25_30,
    "steel_class": SteelClass.A500_NR,
    "roof_type": RoofType.INCLINADA_TELHA_CERAMICA,
}
