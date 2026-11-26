"""Estúdio de Projeto — modelo único: medições exatas, cobertura, peças desenhadas, IFC, PDF, DXF e operações.

Testes do motor tal como em construpilot.pt, corridos aqui com as paredes de partida e a língua de Portugal: provam que o
motor partilhado dá no .fr exatamente os mesmos números e textos que no .pt (paridade). O que depende do país — modelo a
partir do dossier d'urbanisme, textos em francês, rotas — está em tests/test_studio_projet_fr.py.
"""
import math
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_estudio_projeto")
os.environ.setdefault("JWT_SECRET", "test")

from engines import estudio_projeto as EP  # noqa: E402
from engines.estudio_projeto import desenhos as D  # noqa: E402

H = 0.15  # meia espessura da parede exterior de 30 cm


@pytest.fixture(autouse=True)
def _como_em_portugal(monkeypatch):
    from engines.estudio_projeto import i18n as I, materiais as MAT, modelo as M
    monkeypatch.setattr(M, "TIPOS_BASE", M.TIPOS_PT)
    monkeypatch.setattr(MAT, "PAREDES_TIPO", {k: v for k, v in MAT.PAREDES_TIPO.items() if not k.startswith("fr_")})
    with I.usar_lingua("pt"):
        yield


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


def _em_L():
    return [{"id": f"w{i}", "piso": "p0", "a": a, "b": b, "tipo": "ext_30"} for i, (a, b) in enumerate(
        [([0, 0], [10, 0]), ([10, 0], [10, 4]), ([10, 4], [5, 4]), ([5, 4], [5, 8]), ([5, 8], [0, 8]), ([0, 8], [0, 0])])]


@pytest.mark.parametrize("tipo", ["quatro_aguas", "duas_aguas"])
def test_cobertura_inclinada_em_planta_em_L(tipo):
    from shapely.geometry import Polygon as Pg
    d = EP.derivar(modelo(paredes=_em_L(), vaos=[], rotulos=[], cobertura={"tipo": tipo, "inclinacao_graus": 30, "beiral_m": 0.5}))
    c = d["cobertura"]
    assert c["faces"] and not any(a["codigo"] == "COBERTURA_FORMA" for a in d["avisos"])
    faces = [Pg([(p[0], p[1]) for p in f["pts"]]) for f in c["faces"]]
    beirado = Pg(d["pisos"][0]["pegada"][0]).buffer(0.5, join_style=2)
    # as águas cobrem exatamente o contorno + beiral, sem buracos nem sobreposições
    assert sum(f.area for f in faces) == pytest.approx(beirado.area, abs=0.02)
    assert sum(faces[i].intersection(faces[j]).area for i in range(len(faces)) for j in range(i + 1, len(faces))) < 1e-4
    assert d["medicoes"]["cobertura"]["area_m2"] == pytest.approx(beirado.area / math.cos(math.radians(30)), abs=0.1)
    # cumeeira: meio-lado do maior quadrado inscrito (corpo de 5,30 m + 2 × 0,50 de beiral → 3,15 m)
    tan = math.tan(math.radians(30))
    assert c["z_cumeeira"] == pytest.approx(2.95 - tan * 0.5 + tan * 3.15, abs=0.01)
    # cada face é plana com a inclinação pedida e tem triângulos que a cobrem por inteiro
    for f, pl in zip(c["faces"], faces):
        assert sum(Pg([(q[0], q[1]) for q in t]).area for t in f["tris"]) == pytest.approx(pl.area, abs=0.01)
        assert min(q[2] for q in f["pts"]) >= 2.95 - tan * 0.5 - 0.002
    assert bool(c["empenas"]) == (tipo == "duas_aguas")


