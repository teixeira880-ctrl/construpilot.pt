"""Teste S1-fix: preenchimento parcial com clarification_question.

Regressão corrigida: quando o LLM devolve `ok=false` + `clarification_question`,
`run_extractor` deve preservar `params` (preenchimento parcial) para o frontend
poder aplicar imediatamente os campos já extraídos.
"""
from __future__ import annotations

import json

import pytest

from engines.prompt_fill import base as base_mod
from engines.prompt_fill.moradia import MoradiaExtractor


@pytest.fixture
def moradia_extractor():
    return MoradiaExtractor()


@pytest.mark.asyncio
async def test_partial_params_preserved_with_clarification(monkeypatch, moradia_extractor):
    """Mesmo com ok=false e clarification_question, params parciais devem persistir."""

    async def fake_ask_text(_prompt: str) -> str:
        return json.dumps(
            {
                "ok": False,
                "params": {"tipologia": "T3", "pisos": 2, "pe_direito_m": 2.70},
                "ai_filled": ["tipologia", "pisos", "pe_direito_m"],
                "missing_fields": ["area_bruta_m2"],
                "clarification_question": "Qual é a área bruta de construção da moradia T3 (em m²)?",
            }
        )

    monkeypatch.setattr(base_mod, "_ask_text", fake_ask_text)

    result = await base_mod.run_extractor(
        moradia_extractor, "moradia T3 com 2 pisos e pé-direito 2.70"
    )

    assert result["ok"] is False
    assert "clarification_question" in result
    assert "params" in result, "params parciais devem ser preservados"
    assert result["params"]["tipologia"] == "T3"
    assert result["params"]["pisos"] == 2
    assert result["params"]["pe_direito_m"] == pytest.approx(2.70)
    # post_process foi aplicado (pisos como int, floats como float)
    assert isinstance(result["params"]["pisos"], int)
    assert isinstance(result["params"]["pe_direito_m"], float)


@pytest.mark.asyncio
async def test_ok_true_params_still_post_processed(monkeypatch, moradia_extractor):
    """Regressão: fluxo normal com ok=true continua a passar por post_process."""

    async def fake_ask_text(_prompt: str) -> str:
        return json.dumps(
            {
                "ok": True,
                "params": {
                    "tipologia": "T3",
                    "pisos": "2",
                    "pe_direito_m": "2.70",
                    "area_bruta_m2": "180",
                },
                "ai_filled": ["tipologia", "pisos", "pe_direito_m", "area_bruta_m2"],
                "defaults_used": [],
                "notes": [],
            }
        )

    monkeypatch.setattr(base_mod, "_ask_text", fake_ask_text)

    result = await base_mod.run_extractor(
        moradia_extractor, "T3 180 m2 2 pisos pe direito 2.70"
    )

    assert result["ok"] is True
    assert isinstance(result["params"]["pisos"], int)
    assert isinstance(result["params"]["area_bruta_m2"], float)


@pytest.mark.asyncio
async def test_clarification_without_params_still_valid(monkeypatch, moradia_extractor):
    """LLM pode legitimamente devolver clarification sem conseguir inferir nada."""

    async def fake_ask_text(_prompt: str) -> str:
        return json.dumps(
            {
                "ok": False,
                "clarification_question": "Pode descrever a tipologia e a área bruta?",
            }
        )

    monkeypatch.setattr(base_mod, "_ask_text", fake_ask_text)

    result = await base_mod.run_extractor(moradia_extractor, "quero construir uma casa")

    assert result["ok"] is False
    assert result["clarification_question"].startswith("Pode descrever")
    assert "params" not in result or not result.get("params")
