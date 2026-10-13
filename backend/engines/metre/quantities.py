"""Quantity engine by work category: every line carries dimensions, formula, deductions, state and missing data."""
import math

from .contracts import QuantityLine

DEDUCTION_RULES = {"full": "Déduction intégrale de toutes les ouvertures (règle sélectionnée par l'utilisateur)",
                   "none": "Aucune déduction des ouvertures (règle sélectionnée par l'utilisateur)",
                   "threshold": "Déduction des ouvertures dont la surface dépasse le seuil indiqué (règle sélectionnée par l'utilisateur)"}


def _f(v) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _num(value) -> float | None:
    try:
        number = None if value is None or isinstance(value, bool) else float(value)
        return number if number is not None and math.isfinite(number) and number >= 0 else None
    except (TypeError, ValueError):
        return None


def wall_area(item: dict) -> QuantityLine:
    length, height = _num(item.get("length_m")), _num(item.get("height_m"))
    openings = item.get("openings") or []
    rule = item.get("deduction_rule")
    base = {"element": item.get("element", "Mur"), "location": item.get("location"), "unit": "m²", "sources": item.get("sources") or [],
            "dimensions": {"length_m": length, "height_m": height, "openings": openings}}
    if length is None:
        return QuantityLine(**base, formula="—", gross=None, net=None, state="not_verifiable", reason="Longueur absente.", missing=["length_m"])
    if height is None:
        return QuantityLine(**{**base, "unit": "m"}, formula=f"L = {_f(length)} m (longueur disponible)", gross=length, net=length, state="probable",
                            reason="Hauteur absente : la surface ne peut pas être calculée, seule la longueur est fournie.", missing=["height_m"])
    if openings and rule not in DEDUCTION_RULES:
        return QuantityLine(**base, formula=f"{_f(length)} × {_f(height)} = {_f(length * height)} m² (brut)", gross=round(length * height, 3), net=None,
                            state="indeterminate", reason="Ouvertures présentes mais règle de déduction non sélectionnée : surface nette non calculée.",
                            missing=["deduction_rule"])
    gross = round(length * height, 3)
    deductions, threshold = [], _num(item.get("deduction_threshold_m2"))
    if openings and rule == "threshold" and threshold is None:
        return QuantityLine(**base, formula="Seuil de déduction manquant", gross=gross, net=None,
                            state="indeterminate", reason="Le seuil doit être défini avant le calcul net.",
                            missing=["deduction_threshold_m2"])
    for op in openings:
        w, h = _num(op.get("width_m")), _num(op.get("height_m"))
        count = _num(op.get("count", 1))
        if w is None or h is None or count is None or count < 1 or not count.is_integer():
            deductions.append({"label": op.get("label", "ouverture"), "area_m2": None, "applied": False, "reason": "dimensions incomplètes"})
            continue
        area = round(w * h * count, 3)
        applied = rule == "full" or (rule == "threshold" and w * h > threshold)
        deductions.append({"label": op.get("label", "ouverture"), "formula": f"{_f(w)} × {_f(h)} × {_f(count)} = {_f(area)} m²", "area_m2": area, "applied": applied})
    deducted = round(sum(d["area_m2"] for d in deductions if d.get("applied")), 3)
    net = round(gross - deducted, 3)
    extra = _num(item.get("extra_pct"))
    order = round(net * (1 + extra / 100), 3) if extra is not None else None
    incomplete = [d for d in deductions if d.get("area_m2") is None]
    invalid = (bool(incomplete) and rule != "none") or net < 0 or (item.get("extra_pct") is not None and extra is None)
    return QuantityLine(**base, formula=f"{_f(length)} × {_f(height)} = {_f(gross)} m² − {_f(deducted)} m² = {_f(net)} m²", gross=gross,
                        deductions=deductions, net=None if invalid else net, extra_pct=extra, order_qty=None if invalid else order, rule=DEDUCTION_RULES.get(rule, "sans ouverture"),
                        state="indeterminate" if invalid else "confirmed",
                        reason="Dimensions, pertes ou déductions incohérentes : quantité nette à vérifier." if invalid else
                        ("Perte appliquée uniquement car explicitement demandée." if extra is not None else "Aucune perte ajoutée sans règle explicite."))


