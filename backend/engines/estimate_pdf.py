"""PDF « Estimation budgétaire indicative » (particulier) — brandé ConstruPilot, FR/PT."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engines.pdf_takeoff import DARK, GREY, LIGHT_GREY, ORANGE, _styles
from engines.plan_cotes_pdf import _e

_W = A4[0] - 32 * mm
GREEN = colors.HexColor("#16a34a")
AMBER = colors.HexColor("#d97706")

T = {
    "fr": {"kicker": "ESTIMATION BUDGÉTAIRE INDICATIVE", "title": "Fourchette de budget travaux", "low": "Prix bas", "central": "Central", "high": "Prix haut",
           "range": "Amplitude", "finish": "Niveau de finition", "region": "Région de référence", "source": "Source des prix", "date": "Date des prix",
           "conf": "Confiance", "incl": "Inclus dans l'estimation", "excl": "Non inclus", "assum": "Hypothèses retenues", "unc": "Facteurs d'incertitude",
           "missing": "Informations manquantes", "questions": "Questions à poser aux entreprises consultées", "notice": "Mention obligatoire",
           "gen": "Généré le", "foot": "ConstruPilot.fr · Estimation indicative — ne constitue pas un devis", "ref": "Référence"},
    "pt": {"kicker": "ESTIMATIVA ORÇAMENTAL INDICATIVA", "title": "Intervalo de orçamento de obras", "low": "Preço baixo", "central": "Central", "high": "Preço alto",
           "range": "Amplitude", "finish": "Nível de acabamento", "region": "Região de referência", "source": "Fonte dos preços", "date": "Data dos preços",
           "conf": "Confiança", "incl": "Incluído na estimativa", "excl": "Não incluído", "assum": "Hipóteses consideradas", "unc": "Fatores de incerteza",
           "missing": "Informações em falta", "questions": "Perguntas a colocar às empresas consultadas", "notice": "Menção obrigatória",
           "gen": "Gerado em", "foot": "ConstruPilot.fr · Estimativa indicativa — não constitui um orçamento", "ref": "Referência"},
}


def _eur(v) -> str:
    return f"{float(v or 0):,.0f} €".replace(",", " ")


def _bullets(items, S):
    return [Paragraph(f"• {_e(str(x))}", S["body"]) for x in (items or [])] or [Paragraph("—", S["muted"])]


def build_estimate_pdf(est: dict, ref: str, lang: str = "fr") -> bytes:
    L = T["pt" if lang == "pt" else "fr"]
    S = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=L["title"], author="ConstruPilot")
    now = datetime.now(timezone.utc)
    story = [Paragraph("<font color='#FF5A00'><b>Constru</b></font><b>Pilot</b>", S["h1"]), Paragraph(L["kicker"], S["kicker"]),
             Paragraph(_e(est.get("project") or L["title"]), S["h2"]),
             Paragraph(f"{L['ref']} {ref} · {L['gen']} {now.strftime('%d/%m/%Y')}", S["muted"]), Spacer(1, 5 * mm)]
    cells = [[Paragraph(f"<font color='#64748B' size='7'>{L['low'].upper()}</font><br/><font size='15'><b>{_eur(est.get('low_estimate'))}</b></font>", S["body"]),
              Paragraph(f"<font color='#64748B' size='7'>{L['central'].upper()}</font><br/><font size='15'><b>{_eur(est.get('central_estimate'))}</b></font>", S["body"]),
              Paragraph(f"<font color='#64748B' size='7'>{L['high'].upper()}</font><br/><font size='15'><b>{_eur(est.get('high_estimate'))}</b></font>", S["body"])]]
    t = Table(cells, colWidths=[_W / 3] * 3, rowHeights=[22 * mm])
    t.setStyle(TableStyle([("BOX", (0, 0), (0, 0), 1, GREEN), ("BOX", (1, 0), (1, 0), 1, AMBER), ("BOX", (2, 0), (2, 0), 1, ORANGE),
                           ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8)]))
    story += [t, Spacer(1, 4 * mm)]
    meta = [[L["range"], f"{est.get('range_percentage')} %"], [L["finish"], est.get("finish_level") or "—"], [L["region"], est.get("reference_region") or "—"],
            [L["source"], Paragraph(_e(est.get("price_source") or "—"), S["body"])], [L["date"], est.get("price_date") or "—"],
            [L["conf"], f"{float(est.get('confidence') or 0):.0%}"]]
    mt = Table(meta, colWidths=[45 * mm, _W - 45 * mm])
    mt.setStyle(TableStyle([("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("TEXTCOLOR", (0, 0), (0, -1), GREY),
                            ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#E2E8F0")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [mt, Spacer(1, 4 * mm)]
    for key, items in (("incl", est.get("included_items")), ("excl", est.get("excluded_items")), ("assum", est.get("assumptions")),
                       ("unc", est.get("uncertainty_factors")), ("missing", est.get("missing_information")),
                       ("questions", est.get("recommended_questions_for_contractors"))):
        story += [Paragraph(L[key], S["h2"])] + _bullets(items, S)
    story += [Spacer(1, 5 * mm), Paragraph(L["notice"], S["kicker"])]
    box = Table([[Paragraph(_e(est.get("mandatory_notice") or ""), S["body"])]], colWidths=[_W])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, ORANGE), ("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
                             ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 6),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [box]

    def _footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"{L['foot']} · {ref} · {d.page}")
        canvas.setFillColor(ORANGE)
        canvas.rect(16 * mm, 9 * mm, 18 * mm, 1.2, fill=1, stroke=0)
        canvas.setFillColor(DARK)
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
