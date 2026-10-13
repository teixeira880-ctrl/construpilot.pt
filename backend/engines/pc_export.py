"""Exports PDF + Word (docx) de l'étude Permis de Construire (gros œuvre)."""
from __future__ import annotations

from io import BytesIO

from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

from engines.pc_study import schedule_with_dates
from engines.pdf_takeoff import (_fmt, _styles, _table, _story_header_branding,
                                 _story_footer, ORANGE, DARK, LIGHT_GREY)
from reportlab.lib import colors

GANTT_COLORS = [colors.HexColor(c) for c in
                ("#f59e0b", "#f97316", "#0ea5e9", "#10b981", "#8b5cf6")]


def _fr(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}"


def _fr_long(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}"


def _gantt_drawing(rows: list[dict], width: float = 178 * mm) -> Drawing:
    """Frise Gantt colorée : plein = jours ouvrés, translucide = séchage béton."""
    from datetime import date
    t0 = date.fromisoformat(rows[0]["work_start"]).toordinal()
    span = max(1, date.fromisoformat(rows[-1]["cure_end"]).toordinal() + 1 - t0)
    label_w, row_h = 80 * mm, 9 * mm
    bar_w = width - label_w
    h = row_h * len(rows) + 2 * mm
    d = Drawing(width, h)
    for idx, r in enumerate(rows):
        y = h - (idx + 1) * row_h + 2 * mm
        d.add(String(0, y + 3.6 * mm, r["name"][:58],
                     fontName="Helvetica-Bold", fontSize=6.3, fillColor=DARK))
        dates = f"{_fr(r['work_start'])} → {_fr(r['work_end'])}"
        if r["cure_days"]:
            dates += f" · séchage → {_fr(r['cure_end'])}"
        d.add(String(0, y - 0.6 * mm, dates, fontName="Helvetica", fontSize=5.6,
                     fillColor=colors.HexColor("#64748B")))
        ws = date.fromisoformat(r["work_start"]).toordinal()
        we = date.fromisoformat(r["work_end"]).toordinal() + 1
        ce = date.fromisoformat(r["cure_end"]).toordinal() + 1
        col = GANTT_COLORS[idx % len(GANTT_COLORS)]
        x0 = label_w + bar_w * (ws - t0) / span
        xw = max(1.5 * mm, bar_w * (we - ws) / span)
        d.add(Rect(x0, y, xw, 5 * mm, fillColor=col, strokeColor=None))
        if ce > we:
            d.add(Rect(x0 + xw, y, bar_w * (ce - we) / span, 5 * mm,
                       fillColor=colors.Color(col.red, col.green, col.blue, alpha=0.3),
                       strokeColor=None))
    return d


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


