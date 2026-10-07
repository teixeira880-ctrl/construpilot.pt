"""Testes da observabilidade do Assistente BTP (Fase C)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")


def _fake_response(*, text="", function_calls=None):
    parts = []
    for name, args in function_calls or []:
        parts.append(SimpleNamespace(
            function_call=SimpleNamespace(name=name, args=args), text=None,
        ))
    if text:
        parts.append(SimpleNamespace(function_call=None, text=text))
    return SimpleNamespace(candidates=[SimpleNamespace(
        content=SimpleNamespace(parts=parts))])


async def _fake_stream_gen(texts):
    for t in texts:
        yield SimpleNamespace(text=t)


@pytest.fixture
def mock_db():
    with patch("engines.btp_assistant.router.db") as mdb, \
         patch("engines.btp_assistant.tools.executors.db") as medb:
        mdb.btp_assistant_conversations.find_one = AsyncMock(return_value=None)
        mdb.btp_assistant_conversations.update_one = AsyncMock()
        mdb.btp_assistant_metrics.insert_one = AsyncMock()
        mdb.users.find_one = AsyncMock(return_value={"plan": "pro"})
        medb.btp_assistant_orcamentos.insert_one = AsyncMock()
        medb.btp_assistant_orcamentos.find_one = AsyncMock(return_value=None)
        yield mdb


@pytest.mark.anyio
class TestMetricaEhGravada:
    async def test_turno_conversa_grava_metrica(self, mock_db):
        from engines.btp_assistant.router import route_user_request_sync
        with patch(
            "engines.btp_assistant.router.gerar_stream",
            lambda **kw: _fake_stream_gen(["Olá ", "mundo."]),
        ):
            r = await route_user_request_sync(
                user_prompt="Explica-me o RGEU", user_id="u_test",
            )
        assert r.mode == "conversa"
        mock_db.btp_assistant_metrics.insert_one.assert_called_once()
        doc = mock_db.btp_assistant_metrics.insert_one.call_args[0][0]
        # Campos obrigatórios
        for campo in (
            "conversation_id", "user_id", "user_plan", "modo", "modelo",
            "duracao_ms", "events_count", "tools_called", "status",
            "created_at", "grounding_used", "missing_data_count",
            "attachments_count",
        ):
            assert campo in doc, f"campo '{campo}' em falta"
        assert doc["modo"] == "conversa"
        assert doc["modelo"] == "gemini-flash-latest"
        assert doc["grounding_used"] is True
        assert doc["user_plan"] == "pro"
        # Zero PII — prompt NÃO deve estar
        assert "user_prompt" not in doc
        assert "text_pt" not in doc

    async def test_turno_calculo_regista_tool_calls(self, mock_db):
        from engines.btp_assistant.router import route_user_request_sync
        side = [
            _fake_response(function_calls=[("abrir_app", {"nome_app": "orcamento"})]),
            _fake_response(text="Pronto."),
        ]
        with patch(
            "engines.btp_assistant.router.gerar_com_ferramentas",
            AsyncMock(side_effect=side),
        ):
            await route_user_request_sync(
                user_prompt="Abre o módulo de orçamentos", user_id="u_test",
            )
        doc = mock_db.btp_assistant_metrics.insert_one.call_args[0][0]
        assert doc["modo"] == "calculo"
        assert "abrir_app" in doc["tools_called"]
        assert doc["grounding_used"] is False  # modo calculo não usa grounding

    async def test_erro_no_gemini_marca_status_error(self, mock_db):
        from engines.btp_assistant.router import route_user_request_sync
        with patch(
            "engines.btp_assistant.router.gerar_com_ferramentas",
            AsyncMock(side_effect=RuntimeError("boom")),
        ):
            await route_user_request_sync(
                user_prompt="Cria orçamento", user_id="u_test",
            )
        doc = mock_db.btp_assistant_metrics.insert_one.call_args[0][0]
        assert doc["status"] == "error"
