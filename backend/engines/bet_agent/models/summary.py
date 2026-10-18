"""Modelo do resumo honesto do pipeline (Summary + Anomaly).

Regra: o `global_status` nunca pode ser `verde` se existir anomalia bloqueante
ou grave, nem se um entregável crítico estiver em falta.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from engines.bet_agent.models.building import BBox
from engines.bet_agent.registry.deliverables_pt import (
    CRITICAL_DELIVERABLES,
    DeliverableKind,
)


class AnomalySeverity(str, Enum):
    BLOQUEANTE = "bloqueante"
    GRAVE = "grave"
    AVISO = "aviso"


class GlobalStatus(str, Enum):
    VERDE = "verde"
    AMARELO = "amarelo"
    VERMELHO = "vermelho"


class AnomalySource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: Optional[int] = Field(default=None, ge=1)
    bbox: Optional[BBox] = None


class Anomaly(BaseModel):
    """Anomalia detectada por check determinístico ou pelo verificador.

    Toda a mensagem em PT-PT. Nenhuma anomalia pode ser silenciada.
    """
    model_config = ConfigDict(extra="forbid")

    severity: AnomalySeverity
    code: str = Field(description="Código estável (ex: 'GEO-001', 'SEM-003').")
    message_pt: str
    source: AnomalySource = Field(default_factory=AnomalySource)
    remediation: Optional[str] = Field(default=None, description="Sugestão de remediação em PT-PT.")


class HypothesisUsed(BaseModel):
    """Registo de cada hipótese usada no pipeline, com flag user_imposed."""
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Nome do campo (ex: 'slab_type').")
    value: str = Field(description="Representação textual do valor (ex: 'aligeirada_vigotas_abobadilhas').")
    user_imposed: bool
    default_used: bool
    source_note: Optional[str] = None


class CostBreakdown(BaseModel):
    """Metering agregado do dossier (ver cost.py)."""
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cache_read_tokens: int = Field(default=0, ge=0)
    eur_total: float = Field(default=0.0, ge=0.0)
    eur_limit: float = Field(default=10.0, ge=0.0)
    exceeded_limit: bool = False


class Summary(BaseModel):
    """Resumo honesto entregue ao painel admin e ao PDF do dossier.

    Rodapé imposto (constante): "pré-dimensionamento, a verificar e assinar
    pelo técnico responsável".
    """
    model_config = ConfigDict(extra="forbid")

    project_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    requested_deliverables: set[DeliverableKind] = Field(default_factory=set)
    produced_deliverables: set[DeliverableKind] = Field(default_factory=set)
    out_of_scope: set[str] = Field(default_factory=set)

    hypotheses_used: list[HypothesisUsed] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)
    global_status: GlobalStatus = GlobalStatus.VERMELHO

    cost: CostBreakdown = Field(default_factory=CostBreakdown)
    footer: str = "pré-dimensionamento, a verificar e assinar pelo técnico responsável"

    # ------------------------------------------------------------------
    # Lógica auxiliar
    # ------------------------------------------------------------------

    def missing_deliverables(self) -> set[DeliverableKind]:
        """Pedidos mas não produzidos."""
        return self.requested_deliverables - self.produced_deliverables

    def missing_critical(self) -> set[DeliverableKind]:
        """Entregáveis críticos pedidos mas não produzidos."""
        return self.missing_deliverables() & CRITICAL_DELIVERABLES

    def anomalies_by_severity(self, sev: AnomalySeverity) -> list[Anomaly]:
        return [a for a in self.anomalies if a.severity == sev]
