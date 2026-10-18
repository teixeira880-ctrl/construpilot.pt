"""Pipeline completo do BET-PT Agent.

Compõe:
    1. Parse brief → UserBrief
    2. Reader (Opus 5.5) → BuildingModel + pending_questions
    3. Checks determinísticos (geometric + semantic)
    4. Verificador (Opus 5.5 sessão nova) → anomalias adicionais
    5. Summary honesto → global_status + custo + rodapé obrigatório

Retorna um dict serializável para o endpoint admin.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engines.bet_agent.agent.loop import AsyncLLMClient
from engines.bet_agent.agent.verifier import run_verifier
from engines.bet_agent.brief import parse_user_brief
from engines.bet_agent.checks.geometric import run_geometric_checks
from engines.bet_agent.checks.semantic import run_semantic_checks
from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.models.brief import UserBrief
from engines.bet_agent.models.summary import Anomaly, Summary
from engines.bet_agent.reader import read_building
from engines.bet_agent.registry.deliverables_pt import DeliverableKind
from engines.bet_agent.summary import build_summary

logger = logging.getLogger(__name__)


@dataclass
class PipelineRun:
    """Snapshot completo de uma execução do pipeline (p/ UI admin + logs)."""

    project_id: str
    summary: Summary
    pending_questions: list[dict[str, Any]] = field(default_factory=list)
    zoom_requests: list[dict[str, Any]] = field(default_factory=list)
    reader_turns: int = 0
    verifier_turns: int = 0
    verifier_finished: bool = False


async def run_pipeline(
    project_id: str,
    pdf_paths: list[str | Path],
    raw_brief: dict[str, Any] | None,
    client_reader: AsyncLLMClient | None = None,
    client_verifier: AsyncLLMClient | None = None,
    meter: DossierMeter | None = None,
    reader_model: str = "claude-opus-5-5",
    verifier_model: str = "claude-opus-5-5",
    enforce_flag: bool = True,
    skip_verifier: bool = False,
    produced_deliverables: set[DeliverableKind] | None = None,
) -> PipelineRun:
    """Executa o pipeline completo.

    - `client_reader` e `client_verifier` separados — o verificador DEVE ser
      sessão nova; passar instâncias distintas é parte do contrato.
    - `enforce_flag=False` em CI.
    - `produced_deliverables` reflecte o que a camada de entregáveis
      (L2/L3) de facto gerou; em L1 fica a `set()` por omissão → qualquer
      pedido do utilizador aparece como "pedido mas não produzido".
    """
    meter = meter or DossierMeter(project_id=project_id)

    # 1. Brief
    brief: UserBrief = parse_user_brief(raw_brief or {})

    # 2. Reader
    reader_result = await read_building(
        project_id=project_id,
        pdf_paths=pdf_paths,
        brief=brief,
        meter=meter,
        client=client_reader,
        model=reader_model,
        enforce_flag=enforce_flag,
    )
    building = reader_result.building

    # 3. Checks determinísticos
    anomalies: list[Anomaly] = []
    anomalies.extend(run_geometric_checks(building))
    anomalies.extend(run_semantic_checks(building, brief))

    # 4. Verificador (opcional em CI quando mock não é fornecido)
    verifier_turns = 0
    verifier_finished = False
    if not skip_verifier and client_verifier is not None:
        vres = await run_verifier(
            client=client_verifier,
            building=building,
            existing_anomalies=anomalies,
            meter=meter,
            model=verifier_model,
        )
        anomalies.extend(vres.additional_anomalies)
        verifier_turns = vres.turns_used
        verifier_finished = vres.finished

    # 5. Summary
    cost = meter.to_breakdown()
    summary = build_summary(
        building=building,
        brief=brief,
        anomalies=anomalies,
        cost=cost,
        produced_deliverables=produced_deliverables or set(),
    )

    return PipelineRun(
        project_id=project_id,
        summary=summary,
        pending_questions=reader_result.pending_questions,
        zoom_requests=reader_result.zoom_requests,
        reader_turns=reader_result.turns_used,
        verifier_turns=verifier_turns,
        verifier_finished=verifier_finished,
    )
