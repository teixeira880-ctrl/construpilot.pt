"""Correctifs de sécurité des moteurs BET et escaliers — chaque test est comparé à un calcul manuel."""
import math

import pytest

from engines import structuro_autopilot as ap
from engines import structuro_continuous as cont
from engines.structuro_calc import Support, beam_response, example, fingerprint
from engines.structuro_sls import cracked_long_term
from stair_engine import StairInput, compute_straight


# ---------------------------------------------------------------- charges triangle / trapèze

def test_triangle_moment_and_deflection_match_closed_forms():
    L, W, EI = 4.5, 60.0, 20000.0
    r = beam_response(L, 0.0, [], EI, traps=[(W, L / 2)])
    assert r["moment_max_knm"] == pytest.approx(W * L / 6, rel=1e-9)          # 45 kN·m (≠ WL/8 = 33,75)
    assert r["deflection_sampled_mm"] == pytest.approx(W * L ** 3 / (60 * EI) * 1000, rel=1e-4)
    assert r["reaction_left_kn"] == pytest.approx(W / 2)


def test_trapezoid_matches_brute_force_point_loads():
    L, W, a = 4.5, 60.0, 1.5
    p, n = W / (L - a), 20000
    pts = []
    for i in range(n):
        x = (i + 0.5) * L / n
        pts.append((p * min(x / a, 1.0, (L - x) / a) * L / n, x))
    brute = beam_response(L, 0.0, pts)["moment_max_knm"]
    exact = beam_response(L, 0.0, [], traps=[(W, a)])["moment_max_knm"]
    assert exact == pytest.approx(brute, rel=1e-6)


def test_legacy_models_keep_their_fingerprint_fields():
    # Sans forme de charge, la sérialisation (donc l'empreinte) reste celle d'avant.
    assert set(Support(target="X1").model_dump()) == {"target", "fraction", "receiving", "position_m"}
    assert len(fingerprint(example())) == 64


def test_two_way_slab_short_beam_gets_triangle_not_uniform():
    inp = {"building": {"levels": 1}, "grid": {"bays_x_m": [4.0], "bays_y_m": [6.0]},
           "system": {"two_way_slab": True}}
    model = ap.build_model(inp)
    shapes = {(s.target[:2], s.shape) for e in model.elements if e.kind == "slab" for s in e.supports}
    assert ("B_", "triangle") in shapes and ("BY", "trapezoid") in shapes


# ---------------------------------------------------------------- poutres continues

def test_two_equal_spans_textbook():
    w, L = 10.0, 5.0
    r = cont.solve([{"L": L, "loads": {"udl": w}}] * 2)
    assert r["support_moments_knm"][1] == pytest.approx(-w * L * L / 8)       # −31,25
    assert r["reactions_kn"] == pytest.approx([3 / 8 * w * L, 10 / 8 * w * L, 3 / 8 * w * L])


def test_three_equal_spans_and_point_load_textbook():
    w, L = 10.0, 5.0
    r = cont.solve([{"L": L, "loads": {"udl": w}}] * 3)
    assert r["support_moments_knm"][1] == pytest.approx(-0.1 * w * L * L)
    assert r["spans"][0]["m_span_max_knm"] == pytest.approx(0.08 * w * L * L, rel=1e-4)
    r = cont.solve([{"L": L, "loads": {"points": [(20.0, L / 2)]}}, {"L": L, "loads": {}}])
    assert r["support_moments_knm"][1] == pytest.approx(-3 * 20.0 * L / 32)


def test_pattern_loading_envelope_two_spans():
    g, q, L = 13.5, 7.5, 5.0       # 1,35·10 et 1,5·5
    spans = [{"id": i, "L": L, "actions": {"G": {"udl": 10.0}, "Q": {"udl": 5.0}}} for i in "ab"]
    env = cont.envelope(spans, [{"id": "ELU1", "factors": {"G": 1.35, "Q": 1.5}}], {"G": "G", "Q": "Q"})
    assert env["supports"][1]["m_neg_knm"] == pytest.approx(-(g + q) * L * L / 8)
    # Q sur une seule travée : R_A = 3/8·g·L + 7/16·q·L, M+ = R_A²/(2(g+q))
    ra = 3 / 8 * g * L + 7 / 16 * q * L
    assert env["spans"][0]["m_pos_knm"] == pytest.approx(ra * ra / (2 * (g + q)), rel=1e-4)
    # Appui central : 10/8 au lieu de 1 (isostatique) → +25 %
    assert env["supports"][1]["continuity_delta_kn"] == pytest.approx(0.25 * (g + q) * L, rel=1e-6)


