"""Águas pluviais, fossa séptica e ventilação (PT)."""
import pytest

from engines.calc_lots import redes as R


def test_idf_e_regioes():
    assert R.intensidade("A", 5, 5) == pytest.approx(259.26 * 5 ** -0.562)
    assert R.intensidade("B", 5, 5) == pytest.approx(0.8 * R.intensidade("A", 5, 5))
    with pytest.raises(ValueError):
        R.aguas_pluviais({"regiao": "D", "vertentes": [{"area_planta_m2": 50}]})


def test_aguas_pluviais():
    r = R.aguas_pluviais({"vertentes": [{"area_planta_m2": 150, "comprimento_caleira_m": 25}]})
    v = r["vertentes"][0]
    assert v["tubos_queda"] >= 2 and v["phi"] >= 50 and r["coletor"] >= 110
    assert v["cap_caleira"] >= v["Q"] / v["tubos_queda"]


def test_fossa_septica():
    f = R.fossa_septica({"habitantes": 5})
    assert f["volume_util_m3"] == pytest.approx(5 * 150 * 0.8 / 1000 * 3 + 5 * 0.11 * 670 / 1000 + 5 * 0.28 * 60 / 1000)
    assert R.fossa_septica({"habitantes": 5, "solo": "argiloso"})["destino"]["solucao"].startswith("fossa estanque")


def test_ventilacao():
    v = R.ventilacao({"compartimentos": [{"tipo": "sala", "area_m2": 30}, {"tipo": "quarto", "area_m2": 12}, {"tipo": "cozinha", "area_m2": 10}]})
    assert v["rph"] >= 0.5 and all(c["ok"] for c in v["controles"])
    o = R.note({"ventilacao": {"compartimentos": [{"tipo": "sala", "area_m2": 30}, {"tipo": "cozinha", "area_m2": 10}]}})
    assert o["pdf"][:4] == b"%PDF"
