"""Motores PT aprofundados (paridade com o .fr): ventilação / infiltrações / pontes térmicas nas perdas, bomba de calor completa
(bivalência, apoio, inércia, vaso de expansão EN 12828, ErP), eletricidade por circuito com comprimentos reais, diferenciais,
entrada, e canalização / drenagem troço a troço. Cada valor esperado é verificado à mão no comentário."""
import re

import pytest

from engines.calc_lots import aquecimento as A
from engines.calc_lots import instalacoes as I
from engines.calc_lots import lotes_tecnicos, outils

# sala 20 m² × 2,5 m (V = 50 m³) + casa de banho 5 m² × 2,5 m (V = 12,5 m³, θint 22 °C); sem paredes → só ventilação
DIV2 = [{"nome": "Sala", "tipo": "sala", "area_m2": 20, "pe_direito_m": 2.5},
        {"nome": "WC", "tipo": "casa_de_banho", "area_m2": 5, "pe_direito_m": 2.5}]
BASE = {"theta_e": 0, "divisoes": DIV2, "delta_u_pontes": 0, "estanquidade": "muito_estanque", "rph_min": 0.4}


# ------------------------------------------------------------------------------------------------ perdas: ventilação
def test_extracao_contada_uma_vez_ventilacao_natural():
    # q_proj = max(45 m³/h extração WC, 0,4 × 62,5 = 25) = 45 m³/h, entra todo na sala (única divisão principal)
    # sala: 0,34 × (45 × 20 + 0,05 × 50 × 20) = 0,34 × 950 = 323,0 W
    # WC: ar transferido a 20 °C → 0,34 × 45 × (22 − 20) = 30,6 W + infiltração 0,34 × 0,05 × 12,5 × 22 = 4,675 W
    r = A.perdas({**BASE, "ventilacao": "natural"})
    sala, wc = r["divisoes"]
    assert r["q_ventilacao_m3h"] == pytest.approx(45)
    assert sala["q_ar_m3h"] == pytest.approx(45) and wc["origem_ar"] == "transferido"
    assert sala["phi_V"] == pytest.approx(323.0, abs=1e-6)
    assert wc["phi_V"] == pytest.approx(30.6 + 4.675, abs=1e-6)
    # o ar extraído do WC não é somado como ar exterior: Φ_V total = 323,0 + 35,275 (e não + 0,34 × 45 × 22 = 336,6 W)
    assert r["phi_V"] == pytest.approx(358.275, abs=1e-6)


def test_dupla_fluxo_com_recuperacao():
    # θsu = 0 + 0,8 × 20 = 16 °C → sala 0,34 × 45 × (20 − 16) = 61,2 W + infiltração 0,34 × 2,5 × 20 = 17,0 W = 78,2 W
    r = A.perdas({**BASE, "ventilacao": "dupla_fluxo", "recuperacao_calor": 0.8})
    assert r["divisoes"][0]["theta_ar"] == pytest.approx(16.0)
    assert r["divisoes"][0]["phi_V"] == pytest.approx(78.2, abs=1e-6)
    assert r["divisoes"][1]["phi_V"] == pytest.approx(35.275, abs=1e-6)          # WC inalterado (ar transferido)


def test_compatibilidade_recuperacao_sem_tipo_de_ventilacao():
    # chamada antiga (só recuperacao_calor) = dupla fluxo explícita
    a = A.perdas({**BASE, "recuperacao_calor": 0.7})
    b = A.perdas({**BASE, "ventilacao": "dupla_fluxo", "recuperacao_calor": 0.7})
    assert a["ventilacao"] == "dupla_fluxo" and a["phi_total"] == pytest.approx(b["phi_total"])
    # sem recuperador o valor por defeito do .pt (natural) mantém a fórmula anterior: q·V/V_pr + infiltração
    c = A.perdas({**BASE})
    assert c["ventilacao"] == "natural" and c["divisoes"][0]["phi_V"] == pytest.approx(323.0)


def test_n50_e_reaquecimento_e_pontes():
    # n50 = 3 h⁻¹, e = 0,02 → n_inf = 2 × 3 × 0,02 = 0,12 h⁻¹ ; sala: 0,34 × 0,12 × 50 × 20 = 40,8 W
    r = A.perdas({**BASE, "n50": 3})
    assert r["n_inf"] == pytest.approx(0.12) and r["divisoes"][0]["phi_V_infiltracao"] == pytest.approx(40.8)
    # reaquecimento 10 W/m² → 200 W na sala
    assert A.perdas({**BASE, "reaquecimento_w_m2": 10})["divisoes"][0]["phi_RH"] == pytest.approx(200)
    # ψ·L = 8 m × 0,5 = 4 W/°C → +80 W a ΔT 20 K; sem ΔU forfetário quando há pontes descritas
    div = [{**DIV2[0], "paredes": [{"area_m2": 10, "U": 0.5}], "pontes": [{"comprimento_m": 8, "psi": 0.5}]}, DIV2[1]]
    p = A.perdas({"theta_e": 0, "divisoes": div})
    assert p["delta_u_pontes"] == 0 and p["soma_psi_l"] == pytest.approx(4.0)
    assert p["divisoes"][0]["phi_T"] == pytest.approx(10 * 0.5 * 20 + 80)       # 100 + 80 = 180 W
    assert any("Pontes térmicas lineares" in c["ref"] for c in p["controles"])


def test_erros_ventilacao():
    with pytest.raises(ValueError):
        A.perdas({**BASE, "ventilacao": "janela_aberta"})
    with pytest.raises(ValueError):
        A.perdas({**BASE, "ventilacao": "dupla_fluxo", "recuperacao_calor": 1.2})
    with pytest.raises(ValueError):
        A.perdas({**BASE, "estanquidade": "furada"})


# ------------------------------------------------------------------------------------------------ bomba de calor
def test_bivalencia_com_valor_do_fabricante():
    # D = 6 kW a θe = −2 °C, θint 20 ; P(θe) = 4,0 kW (ficha), P(θ) = 4,0·f(θ)/f(−2), f(θ) = 0,874 + 0,018·θ, f(−2) = 0,838
    # 4,0·(0,874 + 0,018θ)/0,838 = 6·(20 − θ)/22 → 4,1719 + 0,085919θ = 5,4545 − 0,27273θ → θ = 3,58 °C
    # apoio = 1,2 × 6 − 4,0 = 3,2 kW → escalão 4 kW
    b = A.bomba_calor(6000, -2, {"p_nominal_kw": 6, "p_theta_e_kw": 4.0})
    assert b["bivalencia_c"] == pytest.approx(3.58, abs=0.05)
    assert b["apoio_kw"] == 4 and b["cobertura"] == pytest.approx(4 / 6)
    biv = next(c for c in b["controles"] if c["ref"] == "Ponto de bivalência")
    assert biv["ok"] is True and "apoio completa" in biv["note"]


def test_curva_do_fabricante_interpolada():
    # pontos (−7; 4,5 kW; COP 2,6), (2; 5,5; 3,4), (7; 6,0; 4,4) → a −2 °C: P = 4,5 + 1,0 × 5/9 = 5,056 kW, COP = 2,6 + 0,8 × 5/9 = 3,044
    curva = [{"theta_ext": -7, "p_kw": 4.5, "cop": 2.6}, {"theta_ext": 2, "p_kw": 5.5, "cop": 3.4}, {"theta_ext": 7, "p_kw": 6.0, "cop": 4.4}]
    b = A.bomba_calor(6000, -2, {"curva_fabricante": curva})
    assert b["p_theta_e_kw"] == pytest.approx(5.0556, abs=1e-3) and b["cop"] == pytest.approx(3.0444, abs=1e-3)
    assert b["p_nominal_kw"] == pytest.approx(6.0) and b["fonte_potencia"] == "curva do fabricante"


def test_deposito_de_inercia():
    # 8 kW nominal × 10 L/kW = 80 L ; instalação 40 L → faltam 40 L → depósito normalizado 40 L
    b = A.bomba_calor(7000, 0, {"p_nominal_kw": 8, "volume_instalacao_l": 40})
    assert b["volume_min_l"] == pytest.approx(80) and b["deposito_inercia_l"] == 40
    assert next(c for c in b["controles"] if c["ref"] == "Volume de água mínimo")["ok"] is False
    # o vaso de expansão é calculado sobre instalação + depósito
    assert b["vaso"]["volume_l"] == pytest.approx(80)


def test_vaso_expansao_en12828():
    # V = 100 L, θmax 45 °C, h = 5 m, válvula 3 bar ; pst = 0,4905 → p0 = ⌈0,6905⌉₀,₁ = 0,7 bar ; pe = 3 − 0,5 = 2,5 bar
    # e = 999,70 / 990,13 − 1 = 0,9666 % → Ve = 0,967 L ; Vwr = max(0,5 L, 3 L) = 3 L
    # Vn = (0,967 + 3) × (2,5 + 1) / (2,5 − 0,7) = 3,967 × 3,5 / 1,8 = 7,713 L → vaso 8 L
    v = A.vaso_expansao(100, 45, 5, 3.0)
    assert v["p0_bar"] == pytest.approx(0.7) and v["pe_bar"] == pytest.approx(2.5)
    assert v["expansao_pct"] == pytest.approx(0.9666, abs=1e-3)
    assert v["vn_min_l"] == pytest.approx(7.713, abs=0.01) and v["vaso_l"] == 8
    # válvula acima de 5 bar: pe = 0,9 × psv
    assert A.vaso_expansao(100, 45, 5, 6.0)["pe_bar"] == pytest.approx(5.4)
    # tarado ≤ p0: irrealizável
    assert A.vaso_expansao(100, 45, 25, 3.0)["realizavel"] is False


def test_vaso_integrado_insuficiente():
    b = A.bomba_calor(6000, 0, {"p_nominal_kw": 6, "volume_instalacao_l": 300, "vaso_integrado_l": 8})
    c = next(c for c in b["controles"] if c["ref"].startswith("Vaso de expansão"))
    assert b["vaso"]["vn_min_l"] > 8 and c["ok"] is False and "suplementar" in c["note"]


def test_erp_ecodesign():
    # Reg. (UE) 813/2013: η_s ≥ 110 % (média temperatura) ; ≥ 125 % (bomba de calor de baixa temperatura)
    def ctl(b):
        return next(c for c in b["controles"] if c["ref"].startswith("Eficiência sazonal"))
    assert ctl(A.bomba_calor(6000, 0, {"eta_s_pct": 105}))["ok"] is False
    assert ctl(A.bomba_calor(6000, 0, {"eta_s_pct": 115}))["ok"] is True
    assert ctl(A.bomba_calor(6000, 0, {"eta_s_pct": 120, "baixa_temperatura": True}))["ok"] is False
    assert ctl(A.bomba_calor(6000, 0, {}))["ok"] is None                       # sem ficha: a verificar, nunca «conforme»
    # SCOP 4,0 da ficha → η_s = 100 × 4,0 / 2,5 − 3 = 157 % → classe A+++ na aplicação de baixa temperatura? 157 < 175 → A++
    b = A.bomba_calor(6000, 0, {"scop": 4.0})
    assert b["eta_s_pct"] == pytest.approx(157) and b["classe_erp"] == "A++" and b["scop_fonte"] == "ficha"


def test_alimentacao_trifasica():
    # P(θe) 10 kW, COP 2,0 → compressor 5 kW ; apoio 1,2 × 12 − 10 = 4,4 → 6 kW ; P abs = 11 kW
    # monofásico: 11 000 / (230 × 0,95) = 50,3 A > 32 A → trifásico: 11 000 / (√3 × 400 × 0,95) = 16,71 A
    b = A.bomba_calor(12000, -3, {"p_nominal_kw": 14, "p_theta_e_kw": 10, "cop_theta_e": 2.0})
    assert b["apoio_kw"] == 6 and b["p_absorvida_kw"] == pytest.approx(11.0)
    assert b["corrente_mono_a"] == pytest.approx(50.34, abs=0.01) and b["alimentacao"] == "tri"
    assert b["corrente_a"] == pytest.approx(16.71, abs=0.01)


def test_apoio_caldeira_fora_da_potencia_eletrica_e_erros():
    b = A.bomba_calor(12000, -3, {"p_nominal_kw": 14, "p_theta_e_kw": 10, "cop_theta_e": 2.0, "tipo_apoio": "caldeira"})
    assert b["apoio_kw"] == 6 and b["p_absorvida_kw"] == pytest.approx(5.0)
    with pytest.raises(ValueError):
        A.bomba_calor(6000, 0, {"tipo_apoio": "lareira"})
    with pytest.raises(ValueError):
        A.bomba_calor(0, 0, {})
    assert "MaPrimeRénov" not in " ".join(A.bomba_calor(6000, 0, {})["regras"])


# ------------------------------------------------------------------------------------------------ eletricidade
def test_comprimento_real_e_seccao_recomendada():
    # 8 pontos de luz a 70 m: Ib = 8 × 100 / 230 = 3,478 A ; ΔU = 2 × 0,023 × 70 / 1,5 × 3,478 = 7,467 V = 3,25 % > 3 %
    # em 2,5 mm²: 4,480 V = 1,95 % → secção recomendada 2,5 mm²
    r = I.eletricidade({"divisoes": [{"nome": "Sala", "tipo": "sala", "area_m2": 20, "pontos_luz": 8, "distancia_quadro_m": 70}],
                        "equipamentos": {"placa": False, "forno": False, "maquina_lavar_roupa": False, "maquina_lavar_loica": False, "termoacumulador": False}})
    il = r["circuitos"][0]
    assert il["nome"] == "Iluminação 1" and il["comprimento_m"] == 70 and il["divisoes"] == ["Sala"]
    assert il["du"] == pytest.approx(3.246, abs=0.005) and il["du_ok"] is False and il["seccao_recomendada"] == 2.5
    assert r["controles"][0]["ok"] is False and any(c["ref"] == "Queda de tensão — Iluminação 1" for c in r["controles"])


def test_queda_tensao_trifasica_fator_1():
    # VE 11 kW tri: Ib = 11 000 / (√3 × 400) = 15,877 A → 16 A / 2,5 mm² ; 15 m:
    # ΔU = 1 × 0,023 × 15 / 2,5 × 15,877 = 2,191 V / 230,94 V = 0,949 % (o fator 3 anterior dava 2,85 %: fisicamente errado)
    r = I.eletricidade({"divisoes": [{"tipo": "sala", "area_m2": 20}], "equipamentos": {"carregamento_ve_kw": 11}, "comprimentos_m": {"carregamento_ve": 15}})
    ve = next(c for c in r["circuitos"] if c["nome"].startswith("Carregamento"))
    assert ve["disjuntor"] == 16 and ve["du"] == pytest.approx(0.949, abs=0.002)


def test_diferenciais_agrupados():
    r = I.eletricidade({"divisoes": [{"tipo": "sala", "area_m2": 30}, {"tipo": "quarto", "area_m2": 12}, {"tipo": "cozinha", "area_m2": 10},
                                     {"tipo": "casa_de_banho", "area_m2": 5}], "equipamentos": {"carregamento_ve_kw": 11}})
    difs = r["diferenciais_lista"]
    ve = [d for d in difs if d["individual"]]
    assert len(ve) == 1 and ve[0]["tipo"] == "B" and ve[0]["polos"] == "4P"          # VE trifásico: diferencial individual tipo B
    assert sum(1 for d in difs if d["tipo"] == "AC") >= 2                              # iluminação / tomadas repartidas
    assert r["diferenciais"] == len(difs)
    por_nome = {c["nome"]: c for c in r["circuitos"]}
    for d in difs:                                                                     # calibre ≥ maior disjuntor a jusante
        assert d["calibre"] >= max(por_nome[n]["disjuntor"] for n in d["circuitos"]) and len(d["circuitos"]) <= 8
    placa = next(d for d in difs if "Placa / fogão" in d["circuitos"])
    assert placa["tipo"] == "A" and placa["calibre"] >= 32


def test_aquecimento_por_divisao_e_apoio_bc():
    # 2 000 W → 8,7 A → 16 A / 2,5 mm² ; 4 000 W → 17,4 A → 20 A / 4 mm²
    r = I.eletricidade({"divisoes": [{"nome": "Q1", "tipo": "quarto", "area_m2": 12, "aquecimento_w": 2000},
                                     {"nome": "Sala", "tipo": "sala", "area_m2": 25, "aquecimento_w": 4000}],
                        "equipamentos": {"bomba_calor_kw": 1.5, "apoio_bomba_calor_kw": 3}})
    c = {x["nome"]: x for x in r["circuitos"]}
    assert (c["Aquecimento elétrico — Q1"]["disjuntor"], c["Aquecimento elétrico — Q1"]["seccao"]) == (16, 2.5)
    assert (c["Aquecimento elétrico — Sala"]["disjuntor"], c["Aquecimento elétrico — Sala"]["seccao"]) == (20, 4.0)
    assert c["Apoio elétrico da bomba de calor"]["disjuntor"] == 16                     # 3 000 / 230 = 13,0 A
    # potência: 25 × 37 + 0,5 × (placa 7 200 + forno 3 000 + 2 máquinas 2 × 2 200) + termo 2 000 + BC 1 500 + apoio 3 000 + 6 000 aquecimento
    assert r["potencia_estimada_w"] == pytest.approx(925 + 0.5 * 14600 + 2000 + 1500 + 3000 + 6000)


def test_entrada_e_monofasica_forcada():
    r = I.eletricidade({"divisoes": [{"tipo": "sala", "area_m2": 30}, {"tipo": "quarto", "area_m2": 12}], "comprimento_entrada_m": 10, "seccao_entrada_mm2": 10})
    e = r["entrada"]
    # ΔU = 2 × 0,023 × 10 / 10 × I / 230 × 100
    assert e["du"] == pytest.approx(2 * 0.023 * 10 / 10 * r["corrente_contrato_a"] / 230 * 100)
    assert r["corrente_contrato_a"] == pytest.approx(r["potencia_contratada_kva"] * 1000 / 230)
    f = I.eletricidade({"divisoes": [{"tipo": "sala", "area_m2": 30}], "equipamentos": {"carregamento_ve_kw": 11}, "alimentacao": "monofasica"})
    assert next(c for c in f["controles"] if c["ref"].startswith("Potência a contratar"))["ok"] is False


# ------------------------------------------------------------------------------------------------ canalização troço a troço
REDE = [{"nome": "T1", "montante": None, "comprimento_m": 10, "desnivel_m": 0},
        {"nome": "T2", "montante": "T1", "comprimento_m": 5, "desnivel_m": 3,
         "dispositivos": [{"tipo": "lavatorio"}, {"tipo": "autoclismo"}, {"tipo": "chuveiro"}]}]


def test_rede_agua_troco_a_troco():
    # Qa = 0,10 + 0,10 + 0,15 = 0,35 L/s ≤ 0,5 → Qc = 0,35 ; Ø20 (15 mm): 1,98 m/s > 1,5 → Ø25 (19 mm): v = 1,2344 m/s
    # Re = 1,2344 × 0,019 / 1e-6 = 23 454 ; λ = 0,3164 / Re^0,25 = 0,025567 ; J = λ/D · v²/2g = 0,10451 m/m
    # T1: 0,10451 × 10 × 1,2 = 1,2541 m = 12,30 kPa → P = 300 − 12,30 = 287,7 kPa
    # T2: 0,6271 m = 6,15 kPa + 3 m × 9,81 = 29,43 kPa → P = 287,7 − 35,58 = 252,1 kPa
    r = I.canalizacao({"rede": REDE, "pressao_rede_kpa": 300})
    t1, t2 = r["rede"]["trocos"]
    assert (t1["dn"], t2["dn"]) == (25, 25) and t1["velocidade_m_s"] == pytest.approx(1.2344, abs=1e-3)
    assert t1["p_fim_kpa"] == pytest.approx(287.7, abs=0.1) and t2["p_fim_kpa"] == pytest.approx(252.1, abs=0.1)
    assert r["pressao_kpa"] == pytest.approx(252.1, abs=0.1) and r["rede"]["ponto_desfavoravel"] == "T2"
    assert r["controles"][1]["ref"].startswith("Pressão") and r["controles"][1]["ok"] is True
    assert r["qa_l_s"] == pytest.approx(0.35)                                          # dispositivos deduzidos da rede


def test_rede_agua_quente_so_dispositivos_aq():
    rede = REDE + [{"nome": "Q1", "montante": None, "comprimento_m": 4, "agua": "quente", "dispositivos": [{"tipo": "lavatorio"}, {"tipo": "autoclismo"}]}]
    q = next(t for t in I.canalizacao({"rede": rede})["rede"]["trocos"] if t["nome"] == "Q1")
    assert q["qa_l_s"] == pytest.approx(0.10)                                          # autoclismo sem água quente


def test_rede_erros():
    with pytest.raises(ValueError):
        I.rede_agua([{"nome": "A", "montante": "B", "comprimento_m": 1}, {"nome": "B", "montante": "A", "comprimento_m": 1}], 300)
    with pytest.raises(ValueError):
        I.rede_agua([{"nome": "A", "montante": "X", "comprimento_m": 1}], 300)
    with pytest.raises(ValueError):
        I.rede_agua([{"nome": "A", "comprimento_m": 1}, {"nome": "A", "comprimento_m": 2}], 300)


def test_drenagem_ramal_meia_seccao():
    # lavatório + chuveiro: Qa = 60 L/min ; 7,3497 × 60^0,5352 = 65,8 > Qa → Qc = 60 L/min
    # Ø50 (46,4 mm) a 2 %: Q = 120 × πD²/8 × (D/4)^(2/3) × √0,02 = 44,1 L/min < 60 → Ø75 (70,6 mm): 135,1 L/min
    r = I.rede_drenagem([{"nome": "R", "tipo": "ramal", "inclinacao_pct": 2, "dispositivos": [{"tipo": "lavatorio"}, {"tipo": "chuveiro"}]}])
    t = r["trocos"][0]
    assert t["qc_l_min"] == pytest.approx(60) and t["dn"] == 75 and t["capacidade_l_min"] == pytest.approx(135.1, abs=0.3)
    assert I._q_meia_seccao(46.4, 0.02) == pytest.approx(44.1, abs=0.1)


def test_drenagem_tubo_de_queda_e_coletor():
    # ramal: autoclismo 90 + lavatório 30 + banheira 60 = 180 L/min → Qc = 7,3497 × 180^0,5352 = 118,4 L/min
    # tubo de queda sem ventilação secundária (ts = 1/7): D = 4,4205 × 118,4^0,375 × 7^0,625 = 89,4 mm > 85,6 (Ø90) → Ø110
    # com ventilação secundária (ts = 1/3): D = 52,6 mm → Ø90 (mínimo com bacia de retrete)
    rede = [{"nome": "R", "jusante": "TQ", "tipo": "ramal", "dispositivos": [{"tipo": "autoclismo"}, {"tipo": "lavatorio"}, {"tipo": "banheira"}]},
            {"nome": "TQ", "jusante": "C", "tipo": "tubo_queda"}, {"nome": "C", "jusante": None, "tipo": "coletor", "inclinacao_pct": 2}]
    r = {t["nome"]: t for t in I.rede_drenagem(rede, 1 / 7)["trocos"]}
    assert r["TQ"]["qc_l_min"] == pytest.approx(118.4, abs=0.1) and r["TQ"]["dn"] == 110
    assert I._di_tubo_queda(118.4, 1 / 7) == pytest.approx(89.4, abs=0.1)
    assert r["C"]["dn"] >= r["TQ"]["dn"] and r["C"]["dn"] >= 100                       # nunca decresce para jusante; coletor ≥ 100
    assert [t["nome"] for t in I.rede_drenagem(rede)["trocos"]] == ["R", "TQ", "C"]    # de montante para jusante
    v = {t["nome"]: t for t in I.rede_drenagem(rede, 1 / 3)["trocos"]}
    assert v["TQ"]["dn"] == 90
    k = I.canalizacao({"dispositivos": [{"tipo": "lavatorio"}], "rede_drenagem": rede})
    assert k["tubo_queda_mm"] == 110 and k["coletor_mm"] == 110


def test_caudal_drenagem_continuo():
    # Qc = min(Qa, 7,3497·Qa^0,5352): igualdade em Qa ≈ 73 L/min ; a forma anterior saltava de 270 para 148 L/min em Qa = 270
    assert I.caudal_calculo_drenagem(60) == pytest.approx(60)
    assert I.caudal_calculo_drenagem(270) == pytest.approx(7.3497 * 270 ** 0.5352)
    prev = 0.0
    for qa in range(10, 2000, 10):
        q = I.caudal_calculo_drenagem(qa)
        assert q >= prev - 1e-9 and q <= qa + 1e-9
        prev = q


# ------------------------------------------------------------------------------------------------ cadeia e ferramentas
DIV_T2 = [{"nome": "Sala", "tipo": "sala", "area_m2": 28, "paredes": [{"area_m2": 14, "U": 0.5}, {"tipo": "envidracado", "area_m2": 5, "U": 2.5}],
           "distancia_quadro_m": 10},
          {"nome": "Quarto", "tipo": "quarto", "area_m2": 12, "paredes": [{"area_m2": 9, "U": 0.5}], "distancia_quadro_m": 14},
          {"nome": "Cozinha", "tipo": "cozinha", "area_m2": 10, "paredes": [{"area_m2": 7, "U": 0.5}], "distancia_quadro_m": 6},
          {"nome": "WC", "tipo": "casa_de_banho", "area_m2": 5, "paredes": [{"area_m2": 4, "U": 0.5}], "distancia_quadro_m": 9}]


def test_cadeia_passa_ida_e_circuitos_separados():
    o = lotes_tecnicos.calcular({"concelho": "Bragança", "divisoes": DIV_T2, "ventilacao": "dupla_fluxo", "recuperacao_calor": 0.8,
                                 "lotes": None}, ("aquecimento", "piso_radiante", "bomba_calor", "eletricidade"))
    bc, pr, el = o["bomba_calor"], o["piso_radiante"], o["eletricidade"]
    assert o["aquecimento"]["ventilacao"] == "dupla_fluxo"
    assert bc["temperatura_ida"] == round(pr["theta_ida"] * 2) / 2                     # ida do piso radiante usada no COP e no vaso
    assert bc["volume_instalacao_l"] == pytest.approx(pr["volume_agua_l"] + 20)
    nomes = [c["nome"] for c in el["circuitos"]]
    assert "Bomba de calor" in nomes
    if bc["apoio_kw"]:
        assert "Apoio elétrico da bomba de calor" in nomes
    assert next(c for c in el["circuitos"] if c["nome"] == "Placa / fogão")["comprimento_m"] == 6   # distância da cozinha


def _args(name, **kw):
    tool = next(t for t in outils.CALC_TOOLS if t["name"] == name)
    return {**{k: None for k in tool["parameters"]["properties"]}, **kw}


def test_ferramentas_com_novos_campos():
    curva = [{"theta_ext": -7, "p_kw": 4.5, "cop": 2.6}, {"theta_ext": 7, "p_kw": 6.0, "cop": None}]
    bc = {k: None for k in outils._BC_PROPS}
    bc.update(curva_fabricante=curva, inercia="forte", eta_s_pct=160)
    r = outils.run("calcul_aquecimento", _args("calcul_aquecimento", theta_e=-1, ventilacao="mecanica_simples", n50=4, divisoes=[
        {"nome": "Sala", "tipo": "sala", "area_m2": 25, "pe_direito_m": None, "theta_int": None, "q_extracao_m3h": None,
         "paredes": [{"area_m2": 20, "U": 0.5, "lado": None, "b": None}], "pontes": [{"comprimento_m": 6, "psi": 0.4, "designacao": None}]},
        {"nome": "WC", "tipo": "casa_de_banho", "area_m2": 5, "pe_direito_m": None, "theta_int": None, "q_extracao_m3h": 60, "paredes": None, "pontes": None}],
        bomba_calor=bc))
    assert "bivalência" in r["resume"] and "vaso de expansão" in r["resume"] and "mecânica simples fluxo" in r["resume"]
    assert r["data"]["vaso_l"] and r["pdf"][:4] == b"%PDF"
    i = outils.run("calcul_instalacoes", _args("calcul_instalacoes", canalizacao={
        "dispositivos": None, "velocidade_max_m_s": None, "comprimento_m": None, "desnivel_m": None, "pressao_rede_kpa": 300, "ventilacao_secundaria": None,
        "taxa_ocupacao": None,
        "rede": [{"nome": "T1", "montante": None, "comprimento_m": 10, "desnivel_m": None, "agua": None, "dispositivos": None},
                 {"nome": "T2", "montante": "T1", "comprimento_m": 5, "desnivel_m": 3, "agua": None,
                  "dispositivos": [{"tipo": "lavatorio", "quantidade": None}, {"tipo": "autoclismo", "quantidade": None}, {"tipo": "chuveiro", "quantidade": None}]}],
        "rede_drenagem": [{"nome": "R", "jusante": None, "tipo": None, "comprimento_m": None, "inclinacao_pct": None,
                           "dispositivos": [{"tipo": "lavatorio", "quantidade": None}]}]}))
    assert "Troços de abastecimento" in i["resume"] and "Troços de drenagem" in i["resume"]
    assert i["data"]["pressao_kpa"] == pytest.approx(252.1, abs=0.1)
    assert re.search(r"\d\.\d", i["resume"]) is None and re.search(r"\d\.\d", r["resume"]) is None              # vírgula decimal
