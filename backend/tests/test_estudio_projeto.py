"""Estúdio de Projeto — modelo único: medições exatas, cobertura, peças desenhadas e rotas (coleções em memória)."""
import math
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_estudio_projeto")
os.environ.setdefault("JWT_SECRET", "test")

from engines import estudio_projeto as EP  # noqa: E402
from engines.estudio_projeto import desenhos as D  # noqa: E402

H = 0.15  # meia espessura da parede exterior de 30 cm


def casa(L=10.0, W=8.0, piso="p0", pre=""):
    return [{"id": pre + "f", "piso": piso, "a": [H, H], "b": [L - H, H], "tipo": "ext_30"},
            {"id": pre + "d", "piso": piso, "a": [L - H, H], "b": [L - H, W - H], "tipo": "ext_30"},
            {"id": pre + "t", "piso": piso, "a": [L - H, W - H], "b": [H, W - H], "tipo": "ext_30"},
            {"id": pre + "e", "piso": piso, "a": [H, W - H], "b": [H, H], "tipo": "ext_30"},
            {"id": pre + "i", "piso": piso, "a": [4.0, H], "b": [4.0, W - H], "tipo": "int_12"}]


def modelo(**kw):
    m = {"pisos": [{"id": "p0"}], "paredes": casa(),
         "vaos": [{"id": "v1", "parede": "f", "tipo": "porta", "pos_m": 2.0},
                  {"id": "v2", "parede": "f", "tipo": "janela", "pos_m": 7.0},
                  {"id": "v3", "parede": "i", "tipo": "porta", "pos_m": 3.0}],
         "cobertura": {"tipo": "duas_aguas", "inclinacao_graus": 30, "beiral_m": 0.5},
         "rotulos": [{"piso": "p0", "x": 2, "y": 4, "nome": "Sala"}]}
    m.update(kw)
    return EP.normalizar(m)


def test_areas_e_paredes_sem_contar_encontros_duas_vezes():
    d = EP.derivar(modelo())
    assert d["ok"] and not d["erros"]
    assert d["pisos"][0]["area_bruta_m2"] == 80.0                     # 10 × 8 pelas faces exteriores
    div = {x["nome"]: x for x in d["divisoes"]}
    assert div["Sala"]["area_m2"] == pytest.approx(3.64 * 7.40, abs=0.01)       # entre faces
    outra = next(x for x in d["divisoes"] if x["nome"] != "Sala")
    assert outra["area_m2"] == pytest.approx(5.64 * 7.40, abs=0.01)
    par = {p["id"]: p for p in d["medicoes"]["paredes"]}
    # a planta das paredes é exatamente a área bruta menos as divisões: nada contado duas vezes
    planta_paredes = sum(p["comprimento_liquido_m"] * p["espessura_m"] for p in par.values())
    assert planta_paredes == pytest.approx(80.0 - 3.64 * 7.40 - 5.64 * 7.40, abs=0.01)
    assert par["i"]["comprimento_liquido_m"] == pytest.approx(7.40, abs=0.001)   # entre faces das exteriores
    assert par["f"]["area_vaos_m2"] == pytest.approx(0.9 * 2.1 + 1.2 * 1.2, abs=0.01)
    assert par["f"]["area_liquida_m2"] == pytest.approx(par["f"]["comprimento_liquido_m"] * 2.7 - 3.33, abs=0.01)
    cam = par["f"]["camadas"]
    assert sum(c["volume_m3"] for c in cam) == pytest.approx(par["f"]["volume_m3"], abs=0.002)
    # paredes da sala: perímetro × pé-direito menos a porta de entrada e a porta interior
    assert div["Sala"]["area_paredes_m2"] == pytest.approx(2 * (3.64 + 7.40) * 2.7 - 2 * 0.9 * 2.1, abs=0.02)
    assert div["Sala"]["rodape_m"] == pytest.approx(2 * (3.64 + 7.40) - 1.8, abs=0.01)


