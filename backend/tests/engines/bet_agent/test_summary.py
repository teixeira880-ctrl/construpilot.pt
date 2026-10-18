"""Testes do Summary: global_status + delta entregáveis + fonte das hipóteses."""
from __future__ import annotations

from engines.bet_agent.brief import parse_user_brief
from engines.bet_agent.models.summary import (
    Anomaly,
    AnomalySeverity,
    AnomalySource,
    CostBreakdown,
    GlobalStatus,
)
from engines.bet_agent.registry.deliverables_pt import DeliverableKind
from engines.bet_agent.summary import build_summary
from engines.bet_agent.testing import mk_building, mk_floor


def _basic_building():
    return mk_building(floors=[mk_floor()])


def _cost(exceeded: bool = False) -> CostBreakdown:
    return CostBreakdown(eur_total=5.0 if not exceeded else 15.0, exceeded_limit=exceeded)


def test_green_when_all_requested_produced_and_no_anomalies() -> None:
    ub = parse_user_brief({"requested_deliverables": ["planta_fundacoes", "quadro_pilares"]})
    bm = _basic_building()
    summary = build_summary(
        building=bm, brief=ub, anomalies=[], cost=_cost(),
        produced_deliverables={DeliverableKind.PLANTA_FUNDACOES, DeliverableKind.QUADRO_PILARES},
    )
    assert summary.global_status == GlobalStatus.VERDE
    assert summary.missing_deliverables() == set()


def test_red_when_critical_deliverable_missing() -> None:
    ub = parse_user_brief({"requested_deliverables": [
        "planta_fundacoes",  # crítico
        "quadro_pilares",
    ]})
    summary = build_summary(
        building=_basic_building(), brief=ub, anomalies=[], cost=_cost(),
        produced_deliverables={DeliverableKind.QUADRO_PILARES},  # falta fundações!
    )
    assert summary.global_status == GlobalStatus.VERMELHO
    assert DeliverableKind.PLANTA_FUNDACOES in summary.missing_critical()


def test_red_when_blocker_anomaly() -> None:
    ub = parse_user_brief({})
    anom = Anomaly(
        severity=AnomalySeverity.BLOQUEANTE,
        code="GEO-004",
        message_pt="escada impossível",
        source=AnomalySource(),
    )
    summary = build_summary(
        building=_basic_building(), brief=ub, anomalies=[anom], cost=_cost(),
        produced_deliverables=set(),
    )
    assert summary.global_status == GlobalStatus.VERMELHO


def test_red_when_4_graves() -> None:
    ub = parse_user_brief({})
    anoms = [
        Anomaly(severity=AnomalySeverity.GRAVE, code=f"GEO-{i:03d}", message_pt="x",
                source=AnomalySource())
        for i in range(4)
    ]
    summary = build_summary(
        building=_basic_building(), brief=ub, anomalies=anoms, cost=_cost(),
        produced_deliverables=set(),
    )
    assert summary.global_status == GlobalStatus.VERMELHO


def test_yellow_when_few_graves_and_majority_produced() -> None:
    ub = parse_user_brief({"requested_deliverables": [
        "planta_fundacoes", "quadro_pilares", "mapa_armaduras", "cobertura",
    ]})
    anom = Anomaly(severity=AnomalySeverity.GRAVE, code="SEM-001", message_pt="x",
                   source=AnomalySource())
    summary = build_summary(
        building=_basic_building(), brief=ub, anomalies=[anom], cost=_cost(),
        produced_deliverables={
            DeliverableKind.PLANTA_FUNDACOES,
            DeliverableKind.QUADRO_PILARES,
            DeliverableKind.MAPA_ARMADURAS,
        },  # 3/4 ⇒ maioria
    )
    assert summary.global_status == GlobalStatus.AMARELO


def test_hypotheses_user_imposed_flagged_in_summary() -> None:
    ub = parse_user_brief({"materials": {"slab_type": "macica"}})
    summary = build_summary(
        building=_basic_building(), brief=ub, anomalies=[], cost=_cost(),
        produced_deliverables=set(),
    )
    user_slab = [h for h in summary.hypotheses_used if h.key == "slab_type"][0]
    assert user_slab.user_imposed is True


def test_footer_always_present() -> None:
    ub = parse_user_brief({})
    summary = build_summary(_basic_building(), ub, [], _cost(), set())
    assert "pré-dimensionamento" in summary.footer
    assert "técnico responsável" in summary.footer


def test_out_of_scope_always_populated() -> None:
    ub = parse_user_brief({})
    summary = build_summary(_basic_building(), ub, [], _cost(), set())
    assert "termica_reh" in summary.out_of_scope
    assert "scie" in summary.out_of_scope


def test_cost_exceeded_degrades_status() -> None:
    """Mesmo com 0 anomalias e 0 entregáveis pedidos, custo >€10 impede verde."""
    ub = parse_user_brief({})
    summary = build_summary(_basic_building(), ub, [], _cost(exceeded=True), set())
    assert summary.global_status != GlobalStatus.VERDE
