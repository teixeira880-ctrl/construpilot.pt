"""Deterministic reading of reinforcement schedules (nomenclature des aciers / treillis) from native PDF text.

Rows are located by column headers and anchors (« HA » in the Type column, « Tnn » in the N° column); every value is the
text printed on the sheet. Arithmetic checks (count × unit length = total length, Σ masses vs recap) are reported, never corrected.
"""
import re
from collections import defaultdict

from engines.rebar import STEEL_KG_PER_M

ROW_TOL = 5.5        # pt: words on the same printed row
ANCHOR_X_TOL = 12.0  # pt: anchors of one table share the N° column
HA_COLUMNS = ["mark", "type", "diameter_mm", "per_element", "elements", "total_count", "spacing_cm", "unit_length_cm", "shape", "mandrel_cm", "total_length_cm"]
MESH_COLUMNS = ["mark", "panel", "per_element", "elements", "total_count", "overlap_transversal_cm", "overlap_bearing_cm", "cuts", "mass_kg"]
_NUM = re.compile(r"^-?\d+(?:[.,]\d+)?$")
_DIMS = re.compile(r"^(\d+)x(\d+)$", re.I)


def _num(s):
    return float(s.replace(",", ".")) if s and _NUM.match(s) else None


def _cx(w):
    return (w[0] + w[2]) / 2


def _cy(w):
    return (w[1] + w[3]) / 2


def _words(page) -> list[tuple]:
    return [w for w in page.get_text("words") if w[4].strip()]


def _find(words, text, *, after_y=None, near_x=None, x_tol=400):
    cands = [w for w in words if w[4] == text and (after_y is None or w[1] >= after_y - 2) and (near_x is None or abs(w[0] - near_x) <= x_tol)]
    return min(cands, key=lambda w: (w[1], abs(w[0] - (near_x or w[0])))) if cands else None


def _title(words, *tokens):
    """First word of a multi-word title, matched on consecutive words of the same row."""
    for w in words:
        if w[4] != tokens[0]:
            continue
        row = sorted([o for o in words if abs(_cy(o) - _cy(w)) <= ROW_TOL and o[0] >= w[0]], key=lambda o: o[0])
        if [o[4] for o in row[:len(tokens)]] == list(tokens):
            return w
    return None


def _ha_header(words, title):
    """Column centres of the HA schedule from its header words (all positions read, none assumed)."""
    y0, y1 = title[3], title[3] + 90
    band = [w for w in words if y0 <= w[1] <= y1 and title[0] - 160 <= w[0] <= title[2] + 420]
    get = lambda t: next((w for w in sorted(band, key=lambda w: w[0]) if w[4] == t), None)  # noqa: E731
    n, typ, dia, esp, mandrin, totale = get("N°"), get("Type"), get("∅") or get("Ø"), get("Esp"), get("Mandrin"), get("TOTALE")
    par, delem, total = get("Par"), get("d'éléments"), next((w for w in band if w[4] == "TOTAL"), None)
    longs = sorted([w for w in band if w[4] == "Long."], key=lambda w: w[0])
    faconnage = get("Façonnage")
    if not all([n, typ, dia, delem, total, longs, totale]):
        return None
    elem = get("Elément")
    cols = {"mark": _cx(n), "type": _cx(typ), "diameter_mm": _cx(dia),
            "per_element": (_cx(par) + _cx(elem)) / 2 if par and elem else _cx(delem) - 45,
            "elements": _cx(delem) + 12, "total_count": _cx(total) + 8, "spacing_cm": _cx(esp) + 8 if esp else None,
            "unit_length_cm": _cx(longs[0]) + 10, "shape": _cx(faconnage) + 20 if faconnage else None,
            "mandrel_cm": _cx(mandrin) if mandrin else None, "total_length_cm": _cx(totale) + 10}
    return {"cols": {k: v for k, v in cols.items() if v is not None}, "y": max(w[3] for w in band if w[4] in ("TOTAL", "TOTALE", "Unitaire")), "x_max": totale[2] + 40}