@pytest.mark.parametrize("tipo,n_faces,n_empenas", [("duas_aguas", 2, 2), ("quatro_aguas", 4, 0), ("uma_agua", 1, 3), ("plana", 0, 0)])
def test_cobertura(tipo, n_faces, n_empenas):
    d = EP.derivar(modelo(cobertura={"tipo": tipo, "inclinacao_graus": 30, "beiral_m": 0.5}))
    c, md = d["cobertura"], d["medicoes"]["cobertura"]
    assert len(c["faces"]) == n_faces and len(c["empenas"]) == n_empenas
    z_topo = 2.70 + 0.25
    if tipo == "plana":
        assert md["area_m2"] == 80.0
        return
    assert md["area_planta_m2"] == pytest.approx(11 * 9, abs=0.02)             # contorno + beiral de 0,5 m
    assert md["area_m2"] == pytest.approx(99 / math.cos(math.radians(30)), abs=0.05)
    vao = 8.5 if tipo == "uma_agua" else 4.0      # uma água: o ponto mais alto é o beiral do lado alto
    assert c["z_cumeeira"] == pytest.approx(z_topo + math.tan(math.radians(30)) * vao, abs=0.005)
    if tipo == "duas_aguas":
        assert md["empenas_m2"] == pytest.approx(2 * 0.5 * 8 * math.tan(math.radians(30)) * 4, abs=0.02)
    for f in c["faces"]:                                                        # o plano passa no topo da parede exterior
        assert min(p[2] for p in f["pts"]) == pytest.approx(z_topo - math.tan(math.radians(30)) * 0.5, abs=0.005)


def test_cobertura_inclinada_em_planta_com_reentrancia_nao_e_inventada():
    L = [{"id": f"w{i}", "piso": "p0", "a": a, "b": b, "tipo": "ext_30"} for i, (a, b) in enumerate(
        [([0, 0], [10, 0]), ([10, 0], [10, 4]), ([10, 4], [5, 4]), ([5, 4], [5, 8]), ([5, 8], [0, 8]), ([0, 8], [0, 0])])]
    d = EP.derivar(modelo(paredes=L, vaos=[], rotulos=[]))
    assert not d["cobertura"]["faces"] and any(a["codigo"] == "COBERTURA_FORMA" for a in d["avisos"])
    plana = EP.derivar(modelo(paredes=L, vaos=[], rotulos=[], cobertura={"tipo": "plana"}))
    assert plana["medicoes"]["cobertura"]["area_m2"] == plana["pisos"][0]["area_bruta_m2"]


def test_vaos_invalidos_sao_assinalados_e_nao_descontados():
    m = modelo(vaos=[{"id": "a", "parede": "f", "tipo": "janela", "pos_m": 0.3},                 # sai da parede
                     {"id": "b", "parede": "f", "tipo": "janela", "pos_m": 5.0},
                     {"id": "c", "parede": "f", "tipo": "janela", "pos_m": 5.5},                 # sobrepõe-se a «b»
                     {"id": "e", "parede": "f", "tipo": "porta", "pos_m": 8.0, "altura_m": 3.2}])  # mais alta do que a parede
    d = EP.derivar(m)
    assert not d["ok"] and {e["id"] for e in d["erros"]} == {"a", "c", "e"}
    f = next(p for p in d["medicoes"]["paredes"] if p["id"] == "f")
    assert f["area_vaos_m2"] == pytest.approx(1.44, abs=0.001)


def test_dois_pisos_cotas_e_lajes():
    m = modelo(pisos=[{"id": "p0"}, {"id": "p1", "laje_m": 0.30}], paredes=casa() + casa(piso="p1", pre="s"), vaos=[], rotulos=[])
    d = EP.derivar(m)
    assert [p["z0"] for p in d["pisos"]] == [0.0, 3.0] and d["pisos"][1]["z1"] == 5.7
    nomes = [x["nome"] for x in d["medicoes"]["lajes"]]
    assert nomes == ["Laje térrea", "Laje do 1.º andar", "Laje de cobertura"]
    assert d["cobertura"]["z_topo_paredes"] == pytest.approx(5.95)
    assert d["medicoes"]["totais"]["area_bruta_construcao_m2"] == 160.0


