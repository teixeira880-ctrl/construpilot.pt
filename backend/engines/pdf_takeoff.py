"""Génération du PDF de MÉTRÉ ConstruPilot PLAN."""
from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                               KeepTogether, PageBreak)

ORANGE = colors.HexColor('#FF5A00')
DARK = colors.HexColor('#0A0D14')
GREY = colors.HexColor('#64748B')
LIGHT_GREY = colors.HexColor('#F1F5F9')


def _fmt(v, unit=""):
    if isinstance(v, (int, float)):
        return f"{v:,.2f} {unit}".replace(",", " ").replace(".", ",").strip()
    return str(v)


def _styles():
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=ss["Heading1"], textColor=DARK,
                              fontName="Helvetica-Bold", fontSize=22, leading=26,
                              spaceAfter=6),
        "h2": ParagraphStyle("h2", parent=ss["Heading2"], textColor=ORANGE,
                              fontName="Helvetica-Bold", fontSize=13, leading=16,
                              spaceBefore=14, spaceAfter=6),
        "kicker": ParagraphStyle("k", textColor=ORANGE, fontName="Helvetica-Bold",
                                  fontSize=9, letterSpacing=1.5, spaceAfter=2),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontSize=9,
                                leading=12, textColor=DARK),
        "muted": ParagraphStyle("mu", parent=ss["BodyText"], fontSize=8, leading=11,
                                 textColor=GREY),
    }


def build_takeoff_pdf(plan: dict, takeoff: dict, materials: dict | None = None,
                       branding: dict | None = None) -> bytes:
    """Rend un PDF de métré à partir d'un plan (rooms + totals + levels).

    `branding` optionnel : {"company_name": str, "contact_line": str, "logo_b64": str}
    """
    from reportlab.platypus import Image as RLImage
    import base64 as b64lib
    from io import BytesIO as BIO
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=18*mm, bottomMargin=18*mm)
    S = _styles()
    story = []

    # ---- Header branding (logo + société) ----
    if branding and (branding.get("company_name") or branding.get("logo_b64")):
        header_cells = []
        if branding.get("logo_b64"):
            try:
                logo_bytes = b64lib.b64decode(branding["logo_b64"].split(",")[-1])
                logo_img = RLImage(BIO(logo_bytes), width=32*mm, height=32*mm,
                                    kind="proportional")
                header_cells.append(logo_img)
            except Exception:
                header_cells.append("")
        else:
            header_cells.append("")
        info_lines = []
        if branding.get("company_name"):
            info_lines.append(Paragraph(f"<b>{branding['company_name']}</b>",
                                         S["body"]))
        if branding.get("contact_line"):
            info_lines.append(Paragraph(branding["contact_line"], S["muted"]))
        header_cells.append(info_lines)
        t = Table([header_cells], colWidths=[35*mm, None])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(t)
        story.append(Spacer(1, 6))

    # ---- Header ConstruPilot ----
    story.append(Paragraph("MÉTRÉ CONSTRUPILOT", S["kicker"]))
    title = plan.get("filename") or "Plan"
    story.append(Paragraph(title, S["h1"]))
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    story.append(Paragraph(
        f"Plan ID <b>{plan.get('plan_id','?')}</b> · {plan.get('page_count', 1)} page(s) · "
        f"{takeoff.get('room_count', 0)} pièces · généré le {date_str}", S["muted"]))
    story.append(Spacer(1, 10))

    # ---- Totaux globaux ----
    tots = takeoff.get("totals", {})
    story.append(Paragraph("Totaux globaux", S["h2"]))
    data = [
        ["Sol", _fmt(tots.get("floor_m2", 0), "m²")],
        ["Plafonds", _fmt(tots.get("ceiling_m2", 0), "m²")],
        ["Murs bruts", _fmt(tots.get("walls_gross_m2", 0), "m²")],
        ["Murs nets", _fmt(tots.get("walls_net_m2", 0), "m²")],
        ["Périmètre total", _fmt(tots.get("perimeter_m", 0), "m")],
    ]
    t = Table(data, colWidths=[60*mm, 40*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # ---- Par niveau ----
    levels = takeoff.get("levels", [])
    if len(levels) > 1:
        story.append(Paragraph("Totaux par niveau", S["h2"]))
        rows = [["Niveau", "Pièces", "Sol", "Murs nets", "Périmètre"]]
        for lvl in levels:
            lt = lvl.get("totals", {})
            rows.append([lvl.get("level_label", "—"),
                         str(len(lvl.get("rooms", []))),
                         _fmt(lt.get("floor_m2", 0), "m²"),
                         _fmt(lt.get("walls_net_m2", 0), "m²"),
                         _fmt(lt.get("perimeter_m", 0), "m")])
        t = Table(rows, colWidths=[35*mm, 20*mm, 30*mm, 30*mm, 30*mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.4, GREY),
            ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ]))
        story.append(t)

    # ---- Détail pièces ----
    rooms = takeoff.get("rooms", [])
    if rooms:
        story.append(Paragraph("Détail par pièce", S["h2"]))
        rows = [["Pièce", "Surface", "Périmètre", "Murs bruts", "Murs nets", "H."]]
        for r in rooms:
            rows.append([r.get("name", "—"),
                         _fmt(r.get("surface_m2", 0), "m²"),
                         _fmt(r.get("perimeter_m", 0), "m"),
                         _fmt(r.get("wall_area_gross_m2", 0), "m²"),
                         _fmt(r.get("wall_area_net_m2", 0), "m²"),
                         _fmt(r.get("ceiling_height_m", 2.5), "m")])
        t = Table(rows, colWidths=[45*mm, 24*mm, 24*mm, 27*mm, 27*mm, 15*mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.4, GREY),
            ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ]))
        story.append(t)

    # ---- Matériaux (optionnel) ----
    if materials:
        story.append(PageBreak())
        story.append(Paragraph("Quantitatif matériaux", S["h2"]))
        rows = [["Matériau", "Quantité"]]
        for section in ("floor", "paint", "placo", "skirting"):
            m = materials.get(section)
            if not m:
                continue
            if section == "floor":
                rows.append([f"Sol ({m.get('material','?')}) — surface + pertes",
                             _fmt(m.get("quantity_m2", 0), "m²")])
            elif section == "paint":
                rows.append([f"Peinture ({m.get('coats',2)} couches, marge {m.get('margin_pct',15)}%)",
                             _fmt(m.get("liters_recommended", 0), "L")])
            elif section == "placo":
                rows.append(["Plaques BA13 (pertes 5%)",
                             _fmt(m.get("plates", 0), "plaques")])
            elif section == "skirting":
                rows.append(["Plinthes (périmètre - portes + pertes)",
                             _fmt(m.get("quantity_m", 0), "m")])
        if len(rows) > 1:
            t = Table(rows, colWidths=[110*mm, 45*mm], repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("BOX", (0, 0), (-1, -1), 0.4, GREY),
                ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
            ]))
            story.append(t)

    # ---- Footer ----
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Métré généré par <b>ConstruPilot</b> — Estimez. Comparez. Construisez. "
        "<br/>Estimations indicatives — ne constituent pas un devis contractuel.",
        S["muted"]))

    doc.build(story)
    return buf.getvalue()


