"""Moteur DPGF : lecture multi-onglets, détection des lots, consignes et CCTP.

Le chiffrage suit toujours le même ordre : prix de la bibliothèque de l'entreprise,
puis estimation IA pour les lignes manquantes, puis coefficients (global / par lot).
Les lignes visées par une consigne d'exclusion restent présentes mais sans prix
(« Non chiffré — hors marché ») et sont exclues du total.
"""
from __future__ import annotations

import io
import re
import unicodedata

import openpyxl

NOT_PRICED = "Não orçamentado — fora da empreitada"

_DESIGN = ("désignation", "designation", "libellé", "libelle", "prestation", "descriptif",
           "ouvrage", "description", "article", "natureza dos trabalhos", "nature")
_UNIT = ("unité", "unite", "un.", "u.", "unit", "ui")
_QTY = ("quantité", "quantite", "qté", "qte", "q.", "quant", "nombre")
_PU = ("prix unitaire", "p.u", "pu ht", "pu", "prix u", "prix ht", "prix")
_TOTAL = ("montant", "total", "prix total", "p. total", "montant ht")
_SKIP = ("sous-total", "sous total", "total lot", "total général", "total general",
         "report", "à reporter", "total ht", "total ttc", "totaux")


def norm(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip().lower())


def fold(v) -> str:
    """Minuscules sans accents, pour les comparaisons de mots-clés."""
    s = unicodedata.normalize("NFKD", str(v or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in s if not unicodedata.combining(c))).strip()


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return None
    s = re.sub(r"[^\d,.-]", "", str(v)).replace(",", ".")
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _find_header(ws):
    for r in range(1, min(ws.max_row, 40) + 1):
        cols = {}
        for c in range(1, min(ws.max_column, 30) + 1):
            val = norm(ws.cell(row=r, column=c).value)
            if not val:
                continue
            if "design" not in cols and any(k in val for k in _DESIGN):
                cols["design"] = c
            elif "unit" not in cols and any(val == k or val.startswith(k) for k in _UNIT):
                cols["unit"] = c
            elif "qty" not in cols and any(k in val for k in _QTY):
                cols["qty"] = c
            elif "total" not in cols and any(k in val for k in _TOTAL):
                cols["total"] = c
            elif "pu" not in cols and any(k in val for k in _PU):
                cols["pu"] = c
        if "design" in cols and ("pu" in cols or "total" in cols or "qty" in cols):
            return r, cols
    return None, {}


_LOT_RE = re.compile(r"^(lot\s*)?n?°?\s*\d{1,2}([.\-—:\s]|$)", re.I)


def _is_lot_title(text: str, qty, pu) -> bool:
    """Ligne de titre de lot : pas de quantité/prix et libellé de type « 03 — CARRELAGE »."""
    if qty or pu:
        return False
    t = text.strip()
    if len(t) < 3 or len(t) > 120:
        return False
    letters = [c for c in t if c.isalpha()]
    upper = letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.7
    return bool(_LOT_RE.match(t) or upper)


def parse_workbook(raw: bytes) -> dict:
    """Lit tous les onglets → lignes chiffrables avec leur lot et leur descriptif."""
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)
    rows: list[dict] = []
    sheets: list[dict] = []
    for ws in wb.worksheets:
        hrow, cols = _find_header(ws)
        if not hrow:
            sheets.append({"sheet": ws.title, "recognised": False, "lines": 0})
            continue
        c_des, c_unit, c_qty = cols.get("design"), cols.get("unit"), cols.get("qty")
        c_pu, c_total = cols.get("pu"), cols.get("total")
        lot = ""
        count = 0
        pending_desc: list[str] = []
        for r in range(hrow + 1, ws.max_row + 1):
            des = ws.cell(row=r, column=c_des).value if c_des else None
            text = str(des or "").strip()
            if not text:
                continue
            low = fold(text)
            if any(k in low for k in (fold(s) for s in _SKIP)):
                continue
            qty = _num(ws.cell(row=r, column=c_qty).value) if c_qty else None
            unit = str(ws.cell(row=r, column=c_unit).value or "").strip() if c_unit else ""
            pu = _num(ws.cell(row=r, column=c_pu).value) if c_pu else None
            if pu == 0:
                pu = None  # colonne « prix unitaire » vide ou à 0 = à chiffrer, pas un prix
            if _is_lot_title(text, qty, pu):
                lot = text
                pending_desc = []
                continue
            if qty is None and not unit and pu is None:
                pending_desc.append(text)          # ligne de descriptif libre
                if len(pending_desc) > 6:
                    pending_desc = pending_desc[-6:]
                continue
            rows.append({
                "line_id": f"l{len(rows) + 1}",
                "sheet": ws.title, "row": r, "lot": lot or "Sem capítulo",
                "designation": text,
                "description": " ".join(pending_desc)[:1500],
                "unit": unit or "u", "qty": qty,
                "pu_file": pu, "pu_library": None, "pu_ai": None,
                "pu_base": pu, "pu": pu, "source": "fichier" if pu else None,
                "matched_designation": None,
                "excluded": False, "exclusion_reason": "",
                "cctp_note": "", "margin_pct": 0,
            })
            pending_desc = []
            count += 1
        sheets.append({"sheet": ws.title, "recognised": True, "lines": count,
                       "header_row": hrow, "columns": cols})
    return {"rows": rows, "sheets": sheets}


