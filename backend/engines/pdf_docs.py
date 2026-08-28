"""PDF générique pour les documents pro : devis, factures, avoirs.

Lignes libres (désignation / qté / unité / PU HT / TVA), TVA multi-taux, acompte.
Réutilise les helpers de mise en page de pdf_takeoff.
"""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image

from engines.pdf_takeoff import (
    _styles, _table, _fmt, _story_header_branding, _story_quote_reviews,
    DARK, LIGHT_GREY, ORANGE,
)
from engines.pdf_i18n import pdf_labels

DOC_LABELS = {"quote": "DEVIS", "invoice": "FACTURE", "credit_note": "AVOIR"}


def _client_block(story: list, client: dict | None, S: dict, L: dict) -> None:
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
    html = "<br/>".join(lines) or L["client"]
    tbl = _table([[Paragraph(f"<b>{L['addressed_to']}</b><br/>" + html, S["body"])]], [88 * mm],
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


def _desig_cell(ln: dict, S: dict):
    """Cellule désignation : titre en gras + description détaillée (puces) en dessous."""
    html = f"<b>{escape(ln.get('designation') or '')}</b>"
    desc = (ln.get("description") or "").strip()
    if desc:
        desc_html = escape(desc).replace("\r\n", "\n").replace("\n", "<br/>")
        html += f'<br/><font size="7.5" color="#5B6472">{desc_html}</font>'
    return Paragraph(html, S["body"])


def _lines_table(story: list, lines: list, S: dict, L: dict) -> None:
    story.append(Paragraph(L["lines_title"], S["h2"]))
    header = [L["c_designation"], L["c_qty"], L["c_unit"], L["c_pu_ht"], L["c_vat"], L["c_total_ht"]]
    rows = [header]

    def _line_row(ln):
        qty = ln.get("qty") or 0
        pu = ln.get("unit_price_ht") or 0
        return [_desig_cell(ln, S), _fmt(qty), ln.get("unit") or "",
                _fmt(pu, "€"), f"{_fmt(ln.get('vat_rate') or 0)}%",
                _fmt(round(qty * pu, 2), "€")]

    # Regroupement par lot (champ `category`), en conservant l'ordre d'apparition.
    groups, order = [], {}
    for ln in lines:
        cat = (ln.get("category") or "").strip()
        if cat not in order:
            order[cat] = len(groups)
            groups.append((cat, []))
        groups[order[cat]][1].append(ln)
    use_groups = any(cat for cat, _ in groups)

    header_rows, subtotal_rows = [], []
    if not lines:
        rows.append([L["no_line"], "", "", "", "", ""])
    elif not use_groups:
        for ln in lines:
            rows.append(_line_row(ln))
    else:
        for cat, lns in groups:
            label = cat or L.get("other_lot", "Autres")
            header_rows.append(len(rows))
            rows.append([Paragraph(f"<b>{escape(label)}</b>", S["body"]), "", "", "", "", ""])
            sub = 0.0
            for ln in lns:
                rows.append(_line_row(ln))
                sub += round((ln.get("qty") or 0) * (ln.get("unit_price_ht") or 0), 2)
            subtotal_rows.append(len(rows))
            rows.append([Paragraph(f'<b>{L.get("subtotal", "Sous-total")} · {escape(label)}</b>',
                                   S["body"]), "", "", "", "",
                         Paragraph(f"<b>{_fmt(round(sub, 2), '€')}</b>", S["body"])])

    extras = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 1), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
    ]
    if use_groups:
        for r in header_rows:
            extras += [("SPAN", (0, r), (4, r)),
                       ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#EEEBE6")),
                       ("TOPPADDING", (0, r), (-1, r), 7)]
        for r in subtotal_rows:
            extras += [("SPAN", (0, r), (4, r)),
                       ("ALIGN", (0, r), (4, r), "RIGHT"),
                       ("LINEABOVE", (0, r), (-1, r), 0.5, LIGHT_GREY),
                       ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FAF8F5"))]
    else:
        extras += [("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY])]

    story.append(_table(
        rows, [78 * mm, 16 * mm, 16 * mm, 22 * mm, 14 * mm, 26 * mm],
        style_extras=extras, repeat_rows=1))


def _recap(story: list, doc: dict, S: dict, L: dict) -> None:
    t = doc.get("totals", {})
    story.append(Spacer(1, 12))
    story.append(Paragraph(L["recap"], S["h2"]))
    rows = [[L["total_ht"], _fmt(t.get("ht", 0), "€")]]
    for rate, amount in (t.get("tva_breakdown") or {}).items():
        rows.append([L["vat"].format(rate=_fmt(float(rate))), _fmt(amount, "€")])
    rows.append([L["total_ttc"], _fmt(t.get("ttc", 0), "€")])
    if (t.get("deposit_pct") or 0) > 0:
        rows.append([L["deposit_asked"].format(pct=_fmt(t.get('deposit_pct'))),
                     _fmt(t.get("deposit_amount", 0), "€")])
        rows.append([L["remaining"], _fmt(t.get("remaining", 0), "€")])
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
                       reviews: dict | None = None, lang: str | None = None) -> bytes:
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    L = pdf_labels(lang)
    story: list = []

    _story_header_branding(story, branding, S)
    _doc_key = {"quote": "doc_quote", "invoice": "doc_invoice", "credit_note": "doc_credit"}
    label = L[_doc_key.get(doc.get("doc_type"), "doc_generic")]
    story.append(Paragraph(label, S["kicker"]))
    story.append(Paragraph(doc.get("title") or doc.get("number") or label, S["h1"]))
    meta = []
    if doc.get("number"):
        meta.append(f"{L['num']} <b>{doc['number']}</b>")
    if doc.get("issue_date"):
        meta.append(f"{L['date']} : {doc['issue_date'][:10]}")
    if doc.get("due_date"):
        meta.append(f"{L['due']} : {doc['due_date'][:10]}")
    if meta:
        story.append(Paragraph(" · ".join(meta), S["muted"]))
    story.append(Spacer(1, 10))

    _client_block(story, doc.get("client"), S, L)
    _lines_table(story, doc.get("lines", []), S, L)
    _recap(story, doc, S, L)

    _attach = doc.get("attachment_image_b64")
    if _attach:
        try:
            import base64
            raw = base64.b64decode(_attach.split(",", 1)[-1])
            img = Image(BytesIO(raw))
            max_w = 170 * mm
            ratio = (img.imageHeight or 1) / (img.imageWidth or 1)
            img.drawWidth = max_w
            img.drawHeight = max_w * ratio
            story.append(Spacer(1, 14))
            story.append(Paragraph(L.get("attachment_3d", "Vue 3D du projet"), S["h2"]))
            story.append(img)
        except Exception:
            pass

    if doc.get("notes"):
        story.append(Spacer(1, 12))
        story.append(Paragraph(L["notes"], S["h2"]))
        story.append(Paragraph(doc["notes"].replace("\n", "<br/>"), S["body"]))

    if doc.get("doc_type") == "quote":
        story.append(Spacer(1, 16))
        story.append(Paragraph(L["agreement"], S["muted"]))
        _story_quote_reviews(story, reviews, S)

    story.append(Spacer(1, 16))
    story.append(Paragraph(L["footer"], S["muted"]))

    pdf.build(story)
    return buf.getvalue()
