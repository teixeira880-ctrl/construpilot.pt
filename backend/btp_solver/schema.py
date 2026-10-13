"""Schémas de sortie du solveur de problèmes BTP.

Un problème BTP est décomposé en :
  - diagnostic (causes probables triées par confiance)
  - solutions (options techniques + coût estimé + délai + risque)
  - calculs / résultats numériques → sérialisables en graphiques
  - références (DTU / NF / articles Code de la construction)
  - plan d'action (étapes, matériel, sécurité)

Le solveur renvoie *toujours* le même schéma, quel que soit le domaine
(fissures, humidité, thermique, structure, sinistre, réception…).
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
    """Un texte réglementaire, DTU, NF ou source web."""
    kind: Literal["dtu", "nf", "code", "web", "cctp"]
    code: str = Field(..., description="Ex: 'DTU 20.1', 'NF EN 206', 'Art. R111-15'")
    title: str | None = None
    url: str | None = None


class SolutionStep(BaseModel):
    order: int
    text: str
    duration_hours: float | None = None
    materials: list[str] = Field(default_factory=list)


class Solution(BaseModel):
    id: str
    label: str
    description: str
    # Chiffrages provisionnels — le solveur doit les remonter même approximatifs
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
    """Série numérique prête à afficher (Recharts / Chart.js)."""
    name: str
    data: list[float]


class Chart(BaseModel):
    """Représentation graphique associée à la solution ou au diagnostic."""
    id: str
    type: Literal["bar", "line", "pie", "radar", "gauge", "comparison"]
    title: str
    x_labels: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    unit: str | None = None
    caption: str | None = None


class SolverResponse(BaseModel):
    """Réponse complète du solveur."""
    problem_id: str
    domain: str = Field(..., description="fissures | humidite | thermique | structure | sinistre | reception | autre")
    urgency: Urgency = "planned"
    summary: str = Field(..., description="Resumo do diagnóstico em 3-5 linhas")
    causes: list[Cause]
    solutions: list[Solution]
    charts: list[Chart] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    action_plan: list[SolutionStep] = Field(default_factory=list)
    disclaimer: str = (
        "Diagnóstico provisório baseado nos elementos fornecidos. Uma visita técnica e o parecer de um gabinete de projeto continuam a ser necessários antes de qualquer intervenção estrutural. Os custos são indicativos para Portugal 2026."
    )
    generated_at_iso: str
    cost_usd: float | None = None
