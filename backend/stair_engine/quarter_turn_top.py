"""Moteur de calcul — escalier quart tournant haut (arrivée tournante).

Volée droite basse + quart tournant en haut (palier rectangulaire OU marches balancées).
Symétrique du quart tournant bas.
"""
from __future__ import annotations

import math
from typing import List

from . import alerts as A
from .blondel import blondel_value, find_optimal_num_steps, optimal_giron_mm
from .models import Alert, QuarterTurnBottomInput, StairResult, TreadDetail
from .norms_fr import DTU_36_3_FR, StairNorms


# QT haut réutilise le même modèle d'entrée que QT bas
QuarterTurnTopInput = QuarterTurnBottomInput


def compute_quarter_turn_top(
    inp: QuarterTurnBottomInput, norms: StairNorms = DTU_36_3_FR
) -> StairResult:
    """Calcule un escalier quart tournant haut.

    Modes:
        - "straight": volée droite basse + palier rectangulaire au sommet.
        - "balanced": volée droite basse + marches balancées en haut.

    En mode "auto", essaie 3→9 winders et retient la première config buildable.
    """
    if inp.balancing == "balanced" and inp.num_winders == "auto":
        return _auto_balanced_top(inp, norms)
    return _compute_qt_top_single(inp, norms)


def _auto_balanced_top(base_inp, norms):
    candidates = [3, 4, 5, 6, 7, 8, 9]
    best = None
    best_red = float("inf")
    for n in candidates:
        trial = base_inp.model_copy(update={"num_winders": n})
        r = _compute_qt_top_single(trial, norms)
        if r.is_buildable:
            r.alerts.insert(0, Alert(
                level="green", code="AUTO_WINDERS_SELECTED",
                message_fr=f'Distribuição automática: {n} degraus em leque.',
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
            message_fr="Nenhuma distribuição de degraus em leque (3-9) satisfaz as restrições."
        ))
    return best


