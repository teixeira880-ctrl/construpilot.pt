"""Coverage of recorded takeoffs is not coverage of an entire construction project."""
import math


SCOPE_NOTICE = ("Estimation partielle des mesures enregistrées, pas un budget global du chantier. "
                "Les bâtiments, niveaux et lots sans métré ou sans prix restent à compléter ; "
                "une absence de donnée ne vaut pas zéro euro.")


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
        warnings.append(f"{len(missing)} plan(s) du groupe sont indisponibles pour ce compte.")
    if empty:
        warnings.append(f"{len(empty)} plan(s) ne contiennent aucune mesure enregistrée.")
    if invalid:
        warnings.append(f"{invalid} mesure(s) ont une quantité absente, nulle ou invalide, non valorisée.")
    if unpriced:
        warnings.append(f"{unpriced} mesure(s) restent sans poste chiffrable.")
    if duplicates:
        warnings.append(f"{len(duplicates)} plan(s) répété(s) dans le groupe sont comptés une seule fois.")
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