def test_cobertura_ortogonal_coincide_com_a_convexa_num_retangulo():
    from shapely.geometry import Polygon as Pg
    from engines.estudio_projeto.cobertura import aguas_ortogonais
    from engines.estudio_projeto.derivar import _aguas
    ret = Pg([(0, 0), (10, 0), (10, 8), (0, 8)])
    for tipo in ("quatro_aguas", "duas_aguas"):
        cob = {"tipo": tipo, "inclinacao_graus": 27, "beiral_m": 0.4, "cumeeira": "auto", "lado_baixo": "frente"}
        a, b = _aguas(ret, cob, 3.0), aguas_ortogonais(ret, cob, 3.0)
        assert a["z_cumeeira"] == pytest.approx(b["z_cumeeira"], abs=0.002)
        assert sum(f["area_m2"] for f in a["faces"]) == pytest.approx(sum(f["area_m2"] for f in b["faces"]), abs=0.05)
        assert sum(e["area_m2"] for e in a["empenas"]) == pytest.approx(sum(e["area_m2"] for e in b["empenas"]), abs=0.03)


def test_cobertura_inclinada_em_contorno_obliquo_com_reentrancia_nao_e_inventada():
    seta = [{"id": f"w{i}", "piso": "p0", "a": a, "b": b, "tipo": "ext_30"} for i, (a, b) in enumerate(
        [([0, 0], [10, 0]), ([10, 0], [10, 6]), ([5, 3], [10, 6]), ([5, 3], [0, 6]), ([0, 6], [0, 0])])]
    d = EP.derivar(modelo(paredes=seta, vaos=[], rotulos=[]))
    assert not d["cobertura"]["faces"] and any(a["codigo"] == "COBERTURA_FORMA" for a in d["avisos"])
    plana = EP.derivar(modelo(paredes=seta, vaos=[], rotulos=[], cobertura={"tipo": "plana"}))
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



RE = pytest.importorskip("routes.estudio_projeto")


def _validar_ifc(f) -> list:
    """Erros de conformidade ao esquema IFC (lista vazia = ficheiro válido)."""
    import logging

    import ifcopenshell.validate

    class _Recolhe(logging.Handler):
        def __init__(self):
            super().__init__()
            self.msgs = []

        def emit(self, record):
            self.msgs.append(record.getMessage())

    log = logging.getLogger("construpilot.estudio.validate")
    log.propagate = False
    h = _Recolhe()
    log.addHandler(h)
    try:
        ifcopenshell.validate.validate(f, log)
    finally:
        log.removeHandler(h)
    return h.msgs


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


def test_fachada_por_parede_caixilharia_por_vao_e_faces_das_divisoes():
    paredes = casa()
    paredes[0]["fachada"] = "madeira_cedro"                                   # só a parede da frente em cedro
    vaos = [{"id": "v1", "parede": "f", "tipo": "porta", "pos_m": 2.0, "caixilharia": "madeira_carvalho_cx"},
            {"id": "v2", "parede": "f", "tipo": "janela", "pos_m": 7.0},
            {"id": "v3", "parede": "i", "tipo": "porta", "pos_m": 3.0}]
    m = modelo(paredes=paredes, vaos=vaos)
    assert m["paredes"][0]["fachada"] == "madeira_cedro" and "fachada" not in m["paredes"][1]
    d = EP.derivar(m)
    par = {w["id"]: w for w in d["paredes"]}
    assert par["f"]["cor"] == "#c58a5a" and par["d"]["cor"] == "#f1efe9" and par["f"]["fachada"]["nome"] == "Ripado de cedro"
    # o comprimento de fachada das quatro paredes soma o perímetro exterior, sem repetir os cunhais
    assert sum(par[k]["fachada_m"] for k in "fdte") == pytest.approx(36.0, abs=0.01)
    assert {v["id"]: v["cor"] for v in par["f"]["vaos"]} == {"v1": "#a9773f", "v2": "#2f3235"}
    ac = d["medicoes"]["acabamentos"]
    fach = {a["material"]: a["area_m2"] for a in ac if a["elemento"] == "Fachada exterior"}
    assert set(fach) == {"Ripado de cedro", "Reboco pintado a branco"}
    assert sum(fach.values()) == pytest.approx(d["medicoes"]["fachada"]["area_liquida_m2"], abs=0.03)   # nada a mais nem a menos
    assert fach["Ripado de cedro"] == pytest.approx(par["f"]["fachada_m"] * 2.95 - 3.33, abs=0.02)
    caix = {a["material"]: a["area_m2"] for a in ac if a["elemento"].startswith("Caixilharia")}
    assert caix == {"Madeira de carvalho": 1.89, "Alumínio lacado antracite com corte térmico, vidro duplo": 1.44}
    # faces da sala: quatro lados; a porta de entrada e a porta interior abrem-se em duas delas
    sala = next(x for x in d["divisoes"] if x["nome"] == "Sala")
    assert len(sala["faces"]) == 4 and sala["z1"] - sala["z0"] == pytest.approx(2.7)
    furos = sorted(f["id"] for face in sala["faces"] for f in face["vaos"])
    assert furos == ["v1", "v3"]
    face_porta = next(face for face in sala["faces"] if any(f["id"] == "v1" for f in face["vaos"]))
    f1 = face_porta["vaos"][0]
    assert f1["u1"] - f1["u0"] == pytest.approx(0.9, abs=0.002) and (f1["z0"], f1["z1"]) == (0.0, 2.1)
    assert D.svg(D.alcado(m, d, "frente")).count("rgb(197,138,90)") >= 1      # o alçado usa a cor da parede


