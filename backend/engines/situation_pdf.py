"""Décompte de situation de travaux (PDF) — format attendu par la maîtrise d'œuvre."""
from __future__ import annotations

import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

GREEN = colors.HexColor("#16a34a")
DARK = colors.HexColor("#0f172a")
LIGHT = colors.HexColor("#f1f5f9")


def _eur(v) -> str:
    try:
        return f"{float(v or 0):,.2f} €".replace(",", " ").replace(".", ",", 1)
    except (TypeError, ValueError):
        return "0,00 €"


def build_situation_pdf(sit: dict, branding: dict | None, client: dict | None) -> bytes:
    branding = branding or {}
    client = client or {}
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#475569"))
    h = ParagraphStyle("h", parent=styles["Normal"], fontSize=16, textColor=DARK, spaceAfter=2, fontName="Helvetica-Bold")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    E = []

    seller = branding.get("company_name") or "ConstruPilot"
    addr = " · ".join(filter(None, [branding.get("address"),
                                    " ".join(filter(None, [branding.get("postal_code"), branding.get("city")]))]))
    ids = " · ".join(filter(None, [f"SIRET {branding.get('siret')}" if branding.get("siret") else None,
                                   f"TVA {branding.get('vat')}" if branding.get("vat") else None]))
    E.append(Paragraph(seller, h))
    if addr:
        E.append(Paragraph(addr, small))
    if ids:
        E.append(Paragraph(ids, small))
    E.append(Spacer(1, 8))

    E.append(Paragraph(f"DÉCOMPTE DE SITUATION N°{sit.get('seq')}", h))
    meta = f"Marché : {sit.get('marche_label') or '—'}"
    if sit.get("invoice_number"):
        meta += f" · Facture : {sit['invoice_number']}"
    if sit.get("created_at"):
        meta += f" · Date : {str(sit['created_at'])[:10]}"
    E.append(Paragraph(meta, small))
    cname = client.get("name") or client.get("company") or " ".join(
        filter(None, [client.get("first_name"), client.get("last_name")]))
    if cname:
        E.append(Paragraph(f"Maître d'ouvrage : {cname}", small))
    E.append(Spacer(1, 10))

    head = ["Lot / Poste", "Marché HT", "% préc.", "% cumulé", "Cumul HT", "Cette situation HT"]
    rows = [head]
    for l in sit.get("lines", []):
        contract = float(l.get("contract_ht") or 0)
        cum = float(l.get("cumul_pct") or 0)
        rows.append([
            Paragraph(str(l.get("designation") or ""), small),
            _eur(contract), f"{float(l.get('prev_pct') or 0):g}%",
            f"{cum:g}%", _eur(round(contract * cum / 100, 2)), _eur(l.get("situation_ht")),
        ])
    tbl = Table(rows, colWidths=[58 * mm, 24 * mm, 16 * mm, 18 * mm, 24 * mm, 28 * mm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    E.append(tbl)
    E.append(Spacer(1, 12))

    ht = float(sit.get("total_ht") or 0)
    ttc = float(sit.get("total_ttc") or 0)
    tva = round(ttc - ht, 2)
    ret = float(sit.get("retention_amount") or 0)
    net = float(sit.get("net_due") or (ttc - ret))
    tot = [
        ["Total situation HT", _eur(ht)],
        ["TVA", _eur(tva)],
        ["Total situation TTC", _eur(ttc)],
    ]
    if ret:
        tot.append([f"Retenue de garantie ({float(sit.get('retention_pct') or 0):g}%)", "- " + _eur(ret)])
    tot.append(["NET À PAYER", _eur(net)])
    tt = Table(tot, colWidths=[120 * mm, 48 * mm], hAlign="RIGHT")
    last = len(tot) - 1
    tt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, last), (-1, last), 0.8, DARK),
        ("BACKGROUND", (0, last), (-1, last), GREEN),
        ("TEXTCOLOR", (0, last), (-1, last), colors.white),
        ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    E.append(tt)
    E.append(Spacer(1, 16))
    E.append(Paragraph("Décompte établi à l'avancement des travaux. La retenue de garantie est "
                       "conservée et libérable à l'expiration du délai légal (1 an après réception).", small))

    doc.build(E)
    return buf.getvalue()
