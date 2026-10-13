"""Cross-checks between the two slab reinforcement layers (nappe inférieure / supérieure) and the formwork plan of the same level.

No geometric overlay is attempted when the PDFs carry no grid axes: the comparison is made on printed lists (marks, panel areas)
and on the slab area rebuilt from the DXF. Every figure is traceable to a printed row or a closed face.
"""
from collections import defaultdict


def _panel_area_rows(mesh: dict | None) -> tuple[float, int]:
    """Laid panel area from the nomenclature cuts (count × w × h) — pieces actually placed, before overlaps."""
    area, pieces = 0.0, 0
    for r in (mesh or {}).get("rows", []):
        for c in r.get("cuts", []):
            n = c["count"] * (r.get("total_count") or 1)
            area += n * c["width_cm"] / 100 * c["height_cm"] / 100
            pieces += n
    return round(area, 1), pieces


def _recap_area(recap: dict | None) -> float:
    return round(sum((r.get("count") or 0) * r["width_cm"] / 100 * r["height_cm"] / 100 for r in (recap or {}).get("rows", []) if r.get("width_cm")), 1)


def cross_nappes(lower: dict, upper: dict, *, slab_area_m2: float | None, labels=("nappe inférieure", "nappe supérieure")) -> dict:
    out = {"layers": {}, "duplicates": {}, "coverage": [], "findings": []}
    for label, res in zip(labels, (lower, upper)):
        mesh, recap, ha = res.get("mesh"), res.get("mesh_recap"), res.get("ha_bars")
        laid_area, pieces = _panel_area_rows(mesh)
        out["layers"][label] = {"mesh_rows": (mesh or {}).get("count"), "mesh_laid_kg": (recap or {}).get("mass_laid_kg"), "mesh_pieces_from_cuts": pieces,
                                "mesh_laid_area_m2_from_cuts": laid_area, "mesh_ordered_area_m2_from_recap": _recap_area(recap),
                                "ha_rows": (ha or {}).get("count"), "ha_mass_kg": (ha or {}).get("total_mass_kg"), "partial": res.get("partial")}
    marks = {}
    for label, res in zip(labels, (lower, upper)):
        marks[label] = {"mesh": {r["mark"]: r for r in (res.get("mesh") or {}).get("rows", [])}, "ha": {r["mark"]: r for r in (res.get("ha_bars") or {}).get("rows", [])}}
    for kind in ("mesh", "ha"):
        common = sorted(set(marks[labels[0]][kind]) & set(marks[labels[1]][kind]), key=lambda m: (len(m), m))
        same, differ = [], []
        for m in common:
            a, b = marks[labels[0]][kind][m], marks[labels[1]][kind][m]
            key = ("panel", "mass_kg") if kind == "mesh" else ("diameter_mm", "unit_length_cm", "total_count")
            (same if all(a.get(k) == b.get(k) for k in key) else differ).append({"mark": m, labels[0]: {k: a.get(k) for k in key}, labels[1]: {k: b.get(k) for k in key}})
        out["duplicates"][kind] = {"common_marks": len(common), "identical": len(same), "different": differ}
        if differ:
            out["findings"].append({"severity": "to_clarify", "subject": f"Repères {kind.upper()} communs aux deux nappes avec valeurs différentes",
                                    "explanation": f"{len(differ)} repère(s) portent le même numéro sur les deux plans avec des caractéristiques différentes : "
                                                   + ", ".join(d["mark"] for d in differ[:8]) + ". Numérotation par plan (normal) ou erreur de repère : à confirmer avec le BET."})
    if slab_area_m2:
        for label, info in out["layers"].items():
            for key, name in (("mesh_laid_area_m2_from_cuts", "surface posée (découpes de la nomenclature)"), ("mesh_ordered_area_m2_from_recap", "surface commandée (récapitulatif)")):
                area = info[key]
                if area:
                    out["coverage"].append({"layer": label, "quantity": name, "area_m2": area, "slab_area_m2": slab_area_m2, "ratio": round(area / slab_area_m2, 3),
                                            "note": "ratio < 1 attendu (zones sans treillis : poutres, poteaux, nomenclature partielle) ; ratio > 1 = recouvrements/chutes"})
        low_cov = [c for c in out["coverage"] if "posée" in c["quantity"] and c["ratio"] < 0.6]
        if low_cov:
            out["findings"].append({"severity": "to_clarify", "subject": "Couverture treillis faible vs dalle",
                                    "explanation": "; ".join(f"{c['layer']} : {c['area_m2']} m² posés pour {slab_area_m2} m² de dalle (ratio {c['ratio']})" for c in low_cov)
                                    + ". Nomenclatures marquées « partielle » : la couverture réelle ne peut pas être conclue à partir de ces seules feuilles."})
    out["note"] = ("Les PDF de ferraillage ne portent pas d'axes de quadrillage (X/Y) : pas de superposition géométrique possible avec le DWG ; "
                   "comparaison par listes (repères, masses, surfaces) uniquement.")
    return out
