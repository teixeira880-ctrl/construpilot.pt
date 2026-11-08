"""Piloto automático v2 — pedidos em linguagem corrente: forma em L, área habitável, piscina, garagem exterior, estilos.
Sem rede: reutiliza o transporte simulado dos testes do piloto automático."""
import pytest

from engines.urbanismo_pt.auto import coerencia as C
from engines.urbanismo_pt.auto import estilos as E
from engines.urbanismo_pt.auto import pedido as PD
from engines.urbanismo_pt.auto import pipeline as P
from engines.urbanismo_pt.auto import programa as PG
from engines.urbanismo_pt.auto import dgt_cache as CACHE
from engines.urbanismo_pt import pdf as UP
from engines.urbanismo_pt import volumes as V

import test_urbanismo_auto as BASE   # transporte simulado (Braga, 6 % de declive)

PEDIDO_CLIENTE = ("cria um dossier completo para entregar à camara municipal, eu quero uma casa terrea em L com 200m2 "
                  "habitaveis piscina e garagem exterior terreno de 1500m2 faxadas revistadas em granito e madeira, "
                  "o endereço é: Rua do Monte 7, Padim da Graça, Braga")


@pytest.fixture(autouse=True)
def _copia(tmp_path):
    CACHE.usar_pasta(str(tmp_path / "dgt"))
    yield


def test_leitura_do_pedido_do_cliente():
    d = P.interpretar_pedido(PEDIDO_CLIENTE)
    assert d["pisos"] == 1 and d["forma"] == "l" and d["piscina"] is True
    assert d["garagem"] is True and d["garagem_tipo"] == "exterior"
    assert d["area_util_alvo_m2"] == 200 and d["area_terreno_m2"] == 1500   # nunca confunde casa e terreno
    assert "granito" in d["fachada"] and "madeira" in d["fachada"]
    assert d["morada"].startswith("Rua do Monte 7")


@pytest.mark.parametrize("txt,esperado", [
    ("casa com 180 m2 habitáveis", {"area_util_alvo_m2": 180}),
    ("terreno de 1.200 m² e casa de 150 m2", {"area_terreno_m2": 1200, "area_util_alvo_m2": 150}),
    ("lote com 900 m2", {"area_terreno_m2": 900}),
    ("moradia de 3 quartos com piscina 10x4", {"tipologia": "T3", "piscina_l_m": 10, "piscina_w_m": 4}),
    ("casa alentejana caiada", {"estilo": "alentejano"}),
    ("quero renovar a casa da minha avó", {"tipo_obra": "renovacao"}),
    ("cobertura plana, estilo contemporâneo", {"cobertura_tipo": "plana", "estilo": "contemporaneo"}),
])
def test_leitura_varia(txt, esperado):
    d = PD.interpretar(txt)
    for k, v in esperado.items():
        assert d.get(k) == v, (k, d)


def test_estilo_nao_vem_da_morada():
    assert "estilo" not in PD.interpretar("moradia T3 na Rua do Monte 5, Braga")
    assert PD.interpretar("casa estilo antigo")["estilo"] == "tradicional_portugues"
    assert len(E.lista()) >= 8 and E.obter("inexistente")["id"] == E.ESTILO_PADRAO


def test_programa_ajusta_area_habitavel():
    p = PG.programa("T4", 1, True, 2, area_util_alvo=200)
    assert p["ajuste_area"]["obtido_util_m2"] == pytest.approx(200, abs=2)
    sala = next(r for r in p["compartimentos"] if r["tipo"] == "sala")
    assert sala["area_projeto_m2"] > PG.CONFORTO["sala"][4]
    pequeno = PG.programa("T3", 1, False, 0, area_util_alvo=70)   # pedido abaixo do confortável: mínimos do RGEU respeitados
    for r in pequeno["compartimentos"]:
        if r.get("minimo_m2"):
            assert r["area_projeto_m2"] >= r["minimo_m2"]


