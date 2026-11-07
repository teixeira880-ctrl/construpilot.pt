"""Étape 1 — Analyse documentaire vérifiable (XLSX + PDF).

Objectifs (déterministes, sans invention) :
- Extraire les données avec leur PROVENANCE exacte (feuille!cellule pour Excel,
  page + zone pour PDF).
- Lire séparément la FORMULE et son RÉSULTAT en cache : si le résultat est absent,
  le SIGNALER (jamais l'inventer).
- Distinguer clairement zéro / cellule vide / illisible / absente.
- Ne pas ignorer en silence les feuilles ou lignes masquées (les inclure + signaler).
- Éviter le double comptage détail/sous-total.
- Contrôler l'arithmétique (quantité × PU, TVA, arrondis) via Decimal.

Le cœur est 100 % déterministe. L'IA n'est pas requise ici (l'interprétation des
colonnes ambiguës = tranche suivante). Réutilise la détection d'en-têtes du DPGF.
"""
from __future__ import annotations

import io
import re
import time
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

import openpyxl
from openpyxl.utils import get_column_letter

try:
    import fitz  # PyMuPDF
except Exception:  # pragma: no cover
    fitz = None

from engines.dpgf_engine import _find_header, _is_lot_title, fold, _SKIP

ENGINE_VERSION = "doc_intel/1.1.0"

# ---------------------------------------------------------------------------
# Nombres FR / PT (virgule décimale, séparateurs de milliers espace/point)
# ---------------------------------------------------------------------------

def parse_number(v) -> dict:
    """Renvoie {value, status, raw}. status ∈ ok|empty|absent|illegible.

    - absent   : la cellule n'existe pas / None
    - empty    : chaîne vide
    - illegible: contenu non convertible en nombre
    - ok       : nombre lu (0 reste une valeur « ok », jamais confondu avec vide)
    """
    if v is None:
        return {"value": None, "status": "absent", "raw": None}
    if isinstance(v, bool):
        return {"value": None, "status": "illegible", "raw": v}
    if isinstance(v, (int, float)):
        return {"value": float(v), "status": "ok", "raw": v}
    raw = str(v)
    s = raw.replace("\u00a0", " ").replace("\u202f", " ").strip()
    if s == "":
        return {"value": None, "status": "empty", "raw": raw}
    cleaned = re.sub(r"[^\d,.\-]", "", s)
    if cleaned in ("", "-", ".", ",", "-.", "-,"):
        return {"value": None, "status": "illegible", "raw": raw}
    has_c, has_d = "," in cleaned, "." in cleaned
    if has_c and has_d:
        if cleaned.rfind(",") > cleaned.rfind("."):          # 1.234,56 → FR/PT
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:                                                 # 1,234.56 → EN
            cleaned = cleaned.replace(",", "")
    elif has_c:
        cleaned = cleaned.replace(",", "") if cleaned.count(",") > 1 else cleaned.replace(",", ".")
    elif has_d and cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")                    # 1.234.567 → milliers
    try:
        return {"value": float(cleaned), "status": "ok", "raw": raw}
    except ValueError:
        return {"value": None, "status": "illegible", "raw": raw}


def guess_language(sample: str) -> str | None:
    s = fold(sample or "")
    if not s:
        return None
    pt = sum(s.count(k) for k in ("betao", "area", "empreitada", "orcamento", "revestimento", "cao "))
    fr = sum(s.count(k) for k in ("maconnerie", "cloison", "platre", "peinture", "plancher", "devis", "lot "))
    if pt > fr and pt > 0:
        return "pt"
    if fr > 0:
        return "fr"
    return None


def _looks_subtotal(text: str) -> bool:
    t = fold(text)
    return any(k in t for k in ("sous total", "sous-total", "s/total", "s total",
                                "total lot", "total ht", "total general", "sous total ht",
                                "subtotal", "total do lote", "total geral"))


# ---------------------------------------------------------------------------
# EXCEL
# ---------------------------------------------------------------------------

