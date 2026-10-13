"""Stroke classification (not every line is a wall) and cross-view deduplication of observed elements."""
from collections import defaultdict

from .contracts import new_id

NON_CONSTRUCTIVE = {"hatch", "furniture", "axis", "dimension_line", "extension_line", "text", "leader", "property_limit",
                    "hidden", "network", "detail_boundary", "grid", "north_arrow", "title_block"}
CONSTRUCTIVE = {"wall", "partition", "column", "beam", "slab", "footing", "door", "window", "stair", "roof", "insulation",
                "waterproofing", "opening"}
LAYER_HINTS = {"hatch": ("hach", "hatch", "poch"), "furniture": ("mobil", "furn", "sanit", "equip"), "axis": ("axe", "axis", "trame", "grid"),
               "dimension_line": ("cote", "cota", "dim"), "text": ("text", "txt", "annot"), "hidden": ("cache", "hidden", "pointill"),
               "network": ("reseau", "elec", "plomb", "vmc", "cvc", "eu", "ep"), "wall": ("mur", "wall", "voile", "cloison", "parede")}


def classify_stroke(stroke: dict) -> dict:
    """Rule-based classification from declared kind, layer name, pattern and line style. Unknown → 'unclassified'."""
    kind = (stroke.get("kind") or "").lower()
    if kind in NON_CONSTRUCTIVE or kind in CONSTRUCTIVE:
        return {**stroke, "classification": kind, "constructive": kind in CONSTRUCTIVE, "basis": "declared_kind"}
    layer = (stroke.get("layer") or "").lower()
    for label, hints in LAYER_HINTS.items():
        if any(h in layer for h in hints):
            return {**stroke, "classification": label, "constructive": label in CONSTRUCTIVE, "basis": f"layer:{layer}"}
    pattern = (stroke.get("pattern") or "").lower()
    if pattern in ("dashed", "dash", "dotted", "dashdot"):
        return {**stroke, "classification": "hidden", "constructive": False, "basis": "line_pattern"}
    if stroke.get("has_arrowheads") or stroke.get("has_ticks"):
        return {**stroke, "classification": "dimension_line", "constructive": False, "basis": "arrowheads"}
    if pattern in ("hatch", "cross", "diagonal"):
        return {**stroke, "classification": "hatch", "constructive": False, "basis": "fill_pattern"}
    return {**stroke, "classification": "unclassified", "constructive": False, "basis": "no_evidence"}


def classify_strokes(strokes: list[dict]) -> dict:
    classified = [classify_stroke(s) for s in strokes]
    counts = defaultdict(int)
    for s in classified:
        counts[s["classification"]] += 1
    return {"strokes": classified, "counts": dict(counts),
            "constructive_count": sum(1 for s in classified if s["constructive"]),
            "note": "Seuls les traits classés constructifs alimentent les quantités ; « unclassified » reste hors métré."}


def _same_location(a: dict, b: dict, tol_m: float) -> bool:
    la, lb = a.get("location") or {}, b.get("location") or {}
    if la.get("level") and lb.get("level") and la["level"] != lb["level"]:
        return False
    if la.get("x_m") is None or lb.get("x_m") is None or la.get("y_m") is None or lb.get("y_m") is None:
        return False
    return abs(la["x_m"] - lb["x_m"]) <= tol_m and abs(la["y_m"] - lb["y_m"]) <= tol_m


def _dims_compatible(a: dict, b: dict) -> bool:
    da, db_ = a.get("dimensions") or {}, b.get("dimensions") or {}
    for key in set(da) & set(db_):
        try:
            if abs(float(da[key]) - float(db_[key])) > 0.02:
                return False
        except (TypeError, ValueError):
            continue
    return True


def dedupe_elements(observations: list[dict], *, location_tol_m: float = 0.3) -> dict:
    """Groups observations of the same element seen in plan, elevation, schedule or detail.

    Identity: same element_type + same tag (F1, P02…). Without tag: same level and position within tolerance.
    Anything else with the same type and compatible dimensions but no proof of identity → uncertain group.
    """
    by_tag = defaultdict(list)
    untagged = []
    for o in observations:
        tag = (o.get("tag") or "").strip().upper()
        if tag:
            by_tag[(o.get("element_type"), tag)].append(o)
        else:
            untagged.append(o)
    elements, uncertain = [], []
    for (etype, tag), group in by_tag.items():
        compatible = all(_dims_compatible(group[0], g) for g in group[1:])
        elements.append({"element_id": new_id("el"), "element_type": etype, "tag": tag, "count": 1,
                         "views": sorted({g.get("view") for g in group if g.get("view")}),
                         "evidence": [g.get("obs_id") for g in group], "dimensions": group[0].get("dimensions") or {},
                         "state": "confirmed" if compatible else "indeterminate",
                         "note": None if compatible else "Dimensions divergentes entre vues : identité à confirmer"})
    located = [o for o in untagged if (o.get("location") or {}).get("x_m") is not None]
    floating = [o for o in untagged if o not in located]
    while located:
        head = located.pop(0)
        group = [head]
        for other in list(located):
            if other.get("element_type") == head.get("element_type") and _same_location(head, other, location_tol_m):
                group.append(other)
                located.remove(other)
        elements.append({"element_id": new_id("el"), "element_type": head.get("element_type"), "tag": None, "count": 1,
                         "views": sorted({g.get("view") for g in group if g.get("view")}), "evidence": [g.get("obs_id") for g in group],
                         "dimensions": head.get("dimensions") or {}, "state": "probable", "note": "Identité par position (sans repère)"})
    # Untagged AND unlocated observations (e.g. a schedule row) matching a known element are kept as uncertain, never counted twice.
    for o in floating:
        twins = [el for el in elements if el["element_type"] == o.get("element_type") and _dims_compatible({"dimensions": el["dimensions"]}, o)]
        if twins:
            uncertain.append({"obs_id": o.get("obs_id"), "element_type": o.get("element_type"), "view": o.get("view"),
                              "possible_elements": [t["element_id"] for t in twins], "reason": "Même type et dimensions compatibles, sans repère ni position"})
        else:
            elements.append({"element_id": new_id("el"), "element_type": o.get("element_type"), "tag": None, "count": 1,
                             "views": [o.get("view")] if o.get("view") else [], "evidence": [o.get("obs_id")],
                             "dimensions": o.get("dimensions") or {}, "state": "indeterminate", "note": "Observation isolée sans repère ni position"})
    counts = defaultdict(int)
    for el in elements:
        counts[el["element_type"]] += el["count"]
    return {"elements": elements, "uncertain_groups": uncertain, "counts": dict(counts),
            "note": "Chaque élément est compté une fois ; les vues (plan, élévation, nomenclature) restent comme preuves."}