def test_no_3d_os_encontros_nao_se_sobrepoem():
    from shapely.geometry import Polygon as Pg
    d = EP.derivar(modelo())
    solidos = []
    for w in d["paredes"]:
        L, h = w["comprimento_m"], w["esp_m"] / 2
        ux, uy = (w["b"][0] - w["a"][0]) / L, (w["b"][1] - w["a"][1]) / L
        a = (w["a"][0] - ux * w["ext3d_a"], w["a"][1] - uy * w["ext3d_a"])
        b = (w["b"][0] + ux * w["ext3d_b"], w["b"][1] + uy * w["ext3d_b"])
        solidos.append(Pg([(a[0] - uy * h, a[1] + ux * h), (b[0] - uy * h, b[1] + ux * h), (b[0] + uy * h, b[1] - ux * h), (a[0] + uy * h, a[1] - ux * h)]))
    for i in range(len(solidos)):
        for j in range(i + 1, len(solidos)):
            assert solidos[i].intersection(solidos[j]).area < 1e-6
    # e juntos cobrem exatamente a planta das paredes (área bruta menos as divisões)
    assert sum(s.area for s in solidos) == pytest.approx(80.0 - sum(x["area_m2"] for x in d["divisoes"]), abs=0.02)


# ------------------------------------------------------------------ escadas
def _dois_pisos(**kw):
    return modelo(pisos=[{"id": "p0"}, {"id": "p1", "laje_m": 0.30}], paredes=casa() + casa(piso="p1", pre="s"), vaos=[], rotulos=[], **kw)


@pytest.mark.parametrize("tipo,n_deg,n_pat", [("reta", 16, 0), ("l", 15, 1), ("u", 15, 1)])
def test_escadas_degraus_pela_altura_real(tipo, n_deg, n_pat):
    from shapely.geometry import Polygon as Pg
    m = _dois_pisos(escadas=[{"id": "e1", "piso": "p0", "tipo": tipo, "x": 6.0, "y": 1.0, "rot": 0, "largura_m": 0.9, "cobertor_m": 0.25}])
    d = EP.derivar(m)
    assert d["ok"], d["erros"]
    e = d["escadas"][0]
    # 3,00 m de piso a piso (2,70 + 0,30): 17 espelhos de 17,65 cm, um cobertor a menos (o patamar conta como cobertor)
    assert e["altura_m"] == 3.0 and e["n_espelhos"] == 17 and e["espelho_m"] == pytest.approx(3.0 / 17, abs=1e-4)
    assert len(e["degraus"]) == n_deg and len(e["patamares"]) == n_pat and e["n_cobertores"] == 16
    cotas_ = sorted(x["z"] for x in e["degraus"] + e["patamares"])
    assert cotas_[0] == pytest.approx(3.0 / 17, abs=0.002) and cotas_[-1] == pytest.approx(3.0 - 3.0 / 17, abs=0.002)
    assert all(b - a == pytest.approx(3.0 / 17, abs=0.002) for a, b in zip(cotas_, cotas_[1:]))      # sobe sempre um espelho
    assert all(Pg(x["pts"]).area == pytest.approx(0.9 * 0.25, abs=0.002) for x in e["degraus"])
    assert e["blondel_m"] == pytest.approx(2 * 3.0 / 17 + 0.25, abs=0.001)
    # vazio na laje do 1.º andar: só onde faltam 2,00 m livres (degraus acima de 0,70 m), descontado da laje
    altos = [x for x in e["degraus"] + e["patamares"] if x["z"] > 0.70]
    assert e["vazio_m2"] == pytest.approx(sum(Pg(x["pts"]).area for x in altos), abs=0.02) and 0 < e["vazio_m2"] < e["area_planta_m2"]
    laje = next(x for x in d["medicoes"]["lajes"] if x["nome"] == "Laje do 1.º andar")
    assert laje["area_m2"] == pytest.approx(80.0 - e["vazio_m2"], abs=0.02)
    assert sum(len(f) for f in next(x for x in d["lajes"] if x["nome"] == "Laje do 1.º andar")["furos"]) == 1
    assert d["medicoes"]["escadas"][0]["n_espelhos"] == 17
    pecas = D.conjunto(m, d)
    assert all(D.png(x)[:4] == b"\x89PNG" for x in pecas) and "sobe" in D.svg(pecas[0])


