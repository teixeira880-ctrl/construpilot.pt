"""Système d'alertes STAIRPILOT.

Codes minimum :
    - HEADROOM_INSUFFICIENT (rouge, échappée < 1.90m) — blocker géométrique
    - STAIRWELL_TOO_SMALL (rouge, trémie incompatible) — blocker géométrique
    - STAIR_RUN_TOO_LONG (rouge, ne rentre pas dans available_length) — blocker
    - STAIR_WIDTH_INSUFFICIENT (rouge, ne rentre pas en largeur) — blocker
    - GEOMETRY_INVALID (rouge) — blocker
    - BALANCING_IMPOSSIBLE (rouge) — blocker
    - BLONDEL_OUT_OF_RANGE (rouge/orange) — non-conformité DTU (n'empêche pas la construction)
    - RISER_TOO_HIGH (rouge/orange) — non-conformité DTU
    - RISER_TOO_LOW (orange)
    - TREAD_TOO_SMALL (rouge/orange) — non-conformité DTU
    - SLOPE_TOO_STEEP (rouge/orange) — non-conformité DTU
    - STAIR_WIDTH_TOO_SMALL (orange)
    - BALANCING_INNER_TOO_SMALL (orange)
    - BALANCING_WALKLINE_TOO_SMALL (rouge) — non-conformité DTU
    - GEOMETRY_OK (vert)
    - OPTIMAL_CONFIG (vert)
    - AUTO_WINDERS_SELECTED (vert)
    - AUTO_WINDERS_NO_SOLUTION (rouge) — blocker
"""
from __future__ import annotations

from typing import List, Optional, Set

from .models import Alert
from .norms_fr import DTU_36_3_FR, StairNorms


# Codes qui bloquent physiquement la construction. Les autres alertes rouges sont
# des non-conformités DTU (à corriger mais l'escalier peut être coulé).
BLOCKING_CODES: Set[str] = {
    "STAIR_RUN_TOO_LONG",
    "STAIR_WIDTH_INSUFFICIENT",
    "STAIRWELL_TOO_SMALL",
    "HEADROOM_INSUFFICIENT",
    "GEOMETRY_INVALID",
    "BALANCING_IMPOSSIBLE",
    "AUTO_WINDERS_NO_SOLUTION",
}


def is_alert_blocking(alert: Alert) -> bool:
    """True se o alerta impede fisicamente a construção (geometria/segurança)."""
    return alert.level == "red" and alert.code in BLOCKING_CODES


def compute_is_geometrically_possible(alerts: List[Alert]) -> bool:
    """True enquanto não há bloqueador geométrico (lógica histórica)."""
    return not any(is_alert_blocking(a) for a in alerts)


def compute_is_buildable(alerts: List[Alert]) -> bool:
    """is_buildable = conforme para uso corrente.

    QUALQUER alerta vermelho torna a escada não conforme — não só os
    `BLOCKING_CODES`. As incompatibilidades regulamentares (inclinação>42°,
    cobertor<220 mm, Blondel fora de 560–700 mm, etc.) tornam a solução
    inadequada para habitação, mesmo que seja geometricamente possível
    construí-la (ver `is_geometrically_possible`).
    """
    return not any(a.level == "red" for a in alerts)


