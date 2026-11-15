"""Ações NP EN 1991 (AN PT) do módulo neutro: mesmos valores que o motor CLT para Portugal, sem depender dele."""
import itertools

import pytest

from engines import acoes_pt as A
from engines.bet_clt import norms as CLT


@pytest.mark.parametrize("zona,alt", itertools.product(["Z1", "Z2", "Z3"], [0, 150, 200, 450, 900, 1400]))
def test_neve_igual_ao_clt(zona, alt):
    raw = {"project": {"snow_zone": zona, "altitude_m": alt}}
    assert A.snow(raw, "PT", []) == CLT.snow(raw, "PT", [])


@pytest.mark.parametrize("zona,H", itertools.product(["A", "B"], [2.5, 5, 7.3, 12, 30]))
def test_vento_igual_ao_clt(zona, H):
    raw = {"project": {"wind_zone": zona}}
    assert A.wind(raw, "PT", H, []) == CLT.wind(raw, "PT", H, [])


def test_sobrecargas_iguais_ao_clt():
    for uso in list(CLT.Q_USE["PT"]) + ["desconhecido"]:
        assert A.q_use("PT", uso) == CLT.q_use("PT", uso)


def test_aviso_em_portugues_e_so_portugal():
    w = []
    A.snow({"project": {"altitude_m": 600}}, "PT", w)
    assert w == [("SNOW", "Zona de neve não indicada: Z2 admitida.")]
    with pytest.raises(ValueError):
        A.snow({"project": {}}, "FR", [])


def test_lsf_nao_depende_do_clt():
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1] / "engines" / "lsf" / "verificacao.py").read_text(encoding="utf-8")
    mods = {n.module for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ImportFrom) and n.module}
    assert not any("clt" in m for m in mods), mods
