"""Ré-extraction locale d'une seule page du PDF source, sans appel IA."""
import pymupdf

from engines.plan_vector_pdf import pdf_lines, pdf_text_blocks, extract_vector_dimensions, extract_elements, extract_auto_spans, _dims_pt
from engines.plan_walls import analyze_walls

GEOMETRY_VERSION = 6


def carry_user_edits(dimensions: list[dict], previous_items: list[dict]) -> list[int]:
    """Reporte les corrections sur les mêmes extrémités, jamais par ancien index.

    Renvoie les anciens index non rapprochés : le caller doit alors conserver
    le rapport précédent au lieu d'effacer silencieusement les corrections.
    """
    unmatched, used = [], set()
    for item in previous_items:
        if not item.get("edited") and not item.get("ignored"):
            continue
        def matches(d):
            if d.get("source", "ai") != item.get("source", "ai"):
                return False
            a = (item["x1"], item["y1"], item["x2"], item["y2"])
            b = (d["x1"], d["y1"], d["x2"], d["y2"])
            return min(max(abs(x-y) for x,y in zip(a,b)),
                       max(abs(x-y) for x,y in zip(a,b[2:]+b[:2]))) <= 2
        candidates = [i for i,d in enumerate(dimensions) if i not in used and matches(d)]
        if len(candidates) != 1:
            unmatched.append(item["index"])
            continue
        idx = candidates[0]
        used.add(idx)
        dimensions[idx].update(ignored=bool(item.get("ignored")), edited=bool(item.get("edited")), original_m=item.get("original_m"))
        if item.get("edited"):
            dimensions[idx]["value_m"] = item["indicated_m"]
    return unmatched


def extract_pdf_page(page, px_per_pt: float, *, vectors=None, text_blocks=None) -> dict:
    """Shared native extraction for import and re-extraction of the original PDF."""
    from engines.plan_page_context import page_context
    from engines.plan_vector_pdf import pt_per_m_from_scale, _mode_ratio
    context = page_context(page.get_text("text") or "")
    tb = pdf_text_blocks(page) if text_blocks is None else text_blocks
    lines = pdf_lines(page) if vectors is None else vectors
    if context["auto_calibration_blocked"]:
        dims = {"dimensions": [], "pt_per_m": None, "self_calibrated": False,
                "matched": 0, "texts_numeric": 0, "blocked": True}
    else:
        dims = extract_vector_dimensions(lines, tb, px_per_pt,
                                        pt_per_m_from_scale(context["detected_scale_denominator"]))
    # A PDF can be resized after export while retaining its printed scale.
    # Several agreeing dimension ratios invalidate that scale; they must not
    # silently become a replacement calibration based on uncertain attachments.
    if dims.get("scale_source") == "declared":
        ratios = [d["measured_m"] / d["value_m"] for d in dims["dimensions"]
                  if d.get("value_m", 0) >= 0.5 and d.get("measured_m", 0) > 0]
        observed_ratio = _mode_ratio(ratios)
        if observed_ratio is not None and abs(observed_ratio - 1) > 0.05:
            dims.update(scale_conflict=True, declared_scale_conflict=True,
                        observed_to_declared_ratio=round(observed_ratio, 6),
                        pt_per_m=None, self_calibrated=False)
            for dimension in dims["dimensions"]:
                dimension["unverified"] = True
    if dims.get("scale_conflict"):
        context["auto_calibration_blocked"] = True
        context["interior_analysis_blocked"] = True
        warning = ("Échelle du cartouche contredite par plusieurs cotes : PDF possiblement redimensionné. Calibrez sur une cote vérifiée avant le métré."
                   if dims.get("declared_scale_conflict") else
                   "Échelles vectorielles contradictoires : isolez et calibrez chaque vue avant le métré.")
        context["reading_warnings"].append(warning)
    ppm = dims.get("pt_per_m")
    trusted_dimensions = [d for d in dims["dimensions"] if not d.get("unverified")]
    uncertain = len(dims["dimensions"]) - len(trusted_dimensions)
    if uncertain:
        context["reading_warnings"].append(f"{uncertain} rattachements de cotes incertains : contrôlez leurs extrémités sur le dessin avant de les utiliser pour le métré.")
    eligible = not context["interior_analysis_blocked"]
    walls = analyze_walls(lines if eligible else [],
                          [{**d, "index": i+1} for i,d in enumerate(dims["dimensions"]) if not d.get("unverified")] if eligible else [],
                          tb if eligible else [], ppm if eligible else None, px_per_pt,
                          page_size_px=(page.rect.width * px_per_pt, page.rect.height * px_per_pt))
    if not eligible:
        walls["validation"]["failed_checks"] = context["reading_warnings"]
    return {**context, "pdf_dimensions": dims["dimensions"],
            "pdf_vector_scale": {k:v for k,v in dims.items() if k != "dimensions"},
            "pdf_elements": extract_elements(lines, tb, px_per_pt, ppm) if ppm and eligible else [],
            "pdf_auto_spans": extract_auto_spans(lines, px_per_pt, ppm, _dims_pt(trusted_dimensions, px_per_pt)) if ppm and eligible else [],
            "walls_analysis": walls, "vectors": lines[:2500], "vectors_truncated": len(lines)>2500,
            "vectors_total": len(lines), "text_blocks": tb[:2000], "text_blocks_total": len(tb),
            "text_blocks_truncated": len(tb)>2000, "geometry_version": GEOMETRY_VERSION}