def check_blondel(blondel_mm: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if blondel_mm < norms.blondel_acceptable_min_mm or blondel_mm > norms.blondel_acceptable_max_mm:
        return Alert(
            level="red",
            code="BLONDEL_OUT_OF_RANGE",
            message_fr=(
                f'Fórmula de Blondel (2h+g) = {blondel_mm:.0f} mm hors plage acceptable [{norms.blondel_acceptable_min_mm:.0f}, {norms.blondel_acceptable_max_mm:.0f}].'
            ),
            metric="blondel_mm",
            value=blondel_mm,
            threshold=norms.blondel_acceptable_min_mm,
        )
    if blondel_mm < norms.blondel_optimal_min_mm or blondel_mm > norms.blondel_optimal_max_mm:
        return Alert(
            level="orange",
            code="BLONDEL_OUT_OF_RANGE",
            message_fr=(
                f'Fórmula de Blondel (2h+g) = {blondel_mm:.0f} mm fora do intervalo ótimo [{norms.blondel_optimal_min_mm:.0f}, {norms.blondel_optimal_max_mm:.0f}].'
            ),
            metric="blondel_mm",
            value=blondel_mm,
            threshold=norms.blondel_optimal_min_mm,
        )
    return None


def check_riser(h_mm: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if h_mm > norms.riser_height_max_mm:
        return Alert(
            level="red",
            code="RISER_TOO_HIGH",
            message_fr=(
                f'Altura do espelho {h_mm:.1f} mm > {norms.riser_height_max_mm:.0f} mm (não conforme com as regras de boa prática / RGEU / DL 163/2006).'
            ),
            metric="riser_height_mm",
            value=h_mm,
            threshold=norms.riser_height_max_mm,
        )
    if h_mm > norms.riser_height_optimal_max_mm:
        return Alert(
            level="orange",
            code="RISER_TOO_HIGH",
            message_fr=(
                f'Altura do espelho {h_mm:.1f} mm acima do intervalo ótimo ({norms.riser_height_optimal_max_mm:.0f} mm).'
            ),
            metric="riser_height_mm",
            value=h_mm,
            threshold=norms.riser_height_optimal_max_mm,
        )
    if h_mm < norms.riser_height_optimal_min_mm - 10:  # <150
        return Alert(
            level="orange",
            code="RISER_TOO_LOW",
            message_fr=(
                f'Altura do espelho {h_mm:.1f} mm inferior ao conforto recomendado (<{norms.riser_height_optimal_min_mm - 10:.0f} mm).'
            ),
            metric="riser_height_mm",
            value=h_mm,
            threshold=norms.riser_height_optimal_min_mm - 10,
        )
    return None


def check_tread(g_mm: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if g_mm < norms.tread_depth_hard_min_mm:
        return Alert(
            level="red",
            code="TREAD_TOO_SMALL",
            message_fr=(
                f'Cobertor {g_mm:.1f} mm < minimum absolu {norms.tread_depth_hard_min_mm:.0f} mm.'
            ),
            metric="tread_depth_mm",
            value=g_mm,
            threshold=norms.tread_depth_hard_min_mm,
        )
    if g_mm < norms.tread_depth_optimal_min_mm:
        return Alert(
            level="orange",
            code="TREAD_TOO_SMALL",
            message_fr=(
                f'Cobertor {g_mm:.1f} mm inferior ao intervalo ótimo ({norms.tread_depth_optimal_min_mm:.0f} mm).'
            ),
            metric="tread_depth_mm",
            value=g_mm,
            threshold=norms.tread_depth_optimal_min_mm,
        )
    return None


def check_slope(slope_deg: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if slope_deg > norms.slope_hard_max_deg:
        return Alert(
            level="red",
            code="SLOPE_TOO_STEEP",
            message_fr=(
                f'Inclinação {slope_deg:.1f}° > {norms.slope_hard_max_deg:.0f}° (escada demasiado íngreme, perigosa).'
            ),
            metric="slope_deg",
            value=slope_deg,
            threshold=norms.slope_hard_max_deg,
        )
    if slope_deg > norms.slope_acceptable_max_deg:
        return Alert(
            level="orange",
            code="SLOPE_TOO_STEEP",
            message_fr=(
                f'Inclinação {slope_deg:.1f}° acima do intervalo confortável ({norms.slope_acceptable_max_deg:.0f}°).'
            ),
            metric="slope_deg",
            value=slope_deg,
            threshold=norms.slope_acceptable_max_deg,
        )
    return None


def check_headroom(
    headroom_mm: float,
    tread_index: Optional[int] = None,
    norms: StairNorms = DTU_36_3_FR,
) -> Optional[Alert]:
    if headroom_mm < norms.headroom_min_mm:
        tread_str = f' ao nível do degrau n.º{tread_index}' if tread_index else ""
        return Alert(
            level="red",
            code="HEADROOM_INSUFFICIENT",
            message_fr=(
                f'Altura livre {headroom_mm:.0f} mm{tread_str} < minimum {norms.headroom_min_mm:.0f} mm (DTU 36.3).'
            ),
            metric="headroom_mm",
            value=headroom_mm,
            threshold=norms.headroom_min_mm,
            tread_index=tread_index,
        )
    return None


def check_stair_width(width_mm: float, norms: StairNorms = DTU_36_3_FR) -> Optional[Alert]:
    if width_mm < norms.stair_width_min_mm:
        return Alert(
            level="orange",
            code="STAIR_WIDTH_TOO_SMALL",
            message_fr=(
                f'Largura da escada {width_mm:.0f} mm < mínimo de conforto {norms.stair_width_min_mm:.0f} mm.'
            ),
            metric="stair_width_mm",
            value=width_mm,
            threshold=norms.stair_width_min_mm,
        )
    return None


def check_stair_run_fits(
    required_run_mm: float, available_length_mm: float
) -> Optional[Alert]:
    if required_run_mm > available_length_mm:
        return Alert(
            level="red",
            code="STAIR_RUN_TOO_LONG",
            message_fr=(
                f'Desenvolvimento em planta necessário {required_run_mm:.0f} mm > disponível {available_length_mm:.0f} mm. A escada não cabe.'
            ),
            metric="stair_run_mm",
            value=required_run_mm,
            threshold=available_length_mm,
        )
    return None


def check_optimal(
    blondel_mm: float, slope_deg: float, norms: StairNorms = DTU_36_3_FR
) -> Optional[Alert]:
    if (
        norms.blondel_optimal_min_mm + 20 <= blondel_mm <= norms.blondel_optimal_max_mm
        and norms.slope_optimal_min_deg <= slope_deg <= norms.slope_optimal_max_deg
    ):
        return Alert(
            level="green",
            code="OPTIMAL_CONFIG",
            message_fr="Configuração ótima: Blondel e inclinação nos intervalos ideais.",
        )
    return None


def summarize(alerts: List[Alert]) -> List[Alert]:
    """Ajoute un GEOMETRY_OK vert si aucune alerte rouge/orange n'a été émise (hors verts)."""
    non_green = [a for a in alerts if a.level != "green"]
    if not non_green:
        alerts.append(
            Alert(
                level="green",
                code="GEOMETRY_OK",
                message_fr="Geometria conforme com os limites RGEU / DL 163/2006.",
            )
        )
    return alerts
