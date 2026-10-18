"""Construção do Summary — resumo honesto do pipeline.

Regra do global_status:
    - **vermelho**: ≥1 bloqueante OU ≥4 graves OU entregável crítico em falta.
    - **amarelo**: 0 bloqueantes, ≤3 graves, maioria entregáveis produzidos.
    - **verde**: zero anomalias bloqueantes/graves + todos entregáveis pedidos
                 produzidos + custo dentro do limite.
"""
from __future__ import annotations

from engines.bet_agent.brief import hypotheses_used
from engines.bet_agent.models.brief import UserBrief
from engines.bet_agent.models.building import BuildingModel
from engines.bet_agent.models.summary import (
    Anomaly,
    AnomalySeverity,
    CostBreakdown,
    GlobalStatus,
    Summary,
)
from engines.bet_agent.registry.deliverables_pt import (
    CRITICAL_DELIVERABLES,
    DeliverableKind,
    OUT_OF_SCOPE,
)


# Entregáveis que a arquitectura considera "maioria" para decidir amarelo.
_MAJORITY_THRESHOLD: float = 0.5


def _compute_global_status(
    anomalies: list[Anomaly],
    requested: set[DeliverableKind],
    produced: set[DeliverableKind],
    cost: CostBreakdown,
) -> GlobalStatus:
    """Decide o global_status a partir das regras documentadas no R1 + L1."""
    blockers = sum(1 for a in anomalies if a.severity == AnomalySeverity.BLOQUEANTE)
    graves = sum(1 for a in anomalies if a.severity == AnomalySeverity.GRAVE)

    missing_critical = (requested - produced) & CRITICAL_DELIVERABLES

    if blockers >= 1 or graves >= 4 or missing_critical:
        return GlobalStatus.VERMELHO

    produced_ratio = (
        len(requested & produced) / len(requested) if requested else 1.0
    )

    if graves == 0 and not (requested - produced) and not cost.exceeded_limit:
        return GlobalStatus.VERDE

    # Amarelo: ainda produzimos "a maioria" e não há bloqueantes.
    if graves <= 3 and produced_ratio >= _MAJORITY_THRESHOLD:
        return GlobalStatus.AMARELO

    return GlobalStatus.VERMELHO


def build_summary(
    building: BuildingModel,
    brief: UserBrief,
    anomalies: list[Anomaly],
    cost: CostBreakdown,
    produced_deliverables: set[DeliverableKind],
) -> Summary:
    """Monta o Summary final — chamado pelo pipeline no fim de cada dossier."""
    # Ordena anomalias por severidade (bloqueante → grave → aviso) para
    # consumo UI/PDF.
    severity_order = {
        AnomalySeverity.BLOQUEANTE: 0,
        AnomalySeverity.GRAVE: 1,
        AnomalySeverity.AVISO: 2,
    }
    ordered = sorted(anomalies, key=lambda a: severity_order.get(a.severity, 3))

    status = _compute_global_status(
        anomalies=ordered,
        requested=brief.requested_deliverables,
        produced=produced_deliverables,
        cost=cost,
    )

    return Summary(
        project_id=building.project_id,
        requested_deliverables=set(brief.requested_deliverables),
        produced_deliverables=set(produced_deliverables),
        out_of_scope=set(OUT_OF_SCOPE),
        hypotheses_used=hypotheses_used(brief),
        anomalies=ordered,
        global_status=status,
        cost=cost,
    )
