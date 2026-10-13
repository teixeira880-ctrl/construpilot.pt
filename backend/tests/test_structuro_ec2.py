"""Lot 2 — tests déterministes du ferraillage EN 1992-1-1 (flexion + effort tranchant)."""
import math

import pytest

from engines import structuro_ec2 as ec2


def test_catalog_has_classes_and_factors():
    cat = ec2.materials_catalog()
    keys = {c["key"] for c in cat["concrete"]}
    assert {"C25/30", "C30/37", "C50/60"} <= keys
    assert cat["factors"] == {"gamma_c": 1.5, "gamma_s": 1.15, "alpha_cc": 1.0}
    assert cat["steel"]["fyk"] == 500


def test_simple_bending_as():
    out = ec2.design_section(100.0, 0.0, b_m=0.30, h_m=0.50, d_m=0.45, fck=25)
    fx = out["flexure"]
    assert fx["mode"] == "simple"
    assert fx["as_comp_cm2"] == 0.0
    assert out["execution_ready"] is False
    # Référence manuelle ≈ 5.39 cm²
    assert fx["as_req_cm2"] == pytest.approx(5.39, abs=0.1)
    # μ < μlim (0.372) et μ positif
    assert 0.09 < fx["mu"] < 0.11 and fx["mu"] < fx["mu_lim"]


def test_min_reinforcement_governs_for_small_moment():
    out = ec2.design_section(5.0, 0.0, b_m=0.30, h_m=0.50, d_m=0.45, fck=25)
    fx = out["flexure"]
    # As calculé faible → As,min prend le dessus
    assert fx["as_req_cm2"] == fx["as_min_cm2"]
    assert fx["as_min_cm2"] == pytest.approx(1.80, abs=0.1)


def test_double_reinforcement_needed():
    out = ec2.design_section(400.0, 0.0, b_m=0.30, h_m=0.50, d_m=0.45, fck=25)
    fx = out["flexure"]
    assert fx["mode"] == "double"
    assert fx["mu"] > fx["mu_lim"]
    assert fx["as_comp_cm2"] > 0
    assert any("compression" in w for w in fx["warnings"])


def test_shear_below_vrdc_uses_minimum():
    out = ec2.design_section(100.0, 40.0, b_m=0.30, h_m=0.50, d_m=0.45, fck=25)
    sh = out["shear"]
    assert sh["needs_stirrups"] is False
    assert sh["asw_s_req_cm2_m"] == sh["asw_s_min_cm2_m"]
    assert sh["asw_s_min_cm2_m"] == pytest.approx(2.4, abs=0.1)


def test_shear_requires_stirrups():
    out = ec2.design_section(100.0, 120.0, b_m=0.30, h_m=0.50, d_m=0.45, fck=25)
    sh = out["shear"]
    assert sh["needs_stirrups"] is True
    assert sh["asw_s_req_cm2_m"] == pytest.approx(2.73, abs=0.15)
    assert sh["cot_theta"] == pytest.approx(2.5, abs=1e-6)


def test_invalid_depth_raises():
    with pytest.raises(ValueError):
        ec2.design_section(100.0, b_m=0.30, h_m=0.50, d_m=0.60, fck=25)


def test_design_study_links_envelope_to_beam():
    model = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.30, "height_m": 0.50}]}
    result = {"cases": [{"id": "ELU1", "label": "ELU STR — Q dominante", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 100.0, "shear_max_kn": 40.0}]}]}
    out = ec2.design_study(model, result,
                           {"fck": 25, "fyk": 500, "gamma_c": 1.5, "gamma_s": 1.15,
                            "alpha_cc": 1.0, "cot_theta": 2.5, "cover_m": 0.05})
    assert out["execution_ready"] is False
    row = out["elements"][0]
    assert row["status"] == "ok" and row["d_m"] == 0.45
    assert row["design"]["flexure"]["mode"] == "simple"
    assert row["med_knm"] == 100.0 and row["med_case"].startswith("ELU")


def test_design_study_without_combinations_reports_missing():
    model = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.30, "height_m": 0.50}]}
    # Seules des actions brutes G/Q (ignorées par l'enveloppe) → pas de moment ELU
    result = {"cases": [{"id": "G", "label": "G", "elements": [
        {"id": "B1", "kind": "beam", "moment_max_knm": 50.0}]}]}
    out = ec2.design_study(model, result, {"cover_m": 0.05})
    assert out["elements"][0]["status"] == "no_envelope"



def test_design_study_reinjects_fresh_automation_bars():
    model = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.30, "height_m": 0.50}]}
    result = {"input_hash": "abc", "cases": [{"id": "ELU1", "label": "ELU STR — Q dominante",
        "elements": [{"id": "B1", "kind": "beam", "moment_max_knm": 100.0, "shear_max_kn": 40.0}]}]}
    auto = {"output_input_hash": "abc", "designs": [{"element_id": "B1", "kind": "beam",
        "diameter_mm": 16, "count": 4, "as_provided_mm2": 804.2, "as_required_mm2": 600.0,
        "stirrup_diameter_mm": 8, "asw_provided_mm2_m": 670.0, "stirrup_spacing_mm": 150.0}]}
    out = ec2.design_study(model, result, {"cover_m": 0.05}, auto)
    assert out["reinjected_from_automation"] is True
    row = out["elements"][0]
    assert row["reinforcement_source"] == "automation"
    assert row["scheme"]["origin"] == "automation"
    assert row["scheme"]["longitudinal"]["label"] == "4Ø16"
    assert row["scheme"]["longitudinal"]["as_provided_cm2"] == 8.04
    assert isinstance(row["provided_ok"], bool)


def test_design_study_ignores_stale_automation():
    model = {"elements": [{"id": "B1", "kind": "beam", "width_m": 0.30, "height_m": 0.50}]}
    result = {"input_hash": "fresh", "cases": [{"id": "ELU1", "label": "ELU STR — Q dominante",
        "elements": [{"id": "B1", "kind": "beam", "moment_max_knm": 100.0, "shear_max_kn": 40.0}]}]}
    auto = {"output_input_hash": "stale", "designs": [{"element_id": "B1", "kind": "beam",
        "diameter_mm": 16, "count": 4, "as_provided_mm2": 804.2}]}
    out = ec2.design_study(model, result, {"cover_m": 0.05}, auto)
    assert out["reinjected_from_automation"] is False
    assert out["elements"][0]["reinforcement_source"] == "proposal"
