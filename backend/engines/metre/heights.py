"""Heights from levels — rule stated by the user (15/09/2026): « l'arase supérieure des murs est l'arase inférieure du plancher, sauf
indication contraire ». Volumes are only produced when the levels are supplied (title block / coffrage PDF / user); nothing is assumed.

levels = {"as_plancher_haut_m": 93.55, "epaisseur_dalle_m": 0.20, "niveau_base_murs_m": 89.50, "source": "PDF coffrage PH RDC ind. 0"}
"""
import math


def _finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def derive_heights(levels: dict) -> dict:
    as_ph, ep, base = (_finite(levels.get(k)) for k in
                       ("as_plancher_haut_m", "epaisseur_dalle_m", "niveau_base_murs_m"))
    ai_ph = _finite(levels.get("ai_plancher_haut_m"))
    if ep is not None and ep <= 0:
        ep = None
    if ai_ph is None and as_ph is not None and ep is not None:
        ai_ph = round(as_ph - ep, 3)
    out = {"ai_plancher_haut_m": ai_ph, "as_murs_m": ai_ph, "rule": "AS paredes = AI pavimento superior (salvo indicação em contrário)", "source": levels.get("source"),
           "exceptions": levels.get("exceptions", [])}
    out["h_murs_m"] = round(ai_ph - base, 3) if ai_ph is not None and base is not None else None
    invalid_height = out["h_murs_m"] is not None and out["h_murs_m"] <= 0
    if invalid_height:
        out["h_murs_m"] = None
    out["h_poteaux_m"] = out["h_murs_m"]
    out["epaisseur_dalle_m"] = ep
    out["missing"] = [k for k, v in (("AI pavimento superior (ou AS + espessura)", ai_ph), ("nível de base das paredes", base), ("espessura da laje", ep)) if v is None]
    if invalid_height:
        out["missing"].append("nível de base inferior à cota das paredes")
    return out


def volumes_from_takeoff(takeoff: dict, levels: dict, beams_pairing: dict | None = None) -> dict:
    h = derive_heights(levels)
    e = takeoff["elements"]
    lines, total = [], 0.0
    if h["h_murs_m"] is not None and e.get("walls"):
        v = e["walls"]["plan_area_m2"] * h["h_murs_m"]
        total += v
        lines.append({"element": "Paredes — volume de betão", "formula": f"Σ(L × e) {e['walls']['plan_area_m2']:.2f} m² × h {h['h_murs_m']:.2f} m (AS paredes = AI pavimento {h['ai_plancher_haut_m']:.2f} − base {levels['niveau_base_murs_m']:.2f})",
                      "net": round(v, 2), "unit": "m³", "state": "confirmed" if not h["exceptions"] else "to_clarify"})
    if h["h_poteaux_m"] is not None and e.get("columns"):
        v = e["columns"]["section_total_m2"] * h["h_poteaux_m"]
        total += v
        lines.append({"element": "Pilares — volume de betão", "formula": f"Σ secções {e['columns']['section_total_m2']:.3f} m² × h {h['h_poteaux_m']:.2f} m", "net": round(v, 2), "unit": "m³", "state": "confirmed"})
    if h["epaisseur_dalle_m"] is not None and e.get("slab"):
        v = e["slab"]["net_area_m2"] * h["epaisseur_dalle_m"]
        total += v
        lines.append({"element": "Laje — volume de betão", "formula": f"área líquida {e['slab']['net_area_m2']:.2f} m² × ép. {h['epaisseur_dalle_m']:.2f} m", "net": round(v, 2), "unit": "m³", "state": "confirmed"})
    if beams_pairing and h["epaisseur_dalle_m"] is not None:
        drop = 0.0
        for r in beams_pairing.get("rows", []):
            d = r.get("dxf")
            if d and r.get("h_cm"):
                retombee = r["h_cm"] / 100 - h["epaisseur_dalle_m"]
                if retombee > 0:
                    drop += d["length_m"] * d["width_m"] * retombee
        if drop:
            total += drop
            lines.append({"element": "Vigas emparelhadas — alturas abaixo da laje", "formula": "Σ C_dxf × b × (h Arche − esp. laje)", "net": round(drop, 2), "unit": "m³", "state": "confirmed"})
    for miss in h["missing"]:
        lines.append({"element": f'Volumes — dado em falta: {miss}', "formula": None, "net": None, "unit": "m³", "state": "indeterminate", "missing": [miss]})
    return {"heights": h, "lines": lines, "total_m3": round(total, 2)
            if lines and not h["missing"] and all(line["state"] == "confirmed" for line in lines) else None}

