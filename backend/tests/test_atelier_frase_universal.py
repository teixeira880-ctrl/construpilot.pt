"""Atelier : « Modifier par une phrase » exécute n'importe quelle demande, en PT ou FR, et ne renvoie jamais d'erreur 500.

Cas réels du 27/11/2026 : « Rajoute une terrasse DEVANT LE SEJOUR TOUT LA LONGUEUR DE LA MAISON » et
« CREE DE MUS DE CLOTURE A TOUT LE TOUR DE LA MAISON SU UN SPACE DE 1500M2 » (fautes de frappe et majuscules comprises).
"""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_atelier_frase")
os.environ.setdefault("JWT_SECRET", "test")

from engines import estudio_projeto as EP  # noqa: E402
from engines.atelier_archi import edicao as ED  # noqa: E402
from engines.atelier_archi import generateur as G  # noqa: E402
from engines.atelier_archi import programme as P  # noqa: E402

CASAS = ["maison T4 plain-pied 110 m² avec garage et cuisine ouverte", "maison R+1 4 chambres 160 m2", "moradia V3 com garagem, dois pisos"]


def _casa(txt=CASAS[0]):
    return G.generer(P.programme(txt))["modelo"]


def _ext(m, tipo):
    return [o for o in m["objetos"] if o["tipo"] == tipo]


@pytest.mark.parametrize("txt", CASAS)
def test_terrasse_devant_le_sejour_toute_la_longueur(txt):
    m = _casa(txt)
    acoes, sobras = ED.interpretar_partes("Rajoute une terrasse DEVANT LE SEJOUR TOUT LA LONGUEUR DE LA MAISON", m)
    assert [a["acao"] for a in acoes] == ["faixa_exterior"] and not sobras
    assert acoes[0]["comprimento"] == "casa" and acoes[0]["divisao"]
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    d = EP.derivar(m2)
    assert d["ok"], d["erros"]
    _, x0, y0, x1, y1 = ED._casa_limites(m2)
    t = _ext(m2, "terraco_pedra")
    comp = sum(o["largura_m"] for o in t)
    assert abs(comp - ((x1 - x0) if t[0]["rot"] == 0 else (y1 - y0))) < 0.01   # toute la longueur de la façade
    # collée à la façade, à l'extérieur de la maison
    o = t[0]
    if o["rot"] == 0:
        assert abs(abs(o["y"] - (y0 if o["y"] < y0 else y1)) - o["prof_m"] / 2) < 0.01
    else:
        assert abs(abs(o["x"] - (x0 if o["x"] < x0 else x1)) - o["prof_m"] / 2) < 0.01


def test_terrasse_portugais_et_profondeur():
    m = _casa(CASAS[2])
    acoes, _ = ED.interpretar_partes("faz um terraço em madeira à frente da sala com 4 m de profundidade em todo o comprimento da casa", m)
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    assert _ext(m2, "deck_madeira")[0]["prof_m"] == 4


@pytest.mark.parametrize("frase", ["CREE DE MUS DE CLOTURE A TOUT LE TOUR DE LA MAISON SU UN SPACE DE 1500M2",
                                   "cria muro de vedação à volta da casa num terreno de 1500 m2"])
def test_cloture_autour_terrain_1500(frase):
    m = _casa()
    acoes, sobras = ED.interpretar_partes(frase, m)
    assert [a["acao"] for a in acoes] == ["contorno_exterior"] and acoes[0]["area_m2"] == 1500 and not sobras
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    assert EP.derivar(m2)["ok"]
    muros = _ext(m2, "muro_vedacao")
    assert abs(sum(o["largura_m"] for o in muros) - 4 * 1500 ** 0.5) < 0.05     # périmètre d'un carré de 1500 m²
    assert all(o["largura_m"] <= 40 for o in muros)


def test_grand_terrain_decoupe_en_troncons():
    m2, msg = ED.contorno_exterior(_casa(), "muro", 10000)
    muros = _ext(m2, "muro_vedacao")
    assert len(muros) == 12 and all(o["largura_m"] <= 40 for o in muros) and EP.derivar(m2)["ok"]


def test_piscine_creee_si_absente():
    m = _casa("petite maison 2 chambres")
    m["objetos"] = [o for o in m["objetos"] if "piscin" not in o["tipo"]]
    m2, feitos, falhas = ED.executar(m, ED.interpretar("piscine de 10 x 5", m))
    assert feitos and not falhas and _ext(m2, "piscina")[0]["largura_m"] == 10


