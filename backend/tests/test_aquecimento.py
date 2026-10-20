import pytest

from engines.calc_lots import aquecimento as A

DIV = [{"tipo": "sala", "area_m2": 30, "paredes": [{"area_m2": 20, "U": 0.4}, {"area_m2": 6, "U": 2.4}, {"area_m2": 30, "U": 0.35, "lado": "solo"}]},
       {"tipo": "quarto", "area_m2": 14, "paredes": [{"area_m2": 10, "U": 0.4}, {"area_m2": 2, "U": 2.4}]},
       {"tipo": "casa_de_banho", "area_m2": 5, "paredes": [{"area_m2": 5, "U": 0.4}]}]


def test_theta_projeto_por_concelho():
    tl = A.perdas({"concelho": "Lisboa", "divisoes": DIV})["theta_e"]
    tb = A.perdas({"concelho": "Bragança", "divisoes": DIV})["theta_e"]
    assert tb < tl < 6


def test_theta_indicada_e_proporcionalidade():
    r1 = A.perdas({"theta_e": 0, "divisoes": DIV, "delta_u_pontes": 0})
    r2 = A.perdas({"theta_e": -10, "divisoes": DIV, "delta_u_pontes": 0})
    assert r1["theta_e_fonte"] == "indicada" and r2["phi_total"] > r1["phi_total"] * 1.4
    sala = r1["divisoes"][0]
    assert abs(sala["phi_T"] - (20 * 0.4 + 6 * 2.4 + 30 * 0.35 * 0.45) * 20) < 1e-6


def test_erros():
    with pytest.raises(ValueError):
        A.perdas({"theta_e": 0, "divisoes": []})
    with pytest.raises(ValueError):
        A.perdas({"theta_e": 0, "divisoes": [{"tipo": "piscina", "area_m2": 10}]})
    with pytest.raises(ValueError):
        A.perdas({"theta_e": 0, "divisoes": [{"tipo": "sala", "area_m2": 10, "paredes": [{"area_m2": 5, "U": 1, "lado": "lua"}]}]})


def test_bomba_calor_cobertura_e_apoio():
    b = A.bomba_calor(6000, 0, {})
    assert 0.7 <= b["cobertura"] <= 1.0 and b["p_theta_e_kw"] + b["apoio_kw"] >= 7.2 - 1e-9
    assert all(c["ok"] is not False for c in b["controles"][:2])


def test_note():
    r = A.note({"concelho": "Porto", "divisoes": DIV, "bomba_calor": {"emissores": "radiadores_bt"}})
    assert r["pdf"] and r["bomba_calor"]["temperatura_ida"] == 45
