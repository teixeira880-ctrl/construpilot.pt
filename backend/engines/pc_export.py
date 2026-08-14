"""Exports PDF + Word (docx) de l'étude Permis de Construire (gros œuvre)."""
from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from engines.pdf_takeoff import (_fmt, _styles, _table, _story_header_branding,
                                 _story_footer, ORANGE, DARK, LIGHT_GREY)
from reportlab.lib import colors


def _hypotheses_rows(study: dict) -> list[list[str]]:
    i = study.get("inputs", {})
    src = study.get("input_sources", {})
    return [
        ["Hypothèse", "Valeur", "Source"],
        ["Niveaux", str(i.get("levels")), src.get("levels", "")],
        ["Surface plancher", _fmt(i.get("surface_m2"), "m²"), src.get("surface_m2", "")],
        ["Hauteur murs", _fmt(i.get("wall_height_m"), "m"), src.get("wall_height_m", "")],
        ["Périmètre extérieur", _fmt(i.get("perimeter_m"), "m"), src.get("perimeter_m", "")],
        ["Refends porteurs", _fmt(i.get("refends_m"), "m"), src.get("refends_m", "")],
        ["Ouvertures", f"{i.get('openings_count')} u · {_fmt(i.get('openings_area_m2'), 'm²')}", "PC (IA) / estimé"],
        ["Escaliers", str(i.get("stairs_count")), "PC (IA) / estimé"],
    ]


RULES_TEXT = ("Règles fixes appliquées : semelles filantes 60 × 30 cm (périmètre + refends "
              "porteurs) · dalle/plancher ép. 15 cm · murs brique isobrique ép. 20 cm · "
              "escalier béton armé · aciers : semelles 3+3 HA10 + cadres HA6 (15 kg/ml), "
              "dalle ST25C + chapeaux (14 kg/m²), escalier 100 kg/m³, chaînages 4 HA10 (3,6 kg/ml).")