def test_action_ia_inconnue_ne_casse_rien_et_note():
    m = _casa()
    m2, feitos, falhas = ED.executar(m, [{"acao": "esticar", "divisao": "Licorne", "metros": "abc"}])
    assert not feitos and falhas
    m3, msg = ED.nota_pedido(m, "mets un dragon sur le toit")
    assert any("dragon" in n["texto"] for n in m3["notas"]) and EP.derivar(m3)["ok"]


# ----------------------------------------------------------------- route : jamais d'erreur 500
class _Col:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, q, *a, **k):
        return self.doc

    async def update_one(self, q, upd, *a, **k):
        self.doc.update(upd["$set"])


def _route(monkeypatch, frase, ia_reponse=None, ia_erro=False):
    RA = pytest.importorskip("routes.atelier_archi")
    import json
    import sys
    import types

    import engines
    ai = types.ModuleType("engines.ai")          # couche IA réelle = paquets Emergent ; ici une cascade simulée
    ai._json = lambda raw, fb: json.loads(raw) if raw else fb
    monkeypatch.setitem(sys.modules, "engines.ai", ai)
    monkeypatch.setattr(engines, "ai", ai, raising=False)
    doc = {"projet_id": "p1", "user_id": "u1", "modelo": _casa(), "titre": "T"}
    col = _Col(doc)
    monkeypatch.setattr(RA.db, "archi_projects", col, raising=False)

    async def fake_complete(*a, **k):
        if ia_erro:
            raise RuntimeError("tous les fournisseurs sont tombés")
        return ia_reponse or '{"acoes": []}'
    ai._complete = fake_complete
    return asyncio.run(RA.editar_por_frase("p1", RA.FraseIn(frase=frase), {"user_id": "u1", "role": "user"})), doc


@pytest.mark.parametrize("frase", ["Rajoute une terrasse DEVANT LE SEJOUR TOUT LA LONGUEUR DE LA MAISON",
                                   "CREE DE MUS DE CLOTURE A TOUT LE TOUR DE LA MAISON SU UN SPACE DE 1500M2",
                                   "agrandis le séjour de 2 m", "toit 4 pans"])
def test_route_execute_et_enregistre(monkeypatch, frase):
    r, doc = _route(monkeypatch, frase)
    assert r["ok"] and r["feitos"] and r["updated_at"]
    assert "modelo" in r and doc["updated_at"] == r["updated_at"]


def test_route_demande_absurde_sans_ia_est_notee(monkeypatch):
    r, doc = _route(monkeypatch, "fais danser la maison en violet fluo", ia_erro=True)
    assert r["ok"] and r["origem"] == "nota" and any("violet" in n["texto"] for n in doc["modelo"]["notas"])


def test_route_ia_traduit_demande_libre(monkeypatch):
    r, _ = _route(monkeypatch, "une statue de lion à côté de l'entrée",
                  ia_reponse='{"acoes": [{"acao": "op", "op": {"op": "objeto", "tipo": "churrasqueira", "x": 0, "y": -6}}]}')
    assert r["ok"] and r["origem"] == "ia" and r["feitos"]


def test_route_erreur_interne_jamais_500(monkeypatch):
    RA = pytest.importorskip("routes.atelier_archi")

    async def boom(*a, **k):
        raise ZeroDivisionError("x")
    monkeypatch.setattr(RA, "_frase", boom)
    doc = {"projet_id": "p1", "user_id": "u1", "modelo": _casa()}
    monkeypatch.setattr(RA.db, "archi_projects", _Col(doc), raising=False)
    r = asyncio.run(RA.editar_por_frase("p1", RA.FraseIn(frase="xx yy"), {"user_id": "u1"}))
    assert r["ok"] is False and r["falhas"]


# ----------------------------------------------------------------- demandes libres du 27/11 (18 h 54)
LIVRES = [
    ("crée une route devant la maison avec un accès privé", {"estrada", "acesso_viaturas"}),
    ("cria uma estrada à frente da casa e acessos privados", {"estrada", "acesso_viaturas"}),
    ("fais un jardin avec des arbres", {"relvado", "arvore"}),
    ("plante 8 arbres", {"arvore"}),
    ("piscine et jardin avec jeux pour enfants", {"piscina", "relvado", "parque_infantil", "baloico"}),
    ("piscina, jardim com jogos para crianças", {"piscina", "relvado", "parque_infantil", "escorrega"}),
    ("étage avec terrasse qui déborde sur la piscine", {"terraco_suspenso", "piscina"}),
    ("andar com terraço a debordar sobre a piscina", {"terraco_suspenso", "piscina"}),
]


