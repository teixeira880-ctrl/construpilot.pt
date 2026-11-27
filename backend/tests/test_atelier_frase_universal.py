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
    r, _ = _route(monkeypatch, "je veux un barbecue dans le jardin",
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
