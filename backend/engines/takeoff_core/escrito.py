"""Cross-check of the take-off against what is WRITTEN on the plans (every building system).

Same rule as the CLT dossier: a quantity read from the geometry is compared with the text of the sheet it came from.
Three things are usually written on an architect's plan and can be checked without interpretation:

- the ceiling height (pé-direito / HSP / ceiling height): the structural wall of the study must not be lower than it,
  nor more than 0.60 m higher (slab and floor build-up);
- the room areas ("Sala 23,45 m²"): their sum is compared with the rooms measured in the study;
- the wall thicknesses ("parede 25 cm", "ép. 20 cm"): each thickness used must exist in writing.

What is not written is reported as "nothing written to check", never assumed to agree.
"""
from __future__ import annotations

import re

AREA_TOL_PCT = 3.0
HEIGHT_OVER_M = 0.60

_NUM = r"(\d{1,4}(?:[.,]\d{1,3})?)"
_AREA = re.compile(_NUM + r"\s*m\s?(?:2|²)(?![\w/])", re.I)
_TOTAL = re.compile(r"(total|bruta|brute|útil|util|habitable|implanta|constru|gross|net\b|lote|terreno|parcelle|shab|shon|abc\b|plot)", re.I)
_HEIGHT = [
    re.compile(r"(?:p[ée][\s.-]*direito|p\.?\s?d\.?|hsp|h\.?s\.?p\.?|hauteur sous plafond|ceiling height|clear height)\s*[:=]?\s*" + _NUM + r"\s*(mm|cm|m)?", re.I),
]
_THICK = re.compile(r"(?:parede|paredes|muro|mur|murs|wall|walls|tijolo|bloco|brique|parpaing|bet[ãa]o|b[ée]ton|esp\.?|espessura|[ée]p\.?|[ée]paisseur|thk\.?|thickness)"
                    r"[^\d\n]{0,25}?" + _NUM + r"\s*(mm|cm|m)\b", re.I)


def _f(s):
    return float(s.replace(",", "."))


def _metres(v, unit, *, default_big="mm"):
    unit = (unit or "").lower()
    if unit == "mm" or (not unit and v > 100 and default_big == "mm"):
        return v / 1000
    if unit == "cm" or (not unit and 20 < v <= 100):
        return v / 100
    return v


def ler(text: str) -> dict:
    """What a sheet says in writing → {"areas": [m²], "totais": [(label, m²)], "alturas_m": [m], "espessuras_mm": [mm]}."""
    text = text or ""
    areas, totals = [], []
    for line in re.split(r"[\n\r]+", text):
        for m in _AREA.finditer(line):
            v = _f(m.group(1))
            if v <= 0:
                continue
            (totals if _TOTAL.search(line) else areas).append((" ".join(line.split())[:60], v) if _TOTAL.search(line) else v)
    heights = sorted({round(_metres(_f(m.group(1)), m.group(2)), 3) for rx in _HEIGHT for m in rx.finditer(text)
                      if 1.8 <= _metres(_f(m.group(1)), m.group(2)) <= 12})
    thick = sorted({int(round(_metres(_f(m.group(1)), m.group(2)) * 1000)) for m in _THICK.finditer(text)
                    if 40 <= _metres(_f(m.group(1)), m.group(2)) * 1000 <= 800})
    return {"areas": areas, "totais": totals, "alturas_m": heights, "espessuras_mm": thick}


def _poly_area(pts):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


def cruzar(result: dict, textos: dict, rooms: dict | None = None) -> list[dict]:
    """result: estudo.run(...); textos: {floor name: text of its sheet}; rooms: {floor name: [polygon, …]} measured rooms.

    → rows {"piso", "item", "escrito", "usado", "ok": True | False | None, "nota"}; ok None = nothing written to check."""
    rows = []
    rooms = rooms or {}

    def row(piso, item, escrito, usado, ok, nota=""):
        rows.append({"piso": piso, "item": item, "escrito": escrito, "usado": usado, "ok": ok, "nota": nota})

    for f in result.get("pisos") or []:
        name = f["nome"]
        if name not in textos:
            row(name, "texto", "—", "—", None, "sem_folha")
            continue
        w = ler(textos[name])
        height = f["altura"]["valor_m"] if isinstance(f["altura"], dict) else float(f["altura"])
        if w["alturas_m"]:
            ok = any(h - 0.011 <= height <= h + HEIGHT_OVER_M for h in w["alturas_m"])
            row(name, "altura", " / ".join(f"{h:.2f} m" for h in w["alturas_m"]), f"{height:.2f} m", ok,
                "" if ok else "altura_fora")
        else:
            row(name, "altura", "—", f"{height:.2f} m", None, "nao_escrito")
        measured = [_poly_area(list(p)) for p in (rooms or {}).get(name) or []]
        if w["areas"] and measured:
            a, b = sum(w["areas"]), sum(measured)
            err = abs(a - b) / a * 100 if a else None
            ok = err is not None and err <= AREA_TOL_PCT and len(w["areas"]) == len(measured)
            row(name, "divisoes", f"{len(w['areas'])} × = {a:.2f} m²", f"{len(measured)} × = {b:.2f} m²", ok,
                "" if ok else ("divisoes_numero" if len(w["areas"]) != len(measured) else "divisoes_area"))
        elif w["areas"]:
            row(name, "divisoes", f"{len(w['areas'])} × = {sum(w['areas']):.2f} m²", "—", None, "divisoes_nao_medidas")
        else:
            row(name, "divisoes", "—", f"{len(measured)} × = {sum(measured):.2f} m²" if measured else "—", None, "nao_escrito")
        used = sorted({int(round(wl.thickness_mm)) for n_, walls, _p in result.get("_redes") or [] if n_ == name for wl in walls})
        if w["espessuras_mm"] and used:
            ok = all(any(abs(t - e) <= 30 for e in w["espessuras_mm"]) for t in used)
            row(name, "espessuras", " / ".join(f"{e} mm" for e in w["espessuras_mm"]), " / ".join(f"{t} mm" for t in used), ok,
                "" if ok else "espessura_fora")
        elif used:
            row(name, "espessuras", "—", " / ".join(f"{t} mm" for t in used), None, "nao_escrito")
    return rows


def resumo(rows: list[dict]) -> dict:
    return {"conferem": sum(r["ok"] is True for r in rows), "nao_conferem": sum(r["ok"] is False for r in rows),
            "sem_texto": sum(r["ok"] is None for r in rows)}
