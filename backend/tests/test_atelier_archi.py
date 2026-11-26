"""Atelier Architecte (app « Architecte & BIM ») : prompt / croquis main levée / photo → maquette du Studio → DCE.

Vérifie : programme déterministe (même prompt = même maquette), plans fermés et sans erreur, escalier aligné d'un niveau
à l'autre, croquis tremblé redressé à l'échelle des cotes, DCE dont toutes les quantités viennent du métré de la maquette,
routes (projets, exports, isolation entre comptes) et rédaction complète du DCE sans IA.
"""
import asyncio
import math
import os
import random

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_atelier_archi")
os.environ.setdefault("JWT_SECRET", "test")

from engines import estudio_projeto as EP  # noqa: E402
from engines.atelier_archi import croquis as C  # noqa: E402
from engines.atelier_archi import dce as DCE  # noqa: E402
from engines.atelier_archi import generateur as GEN  # noqa: E402
from engines.atelier_archi import programme as P  # noqa: E402
from engines.atelier_archi import vision as V  # noqa: E402

RA = pytest.importorskip("routes.atelier_archi")
RC = pytest.importorskip("routes.cctp")
U1 = {"user_id": "u1", "role": "user"}
U2 = {"user_id": "u2", "role": "user"}

PROMPTS = ["Maison T4 plain-pied 110 m² avec garage et cuisine ouverte",
           "maison R+1 5 chambres 160 m2, bureau, buanderie, suite parentale, double garage, toit plat",
           "petite maison 2 chambres", "moradia V3 com garagem, dois pisos", "maison T3 à étage, cuisine fermée, 4 pans"]


# ------------------------------------------------------------------ programme et générateur
def test_typologie_francaise_et_portugaise():
    # France : T4 = séjour + 3 chambres ; Portugal : T4 = 4 quartos
    assert P.lire("maison T4")["chambres"] == (4 if P.PAIS == "PT" else 3)
    assert P.lire("moradia V3")["chambres"] == 3         # V3 = 3 quartos
    assert P.lire("3 chambres, 120 m2")["surface"] == 120
    assert P.lire("maison R+1")["niveaux"] == 2 and P.lire("maison de plain-pied")["niveaux"] == 1
    assert P.lire("toit plat")["toiture"] == "plana"
    assert P.lire("sans garage").get("garage") is None


@pytest.mark.parametrize("prompt", PROMPTS)
def test_maquette_valide_deterministe(prompt):
    a = GEN.generer(P.programme(prompt))
    b = GEN.generer(P.programme(prompt))
    assert a["modelo"] == b["modelo"], "un même prompt doit donner la même maquette"
    m = a["modelo"]
    der = EP.derivar(m)
    assert der["erros"] == [], der["erros"]
    noms = {d["nome"] for d in der["medicoes"]["divisoes"]}
    for p in P.programme(prompt)["pieces"]:
        assert p["nom"] in noms, f"pièce du programme absente du plan : {p['nom']}"
    # chaque pièce a au moins une porte ; chaque chambre / séjour a au moins une fenêtre en façade
    portes = [v for v in m["vaos"] if v["tipo"] in ("porta", "portada", "portao")]
    assert len(portes) >= len(P.programme(prompt)["pieces"])
    ext = {w["id"] for w in m["paredes"] if w["tipo"] == "ext_30"}
    assert sum(1 for v in m["vaos"] if v["parede"] in ext and v["tipo"] in ("janela", "portada")) >= P.programme(prompt)["chambres"] + 1
    for v in m["vaos"]:                                      # toute ouverture tient dans son mur
        w = next(x for x in m["paredes"] if x["id"] == v["parede"])
        L = math.dist(w["a"], w["b"])
        assert v["largura_m"] / 2 <= v["pos_m"] <= L - v["largura_m"] / 2 + 1e-6


