"""Solveur d'escalier demi-tournant dans une cage — contrôles géométriques et cas La Courneuve (3 rue Beaufils)."""
import math

import pytest

from stair_engine import HalfTurnInput, compute_half_turn
from stair_engine.cage_solver import CageStairInput, solve_cage, stacked_headroom, nosing_line

BASE = dict(cage_width_mm=1800, jour_mm=100, slab_thickness_mm=220, flight_thickness_mm=120)


def _area(poly):
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]))) / 2


def _courneuve():
    et = solve_cage(CageStairInput(floor_height_mm=2750, cage_length_mm=2200, start_free_length_mm=0, **BASE))
    rdc = solve_cage(CageStairInput(floor_height_mm=3250, cage_length_mm=2300, start_free_length_mm=350, **BASE),
                     above=(et, 3250, -100))
    ss = solve_cage(CageStairInput(floor_height_mm=2040, cage_length_mm=2300, start_free_length_mm=0, **BASE),
                    above=(rdc, 2040, 0))
    return ss, rdc, et


def test_balanced_walkline_is_filled_exactly():
    _, rdc, _ = _courneuve()
    r = (100 / 2 + rdc.walkline_offset_mm)
    walk = 2 * rdc.y_noyau_mm + math.pi * r                      # LdF dans la cage
    assert (rdc.num_risers - 1 - rdc.start_extension) * rdc.giron_mm == pytest.approx(walk, abs=1.0)
    assert rdc.riser_mm * rdc.num_risers == pytest.approx(3250, abs=0.5)


def test_treads_tile_the_cage():
    _, rdc, _ = _courneuve()
    W, L, j = 1800, 2300, 100
    expected = W * L - j * rdc.y_noyau_mm + rdc.start_extension * rdc.giron_mm * rdc.flight_width_mm
    total = sum(_area(t.polygon) for t in rdc.treads)
    assert total == pytest.approx(expected, rel=0.01)


def test_balancing_gives_usable_inner_giron_and_dtu_ranges():
    ss, rdc, et = _courneuve()
    for r in (rdc, et):
        assert r.mode == "balanced"
        assert r.min_inner_giron_mm >= 120
        assert 580 <= r.blondel_mm <= 660
        assert r.slope_deg <= 35
        assert r.dtu_compliant
    assert ss.mode == "landing" and ss.giron_mm == pytest.approx(ss.y_noyau_mm / 5)


def test_stacked_headroom_hand_check():
    ss, rdc, _ = _courneuve()
    # σ = 0 (bord de trémie, volée de départ) : ligne des nez RdC = h(1 + e) ; sous-face = − h − e_p / cos α
    z_rdc = rdc.riser_mm * (1 + rdc.start_extension)
    soffit = 2040 + z_rdc - rdc.riser_mm - 120 / math.cos(math.radians(rdc.slope_deg))
    expected = soffit - nosing_line(ss, 0.0)
    hr = stacked_headroom(ss, rdc, 2040)
    assert hr["min_headroom_mm"] == pytest.approx(expected, abs=1.0)
    assert hr["min_headroom_mm"] >= 1900


def test_free_length_limits_start_extension():
    r = solve_cage(CageStairInput(floor_height_mm=3250, cage_length_mm=2300, start_free_length_mm=0, **BASE))
    assert r.start_extension == 0
    r = solve_cage(CageStairInput(floor_height_mm=3250, cage_length_mm=2300, start_free_length_mm=350, **BASE))
    assert r.start_extension * r.giron_mm <= 350


def test_half_turn_slope_is_flight_pitch_not_footprint():
    r = compute_half_turn(HalfTurnInput(floor_height_mm=3250, available_length_mm=2300, available_width_mm=1800,
                                        stair_width_mm=850))
    assert r.slope_deg == pytest.approx(math.degrees(math.atan2(r.riser_height_mm, r.tread_depth_mm)), abs=0.05)
