"""Moteur de calcul — escalier demi-tournant (180°).

Deux modes :
    - "straight": volée basse + palier intermédiaire (large 2x largeur escalier) + volée haute en sens inverse.
    - "balanced": volée basse + marches balancées à 180° (typiquement 5-9 winders) + volée haute en sens inverse.

En mode "auto", essaie 5→9 winders (180° nécessite plus de winders qu'un quart).
"""
from __future__ import annotations

import math
from typing import List, Literal, Optional, Union

from pydantic import Field, field_validator

from . import alerts as A
from .blondel import blondel_value, find_optimal_num_steps, optimal_giron_mm
from .models import Alert, StairInput, StairResult, TreadDetail
from .norms_fr import DTU_36_3_FR, StairNorms


class HalfTurnInput(StairInput):
    balancing: Literal["straight", "balanced"] = "balanced"
    landing_length_mm: Optional[float] = Field(default=None, gt=0, le=5000)
    num_winders: Union[int, Literal["auto"]] = "auto"
    walkline_offset_mm: float = Field(default=500, gt=0, le=2000)
    inner_radius_mm: float = Field(default=0, ge=0, le=1000)

    @field_validator("num_winders")
    @classmethod
    def _check(cls, v):
        if isinstance(v, str):
            if v != "auto":
                raise ValueError("num_winders doit être un int ou 'auto'")
            return v
        if not (4 <= v <= 12):
            raise ValueError("num_winders doit être entre 4 et 12 pour un demi-tournant")
        return v


def compute_half_turn(inp: HalfTurnInput, norms: StairNorms = DTU_36_3_FR) -> StairResult:
    if inp.balancing == "balanced" and inp.num_winders == "auto":
        return _auto_balanced_half(inp, norms)
    return _compute_half_single(inp, norms)


def _auto_balanced_half(base_inp, norms):
    candidates = [4, 5, 6, 7, 8, 9, 10, 11, 12]
    best = None
    best_red = float("inf")
    for n in candidates:
        trial = base_inp.model_copy(update={"num_winders": n})
        r = _compute_half_single(trial, norms)
        if r.is_buildable:
            r.alerts.insert(0, Alert(
                level="green", code="AUTO_WINDERS_SELECTED",
                message_fr=f"Répartition automatique : {n} marches balancées à 180°.",
                metric="num_winders", value=float(n),
            ))
            return r
        rc = sum(1 for a in r.alerts if a.level == "red")
        if rc < best_red:
            best_red = rc
            best = r
    if best is not None:
        best.alerts.insert(0, Alert(
            level="red", code="AUTO_WINDERS_NO_SOLUTION",
            message_fr="Aucune répartition (4-12 winders) ne satisfait les contraintes.",
        ))
    return best


