"""Lot 79 — escalier droit : largeur contrôlée, pas de « optimal » avec une alerte rouge."""
from stair_engine.models import StairInput
from stair_engine import straight


def _calc(**kw):
    base = dict(floor_height_mm=2700, available_length_mm=4500, available_width_mm=1000, stair_width_mm=900)
    base.update(kw)
    fn = straight.compute_straight
    return fn(StairInput(**base))


def _codes(r):
    return [a.code for a in r.alerts]


def test_width_exceeding_available_is_blocking():
    r = _calc(available_width_mm=600)
    assert "STAIR_WIDTH_INSUFFICIENT" in _codes(r)
    assert "GEOMETRY_OK" not in _codes(r)
    assert r.is_buildable is False


def test_no_optimal_when_it_does_not_fit():
    r = _calc(available_length_mm=2000)
    assert "STAIR_RUN_TOO_LONG" in _codes(r) and "OPTIMAL_CONFIG" not in _codes(r)


def test_normal_case_unchanged():
    r = _calc()
    assert "STAIR_WIDTH_INSUFFICIENT" not in _codes(r) and r.is_buildable is True
