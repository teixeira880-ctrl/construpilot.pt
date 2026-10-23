"""Étude de sol incomplète : les calculs ne plantent plus (CALC-00), les valeurs par défaut sont tracées comme hypothèses."""
import copy
import json
from pathlib import Path

from engines.bet_core import pipeline, spec

CASE = json.loads((Path(__file__).parents[2] / "engines/bet_core/cases/la_courneuve.json").read_text())


def _run(raw, tmp_path):
    return pipeline.run(raw, tmp_path)


def test_layers_without_base_m_no_longer_crash(tmp_path):
    raw = copy.deepcopy(CASE)
    for L in raw["geotech"]["retaining"]["layers"]:
        L.pop("base_m")
    res = _run(raw, tmp_path)
    assert res["status"] != "MODELE_INVALIDE"
    geo = [a for a in res["anomalies"] if a["code"] == "GEO-HYP"]
    assert geo and "base de la couche" in geo[0]["message"] and geo[0]["level"] == "attention"


def test_minimal_geotech_gets_prudent_defaults_traced(tmp_path):
    raw = copy.deepcopy(CASE)
    raw["geotech"] = {"q_els_kpa": 250, "q_elu_kpa": 420}
    res = _run(raw, tmp_path)
    assert res["status"] != "MODELE_INVALIDE"
    fields = {h["field"] for h in raw["hypotheses"] if h.get("source") == "hypothese"}
    assert {"geotech.foundation_base_depth_m", "geotech.verified_widths_m", "geotech.retaining.layers"} <= fields or \
        "geotech.foundation_base_depth_m" in fields


def test_k0_from_phi_and_given_values_kept():
    raw = copy.deepcopy(CASE)
    raw["geotech"]["retaining"] = {"neighbour_surcharge_kpa": 12, "layers": [{"name": "Remblais", "phi": 30, "base_m": 1.5, "gamma": 18}]}
    spec.complete_geotech(raw)
    L = raw["geotech"]["retaining"]["layers"][0]
    assert L["base_m"] == 1.5 and L["gamma"] == 18 and abs(L["k0"] - 0.5) < 1e-3
    assert raw["geotech"]["retaining"]["neighbour_surcharge_kpa"] == 12


def test_no_geotech_still_asks_for_the_g2():
    raw = copy.deepcopy(CASE)
    raw.pop("geotech")
    assert spec.complete_geotech(raw) == []
    _, anomalies = pipeline.validate(raw)
    assert any(a["code"] == "REF-GEOTECH" for a in anomalies)


def test_dry_run_reports_calc_errors():
    raw = copy.deepcopy(CASE)
    m, anomalies = pipeline.validate(raw)
    assert pipeline.dry_run(m) is None
    m.raw["geotech"]["retaining"]["layers"][0]["base_m"] = None
    calc = pipeline.dry_run(m)
    assert calc and calc["code"] == "CALC-00" and calc["level"] == "bloquant"


def test_null_project_refs_do_not_crash_the_drawings(tmp_path):
    """Cas réel (prod, 21/10/2026) : project.g2_ref nul + G2 très incomplète → TypeError dans le cartouche des plans."""
    raw = copy.deepcopy(CASE)
    g = raw["geotech"]
    for k in ("bearing_layer", "anchorage_m", "water", "soft_layer", "settlement_mm_B060", "min_width_examples_m"):
        g[k] = None
    g["verified_widths_m"] = {"filante": None, "isolee": None}
    g["retaining"]["layers"] = None
    raw["project"]["g2_ref"] = None
    raw["project"]["pc_ref"] = None
    res = _run(raw, tmp_path)
    assert res["status"] != "MODELE_INVALIDE"
    assert res["files"]["pdf"]
