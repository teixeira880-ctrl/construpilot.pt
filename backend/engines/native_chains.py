"""Native CAD dimension chains: groups collinear DXF dimensions into chains and checks them against overall dimensions."""
import math

from engines.metre import chains as chain_engine

ANGLE_TOL_DEG = 1.5
OVERRIDE_TOL_M = 0.005


def _dir(d):
    dx, dy = d["x2"] - d["x1"], d["y2"] - d["y1"]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _angle(d):
    ux, uy = _dir(d)
    return math.degrees(math.atan2(uy, ux)) % 180.0


def _offset(d, ux, uy):
    # signed distance of the dimension line from the origin along the normal
    return -uy * d["x1"] + ux * d["y1"]


def _reading(d, idx, plan_id, page, size):
    w, h = size
    box = [min(d["x1"], d["x2"]) / w, min(d["y1"], d["y2"]) / h, max(d["x1"], d["x2"]) / w, max(d["y1"], d["y2"]) / h] if w and h else None
    return {"label": f"D{idx}", "value_m": round(d["value_m"], 4), "candidates_m": [], "origin": "native_text", "plan_id": plan_id, "page": page,
            "box": [round(v, 4) for v in box] if box else None}


def build_chains(dims: list[dict], *, px_per_m: float, plan_id: str | None = None, page: int = 0, size=(0, 0), max_chains: int = 40) -> dict:
    """Consecutive collinear dimensions sharing endpoints form a chain; a parallel dimension spanning the same interval is its declared total."""
    if not dims or px_per_m <= 0:
        return {"chains": [], "overrides": [], "note": "Aucune cote native linéaire exploitable."}
    join_tol = 0.02 * px_per_m  # 2 cm in drawing units, whatever the render scale
    indexed = [{**d, "idx": i + 1} for i, d in enumerate(dims)]
    overrides = [{"label": f"D{d['idx']}", "text": d.get("raw_text"), "value_m": d["value_m"], "measured_m": d["measured_m"],
                  "difference_m": round(d["value_m"] - d["measured_m"], 4)}
                 for d in indexed if d.get("override") and abs(d["value_m"] - d["measured_m"]) > OVERRIDE_TOL_M]
    # bucket by direction and dimension-line offset
    lines = []
    for d in indexed:
        ang = _angle(d)
        ux, uy = _dir(d)
        if ux < 0 or (ux == 0 and uy < 0):
            ux, uy = -ux, -uy
        off = _offset(d, ux, uy)
        for line in lines:
            if abs(((line["angle"] - ang + 90) % 180) - 90) <= ANGLE_TOL_DEG and abs(line["offset"] - off) <= join_tol:
                line["dims"].append(d)
                break
        else:
            lines.append({"angle": ang, "ux": ux, "uy": uy, "offset": off, "dims": [d]})
    for line in lines:
        ux, uy = line["ux"], line["uy"]
        for d in line["dims"]:
            t1, t2 = d["x1"] * ux + d["y1"] * uy, d["x2"] * ux + d["y2"] * uy
            d["t_start"], d["t_end"] = min(t1, t2), max(t1, t2)
        line["dims"].sort(key=lambda d: d["t_start"])
    chains = []
    for line in lines:
        run = []
        for d in line["dims"] + [None]:
            if d is not None and (not run or abs(d["t_start"] - run[-1]["t_end"]) <= join_tol):
                run.append(d)
                continue
            if len(run) >= 2:
                chains.append({"line": line, "segments": run})
            run = [d] if d is not None else []
    results = []
    chains.sort(key=lambda c: -len(c["segments"]))
    for chain in chains:
        line, segs = chain["line"], chain["segments"]
        start, end = segs[0]["t_start"], segs[-1]["t_end"]
        total = None
        for other in lines:
            if other is line or abs(((other["angle"] - line["angle"] + 90) % 180) - 90) > ANGLE_TOL_DEG:
                continue
            for d in other["dims"]:
                if abs(d["t_start"] - start) <= join_tol and abs(d["t_end"] - end) <= join_tol:
                    total = d
                    break
            if total:
                break
        spans = [_reading(d, d["idx"], plan_id, page, size) for d in segs]
        declared = _reading(total, total["idx"], plan_id, page, size) if total else None
        if declared:
            declared["label"] = f"Total D{total['idx']}"
        check = chain_engine.check_dimension_chain(spans=spans, thicknesses=[], chain_includes_thickness=True, declared_total=declared)
        results.append({"chain_id": f"CH-{len(results) + 1:02d}", "direction_deg": round(line["angle"], 1), "segments": spans,
                        "declared_total": declared, "geometric_length_m": round((end - start) / px_per_m, 4),
                        "calculation": check["calculation"], "comparison": check.get("comparison"), "findings": check["findings"],
                        "note": "Chaîne native : les épaisseurs traversées sont déjà des segments distincts, rien n'est ré-ajouté."})
    results.sort(key=lambda r: (r["declared_total"] is None, -len(r["segments"])))
    for i, r in enumerate(results, 1):
        r["chain_id"] = f"CH-{i:02d}"
    results = results[:max_chains]
    return {"chains": results, "chains_total": len(chains), "lines": len(lines), "overrides": overrides,
            "note": ("Cotes lues dans le fichier CAO (texte natif). Une cote « forcée » (texte ≠ mesure géométrique) est listée dans overrides : "
                     "les deux valeurs sont conservées, aucune n'est corrigée automatiquement.")}


def native_chains_for_page(page_doc: dict, *, plan_id: str, page_index: int = 0) -> dict:
    dims = page_doc.get("dxf_dimensions") or []
    unit_to_m = page_doc.get("unit_to_m")
    ratio = page_doc.get("dxf_ratio") or (page_doc.get("cad_import") or {}).get("scale_px_per_dxf_unit")
    px_per_m = (ratio / unit_to_m) if ratio and unit_to_m else 0
    if not px_per_m and dims:
        # derive pixels-per-metre from the native dimensions themselves (robust median)
        ratios = sorted(math.hypot(d["x2"] - d["x1"], d["y2"] - d["y1"]) / d["measured_m"] for d in dims if d.get("measured_m", 0) > 0.2)
        px_per_m = ratios[len(ratios) // 2] if ratios else 0
    size = (page_doc.get("width_px") or 0, page_doc.get("height_px") or 0)
    return {"plan_id": plan_id, "page": page_index, "dimensions": len(dims), "px_per_m": round(px_per_m, 3),
            **build_chains(dims, px_per_m=px_per_m, plan_id=plan_id, page=page_index, size=size)}