def _mesh_header(words, title):
    y0, y1 = title[3], title[3] + 90
    band = [w for w in words if y0 <= w[1] <= y1 and title[0] - 160 <= w[0] <= title[2] + 420]
    get = lambda t: next((w for w in sorted(band, key=lambda w: w[0]) if w[4] == t), None)  # noqa: E731
    n, panel, delem, total, trans, port, cuts, masse = get("N°"), get("Panneau"), get("d'éléments"), get("TOTAL"), get("Transversal"), get("Porteur"), get("Découpes"), get("Masse")
    if not all([n, panel, delem, total, masse]):
        return None
    par, elem = get("Par"), get("Elément")
    cols = {"mark": _cx(n), "panel": _cx(panel), "per_element": (_cx(par) + _cx(elem)) / 2 if par and elem else _cx(delem) - 45,
            "elements": _cx(delem) + 8, "total_count": _cx(total) + 8,
            "overlap_transversal_cm": _cx(trans) + 8 if trans else None, "overlap_bearing_cm": _cx(port) + 8 if port else None,
            "cuts": _cx(cuts) + 20 if cuts else None, "mass_kg": _cx(masse) + 10}
    return {"cols": {k: v for k, v in cols.items() if v is not None}, "y": max(w[3] for w in (n, panel, delem, total, masse, trans, port, cuts) if w), "x_max": masse[2] + 60}


def _clusters(anchors):
    groups = []
    for a in sorted(anchors, key=lambda w: w[0]):
        for g in groups:
            if abs(g[0][0] - a[0]) <= ANCHOR_X_TOL:
                g.append(a)
                break
        else:
            groups.append([a])
    return [sorted(g, key=lambda w: w[1]) for g in groups if len(g) >= 2]



def _assign(row_words, cols, shift, order, *, max_dist=32.0, free_between=None):
    """Nearest-column assignment with a distance cap; one value per numeric column, surplus goes to the free (shape/cuts) column."""
    centres = {k: cols[k] + shift for k in order if k in cols}
    free_key, lo, hi = free_between if free_between else (None, None, None)
    out, dist = defaultdict(list), {}
    for w in sorted(row_words, key=lambda w: w[0]):
        cx = _cx(w)
        key = min(centres, key=lambda k: abs(centres[k] - cx))
        d = abs(centres[key] - cx)
        in_free = free_key and lo is not None and lo + shift <= cx <= hi + shift
        if key == free_key or (d > max_dist and in_free):
            out[free_key].append(w[4])
            continue
        if d > max_dist:
            continue
        if key in out and key not in ("mark", "type", "panel"):
            if d < dist[key]:
                if in_free:
                    out[free_key].append(out[key][0])
                out[key], dist[key] = [w[4]], d
            elif in_free:
                out[free_key].append(w[4])
            continue
        out[key].append(w[4])
        dist[key] = d
    return out


def _bbox(ws):
    return [round(min(w[0] for w in ws), 1), round(min(w[1] for w in ws), 1), round(max(w[2] for w in ws), 1), round(max(w[3] for w in ws), 1)]


def _ref_shift(clusters, header, key):
    ref = min((c[0][0] for c in clusters if abs(c[0][0] - header["cols"][key]) < 40), default=None)
    return ref


def _h_rules(page) -> list[tuple]:
    """Horizontal ruling lines of the printed tables (y, x0, x1) — the row separators that bound multi-line cells."""
    rules = []
    for d in page.get_drawings():
        for it in d.get("items", []):
            if it[0] == "l" and abs(it[1].y - it[2].y) < 0.6 and abs(it[1].x - it[2].x) > 8:
                rules.append((round((it[1].y + it[2].y) / 2, 1), min(it[1].x, it[2].x), max(it[1].x, it[2].x)))
            elif it[0] == "re" and it[1].height < 0.6 and it[1].width > 8:
                rules.append((round(it[1].y0, 1), it[1].x0, it[1].x1))
    return sorted(set(rules))


def _band(rules, x_lo, x_hi, y):
    """Row band [top, bottom] around y bounded by the nearest rules crossing the column; None when the table has no rules."""
    cx = (x_lo + x_hi) / 2
    ys = sorted({r[0] for r in rules if r[1] <= cx <= r[2] and (r[2] - r[1]) >= 0.4 * (x_hi - x_lo)})
    above = [v for v in ys if v <= y]
    below = [v for v in ys if v > y]
    return (above[-1], below[0]) if above and below else None


