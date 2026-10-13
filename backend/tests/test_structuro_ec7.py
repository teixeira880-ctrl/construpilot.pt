"""Lot 3 — tests déterministes de la portance EN 1997-1 Annexe D."""
from engines import structuro_ec7 as ec7


def test_catalog_defaults():
    c = ec7.catalog()
    assert c["defaults"]["gamma_Rv"] == 1.4
    assert set(c["modes"]) == {"drained", "undrained"}


def test_drained_bearing_factors_phi30():
    r = ec7.bearing("drained", 2.0, 2.0, q_ed_kpa=200, d_m=1.0, gamma_soil=18, phi_deg=30)
    assert r["status"] == "ok"
    assert abs(r["factors"]["Nq"] - 18.40) < 0.1
    assert abs(r["factors"]["Nc"] - 30.14) < 0.2
    assert abs(r["factors"]["Ngamma"] - 20.09) < 0.2
    assert r["q_Rd_kpa"] > 0 and r["utilisation"]["status"] in ("ok", "proche", "a_revoir")
    assert r["execution_ready"] is False


def test_drained_missing_phi_reports():
    r = ec7.bearing("drained", 2, 2, q_ed_kpa=100, gamma_soil=18, phi_deg=0)
    assert r["status"] == "missing" and "φ'" in r["message"]


def test_undrained_bearing():
    r = ec7.bearing("undrained", 2, 2, q_ed_kpa=150, cu_kpa=60, d_m=1, gamma_soil=18)
    assert r["status"] == "ok"
    assert abs(r["factors"]["(pi+2)"] - 5.142) < 0.01
    assert r["q_Rd_kpa"] > 0


def test_design_study_footing_from_envelope():
    model = {"elements": [{"id": "S1", "kind": "footing", "width_m": 2.0, "length_m": 2.0}]}
    result = {"cases": [{"id": "ELU1", "label": "ELU STR", "elements": [
        {"id": "S1", "kind": "footing", "mean_pressure_kpa": 180.0}]}]}
    out = ec7.design_study(model, result, {"mode": "drained", "phi_deg": 30, "gamma_soil": 18, "d_m": 1.0})
    row = out["elements"][0]
    assert row["status"] == "ok" and row["result"]["q_ed_kpa"] == 180.0
    assert out["execution_ready"] is False