@pytest.mark.parametrize("frase,tipos", LIVRES)
@pytest.mark.parametrize("casa", [CASAS[0], CASAS[1]])
def test_demandes_libres_executees(casa, frase, tipos):
    m = _casa(casa)
    acoes, sobras = ED.interpretar_partes(frase, m)
    assert acoes and not sobras, (acoes, sobras)
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    d = EP.derivar(m2)
    assert d["ok"], d["erros"]
    assert tipos <= {o["tipo"] for o in m2["objetos"]}
    assert {e["tipo"] for e in d["medicoes"]["exteriores"]} >= tipos       # tout est métré


def test_terrasse_deborde_reellement_sur_la_piscine():
    m = _casa(CASAS[1])
    m2, _ = ED.terraco_sobre_piscina(m, 3.0)
    t = _ext(m2, "terraco_suspenso")[0]
    p = _ext(m2, "piscina")[0]
    assert t["piso"] == m2["pisos"][-1]["id"] != m2["pisos"][0]["id"]
    assert t["y"] + t["prof_m"] / 2 > p["y"] - p["prof_m"] / 2 + 1.5          # 2 m de recouvrement en plan


@pytest.mark.parametrize("frase,mat", [("façades en granit et bois", "misto_granito_madeira"), ("fachadas com granito e madeira", "misto_granito_madeira"),
                                       ("fachada em xisto", "xisto"), ("bardage bois sur les façades", "madeira")])
def test_facades_materiaux(frase, mat):
    m = _casa()
    m2, feitos, falhas = ED.executar(m, ED.interpretar(frase, m))
    assert feitos and not falhas and m2["materiais"]["fachada"] == mat


def test_tout_en_une_phrase_et_dce():
    from engines.atelier_archi import dce as DCE
    m = _casa(CASAS[1])
    frase = ("route devant la maison avec accès privé ; jardin avec arbres ; jeux pour enfants ; "
             "terrasse à l'étage qui déborde sur la piscine ; façades en granit et bois ; "
             "murs de clôture autour de la maison sur 1500 m2")
    acoes, sobras = ED.interpretar_partes(frase, m)
    assert not sobras
    m2, feitos, falhas = ED.executar(m, acoes)
    assert len(feitos) >= 6 and not falhas, falhas
    assert EP.derivar(m2)["ok"]
    vrd = next(l for l in DCE.selection(m2)["lots"] if l["code"] == "vrd")
    txt = " ".join(x["designation"] for x in vrd["lignes"])
    assert "Route" in txt and "Aire de jeux" in txt and "Mur de clôture" in txt


# ----------------------------------------------------------------- LOT2 : agrandir, U, façade par côté, objets libres
@pytest.mark.parametrize("casa", CASAS)
@pytest.mark.parametrize("frase,cle", [("ajoute une chambre de 15 m2 à droite", "chambre"), ("acrescenta um escritório atrás", "bureau"),
                                       ("rajoute un garage double à gauche", "_garage"), ("crée une véranda derrière le séjour", "veranda"),
                                       ("cria uma suíte de 20 m2", "suite")])
def test_agrandir_la_maison(casa, frase, cle):
    m = _casa(casa)
    d0 = EP.derivar(m)
    acoes, sobras = ED.interpretar_partes(frase, m)
    assert [a["acao"] for a in acoes] == ["acrescentar_divisao"] and acoes[0]["cle"] == cle and not sobras
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    d = EP.derivar(m2)
    assert d["ok"], d["erros"]
    assert len(d["divisoes"]) == len(d0["divisoes"]) + 1                       # une vraie pièce fermée en plus
    assert d["medicoes"]["totais"]["area_util_m2"] > d0["medicoes"]["totais"]["area_util_m2"] + 1.4
    assert len(m2["vaos"]) > len(m["vaos"]) or any(v["tipo"] == "porta" for v in m2["vaos"])


def test_surface_demandee_respectee():
    m = _casa()
    m2, msg = ED.acrescentar_divisao(m, "chambre", 15.0, "direita")
    nova = [d for d in EP.derivar(m2)["divisoes"] if d["nome"] not in {x["nome"] for x in EP.derivar(m)["divisoes"]}][0]
    assert 12.0 <= nova["area_m2"] <= 15.0                                     # 15 m² aux axes → surface utile un peu inférieure