def concrete_volume(item: dict) -> QuantityLine:
    area, l, w, h = _num(item.get("area_m2")), _num(item.get("length_m")), _num(item.get("width_m")), _num(item.get("height_m"))
    base = {"element": item.get("element", "Béton"), "location": item.get("location"), "unit": "m³", "sources": item.get("sources") or [],
            "dimensions": {"area_m2": area, "length_m": l, "width_m": w, "height_m": h}}
    footprint = area if area is not None else (l * w if l is not None and w is not None else None)
    if footprint is None:
        return QuantityLine(**base, formula="—", gross=None, net=None, state="not_verifiable", reason="Emprise (surface ou L × l) absente.",
                            missing=[k for k in ("area_m2", "length_m", "width_m") if base["dimensions"][k] is None])
    if h is None:
        return QuantityLine(**{**base, "unit": "m²"}, formula=f"Emprise = {_f(footprint)} m²", gross=round(footprint, 3), net=round(footprint, 3), state="probable",
                            reason="Hauteur / épaisseur absente : un contour 2D ne définit pas le volume.", missing=["height_m"])
    vol = round(footprint * h, 3)
    return QuantityLine(**base, formula=f"{_f(footprint)} m² × {_f(h)} m = {_f(vol)} m³", gross=vol, net=vol, state="confirmed",
                        reason="Volume géométrique sans recouvrement avec d'autres éléments (à vérifier si éléments adjacents).")


def roof_area(item: dict) -> QuantityLine:
    plan, slope = _num(item.get("plan_area_m2")), _num(item.get("slope_deg"))
    base = {"element": item.get("element", "Couverture"), "location": item.get("location"), "unit": "m²", "sources": item.get("sources") or [],
            "dimensions": {"plan_area_m2": plan, "slope_deg": slope}}
    if plan is None:
        return QuantityLine(**base, formula="—", gross=None, net=None, state="not_verifiable", reason="Surface en plan absente.", missing=["plan_area_m2"])
    if slope is None:
        return QuantityLine(**base, formula=f"Surface projetée = {_f(plan)} m²", gross=plan, net=plan, state="probable",
                            reason="Pente inconnue : surface projetée uniquement, la surface réelle (rampante) n'est pas déduite.", missing=["slope_deg"])
    if slope >= 90:
        return QuantityLine(**base, formula="—", gross=None, net=None, state="not_verifiable",
                            reason="La pente doit être comprise entre 0° inclus et 90° exclus.", missing=["slope_deg"])
    real = round(plan / math.cos(math.radians(slope)), 3)
    return QuantityLine(**base, formula=f"{_f(plan)} / cos({_f(slope)}°) = {_f(real)} m²", gross=real, net=real, state="confirmed",
                        reason="Surface rampante calculée à partir de la pente déclarée.")


def packaged_units(item: dict) -> QuantityLine:
    net, per_unit, pack = _num(item.get("net_quantity")), _num(item.get("units_per_measure")), _num(item.get("pack_size"))
    waste = _num(item.get("waste_pct"))
    base = {"element": item.get("element", "Produit"), "location": item.get("location"), "unit": item.get("unit", "u"), "sources": item.get("sources") or [],
            "dimensions": {"net_quantity": net, "units_per_measure": per_unit, "pack_size": pack, "waste_pct": waste, "product": item.get("product")}}
    if net is None or per_unit is None:
        return QuantityLine(**base, formula="—", gross=None, net=None, state="not_verifiable", reason="Quantité nette ou rendement du produit absent.",
                            missing=[k for k, v in (("net_quantity", net), ("units_per_measure", per_unit)) if v is None])
    invalid = [k for k, v in (("pack_size", pack), ("waste_pct", waste))
               if item.get(k) is not None and (v is None or (k == "pack_size" and v == 0))]
    if invalid:
        return QuantityLine(**base, formula="—", gross=None, net=None, state="not_verifiable",
                            reason="Conditionnement ou taux de perte invalide.", missing=invalid)
    installed = round(net * per_unit, 3)
    with_waste = installed * (1 + waste / 100) if waste is not None else installed
    order = math.ceil(with_waste / pack) * pack if pack else math.ceil(with_waste)
    formula = f"{_f(net)} × {_f(per_unit)} = {_f(installed)} u" + (f" × (1 + {_f(waste)} %)" if waste is not None else "") + \
              (f" → arrondi au conditionnement de {_f(pack)} = {order} u" if pack else f" → arrondi = {order} u")
    return QuantityLine(**base, formula=formula, gross=installed, net=installed, extra_pct=waste, order_qty=order, state="confirmed",
                        reason="Quantité posée et quantité à commander distinguées ; perte appliquée uniquement si fournie.")


CATEGORIES = {"wall_area": wall_area, "concrete_volume": concrete_volume, "roof_area": roof_area, "packaged_units": packaged_units}


def calculate_quantities(items: list[dict]) -> dict:
    lines, unsupported = [], []
    for item in items:
        fn = CATEGORIES.get(item.get("category"))
        if not fn:
            unsupported.append(item.get("category"))
            continue
        lines.append(fn(item).model_dump())
    totals = {}
    for line in lines:
        if line["net"] is not None and line["state"] == "confirmed":
            totals[line["unit"]] = round(totals.get(line["unit"], 0) + line["net"], 3)
    return {"lines": lines, "totals_confirmed": totals, "unsupported_categories": unsupported,
            "note": "Les prix restent séparés des quantités. Les lignes non confirmées ne sont pas totalisées."}

