"""Tests Lot 93 (CP-FIAB-EST) : estimateur construction maison — déchets, €/m² particulier, économies."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend"))
sys.path.insert(0, "/app/backend")

from engines.estimation import estimate, apply_client_markup  # noqa: E402
from engines import savings  # noqa: E402

SITE = "pt"
COUNTRY = "PT" if SITE == "pt" else "FR"
REGION = "Leiria" if SITE == "pt" else None


def _est(finish="standard"):
    return estimate("construction_maison_neuve", 140, finish, COUNTRY, REGION, "maison", "neuf")


def test_dechets_pas_en_double():
    e = _est()
    assert any(l["key"] == "dechets" for l in e["lots"])
    assert e["breakdown"]["waste_disposal"] == 0.0


def test_dechets_forfait_si_pas_de_poste():
    e = estimate("toiture" if SITE == "fr" else "chauffage", 100, "standard", COUNTRY, REGION)
    if not any(l["key"] == "dechets" for l in e["lots"]):
        assert e["breakdown"]["waste_disposal"] > 0


def test_total_egal_somme_des_postes():
    e = _est()
    b = e["breakdown"]
    sub = b["materials"] + b["labour"] + b["equipment_rental"] + b["waste_disposal"]
    assert abs(sub + b["contingency"] - e["total_avg"]) < 1.0
    assert abs(sum(l["total"] for l in e["lots"]) - (b["materials"] + b["labour"])) < 2.0


def test_prix_m2_particulier_coherent_avec_total():
    e = apply_client_markup(_est())
    for lvl, v in e["price_model"].items():
        assert abs(v["total"] / 140 - v["per_sqm"]) < 1.0, lvl
    assert e["price_model"]["eco"]["total"] < e["price_model"]["standard"]["total"] < e["price_model"]["premium"]["total"]
    assert abs(e["price_model"]["standard"]["total"] - e["total_avg"]) < 1.0


def test_economies_sans_double_comptage():
    e = apply_client_markup(_est())
    s = savings.compute(e)
    mat = e["breakdown"]["materials"]
    sup = next(i for i in s["items"] if i["key"] == "supplier_optimization")
    assert abs(sup["amount"] - mat * 0.92 * 0.06) < 1.0
    assert "Tavily" not in sup["basis"]
    assert s["total"] < e["total_avg"] * 0.30


def test_prix_m2_realiste():
    e = apply_client_markup(_est())
    assert 900 < e["price_per_sqm"] < 2600


if SITE == "pt":
    def test_libelles_pt():
        from engines.catalog import LOTS_BY_KEY
        assert LOTS_BY_KEY["toiture"]["name"] == "Cobertura"
        tools = [t for l in LOTS_BY_KEY.values() for t in l.get("tools", [])]
        assert "IVA" not in tools and "Piso" not in tools
        s = savings.compute(apply_client_markup(_est()))
        assert "soit" not in s["message"] and "lot(s)" not in str(s["items"])
