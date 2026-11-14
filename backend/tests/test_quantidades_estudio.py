"""14/11: mapa de quantidades ao vivo do Estúdio — tudo medido na casa editada e decomposto até aos parafusos."""
from engines.mapa_materiais import mapa
from engines.urbanismo_pt.auto import plantas as PL, programa as PG, quantidades_estudio as QE

VOL = {"shape": "l", "footprint_l_m": 15, "footprint_w_m": 12, "levels": 2, "storey_h_m": 3, "setback_side_m": 4, "setback_front_m": 6,
       "plot_l_m": 40, "plot_w_m": 40, "blocks": [{"name": "Garagem", "l_m": 6, "w_m": 5.5, "x_m": 20, "y_m": 6, "h_m": 3}]}
VAOS = [{"fachada": "frente", "piso": 0, "tipo": "envidracado", "x0": 6, "x1": 10, "z0": 0, "z1": 2.4},
        {"fachada": "frente", "piso": 1, "tipo": "janela", "x0": 12, "x1": 13.2, "z0": 3.9, "z1": 5.3}]


def _r(estilo):
    pl = PL.distribuir(VOL, PG.programa("T3", 2, False, 0), "frente", "esquerda")
    return QE.calcular(VOL, estilo, VAOS, {"pisos": pl["pisos"], "casa_rect": pl["casa_rect"]})


def test_medido_na_casa_e_tudo_decomposto():
    for est in ({"fachada": "reboco_branco", "telhado": "duas_aguas"}, {"fachada": "misto_madeira_reboco", "telhado": "plana"},
                {"fachada": "granito", "telhado": "quatro_aguas", "cobertura": "zinco"}):
        r = _r(est)
        assert r["resumo"]["area_implantacao_m2"] == 15 * 12 - 15 * 0.45 * 12 * 0.45     # L: retângulo − recorte
        assert abs(r["resumo"]["vaos_m2"] - (4 * 2.4 + 1.2 * 1.4)) < 1e-6
        assert r["estrutura"] and r["estrutura"].get("pilares")
        m = mapa(r["linhas"])
        assert m["contagem"]["parcial"] == m["contagem"]["sem_receita"] == m["contagem"]["global"] == 0, \
            [a["designacao"] for a in m["artigos"] if a["estado"] not in ("completo", "hipotese")]
        nomes = {t["material"] for t in m["totais"]}
        assert any("Parafuso" in x or "Prego" in x or "Bucha" in x for x in nomes)


def test_anexo_e_caixilharia_contados():
    r = _r({"fachada": "reboco_branco", "telhado": "duas_aguas"})
    des = [l["designation"] for l in r["linhas"]]
    assert any("Garagem" in d for d in des) and any("400x240" in d for d in des) and any("120x140" in d for d in des)
