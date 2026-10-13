"""PDF du procès-verbal de réception de travaux.

Réutilise la palette et les en-têtes des documents pro (pdf_docs) pour une identité cohérente.
"""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from engines.pdf_takeoff import _styles, _table
from engines.pdf_docs import _palette, _doc_styles, _header_banner, _page_footer, _fiscal_parts
from engines.pdf_i18n import pdf_labels

DECISIONS = {
    "sans_reserve": "Réception PRONONCÉE SANS réserve",
    "avec_reserve": "Réception PRONONCÉE AVEC réserves",
    "refus": "Réception REFUSÉE",
}


def _client_name(c: dict) -> str:
    if not c:
        return "Client"
    if c.get("company"):
        return c["company"]
    return " ".join(x for x in [c.get("first_name"), c.get("last_name")] if x) or "Client"


def build_pv_pdf(pv: dict, branding: dict | None = None, lang: str = "fr") -> bytes:
    P = _palette(branding)
    L = pdf_labels(lang)
    S = _doc_styles(_styles(), P, "bandeau")
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=14 * mm, bottomMargin=26 * mm)
    story: list = []
    _header_banner(story, branding, S, P)

    story.append(Paragraph("PROCÈS-VERBAL", S["kicker"]))
    story.append(Paragraph("Réception de travaux", S["h1"]))
    meta = []
    if pv.get("ref"):
        meta.append(f"N° {escape(str(pv['ref']))}")
    if pv.get("date_reception"):
        meta.append(f"Date de réception : {pv['date_reception'][:10]}")
    if meta:
        story.append(Paragraph(" · ".join(meta), S["muted"]))
    story.append(Spacer(1, 10))

    # Parties : entreprise / maître d'ouvrage
    b = branding or {}
    ent = [f"<b>{escape(b.get('company_name') or 'Entreprise')}</b>"]
    if b.get("contact_line"):
        ent.append(escape(b["contact_line"]))
    fisc = _fiscal_parts(b)
    if fisc:
        ent.append(escape(" · ".join(fisc)))
    cl = pv.get("client") or {}
    cli = [f"<b>{escape(_client_name(cl))}</b>"]
    addr = ", ".join(x for x in [cl.get("address"), cl.get("postal_code"), cl.get("city")] if x)
    if addr:
        cli.append(escape(addr))
    if cl.get("email"):
        cli.append(escape(cl["email"]))
    kicker = S["kicker"].clone("pv_k")
    kicker.spaceAfter = 3
    story.append(_table([[
        [Paragraph("ENTREPRISE", kicker), Paragraph("<br/>".join(ent), S["body"])],
        [Paragraph("MAÎTRE D'OUVRAGE", kicker), Paragraph("<br/>".join(cli), S["body"])],
    ]], [87 * mm, 87 * mm], style_extras=[
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, -1), 0), ("LEFTPADDING", (1, 0), (1, -1), 12),
        ("LINEBEFORE", (1, 0), (1, -1), 0.5, P["line"]),
    ]))
    story.append(Spacer(1, 10))

    # Chantier
    site = pv.get("chantier_name") or ""
    if pv.get("chantier_address"):
        site = f"{site} — {pv['chantier_address']}" if site else pv["chantier_address"]
    if site:
        story.append(Paragraph(f"<b>Chantier :</b> {escape(site)}", S["body"]))
        story.append(Spacer(1, 8))

    # Décision
    decision = DECISIONS.get(pv.get("decision"), pv.get("decision") or "")
    story.append(_table([[Paragraph(f"<b>{escape(decision)}</b>", S["banner_title"])]], [174 * mm],
                        style_extras=[
                            ("BACKGROUND", (0, 0), (-1, -1), P["main"] if pv.get("decision") != "refus" else colors.HexColor("#B91C1C")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                            ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9)]))
    story.append(Spacer(1, 12))

    # Réserves
    reserves = pv.get("reserves") or []
    story.append(Paragraph(f"Réserves ({len(reserves)})", S["h2"]))
    if not reserves:
        story.append(Paragraph("Aucune réserve n'a été formulée lors de la réception.", S["body"]))
    else:
        rows = [["N°", "Lot", "Description"]]
        for i, r in enumerate(reserves, 1):
            rows.append([str(i), escape(r.get("lot") or "—"),
                         Paragraph(escape(r.get("description") or ""), S["body"])])
        story.append(_table(rows, [12 * mm, 34 * mm, 128 * mm], style_extras=[
            ("BACKGROUND", (0, 0), (-1, 0), P["head"]),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("VALIGN", (0, 1), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, P["soft"]]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story.append(Spacer(1, 12))

    if pv.get("notes"):
        story.append(Paragraph("Observations", S["h2"]))
        story.append(Paragraph(escape(pv["notes"]).replace("\n", "<br/>"), S["body"]))
        story.append(Spacer(1, 12))

    # Signatures
    pro_sig = pv.get("pro_signature") or {}
    cli_sig = pv.get("client_signature") or {}
    pro_cell = [Paragraph("<b>Pour l'entreprise</b>", S["body"])]
    if pro_sig.get("name"):
        pro_cell.append(Paragraph(f"Signé : {escape(pro_sig['name'])}", S["muted"]))
        pro_cell.append(Paragraph(f"Le {pro_sig.get('at', '')[:10]}", S["muted"]))
    else:
        pro_cell.append(Paragraph("Date et signature :", S["muted"]))
    cli_cell = [Paragraph("<b>Pour le maître d'ouvrage</b>", S["body"])]
    if cli_sig.get("name"):
        cli_cell.append(Paragraph(f"Signé : {escape(cli_sig['name'])}", S["muted"]))
        cli_cell.append(Paragraph(f"Le {cli_sig.get('at', '')[:10]} · en ligne", S["muted"]))
    else:
        cli_cell.append(Paragraph("Date et signature :", S["muted"]))
    story.append(_table([[pro_cell, cli_cell]], [87 * mm, 87 * mm], style_extras=[
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (0, -1), 0.6, P["line"]), ("BOX", (1, 0), (1, -1), 0.6, P["line"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10), ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 22)]))

    def _on_page(canvas, d):
        _page_footer(canvas, d, branding, P, L)

    pdf.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()
