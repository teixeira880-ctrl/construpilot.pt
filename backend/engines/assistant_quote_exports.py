"""Livrables systématiques d'un devis de l'assistant : devis PDF + devis Excel + métré PDF + métré Excel.

Chaque création / révision / ajout / relecture d'un devis brouillon par l'Assistant BTP produit ces quatre
fichiers, pour tout compte entreprise. Les fichiers sont des artefacts privés de la conversation
(``assistant_artifacts``), identifiés de façon stable par (devis, version) : un nouvel appel sur la même
version ne régénère rien. Le brouillon n'est jamais numéroté ici (la numérotation reste à l'émission).
"""
import asyncio
import base64
import hashlib
import io
from datetime import datetime, timezone

from core.db import db
from engines.nom_fichier import nom_document

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_LINE_KINDS_SKIP = ("section", "subsection", "text", "pagebreak")

L = {
    "fr": {"quote": "Devis", "takeoff": "Métré", "draft": "BROUILLON — à vérifier avant envoi", "lot": "Lot", "designation": "Désignation",
           "description": "Description", "qty": "Quantité", "unit": "Unité", "pu": "PU HT", "vat": "TVA %", "total": "Total HT",
           "origin": "Origine du prix", "status": "Statut", "to_confirm": "Quantité à confirmer", "ok": "Renseignée",
           "ht": "Total HT", "tva": "TVA", "ttc": "Total TTC", "client": "Client", "date": "Date", "general": "Général",
           "summary": "Récapitulatif par lot", "lines": "lignes", "estimated": "Prix estimé — à vérifier", "user": "Prix fourni",
           "library": "Bibliothèque", "missing": "À compléter", "note_metre": "Quantités issues du devis brouillon ; les quantités « à confirmer » doivent être relevées sur plans ou sur site.",
           "file_quote_pdf": "Devis (PDF)", "file_quote_xlsx": "Devis (Excel)", "file_metre_pdf": "Métré (PDF)", "file_metre_xlsx": "Métré (Excel)"},
    "pt": {"quote": "Orcamento", "takeoff": "Medicao", "draft": "RASCUNHO — a verificar antes do envio", "lot": "Capítulo", "designation": "Designação",
           "description": "Descrição", "qty": "Quantidade", "unit": "Unidade", "pu": "PU s/ IVA", "vat": "IVA %", "total": "Total s/ IVA",
           "origin": "Origem do preço", "status": "Estado", "to_confirm": "Quantidade a confirmar", "ok": "Indicada",
           "ht": "Total s/ IVA", "tva": "IVA", "ttc": "Total c/ IVA", "client": "Cliente", "date": "Data", "general": "Geral",
           "summary": "Resumo por capítulo", "lines": "linhas", "estimated": "Preço estimado — a verificar", "user": "Preço fornecido",
           "library": "Biblioteca", "missing": "A completar", "note_metre": "Quantidades do rascunho de orçamento; as quantidades «a confirmar» devem ser medidas nas plantas ou em obra.",
           "file_quote_pdf": "Orçamento (PDF)", "file_quote_xlsx": "Orçamento (Excel)", "file_metre_pdf": "Medição (PDF)", "file_metre_xlsx": "Medição (Excel)"},
    "en": {"quote": "Quote", "takeoff": "Takeoff", "draft": "DRAFT — to be checked before sending", "lot": "Trade", "designation": "Item",
           "description": "Description", "qty": "Quantity", "unit": "Unit", "pu": "Unit price excl. VAT", "vat": "VAT %", "total": "Total excl. VAT",
           "origin": "Price origin", "status": "Status", "to_confirm": "Quantity to confirm", "ok": "Given",
           "ht": "Total excl. VAT", "tva": "VAT", "ttc": "Total incl. VAT", "client": "Client", "date": "Date", "general": "General",
           "summary": "Summary by trade", "lines": "lines", "estimated": "Estimated price — to check", "user": "Price provided",
           "library": "Library", "missing": "To complete", "note_metre": "Quantities taken from the draft quote; quantities marked 'to confirm' must be measured on drawings or on site.",
           "file_quote_pdf": "Quote (PDF)", "file_quote_xlsx": "Quote (Excel)", "file_metre_pdf": "Takeoff (PDF)", "file_metre_xlsx": "Takeoff (Excel)"},
}


