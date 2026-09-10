"""Tests pytest Phase 3 : module béton armé."""
from __future__ import annotations
import pytest

from stair_engine import (
    ConcreteAnalysisInput, StairInput,
    compute_concrete_analysis, compute_straight, compute_quarter_turn_bottom,
    QuarterTurnBottomInput, compute_half_turn,
)
from stair_engine.half_turn import HalfTurnInput


def _codes(r):
    return {a.code for a in r.alerts}


def _straight_result_2800_4500():
    return compute_straight(StairInput(
        floor_height_mm=2800, available_length_mm=5000,
        available_width_mm=1500, stair_width_mm=900,
    ))


def test_concrete_straight_standard():
    """Métré standard H=2800/L=4500/W=900 : volume ~0.85m³, coffrage ~9m²."""
    r = _straight_result_2800_4500()
    ca = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="straight",
    ))
    # Volume plausible : paillasse + marches
    assert 0.5 <= ca.quantities["concrete_volume_m3"] <= 1.5
    assert ca.quantities["formwork_area_m2"] > 5
    assert ca.quantities["paillasse_thickness_mm"] >= 120
    assert len(ca.nomenclature) >= 5
    # Disclaimer présent
    assert "message_fr" in ca.disclaimer
    assert "indicatif" in ca.disclaimer["message_fr"].lower()


def test_concrete_paillasse_thickness_from_abaque():
    """Portée ~4m, charge domestique → épaisseur ~200mm depuis abaque."""
    r = _straight_result_2800_4500()
    ca = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="straight",
        live_load_kN_m2=2.5, dead_load_extra_kN_m2=1.5,
    ))
    # stair_length ~ sqrt(2800² + 4200²) = 5049mm → hors abaque (> 5000)
    # Vérifions le comportement
    assert ca.paillasse["thickness_recommended_mm"] >= 100


def test_concrete_out_of_abaque_span_6m():
    """Portée > 5m → SPAN_EXCEEDS_SIMPLE_ANALYSIS."""
    r = _straight_result_2800_4500()
    ca = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="straight",
        slab_span_mm=6000,
    ))
    assert "SPAN_EXCEEDS_SIMPLE_ANALYSIS" in _codes(ca)
    assert "PAILLASSE_OUT_OF_ABAQUE" in _codes(ca)


def test_concrete_exposure_XC3_alert():
    """Exposition XC3 → alerte HIGH_EXPOSURE_REQUIRES_VALIDATION."""
    r = _straight_result_2800_4500()
    ca = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="straight",
        exposure_class="XC3",
    ))
    assert "HIGH_EXPOSURE_REQUIRES_VALIDATION" in _codes(ca)
    assert ca.reinforcement["cover_mm"] == 30


def test_concrete_qt_bottom():
    """Métré QT bas."""
    r = compute_quarter_turn_bottom(QuarterTurnBottomInput(
        floor_height_mm=2800, available_length_mm=4500,
        available_width_mm=2200, stair_width_mm=900,
        balancing="balanced",
    ))
    ca = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="quarter_turn_bottom",
    ))
    assert ca.quantities["concrete_volume_m3"] > 0


def test_concrete_half_turn():
    """Métré demi-tournant."""
    r = compute_half_turn(HalfTurnInput(
        floor_height_mm=2800, available_length_mm=3000,
        available_width_mm=2200, stair_width_mm=900,
        balancing="balanced",
    ))
    ca = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="half_turn",
    ))
    assert ca.quantities["concrete_volume_m3"] > 0
    assert len(ca.nomenclature) >= 5


def test_concrete_nomenclature_weight_consistent():
    """Le poids nomenclature = 0.006165 × d² × longueur × nb (kg/m)."""
    r = _straight_result_2800_4500()
    ca = compute_concrete_analysis(ConcreteAnalysisInput(stair_result=r, stair_type="straight"))
    for row in ca.nomenclature:
        d = int(row.diameter.replace("HA", ""))
        expected_kg = 0.006165 * d * d * row.total_length_m
        assert abs(row.weight_kg - expected_kg) < 0.5, f"repere {row.repere}: attendu {expected_kg:.2f}, obtenu {row.weight_kg}"


def test_concrete_disclaimer_always_present():
    """Le disclaimer est systématique."""
    r = _straight_result_2800_4500()
    ca = compute_concrete_analysis(ConcreteAnalysisInput(stair_result=r, stair_type="straight"))
    assert ca.disclaimer is not None
    assert "message_fr" in ca.disclaimer
    assert "CONCRETE_ANALYSIS_INDICATIVE" in _codes(ca)


def test_concrete_abaque_interpolation():
    """Portée 3200mm → épaisseur interpolée entre 3000 et 3500."""
    from stair_engine.concrete_abaques import lookup_paillasse_thickness
    t3000, _, _ = lookup_paillasse_thickness(3000, 5)
    t3500, _, _ = lookup_paillasse_thickness(3500, 5)
    t3200, _, _ = lookup_paillasse_thickness(3200, 5)
    assert t3000 <= t3200 <= t3500


def test_concrete_heavy_live_load():
    """Charge ERP 4kN/m² → épaisseur > cas domestique."""
    r = _straight_result_2800_4500()
    ca_light = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="straight", live_load_kN_m2=2.5, slab_span_mm=4000,
    ))
    ca_heavy = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="straight", live_load_kN_m2=4.0, slab_span_mm=4000,
    ))
    assert ca_heavy.paillasse["thickness_recommended_mm"] >= ca_light.paillasse["thickness_recommended_mm"]


def test_concrete_flying_stairs_rejected():
    r = _straight_result_2800_4500()
    ca = compute_concrete_analysis(ConcreteAnalysisInput(
        stair_result=r, stair_type="straight", is_flying=True,
    ))
    assert "FLYING_STAIRS_OUT_OF_SCOPE" in _codes(ca)
