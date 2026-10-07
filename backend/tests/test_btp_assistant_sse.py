"""Testes do loop SSE com Gemini mockado (modo cálculo + function calling).

Mocks: `gerar_com_ferramentas` e `gerar_stream` ao nível do nosso
`gemini_client`. Zero chamadas HTTP reais.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.btp_assistant.router import route_user_request_sync  # noqa: E402


# ---------------------------------------------------------------------------
# Helper: constrói uma resposta Gemini SDK-like
# ---------------------------------------------------------------------------
def _fake_response(*, text: str = "", function_calls: list[tuple[str, dict]] | None = None):
    parts = []
    for name, args in function_calls or []:
        parts.append(SimpleNamespace(
            function_call=SimpleNamespace(name=name, args=args),
            text=None,
        ))
    if text:
        parts.append(SimpleNamespace(function_call=None, text=text))
    return SimpleNamespace(
        candidates=[SimpleNamespace(
            content=SimpleNamespace(parts=parts),
        )],
    )


async def _fake_stream_gen(texts):
    for t in texts:
        yield SimpleNamespace(text=t)


# ---------------------------------------------------------------------------
# Mock do MongoDB (motor_core.db)
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_db():
    with patch("engines.btp_assistant.router.db") as mdb, \
         patch("engines.btp_assistant.tools.executors.db") as medb:
        mdb.btp_assistant_conversations.find_one = AsyncMock(return_value=None)
        mdb.btp_assistant_conversations.update_one = AsyncMock()
        medb.btp_assistant_orcamentos.insert_one = AsyncMock()
        medb.btp_assistant_orcamentos.find_one = AsyncMock(return_value=None)
        medb.materials_pt_prices.find_one = AsyncMock(return_value=None)
        medb.plans_pro.find_one = AsyncMock(return_value=None)
        medb.library_pt.find = lambda *a, **k: SimpleNamespace(
            limit=lambda n: SimpleNamespace(to_list=AsyncMock(return_value=[])),
        )
        yield mdb


@pytest.mark.anyio
class TestSSEModoCalculo:
    async def test_sem_function_call_retorna_texto(self, mock_db):
        with patch(
            "engines.btp_assistant.router.gerar_com_ferramentas",
            AsyncMock(return_value=_fake_response(text="Resposta directa em PT.")),
        ):
            r = await route_user_request_sync(
                user_prompt="Cria algo (modo cálculo)", user_id="u1",
            )
        assert r.mode == "calculo"
        assert r.text_pt == "Resposta directa em PT."
        assert r.tool_calls == []

    async def test_abrir_app_executa_e_emite_tool_result(self, mock_db):
        side = [
            _fake_response(function_calls=[("abrir_app", {"nome_app": "orcamento"})]),
            _fake_response(text="A abrir o módulo de orçamentos."),
        ]
        with patch(
            "engines.btp_assistant.router.gerar_com_ferramentas",
            AsyncMock(side_effect=side),
        ):
            r = await route_user_request_sync(
                user_prompt="Abre o módulo de orçamentos", user_id="u1",
            )
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].name == "abrir_app"
        assert r.tool_results[0].status == "ok"
        assert r.tool_results[0].payload["url"] == "/devis"

    async def test_pedir_precisao_devolve_missing_data(self, mock_db):
        side = [
            _fake_response(function_calls=[(
                "pedir_precisao",
                {"campo": "surface_m2",
                 "pergunta_pt": "Qual é a área em m²?",
                 "unidade": "m²",
                 "criticidade": "bloqueante"},
            )]),
        ]
        with patch(
            "engines.btp_assistant.router.gerar_com_ferramentas",
            AsyncMock(side_effect=side),
        ):
            r = await route_user_request_sync(
                user_prompt="Faz uma estimativa", user_id="u1",
            )
        assert len(r.missing_data) == 1
        assert r.missing_data[0].field == "surface_m2"
        assert r.missing_data[0].criticidade == "bloqueante"
        # question_pt é PT-PT
        assert "área" in r.missing_data[0].question_pt.lower() or "m²" in r.missing_data[0].question_pt

    async def test_criar_orcamento_pede_confirmacao(self, mock_db):
        side = [
            _fake_response(function_calls=[(
                "criar_orcamento",
                {"cliente_nome": "Silva", "titulo": "T3",
                 "items": [{"descricao":"X","qtd":1,"unidade":"un","preco_unit_eur":100}]},
            )]),
        ]
        with patch(
            "engines.btp_assistant.router.gerar_com_ferramentas",
            AsyncMock(side_effect=side),
        ):
            r = await route_user_request_sync(
                user_prompt="Cria um orçamento para o Silva", user_id="u1",
            )
        assert len(r.tool_calls) == 1
        assert r.tool_calls[0].requires_user_confirmation is True
        assert r.tool_results[0].status == "needs_user_confirmation"


@pytest.mark.anyio
class TestSSEModoConversa:
    async def test_streaming_concatena_chunks(self, mock_db):
        with patch(
            "engines.btp_assistant.router.gerar_stream",
            lambda **kw: _fake_stream_gen(["Olá ", "mundo ", "em PT."]),
        ):
            r = await route_user_request_sync(
                user_prompt="Explica-me RGEU",  # cai em 'conversa'
                user_id="u1",
            )
        assert r.mode == "conversa"
        assert r.text_pt == "Olá mundo em PT."
        assert r.trace["events_count"] >= 4  # thinking + 3 chunks + final
