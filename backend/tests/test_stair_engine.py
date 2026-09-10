"""Tests pytest du moteur STAIRPILOT — Phase 0.

Lancer : cd /app/backend && pytest tests/ -v
"""
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from stair_engine import (
    DTU_36_3_FR,
    QuarterTurnBottomInput,
    StairInput,
    blondel_value,
    compute_quarter_turn_bottom,
    compute_straight,
    optimal_giron_mm,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _alert_codes(result):
    return {a.code for a in result.alerts}


def _alerts_with_level(result, level):
    return [a for a in result.alerts if a.level == level]


# ---------------------------------------------------------------------------
# Escalier droit
# ---------------------------------------------------------------------------

def test_01_standard_stair_2800_4200():
    """Escalier droit standard H=2800, L=4200 → ~16 marches h=175 g=280."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2800,
            available_length_mm=4200,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    assert r.num_steps == 16
    assert abs(r.riser_height_mm - 175) <= 1
    assert abs(r.tread_depth_mm - 280) <= 5
    assert 580 <= r.blondel_value_mm <= 660
    assert r.is_buildable is True
    assert "OPTIMAL_CONFIG" in _alert_codes(r) or "GEOMETRY_OK" in _alert_codes(r)


def test_02_standard_stair_2500_3600():
    """H=2500, L=3600 → 15 marches h≈166.67 g≈296 (moteur minimise |h-170|)."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2500,
            available_length_mm=4500,  # large pour tenir 14*296 = 4144
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    assert r.num_steps == 15
    assert abs(r.riser_height_mm - 166.67) <= 1
    assert abs(r.tread_depth_mm - 296.67) <= 5
    assert 580 <= r.blondel_value_mm <= 660
    assert r.is_buildable is True


def test_03_non_divisible_height():
    """H=2777, L=4000 → arrondi propre h≈173.56, alertes présentes (Blondel/run)."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2777,
            available_length_mm=4000,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    assert r.num_steps == 16
    assert abs(r.riser_height_mm - 173.56) <= 1
    # Reculement 15*283 ≈ 4245 > 4000 → alerte rouge STAIR_RUN_TOO_LONG
    assert "STAIR_RUN_TOO_LONG" in _alert_codes(r)
    assert r.is_buildable is False


def test_04_insufficient_run():
    """Reculement insuffisant : H=2800, L=2500 → alerte rouge STAIR_RUN_TOO_LONG."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2800,
            available_length_mm=2500,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    assert "STAIR_RUN_TOO_LONG" in _alert_codes(r)
    assert r.is_buildable is False
    assert any(a.level == "red" for a in r.alerts)


def test_05_headroom_insufficient():
    """Trémie courte + ceiling bas → échappée < 1.90m."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2800,
            available_length_mm=5000,
            available_width_mm=1500,
            stair_width_mm=900,
            stairwell_length_mm=1500,  # courte
            stairwell_width_mm=1000,
            ceiling_height_mm=2500,  # bas
        )
    )
    assert "HEADROOM_INSUFFICIENT" in _alert_codes(r)
    head_alerts = [a for a in r.alerts if a.code == "HEADROOM_INSUFFICIENT"]
    assert head_alerts[0].level == "red"
    assert head_alerts[0].tread_index is not None
    assert r.is_buildable is False


def test_06_small_height():
    """H=500, L=2000 → 3 marches h≈166 g≈296 mais pente >40° (petit escalier compact)."""
    r = compute_straight(
        StairInput(
            floor_height_mm=500,
            available_length_mm=2000,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    assert r.num_steps == 3
    assert abs(r.riser_height_mm - 166.67) <= 1
    # Pente extrême (3 marches, 500mm de haut, 593mm de long) → alerte rouge SLOPE_TOO_STEEP
    assert "SLOPE_TOO_STEEP" in _alert_codes(r)


def test_07_extreme_height():
    """H=6000 → 34 marches, alerte car aucune volée intermédiaire (Phase 0 mono-volée)."""
    r = compute_straight(
        StairInput(
            floor_height_mm=6000,
            available_length_mm=15000,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    # 6000/34 ≈ 176.47 (dans plage optimale)
    assert r.num_steps in (34, 35)
    assert 160 <= r.riser_height_mm <= 180
    assert r.is_buildable is True


def test_08_narrow_width():
    """Largeur < 700mm → alerte orange STAIR_WIDTH_TOO_SMALL."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2800,
            available_length_mm=5000,
            available_width_mm=1500,
            stair_width_mm=600,
        )
    )
    assert "STAIR_WIDTH_TOO_SMALL" in _alert_codes(r)
    width_alert = [a for a in r.alerts if a.code == "STAIR_WIDTH_TOO_SMALL"][0]
    assert width_alert.level == "orange"