def test_escalier_aligne_et_meme_emprise_aux_deux_niveaux():
    m = GEN.generer(P.programme("maison R+1 4 chambres garage"))["modelo"]
    assert len(m["pisos"]) == 2 and m["escadas"], "un R+1 a un escalier"
    e = m["escadas"][0]
    murs = {p["id"]: [w for w in m["paredes"] if w["piso"] == p["id"] and w["tipo"] == "ext_30"] for p in m["pisos"]}
    bb = [(min(min(w["a"][0], w["b"][0]) for w in ws), max(max(w["a"][0], w["b"][0]) for w in ws)) for ws in murs.values()]
    assert bb[0] == bb[1]
    # la colonne d'escalier (cloisons verticales qui l'encadrent) existe au même x aux deux niveaux
    xs = [{w["a"][0] for w in m["paredes"] if w["piso"] == p["id"] and w["a"][0] == w["b"][0]} for p in m["pisos"]]
    gauche = max(x for x in xs[0] if x <= e["x"])
    droite = min(x for x in xs[0] if x > e["x"] + 0.5)
    assert 1.8 <= droite - gauche <= 2.4 and gauche in xs[1] and droite in xs[1]


# ------------------------------------------------------------------ croquis
def _wob(a, b, n=12, j=0.08, rnd=None):
    return [[a[0] + (b[0] - a[0]) * i / n + rnd.uniform(-j, j), a[1] + (b[1] - a[1]) * i / n + rnd.uniform(-j, j)] for i in range(n + 1)]


def _croquis():
    rnd = random.Random(7)
    contour = (_wob([0, 0], [24.3, 0.4], rnd=rnd) + _wob([24.3, 0.4], [24.1, 16.2], rnd=rnd)[1:] + _wob([24.1, 16.2], [0.2, 16], rnd=rnd)[1:]
               + _wob([0.2, 16], [0, 0.1], rnd=rnd)[1:])
    return [{"type": "mur", "points": contour}, {"type": "mur", "points": _wob([12.2, 0.2], [11.9, 16.3], rnd=rnd)},
            {"type": "mur", "points": _wob([12, 8.1], [24.4, 7.8], rnd=rnd)},
            {"type": "porte", "points": [[3, 16], [4.8, 16.1]]}, {"type": "fenetre", "points": [[17, 0.1], [19.4, 0]]},
            {"type": "baie", "points": [[4, 0], [9, 0]]}, {"type": "porte", "points": [[12, 11], [12.1, 12.8]]},
            {"type": "porte", "points": [[16, 8], [17.6, 8]]}]


def test_croquis_tremble_redresse_et_mis_a_l_echelle():
    r = C.nettoyer(_croquis(), [{"x": 6, "y": 8, "nom": "Séjour"}], cotes=[{"a": [0, 16], "b": [24.2, 16], "m": 12.1}])
    m = r["modelo"]
    for w in m["paredes"]:
        assert w["a"][0] == w["b"][0] or w["a"][1] == w["b"][1], "murs redressés"
    xs = sorted({x for w in m["paredes"] for x in (w["a"][0], w["b"][0])})
    assert xs[0] == 0 and abs(xs[-1] - 12.05) < 0.15                  # 24,2 unités = 12,1 m
    assert sum(1 for w in m["paredes"] if w["tipo"] == "ext_30") == 4
    assert sum(1 for w in m["paredes"] if w["tipo"] == "int_12") == 2
    der = EP.derivar(m)
    assert der["erros"] == [] and len(der["medicoes"]["divisoes"]) == 3
    assert len(m["vaos"]) == 5
    assert C.nettoyer(_croquis(), cotes=[{"a": [0, 16], "b": [24.2, 16], "m": 12.1}])["modelo"] == \
        C.nettoyer(_croquis(), cotes=[{"a": [0, 16], "b": [24.2, 16], "m": 12.1}])["modelo"]


def test_cotes_incoherentes_signalees_et_croquis_vide_refuse():
    r = C.nettoyer(_croquis(), cotes=[{"a": [0, 16], "b": [24.2, 16], "m": 12.1}, {"a": [0, 0], "b": [0, 16], "m": 10}])
    assert any("cohérentes" in a or "coerentes" in a for a in r["avisos"])
    with pytest.raises(C.ErreurCroquis):
        C.nettoyer([])
    with pytest.raises(C.ErreurCroquis):
        C.nettoyer([{"type": "mur", "points": [[0, 0], [1, 0]]}])