def lots(rows: list[dict]) -> list[str]:
    seen: list[str] = []
    for r in rows:
        if r["lot"] not in seen:
            seen.append(r["lot"])
    return seen


def _dup_key(r: dict) -> tuple:
    """Clé d'identité d'une ligne : lot + désignation normalisée + unité + quantité.

    Deux lignes strictement identiques (souvent une feuille récap/DQE qui répète le
    bordereau, ou un fichier importé deux fois) ne doivent être chiffrées qu'une fois.
    """
    d = unicodedata.normalize("NFKD", r.get("designation") or "").encode("ascii", "ignore").decode()
    d = re.sub(r"[^a-z0-9]+", " ", d.lower()).strip()
    u = re.sub(r"[^a-z0-9]+", "", (r.get("unit") or "").lower())
    lot = unicodedata.normalize("NFKD", r.get("lot") or "").encode("ascii", "ignore").decode()
    lot = re.sub(r"[^a-z0-9]+", " ", lot.lower()).strip()
    q = r.get("qty")
    return (lot, d, u, q)


def dedup_rows(rows: list[dict]) -> int:
    """Marque en doublon (exclu, non chiffré) les lignes strictement identiques déjà vues.

    On garde la 1re occurrence (en privilégiant celle qui porte déjà un prix fichier) et on
    exclut les suivantes. Renvoie le nombre de doublons neutralisés.
    """
    seen: dict[tuple, dict] = {}
    dups = 0
    for r in rows:
        if not (r.get("designation") or "").strip():
            continue
        key = _dup_key(r)
        kept = seen.get(key)
        if kept is None:
            seen[key] = r
            continue
        loser = r
        if r.get("pu_file") is not None and kept.get("pu_file") is None:
            seen[key] = r
            loser = kept
        loser["excluded"] = True
        loser["exclusion_reason"] = "Duplicado (já orçamentado no estudo)"
        loser["pu_base"] = None
        loser["pu"] = None
        loser["source"] = None
        dups += 1
    return dups



def apply_directives(rows: list[dict], directives: dict) -> dict:
    """Applique les consignes : exclusions, coefficients global et par lot."""
    ex_kw = [fold(k) for k in (directives.get("exclude_keywords") or []) if str(k).strip()]
    ex_lots = [fold(k) for k in (directives.get("exclude_lots") or []) if str(k).strip()]
    global_margin = float(directives.get("margin_pct") or 0)
    lot_margins = {fold(k): float(v or 0) for k, v in (directives.get("lot_margins") or {}).items()}
    excluded = 0
    for r in rows:
        hay = fold(f"{r['lot']} {r['designation']} {r['description']}")
        lot_f = fold(r["lot"])
        hit = next((k for k in ex_kw if k and k in hay), None)
        if not hit:
            hit = next((k for k in ex_lots if k and (k in lot_f or lot_f in k)), None)
        if hit:
            r["excluded"] = True
            r["exclusion_reason"] = f'Excluído por instrução «{hit} »'
            r["pu"] = None
            r["pu_base"] = None
            r["source"] = None
            excluded += 1
            continue
        margin = next((v for k, v in lot_margins.items() if k and (k in lot_f or lot_f in k)),
                      global_margin)
        r["margin_pct"] = margin
    return {"excluded": excluded, "margin_pct": global_margin, "lot_margins": lot_margins}


CCTP_IMPACT_CAP = 25.0  # plafond du surcoût CCTP cumulé par ligne (%)


