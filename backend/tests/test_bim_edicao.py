"""Edição do modelo de edifício: as mesmas operações para o editor por opções e por prompt."""
import asyncio
import json
import math

from engines.bim_core import edicao as E
from engines.bim_core.model import BuildingModel, Footing, Opening, Slab, Wall


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


def test_prompt_de_sapata_respeita_selecao_e_pede_medida():
    m = casa()
    m.footings = [Footing("S1", 0, 0, 1.2, 0.8, 0.35), Footing("S2", 4, 0, 1.0, 0.7, 0.30)]
    selected = {"grupo": "footings", "id": "S1"}
    ops, resto, prompts = E.interpretar_selecao("Aumentar o comprimento das sapatas", m, selected)
    assert not ops and not resto and prompts[0]["pedir_medida"]
    ops, resto, prompts = E.interpretar_selecao("Aumentar o comprimento das sapatas em 20 cm", m, selected)
    assert not resto and not prompts
    edited, feito, erros = E.aplicar(m, ops)
    assert not erros and "S1: 1.20" in feito[0]
    assert edited.footings[0].dx == 1.4 and edited.footings[1].dx == 1.0 and m.footings[0].dx == 1.2
    ops, _, _ = E.interpretar_selecao("Reduz a largura de todas as sapatas em 10%", m, selected)
    batch, _, erros = E.aplicar(m, ops)
    assert not erros and [round(foot.dy, 2) for foot in batch.footings] == [0.72, 0.63]


def test_prompt_de_parede_selecionada_preserva_vaos_e_pode_mover():
    m = casa()
    selected = {"grupo": "walls", "id": "V1"}
    ops, resto, prompts = E.interpretar_selecao("Muda o comprimento para 1,50 m", m, selected)
    assert not resto and not prompts
    edited, feito, erros = E.aplicar(m, ops)
    assert not feito and "não cabe" in erros[0] and edited.walls[0].length == 8
    ops, resto, prompts = E.interpretar_selecao("Desloca esta parede 25 cm para a esquerda", m, selected)
    moved, feito, erros = E.aplicar(m, ops)
    assert not resto and not prompts and not erros and moved.walls[0].x1 == -0.25
    assert moved.openings[0].wall_id == "V1" and moved.openings[0].offset == m.openings[0].offset


def test_prompt_ambiguo_sem_selecao_nao_muda_o_modelo():
    m = casa()
    m.footings = [Footing("S1", 0, 0, 1.2, 0.8, 0.35)]
    ops, resto, prompts = E.interpretar_selecao("Aumenta o comprimento das sapatas em 20 cm", m)
    assert not ops and not resto and "Selecione" in prompts[0]["mensagem"]


def test_revestimento_faxadas_com_erro_de_escrita_altera_apenas_exteriores():
    m = casa()
    selected = {"grupo": "openings", "id": "J1"}
    ops, resto, prompts = E.interpretar_selecao("faz o revestimento das faxadas em madeira", m, selected)
    assert not resto and not prompts
    edited, feito, erros = E.aplicar(m, ops)
    assert not erros and "madeira" in feito[0]
    assert edited.params["revestimentos"] == {"V1": "madeira", "V2": "madeira"}
    assert all(w.load_bearing == before.load_bearing for w, before in zip(edited.walls, m.walls))