def extract_xlsx(raw: bytes) -> dict:
    t0 = time.time()
    wb_v = openpyxl.load_workbook(io.BytesIO(raw), data_only=True)   # résultats en cache
    wb_f = openpyxl.load_workbook(io.BytesIO(raw), data_only=False)  # formules

    sheets: list[dict] = []
    lines: list[dict] = []
    warnings: list[dict] = []
    unread: list[dict] = []
    sample_text: list[str] = []

    for name in wb_v.sheetnames:
        ws, wsf = wb_v[name], wb_f[name]
        state = getattr(ws, "sheet_state", "visible")
        if state != "visible":
            warnings.append({"type": "hidden_sheet", "sheet": name, "state": state,
                             "message": f'Folha oculta «{name}» analisada (não ignorada)'})
        hrow, cols = _find_header(ws)
        if not hrow:
            sheets.append({"sheet": name, "state": state, "recognised": False, "lines": 0})
            unread.append({"type": "sheet_unrecognised", "sheet": name,
                           "message": "Cabeçalhos não reconhecidos (interpretação IA prevista numa fase seguinte)"})
            continue

        merged: dict = {}
        for rng in ws.merged_cells.ranges:
            tl = ws.cell(row=rng.min_row, column=rng.min_col).value
            for rr in range(rng.min_row, rng.max_row + 1):
                for cc in range(rng.min_col, rng.max_col + 1):
                    merged[(rr, cc)] = tl

        c_des, c_unit = cols.get("design"), cols.get("unit")
        c_qty, c_pu, c_total = cols.get("qty"), cols.get("pu"), cols.get("total")

        def cval(r, c):
            return merged.get((r, c), ws.cell(row=r, column=c).value) if c else None

        def coord(r, c):
            return f"{name}!{get_column_letter(c)}{r}" if c else None

        def formula_flag(r, c, key, flags):
            if not c:
                return
            fc = wsf.cell(row=r, column=c)
            if fc.data_type == "f":
                cached = ws.cell(row=r, column=c).value
                if cached is None:
                    flags.append(f"formula_result_missing:{key}")

        count, lot, pending = 0, "", []
        for r in range(hrow + 1, ws.max_row + 1):
            hidden = bool(ws.row_dimensions[r].hidden) if r in ws.row_dimensions else False
            text = str(cval(r, c_des) or "").strip()
            qty = parse_number(cval(r, c_qty))
            unit = str(cval(r, c_unit) or "").strip()
            pu = parse_number(cval(r, c_pu))
            amt = parse_number(cval(r, c_total))
            has_values = any(x["value"] is not None for x in (qty, pu, amt)) or bool(unit)
            if not text and not has_values:
                continue
            if text:
                sample_text.append(text)
            low = fold(text)
            if text and any(k in low for k in (fold(s) for s in _SKIP)) and not has_values:
                continue

            flags: list[str] = []
            if hidden:
                flags.append("hidden_row")
            formula_flag(r, c_pu, "pu", flags)
            formula_flag(r, c_total, "amount", flags)
            formula_flag(r, c_qty, "qty", flags)

            prov = {"header_row": hrow, "designation": coord(r, c_des), "qty": coord(r, c_qty),
                    "unit": coord(r, c_unit), "pu": coord(r, c_pu), "amount": coord(r, c_total)}

            if text and _is_lot_title(text, qty["value"], pu["value"]):
                lot, pending = text, []
                lines.append({"line_id": f"l{len(lines)+1}", "sheet": name, "row": r,
                              "kind": "lot_title", "hidden": hidden, "lot": lot,
                              "designation": text, "description": "", "unit": None,
                              "qty": qty, "pu": pu, "amount": amt, "provenance": prov, "flags": flags})
                continue

            if _looks_subtotal(text) and (qty["value"] in (None, 0)) and (pu["value"] in (None, 0)):
                flags.append("subtotal_excluded_from_sum")
                lines.append({"line_id": f"l{len(lines)+1}", "sheet": name, "row": r,
                              "kind": "subtotal", "hidden": hidden, "lot": lot or "Sem capítulo",
                              "designation": text, "description": "", "unit": unit or None,
                              "qty": qty, "pu": pu, "amount": amt, "provenance": prov, "flags": flags})
                continue

            if qty["value"] is None and not unit and pu["value"] is None and amt["value"] is None:
                pending.append(text)
                pending = pending[-6:]
                continue

            lines.append({"line_id": f"l{len(lines)+1}", "sheet": name, "row": r,
                          "kind": "detail", "hidden": hidden, "lot": lot or "Sem capítulo",
                          "designation": text, "description": " ".join(pending)[:1500],
                          "unit": unit or None, "qty": qty, "pu": pu, "amount": amt,
                          "provenance": prov, "flags": flags})
            pending = []
            count += 1

        sheets.append({"sheet": name, "state": state, "recognised": True, "lines": count,
                       "header_row": hrow, "columns": {k: get_column_letter(v) for k, v in cols.items()}})

    return {"format": "xlsx", "language": guess_language(" ".join(sample_text[:200])),
            "sheets": sheets, "lines": lines, "warnings": warnings, "unread": unread,
            "duration_ms": int((time.time() - t0) * 1000)}


