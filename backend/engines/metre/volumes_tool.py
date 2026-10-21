"""Concrete volumes per element of a level, assembled from the documents the user attached: DXF (plan quantities, completed walls), formwork
PDF (NGF level symbols, section marks, grid registration) and section sheets (printed base levels / thicknesses, read once by vision and stored).
Rule applied (user, 15/09/2026): AS murs = AI plancher haut, unless printed otherwise. Missing inputs are named, never assumed."""
from collections import Counter

from engines.metre.coffrage_dxf import coffrage_takeoff
from engines.metre.coupe_marks import locate_coupe_marks
from engines.metre.coupe_zones import assign_wall_zones, clip_elements, coupe_sheet_data, link_coupes, plan_extent_polygon, traces_to_model
from engines.metre.grid_align import dxf_grid_axes, pdf_grid_axes, register, to_model
from engines.metre.heights import derive_heights
from engines.metre.level_symbols import levels_from_symbols, parse_level_symbols, words_from_pdf_page
from engines.plan_vector_pdf import pt_per_m_from_scale
from engines.plan_identity import identify_document


def _pt_per_m(page) -> float | None:
    ident = identify_document(page.get_text(), page.get_text("words"))
    scale = ident.get("declared_scale") or ""
    return pt_per_m_from_scale(int(scale.split("/")[1])) if "/" in scale else None


def read_formwork_pdf(pdf_bytes: bytes) -> dict:
    import pymupdf
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[0]
        ppm = _pt_per_m(page)
        sym = parse_level_symbols(words_from_pdf_page(page))
        marks = locate_coupe_marks(page, pt_per_m=ppm)
        axes = pdf_grid_axes(page)
        return {"pt_per_m": ppm, "level_symbols": sym, "coupe_marks": marks, "grid_axes": axes["axes"],
                "identity": identify_document(page.get_text(), page.get_text("words"))}


