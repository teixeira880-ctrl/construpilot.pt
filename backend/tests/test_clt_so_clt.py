"""CLT only: exact quantities, cutting losses and production cost (bim_studio.clt_only)."""
import json
import os

import pytest
from shapely.geometry import Polygon

from bim_studio import clt_only as C
from bim_studio.clt_economics import library_merged, merged

HOME_A = os.environ.get("HOME_A_PDF", "/mnt/user-data/uploads/17d28da0-Home_A.en2.pdf")

# 6 × 4 m box, 100 mm walls, one 1.2 m door opening under a CLT lintel on the south wall, 140 mm roof with a notch
FLOOR = {"name": "RDC", "height_m": 3.0,
         "walls": [{"thickness_mm": 100, "layers": 5, "length_m": 18.4}],
         "segments": [{"ref": "s1", "thickness_mm": 100, "length_m": 2.4, "rect_m": [0, 0, 2.4, 0.1]},
                      {"ref": "s2", "thickness_mm": 100, "length_m": 2.4, "rect_m": [3.6, 0, 6.0, 0.1]},
                      {"ref": "n", "thickness_mm": 100, "length_m": 6.0, "rect_m": [0, 3.9, 6.0, 4.0]},
                      {"ref": "w", "thickness_mm": 100, "length_m": 3.8, "rect_m": [0, 0.1, 0.1, 3.9]},
                      {"ref": "e", "thickness_mm": 100, "length_m": 3.8, "rect_m": [5.9, 0.1, 6.0, 3.9]}],
         "lintels": [{"ref": "lintel-1", "rect_m": [2.4, 0, 3.6, 0.1], "head_m": 2.3, "thickness_mm": 100}],
         "panels": [{"kind": "lintel", "label": "Lintel 100 mm", "thickness_mm": 100, "layers": 5, "area_m2": 0.84},
                    {"kind": "cobertura", "label": "Cobertura", "thickness_mm": 140, "layers": 5, "area_m2": 22.0}],
         # must be dropped: nothing but CLT is priced
         "rooms": [{"name": "Sala", "area_m2": 20, "perimeter_m": 18}], "windows": [{"width_m": 1.2, "height_m": 1.2, "count": 3}]}
GEO = {"RDC": {"placas": [{"kind": "cobertura", "thickness_mm": 140, "layers": 5, "vazios_m": [],
                           "contorno_m": [(0, 0), (6, 0), (6, 4), (2, 4), (2, 3), (0, 3)]}]}}


def _run():
    return C.compute({"floors": [FLOOR]}, merged({}), library_merged({}), GEO)


def test_only_clt_is_measured_and_priced():
    q = _run()
    assert {e["elemento"] for e in q["elementos"]} == {"Paredes", "Cobertura"}
    assert {l["codigo"] for l in q["linhas"]} <= {"MP-LAMELA", "MP-COLA-PUR", "EN-ELETRICIDADE", "EN-AGUA", "COL-OPERADOR", "TR-MATERIA-PRIMA"}
    assert q["custo_producao_eur"] == pytest.approx(sum(l["custo_eur"] for l in q["linhas"]), abs=0.05)


def test_opening_is_cut_out_of_its_wall_piece():
    q = _run()
    south = next(p for p in q["pecas"] if p["vaos"])
    assert south["comprimento_m"] == pytest.approx(6.0, abs=0.01)             # both runs and the lintel: one piece
    assert south["vaos_m2"] == pytest.approx(1.2 * 2.3, abs=0.01)             # the door is cut out of it
    assert not [p for p in q["pecas"] if p["elemento"] == "Lintel à parte"]    # the lintel is not counted twice
    walls = next(e for e in q["elementos"] if e["elemento"] == "Paredes")
    assert walls["liquido_m2"] == pytest.approx(walls["bruto_m2"] - 1.2 * 2.3, abs=0.01)
    assert all(c["ok"] for c in q["verificacao"])


