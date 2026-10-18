"""Teste de integração do Reader com mock LLM, fixture PT e checks.

Fluxo:
    1. Parse brief da fixture.
    2. Mock LLM responde com floors + walls + openings reflectindo os 5
       defeitos intencionais da fixture.
    3. `read_building` corre o loop (feature flag off → `enforce_flag=False`
       porque é CI).
    4. Checks determinísticos corridos sobre o BuildingModel.
    5. Esperamos ≥ GEO-001 (nembo negativo) + GEO-002 (vão duplicado) +
       GEO-004 (escada não cabe) + SEM-005 (térmica REH fora de âmbito).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engines.bet_agent.brief import parse_user_brief
from engines.bet_agent.checks.geometric import run_geometric_checks
from engines.bet_agent.checks.semantic import run_semantic_checks
from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.reader import read_building
from engines.bet_agent.testing_llm import MockLLMClient, ScriptedResponse, tool_use_block


def _src(page: int = 1, bbox: tuple = (0, 0, 100, 100)) -> dict:
    return {
        "page": page,
        "bbox": {"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]},
        "extraction_method": "vision",
    }


@pytest.mark.asyncio
async def test_e2e_fixture_pt_with_mock_detects_defects(tmp_path: Path) -> None:
    # 1. Fixture gerada em tmp.
    from tests.fixtures.bet_agent.generate_moradia_pt import build_fixture
    paths = build_fixture(target_dir=tmp_path)
    raw = json.loads(paths["brief"].read_text(encoding="utf-8"))
    brief = parse_user_brief(raw)

    # 2. Mock que reporta o building com os 5 defeitos.
    #    Defeitos simulados nos reports:
    #       - 2 openings PORTAO_GARAGEM na mesma parede com bbox próximos → GEO-002
    #       - 1 escada com opening_length=1.2 e floors 0.0/3.0 → GEO-004 bloqueante
    #       - 1 piso vision confidence=0.4 → SEM-003 bloqueante (sótão ambíguo)
    #    NB: nembo negativo (GEO-001) é testado directamente nos checks com
    #        model_construct (ver test_checks_geometric.py). O reader não
    #        consegue emitir length_m<=0 pelo schema Pydantic; o GEO-001 fica
    #        validado por teste unitário à parte.

    script = [
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
            "source": _src(3), "confidence": 0.4,  # vision confiança baixa → SEM-003
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
    client = MockLLMClient(script=script)
    meter = DossierMeter(project_id="fixture-pt")

    result = await read_building(
        project_id="fixture-pt",
        pdf_paths=[paths["arquitectura"], paths["geotecnico"]],
        brief=brief,
        meter=meter,
        client=client,
        enforce_flag=False,  # CI: ignora feature flag.
    )

    bm = result.building
    assert len(bm.floors) == 3
    assert len(bm.walls) == 1
    assert len(bm.openings) == 2
    assert len(bm.stairs) == 1

    # 3. Checks determinísticos.
    anoms = run_geometric_checks(bm) + run_semantic_checks(bm, brief)
    codes = {a.code for a in anoms}

    assert "GEO-002" in codes, f"vão duplicado não apanhado: {codes}"
    assert "GEO-004" in codes, f"escada mal dimensionada não apanhada: {codes}"
    assert "SEM-003" in codes, f"sótão vision baixa confiança não apanhado: {codes}"
    # SEM-005: nota do utilizador menciona térmica REH (fora de âmbito).
    assert "SEM-005" in codes, f"fora de âmbito não apanhado: {codes}"


@pytest.mark.asyncio
async def test_feature_flag_disabled_blocks_reader(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("BET_AGENT_ENABLED", raising=False)
    from engines.bet_agent.reader import ReaderDisabled
    from tests.fixtures.bet_agent.generate_moradia_pt import build_fixture
    paths = build_fixture(target_dir=tmp_path)
    brief = parse_user_brief(json.loads(paths["brief"].read_text(encoding="utf-8")))
    client = MockLLMClient(script=[])
    meter = DossierMeter(project_id="t")
    with pytest.raises(ReaderDisabled):
        await read_building(
            project_id="t",
            pdf_paths=[paths["arquitectura"]],
            brief=brief,
            meter=meter,
            client=client,
            enforce_flag=True,
        )