def compute_volumes(dxf_bytes: bytes, formwork_pdf: bytes | None, coupes_result: dict | None, levels_override: dict | None = None, beams_pairing: dict | None = None) -> dict:
    """Deterministic assembly. coupes_result = stored output of coupes_vision.analyze_coupes_pdf (already rechecked)."""
    import pymupdf
    import ezdxf
    from ezdxf.recover import readfile as recover_readfile
    import os
    import tempfile
    out = {"sources": {}, "findings": []}
    sheet = coupe_sheet_data(coupes_result)
    coupes_summary = (coupes_result or {}).get("summary") or {}
    thick_cm = sorted({round(float(v)) for v in coupes_summary.get("wall_thickness_cm", {})} | {round(float(v)) for d in sheet.values() for v in d["wall_thickness_cm"]})
    fw = None
    if formwork_pdf:
        fw = read_formwork_pdf(formwork_pdf)
        out["sources"]["formwork_pdf"] = {"identity": fw["identity"], "level_symbols": len(fw["level_symbols"]["symbols"]), "dominant": fw["level_symbols"]["dominant"],
                                          "coupe_marks": {"traces": len(fw["coupe_marks"]["coupes"]), "names": fw["coupe_marks"]["names"], "unpaired_heads": len(fw["coupe_marks"]["unpaired_heads"])},
                                          "grid_axes": sorted(fw["grid_axes"])}
    takeoff = coffrage_takeoff(dxf_bytes, wall_thicknesses_cm=thick_cm or None, keep_geometry=True)
    geom = takeoff.pop("_geometry")
    out["sources"]["dxf"] = {"layers": takeoff["layers"], "walls": {k: v for k, v in takeoff["elements"]["walls"].items() if k != "rows"},
                             "columns": {k: v for k, v in takeoff["elements"]["columns"].items() if k != "rows"}, "beams": {k: v for k, v in takeoff["elements"]["beams"].items() if k != "rows"},
                             "slab": takeoff["elements"]["slab"]}
    if coupes_result:
        out["sources"]["coupes"] = {"coupes": sorted(sheet), "dominant": coupes_summary.get("dominant"), "wall_thickness_cm": thick_cm}

    # levels
    base = (coupes_summary.get("dominant") or {}).get("niveau_base_murs_m")
    if fw and fw["level_symbols"]["symbols"]:
        levels = levels_from_symbols(fw["level_symbols"], base_level_m=base, source="símbolos altimétricos da planta de cofragem" + (" + nível de base dos cortes" if base else ""))
    else:
        dom = coupes_summary.get("dominant") or {}
        levels = {"as_plancher_haut_m": dom.get("as_plancher_haut_m"), "epaisseur_dalle_m": dom.get("epaisseur_dalle_cm") / 100 if dom.get("epaisseur_dalle_cm") else None,
                  "niveau_base_murs_m": base, "source": "cortes (dominante)" if dom else None, "exceptions": []}
    for k, v in (levels_override or {}).items():
        if v is not None and k in ("as_plancher_haut_m", "epaisseur_dalle_m", "niveau_base_murs_m"):
            levels[k] = v
            levels["source"] = (levels.get("source") or "") + f' ; {k} indicado pelo utilizador'
    heights = derive_heights(levels)
    out["levels"] = levels
    out["heights"] = heights

    # registration + zones
    reg, traces, extent, zones, links, clipped = None, [], None, None, None, {"clipped": False}
    if fw and fw["grid_axes"]:
        import pymupdf
        with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
            tmp.write(dxf_bytes)
        try:
            try:
                ddoc = ezdxf.readfile(tmp.name)
            except Exception:  # noqa: BLE001
                ddoc, _ = recover_readfile(tmp.name)
        finally:
            os.unlink(tmp.name)
        dxf_axes = dxf_grid_axes(ddoc.modelspace(), geom["unit_to_m"])["axes"]
        reg = register(fw["grid_axes"], dxf_axes, declared_pt_per_m=fw["pt_per_m"])
        out["registration"] = {k: v for k, v in reg.items() if k != "transform"}
        if reg["ok"]:
            with pymupdf.open(stream=formwork_pdf, filetype="pdf") as doc:
                extent = plan_extent_polygon(doc[0], reg)
            traces = traces_to_model(fw["coupe_marks"]["coupes"], reg)
            links = link_coupes(traces, geom, sheet)
            clipped = clip_elements(geom, extent)
            out["coupes_located"] = links
            missing = sorted(set(sheet) - {t["name"] for t in traces}, key=lambda s: int(s.split("-")[0]))
            if missing:
                out["findings"].append({"severity": "info", "subject": "Cortes do caderno não identificados na planta", "explanation": ", ".join(missing)})
            out["findings"].append({"severity": "info", "subject": "Reajuste planta ↔ DXF", "explanation": f"axes {', '.join(reg['common_axes'])} ; resíduo {reg['residual_m'] * 1000:.0f} mm; escala medida/declarada {reg.get('scale_vs_declared')}"})
        else:
            out["findings"].append({"severity": "warning", "subject": "Reajuste planta ↔ DXF impossível", "explanation": reg["error"]})
    zones = assign_wall_zones(geom["wall_bodies"], traces, sheet, default_h_m=heights["h_murs_m"], extent=extent)
    for ex in levels.get("exceptions") or []:
        if "x" in ex:
            x, y = ex.pop("x"), ex.pop("y")
            ex["position_pdf_pt"] = [x, y]
            if reg and reg.get("ok"):
                mx, my = to_model(reg, x, y)
                ex["position_model_m"] = [round(mx, 2), round(my, 2)]
            ex["note"] = "símbolo altimétrico local (zona de laje com espessura diferente); posição em pontos PDF da planta de cofragem" + (" e em metros DXF" if "position_model_m" in ex else "")
    out["walls_by_zone"] = {k: v for k, v in zones.items() if k != "rows"}
    out["walls_by_zone"]["thickness_distribution_cm"] = dict(Counter(r["thickness_cm"] for r in zones["rows"]).most_common())

    # volumes per element
    lines, total = [], 0.0
    e = takeoff["elements"]
    if zones["rows"]:
        v = zones["volume_total_m3"]
        total += v
        lines.append({"element": "Paredes — volume de betão", "formula": f"Σ (área em planta × h zona) em {zones['walls_in_extent']} corpos; h = AI pavimento superior − base do corte mais próximo",
                      "net": round(v, 2), "unit": "m³", "state": "confirmed" if
                      not zones.get("walls_missing_height") and all(r["state"] == "confirmed" for r in zones["rows"]) else "to_clarify",
                      "detail": {"confirmed_m3": zones["volume_confirmed_m3"], "to_clarify_m3": zones["volume_to_clarify_m3"], "by_coupe_m3": zones["volume_by_coupe_m3"]}})
    elif heights["h_murs_m"] is None:
        lines.append({"element": "Paredes — volume de betão", "formula": "Σ (L × e) × h", "net": None, "unit": "m³", "state": "indeterminate", "missing": heights["missing"]})
    cols = clipped.get("columns") or {k: v for k, v in e["columns"].items() if k != "rows"}
    if heights["h_poteaux_m"] is not None and cols.get("count"):
        v = cols["section_total_m2"] * heights["h_poteaux_m"]
        total += v
        lines.append({"element": "Pilares — volume de betão", "formula": f"Σ secções {cols['section_total_m2']:.3f} m² ({cols['count']} pilares) × h {heights['h_poteaux_m']:.2f} m", "net": round(v, 2), "unit": "m³", "state": "confirmed"})
    slab = clipped.get("slab") if clipped.get("clipped") else e.get("slab")
    if heights["epaisseur_dalle_m"] is not None and slab:
        v = slab["net_area_m2"] * heights["epaisseur_dalle_m"]
        total += v
        state = "confirmed" if not levels.get("exceptions") else "to_clarify"
        lines.append({"element": "Laje — volume de betão", "formula": f"área líquida {slab['net_area_m2']:.2f} m² × ép. {heights['epaisseur_dalle_m']:.2f} m", "net": round(v, 2), "unit": "m³", "state": state,
                      "note": f"{len(levels.get('exceptions') or [])} símbolo(s) altimétrico(s) com espessura diferente (zonas locais)" if levels.get("exceptions") else None})
    beams = clipped.get("beams") or {k: v for k, v in e["beams"].items() if k != "rows"}
    drop, paired_in = 0.0, 0
    if beams_pairing and heights["epaisseur_dalle_m"] is not None:
        from shapely.geometry import Point
        for r in beams_pairing.get("rows", []):
            d = r.get("dxf")
            if d and r.get("h_cm") and (extent is None or extent.contains(Point(*d["centroid_m"]))):
                retombee = r["h_cm"] / 100 - heights["epaisseur_dalle_m"]
                if retombee > 0:
                    drop += d["length_m"] * d["width_m"] * retombee; paired_in += 1
    if drop:
        total += drop
        lines.append({"element": "Vigas emparelhadas — alturas abaixo da laje", "formula": f"Σ C_dxf × b × (h folha Arche − esp. laje) em {paired_in} vigas emparelhadas / {beams['count']} en plan",
                      "net": round(drop, 2), "unit": "m³", "state": "to_clarify" if paired_in < beams["count"] else "confirmed",
                      "note": f"{beams['count'] - paired_in} viga(s) da planta sem folha Arche emparelhada: altura abaixo da laje não contada" if paired_in < beams["count"] else None})
    elif beams["count"]:
        lines.append({"element": "Vigas — alturas abaixo da laje", "formula": f"{beams['count']} poutres, {beams['length_total_m']} ml em planta × largura × (h viga − esp. laje)", "net": None, "unit": "m³",
                      "state": "indeterminate", "missing": ["alturas das vigas (folhas de armaduras Arche ou planta de cofragem)"]})
    for miss in heights["missing"]:
        lines.append({"element": f'Dado em falta: {miss}', "formula": None, "net": None, "unit": "m³", "state": "indeterminate", "missing": [miss]})
    out["lines"] = lines
    out["partial_total_m3"] = round(total, 2)
    out["total_m3"] = round(total, 2) if lines and not heights["missing"] and all(line["state"] == "confirmed" for line in lines) else None
    out["scope"] = {"clipped_to_plan": clipped.get("clipped"), "extent_m": clipped.get("extent_m"), "note": "Quantidades limitadas à implantação da planta de cofragem (edifício desenhado) quando o reajuste está disponível; caso contrário, piso completo do DXF."}
    out["rule"] = heights["rule"]
    return out


def compact_for_llm(res: dict) -> dict:
    keep = {k: res[k] for k in ("levels", "heights", "lines", "total_m3", "partial_total_m3", "scope", "rule", "findings", "registration") if k in res}
    keep["sources"] = res.get("sources")
    keep["walls_by_zone"] = res.get("walls_by_zone")
    keep["coupes_located"] = [{k: v for k, v in c.items() if k not in ("a_m", "b_m")} for c in (res.get("coupes_located") or [])]
    return keep

