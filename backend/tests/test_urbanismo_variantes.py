"""Modelos por estilo adaptados ao terreno (14/11): saem dos motores (programa, implantação, plantas), nunca copiados."""
from engines.urbanismo_pt.auto import variantes as VA

TER = {"poligono_m": [[0, 0], [30, 0], [30, 40], [0, 40]], "plot_l_m": 30, "plot_w_m": 40,
       "azimutes": {"frente": 180, "tardoz": 0, "esquerda": 270, "direita": 90}, "area_m2": 1200}


def test_variantes_cabem_e_variam():
    r = VA.gerar({"auto": {"terreno": TER, "pedido": {"tipologia": "T3"}}}, ["contemporaneo", "minhoto_granito", "alentejano"], {}, 3)
    vs = r["variantes"]
    assert len(vs) == 3
    alent = next(v for v in vs if v["estilo"] == "alentejano")
    assert alent["pisos"] == 1                                   # monte alentejano: térreo
    cont = next(v for v in vs if v["estilo"] == "contemporaneo")
    assert cont["estudio"]["telhado"] == "plana" and cont["volume"]["roof_type"] == "plana"
    assert next(v for v in vs if v["estilo"] == "minhoto_granito")["materiais"]["fachada"] == "granito"
    for v in vs:                                                  # dentro da zona edificável (afastamentos 5/3/6)
        x0, y0, x1, y1 = v["plantas"]["casa_rect"]
        assert x0 >= 3 - 1e-6 and x1 <= 27 + 1e-6 and y0 >= 5 - 1e-6 and y1 <= 34 + 1e-6
        assert all(x0 - 1e-6 <= o["x0"] < o["x1"] <= x1 + 1e-6 for o in v["vaos"] if o["fachada"] in ("frente", "tardoz"))


def test_terreno_apertado_diz_porque():
    ter = {**TER, "poligono_m": [[0, 0], [12, 0], [12, 18], [0, 18]], "plot_l_m": 12, "plot_w_m": 18, "area_m2": 216}
    r = VA.gerar({"auto": {"terreno": ter}}, ["contemporaneo"], {}, 4)
    assert r["variantes"] == [] and r["nao_couberam"]


def test_descricao_para_parametros():
    r = VA.ler_descricao("quero uma moradia moderna T4 com cobertura plana, casa de 220 m2, na Rua X em Braga")
    assert r["estilo"] == "contemporaneo" and r["pedido"]["tipologia"] == "T4" and r["pedido"]["area_casa_m2"] == 220.0
    assert "morada" not in r["pedido"]
