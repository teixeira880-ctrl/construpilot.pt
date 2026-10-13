"""Conservative sheet context: a page is not necessarily one view or one level."""
import math
import re
import unicodedata

_SCALE = re.compile(r"(?<![\d.,])1\s*[:/]\s*(\d{1,5})(?!\d)")


def scale_denominators(text: str) -> list[int]:
    return sorted({int(m.group(1)) for m in _SCALE.finditer(text or "") if int(m.group(1)) > 0})


def level_candidates(text: str) -> list[dict]:
    text = text or ""
    levels = set()
    if re.search(r"\b(?:sous[\s-]?sol|caves?|s[\s-]sol)\b", text, re.I):
        levels.add(-1)
    if re.search(r"\b(?:rdc|rez[\s-]de[\s-]chauss[éeè]e?)\b", text, re.I):
        levels.add(0)
    for match in re.finditer(r"\br\s*([+-])\s*(\d{1,2})\b", text, re.I):
        levels.add(int(match.group(2)) * (1 if match.group(1) == "+" else -1))
    for match in re.finditer(r"\b(\d{1,2})(?:e|er|eme|ème)?\s*[eé]tage\b", text, re.I):
        levels.add(int(match.group(1)))
    if re.search(r"\b(?:combles?|grenier)\b", text, re.I):
        levels.add(99)
    return [{"level_index": n, "level_label": "Combles" if n == 99 else "RDC" if n == 0 else "Sous-sol" if n == -1 else f"R{n:+d}"}
            for n in sorted(levels)]


def page_context(text: str) -> dict:
    text = text or ""
    scales = scale_denominators(text)
    levels = level_candidates(text)
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).lower()
    # Title/caption evidence only; "coupe-feu" and a facade note on a floor plan
    # must not turn that floor plan into a section/elevation.
    schedule = bool(re.search(r"^\s*(?:NOMENCLATURE|TABLEAU)\s+DES\s+(?:BAIES|MENUISERIES)\b", text, re.I | re.M))
    section = bool(re.search(r"^\s*COUPES?\s+(?!FEU\b)\S", text, re.I | re.M))
    elevation = bool(re.search(r"^\s*FA[ÇC]ADES?\s+(?:BAT|NORD|SUD|EST|OUEST)", text, re.I | re.M))
    floor = bool(re.search(r"^\s*PLAN\s+(?:R[+\-\d ]|RDC|DE\s+RDC|DU\s+(?:RDC|SOUS-SOL))", text, re.I | re.M))
    kinds = [name for name, present in (("section", section), ("elevation", elevation), ("floor_plan", floor)) if present]
    kind = "opening_schedule" if schedule else "mixed" if len(kinds) > 1 else kinds[0] if kinds else "unknown"
    # Structural diagrams contain parallel reinforcement lines and sections that
    # are not wall faces. Keep their dimensions available, but do not pass them
    # to the generic room/wall detector, even when a unique scale is printed.
    technical_kind = None
    if re.search(r"^\s*-?\s*note de calcul\s*-?\s*$", plain, re.M):
        technical_kind = "calculation_note"
    elif re.search(r"^\s*recapitulatif\b.*\blinteaux\b", plain, re.M):
        technical_kind = "structural_schedule"
    elif re.search(r"^\s*(?:coffrages?\s*[-:]|plan(?:s)? de coffrage\b)", plain, re.M):
        technical_kind = "structural_plan"
    elif (re.search(r"^\s*(?:armatures?\s+(?:inferieures?|superieures?)|chaine poteaux\b|chevetre n[°o])", plain, re.M)
          or ("poutrelles precontraintes" in plain and re.search(r"^\s*plancher\b", plain, re.M))
          or ("arche dalle ec2" in plain and "treillis soude" in plain)):
        technical_kind = "structural_detail"
    if technical_kind:
        kind = technical_kind
    elif not text.strip():
        kind = "text_unavailable"
    warnings = []
    if len(scales) > 1:
        warnings.append("Plusieurs échelles sur cette page (" + ", ".join(f"1:{s}" for s in scales) + "). Isolez chaque vue avant de calibrer et calculer ses quantités.")
    if len(levels) > 1:
        warnings.append("Plusieurs mentions de niveaux : " + ", ".join(x["level_label"] for x in levels) + ". Vérifiez le titre et affectez les mesures à leur vue et à leur niveau.")
    technical_blocked = technical_kind is not None or kind == "text_unavailable"
    interior_blocked = kind in ("section", "elevation", "opening_schedule", "mixed") or len(scales) > 1 or technical_blocked
    if kind in ("section", "elevation", "opening_schedule", "mixed"):
        warnings.append("Cette page contient une coupe, une façade ou une nomenclature : ses contours ne sont pas automatiquement des pièces ou des murs en plan.")
    if technical_kind:
        warnings.append("Document de structure ou note technique : les armatures, coffrages et coupes ne sont pas des murs intérieurs. Quantifiez les éléments par repère et par vue après contrôle.")
    if kind == "text_unavailable":
        warnings.append("Aucun texte exploitable dans cette page : lecture visuelle/OCR et calibration contrôlée nécessaires avant le métré. Une importation réussie ne valide aucune quantité.")
    unique_level = levels[0] if len(levels) == 1 and kind in ("floor_plan", "unknown") else {}
    return {"view_kind": kind, "scale_denominators": scales,
            "detected_scale_denominator": scales[0] if len(scales) == 1 else None,
            "auto_calibration_blocked": len(scales) > 1 or schedule or kind in ("calculation_note", "structural_schedule", "text_unavailable"),
            "interior_analysis_blocked": interior_blocked,
            "level_candidates": levels, "level_index": unique_level.get("level_index"),
            "level_label": unique_level.get("level_label"), "reading_warnings": warnings}


def initial_pdf_calibrations(parsed: dict, now: str) -> dict:
    """Use the scale of each page; never propagate page 1's scale through a PDF."""
    result = {}
    pages = parsed.get("pages") or []
    for pg in pages:
        if pg.get("auto_calibration_blocked"):
            continue
        scale = pg.get("detected_scale_denominator")
        # Compatibility with old single-page imports only.
        if "detected_scale_denominator" not in pg and len(pages) == 1:
            scale = parsed.get("detected_scale_denominator")
        vec = pg.get("pdf_vector_scale") or {}
        if vec.get("scale_conflict"):
            continue
        ptm = vec.get("pt_per_m")
        dpi = pg.get("dpi") or 72
        if not isinstance(dpi, (float, int)) or not math.isfinite(dpi) or dpi <= 0:
            continue
        consensus = vec.get("scale_source") == "vector_consensus" or ("scale_source" not in vec and vec.get("self_calibrated"))
        if consensus and isinstance(ptm, (float, int)) and math.isfinite(ptm) and ptm > 0 and (vec.get("matched") or 0) >= 3:
            ppm = ptm * dpi / 72
            cal = {"method": "pdf_vector", "confidence": .9, "samples_used": vec.get("matched"),
                   "effective_scale_denominator": round(1000 * 72 / 25.4 / ptm, 1)}
        elif isinstance(scale, (float, int)) and math.isfinite(scale) and scale > 0:
            ppm = dpi / .0254 / scale
            cal = {"method": "auto_pdf_scale", "confidence": .75}
        else:
            continue
        result[str(pg["index"])] = {**cal, "pixels_per_meter": round(ppm, 4), "meters_per_pixel": round(1 / ppm, 8),
                                    "scale_denominator": scale, "created_at": now}
    return result
