"""Testes do loop ReAct com MockLLMClient (zero rede, zero Claude live)."""
from __future__ import annotations

import pytest

from engines.bet_agent.agent.loop import run_reader_loop
from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.testing_llm import MockLLMClient, ScriptedResponse, tool_use_block


def _src(page: int = 1) -> dict:
    return {
        "page": page,
        "bbox": {"x1": 0, "y1": 0, "x2": 100, "y2": 100},
        "extraction_method": "vector_text",
    }


@pytest.mark.asyncio
async def test_loop_processes_two_reports_and_finish() -> None:
    client = MockLLMClient(script=[
        ScriptedResponse(content=[
            tool_use_block("tu_1", "report_floor", {
                "id": "F-R0", "kind": "rc", "level_m": 0.0,
                "source": _src(), "confidence": 0.95,
            }),
        ]),
        ScriptedResponse(content=[
            tool_use_block("tu_2", "report_wall", {
                "id": "W-01", "floor_id": "F-R0", "kind": "exterior",
                "length_m": 5.0, "thickness_m": 0.22,
                "source": _src(), "confidence": 0.9,
            }),
        ]),
        ScriptedResponse(content=[
            tool_use_block("tu_3", "finish", {"summary": "leitura completa"}),
        ]),
    ])
    meter = DossierMeter(project_id="t")
    result = await run_reader_loop(
        client=client,
        system_prompt="prompt",
        initial_user_content=[{"type": "text", "text": "brief"}],
        project_id="t",
        meter=meter,
    )
    assert result.finished_via_tool is True
    assert len(result.building.floors) == 1
    assert len(result.building.walls) == 1
    assert result.turns_used == 3
    # Metering agregou alguma coisa.
    cb = meter.to_breakdown()
    assert cb.input_tokens > 0
    assert cb.output_tokens > 0


@pytest.mark.asyncio
async def test_loop_stops_on_ask_user() -> None:
    client = MockLLMClient(script=[
        ScriptedResponse(content=[
            tool_use_block("tu_1", "ask_user", {
                "question_pt": "Qual é a cota do sótão?",
                "page": 3,
                "bbox": {"x1": 10, "y1": 10, "x2": 100, "y2": 100},
                "severity": "bloqueante",
            }),
        ]),
        ScriptedResponse(content=[
            tool_use_block("tu_never", "finish", {"summary": "não deve chegar aqui"}),
        ]),
    ])
    meter = DossierMeter(project_id="t")
    result = await run_reader_loop(
        client=client,
        system_prompt="prompt",
        initial_user_content=[{"type": "text", "text": "brief"}],
        project_id="t",
        meter=meter,
    )
    assert len(result.pending_questions) == 1
    assert result.finished_via_tool is False
    # O 2º script NÃO foi chamado — loop parou no ask_user.
    assert client._index == 1


@pytest.mark.asyncio
async def test_loop_records_zoom_request_and_continues() -> None:
    client = MockLLMClient(script=[
        ScriptedResponse(content=[
            tool_use_block("tu_1", "request_zoom_crop", {
                "page": 2,
                "bbox": {"x1": 50, "y1": 50, "x2": 150, "y2": 150},
                "reason": "cota ilegível",
            }),
        ]),
        ScriptedResponse(content=[
            tool_use_block("tu_2", "finish", {"summary": "ok"}),
        ]),
    ])
    meter = DossierMeter(project_id="t")
    result = await run_reader_loop(
        client=client, system_prompt="p",
        initial_user_content=[{"type": "text", "text": "brief"}],
        project_id="t", meter=meter,
    )
    assert result.finished_via_tool is True
    assert len(result.zoom_requests) == 1
    assert result.zoom_requests[0]["reason"] == "cota ilegível"


@pytest.mark.asyncio
async def test_loop_hits_max_turns_safely() -> None:
    client = MockLLMClient(script=[])  # sempre devolve end_turn vazio

    meter = DossierMeter(project_id="t")
    result = await run_reader_loop(
        client=client, system_prompt="p",
        initial_user_content=[{"type": "text", "text": "brief"}],
        project_id="t", meter=meter, max_turns=3,
    )
    assert result.turns_used == 1  # end_turn imediato ⇒ sai no primeiro turno
    assert result.stopped_reason == "end_turn"


@pytest.mark.asyncio
async def test_loop_tools_cache_control_applied() -> None:
    """Último tool do schema deve ter cache_control ephemeral."""
    client = MockLLMClient(script=[])
    meter = DossierMeter(project_id="t")
    await run_reader_loop(
        client=client, system_prompt="p",
        initial_user_content=[{"type": "text", "text": "x"}],
        project_id="t", meter=meter,
    )
    call = client.calls_received[0]
    tools = call["tools"]
    assert tools[-1].get("cache_control") == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_loop_system_cache_control_applied() -> None:
    """System prompt deve ser enviado como lista de blocos com cache_control."""
    client = MockLLMClient(script=[])
    meter = DossierMeter(project_id="t")
    await run_reader_loop(
        client=client, system_prompt="meu system",
        initial_user_content=[{"type": "text", "text": "x"}],
        project_id="t", meter=meter,
    )
    call = client.calls_received[0]
    sys_blocks = call["system"]
    assert isinstance(sys_blocks, list)
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert sys_blocks[0]["text"] == "meu system"
