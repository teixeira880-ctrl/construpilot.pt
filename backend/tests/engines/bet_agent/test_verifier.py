"""Testes do verificador independente (sessão nova, mock LLM)."""
from __future__ import annotations

import pytest

from engines.bet_agent.agent.verifier import run_verifier
from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.models.building import BuildingModel
from engines.bet_agent.models.summary import AnomalySeverity
from engines.bet_agent.testing_llm import MockLLMClient, ScriptedResponse, tool_use_block


@pytest.mark.asyncio
async def test_verifier_records_additional_anomaly() -> None:
    client = MockLLMClient(script=[
        ScriptedResponse(content=[
            tool_use_block("1", "report_anomaly", {
                "code": "VER-001",
                "severity": "grave",
                "message_pt": "A viga V-01 parece sobre-dimensionada para o vão.",
                "remediation": "Verificar cálculo EC2.",
                "page": 2,
            }),
        ]),
        ScriptedResponse(content=[
            tool_use_block("2", "finish_verification", {"summary": "ok"}),
        ]),
    ])
    meter = DossierMeter(project_id="t")
    building = BuildingModel(project_id="t")
    result = await run_verifier(
        client=client, building=building, existing_anomalies=[], meter=meter,
    )
    assert result.finished is True
    assert len(result.additional_anomalies) == 1
    a = result.additional_anomalies[0]
    assert a.code == "VER-001"
    assert a.severity == AnomalySeverity.GRAVE
    assert a.source.page == 2


@pytest.mark.asyncio
async def test_verifier_handles_unknown_tool_safely() -> None:
    client = MockLLMClient(script=[
        ScriptedResponse(content=[
            tool_use_block("1", "weird_tool", {"x": 1}),
        ]),
        ScriptedResponse(content=[
            tool_use_block("2", "finish_verification", {"summary": "fecha"}),
        ]),
    ])
    meter = DossierMeter(project_id="t")
    result = await run_verifier(
        client=client, building=BuildingModel(project_id="t"),
        existing_anomalies=[], meter=meter,
    )
    assert result.finished is True
    assert result.additional_anomalies == []  # unknown tool não cria anomalia


@pytest.mark.asyncio
async def test_verifier_no_tool_use_exits_clean() -> None:
    client = MockLLMClient(script=[
        ScriptedResponse(stop_reason="end_turn", content=[{"type": "text", "text": "sem anomalias"}]),
    ])
    meter = DossierMeter(project_id="t")
    result = await run_verifier(
        client=client, building=BuildingModel(project_id="t"),
        existing_anomalies=[], meter=meter,
    )
    assert result.additional_anomalies == []
    assert result.finished is False
    assert result.turns_used == 1
