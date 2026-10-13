"""PDF brandés ConstruPilot : (1) comparaison de documents (assistant) ; (2) incohérences des chaînes périphériques (1 page)."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engines.pdf_takeoff import GREY, LIGHT_GREY, ORANGE, _styles
from engines.plan_cotes_pdf import _e

STATUS_FR = {"identical": "Idêntico", "different_quantity": "Quantidade ≠", "different_price": "Preço ≠", "different_scope": "Âmbito ≠",
             "only_a": "Apenas A", "only_b": "Apenas B", "to_confirm": "A confirmar"}
STATUS_PT = {"identical": "Idêntico", "different_quantity": "Quantidade ≠", "different_price": "Preço ≠", "different_scope": "Âmbito ≠",
             "only_a": "Apenas A", "only_b": "Apenas B", "to_confirm": "A confirmar"}


def _doc(buf, pagesize, title):
    return SimpleDocTemplate(buf, pagesize=pagesize, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
                             title=title, author="ConstruPilot")


def _footer_factory(label: str):
    def _footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(GREY)
        canvas.drawRightString(d.pagesize[0] - 14 * mm, 8 * mm, f"{label} · {d.page}")
        canvas.setFillColor(ORANGE)
        canvas.rect(14 * mm, 8 * mm, 18 * mm, 1.2, fill=1, stroke=0)
        canvas.restoreState()
    return _footer


def _n(v):
    return "—" if v is None else f"{float(v):,.2f} €".replace(",", " ")


def _q(v, u):
    return "—" if v is None else f"{v:g} {u or ''}".strip()


def build_comparison_pdf(rec: dict, branding: dict | None, lang: str = "pt") -> bytes:
    pt = lang == "pt"
    L = (lambda fr, p: p if pt else fr)
    c = rec["result"]
    S = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, landscape(A4), L("Comparação de documentos", "Comparação de documentos"))
    W = landscape(A4)[0] - 28 * mm
    company = (branding or {}).get("company_name") or "ConstruPilot"
    story = [Paragraph(f"<font color='#FF5A00'><b>{_e(company)}</b></font>", S["h1"]),
             Paragraph(L("COMPARAÇÃO DE DOCUMENTOS", "COMPARAÇÃO DE DOCUMENTOS"), S["kicker"]),
             Paragraph(f"{L('Document A', 'Documento A')} : <b>{_e(rec.get('filename_a'))}</b> — {L('Document B', 'Documento B')} : <b>{_e(rec.get('filename_b'))}</b>", S["body"]),
             Paragraph(f"{L('Gerado em', 'Gerado em')} {datetime.now(timezone.utc).strftime('%d/%m/%Y')} · {L('réf.', 'ref.')} {rec.get('comparison_id')}"
                       + (f" · {L('focus', 'foco')} : {_e(rec.get('focus'))}" if rec.get("focus") else ""), S["muted"]), Spacer(1, 3 * mm)]
    da, db_ = c.get("document_a") or {}, c.get("document_b") or {}
    head = [[L("Documento", "Documento"), L("Emitente", "Emissor"), L("Data", "Dados"), L("Linhas", "Linhas"), "HT", L("TVA %", "IVA %"), "c/ IVA"],
            ["A — " + (rec.get("filename_a") or "")[:40], da.get("issuer") or "—", da.get("date") or "—", da.get("lines_count"), _n(da.get("total_ht")), da.get("vat_rate") or "—", _n(da.get("total_ttc"))],
            ["B — " + (rec.get("filename_b") or "")[:40], db_.get("issuer") or "—", db_.get("date") or "—", db_.get("lines_count"), _n(db_.get("total_ht")), db_.get("vat_rate") or "—", _n(db_.get("total_ttc"))]]
    t = Table(head, colWidths=[W * f for f in (0.28, 0.2, 0.1, 0.08, 0.12, 0.08, 0.14)])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1"))]))
    story += [t, Spacer(1, 3 * mm), Paragraph(L("Síntese", "Síntese"), S["h2"]), Paragraph(_e(c.get("summary") or ""), S["body"]), Spacer(1, 3 * mm)]
    rows = [[L("Artigo", "Rubrica"), L("Designação A / B", "Designação A / B"), L("Qtd A / B", "Qtd A / B"), "PU A / B", "Total A / B", L("Desvio", "Desvio"), L("Estado", "Estado"), L("Comentário", "Comentário")]]
    ST = STATUS_PT if pt else STATUS_FR
    for ln in c.get("line_matches") or []:
        d = ln.get("delta_pct")
        rows.append([Paragraph(_e(ln.get("topic")), S["body"]), Paragraph(_e(f"{ln.get('designation_a') or '—'} / {ln.get('designation_b') or '—'}"), S["body"]),
                     f"{_q(ln.get('qty_a'), ln.get('unit'))}\n{_q(ln.get('qty_b'), ln.get('unit'))}", f"{_n(ln.get('unit_price_a'))}\n{_n(ln.get('unit_price_b'))}",
                     f"{_n(ln.get('total_a'))}\n{_n(ln.get('total_b'))}", "—" if d is None else f"{d:+.1f} %", ST.get(ln.get("status"), ln.get("status")),
                     Paragraph(_e(ln.get("comment") or ""), S["body"])])
    if len(rows) > 1:
        t = Table(rows, colWidths=[W * f for f in (0.12, 0.24, 0.09, 0.11, 0.12, 0.07, 0.09, 0.16)], repeatRows=1)
        t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1"))]))
        story += [Paragraph(L("Artigos comparados", "Rubricas confrontadas"), S["h2"]), t, Spacer(1, 3 * mm)]
    for key, title in (("only_in_a", L("Apenas em A", "Apenas em A")), ("only_in_b", L("Apenas em B", "Apenas em B")),
                       ("questions_to_ask", L("Perguntas a fazer", "Perguntas a colocar")), ("caveats", L("Reservas", "Reservas"))):
        items = c.get(key) or []
        if items:
            story += [Paragraph(title, S["h2"])] + [Paragraph(f"• {_e(x)}", S["body"]) for x in items]
    diffs = c.get("differences") or []
    if diffs:
        story.append(Paragraph(L("Diferenças notáveis", "Diferenças notáveis"), S["h2"]))
        for d in diffs:
            col = {"high": "#dc2626", "medium": "#d97706"}.get(d.get("importance"), "#64748B")
            story.append(Paragraph(f"<font color='{col}'><b>{_e(d.get('topic'))}</b></font> ({_e(d.get('kind'))}) — {_e(d.get('detail'))}", S["body"]))
    if c.get("account_type") == "individual":
        story += [Spacer(1, 3 * mm), Paragraph(L("Documento informativo: não constitui nem uma classificação nem um parecer sobre a justeza dos preços; só os orçamentos das empresas vinculam.",
                                                 "Documento informativo: não constitui uma classificação nem um parecer sobre a justeza dos preços; apenas os orçamentos das empresas vinculam."), S["muted"])]
    doc.build(story, onFirstPage=_footer_factory(f"{company} · ConstruPilot"), onLaterPages=_footer_factory(f"{company} · ConstruPilot"))
    return buf.getvalue()


def build_inconsistencies_pdf(plan: dict, page_index: int, report: dict, branding: dict | None, lang: str = "pt") -> bytes:
    """Une page : chaînes périphériques, comparaisons et incohérences chiffrées — à transmettre à l'architecte / BET."""
    pt = lang == "pt"
    L = (lambda fr, p: p if pt else fr)
    it = report.get("interior") or {}
    per = it.get("peripheral") or {}
    S = _styles()
    buf = io.BytesIO()
    doc = _doc(buf, A4, L("Incoerências de cotagem", "Incoerências de cotagem"))
    W = A4[0] - 28 * mm
    company = (branding or {}).get("company_name") or "ConstruPilot"
    story = [Paragraph(f"<font color='#FF5A00'><b>{_e(company)}</b></font>", S["h1"]),
             Paragraph(L("INCOERÊNCIAS DE COTAGEM — CADEIAS PERIFÉRICAS", "INCOERÊNCIAS DE COTAGEM — CADEIAS PERIFÉRICAS"), S["kicker"]),
             Paragraph(f"{L('Planta', 'Planta')} : <b>{_e(plan.get('filename'))}</b> · {L('page', 'página')} {page_index + 1} · {L('gerado em', 'gerado em')} {datetime.now(timezone.utc).strftime('%d/%m/%Y')}", S["muted"]), Spacer(1, 4 * mm)]
    inc = per.get("inconsistencies") or []
    story.append(Paragraph(L(f'{len(inc)} incoerência(s) entre as cotas escritas da planta (tolerância ±10 mm; desvios iguais a uma espessura vizinha = referências face/eixo diferentes, excluídos).',
                             f"{len(inc)} incoerência(s) entre as cotas escritas da planta (tolerância ±10 mm; desvios iguais a uma espessura vizinha = referências face/eixo diferentes, excluídos)."), S["body"]))
    rows = [["#", L("Type", "Tipo"), L("Lado(s)", "Lado(s)"), L("Detalhe", "Detalhe"), L("Desvio", "Desvio")]]
    KIND = {"opposite_totals": L("Dimensões gerais opostas", "Dimensões gerais opostas"), "opposite_partials": L("Cotas parciais opostas", "Cotas parciais opostas"),
            "chain_sum": L("Σ parciais ≠ total", "Σ parciais ≠ total"), "missing_opposite": L("Cota sem equivalente", "Cota sem equivalente")}
    for i, x in enumerate(inc, 1):
        rows.append([str(i), KIND.get(x.get("kind"), x.get("kind")), x.get("side") or "—", Paragraph(_e(x.get("detail")), S["body"]),
                     "—" if x.get("delta_mm") is None else f"{x['delta_mm']:+.0f} mm"])
    t = Table(rows, colWidths=[W * f for f in (0.05, 0.22, 0.13, 0.48, 0.12)], repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1"))]))
    story += [t, Spacer(1, 4 * mm), Paragraph(L("Cadeias registadas", "Cadeias registadas"), S["h2"])]
    crow = [[L("Cadeia", "Cadeia"), L("Lado", "Lado"), L("Partielles", "Parciais"), L("Somme", "Soma"), L("Total escrito", "Total escrito"), L("Desvio", "Desvio")]]
    for ch in per.get("chains") or []:
        tot = ch.get("total_m") if ch.get("total_m") is not None else ch.get("reference_total_m")
        crow.append([ch["chain_id"], ch["side"], Paragraph(_e(" + ".join(f"{p['value_m']:.2f}" for p in ch["partials"])), S["body"]), f"{ch['sum_m']:.2f} m",
                     "—" if tot is None else f"{tot:.2f} m" + ("" if ch.get("total_m") is not None else "*"),
                     "—" if ch.get("difference_mm") is None else f"{ch['difference_mm']:+.0f} mm"])
    t2 = Table(crow, colWidths=[W * f for f in (0.11, 0.1, 0.45, 0.1, 0.13, 0.11)], repeatRows=1)
    t2.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1"))]))
    story += [t2, Paragraph(L("* dimensão geral vizinha (cadeia parcial, ex.: cadeia de eixos).", "* dimensão geral vizinha (cadeia parcial, ex. cadeia de eixos)."), S["muted"]),
              Spacer(1, 3 * mm),
              Paragraph(L("Medições provenientes dos vetores exatos do PDF; cada diferença designa duas cotas escritas da planta que não concordam. Indique a cota a adotar.",
                          "Medidas obtidas dos vetores exatos do PDF; cada desvio designa duas cotas escritas da planta que não concordam. Agradecemos que indique a cota a reter."), S["body"])]
    doc.build(story, onFirstPage=_footer_factory(f"{company} · ConstruPilot"), onLaterPages=_footer_factory(f"{company} · ConstruPilot"))
    _ = PageBreak
    return buf.getvalue()
