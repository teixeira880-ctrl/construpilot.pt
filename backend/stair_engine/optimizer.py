"""Moteur d'optimisation — propose N solutions triées par pertinence.

Score global = somme pondérée de :
  - confort (Blondel/pente/giron proches des optimums)
  - encombrement (footprint / available)
  - faisabilité (table statique par type)
  - esthétique (table statique par type)
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .helicoidal import HelicoidalInput, compute_helicoidal
from .half_turn import HalfTurnInput, compute_half_turn
from .models import QuarterTurnBottomInput, StairInput, StairResult
from .quarter_turn import compute_quarter_turn_bottom
from .quarter_turn_top import compute_quarter_turn_top
from .straight import compute_straight


StairTypeName = Literal[
    "straight", "quarter_turn_bottom", "quarter_turn_top", "half_turn", "helicoidal"
]

DEFAULT_TYPES: List[str] = list(StairTypeName.__args__)  # type: ignore[attr-defined]

DEFAULT_WEIGHTS = {"confort": 0.35, "encombrement": 0.25, "faisabilite": 0.20, "esthetique": 0.20}

# Tables statiques
FAISABILITE_SCORE = {
    "straight": 100, "quarter_turn_bottom": 80, "quarter_turn_top": 80,
    "half_turn": 70, "helicoidal": 50,
}
ESTHETIQUE_SCORE = {
    "straight": 60, "quarter_turn_bottom": 75, "quarter_turn_top": 75,
    "half_turn": 70, "helicoidal": 90,
}


class OptimizeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floor_height_mm: float = Field(..., gt=0, le=8000)
    available_length_mm: float = Field(..., gt=0, le=30000)
    available_width_mm: float = Field(..., gt=0, le=30000)
    stair_width_mm: float = Field(default=900, gt=0, le=5000)
    stairwell_length_mm: Optional[float] = None
    stairwell_width_mm: Optional[float] = None
    slab_thickness_mm: float = 200
    ceiling_height_mm: Optional[float] = None
    tread_thickness_mm: float = 30
    has_risers: bool = True
    types_to_test: Optional[List[str]] = None
    max_solutions: int = Field(default=5, ge=1, le=20)
    weights: Optional[Dict[str, float]] = None


class ScoreBreakdown(BaseModel):
    confort: float
    encombrement: float
    faisabilite: float
    esthetique: float


class OptimizeSolution(BaseModel):
    rank: int
    type: str
    variant: str
    score_global: float
    scores: ScoreBreakdown
    result: StairResult


class OptimizeExcluded(BaseModel):
    type: str
    variant: str
    reason: str


class OptimizeResult(BaseModel):
    solutions: List[OptimizeSolution]
    excluded: List[OptimizeExcluded]
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _score_confort(r: StairResult) -> float:
    """Gaussienne autour de Blondel=630, slope=30°, giron=280."""
    # Blondel: idéal 630, sigma 25
    d_blondel = (r.blondel_value_mm - 630) / 25
    score_blondel = 100 * math.exp(-0.5 * d_blondel * d_blondel)
    d_slope = (r.slope_deg - 30) / 5
    score_slope = 100 * math.exp(-0.5 * d_slope * d_slope)
    d_giron = (r.tread_depth_mm - 280) / 30
    score_giron = 100 * math.exp(-0.5 * d_giron * d_giron)
    return (score_blondel + score_slope + score_giron) / 3


def _score_encombrement(r: StairResult, inp: OptimizeInput) -> float:
    avail = inp.available_length_mm * inp.available_width_mm
    used_l = r.stair_run_mm
    # largeur : selon type
    turn_w = r.required_stairwell_mm.get("turn_footprint_width_mm", inp.stair_width_mm)
    used_w = max(inp.stair_width_mm, turn_w or inp.stair_width_mm)
    used = used_l * used_w
    if avail <= 0:
        return 0
    ratio = 1 - min(1, used / avail)
    return max(0, min(100, ratio * 100))


def _score_faisabilite(stype: str) -> float:
    base_key = stype
    for k in FAISABILITE_SCORE:
        if stype.startswith(k):
            base_key = k
            break
    return FAISABILITE_SCORE.get(base_key, 60)


def _score_esthetique(stype: str) -> float:
    for k in ESTHETIQUE_SCORE:
        if stype.startswith(k):
            return ESTHETIQUE_SCORE[k]
    return 70


def compute_optimize(inp: OptimizeInput) -> OptimizeResult:
    types_to_test = inp.types_to_test or DEFAULT_TYPES
    weights = {**DEFAULT_WEIGHTS, **(inp.weights or {})}
    solutions: List[OptimizeSolution] = []
    excluded: List[OptimizeExcluded] = []

    common = dict(
        floor_height_mm=inp.floor_height_mm,
        available_length_mm=inp.available_length_mm,
        available_width_mm=inp.available_width_mm,
        stair_width_mm=inp.stair_width_mm,
        stairwell_length_mm=inp.stairwell_length_mm,
        stairwell_width_mm=inp.stairwell_width_mm,
        slab_thickness_mm=inp.slab_thickness_mm,
        ceiling_height_mm=inp.ceiling_height_mm,
        tread_thickness_mm=inp.tread_thickness_mm,
        has_risers=inp.has_risers,
    )

    candidates: List[tuple[str, str, Any]] = []
    if "straight" in types_to_test:
        candidates.append(("straight", "default", lambda: compute_straight(StairInput(**common))))
    if "quarter_turn_bottom" in types_to_test:
        for bal in ["balanced", "straight"]:
            candidates.append(
                (f"quarter_turn_bottom", bal,
                 lambda b=bal: compute_quarter_turn_bottom(QuarterTurnBottomInput(**common, balancing=b)))
            )
    if "quarter_turn_top" in types_to_test:
        for bal in ["balanced", "straight"]:
            candidates.append(
                (f"quarter_turn_top", bal,
                 lambda b=bal: compute_quarter_turn_top(QuarterTurnBottomInput(**common, balancing=b)))
            )
    if "half_turn" in types_to_test:
        for bal in ["balanced", "straight"]:
            candidates.append(
                ("half_turn", bal,
                 lambda b=bal: compute_half_turn(HalfTurnInput(**common, balancing=b)))
            )
    if "helicoidal" in types_to_test:
        # Configurations plausibles : sweep 270 / 360 / 450
        # outer_radius = min(available_length, available_width) / 2 (l'hélicoïdal tient dans un cercle)
        outer = min(inp.available_length_mm, inp.available_width_mm) / 2
        # Inner : 150mm par défaut (fût standard). Si outer trop petit, échec attendu (alerte).
        inner = 150
        for sweep in [360, 270, 450]:
            candidates.append(
                (f"helicoidal", f"sweep_{sweep}",
                 lambda sw=sweep, o=outer, i=inner: compute_helicoidal(HelicoidalInput(
                    floor_height_mm=inp.floor_height_mm,
                    inner_radius_mm=i, outer_radius_mm=o,
                    sweep_angle_deg=sw,
                    walkline_offset_mm=500,
                    slab_thickness_mm=inp.slab_thickness_mm,
                    ceiling_height_mm=inp.ceiling_height_mm,
                    tread_thickness_mm=inp.tread_thickness_mm,
                    has_risers=inp.has_risers,
                )))
            )

    for type_name, variant, fn in candidates:
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            excluded.append(OptimizeExcluded(
                type=type_name, variant=variant, reason=f"Erreur calcul: {str(e)[:100]}"
            ))
            continue
        if not r.is_buildable:
            reason = next(
                (a.message_fr for a in r.alerts if a.level == "red"),
                "Non constructible"
            )
            excluded.append(OptimizeExcluded(type=type_name, variant=variant, reason=reason))
            continue

        conf = _score_confort(r)
        enc = _score_encombrement(r, inp)
        fais = _score_faisabilite(r.stair_type)
        esth = _score_esthetique(r.stair_type)
        gl = (
            conf * weights["confort"] +
            enc * weights["encombrement"] +
            fais * weights["faisabilite"] +
            esth * weights["esthetique"]
        )
        solutions.append(OptimizeSolution(
            rank=0, type=type_name, variant=variant,
            score_global=round(gl, 2),
            scores=ScoreBreakdown(
                confort=round(conf, 2), encombrement=round(enc, 2),
                faisabilite=round(fais, 2), esthetique=round(esth, 2),
            ),
            result=r,
        ))

    solutions.sort(key=lambda s: s.score_global, reverse=True)
    solutions = solutions[: inp.max_solutions]
    for i, s in enumerate(solutions):
        s.rank = i + 1

    return OptimizeResult(solutions=solutions, excluded=excluded)
