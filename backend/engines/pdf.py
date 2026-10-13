"""Génération du PDF d'estimation ConstruPilot.

Refactorisé (iter36) : `build_estimation_pdf` est un simple orchestrateur qui
délègue à 7 helpers privés (`_esti_*`) — chaque section est maintenant testable
et éditable indépendamment.
"""
from io import BytesIO
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)

ORANGE = colors.HexColor('#FF5A00')
DARK = colors.HexColor('#0A0D14')
GREY = colors.HexColor('#64748B')
LIGHT_ROW = colors.HexColor('#F8FAFC')
LINE_GREY = colors.HexColor('#E2E8F0')


def _money(v):
    return f"{v:,.2f} €".replace(",", " ").replace(".", ",").replace(" ", " ")


def _styles() -> dict:
    """Return a dict of paragraph styles used across all `_esti_*` helpers."""
    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle('h1', parent=ss['Heading1'], textColor=DARK,
                              fontSize=20, spaceAfter=4),
        "h2": ParagraphStyle('h2', parent=ss['Heading2'], textColor=ORANGE,
                              fontSize=12, spaceBefore=14, spaceAfter=6),
        "body": ParagraphStyle('body', parent=ss['BodyText'], fontSize=9,
                                 textColor=DARK, leading=13),
        "small": ParagraphStyle('small', parent=ss['BodyText'], fontSize=8,
                                 textColor=GREY),
    }


def _esti_header(story: list, S: dict) -> None:
    """Brand header : ConstruPilot title + tagline row."""
    header = Table([[Paragraph("<b>ConstruPilot</b>", S["h1"]),
                     Paragraph("O seu especialista em obras,<br/>da ideia à obra.", S["small"])]],
                    colWidths=[100 * mm, 74 * mm])
    header.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, 0), 2, ORANGE),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
    ]))
    story += [header, Spacer(1, 8)]


def _esti_project_meta(story: list, project: dict, estimation: dict,
                        user: dict | None, S: dict) -> None:
    """Project metadata : type, surface, finish, location, client…"""
    story.append(Paragraph(
        f"Estimativa de obras — {project.get('name', 'Projeto')}", S["h2"]))
    meta = [
        ["Tipo de projeto", estimation.get('project_type_name', '-')],
        ["Superfície", f"{estimation.get('surface', 0)} m²"],
        ["Nível de acabamento", estimation.get('finish_level_name', '-')],
        ["Localização",
         f"{project.get('city') or '-'} ({estimation.get('region') or estimation.get('country')})"],
        ["Tipo de edifício", (estimation.get('building_type') or '-').capitalize()],
        ["Data", datetime.now(timezone.utc).strftime('%d/%m/%Y')],
    ]
    if user:
        meta.append(["Cliente", f"{user.get('name', '')} — {user.get('email', '')}"])
    t = Table(meta, colWidths=[45 * mm, 129 * mm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), GREY),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, -2), 0.3, LINE_GREY),
    ]))
    story.append(t)


def _esti_description(story: list, project: dict, S: dict) -> None:
    """Free-text project description."""
    if not project.get('description'):
        return
    story += [Paragraph("Descrição dos trabalhos", S["h2"]),
              Paragraph(project['description'], S["body"])]


def _esti_totals(story: list, estimation: dict, S: dict) -> None:
    """Min / avg / max headline totals."""
    story.append(Paragraph("Síntese orçamental", S["h2"]))
    tot = Table([["Preço mínimo", "Preço médio", "Preço máximo"],
                 [_money(estimation['total_min']), _money(estimation['total_avg']),
                  _money(estimation['total_max'])]], colWidths=[58 * mm] * 3)
    tot.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (1, 1), (1, 1), colors.HexColor('#FFF1E8')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, 1), 13),
        ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('BOX', (0, 0), (-1, -1), 0.5, LINE_GREY),
    ]))
    story += [tot, Spacer(1, 8)]
    _vat = estimation.get("default_vat_rate")
    if _vat is not None:
        _avg = float(estimation.get("total_avg") or 0)
        _rate = float(_vat)
        _label = ("IVA reduzido — reabilitação (Verba 2.27 do CIVA)"
                  if estimation.get("vat_eligible_6") else "IVA — taxa normal")
        vt = Table([[f"{_label} — {_rate:.0f}%", _money(round(_avg * _rate / 100.0, 2))],
                    ["Total c/ IVA (preço médio)", _money(round(_avg * (1 + _rate / 100.0), 2))]],
                   colWidths=[110 * mm, 64 * mm])
        vt.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FFF1E8')),
            ('BOX', (0, 0), (-1, -1), 0.5, LINE_GREY),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story += [vt, Spacer(1, 8)]


