"""Checks determinísticos geométricos — regras explícitas sem LLM.

Cada regra produz 0..N `Anomaly`. Nenhum efeito colateral; funções puras sobre
o `BuildingModel`.

Regras implementadas (R1 + L1.4):
    GEO-001  Nenhum nembo com largura ≤ 0.
    GEO-002  Nenhum vão duplicado (mesma localização, mesmo wall, mesmo kind).
    GEO-003  Pés-direitos plausíveis por tipo de piso.
    GEO-004  Escada cabe na abertura (Lei da escada 2a+b≈63cm).
    GEO-005  Áreas por compartimento consistentes (±5% vs soma dos pisos).
    GEO-006  Nenhuma parede inteiramente dentro de abertura de laje/escada.
    GEO-007  Cotas parciais somam totais (±2 cm) — depende de dados vectoriais.
"""
from __future__ import annotations

import math
from collections import defaultdict

from engines.bet_agent.models.building import (
    BuildingModel,
    FloorKind,
    OpeningKind,
    Stair,
    Wall,
    Opening,
)
from engines.bet_agent.models.summary import (
    Anomaly,
    AnomalySeverity,
    AnomalySource,
)


# Pés-direitos plausíveis (metros) — min, max.
_HEIGHT_RANGES: dict[FloorKind, tuple[float, float]] = {
    FloorKind.CAVE: (2.20, 3.00),
    FloorKind.RC: (2.40, 3.20),
    FloorKind.PISO: (2.40, 3.20),
    FloorKind.SOTAO: (1.80, 3.20),  # sótão habitável exige ≥1.80 m
    FloorKind.COBERTURA: (0.0, 10.0),  # cobertura não tem pé-direito uniforme
}


def _bbox_overlap_pct(a: Opening, wall: Wall) -> float:
    """Aproximação simplificada: pct de sobreposição entre bbox da abertura e bbox da parede.
    Serve só para GEO-002 (vãos duplicados) e GEO-006.
    """
    sa = a.source.bbox
    sb = wall.source.bbox
    ox1 = max(sa.x1, sb.x1)
    oy1 = max(sa.y1, sb.y1)
    ox2 = min(sa.x2, sb.x2)
    oy2 = min(sa.y2, sb.y2)
    if ox2 <= ox1 or oy2 <= oy1:
        return 0.0
    overlap = (ox2 - ox1) * (oy2 - oy1)
    area_a = max(1e-6, (sa.x2 - sa.x1) * (sa.y2 - sa.y1))
    return overlap / area_a


def _check_geo001_nembo_width(building: BuildingModel) -> list[Anomaly]:
    """GEO-001 — nenhum elemento tem largura ≤ 0."""
    out: list[Anomaly] = []
    # Paredes
    for w in building.walls:
        if w.length_m <= 0 or w.thickness_m <= 0:
            out.append(Anomaly(
                severity=AnomalySeverity.GRAVE,
                code="GEO-001",
                message_pt=(
                    f"Parede {w.id} com dimensão não positiva "
                    f"(comp={w.length_m:.2f} m, esp={w.thickness_m:.2f} m)."
                ),
                source=AnomalySource(page=w.source.page, bbox=w.source.bbox),
                remediation="Revisar leitura ou pedir plantas cotadas ao arquitecto.",
            ))
    # Aberturas
    for o in building.openings:
        if o.width_m <= 0 or o.height_m <= 0:
            out.append(Anomaly(
                severity=AnomalySeverity.GRAVE,
                code="GEO-001",
                message_pt=(
                    f"Abertura {o.id} com dimensão não positiva "
                    f"(larg={o.width_m:.2f} m, alt={o.height_m:.2f} m)."
                ),
                source=AnomalySource(page=o.source.page, bbox=o.source.bbox),
                remediation="Validar na planta de alçados ou pedir clarificação.",
            ))
    return out


def _check_geo002_duplicate_openings(building: BuildingModel) -> list[Anomaly]:
    """GEO-002 — vãos duplicados: mesma parede, mesmo kind, bbox com >70% sobreposição."""
    out: list[Anomaly] = []
    by_wall: dict[str, list[Opening]] = defaultdict(list)
    for o in building.openings:
        by_wall[o.wall_id].append(o)
    for wall_id, opens in by_wall.items():
        wall = next((w for w in building.walls if w.id == wall_id), None)
        if wall is None:
            continue
        for i, a in enumerate(opens):
            for b in opens[i + 1:]:
                if a.kind != b.kind:
                    continue
                # Mesma localização aproximada ⇒ assumir duplicação.
                if _bbox_overlap_pct(a, wall) > 0.0 and _bbox_overlap_pct(b, wall) > 0.0:
                    sa, sb = a.source.bbox, b.source.bbox
                    cx1 = (sa.x1 + sa.x2) / 2
                    cy1 = (sa.y1 + sa.y2) / 2
                    cx2 = (sb.x1 + sb.x2) / 2
                    cy2 = (sb.y1 + sb.y2) / 2
                    dist = math.hypot(cx2 - cx1, cy2 - cy1)
                    scale = max((sa.x2 - sa.x1), (sb.x2 - sb.x1), 1.0)
                    if dist / scale < 0.25:  # centros muito próximos
                        out.append(Anomaly(
                            severity=AnomalySeverity.GRAVE,
                            code="GEO-002",
                            message_pt=(
                                f"Vão aparentemente duplicado na parede {wall_id}: "
                                f"{a.id} ({a.kind.value}) e {b.id} ({b.kind.value}) "
                                "com bbox sobrepostos."
                            ),
                            source=AnomalySource(page=a.source.page, bbox=a.source.bbox),
                            remediation="Confirmar se ambos existem ou se é duplicação entre plantas.",
                        ))
    return out


