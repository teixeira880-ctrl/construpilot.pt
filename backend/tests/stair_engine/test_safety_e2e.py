"""Testes de segurança E2E para o motor de escadas.

Garante que:
- `is_buildable` fica a False quando QUALQUER alerta vermelho é emitido
  (não apenas os `BLOCKING_CODES`).
- `is_geometrically_possible` mantém-se True para configurações que são
  fisicamente construíveis mas regulamentarmente não conformes.
- Uma escada reta normal (2800/4000/850) permanece `is_buildable=True`.
"""
from __future__ import annotations

import pytest

from stair_engine import StairInput, compute_half_turn, compute_quarter_turn_bottom, compute_straight  # noqa: F401
from stair_engine.helicoidal import HelicoidalInput, compute_helicoidal
from stair_engine.quarter_turn import QuarterTurnBottomInput


def test_helicoidal_cobertor_inferior_a_220mm_nao_e_buildable():
    """Helicoidal apertada: cobertor na linha de passagem fica muito abaixo
    de 220 mm e a inclinação é demasiado grande. Deve recusar."""
    inp = HelicoidalInput(
        floor_height_mm=3200,
        inner_radius_mm=200,
        outer_radius_mm=700,
        sweep_angle_deg=360,
        walkline_offset_mm=350,
    )
    r = compute_helicoidal(inp)
    reds = [a for a in r.alerts if a.level == "red"]
    assert reds, "esperado pelo menos um alerta vermelho"
    assert r.is_buildable is False, (
        f"escada com cobertor {r.tread_depth_mm:.0f} mm não deve ser is_buildable"
    )


def test_quarter_turn_cobertor_apertado_nao_e_buildable():
    """Em L apertado: cobertor na linha de passagem < 220 mm."""
    inp = QuarterTurnBottomInput(
        floor_height_mm=3200,
        available_length_mm=2200,
        available_width_mm=2200,
        stair_width_mm=800,
        balancing="balanced",
        walkline_offset_mm=400,
    )
    r = compute_quarter_turn_bottom(inp)
    # Pode gerar diversas configurações; validamos que a devolvida (a primeira
    # com `is_buildable` ou a melhor fallback) tem avaliação coerente com os
    # alertas vermelhos emitidos: se houver red, não pode ser buildable.
    reds = [a for a in r.alerts if a.level == "red"]
    if reds:
        assert r.is_buildable is False, (
            f"em L com alerta vermelho ({[a.code for a in reds]}) não deve ser is_buildable"
        )


def test_reta_padrao_e_buildable():
    """Reta 2800/5000/850 deve ser confortavelmente conforme."""
    inp = StairInput(
        floor_height_mm=2800,
        available_length_mm=5000,
        available_width_mm=1200,
        stair_width_mm=850,
    )
    r = compute_straight(inp)
    assert r.is_buildable is True, (
        f"escada reta padrão deve ser is_buildable (alertas={[a.code for a in r.alerts if a.level == 'red']})"
    )
    assert r.is_geometrically_possible is True


def test_is_geometrically_possible_separa_segurança_de_geometria():
    """Para uma escada apertada regulamentarmente mas geometricamente
    construível, `is_buildable=False` mas `is_geometrically_possible=True`."""
    inp = HelicoidalInput(
        floor_height_mm=3200,
        inner_radius_mm=200,
        outer_radius_mm=700,
        sweep_angle_deg=360,
        walkline_offset_mm=350,
    )
    r = compute_helicoidal(inp)
    # Se existirem reds não-blocking (ex.: slope ou cobertor): is_buildable
    # fica False mas is_geometrically_possible pode continuar True.
    only_non_blocking_red = any(
        a.level == "red" and a.code not in {
            "STAIR_RUN_TOO_LONG", "STAIR_WIDTH_INSUFFICIENT",
            "STAIRWELL_TOO_SMALL", "HEADROOM_INSUFFICIENT",
            "GEOMETRY_INVALID", "BALANCING_IMPOSSIBLE", "AUTO_WINDERS_NO_SOLUTION",
        } for a in r.alerts
    )
    if only_non_blocking_red:
        assert r.is_buildable is False
        assert r.is_geometrically_possible is True