def _compute_qt_top_single(inp: QuarterTurnBottomInput, norms: StairNorms) -> StairResult:
    alerts_all: List[Alert] = []
    n_steps, h_mm, in_optimal = find_optimal_num_steps(inp.floor_height_mm, norms)
    if n_steps <= 0:
        return _dead("quarter_turn_top", "GEOMETRY_INVALID", "Altura inválida.")

    g_straight = optimal_giron_mm(h_mm, norms)
    blondel = blondel_value(h_mm, g_straight)

    if not in_optimal:
        alerts_all.append(Alert(
            level="orange", code="RISER_HEIGHT_NON_OPTIMAL",
            message_fr=f'Altura do espelho {h_mm:.1f} mm fora do intervalo ótimo.',
            metric="riser_height_mm", value=h_mm,
        ))

    for fn, arg in [
        (A.check_blondel, blondel), (A.check_riser, h_mm),
        (A.check_tread, g_straight), (A.check_stair_width, inp.stair_width_mm),
    ]:
        a = fn(arg, norms)
        if a:
            alerts_all.append(a)

    treads: List[TreadDetail] = []

    if inp.balancing == "straight":
        landing_l = inp.landing_length_mm or inp.stair_width_mm
        landing_w = inp.landing_width_mm or inp.stair_width_mm
        # Volée basse : n_steps risers, dont le dernier débouche sur le palier haut
        # Palier tourne à 90° pour arriver sur le sol haut (au même niveau que le palier)
        # Convention: palier = 1 tread au niveau H = n_steps * h. Volée basse = (n_steps - 1) treads.
        num_lower_treads = n_steps - 1
        # treads volée basse
        for i in range(1, num_lower_treads + 1):
            treads.append(TreadDetail(
                index=i, type="straight",
                depth_walkline_mm=g_straight, depth_inner_mm=g_straight,
                depth_outer_mm=g_straight, angle_deg=0.0,
                cumulative_height_mm=i * h_mm,
            ))
        # palier arrivée
        treads.append(TreadDetail(
            index=n_steps, type="straight",
            depth_walkline_mm=landing_l, depth_inner_mm=landing_l,
            depth_outer_mm=landing_l, angle_deg=90.0,
            cumulative_height_mm=n_steps * h_mm,
        ))
        lower_run = num_lower_treads * g_straight
        turn_length = landing_l
        turn_width = landing_w
        num_turn = 1
        num_upper = 0
    else:
        num_winders = inp.num_winders if isinstance(inp.num_winders, int) else 5
        angle_per = math.pi / 2 / num_winders
        angle_deg = 90.0 / num_winders
        dw = inp.walkline_offset_mm * angle_per
        di = inp.inner_radius_mm * angle_per if inp.inner_radius_mm > 0 else 0.0
        do = inp.stair_width_mm * angle_per

        if dw < norms.winder_walkline_min_mm:
            alerts_all.append(Alert(
                level="red", code="BALANCING_WALKLINE_TOO_SMALL",
                message_fr=f'Cobertor na linha de passo {dw:.0f} mm < minimum {norms.winder_walkline_min_mm:.0f} mm.',
                metric="depth_walkline_mm", value=dw, threshold=norms.winder_walkline_min_mm,
            ))
        if inp.inner_radius_mm > 0 and di < norms.winder_inner_min_mm:
            alerts_all.append(Alert(
                level="orange", code="BALANCING_INNER_TOO_SMALL",
                message_fr=f'Cobertor interior {di:.0f} mm < minimum {norms.winder_inner_min_mm:.0f} mm.',
                metric="depth_inner_mm", value=di,
            ))

        num_lower = n_steps - num_winders
        if num_lower < 1:
            alerts_all.append(Alert(
                level="red", code="BALANCING_IMPOSSIBLE",
                message_fr=f'Número de degraus em leque ({num_winders}) demasiado elevado para a altura.',
            ))
            num_lower = max(0, num_lower)
        num_lower_treads = max(0, num_lower - 0)  # tous les lower risers ont un tread (winders débutent au-dessus)
        # NB: le dernier lower riser mène sur le premier winder (qui EST un tread), donc treads_lower = num_lower
        # Correction: en QT haut, volée basse = num_lower risers, num_lower treads (le dernier tread est aligné avec l'entrée du quart)
        for i in range(1, num_lower + 1):
            treads.append(TreadDetail(
                index=i, type="straight",
                depth_walkline_mm=g_straight, depth_inner_mm=g_straight,
                depth_outer_mm=g_straight, angle_deg=0.0,
                cumulative_height_mm=i * h_mm,
            ))
        for j in range(1, num_winders + 1):
            treads.append(TreadDetail(
                index=num_lower + j, type="winder",
                depth_walkline_mm=round(dw, 2), depth_inner_mm=round(di, 2),
                depth_outer_mm=round(do, 2), angle_deg=round(angle_deg, 2),
                cumulative_height_mm=(num_lower + j) * h_mm,
            ))
        lower_run = num_lower * g_straight
        turn_length = inp.stair_width_mm
        turn_width = inp.stair_width_mm
        num_turn = num_winders
        num_upper = 0
        num_lower_treads = num_lower

    total_horiz = lower_run + turn_length
    if total_horiz > inp.available_length_mm:
        alerts_all.append(Alert(
            level="red", code="STAIR_RUN_TOO_LONG",
            message_fr=f'Desenvolvimento em planta necessário {total_horiz:.0f} mm > disponível {inp.available_length_mm:.0f} mm.',
            metric="stair_run_mm", value=total_horiz, threshold=inp.available_length_mm,
        ))
    if turn_width > inp.available_width_mm:
        alerts_all.append(Alert(
            level="red", code="STAIR_WIDTH_INSUFFICIENT",
            message_fr=f'Largura necessária para o quarto de volta {turn_width:.0f} mm > disponível {inp.available_width_mm:.0f} mm.',
            metric="available_width_mm", value=turn_width, threshold=inp.available_width_mm,
        ))

    # Pente = pente de la volée (h/g), pas hauteur / emprise de l'escalier tournant.
    slope_deg = math.degrees(math.atan2(h_mm, g_straight)) if g_straight > 0 else 90.0
    sa = A.check_slope(slope_deg, norms)
    if sa:
        alerts_all.append(sa)

    # Échappée sur la volée basse (marches sous la dalle avant la trémie)
    headroom_mm = float("inf")
    headroom_idx = None
    if inp.ceiling_height_mm is not None and inp.stairwell_length_mm is not None:
        # Trémie collée au début du quart tournant : x_end = lower_run
        if inp.stairwell_offset_mm is not None:
            x_start = g_straight + inp.stairwell_offset_mm
        else:
            x_start = lower_run - inp.stairwell_length_mm
        x_end = x_start + inp.stairwell_length_mm
        for t in [tt for tt in treads if tt.type == "straight"]:
            x_i = t.index * g_straight
            y_i = t.cumulative_height_mm
            if x_i < x_start:
                head = inp.ceiling_height_mm - y_i
                if head < headroom_mm:
                    headroom_mm = head
                    headroom_idx = t.index
        if headroom_mm != float("inf"):
            ha = A.check_headroom(headroom_mm, headroom_idx, norms)
            if ha:
                alerts_all.append(ha)

    if inp.stairwell_width_mm is not None and inp.stairwell_width_mm < inp.stair_width_mm:
        alerts_all.append(Alert(
            level="red", code="STAIRWELL_TOO_SMALL",
            message_fr=f'Largura da abertura {inp.stairwell_width_mm:.0f} mm < largura da escada.',
            metric="stairwell_width_mm", value=inp.stairwell_width_mm,
        ))

    is_buildable = A.compute_is_buildable(alerts_all)
    is_geometrically_possible = A.compute_is_geometrically_possible(alerts_all)

    oa = A.check_optimal(blondel, slope_deg, norms)
    if oa:
        alerts_all.append(oa)
    alerts_all = A.summarize(alerts_all)

    stair_length = math.sqrt(inp.floor_height_mm ** 2 + total_horiz ** 2)

    return StairResult(
        stair_type=f"quarter_turn_top_{inp.balancing}",
        num_steps=n_steps, num_treads=len(treads),
        riser_height_mm=round(h_mm, 2), tread_depth_mm=round(g_straight, 2),
        blondel_value_mm=round(blondel, 2), slope_deg=round(slope_deg, 2),
        stair_run_mm=round(total_horiz, 2), stair_length_mm=round(stair_length, 2),
        headroom_mm=round(headroom_mm, 2) if headroom_mm != float("inf") else -1,
        required_stairwell_mm={
            "min_length_mm": round(lower_run, 2), "min_width_mm": round(inp.stair_width_mm, 2),
            "turn_footprint_length_mm": round(turn_length, 2),
            "turn_footprint_width_mm": round(turn_width, 2),
        },
        steps_per_flight=[num_lower_treads if inp.balancing == "straight" else num_lower, num_turn],
        treads=treads, alerts=alerts_all, is_buildable=is_buildable, is_geometrically_possible=is_geometrically_possible,
    )


def _dead(stair_type, code, msg):
    return StairResult(
        stair_type=stair_type, num_steps=0, num_treads=0,
        riser_height_mm=0, tread_depth_mm=0, blondel_value_mm=0, slope_deg=0,
        stair_run_mm=0, stair_length_mm=0, headroom_mm=0,
        required_stairwell_mm={}, steps_per_flight=[], treads=[],
        alerts=[Alert(level="red", code=code, message_fr=msg)],
        is_buildable=False, is_geometrically_possible=False,
    )
