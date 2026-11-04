"""Lot 78 — le dallage est chiffré dans la construction maison."""
from engines import estimation as E
from engines.catalog import EXECUTION_ORDER, LOTS_BY_KEY, PROJECT_TYPES_BY_KEY


def test_dallage_lot_in_house_construction():
    assert "dallage" in LOTS_BY_KEY
    for k in ("construction_maison_neuve", "construction_maison_hors_eau_hors_air",
              "construction_maison_gros_oeuvre", "construction_maison_main_oeuvre"):
        assert PROJECT_TYPES_BY_KEY[k]["lots"].get("dallage") == 1.0, k
    assert EXECUTION_ORDER.index("dallage") == EXECUTION_ORDER.index("fondations") + 1
    assert "dallage" not in PROJECT_TYPES_BY_KEY["extension"]["lots"]


def test_gros_oeuvre_ratio_realistic():
    for country in ("FR", "PT"):
        e = E.estimate("construction_maison_gros_oeuvre", 100, "standard", country)
        keys = [l["key"] for l in e["lots"]]
        assert "dallage" in keys
        d = next(l for l in e["lots"] if l["key"] == "dallage")
        assert d["quantity"] == 100.0 and d["total"] > 0
    fr = E.estimate("construction_maison_gros_oeuvre", 100, "standard", "FR")["price_per_sqm"]
    assert 400 <= fr <= 900