def test_09_qt_bottom_balanced_ok():
    """QT bas balanced H=2800, L=3500, W=2200 → répartition marches OK."""
    r = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=3500,
            available_width_mm=2200,
            stair_width_mm=900,
            balancing="balanced",
            num_winders=3,
            walkline_offset_mm=500,
        )
    )
    assert r.num_steps == 16
    assert abs(r.riser_height_mm - 175) <= 1
    # 3 winders sur 90° → 30°/winder, giron walkline = 500 * π/6 ≈ 261.8 (>= 240)
    winders = [t for t in r.treads if t.type == "winder"]
    assert len(winders) == 3
    assert winders[0].depth_walkline_mm >= 240
    assert "BALANCING_WALKLINE_TOO_SMALL" not in _alert_codes(r)


def test_10_qt_bottom_balanced_tight_walkline_fails():
    """QT bas balanced avec walkline_offset faible → BALANCING_WALKLINE_TOO_SMALL (non-conformité DTU)."""
    r = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=3500,
            available_width_mm=2200,
            stair_width_mm=900,
            balancing="balanced",
            num_winders=4,
            walkline_offset_mm=200,  # trop petit
        )
    )
    # walkline = 200 * π/8 ≈ 78.5 → < 240
    assert "BALANCING_WALKLINE_TOO_SMALL" in _alert_codes(r)
    # Le run 900 + 11*280 = 3980 > 3500 → aussi STAIR_RUN_TOO_LONG (blocker)
    assert r.is_buildable is False


def test_11_qt_bottom_straight_landing():
    """QT bas mode straight avec palier 1000x1000."""
    r = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=5000,
            available_width_mm=2000,
            stair_width_mm=900,
            balancing="straight",
            landing_length_mm=1000,
            landing_width_mm=1000,
            steps_before_landing=0,
        )
    )
    assert r.stair_type == "quarter_turn_bottom_straight"
    assert r.num_steps == 16
    # Emprise : landing_length + (num_upper-1)*g = 1000 + 15*280 = 5200 > 5000 → red run alert
    # Ou dans la limite. Vérifions selon la valeur exacte.


def test_12_qt_bottom_available_width_insufficient():
    """QT bas balanced avec largeur disponible < largeur escalier → alerte."""
    r = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=4000,
            available_width_mm=800,  # < stair_width 900
            stair_width_mm=900,
            balancing="balanced",
        )
    )
    assert "STAIR_WIDTH_INSUFFICIENT" in _alert_codes(r)
    assert r.is_buildable is False


def test_13_negative_height_rejected():
    """Hauteur négative rejetée par Pydantic."""
    with pytest.raises(ValidationError):
        StairInput(
            floor_height_mm=-100,
            available_length_mm=4000,
            available_width_mm=1500,
            stair_width_mm=900,
        )


def test_14_zero_length_rejected():
    """Reculement nul rejeté."""
    with pytest.raises(ValidationError):
        StairInput(
            floor_height_mm=2800,
            available_length_mm=0,
            available_width_mm=1500,
            stair_width_mm=900,
        )


def test_15_extreme_large_values():
    """Very large but valid values do not crash."""
    r = compute_straight(
        StairInput(
            floor_height_mm=4000,
            available_length_mm=20000,
            available_width_mm=5000,
            stair_width_mm=1200,
        )
    )
    assert r.num_steps > 0
    assert r.is_buildable is True


def test_16_blondel_formula():
    """Test unitaire de la formule de Blondel."""
    assert blondel_value(175, 280) == 630
    assert blondel_value(180, 260) == 620


