"""Conservative sheet context: a page is not necessarily one view or one level."""
import math
import re
import unicodedata

_SCALE = re.compile(r"(?<![\d.,])1\s*[:/]\s*(\d{1,5})(?!\d)")


def scale_denominators(text: str) -> list[int]:
    # Lot 56 : « inclinação 1/2 », « folha 1/3 », « página 1/10 » ne sont pas des échelles
    text = text or ""
    out = set()
    for m in _SCALE.finditer(text):
        den = int(m.group(1))
        if den not in STANDARD_SCALES:
            continue
        if den < 10 and not re.search(r"(?:[ée]ch(?:elle)?|scale|esc(?:ala)?)\.?\s*:?\s*$", text[max(0, m.start() - 12):m.start()], re.I):
            continue
        before = text[max(0, m.start() - 14):m.start()]
        if _NOT_SCALE_BEFORE.search(before) or re.match(r"\s*(?:folhas?|p[áa]ginas?|feuilles?|pages?)\b", text[m.end():m.end() + 12], re.I):
            continue
        out.add(den)
    return sorted(out)


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
    return [{"level_index": n, "level_label": "Sótão" if n == 99 else "RDC" if n == 0 else "Cave" if n == -1 else f"R{n:+d}"}
            for n in sorted(levels)]


def page_context(text: str) -> dict:
    text = text or ""
    scales = scale_denominators(text)
    levels = level_candidates(text)
    plain = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)).lower()
    # Title/caption evidence only; "coupe-feu" and a facade note on a floor plan
    # must not turn that floor plan into a section/elevation.
    schedule = bool(re.search(r"^\s*(?:NOMENCLATURE|TABLEAU)\s+DES\s+(?:BAIES|MENUISERIES)\b", text, re.I | re.M))
    # Lot 56 : « Coupe 12 » seul sur sa ligne est un repère de coupe, pas un titre ; PT : CORTE(S)
    section = bool(re.search(r"^\s*(?:COUPES?\s+(?!FEU\b)(?!\d+\s*$)|CORTES?\s+(?!CORTA\b)(?!\d+\s*$))\S", text, re.I | re.M))
    elevation = bool(re.search(r"^\s*(?:FA[ÇC]ADES?\s+(?:BAT|NORD|SUD|EST|OUEST)|AL[ÇC]ADOS?\s+(?:NORTE|SUL|NASCENTE|POENTE|ESTE|OESTE|PRINCIPAL|POSTERIOR|LATERAL))", text, re.I | re.M))
    floor = bool(re.search(r"^\s*(?:PLAN\s+(?:R[+\-\d ]|RDC|DE\s+RDC|DU\s+(?:RDC|SOUS-SOL))|PLANTA\s+(?:D[OA]\s+)?(?:PISO|R/?C|R[ÉE]S|CAVE|S[ÓO]T[ÃA]O|\d|PRIMEIRO|SEGUNDO|PISO))", text, re.I | re.M))  # Lot 56 : PT
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
    elif re.search(r"^\s*(?:coffrages?\s*[-:]|plan(?:s)?\s+(?:de\s+)?coffrage\b|plantas?\s+(?:de\s+)?cofragem\b)", plain, re.M):  # Lot 56
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
        warnings.append("Várias escalas nesta página (" + ", ".join(f"1:{s}" for s in scales) + "). Isole cada vista antes de calibrar e calcular as suas quantidades.")
    if len(levels) > 1:
        warnings.append("Várias menções de pisos: " + ", ".join(x["level_label"] for x in levels) + ". Verifique o título e atribua as medições à sua vista e ao seu piso.")
    technical_blocked = technical_kind is not None or kind == "text_unavailable"
    interior_blocked = kind in ("section", "elevation", "opening_schedule", "mixed") or len(scales) > 1 or technical_blocked
    if kind in ("section", "elevation", "opening_schedule", "mixed"):
        warnings.append("Esta página contém um corte, um alçado ou uma lista: os seus contornos não são automaticamente divisões ou paredes em planta.")
    if technical_kind:
        warnings.append("Documento de estrutura ou nota técnica: as armaduras, cofragens e cortes não são paredes interiores. Quantifique os elementos por marca e por vista após controlo.")
    if kind == "text_unavailable":
        warnings.append("Nenhum texto utilizável nesta página: leitura visual/OCR e calibração controlada necessárias antes da medição. Uma importação bem-sucedida não valida nenhuma quantidade.")
    unique_level = levels[0] if len(levels) == 1 and kind in ("floor_plan", "unknown", "structural_plan") else {}
    if not unique_level and kind in ("floor_plan", "unknown", "structural_plan"):  # Lot 56 : niveau du titre
        _tl = _title_levels(text)
        if len(_tl) == 1:
            unique_level = _tl[0]
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


