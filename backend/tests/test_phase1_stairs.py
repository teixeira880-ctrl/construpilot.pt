"""Tests pytest pour les nouveaux moteurs Phase 1 : QT haut + demi-tournant."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from stair_engine import (
    HalfTurnInput,
    QuarterTurnBottomInput as _QTBInput,
    QuarterTurnTopInput,
    compute_half_turn,
    compute_quarter_turn_top,
)


def _codes(r):
    return {a.code for a in r.alerts}


# ---------------------------------------------------------------------------
# Quarter-turn top
# ---------------------------------------------------------------------------

def test_qt_top_standard_straight():
    """QT haut mode straight : volée basse + palier arrivée."""
    r = compute_quarter_turn_top(
        QuarterTurnTopInput(
            floor_height_mm=2800, available_length_mm=5500, available_width_mm=2000,
            stair_width_mm=900, balancing="straight",
            landing_length_mm=1000, landing_width_mm=1000,
        )
    )
    assert r.stair_type == "quarter_turn_top_straight"
    assert r.num_steps == 16
    assert abs(r.riser_height_mm - 175) <= 1
    assert r.is_buildable is True


def test_qt_top_balanced_auto_ok():
    """QT haut mode auto : trouve une config buildable."""
    r = compute_quarter_turn_top(
        QuarterTurnTopInput(
            floor_height_mm=2800, available_length_mm=4500, available_width_mm=2200,
            stair_width_mm=900, balancing="balanced",
        )
    )
    assert r.is_buildable is True
    assert any(a.code == "AUTO_WINDERS_SELECTED" for a in r.alerts)


def test_qt_top_insufficient_run_blocker():
    """QT haut avec reculement insuffisant → is_buildable=false."""
    r = compute_quarter_turn_top(
        QuarterTurnTopInput(
            floor_height_mm=2800, available_length_mm=1000, available_width_mm=2000,
            stair_width_mm=900, balancing="straight",
            landing_length_mm=1000, landing_width_mm=1000,
        )
    )
    assert r.is_buildable is False
    assert "STAIR_RUN_TOO_LONG" in _codes(r)


def test_qt_top_dtu_nonconform_but_buildable():
    """QT haut : walkline < 240 mais fit géométriquement → buildable=true avec red DTU."""
    r = compute_quarter_turn_top(
        QuarterTurnTopInput(
            floor_height_mm=2800, available_length_mm=5000, available_width_mm=2200,
            stair_width_mm=900, balancing="balanced",
            num_winders=6, walkline_offset_mm=500,
        )
    )
    # 6 winders → walkline arc = 500 * π/12 ≈ 131mm < 240
    assert "BALANCING_WALKLINE_TOO_SMALL" in _codes(r)
    # Géométrie doit rentrer (5000mm large)
    assert r.is_buildable is True


def test_qt_top_headroom_insufficient():
    """QT haut avec trémie trop courte + ceiling bas → headroom < 1900."""
    r = compute_quarter_turn_top(
        QuarterTurnTopInput(
            floor_height_mm=2800, available_length_mm=5000, available_width_mm=2000,
            stair_width_mm=900, balancing="straight",
            landing_length_mm=1000, landing_width_mm=1000,
            stairwell_length_mm=1000, stairwell_width_mm=1000, ceiling_height_mm=2400,
        )
    )
    assert "HEADROOM_INSUFFICIENT" in _codes(r)
    assert r.is_buildable is False


# ---------------------------------------------------------------------------
# Half turn
# ---------------------------------------------------------------------------

def test_half_turn_straight_standard():
    """Demi-tournant straight : 2 volées + palier intermédiaire."""
    r = compute_half_turn(
        HalfTurnInput(
            floor_height_mm=2800, available_length_mm=3000, available_width_mm=2200,
            stair_width_mm=900, balancing="straight",
            landing_length_mm=1000,
        )
    )
    assert r.stair_type == "half_turn_straight"
    assert r.num_steps == 16
    assert r.is_buildable is True
    # steps_per_flight: [n_lower, 1, n_upper-1]
    assert len(r.steps_per_flight) == 3


def test_half_turn_balanced_auto_ok():
    """Demi-tournant auto : trouve config buildable avec 4-12 winders."""
    r = compute_half_turn(
        HalfTurnInput(
            floor_height_mm=2800, available_length_mm=2800, available_width_mm=2000,
            stair_width_mm=900, balancing="balanced",
        )
    )
    assert r.is_buildable is True
    assert any(a.code == "AUTO_WINDERS_SELECTED" for a in r.alerts)


def test_half_turn_insufficient_width():
    """Demi-tournant : largeur dispo < 2×stair_width → STAIR_WIDTH_INSUFFICIENT."""
    r = compute_half_turn(
        HalfTurnInput(
            floor_height_mm=2800, available_length_mm=3000, available_width_mm=1500,
            stair_width_mm=900, balancing="straight",
        )
    )
    # 2*900 = 1800 > 1500
    assert "STAIR_WIDTH_INSUFFICIENT" in _codes(r)
    assert r.is_buildable is False


def test_half_turn_insufficient_run():
    """Demi-tournant : longueur dispo trop courte."""
    r = compute_half_turn(
        HalfTurnInput(
            floor_height_mm=2800, available_length_mm=1500, available_width_mm=2200,
            stair_width_mm=900, balancing="straight",
        )
    )
    assert "STAIR_RUN_TOO_LONG" in _codes(r)
    assert r.is_buildable is False


def test_half_turn_num_winders_out_of_range():
    """num_winders hors 4-12 rejeté pour demi-tournant."""
    with pytest.raises(ValidationError):
        HalfTurnInput(
            floor_height_mm=2800, available_length_mm=3000, available_width_mm=2200,
            stair_width_mm=900, balancing="balanced", num_winders=2,
        )
    with pytest.raises(ValidationError):
        HalfTurnInput(
            floor_height_mm=2800, available_length_mm=3000, available_width_mm=2200,
            stair_width_mm=900, balancing="balanced", num_winders=20,
        )


def test_half_turn_dtu_walkline_alert():
    """Demi-tournant : 10 winders → walkline très petit → alerte red non-blocker."""
    r = compute_half_turn(
        HalfTurnInput(
            floor_height_mm=2800, available_length_mm=3500, available_width_mm=2200,
            stair_width_mm=900, balancing="balanced", num_winders=10,
        )
    )
    # walkline = 500 * π/10 ≈ 157 < 240
    assert "BALANCING_WALKLINE_TOO_SMALL" in _codes(r)


def test_half_turn_all_alerts_have_message():
    """Toutes les alertes du demi-tournant ont un message non-vide."""
    r = compute_half_turn(
        HalfTurnInput(
            floor_height_mm=2800, available_length_mm=1500, available_width_mm=1200,
            stair_width_mm=900, balancing="balanced",
        )
    )
    for a in r.alerts:
        assert a.message and a.message.strip()
        assert a.message == a.message_fr
