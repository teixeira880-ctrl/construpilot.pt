"""Testes dos schemas das 11 Function Declarations (PT-PT, campos obrigatórios)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.btp_assistant.tools.registry import (  # noqa: E402
    NOMES_FERRAMENTAS_COM_CONFIRMACAO,
    TOOLS,
    TOOLS_INDEX,
)


class TestRegistryEstrutura:
    def test_tem_11_ferramentas(self):
        assert len(TOOLS) == 11

    def test_nomes_unicos(self):
        nomes = [t["name"] for t in TOOLS]
        assert len(set(nomes)) == len(nomes)

    def test_todos_com_name_description_parameters(self):
        for t in TOOLS:
            assert t.get("name"), f"ferramenta sem name: {t}"
            assert t.get("description"), f"{t['name']} sem description"
            assert isinstance(t.get("parameters"), dict), (
                f"{t['name']} sem parameters dict"
            )

    def test_descricao_em_pt_pt(self):
        """Smoke: descrições não devem ter palavras FR nem EN típicas."""
        bloqueios = ("French", "English", "s'il vous", "please", "the user")
        for t in TOOLS:
            for b in bloqueios:
                assert b.lower() not in t["description"].lower(), (
                    f"{t['name']} contém '{b}' na descrição"
                )

    def test_parameters_tem_type_object(self):
        for t in TOOLS:
            p = t["parameters"]
            assert p.get("type") == "object"
            assert "properties" in p

    def test_required_subset_de_properties(self):
        for t in TOOLS:
            p = t["parameters"]
            req = set(p.get("required") or [])
            props = set((p.get("properties") or {}).keys())
            assert req <= props, (
                f"{t['name']}: required {req - props} não existem em properties"
            )


class TestFerramentasComConfirmacao:
    def test_set_definido(self):
        assert "criar_orcamento" in NOMES_FERRAMENTAS_COM_CONFIRMACAO
        assert "exportar_excel" in NOMES_FERRAMENTAS_COM_CONFIRMACAO
        assert "adicionar_item_orcamento" in NOMES_FERRAMENTAS_COM_CONFIRMACAO

    def test_nao_contem_ferramentas_read_only(self):
        read_only = {
            "pesquisar_norma", "obter_preco_material",
            "pesquisar_biblioteca", "pedir_precisao", "abrir_app",
        }
        for name in read_only:
            assert name not in NOMES_FERRAMENTAS_COM_CONFIRMACAO, (
                f"{name} não deveria exigir confirmação"
            )


class TestFerramentasChave:
    def test_pedir_precisao_tem_criticidade(self):
        f = TOOLS_INDEX["pedir_precisao"]
        assert "criticidade" in f["parameters"]["required"]
        enum = f["parameters"]["properties"]["criticidade"]["enum"]
        assert set(enum) == {"bloqueante", "importante", "opcional"}

    def test_abrir_app_tem_enum_de_modulos(self):
        f = TOOLS_INDEX["abrir_app"]
        enum = f["parameters"]["properties"]["nome_app"]["enum"]
        assert "orcamento" in enum and "plans-pro" in enum

    def test_criar_orcamento_items_tem_estrutura(self):
        f = TOOLS_INDEX["criar_orcamento"]
        items = f["parameters"]["properties"]["items"]
        assert items["type"] == "array"
        subprops = items["items"]["properties"]
        assert {"descricao", "qtd", "unidade", "preco_unit_eur"} <= subprops.keys()

    def test_estimar_custo_tem_acabamento_enum(self):
        f = TOOLS_INDEX["estimar_custo"]
        enum = f["parameters"]["properties"]["acabamento"]["enum"]
        assert set(enum) == {"economico", "standard", "premium"}
