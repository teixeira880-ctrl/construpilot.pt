"""Fórmula Blondel + ergonomia.

Blondel: 2h + g ∈ [60, 64] cm (ideal 63-64) — relaciona altura do espelho (h)
e profundidade do cobertor (g) de um degrau para passo humano confortável.

Conforto adicional:
  - h + g ∈ [43, 47] cm → regra "segurança" (anti-queda)
  - h × g ∈ [400, 500] cm² → regra "comodidade" (menos usada)
  - inclinação ideal 30° (confortável). >35° considera-se "íngreme".
"""
from __future__ import annotations

import math
from dataclasses import dataclass


BLONDEL_MIN = 60.0  # cm
BLONDEL_MAX = 64.0  # cm
BLONDEL_IDEAL = 63.0  # cm

INCLINATION_IDEAL_DEG = 30.0
INCLINATION_MAX_HAB_DEG = 36.0  # habitação
INCLINATION_MAX_PUB_DEG = 32.0  # público / evacuação


@dataclass
class BlondelResult:
    h_cm: float            # altura espelho
    g_cm: float            # profundidade cobertor
    blondel: float         # 2h + g
    inclination_deg: float
    blondel_ok: bool
    comfort_score: float   # 0..10


def blondel_optimal(altura_total_cm: float, num_degraus: int) -> BlondelResult:
    """Dado altura total e nº de degraus, devolve dimensões + conforto."""
    if num_degraus <= 0:
        raise ValueError("num_degraus deve ser > 0")
    h = altura_total_cm / num_degraus
    # g ideal pela Blondel: 2h + g = 63  ⇒  g = 63 - 2h
    g = BLONDEL_IDEAL - 2 * h
    if g < 24:
        g = 24.0  # mínimo prático (RGEU)
    if g > 32:
        g = 32.0  # máximo prático
    return _compute(h, g)


def blondel_check(h_cm: float, g_cm: float) -> BlondelResult:
    """Verifica dimensões fornecidas pelo utilizador."""
    return _compute(h_cm, g_cm)


def _compute(h: float, g: float) -> BlondelResult:
    blondel = 2 * h + g
    incl = math.degrees(math.atan(h / g)) if g > 0 else 90.0
    blondel_ok = BLONDEL_MIN <= blondel <= BLONDEL_MAX
    # Conforto: penaliza desvio da Blondel ideal + inclinação >32°
    blondel_pen = min(1.0, abs(blondel - BLONDEL_IDEAL) / 6.0)
    incl_pen = max(0.0, (incl - 30.0) / 10.0)
    score = max(0.0, 10.0 - 4 * blondel_pen - 3 * min(1.0, incl_pen))
    return BlondelResult(
        h_cm=round(h, 2), g_cm=round(g, 2),
        blondel=round(blondel, 2), inclination_deg=round(incl, 1),
        blondel_ok=blondel_ok, comfort_score=round(score, 1),
    )


def suggest_num_steps(altura_total_cm: float) -> int:
    """Nº de degraus que minimiza desvio Blondel (h entre 16-18cm típico)."""
    best = None
    best_score = -1.0
    for n in range(max(3, int(altura_total_cm // 20)), int(altura_total_cm // 14) + 1):
        r = blondel_optimal(altura_total_cm, n)
        if r.comfort_score > best_score:
            best_score = r.comfort_score
            best = n
    return best or max(3, round(altura_total_cm / 17))