@pytest.mark.parametrize("casa", CASAS[:2])
def test_maison_en_u(casa):
    m = _casa(casa)
    acoes, _ = ED.interpretar_partes("fais la maison en U", m)
    assert acoes == [{"acao": "forma", "forma": "u"}]
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    d = EP.derivar(m2)
    assert d["ok"] and any("Suite d'amis" in x["nome"] or "hóspedes" in x["nome"] for x in d["divisoes"])


def test_facade_par_cote():
    m = _casa()
    acoes, sobras = ED.interpretar_partes("façade avant en granit ; fachada tardoz em madeira", m)
    assert [a["acao"] for a in acoes] == ["fachada_lado", "fachada_lado"] and not sobras
    m2, feitos, falhas = ED.executar(m, acoes)
    assert len(feitos) == 2 and not falhas
    assert {w.get("fachada") for w in m2["paredes"]} >= {"granito", "madeira"} and EP.derivar(m2)["ok"]


@pytest.mark.parametrize("frase,tipo,n", [("ajoute un portail", "portao_entrada", 1), ("mets 3 transats", "espreguicadeira", 3),
                                          ("quero uma horta e um lago", "horta", 1), ("court de tennis", "campo_tenis", 1),
                                          ("un barbecue et une pergola", "churrasqueira", 1)])
def test_objets_libres_sans_chevauchement(frase, tipo, n):
    m = _casa()
    acoes, sobras = ED.interpretar_partes(frase, m)
    assert acoes and not sobras
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    novos = m2["objetos"][len(m["objetos"]):]
    assert len([o for o in novos if o["tipo"] == tipo]) == n and EP.derivar(m2)["ok"]
    cx = [(o["x"], o["y"]) for o in novos]
    assert len(set(cx)) == len(cx)


def test_supprimer_etage_hauteur_terrain():
    m = _casa()
    m1, f1, x1 = ED.executar(m, ED.interpretar("piscine de 10 x 5 ; puis supprime la piscine", m))
    assert len(f1) == 2 and not x1 and not _ext(m1, "piscina")
    m2, f2, x2 = ED.executar(m, ED.interpretar("ajoute un étage ; hauteur sous plafond 2,70 m", m))
    assert len(f2) == 2 and not x2 and len(m2["pisos"]) == len(m["pisos"]) + 1
    m3, f3, x3 = ED.executar(m, ED.interpretar("clôture autour du terrain de 30 x 50", m))
    assert f3 and not x3 and abs(sum(o["largura_m"] for o in _ext(m3, "muro_vedacao")) - 160) < 0.1


def test_plusieurs_demandes_reliees_par_et():
    m = _casa()
    acoes, sobras = ED.interpretar_partes("ajoute un bureau à droite et un garage à gauche", m)
    assert [a.get("cle") for a in acoes] == ["bureau", "_garage"] and not sobras
    m2, feitos, falhas = ED.executar(m, acoes)
    assert len(feitos) == 2 and not falhas, falhas
    assert EP.derivar(m2)["ok"]


# ----------------------------------------------------------------- LOT3 : meubler, déplacer / tourner, terrain réel, garde-corps et poteaux
@pytest.mark.parametrize("casa", CASAS)
def test_meubler_toute_la_maison(casa):
    from shapely.geometry import Point, Polygon, box
    from engines.estudio_projeto.objetos import OBJETOS
    m = _casa(casa)
    acoes, sobras = ED.interpretar_partes("meuble toute la maison", m)
    assert acoes == [{"acao": "mobilar", "divisao": None}] and not sobras
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    d = EP.derivar(m2)
    assert d["ok"], d["erros"]
    novos = m2["objetos"][len(m["objetos"]):]
    assert len(novos) >= 15 and {"cama_casal", "sofa_3", "sanita", "frigorifico"} <= {o["tipo"] for o in novos}
    caixas = []
    for o in novos:                                   # chaque meuble est dans une pièce et ne chevauche aucun autre
        b = OBJETOS[o["tipo"]]
        a_, b_ = (b["largura_m"], b["prof_m"]) if round(o["rot"]) % 180 == 0 else (b["prof_m"], b["largura_m"])
        cx = box(o["x"] - a_ / 2, o["y"] - b_ / 2, o["x"] + a_ / 2, o["y"] + b_ / 2)
        assert any(dv["piso"] == o["piso"] and Polygon(dv["pts"]).buffer(0.03).contains(cx) for dv in d["divisoes"]), o
        assert all(c.intersection(cx).area < 0.01 for p_, c in caixas if p_ == o["piso"]), o
        caixas.append((o["piso"], cx))
    m3, f3, x3 = ED.executar(m2, acoes)               # redemander ne double pas le mobilier
    assert len(m3["objetos"]) == len(m2["objetos"])


