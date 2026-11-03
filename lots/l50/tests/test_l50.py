"""Lot 50 — devis de l'assistant chiffré automatiquement."""
import asyncio
import os
import sys
import pathlib

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_l50")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from engines import assistant_quote_pricing as P  # noqa: E402
from engines import assistant_quote_schema as S  # noqa: E402
from engines import assistant_quote_service as V  # noqa: E402


def test_catalog_price_matches_trade_and_unit():
    m = P.catalog_price("Peinture murs et plafonds 2 couches", "m²")
    assert m and m["price_source"] == "construpilot_catalog" and m["unit_price_ht"] > 0 and m["price_estimated"]
    assert P.catalog_price("Pintura de paredes interiores", "m2")["unit_price_ht"] == m["unit_price_ht"]
    assert P.catalog_price("Peinture murs", "u") is None          # unité incompatible
    assert P.catalog_price("Prestation inconnue xyz", "m²") is None


def test_specific_before_general():
    sdb = P.catalog_price("Salle de bain complète : carrelage, plomberie", "m²")
    assert sdb["price_reference"] == "catalog:salle_de_bain"


def test_build_lines_fills_library_misses_only():
    class L:
        def __init__(self, d, u, origin):
            self.line_id, self.designation, self.description, self.quantity = None, d, "", 10
            self.unit, self.unit_price, self.price_origin, self.vat_rate, self.lot = u, None, origin, None, ""

    class B:
        vat_rate = None
        lines = [L("Carrelage sol 60x60", "m²", "library"), L("Carrelage sol 60x60", "m²", "unpriced"),
                 L("Prestation inconnue", "u", "library")]

    async def base(body, user, previous=None):
        return [{"designation": l.designation, "unit": l.unit, "category": "", "price_missing": True,
                 "unit_price_ht": 0, "price_source": "unpriced"} for l in body.lines]

    P._build_lines_lot50_base = base
    rows = asyncio.run(P.build_lines(B(), {"user_id": "u"}))
    assert rows[0]["price_source"] == "construpilot_catalog" and not rows[0]["price_missing"]
    assert rows[1]["price_missing"]          # « sans prix » demandé explicitement : respecté
    assert rows[2]["price_missing"]          # aucune correspondance : l'assistant doit estimer


def test_instructions_default_to_auto_pricing():
    assert "Lot 50" in pathlib.Path(S.__file__).read_text(encoding="utf-8")
    assert "estimate" in S.LINE_PROPERTIES["price_origin"]["description"]
    assert S.QUOTE_INSTRUCTIONS.count("action_required") >= 1


def test_present_asks_to_price_missing_lines():
    def base(doc):
        return {"draft": {"lines": doc["lines"]}}
    V._present_lot50_base = base
    out = V.present({"lines": [{"line_id": "a", "price_missing": True}, {"line_id": "b", "price_missing": False}]})
    assert "action_required" in out and "a" in out["action_required"] and "estimate" in out["action_required"]
    assert "action_required" not in V.present({"lines": [{"line_id": "b"}]})
