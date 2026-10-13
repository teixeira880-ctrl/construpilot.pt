"""PDF « version interne » d'un devis : coûts de revient et marges par ligne / par lot.

Réservé au pro — jamais envoyé au client.
"""
from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from engines.pdf_takeoff import DARK, LIGHT_GREY, ORANGE, _fmt, _story_header_branding, _styles, _table

RED = colors.HexColor("#C0392B")
GREEN = colors.HexColor("#1E8449")
AMBER = colors.HexColor("#B9770E")


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.0f} %"


def _margin_color(pct: float | None, loss: bool = False):
    if loss or (pct is not None and pct < 0):
        return RED
    if pct is not None and pct < 15:
        return AMBER
    return GREEN


def _line_stats(ln: dict) -> dict:
    qty = float(ln.get("qty") or 0)
    pu = float(ln.get("unit_price_ht") or 0)
    cost = float(ln.get("cost_price_ht") or 0)
    sale = round(qty * pu, 2)
    cost_total = round(qty * cost, 2) if cost > 0 else None
    margin = round(sale - cost_total, 2) if cost_total is not None else None
    pct = (margin / sale * 100) if margin is not None and sale > 0 else (-100.0 if margin is not None else None)
    return {"qty": qty, "pu": pu, "cost": cost, "sale": sale, "cost_total": cost_total,
            "margin": margin, "pct": pct, "loss": cost > 0 and pu < cost}


