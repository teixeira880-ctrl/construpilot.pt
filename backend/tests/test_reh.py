"""Pré-certificado REH indicativo (PT)."""
import pytest

from engines.calc_lots import reh as R


def test_clima_concelhos_e_altitude():
    c = R.clima("Lisboa", altitude_m=100)
    assert c["nuts"] == "Grande Lisboa" and c["zona_i"] == "I1" and c["GD"] == pytest.approx(1071 + 1700 * (0.100 - 0.109))
    assert R.clima("Bragança")["zona_i"] == "I3"
    assert R.clima("evora")["nuts"] == "Alentejo Central"
    assert R.clima("Funchal")["nuts"] == "RA Madeira"
    with pytest.raises(ValueError):
        R.clima("Paris")


def test_existente_antigo_pior_que_bomba_de_calor():
    base = {"area_util_m2": 120, "concelho": "Porto", "obra": "existente", "ano_construcao": 1975}
    a = R.calcular(base)
    b = R.calcular({**base, "aquecimento": {"tipo": "bomba_calor"}, "aqs": {"tipo": "bomba_calor"}})
    assert a["Nic"] > a["Ni"] and a["classe"] in ("D", "E", "F")
    assert b["Ntc"] < a["Ntc"] and "ABCDEF".index(b["classe"][0]) <= "ABCDEF".index(a["classe"][0])


def test_obra_nova_requisitos():
    r = R.calcular({"area_util_m2": 150, "concelho": "Bragança", "obra": "nova", "aquecimento": {"tipo": "bomba_calor"}, "aqs": {"tipo": "bomba_calor"},
                    "renovavel_kwh": 1500, "renovavel_tipo": "fotovoltaico", "ventilacao_mecanica": True})
    umax = [c for c in r["controles"] if c["ref"].startswith(("Umáx", "Uw"))]
    assert umax and all(c["ok"] for c in umax)
    assert r["classe"] in ("A+", "A")
    assert r["RenHab"] >= 0.5
    mau = R.calcular({"area_util_m2": 100, "concelho": "Lisboa", "obra": "nova",
                      "envolvente": [{"tipo": "parede", "area_m2": 100, "U": 0.9}, {"tipo": "envidracado", "area_m2": 15, "U": 3.5, "orientacao": "S"}]})
    assert any(c["ok"] is False for c in mau["controles"])


def test_entradas_invalidas_e_pdf():
    with pytest.raises(ValueError):
        R.calcular({"area_util_m2": 0, "concelho": "Porto"})
    with pytest.raises(ValueError):
        R.calcular({"area_util_m2": 80, "concelho": "Porto", "obra": "demolicao"})
    o = R.note({"area_util_m2": 80, "concelho": "Lisboa", "tipo": "apartamento", "posicao": "intermedio", "ano_construcao": 1995})
    assert o["pdf"][:4] == b"%PDF"