def test_escada_rodada_e_erros():
    m = _dois_pisos(escadas=[{"id": "a", "piso": "p0", "tipo": "u", "x": 6.0, "y": 6.5, "rot": 270, "sentido": "esq"},
                             {"id": "b", "piso": "p1", "tipo": "reta", "x": 6.0, "y": 1.0}])
    d = EP.derivar(m)
    assert not d["ok"] and [e["codigo"] for e in d["erros"]] == ["ESCADA_SEM_PISO"]
    a = d["escadas"][0]
    xs = [p[0] for x in a["degraus"] for p in x["pts"]]
    assert min(xs) == pytest.approx(6.0, abs=0.002) and max(xs) > 7.5          # rodada: sobe segundo +x
    fora = EP.derivar(_dois_pisos(escadas=[{"id": "f", "piso": "p0", "tipo": "reta", "x": 9.0, "y": 6.0}]))
    assert {x["codigo"] for x in fora["avisos"]} >= {"ESCADA_FORA", "ESCADA_PAREDE"}
    with pytest.raises(EP.ErroModelo):
        EP.normalizar({"pisos": [{"id": "p0"}], "escadas": [{"id": "e", "piso": "nao"}]})


# ------------------------------------------------------------------ exportação IFC
def test_ifc_reabre_valido_e_com_as_mesmas_quantidades():
    import ifcopenshell
    import ifcopenshell.util.element as E
    import ifcopenshell.util.placement as PL
    try:
        from engines.bim_core.ifc_builder import validate
    except ModuleNotFoundError:          # lote BIM ainda não portado para o .fr: a mesma validação, diretamente no IfcOpenShell
        validate = _validar_ifc
    from engines.estudio_projeto import ifc as IFC
    paredes = casa() + casa(piso="p1", pre="s")
    paredes[0]["fachada"] = "madeira_cedro"
    m = modelo(pisos=[{"id": "p0"}, {"id": "p1", "laje_m": 0.30}], paredes=paredes,
               vaos=[{"id": "v1", "parede": "f", "tipo": "porta", "pos_m": 2.0}, {"id": "v2", "parede": "f", "tipo": "janela", "pos_m": 7.0},
                     {"id": "v3", "parede": "d", "tipo": "portao", "pos_m": 3.5}, {"id": "v4", "parede": "sf", "tipo": "portada", "pos_m": 5.0}],
               escadas=[{"id": "e1", "piso": "p0", "tipo": "u", "x": 6.0, "y": 1.0}],
               rotulos=[{"piso": "p0", "x": 2, "y": 4, "nome": "Sala", "pavimento": "soalho_carvalho"}])
    d = EP.derivar(m)
    f = IFC.construir(m, d, chave="proc1", nome_projeto="Casa de ensaio")
    assert validate(f) == []
    g = ifcopenshell.file.from_string(f.to_string())                  # o que conta é o ficheiro tal como é descarregado
    assert g.schema == "IFC4"
    assert [(s.Name, s.Elevation) for s in sorted(g.by_type("IfcBuildingStorey"), key=lambda s: s.Elevation)] == [("Rés-do-chão", 0.0), ("1.º andar", 3.0)]
    paredes_ifc = [w for w in g.by_type("IfcWall") if not w.Name.startswith("Empena")]
    assert len(paredes_ifc) == len(d["paredes"]) == 10 and len([w for w in g.by_type("IfcWall") if w.Name.startswith("Empena")]) == len(d["cobertura"]["empenas"])
    assert len(g.by_type("IfcDoor")) == 2 and len(g.by_type("IfcWindow")) == 2 and len(g.by_type("IfcStair")) == 1
    assert len(g.by_type("IfcSpace")) == len(d["divisoes"]) and len(g.by_type("IfcRoof")) == 1
    # cada vão abre a sua parede e é preenchido pela sua porta ou janela
    assert len(g.by_type("IfcRelVoidsElement")) == 4 + 1 and len(g.by_type("IfcRelFillsElement")) == 4      # + o vazio da escada na laje
    w = next(x for x in paredes_ifc if x.Name == "Parede f")
    ps = E.get_psets(w)
    mp = next(x for x in d["medicoes"]["paredes"] if x["id"] == "f")
    assert ps["Qto_WallBaseQuantities"]["NetSideArea"] == pytest.approx(mp["area_liquida_m2"]) and ps["Pset_WallCommon"]["IsExternal"] is True
    assert ps["CP_Estudio"]["Fachada"] == "Ripado de cedro"
    cj = E.get_material(w)
    assert cj.is_a("IfcMaterialLayerSet") and [c.Material.Name for c in cj.MaterialLayers] == [c["material"] for c in m["tipos_parede"]["ext_30"]["camadas"]]
    assert sum(c.LayerThickness for c in cj.MaterialLayers) == pytest.approx(0.30)
    # posição no mundo: a parede «sf» (1.º andar) começa no ponto certo e à cota do piso
    sf = next(x for x in paredes_ifc if x.Name == "Parede sf")
    mt = PL.get_local_placement(sf.ObjectPlacement)
    dw = next(x for x in d["paredes"] if x["id"] == "sf")
    assert mt[0][3] == pytest.approx(dw["a"][0] - dw["ext3d_a"], abs=1e-6) and mt[2][3] == pytest.approx(3.0, abs=1e-6)
    sala = next(x for x in g.by_type("IfcSpace") if x.Name == "Sala")
    assert E.get_psets(sala)["CP_Acabamentos"]["Pavimento"] == "Soalho de carvalho"
    assert E.get_psets(sala)["Qto_SpaceBaseQuantities"]["NetFloorArea"] == pytest.approx(3.64 * 7.40, abs=0.01)
    esc = E.get_psets(g.by_type("IfcStair")[0])["Pset_StairCommon"]
    assert esc["NumberOfRiser"] == 17 and esc["RiserHeight"] == pytest.approx(3.0 / 17, abs=1e-4)
    # exportar outra vez dá os mesmos identificadores
    f2 = IFC.construir(m, EP.derivar(m), chave="proc1")
    assert {x.GlobalId for x in f.by_type("IfcWall")} == {x.GlobalId for x in f2.by_type("IfcWall")}
    # geometria real: o volume de cada parede do IFC é o da parede menos os seus vãos
    import ifcopenshell.geom
    import ifcopenshell.util.shape as SH
    cfg = ifcopenshell.geom.settings()
    forma = ifcopenshell.geom.create_shape(cfg, next(x for x in f.by_type("IfcWall") if x.Name == "Parede f"))
    dwf = next(x for x in d["paredes"] if x["id"] == "f")
    esperado = ((dwf["comprimento_m"] + dwf["ext3d_a"] + dwf["ext3d_b"]) * 2.7 - 0.9 * 2.1 - 1.2 * 1.2) * 0.30
    assert SH.get_volume(forma.geometry) == pytest.approx(esperado, abs=0.01)