def apply_prescriptions(rows: list[dict], prescriptions: list[dict]) -> int:
    """Rattache les prescriptions CCTP aux lignes (note + impact prix en %).

    L'impact retenu est celui de la prescription la plus exigeante, plafonné : une dizaine
    de prescriptions visant un même lot ne doit jamais tripler un prix unitaire.
    """
    touched = 0
    for p in prescriptions or []:
        kws = [fold(k) for k in (p.get("keywords") or []) if str(k).strip()]
        lot = fold(p.get("lot") or "")
        note = str(p.get("text") or "").strip()[:500]
        impact = float(p.get("price_impact_pct") or 0)
        if not note:
            continue
        for r in rows:
            hay = fold(f"{r['lot']} {r['designation']} {r['description']}")
            if (kws and any(k in hay for k in kws)) or (lot and lot in fold(r["lot"])):
                r["cctp_note"] = (r["cctp_note"] + " · " + note).strip(" ·")[:800]
                r["cctp_impact_pct"] = min(max(float(r.get("cctp_impact_pct") or 0), impact),
                                           CCTP_IMPACT_CAP)
                touched += 1
    return touched


def finalise(rows: list[dict]) -> dict:
    """Calcule le PU retenu (base + coefficients), les totaux par lot et le total général.

    Le coefficient (consigne + impact CCTP) s'applique aux prix bibliothèque et IA ;
    un prix saisi à la main ou déjà présent au bordereau est retenu tel quel.
    Idempotent : le PU est toujours recalculé depuis ``pu_base``.
    """
    by_lot: dict[str, dict] = {}
    total = 0.0
    priced = 0
    for r in rows:
        if r["excluded"]:
            r["pu"] = None
            r["total"] = None
        else:
            base, src = r.get("pu_base"), r.get("source")
            if base is None:
                if r.get("pu_library") is not None:
                    base, src = r["pu_library"], "bibliotheque"
                elif r.get("pu_file") is not None:
                    base, src = r["pu_file"], "fichier"
                elif r.get("pu_ai") is not None:
                    base, src = r["pu_ai"], "ia"
                r["pu_base"], r["source"] = base, src
            if base is not None:
                coef = 1.0
                if src in ("bibliotheque", "ia", "soustraitant"):
                    coef += (float(r.get("margin_pct") or 0) + float(r.get("cctp_impact_pct") or 0)) / 100
                r["pu"] = round(float(base) * coef, 2)
                r["total"] = round(r["pu"] * (r["qty"] or 0), 2) if r.get("qty") is not None else None
                priced += 1
            else:
                r["pu"] = None
                r["total"] = None
        slot = by_lot.setdefault(r["lot"], {"lot": r["lot"], "total_ht": 0.0, "cost_ht": 0.0,
                                            "lines": 0, "excluded": 0, "unpriced": 0})
        slot["lines"] += 1
        if r["excluded"]:
            slot["excluded"] += 1
        elif r.get("total"):
            slot["total_ht"] = round(slot["total_ht"] + r["total"], 2)
            cost = float(r.get("pu_base") or 0) * (r.get("qty") or 0)
            slot["cost_ht"] = round(slot["cost_ht"] + cost, 2)
            total = round(total + r["total"], 2)
        elif r.get("pu") is None:
            slot["unpriced"] += 1
    for slot in by_lot.values():
        slot["margin_pct"] = (round((slot["total_ht"] - slot["cost_ht"]) / slot["cost_ht"] * 100, 1)
                              if slot["cost_ht"] else 0.0)
        slot["margin_ht"] = round(slot["total_ht"] - slot["cost_ht"], 2)
    return {"lots": list(by_lot.values()), "grand_total_ht": round(total, 2), "priced": priced}


def write_workbook(raw: bytes, rows: list[dict]) -> bytes:
    """Réécrit le classeur d'origine avec les PU, totaux et mentions d'exclusion."""
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)
    cols_by_sheet: dict[str, dict] = {}
    for ws in wb.worksheets:
        hrow, cols = _find_header(ws)
        if hrow:
            cols_by_sheet[ws.title] = cols
    for r in rows:
        cols = cols_by_sheet.get(r["sheet"])
        if not cols:
            continue
        ws = wb[r["sheet"]]
        c_pu, c_total = cols.get("pu"), cols.get("total")
        if r["excluded"]:
            if c_pu:
                ws.cell(row=r["row"], column=c_pu).value = NOT_PRICED
            if c_total:
                ws.cell(row=r["row"], column=c_total).value = None
            continue
        if r.get("pu") is not None and c_pu:
            ws.cell(row=r["row"], column=c_pu).value = r["pu"]
        if r.get("total") is not None and c_total:
            ws.cell(row=r["row"], column=c_total).value = r["total"]
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
