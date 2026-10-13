"""Level symbols of BEGT-style formwork plans (example supplied by the user, 15/09/2026):

    ┌ 60.55b ┐   NGF level of the slab top (suffix b = brut, f = fini)
    │  NGF   │
    │   18   │   slab thickness (cm)
    └  CS    ┘   CS = coulé sur place, CSP = coulé sur prédalle (as printed)
plus opening labels « LT(Ai: 59.95) », « Allège(As:60.80) », « Seuil(As:60.65) », « Relevé(As:60.65) », « GT - 01a (60x190 ht) ».
Everything is read from text; AI plancher = NGF − épaisseur only when both are printed in the same symbol.
"""
import re

NGF_LEVEL = re.compile(r"^([+-]?\d{2,3}[.,]\d{2})\s*([bf])?$", re.I)
THICKNESS = re.compile(r"^\d{2,3}$")
KIND = re.compile(r"^(CSP|CS|PREDALLE|PRÉDALLE|PREFA|PRÉFA)$", re.I)
OPENING = re.compile(r"(LT|All[èe]ge|Seuil|Relev[ée]|Acrot[èe]re|Poutre|Voile|Mur)\s*\(\s*(A[isS])\s*:?\s*([+-]?\d{2,3}[.,]\d{2,3})\s*\)", re.I)
SIZE = re.compile(r"\b([A-Z]{2})\s*-\s*(\d{2}[a-z]?)\s*\((\d{2,4})\s*x\s*(\d{2,4})\s*ht?\)", re.I)


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def parse_level_symbols(words: list[tuple], *, radius_pt: float | None = None) -> dict:
    """words = (x0, y0, x1, y1, text). A symbol = « NGF » word with, within the circle: a level (« 93,37 » ± « B »), a thickness (« 20 »),
    optionally « 93.44 fini » and CS/CSP. Works for upright and rotated symbols (proximity only, no reading order)."""
    ngf = [w for w in words if w[4].strip().upper() == "NGF"]
    symbols, used = [], set()
    for n in ngf:
        cx, cy = (n[0] + n[2]) / 2, (n[1] + n[3]) / 2
        r = radius_pt or 4.5 * max(n[2] - n[0], n[3] - n[1])
        near = sorted([w for w in words if w is not n and abs((w[0] + w[2]) / 2 - cx) <= r and abs((w[1] + w[3]) / 2 - cy) <= r],
                      key=lambda w: abs((w[0] + w[2]) / 2 - cx) + abs((w[1] + w[3]) / 2 - cy))
        lv = [w for w in near if NGF_LEVEL.match(w[4].strip())]
        if not lv or any(re.fullmatch(r"A[isS]:?", w[4].strip()) for w in near):
            continue  # « Ai: 92,77 NGF » = opening / reservation label, not a slab symbol
        fini_w = next((w for w in near if w[4].strip().lower() in ("fini", "f")), None)
        brut_w = next((w for w in near if w[4].strip().lower() in ("brut", "b")), None)
        def _dist(a, b):
            return abs((a[0] + a[2]) / 2 - (b[0] + b[2]) / 2) + abs((a[1] + a[3]) / 2 - (b[1] + b[3]) / 2)
        brut = min(lv, key=lambda w: _dist(w, brut_w) if brut_w else _dist(w, n))
        m = NGF_LEVEL.match(brut[4].strip())
        fini = next((w for w in lv if w is not brut and (m.group(2) or "").lower() != "f" and (fini_w is None or _dist(w, fini_w) < _dist(brut, fini_w))), None)
        thick = next((w[4].strip() for w in near if THICKNESS.match(w[4].strip()) and 8 <= int(w[4]) <= 60), None)
        kind = next((w[4].strip().upper() for w in near if KIND.match(w[4].strip())), None)
        as_m = _f(m.group(1))
        sym = {"as_plancher_m": as_m, "finish": "fini" if (m.group(2) or "").lower() == "f" else "brut", "as_fini_m": _f(NGF_LEVEL.match(fini[4].strip()).group(1)) if fini else None,
               "epaisseur_cm": int(thick) if thick else None, "kind": kind, "x": round(cx, 1), "y": round(cy, 1),
               "raw": " ".join(w[4] for w in [brut, n] + ([fini] if fini else []) + [w for w in near if w[4].strip() == thick][:1])}
        sym["ai_plancher_m"] = round(as_m - int(thick) / 100, 3) if thick else None
        symbols.append(sym)
    text = "\n".join(w[4] for w in words)
    openings = [{"element": m.group(1), "kind": m.group(2).upper()[:2].replace("AS", "AS").replace("AI", "AI"), "level_m": _f(m.group(3)), "raw": m.group(0)} for m in OPENING.finditer(text)]
    sizes = [{"type": m.group(1).upper(), "ref": m.group(2), "w_cm": int(m.group(3)), "h_cm": int(m.group(4)), "raw": m.group(0)} for m in SIZE.finditer(text)]
    levels = sorted({s["as_plancher_m"] for s in symbols})
    thicknesses = sorted({s["epaisseur_cm"] for s in symbols if s["epaisseur_cm"]})
    return {"symbols": symbols, "distinct_as_plancher_m": levels, "distinct_epaisseur_cm": thicknesses, "openings": openings, "sizes": sizes,
            "dominant": {"as_plancher_m": max(levels, key=lambda v: sum(1 for s in symbols if s["as_plancher_m"] == v)) if levels else None,
                         "epaisseur_cm": max(thicknesses, key=lambda v: sum(1 for s in symbols if s["epaisseur_cm"] == v)) if thicknesses else None},
            "note": "Niveaux lus dans les symboles NGF (niveau / épaisseur / CS-CSP) et étiquettes (Ai/As) ; AI plancher = NGF − épaisseur du même symbole. Aucun niveau déduit."}


def levels_from_symbols(parsed: dict, *, base_level_m: float | None, source: str) -> dict:
    """Build the input of heights.derive_heights from the dominant slab symbol; the base level comes from the lower floor plan or the user."""
    dom = parsed["dominant"]
    out = {"as_plancher_haut_m": dom["as_plancher_m"], "epaisseur_dalle_m": dom["epaisseur_cm"] / 100 if dom["epaisseur_cm"] else None, "niveau_base_murs_m": base_level_m, "source": source}
    others = [s for s in parsed["symbols"] if s["as_plancher_m"] != dom["as_plancher_m"] or s["epaisseur_cm"] != dom["epaisseur_cm"]]
    out["exceptions"] = [{"as_plancher_m": s["as_plancher_m"], "epaisseur_cm": s["epaisseur_cm"], "x": s["x"], "y": s["y"]} for s in others]
    return out


def words_from_pdf_page(page) -> list[tuple]:
    return [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