def test_normalizar_recusa_estrutura_invalida():
    for mau in ({}, {"pisos": []}, {"pisos": [{"id": "p0"}], "paredes": [{"id": "w", "piso": "x", "a": [0, 0], "b": [1, 0], "tipo": "ext_30"}]},
                {"pisos": [{"id": "p0"}], "paredes": [{"id": "w", "piso": "p0", "a": [0, 0], "b": [1e9, 0], "tipo": "ext_30"}]},
                {"pisos": [{"id": "p0"}], "paredes": [], "vaos": [{"id": "v", "parede": "nao", "pos_m": 1}]},
                {"pisos": [{"id": "p0"}], "tipos_parede": {"x": {"camadas": []}}}):
        with pytest.raises(EP.ErroModelo):
            EP.normalizar(mau)
    m = EP.normalizar({"pisos": [{"id": "p0", "nome": "<script>R/C"}], "rotulos": [{"piso": "p0", "x": 1, "y": 1, "nome": "<b>Sala</b>"}]})
    assert "<" not in m["pisos"][0]["nome"] and "<" not in m["rotulos"][0]["nome"]


def test_pecas_desenhadas_svg_e_png():
    m = modelo()
    d = EP.derivar(m)
    pecas = D.conjunto(m, d)
    assert [p["code"] for p in pecas] == ["PLANTAS", "ALCADOS", "ALCADOS", "ALCADOS", "ALCADOS", "CORTES", "CORTES"]
    s = D.svg(pecas[0])
    assert s.startswith("<svg") and "Sala" in s and "10,00" in s and "8,00" in s and "<script" not in s
    for p in D.pecas_png(m, d):
        assert p["png"][:8] == b"\x89PNG\r\n\x1a\n" and p["title"]
    assert "+2,95" in D.svg(D.alcado(m, d, "frente"))
    assert "x = 5,00" in D.corte(m, d, "x")["titulo"]


# ------------------------------------------------------------------ a partir de um processo real do piloto automático e rotas
UA = pytest.importorskip("routes.urbanismo_auto")
RE = pytest.importorskip("routes.estudio_projeto")
import test_urbanismo_auto as TU  # noqa: E402
import test_urbanismo_auto_routes as TR  # noqa: E402
from engines.urbanismo_pt.auto import geo as G  # noqa: E402

USER = {"user_id": "u1", "role": "user"}


class CollDel(TR.Coll):
    async def delete_one(self, q):
        self.docs = [x for x in self.docs if not self._m(x, q)]


class DBE:
    def __init__(self):
        self.urbanismo_estudios = CollDel()


@pytest.fixture()
def env(monkeypatch):
    db = TR.DB()
    monkeypatch.setattr(UA, "db", db)
    dbe = DBE()
    monkeypatch.setattr(RE, "db", dbe)
    G.set_transport(TU.fake())
    G._COLLECTIONS.update(t=0.0, list=[])
    yield db, dbe
    G.set_transport(None)


