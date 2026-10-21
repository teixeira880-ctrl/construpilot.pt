"""EN 1992 §7.3 — tests déterministes de la fissuration."""
from engines import structuro_crack as crack

MODEL = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.25, "height_m": 0.45}]}
RESULT = {"cases": [
    {"id": "ELU1", "label": "ELU", "elements": [{"id": "B1", "kind": "beam", "moment_max_knm": 80.0, "shear_max_kn": 40.0}]},
    {"id": "ELSqp", "label": "ELS quasi-permanente", "elements": [{"id": "B1", "kind": "beam", "moment_max_knm": 50.0}]},
]}
OPTS = {"fck": 25, "fyk": 500, "cover_m": 0.05, "bar_mm": 16, "stirrup_mm": 8, "legs": 2, "w_max_mm": 0.3}


def test_crack_width_computed():
    out = crack.crack_study(MODEL, RESULT, OPTS)
    row = out["elements"][0]
    assert row["status"] == "ok"
    assert row["mqp_knm"] == 50.0 and row["sigma_s_mpa"] > 0
    assert row["wk_mm"] > 0 and row["rho_p_eff"] > 0
    assert row["as_min_fiss_cm2"] > 0
    assert row["utilisation"]["ratio"] is not None
    assert out["execution_ready"] is False


def test_need_sls_without_qp_combo():
    res = {"cases": [{"id": "ELU1", "label": "ELU", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 80.0, "shear_max_kn": 40.0}]}]}
    out = crack.crack_study(MODEL, res, OPTS)
    assert out["elements"][0]["status"] == "need_sls"


def test_no_design_when_section_missing():
    out = crack.crack_study({"elements": [{"id": "B1", "kind": "beam"}]}, RESULT, OPTS)
    assert out["elements"][0]["status"] == "no_design"


def test_crack_reinjects_automation_bar_diameter():
    model = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.30, "height_m": 0.50}]}
    result = {"input_hash": "h1", "cases": [
        {"id": "ELU1", "label": "ELU STR", "elements": [{"id": "B1", "kind": "beam", "moment_max_knm": 100.0, "shear_max_kn": 40.0}]},
        {"id": "ELSqp1", "label": "ELS qp", "elements": [{"id": "B1", "kind": "beam", "moment_max_knm": 60.0}]}]}
    auto = {"output_input_hash": "h1", "designs": [{"element_id": "B1", "kind": "beam",
        "diameter_mm": 25, "count": 3, "as_provided_mm2": 1472.6, "stirrup_diameter_mm": 8,
        "asw_provided_mm2_m": 670.0, "stirrup_spacing_mm": 150.0}]}
    out = crack.crack_study(model, result, {"fck": 25, "fyk": 500, "cover_m": 0.05, "bar_mm": 12, "w_max_mm": 0.3, "kt": 0.4}, auto)
    assert out["reinjected_from_automation"] is True
    row = next(r for r in out["elements"] if r["id"] == "B1")
    assert row["status"] == "ok"
    assert row["bar_mm"] == 25  # Ø choisi réinjecté, pas le bar_mm global (12)
    assert row["reinforcement_source"] == "automation"
