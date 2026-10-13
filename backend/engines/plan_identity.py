"""Document identity from native title-block text: revision index, revision date (≠ upload date), declared scale, document code."""
import re
from datetime import datetime

REV_ROW = re.compile(r"\b([A-K])\s+(\d{2}/\d{2}/\d{4})\s+([A-ZÀ-Ý][^|\n]{0,80}?)(?=\s+[A-K]\s+\d{2}/\d{2}/\d{4}|\s*$|\s+\d{1,2}D\b|\s{2,})")
SCALE = re.compile(r"(?<!\d)1\s*[/:]\s*(20|25|50|75|100|200|250|500)(?!\d)")
REV_ROW_NUM = re.compile(r"(?<![\w/])(\d{1,2}|[A-K])\s+((?:1[èe]re|Premi[èe]re|Diffusion|Mise|Modif\w*|Cr[ée]ation|Ajout|Suppression|Correction|R[ée]vision|[ÉE]mission)[^|\n]{0,60}?)\s+(\d{2}/\d{2}/\d{4})")
DOC_CODE = re.compile(r"\b(COF|FER|ARM|ARC|PLA|ELE|PLB|CVC|STR|SYN)\s?(\d{4})\s+((?:R\+\d|RDC|SS\d?|N\d|TOIT)[\w+]*)\b", re.I)
DOC_CODE_LOT = re.compile(r"\b(GO|CO|FE|AR|ST|EL|PL|CV|VRD)\s*-\s*([A-Z]\d{1,2})\s*-\s*(R\d|SS\d|RDC|N\d)\s*-\s*(\d{3})\b")
LOT = {"GO": "Gros œuvre", "CO": "Coffrage", "FE": "Ferraillage", "AR": "Architecture", "ST": "Structure", "EL": "Électricité", "PL": "Plomberie", "CV": "CVC", "VRD": "VRD"}
LEVEL = re.compile(r"\b(PH\s*)?(R\+\d|RDC|SS\d|Sous-sol|Toiture|Combles|N\d)\b", re.I)
DISCIPLINE = {"COF": "Structure — coffrage", "FER": "Structure — ferraillage", "ARM": "Structure — armatures", "ARC": "Architecture",
              "PLA": "Architecture", "ELE": "Électricité", "PLB": "Plomberie", "CVC": "CVC", "STR": "Structure", "SYN": "Synthèse"}


def _date(s: str):
    try:
        return datetime.strptime(s, "%d/%m/%Y")
    except ValueError:
        return None


def row_text(words, tol: float = 4.0) -> str:
    """Title-block cells printed on one line (« GO - B3 - R0 - 303 ») are separate text blocks: rebuild rows from word positions."""
    rows: list[list] = []
    for w in sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        cy = (w[1] + w[3]) / 2
        if rows and abs(rows[-1][0] - cy) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([cy, [w]])
    return "\n".join(" ".join(x[4] for x in sorted(r[1], key=lambda x: x[0])) for r in rows)


def identify_document(text: str, words=None) -> dict:
    """Best-effort title-block parsing; every field is None when not found (never guessed)."""
    t = re.sub(r"[ \t]+", " ", (text or "") + ("\n" + row_text(words) if words else ""))
    revisions = []
    for m in REV_ROW.finditer(t):
        if _date(m.group(2)):
            revisions.append({"index": m.group(1), "date": m.group(2), "label": m.group(3).strip()[:80]})
    for m in REV_ROW_NUM.finditer(t):
        if _date(m.group(3)):
            revisions.append({"index": m.group(1), "date": m.group(3), "label": m.group(2).strip()[:80]})
    seen, uniq = set(), []
    for r in revisions:
        if (r["index"], r["date"]) not in seen:
            seen.add((r["index"], r["date"]))
            uniq.append(r)
    latest = max(uniq, key=lambda r: (_date(r["date"]), r["index"])) if uniq else None
    scale = SCALE.search(t)
    code = DOC_CODE.search(t)
    lot = DOC_CODE_LOT.search(t) if not code else None
    level = LEVEL.search(t)
    if lot:
        code_str, discipline = "-".join(lot.groups()), LOT.get(lot.group(1))
    else:
        code_str = f"{code.group(1).upper()} {code.group(2)} {code.group(3).upper()}" if code else None
        discipline = DISCIPLINE.get(code.group(1).upper()) if code else None
    no_scale = re.search(r"[ÉEé]chelle\s*:?\s*(sans|s\.?o\.?|—|-)\b", t, re.I)
    title_m = (re.search(r"Plan\s+(coffrage|ferraillage|de\s+\w+|d'\w+)[^|\n]{0,40}", t, re.I)
               or re.search(r"(Armatures?\s+de\s+\w+|Nappe\s+(?:sup[ée]rieure|inf[ée]rieure))[^|\n]{0,40}", t, re.I))
    return {"revision_index": latest["index"] if latest else None, "revision_date": latest["date"] if latest else None,
            "revision_label": latest["label"] if latest else None, "revision_history": uniq[:12],
            "revision_index_is_numeric": bool(latest and latest["index"].isdigit()),
            "declared_scale": f"1/{scale.group(1)}" if scale else ("sans échelle" if no_scale else None),
            "document_code": code_str, "discipline": discipline,
            "level": level.group(2).upper() if level else None, "title": title_m.group(0).strip() if title_m else None,
            "note": "Révision et date lues dans le cartouche du document ; la date d'import n'est pas la date de révision."}
