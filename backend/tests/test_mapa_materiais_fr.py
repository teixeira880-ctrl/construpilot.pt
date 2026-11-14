"""14/11 (.fr): o mapa de materiais e a estrutura calculada também no .fr — designações francesas decompostas e
nenhum material apresentado em português."""
import re

from engines import estrutura_implantacao as EI, estrutura_metalica as EM
from engines.mapa_materiais import mapa
from engines.mapa_materiais_i18n import traduzir

PT = re.compile(r"ção|ções|ões|ã|õ|\bnão\b|\bem\b|\bpara\b|\bpor\b|\bcom\b|\bdos?\b|\bdas?\b|\bmedir\b|Aço|Betão|espessura|caixa|saco|rolo|lata|balde|madre|chumbadour|parafus")
DESIG_FR = [("Enrobé BBSG 0/14 e=6 cm", "m2"), ("Enrobé", "m2"), ("Pavés béton drainants", "m2"), ("Bordure béton T2", "ml"),
            ("Espaces verts engazonnés", "m2"), ("Marquage au sol", "m2"), ("Cloison plaque de plâtre 72/48", "m2"),
            ("Faux plafond BA13", "m2"), ("Maçonnerie parpaing 50x20x20", "m2"), ("Enduit e=2 cm", "m2"), ("Chape e=5 cm", "m2"),
            ("Carrelage 60x60 cm", "m2"), ("Peinture 2 couches", "m2"), ("Étanchéité membrane bicouche", "m2"),
            ("Béton armé C25/30 90 kg/m3", "m3"), ("Acier HA B500B", "kg"), ("Fenêtre 120x100", "u"), ("Fouilles en rigole", "m3"),
            ("Coffrage des poteaux", "m2"), ("Dallage sur terre-plein e=0,15", "m2"), ("Boulons M20 classe 8.8", "u"),
            ("Panneau sandwich de bardage", "m2"), ("Faîtière en tôle laquée", "ml"), ("Protection anticorrosion 2 couches", "m2"),
            ("Acier S275 en profilés IPE300 — traverses", "kg")]


def _linhas():
    pts = [(0, 0), (60, 0), (60, 40), (0, 40)]
    return ([{"designation": d, "unit": u, "qty": 10} for d, u in DESIG_FR]
            + EM.calcular(pts, nome="t", lang="fr", pais="FR", code_postal="69001", altitude=200)["linhas"]
            + EI.calcular(pts, nome="t", lang="fr", pais="FR")["linhas"])


def test_designacoes_francesas_decompostas():
    m = mapa(_linhas())
    sem = [a["designacao"] for a in m["artigos"] if a["estado"] in ("sem_receita", "global")]
    assert not sem, sem


def test_nada_em_portugues_no_fr():
    m = traduzir(mapa(_linhas()), "fr")
    textos = [m["aviso"]] + [x for a in m["artigos"] for mt in a["materiais"] for x in (mt["material"], mt["fonte"], mt["em_falta"], mt["embalagens"]) if x]
    textos += [a["motivo"] for a in m["artigos"] if a.get("motivo")] + [l["designation"] + " " + l["description"] for l in _linhas()[len(DESIG_FR):]]
    restos = sorted({t for t in textos if PT.search(t.replace(" ou ", " ").replace(" ou ", " "))})
    assert not restos, restos[:10]


def test_neve_francesa_pelo_departamento():
    r = EM.calcular([(0, 0), (60, 0), (60, 40), (0, 40)], nome="t", lang="fr", pais="FR", code_postal="73000", altitude=600)
    assert "NF EN 1991-1-3/NA" in r["hipoteses"] and "B500B" in " ".join(l["designation"] for l in r["linhas"])