def test_losses_come_from_the_layout_and_cost_follows_the_pressed_volume():
    q = _run()
    assert q["clt_prensado_m3"] > q["clt_liquido_m3"]
    assert q["perda_m3"] == pytest.approx(q["clt_prensado_m3"] - q["clt_liquido_m3"], abs=0.002)
    timber = next(l for l in q["linhas"] if l["codigo"] == "MP-LAMELA")
    assert timber["quantidade"] == pytest.approx(q["clt_prensado_m3"] * float(merged({})["timber_input_m3_per_m3"]["value"]), rel=0.01)
    fixed = q["formato_fixo"]
    assert fixed["clt_liquido_m3"] == q["clt_liquido_m3"]
    assert fixed["clt_prensado_m3"] >= q["clt_prensado_m3"] and fixed["custo_producao_eur"] >= q["custo_producao_eur"]


def test_roof_outline_is_pressed_as_rectangles_inside_it():
    roof = Polygon(GEO["RDC"]["placas"][0]["contorno_m"])
    pieces, _along = C._strips(roof, 3.5, 18.0)
    assert sum(p[2] for p in pieces) == pytest.approx(roof.area, abs=1e-6)
    assert sum(p[0] * p[1] for p in pieces) == pytest.approx(roof.area, abs=1e-3)      # rectilinear outline: nothing pressed outside it
    assert all(w <= 3.5 + 1e-9 and l <= 18.0 + 1e-9 for l, w, *_r in pieces)
    with_stair = Polygon(roof.exterior.coords, [[(3, 1), (4, 1), (4, 2), (3, 2)]])
    pieces, _along = C._strips(with_stair, 3.5, 18.0)
    assert sum(p[0] * p[1] - p[2] for p in pieces) == pytest.approx(1.0, abs=1e-3)           # the stair opening is a cutting loss


def test_same_input_gives_identical_figures():
    strip = lambda q: json.dumps({k: v for k, v in q.items() if k != "_desenhos"}, sort_keys=True, default=str)
    assert strip(_run()) == strip(_run())


def test_note_has_the_dimensioned_annex():
    o = C.note({"floors": [FLOOR]}, merged({}), library_merged({}), "Teste · Só CLT", geometria=GEO)
    assert o["pdf"][:4] == b"%PDF" and o["data"]["verificacao_ok"] is True
    assert "só CLT" in " ".join(o["resumo"])


@pytest.mark.skipif(not os.path.exists(HOME_A), reason="client drawing not in the repository")
def test_home_a_reviewed_pdf():
    data = open(HOME_A, "rb").read()
    plan = C.floors_from_reviewed_pdf(data, client_rules=False)                # everything hatched as CLT on the plans
    q = C.compute({"floors": plan["floors"]}, merged({}), library_merged({}), plan["geometria"])
    assert q["clt_liquido_m3"] == pytest.approx(74.235, abs=0.01)
    f = C.floors_from_reviewed_pdf(data)                                       # 14/11: every wall hatched as CLT is CLT, nothing is removed
    assert f["retirado"] == []
    q = C.compute({"floors": f["floors"]}, merged({}), library_merged({}), f["geometria"])
    assert q["clt_liquido_m3"] == pytest.approx(74.235, abs=0.01)
    assert 84 < q["fachadas_inteiras"]["clt_prensado_m3"] < 88                 # whole façade panels: the ≈ 85 m³ the manufacturer expects
    assert q["clt_bruto_m2"] - q["vaos_cortados_m2"] == pytest.approx(q["clt_liquido_m2"], abs=0.02)
    assert all(c["ok"] for c in q["verificacao"]) and len(q["verificacao"]) == 2
    assert C.floors_from_reviewed_pdf(data + b" ") is None


# ----------------------------------------------------------------------------------------------- Assistant tool
def test_assistant_tool_is_declared_and_routed():
    from engines.calc_lots import outils
    assert "clt_so_quantidades" in outils.CALC_TOOL_NAMES
    assert "clt_so_quantidades" in outils.PROTOCOL_PT and "clt_so_quantidades" in outils.PROGRESS_LABELS