def build_pc_pdf(plan: dict, study: dict, branding: dict | None = None,
                 start_date: str | None = None) -> bytes:
    if study.get("schema_version") == "construction-dossier-1":
        from engines.study_dossier_pdf import build_dossier_pdf
        return build_dossier_pdf(plan, study, branding)
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
    lb = study.get("levels_breakdown") or []
    if lb:
        story.append(Paragraph("Quantités par niveau — pour phaser vos commandes", S["h2"]))
        rows = [["Niveau", "Béton", "Aciers", "Briques", "Murs", "Total HT"]]
        for l in lb:
            rows.append([l["name"], _fmt(l["beton_m3"], "m³"), _fmt(l["acier_kg"], "kg", 0),
                         _fmt(l["briques_u"], "u", 0) if l["briques_u"] else "—",
                         _fmt(l["murs_m2"], "m²") if l["murs_m2"] else "—",
                         _fmt(l["ht"], "€")])
        story.append(_table(rows, [34 * mm, 26 * mm, 26 * mm, 26 * mm, 26 * mm, 36 * mm],
                            [("BACKGROUND", (0, 0), (-1, 0), DARK),
                             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                             ("FONTSIZE", (0, 0), (-1, -1), 8),
                             ("ALIGN", (1, 1), (-1, -1), "RIGHT")]))

    story.append(Paragraph("Récapitulatif", S["h2"]))
    story.append(_table([
        ["Béton total", _fmt(t.get("beton_m3"), "m³"),
         "Aciers total", _fmt(t.get("acier_kg"), "kg", 0)],
        ["Briques isobrique", _fmt(t.get("briques_u"), "u", 0),
         "Semelles filantes", _fmt(t.get("semelles_ml"), "ml")],
        ["Total HT", _fmt(t.get("ht"), "€"),
         f"TVA {round(float(t.get('tva_rate') or 0.23) * 100)} %", _fmt(t.get("tva"), "€")],
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

    pl = study.get("planning")
    if pl and pl.get("phases"):
        story.append(Paragraph("Planning de chantier — gros œuvre", S["h2"]))
        sched = schedule_with_dates(pl, start_date) if start_date else None
        if sched:
            story.append(Paragraph(
                f"Démarrage prévu le <b>{_fr_long(sched[0]['work_start'])}</b> — "
                f"fin de chantier estimée le <b>{_fr_long(sched[-1]['cure_end'])}</b> "
                "(plein = jours ouvrés, translucide = séchage béton).", S["body"]))
            story.append(Spacer(1, 3))
            story.append(_gantt_drawing(sched))
            story.append(Spacer(1, 4))
        rows = [["Phase", "Jours ouvrés", "Séchage", "Début", "Fin"]]
        for i_ph, ph in enumerate(pl["phases"]):
            deb = _fr_long(sched[i_ph]["work_start"]) if sched else f"J{ph['start_day']}"
            fin = _fr_long(sched[i_ph]["cure_end"]) if sched else f"J{ph['end_day']}"
            rows.append([Paragraph(ph["name"], S["body"]), str(ph["work_days"]),
                         f"+{ph['cure_days']} j" if ph["cure_days"] else "—",
                         deb, fin])
        story.append(_table(rows, [86 * mm, 20 * mm, 18 * mm, 25 * mm, 25 * mm],
                            [("BACKGROUND", (0, 0), (-1, 0), DARK),
                             ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                             ("FONTSIZE", (0, 0), (-1, -1), 8),
                             ("ALIGN", (1, 1), (-1, -1), "CENTER")]))
        story.append(Spacer(1, 3))
        story.append(Paragraph(
            f"Équipe de {pl['crew_size']} compagnons — {pl['total_work_days']} jours ouvrés "
            f"de travail + {pl['total_cure_days']} jours de séchage béton, "
            f"soit ≈ {pl['total_days']} jours ({pl['total_weeks']} semaines) de chantier.",
            S["muted"]))
    _story_footer(story, S)
    doc.build(story)
    return buf.getvalue()


def build_pc_docx(plan: dict, study: dict, branding: dict | None = None,
                  start_date: str | None = None) -> bytes:
    """Export Word (.docx) de l'étude PC — même contenu que le PDF."""
    if study.get("schema_version") == "construction-dossier-1":
        from engines.study_dossier_pdf import build_dossier_docx
        return build_dossier_docx(plan, study, branding)
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
    lb = study.get("levels_breakdown") or []
    if lb:
        doc.add_heading("Quantités par niveau — pour phaser vos commandes", level=1)
        tbl = doc.add_table(rows=1 + len(lb), cols=6)
        tbl.style = "Light Grid Accent 1"
        for c, v in enumerate(["Niveau", "Béton m³", "Aciers kg", "Briques", "Murs m²", "Total HT €"]):
            tbl.rows[0].cells[c].text = v
        for r, l in enumerate(lb, start=1):
            cells = tbl.rows[r].cells
            cells[0].text = l["name"]
            cells[1].text = _fmt(l["beton_m3"])
            cells[2].text = _fmt(l["acier_kg"], "", 0)
            cells[3].text = _fmt(l["briques_u"], "", 0) if l["briques_u"] else "—"
            cells[4].text = _fmt(l["murs_m2"]) if l["murs_m2"] else "—"
            cells[5].text = _fmt(l["ht"])

    doc.add_heading("Récapitulatif", level=1)
    recap = doc.add_table(rows=4, cols=2)
    recap.style = "Light Grid Accent 1"
    data = [("Béton total", _fmt(t.get("beton_m3"), "m³")),
            ("Aciers total", _fmt(t.get("acier_kg"), "kg", 0)),
            (f"Total HT / TVA {round(float(t.get('tva_rate') or 0.23) * 100)} %",
             f"{_fmt(t.get('ht'), '€')} / {_fmt(t.get('tva'), '€')}"),
            ("TOTAL TTC", _fmt(t.get("ttc"), "€"))]
    for r_idx, (k, v) in enumerate(data):
        recap.rows[r_idx].cells[0].text = k
        recap.rows[r_idx].cells[1].text = v

    if study.get("warnings"):
        doc.add_heading("Avertissements IA", level=1)
        for w in study["warnings"][:8]:
            doc.add_paragraph(w, style="List Bullet")

    pl = study.get("planning")
    if pl and pl.get("phases"):
        doc.add_heading("Planning de chantier — gros œuvre", level=1)
        sched = schedule_with_dates(pl, start_date) if start_date else None
        if sched:
            doc.add_paragraph(
                f"Démarrage prévu le {_fr_long(sched[0]['work_start'])} — "
                f"fin de chantier estimée le {_fr_long(sched[-1]['cure_end'])}.")
        tbl = doc.add_table(rows=1 + len(pl["phases"]), cols=5)
        tbl.style = "Light Grid Accent 1"
        for c, v in enumerate(["Phase", "Jours ouvrés", "Séchage", "Début", "Fin"]):
            tbl.rows[0].cells[c].text = v
        for r, ph in enumerate(pl["phases"], start=1):
            cells = tbl.rows[r].cells
            cells[0].text = ph["name"]
            cells[1].text = str(ph["work_days"])
            cells[2].text = f"+{ph['cure_days']} j" if ph["cure_days"] else "—"
            cells[3].text = _fr_long(sched[r - 1]["work_start"]) if sched else f"J{ph['start_day']}"
            cells[4].text = _fr_long(sched[r - 1]["cure_end"]) if sched else f"J{ph['end_day']}"
        doc.add_paragraph(
            f"Équipe de {pl['crew_size']} compagnons — {pl['total_work_days']} jours ouvrés "
            f"+ {pl['total_cure_days']} jours de séchage béton, soit ≈ {pl['total_days']} "
            f"jours ({pl['total_weeks']} semaines) de chantier.")

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_purchase_order_pdf(plan: dict, level_name: str, items: list[dict],
                             branding: dict | None, order_ref: str,
                             supplier_name: str = "", notes: str = "") -> bytes:
    """Bon de commande matériaux (un niveau de l'étude PC) prêt à envoyer au négoce."""
    from datetime import date

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    S = _styles()
    story: list = []
    _story_header_branding(story, branding, S)
    story.append(Paragraph("BON DE COMMANDE MATÉRIAUX", S["kicker"]))
    story.append(Paragraph(order_ref, S["h1"]))
    story.append(Paragraph(
        f"Date : {date.today().strftime('%d/%m/%Y')} · "
        f"Chantier : {plan.get('filename') or 'permis de construire'} · "
        f"Phase : <b>{level_name}</b>", S["muted"]))
    if supplier_name:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"À l'attention de : <b>{supplier_name}</b>", S["body"]))
    story.append(Spacer(1, 6))

    rows = [["Désignation", "U", "Qté commandée*", "PU indicatif", "Total indicatif"]]
    for it in items:
        rows.append([Paragraph(it["designation"], S["body"]), it["unit"],
                     _fmt(it["qty"]), _fmt(it["pu_mat"], "€"), _fmt(it["total"], "€")])
    total = round(sum(it["total"] for it in items), 2)
    rows.append(["", "", "", "TOTAL HT indicatif", _fmt(total, "€")])
    story.append(_table(rows, [78 * mm, 12 * mm, 28 * mm, 28 * mm, 28 * mm],
                        [("BACKGROUND", (0, 0), (-1, 0), DARK),
                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("FONTSIZE", (0, 0), (-1, -1), 8),
                         ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                         ("FONTNAME", (3, len(rows) - 1), (-1, len(rows) - 1),
                          "Helvetica-Bold"),
                         ("TEXTCOLOR", (4, len(rows) - 1), (4, len(rows) - 1), ORANGE)],
                        repeat_rows=1))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "* Quantités incluant +5 % de chutes/pertes, arrondies au conditionnement "
        "supérieur. Prix indicatifs issus de notre étude — merci de confirmer vos "
        "tarifs, disponibilités et délais de livraison.", S["muted"]))
    if notes:
        story.append(Paragraph("Notes", S["h2"]))
        story.append(Paragraph(notes.replace("\n", "<br/>"), S["body"]))
    _story_footer(story, S)
    doc.build(story)
    return buf.getvalue()


