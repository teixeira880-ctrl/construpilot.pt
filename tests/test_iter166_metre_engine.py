"""Iteration 166 — deterministic metré engine acceptance tests (synthetic data, NOT real project conclusions).

Covers spec tests A (non-constructive strokes), B (interior vs exterior chain), C (arithmetic difference),
D (ambiguous OCR), F (missing height / slope), G (repeated element), J (deduction rule) and the tool contracts.
"""
import sys

import pytest

sys.path.append("/app/backend")

from jsonschema import Draft202012Validator

from engines.metre import chains, dedupe, quantities
from engines.metre.tools import METRE_TOOLS, METRE_TOOL_NAMES, run_metre_tool


def _r(label, value=None, origin="native_text", candidates=None):
    return {"label": label, "value_m": value, "candidates_m": candidates or [], "origin": origin, "plan_id": None, "page": None, "box": None}


# A — hatches, furniture, axes and dimension lines never become walls
def test_A_non_constructive_strokes_are_not_walls():
    strokes = [{"stroke_id": "s1", "kind": None, "layer": "HACHURES", "pattern": None, "has_arrowheads": False, "has_ticks": False},
               {"stroke_id": "s2", "kind": "furniture", "layer": None, "pattern": None, "has_arrowheads": False, "has_ticks": False},
               {"stroke_id": "s3", "kind": None, "layer": "AXES", "pattern": None, "has_arrowheads": False, "has_ticks": False},
               {"stroke_id": "s4", "kind": None, "layer": None, "pattern": None, "has_arrowheads": True, "has_ticks": False},
               {"stroke_id": "s5", "kind": None, "layer": "MURS", "pattern": None, "has_arrowheads": False, "has_ticks": False},
               {"stroke_id": "s6", "kind": None, "layer": None, "pattern": None, "has_arrowheads": False, "has_ticks": False}]
    res = run_metre_tool("classify_strokes", {"strokes": strokes})
    by_id = {s["stroke_id"]: s["classification"] for s in res["strokes"]}
    assert by_id == {"s1": "hatch", "s2": "furniture", "s3": "axis", "s4": "dimension_line", "s5": "wall", "s6": "unclassified"}
    assert res["constructive_count"] == 1
    assert not next(s for s in res["strokes"] if s["stroke_id"] == "s6")["constructive"]


# B — 4,00 + 5,00 + 0,20 + 0,10 + 0,20 = 9,50 m ; thicknesses shown once and never re-added
def test_B_interior_spans_plus_wall_thicknesses():
    spans = [_r("vide 1", 4.0), _r("vide 2", 5.0)]
    thick = [_r("mur ext. gauche", 0.20), _r("cloison", 0.10), _r("mur ext. droit", 0.20)]
    res = chains.check_dimension_chain(spans=spans, thicknesses=thick, declared_total=_r("total", 9.50))
    calc = res["calculation"]
    assert calc["result"] == 9.5 and calc["state"] == "confirmed"
    assert calc["formula"].startswith("4 + 5 + 0.2 + 0.1 + 0.2 = 9.5 m")
    assert res["findings"] == []
    # chain already includes the thicknesses: they are documented but not added again
    included = chains.check_dimension_chain(spans=[_r("total chaîné", 9.5)], thicknesses=thick, chain_includes_thickness=True)
    assert included["calculation"]["result"] == 9.5 and "non ré-ajoutées" in included["calculation"]["formula"]
    # to axes of the end walls: half thickness at both ends → 4 + 5 + 0.1 + 0.1 + 0.1 = 9.30
    axes = chains.check_dimension_chain(spans=spans, thicknesses=thick, reference="axes")
    assert axes["calculation"]["result"] == 9.3 and "0.2/2" in axes["calculation"]["formula"]


# C — 13,27 vs 13,30 on the same confirmed interval = 3 cm ; different references → no incoherence
def test_C_arithmetic_difference_same_vs_different_reference():
    same = chains.compare_values(_r("cote A", 13.27), _r("cote B", 13.30), same_interval=True, same_reference=True)
    assert same["calculation"]["result"] == pytest.approx(0.03)
    assert "3 cm" in same["calculation"]["formula"]
    assert len(same["findings"]) == 1 and same["findings"][0]["severity"] == "demonstrated"
    assert "BET" in same["findings"][0]["action"] and same["calculation"]["tolerance"]["execution_tol"] is None
    other = chains.compare_values(_r("cote A", 13.27), _r("cote B", 13.30), same_interval=False, same_reference=True)
    assert other["calculation"]["state"] == "indeterminate" and other["findings"][0]["severity"] == "info"
    assert "ne constitue pas une incohérence" in other["calculation"]["reason"]
    within = chains.compare_values(_r("cote A", 13.27), _r("cote B", 13.275), same_interval=True, same_reference=True)
    assert within["findings"] == []


