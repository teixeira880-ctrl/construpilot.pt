"""Lot 4 — tests déterministes de la vérification acier EN 1993-1-1."""
from engines import structuro_ec3 as ec3


def test_catalog():
    c = ec3.catalog()
    assert "IPE300" in [p["key"] for p in c["profiles"]]
    assert c["grades"]["S235"] == 235


def test_bending_and_shear_ipe300_s235():
    p = ec3.PROFILES["IPE300"]
    r = ec3.verify(150, 100, wpl_y_cm3=p["Wpl"], wel_y_cm3=p["Wel"], av_cm2=p["Av"],
                   fy_mpa=235, section_class=1, gamma_m0=1.0)
    assert abs(r["bending"]["mc_rd_knm"] - 147.58) < 1.0
    assert r["bending"]["utilisation"]["status"] == "a_revoir"  # 150 > 147.6
    assert abs(r["shear"]["vpl_rd_kn"] - 348.7) < 2.0
    assert r["execution_ready"] is False


def test_class3_uses_elastic_modulus():
    p = ec3.PROFILES["IPE300"]
    r3 = ec3.verify(100, 0, wpl_y_cm3=p["Wpl"], wel_y_cm3=p["Wel"], av_cm2=p["Av"],
                    fy_mpa=235, section_class=3)
    assert abs(r3["bending"]["mc_rd_knm"] - 557 * 235 / 1000) < 1.0


def test_ltb_requires_mcr():
    p = ec3.PROFILES["IPE300"]
    r = ec3.verify(100, 0, wpl_y_cm3=p["Wpl"], wel_y_cm3=p["Wel"], av_cm2=p["Av"], fy_mpa=235)
    assert r["lateral_torsional"]["utilisation"]["status"] == "non_calcule"


def test_ltb_with_mcr():
    p = ec3.PROFILES["IPE300"]
    r = ec3.verify(100, 0, wpl_y_cm3=p["Wpl"], wel_y_cm3=p["Wel"], av_cm2=p["Av"],
                   fy_mpa=235, mcr_knm=200, buckling_curve="a")
    assert 0 < r["lateral_torsional"]["chi_lt"] <= 1.0
    assert r["lateral_torsional"]["mb_rd_knm"] > 0


def test_design_study_from_envelope():
    model = {"elements": [{"id": "B1", "kind": "beam"}]}
    result = {"cases": [{"id": "ELU1", "label": "ELU", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 120.0, "shear_max_kn": 80.0}]}]}
    out = ec3.design_study(model, result, {"profile": "IPE300", "grade": "S235"})
    assert out["elements"][0]["status"] == "ok"
    assert out["elements"][0]["profile"] == "IPE300"


def test_mcr_elastic_ipe300_5m():
    p = ec3.PROFILES["IPE300"]
    mcr = ec3.mcr_elastic(p["Iz"], p["It"], p["Iw"], 5.0, 1.0)
    assert abs(mcr - 115.4) < 5.0  # moment uniforme, poutre bi-appuyée 5 m


def test_mv_interaction_reduces_moment():
    p = ec3.PROFILES["IPE300"]
    # Vpl ≈ 348.7 kN ; V=250 > 0.5·Vpl → réduction appliquée (classe 1, tw/h/tf fournis)
    r = ec3.verify(100, 250, wpl_y_cm3=p["Wpl"], wel_y_cm3=p["Wel"], av_cm2=p["Av"], fy_mpa=235,
                   section_class=1, tw_mm=p["tw"], h_mm=p["h"], tf_mm=p["tf"])
    assert r["bending"]["mv_interaction"] is True
    assert r["bending"]["mc_rd_eff_knm"] < r["bending"]["mc_rd_knm"]


def test_design_study_auto_mcr_from_plan_span():
    model = {"elements": [{"id": "B1", "kind": "beam", "length_m": 5.0}]}
    result = {"cases": [{"id": "ELU1", "label": "ELU", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 120.0, "shear_max_kn": 80.0}]}]}
    out = ec3.design_study(model, result, {"profile": "IPE300", "grade": "S235", "c1": 1.0})
    row = out["elements"][0]
    assert row["span_source"] == "plan" and row["span_m"] == 5.0
    assert row["mcr_source"].startswith("auto") and row["mcr_knm"] > 0
    assert row["result"]["lateral_torsional"]["utilisation"]["status"] != "non_calcule"