def test_meubler_une_piece_en_portugais():
    m = _casa(CASAS[2])
    acoes, _ = ED.interpretar_partes("mobila a sala", m)
    assert acoes[0]["acao"] == "mobilar" and acoes[0]["divisao"]
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas and any(o["tipo"] == "sofa_3" for o in m2["objetos"])


def test_deplacer_et_tourner():
    m = _casa("maison de plain-pied 3 chambres avec suite parentale, garage, piscine")
    p0 = _ext(m, "piscina")[0]
    m2, f, x = ED.executar(m, ED.interpretar("déplace la piscine de 4 m à gauche ; puis tourne la piscine de 90 degrés", m))
    p1 = _ext(m2, "piscina")[0]
    assert len(f) == 2 and not x and abs(p1["x"] - (p0["x"] - 4)) < 0.01 and p1["rot"] == (p0["rot"] + 90) % 360
    m3, f3, x3 = ED.executar(m, ED.interpretar("desloca a piscina para a frente da casa", m))
    _, x0, y0, x1, y1 = ED._casa_limites(m3)
    assert f3 and not x3 and _ext(m3, "piscina")[0]["y"] < y0


@pytest.mark.parametrize("frase,n,area", [("terrain en trapèze : 30 m devant, 20 m derrière, 40 m de profondeur", 4, 1000.0),
                                          ("terreno triangular com 30 m de frente e 40 m de profundidade", 3, 600.0),
                                          ("terrain points (0,0) (32,0) (28,45) (10,50) (0,30)", 5, None),
                                          ("lote de lados 30, 42, 26, 40", 4, None)])
def test_terrain_forme_reelle(frase, n, area):
    import math as _m
    m = _casa()
    acoes, sobras = ED.interpretar_partes(frase, m)
    assert [a["acao"] for a in acoes] == ["terreno_real"] and not sobras, acoes
    m2, feitos, falhas = ED.executar(m, acoes)
    assert feitos and not falhas, falhas
    assert EP.derivar(m2)["ok"]
    muros = _ext(m2, "muro_vedacao")
    assert len({o["rot"] for o in muros}) >= min(n, 3) and all(o["largura_m"] <= 40 for o in muros)
    pts = ED.terreno_pontos(acoes[0]["forma"], acoes[0]["frente"], acoes[0]["tardoz"], acoes[0]["prof"], acoes[0]["lados"], acoes[0]["pontos"])
    assert len(pts) == n
    per = sum(_m.hypot(pts[(i + 1) % n][0] - pts[i][0], pts[(i + 1) % n][1] - pts[i][1]) for i in range(n))
    assert abs(sum(o["largura_m"] for o in muros) - per) < 0.1                      # la clôture suit tout le périmètre réel
    if area:
        assert f"{area:,.1f}".replace(",", " ").replace(".", ",") in feitos[0]
    if acoes[0]["lados"]:
        ls = [_m.hypot(pts[(i + 1) % 4][0] - pts[i][0], pts[(i + 1) % 4][1] - pts[i][1]) for i in range(4)]
        assert all(abs(a - b) < 0.05 for a, b in zip(ls, acoes[0]["lados"]))           # les 4 côtés demandés sont respectés


def test_terrasse_porte_a_faux_garde_corps_et_poteaux():
    m2, msg = ED.terraco_sobre_piscina(_casa(CASAS[1]), 3.0)
    g, p = _ext(m2, "guarda_corpo"), _ext(m2, "pilar")
    t = _ext(m2, "terraco_suspenso")[0]
    assert len(g) == 3 and abs(sum(x["largura_m"] for x in g) - (t["largura_m"] + 2 * t["prof_m"])) < 0.01
    assert len(p) >= 2 and all(x["piso"] == m2["pisos"][0]["id"] for x in p) and all(x["piso"] == t["piso"] for x in g)
    pis = _ext(m2, "piscina")[0]
    assert all(x["y"] + 0.13 < pis["y"] - pis["prof_m"] / 2 for x in p)                # aucun poteau dans la piscine
    d = EP.derivar(m2)
    assert d["ok"] and {"guarda_corpo", "pilar"} <= {e["tipo"] for e in d["medicoes"]["exteriores"]}
    from engines.estudio_projeto import ifc
    assert ifc is not None
