"""Moteur de calcul — escalier hélicoïdal (colimaçon)."""
from __future__ import annotations

import math
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from . import alerts as A
from .blondel import blondel_value, find_optimal_num_steps
from .models import Alert, StairResult, TreadDetail
from .norms_fr import DTU_36_3_FR, StairNorms


class HelicoidalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floor_height_mm: float = Field(..., gt=0, le=8000)
    inner_radius_mm: float = Field(..., gt=0, le=2000)
    outer_radius_mm: float = Field(..., gt=100, le=3000)
    sweep_angle_deg: float = Field(default=360, gt=0, le=1440)
    direction: Literal["cw", "ccw"] = "cw"
    walkline_offset_mm: float = Field(default=500, gt=0, le=2000)
    slab_thickness_mm: float = 200
    ceiling_height_mm: Optional[float] = Field(default=None, gt=0, le=8000)
    tread_thickness_mm: float = 30
    has_risers: bool = True


class HelicoidalTreadDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int
    type: str = "helicoidal_winder"
    start_angle_deg: float
    end_angle_deg: float
    inner_radius_mm: float
    outer_radius_mm: float
    depth_walkline_mm: float
    depth_inner_mm: float
    depth_outer_mm: float
    riser_bottom_mm: float
    riser_top_mm: float