def test_assistant_tool_from_floors_always_carries_the_follow_up():
    import pymupdf
    from engines.calc_lots import outils
    o = outils.run("clt_so_quantidades", {"titulo": "Teste · Só CLT", "_entrada": {"floors": [FLOOR]}})
    assert o["pdf"][:4] == b"%PDF" and o["data"]["clt_liquido_m3"] > 0
    text = " ".join(pg.get_text() for pg in pymupdf.open(stream=o["pdf"], filetype="pdf"))
    assert "Lista de peças" in text and "Anexo A" in text                     # piece list + dimensioned drawings: never a dossier without them
    assert "cruzamento" in o["resume"].lower()                                # says the written cross-check was not possible without the PDF
    with pytest.raises(ValueError):
        outils.run("clt_so_quantidades", {"titulo": "sem pisos"})


@pytest.mark.skipif(not os.path.exists(HOME_A), reason="client drawing not in the repository")
def test_assistant_tool_on_the_home_a_pdf():
    from engines.calc_lots import outils
    o = outils.run("clt_so_quantidades", {"_pdf": open(HOME_A, "rb").read(), "empresa": "clt-rezult"})
    assert o["data"]["clt_liquido_m3"] == pytest.approx(74.235, abs=0.01) and o["data"]["verificacao_ok"] is True
    assert "tudo confere" in o["resume"]


def test_written_cross_check_on_any_pdf():
    import pymupdf
    doc = pymupdf.open()
    pg = doc.new_page()
    pg.insert_text((50, 60), "CLT Panel140-5s   CLT 5s 100 wall   Ceiling height 2700 mm   Opening 900x2100H")
    rows = C.written_on_any_plan(doc.tobytes(), [FLOOR])
    by = {r["item"]: r for r in rows}
    assert by["Laje e cobertura CLT"]["ok"] and by["Paredes CLT"]["ok"] and by["Alturas"]["ok"]
    other = dict(FLOOR, panels=[{"kind": "cobertura", "label": "x", "thickness_mm": 200, "layers": 5, "area_m2": 22.0}])
    assert not {r["item"]: r for r in C.written_on_any_plan(doc.tobytes(), [other])}["Laje e cobertura CLT"]["ok"]


@pytest.mark.skipif(not os.path.exists(HOME_A), reason="client drawing not in the repository")
def test_home_a_3d_model_matches_the_plans():
    """The model used for the 3D images and the drawings must be the house of the plans: first-floor walls on grid
    axes 2 and 3, and every exterior opening of the model in a gap between the CLT runs measured on the plans."""
    from engines.calc_lots import pacote_ua
    m = pacote_ua.parametros("home_a_rezult_kyiv")["modelo_estrutural"]
    gx = {g["nome"]: g["pos_m"] for g in m["grelhas_x"]}
    upper = next(w for w in m["muros"] if w["cota_base_m"] > 3 and w["pontos"][0] == w["pontos"][-1])
    xs = sorted({round(p[0], 3) for p in upper["pontos"]})
    assert xs == sorted({round(gx["2"], 3), round(gx["3"], 3), round(gx["7"], 3)})
    plan = C.floors_from_reviewed_pdf(open(HOME_A, "rb").read(), client_rules=False)
    assert len(m["vaos"]) == 17
    for fl, base, dx in ((plan["floors"][0], 0.0, 2.216), (plan["floors"][1], 3.36, 2.456)):
        runs = [(x0 - dx, y0 + 18.747, x1 - dx, y1 + 18.747) for x0, y0, x1, y1 in (s["rect_m"] for s in fl["segments"])]
        for v in (v for v in m["vaos"] if v["cota_base"] == base):
            a, b = v["de"] + 0.03, v["ate"] - 0.03
            for x0, y0, x1, y1 in runs:
                if v["eixo"] == "x":                                           # wall along x at y = linha
                    hit = y0 - 0.06 <= v["linha"] <= y1 + 0.06 and x1 - x0 > y1 - y0 and x0 < b and x1 > a
                else:
                    hit = x0 - 0.06 <= v["linha"] <= x1 + 0.06 and y1 - y0 > x1 - x0 and y0 < b and y1 > a
                assert not hit, (v, (x0, y0, x1, y1))


