"""Testes de FASE 1 — normas PT e eliminação de resíduos FR no autopiloto BET."""
from __future__ import annotations

import pytest

from engines import norms_pt
from engines.structuro_autopilot import (
    IMPOSED,
    normalize_inputs,
    default_inputs,
    _lvl_name,
    _mark,
)


# ------------------------------------------------------- norms_pt
def test_norms_pt_sobrecargas():
    assert norms_pt.IMPOSED_LOADS["habitation"]["q"] == 2.0
    assert norms_pt.IMPOSED_LOADS["habitation"]["cat"] == "A"
    assert norms_pt.IMPOSED_LOADS["bureau"]["q"] == 3.0
    assert norms_pt.IMPOSED_LOADS["industriel"]["q"] == 7.5
    assert norms_pt.IMPOSED_STAIRS_HABITATION_KN_M2 == 3.0


def test_norms_pt_coeficientes_betao():
    assert norms_pt.GAMMA_C == 1.5
    assert norms_pt.GAMMA_S == 1.15
    assert norms_pt.ALPHA_CC == 0.85
    assert norms_pt.DEFAULT_CONCRETE_CLASS == "C25/30"


def test_norms_pt_psi_quadro():
    assert norms_pt.PSI_FACTORS["A"]["psi2"] == 0.3
    assert norms_pt.PSI_FACTORS["E"]["psi2"] == 0.8
    assert norms_pt.PSI_FACTORS["H"]["psi0"] == 0.0


def test_norms_pt_recobrimentos():
    assert norms_pt.COVERS_MM["XC1"] == 25
    assert norms_pt.COVERS_MM["fundacao"] == 50


def test_norms_pt_sismo_aviso():
    assert "NP EN 1998-1" in norms_pt.SEISMIC_WARNING_TEXT
    assert "projetista" in norms_pt.SEISMIC_WARNING_TEXT
    assert "zona_sismica_tipo1" in norms_pt.SEISMIC_INPUT_SCHEMA


# ------------------------------------------------------- autopilot aliases PT
@pytest.mark.parametrize("pt_alias,expected", [
    ("habitacao", "habitation"),
    ("habitação", "habitation"),
    ("escritorios", "bureau"),
    ("comercio", "commerce"),
    ("estacionamento", "parking"),
    ("industrial", "industriel"),
    ("publico", "erp"),
])
def test_normalize_inputs_aceita_alias_pt(pt_alias, expected):
    cfg = normalize_inputs({"building": {"destination": pt_alias}})
    assert cfg["building"]["destination"] == expected
    assert cfg["loads"]["floor_var_kn_m2"] == IMPOSED[expected]["q"]


def test_normalize_inputs_mantem_chave_interna():
    """Chamadas antigas em FR têm de continuar a funcionar."""
    cfg = normalize_inputs({"building": {"destination": "bureau"}})
    assert cfg["building"]["destination"] == "bureau"
    assert cfg["loads"]["floor_var_kn_m2"] == 3.0


# ------------------------------------------------------- níveis PT-PT
def test_lvl_name_pt():
    # Edifício R/C + 1
    assert _lvl_name(0, 2) == "Cobertura"
    assert _lvl_name(1, 2) == "R/C"
    # Edifício R/C + 2
    assert _lvl_name(0, 3) == "Cobertura"
    assert _lvl_name(1, 3) == "1.º piso"
    assert _lvl_name(2, 3) == "R/C"
    # Edifício único piso
    assert _lvl_name(0, 1) == "Laje de teto"


def test_mark_coerente_com_niveis_pt():
    assert _mark("column", "R/C") == "POT-RC"
    assert _mark("footing", "Fundações") == "SEM-FUND"
    assert _mark("column", "Cobertura") == "POT-COBERTURA"
    assert _mark("slab", "Laje de teto") == "DAL-PH"
    assert _mark("beam", "1.º piso") == "PTR-1P"


# ------------------------------------------------------- auto-pilot sem FR
def test_build_and_compute_sem_fr():
    """Executa um build mínimo e procura resíduos FR em qualquer `level`
    de elementos ou de mapa de armaduras."""
    from engines.structuro_autopilot import build_and_compute

    cfg = default_inputs()
    # 2 pisos para forçar níveis Cobertura/R/C
    cfg["building"]["levels"] = 2
    model = build_and_compute(cfg)
    FR_TERMS = ("Fondations", "Toiture", "Plancher haut", "RDC",
                "R+0", "R+1", "R+2")
    for e in model.get("elements", []):
        lvl = e.get("level", "")
        for t in FR_TERMS:
            assert t not in lvl, f"nível FR residual: {lvl!r}"
    for s in model.get("rebar_schedule", []):
        lvl = s.get("level", "")
        for t in FR_TERMS:
            assert t not in lvl, f"nível FR em rebar_schedule: {lvl!r}"
