"""Moteur de calcul — escalier droit."""
from __future__ import annotations

import math
from typing import List, Optional, Tuple

from . import alerts as A
from .blondel import blondel_value, find_optimal_num_steps, optimal_giron_mm
from .models import Alert, StairInput, StairResult, TreadDetail
from .norms_fr import DTU_36_3_FR, StairNorms


def _compute_min_headroom(
    num_treads: int,
    riser_height_mm: float,
    tread_depth_mm: float,
    ceiling_height_mm: Optional[float],
    slab_thickness_mm: float,
    stairwell_length_mm: Optional[float],
    stairwell_offset_mm: Optional[float],
    stair_run_mm: float,
) -> Tuple[float, Optional[int], List[Alert]]:
    """Calcule l'échappée minimale (formule rigoureuse trémie).

    Convention: on suppose que la trémie est alignée avec la volée. Si `stairwell_offset_mm`
    est fourni, il représente la distance horizontale entre le nez de la 1ère marche et le
    bord "bas" (côté montée) de la trémie. Sinon, on suppose la trémie collée en haut :
    bord haut de trémie = position du dernier nez de marche.

    Pour chaque marche i (1..num_treads) :
        x_i = i * g   (position horizontale du nez de marche i depuis le pied)
        y_i = i * h   (hauteur du dessus de marche i depuis le sol bas)

    La trémie occupe [x_start, x_end] avec x_end - x_start = stairwell_length_mm.
    - Sous la dalle (x_i < x_start) : échappée = ceiling_height - y_i.
    - Dans la trémie (x_start <= x_i <= x_end) : pas de contrainte de plafond.
    - Au-delà (x_i > x_end) : la marche émerge sur le plancher haut, considéré libre.

    Retourne (min_headroom, tread_index_min, alertes).
    """
    alerts_local: List[Alert] = []
    if ceiling_height_mm is None:
        # Sans hauteur sous plafond, on ne peut pas calculer.
        return (float("inf"), None, alerts_local)

    # Détermine la position de la trémie
    if stairwell_length_mm is None:
        # Pas d'info trémie : on assume qu'aucune dalle ne surplombe → échappée illimitée.
        return (float("inf"), None, alerts_local)

    if stairwell_offset_mm is not None:
        # nez de la 1ère marche à x = 1*g. Le bord bas de trémie est à x_start = g + offset.
        x_start = tread_depth_mm + stairwell_offset_mm
        x_end = x_start + stairwell_length_mm
    else:
        # Trémie collée en haut : le bord haut aligné avec le dernier nez (x = num_treads * g)
        x_end = stair_run_mm  # = num_treads * g
        x_start = x_end - stairwell_length_mm

    min_head = float("inf")
    min_index: Optional[int] = None
    for i in range(1, num_treads + 1):
        x_i = i * tread_depth_mm
        y_i = i * riser_height_mm
        if x_i < x_start:
            head = ceiling_height_mm - y_i
            if head < min_head:
                min_head = head
                min_index = i
        elif x_i > x_end:
            # marche au-delà de trémie côté haut → au-dessus du plancher haut → non physique
            # On considère cela comme trémie mal placée (marche émerge dans le plancher haut).
            alerts_local.append(
                Alert(
                    level="red",
                    code="STAIRWELL_TOO_SMALL",
                    message_fr=(
                        f"La marche n°{i} émerge au-delà de la trémie côté haut "
                        f"(x={x_i:.0f} mm > bord haut trémie {x_end:.0f} mm)."
                    ),
                    metric="stairwell_length_mm",
                    value=stairwell_length_mm,
                    threshold=x_i - x_start,
                    tread_index=i,
                )
            )
        # sinon marche dans l'ouverture → OK

    # Point critique réel : l'arête de la trémie. L'échappée se mesure verticalement depuis la
    # LIGNE DE FOULÉE (droite des nez, y = x·h/g), pas seulement aux nez : entre deux nez la ligne
    # continue de monter jusqu'au bord de dalle. Ignorer ce point surestimait l'échappée
    # jusqu'à une hauteur de marche.
    edge_head, edge_index = edge_headroom(ceiling_height_mm, x_start, riser_height_mm,
                                          tread_depth_mm, stair_run_mm)
    if edge_head is not None and edge_head < min_head:
        min_head, min_index = edge_head, edge_index

    if min_head == float("inf"):
        # Aucune marche sous la dalle → OK
        min_head = ceiling_height_mm  # sûr

    return (min_head, min_index, alerts_local)