# D — 13,27 / 13,72 : arithmetic fit never resolves; native text does
def test_D_ambiguous_ocr_requires_independent_evidence():
    unresolved = chains.resolve_reading(label="cote façade", candidates_m=[13.27, 13.72], arithmetic_fit_m=13.72,
                                        confirmations=[{"kind": "arithmetic_fit", "value_m": 13.72, "ref": None}])
    assert unresolved["state"] == "indeterminate" and "ignorée" in unresolved["reason"]
    chain = chains.check_dimension_chain(spans=[_r("cote façade", None, candidates=[13.27, 13.72]), _r("vide", 2.0)])
    assert chain["calculation"]["result"] is None and chain["calculation"]["state"] == "indeterminate"
    resolved = chains.resolve_reading(label="cote façade", candidates_m=[13.27, 13.72],
                                      confirmations=[{"kind": "native_text", "value_m": 13.27, "ref": "page 2 texte natif"}])
    assert resolved["state"] == "confirmed" and resolved["reading"]["value_m"] == 13.27
    conflicting = chains.resolve_reading(label="x", candidates_m=[13.27, 13.72], confirmations=[
        {"kind": "native_text", "value_m": 13.27, "ref": None}, {"kind": "zoom_crop", "value_m": 13.72, "ref": None}])
    assert conflicting["state"] == "indeterminate"


# F — missing height or slope: length / projected area only, never invented area or volume
def test_F_missing_height_or_slope_never_invents_quantities():
    res = quantities.calculate_quantities([
        {"category": "wall_area", "element": "Mur A", "length_m": 6.0, "height_m": None},
        {"category": "concrete_volume", "element": "Dalle", "area_m2": 40.0, "height_m": None},
        {"category": "roof_area", "element": "Toiture", "plan_area_m2": 80.0, "slope_deg": None},
        {"category": "roof_area", "element": "Toiture 30°", "plan_area_m2": 80.0, "slope_deg": 30}])
    wall, slab, roof, roof30 = res["lines"]
    assert wall["unit"] == "m" and wall["net"] == 6.0 and wall["missing"] == ["height_m"] and wall["state"] == "probable"
    assert slab["unit"] == "m²" and slab["net"] == 40.0 and slab["missing"] == ["height_m"]
    assert roof["net"] == 80.0 and roof["missing"] == ["slope_deg"]
    assert roof30["net"] == pytest.approx(92.376, abs=0.001) and roof30["state"] == "confirmed"
    assert res["totals_confirmed"] == {"m²": pytest.approx(92.376, abs=0.001)}


# G — the same window in plan, elevation and schedule counts once with three evidences
def test_G_repeated_element_counted_once():
    obs = [{"obs_id": "o1", "element_type": "window", "tag": "F1", "view": "plan", "dimensions": {"width_m": 1.2, "height_m": None, "length_m": None}, "location": {"level": "RDC", "x_m": 2.0, "y_m": 3.0}},
           {"obs_id": "o2", "element_type": "window", "tag": "f1", "view": "elevation", "dimensions": {"width_m": 1.2, "height_m": 1.35, "length_m": None}, "location": {"level": None, "x_m": None, "y_m": None}},
           {"obs_id": "o3", "element_type": "window", "tag": "F1", "view": "schedule", "dimensions": {"width_m": 1.2, "height_m": 1.35, "length_m": None}, "location": {"level": None, "x_m": None, "y_m": None}},
           {"obs_id": "o4", "element_type": "window", "tag": None, "view": "plan", "dimensions": {"width_m": 0.8, "height_m": None, "length_m": None}, "location": {"level": "RDC", "x_m": 8.0, "y_m": 3.0}},
           {"obs_id": "o5", "element_type": "window", "tag": None, "view": "elevation", "dimensions": {"width_m": 0.8, "height_m": 1.0, "length_m": None}, "location": {"level": None, "x_m": None, "y_m": None}}]
    res = dedupe.dedupe_elements(obs)
    f1 = next(e for e in res["elements"] if e["tag"] == "F1")
    assert f1["count"] == 1 and sorted(f1["evidence"]) == ["o1", "o2", "o3"] and f1["views"] == ["elevation", "plan", "schedule"]
    assert res["counts"] == {"window": 2}
    assert len(res["uncertain_groups"]) == 1 and res["uncertain_groups"][0]["obs_id"] == "o5"


# J — 5 × 2,8 = 14 m², opening 1 × 2,1 = 2,1 m², net 11,9 m² under an explicit full-deduction rule
def test_J_wall_area_with_explicit_deduction_rule():
    item = {"category": "wall_area", "element": "Mur pignon", "length_m": 5.0, "height_m": 2.8,
            "openings": [{"label": "porte", "width_m": 1.0, "height_m": 2.1}]}
    full = quantities.calculate_quantities([{**item, "deduction_rule": "full"}])["lines"][0]
    assert full["gross"] == 14.0 and full["net"] == 11.9 and full["deductions"][0]["area_m2"] == 2.1
    assert full["order_qty"] is None and full["extra_pct"] is None and "sélectionnée par l'utilisateur" in full["rule"]
    assert "Aucune perte" in full["reason"]
    no_rule = quantities.calculate_quantities([item])["lines"][0]
    assert no_rule["net"] is None and no_rule["state"] == "indeterminate" and no_rule["missing"] == ["deduction_rule"]
    none_rule = quantities.calculate_quantities([{**item, "deduction_rule": "none"}])["lines"][0]
    assert none_rule["net"] == 14.0
    threshold = quantities.calculate_quantities([{**item, "deduction_rule": "threshold", "deduction_threshold_m2": 3.0}])["lines"][0]
    assert threshold["net"] == 14.0 and threshold["deductions"][0]["applied"] is False
    waste = quantities.calculate_quantities([{**item, "deduction_rule": "full", "extra_pct": 5}])["lines"][0]
    assert waste["order_qty"] == pytest.approx(12.495)


