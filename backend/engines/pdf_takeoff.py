"""Génération du PDF de MÉTRÉ ConstruPilot PLAN."""
from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                               PageBreak)

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


# ============ TAKEOFF PDF HELPERS ============
# Each helper appends to `story` (mutates in place) — keeps the main builder flat.

def _table(rows, col_widths, style_extras=None, repeat_rows=0):
    """Small helper: build a Table with default border style + optional extras."""
    t = Table(rows, colWidths=col_widths,
              repeatRows=repeat_rows) if repeat_rows else Table(rows, colWidths=col_widths)
    base_style = [
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    t.setStyle(TableStyle(base_style + (style_extras or [])))
    return t


def _decode_brand_logo(logo_b64_str: str, size_mm: float = 32):
    """Try to decode a b64 logo into a ReportLab Image; return None on failure."""
    from reportlab.platypus import Image as RLImage
    import base64 as b64lib
    from io import BytesIO as BIO
    try:
        logo_bytes = b64lib.b64decode(logo_b64_str.split(",")[-1])
        return RLImage(BIO(logo_bytes), width=size_mm * mm, height=size_mm * mm,
                       kind="proportional")
    except Exception:
        return None


def _story_header_branding(story: list, branding: dict | None, S: dict) -> None:
    """Section 1 — logo + company + contact line."""
    if not branding or not (branding.get("company_name") or branding.get("logo_b64")):
        return
    logo_cell = _decode_brand_logo(branding["logo_b64"]) if branding.get("logo_b64") else None
    info_lines = []
    if branding.get("company_name"):
        info_lines.append(Paragraph(f"<b>{branding['company_name']}</b>", S["body"]))
    if branding.get("contact_line"):
        info_lines.append(Paragraph(branding["contact_line"], S["muted"]))
    t = Table([[logo_cell or "", info_lines]], colWidths=[35 * mm, None])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(t)
    story.append(Spacer(1, 6))


def _story_takeoff_title(story: list, plan: dict, takeoff: dict, S: dict) -> None:
    """Section 2 — main title + subtitle line."""
    story.append(Paragraph("MÉTRÉ CONSTRUPILOT", S["kicker"]))
    story.append(Paragraph(plan.get("filename") or "Plan", S["h1"]))
    date_str = datetime.now(timezone.utc).strftime("%d/%m/%Y")
    story.append(Paragraph(
        f"Plan ID <b>{plan.get('plan_id', '?')}</b> · {plan.get('page_count', 1)} page(s) · "
        f"{takeoff.get('room_count', 0)} pièces · généré le {date_str}", S["muted"]))
    story.append(Spacer(1, 10))


def _story_totals_global(story: list, totals: dict, S: dict) -> None:
    """Section 3 — global totals two-column table."""
    story.append(Paragraph("Totaux globaux", S["h2"]))
    data = [
        ["Sol", _fmt(totals.get("floor_m2", 0), "m²")],
        ["Plafonds", _fmt(totals.get("ceiling_m2", 0), "m²")],
        ["Murs bruts", _fmt(totals.get("walls_gross_m2", 0), "m²")],
        ["Murs nets", _fmt(totals.get("walls_net_m2", 0), "m²")],
        ["Périmètre total", _fmt(totals.get("perimeter_m", 0), "m")],
    ]
    story.append(_table(data, [60 * mm, 40 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))


def _story_totals_per_level(story: list, levels: list, S: dict) -> None:
    """Section 4 — per-level breakdown (only if >1 level)."""
    if len(levels) <= 1:
        return
    story.append(Paragraph("Totaux par niveau", S["h2"]))
    rows = [["Niveau", "Pièces", "Sol", "Murs nets", "Périmètre"]]
    for lvl in levels:
        lt = lvl.get("totals", {})
        rows.append([lvl.get("level_label", "—"),
                     str(len(lvl.get("rooms", []))),
                     _fmt(lt.get("floor_m2", 0), "m²"),
                     _fmt(lt.get("walls_net_m2", 0), "m²"),
                     _fmt(lt.get("perimeter_m", 0), "m")])
    story.append(_table(rows, [35 * mm, 20 * mm, 30 * mm, 30 * mm, 30 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ]))


def _story_rooms_detail(story: list, rooms: list, S: dict) -> None:
    """Section 5 — one-row-per-room detail table."""
    if not rooms:
        return
    story.append(Paragraph("Détail par pièce", S["h2"]))
    rows = [["Pièce", "Surface", "Périmètre", "Murs bruts", "Murs nets", "H."]]
    for r in rooms:
        rows.append([r.get("name", "—"),
                     _fmt(r.get("surface_m2", 0), "m²"),
                     _fmt(r.get("perimeter_m", 0), "m"),
                     _fmt(r.get("wall_area_gross_m2", 0), "m²"),
                     _fmt(r.get("wall_area_net_m2", 0), "m²"),
                     _fmt(r.get("ceiling_height_m", 2.5), "m")])
    story.append(_table(rows, [45 * mm, 24 * mm, 24 * mm, 27 * mm, 27 * mm, 15 * mm],
                        style_extras=[
                            ("BACKGROUND", (0, 0), (-1, 0), DARK),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
                        ], repeat_rows=1))


def _material_row(section: str, m: dict) -> list[str] | None:
    """Map (section, material meta) to a printable table row, or None to skip."""
    if section == "floor":
        return [f"Sol ({m.get('material', '?')}) — surface + pertes",
                _fmt(m.get("quantity_m2", 0), "m²")]
    if section == "paint":
        return [f"Peinture ({m.get('coats', 2)} couches, marge {m.get('margin_pct', 15)}%)",
                _fmt(m.get("liters_recommended", 0), "L")]
    if section == "placo":
        return ["Plaques BA13 (pertes 5%)", _fmt(m.get("plates", 0), "plaques")]
    if section == "skirting":
        return ["Plinthes (périmètre - portes + pertes)",
                _fmt(m.get("quantity_m", 0), "m")]
    return None


def _story_materials(story: list, materials: dict | None, S: dict) -> None:
    """Section 6 — materials breakdown (on a new page)."""
    if not materials:
        return
    story.append(PageBreak())
    story.append(Paragraph("Quantitatif matériaux", S["h2"]))
    rows = [["Matériau", "Quantité"]]
    for section in ("floor", "paint", "placo", "skirting"):
        row = _material_row(section, materials.get(section) or {})
        if row and materials.get(section):
            rows.append(row)
    if len(rows) == 1:
        return
    story.append(_table(rows, [110 * mm, 45 * mm], style_extras=[
        ("BACKGROUND", (0, 0), (-1, 0), ORANGE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
    ], repeat_rows=1))


def _story_footer(story: list, S: dict) -> None:
    """Section 7 — small legal disclaimer footer."""
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Métré généré par <b>ConstruPilot</b> — Estimez. Comparez. Construisez. "
        "<br/>Estimations indicatives — ne constituent pas un devis contractuel.",
        S["muted"]))


def build_takeoff_pdf(plan: dict, takeoff: dict, materials: dict | None = None,
                       branding: dict | None = None) -> bytes:
    """Rend un PDF de métré à partir d'un plan (rooms + totals + levels).

    `branding` optionnel : {"company_name": str, "contact_line": str, "logo_b64": str}

    Complexité maîtrisée : chaque section est déléguée à un helper `_story_*`.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm)
    S = _styles()
    story: list = []

    _story_header_branding(story, branding, S)
    _story_takeoff_title(story, plan, takeoff, S)
    _story_totals_global(story, takeoff.get("totals", {}), S)
    _story_totals_per_level(story, takeoff.get("levels", []), S)
    _story_rooms_detail(story, takeoff.get("rooms", []), S)
    _story_materials(story, materials, S)
    _story_footer(story, S)

    doc.build(story)
    return buf.getvalue()


# ============ DEVIS (Full quote PDF) ============

def build_quote_pdf(quote: dict, branding: dict | None = None,
                    signature: dict | None = None) -> bytes:
    """Rend un PDF Devis à partir d'un quote (line_items + totaux)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=18*mm, bottomMargin=18*mm)
    S = _styles()
    story: list = []

    # ---- Header branding (shared helper) ----
    _story_header_branding(story, branding, S)

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
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18*mm, rightMargin=18*mm,
                             topMargin=18*mm, bottomMargin=18*mm)
    S = _styles()
    story: list = []

    # ---- Header branding (shared helper) ----
    _story_header_branding(story, branding, S)

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