def _free_by_anchor(words, cluster, lo, hi, rules=()):
    """Words of the free column (shape sketch dims / cut list): same ruled row band as the anchor, else nearest anchor centre."""
    ys = [_cy(a) for a in cluster]
    bands = [_band(rules, lo, hi, y) for y in ys]
    out = defaultdict(list)
    for w in sorted(words, key=lambda w: (_cy(w), w[0])):
        cy = _cy(w)
        if not (lo <= _cx(w) <= hi and ys[0] - 22 <= cy <= ys[-1] + 22):
            continue
        hit = next((k for k, b in enumerate(bands) if b and b[0] <= cy <= b[1]), None)
        if hit is None and any(bands):
            continue
        out[hit if hit is not None else min(range(len(ys)), key=lambda k: abs(ys[k] - cy))].append(w)
    return out


def parse_ha_table(words, header, anchor_x_ref, rules=()) -> list[dict]:
    cols = header["cols"]
    anchors = [w for w in words if re.fullmatch(r"HA\d*", w[4]) and (w[1] > header["y"] or abs(w[0] - anchor_x_ref) > 100)]
    clusters = _clusters(anchors)
    ref = _ref_shift(clusters, header, "type") or anchor_x_ref
    shape_lo, shape_hi = cols["unit_length_cm"] + 28, cols.get("mandrel_cm", cols["total_length_cm"] - 40) - 18
    rows = []
    for cluster in clusters:
        shift = cluster[0][0] - ref
        x_lo, x_hi = cols["mark"] + shift - 25, cols["total_length_cm"] + shift + 30
        free = _free_by_anchor(words, cluster, shape_lo + shift, shape_hi + shift, rules)
        for i, a in enumerate(cluster):
            y = _cy(a)
            main = [w for w in words if abs(_cy(w) - y) <= ROW_TOL and x_lo <= w[0] <= x_hi and not (shape_lo + shift <= _cx(w) <= shape_hi + shift)]
            cells = _assign(main, cols, shift, HA_COLUMNS)
            dia_txt = "".join(cells.get("diameter_mm", [])) or a[4][2:]
            row = {"mark": " ".join(cells.get("mark", [])) or None, "type": "".join(cells.get("type", [])) or a[4],
                   "diameter_mm": _num(dia_txt), "per_element": _num("".join(cells.get("per_element", []))),
                   "elements": _num("".join(cells.get("elements", []))), "total_count": _num("".join(cells.get("total_count", []))),
                   "spacing_cm": _num("".join(cells.get("spacing_cm", []))), "unit_length_cm": _num("".join(cells.get("unit_length_cm", []))),
                   "mandrel_cm": _num("".join(cells.get("mandrel_cm", []))), "total_length_cm": _num("".join(cells.get("total_length_cm", []))),
                   "shape_dims": [w[4] for w in free.get(i, [])], "bbox_pt": _bbox(main + free.get(i, [])), "origin": "native_text"}
            if row["diameter_mm"] is None or (row["total_count"] is None and row["total_length_cm"] is None):
                continue
            rows.append(row)
    return rows


def parse_mesh_table(words, header, anchor_x_ref, rules=()) -> list[dict]:
    cols = header["cols"]
    anchors = [w for w in words if re.fullmatch(r"T\d{1,3}", w[4]) and (w[1] > header["y"] or abs(w[0] - anchor_x_ref) > 100)]
    clusters = _clusters(anchors)
    ref = _ref_shift(clusters, header, "mark") or anchor_x_ref
    cuts_c = cols.get("cuts")
    cuts_lo, cuts_hi = (cuts_c - 60, cuts_c + 60) if cuts_c else (None, None)
    rows = []
    for cluster in clusters:
        shift = cluster[0][0] - ref
        x_lo, x_hi = cols["mark"] + shift - 20, cols["mass_kg"] + shift + 30
        free = _free_by_anchor(words, cluster, cuts_lo + shift, cuts_hi + shift, rules) if cuts_c else {}
        for i, a in enumerate(cluster):
            y = _cy(a)
            main = [w for w in words if abs(_cy(w) - y) <= ROW_TOL and x_lo <= w[0] <= x_hi and not (cuts_c and cuts_lo + shift <= _cx(w) <= cuts_hi + shift)]
            cells = _assign(main, cols, shift, MESH_COLUMNS)
            row = {"mark": a[4], "panel": " ".join(cells.get("panel", [])) or None,
                   "per_element": _num("".join(cells.get("per_element", []))), "elements": _num("".join(cells.get("elements", []))),
                   "total_count": _num("".join(cells.get("total_count", []))),
                   "overlap_transversal_cm": _num("".join(cells.get("overlap_transversal_cm", []))),
                   "overlap_bearing_cm": _num("".join(cells.get("overlap_bearing_cm", []))),
                   "cuts": _parse_cuts([w[4] for w in free.get(i, [])]), "mass_kg": _num("".join(cells.get("mass_kg", []))),
                   "bbox_pt": _bbox(main + free.get(i, [])), "origin": "native_text"}
            if row["mass_kg"] is None or row["total_count"] is None or not row["panel"] or not re.match(r"(TS|ST|FAP|PAF|P)\w*", row["panel"]):
                continue
            rows.append(row)
    return rows


