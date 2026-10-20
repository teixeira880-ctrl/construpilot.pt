import pytest

from engines.calc_lots import instalacoes as I

T2 = [{"tipo": "sala", "area_m2": 30}, {"tipo": "quarto", "area_m2": 12}, {"tipo": "quarto", "area_m2": 12},
      {"tipo": "cozinha", "area_m2": 10}, {"tipo": "casa_de_banho", "area_m2": 5}, {"tipo": "corredor", "area_m2": 6}]


def test_circuitos_max_8_pontos_e_seccoes():
    r = I.eletricidade({"divisoes": T2})
    for c in r["circuitos"]:
        if c["nome"].startswith("Iluminação"):
            assert c["seccao"] == 1.5 and c["disjuntor"] == 10 and c["pontos"] <= 8
        if c["nome"].startswith("Tomadas"):
            assert c["seccao"] == 2.5 and c["disjuntor"] == 16 and c["pontos"] <= 8
    assert sum(c["pontos"] for c in r["circuitos"] if c["nome"].startswith("Tomadas")) == r["tomadas"]
    assert r["potencia_contratada_kva"] in I.ESCALOES and r["potencia_contratada_kva"] >= 6.9


def test_ve_trifasico_e_terra():
    r = I.eletricidade({"divisoes": T2, "equipamentos": {"carregamento_ve_kw": 11}, "resistencia_terra_ohm": 150})
    ve = [c for c in r["circuitos"] if c["nome"].startswith("Carregamento")][0]
    assert ve["b"] == 3 and r["alimentacao"] == "trifásica"
    terra = [c for c in r["controles"] if c["ref"].startswith("Ligação")][0]
    assert terra["ok"] is False


def test_divisao_desconhecida():
    with pytest.raises(ValueError):
        I.eletricidade({"divisoes": [{"tipo": "piscina", "area_m2": 10}]})
    with pytest.raises(ValueError):
        I.eletricidade({"divisoes": []})


def test_caudal_calculo_monotono():
    prev = 0
    for qa in [0.1, 0.5, 1, 2, 3.5, 5.3, 10, 25, 50, 200]:
        qc = I.caudal_calculo(qa)
        assert qc <= qa + 1e-9 and qc >= prev - 0.03
        prev = qc


def test_canalizacao_t2():
    r = I.canalizacao({"dispositivos": [{"tipo": "lavatorio", "quantidade": 2}, {"tipo": "chuveiro"}, {"tipo": "banheira"},
                                        {"tipo": "autoclismo", "quantidade": 2}, {"tipo": "lava_loica"}, {"tipo": "maquina_lavar_roupa"}]})
    assert abs(r["qa_l_s"] - 1.2) < 1e-9 and r["qc_l_s"] < r["qa_l_s"]
    assert 0.5 <= r["velocidade_m_s"] <= 2.0 and r["tubo_queda_mm"] == 100
    assert all(c["ok"] for c in r["controles"])


def test_pressao_insuficiente_e_excessiva():
    d = [{"tipo": "banheira", "quantidade": 3}]
    assert I.canalizacao({"dispositivos": d, "pressao_rede_kpa": 80, "desnivel_m": 6})["controles"][1]["ok"] is False
    assert I.canalizacao({"dispositivos": d, "pressao_rede_kpa": 700})["controles"][1]["ok"] is False


def test_note_pdf():
    r = I.note({"eletricidade": {"divisoes": T2}, "canalizacao": {"dispositivos": [{"tipo": "lavatorio"}]}})
    assert r["pdf"] and "eletricidade" in r and "canalizacao" in r
    with pytest.raises(ValueError):
        I.note({})
