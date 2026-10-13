"""Moteur de calcul — escalier quart tournant bas (départ tournant)."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from . import alerts as A
from .blondel import blondel_value, find_optimal_num_steps, optimal_giron_mm
from .models import Alert, QuarterTurnBottomInput, StairResult, TreadDetail
from .norms_fr import DTU_36_3_FR, StairNorms


def compute_quarter_turn_bottom(
    inp: QuarterTurnBottomInput, norms: StairNorms = DTU_36_3_FR
) -> StairResult:
    """Calcule un escalier quart tournant bas.

    Deux modes :
      - "straight"  : palier bas rectangulaire + volée droite au-dessus.
      - "balanced"  : marches balancées dans le quart + volée droite au-dessus.

    En mode balanced avec `num_winders="auto"`, on essaie 7, 6, 5, 4, 3 winders et
    on retient la première configuration `is_buildable=True`. Sinon, on retourne
    la meilleure configuration (celle avec le moins d'alertes rouges).
    """
    if inp.balancing == "balanced" and inp.num_winders == "auto":
        return _compute_balanced_auto(inp, norms)
    return _compute_qt_single(inp, norms)


def _compute_balanced_auto(
    base_inp: QuarterTurnBottomInput, norms: StairNorms
) -> StairResult:
    """Essaie plusieurs valeurs de num_winders (3→9 croissant) et renvoie la 1ère buildable.

    On privilégie le MINIMUM de winders qui rend l'escalier constructible.
    Ainsi on maximise le confort (ligne de foulée) et on garde autant que possible
    des marches droites pour la conformité DTU.
    """
    candidates = [3, 4, 5, 6, 7, 8, 9]
    best_result: StairResult | None = None
    best_red_count = float("inf")
    for n in candidates:
        trial_inp = base_inp.model_copy(update={"num_winders": n})
        result = _compute_qt_single(trial_inp, norms)
        if result.is_buildable:
            result.alerts.insert(
                0,
                Alert(
                    level="green",
                    code="AUTO_WINDERS_SELECTED",
                    message_fr=(
                        f'Distribuição automática: {n} degraus em leque (mínimo que permite à escada caber no espaço disponível).'
                    ),
                    metric="num_winders",
                    value=float(n),
                ),
            )
            return result
        red_count = sum(1 for a in result.alerts if a.level == "red")
        if red_count < best_red_count:
            best_red_count = red_count
            best_result = result
    # Aucune configuration OK : renvoyer la meilleure
    if best_result is not None:
        best_result.alerts.insert(
            0,
            Alert(
                level="red",
                code="AUTO_WINDERS_NO_SOLUTION",
                message_fr=(
                    "Nenhuma distribuição de degraus em leque (3 a 9) satisfaz as restrições geométricas. Configuração devolvida: a que tem menos alertas vermelhos."
                ),
            ),
        )
    return best_result  # type: ignore[return-value]


def _compute_qt_single(
    inp: QuarterTurnBottomInput, norms: StairNorms = DTU_36_3_FR
) -> StairResult:
    alerts_all: List[Alert] = []

    # 1. Nombre total de marches et hauteur de marche
    n_steps, h_mm, in_optimal = find_optimal_num_steps(inp.floor_height_mm, norms)
    if n_steps <= 0:
        return _dead_result("quarter_turn_bottom", "GEOMETRY_INVALID", "Altura inválida.")

    # 2. Giron droit optimal
    g_straight = optimal_giron_mm(h_mm, norms)
    blondel = blondel_value(h_mm, g_straight)

    if not in_optimal:
        alerts_all.append(
            Alert(
                level="orange",
                code="RISER_HEIGHT_NON_OPTIMAL",
                message_fr=(
                    f'Altura do espelho {h_mm:.1f} mm fora do intervalo ótimo.'
                ),
                metric="riser_height_mm",
                value=h_mm,
            )
        )

    # Checks Blondel / riser / tread / slope / width
    for check_fn, arg in [
        (A.check_blondel, blondel),
        (A.check_riser, h_mm),
        (A.check_tread, g_straight),
        (A.check_stair_width, inp.stair_width_mm),
    ]:
        alert = check_fn(arg, norms)
        if alert:
            alerts_all.append(alert)

    treads: List[TreadDetail] = []

    if inp.balancing == "straight":
        result_geom = _compute_straight_landing_mode(inp, n_steps, h_mm, g_straight, norms, alerts_all, treads)
    else:
        result_geom = _compute_balanced_mode(inp, n_steps, h_mm, g_straight, norms, alerts_all, treads)

    stair_run = result_geom["stair_run_mm"]
    upper_flight_run = result_geom["upper_flight_run_mm"]
    turn_footprint_length = result_geom["turn_footprint_length_mm"]
    turn_footprint_width = result_geom["turn_footprint_width_mm"]
    num_treads_total = result_geom["num_treads_total"]
    num_upper = result_geom["num_upper"]
    num_turn = result_geom["num_turn"]

    # Vérification encombrement
    if turn_footprint_length + upper_flight_run > inp.available_length_mm:
        alerts_all.append(
            Alert(
                level="red",
                code="STAIR_RUN_TOO_LONG",
                message_fr=(
                    f'Desenvolvimento em planta necessário {turn_footprint_length + upper_flight_run:.0f} mm > disponível {inp.available_length_mm:.0f} mm (mode {inp.balancing}).'
                ),
                metric="stair_run_mm",
                value=turn_footprint_length + upper_flight_run,
                threshold=inp.available_length_mm,
            )
        )

    if turn_footprint_width > inp.available_width_mm:
        alerts_all.append(
            Alert(
                level="red",
                code="STAIR_WIDTH_INSUFFICIENT",
                message_fr=(
                    f'Largura necessária para o quarto de volta {turn_footprint_width:.0f} mm > disponível {inp.available_width_mm:.0f} mm.'
                ),
                metric="available_width_mm",
                value=turn_footprint_width,
                threshold=inp.available_width_mm,
            )
        )

    # Slope calculée sur l'ensemble (approximation : hauteur / (turn + upper))
    total_horiz = turn_footprint_length + upper_flight_run
    # Pente = pente de la volée (h/g), pas hauteur / emprise de l'escalier tournant.
    slope_deg = math.degrees(math.atan2(h_mm, g_straight)) if g_straight > 0 else 90.0
    slope_alert = A.check_slope(slope_deg, norms)
    if slope_alert:
        alerts_all.append(slope_alert)

    # Échappée simplifiée pour QT : on considère la volée droite au-dessus.
    # On calcule l'échappée sur la volée droite (marches num_turn+1 à num_treads_total).
    headroom_mm = float("inf")
    headroom_idx: Optional[int] = None
    if inp.ceiling_height_mm is not None and inp.stairwell_length_mm is not None:
        # Position horizontale des marches de la volée droite depuis pied de l'escalier (post-turn)
        # nez de la première marche droite au-dessus du turn est à x = turn_footprint_length + g
        # Trémie collée en haut par défaut : x_end = turn_footprint_length + upper_flight_run
        if inp.stairwell_offset_mm is not None:
            x_start = turn_footprint_length + g_straight + inp.stairwell_offset_mm
        else:
            x_end_ref = turn_footprint_length + upper_flight_run
            x_start = x_end_ref - inp.stairwell_length_mm
        x_end = x_start + inp.stairwell_length_mm

        min_head = float("inf")
        min_idx = None
        # Marches balancées : elles ont chacune une hauteur cumulée h_mm * index
        # On checkera uniquement les treads dont x_i est défini (les straight)
        for t in treads:
            if t.type != "straight":
                # winders sont dans le quart : la trémie du haut ne les concerne pas si trémie côté droit
                # Selon la disposition, elles peuvent être sous la dalle → simplification Phase 0 : on ignore
                continue
            # position x du nez de marche droite
            # index t.index dans la numérotation globale ; les straight treads commencent après le tour
            straight_pos = t.index - num_turn  # 1-based dans la volée droite
            x_i = turn_footprint_length + straight_pos * g_straight
            y_i = t.cumulative_height_mm
            if x_i < x_start:
                head = inp.ceiling_height_mm - y_i
                if head < min_head:
                    min_head = head
                    min_idx = t.index
            elif x_i > x_end:
                alerts_all.append(
                    Alert(
                        level="red",
                        code="STAIRWELL_TOO_SMALL",
                        message_fr=(
                            f'O degrau n.º{t.index} emerge para além da abertura (x={x_i:.0f} mm > bordo superior da abertura {x_end:.0f} mm).'
                        ),
                        metric="stairwell_length_mm",
                        value=inp.stairwell_length_mm,
                        tread_index=t.index,
                    )
                )
        if min_head != float("inf"):
            headroom_mm = min_head
            headroom_idx = min_idx
            head_alert = A.check_headroom(headroom_mm, headroom_idx, norms)
            if head_alert:
                alerts_all.append(head_alert)

    # Trémie width
    if inp.stairwell_width_mm is not None and inp.stairwell_width_mm < inp.stair_width_mm:
        alerts_all.append(
            Alert(
                level="red",
                code="STAIRWELL_TOO_SMALL",
                message_fr=(
                    f'Largura da abertura {inp.stairwell_width_mm:.0f} mm < largura da escada {inp.stair_width_mm:.0f} mm.'
                ),
                metric="stairwell_width_mm",
                value=inp.stairwell_width_mm,
            )
        )

    # is_buildable
    is_buildable = A.compute_is_buildable(alerts_all)
    is_geometrically_possible = A.compute_is_geometrically_possible(alerts_all)

    # OPTIMAL
    opt_alert = A.check_optimal(blondel, slope_deg, norms)
    if opt_alert:
        alerts_all.append(opt_alert)

    alerts_all = A.summarize(alerts_all)

    stair_length = math.sqrt(inp.floor_height_mm ** 2 + total_horiz ** 2)

    return StairResult(
        stair_type=f"quarter_turn_bottom_{inp.balancing}",
        num_steps=n_steps,
        num_treads=num_treads_total,
        riser_height_mm=round(h_mm, 2),
        tread_depth_mm=round(g_straight, 2),
        blondel_value_mm=round(blondel, 2),
        slope_deg=round(slope_deg, 2),
        stair_run_mm=round(total_horiz, 2),
        stair_length_mm=round(stair_length, 2),
        headroom_mm=round(headroom_mm, 2) if headroom_mm != float("inf") else -1,
        required_stairwell_mm={
            "min_length_mm": round(upper_flight_run, 2),
            "min_width_mm": round(inp.stair_width_mm, 2),
            "turn_footprint_length_mm": round(turn_footprint_length, 2),
            "turn_footprint_width_mm": round(turn_footprint_width, 2),
        },
        steps_per_flight=[num_turn, num_upper],
        treads=treads,
        alerts=alerts_all,
        is_buildable=is_buildable,
        is_geometrically_possible=is_geometrically_possible,
    )


def _compute_straight_landing_mode(
    inp: QuarterTurnBottomInput,
    n_steps: int,
    h_mm: float,
    g_straight: float,
    norms: StairNorms,
    alerts_all: List[Alert],
    treads: List[TreadDetail],
) -> dict:
    # steps_before_landing risers avant le palier, puis palier, puis volée droite au-dessus.
    steps_before = max(0, inp.steps_before_landing)
    landing_h = steps_before * h_mm  # hauteur du dessus du palier
    landing_length = inp.landing_length_mm or inp.stair_width_mm
    landing_width = inp.landing_width_mm or inp.stair_width_mm

    num_turn = steps_before  # les marches avant palier sont dans le turn zone
    num_upper = n_steps - steps_before  # risers restants (le dernier débouche sur sol haut)
    # Convention : num_upper est le nombre de risers dans la volée droite. Le dernier riser
    # débouche sur le sol haut → num_upper - 1 treads physiques dans la volée droite, + palier compte comme 1 tread.
    num_treads_upper = num_upper - 1
    num_treads_total = num_turn + 1 + num_treads_upper  # +1 pour le palier

    # tread footprint dans le turn zone
    for i in range(1, steps_before + 1):
        treads.append(
            TreadDetail(
                index=i,
                type="straight",
                depth_walkline_mm=g_straight,
                depth_inner_mm=g_straight,
                depth_outer_mm=g_straight,
                angle_deg=0.0,
                cumulative_height_mm=i * h_mm,
            )
        )
    # Palier (tread spécial)
    treads.append(
        TreadDetail(
            index=steps_before + 1,
            type="straight",
            depth_walkline_mm=landing_length,
            depth_inner_mm=landing_length,
            depth_outer_mm=landing_length,
            angle_deg=90.0,  # changement de direction
            cumulative_height_mm=landing_h,
        )
    )
    # Volée droite
    for j in range(1, num_treads_upper + 1):
        idx = steps_before + 1 + j
        treads.append(
            TreadDetail(
                index=idx,
                type="straight",
                depth_walkline_mm=g_straight,
                depth_inner_mm=g_straight,
                depth_outer_mm=g_straight,
                angle_deg=0.0,
                cumulative_height_mm=landing_h + j * h_mm,
            )
        )

    upper_flight_run = num_treads_upper * g_straight
    turn_footprint_length = landing_length  # profondeur du palier dans la direction de la volée droite
    turn_footprint_width = landing_width

    return {
        "stair_run_mm": upper_flight_run,
        "upper_flight_run_mm": upper_flight_run,
        "turn_footprint_length_mm": turn_footprint_length,
        "turn_footprint_width_mm": turn_footprint_width,
        "num_treads_total": num_treads_total,
        "num_upper": num_upper,
        "num_turn": num_turn + 1,  # +1 pour compter le palier
    }


def _compute_balanced_mode(
    inp: QuarterTurnBottomInput,
    n_steps: int,
    h_mm: float,
    g_straight: float,
    norms: StairNorms,
    alerts_all: List[Alert],
    treads: List[TreadDetail],
) -> dict:
    num_winders = inp.num_winders if isinstance(inp.num_winders, int) else 5
    walkline = inp.walkline_offset_mm
    inner_radius = inp.inner_radius_mm

    # Quart tournant : 90° réparti sur num_winders
    angle_per_winder = math.pi / 2 / num_winders  # radians
    angle_per_winder_deg = 90.0 / num_winders

    # Giron sur ligne de foulée
    depth_walkline = walkline * angle_per_winder  # arc de cercle

    # Giron intérieur (si inner_radius > 0, sinon 0)
    depth_inner = inner_radius * angle_per_winder if inner_radius > 0 else 0.0

    # Giron extérieur (à la largeur d'escalier moins un pouce)
    outer_radius = inp.stair_width_mm  # rayon extérieur = largeur escalier (pivot à l'intérieur)
    depth_outer = outer_radius * angle_per_winder

    # Vérifications
    if depth_walkline < norms.winder_walkline_min_mm:
        alerts_all.append(
            Alert(
                level="red",
                code="BALANCING_WALKLINE_TOO_SMALL",
                message_fr=(
                    f'Cobertor na linha de passo {depth_walkline:.0f} mm < minimum {norms.winder_walkline_min_mm:.0f} mm. Reduzir o número de degraus em leque ou aumentar o afastamento da linha de passo.'
                ),
                metric="depth_walkline_mm",
                value=depth_walkline,
                threshold=norms.winder_walkline_min_mm,
            )
        )

    if inner_radius > 0 and depth_inner < norms.winder_inner_min_mm:
        alerts_all.append(
            Alert(
                level="orange",
                code="BALANCING_INNER_TOO_SMALL",
                message_fr=(
                    f'Cobertor interior {depth_inner:.0f} mm < mínimo recomendado {norms.winder_inner_min_mm:.0f} mm.'
                ),
                metric="depth_inner_mm",
                value=depth_inner,
                threshold=norms.winder_inner_min_mm,
            )
        )

    # Placement : le quart tournant occupe un carré au bas de l'escalier
    # de côté = stair_width_mm (par convention)
    turn_footprint_length = inp.stair_width_mm
    turn_footprint_width = inp.stair_width_mm

    # Volée droite au-dessus : n_steps - num_winders risers
    num_upper = n_steps - num_winders
    if num_upper < 1:
        alerts_all.append(
            Alert(
                level="red",
                code="BALANCING_IMPOSSIBLE",
                message_fr=(
                    f'Número de degraus em leque ({num_winders}) >= número total de degraus ({n_steps}). Reduzir o número de degraus em leque.'
                ),
                metric="num_winders",
                value=float(num_winders),
                threshold=float(n_steps - 1),
            )
        )
        num_upper = max(0, num_upper)

    num_treads_upper = max(0, num_upper - 1)
    num_treads_total = num_winders + num_treads_upper

    # Winders
    for i in range(1, num_winders + 1):
        treads.append(
            TreadDetail(
                index=i,
                type="winder",
                depth_walkline_mm=round(depth_walkline, 2),
                depth_inner_mm=round(depth_inner, 2),
                depth_outer_mm=round(depth_outer, 2),
                angle_deg=round(angle_per_winder_deg, 2),
                cumulative_height_mm=i * h_mm,
            )
        )
    # Straight treads au-dessus
    for j in range(1, num_treads_upper + 1):
        treads.append(
            TreadDetail(
                index=num_winders + j,
                type="straight",
                depth_walkline_mm=g_straight,
                depth_inner_mm=g_straight,
                depth_outer_mm=g_straight,
                angle_deg=0.0,
                cumulative_height_mm=(num_winders + j) * h_mm,
            )
        )

    upper_flight_run = num_treads_upper * g_straight

    return {
        "stair_run_mm": upper_flight_run,
        "upper_flight_run_mm": upper_flight_run,
        "turn_footprint_length_mm": turn_footprint_length,
        "turn_footprint_width_mm": turn_footprint_width,
        "num_treads_total": num_treads_total,
        "num_upper": num_upper,
        "num_turn": num_winders,
    }


def _dead_result(stair_type: str, code: str, msg: str) -> StairResult:
    return StairResult(
        stair_type=stair_type,
        num_steps=0,
        num_treads=0,
        riser_height_mm=0,
        tread_depth_mm=0,
        blondel_value_mm=0,
        slope_deg=0,
        stair_run_mm=0,
        stair_length_mm=0,
        headroom_mm=0,
        required_stairwell_mm={},
        steps_per_flight=[],
        treads=[],
        alerts=[Alert(level="red", code=code, message_fr=msg)],
        is_buildable=False,
        is_geometrically_possible=False,
    )