def _parse_cuts(tokens: list[str]) -> list[dict]:
    text = " ".join(tokens)
    return [{"count": int(c), "width_cm": int(a), "height_cm": int(b)} for c, a, b in re.findall(r"(\d+)\s*x\s*(\d+)x(\d+)", text)]


def parse_mesh_recap(words) -> dict | None:
    title = _title(words, "RECAPITULATIF", "MALHAS")
    if not title:
        return None
    hdr = [w for w in words if title[3] - 2 <= w[1] <= title[3] + 22 and title[0] - 130 <= w[0] <= title[2] + 300]
    get = lambda t: next((w for w in sorted(hdr, key=lambda w: w[0]) if w[4] == t), None)  # noqa: E731
    panel, nombre, dims, masse = get("Panneau"), get("Nombre"), get("Dimensions"), get("Masse")
    if not all([panel, nombre, dims, masse]):
        return None
    rows = []
    y_hdr = max(w[3] for w in hdr)
    last_y = y_hdr
    for d in sorted([w for w in words if _DIMS.match(w[4]) and w[1] > y_hdr and abs(_cx(w) - _cx(dims)) <= 40], key=lambda w: w[1]):
        if d[1] - last_y > 80:
            break
        last_y = d[3]
        row_words = [w for w in words if abs(_cy(w) - _cy(d)) <= ROW_TOL and panel[0] - 30 <= w[0] <= masse[2] + 60]
        pw = [w[4] for w in sorted(row_words, key=lambda w: w[0]) if _cx(w) < _cx(nombre) - 20]
        nb = next((_num(w[4]) for w in row_words if abs(_cx(w) - _cx(nombre)) <= 30 and _NUM.match(w[4])), None)
        ms = next((_num(w[4]) for w in row_words if _cx(w) > _cx(dims) + 40 and _NUM.match(w[4])), None)
        m = _DIMS.match(d[4])
        rows.append({"panel": " ".join(pw) or None, "count": nb, "width_cm": int(m.group(1)), "height_cm": int(m.group(2)), "mass_kg": ms,
                     "bbox_pt": _bbox(row_words), "origin": "native_text"})
    total = round(sum(r["mass_kg"] for r in rows if r["mass_kg"] is not None), 1) if rows else None
    return {"rows": rows, "sum_mass_kg": total, "mass_laid_kg": _labelled_kg(words, "posée"), "mass_total_kg": _labelled_kg(words, "totale", prefix="Massa")}


def _labelled_kg(words, label, *, prefix=None):
    """Number printed right after « <prefix> <label> : » on the same row (e.g. « Masse posée : 2476 kg »)."""
    for w in words:
        if w[4].lower() != label.lower():
            continue
        row = sorted([o for o in words if abs(_cy(o) - _cy(w)) <= ROW_TOL], key=lambda o: o[0])
        idx = next((i for i, o in enumerate(row) if o is w), None)
        if idx is None or (prefix and (idx == 0 or row[idx - 1][4] != prefix)):
            continue
        after = row[idx + 1:]
        for j, o in enumerate(after):
            if _NUM.match(o[4]) and j + 1 < len(after) and after[j + 1][4].lower() == "kg":
                return _num(o[4])
            if _NUM.match(o[4]) and o[4].replace(".", "").isdigit() and len(o[4]) >= 3:
                return _num(o[4])
    return None


