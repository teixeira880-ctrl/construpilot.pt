"""Testes dos esquemas Pydantic — camada semântica Plans Pro Fase 1."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.plans_pro.semantic.schemas import (  # noqa: E402
    AnalisePlanta,
    Armadura,
    CrossCheckWarning,
    Dimensao,
    ElementoBase,
    Material,
    MissingDataRequest,
    Sapata,
)


class TestMaterial:
    def test_validacao_feliz(self):
        m = Material(nome="C25/30", categoria="betao", classe="C25/30", confidence=0.95)
        assert m.categoria == "betao"
        assert m.confidence == 0.95

    def test_confidence_fora_de_intervalo(self):
        with pytest.raises(ValidationError):
            Material(nome="X", categoria="betao", classe=None, confidence=1.5)

    def test_categoria_invalida(self):
        with pytest.raises(ValidationError):
            Material(nome="X", categoria="desconhecida", classe=None, confidence=0.5)

    def test_extra_forbid(self):
        with pytest.raises(ValidationError):
            Material(
                nome="X", categoria="betao", classe=None,
                confidence=0.5, campo_fantasma=1,
            )

    def test_strict_type_nao_coage(self):
        """`strict=True` → `confidence="0.9"` (str) NÃO é coagido para float."""
        with pytest.raises(ValidationError):
            Material(
                nome="X", categoria="betao", classe=None,
                confidence="0.9",  # type: ignore[arg-type]
            )


class TestDimensao:
    def test_metros(self):
        d = Dimensao(valor=2.5, unidade="m", eixo="comprimento")
        assert d.valor == 2.5

    def test_unidade_invalida(self):
        with pytest.raises(ValidationError):
            Dimensao(valor=1.0, unidade="polegadas", eixo="x")  # type: ignore[arg-type]

    def test_eixo_invalido(self):
        with pytest.raises(ValidationError):
            Dimensao(valor=1.0, unidade="m", eixo="diagonal")  # type: ignore[arg-type]


class TestElementoBase:
    def test_source_aceita_valores_oficiais(self):
        for s in ("ocr", "geometria", "aps_classification",
                  "llm", "deducao_heuristica", "cross_check"):
            e = ElementoBase(
                id="E1", tipo="sapata", confidence=0.8, source=s,  # type: ignore[arg-type]
            )
            assert e.source == s

    def test_source_invalido(self):
        with pytest.raises(ValidationError):
            ElementoBase(id="E1", tipo="sapata", confidence=0.8, source="chute")  # type: ignore[arg-type]

    def test_defaults(self):
        e = ElementoBase(id="E1", tipo="sapata", confidence=0.8, source="llm")
        assert e.warnings == []
        assert e.dimensoes == []
        assert e.material is None

    def test_subclasses_impoem_discriminador(self):
        s = Sapata(id="S1", confidence=0.9, source="aps_classification")
        assert s.tipo == "sapata"
        a = Armadura(id="A1", confidence=0.9, source="llm", classe_aco="A500NR")
        assert a.tipo == "armadura"


class TestMissingDataRequest:
    def test_feliz(self):
        q = MissingDataRequest(
            question_pt="Qual é o rácio?", field="x.y", unit="kg/m³",
            element_id="E1", suggested_default=100.0, criticidade="bloqueante",
        )
        assert q.criticidade == "bloqueante"

    def test_criticidade_invalida(self):
        with pytest.raises(ValidationError):
            MissingDataRequest(
                question_pt="?", field="x", unit=None,
                element_id=None, suggested_default=None,
                criticidade="urgente",  # type: ignore[arg-type]
            )


class TestCrossCheckWarning:
    def test_severidades(self):
        for sev in ("info", "aviso", "erro"):
            w = CrossCheckWarning(
                fonte_a="aps", fonte_b="llm", campo="x",
                valor_a=1, valor_b=2, severidade=sev,  # type: ignore[arg-type]
            )
            assert w.severidade == sev

    def test_severidade_invalida(self):
        with pytest.raises(ValidationError):
            CrossCheckWarning(
                fonte_a="a", fonte_b="b", campo="x",
                valor_a=1, valor_b=2, severidade="catastrofe",  # type: ignore[arg-type]
            )


class TestAnalisePlanta:
    def test_feliz_vazia(self):
        a = AnalisePlanta(
            plan_id="pln_1", elementos=[], missing_data=[], warnings=[],
            confidence_global=0.5, requires_human_review=False,
        )
        assert a.plan_id == "pln_1"
        assert a.trace == {}

    def test_confidence_global_fora_intervalo(self):
        with pytest.raises(ValidationError):
            AnalisePlanta(
                plan_id="x", elementos=[], missing_data=[], warnings=[],
                confidence_global=1.2, requires_human_review=False,
            )

    def test_extra_forbid_na_raiz(self):
        with pytest.raises(ValidationError):
            AnalisePlanta(
                plan_id="x", elementos=[], missing_data=[], warnings=[],
                confidence_global=0.5, requires_human_review=False,
                campo_fantasma=True,
            )