def build_deposit_invoice_pdf(plan: dict, branding: dict | None, inv: dict) -> bytes:
    """Facture d'acompte acquittée (paiement CB) prête à envoyer au client."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    S = _styles()
    story: list = []
    _story_header_branding(story, branding, S)
    story.append(Paragraph("FACTURE D'ACOMPTE — ACQUITTÉE", S["kicker"]))
    story.append(Paragraph(inv["invoice_no"], S["h1"]))
    paid_date = _fr_long(inv["paid_at"]) if inv.get("paid_at") else ""
    story.append(Paragraph(
        f"Date : {paid_date} · Chantier : {plan.get('filename') or 'permis de construire'}",
        S["muted"]))
    client = inv.get("client_name") or ""
    if client or inv.get("client_email"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"Client : <b>{client or inv.get('client_email')}</b>"
            + (f" · {inv['client_email']}" if client and inv.get("client_email") else ""),
            S["body"]))
    story.append(Spacer(1, 6))

    amount = float(inv["amount"])
    ht = round(amount / 1.2, 2)
    tva = round(amount - ht, 2)
    total_ttc = float(inv.get("total_ttc") or 0)
    rows = [["Désignation", "Montant HT", "TVA 20 %", "Montant TTC"],
            [Paragraph(f"Acompte {inv.get('pct', 0):g} % sur l'étude gros œuvre — "
                       f"marché de {_fmt(total_ttc, '€')} TTC", S["body"]),
             _fmt(ht, "€"), _fmt(tva, "€"), _fmt(amount, "€")],
            ["", "", "TOTAL ACQUITTÉ", _fmt(amount, "€")]]
    story.append(_table(rows, [88 * mm, 30 * mm, 30 * mm, 30 * mm],
                        [("BACKGROUND", (0, 0), (-1, 0), DARK),
                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                         ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                         ("FONTNAME", (2, 2), (-1, 2), "Helvetica-Bold"),
                         ("TEXTCOLOR", (3, 2), (3, 2), ORANGE)]))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"Facture acquittée — règlement reçu par carte bancaire le {paid_date} "
        f"(réf. paiement {str(inv.get('session_id') or '')[:28]}).", S["body"]))
    if total_ttc:
        story.append(Paragraph(
            f"Reste à facturer sur le marché : <b>{_fmt(round(total_ttc - amount, 2), '€')} "
            "TTC</b> (situations de travaux à venir).", S["muted"]))
    story.append(Paragraph(
        "TVA acquittée sur les encaissements. Document généré par ConstruPilot.", S["muted"]))
    _story_footer(story, S)
    doc.build(story)
    return buf.getvalue()


def build_situation_invoice_pdf(plan: dict, branding: dict | None, inv: dict) -> bytes:
    """Facture de situation de travaux (ou de solde) — acquittée ou à régler."""
    from datetime import date

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    S = _styles()
    story: list = []
    _story_header_branding(story, branding, S)
    kind = "FACTURE DE SOLDE" if inv.get("is_final") else "FACTURE DE SITUATION"
    status = "ACQUITTÉE" if inv.get("paid") else "À RÉGLER"
    story.append(Paragraph(f"{kind} — {status}", S["kicker"]))
    story.append(Paragraph(inv["invoice_no"], S["h1"]))
    day = _fr_long(inv["created_at"]) if inv.get("created_at") else date.today().strftime("%d/%m/%Y")
    story.append(Paragraph(
        f"Date : {day} · Chantier : {plan.get('filename') or 'permis de construire'}",
        S["muted"]))
    client = inv.get("client_name") or ""
    if client or inv.get("client_email"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"Client : <b>{client or inv.get('client_email')}</b>"
            + (f" · {inv['client_email']}" if client and inv.get("client_email") else ""),
            S["body"]))
    story.append(Spacer(1, 6))

    amount = float(inv["amount"])
    ht = round(amount / 1.2, 2)
    tva = round(amount - ht, 2)
    total_ttc = float(inv.get("total_ttc") or 0)
    if inv.get("is_final"):
        desig = "Solde du marché — travaux gros œuvre achevés"
    else:
        desig = (f"Situation n° {inv.get('sit_no')} — avancement cumulé "
                 f"{inv.get('pct_cumul', 0):g} % du marché")
    if inv.get("note"):
        desig += f" · {inv['note']}"
    rows = [["Désignation", "Montant HT", "TVA 20 %", "Montant TTC"],
            [Paragraph(desig, S["body"]), _fmt(ht, "€"), _fmt(tva, "€"), _fmt(amount, "€")],
            ["", "", "TOTAL " + ("ACQUITTÉ" if inv.get("paid") else "À RÉGLER"),
             _fmt(amount, "€")]]
    story.append(_table(rows, [88 * mm, 30 * mm, 30 * mm, 30 * mm],
                        [("BACKGROUND", (0, 0), (-1, 0), DARK),
                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                         ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                         ("FONTNAME", (2, 2), (-1, 2), "Helvetica-Bold"),
                         ("TEXTCOLOR", (3, 2), (3, 2), ORANGE)]))
    story.append(Spacer(1, 5))
    already = float(inv.get("already_invoiced") or 0)
    if total_ttc:
        story.append(Paragraph(
            f"Marché total : <b>{_fmt(total_ttc, '€')} TTC</b> · déjà facturé avant "
            f"cette situation (acompte compris) : {_fmt(already, '€')} · reste à "
            f"facturer après cette situation : "
            f"<b>{_fmt(round(max(0.0, total_ttc - already - amount), 2), '€')}</b>.",
            S["muted"]))
    if inv.get("paid"):
        paid_date = _fr_long(inv["paid_at"]) if inv.get("paid_at") else ""
        story.append(Paragraph(
            f"Facture acquittée — règlement reçu par carte bancaire le {paid_date} "
            f"(réf. paiement {str(inv.get('session_id') or '')[:28]}).", S["body"]))
    else:
        story.append(Paragraph(
            "Règlement en ligne par carte bancaire via le lien sécurisé transmis "
            "par email, ou par virement à réception.", S["body"]))
    story.append(Paragraph(
        "TVA acquittée sur les encaissements. Document généré par ConstruPilot.", S["muted"]))
    _story_footer(story, S)
    doc.build(story)
    return buf.getvalue()