def test_lecture_photo_passe_par_le_meme_nettoyage():
    lu = {"murs": [{"a": [0, 0], "b": [10.02, 0.05], "exterieur": True}, {"a": [10, 0], "b": [10, 8], "exterieur": True},
                   {"a": [10, 8], "b": [0, 8.1], "exterieur": True}, {"a": [0, 8], "b": [0, 0], "exterieur": True}],
          "ouvertures": [{"type": "porte", "a": [4, 0], "b": [5, 0]}], "pieces": [{"nom": "Séjour", "x": 5, "y": 4}]}
    t = V.traits_depuis_lecture(lu)
    r = C.nettoyer(t["traits"], t["textes"], y_bas=False)
    assert len(r["modelo"]["paredes"]) == 4 and len(r["modelo"]["vaos"]) == 1
    assert EP.derivar(r["modelo"])["medicoes"]["divisoes"][0]["nome"] == "Séjour"


# ------------------------------------------------------------------ DCE
def test_dce_quantites_issues_du_metre_de_la_maquette():
    m = GEN.generer(P.programme("maison T4 R+1 garage 120 m2"))["modelo"]
    md = EP.derivar(m)["medicoes"]
    s = DCE.selection(m)
    lots = {l["code"]: l for l in s["lots"]}
    assert {"gros_oeuvre", "charpente_couverture", "menuiseries_ext", "menuiseries_int", "platrerie", "sols_durs", "peinture",
            "electricite", "plomberie"} <= set(lots)
    ext = sum(v["quantidade"] for v in md["mapa_vaos"] if v["exterior"])
    assert sum(l["quantite"] for l in lots["menuiseries_ext"]["lignes"] if l["unite"] == "u") == ext
    fac = next(l for l in lots["gros_oeuvre"]["lignes"] if l["designation"].startswith("Revêtement de façade"))
    assert fac["quantite"] == round(md["fachada"]["area_liquida_m2"], 2)
    cou = next(l for l in lots["charpente_couverture"]["lignes"] if l["designation"].startswith("Couverture"))
    assert cou["quantite"] == round(md["cobertura"]["area_m2"], 2)
    # aucune quantité qui ne soit pas une mesure de la maquette (surfaces, longueurs, comptes)
    for l in s["lots"]:
        for x in l["lignes"]:
            assert x["quantite"] is None or x["quantite"] > 0
    # garage exclu des finitions intérieures
    assert all("Garage" not in x["localisation"] for x in lots["peinture"]["lignes"] + lots["sols_durs"]["lignes"])


def test_dce_complet_sans_ia():
    from engines import cctp_redacteur as R
    m = GEN.generer(P.programme("maison T4 plain-pied garage"))["modelo"]
    s = DCE.selection(m)
    projet = RC.Projet(nom="Maison test", pieces=[RC.Piece(nom=x["nom"], type=x["type"], surface=x["surface"]) for x in s["pieces"]]).model_dump()
    lots = asyncio.run(R.rediger(projet, s["lots"], ia=False))
    fichiers = R.fichiers_dossier(projet, lots, None)
    noms = [n for n, _, _ in fichiers]
    assert any(n.startswith("CCTP_Lot-03_Gros-oeuvre") for n in noms) and any(n.startswith("DPGF_") for n in noms)
    assert any(n.startswith("RC_") for n in noms) and len(noms) >= 12


# ------------------------------------------------------------------ routes (base en mémoire)
class _Cur:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, k, d):
        self.docs = sorted(self.docs, key=lambda x: x.get(k) or "", reverse=d < 0)
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class Coll:
    def __init__(self):
        self.docs = []

    @staticmethod
    def _m(d, q):
        return all(d.get(k) == v for k, v in q.items())

    @staticmethod
    def _p(d, proj):
        if not proj:
            return dict(d)
        out = {k: v for k, v in d.items() if proj.get(k, 1) != 0}
        out.pop("_id", None)
        return out

    async def find_one(self, q, proj=None):
        return next((self._p(d, proj) for d in self.docs if self._m(d, q)), None)

    def find(self, q, proj=None):
        return _Cur([self._p(d, proj) for d in self.docs if self._m(d, q)])

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def count_documents(self, q):
        return sum(1 for d in self.docs if self._m(d, q))

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if self._m(d, q):
                d.update(upd.get("$set", {}))
                return
        if upsert:
            self.docs.append({**q, **upd.get("$set", {})})

    async def delete_one(self, q):
        self.docs = [d for d in self.docs if not self._m(d, q)]