# ------------------------------------------------------------------------------------ sale, margin, country prices
def test_sale_and_margin_from_the_library():
    lib = library_merged({"VENDA-CLT": {"category": "venda", "name": "Painel CLT fornecido", "unit": "m³", "cost_eur": "0", "sale_eur": "800",
                                        "basis": "m3_clt", "per_basis": "1", "origin": "empresa", "source": "tabela da empresa"}})
    q = C.compute({"floors": [FLOOR]}, merged({}), lib, GEO)
    assert q["venda_eur"] == pytest.approx(q["clt_liquido_m3"] * 800, abs=0.05) and q["venda_origem"] == "empresa"
    assert q["margem_eur"] == pytest.approx(q["venda_eur"] - q["custo_producao_eur"], abs=0.02)
    assert not any(h.startswith("VENDA-CLT") for h in q["hipoteses"])          # a company price is not a hypothesis
    assert any(h.startswith("VENDA-CLT") for h in _run()["hipoteses"])         # the market reference is


def test_country_market_prices_only_where_the_company_has_none():
    base, ua = library_merged({}), library_merged({}, "UA")
    assert ua["EN-ELETRICIDADE"]["cost_eur"] != base["EN-ELETRICIDADE"]["cost_eur"] and "Ucrânia" in ua["EN-ELETRICIDADE"]["source"]
    assert ua["COL-OPERADOR"]["origin"] == "mercado" and float(ua["COL-OPERADOR"]["cost_eur"]) < float(base["COL-OPERADOR"]["cost_eur"])
    assert ua["MP-LAMELA"]["cost_eur"] == base["MP-LAMELA"]["cost_eur"] and "sem preço público" in ua["MP-LAMELA"]["source"]
    own = library_merged({"EN-ELETRICIDADE": {"cost_eur": "0.15", "origin": "empresa", "source": "fatura"}}, "UA")
    assert own["EN-ELETRICIDADE"]["cost_eur"] == "0.15" and own["EN-ELETRICIDADE"]["source"] == "fatura"
    assert library_merged({}, "PT") == base and library_merged({}, None) == base


# ------------------------------------------------------------------------------------- English and assembled-CLT views
def test_english_dossier_has_no_portuguese_left():
    import re
    import pymupdf
    o = C.note({"floors": [FLOOR]}, merged({}), library_merged({}, "UA"), "Test · CLT only", lingua="en", geometria=GEO, imagens=False,
               cruzamento=[{"item": "Paredes CLT", "escrito": "CLT 5s 100 wall", "usado": "100 mm", "ok": True, "nota": ""}])
    text = " ".join(pg.get_text() for pg in pymupdf.open(stream=o["pdf"], filetype="pdf"))
    assert "Production cost" in text and "Piece list" in text and "CLT walls" in text
    left = [w for w in re.findall(r"[A-Za-zÀ-ÿ]*[ãõçáéíóúâêôà][A-Za-zÀ-ÿ]*", text) if w not in ("Ucrânia", "façade")]
    assert not left, left[:20]
    assert not re.search(r"\b(hipotese|Paredes|Cobertura|Laje|camadas)\b", text)


def test_assembled_clt_boxes_are_the_calculated_clt():
    """The 3D shows the CLT that was calculated: same volume as the net CLT (visual joints aside), openings left open."""
    from bim_studio import clt_render
    q = _run()
    bs = clt_render.boxes({"floors": [FLOOR]}, merged({}), GEO)
    volume = sum((b[3] - b[0]) * (b[4] - b[1]) * (b[5] - b[2]) for b in bs)
    assert volume == pytest.approx(q["clt_liquido_m3"], rel=0.03)
    door = [b for b in bs if b[6] == "parede" and b[2] > 2.0 and b[5] - b[2] < 1.0]      # only the part over the door remains in the gap
    assert door and all(b[2] == pytest.approx(2.3) for b in door)


