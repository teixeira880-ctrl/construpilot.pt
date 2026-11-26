"""Motor de construção tradicional (engines.tradicional): elementos dimensionados, alvenaria fiada a fiada, mapa por piso, livrables."""
import json
import math
import os

import pytest

from engines.tradicional.estudo import adapter, calcular, defaults, estudo
from engines.tradicional.estudo.note import note
from engines.tradicional.estudo.pdf import dossier
from engines.tradicional.estudo.viewer import html_viewer
from engines.tradicional.estudo.xlsx import xlsx

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "mep_moradia_exemplo.json")


@pytest.fixture(scope="module")
def ex():
    return calcular(defaults.exemplo())


def test_pilares_e_vigas(ex):
    e = ex["estudo"]
    assert e["nPilares"] == 10 and e["nSapatas"] == 10
    # nenhuma viga com vão maior que o máximo entre pilares, exceto se não houver lugar fora dos vãos (aviso)
    assert all(v["L"] <= ex["regras"]["vaoMaxPilares"] + 300 for v in ex["vigas"])
    # cada viga liga dois pilares do mesmo piso e todas verificam
    assert all(len(v["pilares"]) == 2 for v in ex["vigas"])
    assert not any("não verifica" in a for a in ex["avisos"])


def test_descida_de_cargas(ex):
    """O pilar do R/C recebe as reações das vigas do R/C + tudo o que vem do andar de cima."""
    por = {}
    for p in ex["pilares"]:
        por.setdefault(p["pilar"], []).append(p)
    for lst in por.values():
        if len(lst) == 2:
            cima, baixo = sorted(lst, key=lambda p: -p["z0"])
            assert baixo["Ntot_G"] > cima["Ntot_G"]
    s = {x["pilar"]: x for x in ex["sapatas"]}
    for pid, lst in por.items():
        base = min(lst, key=lambda p: p["z0"])
        assert s[pid]["G"] == pytest.approx(base["Ntot_G"])


def test_aco_vem_do_dimensionamento(ex):
    from engines.calc_lots import structure as ST
    v = ex["vigas"][0]
    r = ST.poutre_ba({"portee_m": v["L"] / 1000, "b_m": v["b"] / 1000, "h_m": v["h"] / 1000, "g_kn_m": v["g"], "q_kn_m": v["q"], "appuis": v["apoios"]})
    assert v["kg"] == pytest.approx(r["quantites"]["acier_kg"]) and v["armadura"] == r["barres"]["label"]


def test_alvenaria_fiada_a_fiada(ex):
    w = next(x for x in ex["paredes"] if x["id"] == "RC-1")
    U = defaults.UNIDADES["T30x20x22"]
    assert w["fiadas"] == math.ceil(2700 / (U["h"] + U["junta"]))
    nominal = w["areaAlv"] / ((U["l"] + U["junta"]) * (U["h"] + U["junta"]) / 1e6)
    assert w["contagem"] == "unidade a unidade"                # motor de alvenaria da plataforma (cada tijolo no seu sítio)
    assert nominal <= w["unidades"] <= nominal * 1.4           # peças assentes (inteiras + cortadas) ≥ área / módulo
    W = [x for x in ex["paredes"] if x["nivel"] == w["nivel"] and x["unidade"] == w["unidade"]]
    nom = sum(x["areaAlv"] for x in W) / ((U["l"] + U["junta"]) * (U["h"] + U["junta"]) / 1e6)
    compra = sum(x["a_comprar"] for x in ex["alvenariaResumo"] if x["nivel"] == w["nivel"] and x["unidade"] == w["unidade"])
    assert nom <= compra <= nom * 1.15                         # a comprar: inteiras + unidades para os cortes (sobras reaproveitadas)
    assert ex["estudo"]["unidadesAlvenaria"] == sum(x["a_comprar"] for x in ex["alvenariaResumo"]) + ex["coberturas"][0]["empenas"]["unidades"]


def test_mapa_por_piso(ex):
    st = estudo(defaults.exemplo())
    cats = [l["cat"] for l in st["linhas"]]
    assert cats[0].endswith("Fundações") and any("R/C — betão armado" in c for c in cats) and any("1.º andar — alvenarias" in c for c in cats)
    assert any(c.endswith("Cobertura") for c in cats)
    assert st["totais"]["total"] == 0                      # sem biblioteca: nenhum preço inventado
    bet = sum(l["qtd"] for l in st["linhas"] if l["un"] == "m³" and "Betão C25" in l["designacao"])
    assert bet == pytest.approx(ex["estudo"]["m3Betao"], rel=1e-3)


def test_planta_real_e_retangulo():
    r = calcular(adapter.from_mep_input(json.load(open(FIX))))
    assert r["estudo"]["nPilares"] > 10 and r["estudo"]["m3Betao"] > 30
    r2 = note({"implantacao": {"comprimento_m": 9, "largura_m": 7, "pisos": 2}, "render": False})
    assert r2["pdf"][:4] == b"%PDF" and [x[3] for x in r2["files_extra"]] == ["xlsx", "html"]


def test_livrables(ex):
    st = estudo(defaults.exemplo())
    pdf = dossier(st["resultado"], st["linhas"], st["totais"], {"company_name": "Construtora Teste, Lda"}, [])
    import pymupdf
    d = pymupdf.open(stream=pdf, filetype="pdf")
    txt = "".join(p.get_text() for p in d)
    assert "Planta de fundações" in txt and "Alçado de parede — RC-1" in txt and "Construtora Teste" in txt
    assert xlsx(st["resultado"], st["linhas"], st["totais"])[:2] == b"PK"
    assert b"window.CLT={" in html_viewer(st["resultado"], "x")
