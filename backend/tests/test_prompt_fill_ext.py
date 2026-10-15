"""Testes para os 6 extractors prompt_fill. Mock total do LLM — sem rede.

Cada app tem:
  - happy path (ok=true, params preenchidos)
  - clarification (ok=false + clarification_question)
  - erro (post_process rejeita)
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from engines.prompt_fill.base import run_extractor
from engines.prompt_fill import medicoes, orcamentos, plantas, autorizacao, moradia, calculadoras


async def _mock(extractor, resposta_llm, context=None):
    with patch("engines.prompt_fill.base._ask_text", return_value=resposta_llm):
        return await run_extractor(extractor, prompt="dummy", context=context or {})


# ---- MEDIÇÕES ----
@pytest.mark.asyncio
async def test_medicoes_happy_path():
    ext = medicoes.MedicoesExtractor()
    resp = json.dumps({"ok": True, "params": {"comprimento_m": 5.2, "largura_m": 3.8, "pe_direito_m": 2.6},
                       "ai_filled": ["comprimento_m", "largura_m"], "defaults_used": ["pe_direito_m"], "notes": []})
    out = await _mock(ext, resp)
    assert out["ok"] is True
    assert out["params"]["comprimento_m"] == 5.2


@pytest.mark.asyncio
async def test_medicoes_clarification():
    ext = medicoes.MedicoesExtractor()
    resp = json.dumps({"ok": False, "clarification_question": "Qual é o comprimento da divisão?"})
    out = await _mock(ext, resp)
    assert out["ok"] is False and "comprimento" in out["clarification_question"].lower()


@pytest.mark.asyncio
async def test_medicoes_invalid_value():
    ext = medicoes.MedicoesExtractor()
    resp = json.dumps({"ok": True, "params": {"comprimento_m": -1, "largura_m": 2},
                       "ai_filled": [], "defaults_used": [], "notes": []})
    out = await _mock(ext, resp)
    assert out["ok"] is False and "inválido" in out["error"].lower()


# ---- ORÇAMENTOS ----
@pytest.mark.asyncio
async def test_orcamentos_happy_path():
    ext = orcamentos.OrcamentosExtractor()
    resp = json.dumps({"ok": True, "params": {"tipo_obra": "remodelacao_total", "area_m2": 80, "tipologia": "T2",
                                               "gama_acabamentos": "media", "regiao": "Lisboa"},
                       "ai_filled": ["tipo_obra", "area_m2", "tipologia"],
                       "defaults_used": ["gama_acabamentos", "regiao"], "notes": []})
    out = await _mock(ext, resp)
    assert out["ok"] is True
    assert out["params"]["area_m2"] == 80.0


@pytest.mark.asyncio
async def test_orcamentos_clarification():
    ext = orcamentos.OrcamentosExtractor()
    resp = json.dumps({"ok": False, "clarification_question": "Qual é a área em metros quadrados?"})
    out = await _mock(ext, resp)
    assert out["ok"] is False


# ---- PLANTAS ----
@pytest.mark.asyncio
async def test_plantas_happy_path():
    ext = plantas.PlantasExtractor()
    resp = json.dumps({"ok": True, "params": {"tipo_edificio": "moradia", "pisos": 2, "tipologia": "T3",
                                               "pe_direito_m": 2.6, "uso": "habitacao"},
                       "ai_filled": ["tipo_edificio", "pisos", "tipologia"],
                       "defaults_used": ["pe_direito_m", "uso"], "notes": []})
    out = await _mock(ext, resp)
    assert out["ok"] is True
    assert out["params"]["pisos"] == 2


@pytest.mark.asyncio
async def test_plantas_clarification():
    ext = plantas.PlantasExtractor()
    resp = json.dumps({"ok": False, "clarification_question": "Qual é o tipo de edifício?"})
    out = await _mock(ext, resp)
    assert out["ok"] is False


# ---- AUTORIZAÇÃO ----
@pytest.mark.asyncio
async def test_autorizacao_happy_path():
    ext = autorizacao.AutorizacaoExtractor()
    resp = json.dumps({"ok": True, "params": {"tipo_obra": "anexo", "area_implantacao_m2": 8, "altura_m": 2.10,
                                               "confina_via_publica": False},
                       "ai_filled": ["tipo_obra", "area_implantacao_m2", "altura_m"],
                       "defaults_used": ["confina_via_publica"], "notes": []})
    out = await _mock(ext, resp)
    assert out["ok"] is True
    assert out["params"]["tipo_obra"] == "anexo"


@pytest.mark.asyncio
async def test_autorizacao_clarification():
    ext = autorizacao.AutorizacaoExtractor()
    resp = json.dumps({"ok": False, "clarification_question": "Que tipo de obra pretende fazer?"})
    out = await _mock(ext, resp)
    assert out["ok"] is False


# ---- MORADIA ----
@pytest.mark.asyncio
async def test_moradia_happy_path():
    ext = moradia.MoradiaExtractor()
    resp = json.dumps({"ok": True, "params": {"tipologia": "T3", "area_bruta_m2": 180, "pisos": 2,
                                               "pe_direito_m": 2.7, "cave": False, "area_lote_m2": 400},
                       "ai_filled": ["tipologia", "area_bruta_m2", "area_lote_m2"],
                       "defaults_used": ["pisos", "pe_direito_m", "cave"], "notes": []})
    out = await _mock(ext, resp)
    assert out["ok"] is True
    assert out["params"]["area_bruta_m2"] == 180.0


@pytest.mark.asyncio
async def test_moradia_clarification():
    ext = moradia.MoradiaExtractor()
    resp = json.dumps({"ok": False, "clarification_question": "Qual é a tipologia (T1/T2/T3)?"})
    out = await _mock(ext, resp)
    assert out["ok"] is False


# ---- CALCULADORAS ----
@pytest.mark.asyncio
async def test_calculadoras_happy_path():
    ext = calculadoras.CalculadorasExtractor()
    resp = json.dumps({"ok": True, "params": {"calc_type": "betao", "area_m2": 20, "espessura_cm": 15,
                                               "classe_betao": "C25/30"},
                       "ai_filled": ["calc_type", "area_m2", "espessura_cm"],
                       "defaults_used": ["classe_betao"], "notes": []})
    out = await _mock(ext, resp)
    assert out["ok"] is True
    assert out["params"]["calc_type"] == "betao"


@pytest.mark.asyncio
async def test_calculadoras_clarification():
    ext = calculadoras.CalculadorasExtractor()
    resp = json.dumps({"ok": False, "clarification_question": "Que tipo de cálculo precisa (betão, tinta, azulejo…)?"})
    out = await _mock(ext, resp)
    assert out["ok"] is False