# ------------------------------------------------------------------ objetos, mapa de vãos, cotas, notas, exportações, operações
def test_objetos_mapa_de_vaos_quadro_de_areas_cotas_e_notas():
    m = modelo(objetos=[{"id": "o1", "piso": "p0", "tipo": "sofa_3", "x": 2.0, "y": 4.0, "rot": 90},
                        {"id": "o2", "piso": "p0", "tipo": "sofa_3", "x": 2.0, "y": 6.0},
                        {"id": "o3", "piso": "p0", "tipo": "mesa_redonda", "x": 7.0, "y": 4.0}],
               cotas=[{"id": "c1", "piso": "p0", "a": [0, 0], "b": [4, 0], "afastamento_m": -1.2}],
               notas=[{"id": "n1", "piso": "p0", "x": 7, "y": 2, "texto": "Pavimento radiante"}])
    m["vaos"][1].update(modelo="correr_3", protecao="estore_termico")
    m = EP.normalizar(m)
    d = EP.derivar(m)
    assert d["ok"]
    o1 = next(o for o in d["objetos"] if o["id"] == "o1")
    xs, ys = [p[0] for p in o1["pts"]], [p[1] for p in o1["pts"]]
    assert max(xs) - min(xs) == pytest.approx(0.95, abs=1e-3) and max(ys) - min(ys) == pytest.approx(2.20, abs=1e-3)   # rodado 90°
    assert {o["tipo"]: o["quantidade"] for o in d["medicoes"]["objetos"]} == {"sofa_3": 2, "mesa_redonda": 1}
    mv = {l["codigo"]: l for l in d["medicoes"]["mapa_vaos"]}
    assert set(mv) == {"J1", "P1", "P2"} and mv["J1"]["folhas"] == 3 and "térmico" in mv["J1"]["protecao"]
    assert mv["P1"]["exterior"] != mv["P2"]["exterior"]
    assert sum(l["quantidade"] for l in mv.values()) == 3
    q = d["medicoes"]["quadro_areas"][0]
    assert q["area_bruta_m2"] == 80.0 and q["area_util_m2"] == pytest.approx(3.64 * 7.4 + 5.64 * 7.4, abs=0.02)
    assert q["paredes_e_vazios_m2"] == pytest.approx(80.0 - q["area_util_m2"], abs=0.01)
    assert d["medicoes"]["area_implantacao_m2"] == 80.0
    pl = D.planta(m, d, 0)
    textos = [i["txt"] for i in pl["itens"] if i["t"] == "text"]
    assert "Pavimento radiante" in textos and "J1" in textos and "4,00" in textos                # nota, código do vão e cota do utilizador
    assert {i.get("cam") for i in pl["itens"]} >= {"PAREDES", "VAOS", "MOBILIARIO", "COTAS", "TEXTO"}
    with pytest.raises(EP.ErroModelo):
        modelo(objetos=[{"id": "o", "piso": "p0", "tipo": "nao_existe", "x": 1, "y": 1}])