def test_packaged_units_distinguish_installed_and_ordered():
    line = quantities.packaged_units({"element": "Blocs 20", "net_quantity": 11.9, "units_per_measure": 12.5, "pack_size": 60, "waste_pct": None})
    assert line.net == 148.75 and line.order_qty == 180 and line.extra_pct is None


# Tool contracts: strict schemas valid, examples validate, unknown tool refused
def test_tool_schemas_are_strict_and_validate_examples():
    for tool in METRE_TOOLS:
        Draft202012Validator.check_schema(tool["parameters"])
        assert tool["strict"] is True and tool["parameters"]["additionalProperties"] is False
        assert set(tool["parameters"]["required"]) == set(tool["parameters"]["properties"])
    schema = next(t for t in METRE_TOOLS if t["name"] == "check_dimension_chain")["parameters"]
    args = {"spans": [_r("a", 4.0), _r("b", 5.0)], "thicknesses": [_r("m", 0.2)], "chain_includes_thickness": False, "reference": "faces", "declared_total": None}
    Draft202012Validator(schema).validate(args)
    assert run_metre_tool("check_dimension_chain", args)["calculation"]["result"] == 9.2
    assert run_metre_tool("nope", {})["ok"] is False
    assert METRE_TOOL_NAMES == {"check_dimension_chain", "compare_dimension_values", "resolve_ambiguous_reading", "classify_strokes", "dedupe_elements",
                                "calculate_quantities", "calibrate_view", "measure_pixels"}


# E — one sheet, two scales; distorted scan; declared scale invalid after resizing
def test_E_local_scales_and_distortion_block_pixel_measures():
    from engines.metre import calibration as cal
    plan = cal.calibrate_view(view_id="plan", references=[{"label": "c1", "value_m": 4.0, "px_length": 800, "axis": "h"}, {"label": "c2", "value_m": 2.5, "px_length": 500, "axis": "v"}],
                              declared_scale="1/50", dpi=100)
    detail = cal.calibrate_view(view_id="detail", references=[{"label": "d1", "value_m": 0.5, "px_length": 500, "axis": "h"}, {"label": "d2", "value_m": 0.2, "px_length": 200, "axis": "v"}])
    assert plan["status"] == "reliable" and plan["px_per_m"] == 200 and detail["status"] == "reliable" and detail["px_per_m"] == 1000
    assert plan["declared_check"]["difference_pct"] != 0 and any("cartouche" in r for r in plan["reasons"])  # 100 dpi at 1/50 ≠ 200 px/m
    assert cal.measure_pixels(calibration=plan, label="mur", px_length=1000)["calculation"]["result"] == 5.0
    assert cal.measure_pixels(calibration=detail, label="feuillure", px_length=1000)["calculation"]["result"] == 1.0
    # distorted scan: h and v differ by 8 % → pixel measures blocked unless axis given with per-axis calibration
    scan = cal.calibrate_view(view_id="scan", references=[{"label": "a", "value_m": 4.0, "px_length": 800, "axis": "h"}, {"label": "b", "value_m": 2.0, "px_length": 400, "axis": "h"},
                                                          {"label": "c", "value_m": 3.0, "px_length": 648, "axis": "v"}, {"label": "d", "value_m": 1.0, "px_length": 216, "axis": "v"}])
    assert scan["status"] == "per_axis" and scan["px_per_m"] is None and scan["px_per_m_by_axis"] == {"h": 200.0, "v": 216.0}
    blocked = cal.measure_pixels(calibration=scan, label="x", px_length=400)
    assert blocked["allowed"] is False and blocked["calculation"]["state"] == "not_verifiable"
    assert cal.measure_pixels(calibration=scan, label="x", px_length=432, axis="v")["calculation"]["result"] == 2.0
    # single or inconsistent references → unreliable, explicit dimensions remain the only usable values
    weak = cal.calibrate_view(view_id="w", references=[{"label": "a", "value_m": 4.0, "px_length": 800, "axis": None}])
    bad = cal.calibrate_view(view_id="b", references=[{"label": "a", "value_m": 4.0, "px_length": 800, "axis": None}, {"label": "b", "value_m": 4.0, "px_length": 900, "axis": None}])
    assert weak["measurements_allowed"] is False and bad["status"] == "unreliable"
    assert run_metre_tool("measure_pixels", {"calibration": {"view_id": "b", "status": "unreliable", "px_per_m": None, "px_per_m_by_axis": None, "measurements_allowed": False, "spread_pct": 12.0, "reasons": []},
                                              "label": "x", "px_length": 100, "axis": None})["allowed"] is False