def _lang(lang):
    return lang if lang in L else "fr"


def _rows(doc):
    return [r for r in (doc.get("lines") or []) if r.get("kind") not in _LINE_KINDS_SKIP]


def _origin(r, t):
    if r.get("price_missing"):
        return t["missing"]
    if r.get("price_source") == "user_input":
        return t["user"]
    if r.get("price_estimated"):
        return r.get("price_reference_label") or t["estimated"]
    return t["library"]


def _client(doc):
    c = doc.get("client") or {}
    return doc.get("client_name") or c.get("company") or " ".join(filter(None, [c.get("first_name"), c.get("last_name")])) or ""


def _line_total(r):
    from decimal import ROUND_HALF_UP, Decimal
    disc = Decimal(str(r.get("discount_pct") or 0))
    return float((Decimal(str(r.get("qty") or 0)) * Decimal(str(r.get("unit_price_ht") or 0)) * (1 - disc / 100))
                 .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _style_header(ws, row, ncols):
    from openpyxl.styles import Alignment, Font, PatternFill
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
        cell.alignment = Alignment(vertical="center", wrap_text=True)


def _sheet_head(ws, title, doc, branding, t):
    from openpyxl.styles import Font
    ws["A1"] = (branding or {}).get("company_name") or "ConstruPilot"
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = title
    ws["A2"].font = Font(bold=True, size=12)
    ws["A3"] = t["draft"]
    ws["A3"].font = Font(italic=True, color="B45309")
    ws["A4"] = f"{t['client']} : {_client(doc) or '—'}"
    ws["A5"] = f"{t['date']} : {datetime.now(timezone.utc).date().isoformat()}"
    return 7


def build_quote_xlsx(doc, branding=None, lang="fr") -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    t = L[_lang(lang)]
    wb = Workbook()
    ws = wb.active
    ws.title = t["quote"][:31]
    r0 = _sheet_head(ws, doc.get("title") or t["quote"], doc, branding, t)
    heads = [t["lot"], t["designation"], t["description"], t["qty"], t["unit"], t["pu"], t["vat"], t["total"], t["origin"]]
    for i, h in enumerate(heads, 1):
        ws.cell(row=r0, column=i, value=h)
    _style_header(ws, r0, len(heads))
    rows = _rows(doc)
    first = r0 + 1
    for k, r in enumerate(rows):
        n = first + k
        disc = float(r.get("discount_pct") or 0)
        ws.cell(row=n, column=1, value=r.get("category") or t["general"])
        ws.cell(row=n, column=2, value=r.get("designation") or "")
        ws.cell(row=n, column=3, value=r.get("description") or "").alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(row=n, column=4, value=None if r.get("quantity_missing") else float(r.get("qty") or 0))
        ws.cell(row=n, column=5, value=r.get("unit") or "")
        ws.cell(row=n, column=6, value=None if r.get("price_missing") else float(r.get("unit_price_ht") or 0))
        ws.cell(row=n, column=7, value=float(r.get("vat_rate") or 0))
        factor = f"*(1-{disc}/100)" if disc else ""
        ws.cell(row=n, column=8, value=f"=ROUND(N(D{n})*N(F{n}){factor},2)")
        ws.cell(row=n, column=9, value=_origin(r, t))
        for c in (4, 6, 8):
            ws.cell(row=n, column=c).number_format = "#,##0.00"
    last = first + len(rows) - 1
    tr = last + 2
    rng_h, rng_g = f"H{first}:H{max(last, first)}", f"G{first}:G{max(last, first)}"
    ws.cell(row=tr, column=7, value=t["ht"]).font = Font(bold=True)
    ws.cell(row=tr, column=8, value=f"=ROUND(SUM({rng_h}),2)")
    ws.cell(row=tr + 1, column=7, value=t["tva"]).font = Font(bold=True)
    ws.cell(row=tr + 1, column=8, value=f"=ROUND(SUMPRODUCT({rng_h},{rng_g})/100,2)")
    ws.cell(row=tr + 2, column=7, value=t["ttc"]).font = Font(bold=True)
    ws.cell(row=tr + 2, column=8, value=f"=H{tr}+H{tr + 1}")
    for rr in range(tr, tr + 3):
        ws.cell(row=rr, column=8).number_format = "#,##0.00"
        ws.cell(row=rr, column=8).font = Font(bold=True)
    for col, w in zip("ABCDEFGHI", (18, 42, 50, 11, 8, 13, 8, 14, 26)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = ws.cell(row=first, column=1)
    _metre_sheet(wb.create_sheet(t["takeoff"][:31]), doc, branding, t)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _metre_sheet(ws, doc, branding, t):
    from openpyxl.styles import Alignment, Font
    r0 = _sheet_head(ws, f"{t['takeoff']} — {doc.get('title') or ''}".strip(" —"), doc, branding, t)
    heads = [t["lot"], t["designation"], t["description"], t["qty"], t["unit"], t["status"]]
    for i, h in enumerate(heads, 1):
        ws.cell(row=r0, column=i, value=h)
    _style_header(ws, r0, len(heads))
    n = r0
    for r in _rows(doc):
        n += 1
        ws.cell(row=n, column=1, value=r.get("category") or t["general"])
        ws.cell(row=n, column=2, value=r.get("designation") or "")
        ws.cell(row=n, column=3, value=r.get("description") or "").alignment = Alignment(wrap_text=True, vertical="top")
        q = ws.cell(row=n, column=4, value=None if r.get("quantity_missing") else float(r.get("qty") or 0))
        q.number_format = "#,##0.00"
        ws.cell(row=n, column=5, value=r.get("unit") or "")
        ws.cell(row=n, column=6, value=t["to_confirm"] if r.get("quantity_missing") else t["ok"])
    ws.cell(row=n + 2, column=1, value=t["note_metre"]).font = Font(italic=True)
    # Récapitulatif par lot et unité
    s = n + 4
    ws.cell(row=s, column=1, value=t["summary"]).font = Font(bold=True)
    agg = {}
    for r in _rows(doc):
        if r.get("quantity_missing"):
            continue
        key = (r.get("category") or t["general"], r.get("unit") or "")
        agg[key] = agg.get(key, 0.0) + float(r.get("qty") or 0)
    for i, ((lot, unit), qty) in enumerate(sorted(agg.items()), 1):
        ws.cell(row=s + i, column=1, value=lot)
        ws.cell(row=s + i, column=4, value=round(qty, 3)).number_format = "#,##0.00"
        ws.cell(row=s + i, column=5, value=unit)
    for col, w in zip("ABCDEF", (18, 42, 50, 11, 8, 22)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)


def build_metre_xlsx(doc, branding=None, lang="fr") -> bytes:
    from openpyxl import Workbook
    t = L[_lang(lang)]
    wb = Workbook()
    _metre_sheet(wb.active, doc, branding, t)
    wb.active.title = t["takeoff"][:31]
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_metre_pdf(doc, branding=None, lang="fr") -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    t = L[_lang(lang)]
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("small", fontSize=8, leading=10)
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"{t['takeoff']} — {doc.get('title') or ''}")
    story = [Paragraph(escape((branding or {}).get("company_name") or "ConstruPilot"), ss["Heading3"]),
             Paragraph(escape(f"{t['takeoff']} — {doc.get('title') or ''}".strip(" —")), ss["Title"]),
             Paragraph(f"<i>{escape(t['draft'])}</i>", small),
             Paragraph(escape(f"{t['client']} : {_client(doc) or '—'}  ·  {t['date']} : {datetime.now(timezone.utc).date().isoformat()}"), small),
             Spacer(1, 4 * mm)]
    data = [[t["lot"], t["designation"], t["description"], t["qty"], t["unit"], t["status"]]]
    for r in _rows(doc):
        qty = "—" if r.get("quantity_missing") else f"{float(r.get('qty') or 0):,.2f}".replace(",", " ")
        data.append([Paragraph(escape(r.get("category") or t["general"]), small), Paragraph(escape(r.get("designation") or ""), small),
                     Paragraph(escape((r.get("description") or "")[:600]), small), qty, r.get("unit") or "",
                     Paragraph(escape(t["to_confirm"] if r.get("quantity_missing") else t["ok"]), small)])
    tbl = LongTable(data, colWidths=[35 * mm, 70 * mm, 105 * mm, 22 * mm, 15 * mm, 26 * mm], repeatRows=1)
    tbl.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F3A5F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                             ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (3, 1), (3, -1), "RIGHT"),
                             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")])]))
    story += [tbl, Spacer(1, 4 * mm), Paragraph(f"<i>{escape(t['note_metre'])}</i>", small)]
    pdf.build(story)
    return buf.getvalue()