def compute_helicoidal(inp: HelicoidalInput, norms: StairNorms = DTU_36_3_FR) -> StairResult:
    alerts_all: List[Alert] = []

    if inp.outer_radius_mm <= inp.inner_radius_mm + 300:
        alerts_all.append(Alert(
            level="red", code="STAIR_WIDTH_TOO_SMALL",
            message_fr=f'Largura da escada {inp.outer_radius_mm - inp.inner_radius_mm:.0f} mm < 300 mm minimum.',
        ))

    stair_width_mm = inp.outer_radius_mm - inp.inner_radius_mm

    n_steps, h_mm, in_optimal = find_optimal_num_steps(inp.floor_height_mm, norms)
    if n_steps <= 0:
        return _dead("Altura inválida.")

    angle_per_step_deg = inp.sweep_angle_deg / n_steps
    angle_per_step_rad = math.radians(angle_per_step_deg)

    walkline_radius = min(
        inp.inner_radius_mm + inp.walkline_offset_mm,
        inp.outer_radius_mm - 30,
    )

    tread_walkline = walkline_radius * angle_per_step_rad
    tread_inner = inp.inner_radius_mm * angle_per_step_rad
    tread_outer = inp.outer_radius_mm * angle_per_step_rad

    blondel = blondel_value(h_mm, tread_walkline)

    # Alertes spécifiques hélicoïdal
    if tread_inner < 100:
        alerts_all.append(Alert(
            level="red", code="HELICOIDAL_INNER_TREAD_TOO_SMALL",
            message_fr=f'Cobertor interior {tread_inner:.0f} mm < 100 mm mínimo. Aumente o raio do núcleo central.',
            metric="tread_inner_mm", value=tread_inner, threshold=100,
        ))
    if tread_walkline < 220:
        alerts_all.append(Alert(
            level="red", code="HELICOIDAL_WALKLINE_TREAD_TOO_SMALL",
            message_fr=f'Cobertor na linha de passo {tread_walkline:.0f} mm < 220 mm minimum absolu.',
            metric="tread_walkline_mm", value=tread_walkline, threshold=220,
        ))
    elif tread_walkline < 240:
        alerts_all.append(Alert(
            level="orange", code="HELICOIDAL_WALKLINE_TREAD_TOO_SMALL",
            message_fr=f'Cobertor na linha de passo {tread_walkline:.0f} mm < 240 mm confort DTU.',
            metric="tread_walkline_mm", value=tread_walkline, threshold=240,
        ))
    elif 250 <= tread_walkline <= 300:
        alerts_all.append(Alert(
            level="green", code="HELICOIDAL_WALKLINE_TREAD_OPTIMAL",
            message_fr=f'Cobertor na linha de passo {tread_walkline:.0f} mm : confort optimal.',
        ))

    # Autres checks DTU
    if not in_optimal:
        alerts_all.append(Alert(
            level="orange", code="RISER_HEIGHT_NON_OPTIMAL",
            message_fr=f'Altura do espelho {h_mm:.1f} mm fora do intervalo ótimo.',
        ))
    ra = A.check_riser(h_mm, norms)
    if ra:
        alerts_all.append(ra)

    # Échappée hélicoïdal (uniquement si tour complet ou plus)
    headroom_mm = float("inf")
    if inp.ceiling_height_mm and inp.sweep_angle_deg >= 360:
        # Hauteur montée en un tour complet
        h_per_turn = h_mm * (360.0 / inp.sweep_angle_deg) * n_steps / (n_steps)  # = h_mm * (n_steps * 360/sweep) / n_steps
        # Plus simple: hauteur montée par tour = h_mm * (360 / angle_per_step_deg)
        steps_per_turn = 360.0 / angle_per_step_deg
        height_per_turn = h_mm * steps_per_turn
        # Échappée théorique = hauteur par tour - épaisseur de marche - marge sous dalle
        headroom_mm = height_per_turn - inp.tread_thickness_mm
        if headroom_mm < norms.headroom_min_mm:
            alerts_all.append(Alert(
                level="red", code="HELICOIDAL_HEADROOM_INSUFFICIENT",
                message_fr=f'Altura livre {headroom_mm:.0f} mm entre voltas < 1900 mm (regras de boa prática).',
                metric="headroom_mm", value=headroom_mm, threshold=norms.headroom_min_mm,
            ))

    # Génération des treads
    treads: List[TreadDetail] = []
    sign = 1 if inp.direction == "cw" else -1
    for i in range(1, n_steps + 1):
        a_start = sign * (i - 1) * angle_per_step_deg
        a_end = sign * i * angle_per_step_deg
        treads.append(TreadDetail(
            index=i, type="winder",
            depth_walkline_mm=round(tread_walkline, 2),
            depth_inner_mm=round(tread_inner, 2),
            depth_outer_mm=round(tread_outer, 2),
            angle_deg=round(angle_per_step_deg, 2),
            cumulative_height_mm=round(i * h_mm, 2),
        ))

    is_buildable = A.compute_is_buildable(alerts_all)
    is_geometrically_possible = A.compute_is_geometrically_possible(alerts_all)

    slope_deg = math.degrees(math.atan2(inp.floor_height_mm, 2 * math.pi * walkline_radius * inp.sweep_angle_deg / 360))
    if not any(a.code == "SLOPE_TOO_STEEP" for a in alerts_all):
        sa = A.check_slope(slope_deg, norms)
        if sa:
            alerts_all.append(sa)

    alerts_all = A.summarize(alerts_all)

    return StairResult(
        stair_type=f"helicoidal_{int(inp.sweep_angle_deg)}",
        num_steps=n_steps,
        num_treads=n_steps,
        riser_height_mm=round(h_mm, 2),
        tread_depth_mm=round(tread_walkline, 2),
        blondel_value_mm=round(blondel, 2),
        slope_deg=round(slope_deg, 2),
        stair_run_mm=round(2 * inp.outer_radius_mm, 2),
        stair_length_mm=round(math.sqrt(inp.floor_height_mm ** 2 + (2 * math.pi * walkline_radius * inp.sweep_angle_deg / 360) ** 2), 2),
        headroom_mm=round(headroom_mm, 2) if headroom_mm != float("inf") else -1,
        required_stairwell_mm={
            "min_length_mm": round(2 * inp.outer_radius_mm, 2),
            "min_width_mm": round(2 * inp.outer_radius_mm, 2),
            "diameter_mm": round(2 * inp.outer_radius_mm, 2),
            "inner_diameter_mm": round(2 * inp.inner_radius_mm, 2),
        },
        steps_per_flight=[n_steps],
        treads=treads,
        alerts=alerts_all,
        is_buildable=is_buildable,
        is_geometrically_possible=is_geometrically_possible,
    )


def _dead(msg: str) -> StairResult:
    return StairResult(
        stair_type="helicoidal", num_steps=0, num_treads=0,
        riser_height_mm=0, tread_depth_mm=0, blondel_value_mm=0, slope_deg=0,
        stair_run_mm=0, stair_length_mm=0, headroom_mm=0,
        required_stairwell_mm={}, steps_per_flight=[], treads=[],
        alerts=[Alert(level="red", code="GEOMETRY_INVALID", message_fr=msg)],
        is_buildable=False,
        is_geometrically_possible=False,
    )