def test_modelo_do_processo_coincide_com_o_processo(env):
    async def go():
        r = await UA.executar_e_gravar({"texto": "autorização de construção na rua do monte nº7 padim da graça braga"}, USER)
        pid = r["processo_id"]
        doc = await env[0].urbanismo_processos.find_one({"processo_id": pid})
        antes = repr(doc)
        e = await RE.obter(pid, USER)
        assert e["origem"] == "processo" and e["derivado"]["ok"], e["derivado"]["erros"]
        x0, y0, x1, y1 = doc["auto"]["plantas"]["casa_rect"]
        n = len(doc["auto"]["plantas"]["pisos"])
        # mesma implantação: área bruta de cada piso = retângulo da casa no processo
        for p in e["derivado"]["pisos"]:
            assert p["area_bruta_m2"] == pytest.approx((x1 - x0) * (y1 - y0), abs=0.02)
        assert len(e["derivado"]["pisos"]) == n
        # mesmos vãos de fachada, nas mesmas posições e cotas
        vs = [v for w in e["derivado"]["paredes"] for v in w["vaos"]]
        assert len(vs) == len(doc["auto"]["vaos"]) and all(v["valido"] for v in vs)
        o = doc["auto"]["vaos"][0]
        w = next(w for w in e["derivado"]["paredes"] if w["id"] == f"p{o['piso']}_{o['fachada']}")
        v = w["vaos"][0] if o["fachada"] == "frente" else None
        if v:
            assert w["a"][0] + min(x["u0"] for x in w["vaos"]) == pytest.approx(min(q["x0"] for q in doc["auto"]["vaos"]
                                                                               if q["piso"] == o["piso"] and q["fachada"] == "frente"), abs=0.002)
        # uma divisão por compartimento do processo, com o mesmo nome
        nomes_proc = sorted(c["nome"] for p in doc["auto"]["plantas"]["pisos"] for c in p["compartimentos"])
        assert sorted(dv["nome"] for dv in e["derivado"]["divisoes"]) == nomes_proc
        # altura das paredes = altura de fachada do processo
        from engines.urbanismo_pt import volumes as V
        assert e["derivado"]["cobertura"]["z_topo_paredes"] == pytest.approx(V.heights(doc["volume"])["altura_fachada_m"], abs=0.01)
        # o processo não foi tocado
        assert repr(await env[0].urbanismo_processos.find_one({"processo_id": pid})) == antes
        return pid, e
    pid, e = TU._loop_run(go())

    async def editar():
        m = e["modelo"]
        m["vaos"].append({"id": "novo", "parede": "p0_direita", "tipo": "janela", "pos_m": 2.0})
        g = await RE.guardar(pid, RE.ModeloIn(modelo=m), USER)
        assert g["ok"] and g["derivado"]["medicoes"]["totais"]["n_vaos"] == e["derivado"]["medicoes"]["totais"]["n_vaos"] + 1
        e2 = await RE.obter(pid, USER)
        assert e2["origem"] == "guardado" and any(v["id"] == "novo" for v in e2["modelo"]["vaos"])
        pdf = await RE.pranchas(pid, USER)
        assert pdf.body[:4] == b"%PDF"
        csv_ = (await RE.medicoes(pid, USER)).body.decode("utf-8")
        assert "PAREDES" in csv_ and "p0_frente" in csv_ and "COBERTURA" in csv_
        svg = await RE.desenho_svg(RE.DesenhoIn(modelo=m, tipo="corte", eixo="y"), USER)
        assert svg.body.startswith(b"<svg")
        with pytest.raises(Exception):
            await RE.obter(pid, {"user_id": "u2"})                    # outro utilizador não vê
        with pytest.raises(Exception):
            await RE.guardar(pid, RE.ModeloIn(modelo={"pisos": []}), USER)
        await RE.repor(pid, USER)
        assert (await RE.obter(pid, USER))["origem"] == "processo"
    TU._loop_run(editar())


# ------------------------------------------------------------------ biblioteca de materiais
def test_biblioteca_de_materiais_e_coerente():
    from engines.estudio_projeto import materiais as MAT
    cat = MAT.catalogo()
    ids = [m["id"] for m in cat["biblioteca"]]
    assert len(ids) == len(set(ids)) and len(ids) >= 280
    assert all(m["nome"] and m["categoria"] in cat["categorias"] and m["cor"].startswith("#") and len(m["cor"]) == 7
               and all(e >= 0 for e in m["espessuras_cm"]) for m in cat["biblioteca"])
    for k, lista in cat["acabamentos"].items():
        lids = [x["id"] for x in lista]
        assert len(lids) == len(set(lids)) and all(len(i) <= 40 for i in lids) and cat["padrao"][k] in lids
    # os identificadores que o processo de licenciamento já usa continuam a existir, com o mesmo nome
    from engines.urbanismo_pt.auto import pecas_auto as PA
    for k, antigos in (("fachada", PA.MATERIAIS_FACHADA), ("cobertura", PA.MATERIAIS_COBERTURA), ("caixilharia", PA.CAIXILHARIA)):
        atuais = {x["id"]: x["nome"] for x in cat["acabamentos"][k]}
        assert all(atuais.get(i) == nome for i, nome in antigos.items())
    # cada parede-tipo usa só materiais da biblioteca e é aceite pelo modelo
    assert len(cat["paredes_tipo"]) >= 35
    for tid, t in cat["paredes_tipo"].items():
        assert all(MAT.existe(c["material"]) for c in t["camadas"]), tid
    m = EP.normalizar({"pisos": [{"id": "p0"}], "tipos_parede": cat["paredes_tipo"],
                       "paredes": [{"id": "w", "piso": "p0", "a": [0, 0], "b": [5, 0], "tipo": "ext_clt_ventilada"}]})
    assert len(m["tipos_parede"]) == len(cat["paredes_tipo"]) + 3
    w = EP.derivar(m)["medicoes"]["paredes"][0]
    assert w["espessura_m"] == pytest.approx(0.343, abs=0.0006) and len(w["camadas"]) == 6


