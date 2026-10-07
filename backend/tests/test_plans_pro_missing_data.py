"""Testes do fluxo `MissingDataRequest` — rácio aço ausente, question_pt."""
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
from engines.plans_pro.plan_vision import full_analysis  # noqa: E402
from engines.plans_pro.semantic.schemas import (  # noqa: E402
    AnalisePlanta,
    MissingDataRequest,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "plans_pro"


def _mock_ai(text: str) -> AIResponse:
    return AIResponse(text=text, provider="openai", model="gpt-4o")


class TestMissingDataFixture:
    def test_fixture_tem_racio_ausente(self):
        data = json.loads((FIX / "vision_response_missing.json").read_text(encoding="utf-8"))
        analise = AnalisePlanta.model_validate(data)
        # Confirma que a fixture modela correctamente um MissingDataRequest
        assert len(analise.missing_data) == 1
        md = analise.missing_data[0]
        assert md.field == "armadura.racio_kg_m3"
        assert md.unit == "kg/m³"
        assert md.criticidade == "bloqueante"
        # question_pt tem acentos e léxico PT-PT
        assert "rácio" in md.question_pt or "racio" in md.question_pt
        assert md.question_pt.endswith("?")

    def test_elemento_tem_racio_a_none(self):
        data = json.loads((FIX / "vision_response_missing.json").read_text(encoding="utf-8"))
        analise = AnalisePlanta.model_validate(data)
        # Confirma que o motor NÃO inventou valor para racio_kg_m3
        arm = next(e for e in analise.elementos if e.tipo == "armadura")
        assert arm.racio_kg_m3 is None


@pytest.mark.anyio
class TestFullAnalysisGeraMissingDataEmSchemaInvalido:
    """Quando o LLM devolve JSON malformado, `full_analysis` DEVE embalar
    um `MissingDataRequest` em PT-PT em vez de rebentar."""

    async def test_schema_invalido_vira_missing_data_bloqueante(self):
        raw_mal = (FIX / "vision_response_malformado.json").read_text(encoding="utf-8")

        class _Prov:
            def __init__(self, text):
                self.ask = AsyncMock(return_value=_mock_ai(text))

        with patch(
            "engines.plans_pro.semantic.llm_structured.ai_router"
        ) as router:
            router.gemini = _Prov(raw_mal)
            router.openai_vision = _Prov(raw_mal)
            router.openai_coach = None
            router.claude = _Prov(raw_mal)
            router.perplexity = None

            analise = await full_analysis(
                plan_id="pln_test_bad",
                filename="moradia.rvt",
                metadata={"quantities": {}},
                thumbnail_bytes=None,
                project_hint=None,
                include_web_norms=False,
            )

        assert len(analise.missing_data) == 1
        md = analise.missing_data[0]
        assert md.criticidade == "bloqueante"
        # Mensagem em PT-PT
        assert "falhou" in md.question_pt.lower() or "manualmente" in md.question_pt.lower()
        assert analise.requires_human_review is True
        assert analise.confidence_global == 0.0
        # NÃO inventou elementos
        assert analise.elementos == []
