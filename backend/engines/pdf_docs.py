"""PDF générique pour les documents pro : devis, factures, avoirs.

Lignes libres (désignation / qté / unité / PU HT / TVA), TVA multi-taux, acompte.
Réutilise les helpers de mise en page de pdf_takeoff.
"""
from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from engines.pdf_takeoff import (
    _styles, _table, _fmt, _story_header_branding, _story_quote_reviews,
    DARK, LIGHT_GREY, ORANGE,
)

DOC_LABELS = {"quote": "DEVIS", "invoice": "FACTURE", "credit_note": "AVOIR"}


def _client_block(story: list, client: dict | None, S: dict) -> None:
    if not client:
        return
    name = " ".join(x for x in [client.get("first_name"), client.get("last_name")] if x)
    lines = []
    if client.get("company"):
        lines.append(f"<b>{client['company']}</b>")
    if name:
        lines.append(name if not client.get("company") else name)
    addr = ", ".join(x for x in [client.get("address"), client.get("postal_code"),
                                 client.get("city")] if x)
    if addr:
        lines.append(addr)
    if client.get("email"):
        lines.append(client["email"])
    if client.get("phone"):
        lines.append(client["phone"])
    if client.get("siret"):
        lines.append(f"SIRET {client['siret']}")
    html = "<br/>".join(lines) or "Client"
    tbl = _table([[Paragraph("<b>Adressé à</b><br/>" + html, S["body"])]], [88 * mm],
                 style_extras=[
                     ("BOX", (0, 0), (-1, -1), 0.6, LIGHT_GREY),
                     ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F7F7F5")),
                     ("LEFTPADDING", (0, 0), (-1, -1), 10),
                     ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                     ("TOPPADDING", (0, 0), (-1, -1), 8),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                 ])
    story.append(tbl)
    story.append(Spacer(1, 10))


def _lines_table(story: list, lines: list, S: dict) -> None:
    story.append(Paragraph("Détail des prestations", S["h2"]))
    rows = [["Désignation", "Qté", "Unité", "PU HT", "TVA", "Total HT"]]
    for ln in lines:
        qty = ln.get("qty") or 0
        pu = ln.get("unit_price_ht") or 0
        rows.append([
            ln.get("designation") or "",
            _fmt(qty), ln.get("unit") or "",
            _fmt(pu, "€"),
            f"{_fmt(ln.get('vat_rate') or 0)}%",
            _fmt(round(qty * pu, 2), "€"),
        ])
    if len(rows) == 1:
        rows.append(["Aucune ligne", "", "", "", "", ""])
    story.append(_table(
        rows, [78 * mm, 16 * mm, 16 * mm, 22 * mm, 14 * mm, 26 * mm],
        style_extras=[
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ], repeat_rows=1))


def _recap(story: list, doc: dict, S: dict) -> None:
    t = doc.get("totals", {})
    story.append(Spacer(1, 12))
    story.append(Paragraph("Récapitulatif", S["h2"]))
    rows = [["Total HT", _fmt(t.get("ht", 0), "€")]]
    for rate, amount in (t.get("tva_breakdown") or {}).items():
        rows.append([f"TVA {_fmt(float(rate))} %", _fmt(amount, "€")])
    rows.append(["TOTAL TTC", _fmt(t.get("ttc", 0), "€")])
    if (t.get("deposit_pct") or 0) > 0:
        rows.append([f"Acompte demandé ({_fmt(t.get('deposit_pct'))} %)",
                     _fmt(t.get("deposit_amount", 0), "€")])
        rows.append(["Reste à régler", _fmt(t.get("remaining", 0), "€")])
    ttc_row = 1 + len(t.get("tva_breakdown") or {})
    story.append(_table(rows, [110 * mm, 45 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("BACKGROUND", (0, ttc_row), (-1, ttc_row), ORANGE),
        ("TEXTCOLOR", (0, ttc_row), (-1, ttc_row), colors.white),
        ("FONTNAME", (0, ttc_row), (-1, ttc_row), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTSIZE", (0, ttc_row), (-1, ttc_row), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))


def build_document_pdf(doc: dict, branding: dict | None = None,
                       reviews: dict | None = None) -> bytes:
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    story: list = []

    _story_header_branding(story, branding, S)
    label = DOC_LABELS.get(doc.get("doc_type"), "DOCUMENT")
    story.append(Paragraph(label, S["kicker"]))
    story.append(Paragraph(doc.get("title") or doc.get("number") or label, S["h1"]))
    meta = []
    if doc.get("number"):
        meta.append(f"N° <b>{doc['number']}</b>")
    if doc.get("issue_date"):
        meta.append(f"Date : {doc['issue_date'][:10]}")
    if doc.get("due_date"):
        meta.append(f"Échéance : {doc['due_date'][:10]}")
    if meta:
        story.append(Paragraph(" · ".join(meta), S["muted"]))
    story.append(Spacer(1, 10))

    _client_block(story, doc.get("client"), S)
    _lines_table(story, doc.get("lines", []), S)
    _recap(story, doc, S)

    if doc.get("notes"):
        story.append(Spacer(1, 12))
        story.append(Paragraph("Notes", S["h2"]))
        story.append(Paragraph(doc["notes"].replace("\n", "<br/>"), S["body"]))

    if doc.get("doc_type") == "quote":
        story.append(Spacer(1, 16))
        story.append(Paragraph("Bon pour accord (date + signature) :", S["muted"]))
        _story_quote_reviews(story, reviews, S)

    story.append(Spacer(1, 16))
    story.append(Paragraph(
        "Document émis via ConstruPilot. TVA applicable selon la nature des travaux "
        "(10 % rénovation logement +2 ans, 20 % neuf, 5,5 % rénovation énergétique). "
        "Conditions de règlement selon mentions ci-dessus.", S["muted"]))

    pdf.build(story)
    return buf.getvalue()