def parse_steel_recap(words) -> dict | None:
    """« RECAP DES ACIERS » : Poids HA façonnés / non façonnés (kg), when printed."""
    title = _title(words, "RECAP", "DES", "AÇOS")
    if not title:
        return None
    out = {}
    for w in words:
        if w[4] != "Poids" or w[1] < title[3] - 2 or w[1] > title[3] + 200:
            continue
        row = sorted([o for o in words if abs(_cy(o) - _cy(w)) <= ROW_TOL and o[0] >= w[0]], key=lambda o: o[0])
        value_w = next((o for o in row if _NUM.match(o[4])), None)
        label = " ".join(o[4] for o in row[1:] if (value_w is None or o[0] < value_w[0]) and not _NUM.match(o[4]) and o[4] != "..")
        value = _num(value_w[4]) if value_w else None
        key = "ha_straight_kg" if "non" in label.split() else "ha_shaped_kg"
        out[key] = value
        out[key.replace("_kg", "_label")] = label
    return out or None


def check_ha_rows(rows: list[dict]) -> dict:
    """count × unit length = total length ; mass = total length × kg/m (theoretical, EN 10080)."""
    by_dia, checks, mass = defaultdict(lambda: {"count": 0, "length_m": 0.0, "mass_kg": 0.0}), [], 0.0
    for r in rows:
        pe, ne, tot, lu, lt = r["per_element"], r["elements"], r["total_count"], r["unit_length_cm"], r["total_length_cm"]
        if pe is not None and ne is not None and tot is not None:
            checks.append({"mark": r["mark"], "check": "per_element × elements = total", "formula": f"{pe:g} × {ne:g} = {pe * ne:g}",
                           "declared": tot, "state": "confirmed" if abs(pe * ne - tot) < 0.5 else "to_clarify"})
        if tot is not None and lu is not None and lt is not None:
            checks.append({"mark": r["mark"], "check": "total × unit length = total length", "formula": f"{tot:g} × {lu:g} cm = {tot * lu:g} cm",
                           "declared": lt, "state": "confirmed" if abs(tot * lu - lt) <= max(1.0, 0.005 * lt) else "to_clarify"})
        dia = f"HA{int(r['diameter_mm'])}" if r["diameter_mm"] else None
        kg_m = STEEL_KG_PER_M.get(dia or "")
        if dia and lt is not None and kg_m:
            row_mass = lt / 100 * kg_m
            r["mass_kg"] = round(row_mass, 2)
            r["kg_per_m"] = kg_m
            by_dia[dia]["count"] += int(tot or 0)
            by_dia[dia]["length_m"] += lt / 100
            by_dia[dia]["mass_kg"] += row_mass
            mass += row_mass
    return {"by_diameter": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in sorted(by_dia.items())},
            "total_mass_kg": round(mass, 1), "checks": checks,
            "inconsistencies": [c for c in checks if c["state"] != "confirmed"]}


def check_mesh(rows: list[dict], recap: dict | None) -> dict:
    total = round(sum(r["mass_kg"] for r in rows if r["mass_kg"] is not None), 1)
    by_panel = defaultdict(lambda: {"count": 0, "mass_kg": 0.0})
    for r in rows:
        if r["panel"]:
            by_panel[r["panel"]]["count"] += int(r["total_count"] or 0)
            by_panel[r["panel"]]["mass_kg"] += r["mass_kg"] or 0.0
    out = {"rows_mass_kg": total, "by_panel": {k: {"count": v["count"], "mass_kg": round(v["mass_kg"], 1)} for k, v in sorted(by_panel.items())}, "comparisons": []}
    if recap:
        if recap.get("mass_laid_kg") is not None:
            out["comparisons"].append({"a": "Σ lista de malhas (painéis colocados)", "a_kg": total, "b": "Massa colocada (legenda)", "b_kg": recap["mass_laid_kg"],
                                       "difference_kg": round(total - recap["mass_laid_kg"], 1), "expect_equal": True})
        if recap.get("sum_mass_kg") is not None and recap.get("mass_total_kg") is not None:
            out["comparisons"].append({"a": "Σ resumo de malhas (painéis a encomendar)", "a_kg": recap["sum_mass_kg"], "b": "Massa total (legenda)", "b_kg": recap["mass_total_kg"],
                                       "difference_kg": round(recap["sum_mass_kg"] - recap["mass_total_kg"], 1), "expect_equal": True})
        if recap.get("mass_total_kg") is not None and recap.get("mass_laid_kg") is not None:
            out["comparisons"].append({"a": "Massa total (encomendada)", "a_kg": recap["mass_total_kg"], "b": "Massa colocada", "b_kg": recap["mass_laid_kg"],
                                       "difference_kg": round(recap["mass_total_kg"] - recap["mass_laid_kg"], 1), "expect_equal": False,
                                       "meaning": "desperdícios de corte dos painéis (valores impressos, não recalculados)"})
    return out