def _esti_breakdown(story: list, estimation: dict) -> None:
    """Cost breakdown : materials / labour / rentals / waste / contingency / €/m²."""
    b = estimation['breakdown']
    br = Table([["Materiais", _money(b['materials'])],
                ["Outro", _money(b['labour'])],
                ["Aluguer de equipamento", _money(b['equipment_rental'])],
                ["Resíduos / evacuação", _money(b['waste_disposal'])],
                [f"Margem para imprevistos ({int(b['contingency_rate'] * 100)} %)", _money(b['contingency'])],
                ["Preço médio por m²", f"{estimation['price_per_sqm']:.2f} €/m²"]],
               colWidths=[110 * mm, 64 * mm])
    br.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, LIGHT_ROW]),
        ('BOX', (0, 0), (-1, -1), 0.5, LINE_GREY),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(br)


def _esti_lots(story: list, estimation: dict, S: dict) -> None:
    """Per-lot detail table (8 columns)."""
    story.append(Paragraph("Detalhe por especialidade", S["h2"]))
    rows = [["Lote", "Qtd.", "Un.", "Materiais", "M.O.", "€/u", "Total", "Dificuldade"]]
    for lot in estimation['lots']:
        rows.append([
            lot['name'], f"{lot['quantity']:g}", lot['unit'],
            _money(lot['material_cost']), _money(lot['labour_cost']),
            f"{lot['price_per_unit']:.2f}", _money(lot['total']),
            lot['difficulty_label'],
        ])
    lt = Table(rows,
               colWidths=[36 * mm, 13 * mm, 12 * mm, 24 * mm, 24 * mm, 15 * mm, 26 * mm, 24 * mm],
               repeatRows=1)
    lt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 7.2),
        ('ALIGN', (1, 1), (-2, -1), 'RIGHT'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_ROW]),
        ('GRID', (0, 0), (-1, -1), 0.25, LINE_GREY),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(lt)


def _esti_planning(story: list, planning: list, estimation: dict, S: dict) -> None:
    """Optional per-week planning table + total duration line."""
    if not planning:
        return
    story.append(Paragraph("Planeamento estimativo", S["h2"]))
    prows = [["Semana", "Lote", "Duração"]]
    for p in planning:
        week_range = f"S{p['start_week']}"
        if p['end_week'] != p['start_week']:
            week_range += f" → S{p['end_week']}"
        prows.append([week_range, p['name'], f"{p['duration_weeks']} sem."])
    pt = Table(prows, colWidths=[30 * mm, 114 * mm, 30 * mm], repeatRows=1)
    pt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), DARK),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_ROW]),
        ('GRID', (0, 0), (-1, -1), 0.25, LINE_GREY),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story += [pt, Paragraph(
        f"Duração total estimada: {estimation['duration_weeks']} semaines ({estimation['total_hours']:g} horas de mão de obra).", S["small"])]


def _esti_advice(story: list, advice: str, S: dict) -> None:
    """Optional AI-generated recommendations block."""
    if not advice:
        return
    story.append(Paragraph("Recomendações ConstruPilot", S["h2"]))
    for line in advice.split("\n"):
        line = line.strip().lstrip("-•*").strip()
        if line:
            story.append(Paragraph(f"• {line}", S["body"]))


def _esti_footer(story: list, S: dict) -> None:
    """Standard legal footer."""
    story += [Spacer(1, 12), Paragraph(
        "Documento gerado automaticamente pelo ConstruPilot. Estimativa indicativa baseada em preços de referência regionais, que não constitui um orçamento contratual. Para uma proposta firme, peça uma intervenção ConstruPilot a partir da aplicação.", S["small"])]


def build_estimation_pdf(project: dict, estimation: dict, planning: list, advice: str = "",
                          user: dict | None = None) -> bytes:
    """Génère le PDF d'estimation ConstruPilot en assemblant 9 helpers privés.

    Complexité maîtrisée : chaque section est déléguée à un helper `_esti_*`.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             leftMargin=18 * mm, rightMargin=18 * mm,
                             topMargin=16 * mm, bottomMargin=16 * mm,
                             title=f"Estimation ConstruPilot - {project.get('name', '')}")
    S = _styles()
    story: list = []

    _esti_header(story, S)
    _esti_project_meta(story, project, estimation, user, S)
    _esti_description(story, project, S)
    _esti_totals(story, estimation, S)
    _esti_breakdown(story, estimation)
    _esti_lots(story, estimation, S)
    _esti_planning(story, planning, estimation, S)
    _esti_advice(story, advice, S)
    _esti_footer(story, S)

    doc.build(story)
    return buf.getvalue()
