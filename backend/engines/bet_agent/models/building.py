"""Modelo do edifício lido pelo pipeline (BuildingModel).

Cada elemento tem obrigatoriamente:
    - `source`: {page, bbox, extraction_method}
    - `confidence`: ∈ [0, 1]
    - `user_imposed`: True se o utilizador fixou a hipótese (prioridade).

Nenhum valor estrutural é gerado pelo LLM. O LLM só preenche `source` e dados
observáveis directamente nas plantas. Dimensões/cálculos resultam de regras
determinísticas (ver `checks/` + lotes BET existentes).
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExtractionMethod(str, Enum):
    VISION = "vision"
    """LLM leu num render PNG (confiança variável, exige validação)."""

    VECTOR_TEXT = "vector_text"
    """Texto vectorial extraído do PDF (cota numérica directamente)."""

    USER = "user"
    """Imposto no `UserBrief`. Prioridade absoluta."""


class BBox(BaseModel):
    """Caixa de delimitação em coordenadas da página (origem canto superior esquerdo).
    Unidades: pontos PDF (1 pt = 1/72 inch)."""
    model_config = ConfigDict(extra="forbid")

    x1: float
    y1: float
    x2: float
    y2: float


class ElementSource(BaseModel):
    """Rastreabilidade obrigatória para cada elemento lido."""
    model_config = ConfigDict(extra="forbid")

    page: int = Field(ge=1, description="Nº da página 1-indexed.")
    bbox: BBox
    extraction_method: ExtractionMethod


class _Base(BaseModel):
    """Base comum: todo elemento rastreado tem source + confidence + flag user_imposed."""
    model_config = ConfigDict(extra="forbid")

    id: str = Field(description="ID estável do elemento (ex: 'P-R1-01', 'V-RC-L4').")
    source: ElementSource
    confidence: float = Field(ge=0.0, le=1.0)
    user_imposed: bool = False


# ---------------------------------------------------------------------------
# Elementos do edifício
# ---------------------------------------------------------------------------

class FloorKind(str, Enum):
    CAVE = "cave"
    RC = "rc"
    PISO = "piso"
    SOTAO = "sotao"
    COBERTURA = "cobertura"


class Floor(_Base):
    kind: FloorKind
    level_m: float = Field(description="Cota de pavimento em metros, lida ou imposta.")
    height_clear_m: Optional[float] = Field(default=None, description="Pé-direito livre em metros.")
    habitable: Optional[bool] = Field(default=None, description="Para sótão/cave: habitável ou não (critério determinístico).")


class WallKind(str, Enum):
    EXTERIOR = "exterior"
    INTERIOR = "interior"
    CONTENCAO = "contencao"
    EMPENA = "empena"


class Wall(_Base):
    floor_id: str
    kind: WallKind
    length_m: float = Field(gt=0)
    thickness_m: float = Field(gt=0)
    material_hint: Optional[str] = Field(default=None, description="Tag solta observada no projecto (ex: 'tijolo furado 15').")


class StructuralKind(str, Enum):
    PILAR = "pilar"
    VIGA = "viga"
    LAJE = "laje"
    SAPATA = "sapata"
    VIGA_FUNDACAO = "viga_fundacao"
    PAREDE_CAVE = "parede_cave"


class StructuralElement(_Base):
    floor_id: str
    kind: StructuralKind
    width_mm: Optional[int] = Field(default=None, ge=0)
    height_mm: Optional[int] = Field(default=None, ge=0)
    length_m: Optional[float] = Field(default=None, ge=0)
    thickness_mm: Optional[int] = Field(default=None, ge=0, description="Para laje/parede/sapata.")
    span_m: Optional[float] = Field(default=None, ge=0, description="Para viga/laje.")


class OpeningKind(str, Enum):
    PORTA = "porta"
    JANELA = "janela"
    PORTAO_GARAGEM = "portao_garagem"
    VARANDA = "varanda"


class Opening(_Base):
    wall_id: str
    kind: OpeningKind
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    sill_height_m: Optional[float] = Field(default=None, ge=0)


class Stair(_Base):
    floor_from_id: str
    floor_to_id: str
    opening_length_m: float = Field(gt=0, description="Comprimento disponível na laje para a escada.")
    opening_width_m: float = Field(gt=0, description="Largura disponível na laje para a escada.")
    riser_count: Optional[int] = Field(default=None, ge=1)
    riser_height_m: Optional[float] = Field(default=None, gt=0)
    tread_depth_m: Optional[float] = Field(default=None, gt=0)


class SlabOpening(_Base):
    """Aberturas na laje (caixa de escadas, elevador, patim)."""
    floor_id: str
    length_m: float = Field(gt=0)
    width_m: float = Field(gt=0)
    purpose: str = Field(description="'escada', 'elevador', 'tecnico', ...")


class RoofKind(str, Enum):
    INCLINADA_TELHA_CERAMICA = "inclinada_telha_ceramica"
    INCLINADA_CHAPA = "inclinada_chapa"
    PLANA_ACESSIVEL = "plana_acessivel"
    PLANA_NAO_ACESSIVEL = "plana_nao_acessivel"


class Roof(_Base):
    kind: RoofKind
    slope_pct: Optional[float] = Field(default=None, ge=0, le=100)
    area_m2: Optional[float] = Field(default=None, gt=0)
    overhang_m: Optional[float] = Field(default=None, ge=0)


class Room(_Base):
    floor_id: str
    name: str = Field(description="Rótulo lido (ex: 'Sala', 'Quarto 1').")
    use_hint: Optional[str] = Field(default=None, description="Pode ser preenchido via UserBrief.room_uses.")
    area_m2: float = Field(gt=0)
    min_clear_height_m: Optional[float] = Field(default=None, gt=0)
    has_window: Optional[bool] = None


# ---------------------------------------------------------------------------
# Redes técnicas (águas / esgotos / pluviais / electricidade / telecom)
# ---------------------------------------------------------------------------

class NetworkKind(str, Enum):
    AGUAS = "aguas"
    ESGOTOS_DOMESTICOS = "esgotos_domesticos"
    AGUAS_PLUVIAIS = "aguas_pluviais"
    ELECTRICIDADE = "electricidade"
    TELECOM_ITED = "telecom_ited"


class NetworkElement(_Base):
    """Marcador leve de que uma rede foi vista nos projectos de especialidade.
    Não é cálculo — só rastreio de presença para dar nos entregáveis separados.
    """
    network: NetworkKind
    floor_id: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Edifício completo
# ---------------------------------------------------------------------------

class SitePlan(BaseModel):
    """Dados do terreno/situação (lidos no estudo geotécnico + plantas)."""
    model_config = ConfigDict(extra="forbid")

    water_table_depth_m: Optional[float] = Field(default=None, ge=0)
    admissible_stress_kpa: Optional[float] = Field(default=None, ge=0)
    foundation_level_m: Optional[float] = Field(default=None)
    soil_class: Optional[str] = Field(default=None, description="Classe de solo NP EN 1998-1 (A..E).")
    seismic_zone: Optional[str] = Field(default=None)
    source: Optional[ElementSource] = None


# Campos para RTIEBT / DR 23/95 — presentes em L1 mas vazios/flagged.
# O cálculo real virá em L2/L3.
class ElectricalBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Decisão 5 do fundador: campos presentes, vazios, flagged em L1.
    rtiebt_scope_present: bool = False
    dr_23_95_scope_present: bool = False
    needs_future_computation: bool = True
    notes: Optional[str] = None


class BuildingModel(BaseModel):
    """Modelo central lido pelo pipeline. Serializável para JSON/DB."""
    model_config = ConfigDict(extra="forbid")

    project_id: str
    floors: list[Floor] = Field(default_factory=list)
    walls: list[Wall] = Field(default_factory=list)
    structural_elements: list[StructuralElement] = Field(default_factory=list)
    openings: list[Opening] = Field(default_factory=list)
    stairs: list[Stair] = Field(default_factory=list)
    slab_openings: list[SlabOpening] = Field(default_factory=list)
    roof: Optional[Roof] = None
    rooms: list[Room] = Field(default_factory=list)
    networks: list[NetworkElement] = Field(default_factory=list)
    site: SitePlan = Field(default_factory=SitePlan)
    electrical: ElectricalBrief = Field(default_factory=ElectricalBrief)