# ---------------------------------------------------------------------------
# PDF (texte natif + coordonnées ; scans signalés pour OCR ultérieur)
# ---------------------------------------------------------------------------

def extract_pdf(raw: bytes) -> dict:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) indisponível")
    t0 = time.time()
    doc = fitz.open(stream=raw, filetype="pdf")
    pages: list[dict] = []
    lines: list[dict] = []
    tables: list[dict] = []
    warnings: list[dict] = []
    unread: list[dict] = []
    sample_text: list[str] = []

    for pno in range(doc.page_count):
        page = doc[pno]
        d = page.get_text("dict")
        n = 0
        text_present = False
        for block in d.get("blocks", []):
            for ln in block.get("lines", []):
                txt = "".join(sp.get("text", "") for sp in ln.get("spans", [])).strip()
                if not txt:
                    continue
                text_present = True
                bb = ln.get("bbox", [0, 0, 0, 0])
                n += 1
                if len(sample_text) < 200:
                    sample_text.append(txt)
                lines.append({"line_id": f"p{pno+1}_{n}", "page": pno + 1,
                              "bbox": [round(float(x), 1) for x in bb], "text": txt[:1000]})
        img_count = len(page.get_images(full=True))
        scanned = (not text_present) and img_count > 0
        if scanned:
            warnings.append({"type": "scanned_page", "page": pno + 1,
                             "message": "Página provavelmente digitalizada — OCR a ativar (IA de visão)"})
            unread.append({"type": "scanned_page", "page": pno + 1})

        n_tab = 0
        try:
            finder = page.find_tables()
            for ti, tab in enumerate(getattr(finder, "tables", []) or []):
                cells = tab.extract()
                tables.append({"table_id": f"p{pno+1}_t{ti+1}", "page": pno + 1,
                               "bbox": [round(float(x), 1) for x in tab.bbox], "rows": cells})
                n_tab += 1
        except Exception:
            pass
        pages.append({"page": pno + 1, "lines": n, "scanned": scanned,
                      "images": img_count, "tables": n_tab})
    doc.close()
    return {"format": "pdf", "language": guess_language(" ".join(sample_text)),
            "pages": pages, "lines": lines, "tables": tables,
            "warnings": warnings, "unread": unread,
            "duration_ms": int((time.time() - t0) * 1000)}


# ---------------------------------------------------------------------------
# Contrôles arithmétiques déterministes (Decimal)
# ---------------------------------------------------------------------------

