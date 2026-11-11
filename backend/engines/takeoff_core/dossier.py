"""Premium dossier of a study, the same presentation for every company and every construction system.

Cover with the company brand, the method, heights and their origin, quantities per floor with the origin of each
number, cross-checks, estimate with the source of each price, hypotheses to confirm, measurements per piece, and
Annex A: the dimensioned drawings the quantities come from (always attached). Languages: pt, en, uk, fr.

ReportLab (BSD) for the pages and pypdf (BSD) to append the annex: no AGPL dependency.
"""
from __future__ import annotations

import io
from datetime import date

from . import desenhos
from .i18n import code_label, tr

CONSTRUPILOT = {"nome": "ConstruPilot", "cor": (0.09, 0.29, 0.22), "site": "construpilot", "logo_bytes": None}


def _fmt(x, digits=2, lang="pt"):
    s = f"{x:,.{digits}f}"
    if lang in ("pt", "fr", "uk"):
        s = s.replace(",", " ").replace(".", ",")
    return s


def build(result, *, brand=None, lang="pt", title=None):
    """result: estudo.run(...) (with its _redes). brand: {"nome", "cor" (r,g,b 0-1), "logo_bytes", "site"}."""
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                    TableStyle)

    brand = {**CONSTRUPILOT, **(brand or {})}
    t = lambda s: tr(s, lang)  # noqa: E731
    n = lambda x, d=2: _fmt(x, d, lang)  # noqa: E731
    fr, fb = desenhos.register_fonts()
    colour = colors.Color(*brand["cor"])
    title = title or f"{result['projeto']} · {t('Dossier de medições e orçamento')}"
    S = {
        "h1": ParagraphStyle("h1", fontName=fb, fontSize=15, leading=19, textColor=colour, spaceBefore=6, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=fb, fontSize=11, leading=14, textColor=colors.black, spaceBefore=6, spaceAfter=4),
        "p": ParagraphStyle("p", fontName=fr, fontSize=8.8, leading=12, alignment=TA_LEFT),
        "small": ParagraphStyle("s", fontName=fr, fontSize=7.2, leading=9.2, textColor=colors.Color(.3, .3, .3)),
        "cell": ParagraphStyle("c", fontName=fr, fontSize=7.2, leading=8.8),
        "cellb": ParagraphStyle("cb", fontName=fb, fontSize=7.2, leading=8.8),
        "cover": ParagraphStyle("cv", fontName=fb, fontSize=24, leading=29, textColor=colors.white),
        "coversub": ParagraphStyle("cvs", fontName=fr, fontSize=11, leading=15, textColor=colors.white),
        "kpi": ParagraphStyle("k", fontName=fb, fontSize=15, leading=18, textColor=colour),
        "kpil": ParagraphStyle("kl", fontName=fr, fontSize=7.5, leading=9, textColor=colors.Color(.35, .35, .35)),
    }
    P = lambda s, st="cell": Paragraph(str(s), S[st])  # noqa: E731
    ORIGIN_COLOUR = {"medido": colors.Color(.86, .95, .88), "regra": colors.Color(.88, .92, .98),
                     "estimativa": colors.Color(1, .95, .82), "estimativa_imagem": colors.Color(.99, .87, .85)}

    def table(rows, widths, header=True, origin_col=None):
        tb = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
        style = [("GRID", (0, 0), (-1, -1), 0.25, colors.Color(.75, .75, .75)), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), colour), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        if origin_col is not None:
            for i, r in enumerate(rows[1:], 1):
                key = getattr(r[origin_col], "_origin", None)
                if key in ORIGIN_COLOUR:
                    style.append(("BACKGROUND", (origin_col, i), (origin_col, i), ORIGIN_COLOUR[key]))
        tb.setStyle(TableStyle(style))
        return tb

    def origin_cell(o):
        p = P(t("origem." + o))
        p._origin = o
        return p

    def hdr(*cols):
        return [Paragraph(f"<font color='white'>{c}</font>", S["cellb"]) for c in cols]

    story = []
    # ------------------------------------------------------------------ cover
    def cover(canvas, doc):
        W, H = A4
        canvas.saveState()
        canvas.setFillColor(colour)
        canvas.rect(0, H - 120 * mm, W, 120 * mm, stroke=0, fill=1)
        if brand.get("logo_bytes"):
            from reportlab.lib.utils import ImageReader
            img = ImageReader(io.BytesIO(brand["logo_bytes"]))
            iw, ih = img.getSize()
            k = min(60 * mm / iw, 22 * mm / ih)
            canvas.setFillColor(colors.white)
            canvas.roundRect(16 * mm, H - 40 * mm, iw * k + 8 * mm, ih * k + 6 * mm, 3, stroke=0, fill=1)
            canvas.drawImage(img, 20 * mm, H - 37 * mm, iw * k, ih * k, mask="auto")
        else:
            canvas.setFillColor(colors.white)
            canvas.setFont(fb, 20)
            canvas.drawString(20 * mm, H - 30 * mm, brand["nome"])
        canvas.restoreState()
        footer(canvas, doc)

    def footer(canvas, doc):
        W, _H = A4
        canvas.saveState()
        canvas.setStrokeColor(colour)
        canvas.setLineWidth(0.6)
        canvas.line(15 * mm, 13 * mm, W - 15 * mm, 13 * mm)
        canvas.setFont(fr, 7)
        canvas.setFillColor(colors.Color(.35, .35, .35))
        canvas.drawString(15 * mm, 8.5 * mm, f"{brand['nome']} · {result['projeto']} · {t('métodos ConstruPilot comuns a todas as construções')}")
        canvas.drawRightString(W - 15 * mm, 8.5 * mm, f"{t('página')} {doc.page}")
        canvas.restoreState()

    story.append(Spacer(1, 45 * mm))
    story.append(P(title, "cover"))
    story.append(Spacer(1, 4 * mm))
    systems = ", ".join(t("sistema." + s) for s in result["sistemas_usados"])
    story.append(P(f"{systems} · {result['pais']} · {date.today().isoformat()}", "coversub"))
    story.append(Spacer(1, 42 * mm))
    tot = {(r["codigo"], r["sistema"]): r for r in result["totais"]}
    net = sum(r["quantidade"] for r in result["totais"] if r["codigo"] == "parede_area_liquida")
    vol = sum(r["quantidade"] for r in result["totais"] if r["codigo"] == "parede_volume")
    nv = sum(r["quantidade"] for r in result["totais"] if r["codigo"].startswith("vaos_"))
    budget = result.get("orcamento")
    kpis = [(n(net), "m²", t("paredes, área líquida")), (n(vol, 3), "m³", t("paredes, volume")), (n(nv, 0), "", t("vãos")),
            ((n(budget["subtotal"]) + " €") if budget else "—", "", t("total sem IVA") if budget else t("sem biblioteca de preços"))]
    story.append(Table([[P(f"{v} <font size=9>{u}</font>", "kpi") for v, u, _l in kpis], [P(lbl, "kpil") for _v, _u, lbl in kpis]],
                       colWidths=[44 * mm] * 4, style=TableStyle([("LINEABOVE", (0, 0), (-1, 0), 1.2, colour)])))
    story.append(Spacer(1, 10 * mm))
    ok = result["verificacoes_ok"]
    story.append(P(f"<b>{t('Verificações cruzadas')}:</b> " + (t("todas dentro da tolerância") if ok else t("há verificações fora da tolerância: ver secção 4")), "p"))
    story.append(P(t("Cada número indica a sua origem: medido no desenho, regra com valor publicado ou da empresa, ou estimativa "
                     "(hipótese, altura standard, vão inferido). O Anexo A mostra os desenhos cotados de onde vêm as medidas."), "p"))
    story.append(PageBreak())
    # ------------------------------------------------------------------ 1 method
    story.append(P("1. " + t("Método"), "h1"))
    steps = ["Alturas: as do projeto; sem alturas na planta, RDC 3,00 m e outros pisos 2,50 m, marcadas «standard».",
             "Rede de paredes: cada extremo que encosta a outra parede vai ao eixo dela; troços alinhados sob um lintel (desenhado ou inferido de um intervalo) passam a uma peça com o vão recortado.",
             "Peças: juntas L, T e X resolvidas sem contagem dupla (num T a parede que encosta é cortada; num L ou X a mais longa passa); divisão ao formato de produção nos sistemas pré-fabricados.",
             "Quantidades: regra de cada sistema construtivo aplicada à geometria medida; cada parâmetro tem origem e fonte e é editável pela empresa.",
             "Verificações: dois métodos independentes têm de concordar dentro da tolerância (volume das peças vs união exata das plantas; área bruta − vãos vs área líquida).",
             "Preços: biblioteca da empresa, cada preço com a sua fonte; quantidades sem preço ficam listadas."]
    for i, s in enumerate(steps, 1):
        story.append(P(f"{i}. {t(s)}", "p"))
    story.append(Spacer(1, 3 * mm))
    story.append(table([hdr(t("Origem"), t("Significado"))] + [
        [origin_cell(o), P(t("origem_desc." + o))] for o in ("medido", "regra", "estimativa", "estimativa_imagem")],
        [35 * mm, 140 * mm], origin_col=0))
    # ------------------------------------------------------------------ 2 heights
    story.append(P("2. " + t("Pisos e alturas"), "h1"))
    rows = [hdr(t("Piso"), t("Leitura"), t("Altura"), t("Origem"), t("Fonte"))]
    for f in result["pisos"]:
        h = f["altura"]
        rows.append([P(f["nome"]), P(t("leitura." + f["leitura"])), P(n(h["valor_m"]) + " m"), origin_cell(h["origem"] if h["origem"] != "standard" else "estimativa"),
                     P(t(h["fonte"]))])
    story.append(table(rows, [25 * mm, 22 * mm, 18 * mm, 25 * mm, 85 * mm], origin_col=3))
    # ------------------------------------------------------------------ 3 quantities
    story.append(P("3. " + t("Quantidades por piso"), "h1"))
    for f in result["pisos"]:
        rows = [hdr(t("Designação"), t("Sistema"), t("Quantidade"), t("Un."), t("Origem"), t("Método"))]
        for r in f["linhas"]:
            rows.append([P(code_label(r["codigo"], lang)), P(t("sistema." + r["sistema"]) if r["sistema"] else "—"),
                         P(n(r["quantidade"], 0 if r["unidade"] == "un" else 2)), P(r["unidade"]), origin_cell(r["origem"]),
                         P(t(r["metodo"]) + ("".join(f"<br/><font size=6 color='#555555'>{s}</font>" for s in r["fontes"])))])
        story.append(P(f["nome"], "h2"))
        story.append(table(rows, [40 * mm, 28 * mm, 20 * mm, 10 * mm, 20 * mm, 57 * mm], origin_col=4))
    story.append(P(t("Totais do projeto"), "h2"))
    rows = [hdr(t("Designação"), t("Sistema"), t("Quantidade"), t("Un."), t("Origem"))]
    for r in result["totais"]:
        rows.append([P(code_label(r["codigo"], lang)), P(t("sistema." + r["sistema"]) if r["sistema"] else "—"),
                     P(n(r["quantidade"], 0 if r["unidade"] == "un" else 2)), P(r["unidade"]), origin_cell(r["origem"])])
    story.append(table(rows, [60 * mm, 40 * mm, 30 * mm, 15 * mm, 30 * mm], origin_col=4))
    # ------------------------------------------------------------------ 4 checks
    story.append(P("4. " + t("Verificações cruzadas"), "h1"))
    rows = [hdr(t("Piso"), t("Verificação"), t("Método A"), t("Método B"), t("Erro"), t("Resultado"))]
    for c in result["verificacoes"]:
        res = t("informativo") if c.get("informativo") else (t("dentro da tolerância") if c["passou"] else t("FORA da tolerância"))
        rows.append([P(c["piso"]), P(t("verif." + c["verificacao"]) + (f"<br/><font size=6>{t(c['nota']) if c.get('nota') else ''}</font>")),
                     P(f"{n(c['a'], 3)} {c['unidade']}"), P(f"{n(c['b'], 3)} {c['unidade']}"),
                     P("—" if c.get("erro_pct") is None else f"{n(c['erro_pct'], 3)} %"), P(res)])
    story.append(table(rows, [22 * mm, 60 * mm, 25 * mm, 25 * mm, 18 * mm, 25 * mm]))
    # ------------------------------------------------------------------ 5 estimate
    story.append(P("5. " + t("Orçamento"), "h1"))
    if budget:
        rows = [hdr(t("Designação"), t("Piso"), t("Qtd."), t("Un."), t("Preço un."), t("Total"), t("Fonte do preço"))]
        for line in budget["linhas"]:
            rows.append([P(code_label(line["codigo"], lang) + (f" · {t('sistema.' + line['sistema'])}" if line["sistema"] else "")),
                         P(line["piso"]), P(n(line["quantidade"], 0 if line["unidade"] == "un" else 2)), P(line["unidade"]),
                         P(n(line["preco_unitario"])), P(n(line["total"])), P(line["fonte_preco"])])
        story.append(table(rows, [45 * mm, 18 * mm, 16 * mm, 10 * mm, 18 * mm, 22 * mm, 46 * mm]))
        story.append(Spacer(1, 2 * mm))
        story.append(table([[P(t("Subtotal sem IVA"), "cellb"), P(n(budget["subtotal"]) + " €", "cellb")],
                            [P(f"{t('IVA')} {n(budget['iva_pct'], 1)} % · {budget['iva_fonte']}"), P(n(budget["iva"]) + " €")],
                            [P(t("Total com IVA"), "cellb"), P(n(budget["total"]) + " €", "cellb")],
                            [P(t("Parte do total que depende de estimativas")), P(n(budget["parte_estimativa"]) + " €")]],
                           [130 * mm, 45 * mm], header=False))
        if budget["sem_preco"]:
            story.append(P(t("Quantidades sem preço na biblioteca (não incluídas no total)"), "h2"))
            story.append(P(", ".join(sorted({code_label(m["codigo"], lang) + (f" ({t('sistema.' + m['sistema'])})" if m["sistema"] else "")
                                             for m in budget["sem_preco"]})), "small"))
    else:
        story.append(P(t("Sem biblioteca de preços: o dossier apresenta só as quantidades. Importe a biblioteca da empresa para obter o orçamento."), "p"))
    # ------------------------------------------------------------------ 6 hypotheses
    story.append(P("6. " + t("Hipóteses e valores standard a confirmar"), "h1"))
    rows = [hdr(t("Parâmetro"), t("Valor"), t("Origem"), t("Fonte"))]
    for h in result["hipoteses"]:
        rows.append([P(t("param." + h["chave"])), P(f"{h['valor']:g} {h['unidade']}"),
                     origin_cell("estimativa"), P(t(h["fonte"]))])
    story.append(table(rows, [55 * mm, 22 * mm, 23 * mm, 75 * mm], origin_col=2))
    story.append(P(t("Todos estes valores são editáveis pela empresa; um valor da empresa passa a «regra» com a fonte indicada."), "small"))
    # ------------------------------------------------------------------ 7 pieces
    story.append(PageBreak())
    story.append(P("7. " + t("Medições por peça"), "h1"))
    for f in result["pisos"]:
        rows = [hdr(t("Peça"), t("Sistema"), t("Comp. m"), t("Alt. m"), t("Esp. mm"), t("Líquida m²"), t("Volume m³"), t("Vãos"))]
        for p in f["analise"]["pecas"]:
            rows.append([P(p["id"]), P(t("sistema." + p["sistema"]) if p.get("sistema") else "—"), P(n(p["comprimento_m"], 3)),
                         P(n(p["altura_m"], 2)), P(f"{p['espessura_mm']:g}"), P(n(p["area_liquida_m2"], 2)), P(n(p["volume_liquido_m3"], 3)),
                         P(len(p["vaos"]))])
        story.append(KeepTogether([P(f["nome"], "h2")]))
        story.append(table(rows, [30 * mm, 32 * mm, 18 * mm, 15 * mm, 15 * mm, 22 * mm, 22 * mm, 12 * mm]))
        if f.get("vaos_inferidos"):
            story.append(P(t("Vãos inferidos de intervalos entre troços (a confirmar)") + ": " +
                           ", ".join(f"{v['ref'].replace('inferido ', '')} ({n(v['largura_m'])} m)" for v in f["vaos_inferidos"]), "small"))
    # ------------------------------------------------------------------ annex A
    networks = result["_redes"]
    meta = {f["nome"]: f"{t('altura')} {n(f['altura']['valor_m'])} m ({t('origem.' + ('estimativa' if f['altura']['origem'] == 'standard' else f['altura']['origem']))}) · "
                       f"{t('leitura.' + f['leitura'])}" for f in result["pisos"]}
    annex, sheets = desenhos.annex_pdf(networks, meta, title=result["projeto"], brand=brand, lang=lang)
    story.append(PageBreak())
    story.append(P(t("Anexo A · Desenhos cotados"), "h1"))
    story.append(P(t("Os desenhos seguintes foram gerados a partir da mesma geometria das medições: cada comprimento, altura e vão do "
                     "dossier pode ser lido neles. Cotas em milímetros, escala indicada em cada folha."), "p"))
    story.append(table([hdr(t("Folha"), t("Conteúdo"))] + [[P(f"A.{i}"), P(s)] for i, s in enumerate(sheets, 1)], [20 * mm, 155 * mm]))

    body = io.BytesIO()
    doc = SimpleDocTemplate(body, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm,
                            title=title, author=brand["nome"], subject=t("Dossier de medições e orçamento"))
    doc.build(story, onFirstPage=cover, onLaterPages=footer)
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(body.getvalue())))
    writer.append(PdfReader(io.BytesIO(annex)))
    writer.add_metadata({"/Title": title, "/Author": brand["nome"]})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