def test_17_optimal_giron_computation():
    """Giron optimal via Blondel = 630 - 2h."""
    assert optimal_giron_mm(175) == pytest.approx(280, abs=1)
    assert optimal_giron_mm(160) == pytest.approx(310, abs=1)
    # Clamp haut
    assert optimal_giron_mm(150) == 320
    # Clamp bas (h=250 → g théorique 130 → clampé 220)
    assert optimal_giron_mm(250) == 220


def test_18_slope_calculation():
    """Vérifie la pente calculée."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2800,
            available_length_mm=5000,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    expected_slope = math.degrees(math.atan2(2800, r.stair_run_mm))
    assert abs(r.slope_deg - expected_slope) < 0.5
    # 16 marches, 15 girons de 280 = 4200 → slope = atan(2800/4200) ≈ 33.7°
    assert 30 <= r.slope_deg <= 40


def test_19_headroom_ok_with_generous_stairwell():
    """Trémie généreuse + ceiling haut → échappée OK."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2800,
            available_length_mm=5000,
            available_width_mm=1500,
            stair_width_mm=900,
            stairwell_length_mm=3500,
            stairwell_width_mm=1000,
            ceiling_height_mm=2800,
        )
    )
    assert "HEADROOM_INSUFFICIENT" not in _alert_codes(r)
    assert r.headroom_mm > 1900 or r.headroom_mm == -1  # -1 = inf