def _D(x) -> Decimal:
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def arithmetic_check(lines: list[dict], vat_rate: float | None = None) -> dict:
    checks: list[dict] = []
    sum_computed = Decimal(0)
    sum_file = Decimal(0)
    for ln in lines:
        if ln.get("kind") != "detail":
            continue
        q = ln["qty"]["value"]
        pu = ln["pu"]["value"]
        amt = ln["amount"]["value"]
        e = {"line_id": ln["line_id"], "sheet": ln.get("sheet"), "row": ln.get("row"),
             "provenance": ln["provenance"].get("amount") or ln["provenance"].get("pu")}
        if q is None or pu is None:
            e["status"] = "insufficient"
            e["reason"] = "quantidade ou PU em falta"
            if amt is not None:
                sum_file += _D(amt)
            checks.append(e)
            continue
        computed = (_D(q) * _D(pu)).quantize(Decimal("0.01"), ROUND_HALF_UP)
        sum_computed += computed
        e["computed"] = float(computed)
        if amt is None:
            e["status"] = "computed_only"
        else:
            f = _D(amt)
            sum_file += f
            diff = abs(f - computed)
            tol = max(Decimal("0.01"), computed * Decimal("0.005"))
            e["file_amount"] = float(f)
            e["diff"] = float(diff)
            e["status"] = "ok" if diff <= tol else "mismatch"
        checks.append(e)

    subtotals = [{"line_id": l["line_id"], "row": l["row"], "sheet": l.get("sheet"),
                  "designation": l["designation"], "amount": l["amount"]["value"]}
                 for l in lines if l.get("kind") == "subtotal"]

    total_ht = sum_computed
    vat_amount = (total_ht * _D(vat_rate) / Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP) if vat_rate else None
    total_ttc = (total_ht + vat_amount) if vat_amount is not None else None

    summary = {
        "detail_lines": sum(1 for l in lines if l.get("kind") == "detail"),
        "sum_computed_ht": float(sum_computed),
        "sum_file_amounts": float(sum_file),
        "mismatches": sum(1 for c in checks if c.get("status") == "mismatch"),
        "insufficient": sum(1 for c in checks if c.get("status") == "insufficient"),
        "subtotals_excluded": len(subtotals),
        "vat_rate": vat_rate,
        "vat_amount": float(vat_amount) if vat_amount is not None else None,
        "total_ttc": float(total_ttc) if total_ttc is not None else None,
    }
    return {"checks": checks, "subtotals": subtotals, "summary": summary}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def analyse(raw: bytes, filename: str, vat_rate: float | None = None) -> dict:
    ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else ""
    if ext in ("xlsx", "xlsm"):
        res = extract_xlsx(raw)
    elif ext == "pdf":
        res = extract_pdf(raw)
    else:
        raise ValueError(f"Formato não suportado nesta etapa: .{ext or '?'} (XLSX ou PDF esperado)")
    if res["format"] == "xlsx":
        a = arithmetic_check(res.get("lines", []), vat_rate)
        res["arithmetic"] = finalize_arithmetic(a, {}, vat_rate, "xlsx")
    else:
        res["arithmetic"] = pdf_arithmetic(res, vat_rate)
    res["engine_version"] = ENGINE_VERSION
    return res


# ---------------------------------------------------------------------------
# Auditoria V2 (07/11/2026) — controlo aritmético também para PDF e OCR.
# Antes: só os .xlsx eram verificados ; um PDF com 10 × 25 = 275 mostrava
# «0 pontos a verificar». Agora : leitura determinística das linhas
# (quantidade, PU, montante) + totais declarados (s/ IVA, IVA, c/ IVA) e um
# estado explícito : executed | not_run | inconclusive.
# ---------------------------------------------------------------------------

