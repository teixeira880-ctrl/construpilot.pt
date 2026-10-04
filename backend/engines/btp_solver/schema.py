"""Esquemas de saída do solver BTP · versão PT.

Um problema BTP é decomposto em:
  - diagnóstico (causas prováveis ordenadas por confiança)
  - soluções (opções técnicas + custo estimado + duração + risco)
  - cálculos / resultados numéricos → serializáveis em gráficos
  - referências (RGEU, RJUE, Eurocódigos, NP EN, LNEC, artigos legais)
  - plano de ação (passos, materiais, segurança)

Mantém o schema do FR por compatibilidade. Preços em EUR, mercado PT 2026.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Confidence = Literal["low", "medium", "high"]
Risk = Literal["low", "medium", "high", "critical"]
Urgency = Literal["informative", "planned", "urgent", "immediate"]


class Cause(BaseModel):
    label: str
    confidence: Confidence
    explanation: str
    indicators_matched: list[str] = Field(default_factory=list)


class Reference(BaseModel):
    """Um texto normativo PT, Eurocódigo ou fonte web."""
    kind: Literal["rgeu", "rjue", "ec", "np_en", "lnec", "dl", "web", "cctp"]
    code: str = Field(..., description="Ex: 'RGEU art. 65º', 'EN 1992-1-1', 'NP EN 206', 'DL 101-D/2020'")
    title: str | None = None
    url: str | None = None


class SolutionStep(BaseModel):
    order: int
    text: str
    duration_hours: float | None = None
    materials: list[str] = Field(default_factory=list)
    biblioteca_pt_ref: str | None = Field(
        None,
        description="Chave do item na Biblioteca PT 2026 (quando aplicável, ex: 'ALV_TIJ_11').",
    )


class Solution(BaseModel):
    id: str
    label: str
    description: str
    # Chiffrages provisionais — devolvidos mesmo que aproximados.
    cost_min_eur: float | None = None
    cost_max_eur: float | None = None
    duration_days_min: float | None = None
    duration_days_max: float | None = None
    risk: Risk = "medium"
    warranty_years: int | None = None
    steps: list[SolutionStep] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    recommended: bool = False


class ChartSeries(BaseModel):
    """Série numérica pronta a desenhar (Recharts)."""
    name: str
    data: list[float]


class Chart(BaseModel):
    """Representação gráfica associada à solução ou ao diagnóstico."""
    id: str
    type: Literal["bar", "line", "pie", "radar", "gauge", "comparison"]
    title: str
    x_labels: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    unit: str | None = None
    caption: str | None = None


class SolverResponse(BaseModel):
    """Resposta completa do solver."""
    problem_id: str
    domain: str = Field(..., description="fissuras | humidade | termico | estrutura | sinistro | recepcao | outro")
    urgency: Urgency = "planned"
    summary: str = Field(..., description="Resumo do diagnóstico em 3-5 linhas")
    causes: list[Cause]
    solutions: list[Solution]
    charts: list[Chart] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    action_plan: list[SolutionStep] = Field(default_factory=list)
    disclaimer: str = (
        "Diagnóstico provisório baseado nos elementos fornecidos. "
        "Uma visita técnica e o parecer de um engenheiro ou arquiteto inscrito "
        "na respetiva Ordem continuam a ser necessários antes de qualquer "
        "intervenção estrutural. Preços indicativos para o mercado de Portugal "
        "continental em 2026, IVA 23 % não incluído."
    )
    generated_at_iso: str
    cost_usd: float | None = None
    model_used: str | None = None
    web_enriched: bool = False