# --- Lot 56 : niveaux FR + PT, sans enjamber les lignes ni lire une échelle -----------------------------------

STANDARD_SCALES = {1, 2, 5, 10, 20, 25, 50, 75, 100, 125, 150, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 25000}
_NOT_SCALE_BEFORE = re.compile(r"(inclina[çc][ãa]o|pendente|declive|junta|juntas|folha|folhas|p[áa]gina|p[áa]ginas|tra[çc]o|dosagem|rela[çc][ãa]o"
                               r"|pente|pentes|joint|joints|page|pages|feuille|feuilles|ratio)\W{0,3}$", re.I)

def level_candidates(text: str) -> list[dict]:
    text = text or ""
    levels = set()
    if re.search(r"\b(?:sous[\s-]?sol|caves?|s[\s-]sol|subcave)\b", text, re.I):
        levels.add(-1)
    if re.search(r"\b(?:rdc|rez[\s-]de[\s-]chauss[éeè]e?|r/c|r[ée]s[\s-]do[\s-]ch[ãa]o)(?![\w/])", text, re.I):
        levels.add(0)
    for match in re.finditer(r"(?<![\w/])r[ \t]*([+-])[ \t]*(\d{1,2})\b", text, re.I):
        levels.add(int(match.group(2)) * (1 if match.group(1) == "+" else -1))
    # Lot 72 : « +3.10  Étage » est une cote, pas le 10e étage
    for match in re.finditer(r"(?<![:/\d.,])(?<![:/.,][ \t])\b(\d{1,2})(?:e|er|eme|ème)?[ \t]*[eé]tage\b", text, re.I):
        levels.add(int(match.group(1)))
    for match in re.finditer(r"\b[eé]tage[ \t]+(\d{1,2})\b", text, re.I):
        levels.add(int(match.group(1)))
    for match in re.finditer(r"\bpiso[ \t]*(-?[ \t]*\d{1,2})\b", text, re.I):
        levels.add(int(match.group(1).replace(" ", "").replace("\t", "")))
    for match in re.finditer(r"(?<![:/\d.,])\b(\d{1,2})[ \t]*\.?[ \t]*[ºo°][ \t]*andar\b", text, re.I):  # Lot 72
        levels.add(int(match.group(1)))
    if re.search(r"\b(?:combles?|grenier|s[óo]t[ãa]o|[áa]guas[\s-]furtadas)\b", text, re.I):
        levels.add(99)
    return [{"level_index": n, "level_label": "Sótão" if n == 99 else "RDC" if n == 0 else "Cave" if n == -1 else f"R{n:+d}"}
            for n in sorted(levels)]


def _title_levels(text: str) -> list[dict]:
    """Niveaux cités dans les lignes de titre (« Plan coffrage PH R+4 », « Planta do piso 1 »)."""
    lines = [ln for ln in (text or "").splitlines() if re.match(r"\s*(?:plans?|plantas?)\b", ln, re.I)]
    found = {}
    _doc_floors = {lv["level_index"] for lv in level_candidates(text) if 0 < lv["level_index"] < 99}
    for ln in lines:
        for lv in level_candidates(ln):
            found[lv["level_index"]] = lv
        # Lot 72 : « … — Étage » seul dans un titre = R+1 si le document ne cite pas d'étage au-delà de R+1
        if (not level_candidates(ln) and re.search(r"(?:^|[\s—–\-:])[eé]tage\s*$", ln, re.I)
                and _doc_floors <= {1}):
            found[1] = {"level_index": 1, "level_label": "R+1"}
    return list(found.values())