def test_acabamentos_escolhidos_entram_nas_cores_e_nas_medicoes():
    d = EP.derivar(modelo(materiais={"fachada": "aco_corten", "cobertura": "zinco_quartzo", "pavimento": "soalho_carvalho",
                                     "parede_interior": "estuque", "teto": "teto_madeira", "caixilharia": "aluminio_preto"}))
    assert d["cores"]["fachada"] == "#8a4a2c" and d["cores"]["cobertura"] == "#7c858b"
    ac = {a["elemento"]: a for a in d["medicoes"]["acabamentos"]}
    assert ac["Pavimentos"]["material"] == "Soalho de carvalho" and ac["Pavimentos"]["area_m2"] == d["medicoes"]["totais"]["area_util_m2"]
    assert ac["Fachada exterior"]["material"] == "Chapa de aço corten" and ac["Fachada exterior"]["area_m2"] == d["medicoes"]["fachada"]["area_liquida_m2"]
    assert ac["Tetos"]["material"] == "Teto em ripado de madeira"
    desconhecido = EP.derivar(modelo(materiais={"fachada": "nao_existe"}))
    assert desconhecido["cores"]["fachada"] == "#f1efe9"            # identificador desconhecido → acabamento de omissão


def test_acabamentos_divisao_a_divisao():
    rot = [{"piso": "p0", "x": 2, "y": 4, "nome": "Sala", "pavimento": "soalho_carvalho", "teto": "teto_madeira"},
           {"piso": "p0", "x": 7, "y": 4, "nome": "Cozinha", "pavimento": "gres_antracite", "parede_interior": "azulejo_branco_int",
            "teto": "nao_existe"}]
    m = modelo(rotulos=rot, materiais={"pavimento": "microcimento_pav", "parede_interior": "pintura_creme", "teto": "teto_gesso_cartonado"})
    assert m["rotulos"][0]["pavimento"] == "soalho_carvalho" and "parede_interior" not in m["rotulos"][0]
    d = EP.derivar(m)
    div = {x["nome"]: x for x in d["divisoes"]}
    sala, coz = div["Sala"], div["Cozinha"]
    assert sala["acabamentos"]["pavimento"]["nome"] == "Soalho de carvalho" and sala["proprios"] == ["pavimento", "teto"]
    assert sala["acabamentos"]["parede_interior"]["nome"] == "Pintura creme"            # sem escolha própria → o da casa
    assert coz["acabamentos"]["parede_interior"]["nome"] == "Azulejo branco"
    assert coz["acabamentos"]["teto"]["id"] == "teto_estuque"                           # identificador desconhecido → omissão
    ac = d["medicoes"]["acabamentos"]
    pav = {a["material"]: a["area_m2"] for a in ac if a["elemento"] == "Pavimentos"}
    assert pav == {"Soalho de carvalho": sala["area_m2"], "Grés porcelânico antracite": coz["area_m2"]}
    assert sum(pav.values()) == pytest.approx(d["medicoes"]["totais"]["area_util_m2"], abs=0.011)   # nenhuma área contada duas vezes
    par = {a["material"]: a["area_m2"] for a in ac if a["elemento"].startswith("Paredes interiores")}
    assert par == {"Pintura creme": sala["area_paredes_m2"], "Azulejo branco": coz["area_paredes_m2"]}
    linha = next(x for x in d["medicoes"]["divisoes"] if x["nome"] == "Sala")
    assert linha["pavimento"] == "Soalho de carvalho" and linha["teto"] == "Teto em ripado de madeira"
    from routes.estudio_projeto import medicoes_csv
    assert "Soalho de carvalho" in medicoes_csv(d) and "Azulejo branco" in medicoes_csv(d)
    assert D.png(D.planta(m, d, 0))[:4] == b"\x89PNG"
    # uma divisão sem rótulo usa os acabamentos da casa
    d2 = EP.derivar(modelo(rotulos=[], materiais={"pavimento": "microcimento_pav"}))
    assert {x["acabamentos"]["pavimento"]["id"] for x in d2["divisoes"]} == {"microcimento_pav"}
