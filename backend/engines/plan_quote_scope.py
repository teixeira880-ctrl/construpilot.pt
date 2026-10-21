"""Coverage of recorded takeoffs is not coverage of an entire construction project."""
import math


SCOPE_NOTICE = ("Estimativa parcial das medições guardadas, não um orçamento global da obra. Os edifícios, pisos e capítulos sem medição ou sem preço ficam por completar; uma ausência de dados não vale zero euros.")


def unique_levels(levels):
    seen, result = set(), []
    for level in levels or []:
        pid = level.get("plan_id")
        if pid not in seen:
            result.append(level)
            seen.add(pid)
    return result


def positive_quantity(measure, quantity):
    try:
        value = quantity(measure)
        if isinstance(value, bool):
            return None
        value = float(value)
    except (TypeError, ValueError, OverflowError, KeyError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def group_coverage(levels, by_id, quantity, known_poste):
    unique = unique_levels(levels)
    seen, duplicates = set(), set()
    for level in levels or []:
        pid = level.get("plan_id")
        if pid in seen:
            duplicates.add(pid)
        seen.add(pid)
    missing, empty = [], []
    measurements = unpriced = invalid = 0
    for level in unique:
        pid = level.get("plan_id")
        plan = by_id.get(pid)
        if plan is None:
            missing.append(pid)
            continue
        rows = plan.get("measurements") or []
        if not rows:
            empty.append(pid)
        for measure in rows:
            measurements += 1
            if positive_quantity(measure, quantity) is None:
                invalid += 1
            elif not measure.get("poste") or not known_poste(measure["poste"]):
                unpriced += 1
    warnings = [SCOPE_NOTICE]
    if missing:
        warnings.append(f'{len(missing)} planta(s) do grupo estão indisponíveis para esta conta.')
    if empty:
        warnings.append(f'{len(empty)} planta(s) não contêm nenhuma medição guardada.')
    if invalid:
        warnings.append(f'{invalid} medição(ões) têm uma quantidade ausente, nula ou inválida, não valorizada.')
    if unpriced:
        warnings.append(f'{unpriced} medição(ões) continuam sem artigo orçamentável.')
    if duplicates:
        warnings.append(f'{len(duplicates)} planta(s) repetida(s) no grupo são contadas uma única vez.')
    return {"status": "partial", "project_complete": False,
            "recorded_measurements_complete": bool(measurements) and not (missing or empty or invalid or unpriced),
            "plans_count": len(unique), "available_plans": len(unique)-len(missing),
            "missing_plan_ids": missing, "empty_plan_ids": empty,
            "duplicate_plan_ids": sorted(duplicates, key=str), "measurements_count": measurements,
            "unpriced_measurements": unpriced, "invalid_measurements": invalid,
            "warnings": warnings}


def finite_nonnegative(value):
    if isinstance(value, bool):
        return 0.0
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return value if math.isfinite(value) and value >= 0 else 0.0