def build_pc_pdf(plan: dict, study: dict, branding: dict | None = None) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    S = _styles()
    story: list = []
    _story_header_branding(story, branding, S)
    story.append(Paragraph("ÉTUDE PERMIS DE CONSTRUIRE — GROS ŒUVRE", S["kicker"]))
    story.append(Paragraph(plan.get("filename") or "Permis de construire", S["h1"]))
    story.append(Paragraph(f"Générée le {str(study.get('generated_at') or '')[:10]}"
                           f" · confiance IA {round(float(study.get('confidence') or 0) * 100)} %",
                           S["muted"]))

    if study.get("demandes"):
        story.append(Paragraph("Ce que demande le permis", S["h2"]))
        for d in study["demandes"][:10]:
            story.append(Paragraph(f"• {d}", S["body"]))

    story.append(Paragraph("Hypothèses de chiffrage", S["h2"]))
    story.append(_table(_hypotheses_rows(study), [55 * mm, 60 * mm, 45 * mm],
                        [("BACKGROUND", (0, 0), (-1, 0), DARK),
                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(RULES_TEXT, S["muted"]))

    for lot in study.get("lots", []):
        story.append(Paragraph(lot["lot"], S["h2"]))
        rows = [["Désignation", "U", "Qté", "PU mat.", "PU MO", "Total HT"]]
        for ln in lot["lines"]:
            rows.append([Paragraph(f"<b>{ln['designation']}</b><br/>"
                                   f"<font size=7 color='#64748B'>{ln['detail']}</font>", S["body"]),
                         ln["unit"], _fmt(ln["qty"]), _fmt(ln["pu_mat"], "€"),
                         _fmt(ln["pu_mo"], "€"), _fmt(ln["total"], "€")])
        story.append(_table(rows, [82 * mm, 10 * mm, 18 * mm, 20 * mm, 20 * mm, 24 * mm],
                            [("BACKGROUND", (0, 0), (-1, 0), DARK),
                             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                             ("FONTSIZE", (0, 0), (-1, -1), 8),
                             ("ALIGN", (2, 1), (-1, -1), "RIGHT")], repeat_rows=1))

    t = study.get("totals", {})
    story.append(Paragraph("Récapitulatif", S["h2"]))
    story.append(_table([
        ["Béton total", _fmt(t.get("beton_m3"), "m³"),
         "Aciers total", _fmt(t.get("acier_kg"), "kg", 0)],
        ["Briques isobrique", _fmt(t.get("briques_u"), "u", 0),
         "Semelles filantes", _fmt(t.get("semelles_ml"), "ml")],
        ["Total HT", _fmt(t.get("ht"), "€"),
         f"TVA {round(float(t.get('tva_rate') or 0.2) * 100)} %", _fmt(t.get("tva"), "€")],
        ["TOTAL TTC", _fmt(t.get("ttc"), "€"), "", ""],
    ], [45 * mm, 42 * mm, 45 * mm, 42 * mm],
        [("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
         ("FONTSIZE", (0, 0), (-1, -1), 9),
         ("TEXTCOLOR", (0, 3), (1, 3), ORANGE),
         ("FONTNAME", (0, 3), (1, 3), "Helvetica-Bold")]))

    if study.get("warnings"):
        story.append(Paragraph("Avertissements IA", S["h2"]))
        for w in study["warnings"][:8]:
            story.append(Paragraph(f"• {w}", S["muted"]))
    _story_footer(story, S)
    doc.build(story)
    return buf.getvalue()


def build_pc_docx(plan: dict, study: dict, branding: dict | None = None) -> bytes:
    """Export Word (.docx) de l'étude PC — même contenu que le PDF."""
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    if branding and branding.get("company_name"):
        p = doc.add_paragraph()
        run = p.add_run(branding["company_name"])
        run.bold = True
        if branding.get("contact_line"):
            p.add_run("\n" + branding["contact_line"]).font.size = Pt(8)

    h = doc.add_heading("Étude Permis de Construire — Gros Œuvre", level=0)
    for run in h.runs:
        run.font.color.rgb = RGBColor(0xFF, 0x5A, 0x00)
    doc.add_paragraph(f"{plan.get('filename') or 'Permis de construire'} — "
                      f"générée le {str(study.get('generated_at') or '')[:10]} · "
                      f"confiance IA {round(float(study.get('confidence') or 0) * 100)} %")

    if study.get("demandes"):
        doc.add_heading("Ce que demande le permis", level=1)
        for d in study["demandes"][:10]:
            doc.add_paragraph(d, style="List Bullet")

    doc.add_heading("Hypothèses de chiffrage", level=1)
    rows = _hypotheses_rows(study)
    tbl = doc.add_table(rows=len(rows), cols=3)
    tbl.style = "Light Grid Accent 1"
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            tbl.rows[r_idx].cells[c_idx].text = str(val)
    doc.add_paragraph(RULES_TEXT).runs[0].font.size = Pt(8)

    for lot in study.get("lots", []):
        doc.add_heading(lot["lot"], level=1)
        tbl = doc.add_table(rows=1 + len(lot["lines"]), cols=6)
        tbl.style = "Light Grid Accent 1"
        hdr = ["Désignation", "U", "Qté", "PU mat. €", "PU MO €", "Total HT €"]
        for c, v in enumerate(hdr):
            tbl.rows[0].cells[c].text = v
        for r, ln in enumerate(lot["lines"], start=1):
            cells = tbl.rows[r].cells
            cells[0].text = f"{ln['designation']}\n{ln['detail']}"
            cells[1].text = ln["unit"]
            cells[2].text = _fmt(ln["qty"])
            cells[3].text = _fmt(ln["pu_mat"])
            cells[4].text = _fmt(ln["pu_mo"])
            cells[5].text = _fmt(ln["total"])

    t = study.get("totals", {})
    doc.add_heading("Récapitulatif", level=1)
    recap = doc.add_table(rows=4, cols=2)
    recap.style = "Light Grid Accent 1"
    data = [("Béton total", _fmt(t.get("beton_m3"), "m³")),
            ("Aciers total", _fmt(t.get("acier_kg"), "kg", 0)),
            (f"Total HT / TVA {round(float(t.get('tva_rate') or 0.2) * 100)} %",
             f"{_fmt(t.get('ht'), '€')} / {_fmt(t.get('tva'), '€')}"),
            ("TOTAL TTC", _fmt(t.get("ttc"), "€"))]
    for r_idx, (k, v) in enumerate(data):
        recap.rows[r_idx].cells[0].text = k
        recap.rows[r_idx].cells[1].text = v

    if study.get("warnings"):
        doc.add_heading("Avertissements IA", level=1)
        for w in study["warnings"][:8]:
            doc.add_paragraph(w, style="List Bullet")

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
