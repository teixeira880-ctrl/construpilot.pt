"""Edição do modelo de edifício: as mesmas operações para o editor por opções e por prompt."""
import json

from engines.bim_core import edicao as E
from engines.bim_core.model import BuildingModel, Opening, Slab, Wall


def casa():
    m = BuildingModel(plan_id="p", page_index=0, storey_name="RC", params={"wall_height": 2.7})
    m.walls += [Wall("V1", 0, 0, 8, 0, 0.20, 2.7, True), Wall("V2", 8, 0, 8, 6, 0.20, 2.7, True), Wall("C1", 4, 0, 4, 6, 0.10, 2.7, False)]
    m.openings.append(Opening("J1", "fenetre", "V1", 1.0, 1.2, 0.9, 1.2))
    m.slabs.append(Slab("L1", "Laje", [(0, 0), (8, 0), (8, 6), (0, 6)], 0.20, None))
    return m


def test_ida_e_volta_em_json_e_original_intacto():
    m = casa()
    d = json.loads(json.dumps(E.para_dict(m)))
    assert E.para_dict(E.de_dict(d)) == E.para_dict(m)
    novo, feito, erros = E.aplicar(m, [{"op": "parede_alterar", "id": "V1", "espessura": 0.25}])
    assert not erros and feito == ["Parede «V1»: espessura 25 cm."]
    assert novo.walls[0].thickness == 0.25 and m.walls[0].thickness == 0.20


def test_operacoes_de_paredes_e_vaos():
    m, feito, erros = E.aplicar(casa(), [
        {"op": "parede_criar", "x1": 0, "y1": 6, "x2": 8, "y2": 6, "espessura": 0.2, "resistente": True},
        {"op": "vao_criar", "parede": "P1", "tipo": "porta", "largura": 0.9, "offset": 2.0},
        {"op": "vao_criar", "parede": "V2", "tipo": "janela", "largura": 1.5},
        {"op": "parede_mover", "id": "C1", "dx": 0.5},
        {"op": "material", "id": "V1", "material": "Bloco térmico 20"},
        {"op": "pe_direito", "altura": 2.8}])
    assert not erros and len(feito) == 6
    assert [w.source_id for w in m.walls] == ["V1", "V2", "C1", "P1"] and all(w.height == 2.8 for w in m.walls)
    porta = next(v for v in m.openings if v.wall_id == "P1")
    assert (porta.kind, porta.sill, porta.height) == ("porte", 0.0, 2.1)
    janela = next(v for v in m.openings if v.wall_id == "V2")
    assert janela.offset == 2.25 and janela.sill == 0.9                       # centrada na parede de 6 m
    assert m.walls[2].x1 == 4.5 and m.params["materiais"] == {"V1": "Bloco térmico 20"}
    m2, feito, erros = E.aplicar(m, [{"op": "parede_apagar", "id": "P1"}])
    assert "com os seus 1 vão(s)" in feito[0] and all(v.wall_id != "P1" for v in m2.openings)


def test_operacoes_recusadas_dizem_porque_e_nao_deixam_nada_a_meio():
    m, feito, erros = E.aplicar(casa(), [
        {"op": "vao_criar", "parede": "V1", "tipo": "janela", "largura": 1.0, "offset": 1.5},      # sobrepõe J1
        {"op": "vao_criar", "parede": "V1", "tipo": "porta", "largura": 0.9, "offset": 7.5},       # sai da parede
        {"op": "parede_alterar", "id": "V1", "espessura": 2.0},                                    # fora dos limites
        {"op": "parede_alterar", "id": "V1", "x2": 2.0},                                           # J1 deixaria de caber
        {"op": "pe_direito", "altura": 2.0},                                                       # J1 chega a 2,1 m
        {"op": "parede_apagar", "id": "ZZ"}, {"op": "voar"}, {"op": "vao_criar", "parede": "V1"}])
    assert not feito and len(erros) == 8 and E.para_dict(m) == E.para_dict(casa())
    assert "sobrepõe-se" in erros[0] and "não cabe" in erros[1] and "fora dos limites" in erros[2] and "não cabe" in erros[3]
    assert "Não existe a parede «ZZ»" in erros[5] and "desconhecida" in erros[6] and "dados em falta" in erros[7]


def test_frases_correntes_viram_operacoes():
    m = casa()
    ops, resto = E.interpretar("Muda a espessura da parede v1 para 25 cm; acrescenta uma janela de 1,20 m na parede V2 a 2 m do início. "
                               "Pé-direito 2,80; move a parede c1 50 cm para a direita; divisórias com 12 cm; apaga a janela J1; pinta tudo de azul", m)
    assert ops == [{"op": "parede_alterar", "id": "V1", "espessura": 0.25},
                   {"op": "vao_criar", "tipo": "janela", "largura": 1.2, "parede": "V2", "offset": 2.0},
                   {"op": "pe_direito", "altura": 2.8}, {"op": "parede_mover", "id": "C1", "dx": 0.5, "dy": 0},
                   {"op": "paredes_espessura", "espessura": 0.12, "resistente": False}, {"op": "vao_apagar", "id": "J1"}]
    assert resto == ["pinta tudo de azul"]
    novo, feito, erros = E.aplicar(m, ops)
    assert not erros and len(feito) == 6 and novo.walls[2].thickness == 0.12 and len(novo.openings) == 1