_HDR_KEYS = {
    "qty": ("quantite", "quantidade", "qte", "qtd", "qty", "quant"),
    "pu": ("prix unitaire", "preco unitario", "p.u", "pu ", "pu", "unit price", "prix u", "preco u"),
    "amount": ("total ht", "montant", "montante", "total s/ iva", "total sem iva", "total", "importe", "valor"),
    "unit": ("unite", "unidade", "un.", "un", "u"),
    "design": ("designation", "designacao", "descricao", "description", "libelle", "artigo"),
}
_TOTAL_HT = ("total ht", "total s/ iva", "total sem iva", "total sans tva", "subtotal", "sous-total", "sous total", "total liquido")
_TOTAL_TTC = ("total ttc", "total c/ iva", "total com iva", "total a pagar", "net a payer", "total geral")
_VAT = ("tva", "iva")


def _cell_role(text: str) -> str | None:
    t = fold(text).strip(" :.")
    if not t:
        return None
    # ordem importa : «prix unitaire ht» é PU, «total ht» é montante
    for key in ("pu", "qty", "design", "amount", "unit"):
        for k in _HDR_KEYS[key]:
            kk = k.strip()
            if key == "unit":
                if t == kk or t.startswith(kk + " ") or t in ("unite", "unidade"):
                    return key
                continue
            if key == "pu" and kk == "pu":
                if t == "pu" or t.startswith("pu ") or t.startswith("p.u"):
                    return key
                continue
            if kk in t:
                return key
    return None


def _split_cells(text: str) -> list[str]:
    for sep in ("|", "\t", ";"):
        if sep in text:
            return [c.strip() for c in text.split(sep)]
    return [c.strip() for c in re.split(r"\s{3,}", text) if c.strip()]


def _pdf_rows(lines: list[dict]) -> list[dict]:
    """Agrupa as linhas de texto (PyMuPDF) por página e por linha visual."""
    rows: list[dict] = []
    by_page: dict[int, list[dict]] = {}
    for ln in lines:
        if ln.get("ocr"):
            continue
        by_page.setdefault(ln.get("page", 1), []).append(ln)
    for page, lns in by_page.items():
        lns = sorted(lns, key=lambda l: ((l.get("bbox") or [0, 0, 0, 0])[1], (l.get("bbox") or [0])[0]))
        cur: list[dict] = []
        cy = None
        for ln in lns:
            bb = ln.get("bbox") or [0, 0, 0, 0]
            yc = (bb[1] + bb[3]) / 2
            if cy is not None and abs(yc - cy) <= 3:
                cur.append(ln)
            else:
                if cur:
                    rows.append({"page": page, "parts": cur})
                cur, cy = [ln], yc
        if cur:
            rows.append({"page": page, "parts": cur})
    out = []
    for r in rows:
        parts = sorted(r["parts"], key=lambda l: (l.get("bbox") or [0])[0])
        cells: list[dict] = []
        for p in parts:
            bb = p.get("bbox") or [0, 0, 0, 0]
            sub = _split_cells(p["text"])
            if len(sub) > 1:
                w = (bb[2] - bb[0]) / len(sub)
                for i, s in enumerate(sub):
                    cells.append({"text": s, "x": bb[0] + w * (i + 0.5), "line_id": p["line_id"], "split": True})
            else:
                cells.append({"text": p["text"].strip(), "x": (bb[0] + bb[2]) / 2, "line_id": p["line_id"], "split": False})
        out.append({"page": r["page"], "cells": cells, "line_id": parts[0]["line_id"],
                    "text": " | ".join(c["text"] for c in cells)})
    return out


def _amount_in(text: str) -> float | None:
    """Último número de uma linha de total («TVA 20%: 65.00 EUR» → 65.0)."""
    nums = re.findall(r"-?\d[\d\s  .,]*\d|-?\d", text)
    vals = []
    for n in nums:
        p = parse_number(n)
        if p["status"] == "ok":
            vals.append(p["value"])
    return vals[-1] if vals else None


def _rate_in(text: str) -> float | None:
    m = re.search(r"(\d{1,2}(?:[.,]\d{1,2})?)\s*%", text)
    return float(m.group(1).replace(",", ".")) if m else None