def edge_headroom(ceiling_height_mm: float, x_start_mm: float, riser_height_mm: float,
                  tread_depth_mm: float, stair_run_mm: float) -> Tuple[Optional[float], Optional[int]]:
    """Échappée à l'arête basse de la trémie, mesurée depuis la ligne des nez de marche.

    x_start_mm : distance horizontale du pied de l'escalier au bord de trémie côté montée.
    Retourne (échappée mm, n° de marche sous l'arête) ou (None, None) si aucune marche
    n'est sous la dalle."""
    if tread_depth_mm <= 0 or x_start_mm <= 0:
        return None, None
    x = min(x_start_mm, stair_run_mm)
    head = ceiling_height_mm - x * riser_height_mm / tread_depth_mm
    return head, max(1, int(math.ceil(x / tread_depth_mm - 1e-9)))


def compute_straight(
    inp: StairInput, norms: StairNorms = DTU_36_3_FR
) -> StairResult:
    """Calcule un escalier droit."""
    alerts_all: List[Alert] = []

    # 1. Nb marches et hauteur
    n_steps, h_mm, in_optimal = find_optimal_num_steps(inp.floor_height_mm, norms)
    if n_steps <= 0:
        # cas dégénéré
        return StairResult(
            stair_type="straight",
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
            alerts=[
                Alert(
                    level="red",
                    code="GEOMETRY_INVALID",
                    message_fr="Hauteur d'étage invalide ou impossible à découper.",
                )
            ],
            is_buildable=False,
        )

    num_treads = n_steps - 1  # convention : le dernier "riser" débouche sur le sol haut

    # 2. Giron via Blondel (optimal, non contraint par L)
    g_mm = optimal_giron_mm(h_mm, norms)
    blondel = blondel_value(h_mm, g_mm)

    # 3. Géométrie
    stair_run = num_treads * g_mm
    stair_length = math.sqrt(inp.floor_height_mm ** 2 + stair_run ** 2)
    slope_deg = math.degrees(math.atan2(inp.floor_height_mm, stair_run)) if stair_run > 0 else 90.0

    # 4. Échappée (formule rigoureuse)
    headroom_mm, headroom_idx, headroom_alerts = _compute_min_headroom(
        num_treads=num_treads,
        riser_height_mm=h_mm,
        tread_depth_mm=g_mm,
        ceiling_height_mm=inp.ceiling_height_mm,
        slab_thickness_mm=inp.slab_thickness_mm,
        stairwell_length_mm=inp.stairwell_length_mm,
        stairwell_offset_mm=inp.stairwell_offset_mm,
        stair_run_mm=stair_run,
    )
    alerts_all.extend(headroom_alerts)

    # 5. Alertes de conformité
    if not in_optimal:
        alerts_all.append(
            Alert(
                level="orange",
                code="RISER_HEIGHT_NON_OPTIMAL",
                message_fr=(
                    f"Hauteur de marche {h_mm:.1f} mm hors plage optimale "
                    f"[{norms.riser_height_optimal_min_mm:.0f}, {norms.riser_height_optimal_max_mm:.0f}] mm."
                ),
                metric="riser_height_mm",
                value=h_mm,
            )
        )

    for check_fn, arg in [
        (A.check_blondel, blondel),
        (A.check_riser, h_mm),
        (A.check_tread, g_mm),
        (A.check_slope, slope_deg),
        (A.check_stair_width, inp.stair_width_mm),
    ]:
        alert = check_fn(arg, norms) if check_fn is not A.check_stair_width else check_fn(arg, norms)
        if alert:
            alerts_all.append(alert)

    # Échappée
    if headroom_mm != float("inf"):
        head_alert = A.check_headroom(headroom_mm, headroom_idx, norms)
        if head_alert:
            alerts_all.append(head_alert)

    # Reculement
    run_alert = A.check_stair_run_fits(stair_run, inp.available_length_mm)
    if run_alert:
        alerts_all.append(run_alert)

    # Trémie width
    if inp.stairwell_width_mm is not None and inp.stairwell_width_mm < inp.stair_width_mm:
        alerts_all.append(
            Alert(
                level="red",
                code="STAIRWELL_TOO_SMALL",
                message_fr=(
                    f"Largeur trémie {inp.stairwell_width_mm:.0f} mm < largeur escalier "
                    f"{inp.stair_width_mm:.0f} mm."
                ),
                metric="stairwell_width_mm",
                value=inp.stairwell_width_mm,
                threshold=inp.stair_width_mm,
            )
        )

    # 6. is_buildable
    is_buildable = A.compute_is_buildable(alerts_all)

    # 7. Optimal config (vert)
    opt_alert = A.check_optimal(blondel, slope_deg, norms)
    if opt_alert:
        alerts_all.append(opt_alert)

    # 8. GEOMETRY_OK si tout est propre
    alerts_all = A.summarize(alerts_all)

    # 9. Treads details
    treads: List[TreadDetail] = []
    for i in range(1, num_treads + 1):
        treads.append(
            TreadDetail(
                index=i,
                type="straight",
                depth_walkline_mm=g_mm,
                depth_inner_mm=g_mm,
                depth_outer_mm=g_mm,
                angle_deg=0.0,
                cumulative_height_mm=i * h_mm,
            )
        )

    required_stairwell = {
        # Longueur trémie mini pour respecter 1.90m d'échappée en fin d'escalier
        "min_length_mm": _required_stairwell_length(
            n_steps, h_mm, g_mm, inp.ceiling_height_mm, norms.headroom_min_mm, stair_run
        ),
        "min_width_mm": inp.stair_width_mm,
    }

    return StairResult(
        stair_type="straight",
        num_steps=n_steps,
        num_treads=num_treads,
        riser_height_mm=round(h_mm, 2),
        tread_depth_mm=round(g_mm, 2),
        blondel_value_mm=round(blondel, 2),
        slope_deg=round(slope_deg, 2),
        stair_run_mm=round(stair_run, 2),
        stair_length_mm=round(stair_length, 2),
        headroom_mm=round(headroom_mm, 2) if headroom_mm != float("inf") else -1,
        required_stairwell_mm=required_stairwell,
        steps_per_flight=[n_steps],
        treads=treads,
        alerts=alerts_all,
        is_buildable=is_buildable,
    )


def _required_stairwell_length(
    num_steps: int,
    h_mm: float,
    g_mm: float,
    ceiling_height_mm: Optional[float],
    min_headroom_mm: float,
    stair_run_mm: float,
) -> float:
    """Calcule la longueur trémie minimale nécessaire pour respecter l'échappée mini.

    Cherche le plus grand k tel que ceiling_height - k*h >= min_headroom.
    La trémie doit couvrir toutes les marches k+1 ... num_treads.
    Longueur trémie min = (num_treads - k) * g.
    """
    if ceiling_height_mm is None:
        return 0.0
    # Sur la 1ère marche : head = ceiling - h. On veut head >= min_headroom.
    # k_max : plus grand k tel que ceiling - k*h >= min_headroom
    #        → k <= (ceiling - min_headroom) / h
    if h_mm <= 0 or g_mm <= 0:
        return 0.0
    # La ligne des nez y = x·h/g doit rester ≥ min_headroom sous la dalle :
    # bord de trémie au plus à x_max = (plafond − échappée mini)·g/h du pied.
    x_max = max(0.0, (ceiling_height_mm - min_headroom_mm) * g_mm / h_mm)
    return round(max(0.0, stair_run_mm - x_max), 2)
