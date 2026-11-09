"""Motores PT usados para obra CLT / Ucrânia: sobrecargas de cobertura por defeito, CLT no isolamento, clima ucraniano, REH (tipologia, PV)."""
from engines.calc_lots import aquecimento, gros_oeuvre, isolamento, reh


def _laje(**kw):
    d = {"ref": "C", "tipo": "clt", "x0_m": 0, "y0_m": 0, "x1_m": 5, "y1_m": 4, "espessura_m": 0.14, "camadas_mm": [28] * 5, "vao_m": 4.0,
         "cota_topo_m": 3.0, "g2_kn_m2": 1.0, "direcao_vao": "y"}
    d.update(kw)
    return d


def test_cobertura_sem_q_recebe_sobrecarga_e_neve():
    m = {"lajes": [_laje(piso="cobertura"), _laje(ref="T", piso="pavimento", cobertura_terraco=True), _laje(ref="N", piso="cobertura")],
         "neve_kn_m2": None}
    m["lajes"][2]["neve_kn_m2"] = 1.6
    hip = gros_oeuvre.cargas_cobertura(m)
    c, t, n = m["lajes"]
    assert c["q_kn_m2"] == 0.4 and c["psi2"] == 0.0            # cat. H
    assert t["q_kn_m2"] == 2.0 and t["psi2"] == 0.3            # terraço acessível
    assert n["q_kn_m2"] == 1.6 and n["psi2"] == 0.0            # neve > 0,4
    assert any("categoria H" in h for h in hip) and any("neve" in h.lower() for h in hip)


def test_q_indicado_nao_e_alterado_e_produto_ao_nivel_do_modelo():
    m = {"grelhas_x": [{"nome": "1", "pos_m": 0}, {"nome": "2", "pos_m": 5}], "grelhas_y": [{"nome": "A", "pos_m": 0}, {"nome": "B", "pos_m": 4}],
         "produto_clt": "rezult_clt", "lajes": [_laje(piso="cobertura", q_kn_m2=0.8)]}
    v = gros_oeuvre.verificar(m)
    assert m["lajes"][0]["q_kn_m2"] == 0.8 and m["lajes"][0]["produto"] == "rezult_clt"
    assert "Rezult" in v["elementos"][0]["seccao"]


def test_isolamento_clt_ucrania():
    r = isolamento.calcular({"sistema": "fachada_ventilada", "cidade_ua": "kyiv", "suporte": [{"material": "clt", "ep_mm": 100}], "isolante": "la_rocha"})
    assert r["pais"] == "ua" and abs(r["umax"] - 0.25) < 1e-9 and r["theta_e"] == -22
    assert r["U"] <= 0.25 and r["barreira_vapor"] and not r["glaser"]["condensation"]
    assert r["couches"][0]["code"] == "gesso_cartonado"


def test_isolamento_pt_inalterado():
    r = isolamento.calcular({"sistema": "etics", "concelho": "Porto", "suporte": [{"material": "tijolo_furado", "ep_mm": 150}]})
    assert r["pais"] == "pt" and r["couches"][0]["code"] == "estuque" and not r["barreira_vapor"]


def test_aquecimento_cidade_ucrania_e_pisos():
    hyp = []
    te, src = aquecimento.theta_projeto({"cidade_ua": "kharkiv"}, hyp)
    assert te < -15 and "Kharkiv" in hyp[0]


def test_reh_tipologia_por_defeito_e_pv_limitado():
    base = {"area_util_m2": 200, "concelho": "Lisboa", "obra": "nova", "tipo": "moradia", "aquecimento": {"tipo": "bomba_calor"}, "aqs": {"tipo": "bomba_calor"}}
    r = reh.calcular(base)
    assert r["ocupantes"] <= 6
    r2 = reh.calcular(dict(base, renovavel_kwh=50000, renovavel_tipo="fotovoltaico"))
    assert any("fotovoltaico limitado" in h for h in r2["hipoteses"])
