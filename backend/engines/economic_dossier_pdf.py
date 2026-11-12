"""PDF premium do dossier económico (custo, venda, margem, meios, planeamento, cenários, hipóteses) — com a capa e as
cores da empresa (engines.pdf_premium), no mesmo formato que o dossier da conta CLT."""
from __future__ import annotations

import io

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engines.pdf_fonts import F


def _n(v, d=2):
    return f"{float(v):,.{d}f}".replace(",", " ").replace(".", ",")


def _e(v, d=0):
    return _n(v, d) + " €"


def build(r: dict, branding: dict | None = None, lang: str = "pt") -> bytes:
    from engines import pdf_premium
    fr = str(lang or "").lower().startswith("fr-") or lang == "fr_true"
    T = (lambda pt, f: f if fr else pt)
    accent = pdf_premium.cor_empresa(branding)
    acc = colors.HexColor(accent)
    soft = colors.HexColor("#F3F5F4")
    H1 = ParagraphStyle("h1", fontName=F("Helvetica-Bold"), fontSize=15, leading=19, textColor=acc, spaceAfter=4, spaceBefore=2)
    H2 = ParagraphStyle("h2", fontName=F("Helvetica-Bold"), fontSize=11, leading=14, textColor=colors.HexColor("#1f2937"), spaceBefore=8, spaceAfter=4)
    P = ParagraphStyle("p", fontName=F("Helvetica"), fontSize=8.6, leading=11.8, textColor=colors.HexColor("#374151"))
    S = ParagraphStyle("s", fontName=F("Helvetica"), fontSize=7.2, leading=9.2, textColor=colors.HexColor("#4b5563"))

    def table(rows, widths, total=None, right_from=1):
        data = rows + ([total] if total else [])
        tb = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        st = [("BACKGROUND", (0, 0), (-1, 0), acc), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("FONTNAME", (0, 0), (-1, 0), F("Helvetica-Bold")), ("FONTNAME", (0, 1), (-1, -1), F("Helvetica")),
              ("FONTSIZE", (0, 0), (-1, -1), 7.4), ("ALIGN", (right_from, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, soft]),
              ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
              ("TOPPADDING", (0, 0), (-1, -1), 2.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4)]
        if total:
            st += [("FONTNAME", (0, -1), (-1, -1), F("Helvetica-Bold")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E6ECE9"))]
        tb.setStyle(TableStyle(st))
        return tb

    def para(x):
        return Paragraph(str(x), S)

    s = []
    # ---------------- 1. síntese
    s += [Paragraph(T("Síntese económica da obra", "Synthèse économique du chantier"), H1),
          Paragraph(T(f"{r['title']}" + (f" — cliente {r['client']}" if r["client"] else "") + ". Custos calculados com as bibliotecas de "
                      "compra e de venda da empresa e com os seus recursos (mão de obra, veículos, máquinas, gasóleo, custos de estrutura).",
                      f"{r['title']}" + (f" — client {r['client']}" if r["client"] else "") + ". Coûts calculés avec les bibliothèques d'achat "
                      "et de vente de l'entreprise et ses ressources (main-d'œuvre, véhicules, engins, gazole, frais de structure)."), P),
          Spacer(1, 4)]
    kp = [[T("Venda s/ IVA", "Vente HT"), T("Custo total", "Coût total"), T("Margem", "Marge"), T("Margem %", "Marge %"), T("Duração", "Durée")],
          [_e(r["sale"]), _e(r["cost"]), _e(r["margin"]), f"{_n(r['margin_pct'], 1)} %", f"{r['days']} {T('dias', 'jours')}"]]
    kt = Table(kp, colWidths=[35 * mm] * 5)
    kt.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), F("Helvetica")), ("FONTSIZE", (0, 0), (-1, 0), 7),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6b7280")), ("FONTNAME", (0, 1), (-1, 1), F("Helvetica-Bold")),
                            ("FONTSIZE", (0, 1), (-1, 1), 12.5), ("LINEBEFORE", (0, 0), (0, -1), 3, acc),
                            ("TEXTCOLOR", (2, 1), (3, 1), colors.HexColor("#b91c1c") if r["margin"] < 0 else colors.HexColor("#1f2937")),
                            ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")), ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    s.append(kt)
    # barra de decomposição da venda
    d = Drawing(176 * mm, 26 * mm)
    parts = [(T("Custos diretos", "Coûts directs"), r["direct"], acc), (T("Estaleiro e meios", "Chantier et moyens"), r["site_total"], colors.HexColor("#6b7280")),
             (T("Estrutura", "Structure"), r["overhead"], colors.HexColor("#9ca3af")),
             (T("Margem", "Marge"), max(0.0, r["margin"]), colors.HexColor("#16a34a"))]
    tot = max(r["sale"], r["cost"]) or 1
    x = 0.0
    for lab, v, col in parts:
        w = 176 * mm * v / tot
        d.add(Rect(x, 9 * mm, w, 9 * mm, fillColor=col, strokeColor=colors.white))
        if w > 24 * mm:
            d.add(String(x + 2 * mm, 12 * mm, f"{lab} {_n(v / tot * 100, 0)} %", fontName=F("Helvetica-Bold"), fontSize=7, fillColor=colors.white))
        x += w
    d.add(String(0, 3 * mm, T("Decomposição do preço de venda", "Décomposition du prix de vente"), fontName=F("Helvetica"), fontSize=7,
                 fillColor=colors.HexColor("#6b7280")))
    s += [Spacer(1, 6), d]
    # ---------------- 2. rentabilidade por capítulo
    s.append(Paragraph(T("Rentabilidade por capítulo", "Rentabilité par lot"), H2))
    rows = [[T("Capítulo", "Lot"), T("Venda", "Vente"), T("Custos diretos", "Coûts directs"), T("Custo total", "Coût total"),
             T("Margem", "Marge"), "%"]]
    for lt in r["lots"]:
        rows.append([para(lt["lot"]), _e(lt["sale"]), _e(lt["direct"]), _e(lt["cost"]), _e(lt["margin"]), f"{_n(lt['margin_pct'], 1)} %"])
    s.append(table(rows, (62, 23, 24, 23, 23, 15), ["Total", _e(r["sale"]), _e(r["direct"]), _e(r["cost"]), _e(r["margin"]),
                                                     f"{_n(r['margin_pct'], 1)} %"]))
    hc = HorizontalBarChart()
    lots = r["lots"][:12]
    if lots:
        dh = Drawing(176 * mm, (14 + 7 * len(lots)) * mm)
        hc.x, hc.y, hc.width, hc.height = 52 * mm, 6 * mm, 118 * mm, (6 + 7 * len(lots)) * mm
        hc.data = [[lt["margin_pct"] for lt in reversed(lots)]]
        hc.categoryAxis.categoryNames = [lt["lot"][:28] for lt in reversed(lots)]
        hc.categoryAxis.labels.fontName = F("Helvetica")
        hc.categoryAxis.labels.fontSize = 6.5
        hc.valueAxis.labels.fontSize = 6.5
        hc.valueAxis.valueMin = min(0, min(lt["margin_pct"] for lt in lots) - 5)
        hc.valueAxis.valueMax = max(30, max(lt["margin_pct"] for lt in lots) + 5)
        hc.bars[0].fillColor = acc
        hc.bars.strokeColor = None
        dh.add(hc)
        dh.add(String(0, 1 * mm, T("Margem % por capítulo", "Marge % par lot") + f" — {T('objetivo', 'objectif')} {_n(r['target_margin_pct'], 0)} %",
                      fontName=F("Helvetica"), fontSize=7, fillColor=colors.HexColor("#6b7280")))
        s += [Spacer(1, 4), dh]
    # ---------------- 3. linhas
    s += [PageBreak(), Paragraph(T("Custos diretos linha a linha", "Coûts directs ligne par ligne"), H1),
          Paragraph(T("Preço de venda = orçamento (biblioteca de venda). Custo = preço de compra (custo indicado, biblioteca de compra) "
                      "ou HIPÓTESE pela margem-alvo quando falta.", "Prix de vente = devis (bibliothèque de vente). Coût = prix d'achat "
                      "(coût indiqué, bibliothèque d'achat) ou HYPOTHÈSE par la marge cible s'il manque."), P), Spacer(1, 3)]
    rows = [[T("Designação", "Désignation"), T("Qtd.", "Qté"), T("Un.", "U."), T("PU venda", "PU vente"), T("Custo un.", "Coût u."),
             T("Venda", "Vente"), T("Custo", "Coût"), T("Origem do custo", "Origine du coût")]]
    cur = None
    for l in r["lines"]:
        if l["lot"] != cur:
            cur = l["lot"]
            rows.append([para(f"<b>{cur}</b>"), "", "", "", "", "", "", ""])
        rows.append([para(l["designation"][:120]), _n(l["qty"]), l["unit"], _n(l["pu"]), _n(l["cu"]), _n(l["sale"]), _n(l["cost"]),
                     para(l["origin"] + (f" — {l['ref'][:50]}" if l["ref"] else ""))])
    s.append(table(rows, (56, 13, 9, 15, 15, 18, 18, 32)))
    # ---------------- 4. estaleiro e meios
    s += [PageBreak(), Paragraph(T("Estaleiro, equipa e meios", "Chantier, équipe et moyens"), H1)]
    res = {x["id"]: x for x in r["resources"]}
    s.append(Paragraph(T("Equipa no local: ", "Équipe sur site : ") + ", ".join(f"{n:g} × {res[k]['name']}" for k, n in r["team"].items())
                       + T(f" — duração estimada {r['days']} dias úteis (mão de obra dos custos diretos ≈ {_e(r['labour_cost'])}).",
                           f" — durée estimée {r['days']} jours ouvrés (main-d'œuvre des coûts directs ≈ {_e(r['labour_cost'])})."), P))
    rows = [[T("Meio", "Moyen"), T("Qtd.", "Qté"), T("Un.", "U."), T("Custo un.", "Coût u."), "Total", T("Origem", "Origine")]]
    for x in r["site"]:
        rows.append([para(x["item"]), _n(x["qty"], 1), x["unit"], _n(x["pu"]), _e(x["total"]),
                     T("empresa", "entreprise") if x.get("origin") == "empresa" else T("HIPÓTESE", "HYPOTHÈSE")])
    rows.append([para(T(f"Custos de estrutura ({_n(r['overhead_pct'], 0)} % do custo)", f"Frais de structure ({_n(r['overhead_pct'], 0)} % du coût)")),
                 "", "", "", _e(r["overhead"]), ""])
    s.append(table(rows, (78, 16, 10, 20, 24, 28), ["Total", "", "", "", _e(r["site_total"] + r["overhead"]), ""]))
    s.append(Paragraph(T("Recursos da empresa", "Ressources de l'entreprise"), H2))
    kind_lab = {"mao_de_obra": T("Mão de obra", "Main-d'œuvre"), "veiculo": T("Veículo", "Véhicule"), "maquina": T("Máquina", "Engin")}
    rows = [[T("Recurso", "Ressource"), T("Tipo", "Type"), T("Custo", "Coût"), T("Consumo", "Consommation"), T("Origem", "Origine")]]
    for x in r["resources"]:
        rows.append([para(x["name"]), kind_lab.get(x.get("kind"), x.get("kind", "")), f"{_n(x['cost'])} €/{x.get('unit', 'h')}",
                     f"{_n(x['consumption_l_100km'], 1)} L/100 km" if x.get("consumption_l_100km") else "—",
                     T("empresa", "entreprise") if x.get("origin") == "empresa" else T("HIPÓTESE", "HYPOTHÈSE")])
    s.append(table(rows, (70, 28, 30, 30, 18), right_from=2))
    # ---------------- 5. planeamento e curva de custos
    s += [PageBreak(), Paragraph(T("Planeamento e curva de custos", "Planning et courbe des coûts"), H1)]
    plan = r["plan"]
    if plan:
        tot_d = max(1.0, r["total_days"])
        gh = Drawing(176 * mm, (12 + 7 * len(plan)) * mm)
        x0 = 58 * mm
        wbar = 176 * mm - x0
        for i, p in enumerate(plan):
            y = (6 + 7 * (len(plan) - 1 - i)) * mm
            gh.add(String(0, y + 1.5 * mm, p["lot"][:32], fontName=F("Helvetica"), fontSize=6.8, fillColor=colors.HexColor("#374151")))
            gh.add(Rect(x0 + wbar * p["start"] / tot_d, y, max(1.5 * mm, wbar * p["days"] / tot_d), 5 * mm, fillColor=acc, strokeColor=None))
        for k in range(0, int(tot_d) + 1, max(5, int(tot_d / 8) or 5)):
            xx = x0 + wbar * k / tot_d
            gh.add(Line(xx, 4 * mm, xx, (8 + 7 * len(plan)) * mm, strokeColor=colors.HexColor("#E5E7EB"), strokeWidth=0.4))
            gh.add(String(xx, 0.5 * mm, f"{T('dia', 'j')} {k}", fontName=F("Helvetica"), fontSize=6, fillColor=colors.HexColor("#6b7280")))
        s += [gh, Spacer(1, 6)]
        # curva de custos acumulados (S): custo de cada capítulo distribuído na sua duração
        steps = 40
        cum, pts = 0.0, []
        lot_cost = {lt["lot"]: lt["cost"] for lt in r["lots"]}
        for k in range(steps + 1):
            t = tot_d * k / steps
            c = 0.0
            for p in plan:
                f_ = min(1.0, max(0.0, (t - p["start"]) / p["days"])) if p["days"] else 1.0
                c += lot_cost.get(p["lot"], 0) * f_
            pts.append((t, c))
        cmax = max(c for _t, c in pts) or 1
        ch = Drawing(176 * mm, 55 * mm)
        ox, oy, W_, H_ = 14 * mm, 8 * mm, 158 * mm, 42 * mm
        ch.add(Rect(ox, oy, W_, H_, fillColor=colors.HexColor("#FAFAF9"), strokeColor=colors.HexColor("#E5E7EB")))
        ch.add(PolyLine([v for t, c in pts for v in (ox + W_ * t / tot_d, oy + H_ * c / cmax)], strokeColor=acc, strokeWidth=1.6))
        sale_y = oy + H_ * min(1.0, r["sale"] / cmax) if r["sale"] <= cmax * 1.0 else oy + H_
        ch.add(Line(ox, sale_y, ox + W_, sale_y, strokeColor=colors.HexColor("#16a34a"), strokeDashArray=[3, 2], strokeWidth=0.8))
        ch.add(String(ox, oy + H_ + 2 * mm, T(f"Custo acumulado (máx. {_e(cmax)}) — linha verde: venda {_e(r['sale'])}",
                                              f"Coût cumulé (max. {_e(cmax)}) — ligne verte : vente {_e(r['sale'])}"),
                      fontName=F("Helvetica"), fontSize=7, fillColor=colors.HexColor("#374151")))
        s.append(ch)
    # ---------------- 6. cenários
    s.append(Paragraph(T("Cenários de sensibilidade", "Scénarios de sensibilité"), H2))
    rows = [[T("Cenário", "Scénario"), T("Venda", "Vente"), T("Custo", "Coût"), T("Margem", "Marge"), "%"]]
    for sc in r["scenarios"]:
        rows.append([sc["label"], _e(sc["sale"]), _e(sc["cost"]), _e(sc["margin"]), f"{_n(sc['margin_pct'], 1)} %"])
    s.append(table(rows, (70, 26, 26, 26, 18)))
    # ---------------- 7. hipóteses
    s.append(Paragraph(T("Hipóteses e origem dos valores", "Hypothèses et origine des valeurs"), H2))
    for h in r["hypotheses"]:
        s.append(Paragraph("• " + h, P))
    s.append(Spacer(1, 3))
    s.append(Paragraph(T("Valores « empresa » = introduzidos pela empresa (bibliotecas e recursos). Valores HIPÓTESE = por defeito, a substituir "
                         "antes de usar este dossier para decidir um preço. Documento interno — não enviar ao cliente.",
                         "Valeurs « entreprise » = saisies par l'entreprise (bibliothèques et ressources). Valeurs HYPOTHÈSE = par défaut, à "
                         "remplacer avant de décider un prix. Document interne — ne pas envoyer au client."), S))
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=r["title"], author="ConstruPilot")
    doc.build(s)
    lg = "fr" if fr else "pt"
    capa = {"tipo": T("Dossier económico — documento interno", "Dossier économique — document interne"),
            "titulo": r["title"] or T("Dossier económico", "Dossier économique"),
            "subtitulo": T("Quanto custa, quanto se vende e a margem — bibliotecas de compra e venda e recursos da empresa",
                           "Combien ça coûte, combien on vend et la marge — bibliothèques d'achat et de vente et ressources de l'entreprise"),
            "local": r["client"], "data": "",
            "kpis": [(T("Venda s/ IVA", "Vente HT"), *pdf_premium._eur(r["sale"], lg)), (T("Custo total", "Coût total"), *pdf_premium._eur(r["cost"], lg)),
                     (T("Margem", "Marge"), *pdf_premium._eur(r["margin"], lg)), (T("Margem %", "Marge %"), _n(r["margin_pct"], 1), "%"),
                     (T("Duração", "Durée"), str(r["days"]), T("dias úteis", "jours ouvrés")),
                     (T("Capítulos", "Lots"), str(len(r["lots"])), ""),
                     (T("Linhas a confirmar", "Lignes à confirmer"), str(r["hyp_lines"]), T("custo por hipótese", "coût par hypothèse"))],
            "indice": [T("Síntese económica da obra", "Synthèse économique du chantier"), T("Rentabilidade por capítulo", "Rentabilité par lot"),
                       T("Custos diretos linha a linha", "Coûts directs ligne par ligne"), T("Estaleiro, equipa e meios", "Chantier, équipe et moyens"),
                       T("Recursos da empresa", "Ressources de l'entreprise"), T("Planeamento e curva de custos", "Planning et courbe des coûts"),
                       T("Cenários de sensibilidade", "Scénarios de sensibilité"), T("Hipóteses e origem dos valores", "Hypothèses et origine des valeurs")]}
    return pdf_premium.acabar(buf.getvalue(), capa, branding, lg, paginas="completo")