def test_design_study_span_manual_override():
    model = {"elements": [{"id": "B1", "kind": "beam"}]}  # pas de portée au plan
    result = {"cases": [{"id": "ELU1", "label": "ELU", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 120.0, "shear_max_kn": 80.0}]}]}
    out = ec3.design_study(model, result, {"profile": "IPE300", "spans": {"B1": 4.0}})
    assert out["elements"][0]["span_source"] == "manuel" and out["elements"][0]["mcr_knm"] > 0


def test_design_study_override_wins_over_plan():
    model = {"elements": [{"id": "B1", "kind": "beam", "length_m": 4.0}]}
    result = {"cases": [{"id": "ELU1", "label": "ELU", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 120.0, "shear_max_kn": 80.0}]}]}
    base = ec3.design_study(model, result, {"profile": "IPE300", "c1": 1.0})
    over = ec3.design_study(model, result, {"profile": "IPE300", "c1": 1.0, "spans": {"B1": 6.0}})
    assert base["elements"][0]["span_source"] == "plan" and base["elements"][0]["span_m"] == 4.0
    assert over["elements"][0]["span_source"] == "manuel" and over["elements"][0]["span_m"] == 6.0
    # portée plus grande → Mcr plus faible
    assert over["elements"][0]["mcr_knm"] < base["elements"][0]["mcr_knm"]


def test_verify_column_buckling():
    p = ec3.PROFILES["IPE300"]
    r = ec3.verify_column(200, 0, A_cm2=p["A"], iy_cm4=p["Iy"], iz_cm4=p["Iz"], it_cm4=p["It"], iw_cm6=p["Iw"],
                          wpl_y_cm3=p["Wpl"], wel_y_cm3=p["Wel"], b_fl_mm=p["b"], h_mm=p["h"], tf_mm=p["tf"],
                          fy_mpa=235, lcr_y_m=2.8, curve_y="a", curve_z="b")
    assert r["npl_rd_kn"] > 0 and r["nb_rd_kn"] > 0 and r["nb_rd_kn"] < r["npl_rd_kn"]
    assert 0 < r["chi"] <= 1.0 and 0.5 < r["lambda_bar"] < 1.5
    assert r["buckling"]["utilisation"]["ratio"] > 0
    # flambement des deux axes calculé ; l'axe faible gouverne (χz ≤ χy)
    assert r["chi_z"] <= r["chi_y"] and r["nb_rd_kn"] == r["nb_rd_z_kn"]
    assert "interaction" not in r  # pas de M → pas d'interaction membre


def test_verify_column_axial_bending_interaction_kyy_kzy():
    p = ec3.PROFILES["IPE300"]
    r = ec3.verify_column(200, 50, A_cm2=p["A"], iy_cm4=p["Iy"], iz_cm4=p["Iz"], it_cm4=p["It"], iw_cm6=p["Iw"],
                          wpl_y_cm3=p["Wpl"], wel_y_cm3=p["Wel"], b_fl_mm=p["b"], h_mm=p["h"], tf_mm=p["tf"],
                          fy_mpa=235, lcr_y_m=2.8, curve_y="a", curve_z="b", curve_lt="a", cmy=0.9, cm_lt=0.9)
    assert r["cross_section"]["mn_y_rd_knm"] <= r["mc_rd_knm"]
    inter = r["interaction"]
    assert inter["value"] > 0 and inter["utilisation"]["ratio"] is not None
    assert inter["kyy"] > 0 and inter["kzy"] > 0            # facteurs d'interaction §6.3.3 calculés
    assert inter["eq_661"] > 0 and inter["eq_662"] > 0      # deux équations 6.61 & 6.62
    assert abs(inter["value"] - max(inter["eq_661"], inter["eq_662"])) < 1e-6
    assert 0 < inter["chi_lt"] <= 1.0
    assert "método 2" in inter["method"]


def test_design_study_columns_from_envelope():
    model = {"elements": [{"id": "P1", "kind": "column", "height_m": 2.8}]}
    result = {"cases": [{"id": "ELU1", "label": "ELU", "elements": [
        {"id": "P1", "kind": "column", "total_kn": 200.0, "axial_stress_mpa": 2.2}]}]}
    out = ec3.design_study(model, result, {"profile": "IPE300", "grade": "S235", "k_buckling": 1.0})
    col = out["columns"][0]
    assert col["status"] == "ok" and col["lcr_source"].startswith("plan")
    assert col["lcr_m"] == 2.8 and col["result"]["nb_rd_kn"] > 0