# ============ DEVIS (Full quote PDF) ============

def build_quote_pdf(quote: dict, branding: dict | None = None,
                    signature: dict | None = None) -> bytes:
    """Rend un PDF Devis à partir d'un quote (line_items + totaux)."""
    from reportlab.platypus import Image as RLImage
    import base64 as b64lib
    from io import BytesIO as BIO
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=18*mm, bottomMargin=18*mm)
    S = _styles()
    story = []

    # ---- Header branding ----
    if branding and (branding.get("company_name") or branding.get("logo_b64")):
        header_cells = []
        if branding.get("logo_b64"):
            try:
                logo_bytes = b64lib.b64decode(branding["logo_b64"].split(",")[-1])
                logo_img = RLImage(BIO(logo_bytes), width=32*mm, height=32*mm,
                                    kind="proportional")
                header_cells.append(logo_img)
            except Exception:
                header_cells.append("")
        else:
            header_cells.append("")
        info_lines = []
        if branding.get("company_name"):
            info_lines.append(Paragraph(f"<b>{branding['company_name']}</b>", S["body"]))
        if branding.get("contact_line"):
            info_lines.append(Paragraph(branding["contact_line"], S["muted"]))
        header_cells.append(info_lines)
        t = Table([header_cells], colWidths=[35*mm, None])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(t)
        story.append(Spacer(1, 6))

    # ---- Title ----
    story.append(Paragraph("DEVIS ESTIMATIF CONSTRUPILOT", S["kicker"]))
    story.append(Paragraph(quote.get("filename") or "Devis travaux", S["h1"]))
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    finish_label = {"eco": "Éco", "std": "Standard", "premium": "Premium"}.get(
        quote.get("finish", "std"), "Standard")
    story.append(Paragraph(
        f"Plan <b>{quote.get('plan_id','?')}</b> · Gamme <b>{finish_label}</b> · "
        f"Sol : <b>{quote.get('floor_material','').capitalize()}</b> · généré le {date_str}",
        S["muted"]))
    story.append(Spacer(1, 10))

    # ---- Totaux surfaces ----
    tots = quote.get("totals", {})
    story.append(Paragraph("Surfaces mesurées", S["h2"]))
    surf_data = [
        ["Sol", _fmt(tots.get("floor_m2", 0), "m²")],
        ["Plafonds", _fmt(tots.get("ceiling_m2", 0), "m²")],
        ["Murs nets", _fmt(tots.get("walls_net_m2", 0), "m²")],
        ["Périmètre", _fmt(tots.get("perimeter_m", 0), "m")],
    ]
    t = Table(surf_data, colWidths=[60*mm, 40*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # ---- Detail lignes ----
    story.append(Paragraph("Détail des postes", S["h2"]))
    rows = [["Désignation", "Qté", "Unit.", "Matériaux", "M.O.", "Total HT"]]
    for li in quote.get("line_items", []):
        rows.append([
            li["name"],
            _fmt(li["quantity"]),
            li["unit"],
            _fmt(li["material_total"], "€"),
            _fmt(li["labour_total"], "€"),
            _fmt(li["total"], "€"),
        ])
    t = Table(rows, colWidths=[70*mm, 18*mm, 14*mm, 25*mm, 22*mm, 25*mm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
    ]))
    story.append(t)

    # ---- Totaux ----
    story.append(Spacer(1, 12))
    story.append(Paragraph("Récapitulatif", S["h2"]))
    tva_pct = int(round(quote.get("tva_rate", 0.10) * 100))
    tot_rows = [
        ["Sous-total matériaux", _fmt(quote.get("subtotal_material", 0), "€")],
        ["Sous-total main d'œuvre", _fmt(quote.get("subtotal_labour", 0), "€")],
        ["Sous-total HT", _fmt(quote.get("subtotal_ht", 0), "€")],
        [f"TVA {tva_pct} %", _fmt(quote.get("tva", 0), "€")],
        ["TOTAL TTC", _fmt(quote.get("total_ttc", 0), "€")],
    ]
    t = Table(tot_rows, colWidths=[110*mm, 45*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("BACKGROUND", (0, -1), (-1, -1), ORANGE),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    # ---- Signature block (si présent) ----
    if signature and signature.get("b64"):
        from reportlab.platypus import Image as RLImage
        from io import BytesIO as BIO
        import base64 as b64lib
        story.append(Spacer(1, 18))
        story.append(Paragraph("Bon pour accord — Signature client", S["h2"]))
        sig_img = None
        try:
            sig_bytes = b64lib.b64decode(signature["b64"])
            sig_img = RLImage(BIO(sig_bytes), width=60*mm, height=25*mm,
                              kind="proportional")
        except Exception:
            sig_img = ""
        signed_at = signature.get("at") or ""
        signed_date = signed_at[:10] if signed_at else ""
        info = [
            Paragraph(f"<b>Signataire :</b> {signature.get('name') or ''}", S["body"]),
            Paragraph(f"<b>Email :</b> {signature.get('client_email') or ''}", S["body"]),
            Paragraph(f"<b>Signé le :</b> {signed_date}", S["body"]),
        ]
        sig_table = Table([[sig_img, info]], colWidths=[70*mm, None])
        sig_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOX", (0, 0), (-1, -1), 0.6, ORANGE),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7EC")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ]))
        story.append(sig_table)

    # ---- Footer ----
    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Devis <b>estimatif</b> généré par ConstruPilot à partir de votre plan métré. "
        "Prix moyens France 2026 (base de référence + main d'œuvre). "
        "TVA à 10 % applicable en rénovation logement de plus de 2 ans. "
        "Ce document ne constitue pas un devis contractuel : demandez plusieurs devis "
        "artisans pour comparer.", S["muted"]))

    doc.build(story)
    return buf.getvalue()


