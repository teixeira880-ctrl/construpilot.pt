"""Génération du PDF d'estimation ConstruPilot."""
from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                               KeepTogether)

ORANGE = colors.HexColor('#FF5A00')
DARK = colors.HexColor('#0A0D14')
GREY = colors.HexColor('#64748B')


def _money(v):
    return f"{v:,.2f} €".replace(",", " ").replace(".", ",").replace(" ", " ")


def build_estimation_pdf(project: dict, estimation: dict, planning: list, advice: str = "",
                         user: dict | None = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                           topMargin=16 * mm, bottomMargin=16 * mm,
                           title=f"Estimation ConstruPilot - {project.get('name', '')}")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=ss['Heading1'], textColor=DARK, fontSize=20, spaceAfter=4)
    h2 = ParagraphStyle('h2', parent=ss['Heading2'], textColor=ORANGE, fontSize=12,
                        spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle('body', parent=ss['BodyText'], fontSize=9, textColor=DARK, leading=13)
    small = ParagraphStyle('small', parent=ss['BodyText'], fontSize=8, textColor=GREY)

    story = []
    header = Table([[Paragraph("<b>ConstruPilot</b>", h1),
                     Paragraph("Votre expert travaux,<br/>de l'idée au chantier.", small)]],
                   colWidths=[100 * mm, 74 * mm])
    header.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                                ('LINEBELOW', (0, 0), (-1, 0), 2, ORANGE),
                                ('BOTTOMPADDING', (0, 0), (-1, 0), 8)]))
    story += [header, Spacer(1, 8)]

    story.append(Paragraph(f"Estimation de travaux — {project.get('name', 'Projet')}", h2))
    meta = [
        ["Type de projet", estimation.get('project_type_name', '-')],
        ["Surface", f"{estimation.get('surface', 0)} m²"],
        ["Niveau de finition", estimation.get('finish_level_name', '-')],
        ["Localisation", f"{project.get('city') or '-'} ({estimation.get('region') or estimation.get('country')})"],
        ["Type de bâtiment", (estimation.get('building_type') or '-').capitalize()],
        ["Date", datetime.now(timezone.utc).strftime('%d/%m/%Y')],
    ]
    if user:
        meta.append(["Client", f"{user.get('name', '')} — {user.get('email', '')}"])
    t = Table(meta, colWidths=[45 * mm, 129 * mm])
    t.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9),
                           ('TEXTCOLOR', (0, 0), (0, -1), GREY),
                           ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                           ('LINEBELOW', (0, 0), (-1, -2), 0.3, colors.HexColor('#E2E8F0'))]))
    story += [t]

    if project.get('description'):
        story += [Paragraph("Description des travaux", h2), Paragraph(project['description'], body)]

    story.append(Paragraph("Synthèse budgétaire", h2))
    tot = Table([["Prix minimum", "Prix moyen", "Prix maximum"],
                 [_money(estimation['total_min']), _money(estimation['total_avg']),
                  _money(estimation['total_max'])]], colWidths=[58 * mm] * 3)
    tot.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#FFF1E8')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, 1), 13), ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
    ]))
    story += [tot, Spacer(1, 8)]

    b = estimation['breakdown']
    br = Table([["Matériaux", _money(b['materials'])], ["Main-d'œuvre", _money(b['labour'])],
                ["Location de matériel", _money(b['equipment_rental'])],
                ["Déchets / évacuation", _money(b['waste_disposal'])],
                [f"Marge imprévus ({int(b['contingency_rate'] * 100)} %)", _money(b['contingency'])],
                ["Prix moyen au m²", f"{estimation['price_per_sqm']:.2f} €/m²"]],
               colWidths=[110 * mm, 64 * mm])
    br.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9), ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
                            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
                            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
    story += [br]

    story.append(Paragraph("Détail par lot", h2))
    rows = [["Lot", "Qté", "Unité", "Matériaux", "M.O.", "€/u", "Total", "Difficulté"]]
    for l in estimation['lots']:
        rows.append([l['name'], f"{l['quantity']:g}", l['unit'], _money(l['material_cost']),
                     _money(l['labour_cost']), f"{l['price_per_unit']:.2f}", _money(l['total']),
                     l['difficulty_label']])
    lt = Table(rows, colWidths=[36 * mm, 13 * mm, 12 * mm, 24 * mm, 24 * mm, 15 * mm, 26 * mm, 24 * mm],
               repeatRows=1)
    lt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7.2), ('ALIGN', (1, 1), (-2, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story += [lt]

    if planning:
        story.append(Paragraph("Planning estimatif", h2))
        prows = [["Semaine", "Lot", "Durée"]]
        for p in planning:
            prows.append([f"S{p['start_week']}" + (f" → S{p['end_week']}" if p['end_week'] != p['start_week'] else ""),
                          p['name'], f"{p['duration_weeks']} sem."])
        pt = Table(prows, colWidths=[30 * mm, 114 * mm, 30 * mm], repeatRows=1)
        pt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), DARK), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story += [pt, Paragraph(f"Durée totale estimée : {estimation['duration_weeks']} semaines "
                                f"({estimation['total_hours']:g} heures de main-d'œuvre).", small)]

    if advice:
        story.append(Paragraph("Recommandations ConstruPilot", h2))
        for line in advice.split("\n"):
            line = line.strip().lstrip("-•*").strip()
            if line:
                story.append(Paragraph(f"• {line}", body))

    story += [Spacer(1, 12), Paragraph(
        "Document généré automatiquement par ConstruPilot. Estimation indicative fondée sur des prix de "
        "référence régionaux, ne constituant pas un devis contractuel. Pour une proposition ferme, "
        "demandez une intervention ConstruPilot depuis l'application.", small)]

    doc.build(story)
    return buf.getvalue()