def _rows_from_tables(tables: list[dict]) -> list[dict]:
    rows = []
    for t in tables or []:
        for i, r in enumerate(t.get("rows") or []):
            cells = [{"text": str(c or "").strip(), "x": j, "line_id": f"{t['table_id']}_r{i+1}", "split": True}
                     for j, c in enumerate(r)]
            rows.append({"page": t.get("page", 1), "cells": cells, "line_id": f"{t['table_id']}_r{i+1}",
                         "text": " | ".join(c["text"] for c in cells), "table": t["table_id"]})
    return rows


def _parse_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    """Devolve (linhas de detalhe normalizadas, totais declarados)."""
    details: list[dict] = []
    declared: dict = {}
    header = None  # {role: (index, x)}
    for r in rows:
        cells = r["cells"]
        roles = [_cell_role(c["text"]) for c in cells]
        if roles.count(None) <= len(roles) - 3 and {"qty", "pu", "amount"} <= set(roles):
            header = {}
            for i, role in enumerate(roles):
                if role and role not in header:
                    header[role] = (i, cells[i]["x"])
            header["_n"] = len(cells)
            header["_split"] = all(c["split"] for c in cells)
            continue
        low = fold(r["text"])
        is_total = any(k in low for k in _TOTAL_HT + _TOTAL_TTC) or (
            any(re.search(rf"\b{k}\b", low) for k in _VAT) and _rate_in(r["text"]) is not None)
        if is_total:
            val = _amount_in(r["text"])
            src = {"page": r["page"], "line_id": r["line_id"], "text": r["text"][:200]}
            if any(k in low for k in _TOTAL_TTC) or "ttc" in low:
                declared.setdefault("ttc", {"value": val, **src})
            elif any(re.search(rf"\b{k}\b", low) for k in _VAT) and not any(k in low for k in _TOTAL_HT):
                declared.setdefault("vat", {"value": val, "rate": _rate_in(r["text"]), **src})
            else:
                declared.setdefault("ht", {"value": val, **src})
            continue
        if not header:
            continue

        def pick(role):
            if role not in header:
                return None
            idx, hx = header[role]
            if header["_split"] and len(cells) == header["_n"]:
                return cells[idx]["text"]
            best = min(cells, key=lambda c: abs(c["x"] - hx)) if cells else None
            return best["text"] if best else None

        q, pu, amt = (parse_number(pick(k)) for k in ("qty", "pu", "amount"))
        des = pick("design") if "design" in header else cells[0]["text"]
        if sum(1 for x in (q, pu, amt) if x["value"] is not None) < 2:
            continue
        details.append({"line_id": r["line_id"], "page": r["page"], "kind": "detail",
                        "designation": (des or "")[:300], "unit": pick("unit"),
                        "qty": q, "pu": pu, "amount": amt,
                        "provenance": {"amount": f"página {r['page']}", "pu": f"página {r['page']}"},
                        "source_text": r["text"][:300]})
    return details, declared


def _totals_check(arith: dict, declared: dict, vat_rate: float | None) -> list[dict]:
    """Compara os totais declarados no documento com o recálculo determinístico."""
    out: list[dict] = []
    s = arith["summary"]
    computed_ht = _D(s["sum_computed_ht"])
    rate = vat_rate if vat_rate is not None else (declared.get("vat") or {}).get("rate")

    def chk(key, label, expected, src):
        if src is None or src.get("value") is None or expected is None:
            return
        f = _D(src["value"])
        diff = abs(f - expected)
        tol = max(Decimal("0.02"), expected * Decimal("0.005"))
        out.append({"type": key, "label": label, "status": "ok" if diff <= tol else "mismatch",
                    "file_amount": float(f), "computed": float(expected), "diff": float(diff),
                    "page": src.get("page"), "line_id": src.get("line_id"), "source_text": src.get("text")})

    if s["detail_lines"]:
        chk("total_ht", "Total s/ IVA", computed_ht, declared.get("ht"))
    vat_expected = (computed_ht * _D(rate) / Decimal(100)).quantize(Decimal("0.01"), ROUND_HALF_UP) if rate is not None and s["detail_lines"] else None
    chk("vat", f"IVA {rate:g}%" if rate is not None else "IVA", vat_expected, declared.get("vat"))
    if vat_expected is not None:
        chk("total_ttc", "Total c/ IVA", computed_ht + vat_expected, declared.get("ttc"))
    # Coerência interna do documento (mesmo sem linhas lidas) : HT + IVA = TTC
    ht, vat, ttc = (declared.get(k) or {} for k in ("ht", "vat", "ttc"))
    if ht.get("value") is not None and vat.get("value") is not None and ttc.get("value") is not None:
        chk("doc_ttc_coherence", "Coerência s/ IVA + IVA = c/ IVA (documento)",
            _D(ht["value"]) + _D(vat["value"]), ttc)
    return out


