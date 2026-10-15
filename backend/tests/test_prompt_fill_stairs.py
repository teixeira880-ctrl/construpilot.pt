"""Testes do extractor PT-PT para escadas. Mock total do LLM — sem rede."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from engines.prompt_fill.base import run_extractor
from engines.prompt_fill.stairs import StairsExtractor


EXTRACTOR = StairsExtractor()


async def _mocked(resposta_llm: str):
    with patch("engines.prompt_fill.base._ask_text", return_value=resposta_llm):
        return await run_extractor(
            EXTRACTOR,
            prompt="dummy",
            context={},
        )


@pytest.mark.asyncio
async def test_prompt_completo_em_u():
    resposta = json.dumps(
        {
            "ok": True,
            "params": {
                "tipo": "em_U",
                "altura_a_vencer_mm": 2700,
                "largura_mm": 900,
                "espelho_alvo_mm": 175,
                "cobertor_alvo_mm": 280,
                "material": "betao_armado",
            },
            "ai_filled": ["tipo", "altura_a_vencer_mm", "largura_mm"],
            "defaults_used": ["espelho_alvo_mm", "cobertor_alvo_mm", "material"],
            "notes": ["Valores Blondel por defeito (RGEU)."],
        },
        ensure_ascii=False,
    )
    out = await _mocked(resposta)
    assert out["ok"] is True
    assert out["params"]["tipo"] == "em_U"
    assert out["params"]["altura_a_vencer_mm"] == 2700.0
    assert out["params"]["largura_mm"] == 900.0
    assert "tipo" in out["ai_filled"]
    assert "espelho_alvo_mm" in out["defaults_used"]


@pytest.mark.asyncio
async def test_prompt_vago_devolve_clarification():
    resposta = json.dumps(
        {
            "ok": False,
            "clarification_question": "Qual é a altura entre pisos a vencer (em metros)?",
        },
        ensure_ascii=False,
    )
    out = await _mocked(resposta)
    assert out["ok"] is False
    assert "altura" in out["clarification_question"].lower()


@pytest.mark.asyncio
async def test_altura_absurda_post_process_rejeita():
    resposta = json.dumps(
        {
            "ok": True,
            "params": {
                "tipo": "reta",
                "altura_a_vencer_mm": 10000,  # 10 m, acima do limite
                "largura_mm": 900,
            },
            "ai_filled": ["tipo", "altura_a_vencer_mm", "largura_mm"],
            "defaults_used": [],
            "notes": [],
        },
        ensure_ascii=False,
    )
    out = await _mocked(resposta)
    assert out["ok"] is False
    assert "altura" in out["error"].lower()


@pytest.mark.asyncio
async def test_parser_remove_fences_json():
    bloco = (
        "```json\n"
        + json.dumps(
            {
                "ok": True,
                "params": {
                    "tipo": "helicoidal",
                    "altura_a_vencer_mm": 2800,
                    "largura_mm": 900,
                },
                "ai_filled": ["tipo", "altura_a_vencer_mm"],
                "defaults_used": ["largura_mm"],
                "notes": [],
            },
            ensure_ascii=False,
        )
        + "\n```"
    )
    out = await _mocked(bloco)
    assert out["ok"] is True
    assert out["params"]["tipo"] == "helicoidal"
    assert out["params"]["altura_a_vencer_mm"] == 2800.0


@pytest.mark.asyncio
async def test_llm_devolve_lixo_erro_graciante():
    out = await _mocked("isto não é JSON de todo")
    assert out["ok"] is False
    assert "ilegível" in out["error"].lower() or "mal formatada" in out["error"].lower()


@pytest.mark.asyncio
async def test_tipo_desconhecido_rejeitado():
    resposta = json.dumps(
        {
            "ok": True,
            "params": {
                "tipo": "ziguezague",  # fora do enum
                "altura_a_vencer_mm": 2700,
                "largura_mm": 900,
            },
            "ai_filled": ["tipo"],
            "defaults_used": [],
            "notes": [],
        },
        ensure_ascii=False,
    )
    out = await _mocked(resposta)
    assert out["ok"] is False
    assert "tipo" in out["error"].lower()