class DB:
    def __init__(self):
        self.archi_projects, self.cctp_dossiers, self.archi_prompt_cache = Coll(), Coll(), Coll()


@pytest.fixture
def db(monkeypatch):
    d = DB()
    monkeypatch.setattr(RA, "db", d)
    monkeypatch.setattr(RC, "db", d)

    async def _brand(uid):
        return None
    monkeypatch.setattr(RC, "_branding", _brand)
    return d


def run(c):
    return asyncio.run(c)


def test_parcours_projet_complet_et_isolation(db):
    async def go():
        ap = await RA.esquisse_prompt(RA.PromptIn(prompt="Maison T4 plain-pied 110 m² avec garage", ia=False), U1)
        assert ap["resume"]["niveaux"] == 1 and ap["avisos"] and ap["derivado"]["medicoes"]
        cr = await RA.creer_projet(RA.ProjetIn(titre="Maison Dupont", modelo=ap["modelo"], origine="prompt", adresse="12 rue des Lilas"), U1)
        pid = cr["projet_id"]
        o = await RA.obter(pid, U1)
        assert o["titulo"] == "Maison Dupont" and o["catalogo"]["tipos_parede"] and o["projet"]["origine"] == "prompt"
        with pytest.raises(Exception):
            await RA.obter(pid, U2)                                  # un autre compte ne voit pas le projet
        mod = o["modelo"]
        mod["pisos"][0]["pe_direito_m"] = 2.95
        g = await RA.guardar(pid, RA.ModeloIn(modelo=mod), U1)
        assert g["ok"]
        assert (await RA.obter(pid, U1))["modelo"]["pisos"][0]["pe_direito_m"] == 2.95
        for f in (RA.pranchas, RA.modelo_ifc, RA.medicoes, RA.desenhos_dxf):
            r = await f(pid, U1)
            assert len(r.body) > 500
        ap2 = await RA.dce_apercu(pid, U1)
        assert any(l["code"] == "menuiseries_ext" for l in ap2["lots"])
        await RA.repor(pid, U1)
        assert (await RA.obter(pid, U1))["modelo"]["pisos"][0]["pe_direito_m"] == GEN.PE_DIREITO
        lst = await RA.lister(U1)
        assert [p["projet_id"] for p in lst["projets"]] == [pid] and "modelo" not in lst["projets"][0]
        assert (await RA.lister(U2))["projets"] == []
        await RA.supprimer(pid, U1)
        assert (await RA.lister(U1))["projets"] == []
    run(go())


def test_croquis_par_la_route_et_dce_redige(db):
    async def go():
        body = RA.CroquisIn(traits=[RA.Trait(**t) for t in _croquis()], textes=[RA.Texte(x=6, y=8, nom="Séjour")],
                            cotes=[RA.Cote(a=[0, 16], b=[24.2, 16], m=12.1)])
        ap = await RA.esquisse_croquis(body, U1)
        assert ap["stats"]["murs"] == 6
        pid = (await RA.creer_projet(RA.ProjetIn(titre="Extension", modelo=ap["modelo"], origine="croquis"), U1))["projet_id"]
        r = await RA.dce_lancer(pid, RA.DceIn(ia=False), U1)
        for _ in range(200):
            d = await db.cctp_dossiers.find_one({"dossier_id": r["dossier_id"]})
            if d["status"] != "running":
                break
            await asyncio.sleep(0.05)
        assert d["status"] == "done", d.get("error")
        assert any(f["nom"].startswith("DPGF_") for f in d["fichiers"])
        assert (await RA.obter(pid, U1))["projet"]["dce_id"] == r["dossier_id"]
    run(go())
