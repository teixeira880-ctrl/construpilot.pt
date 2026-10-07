"""Testes da integração Gemini no `plans_pro.semantic.llm_structured`.

Cobre:
    * Gemini responde válido → `providers_used="gemini"`.
    * Gemini schema inválido → cascata para Claude.
    * Gemini 401 → cascata para Claude.
    * `_schema_for_gemini` remove `additionalProperties`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.ai_providers.base import AIProviderError, AIResponse  # noqa: E402
from engines.plans_pro.semantic.exceptions import (  # noqa: E402
    SchemaValidationError,
    VisionAnalysisError,
)
from engines.plans_pro.semantic.llm_structured import (  # noqa: E402
    _schema_for_gemini,
    _strip_additional_properties,
    analisar_com_structured_output,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "plans_pro"


def _ai(text: str) -> AIResponse:
    return AIResponse(text=text, provider="gemini", model="gemini-pro-latest")


class _Prov:
    def __init__(self, mock):
        self.ask = mock


class TestSchemaForGemini:
    def test_remove_additional_properties(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "x": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"y": {"type": "integer"}},
                }
            },
        }
        out = _schema_for_gemini(schema)
        assert "additionalProperties" not in out
        assert "additionalProperties" not in out["properties"]["x"]
        # Confirma que não altera o input (deep copy)
        assert schema["additionalProperties"] is False

    def test_strip_recursivo_em_arrays(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                    },
                }
            },
        }
        _strip_additional_properties(schema)
        assert "additionalProperties" not in schema
        assert "additionalProperties" not in schema["properties"]["items"]["items"]


@pytest.mark.anyio
class TestCascadeGemini:
    async def test_gemini_ok_claude_e_openai_nao_sao_chamados(self):
        raw_valido = (FIX / "vision_response_coerente.json").read_text(encoding="utf-8")

        mock_gemini = AsyncMock(return_value=_ai(raw_valido))
        mock_claude = AsyncMock()
        mock_openai = AsyncMock()

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = _Prov(mock_gemini)
            router.claude = _Prov(mock_claude)
            router.openai_vision = _Prov(mock_openai)
            router.openai_coach = None
            analise, trace = await analisar_com_structured_output(
                plan_id="pln_test_coer",
                filename="moradia.rvt",
                metadata={"quantities": {}},
                image_data_uri=None,
                project_hint=None,
            )
        assert trace["providers_used"] == "gemini"
        assert mock_claude.await_count == 0
        assert mock_openai.await_count == 0
        assert analise.plan_id == "pln_test_coer"

    async def test_gemini_schema_invalido_cai_para_claude(self):
        raw_valido = (FIX / "vision_response_coerente.json").read_text(encoding="utf-8")
        raw_mal = (FIX / "vision_response_malformado.json").read_text(encoding="utf-8")

        mock_gemini = AsyncMock(return_value=_ai(raw_mal))
        mock_claude = AsyncMock(return_value=_ai(raw_valido))
        mock_openai = AsyncMock()

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = _Prov(mock_gemini)
            router.claude = _Prov(mock_claude)
            router.openai_vision = _Prov(mock_openai)
            router.openai_coach = None
            analise, trace = await analisar_com_structured_output(
                plan_id="pln_test_coer",
                filename="moradia.rvt",
                metadata={"quantities": {}},
                image_data_uri=None,
                project_hint=None,
            )
        assert trace["providers_used"] == "claude"
        assert mock_openai.await_count == 0
        # trace deve registar schema_error do Gemini
        assert any(err.get("provider") == "gemini"
                   for err in trace["schema_errors"])

    async def test_gemini_401_cai_para_claude(self):
        raw_valido = (FIX / "vision_response_coerente.json").read_text(encoding="utf-8")
        err_401 = AIProviderError(
            "chave bloqueada", provider="gemini",
            code="http_401", status_code=401, retriable=False,
        )

        mock_gemini = AsyncMock(side_effect=err_401)
        mock_claude = AsyncMock(return_value=_ai(raw_valido))

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = _Prov(mock_gemini)
            router.claude = _Prov(mock_claude)
            router.openai_vision = None
            router.openai_coach = None
            analise, trace = await analisar_com_structured_output(
                plan_id="pln_test_coer",
                filename="moradia.rvt",
                metadata={"quantities": {}},
                image_data_uri=None,
                project_hint=None,
            )
        assert trace["providers_used"] == "claude"
        # trace deve registar network_error do Gemini
        assert any(err.get("provider") == "gemini"
                   for err in trace["network_errors"])

    async def test_todos_falham_levanta_vision_error(self):
        err = AIProviderError("fail", provider="x", code="x", retriable=True)
        mock_fail = AsyncMock(side_effect=err)

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = _Prov(mock_fail)
            router.claude = _Prov(mock_fail)
            router.openai_vision = _Prov(mock_fail)
            router.openai_coach = None
            with pytest.raises(VisionAnalysisError):
                await analisar_com_structured_output(
                    plan_id="x",
                    filename="x.rvt",
                    metadata={"quantities": {}},
                    image_data_uri=None,
                    project_hint=None,
                )

    async def test_todos_devolvem_schema_invalido_levanta_schema_error(self):
        raw_mal = (FIX / "vision_response_malformado.json").read_text(encoding="utf-8")

        mock_mal = AsyncMock(return_value=_ai(raw_mal))

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = _Prov(mock_mal)
            router.claude = _Prov(mock_mal)
            router.openai_vision = _Prov(mock_mal)
            router.openai_coach = None
            with pytest.raises(SchemaValidationError):
                await analisar_com_structured_output(
                    plan_id="x",
                    filename="x.rvt",
                    metadata={"quantities": {}},
                    image_data_uri=None,
                    project_hint=None,
                )