def extract_rebar_schedule(page) -> dict:
    """Read every reinforcement table printed on a page; empty tables mean « not found », never zero."""
    words = _words(page)
    rules = _h_rules(page)
    result = {"ha_bars": None, "mesh": None, "mesh_recap": None, "steel_recap": None, "partial": False, "findings": [], "page_size_pt": [round(page.rect.width, 1), round(page.rect.height, 1)]}
    ha_title = _title(words, "Nomenclature", "des", "aciers")
    if ha_title:
        result["partial"] = result["partial"] or any(w[4].startswith("(partielle") for w in words if abs(_cy(w) - _cy(ha_title)) <= ROW_TOL)
        header = _ha_header(words, ha_title)
        if header:
            rows = parse_ha_table(words, header, header["cols"]["type"] - 13, rules)
            result["ha_bars"] = {"rows": rows, "count": len(rows), **check_ha_rows(rows)}
    mesh_title = _title(words, "Nomenclature", "de", "treillis")
    if mesh_title:
        result["partial"] = result["partial"] or any(w[4].startswith("(partielle") for w in words if abs(_cy(w) - _cy(mesh_title)) <= ROW_TOL)
        header = _mesh_header(words, mesh_title)
        if header:
            rows = parse_mesh_table(words, header, header["cols"]["mark"] - 6, rules)
            result["mesh"] = {"rows": rows, "count": len(rows)}
    result["mesh_recap"] = parse_mesh_recap(words)
    result["steel_recap"] = parse_steel_recap(words)
    recap = result["steel_recap"] or {}
    if result["ha_bars"] and recap.get("ha_shaped_kg") is not None:
        recap_total = round(recap["ha_shaped_kg"] + (recap.get("ha_straight_kg") or 0.0), 1)
        result["ha_bars"]["comparison"] = {"a": "Σ lista A500 (massa teórica)", "a_kg": result["ha_bars"]["total_mass_kg"],
                                          "b": "Resumo de aços: A500 moldados + não moldados", "b_kg": recap_total,
                                          "difference_kg": round(result["ha_bars"]["total_mass_kg"] - recap_total, 1)}
    if result["mesh"]:
        result["mesh"].update(check_mesh(result["mesh"]["rows"], result["mesh_recap"]))
    if result["partial"]:
        result["findings"].append({"severity": "info", "subject": "Nomenclature partielle",
                                   "explanation": "A folha indica «(parcial)»: os totais das tabelas não representam o conjunto dos aços do piso."})
    for c in (result["ha_bars"] or {}).get("inconsistencies", []):
        result["findings"].append({"severity": "to_clarify", "subject": f"Referência {c['mark']}", "explanation": f"{c['check']} : {c['formula']} ≠ {c['declared']:g} (valor impresso)."})
    if not (ha_title or mesh_title or result["mesh_recap"]):
        result["findings"].append({"severity": "info", "subject": "Nenhuma lista nativa",
                                   "explanation": "Nenhuma tabela de lista em texto nativo nesta página (texto vetorizado ou planta digitalizada: leitura visual necessária)."})
    result["note"] = "Valores lidos no texto nativo do PDF; massas A500 = comprimento total × massa linear teórica (EN 10080). Nenhum valor corrigido."
    return result


def extract_from_pdf_bytes(pdf_bytes: bytes, page_index: int = 0) -> dict:
    import pymupdf
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        if page_index < 0 or page_index >= len(doc):
            raise ValueError("Página ausente do PDF")
        return {"page": page_index, **extract_rebar_schedule(doc[page_index])}