def test_pdf_vetorial_a_escala_e_dxf_em_metros():
    import ezdxf
    from ezdxf import bbox
    from engines.estudio_projeto import exportar as EX
    m = modelo()
    d = EP.derivar(m)
    cj = D.conjunto(m, d)
    assert EX.escala_que_cabe(cj[0]["itens"], 420, 297) == 50                    # casa de 10 × 8 m cabe a 1:50 num A3
    pdf = EX.pranchas_pdf({"title": "Moradia"}, cj)
    assert pdf[:5] == b"%PDF-" and pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") >= 1
    import io
    doc = ezdxf.read(io.StringIO(EX.dxf(cj, "Moradia").decode("utf-8")))
    assert doc.header["$INSUNITS"] == 6                                          # metros
    msp = doc.modelspace()
    camadas = {e.dxf.layer for e in msp}
    assert {"PAREDES", "VAOS", "COTAS", "TEXTO"} <= camadas
    # a primeira peça (planta do rés-do-chão) fica na origem: as paredes medem exatamente 10 × 8 m
    planta = [e for e in msp.query('*[layer=="PAREDES"]') if e.dxftype() != "HATCH"]
    ext = bbox.extents(planta)
    assert ext.size.x == pytest.approx(10.0, abs=0.001) and ext.size.y == pytest.approx(8.0, abs=0.001)


