"""Testes do cross-check APS ↔ Vision LLM."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.plans_pro.semantic.cross_check import (  # noqa: E402
    aplicar_warnings,
    cross_check,
)
from engines.plans_pro.semantic.schemas import AnalisePlanta  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "plans_pro"


def _load(fname: str) -> dict:
    return json.loads((FIX / fname).read_text(encoding="utf-8"))


class TestCrossCheckAberturas:
    def test_15_vs_3_janelas_dispara_erro(self):
        aps = _load("aps_metadata_moradia.json")
        vis = AnalisePlanta.model_validate(_load("vision_response_incoerente.json"))
        warnings = cross_check(aps, vis)
        janelas_erros = [
            w for w in warnings
            if w.campo == "contagem.janelas" and w.severidade == "erro"
        ]
        assert janelas_erros, "15 vs 3 janelas deveria disparar severidade='erro'"
        assert janelas_erros[0].valor_a == 15
        assert janelas_erros[0].valor_b == 3

    def test_15_vs_15_zero_warnings_de_contagem(self):
        aps = _load("aps_metadata_moradia.json")
        # Construir vision com exactamente 15 janelas + 7 portas
        elementos = []
        for i in range(15):
            elementos.append({
                "id": f"J{i}", "tipo": "abertura", "confidence": 0.9,
                "source": "llm", "warnings": [], "dimensoes": [], "material": None,
                "cota_assentamento": None, "diametro_mm": None, "racio_kg_m3": None,
                "classe_aco": None, "sub_tipo": "janela",
            })
        for i in range(7):
            elementos.append({
                "id": f"P{i}", "tipo": "abertura", "confidence": 0.9,
                "source": "llm", "warnings": [], "dimensoes": [], "material": None,
                "cota_assentamento": None, "diametro_mm": None, "racio_kg_m3": None,
                "classe_aco": None, "sub_tipo": "porta",
            })
        vis = AnalisePlanta(
            plan_id="x", elementos=elementos, missing_data=[], warnings=[],
            confidence_global=0.9, requires_human_review=False,
        )
        warnings = cross_check(aps, vis)
        contagem_warnings = [w for w in warnings if w.campo.startswith("contagem.")]
        assert contagem_warnings == []

    def test_diferenca_moderada_dispara_aviso(self):
        # 15 vs 13 → diff=2/15=0.133 → aviso (>10% e <=20%)
        aps = _load("aps_metadata_moradia.json")
        elementos = [
            {
                "id": f"J{i}", "tipo": "abertura", "confidence": 0.9,
                "source": "llm", "warnings": [], "dimensoes": [], "material": None,
                "cota_assentamento": None, "diametro_mm": None, "racio_kg_m3": None,
                "classe_aco": None, "sub_tipo": "janela",
            }
            for i in range(13)
        ]
        vis = AnalisePlanta(
            plan_id="x", elementos=elementos, missing_data=[], warnings=[],
            confidence_global=0.9, requires_human_review=False,
        )
        warnings = cross_check(aps, vis)
        avisos = [w for w in warnings
                  if w.campo == "contagem.janelas" and w.severidade == "aviso"]
        assert avisos


class TestCrossCheckMateriais:
    def test_llm_adiciona_material_ausente_de_aps(self):
        aps = _load("aps_metadata_moradia.json")  # tem C25/30, A500NR, PP, XPS
        # LLM devolve C30/37 (ausente de APS)
        vis = AnalisePlanta(
            plan_id="x",
            elementos=[
                {
                    "id": "L1", "tipo": "laje", "confidence": 0.9,
                    "source": "llm", "warnings": [], "dimensoes": [],
                    "material": {"nome": "C30/37", "categoria": "betao",
                                 "classe": "C30/37", "confidence": 0.9},
                    "cota_assentamento": None, "diametro_mm": None,
                    "racio_kg_m3": None, "classe_aco": None, "sub_tipo": None,
                }
            ],
            missing_data=[], warnings=[],
            confidence_global=0.9, requires_human_review=False,
        )
        warnings = cross_check(aps, vis)
        extras = [w for w in warnings if w.campo == "materiais.ausente_em_aps"]
        assert any(w.valor_b == "C30/37" for w in extras)
        assert all(w.severidade == "aviso" for w in extras)


class TestCrossCheckArea:
    def test_area_divergente_dispara_erro(self):
        aps = {"quantities": {}, "bbox": {"area_m2": 100.0}, "materiais": []}
        # Soma de áreas vision = 0,3 × 0,6 = 0,18 m² → diff > 15%
        vis = AnalisePlanta(
            plan_id="x",
            elementos=[
                {
                    "id": "L1", "tipo": "laje", "confidence": 0.9,
                    "source": "llm", "warnings": [],
                    "dimensoes": [
                        {"valor": 0.3, "unidade": "m", "eixo": "comprimento"},
                        {"valor": 0.6, "unidade": "m", "eixo": "largura"},
                    ],
                    "material": None, "cota_assentamento": None, "diametro_mm": None,
                    "racio_kg_m3": None, "classe_aco": None, "sub_tipo": None,
                }
            ],
            missing_data=[], warnings=[],
            confidence_global=0.9, requires_human_review=False,
        )
        warnings = cross_check(aps, vis)
        erros_area = [w for w in warnings if w.campo == "area.total_m2"]
        assert erros_area and erros_area[0].severidade == "erro"


class TestAplicarWarnings:
    def test_erro_forca_revisao_humana(self):
        aps = _load("aps_metadata_moradia.json")
        vis = AnalisePlanta.model_validate(_load("vision_response_incoerente.json"))
        warnings = cross_check(aps, vis)
        nova = aplicar_warnings(vis, warnings)
        assert nova.requires_human_review is True
        assert nova.confidence_global < vis.confidence_global

    def test_confidence_global_reduz_proporcionalmente(self):
        vis = AnalisePlanta(
            plan_id="x", elementos=[], missing_data=[], warnings=[],
            confidence_global=1.0, requires_human_review=False,
        )
        from engines.plans_pro.semantic.schemas import CrossCheckWarning
        warnings = [
            CrossCheckWarning(fonte_a="a", fonte_b="b", campo="x",
                              valor_a=1, valor_b=2, severidade="aviso"),
            CrossCheckWarning(fonte_a="a", fonte_b="b", campo="y",
                              valor_a=1, valor_b=2, severidade="aviso"),
        ]
        nova = aplicar_warnings(vis, warnings)
        assert abs(nova.confidence_global - 0.9) < 1e-9
