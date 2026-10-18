"""Testes do dispatcher de tools (sem chamadas reais ao LLM)."""
from __future__ import annotations

import pytest

from engines.bet_agent.agent.tools import (
    READER_TOOLS,
    handle_tool_use,
)
from engines.bet_agent.models.building import BuildingModel


def _src(page: int = 1) -> dict:
    return {
        "page": page,
        "bbox": {"x1": 0, "y1": 0, "x2": 100, "y2": 100},
        "extraction_method": "vector_text",
    }


def test_report_floor_appends_to_building() -> None:
    bm = BuildingModel(project_id="t")
    questions: list = []
    res = handle_tool_use(
        name="report_floor",
        raw_input={
            "id": "F-R0", "kind": "rc", "level_m": 0.0,
            "height_clear_m": 2.70, "habitable": True,
            "source": _src(), "confidence": 0.95,
        },
        building=bm, pending_questions=questions,
    )
    assert res.ok is True
    assert len(bm.floors) == 1
    assert bm.floors[0].id == "F-R0"


def test_report_wall_and_opening() -> None:
    bm = BuildingModel(project_id="t")
    questions: list = []
    res_w = handle_tool_use(
        name="report_wall",
        raw_input={
            "id": "W-01", "floor_id": "F-R0", "kind": "exterior",
            "length_m": 5.0, "thickness_m": 0.22,
            "source": _src(), "confidence": 0.9,
        },
        building=bm, pending_questions=questions,
    )
    assert res_w.ok
    res_o = handle_tool_use(
        name="report_opening",
        raw_input={
            "id": "O-01", "wall_id": "W-01", "kind": "porta",
            "width_m": 0.9, "height_m": 2.1,
            "source": _src(), "confidence": 0.9,
        },
        building=bm, pending_questions=questions,
    )
    assert res_o.ok
    assert len(bm.walls) == 1 and len(bm.openings) == 1


def test_invalid_payload_returns_validation_failed() -> None:
    bm = BuildingModel(project_id="t")
    res = handle_tool_use(
        name="report_wall",
        raw_input={"id": "W-bad", "length_m": -1.0},  # payload incompleto
        building=bm, pending_questions=[],
    )
    assert res.ok is False
    assert "validation_failed" in res.tool_result_payload


def test_ask_user_records_question_and_signals_blocking() -> None:
    bm = BuildingModel(project_id="t")
    questions: list = []
    res = handle_tool_use(
        name="ask_user",
        raw_input={
            "question_pt": "Qual é a cota do sótão?",
            "page": 3,
            "bbox": {"x1": 10, "y1": 10, "x2": 100, "y2": 100},
            "severity": "bloqueante",
        },
        building=bm, pending_questions=questions,
    )
    assert res.ok is True
    assert res.user_question is not None
    assert len(questions) == 1


def test_zoom_request_recorded() -> None:
    bm = BuildingModel(project_id="t")
    res = handle_tool_use(
        name="request_zoom_crop",
        raw_input={
            "page": 2,
            "bbox": {"x1": 50, "y1": 50, "x2": 150, "y2": 150},
            "reason": "cota ilegível na vista reduzida",
        },
        building=bm, pending_questions=[],
    )
    assert res.ok is True
    assert res.zoom_request is not None


def test_finish_tool_signals_finish() -> None:
    bm = BuildingModel(project_id="t")
    res = handle_tool_use(
        name="finish",
        raw_input={"summary": "leitura completa, zero dúvidas"},
        building=bm, pending_questions=[],
    )
    assert res.finish_signal is True


def test_unknown_tool_returns_error() -> None:
    bm = BuildingModel(project_id="t")
    res = handle_tool_use(
        name="hallucinated_tool",
        raw_input={}, building=bm, pending_questions=[],
    )
    assert res.ok is False
    assert "unknown_tool" in res.tool_result_payload


def test_reader_tools_schema_wellformed() -> None:
    """Garante que cada tool tem name, description, input_schema com type=object."""
    names = {t["name"] for t in READER_TOOLS}
    expected = {
        "report_floor", "report_wall", "report_structural_element",
        "report_opening", "report_stair", "report_roof", "report_room",
        "report_slab_opening", "request_zoom_crop", "ask_user", "finish",
    }
    assert expected == names
    for t in READER_TOOLS:
        assert "name" in t and "description" in t
        schema = t["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema
