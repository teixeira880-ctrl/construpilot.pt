"""Especialidades (eletricidade, águas / esgotos, piso radiante + bomba de calor), planos EN / UK e orçamento detalhado UA."""
import re

import pymupdf

from engines.calc_lots import devis_ua, especialidades, gros_oeuvre, planos_especialidades

PER = [[0, 0], [8, 0], [8, 6], [0, 6], [0, 0]]


def _modelo():
    m = {"projeto": "Test house", "local": "Kyiv", "grelhas_x": [{"nome": "1", "pos_m": 0}, {"nome": "2", "pos_m": 8}],
         "grelhas_y": [{"nome": "A", "pos_m": 0}, {"nome": "B", "pos_m": 6}], "solo_q_adm_kpa": 200, "cota_pavimento_m": 0.0,
         "niveis": [{"nome": "GF", "cota_m": 0.0}], "sapatas": [], "pilares": [], "vigas": [],
         "sapatas_continuas": [{"ref": "SC1", "pontos": PER, "b_m": 0.6, "h_m": 0.4, "cota_topo_m": -0.8, "g_kn_m": 30, "q_kn_m": 8, "largura_muro_m": 0.2}],
         "muros": [{"pontos": PER, "espessura_m": 0.1, "cota_base_m": 0.0, "cota_topo_m": 3.0, "material": "clt"}],
         "lajes": [{"ref": "R", "piso": "cobertura", "tipo": "clt", "x0_m": 0, "y0_m": 0, "x1_m": 8, "y1_m": 6, "espessura_m": 0.16, "camadas_mm": [32] * 5,
                    "vao_m": 6.0, "cota_topo_m": 3.2, "g2_kn_m2": 1.5, "direcao_vao": "y"}]}
    d = lambda i, en, uk, t, x0, y0, x1, y1, ap=(), j=0.0, por=None: {  # noqa: E731
        "id": i, "nome_en": en, "nome_uk": uk, "tipo": t, "cota": 0.0, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "pe_direito": 2.7, "aquecida": True,
        "janelas_m2": j, "aparelhos": [dict(tipo=a[0], x=a[1], y=a[2]) for a in ap], "porta": por, "revestimento": "ceramico" if t == "casa_de_banho" else None}
    m["divisoes"] = [d("1", "Living", "Вітальня", "sala", 0.1, 0.1, 5.0, 5.9, j=6, por=(5.0, 3.0)),
                     d("2", "Kitchen", "Кухня", "cozinha", 5.1, 3.0, 7.9, 5.9, ap=[("lava_loica", 7.6, 4.5), ("maquina_lavar_loica", 7.6, 5.2)], por=(5.1, 4.0)),
                     d("3", "Bathroom", "Санвузол", "casa_de_banho", 5.1, 0.1, 7.9, 2.9, ap=[("autoclismo", 7.6, 0.5), ("lavatorio", 7.6, 1.5), ("chuveiro", 6.0, 0.6)],
                       por=(5.1, 2.0))]
    m["mep"] = {"cidade_ua": "kyiv", "U": {"parede": 0.25, "cobertura": 0.15, "pavimento_enu": 0.3, "janela": 1.0},
                "niveis": [{"cota": 0.0, "en": "Ground floor", "uk": "Перший поверх", "contorno": PER}], "quadro": {"cota": 0.0, "x": 5.2, "y": 2.9},
                "central": {"cota": 0.0, "x": 7.5, "y": 2.6}, "coluna_agua": {"x": 5.3, "y": 2.8}, "entrada_agua": {"cota": 0.0, "x": 7.9, "y": 2.5},
                "coletores": [{"cota": 0.0, "x": 5.2, "y": 2.5}], "prumadas": [{"id": "TQ1", "x": 7.7, "y": 2.8}], "saida_esgoto": {"x": 9.0, "y": 2.8},
                "unidade_exterior": {"x": 7.0, "y": -1.0}}
    return m


def test_calculo_e_quantidades():
    m = _modelo()
    r = especialidades.calcular(m)
    assert 2000 < r["phi_total_w"] < 9000 and set(r["phi"]) == {"1", "2", "3"}
    q = r["quantidades"]
    assert q["tomadas"] > 5 and q["pontos_luz"] >= 3 and q["circuitos"] >= 5
    assert q["aparelhos"] == {"lava_loica": 1, "maquina_lavar_loica": 1, "autoclismo": 1, "lavatorio": 1, "chuveiro": 1}
    assert q["piso_radiante_m2"] > 30 and q["circuitos_pr"] >= 3 and q["bc_kw"] >= 6
    assert any(k.startswith("Ø110") for k in q["tubo_pvc_m"])        # sanita → Ø110 (ou Ø90) até ao tubo de queda


def test_parede_exterior_e_area_sob():
    d = {"x0": 0, "y0": 0, "x1": 4, "y1": 3}
    assert abs(especialidades.parede_exterior(d, PER) - 7.0) < 1e-6
    assert abs(especialidades.area_sob(d, [[2, 0], [4, 0], [4, 3], [2, 3], [2, 0]]) - 6.0) < 0.2


def test_planos_en_uk_sem_mistura():
    m = _modelo()
    r = especialidades.calcular(m)
    ver = gros_oeuvre.verificar(m)
    for lg in ("en", "uk"):
        pdf = planos_especialidades.planos(m, r, ver, "09/11/2026", lg)
        d = pymupdf.open(stream=pdf, filetype="pdf")
        t = "".join(p.get_text() for p in d)
        assert len(d) == 1 * 2 + 2 + 1 + 1 + 1                         # EL, WS por piso + esquemas + HT + HT esquema + GO-09
        assert "EL-01" in t and "WS-02" in t and "HT-01" in t and "GO-09" in t
        if lg == "en":
            assert not re.search(r"[А-Яа-яІіЇїЄєҐґ]{4,}", t.replace("ДБН", "").replace("ДСТУ", ""))
        assert "Iluminação" not in t and "Tomadas" not in t


def test_orcamento_detalhado():
    m = _modelo()
    r = especialidades.calcular(m)
    gros_oeuvre.verificar(m)
    dv = devis_ua.build(m, r, planos_especialidades.conectores(m), {"fachada_m2": 70, "cobertura_m2": 48, "vidro_alu_m2": 4, "vidro_pvc_m2": 4,
                                                                     "terraco_m2": 0, "portas_int": 2, "escadas": 0})
    lots = [lt[0] for lt, _ in dv["lots"]]
    assert any(l.startswith("5. Electrical") for l in lots) and any(l.startswith("7. Heating") for l in lots)
    assert abs(dv["ttc"] - dv["ht"] * 1.2) < 1 and dv["parte_fonte"] > 0.3
    for lg in ("en", "uk"):
        pdf = devis_ua.pdf(dv, lg, "Test", "Kyiv")
        t = "".join(p.get_text() for p in pymupdf.open(stream=pdf, filetype="pdf"))
        assert ("ПДВ 20 %" in t) if lg == "uk" else ("VAT 20 %" in t)