# ============ MULTI-PLAN PROJECT PDF ============

def build_project_quote_pdf(project: dict, branding: dict | None = None) -> bytes:
    """PDF Devis Projet consolidant plusieurs plans (multi-niveaux, extensions…)."""
    from reportlab.platypus import Image as RLImage, PageBreak
    import base64 as b64lib
    from io import BytesIO as BIO
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=18*mm, bottomMargin=18*mm)
    S = _styles()
    story = []

    # ---- Header branding ----
    if branding and (branding.get("company_name") or branding.get("logo_b64")):
        header_cells = []
        if branding.get("logo_b64"):
            try:
                logo_bytes = b64lib.b64decode(branding["logo_b64"].split(",")[-1])
                header_cells.append(RLImage(BIO(logo_bytes), width=32*mm, height=32*mm,
                                             kind="proportional"))
            except Exception:
                header_cells.append("")
        else:
            header_cells.append("")
        info_lines = []
        if branding.get("company_name"):
            info_lines.append(Paragraph(f"<b>{branding['company_name']}</b>", S["body"]))
        if branding.get("contact_line"):
            info_lines.append(Paragraph(branding["contact_line"], S["muted"]))
        header_cells.append(info_lines)
        t = Table([header_cells], colWidths=[35*mm, None])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(t)
        story.append(Spacer(1, 6))

    # ---- Title ----
    story.append(Paragraph("DEVIS PROJET CONSOLIDÉ", S["kicker"]))
    story.append(Paragraph(project.get("project_name") or "Projet ConstruPilot", S["h1"]))
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    finish_label = {"eco": "Éco", "std": "Standard",
                    "premium": "Premium"}.get(project.get("finish", "std"), "Standard")
    story.append(Paragraph(
        f"<b>{project.get('plan_count', 0)} plans</b> · Gamme <b>{finish_label}</b> · "
        f"généré le {date_str}", S["muted"]))
    story.append(Spacer(1, 12))

    # ---- Surfaces globales ----
    tots = project.get("totals", {})
    story.append(Paragraph("Surfaces totales du projet", S["h2"]))
    surf_data = [
        ["Sol total", _fmt(tots.get("floor_m2", 0), "m²")],
        ["Plafonds total", _fmt(tots.get("ceiling_m2", 0), "m²")],
        ["Murs nets total", _fmt(tots.get("walls_net_m2", 0), "m²")],
        ["Périmètre total", _fmt(tots.get("perimeter_m", 0), "m")],
    ]
    t = Table(surf_data, colWidths=[60*mm, 40*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    story.append(t)
    story.append(Spacer(1, 14))

    # ---- Détail par plan ----
    for i, sq in enumerate(project.get("sub_quotes", []), 1):
        story.append(Paragraph(f"Plan {i} : {sq.get('filename', 'Sans nom')}", S["h2"]))
        story.append(Paragraph(
            f"Sol {sq['totals']['floor_m2']} m² · Murs nets "
            f"{sq['totals']['walls_net_m2']} m² · Périmètre "
            f"{sq['totals']['perimeter_m']} m", S["muted"]))
        rows = [["Désignation", "Qté", "Unit.", "Total HT"]]
        for li in sq.get("line_items", []):
            rows.append([li["name"], _fmt(li["quantity"]), li["unit"],
                         _fmt(li["total"], "€")])
        rows.append(["", "", "TOTAL HT plan", _fmt(sq.get("subtotal_ht", 0), "€")])
        t = Table(rows, colWidths=[85*mm, 20*mm, 20*mm, 30*mm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), DARK),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, -1), (-1, -1), LIGHT_GREY),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.4, GREY),
            ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

    # ---- Récap projet ----
    story.append(Spacer(1, 8))
    story.append(Paragraph("Récapitulatif projet", S["h2"]))
    tva_pct = int(round(project.get("tva_rate", 0.10) * 100))
    tot_rows = [
        ["Sous-total matériaux", _fmt(project.get("subtotal_material", 0), "€")],
        ["Sous-total main d'œuvre", _fmt(project.get("subtotal_labour", 0), "€")],
        ["Sous-total HT", _fmt(project.get("subtotal_ht", 0), "€")],
        [f"TVA {tva_pct} %", _fmt(project.get("tva", 0), "€")],
        ["TOTAL PROJET TTC", _fmt(project.get("total_ttc", 0), "€")],
    ]
    t = Table(tot_rows, colWidths=[110*mm, 45*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("BACKGROUND", (0, -1), (-1, -1), ORANGE),
        ("TEXTCOLOR", (0, -1), (-1, -1), colors.white),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    story.append(Spacer(1, 18))
    story.append(Paragraph(
        "Devis <b>projet consolidé</b> généré par ConstruPilot à partir de plusieurs "
        "plans mesurés. Prix moyens France 2026. TVA à 10 % applicable en rénovation "
        "logement de plus de 2 ans. Document estimatif non contractuel.", S["muted"]))

    doc.build(story)
    return buf.getvalue()
