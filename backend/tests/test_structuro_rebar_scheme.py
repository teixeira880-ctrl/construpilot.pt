"""Plans de ferraillage — tests déterministes du passage As → schéma d'armatures."""
import pytest

from engines import structuro_rebar_scheme as rs


def test_longitudinal_covers_as():
    s = rs.scheme(5.39, 2.4, bar_mm=16, stirrup_mm=8, legs=2, s_max_m=0.30)
    assert s["longitudinal"]["count"] == 3            # 3Ø16 ≈ 6.03 cm² ≥ 5.39
    assert s["longitudinal"]["as_provided_cm2"] >= 5.39
    assert s["longitudinal"]["label"] == "3Ø16"
    assert s["execution_ready"] is False


def test_stirrups_respect_s_max():
    s = rs.scheme(5.39, 2.4, bar_mm=16, stirrup_mm=8, legs=2, s_max_m=0.30)
    assert s["stirrups"]["s_adopt_m"] <= 0.30
    assert s["stirrups"]["asw_s_prov_cm2_m"] >= 2.4


def test_no_shear_no_stirrups():
    s = rs.scheme(10.0, 0.0)
    assert s["stirrups"] is None
    assert s["longitudinal"]["count"] >= 2


def test_invalid_diameter():
    with pytest.raises(ValueError):
        rs.scheme(5, 2, bar_mm=15)
