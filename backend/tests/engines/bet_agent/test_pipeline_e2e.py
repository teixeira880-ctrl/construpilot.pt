"""Teste de não-regressão end-to-end: pipeline completo contra fixture PT.

Mock Reader devolve o BuildingModel com os 5 defeitos.
Mock Verificador reporta 1 anomalia adicional.
Esperamos `global_status == vermelho` com todos os defeitos listados.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.models.summary import GlobalStatus
from engines.bet_agent.pipeline import run_pipeline
from engines.bet_agent.testing_llm import MockLLMClient, ScriptedResponse, tool_use_block


def _src(page: int = 1, bbox: tuple = (0, 0, 100, 100)) -> dict:
    return {
        "page": page,
        "bbox": {"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]},
        "extraction_method": "vision",
    }


@pytest.mark.asyncio
async def test_pipeline_fixture_pt_global_status_vermelho(tmp_path: Path) -> None:
    from tests.fixtures.bet_agent.generate_moradia_pt import build_fixture
    paths = build_fixture(target_dir=tmp_path)
    raw_brief = json.loads(paths["brief"].read_text(encoding="utf-8"))

    reader_script = [
        ScriptedResponse(content=[tool_use_block("1", "report_floor", {
            "id": "F-R0", "kind": "rc", "level_m": 0.0, "height_clear_m": 2.7,
            "source": _src(1), "confidence": 0.95,
        })]),
        ScriptedResponse(content=[tool_use_block("2", "report_floor", {
            "id": "F-R1", "kind": "piso", "level_m": 3.0, "height_clear_m": 2.7,
            "source": _src(1), "confidence": 0.95,
        })]),
        ScriptedResponse(content=[tool_use_block("3", "report_floor", {
            "id": "F-S", "kind": "sotao", "level_m": 5.7,
            "height_clear_m": 1.9, "habitable": True,
            "source": _src(3), "confidence": 0.4,
        })]),
        ScriptedResponse(content=[tool_use_block("4", "report_wall", {
            "id": "W-garagem", "floor_id": "F-R0", "kind": "exterior",
            "length_m": 4.0, "thickness_m": 0.22,
            "source": _src(1, (0, 0, 400, 100)), "confidence": 0.9,
        })]),
        ScriptedResponse(content=[tool_use_block("5", "report_opening", {
            "id": "O-portao-A", "wall_id": "W-garagem", "kind": "portao_garagem",
            "width_m": 3.0, "height_m": 2.2,
            "source": _src(1, (50, 10, 150, 90)), "confidence": 0.85,
        })]),
        ScriptedResponse(content=[tool_use_block("6", "report_opening", {
            "id": "O-portao-B", "wall_id": "W-garagem", "kind": "portao_garagem",
            "width_m": 3.0, "height_m": 2.2,
            "source": _src(2, (55, 10, 155, 90)), "confidence": 0.85,
        })]),
        ScriptedResponse(content=[tool_use_block("7", "report_stair", {
            "id": "S-01", "floor_from_id": "F-R0", "floor_to_id": "F-R1",
            "opening_length_m": 1.2, "opening_width_m": 1.0,
            "source": _src(4), "confidence": 0.9,
        })]),
        ScriptedResponse(content=[tool_use_block("8", "finish", {"summary": "ok"})]),
    ]

    verifier_script = [
        ScriptedResponse(content=[tool_use_block("1", "report_anomaly", {
            "code": "VER-010",
            "severity": "grave",
            "message_pt": "Nível freático a 4m exige revisão da impermeabilização da cave.",
            "remediation": "Validar com especialista de impermeabilizações.",
        })]),
        ScriptedResponse(content=[tool_use_block("2", "finish_verification", {"summary": "ok"})]),
    ]

    meter = DossierMeter(project_id="pipeline-fixture")

    result = await run_pipeline(
        project_id="pipeline-fixture",
        pdf_paths=[paths["arquitectura"], paths["geotecnico"]],
        raw_brief=raw_brief,
        client_reader=MockLLMClient(script=reader_script),
        client_verifier=MockLLMClient(script=verifier_script),
        meter=meter,
        enforce_flag=False,
        produced_deliverables=set(),  # L1: nada produzido ainda
    )

    summary = result.summary
    assert summary.global_status == GlobalStatus.VERMELHO
    codes = {a.code for a in summary.anomalies}
    # Verifica que os defeitos essenciais foram apanhados pelo pipeline:
    assert "GEO-002" in codes
    assert "GEO-004" in codes
    assert "SEM-003" in codes
    assert "SEM-005" in codes
    # Verificador contribuiu com VER-010
    assert "VER-010" in codes

    # Entregáveis críticos pedidos mas não produzidos → aparecem como falta.
    missing_critical = summary.missing_critical()
    assert len(missing_critical) > 0

    # Rodapé obrigatório presente.
    assert "pré-dimensionamento" in summary.footer.lower()

    # Custo acumulado existe e está dentro do limite €10 (mock usa poucos tokens).
    assert summary.cost.eur_total > 0
    assert summary.cost.eur_total < 10.0
    assert summary.cost.exceeded_limit is False

    # Pipeline não gerou perguntas pendentes neste cenário.
    assert result.pending_questions == []
    assert result.verifier_finished is True


@pytest.mark.asyncio
async def test_pipeline_without_verifier_still_produces_summary(tmp_path: Path) -> None:
    from tests.fixtures.bet_agent.generate_moradia_pt import build_fixture
    paths = build_fixture(target_dir=tmp_path)
    raw_brief = json.loads(paths["brief"].read_text(encoding="utf-8"))
    reader_script = [
        ScriptedResponse(content=[tool_use_block("1", "finish", {"summary": "modelo vazio"})]),
    ]
    result = await run_pipeline(
        project_id="pipeline-nover",
        pdf_paths=[paths["arquitectura"]],
        raw_brief=raw_brief,
        client_reader=MockLLMClient(script=reader_script),
        client_verifier=None,  # Verificador ausente
        skip_verifier=True,
        enforce_flag=False,
    )
    assert result.summary is not None
    # Pedidos → não produzidos (produced_deliverables default = set()) → vermelho.
    assert result.summary.global_status == GlobalStatus.VERMELHO
