"""Treillis symbols drawn on the slab plan (Arche « cross » with the panel mark in a circle): labels 240 / 200 / 250 / 43 / 30 around
the mark are checked against the panel row of the nomenclature (cut dimensions and overlaps) — text ↔ text, plus the line-length
confirmation when the drawing offers one. States: confirmed_by_geometry, confirmed_by_schedule, to_clarify."""
import math
import re

from engines.metre.oblique_dims import match_labels

RADIUS_M = 3.2


def _drawing_marks(page, exclude_rects):
    marks = []
    for w in page.get_text("words"):
        if not re.fullmatch(r"T\d{1,3}", w[4]):
            continue
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if any(r[0] <= cx <= r[2] and r[1] <= cy <= r[3] for r in exclude_rects):
            continue
        marks.append({"mark": w[4], "cx": cx, "cy": cy})
    return marks


def panel_labels(page, pt_per_m: float, mesh_rows: list[dict], exclude_rects) -> dict:
    res = match_labels(page, pt_per_m, exclude_rects=exclude_rects)
    ppm = res["pt_per_m"]
    marks = _drawing_marks(page, exclude_rects)
    rows = {r["mark"]: r for r in mesh_rows}
    per_mark = {m["mark"] + f"@{int(m['cx'])}": {"mark": m["mark"], "labels": [], "in_schedule": m["mark"] in rows} for m in marks}
    geo_ok = {(d["raw_text"], tuple(d["label_bbox"])) for d in res["dimensions"]}
    for lab in res["dimensions"] + res["unmatched"]:
        bx = lab["label_bbox"]
        lx, ly = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
        near = [(math.hypot(m["cx"] - lx, m["cy"] - ly), m) for m in marks]
        if not near:
            break
        dist, m = min(near, key=lambda t: t[0])
        if dist > RADIUS_M * ppm:
            continue
        per_mark[m["mark"] + f"@{int(m['cx'])}"]["labels"].append({"text": lab["raw_text"], "value_cm": int(lab["raw_text"]), "distance_m": round(dist / ppm, 2),
                                                                      "geometry": (lab["raw_text"], tuple(bx)) in geo_ok})
    out_rows, counts = [], {"confirmed_by_geometry": 0, "confirmed_by_schedule": 0, "to_clarify": 0, "marks_not_in_schedule": 0}
    for key, info in per_mark.items():
        row = rows.get(info["mark"])
        expected = set()
        if row:
            for c in row.get("cuts", []):
                expected |= {c["width_cm"], c["height_cm"]}
            expected |= {int(v) for v in (row.get("overlap_transversal_cm"), row.get("overlap_bearing_cm")) if v}
        if not row:
            counts["marks_not_in_schedule"] += 1
        checked = []
        for lab in info["labels"]:
            if lab["geometry"]:
                state = "confirmed_by_geometry"
            elif lab["value_cm"] in expected:
                state = "confirmed_by_schedule"
            else:
                state = "to_clarify"
            counts[state] += 1
            checked.append({**lab, "state": state})
        out_rows.append({"mark": info["mark"], "in_schedule": bool(row), "panel": row.get("panel") if row else None, "expected_cm": sorted(expected),
                         "labels": checked, "missing_expected_cm": sorted(expected - {l["value_cm"] for l in checked}) if row else []})
    return {"marks_in_drawing": len(marks), "rows": out_rows, "counts": counts, "calibration": res["calibration"],
            "note": ("Etiquetas de painéis associadas à marca Tnn mais próxima (≤ 3,2 m); confirmadas pela geometria (linha paralela do mesmo comprimento) ou pela lista (dimensão de corte / sobreposição impressa); as outras ficam por esclarecer. Nenhum valor deduzido.")}