def finalize_arithmetic(arith: dict, declared: dict, vat_rate: float | None, source: str) -> dict:
    totals = _totals_check(arith, declared, vat_rate)
    s = arith["summary"]
    checked = sum(1 for c in arith["checks"] if c.get("status") in ("ok", "mismatch"))
    s["lines_checked"] = checked
    s["totals_checks"] = len(totals)
    s["mismatches"] = s["mismatches"] + sum(1 for t in totals if t["status"] == "mismatch")
    if checked == 0 and not totals:
        status, reason = "not_run", "Nenhuma linha com quantidade × preço unitário × montante foi reconhecida : a aritmética NÃO foi verificada."
    elif s["insufficient"]:
        status, reason = "inconclusive", "Verificação parcial : algumas linhas ou totais não puderam ser lidos."
    else:
        status, reason = "executed", None
    if declared.get("ht") and s["detail_lines"]:
        s["declared_ht"] = declared["ht"]["value"]
    s["status"] = status
    s["status_reason"] = reason
    s["source"] = source
    arith["totals"] = totals
    arith["declared"] = declared
    return arith


def pdf_arithmetic(res: dict, vat_rate: float | None = None) -> dict:
    # Texto nativo primeiro (fiel ao documento) ; tabelas detetadas só como recurso
    # (o find_tables do PyMuPDF pode partir «15,00» em «15 00\n,»).
    details, declared = _parse_rows(_pdf_rows(res.get("lines") or []))
    if not details:
        d2, decl2 = _parse_rows(_rows_from_tables(res.get("tables") or []))
        details = d2
        for k, v in decl2.items():
            declared.setdefault(k, v)
    arith = arithmetic_check(details, vat_rate if vat_rate is not None else (declared.get("vat") or {}).get("rate"))
    arith["lines"] = details
    return finalize_arithmetic(arith, declared, vat_rate, "pdf_text")


def ocr_arithmetic(ocr: dict, vat_rate: float | None = None) -> dict:
    """Recontrolo determinístico dos campos lidos pela IA (a IA nunca calcula)."""
    details = []
    for i, it in enumerate((ocr or {}).get("line_items") or []):
        q, pu, amt = (parse_number(it.get(k)) for k in ("quantity", "unit_price", "amount"))
        if sum(1 for x in (q, pu, amt) if x["value"] is not None) < 2:
            continue
        details.append({"line_id": f"ocr_item_{i+1}", "kind": "detail", "page": it.get("page"),
                        "designation": str(it.get("description") or "")[:300], "unit": it.get("unit"),
                        "qty": q, "pu": pu, "amount": amt,
                        "provenance": {"amount": "IA (OCR)", "pu": "IA (OCR)"}})
    doc = (ocr or {}).get("document") or {}
    declared = {}
    for key, field in (("ht", "subtotal"), ("vat", "tax"), ("ttc", "total")):
        p = parse_number(doc.get(field))
        if p["value"] is not None:
            declared[key] = {"value": p["value"], "text": f"{field}: {doc.get(field)} (IA)"}
    arith = arithmetic_check(details, vat_rate)
    arith["lines"] = details
    return finalize_arithmetic(arith, declared, vat_rate, "ocr")
