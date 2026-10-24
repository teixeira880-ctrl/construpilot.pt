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
            dates += f" · secagem → {_fr(r['cure_end'])}"
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
        ["Hipótese", "Valor", "Fonte"],
        ["Níveis", str(i.get("levels")), src.get("levels", "")],
        ["Área de pavimento", _fmt(i.get("surface_m2"), "m²"), src.get("surface_m2", "")],
        ["Altura paredes", _fmt(i.get("wall_height_m"), "m"), src.get("wall_height_m", "")],
        ["Perímetro exterior", _fmt(i.get("perimeter_m"), "m"), src.get("perimeter_m", "")],
        ["Paredes interiores resistentes", _fmt(i.get("refends_m"), "m"), src.get("refends_m", "")],
        ["Vãos", f"{i.get('openings_count')} u · {_fmt(i.get('openings_area_m2'), 'm²')}", "Projeto de licenciamento (IA) / estimado"],
        ["Escadas", str(i.get("stairs_count")), "Projeto de licenciamento (IA) / estimado"],
    ]


RULES_TEXT = ("Regras fixas aplicadas: sapatas contínuas 60 × 30 cm (perímetro + paredes interiores resistentes) · laje/pavimento esp. 15 cm · paredes de tijolo térmico esp. 20 cm · escada de betão armado · aços: sapatas 3+3 Ø10 + estribos Ø6 (15 kg/ml), laje malha AQ38 + armaduras superiores (14 kg/m²), escada 100 kg/m³, lintéis 4 Ø10 (3,6 kg/ml).")


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
    story.append(Paragraph("ESTUDO DO PROJETO DE LICENCIAMENTO — ESTRUTURA E ALVENARIAS", S["kicker"]))
    story.append(Paragraph(plan.get("filename") or "Licença de construção", S["h1"]))
    story.append(Paragraph(f"Gerada a {str(study.get('generated_at') or '')[:10]} · confiança IA {round(float(study.get('confidence') or 0) * 100)} %",
                           S["muted"]))

    if study.get("demandes"):
        story.append(Paragraph("O que pede a licença", S["h2"]))
        for d in study["demandes"][:10]:
            story.append(Paragraph(f"• {d}", S["body"]))

    story.append(Paragraph("Hipóteses de orçamentação", S["h2"]))
    story.append(_table(_hypotheses_rows(study), [55 * mm, 60 * mm, 45 * mm],
                        [("BACKGROUND", (0, 0), (-1, 0), DARK),
                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    story.append(Spacer(1, 4))
    story.append(Paragraph(RULES_TEXT, S["muted"]))

    for lot in study.get("lots", []):
        story.append(Paragraph(lot["lot"], S["h2"]))
        rows = [["Designação", "U", "Qtd.", "PU mat.", "PU MO", "Total s/ IVA"]]
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
        story.append(Paragraph("Quantidades por nível — para faseamento das suas encomendas", S["h2"]))
        rows = [["Piso", "Betão", "Aços", "Tijolos", "Paredes", "Total s/ IVA"]]
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

    story.append(Paragraph("Resumo", S["h2"]))
    story.append(_table([
        ["Betão total", _fmt(t.get("beton_m3"), "m³"),
         "Aços total", _fmt(t.get("acier_kg"), "kg", 0)],
        ["Tijolos térmicos", _fmt(t.get("briques_u"), "u", 0),
         "Sapatas contínuas", _fmt(t.get("semelles_ml"), "ml")],
        ["Total s/ IVA", _fmt(t.get("ht"), "€"),
         f"IVA {round(float(t.get('tva_rate') or 0.23) * 100)} %", _fmt(t.get("tva"), "€")],
        ["TOTAL C/ IVA", _fmt(t.get("ttc"), "€"), "", ""],
    ], [45 * mm, 42 * mm, 45 * mm, 42 * mm],
        [("BACKGROUND", (0, 0), (-1, -1), LIGHT_GREY),
         ("FONTSIZE", (0, 0), (-1, -1), 9),
         ("TEXTCOLOR", (0, 3), (1, 3), ORANGE),
         ("FONTNAME", (0, 3), (1, 3), "Helvetica-Bold")]))

    if study.get("warnings"):
        story.append(Paragraph("Avisos IA", S["h2"]))
        for w in study["warnings"][:8]:
            story.append(Paragraph(f"• {w}", S["muted"]))

    pl = study.get("planning")
    if pl and pl.get("phases"):
        story.append(Paragraph("Planeamento de obra — estrutura", S["h2"]))
        sched = schedule_with_dates(pl, start_date) if start_date else None
        if sched:
            story.append(Paragraph(
                f"Arranque previsto em <b>{_fr_long(sched[0]['work_start'])}</b> — fim de obra estimado em <b>{_fr_long(sched[-1]['cure_end'])}</b> (cheio = dias úteis, translúcido = secagem do betão).", S["body"]))
            story.append(Spacer(1, 3))
            story.append(_gantt_drawing(sched))
            story.append(Spacer(1, 4))
        rows = [["Fase", "Dias úteis", "Secagem", "Início", "Fim"]]
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
            f"Equipa de {pl['crew_size']} colaboradores — {pl['total_work_days']} dias úteis de trabalho + {pl['total_cure_days']} dias de secagem betão, ou seja ≈ {pl['total_days']} dias ({pl['total_weeks']} semanas) de obra.",
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

    h = doc.add_heading("Estudo Licença de Construção — Estrutura", level=0)
    for run in h.runs:
        run.font.color.rgb = RGBColor(0xFF, 0x5A, 0x00)
    doc.add_paragraph(f"{plan.get('filename') or 'Licença de construção'} — gerada em {str(study.get('generated_at') or '')[:10]} · confiança IA {round(float(study.get('confidence') or 0) * 100)} %")

    if study.get("demandes"):
        doc.add_heading("O que pede a licença", level=1)
        for d in study["demandes"][:10]:
            doc.add_paragraph(d, style="List Bullet")

    doc.add_heading("Hipóteses de orçamentação", level=1)
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
        hdr = ["Designação", "U", "Qtd.", "PU mat. €", "PU MO €", "Total s/ IVA €"]
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
        doc.add_heading("Quantidades por nível — para faseamento das suas encomendas", level=1)
        tbl = doc.add_table(rows=1 + len(lb), cols=6)
        tbl.style = "Light Grid Accent 1"
        for c, v in enumerate(["Piso", "Betão m³", "Aços kg", "Tijolos", "Paredes m²", "Total s/ IVA €"]):
            tbl.rows[0].cells[c].text = v
        for r, l in enumerate(lb, start=1):
            cells = tbl.rows[r].cells
            cells[0].text = l["name"]
            cells[1].text = _fmt(l["beton_m3"])
            cells[2].text = _fmt(l["acier_kg"], "", 0)
            cells[3].text = _fmt(l["briques_u"], "", 0) if l["briques_u"] else "—"
            cells[4].text = _fmt(l["murs_m2"]) if l["murs_m2"] else "—"
            cells[5].text = _fmt(l["ht"])

    doc.add_heading("Resumo", level=1)
    recap = doc.add_table(rows=4, cols=2)
    recap.style = "Light Grid Accent 1"
    data = [("Betão total", _fmt(t.get("beton_m3"), "m³")),
            ("Aços total", _fmt(t.get("acier_kg"), "kg", 0)),
            (f"Total s/ IVA / IVA {round(float(t.get('tva_rate') or 0.23) * 100)} %",
             f"{_fmt(t.get('ht'), '€')} / {_fmt(t.get('tva'), '€')}"),
            ("TOTAL C/ IVA", _fmt(t.get("ttc"), "€"))]
    for r_idx, (k, v) in enumerate(data):
        recap.rows[r_idx].cells[0].text = k
        recap.rows[r_idx].cells[1].text = v

    if study.get("warnings"):
        doc.add_heading("Avisos IA", level=1)
        for w in study["warnings"][:8]:
            doc.add_paragraph(w, style="List Bullet")

    pl = study.get("planning")
    if pl and pl.get("phases"):
        doc.add_heading("Planeamento de obra — estrutura", level=1)
        sched = schedule_with_dates(pl, start_date) if start_date else None
        if sched:
            doc.add_paragraph(
                f"Arranque previsto em {_fr_long(sched[0]['work_start'])} — fim de obra estimado em {_fr_long(sched[-1]['cure_end'])}.")
        tbl = doc.add_table(rows=1 + len(pl["phases"]), cols=5)
        tbl.style = "Light Grid Accent 1"
        for c, v in enumerate(["Fase", "Dias úteis", "Secagem", "Início", "Fim"]):
            tbl.rows[0].cells[c].text = v
        for r, ph in enumerate(pl["phases"], start=1):
            cells = tbl.rows[r].cells
            cells[0].text = ph["name"]
            cells[1].text = str(ph["work_days"])
            cells[2].text = f"+{ph['cure_days']} j" if ph["cure_days"] else "—"
            cells[3].text = _fr_long(sched[r - 1]["work_start"]) if sched else f"J{ph['start_day']}"
            cells[4].text = _fr_long(sched[r - 1]["cure_end"]) if sched else f"J{ph['end_day']}"
        doc.add_paragraph(
            f"Equipa de {pl['crew_size']} colaboradores — {pl['total_work_days']} dias úteis + {pl['total_cure_days']} dias de secagem betão, ou seja ≈ {pl['total_days']} dias ({pl['total_weeks']} semanas) de obra.")

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
    story.append(Paragraph("NOTA DE ENCOMENDA DE MATERIAIS", S["kicker"]))
    story.append(Paragraph(order_ref, S["h1"]))
    story.append(Paragraph(
        f"Date : {date.today().strftime('%d/%m/%Y')} · Obra: {plan.get('filename') or 'projeto de licenciamento'} · Phase : <b>{level_name}</b>", S["muted"]))
    if supplier_name:
        story.append(Spacer(1, 4))
        story.append(Paragraph(f'À atenção de: <b>{supplier_name}</b>', S["body"]))
    story.append(Spacer(1, 6))

    rows = [["Designação", "U", "Qtd. encomendada*", "PU indicativo", "Total indicativo"]]
    for it in items:
        rows.append([Paragraph(it["designation"], S["body"]), it["unit"],
                     _fmt(it["qty"]), _fmt(it["pu_mat"], "€"), _fmt(it["total"], "€")])
    total = round(sum(it["total"] for it in items), 2)
    rows.append(["", "", "", "TOTAL s/ IVA indicativo", _fmt(total, "€")])
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
        "* Quantidades que incluem +5 % de desperdícios/perdas, arredondadas à embalagem superior. Preços indicativos provenientes do nosso estudo — confirme os seus preços, disponibilidades e prazos de entrega.", S["muted"]))
    if notes:
        story.append(Paragraph("Notas", S["h2"]))
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
    story.append(Paragraph("FATURA DE ADIANTAMENTO — PAGA", S["kicker"]))
    story.append(Paragraph(inv["invoice_no"], S["h1"]))
    paid_date = _fr_long(inv["paid_at"]) if inv.get("paid_at") else ""
    story.append(Paragraph(
        f"Date : {paid_date} · Obra: {plan.get('filename') or 'projeto de licenciamento'}",
        S["muted"]))
    client = inv.get("client_name") or ""
    if client or inv.get("client_email"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"Cliente: <b>{client or inv.get('client_email')}</b>"
            + (f" · {inv['client_email']}" if client and inv.get("client_email") else ""),
            S["body"]))
    story.append(Spacer(1, 6))

    amount = float(inv["amount"])
    ht = round(amount / 1.2, 2)
    tva = round(amount - ht, 2)
    total_ttc = float(inv.get("total_ttc") or 0)
    rows = [["Designação", "Montante s/ IVA", "IVA 20 %", "Montante c/ IVA"],
            [Paragraph(f"Adiantamento {inv.get('pct', 0):g} % sobre o estudo de estrutura — empreitada de {_fmt(total_ttc, '€')} c/ IVA", S["body"]),
             _fmt(ht, "€"), _fmt(tva, "€"), _fmt(amount, "€")],
            ["", "", "TOTAL PAGO", _fmt(amount, "€")]]
    story.append(_table(rows, [88 * mm, 30 * mm, 30 * mm, 30 * mm],
                        [("BACKGROUND", (0, 0), (-1, 0), DARK),
                         ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                         ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                         ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                         ("FONTNAME", (2, 2), (-1, 2), "Helvetica-Bold"),
                         ("TEXTCOLOR", (3, 2), (3, 2), ORANGE)]))
    story.append(Spacer(1, 5))
    story.append(Paragraph(
        f"Fatura paga — pagamento recebido por cartão bancário em {paid_date} (ref. pagamento {str(inv.get('session_id') or '')[:28]}).", S["body"]))
    if total_ttc:
        story.append(Paragraph(
            f"Por faturar na empreitada: <b>{_fmt(round(total_ttc - amount, 2), '€')} c/ IVA</b> (autos de medição a emitir).", S["muted"]))
    story.append(Paragraph(
        "IVA liquidado sobre os recebimentos. Documento gerado pelo ConstruPilot.", S["muted"]))
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
    kind = "FATURA FINAL" if inv.get("is_final") else "FATURA DE AUTO DE MEDIÇÃO"
    status = "PAGA" if inv.get("paid") else "A PAGAR"
    story.append(Paragraph(f"{kind} — {status}", S["kicker"]))
    story.append(Paragraph(inv["invoice_no"], S["h1"]))
    day = _fr_long(inv["created_at"]) if inv.get("created_at") else date.today().strftime("%d/%m/%Y")
    story.append(Paragraph(
        f"Date : {day} · Obra: {plan.get('filename') or 'projeto de licenciamento'}",
        S["muted"]))
    client = inv.get("client_name") or ""
    if client or inv.get("client_email"):
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"Cliente: <b>{client or inv.get('client_email')}</b>"
            + (f" · {inv['client_email']}" if client and inv.get("client_email") else ""),
            S["body"]))
    story.append(Spacer(1, 6))

    amount = float(inv["amount"])
    ht = round(amount / 1.2, 2)
    tva = round(amount - ht, 2)
    total_ttc = float(inv.get("total_ttc") or 0)
    if inv.get("is_final"):
        desig = "Saldo da empreitada — trabalhos de estrutura concluídos"
    else:
        desig = (f"Auto de medição n.º {inv.get('sit_no')} — avanço acumulado {inv.get('pct_cumul', 0):g} % da empreitada")
    if inv.get("note"):
        desig += f" · {inv['note']}"
    rows = [["Designação", "Montante s/ IVA", "IVA 20 %", "Montante c/ IVA"],
            [Paragraph(desig, S["body"]), _fmt(ht, "€"), _fmt(tva, "€"), _fmt(amount, "€")],
            ["", "", "TOTAL " + ("PAGO" if inv.get("paid") else "A PAGAR"),
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
            f"Empreitada total: <b>{_fmt(total_ttc, '€')} c/ IVA</b> · já faturado antes deste auto (adiantamento incluído): {_fmt(already, '€')} · por faturar após este auto: <b>{_fmt(round(max(0.0, total_ttc - already - amount), 2), '€')}</b>.",
            S["muted"]))
    if inv.get("paid"):
        paid_date = _fr_long(inv["paid_at"]) if inv.get("paid_at") else ""
        story.append(Paragraph(
            f"Fatura paga — pagamento recebido por cartão bancário em {paid_date} (ref. pagamento {str(inv.get('session_id') or '')[:28]}).", S["body"]))
    else:
        story.append(Paragraph(
            "Pagamento online por cartão bancário através da ligação segura enviada por e-mail, ou por transferência na receção.", S["body"]))
    story.append(Paragraph(
        "IVA liquidado sobre os recebimentos. Documento gerado pelo ConstruPilot.", S["muted"]))
    _story_footer(story, S)
    doc.build(story)
    return buf.getvalue()
