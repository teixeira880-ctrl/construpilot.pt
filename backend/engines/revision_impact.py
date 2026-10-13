"""Revision deltas share the quantity basis used in generated quotes."""
from engines.chantier_costs import number
from engines.assistant_quote_pricing import unit_key


def revision_delta(before, after, price=None):
    va = number(before.get("quantity_net")) if before else 0
    vb = number(after.get("quantity_net")) if after else 0
    compatible = not before or not after or unit_key(before.get("unit")) == unit_key(after.get("unit"))
    delta = round(vb - va, 3) if compatible and va is not None and vb is not None else None
    # quote-draft uses quantities to order (includes declared waste), not net quantities.
    oa = number(before.get("quantity_to_order")) if before else 0
    ob = number(after.get("quantity_to_order")) if after else 0
    billed = round(ob - oa, 3) if compatible and oa is not None and ob is not None else None
    kind = "ajoutée" if not before else "supprimée" if not after else "indéterminée" if delta is None else "inchangée" if delta == 0 and billed in (0, None) else "modifiée"
    price = price or {}
    unit = (after or before)["unit"]
    valid_price = not price.get("ambiguous") and unit_key(price.get("unit")) == unit_key(unit) and price.get("unit_price_ht") is not None
    # Manually changed quote quantities are not silently treated as the source reference.
    matches_reference = before is None or (number(price.get("quantity")) is not None and oa is not None and abs(price["quantity"] - oa) < 0.0011)
    impact = round(billed * price["unit_price_ht"], 2) if valid_price and matches_reference and billed is not None else None
    return {"before": va if before else None, "after": vb if after else None, "delta": delta,
            "delta_to_order": billed, "kind": kind, "impact_ht": impact,
            "pricing_usable": valid_price and matches_reference and billed is not None}
