"""Génération PDF d'un bon de commande fournisseur (approvisionnement)."""
from datetime import datetime, timezone
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)

BRAND = colors.HexColor("#FF5A00")
TYPE_LABEL = {"acier": "Ferraillage / Acier", "etancheite": "Étanchéité",
              "toiture": "Toiture", "vrd": "VRD"}


def build_order_pdf(order: dict, company: dict | None = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=18, textColor=colors.HexColor("#0A0D14"))
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=8, textColor=colors.HexColor("#64748B"))
    normal = ss["Normal"]
    el = []

    company_name = (company or {}).get("company_name") or "ConstruPilot"
    el.append(Paragraph(f"<b>{company_name}</b>", h1))
    el.append(Paragraph("Bon de commande — Approvisionnement chantier", small))
    el.append(Spacer(1, 8))

    sup = order.get("supplier") or {}
    date = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    meta = [
        ["N° commande", order.get("order_id", "—"), "Date", date],
        ["Type", TYPE_LABEL.get(order.get("type"), order.get("type", "—")),
         "Projet", order.get("project") or "—"],
        ["Fournisseur", sup.get("name") or "—", "Agence", sup.get("agency") or "—"],
        ["N° client", sup.get("client_number") or "—", "Livraison", sup.get("delivery_address") or "—"],
    ]
    mt = Table(meta, colWidths=[28 * mm, 60 * mm, 24 * mm, 66 * mm])
    mt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748B")),
        ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#64748B")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(mt)
    el.append(Spacer(1, 10))

    priced = any(it.get("unit_price") for it in order.get("items", []))
    head = ["Désignation", "Qté", "Unité", "Cmd.", "Cond."]
    if priced:
        head += ["PU HT", "Total HT"]
    rows = [head]
    for it in order.get("items", []):
        r = [Paragraph(str(it.get("designation", "")), normal),
             str(it.get("qty", "")), str(it.get("unit", "")),
             str(it.get("commandable_qty") if it.get("commandable_qty") is not None else "—"),
             str(it.get("commandable_unit") or "—")]
        if priced:
            r += [f"{it.get('unit_price', 0):.2f} €", f"{it.get('line_total', 0):.2f} €"]
        rows.append(r)

    col_w = [66 * mm, 16 * mm, 14 * mm, 16 * mm, 20 * mm]
    if priced:
        col_w = [50 * mm, 14 * mm, 12 * mm, 14 * mm, 16 * mm, 20 * mm, 22 * mm]
    t = Table(rows, colWidths=col_w, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]
    t.setStyle(TableStyle(style))
    el.append(t)

    if priced:
        el.append(Spacer(1, 8))
        total = sum(it.get("line_total", 0) for it in order.get("items", []))
        tot = Table([["Total estimé HT", f"{total:.2f} €"]], colWidths=[130 * mm, 32 * mm])
        tot.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 10), ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"), ("TEXTCOLOR", (1, 0), (1, 0), BRAND),
        ]))
        el.append(tot)

    el.append(Spacer(1, 16))
    el.append(Paragraph("Estimation quantitative indicative issue de l'analyse IA du plan — "
                        "à vérifier avant commande ferme.", small))
    doc.build(el)
    return buf.getvalue()
