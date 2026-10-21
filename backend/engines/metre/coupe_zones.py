"""Links every section trace located on the formwork plan to the model (DXF) through the grid registration: elements crossed by the trace,
zone of influence, and the base level / wall thickness that the section sheet prints for that zone. Wall heights then follow the user's
rule (AS murs = AI plancher haut) zone by zone instead of one average."""
import math
import re
from collections import Counter

from shapely.geometry import LineString, Polygon, box

from engines.metre.grid_align import to_model

ZONE_REACH_M = 8.0
LABEL = re.compile(r"^(T|PV|L|BN|Tr|P|VB|VH|PLB|RES)\d+\.\d+$")


def plan_extent_polygon(page, reg: dict, margin_m: float = 2.5) -> Polygon:
    """Model-space footprint of the plan view = bbox of the element labels of the drawn building (T3.x, PV3.x, L3.x…), margin added."""
    words = [w for w in page.get_text("words") if LABEL.match(w[4])]
    if not words:
        return None
    pts = [to_model(reg, (w[0] + w[2]) / 2, (w[1] + w[3]) / 2) for w in words]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return box(min(xs) - margin_m, min(ys) - margin_m, max(xs) + margin_m, max(ys) + margin_m)


def traces_to_model(coupes: list[dict], reg: dict) -> list[dict]:
    out = []
    for c in coupes:
        a, b = to_model(reg, *c["a_pt"]), to_model(reg, *c["b_pt"])
        out.append({**{k: v for k, v in c.items() if k not in ("a_pt", "b_pt", "midpoint_pt")}, "a_m": [round(a[0], 2), round(a[1], 2)], "b_m": [round(b[0], 2), round(b[1], 2)],
                    "line": LineString([a, b])})
    return out


def coupe_sheet_data(coupes_result: dict | None) -> dict:
    """name → printed levels/thicknesses of that section (from the stored transcription, deterministic checks included)."""
    data = {}
    dominant_base = (((coupes_result or {}).get("summary") or {}).get("dominant") or {}).get("niveau_base_murs_m")
    for s in (coupes_result or {}).get("sheets", []):
        for c in s.get("coupes_checked", []):
            if not c.get("name"):
                continue
            heights = c.get("heights") or []
            base = Counter(h["base_level_m"] for h in heights)
            chosen = _choose_height(heights, dominant_base)
            data[c["name"]] = {"as_plancher_haut_m": c.get("as_plancher_haut_m"), "ai_plancher_haut_m": c.get("ai_plancher_haut_m"),
                               "slab_thickness_cm": c.get("slab_thickness_cm") or [], "wall_thickness_cm": c.get("wall_thickness_cm") or [],
                               "base_levels_m": sorted(base), "heights": heights,
                               "h_mur_m": chosen["h_mur_m"] if chosen else None, "base_used_m": chosen["base_level_m"] if chosen else None,
                               "chain_proof": bool(chosen and chosen.get("chain_proof_cm")),
                               "single_base": (max(base) - min(base)) <= 0.02 if base else False, "page": s.get("page")}
    return data


def _choose_height(heights: list[dict], dominant_base: float | None):
    """Several printed base levels on one section: keep the one proven by the vertical chain and closest to the level's dominant base."""
    if not heights:
        return None
    ref = dominant_base if dominant_base is not None else min(h["base_level_m"] for h in heights)
    return min(heights, key=lambda h: (0 if h.get("chain_proof_cm") else 1, abs(h["base_level_m"] - ref)))


def link_coupes(traces: list[dict], geometry: dict, sheet_data: dict) -> list[dict]:
    """Elements crossed by each trace (walls / beams / columns of the model) + section data of the same name."""
    out = []
    for t in traces:
        corridor = t["line"].buffer(0.05)
        crossed_walls = [i for i, w in enumerate(geometry["wall_bodies"]) if w.intersects(corridor)]
        crossed_beams = [i for i, b in enumerate(geometry["beams"]) if b.intersects(corridor)]
        crossed_cols = [i for i, c in enumerate(geometry["columns"]) if c.intersects(corridor)]
        thick = sorted({round(_thickness(geometry["wall_bodies"][i]) * 100) for i in crossed_walls})
        sd = sheet_data.get(t["name"])
        row = {"name": t["name"], "instance": t["instance"], "a_m": t["a_m"], "b_m": t["b_m"], "length_m": round(t["line"].length, 2),
               "walls_crossed": len(crossed_walls), "wall_thicknesses_dxf_cm": thick, "beams_crossed": len(crossed_beams), "columns_crossed": len(crossed_cols),
               "sheet": None, "thickness_check": None}
        if sd:
            row["sheet"] = {k: sd[k] for k in ("as_plancher_haut_m", "ai_plancher_haut_m", "slab_thickness_cm", "wall_thickness_cm", "base_levels_m", "base_used_m", "h_mur_m", "chain_proof", "single_base", "page")}
            common = set(thick) & {round(v) for v in sd["wall_thickness_cm"]}
            row["thickness_check"] = {"state": "confirmed" if common else ("to_clarify" if thick and sd["wall_thickness_cm"] else "indeterminate"), "common_cm": sorted(common)}
        out.append(row)
    return out


