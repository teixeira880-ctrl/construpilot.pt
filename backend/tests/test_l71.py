"""Lot 71 — linteau calculé sur la portée utile (l_n + about)."""
from engines import structuro_lintel as L

BASE = {"clear_span_m": 2.4, "wall_thickness_m": 0.5, "permanent_line_kn_m": 25, "variable_line_kn_m": 5,
        "load_model": "rectangular", "masonry_height_above_m": 0.0, "material": "both"}


def test_effective_span_used_for_actions():
    a0 = L.lintel_design({**BASE, "bearing_length_m": 0.0})
    a2 = L.lintel_design({**BASE, "bearing_length_m": 0.2})
    assert a2["clear_span_m"] == 2.4 and a2["effective_span_m"] == 2.6
    assert a0["effective_span_m"] == 2.4
    # charges uniformes (maçonnerie h=0) : M ∝ L²
    r = a2["actions"]["m_ed_knm"] / a0["actions"]["m_ed_knm"]
    assert abs(r - (2.6 / 2.4) ** 2) < 0.01
    m = 1.35 * 25 * 2.6 ** 2 / 8 + 1.5 * 5 * 2.6 ** 2 / 8
    assert abs(a2["actions"]["m_ed_knm"] - m) < 0.05
    assert any("l_eff" in n for n in a2["notes"])
    assert a2["geometry"]["clear_span_m"] == 2.4


def test_installed_length_includes_both_bearings():
    out = L.lintel_design({**BASE, "bearing_length_m": 0.2})
    if out["rc"] and out["rc"]["status"] == "ok":
        b, h = out["rc"]["b_mm"] / 1000, out["rc"]["h_mm"] / 1000
        assert abs(out["rc"]["concrete_m3"] - b * h * 2.8) < 0.002
    if out["steel"] and out["steel"]["status"] == "ok":
        p = L.profiles.PROFILE_DATA[out["steel"]["profile"]]
        exp = p["A"] * 1e-4 * L.STEEL_DENSITY * 2.8 * out["steel"]["count"]
        assert abs(out["steel"]["mass_kg"] - exp) < 0.2
