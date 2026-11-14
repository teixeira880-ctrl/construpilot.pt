"""Assistente IA do Estúdio: só passam alterações válidas; a casa fica dentro do lote."""
from engines.urbanismo_pt.auto.estudio_ia import validar

EST = {"vol": {"plot_l_m": 30, "plot_w_m": 40, "footprint_l_m": 12, "footprint_w_m": 9, "levels": 2, "storey_h_m": 3,
               "setback_front_m": 6, "setback_side_m": 5},
       "vaos": [{"fachada": "frente", "piso": 0, "tipo": "janela", "x0": 10, "x1": 11.2}]}


def test_aceita_alteracoes_validas():
    r = validar({"vol": {"levels": 1, "footprint_l_m": 16}, "estilo": {"telhado": "plana", "fachada": "madeira", "cor_fachada": "#efe4c8"},
                 "vaos": {"acrescentar": [{"fachada": "tardoz", "piso": 0, "tipo": "envidracado", "largura_m": 4, "altura_m": 2.4}],
                          "alterar": [{"indice": 0, "largura_m": 2}]}, "resposta": "Casa térrea moderna."}, EST)
    assert r["vol"] == {"levels": 1, "footprint_l_m": 16.0}
    assert r["estilo"]["telhado"] == "plana" and r["estilo"]["cobertura"] == "plana_seixo"
    assert r["vaos"]["acrescentar"][0]["peitoril_m"] == 0.0 and r["vaos"]["alterar"] == [{"indice": 0, "largura_m": 2.0}]
    assert r["alterou"] and not r["recusas"]


def test_recusa_o_que_nao_existe_ou_nao_cabe():
    r = validar({"vol": {"footprint_l_m": 25, "levels": 9}, "estilo": {"fachada": "marmore", "cor_fachada": "rosa", "piscina": True},
                 "vaos": {"acrescentar": [{"fachada": "telhado"}, {"fachada": "frente", "piso": 3}], "remover": [7, 0]}}, EST)
    assert "footprint_l_m" not in r["vol"] and "levels" not in r["vol"]      # 25 + 2×5 > 30 ; 9 pisos fora dos limites
    assert r["estilo"] == {} and r["vaos"]["acrescentar"] == [] and r["vaos"]["remover"] == [0]
    assert any("não cabe no lote" in x for x in r["recusas"]) and len(r["recusas"]) >= 5


def test_so_resposta_quando_e_pergunta():
    r = validar({"resposta": "A casa tem 216 m² de área bruta."}, EST)
    assert not r["alterou"] and r["resposta"].startswith("A casa")


def test_forma_em_l_e_garagem_dentro_do_lote():
    r = validar({"vol": {"shape": "l", "wing_l_m": 5}, "anexos": {"acrescentar": [{"nome": "Garagem", "l_m": 6, "w_m": 5.5, "lado": "direita"},
                                                                                  {"nome": "Arrumos", "l_m": 9, "w_m": 3, "lado": "esquerda"}]}}, EST)
    assert r["vol"]["shape"] == "l" and r["vol"]["wing_l_m"] == 5.0
    assert r["vol"]["blocks"] == [{"name": "Garagem", "l_m": 6.0, "w_m": 5.5, "h_m": 3.0, "x_m": 18.0, "y_m": 6.0}]
    assert any("Arrumos" in x and "não cabe" in x for x in r["recusas"])      # 5 − 1 − 9 < 0
    assert validar({"vol": {"shape": "oval"}}, EST)["recusas"]
    r2 = validar({"anexos": {"remover_todos": True}}, {**EST, "vol": {**EST["vol"], "blocks": [{"name": "G"}]}})
    assert r2["vol"]["blocks"] == [] and r2["alterou"]