def test_prices_that_are_not_the_company_s_are_marked_fictitious():
    import pymupdf
    text = lambda o: " ".join(pg.get_text() for pg in pymupdf.open(stream=o["pdf"], filetype="pdf"))
    o = C.note({"floors": [FLOOR]}, merged({}), library_merged({}), "Teste · Só CLT", geometria=GEO, imagens=False)
    assert text(o).count("PREÇOS FICTÍCIOS") >= 3 and "(preços" in text(o)                 # top, cost section, sale section + the cost labels
    assert o["resumo"][1].startswith("PREÇOS FICTÍCIOS")
    en = C.note({"floors": [FLOOR]}, merged({}), library_merged({}), "Test · CLT only", lingua="en", empresa="clt-rezult", geometria=GEO, imagens=False)
    assert "FICTITIOUS PRICES. We do not have the price library of CLT Rezult" in text(en).replace("\n", " ")
    base = library_merged({})
    codes = ("MP-LAMELA", "MP-COLA-PUR", "EN-ELETRICIDADE", "EN-AGUA", "COL-OPERADOR", "TR-MATERIA-PRIMA", "VENDA-CLT")
    own = library_merged({c: {**base[c], "origin": "empresa", "source": "tabela da empresa", "sale_eur": "800" if c == "VENDA-CLT" else base[c].get("sale_eur")}
                          for c in codes})
    mine = C.note({"floors": [FLOOR]}, merged({}), own, "Teste · Só CLT", geometria=GEO, imagens=False)
    assert "FICTÍCIOS" not in text(mine) and not mine["resumo"][1].startswith("PREÇOS")


def test_complete_study_takes_approximate_complements_without_touching_the_estimate():
    import pymupdf
    from bim_studio import clt_complements as CC, clt_study
    entrada = {"floors": [{"name": "RDC", "height_m": "3", "walls": [{"thickness_mm": "100", "layers": 5, "length_m": "20"}],
                           "roof_buildup_m2": "24", "facade_m2": "60", "ceiling_m2": "20", "board_layers_m2": "80",
                           "rooms": [{"nome": "Sala", "tipo": "sala", "area_m2": "14", "perimetro_m": "15"},
                                     {"nome": "WC", "tipo": "casa_de_banho", "area_m2": "6", "perimetro_m": "10", "aparelhos": ["lavatorio"]}]}]}
    rows = CC.lines(entrada, terrace_m2=10, roof_edge_m=20)
    assert {r["capitulo"] for r in rows} >= {"vmc", "aquecimento", "cobertura", "fachada", "ligacoes", "terraco"}
    assert all(float(r["quantidade"]).is_integer() for r in rows if r["unidade"] == "un")
    assert all(r["custo_un"] == 0 for r in rows if r["so_quantidade"]) and all(r["regra"]["pt"] and r["regra"]["en"] for r in rows)
    base = clt_study.note(entrada, merged({}), library_merged({}), "Casa")
    full = clt_study.note(entrada, merged({}), library_merged({}), "Casa", complementos=rows)
    assert full["data"]["custo_total_eur"] == base["data"]["custo_total_eur"]              # the estimate itself is unchanged
    comp = full["data"]["complementos"]
    assert comp["custo_total_eur"] == pytest.approx(base["data"]["custo_total_eur"] + CC.totals(rows)["custo_eur"], abs=0.05)
    text = " ".join(pg.get_text() for pg in pymupdf.open(stream=full["pdf"], filetype="pdf"))
    assert "APROXIMAÇÃO" in text and "CASA COMPLETA, aproximado" in text and "PREÇOS FICTÍCIOS" in text


def test_assistant_method_and_complete_study_tool():
    from engines.calc_lots import outils
    for rule in ("MÉTODO DE TRABALHO PARA QUANTIDADES", "PREÇOS FICTÍCIOS", "pergunta numa frase", "seguimento"):
        assert rule in outils.PROTOCOL_PT
    floors = {"floors": [dict(FLOOR, rooms=[{"nome": "Sala", "tipo": "sala", "area_m2": "20", "perimetro_m": "18"}], roof_buildup_m2="22", facade_m2="50",
                              windows=[{"largura_m": "1.2", "tipo": "janela"}])]}
    o = outils.run("estudo_clt_completo", {"titulo": "Casa teste", "_entrada": floors})
    assert o["data"]["complementos"]["custo_total_eur"] > o["data"]["custo_total_eur"]      # approximate complements are always added
    assert "PREÇOS FICTÍCIOS" in o["resume"] and "Complementos aproximados" in o["resume"]