def test_pedido_do_cliente_de_a_a_z():
    r = BASE.run({"texto": PEDIDO_CLIENTE})
    assert r["ok"] and r["estado"] == "pronto", (r.get("estado"), r.get("coerencia"))
    a, v, q = r["processo"]["auto"], r["processo"]["volume"], r["verificacao"]["quadro"]
    # forma em L, térrea, com a área pedida
    assert a["forma"] == "l" and v["shape"] == "l" and v["levels"] == 1
    assert a["ajuste_area"]["obtido_util_m2"] == pytest.approx(200, abs=2)
    contorno = V.building_polygons(v)[0]["pts"]
    assert len(contorno) == 6
    # garagem independente: afastada da casa, sem tocar no L
    from shapely.geometry import Polygon, box
    g = v["blocks"][0]
    casa = Polygon(contorno)
    gar = box(g["x_m"], g["y_m"], g["x_m"] + g["l_m"], g["y_m"] + g["w_m"])
    assert casa.distance(gar) >= 1.5 - 1e-6 and "independente" in g["name"]
    # piscina dentro do terreno, afastada dos limites e da casa, fora da área de implantação
    pi = a["piscina"]
    pool = box(pi["x_m"], pi["y_m"], pi["x_m"] + pi["l_m"], pi["y_m"] + pi["w_m"])
    terreno = Polygon(a["terreno"]["poligono_m"])
    assert terreno.buffer(-2.0, join_style=2).contains(pool) and pool.distance(casa) >= 2.0 - 1e-6
    assert q["area_implantacao_m2"] == pytest.approx(casa.area + g["l_m"] * g["w_m"], rel=1e-3)
    # materiais e estilo
    assert a["materiais"]["fachada"] == "misto_granito_madeira"
    assert a["estilo"]["id"] == E.ESTILO_PADRAO
    # todos os compartimentos conformes e vãos em fachadas laterais do L
    for p in a["plantas"]["pisos"]:
        assert all(c["conforme"] for c in p["compartimentos"]), p
    assert "frente" in {x["fachada"] for x in a["vaos"]}
    # quartos da ala abrem para o pátio do L com vãos generosos (como a fachada do sol)
    pat = [x for x in a["vaos"] if x["compartimento"].startswith(("Suite", "Quarto"))]
    assert pat and all(x["fachada"] == "direita" and x["z1"] - x["z0"] >= 2.2 - 1e-6 for x in pat)
    assert all(x.get("plano_m") is not None for x in a["vaos"])
    # quartos na ala, sala no corpo
    quartos = [c for c in a["plantas"]["pisos"][0]["compartimentos"] if c["tipo"] == "quarto"]
    gl = a["geometria_l"]
    assert all(c["y0"] >= v["setback_front_m"] + gl["d1"] - 1e-3 for c in quartos)
    # memória sem números inventados e menciona as escolhas
    mem = r["processo"]["memoria_texto"]
    assert "planta em L" in mem and "Piscina descoberta" in mem and "independente" in mem
    assert not any(f["codigo"] == "MEMORIA_NUMEROS" for f in r["coerencia"]["falhas"])
    # peças desenhadas geradas (incl. planta do piso com o contorno em L)
    ds = UP.desenhos(r["processo"], None)
    assert {"PLANTA_IMPLANTACAO", "PLANTAS_PISOS", "ALCADOS", "CORTES"} <= {d["code"] for d in ds}


def test_l_que_nao_cabe_passa_a_retangular():
    r = BASE.run({"texto": "casa térrea em L com 260 m2 habitáveis, terreno de 450 m2, Rua do Monte 7, Padim da Graça, Braga"})
    if r["ok"]:
        assert r["processo"]["volume"]["shape"] == "rectangle" or r["processo"]["volume"]["levels"] == 2
        assert any("L não cabia" in x or "pisos" in x for x in r["pressupostos"])
    else:
        assert r["estado"] == "nao_cabe" and r["perguntas"]


def test_renovacao_pede_o_existente_so_em_modo_profissional():
    r = BASE.run({"texto": "quero renovar a minha casa na Rua do Monte 7, Braga", "modo_leigo": False})
    assert r["ok"] is False and r["estado"] == "renovacao" and len(r["perguntas"]) == 2


def test_modo_leigo_nunca_pergunta_o_que_pode_decidir():
    r = BASE.run({"texto": "quero renovar a minha casa na Rua do Monte 7, Padim da Graça, Braga"})
    assert r["ok"] and r["perguntas"] == [] and r["modo_leigo"]
    assert any("plantas da casa existente" in x for x in r["pressupostos"])
    assert any("nome" in x.lower() for x in r["a_completar"])          # papelada fica para depois, sem bloquear
    # casa grande demais para o terreno: reduz sozinho em vez de perguntar
    r2 = BASE.run({"texto": "moradia T5 térrea com 400 m2 habitáveis, terreno de 500 m2, Rua do Monte 7, Padim da Graça, Braga"})
    if r2["ok"]:
        assert r2["perguntas"] == [] and any("não cabia" in x or "não cabiam" in x or "pisos" in x for x in r2["pressupostos"])
    else:
        assert r2["estado"] in ("nao_cabe", "inviavel")
    # sem morada é a única coisa que pergunta
    r3 = BASE.run({"texto": "quero uma casa T3"})
    assert r3["estado"] == "falta_morada" and len(r3["perguntas"]) == 1


