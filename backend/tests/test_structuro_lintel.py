"""Linteau de reprise d'ouverture EN 1992/1993 — tests déterministes."""
from engines import structuro_lintel as L


def test_arching_proposes_steel_rc_and_economical_pick():
    out = L.lintel_design({
        "clear_span_m": 2.4, "wall_thickness_m": 0.5, "masonry_unit_weight_kn_m3": 22,
        "masonry_height_above_m": 2.7, "load_model": "arching", "arch_angle_deg": 60,
        "permanent_line_kn_m": 8.0, "variable_line_kn_m": 3.0, "material": "both",
        "steel_grade": "S235", "steel_families": ["IPE", "HEA", "HEB"], "max_profiles": 2,
        "rc_width_m": 0.2, "fck": 25, "fyk": 500,
        "steel_eur_per_kg": 3.0, "concrete_eur_per_m3": 180, "rebar_eur_per_kg": 2.0})
    assert out["load_model"] == "arching"
    assert out["actions"]["m_ed_knm"] > 0 and out["actions"]["v_ed_kn"] > 0
    assert out["steel"]["status"] == "ok" and out["steel"]["label"].startswith(("IPE", "HEA", "HEB", "1", "2"))
    assert out["rc"]["status"] == "ok" and out["rc"]["as_required_cm2"] > 0
    assert out["recommendation"]["material"] in ("steel", "rc")
    # flèche vérifiée (caractéristique sous limite)
    assert out["steel"]["defl_char_mm"] <= out["steel"]["defl_char_limit_mm"]


def test_rectangular_model_is_more_severe_than_arching():
    base = {"clear_span_m": 3.0, "wall_thickness_m": 0.2, "masonry_unit_weight_kn_m3": 20,
            "masonry_height_above_m": 2.6, "permanent_line_kn_m": 6, "variable_line_kn_m": 2,
            "material": "steel"}
    arch = L.lintel_design({**base, "load_model": "arching"})
    rect = L.lintel_design({**base, "load_model": "rectangular"})
    assert rect["actions"]["m_ed_knm"] >= arch["actions"]["m_ed_knm"]


def test_arching_falls_back_to_rectangular_when_masonry_too_low():
    out = L.lintel_design({"clear_span_m": 3.0, "wall_thickness_m": 0.2, "load_model": "arching",
                           "masonry_height_above_m": 0.4, "permanent_line_kn_m": 3, "material": "steel"})
    assert out["load_model"] == "rectangular"
    assert any("arco incompleto" in n for n in out["notes"])


def test_bearing_check_flags_insufficient_support():
    out = L.lintel_design({"clear_span_m": 3.0, "wall_thickness_m": 0.1, "permanent_line_kn_m": 40,
                           "variable_line_kn_m": 20, "bearing_length_m": 0.05,
                           "masonry_comp_strength_mpa": 0.3, "material": "steel"})
    assert out["bearing"]["status"] == "fails_check"
    assert out["bearing"]["required_length_m"] > out["bearing"]["bearing_length_m"]


def test_steel_no_solution_when_span_huge_single_small():
    out = L.lintel_design({"clear_span_m": 11.0, "wall_thickness_m": 0.2, "permanent_line_kn_m": 60,
                           "variable_line_kn_m": 30, "material": "steel",
                           "steel_families": ["IPE"], "max_profiles": 1})
    assert out["steel"]["status"] == "no_solution"


def test_null_rc_fields_from_frontend_do_not_crash():
    # Le frontend envoie rc_width_m/rc_height_m = None par défaut (état React nul).
    out = L.lintel_design({"clear_span_m": 2.4, "wall_thickness_m": 0.5, "permanent_line_kn_m": 8,
                           "variable_line_kn_m": 3, "material": "both", "rc_width_m": None,
                           "rc_height_m": None})
    assert out["rc"]["status"] in ("ok", "no_solution")
    assert out["steel"]["status"] in ("ok", "no_solution")


def test_deversement_reduces_capacity_when_not_restrained():
    base = {"clear_span_m": 3.0, "wall_thickness_m": 0.2, "masonry_height_above_m": 2.7,
            "permanent_line_kn_m": 10, "variable_line_kn_m": 4, "material": "steel",
            "steel_families": ["IPE"], "max_profiles": 2}
    restr = L.lintel_design({**base, "lateral_restraint_masonry": True})
    free = L.lintel_design({**base, "lateral_restraint_masonry": False})
    assert restr["steel"]["status"] == "ok"
    assert restr["steel"].get("ltb") is None
    if free["steel"]["status"] == "ok":
        lt = free["steel"]["ltb"]
        assert lt is not None and 0 < lt["chi_lt"] <= 1.0
        assert free["steel"]["mb_rd_knm"] <= free["steel"]["mrd_knm"] + 1e-6
        assert lt["mcr_knm"] > 0


def test_deversement_skips_mono_symmetric_upn_when_free():
    out = L.lintel_design({"clear_span_m": 2.4, "wall_thickness_m": 0.2, "permanent_line_kn_m": 6,
                           "material": "steel", "steel_families": ["UPN"], "max_profiles": 2,
                           "lateral_restraint_masonry": False})
    assert out["steel"]["status"] == "no_solution"


def test_lintel_pdf_and_dxf_exports():
    from engines.structuro_lintel_export import build_lintel_pdf, build_lintel_dxf
    res = L.lintel_design({"clear_span_m": 2.4, "wall_thickness_m": 0.5, "permanent_line_kn_m": 8,
                           "variable_line_kn_m": 3, "material": "both", "rc_width_m": 0.2})
    pdf = build_lintel_pdf(res, "Baie salon", 2)
    dxf = build_lintel_dxf(res, "Baie salon")
    assert pdf[:5] == b"%PDF-" and len(pdf) > 1000
    assert b"SECTION" in dxf[:200] and len(dxf) > 1000
