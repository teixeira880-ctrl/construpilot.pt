"""Formwork take-off from a native DXF (Revit/AutoCAD export): every element is a closed face rebuilt from the layer's own lines.

Nothing is inferred from block names or text. Heights are not in a plan view: volumes stay « indeterminate » with the missing input
listed, only plan quantities (lengths, thicknesses, sections, areas) are produced, each with its formula.
"""
import math
import re
from collections import defaultdict

from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

LAYER_ROLES = {"wall": r"mur|wall", "beam": r"poutre|beam", "column": r"poteau|column|pilier", "slab": r"dalle|slab|plancher", "lintel": r"linteau|lintel"}
_UNITS = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}


def _role(layer: str) -> str | None:
    low = layer.lower()
    return next((role for role, rx in LAYER_ROLES.items() if re.search(rx, low)), None)


def _lines(msp, layers: set[str], u: float) -> list[LineString]:
    out = []
    for e in msp:
        if e.dxf.layer not in layers:
            continue
        t = e.dxftype()
        if t == "LINE":
            out.append(LineString([(e.dxf.start.x * u, e.dxf.start.y * u), (e.dxf.end.x * u, e.dxf.end.y * u)]))
        elif t in ("ARC", "LWPOLYLINE", "POLYLINE"):
            if t == "ARC":
                pts = [(p.x * u, p.y * u) for p in e.flattening(0.005)]
            elif t == "POLYLINE":
                pts = [(v.dxf.location.x * u, v.dxf.location.y * u) for v in e.vertices]
            else:
                pts = [(p[0] * u, p[1] * u) for p in e.get_points("xy")]
            if len(pts) > 1:
                if t != "ARC" and getattr(e, "is_closed", getattr(e, "closed", False)):
                    pts.append(pts[0])
                out.append(LineString(pts))
    return out


def _hatch_polys(msp, layers: set[str], u: float) -> list[Polygon]:
    polys = []
    for e in msp:
        if e.dxftype() != "HATCH" or e.dxf.layer not in layers:
            continue
        for path in e.paths:
            pts = []
            if hasattr(path, "vertices"):
                pts = [(v[0] * u, v[1] * u) for v in path.vertices]
            elif hasattr(path, "edges"):
                for edge in path.edges:
                    if edge.type == "LineEdge":
                        pts.append((edge.start[0] * u, edge.start[1] * u))
                    elif edge.type == "ArcEdge":
                        pts.append((edge.center[0] * u + edge.radius * u * math.cos(math.radians(edge.start_angle)),
                                    edge.center[1] * u + edge.radius * u * math.sin(math.radians(edge.start_angle))))
            if len(pts) >= 3:
                poly = Polygon(pts)
                if poly.is_valid and poly.area > 1e-4:
                    polys.append(poly)
    return polys


def _thin(face: Polygon, max_thickness: float):
    """Elongated face → (length, thickness) from the minimum rotated rectangle; None when not a bar-like body."""
    rect = face.minimum_rotated_rectangle
    xs, ys = rect.exterior.coords.xy
    sides = sorted({round(math.hypot(xs[i + 1] - xs[i], ys[i + 1] - ys[i]), 4) for i in range(4)})
    if len(sides) < 2:
        return None
    thickness, length = sides[0], sides[-1]
    if thickness <= 0 or thickness > max_thickness or length < 2 * thickness or face.area < 0.6 * rect.area:
        return None
    return length, thickness