def extract_page_geometry(pdf_bytes: bytes, page_index: int, px_per_pt: float) -> dict:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        result = extract_pdf_page(doc[page_index], px_per_pt)
        # Re-extraction must preserve the user's assigned page level.
        result.pop("level_index", None)
        result.pop("level_label", None)
        return result


def refresh_interior(page: dict, items: list[dict], pixels_per_meter: float | None = None) -> dict:
    """Répercute corrections/ignorés dans les travées, sans toucher aux faces.

    Les cotes du rapport sont déjà en pixels. Les primitives/segments conservés
    sont en points PDF. Une calibration manuelle prévaut pour cette opération.
    """
    if page.get("interior_analysis_blocked"):
        result = analyze_walls([], [], [], None, 1)
        result["validation"]["failed_checks"] = page.get("reading_warnings") or ["vue à isoler avant analyse intérieure"]
        return result
    previous = page.get("walls_analysis") or {}
    px = 1.0 if page.get("geometry_coordinate_space") == "image_px" else float(page.get("dpi") or 0) / 72
    ppm = (pixels_per_meter / px if px else None) if pixels_per_meter is not None else (
        previous.get("pt_per_m") or (page.get("pdf_vector_scale") or {}).get("pt_per_m"))
    dims = [{"index": it["index"], "orientation": it["orientation"],
             "x1": it["x1"], "y1": it["y1"], "x2": it["x2"], "y2": it["y2"],
             "value_m": it["indicated_m"], "raw_text": it.get("raw_text", "")}
            for it in items if not it.get("ignored") and not it.get("unverified") and it.get("source") in ("pdf", "dxf")]
    segments = previous.get("segments") if previous.get("engine_version") == 2 else None
    if not segments and (page.get("vectors_truncated") or len(page.get("vectors") or []) >= 2500):
        result = analyze_walls([], [], [], None, 1)
        result["validation"]["failed_checks"] = ["réextraire le PDF original : anciens vecteurs tronqués"]
    else:
        result = analyze_walls(page.get("vectors") or [], dims, page.get("text_blocks") or [], ppm, px,
                               segments=segments, page_size_px=(page.get("width_px",1),page.get("height_px",1)))
    result["cote_index_space"] = "report"
    if (page.get("cad_import") or {}).get("diagnostics"):
        from engines.plan_walls import INCOMPLETE_MSG
        result["validation"]["complete"] = False
        result["validation"]["message"] = INCOMPLETE_MSG
        result["validation"]["failed_checks"].append("import CAO avec réserves : consulter les diagnostics")
    return result
