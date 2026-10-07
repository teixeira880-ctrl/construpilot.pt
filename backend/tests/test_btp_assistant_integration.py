"""Testes de integração REAIS (opt-in via `-m integration`) para o Assistente BTP.

Executam chamadas Gemini reais com a `GEMINI_API_KEY` do ambiente.
Skippam se chave ausente. Nunca em CI por defeito — use:

    pytest -m integration tests/test_btp_assistant_integration.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.btp_assistant.router import route_user_request_sync  # noqa: E402


pytestmark = pytest.mark.integration


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
        yield mdb


@pytest.mark.anyio
async def test_conversa_real_dosagem_c25_30(mock_db):
    """Modo CONVERSA: pergunta técnica → resposta Markdown PT-PT."""
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY ausente.")
    r = await route_user_request_sync(
        user_prompt="Em PT-PT, dosagem padrão de betão C25/30 por m³. Curto.",
        user_id="u_integration",
    )
    assert r.mode == "conversa"
    assert r.text_pt
    # Resposta deve mencionar algum dos termos técnicos esperados
    assert any(k in r.text_pt.lower() for k in ("c25/30", "cimento", "kg", "areia"))
    assert r.trace["events_count"] > 2


@pytest.mark.anyio
async def test_calculo_real_criar_orcamento(mock_db):
    """Modo CÁLCULO: pedido → function_call `criar_orcamento` pendente de confirmação."""
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY ausente.")
    r = await route_user_request_sync(
        user_prompt=(
            "Cria um orçamento de teste para o cliente 'Silva Teste' "
            "com UM item: 'Betão C25/30', 10 m³, a 120 EUR/m³. "
            "Título: 'Fundações Teste'."
        ),
        user_id="u_integration",
    )
    assert r.mode == "calculo"
    nomes = [tc.name for tc in r.tool_calls]
    assert "criar_orcamento" in nomes, (
        f"Esperava criar_orcamento, tool_calls={nomes}, texto='{r.text_pt[:200]}'"
    )
    # Confirmação pendente (write-tool)
    tr = [x for x in r.tool_results if x.status == "needs_user_confirmation"]
    assert tr, "Deveria pedir confirmação do utilizador"


@pytest.mark.anyio
async def test_calculo_real_abrir_app(mock_db):
    """Modo CÁLCULO: 'abre o módulo' → function_call `abrir_app`."""
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY ausente.")
    r = await route_user_request_sync(
        user_prompt="Abre-me o módulo de orçamentos agora.",
        user_id="u_integration",
    )
    assert r.mode == "calculo"
    nomes = [tc.name for tc in r.tool_calls]
    assert "abrir_app" in nomes, f"tool_calls={nomes}"
    tr = next(x for x in r.tool_results if x.tool_call_id == r.tool_calls[0].id)
    assert tr.status == "ok"
    assert tr.payload.get("url") in ("/devis", "/plans-pro", "/calculadoras",
                                      "/precos", "/estimador", "/biblioteca",
                                      "/calculadoras/escadas")