def coffrage_takeoff(dxf_bytes: bytes, *, wall_thicknesses_cm: list[float] | None = None, keep_geometry: bool = False) -> dict:
    import os
    import tempfile
    import ezdxf
    from ezdxf.recover import readfile as recover_readfile
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        tmp.write(dxf_bytes)
    try:
        try:
            doc = ezdxf.readfile(tmp.name)
        except Exception:  # noqa: BLE001 — binary blobs in some exports need the recovering loader
            doc, _ = recover_readfile(tmp.name)
    finally:
        os.unlink(tmp.name)
    msp = doc.modelspace()
    u = _UNITS.get(doc.header.get("$INSUNITS", 0), 0.01)
    layers = defaultdict(set)
    for name in {e.dxf.layer for e in msp}:
        role = _role(name)
        if role and not re.search(r"hach|hatch|annot|etiq", name.lower()):
            layers[role].add(name)
    out = {"unit_to_m": u, "layers": {k: sorted(v) for k, v in layers.items()}, "elements": {}, "lines": [], "findings": []}

    def faces(role):
        ls = _lines(msp, layers.get(role, set()), u)
        return list(polygonize(unary_union(ls))) if ls else []

    cols = _hatch_polys(msp, layers.get("column", set()), u) or [f for f in faces("column") if 0.03 <= f.area <= 3]
    rows = []
    for i, c in enumerate(sorted(cols, key=lambda p: (round(p.centroid.y, 1), p.centroid.x)), 1):
        rect = c.minimum_rotated_rectangle
        xs, ys = rect.exterior.coords.xy
        sides = sorted(math.hypot(xs[j + 1] - xs[j], ys[j + 1] - ys[j]) for j in range(2))
        rows.append({"ref": f"P{i:02d}", "w_cm": round(sides[0] * 100, 1), "h_cm": round(sides[1] * 100, 1), "section_m2": round(c.area, 4),
                     "formula": f"{sides[0] * 100:.0f} × {sides[1] * 100:.0f} cm = {c.area:.3f} m²", "centroid_m": [round(c.centroid.x, 2), round(c.centroid.y, 2)],
                     "source": "HATCH secção (camada pilares)" if _hatch_polys(msp, layers.get("column", set()), u) else "face fechada (linhas da camada pilares)"})
    out["elements"]["columns"] = {"count": len(rows), "section_total_m2": round(sum(r["section_m2"] for r in rows), 3), "rows": rows}

    walls, thin_layers, wall_faces = [], [], []
    for f in faces("wall"):
        tl = _thin(f, 0.6)
        if tl and tl[0] >= 0.3 and tl[1] < 0.08:
            thin_layers.append({"length_m": round(tl[0], 3), "thickness_m": round(tl[1], 3)})
        elif tl and tl[0] >= 0.3:
            walls.append({"length_m": round(tl[0], 3), "thickness_m": round(tl[1], 3), "plan_area_m2": round(f.area, 3), "centroid_m": [round(f.centroid.x, 2), round(f.centroid.y, 2)]})
            wall_faces.append(f)
    walls.sort(key=lambda w: -w["length_m"])
    for i, w in enumerate(walls, 1):
        w["ref"] = f"M{i:02d}"
        w["formula"] = f"{w['length_m']:.2f} m × {w['thickness_m'] * 100:.0f} cm = {w['plan_area_m2']:.3f} m²"
    by_t = defaultdict(float)
    for w in walls:
        by_t[f"{round(w['thickness_m'] * 100)} cm"] += w["length_m"]
    out["elements"]["walls"] = {"count": len(walls), "length_total_m": round(sum(w["length_m"] for w in walls), 2), "plan_area_m2": round(sum(w["plan_area_m2"] for w in walls), 2),
                                "length_by_thickness_m": {k: round(v, 2) for k, v in sorted(by_t.items())}, "rows": walls,
                                "thin_layers_excluded": {"count": len(thin_layers), "length_m": round(sum(t["length_m"] for t in thin_layers), 2),
                                                         "note": "corpo < 8 cm (forro, isolante, reboco?) excluído das paredes de betão — a confirmar"}}
    wall_bodies = list(wall_faces)
    if wall_thicknesses_cm:
        from engines.metre.wall_pairs import complete_walls
        comp = complete_walls(msp, layers.get("wall", set()), u, wall_thicknesses_cm, wall_faces)
        wall_bodies = comp.pop("bodies")
        w = out["elements"]["walls"]
        w["closed_faces_only"] = {"count": w["count"], "length_total_m": w["length_total_m"], "plan_area_m2": w["plan_area_m2"]}
        w["completion"] = comp
        w["plan_area_m2"] = comp["union_plan_area_m2"]
        w["length_total_m"] = round(w["length_total_m"] + comp["added_length_m"], 2)
        for k, v in comp["added_by_thickness"].items():
            w["length_by_thickness_m"][k] = round(w["length_by_thickness_m"].get(k, 0) + v["length_m"], 2)
        w["length_by_thickness_m"] = dict(sorted(w["length_by_thickness_m"].items()))

    beams = []
    for f in faces("beam"):
        tl = _thin(f, 1.0)
        if tl and tl[0] >= 0.5 and tl[1] >= 0.10:
            beams.append({"length_m": round(tl[0], 3), "width_m": round(tl[1], 3), "plan_area_m2": round(f.area, 3), "centroid_m": [round(f.centroid.x, 2), round(f.centroid.y, 2)]})
    beams.sort(key=lambda b: -b["length_m"])
    for i, b in enumerate(beams, 1):
        b["ref"] = f"PO{i:02d}"
        b["formula"] = f"{b['length_m']:.2f} m × {b['width_m'] * 100:.0f} cm (largura em planta)"
    out["elements"]["beams"] = {"count": len(beams), "length_total_m": round(sum(b["length_m"] for b in beams), 2), "rows": beams}

    slab_faces = faces("slab")
    slab_union = unary_union(slab_faces) if slab_faces else None
    if slab_union is not None and not slab_union.is_empty:
        polys = list(slab_union.geoms) if hasattr(slab_union, "geoms") else [slab_union]
        holes = [Polygon(r).area for p in polys for r in p.interiors]
        out["elements"]["slab"] = {"gross_area_m2": round(sum(p.area for p in polys) + sum(holes), 2), "openings_count": len(holes),
                                   "openings_area_m2": round(sum(holes), 2), "net_area_m2": round(sum(p.area for p in polys), 2), "panels": len(polys),
                                   "formula": "área das faces fechadas da camada laje (união); aberturas = anéis interiores"}
    else:
        out["elements"]["slab"] = None

    lintels = sum(1 for e in msp if e.dxf.layer in layers.get("lintel", set()) and e.dxftype() == "INSERT")
    out["elements"]["lintels"] = {"count_blocks": lintels, "note": "blocos contados, dimensões não lidas (símbolos)"}

    L = out["lines"]
    if walls:
        L.append({"element": "Paredes — comprimento acumulado", "formula": " + ".join(f"{w['length_m']:.2f}" for w in walls[:8]) + (" + …" if len(walls) > 8 else ""),
                  "net": out["elements"]["walls"]["length_total_m"], "unit": "ml", "state": "confirmed"})
        L.append({"element": "Paredes — volume de betão", "formula": "Σ (C × e) × altura sob a laje", "net": None, "unit": "m³", "state": "indeterminate", "missing": ["altura sob a laje"]})
    if rows:
        L.append({"element": "Pilares — secções", "formula": f'{len(rows)} pilares, Σ secções', "net": out["elements"]["columns"]["section_total_m2"], "unit": "m²", "state": "confirmed"})
        L.append({"element": "Pilares — volume de betão", "formula": "Σ secções × altura", "net": None, "unit": "m³", "state": "indeterminate", "missing": ["altura dos pilares"]})
    if beams:
        L.append({"element": "Vigas — comprimento acumulado", "formula": f"{len(beams)} poutres", "net": out["elements"]["beams"]["length_total_m"], "unit": "ml", "state": "confirmed"})
        L.append({"element": "Vigas — volume de betão", "formula": "Σ (C × largura) × altura abaixo da laje", "net": None, "unit": "m³", "state": "indeterminate", "missing": ["altura abaixo da laje / altura da viga"]})
    if out["elements"]["slab"]:
        L.append({"element": "Laje — área líquida", "formula": out["elements"]["slab"]["formula"], "net": out["elements"]["slab"]["net_area_m2"], "unit": "m²", "state": "confirmed"})
        L.append({"element": "Laje — volume de betão", "formula": "área líquida × espessura", "net": None, "unit": "m³", "state": "indeterminate", "missing": ["espessura da laje"]})
    out["findings"].append({"severity": "info", "subject": "Alturas ausentes da planta", "explanation": "Vista em planta: nenhuma altura/espessura legível no DXF; os volumes ficam indeterminados enquanto estes valores não forem fornecidos ou lidos num corte."})
    out["note"] = "Quantidades em planta provenientes das faces fechadas de cada camada (linhas nativas); nenhuma dimensão deduzida de nomes de blocos ou de textos."
    if keep_geometry:
        out["_geometry"] = {"wall_bodies": wall_bodies, "beams": [f for f in faces("beam") if _thin(f, 1.0)], "columns": cols,
                            "slab": slab_union, "msp": msp, "unit_to_m": u, "layers": {k: set(v) for k, v in layers.items()}}
    return out
