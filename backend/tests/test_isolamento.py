import pytest

from engines.calc_lots import isolamento as I


@pytest.mark.parametrize("sk", list(I.SISTEMAS))
def test_espessura_cumpre_umax(sk):
    for c in ("Lisboa", "Bragança"):
        r = I.calcular({"sistema": sk, "concelho": c, "lambda_declarado": 0.035})
        assert r["U"] <= r["umax"] + 1e-9 and r["controles"][0]["ok"] is True


def test_umax_por_zona_e_acores():
    assert I.calcular({"concelho": "Bragança"})["umax"] < I.calcular({"concelho": "Lisboa"})["umax"]
    assert I.calcular({"concelho": "Ponta Delgada"})["umax"] > 1.0


def test_lambda_por_defeito_fica_a_verificar_e_espessura_insuficiente():
    assert I.calcular({"concelho": "Lisboa"})["controles"][0]["ok"] is None
    r = I.calcular({"concelho": "Bragança", "isolante_ep_mm": 20, "lambda_declarado": 0.036})
    assert r["controles"][0]["ok"] is False and not r["conforme"]


def test_interior_barreira_vapor():
    r = I.calcular({"sistema": "interior", "concelho": "Guarda", "humidade": "forte"})
    assert r["barreira_vapor"] and any(c["code"] == "barreira_vapor" for c in r["couches"])


def test_erros_e_note():
    with pytest.raises(ValueError):
        I.calcular({"sistema": "magia", "concelho": "Lisboa"})
    with pytest.raises(ValueError):
        I.calcular({"concelho": "Lisboa", "isolante": "betao"})
    r = I.note({"sistema": "etics", "concelho": "Porto", "area_m2": 100})
    assert r["pdf"] and r["metre"]