def _compute_half_single(inp: HalfTurnInput, norms: StairNorms) -> StairResult:
    alerts_all: List[Alert] = []
    n_steps, h_mm, in_optimal = find_optimal_num_steps(inp.floor_height_mm, norms)
    if n_steps <= 0:
        return _dead("half_turn", "GEOMETRY_INVALID", "Hauteur invalide.")

    g = optimal_giron_mm(h_mm, norms)
    blondel = blondel_value(h_mm, g)

    if not in_optimal:
        alerts_all.append(Alert(
            level="orange", code="RISER_HEIGHT_NON_OPTIMAL",
            message_fr=f"Hauteur de marche {h_mm:.1f} mm hors plage optimale.",
            metric="riser_height_mm", value=h_mm,
        ))

    for fn, arg in [
        (A.check_blondel, blondel), (A.check_riser, h_mm),
        (A.check_tread, g), (A.check_stair_width, inp.stair_width_mm),
    ]:
        a = fn(arg, norms)
        if a:
            alerts_all.append(a)

    treads: List[TreadDetail] = []

    if inp.balancing == "straight":
        # split n_steps en deux volées séparées par un palier
        n_lower = n_steps // 2
        n_upper = n_steps - n_lower
        landing_l = inp.landing_length_mm or inp.stair_width_mm
        # Volée basse : n_lower risers → num_lower_treads = n_lower - 1
        for i in range(1, n_lower):
            treads.append(TreadDetail(
                index=i, type="straight",
                depth_walkline_mm=g, depth_inner_mm=g, depth_outer_mm=g,
                angle_deg=0.0, cumulative_height_mm=i * h_mm,
            ))
        # Palier intermédiaire (à hauteur n_lower * h)
        treads.append(TreadDetail(
            index=n_lower, type="straight",
            depth_walkline_mm=landing_l, depth_inner_mm=landing_l, depth_outer_mm=landing_l,
            angle_deg=180.0, cumulative_height_mm=n_lower * h_mm,
        ))
        # Volée haute : n_upper risers, num_upper_treads = n_upper - 1
        for j in range(1, n_upper):
            idx = n_lower + j
            treads.append(TreadDetail(
                index=idx, type="straight",
                depth_walkline_mm=g, depth_inner_mm=g, depth_outer_mm=g,
                angle_deg=0.0, cumulative_height_mm=(n_lower + j) * h_mm,
            ))
        num_turn_treads = 1
        lower_run = (n_lower - 1) * g
        upper_run = (n_upper - 1) * g
        # Emprise: max(lower_run, upper_run) + landing_l (aller-retour dans la longueur)
        footprint_length = max(lower_run, upper_run) + landing_l
        footprint_width = 2 * inp.stair_width_mm  # aller + retour
    else:
        num_winders = inp.num_winders if isinstance(inp.num_winders, int) else 6
        angle_per = math.pi / num_winders  # 180° réparti
        angle_deg = 180.0 / num_winders
        dw = inp.walkline_offset_mm * angle_per
        di = inp.inner_radius_mm * angle_per if inp.inner_radius_mm > 0 else 0.0
        do = inp.stair_width_mm * angle_per

        if dw < norms.winder_walkline_min_mm:
            alerts_all.append(Alert(
                level="red", code="BALANCING_WALKLINE_TOO_SMALL",
                message_fr=f"Giron ligne de foulée {dw:.0f} mm < minimum {norms.winder_walkline_min_mm:.0f} mm.",
                metric="depth_walkline_mm", value=dw, threshold=norms.winder_walkline_min_mm,
            ))
        if inp.inner_radius_mm > 0 and di < norms.winder_inner_min_mm:
            alerts_all.append(Alert(
                level="orange", code="BALANCING_INNER_TOO_SMALL",
                message_fr=f"Giron intérieur {di:.0f} mm < minimum {norms.winder_inner_min_mm:.0f} mm.",
                metric="depth_inner_mm", value=di,
            ))

        # Répartition : moitié risers en volée basse, num_winders au milieu, reste en haut
        remaining = n_steps - num_winders
        if remaining < 2:
            alerts_all.append(Alert(
                level="red", code="BALANCING_IMPOSSIBLE",
                message_fr=f"Trop de winders ({num_winders}) pour la hauteur.",
            ))
            remaining = max(0, remaining)
        n_lower = remaining // 2
        n_upper = remaining - n_lower
        # Volée basse : n_lower risers → n_lower treads (dernier tread aligné avec entrée du 180°)
        for i in range(1, n_lower + 1):
            treads.append(TreadDetail(
                index=i, type="straight",
                depth_walkline_mm=g, depth_inner_mm=g, depth_outer_mm=g,
                angle_deg=0.0, cumulative_height_mm=i * h_mm,
            ))
        for j in range(1, num_winders + 1):
            treads.append(TreadDetail(
                index=n_lower + j, type="winder",
                depth_walkline_mm=round(dw, 2), depth_inner_mm=round(di, 2),
                depth_outer_mm=round(do, 2), angle_deg=round(angle_deg, 2),
                cumulative_height_mm=(n_lower + j) * h_mm,
            ))
        # Volée haute : n_upper risers → n_upper - 1 treads (dernier riser débouche sur sol haut)
        for k in range(1, n_upper):
            idx = n_lower + num_winders + k
            treads.append(TreadDetail(
                index=idx, type="straight",
                depth_walkline_mm=g, depth_inner_mm=g, depth_outer_mm=g,
                angle_deg=0.0, cumulative_height_mm=(n_lower + num_winders + k) * h_mm,
            ))
        num_turn_treads = num_winders
        lower_run = n_lower * g
        upper_run = max(0, n_upper - 1) * g
        # Emprise: le 180° occupe un rectangle stair_width * (2*stair_width)
        # footprint_length = max(lower_run + stair_width, upper_run + stair_width)
        # Simpler: footprint_length = max(lower_run, upper_run) + stair_width (rayon du demi-tournant)
        footprint_length = max(lower_run, upper_run) + inp.stair_width_mm
        footprint_width = 2 * inp.stair_width_mm

    if footprint_length > inp.available_length_mm:
        alerts_all.append(Alert(
            level="red", code="STAIR_RUN_TOO_LONG",
            message_fr=f"Reculement nécessaire {footprint_length:.0f} mm > disponible {inp.available_length_mm:.0f} mm.",
            metric="stair_run_mm", value=footprint_length, threshold=inp.available_length_mm,
        ))
    if footprint_width > inp.available_width_mm:
        alerts_all.append(Alert(
            level="red", code="STAIR_WIDTH_INSUFFICIENT",
            message_fr=f"Largeur nécessaire pour le demi-tournant {footprint_width:.0f} mm > disponible {inp.available_width_mm:.0f} mm.",
            metric="available_width_mm", value=footprint_width, threshold=inp.available_width_mm,
        ))

    total_horiz = footprint_length
    slope_deg = math.degrees(math.atan2(inp.floor_height_mm, total_horiz)) if total_horiz > 0 else 90.0
    sa = A.check_slope(slope_deg, norms)
    if sa:
        alerts_all.append(sa)

    # Échappée simplifiée : sur la volée haute (les marches qui reviennent vers le sol haut)
    headroom_mm = float("inf")
    if inp.ceiling_height_mm is not None and inp.stairwell_length_mm is not None:
        # On checke chaque marche cumulée à sa hauteur y_i
        for t in treads:
            y_i = t.cumulative_height_mm
            # Approximation : dalle au-dessus si y_i < ceiling_height et hors trémie
            # Trémie assumée couvrir toute la volée haute
            if t.type == "winder":
                # winders sous le palier de trémie (assumés dans l'opening)
                continue
            head = inp.ceiling_height_mm - y_i
            if head < headroom_mm:
                headroom_mm = head
        if headroom_mm != float("inf"):
            ha = A.check_headroom(headroom_mm, None, norms)
            if ha:
                alerts_all.append(ha)

    is_buildable = A.compute_is_buildable(alerts_all)

    oa = A.check_optimal(blondel, slope_deg, norms)
    if oa:
        alerts_all.append(oa)
    alerts_all = A.summarize(alerts_all)

    stair_length = math.sqrt(inp.floor_height_mm ** 2 + total_horiz ** 2)

    return StairResult(
        stair_type=f"half_turn_{inp.balancing}",
        num_steps=n_steps, num_treads=len(treads),
        riser_height_mm=round(h_mm, 2), tread_depth_mm=round(g, 2),
        blondel_value_mm=round(blondel, 2), slope_deg=round(slope_deg, 2),
        stair_run_mm=round(total_horiz, 2), stair_length_mm=round(stair_length, 2),
        headroom_mm=round(headroom_mm, 2) if headroom_mm != float("inf") else -1,
        required_stairwell_mm={
            "min_length_mm": round(footprint_length, 2), "min_width_mm": round(footprint_width, 2),
            "turn_footprint_length_mm": round(inp.stair_width_mm, 2),
            "turn_footprint_width_mm": round(2 * inp.stair_width_mm, 2),
        },
        steps_per_flight=[
            n_lower, num_turn_treads if inp.balancing == "balanced" else 1,
            max(0, n_upper - (1 if inp.balancing == "balanced" else 1)),
        ],
        treads=treads, alerts=alerts_all, is_buildable=is_buildable,
    )


def _dead(stair_type, code, msg):
    return StairResult(
        stair_type=stair_type, num_steps=0, num_treads=0,
        riser_height_mm=0, tread_depth_mm=0, blondel_value_mm=0, slope_deg=0,
        stair_run_mm=0, stair_length_mm=0, headroom_mm=0,
        required_stairwell_mm={}, steps_per_flight=[], treads=[],
        alerts=[Alert(level="red", code=code, message_fr=msg)],
        is_buildable=False,
    )
