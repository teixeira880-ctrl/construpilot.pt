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
    dep = float(sit.get("deposit_imputed_ht") or 0)
    works = float(sit.get("works_ht") or (ht + dep))
    tot = []
    if dep:
        tot.append(["Travaux de la situation HT", _eur(works)])
        tot.append(["Acompte déjà versé (déduit) HT", "- " + _eur(dep)])
    tot += [
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


def build_payment_certificate(sit: dict, branding: dict | None, client: dict | None) -> bytes:
    """Certificat de paiement (état d'acompte) avec visa maître d'œuvre."""
    branding = branding or {}
    client = client or {}
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#475569"))
    h = ParagraphStyle("h", parent=styles["Normal"], fontSize=16, textColor=DARK, spaceAfter=2, fontName="Helvetica-Bold")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    E = [Paragraph(branding.get("company_name") or "ConstruPilot", h)]
    ids = " · ".join(filter(None, [f"SIRET {branding.get('siret')}" if branding.get("siret") else None,
                                   f"TVA {branding.get('vat')}" if branding.get("vat") else None]))
    if ids:
        E.append(Paragraph(ids, small))
    E.append(Spacer(1, 10))
    E.append(Paragraph(f"CERTIFICAT DE PAIEMENT N°{sit.get('seq')}", h))
    E.append(Paragraph(f"Marché : {sit.get('marche_label') or '—'} · Facture liée : {sit.get('invoice_number') or '—'}", small))
    cname = client.get("name") or client.get("company") or ""
    if cname:
        E.append(Paragraph(f"Maître d'ouvrage : {cname}", small))
    E.append(Spacer(1, 12))

    ht = float(sit.get("total_ht") or 0)
    ttc = float(sit.get("total_ttc") or 0)
    ret = float(sit.get("retention_amount") or 0)
    net = float(sit.get("net_due") or (ttc - ret))
    dep = float(sit.get("deposit_imputed_ht") or 0)
    works = float(sit.get("works_ht") or (ht + dep))
    rows = []
    if dep:
        rows.append(["Travaux de la situation HT", _eur(works)])
        rows.append(["Acompte déjà versé (déduit) HT", "- " + _eur(dep)])
    rows += [
        ["Montant des travaux (situation) HT", _eur(ht)],
        ["Montant TTC", _eur(ttc)],
        [f"Retenue de garantie ({float(sit.get('retention_pct') or 0):g}%)", "- " + _eur(ret)],
        ["MONTANT CERTIFIÉ — BON À PAYER (TTC)", _eur(net)],
    ]
    tt = Table(rows, colWidths=[120 * mm, 48 * mm])
    last = len(rows) - 1
    tt.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, last), (-1, last), 0.8, DARK),
        ("BACKGROUND", (0, last), (-1, last), GREEN),
        ("TEXTCOLOR", (0, last), (-1, last), colors.white),
        ("FONTNAME", (0, last), (-1, last), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    E.append(tt)
    E.append(Spacer(1, 24))
    E.append(Paragraph("Je soussigné, maître d'œuvre, certifie que les travaux correspondant au présent "
                       "décompte ont été exécutés et donne bon à payer pour le montant certifié ci-dessus.", small))
    E.append(Spacer(1, 20))
    sign = Table([["Date : ______________________", "Visa & cachet du maître d'œuvre :"]],
                 colWidths=[84 * mm, 84 * mm])
    sign.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("TOPPADDING", (0, 0), (-1, -1), 30)]))
    E.append(sign)
    doc.build(E)
    return buf.getvalue()


def build_dgd_pdf(recap: dict, branding: dict | None, client: dict | None) -> bytes:
    """Décompte général définitif (DGD) : bilan complet du marché, acompte et retenue inclus."""
    branding = branding or {}
    client = client or {}
    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8,
                           textColor=colors.HexColor("#475569"))
    h = ParagraphStyle("h", parent=styles["Normal"], fontSize=16, textColor=DARK,
                       spaceAfter=2, fontName="Helvetica-Bold")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    E = []
    m = recap.get("marche") or {}
    t = recap.get("totals") or {}

    seller = branding.get("company_name") or "ConstruPilot"
    addr = " · ".join(filter(None, [branding.get("address"),
                                    " ".join(filter(None, [branding.get("postal_code"),
                                                           branding.get("city")]))]))
    E.append(Paragraph(seller, h))
    if addr:
        E.append(Paragraph(addr, small))
    E.append(Spacer(1, 8))
    E.append(Paragraph("DÉCOMPTE GÉNÉRAL DÉFINITIF", h))
    meta = f"Marché : {m.get('number') or m.get('title') or '—'}"
    if m.get("reception_date"):
        meta += f" · Réception : {m['reception_date']}"
    E.append(Paragraph(meta, small))
    cname = client.get("name") or client.get("company") or " ".join(
        filter(None, [client.get("first_name"), client.get("last_name")]))
    if cname:
        E.append(Paragraph(f"Maître d'ouvrage : {cname}", small))
    E.append(Spacer(1, 10))

    rows = [["Poste du marché", "Marché HT", "Avanc.", "Facturé HT", "Solde HT"]]
    for ln in recap.get("lines", [])[:120]:
        rows.append([Paragraph(str(ln.get("designation") or "")[:110], small),
                     _eur(ln.get("contract_ht")), f"{float(ln.get('cumul_pct') or 0):g}%",
                     _eur(ln.get("billed_ht")), _eur(ln.get("remaining_ht"))])
    tb = Table(rows, colWidths=[78 * mm, 24 * mm, 16 * mm, 26 * mm, 24 * mm], repeatRows=1)
    tb.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    E.append(tb)
    E.append(Spacer(1, 12))

    tot = [["Montant du marché HT", _eur(t.get("contract_ht"))],
           ["Travaux facturés à ce jour HT", _eur(t.get("billed_ht"))],
           ["Solde de travaux HT", _eur(t.get("remaining_ht"))]]
    if t.get("deposit_available_ht"):
        tot.append(["Acompte encaissé restant à imputer HT", "- " + _eur(t["deposit_available_ht"])])
    tot.append(["Solde à facturer HT", _eur(t.get("dgd_ht"))])
    tot.append(["Solde à facturer TTC", _eur(t.get("dgd_ttc"))])
    if t.get("retention_held"):
        label = "Retenue de garantie libérée" if t.get("retention_released") else "Retenue de garantie détenue"
        tot.append([label, _eur(t["retention_held"])])
    tot.append(["TOTAL DÛ AU TITRE DU DGD", _eur(t.get("dgd_due"))])
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
    E.append(Spacer(1, 14))

    sits = recap.get("situations") or []
    if sits:
        srows = [["Situation", "Facture", "Montant TTC", "Acompte déduit HT", "Retenue"]]
        for sx in sits:
            srows.append([f"N°{sx.get('seq')}", str(sx.get("invoice_number") or "—"),
                          _eur(sx.get("total_ttc")), _eur(sx.get("deposit_imputed_ht")),
                          _eur(sx.get("retention_amount"))])
        st = Table(srows, colWidths=[24 * mm, 44 * mm, 34 * mm, 34 * mm, 32 * mm], repeatRows=1)
        st.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ]))
        E.append(Paragraph("Récapitulatif des situations", small))
        E.append(Spacer(1, 4))
        E.append(st)
        E.append(Spacer(1, 12))

    E.append(Paragraph(
        "Le présent décompte général définitif arrête les comptes du marché : travaux exécutés, "
        "acomptes versés et retenue de garantie. Il vaut solde du marché sous réserve des réserves "
        "de réception éventuelles.", small))
    doc.build(E)
    return buf.getvalue()