def test_operacoes_fazem_o_pedido_ou_dizem_porque_nao():
    from engines.estudio_projeto import operacoes as OP
    m, feitos, falhas = OP.aplicar(EP.modelo_vazio(), [
        {"op": "sala", "x0": 0.15, "y0": 0.15, "x1": 9.85, "y1": 7.85, "tipo": "ext_30"},
        {"op": "parede", "a": [4, 0.15], "b": [4, 7.85]},
        {"op": "vao", "tipo": "janela", "lado": "tardoz", "largura_m": 1.6},
        {"op": "vao", "tipo": "porta", "lado": "frente", "pos_m": 2.0},
        {"op": "vao", "tipo": "janela", "lado": "frente", "pos_m": 2.0},           # ocupado: desloca-se para o lugar livre mais próximo
        {"op": "materiais", "fachada": "granito", "pavimento": "soalho de carvalho"},
        {"op": "divisao", "nome": "Divisão 1", "novo_nome": "Cozinha", "pavimento": "microcimento"},
        {"op": "objeto", "tipo": "cama casal", "divisao": "Divisão 2"},
        {"op": "cobertura", "tipo": "quatro_aguas", "inclinacao_graus": 20},
        {"op": "piso_adicionar"}, {"op": "escada", "x": 7, "y": 4, "tipo": "reta"},
        {"op": "vao", "parede": "nao_ha"}, {"op": "materiais", "fachada": "kriptonite"}, {"op": "voar"},
        {"op": "vao", "tipo": "portao", "lado": "esquerda", "largura_m": 30},
    ])
    assert len(feitos) == 11 and len(falhas) == 4, (feitos, falhas)
    assert "nao_ha" in falhas[0] and "kriptonite" in falhas[1] and "voar" in falhas[2] and "não cabe" in falhas[3]
    d = EP.derivar(m)
    assert d["ok"], d["erros"]
    assert len(m["pisos"]) == 2 and m["cobertura"]["tipo"] == "quatro_aguas" and len(m["escadas"]) == 1
    frente = sorted((v["pos_m"], v["largura_m"]) for v in m["vaos"] if v["parede"] == "w1")
    assert len(frente) == 2 and frente[1][0] - frente[0][0] >= (frente[0][1] + frente[1][1]) / 2          # não se sobrepõem
    coz = next(dv for dv in d["divisoes"] if dv["nome"] == "Cozinha")
    assert "icrocimento" in coz["acabamentos"]["pavimento"]["nome"]
    assert any(a_["elemento"].lower().startswith("fachada") and "ranito" in a_["material"] for a_ in d["medicoes"]["acabamentos"])
    assert m["materiais"]["fachada"] and "arvalho" in next(dv for dv in d["divisoes"] if dv["nome"] != "Cozinha")["acabamentos"]["pavimento"]["nome"]
    assert [o["tipo"] for o in m["objetos"]] == ["cama_casal"]
    r = OP.resumo(m, d)
    assert r["totais"]["area_bruta_construcao_m2"] == 160.0 and len(r["paredes_exteriores"]) == 8
    # uma operação que deixaria o modelo inválido não fica
    m2, f2, x2 = OP.aplicar(m, [{"op": "pe_direito", "piso": 0, "valor": 9}])
    assert not f2 and x2 and m2["pisos"][0]["pe_direito_m"] == m["pisos"][0]["pe_direito_m"]


def test_ifc_leva_os_objetos():
    from engines.estudio_projeto import ifc as IFC
    m = modelo(objetos=[{"id": "o1", "piso": "p0", "tipo": "sanita", "x": 7, "y": 4}, {"id": "o2", "piso": "p0", "tipo": "sofa_3", "x": 2, "y": 4},
                        {"id": "o3", "piso": "p0", "tipo": "frigorifico", "x": 7, "y": 6}])
    f = IFC.construir(m, EP.derivar(m))
    assert len(f.by_type("IfcSanitaryTerminal")) == 1 and len(f.by_type("IfcFurniture")) == 1 and len(f.by_type("IfcElectricAppliance")) == 1