def _frame(**soil):
    return {"building": {"levels": 2}, "grid": {"bays_x_m": [5.0, 5.0], "bays_y_m": [4.5]},
            "system": {"two_way_slab": True}, "soil": soil}


def test_frame_beams_have_support_steel_and_columns_include_continuity():
    out = ap.build_and_compute(_frame(q_els_kpa=200, q_elu_kpa=300, q_confirmed=True))
    beams = out["superstructure"]["beams"]
    assert beams and all(b["as_top_req_cm2"] >= 0.15 * b["as_req_cm2"] - 0.006 for b in beams)
    x_beam = next(b for b in beams if b["family"] == "X")
    assert x_beam["m_support_knm"] > 0                      # chapeau sur l'appui intermédiaire
    uls = next(c for c in out["result"]["cases"] if c["id"].startswith("ELU"))
    central = next(r for r in uls["elements"] if r["id"] == "C_1_1_0")
    assert central.get("continuity_delta_kn", 0) > 0
    assert all(b["deflection"]["w_long_term_mm"] > b["deflection"]["w_elastic_mm"] for b in beams)


# ---------------------------------------------------------------- sol : jamais de valeur inventée

def test_no_soil_means_no_footing_dimensions():
    out = ap.build_and_compute(_frame())
    assert all(f["status"] == "sol_a_confirmer" and f["dim_m"] is None for f in out["footing_sizes"].values())
    assert out["summary"]["max_footing_dim_m"] is None
    assert out["summary"]["warnings"]


def test_unconfirmed_soil_values_are_not_used():
    out = ap.build_and_compute(_frame(q_els_kpa=200, q_elu_kpa=300))
    assert all(f["dim_m"] is None for f in out["footing_sizes"].values())
    ok = ap.build_and_compute(_frame(q_els_kpa=200, q_elu_kpa=300, q_confirmed=True))
    assert all(f["dim_m"] for f in ok["footing_sizes"].values())


# ---------------------------------------------------------------- flèche fissurée

def test_cracked_long_term_deflection_hand_check():
    # 25×50, d=45 cm, 4HA16 (804 mm²), C25/30, φ=2 : Ec,eff = 31476/3 ; x ≈ 181 mm ; I_II ≈ 1,60e9 mm⁴
    ei_ref = 32e6 * 0.25 * 0.5 ** 3 / 12
    r = cracked_long_term(5.0, ei_ref, b_m=0.25, h_m=0.5, d_m=0.45, as_mm2=804, m_qp_knm=60)
    ec_eff = 22000 * (33 / 10) ** 0.3 / 3
    alpha = 200000 / ec_eff
    x = (-alpha * 804 + math.sqrt((alpha * 804) ** 2 + 2 * 250 * alpha * 804 * 450)) / 250
    i2 = 250 * x ** 3 / 3 + alpha * 804 * (450 - x) ** 2
    assert r["i_cracked_cm4"] == pytest.approx(i2 / 1e4, abs=1)
    mcr = 0.3 * 25 ** (2 / 3) * 250 * 500 ** 2 / 6 / 1e6
    zeta = 1 - 0.5 * (mcr / 60) ** 2
    ei1 = ec_eff * 1e3 * (250 * 500 ** 3 / 12) * 1e-12
    ei2 = ec_eff * 1e3 * i2 * 1e-12
    expected = zeta * 5.0 * ei_ref / ei2 + (1 - zeta) * 5.0 * ei_ref / ei1
    assert r["w_long_term_mm"] == pytest.approx(expected, abs=0.01)
    assert r["amplification"] > 3


# ---------------------------------------------------------------- escaliers : échappée

def test_headroom_measured_at_stairwell_edge_on_nosing_line():
    r = compute_straight(StairInput(floor_height_mm=2720, available_length_mm=5000, available_width_mm=2000,
                                    stair_width_mm=900, ceiling_height_mm=2500, stairwell_length_mm=2600,
                                    stairwell_offset_mm=1600))
    x_edge = r.tread_depth_mm + 1600
    assert r.headroom_mm == pytest.approx(2500 - x_edge * r.riser_height_mm / r.tread_depth_mm, abs=0.01)


def test_required_stairwell_length_is_exact():
    r = compute_straight(StairInput(floor_height_mm=2720, available_length_mm=5000, available_width_mm=2000,
                                    stair_width_mm=900, ceiling_height_mm=2500))
    h, g = r.riser_height_mm, r.tread_depth_mm
    expected = r.stair_run_mm - (2500 - 1900) * g / h
    assert r.required_stairwell_mm["min_length_mm"] == pytest.approx(expected, abs=0.01)
