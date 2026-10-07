"""Testes dos executores de ferramentas (chamadas reais ao BD/engines mockados)."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.btp_assistant.tools.executors import (  # noqa: E402
    exec_abrir_app,
    exec_adicionar_item_orcamento,
    exec_calcular_metrado,
    exec_criar_orcamento,
    exec_estimar_custo,
    exec_obter_preco_material,
    exec_pedir_precisao,
    exec_pesquisar_biblioteca,
    executar_tool_call,
)
from engines.btp_assistant.types import ToolCall  # noqa: E402


def _call(name: str, args: dict) -> ToolCall:
    return ToolCall(id=f"tc_{name}", name=name, arguments=args)


@pytest.mark.anyio
class TestAbrirApp:
    async def test_abrir_orcamento(self):
        r = await exec_abrir_app(_call("abrir_app", {"nome_app": "orcamento"}),
                                 user_id="u1")
        assert r.status == "ok"
        assert r.payload["url"] == "/devis"
        assert r.payload["action"] == "navigate"

    async def test_abrir_desconhecido(self):
        r = await exec_abrir_app(_call("abrir_app", {"nome_app": "foo"}),
                                 user_id="u1")
        assert r.status == "error"


@pytest.mark.anyio
class TestCriarOrcamento:
    async def test_feliz(self):
        with patch("engines.btp_assistant.tools.executors.db") as mock_db:
            mock_db.btp_assistant_orcamentos.insert_one = AsyncMock()
            r = await exec_criar_orcamento(
                _call("criar_orcamento", {
                    "cliente_nome": "Silva", "titulo": "T3 Lisboa",
                    "items": [
                        {"descricao": "Betão C25/30", "qtd": 10,
                         "unidade": "m³", "preco_unit_eur": 120.0},
                    ],
                }),
                user_id="u1",
            )
        assert r.status == "ok"
        assert "orcamento_id" in r.payload
        assert r.payload["subtotal_eur"] == 1200.0
        # IVA 23% default
        assert r.payload["iva_eur"] == 276.0
        assert r.payload["total_eur"] == 1476.0

    async def test_sem_cliente_pede_precisao(self):
        r = await exec_criar_orcamento(
            _call("criar_orcamento", {"titulo": "x", "items": [{"descricao":"a","qtd":1,"unidade":"un","preco_unit_eur":1}]}),
            user_id="u1",
        )
        assert r.status == "needs_user_input"
        assert any(md.field == "cliente_nome" for md in r.missing_data)


@pytest.mark.anyio
class TestAdicionarItemOrcamento:
    async def test_orcamento_inexistente(self):
        with patch("engines.btp_assistant.tools.executors.db") as mock_db:
            mock_db.btp_assistant_orcamentos.find_one = AsyncMock(return_value=None)
            r = await exec_adicionar_item_orcamento(
                _call("adicionar_item_orcamento", {
                    "orcamento_id": "orc_xx", "descricao": "x",
                    "qtd": 1, "unidade": "un", "preco_unit_eur": 1,
                }),
                user_id="u1",
            )
        assert r.status == "error"


@pytest.mark.anyio
class TestCalcularMetrado:
    async def test_sem_plan_id(self):
        r = await exec_calcular_metrado(
            _call("calcular_metrado", {}), user_id="u1",
        )
        assert r.status == "needs_user_input"
        assert any(md.field == "plan_id" for md in r.missing_data)

    async def test_plan_com_analise_cache(self):
        with patch("engines.btp_assistant.tools.executors.db") as mock_db:
            mock_db.plans_pro.find_one = AsyncMock(return_value={
                "plan_id": "pln_x",
                "ai_analysis": {"analise": {
                    "elementos": [{"id": "E1"}, {"id": "E2"}],
                    "confidence_global": 0.8,
                    "requires_human_review": False,
                }},
            })
            r = await exec_calcular_metrado(
                _call("calcular_metrado", {"plan_id": "pln_x"}),
                user_id="u1",
            )
        assert r.status == "ok"
        assert r.payload["elementos_count"] == 2


@pytest.mark.anyio
class TestEstimarCusto:
    async def test_sem_surface_pede_precisao(self):
        r = await exec_estimar_custo(
            _call("estimar_custo", {"tipo_projecto": "x", "surface_m2": 0}),
            user_id="u1",
        )
        assert r.status == "needs_user_input"
        assert any(md.field == "surface_m2" for md in r.missing_data)


@pytest.mark.anyio
class TestObterPrecoMaterial:
    async def test_encontra_na_biblioteca(self):
        with patch("engines.btp_assistant.tools.executors.db") as mock_db:
            mock_db.materials_pt_prices.find_one = AsyncMock(return_value={
                "nome": "Cimento CEM II 42,5",
                "preco_eur": 5.50, "unidade": "saco 25kg", "regiao": "Lisboa",
            })
            r = await exec_obter_preco_material(
                _call("obter_preco_material",
                      {"material": "cimento", "regiao_pt": "Lisboa"}),
                user_id="u1",
            )
        assert r.status == "ok"
        assert r.payload["fonte"] == "biblioteca_interna"

    async def test_nao_encontrado_sinaliza_grounding(self):
        with patch("engines.btp_assistant.tools.executors.db") as mock_db:
            mock_db.materials_pt_prices.find_one = AsyncMock(return_value=None)
            r = await exec_obter_preco_material(
                _call("obter_preco_material", {"material": "material_desconhecido"}),
                user_id="u1",
            )
        assert r.status == "ok"
        assert r.payload["fonte"] == "nao_encontrado_interno"
        assert "Google Search" in r.payload["sugestao_agente"]


@pytest.mark.anyio
class TestPedirPrecisao:
    async def test_devolve_missing_data(self):
        r = await exec_pedir_precisao(
            _call("pedir_precisao", {
                "campo": "surface_m2",
                "pergunta_pt": "Qual é a área em m²?",
                "unidade": "m²",
                "criticidade": "bloqueante",
            }),
            user_id="u1",
        )
        assert r.status == "needs_user_input"
        assert len(r.missing_data) == 1
        assert r.missing_data[0].field == "surface_m2"
        assert r.missing_data[0].criticidade == "bloqueante"


@pytest.mark.anyio
class TestDespachante:
    async def test_tool_desconhecida(self):
        r = await executar_tool_call(
            _call("ferramenta_inexistente", {}), user_id="u1",
        )
        assert r.status == "error"

    async def test_erro_no_executor_e_capturado(self):
        with patch(
            "engines.btp_assistant.tools.executors.db"
        ) as mock_db:
            mock_db.btp_assistant_orcamentos.insert_one = AsyncMock(
                side_effect=RuntimeError("mongo down"),
            )
            r = await executar_tool_call(
                _call("criar_orcamento", {
                    "cliente_nome": "x", "titulo": "y",
                    "items": [{"descricao":"a","qtd":1,"unidade":"un","preco_unit_eur":1}],
                }),
                user_id="u1",
            )
        assert r.status == "error"
