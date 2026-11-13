"""Dossier económico (construção tradicional): bibliotecas de compra / venda, recursos da empresa, margem e PDF."""
import asyncio

import pymupdf
import pytest

from engines import economic_dossier as E
from engines import economic_dossier_pdf as EP

LINES = [{"kind": "section", "title": "Alvenarias"},
         {"designation": "Parede tijolo 15", "unit": "m²", "qty": 100, "unit_price_ht": 40},
         {"designation": "Reboco interior", "unit": "m²", "qty": 200, "unit_price_ht": 15, "cost_price_ht": 10},
         {"kind": "section", "title": "Pavimentos"},
         {"designation": "Cerâmico 60x60", "unit": "m²", "qty": 50, "unit_price_ht": 50}]


def test_costs_from_purchase_library_quote_and_hypothesis():
    r = E.compute({"title": "T", "lines": LINES}, E.merge(None, "PT"), [{"designation": "Parede tijolo 15 cm", "unit": "m²", "cost_price_ht": 28}])
    o = {l["designation"]: l for l in r["lines"]}
    assert o["Parede tijolo 15"]["cu"] == 28 and o["Parede tijolo 15"]["origin"] == "biblioteca de compra"
    assert o["Reboco interior"]["cu"] == 10
    assert o["Cerâmico 60x60"]["origin"].startswith("HIPÓTESE") and r["hyp_lines"] == 1
    assert r["sale"] == 9500 and abs(r["cost"] - (r["direct"] + r["site_total"] + r["overhead"])) < 0.02
    assert abs(r["margin"] - (r["sale"] - r["cost"])) < 0.02 and r["scenarios"][0]["margin"] == r["margin"]
    assert any("gasóleo" in x["item"] for x in r["site"]) and r["days"] >= 1


def test_company_resources_override_defaults():
    base = E.compute({"lines": LINES}, E.merge(None, "PT"))
    cheap = E.merge({"resources": [{"id": "carrinha", "kind": "veiculo", "name": "Carrinha", "unit": "dia", "cost": 0, "consumption_l_100km": 0}],
                     "params": {"fuel_price_l": 0, "overhead_pct": 0}}, "PT")
    r = E.compute({"lines": LINES}, cheap)
    assert r["cost"] < base["cost"] and next(x for x in cheap["resources"] if x["id"] == "carrinha")["origin"] == "empresa"


def test_pdf_has_cover_and_sections():
    r = E.compute({"title": "Moradia", "client": {"name": "Ana"}, "lines": LINES}, E.merge(None, "PT"))
    d = pymupdf.open(stream=EP.build(r, {"company_name": "X", "accent_color": "#1F6B4F"}, "pt"), filetype="pdf")
    txt = "".join(p.get_text() for p in d)
    for k in ("Síntese económica da obra", "Rentabilidade por capítulo", "Estaleiro, equipa e meios", "Cenários de sensibilidade", "Margem"):
        assert k in txt
    fr = pymupdf.open(stream=EP.build(r, {"company_name": "X"}, "fr-FR"), filetype="pdf")
    assert "Synthèse économique du chantier" in "".join(p.get_text() for p in fr)


def test_route_uses_saved_resources(monkeypatch):
    mm = pytest.importorskip("mongomock_motor")
    db = mm.AsyncMongoMockClient()["t"]
    import routes.company_costs as C
    monkeypatch.setattr(C, "db", db)

    async def run():
        await db.users.insert_one({"user_id": "u1", "brand_country": "PT"})
        await db.pro_documents.insert_one({"doc_id": "d1", "user_id": "u1", "doc_type": "quote", "title": "Q", "lines": LINES})
        await db.library_items.insert_one({"user_id": "u1", "designation": "Parede tijolo 15", "unit": "m²", "cost_price_ht": 30, "unit_price_ht": 40})
        await C.put_costs(C.CostsIn(resources=[C.ResourceIn(id="trolha", kind="mao_de_obra", name="Trolha", unit="h", cost=20)],
                                    params=C.ParamsIn(fuel_price_l=1.5)), user={"user_id": "u1"})
        return await C.economic_dossier("d1", format="json", user={"user_id": "u1"})
    r = asyncio.run(run())
    assert r["params"]["fuel_price_l"] == 1.5 and next(l for l in r["lines"] if l["designation"] == "Parede tijolo 15")["cu"] == 30


def test_french_company_gets_french_texts():
    r = E.compute({"lines": LINES}, E.merge(None, "FR"), [], "FR")
    assert next(l for l in r["lines"] if l["designation"] == "Cerâmico 60x60")["origin"].startswith("HYPOTHÈSE")
    assert any("gazole" in x["item"] for x in r["site"]) and all(x["unit"] != "dia" for x in r["site"])
    assert r["scenarios"][2]["label"] == "Main-d'œuvre +10 %" and any("Équipe sur site" in h for h in r["hypotheses"])


def test_hypothesis_costs_reach_target_net_margin_and_crews_scale():
    """13/11 (Valpaços): 1,98 M€ sem preços de compra → margem −0,9 % e 934 dias com 3 pessoas. Agora: margem líquida = alvo,
    várias equipas em paralelo."""
    from engines import economic_dossier as E
    doc = {"lines": [{"designation": f"Item {i}", "unit": "m2", "qty": 100, "unit_price_ht": 220, "category": f"Lot {i % 9}"}
                     for i in range(90)]}
    r = E.compute(doc, E.merge(None, "PT"), [], "PT")
    assert abs(r["margin_pct"] - 20.0) < 0.5
    assert r["days"] <= E.MAX_TEAM_DAYS and r["team"]["trolha"] > 2