def _thickness(poly: Polygon) -> float:
    rect = poly.minimum_rotated_rectangle
    xs, ys = rect.exterior.coords.xy
    return min(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(2))


def assign_wall_zones(wall_bodies: list[Polygon], traces: list[dict], sheet_data: dict, *, default_h_m: float | None, extent: Polygon | None) -> dict:
    """Each wall body takes the height of the nearest section (same name → same printed base level) within ZONE_REACH_M; otherwise the default height."""
    zones, rows = Counter(), []
    vol_conf = vol_clar = 0.0
    inside = 0
    for i, w in enumerate(wall_bodies):
        if extent is not None and not extent.contains(w.centroid):
            continue
        inside += 1
        t = _thickness(w)
        best = min(((tr["line"].distance(w.centroid), tr) for tr in traces), key=lambda x: x[0], default=(None, None))
        dist, tr = best
        sd = sheet_data.get(tr["name"]) if tr and dist is not None and dist <= ZONE_REACH_M else None
        h = sd["h_mur_m"] if sd and sd.get("h_mur_m") else default_h_m
        if h is None or not math.isfinite(h) or h <= 0:
            continue
        state = "confirmed" if sd and sd.get("h_mur_m") and sd["single_base"] and sd["chain_proof"] else "to_clarify"
        v = w.area * h
        if state == "confirmed":
            vol_conf += v
        else:
            vol_clar += v
        key = tr["name"] if sd else "sem corte (altura dominante)"
        zones[key] += v
        rows.append({"wall_index": i, "thickness_cm": round(t * 100), "plan_area_m2": round(w.area, 3), "coupe": tr["name"] if sd else None, "distance_m": round(dist, 2) if dist is not None else None,
                     "h_m": round(h, 3), "base_level_m": sd["base_used_m"] if sd else None, "volume_m3": round(v, 3), "state": state})
    return {"walls_in_extent": inside, "walls_missing_height": inside - len(rows),
            "rows": rows, "volume_by_coupe_m3": {k: round(v, 2) for k, v in zones.most_common()},
            "volume_confirmed_m3": round(vol_conf, 2), "volume_to_clarify_m3": round(vol_clar, 2), "volume_total_m3": round(vol_conf + vol_clar, 2),
            "note": f'Altura de cada corpo de parede = AI do pavimento superior − nível de base impresso no corte mais próximo (≤ {ZONE_REACH_M:g} m); sem corte ao alcance, altura dominante (a esclarecer).'}


def clip_elements(geometry: dict, extent: Polygon | None) -> dict:
    """Plan quantities restricted to the plan footprint (the DXF may hold the whole level of several buildings)."""
    if extent is None:
        return {"clipped": False}
    cols = [c for c in geometry["columns"] if extent.contains(c.centroid)]
    beams = [b for b in geometry["beams"] if extent.contains(b.centroid)]
    slab = geometry["slab"].intersection(extent) if geometry.get("slab") is not None else None
    return {"clipped": True, "extent_m": [round(v, 2) for v in extent.bounds], "columns": {"count": len(cols), "section_total_m2": round(sum(c.area for c in cols), 3)},
            "beams": {"count": len(beams), "length_total_m": round(sum(_length(b) for b in beams), 2)},
            "slab": {"net_area_m2": round(slab.area, 2)} if slab is not None and not slab.is_empty else None,
            "columns_geoms": cols, "beams_geoms": beams}


def _length(poly: Polygon) -> float:
    rect = poly.minimum_rotated_rectangle
    xs, ys = rect.exterior.coords.xy
    return max(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]) for i in range(2))