def test_prompt_real_de_ceramica_mantem_o_recorte_do_l_e_a_laje_estrutural():
    from ifcopenshell import geom
    from ifcopenshell.util import element
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union
    from engines.bim_core import ifc_builder

    m = casa()
    slab = m.slabs[0]
    slab.name = "Piso térreo"
    slab.points = [(0, 0), (6, 0), (6, 5), (12, 5), (12, 10), (0, 10)]
    m.slabs.append(Slab("L2", "Primeiro piso", [(0, 0), (3, 0), (3, 3), (0, 3)], .18, None))
    selection = {"grupo": "slabs", "id": "L1"}
    ops, rest, messages = E.interpretar_selecao("mete ceramica no piso terreo", m, selection)
    assert ops and not rest and not messages
    edited, done, errors = E.aplicar(m, ops)
    assert done and not errors and edited.slabs == m.slabs
    assert edited.params["pavimentos"] == {"L1": {"material": "ceramica", "espessura": None}}
    model = ifc_builder.build_ifc(E.de_dict(json.loads(json.dumps(E.para_dict(edited)))))
    assert not ifc_builder.validate(model)
    covering, = model.by_type("IfcCovering")
    assert covering.PredefinedType == "FLOORING"
    assert element.get_material(covering).Name == "Cerâmica"
    assert element.get_psets(covering)["Qto_CoveringBaseQuantities"]["NetArea"] == 90
    assert element.get_psets(covering)["CP_Acabamento"]["EspessuraDefinida"] is False
    # Keep the parent shape alive while reading the geometry in IfcOpenShell.
    result = geom.create_shape(geom.settings(), covering)
    points = list(zip(*[iter(result.geometry.verts)]*3))
    faces = list(zip(*[iter(result.geometry.faces)]*3))
    outline = unary_union([Polygon([points[i][:2] for i in face]) for face in faces])
    assert outline.equals(Polygon(slab.points)) and not outline.covers(Point(9, 2))
    slab_ifc = model.by_guid(ifc_builder.stable_guid("p", 0, "IfcSlab", "L1"))
    assert element.get_material(slab_ifc).Name == "Betão armado C25/30"
    assert element.get_psets(slab_ifc)["Qto_SlabBaseQuantities"]["Depth"] == .20


def test_acabamentos_podem_ser_combinados_sem_editar_o_piso_errado():
    m = casa()
    m.slabs[0].name = "Primeiro piso"
    ops, rest, messages = E.interpretar_selecao("mete cerâmica no piso térreo", m, {"grupo": "slabs", "id": "L1"})
    assert not ops and not rest and messages
    ops, rest, messages = E.interpretar_selecao("mete cerâmica no chão da cozinha", m, {"grupo": "slabs", "id": "L1"})
    assert not ops and not rest and messages
    ops, rest, messages = E.interpretar_selecao("Põe grés porcelânico no primeiro piso e pinta V2 de verde-sálvia", m)
    assert len(ops) == 2 and not rest and not messages
    edited, _, errors = E.aplicar(m, ops)
    assert not errors and edited.params["cores_parede"] == {"V2": "#8a9b83"}
    assert edited.params["pavimentos"]["L1"]["material"] == "porcelanato"


def test_ia_compila_mais_do_que_uma_operacao_e_recusa_medidas_ou_alvos_inventados():
    from engines.bim_core import prompt

    m = casa()
    m.slabs[0].name = "Piso térreo"
    m.walls[0].load_bearing = True
    selected = {"grupo": "walls", "id": "V1"}
    action = {"op": "dimensao", "grupo": "walls", "alvo": "selecionado", "campo": "espessura",
              "modo": "relativo", "medida": "5 cm"}
    floor = {"op": "pavimento", "alvo": "L1", "material": "ceramica"}
    text = "Engrossa esta parede em 5 cm e troca o acabamento do piso térreo por cerâmica"

    async def invalid(*args, **kwargs):
        return json.dumps({"operacoes": [action | {"medida": "50 cm"}, floor]})

    async def valid(*args, **kwargs):
        return json.dumps({"operacoes": [action, floor]})

    ops, clarifications = asyncio.run(prompt.interpret(text, m, selected, [invalid, valid]))
    assert not clarifications and len(ops) == 2
    edited, done, errors = E.aplicar(m, ops)
    assert len(done) == 2 and not errors and edited.walls[0].thickness == .25
    assert asyncio.run(prompt.interpret(text, m, selected, [invalid])) == ([], [])
    assert asyncio.run(prompt.interpret("Engrossa a parede V2 em 5 cm", m, selected, [valid])) == ([], [])

    async def alternate_envelope(*args, **kwargs):
        return '{"operacoes":[{"tipo":"parede_pintar","alvo":"V1","cor":"verde salvia"}],"pergunta":""}'

    ops, questions = asyncio.run(prompt.interpret("Queria esta parede num verde-sálvia discreto", m, selected,
                                                [alternate_envelope]))
    assert not questions and ops[0]["cor"] == "#8a9b83" and ops[0]["ids"] == ["V1"]


