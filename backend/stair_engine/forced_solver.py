"""Solveur "forcé" — trouve TOUJOURS une solution géométrique, même hors normes DTU.

Utilisé par l'assistant IA quand `optimize_stair` ne renvoie aucune solution
`is_buildable=true` (i.e. l'espace est trop contraint pour respecter la norme).

Le solveur relâche progressivement les contraintes :
- pente jusqu'à 55° (au lieu de 40°)
- giron jusqu'à 180 mm (au lieu de 220 mm mini DTU)
- hauteur de marche jusqu'à 220 mm (au lieu de 195 mm max acceptable)
- échappée jusqu'à 1700 mm (au lieu de 1900 mm mini)
- winders jusqu'à 12 pour QT bas balancé

Retourne un `StairResult` valide avec **une alerte rouge dédiée
`NON_CONFORMING_FORCED_SOLUTION`** listant les seuils enfreints.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from .models import Alert, StairResult, TreadDetail


# Limites du solveur forcé (au-delà : géométriquement impossible, on renvoie tout de même)
FORCED_RISER_MIN = 140.0
FORCED_RISER_MAX = 220.0
FORCED_GIRON_MIN = 180.0
FORCED_GIRON_MAX = 320.0
FORCED_SLOPE_MAX_DEG = 55.0
FORCED_HEADROOM_MIN = 1700.0

# Seuils DTU pour signaler les infractions (lecture seule)
DTU_RISER_MAX = 195.0
DTU_GIRON_MIN = 220.0
DTU_SLOPE_MAX = 40.0
DTU_HEADROOM_MIN = 1900.0
DTU_BLONDEL_MIN = 580.0
DTU_BLONDEL_MAX = 660.0


class ForceSolutionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floor_height_mm: float = Field(..., gt=0, le=8000)
    available_length_mm: float = Field(..., gt=0, le=30000)
    available_width_mm: float = Field(..., gt=0, le=30000)
    stair_width_mm: float = Field(default=900, gt=0, le=5000)
    stairwell_length_mm: Optional[float] = Field(default=None, gt=0, le=30000)
    stairwell_width_mm: Optional[float] = Field(default=None, gt=0, le=30000)
    ceiling_height_mm: Optional[float] = Field(default=None, gt=0, le=8000)
    slab_thickness_mm: float = 200
    tread_thickness_mm: float = 30


def _select_num_steps_forced(floor_height_mm: float) -> Tuple[int, float]:
    """Choisit n_steps de sorte que h ∈ [FORCED_RISER_MIN, FORCED_RISER_MAX].

    Priorise h le plus proche de 175 (DTU idéal). Fallback : n=max qui garde h > 100.
    """
    best_n = 0
    best_dist = float("inf")
    for n in range(1, 200):
        h = floor_height_mm / n
        if FORCED_RISER_MIN <= h <= FORCED_RISER_MAX:
            d = abs(h - 175.0)
            if d < best_dist:
                best_dist = d
                best_n = n
    if best_n:
        return best_n, floor_height_mm / best_n
    # Fallback : plus grand n qui donne h > 100
    for n in range(200, 0, -1):
        h = floor_height_mm / n
        if h >= 100.0:
            return n, h
    return 1, floor_height_mm


def _build_forced_straight(inp: ForceSolutionInput) -> Tuple[StairResult, List[str]]:
    """Escalier droit forcé — utilise tout le recul dispo, giron min 180 mm.

    Retourne (result, liste_infractions_texte).
    """
    infractions: List[str] = []

    n_steps, h_mm = _select_num_steps_forced(inp.floor_height_mm)
    num_treads = max(1, n_steps - 1)

    # Choix du giron : on veut n_treads * g <= available_length et g >= FORCED_GIRON_MIN
    # On maximise g dans [FORCED_GIRON_MIN, FORCED_GIRON_MAX] tout en tenant dans available_length.
    g_from_space = inp.available_length_mm / num_treads
    g_mm = max(FORCED_GIRON_MIN, min(FORCED_GIRON_MAX, g_from_space))

    # Si le giron nécessaire est < FORCED_GIRON_MIN → on essaie de réduire num_treads
    # en augmentant h (jusqu'à FORCED_RISER_MAX)
    while (inp.available_length_mm / num_treads) < FORCED_GIRON_MIN and num_treads > 1:
        num_treads -= 1
        n_steps -= 1
        h_mm = inp.floor_height_mm / n_steps
        if h_mm > FORCED_RISER_MAX:
            # On dépasse le max forcé → on stoppe et on garde cette valeur (hors normes tout)
            break
        g_from_space = inp.available_length_mm / num_treads
        g_mm = max(FORCED_GIRON_MIN, min(FORCED_GIRON_MAX, g_from_space))

    # Géométrie finale
    stair_run = num_treads * g_mm
    stair_length = math.sqrt(inp.floor_height_mm ** 2 + stair_run ** 2)
    slope_deg = math.degrees(math.atan2(inp.floor_height_mm, stair_run)) if stair_run > 0 else 90.0
    blondel = 2.0 * h_mm + g_mm

    # Échappée simplifiée
    headroom = -1.0
    if inp.ceiling_height_mm is not None and inp.stairwell_length_mm is not None:
        # Approximation : trémie collée en haut, échappée = ceiling - h * k
        # où k = num_treads - stairwell_length / g
        # Arête de trémie mesurée sur la ligne des nez (pas seulement aux nez de marche).
        from .straight import edge_headroom
        x_start = stair_run - inp.stairwell_length_mm
        head, _ = edge_headroom(inp.ceiling_height_mm, x_start, h_mm, g_mm, stair_run)
        headroom = head if head is not None else inp.ceiling_height_mm  # aucune marche sous la dalle
    elif inp.ceiling_height_mm is not None:
        headroom = inp.ceiling_height_mm - h_mm  # première marche sous la dalle

    # Recensement des infractions DTU
    if h_mm > DTU_RISER_MAX:
        infractions.append(f'altura do degrau {h_mm:.0f} mm > {DTU_RISER_MAX:.0f} mm max DTU')
    if g_mm < DTU_GIRON_MIN:
        infractions.append(f"giron {g_mm:.0f} mm < {DTU_GIRON_MIN:.0f} mm min DTU")
    if slope_deg > DTU_SLOPE_MAX:
        infractions.append(f"pente {slope_deg:.1f}° > {DTU_SLOPE_MAX:.0f}° max DTU")
    if not (DTU_BLONDEL_MIN <= blondel <= DTU_BLONDEL_MAX):
        infractions.append(f"Blondel 2h+g={blondel:.0f} mm hors range DTU [580–660]")
    if headroom > 0 and headroom < DTU_HEADROOM_MIN:
        infractions.append(f"échappée {headroom:.0f} mm < {DTU_HEADROOM_MIN:.0f} mm min DTU")
    if stair_run > inp.available_length_mm + 1:  # tolérance 1mm
        infractions.append(
            f'desenvolvimento necessário {stair_run:.0f} mm > disponível {inp.available_length_mm:.0f} mm (a escada excede — considerar um quarto de volta ou patamar)'
        )

    alerts: List[Alert] = []
    if infractions:
        alerts.append(Alert(
            level="red",
            code="NON_CONFORMING_FORCED_SOLUTION",
            message_fr=(
                "Solução fora das regras de boa prática. Compromissos aceites: "
                + " ; ".join(infractions)
                + ". A validar por um gabinete de projeto consoante o uso (acesso técnico, cave, etc.)."
            ),
        ))
    if slope_deg > FORCED_SLOPE_MAX_DEG:
        alerts.append(Alert(
            level="red",
            code="SLOPE_DANGEROUS_EXTREME",
            message_fr=(
                f'Inclinação extrema {slope_deg:.1f}° > {FORCED_SLOPE_MAX_DEG:.0f}° — apenas uso tipo escada de sótão/escadote.'
            ),
            metric="slope_deg", value=slope_deg, threshold=FORCED_SLOPE_MAX_DEG,
        ))
    if headroom > 0 and headroom < FORCED_HEADROOM_MIN:
        alerts.append(Alert(
            level="red",
            code="HEADROOM_EXTREME",
            message_fr=(
                f'Altura livre {headroom:.0f} mm < {FORCED_HEADROOM_MIN:.0f} mm — passagem de pé impossível.'
            ),
            metric="headroom_mm", value=headroom, threshold=FORCED_HEADROOM_MIN,
        ))

    treads: List[TreadDetail] = []
    for i in range(1, num_treads + 1):
        treads.append(TreadDetail(
            index=i,
            type="straight",
            depth_walkline_mm=g_mm,
            depth_inner_mm=g_mm,
            depth_outer_mm=g_mm,
            angle_deg=0.0,
            cumulative_height_mm=i * h_mm,
        ))

    return StairResult(
        stair_type="straight_forced",
        num_steps=n_steps,
        num_treads=num_treads,
        riser_height_mm=round(h_mm, 2),
        tread_depth_mm=round(g_mm, 2),
        blondel_value_mm=round(blondel, 2),
        slope_deg=round(slope_deg, 2),
        stair_run_mm=round(stair_run, 2),
        stair_length_mm=round(stair_length, 2),
        headroom_mm=round(headroom, 2) if headroom > 0 else -1,
        required_stairwell_mm={"min_length_mm": round(stair_run, 2), "min_width_mm": inp.stair_width_mm},
        steps_per_flight=[n_steps],
        treads=treads,
        alerts=alerts,
        is_buildable=True,
    ), infractions


def compute_forced_solution(inp: ForceSolutionInput) -> Dict[str, Any]:
    """Point d'entrée du solveur forcé.

    Actuellement retourne toujours une solution "escalier droit forcé"
    (compromis maximal). Étendable en Phase 5 avec un solveur QT/DT forcé.
    """
    result, infractions = _build_forced_straight(inp)
    return {
        "stair_result": result.model_dump(mode="json"),
        "type": "straight_forced",
        "infractions_dtu": infractions,
        "is_buildable": result.is_buildable,
    }