def test_estilo_tradicional_muda_cobertura_e_materiais():
    r = BASE.run({"texto": "moradia T3 estilo tradicional português, térrea, terreno de 1000 m2, Rua do Monte 7, Padim da Graça, Braga"})
    assert r["ok"], r
    a, v = r["processo"]["auto"], r["processo"]["volume"]
    assert a["estilo"]["id"] == "tradicional_portugues" and v["roof_type"] == "duas_aguas"
    assert a["materiais"]["cobertura"] == "telha_ceramica" and a["materiais"]["fachada"] == "misto_granito_reboco"
    r2 = BASE.run({"texto": "moradia T3 contemporânea, térrea, terreno de 1000 m2, Rua do Monte 7, Padim da Graça, Braga"})
    assert r2["processo"]["volume"]["roof_type"] == "plana" and r2["coerencia"]["ok"]


def test_numero_arredondado_com_fonte_e_aceite():
    assert C.numeros_sem_fonte("Lavandaria (5,5 m²) e I.S. (4,3 m²)", [5.54, 4.34]) == []
    assert C.numeros_sem_fonte("área de 7,9 m²", [5.54]) == ["7,9 m²"]


def test_casa_em_l_todos_os_compartimentos_tem_acesso_e_pecas_a_escala():
    """Cada compartimento abre para uma circulação (o corredor da ala nasce na circulação do corpo) e o dossier
    traz as peças de arquitetura à escala: planta com paredes e portas, cobertura, 4 alçados, 2 cortes e piscina."""
    from engines.urbanismo_pt.auto import desenho_tecnico as DT
    r = BASE.run({"texto": PEDIDO_CLIENTE})
    assert r["ok"]
    proc = r["processo"]
    comps = proc["auto"]["plantas"]["pisos"][0]["compartimentos"]
    portas = DT._portas(comps)
    # grafo de acessos: portas + ligações abertas entre sala / entrada / circulação
    lig = {c["nome"]: set() for c in comps}
    for p in portas:
        lig[p["comp"]["nome"]].add(p["para"]["nome"])
        lig[p["para"]["nome"]].add(p["comp"]["nome"])
    ab = [c for c in comps if c["tipo"] in DT.NAO_PORTA]
    for c in ab:
        for o in ab:
            if c is not o and (min(c["x1"], o["x1"]) - max(c["x0"], o["x0"]) > 0.9 and
                               (abs(c["y1"] - o["y0"]) < 1e-3 or abs(c["y0"] - o["y1"]) < 1e-3)
                               or min(c["y1"], o["y1"]) - max(c["y0"], o["y0"]) > 0.9 and
                               (abs(c["x1"] - o["x0"]) < 1e-3 or abs(c["x0"] - o["x1"]) < 1e-3)):
                lig[c["nome"]].add(o["nome"])
    entrada = next(c["nome"] for c in comps if c["tipo"] == "entrada")
    vistos, fila = {entrada}, [entrada]
    while fila:
        n = fila.pop()
        for m in lig[n] - vistos:
            vistos.add(m)
            fila.append(m)
    assert vistos == set(lig), f"sem acesso: {set(lig) - vistos}"
    pecas = DT.pecas(proc)
    codes = [p["code"] for p in pecas]
    assert codes.count("ALCADOS") == 2 and "CORTES" in codes and "PLANTA_COBERTURA" in codes and "PISCINA" in codes
    assert all(p["folha"] for p in pecas)
    ds = UP.desenhos(proc, None)
    assert any(d["filename"] == "planta_piso_0.png" for d in ds) and not any(d["filename"] == "corte_AA.png" for d in ds)


@pytest.mark.parametrize("txt,morada", [
    ("Casa em L na Rua do Monte 7, Padim da Graça, 4700-651 Braga. Dossier completo para a câmara, mesmo que pertença à REN.",
     "Rua do Monte 7, Padim da Graça, 4700-651 Braga"),
    ("quero uma casa na Av. da Liberdade 10, Lisboa. Com piscina", "Av. da Liberdade 10, Lisboa"),
    ("moradia em Rua do Monte 7, Braga, mesmo que esteja em REN", "Rua do Monte 7, Braga"),
])
def test_morada_acaba_no_fim_da_frase(txt, morada):
    assert P.interpretar_pedido(txt)["morada"] == morada