def test_ifc_janela_e_porta_tem_acabamentos_distintos_e_conservam_os_vaos():
    from engines.bim_core import ifc_builder

    m = casa()
    m.openings.append(Opening("D1", "porte", "V2", 1., .9, 0., 2.1))
    model = ifc_builder.build_ifc(m)
    assert not ifc_builder.validate(model)
    window, = model.by_type("IfcWindow")
    door, = model.by_type("IfcDoor")

    def styles(product):
        return {styled.Styles[0].Name for item in product.Representation.Representations[0].Items for styled in item.StyledByItem}

    assert styles(window) == {"Caixilharia antracite", "Vidro"}
    assert styles(door) == {"Caixilharia antracite", "Folha de madeira", "Ferragens acetinadas"}
    glass = next(style for style in model.by_type("IfcSurfaceStyle") if style.Name == "Vidro")
    assert 0 < glass.Styles[0].Transparency < 1
    assert (window.OverallWidth, window.OverallHeight, door.OverallWidth, door.OverallHeight) == (1.2, 1.2, .9, 2.1)


def test_sapatas_lineares_seguem_a_parede_e_nao_duplicam():
    m = casa()
    sel = {"grupo": "walls", "id": "V2"}
    ops, rest, messages = E.interpretar_selecao("criar sapatas lineares", m, sel)
    assert not ops and not rest and "largura e a altura" in messages[0]["mensagem"]
    ops, rest, messages = E.interpretar_selecao("criar sapata linear com 60 cm de largura e 35 cm de altura", m, sel)
    assert not rest and not messages
    edited, done, errors = E.aplicar(m, ops)
    assert done and not errors
    item = edited.footings[0]
    assert (item.wall_id, item.cx, item.cy, item.dx, item.dy, item.depth, item.angle) == (
        "V2", 8, 3, 6, 0.60, 0.35, math.pi / 2,
    )
    duplicated, done, errors = E.aplicar(edited, ops)
    assert not done and errors and len(duplicated.footings) == 1


def test_comando_ao_longo_das_fachadas_aceita_frase_em_duas_linhas():
    ops, resto, mensagens = E.interpretar_selecao("criar sapatas\na toda a longura das façadas", casa())
    assert not ops and not resto
    assert len(mensagens) == 1 and "largura e a altura" in mensagens[0]["mensagem"]
    assert E.mesmas_medidas("queria pôr mais 5 cm", "aumenta a espessura em 5 cm")
    assert not E.mesmas_medidas("queria pôr mais 5 cm", "aumenta a espessura em 50 cm")


def test_sapata_ate_ao_limite_usa_a_parede_alinhada():
    m = casa()
    m.footings.append(Footing("S1", 2, 0, 1.2, 0.8, 0.35))
    ops, resto, prompts = E.interpretar_selecao("aumentar au limite da casa", m, {"grupo": "footings", "id": "S1"})
    novo, feito, erros = E.aplicar(m, ops)
    assert not (resto or prompts or erros)
    assert feito and (novo.footings[0].cx, novo.footings[0].dx, novo.footings[0].dy) == (4, 8, 0.8)


def test_quatro_cantos_sao_os_cantos_reais_do_contorno():
    m = casa()
    m.footings.append(Footing("S1", 2, 0, 1.2, 0.8, 0.35))
    ops, _, _ = E.interpretar_selecao("nos quatro cantos", m, {"grupo": "footings", "id": "S1"})
    novo, feito, erros = E.aplicar(m, ops)
    assert feito and not erros
    assert {(f.cx, f.cy) for f in novo.footings[1:]} == {(0, 0), (8, 0), (8, 6), (0, 6)}
    m.slabs[0].points = [(0, 0), (4, 0), (4, 3), (8, 3), (8, 6), (0, 6)]
    novo, feito, erros = E.aplicar(m, ops)
    assert not feito and len(novo.footings) == 1 and "6 cantos" in erros[0]