# ============ ATTESTATION TVA (Cerfa 1301-SD simplifié) ============

def build_tva_attestation_pdf(
    client_name: str,
    client_address: str,
    work_address: str,
    work_description: str,
    company_name: str = "",
    company_address: str = "",
    branding: dict | None = None,
    tva_rate: float = 0.10,
) -> bytes:
    """Attestation simplifiée du client (art. 279-0 bis CGI) : logement > 2 ans.

    À signer par le client puis à remettre à l'entreprise avant la facturation.
    Format libre inspiré du Cerfa 1301-SD. Ne remplace pas l'original si le
    client préfère.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=20*mm, rightMargin=20*mm,
                             topMargin=20*mm, bottomMargin=20*mm)
    S = _styles()
    story = []

    tva_pct = int(round(tva_rate * 100))
    is_reduced = tva_pct == 10 or tva_pct == 5 or tva_pct == 55  # 5.5 arrondi
    header_title = (f"ATTESTATION — TVA À TAUX RÉDUIT ({tva_pct} %)"
                     if is_reduced else "ATTESTATION TRAVAUX")
    story.append(Paragraph(header_title, S["kicker"]))
    story.append(Paragraph("Article 279-0 bis du Code Général des Impôts", S["h1"]))
    story.append(Paragraph(
        "Certificat à remettre à l'entreprise pour bénéficier du taux réduit de TVA "
        "sur les travaux réalisés dans un local à usage d'habitation achevé "
        "depuis plus de deux ans.", S["muted"]))
    story.append(Spacer(1, 12))

    # Client info
    story.append(Paragraph("Je soussigné(e)", S["h2"]))
    client_rows = [
        ["Nom / Prénom :", client_name or "………………………………………………"],
        ["Adresse (client) :", client_address or "………………………………………………"],
        ["Adresse des travaux :", work_address or "………………………………………………"],
    ]
    t = Table(client_rows, colWidths=[45*mm, 120*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 12))

    # Déclarations
    story.append(Paragraph("Certifie sur l'honneur que :", S["h2"]))
    story.append(Paragraph(
        "1. Le local dans lequel les travaux sont réalisés est <b>affecté à un "
        "usage d'habitation</b> (résidence principale ou secondaire).",
        S["body"]))
    story.append(Paragraph(
        "2. Le local est <b>achevé depuis plus de deux ans</b> à la date de "
        "démarrage des travaux.",
        S["body"]))
    story.append(Paragraph(
        "3. Les travaux réalisés ne concourent pas à la production d'un "
        "immeuble neuf, ni à une élévation de plus de 10 % de la surface de "
        "plancher.",
        S["body"]))
    story.append(Spacer(1, 12))

    # Description travaux
    story.append(Paragraph("Nature des travaux :", S["h2"]))
    story.append(Paragraph(work_description or "………………………………………………",
                            S["body"]))
    story.append(Spacer(1, 20))

    # Entreprise + Signature
    story.append(Paragraph("Entreprise réalisant les travaux :", S["h2"]))
    ent_rows = [
        ["Raison sociale :", company_name or "………………………………………………"],
        ["Adresse :", company_address or "………………………………………………"],
    ]
    t = Table(ent_rows, colWidths=[45*mm, 120*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT_GREY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.4, GREY),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, GREY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(t)
    story.append(Spacer(1, 20))

    story.append(Paragraph(
        "Fait à …………………………………………… le ……… / ……… / ………………",
        S["body"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Signature du client (précédée de « Bon pour accord ») :",
                            S["body"]))
    story.append(Spacer(1, 40))
    # Cadre signature
    sig_frame = Table([[""]], colWidths=[90*mm], rowHeights=[30*mm])
    sig_frame.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, GREY)]))
    story.append(sig_frame)
    story.append(Spacer(1, 12))

    # Footer légal
    story.append(Paragraph(
        "<b>Attention</b> : toute fausse déclaration engage la responsabilité du "
        "client. L'administration peut demander le paiement du complément de TVA "
        "correspondant à la différence entre le taux réduit et le taux normal. "
        "Conservez ce document 5 ans.", S["muted"]))

    doc.build(story)
    return buf.getvalue()