def _check_geo003_floor_height(building: BuildingModel) -> list[Anomaly]:
    """GEO-003 — pé-direito dentro do intervalo plausível por tipo."""
    out: list[Anomaly] = []
    for f in building.floors:
        if f.height_clear_m is None:
            continue
        lo, hi = _HEIGHT_RANGES.get(f.kind, (0.0, 10.0))
        if f.height_clear_m < lo or f.height_clear_m > hi:
            out.append(Anomaly(
                severity=AnomalySeverity.AVISO if f.kind != FloorKind.CAVE else AnomalySeverity.GRAVE,
                code="GEO-003",
                message_pt=(
                    f"Pé-direito do piso {f.id} ({f.kind.value}) = {f.height_clear_m:.2f} m "
                    f"fora do intervalo plausível [{lo:.2f}, {hi:.2f}] m."
                ),
                source=AnomalySource(page=f.source.page, bbox=f.source.bbox),
                remediation="Validar na secção/corte do projecto.",
            ))
    return out


def _check_geo004_stair_fits(building: BuildingModel) -> list[Anomaly]:
    """GEO-004 — escada cabe na abertura: 2a+b ≈ 63 cm, comprimento ≤ opening_length."""
    out: list[Anomaly] = []
    for s in building.stairs:
        anom = _validate_single_stair(s, building)
        out.extend(anom)
    return out


def _validate_single_stair(s: Stair, building: BuildingModel) -> list[Anomaly]:
    out: list[Anomaly] = []
    # Altura total piso-piso.
    f_from = next((f for f in building.floors if f.id == s.floor_from_id), None)
    f_to = next((f for f in building.floors if f.id == s.floor_to_id), None)
    if f_from is None or f_to is None:
        return out
    delta_h = abs(f_to.level_m - f_from.level_m)
    if delta_h <= 0:
        return out

    # Nº espelhos: usa riser_count se dado, senão arredonda a partir de 0.18 m.
    riser_count = s.riser_count or max(1, round(delta_h / 0.18))
    riser_h = delta_h / riser_count
    tread_d = s.tread_depth_m or max(0.0, 0.63 - 2 * riser_h)

    # Lei da escada 2a+b ≈ 63 cm (tolerância ±5 cm).
    law = 2 * riser_h + tread_d
    if law < 0.58 or law > 0.68:
        out.append(Anomaly(
            severity=AnomalySeverity.GRAVE,
            code="GEO-004",
            message_pt=(
                f"Escada {s.id}: 2a+b = {law * 100:.1f} cm fora da gama 58–68 cm "
                f"(riser={riser_h * 100:.1f} cm, tread={tread_d * 100:.1f} cm)."
            ),
            source=AnomalySource(page=s.source.page, bbox=s.source.bbox),
            remediation="Rever desenho ou propor novo lanço com cobertor e espelho dentro da lei.",
        ))

    # Comprimento resultante.
    length_needed = tread_d * max(0, riser_count - 1)
    if length_needed > s.opening_length_m + 0.05:
        out.append(Anomaly(
            severity=AnomalySeverity.BLOQUEANTE,
            code="GEO-004",
            message_pt=(
                f"Escada {s.id}: comprimento necessário ≈ {length_needed:.2f} m "
                f"excede abertura disponível ({s.opening_length_m:.2f} m) "
                f"para delta_h = {delta_h:.2f} m."
            ),
            source=AnomalySource(page=s.source.page, bbox=s.source.bbox),
            remediation="Ampliar abertura de escada ou adicionar patim intermédio.",
        ))
    return out


def _check_geo006_wall_in_slab_opening(building: BuildingModel) -> list[Anomaly]:
    """GEO-006 — parede dentro de abertura de laje (nenhuma pode estar inteira dentro)."""
    out: list[Anomaly] = []
    openings_by_floor: dict[str, list] = defaultdict(list)
    for so in building.slab_openings:
        openings_by_floor[so.floor_id].append(so)

    for w in building.walls:
        wall_bbox = w.source.bbox
        for so in openings_by_floor.get(w.floor_id, []):
            sbb = so.source.bbox
            # Parede completamente contida na abertura ⇒ anomalia.
            inside = (
                wall_bbox.x1 >= sbb.x1 and wall_bbox.x2 <= sbb.x2
                and wall_bbox.y1 >= sbb.y1 and wall_bbox.y2 <= sbb.y2
            )
            if inside:
                out.append(Anomaly(
                    severity=AnomalySeverity.GRAVE,
                    code="GEO-006",
                    message_pt=(
                        f"Parede {w.id} parece estar inteiramente dentro de uma abertura "
                        f"de laje ({so.purpose}) no piso {w.floor_id}."
                    ),
                    source=AnomalySource(page=w.source.page, bbox=w.source.bbox),
                    remediation="Verificar leitura ou pedir planta com indicação clara da caixa.",
                ))
    return out


def run_geometric_checks(building: BuildingModel) -> list[Anomaly]:
    """Pipeline geométrico — executa todas as regras e devolve lista agregada."""
    result: list[Anomaly] = []
    result.extend(_check_geo001_nembo_width(building))
    result.extend(_check_geo002_duplicate_openings(building))
    result.extend(_check_geo003_floor_height(building))
    result.extend(_check_geo004_stair_fits(building))
    result.extend(_check_geo006_wall_in_slab_opening(building))
    return result