def build_internal_quote_pdf(doc: dict, branding: dict | None = None) -> bytes:
    buf = BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm)
    S = _styles()
    story: list = []
    _story_header_branding(story, branding, S)

    story.append(Paragraph("VERSÃO INTERNA — CONFIDENCIAL", S["kicker"]))
    story.append(Paragraph(
        f"Análise de margem · Orçamento {escape(doc.get('number') or doc.get('doc_id') or '')}{(' · ' + escape(doc.get('title')) if doc.get('title') else '')}", S["h1"]))
    story.append(Paragraph(
        "Custos de produção (mão de obra + materiais) e margem previsional por artigo e por capítulo. <b>Não transmitir ao cliente.</b>", S["muted"] if "muted" in S else S["body"]))
    story.append(Spacer(1, 6))

    lines = doc.get("lines") or []
    header = ["Designação", "Qtd.", "U", "PU venda s/ IVA", "Custo unit. s/ IVA", "Total venda s/ IVA",
              "Custo total", "Marge €", "Marge %"]
    rows: list = [header]
    styles: list = []

    groups, order = [], {}
    for ln in lines:
        cat = (ln.get("category") or "").strip() or "Autres"
        if cat not in order:
            order[cat] = len(groups)
            groups.append((cat, []))
        groups[order[cat]][1].append(ln)

    tot_sale = tot_cost = 0.0
    has_cost = False
    loss_count = 0
    lot_summary: list[tuple[str, float, float | None, float | None, int]] = []

    for cat, lns in groups:
        r = len(rows)
        rows.append([Paragraph(f"<b>{escape(cat)}</b>", S["body"])] + [""] * 8)
        styles += [("SPAN", (0, r), (-1, r)), ("BACKGROUND", (0, r), (-1, r), colors.HexColor("#EEEBE6"))]
        sub_sale = sub_cost = 0.0
        sub_has_cost = False
        sub_loss = 0
        for ln in lns:
            st = _line_stats(ln)
            sub_sale += st["sale"]
            if st["cost_total"] is not None:
                sub_has_cost = True
                sub_cost += st["cost_total"]
            if st["loss"]:
                sub_loss += 1
            ri = len(rows)
            desig = escape(ln.get("designation") or "")
            if st["loss"]:
                desig = f'<font color="#C0392B"><b>⚠ {desig}</b></font>'
            rows.append([Paragraph(desig, S["body"]), _fmt(st["qty"]), ln.get("unit") or "",
                         _fmt(st["pu"], "€"), _fmt(st["cost"], "€") if st["cost"] > 0 else "—",
                         _fmt(st["sale"], "€"),
                         _fmt(st["cost_total"], "€") if st["cost_total"] is not None else "—",
                         _fmt(st["margin"], "€") if st["margin"] is not None else "—",
                         _pct(st["pct"])])
            if st["pct"] is not None:
                styles.append(("TEXTCOLOR", (7, ri), (8, ri), _margin_color(st["pct"], st["loss"])))
            if st["loss"]:
                styles.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#FDECEA")))
        sub_margin = round(sub_sale - sub_cost, 2) if sub_has_cost else None
        sub_pct = (sub_margin / sub_sale * 100) if sub_margin is not None and sub_sale > 0 else None
        ri = len(rows)
        rows.append([Paragraph(f'<b>Subtotal · {escape(cat)}</b>', S["body"]), "", "", "", "",
                     Paragraph(f"<b>{_fmt(round(sub_sale, 2), '€')}</b>", S["body"]),
                     _fmt(round(sub_cost, 2), "€") if sub_has_cost else "—",
                     _fmt(sub_margin, "€") if sub_margin is not None else "—", _pct(sub_pct)])
        styles += [("SPAN", (0, ri), (4, ri)), ("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#FAF8F5")),
                   ("LINEABOVE", (0, ri), (-1, ri), 0.5, LIGHT_GREY)]
        if sub_pct is not None:
            styles.append(("TEXTCOLOR", (7, ri), (8, ri), _margin_color(sub_pct, sub_loss > 0)))
        tot_sale += sub_sale
        tot_cost += sub_cost
        has_cost = has_cost or sub_has_cost
        loss_count += sub_loss
        lot_summary.append((cat, sub_sale, sub_margin, sub_pct, sub_loss))

    if not lines:
        rows.append(["Sem linhas"] + [""] * 8)

    extras = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 1), (-1, -1), "TOP"), ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
    ] + styles
    story.append(_table(rows, [84 * mm, 14 * mm, 12 * mm, 24 * mm, 24 * mm, 28 * mm, 26 * mm, 26 * mm, 18 * mm],
                        style_extras=extras, repeat_rows=1))
    story.append(Spacer(1, 10))

    # Récapitulatif
    tot_margin = round(tot_sale - tot_cost, 2) if has_cost else None
    tot_pct = (tot_margin / tot_sale * 100) if tot_margin is not None and tot_sale > 0 else None
    story.append(Paragraph("Síntese", S["h2"]))
    recap = [["Total venda s/ IVA", _fmt(round(tot_sale, 2), "€")],
             ["Custo de produção total", _fmt(round(tot_cost, 2), "€") if has_cost else "— (nenhum custo introduzido)"],
             ["Margem previsional", f"{_fmt(tot_margin, '€')} · {_pct(tot_pct)}" if tot_margin is not None else "—"],
             ["Artigos orçamentados com prejuízo", str(loss_count) if has_cost else "—"]]
    rextras = [("FONTSIZE", (0, 0), (-1, -1), 9), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
               ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
               ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_GREY])]
    if tot_pct is not None:
        rextras.append(("TEXTCOLOR", (1, 2), (1, 2), _margin_color(tot_pct, loss_count > 0)))
    if loss_count:
        rextras.append(("TEXTCOLOR", (1, 3), (1, 3), RED))
    story.append(_table(recap, [90 * mm, 60 * mm], style_extras=rextras))

    if lot_summary and has_cost:
        story.append(Spacer(1, 8))
        story.append(Paragraph("Marge par lot", S["h2"]))
        lrows = [["Lote", "Venda s/ IVA", "Marge €", "Marge %", "Com prejuízo"]]
        lstyles = [("BACKGROUND", (0, 0), (-1, 0), DARK), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                   ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 1), (-1, -1), "RIGHT")]
        for i, (cat, sale, margin, pct, loss) in enumerate(lot_summary, start=1):
            lrows.append([cat, _fmt(round(sale, 2), "€"), _fmt(margin, "€") if margin is not None else "—",
                          _pct(pct), str(loss) if loss else ""])
            if pct is not None:
                lstyles.append(("TEXTCOLOR", (2, i), (3, i), _margin_color(pct, loss > 0)))
        story.append(_table(lrows, [110 * mm, 40 * mm, 40 * mm, 28 * mm, 22 * mm], style_extras=lstyles))

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "Documento de trabalho interno gerado pelo ConstruPilot. Os custos de produção vêm da sua biblioteca e das suas introduções; a margem é previsional (sem custos gerais não afetados).",
        S["small"] if "small" in S else S["body"]))

    def _watermark(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(ORANGE)
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, "VERSÃO INTERNA — NÃO TRANSMITIR AO CLIENTE")
        canvas.restoreState()

    pdf.build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    return buf.getvalue()