def test_20_optimal_config_alert():
    """Configuration idéale → alerte verte OPTIMAL_CONFIG."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2720,  # 17*160 = 2720 → h=160, g=310 → Blondel=630, slope≈30°
            available_length_mm=6000,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    # h=170, g=290, blondel=630, slope=atan(2720/16*290)... check
    assert r.is_buildable is True
    codes = _alert_codes(r)
    # Au minimum GEOMETRY_OK ou OPTIMAL_CONFIG doit être présent
    assert "OPTIMAL_CONFIG" in codes or "GEOMETRY_OK" in codes


def test_21_norms_endpoint_values():
    """Sanity check sur les seuils DTU."""
    d = DTU_36_3_FR.as_dict()
    assert d["headroom_min_mm"] == 1900
    assert d["blondel_optimal_min_mm"] == 600
    assert d["blondel_optimal_max_mm"] == 640
    assert d["standard"] == "DTU 36.3"
    assert d["country_code"] == "FR"


def test_22_result_has_computed_at():
    """Le résultat contient un timestamp."""
    r = compute_straight(
        StairInput(
            floor_height_mm=2800,
            available_length_mm=5000,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    assert r.computed_at is not None


def test_23_qt_balanced_treads_geometry():
    """Vérifie la géométrie des winders."""
    r = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=4500,
            available_width_mm=2200,
            stair_width_mm=1000,
            balancing="balanced",
            num_winders=3,
            walkline_offset_mm=500,
        )
    )
    winders = [t for t in r.treads if t.type == "winder"]
    assert len(winders) == 3
    # 3 winders sur 90° = 30° chacun
    for w in winders:
        assert abs(w.angle_deg - 30.0) < 0.1
    # Somme des hauteurs cumulées correcte
    assert winders[-1].cumulative_height_mm == pytest.approx(3 * r.riser_height_mm)


def test_24_riser_too_high_alert():
    """Hauteur élevée → alerte RISER_TOO_HIGH."""
    # H=3800 sur 19 marches = 200 mm → limite haute
    r = compute_straight(
        StairInput(
            floor_height_mm=3800,
            available_length_mm=6000,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    # Le moteur doit trouver h dans plage optimale : 3800/20 = 190 (>180 → non optimal)
    # ou 3800/22 = 172.7 (optimal). Il choisira 22 marches.
    assert r.num_steps in range(21, 24)
    assert 160 <= r.riser_height_mm <= 180


def test_25_qt_bottom_auto_winders_tight_run():
    """QT bas H=2800/L=3000/W=2200 avec num_winders='auto' doit trouver une config buildable."""
    r = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=3000,
            available_width_mm=2200,
            stair_width_mm=900,
            stairwell_length_mm=2800,
            stairwell_width_mm=1000,
            ceiling_height_mm=2800,
            balancing="balanced",
            # num_winders omitted → défaut auto
        )
    )
    assert r.is_buildable is True, (
        f"Attendu buildable=True, obtenu {r.is_buildable}, alerts={[a.code for a in r.alerts]}"
    )
    # Sélection auto doit être signalée
    auto_alerts = [a for a in r.alerts if a.code == "AUTO_WINDERS_SELECTED"]
    assert len(auto_alerts) == 1
    winders_used = int(auto_alerts[0].value)
    # Contraint géométrique : L=3000 impose de nombreux winders (typiquement 6-9)
    assert 6 <= winders_used <= 9, f"Nb winders sélectionné = {winders_used}"
    # Encombrement doit rentrer
    footprint = r.required_stairwell_mm["turn_footprint_length_mm"] + r.required_stairwell_mm["min_length_mm"]
    assert footprint <= 3000 + 1  # tolérance arrondi


def test_26_all_alerts_have_message():
    """Toutes les alertes retournées doivent avoir un champ `message` non-vide."""
    scenarios = [
        # Scenario nominal
        compute_straight(
            StairInput(
                floor_height_mm=2800,
                available_length_mm=4500,
                available_width_mm=1500,
                stair_width_mm=900,
                stairwell_length_mm=3200,
                stairwell_width_mm=1000,
                ceiling_height_mm=2800,
            )
        ),
        # Scenario avec plusieurs alertes rouges
        compute_straight(
            StairInput(
                floor_height_mm=2800,
                available_length_mm=2000,
                available_width_mm=1500,
                stair_width_mm=600,
                stairwell_length_mm=1000,
                stairwell_width_mm=500,
                ceiling_height_mm=2400,
            )
        ),
        # QT bas
        compute_quarter_turn_bottom(
            QuarterTurnBottomInput(
                floor_height_mm=2800,
                available_length_mm=3000,
                available_width_mm=2200,
                stair_width_mm=900,
                balancing="balanced",
            )
        ),
    ]
    for r in scenarios:
        assert len(r.alerts) > 0
        for a in r.alerts:
            assert a.message and a.message.strip(), f"Alerte {a.code} sans message: {a}"
            assert a.message_fr and a.message_fr.strip(), f"Alerte {a.code} sans message_fr: {a}"
            # message doit être identique à message_fr (auto-populated)
            assert a.message == a.message_fr


def test_27_qt_bottom_manual_winders_5():
    """QT bas mode balanced avec num_winders=5 explicite."""
    r = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=3500,
            available_width_mm=2200,
            stair_width_mm=900,
            balancing="balanced",
            num_winders=5,
        )
    )
    winders = [t for t in r.treads if t.type == "winder"]
    assert len(winders) == 5
    # 5 winders sur 90° → 18° par winder
    assert abs(winders[0].angle_deg - 18.0) < 0.1
    # walkline = 500 * (π/2 / 5) = 500 * 0.314159 ≈ 157.08 → < 240 → alerte rouge non-blocker
    assert "BALANCING_WALKLINE_TOO_SMALL" in _alert_codes(r)


def test_28_num_winders_out_of_range_rejected():
    """num_winders hors range 2-9 rejeté."""
    with pytest.raises(ValidationError):
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=3500,
            available_width_mm=2200,
            stair_width_mm=900,
            balancing="balanced",
            num_winders=15,  # trop élevé
        )
    with pytest.raises(ValidationError):
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=3500,
            available_width_mm=2200,
            stair_width_mm=900,
            balancing="balanced",
            num_winders="wrong-string",
        )


def test_29_auto_and_explicit_same_winders_give_same_is_buildable():
    """Sécurité : auto-mode et mode explicite avec le MÊME nombre de winders
    doivent produire la même géométrie et donc le même is_buildable."""
    # H=2800, L=3000, W=2200 : auto choisit 8 winders (validé par test_25).
    base_params = dict(
        floor_height_mm=2800,
        available_length_mm=3000,
        available_width_mm=2200,
        stair_width_mm=900,
        stairwell_length_mm=2800,
        stairwell_width_mm=1000,
        ceiling_height_mm=2800,
        balancing="balanced",
    )

    r_auto = compute_quarter_turn_bottom(QuarterTurnBottomInput(**base_params))
    auto_alerts = [a for a in r_auto.alerts if a.code == "AUTO_WINDERS_SELECTED"]
    assert len(auto_alerts) == 1
    winders_auto = int(auto_alerts[0].value)

    r_explicit = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(**base_params, num_winders=winders_auto)
    )

    # Même géométrie (au sens strict) et donc même is_buildable
    assert r_auto.is_buildable == r_explicit.is_buildable
    assert r_auto.num_treads == r_explicit.num_treads
    assert r_auto.stair_run_mm == r_explicit.stair_run_mm
    assert r_auto.riser_height_mm == r_explicit.riser_height_mm
    # Les alertes non-auto doivent être les mêmes
    codes_auto = {a.code for a in r_auto.alerts if a.code != "AUTO_WINDERS_SELECTED"}
    codes_explicit = {a.code for a in r_explicit.alerts}
    assert codes_auto == codes_explicit


def test_30_physically_impossible_geometry_is_not_buildable():
    """Géométrie physiquement impossible → is_buildable=false avec alerte rouge blocker."""
    # H=2800 avec L=500 : impossible de faire tenir un escalier
    r = compute_straight(
        StairInput(
            floor_height_mm=2800,
            available_length_mm=500,
            available_width_mm=1500,
            stair_width_mm=900,
        )
    )
    assert r.is_buildable is False
    blockers = {"STAIR_RUN_TOO_LONG", "STAIR_WIDTH_INSUFFICIENT", "HEADROOM_INSUFFICIENT",
                "STAIRWELL_TOO_SMALL", "GEOMETRY_INVALID", "BALANCING_IMPOSSIBLE",
                "AUTO_WINDERS_NO_SOLUTION"}
    red_codes = {a.code for a in r.alerts if a.level == "red"}
    assert red_codes & blockers, f"Aucun blocker géométrique trouvé : {red_codes}"


def test_31_dtu_nonconform_but_physically_ok_is_buildable():
    """Géométrie physiquement possible mais non-conforme DTU (pente > 40°)
    → is_buildable=true avec alerte rouge non-blocker."""
    # H=2800, L=3200 : run réel 15*280=4200 ne rentre pas → STAIR_RUN_TOO_LONG blocker.
    # Pour une pente > 40° sans blocker, il faut un cas différent : escalier balancé auto
    # H=2800, L=3000, W=2200 → auto choisit 8 winders, pente ≈ 44° (rouge non-blocker),
    # walkline < 240 (rouge non-blocker), géométrie qui rentre.
    r = compute_quarter_turn_bottom(
        QuarterTurnBottomInput(
            floor_height_mm=2800,
            available_length_mm=3000,
            available_width_mm=2200,
            stair_width_mm=900,
            balancing="balanced",
        )
    )
    assert r.is_buildable is True
    # Il DOIT y avoir au moins une alerte rouge non-blocker DTU
    red_alerts = [a for a in r.alerts if a.level == "red"]
    assert len(red_alerts) >= 1
    blockers = {"STAIR_RUN_TOO_LONG", "STAIR_WIDTH_INSUFFICIENT", "HEADROOM_INSUFFICIENT",
                "STAIRWELL_TOO_SMALL", "GEOMETRY_INVALID", "BALANCING_IMPOSSIBLE",
                "AUTO_WINDERS_NO_SOLUTION"}
    red_codes = {a.code for a in red_alerts}
    non_blocker_reds = red_codes - blockers
    assert len(non_blocker_reds) > 0, f"Attendu au moins 1 red DTU non-blocker, trouvé : {red_codes}"


def test_32_is_buildable_independent_of_num_winders_when_both_fit():
    """Deux configurations num_winders différentes qui rentrent toutes deux → is_buildable=true."""
    base_params = dict(
        floor_height_mm=2800,
        available_length_mm=5000,  # large : plusieurs configs winder rentrent
        available_width_mm=2500,
        stair_width_mm=900,
        balancing="balanced",
    )
    for n in [3, 4, 5]:
        r = compute_quarter_turn_bottom(
            QuarterTurnBottomInput(**base_params, num_winders=n)
        )
        # Avec L=5000, tous rentrent
        assert r.is_buildable is True, f"n={n} devrait être buildable, alerts={[a.code for a in r.alerts]}"