async def _context(doc, user):
    from routes.company_page import pdf_customization
    from routes.documents import _doc_lang
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(user["user_id"]) or {}
    try:
        branding = {**branding, **await pdf_customization(user["user_id"])}
    except Exception:  # noqa: BLE001 — personnalisation facultative
        pass
    lang = await _doc_lang(doc, branding)
    acct_langs = [x for x in (user.get("doc_langs") or []) if x in ("fr", "pt", "en", "uk")]
    if acct_langs:
        lang = acct_langs[0]
        try:
            from engines.doc_translate import translate_doc
            doc = await translate_doc(db, doc, lang)
        except Exception:  # noqa: BLE001 — sans traduction, le contenu d'origine reste exploitable
            pass
    return doc, branding, lang


def _quote_pdf(doc, branding, lang):
    from engines.pdf_docs import build_document_pdf
    draft = {**doc, "number": None}          # jamais de numéro légal sur un brouillon
    return build_document_pdf(draft, branding=branding, lang=lang)


async def attach_quote_exports(doc_id, user, conv) -> list[dict]:
    """Produit (ou retrouve) devis PDF/XLSX + métré PDF/XLSX pour la version courante du devis."""
    from engines.assistant_files import public_artifact
    uid = user["user_id"]
    doc = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": uid, "doc_type": "quote"}, {"_id": 0})
    if not doc or not _rows(doc):
        return []
    version = hashlib.sha256(f"{doc_id}|{doc.get('updated_at')}".encode()).hexdigest()[:20]
    kinds = ("quote_pdf", "quote_xlsx", "metre_pdf", "metre_xlsx")
    ids = {k: f"qx_{version}_{k}" for k in kinds}
    existing = {a["artifact_id"]: a async for a in db.assistant_artifacts.find(
        {"artifact_id": {"$in": list(ids.values())}, "user_id": uid}, {"_id": 0, "data_b64": 0, "body": 0})}
    if len(existing) == len(kinds):
        return [public_artifact(existing[ids[k]]) for k in kinds]
    src, branding, lang = await _context(doc, user)
    builders = {"quote_pdf": (_quote_pdf, "pdf"), "quote_xlsx": (build_quote_xlsx, "xlsx"),
                "metre_pdf": (build_metre_pdf, "pdf"), "metre_xlsx": (build_metre_xlsx, "xlsx")}
    t = L[_lang(lang)]
    out, now = [], datetime.now(timezone.utc).isoformat()
    for k in kinds:
        if ids[k] in existing:
            out.append(public_artifact(existing[ids[k]]))
            continue
        fn, ext = builders[k]
        data = await asyncio.to_thread(fn, src, branding, lang)
        type_doc = t["quote"] if k.startswith("quote") else t["takeoff"]
        art = {"artifact_id": ids[k], "user_id": uid, "conversation_id": conv["conversation_id"],
               "request_id": conv.get("_quote_request_id"), "title": t["file_" + k], "body": f"{type_doc} — {doc.get('title') or ''}",
               "filename": nom_document(type_doc, doc.get("title") or _client(doc), ext=ext), "format": ext,
               "mime": "application/pdf" if ext == "pdf" else XLSX_MIME, "size": len(data),
               "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": now,
               "illustrative": False, "quote_doc_id": doc_id, "quote_export": k,
               "download": f"/assistant/artifacts/{ids[k]}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": ids[k], "user_id": uid}, {"$setOnInsert": art}, upsert=True)
        out.append(public_artifact(art))
    return out


