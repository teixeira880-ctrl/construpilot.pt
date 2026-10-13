"""Fase 0 — nenhuma escada com alerta vermelho é apresentada como conforme."""
from stair_engine.models import StairInput
from stair_engine.straight import compute_straight
from stair_engine.helicoidal import HelicoidalInput, compute_helicoidal
from stair_engine import alerts as A


def test_straight_standard_is_buildable():
    r = compute_straight(StairInput(floor_height_mm=2800, available_length_mm=4500,
                                    available_width_mm=1000, stair_width_mm=900))
    assert r.is_buildable is True
    assert r.is_geometrically_possible is True
    assert not any(a.level == "red" for a in r.alerts)


def test_steep_helicoidal_not_buildable():
    r = compute_helicoidal(HelicoidalInput(floor_height_mm=3000, inner_radius_mm=150,
                                           outer_radius_mm=700, sweep_angle_deg=270,
                                           walkline_offset_mm=500))
    if any(a.level == "red" for a in r.alerts):
        assert r.is_buildable is False


def test_any_red_alert_blocks():
    red = A.Alert(level="red", code="TREAD_TOO_SMALL", message_fr="x")
    assert A.compute_is_buildable([red]) is False
    assert A.compute_is_geometrically_possible([red]) is True
