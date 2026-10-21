"""Dalles 2 sens — validation contre les notes « Dalle EC2 » du BET CONSTRUIRE (affaire 25-029,
JAOUHAR, Courbevoie, 17/09/2025). Valeurs BET converties des T·m/ml en kN·m/ml (×10).

Écarts connus et documentés :
- Dalle D3 (PH RdC) : contour quasi rectangulaire → reproduction à < 1 % (sens court) ;
  sens long : le BET intègre le contour réel (redans), le modèle rectangulaire est plus défavorable.
- Dalle D2 (PH R+1) : contour en L (redans de 2,51 m) — le rectangle équivalent est sécuritaire (+9 %).
"""
import pytest

from engines import structuro_slab2way as s2

# BET D3 : lx 6,119 × ly 9,35 m, dalle pleine 20 cm, G2 = 1,0 kN/m², Q = 1,5 kN/m², rives sur voiles
D3 = dict(lx=6.119, ly=9.35, h=0.20, g2_kn_m2=1.0, q_kn_m2=1.5, d_m=0.175)


def test_d3_span_moment_short_direction_matches_bet():
    r = s2.design(**D3)
    assert r["span"]["x"]["m_knm"] == pytest.approx(36.1069, rel=0.01)        # BET Oy Mu = 3,61069 T·m


def test_d3_steel_mesh_and_minimum_match_bet():
    r = s2.design(**D3)
    assert r["as_min_cm2_m"] == pytest.approx(2.33, abs=0.02)                   # BET ATh appuis = 2,33
    assert r["span"]["x"]["as_req_cm2_m"] == pytest.approx(4.83, rel=0.03)      # BET ATh bas = 4,83
    assert r["span"]["x"]["mesh"]["label"] == "ST50"                            # BET : ST50 (5,03)


def test_d3_edge_supports_match_bet():
    r = s2.design(**D3)
    for k in ("x0", "x1", "y0", "y1"):
        assert r["supports"][k]["m_knm"] == pytest.approx(-4.3443, rel=0.01)  # BET appuis voiles −0,43443 T·m
        assert r["supports"][k]["mesh"]["label"] == "ST10+PAF10"               # BET : ST10 + PAF10 = 2,38


def test_d3_long_direction_is_conservative():
    r = s2.design(**D3)
    assert r["span"]["y"]["m_knm"] >= 9.44                                     # BET Ox = 0,944 T·m


def test_d2_rectangle_equivalent_is_safe_and_close():
    r = s2.design(6.09, 10.20, 0.20, 1.0, 2.5, d_m=0.175)
    m = r["span"]["x"]["m_knm"]
    assert 41.5441 <= m <= 41.5441 * 1.10                                       # BET Oy Mu = 4,15441 T·m


def test_ld_limit_reproduces_bet_both_directions():
    # BET D2 : Oy L/d 37,48 ≤ 41,95 (K 1,5 ; correction 1,043) ; Ox L/d 62,77 ≤ 323,35 (correction 1,400)
    oy = s2.ld_check(6.09, 0.1625, 5.59, 5.83, 25, 1.5)
    assert oy["l_over_d"] == pytest.approx(37.48, abs=0.05)
    assert oy["limit"] == pytest.approx(41.95, rel=0.005)
    assert oy["correction"] == pytest.approx(1.043, abs=0.001)
    ox = s2.ld_check(10.2, 0.1625, 1.77, 2.48, 25, 1.5)
    assert ox["limit"] == pytest.approx(323.35, rel=0.005)


def test_one_way_and_input_validation():
    r = s2.design(2.0, 6.0, 0.16, 1.0, 1.5)
    assert r["one_way"] and r["span"]["y"]["m_knm"] == 0.0
    assert r["span"]["x"]["m_knm"] == pytest.approx(1.25 * r["loads"]["pu"] * 4 / 8)
    with pytest.raises(ValueError):
        s2.design(6.0, 4.0, 0.2, 1, 1)
    with pytest.raises(ValueError):
        s2.design(4.0, 6.0, 0.2, 1, 1, edges={"x0": "encastré"})


def test_continuity_reduces_span_moment():
    rive = s2.design(5.0, 6.0, 0.20, 1.0, 1.5)
    cont = s2.design(5.0, 6.0, 0.20, 1.0, 1.5, edges={"x0": "continu", "x1": "continu"})
    assert cont["span"]["x"]["m_knm"] == pytest.approx(0.75 * cont["m0"]["x"], abs=2e-3)
    assert cont["span"]["x"]["m_knm"] < rive["span"]["x"]["m_knm"]