async def with_exports(result, user, conv):
    """Ajoute les 4 fichiers au résultat d'un outil devis ; une erreur d'export ne casse jamais le devis."""
    doc_id = (result or {}).get("doc_id")
    if not doc_id:
        return result
    try:
        files = await attach_quote_exports(doc_id, user, conv)
    except Exception as exc:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("quote exports failed for %s", doc_id)
        return {**result, "files_error": f"Fichiers PDF/Excel non générés : {type(exc).__name__}. Le devis est enregistré ; réessayer avec read_quote_draft."}
    if files:
        result = {**result, "artifacts": files,
                  "files_note": "Devis et métré fournis en PDF ET en Excel (4 fichiers joints). Annonce-les tous les quatre."}
    return result


async def study_exports(plan_id, user, conv, study) -> list[dict]:
    """Étude complète d'un permis : devis/métré sourcés en PDF et en Excel (les exports existants de l'étude)."""
    from engines.assistant_files import public_artifact
    from routes.plans_export import export_xlsx
    from routes.plans_pc import export_pc_pdf
    if not study or not study.get("items"):
        return []
    uid = user["user_id"]
    version = hashlib.sha256(f"{plan_id}|{study.get('generated_at') or study.get('updated_at') or len(study.get('items') or [])}|{(study.get('totals') or {})}".encode()).hexdigest()[:20]
    out, now = [], datetime.now(timezone.utc).isoformat()
    for kind, fn, ext, title in (("study_pdf", export_pc_pdf, "pdf", "Devis + métré de l'étude (PDF)"),
                                 ("study_xlsx", export_xlsx, "xlsx", "Devis + métré de l'étude (Excel)")):
        ident = f"sx_{version}_{kind}"
        old = await db.assistant_artifacts.find_one({"artifact_id": ident, "user_id": uid}, {"_id": 0, "data_b64": 0, "body": 0})
        if old:
            out.append(public_artifact(old))
            continue
        resp = await (fn(plan_id, None, user=user) if ext == "pdf" else fn(plan_id, user=user))
        data = bytes(resp.body)
        art = {"artifact_id": ident, "user_id": uid, "conversation_id": conv["conversation_id"], "request_id": conv.get("_quote_request_id"),
               "title": title, "body": title, "filename": nom_document("Etude", study.get("title") or plan_id, ext=ext), "format": ext,
               "mime": "application/pdf" if ext == "pdf" else XLSX_MIME, "size": len(data), "data_b64": base64.b64encode(data).decode(),
               "source_artifact_ids": [], "created_at": now, "illustrative": False, "plan_id": plan_id,
               "download": f"/assistant/artifacts/{ident}/content"}
        await db.assistant_artifacts.update_one({"artifact_id": ident, "user_id": uid}, {"$setOnInsert": art}, upsert=True)
        out.append(public_artifact(art))
    return out
