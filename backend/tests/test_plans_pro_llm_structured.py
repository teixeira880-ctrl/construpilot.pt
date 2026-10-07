"""Testes do `llm_structured.py` — zero JSON patching, mocks totais."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.ai_providers.base import AIResponse  # noqa: E402
from engines.plans_pro.semantic.exceptions import (  # noqa: E402
    SchemaValidationError,
    VisionAnalysisError,
)
from engines.plans_pro.semantic.llm_structured import (  # noqa: E402
    _parse_strict,
    _schema_openai_strict,
    analisar_com_structured_output,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "plans_pro"


def _mock_ai_response(text: str) -> AIResponse:
    return AIResponse(text=text, provider="openai", model="gpt-4o")


class TestParseStrict:
    def test_resposta_valida_devolve_pydantic(self):
        raw = (FIX / "vision_response_coerente.json").read_text(encoding="utf-8")
        analise = _parse_strict(raw)
        assert analise.plan_id == "pln_test_coer"
        assert len(analise.elementos) == 2

    def test_json_invalido_levanta_schema_error(self):
        with pytest.raises(SchemaValidationError):
            _parse_strict("{isto não é json")

    def test_json_malformado_pydantic_levanta_schema_error(self):
        """O fixture `malformado.json` tem campo extra `campo_inventado`
        + campo raiz `foo_extra` + falta imensa de campos obrigatórios.
        Com `extra='forbid'` + `strict=True` → rejeita (NÃO patch)."""
        raw = (FIX / "vision_response_malformado.json").read_text(encoding="utf-8")
        with pytest.raises(SchemaValidationError):
            _parse_strict(raw)

    def test_json_que_nao_e_dict_levanta_schema_error(self):
        with pytest.raises(SchemaValidationError):
            _parse_strict("[1, 2, 3]")

    def test_schema_error_preserva_raw_truncado(self):
        try:
            _parse_strict("{inválido}")
        except SchemaValidationError as e:
            assert "{inválido}" in e.raw_response
        else:  # pragma: no cover
            pytest.fail("Devia ter lançado SchemaValidationError")


class TestSchemaOpenAI:
    def test_schema_strict_tem_additional_properties_false(self):
        s = _schema_openai_strict()
        # Raiz
        assert s.get("additionalProperties") is False
        # Pelo menos uma referência interna tem additionalProperties:false
        defs = s.get("$defs") or s.get("definitions") or {}
        for name, d in defs.items():
            if d.get("type") == "object" or "properties" in d:
                assert d.get("additionalProperties") is False, f"{name} sem additionalProperties:false"


@pytest.mark.anyio
class TestOrdemFallback:
    """OpenAI primeiro, Claude só se OpenAI falhar."""

    async def test_openai_valida_claude_nao_e_chamado(self):
        """Fase 1b: ordem Gemini → Claude → OpenAI. Com Gemini=None e
        Claude com resposta válida, Claude vence; OpenAI nem é chamado."""
        raw_valido = (FIX / "vision_response_coerente.json").read_text(encoding="utf-8")

        mock_openai = AsyncMock(return_value=_mock_ai_response("ignorado"))
        mock_claude = AsyncMock(return_value=_mock_ai_response(raw_valido))

        class _Prov:
            def __init__(self, fn):
                self.ask = fn

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = None
            router.openai_vision = _Prov(mock_openai)
            router.openai_coach = None
            router.claude = _Prov(mock_claude)
            analise, trace = await analisar_com_structured_output(
                plan_id="pln_test_coer",
                filename="moradia.rvt",
                metadata={"quantities": {}},
                image_data_uri=None,
                project_hint=None,
            )
        assert trace["providers_used"] == "claude"
        assert mock_claude.await_count == 1
        assert mock_openai.await_count == 0
        assert analise.plan_id == "pln_test_coer"

    async def test_openai_malformado_cai_para_claude(self):
        raw_valido = (FIX / "vision_response_coerente.json").read_text(encoding="utf-8")
        raw_mal = (FIX / "vision_response_malformado.json").read_text(encoding="utf-8")

        mock_openai = AsyncMock(return_value=_mock_ai_response(raw_mal))
        mock_claude = AsyncMock(return_value=_mock_ai_response(raw_valido))

        class _Prov:
            def __init__(self, fn):
                self.ask = fn

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = None
            router.openai_vision = _Prov(mock_openai)
            router.openai_coach = None
            router.claude = _Prov(mock_claude)
            analise, trace = await analisar_com_structured_output(
                plan_id="pln_test_coer",
                filename="moradia.rvt",
                metadata={"quantities": {}},
                image_data_uri=None,
                project_hint=None,
            )
        # Nota Fase 1b: ordem agora é Gemini → Claude → OpenAI. Com
        # Gemini=None, Claude responde primeiro (válido) e vence.
        assert trace["providers_used"] == "claude"
        assert mock_claude.await_count == 1
        # OpenAI não foi preciso porque Claude já respondeu bem
        assert mock_openai.await_count == 0

    async def test_ambos_malformados_levantam_schema_error(self):
        raw_mal = (FIX / "vision_response_malformado.json").read_text(encoding="utf-8")

        mock_openai = AsyncMock(return_value=_mock_ai_response(raw_mal))
        mock_claude = AsyncMock(return_value=_mock_ai_response(raw_mal))

        class _Prov:
            def __init__(self, fn):
                self.ask = fn

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = None
            router.openai_vision = _Prov(mock_openai)
            router.openai_coach = None
            router.claude = _Prov(mock_claude)
            with pytest.raises(SchemaValidationError):
                await analisar_com_structured_output(
                    plan_id="x",
                    filename="x.rvt",
                    metadata={"quantities": {}},
                    image_data_uri=None,
                    project_hint=None,
                )

    async def test_sem_providers_levanta_vision_error(self):
        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = None
            router.openai_vision = None
            router.openai_coach = None
            router.claude = None
            with pytest.raises(VisionAnalysisError):
                await analisar_com_structured_output(
                    plan_id="x",
                    filename="x.rvt",
                    metadata={"quantities": {}},
                    image_data_uri=None,
                    project_hint=None,
                )
