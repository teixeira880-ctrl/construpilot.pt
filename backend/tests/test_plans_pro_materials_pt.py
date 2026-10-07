"""Testes do léxico PT-BTP (determinístico, zero LLM)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.plans_pro.semantic.materials_pt import (  # noqa: E402
    extrair_dimensao,
    reconhecer_material,
)


class TestReconhecerBetao:
    @pytest.mark.parametrize(
        "txt,esperado",
        [
            ("C12/15", "C12/15"),
            ("c25/30", "C25/30"),
            ("C 30/37", "C30/37"),
            ("C 50/60", "C50/60"),
        ],
    )
    def test_classes_oficiais(self, txt, esperado):
        m = reconhecer_material(txt)
        assert m is not None
        assert m.categoria == "betao"
        assert m.classe == esperado

    def test_classe_fora_tabela_devolve_none(self):
        assert reconhecer_material("C99/99") is None

    def test_sem_texto_devolve_none(self):
        assert reconhecer_material("") is None
        assert reconhecer_material("texto neutro") is None


class TestReconhecerAco:
    @pytest.mark.parametrize(
        "txt,esperado",
        [
            ("A400", "A400"),
            ("A500", "A500"),
            ("A500NR", "A500NR"),
            ("A500ER", "A500ER"),
            ("B500A", "B500A"),
            ("B500B", "B500B"),
        ],
    )
    def test_classes_aco(self, txt, esperado):
        m = reconhecer_material(txt)
        assert m is not None
        assert m.categoria == "aco"
        assert m.classe == esperado


class TestReconhecerVarao:
    @pytest.mark.parametrize(
        "txt,diam",
        [
            ("∅12", 12),
            ("Ø 10", 10),
            ("fi 16", 16),
            ("phi 20", 20),
            ("varão 8", 8),
            ("D16", 16),
            ("∅25 mm", 25),
        ],
    )
    def test_varoes(self, txt, diam):
        m = reconhecer_material(txt)
        assert m is not None
        assert m.categoria == "aco"
        assert m.nome == f"∅{diam}"


class TestReconhecerAlvenaria:
    @pytest.mark.parametrize(
        "txt,token",
        [
            ("PP", "PP"),
            ("BA", "BA"),
            ("BB", "BB"),
            ("TJ 15", "TJ 15"),
            ("TJ15", "TJ15"),
            ("BLOCO 20", "BLOCO 20"),
            ("BLOCO TÉRMICO", "BLOCO TÉRMICO"),
            ("TIJOLO", "TIJOLO"),
        ],
    )
    def test_alvenaria(self, txt, token):
        m = reconhecer_material(txt)
        assert m is not None
        assert m.categoria == "alvenaria"


class TestReconhecerIsolamento:
    @pytest.mark.parametrize("txt", ["XPS", "EPS", "MW", "lã mineral"])
    def test_isolamento(self, txt):
        m = reconhecer_material(txt)
        assert m is not None
        assert m.categoria == "isolamento"


class TestExtrairDimensao:
    def test_produto_metros(self):
        ds = extrair_dimensao("0,30x0,60 m")
        eixos = sorted(d.eixo for d in ds)
        assert "comprimento" in eixos and "largura" in eixos
        valores = sorted(d.valor for d in ds)
        assert valores == [0.3, 0.6]
        assert all(d.unidade == "m" for d in ds)

    def test_produto_cm(self):
        ds = extrair_dimensao("30 x 60 cm")
        assert all(d.unidade == "cm" for d in ds)
        assert sorted(d.valor for d in ds) == [30.0, 60.0]

    def test_espessura_cm(self):
        ds = extrair_dimensao("e=20 cm")
        assert len(ds) == 1
        assert ds[0].eixo == "espessura"
        assert ds[0].unidade == "cm"
        assert ds[0].valor == 20.0

    def test_espessura_sem_unidade(self):
        ds = extrair_dimensao("e=4")
        assert len(ds) == 1
        assert ds[0].eixo == "espessura"
        assert ds[0].unidade == "cm"
        assert ds[0].valor == 4.0

    def test_altura(self):
        ds = extrair_dimensao("h=2,80 m")
        assert any(d.eixo == "altura" and d.valor == 2.8 for d in ds)

    def test_dimensao_simples_mm(self):
        ds = extrair_dimensao("2500 mm")
        assert len(ds) == 1
        assert ds[0].valor == 2500.0
        assert ds[0].unidade == "mm"

    def test_vazio_devolve_lista_vazia(self):
        assert extrair_dimensao("") == []
        assert extrair_dimensao("texto neutro") == []


class TestNaoInventa:
    """O léxico NUNCA deve devolver um material inventado."""

    @pytest.mark.parametrize(
        "txt",
        [
            "palavra qualquer",
            "C99/88",         # classe não oficial
            "A999",           # aço não oficial
            "∅3",             # diâmetro não standard
            "D5",             # diâmetro não standard
            "ZPS",            # isolamento inventado
            "XX e=4 cm",      # dimensão existe, material não — função só devolve material
        ],
    )
    def test_devolve_none_quando_nada_bate(self, txt):
        assert reconhecer_material(txt) is None
