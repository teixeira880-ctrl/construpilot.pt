"""Bibliothèque de prix propre à l'entreprise (Excel / PDF).

Parse un bordereau de prix uploadé par un Pro (.xlsx ou .pdf) en lignes
{designation, unit, unit_price, ref} et fournit une correspondance floue
pour retrouver le prix d'une ligne de DPGF avant de recourir à l'IA.
"""
import base64
import io
import re
from difflib import SequenceMatcher

import openpyxl
import pymupdf
from PIL import Image

_DESIGN = ("désignation", "designation", "libellé", "libelle", "prestation",
           "descriptif", "ouvrage", "article", "produit", "description")
_UNIT = ("unité", "unite", "un.", "u.", "unit")
_PU = ("prix unitaire", "p.u", "pu ht", "prix u", "prix", "tarif", "pu")
_REF = ("réf", "ref", "code", "référence", "reference")

# Mots vides ignorés pour la comparaison floue des désignations.
_STOP = {"de", "du", "des", "la", "le", "les", "en", "et", "a", "au", "aux",
         "un", "une", "pour", "avec", "sur", "par", "ml", "m2", "m3"}


def _norm(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip().lower())


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return None
    s = re.sub(r"[^\d,.-]", "", str(v)).replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _tokens(s: str) -> set:
    return {w for w in re.split(r"[^a-z0-9àâçéèêëîïôûùüÿñæœ]+", _norm(s))
            if w and w not in _STOP and len(w) > 1}


def similarity(a: str, b: str) -> float:
    """Score de similarité 0..1 combinant recouvrement de tokens + ratio de séquence."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    jacc = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    return 0.6 * jacc + 0.4 * seq


def parse_excel(raw: bytes) -> list[dict]:
    """Lit un bordereau de prix Excel → lignes {designation, unit, unit_price, ref}."""
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    lines = []
    for ws in wb.worksheets:
        hrow, cols = _find_header(ws)
        if not hrow:
            continue
        c_des, c_unit, c_pu, c_ref = (cols.get("design"), cols.get("unit"),
                                      cols.get("pu"), cols.get("ref"))
        for r in range(hrow + 1, ws.max_row + 1):
            des = ws.cell(row=r, column=c_des).value if c_des else None
            pu = _num(ws.cell(row=r, column=c_pu).value) if c_pu else None
            if not _norm(des) or not pu or pu <= 0:
                continue
            lines.append({
                "designation": str(des).strip()[:300],
                "unit": (str(ws.cell(row=r, column=c_unit).value or "").strip()[:20]
                         if c_unit else ""),
                "unit_price": round(pu, 2),
                "ref": (str(ws.cell(row=r, column=c_ref).value or "").strip()[:40]
                        if c_ref else ""),
            })
    return lines


def _find_header(ws):
    for r in range(1, min(ws.max_row, 40) + 1):
        cells = {c: _norm(ws.cell(row=r, column=c).value)
                 for c in range(1, min(ws.max_column, 30) + 1)}
        cols = {}
        for c, val in cells.items():
            if not val:
                continue
            if "design" not in cols and any(k in val for k in _DESIGN):
                cols["design"] = c
            elif "ref" not in cols and any(val == k or val.startswith(k) for k in _REF):
                cols["ref"] = c
            elif "unit" not in cols and any(val == k or val.startswith(k) for k in _UNIT):
                cols["unit"] = c
            elif "pu" not in cols and any(k in val for k in _PU):
                cols["pu"] = c
        if "design" in cols and "pu" in cols:
            return r, cols
    return None, {}


def pdf_to_images_b64(raw: bytes, max_pages: int = 12, dpi: int = 150) -> list[str]:
    """Rend chaque page PDF en PNG base64 (pour analyse Vision IA)."""
    doc = pymupdf.open(stream=raw, filetype="pdf")
    out = []
    for i, page in enumerate(doc):
        if i >= max_pages:
            break
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img.thumbnail((1600, 1600))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        out.append(base64.b64encode(buf.getvalue()).decode())
    doc.close()
    return out


def match_price(designation: str, unit: str, library: list[dict],
                threshold: float = 0.55):
    """Retrouve le meilleur prix de la bibliothèque pour une ligne de DPGF.

    Priorité au code/référence si présent, sinon similarité de désignation.
    Retourne (unit_price, matched_designation, score) ou None.
    """
    if not library:
        return None
    best, best_score = None, 0.0
    for it in library:
        score = similarity(designation, it.get("designation", ""))
        u = _norm(unit)
        iu = _norm(it.get("unit"))
        if u and iu and u == iu:
            score += 0.1
        if score > best_score:
            best, best_score = it, score
    if best and best_score >= threshold:
        return (best["unit_price"], best["designation"], round(best_score, 2))
    return None
