"""Dossier PDF do estudo LSF — nota (A4) + desenhos de fabrico (A3) + acabamento premium (capa, logótipo, cores da empresa).

Rastreio do que foi calculado: cada parede tem o seu alçado com TODAS as peças numeradas (o mesmo ID da lista de corte, do
Excel e do visualizador 3D), a tabela das peças ao lado e as placas com o número de parafusos contados; a planta de cada piso
identifica as paredes; cada asna e cada zona de piso são desenhadas com as peças cotadas.
"""
from __future__ import annotations

import io
import math
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .defaults import REGRAS_FONTE
from .i18n import num, t

_FONTS = False


def _fonts():
    global _FONTS
    if _FONTS:
        return
    from engines.bet_core.brand import FONTS
    for nm, fn in (("LSF-R", "Inter_400Regular.ttf"), ("LSF-M", "Inter_500Medium.ttf"), ("LSF-B", "Inter_700Bold.ttf"),
                   ("LSF-T", "BarlowSemiCondensed_700Bold.ttf")):
        try:
            pdfmetrics.registerFont(TTFont(nm, str(FONTS / fn)))
        except Exception:  # noqa: BLE001
            pass
    _FONTS = True


TX = {
    "sumario": ("Síntese", "Synthèse", "Summary", "Підсумок"),
    "hip": ("Hipóteses adotadas (a validar)", "Hypothèses retenues (à valider)", "Assumptions (to be validated)", "Прийняті припущення (перевірити)"),
    "avisos": ("Pontos a verificar", "Points à vérifier", "Items to check", "Пункти для перевірки"),
    "mapa": ("Mapa de quantidades", "Métré quantitatif", "Bill of quantities", "Відомість кількостей"),
    "corte": ("Lista de corte (comprimentos de fabrico)", "Liste de débit (longueurs de fabrication)", "Cutting list (fabrication lengths)",
              "Специфікація різання (довжини виготовлення)"),
    "regras": ("Regras de fixação aplicadas", "Règles de fixation appliquées", "Fixing rules applied", "Застосовані правила кріплення"),
    "placas": ("Planos de corte das placas", "Plans de calepinage des panneaux", "Board cutting plans", "Плани розкрою плит"),
    "render": ("Estrutura LSF montada", "Ossature LSF montée", "Assembled LSF frame", "Змонтований каркас LSF"),
    "alcado": ("Alçado de fabrico", "Élévation de fabrication", "Fabrication elevation", "Фасад виготовлення"),
    "planta": ("Planta das paredes", "Plan des murs", "Wall plan", "План стін"),
    "asna": ("Asna tipo", "Ferme type", "Typical truss", "Типова ферма"),
    "piso": ("Estrutura do piso", "Structure du plancher", "Floor framing", "Конструкція перекриття"),
    "total": ("Total", "Total", "Total", "Разом"),
    "sem_preco": ("a orçamentar", "à chiffrer", "to be priced", "до розрахунку"),
    "origem": ("origem do preço", "origine du prix", "price source", "джерело ціни"),
}
_IDX = {"pt": 0, "fr": 1, "en": 2, "uk": 3}


def tx(k, lang):
    return TX[k][_IDX.get(lang, 0)]


def _hex(c):
    if isinstance(c, (tuple, list)):
        return colors.Color(*c[:3])
    c = (c or "#203B2D").lstrip("#")
    return colors.Color(int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255)


def _styles(acc, lang):
    tf = "LSF-B" if lang == "uk" else "LSF-T"
    return {
        "h1": ParagraphStyle("h1", fontName=tf, fontSize=17, leading=21, textColor=acc, spaceBefore=6, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName=tf, fontSize=12.5, leading=16, textColor=acc, spaceBefore=10, spaceAfter=4),
        "p": ParagraphStyle("p", fontName="LSF-R", fontSize=8.6, leading=11.6, textColor=colors.HexColor("#1d2630")),
        "s": ParagraphStyle("s", fontName="LSF-R", fontSize=7.4, leading=9.4, textColor=colors.HexColor("#4a5560")),
        "b": ParagraphStyle("b", fontName="LSF-B", fontSize=8.6, leading=11.6),
        "warn": ParagraphStyle("w", fontName="LSF-M", fontSize=8.2, leading=11, textColor=colors.HexColor("#9a3d0a")),
    }


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _tbl(data, widths, acc, num_cols=(), font=7.4, zebra=True):
    st = [("FONT", (0, 0), (-1, -1), "LSF-R", font), ("FONT", (0, 0), (-1, 0), "LSF-B", font),
          ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("BACKGROUND", (0, 0), (-1, 0), acc),
          ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#dfe4e9")),
          ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]
    for c in num_cols:
        st.append(("ALIGN", (c, 1), (c, -1), "RIGHT"))
    if zebra:
        for i in range(1, len(data)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f5f7f8")))
    tb = Table(data, colWidths=widths, repeatRows=1)
    tb.setStyle(TableStyle(st))
    return tb


# ---------------------------------------------------------------------------------------------------------------- nota
def nota(res: dict, lin: list[dict], tot: dict | None, lang: str = "pt", accent="#203B2D", empresa: str | None = None,
         renders: list | None = None, titulo: str | None = None) -> bytes:
    _fonts()
    acc = _hex(accent)
    S = _styles(acc, lang)
    buf = io.BytesIO()
    W, H = A4

    def deco(c, d):
        c.saveState()
        c.setFont("LSF-R", 7)
        c.setFillColor(colors.HexColor("#6b7680"))
        c.drawString(18 * mm, 10 * mm, (empresa + " · " if empresa else "") + (titulo or res.get("nome") or "LSF")[:90])
        c.drawRightString(W - 18 * mm, 10 * mm, f"{d.page}")
        c.setStrokeColor(acc)
        c.setLineWidth(0.6)
        c.line(18 * mm, 13 * mm, W - 18 * mm, 13 * mm)
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=titulo or res.get("nome") or "LSF", author=empresa or "ConstruPilot")
    E = []
    e = res["estudo"]
    E.append(Paragraph(_esc(titulo or res.get("nome") or t("titulo", lang)), S["h1"]))
    E.append(Paragraph(_esc(t("titulo", lang)) + f" · {date.today().strftime('%d/%m/%Y')}", S["s"]))
    E.append(Spacer(1, 3 * mm))
    E.append(Paragraph(_esc(t("pre", lang)), S["warn"]))
    E.append(Paragraph(tx("sumario", lang), S["h2"]))
    k = [[t("kg_aco", lang), f"{num(e['kgAco'], 0, lang)} kg"], [t("pecas", lang), num(e["nMembros"], 0, lang)],
         [t("parafusos", lang), num(e["nParafusos"], 0, lang)]]
    if e.get("kgPorM2"):
        k.append([t("kg_m2", lang), f"{num(e['kgPorM2'], 1, lang)} kg/m²"])
    for g, v in (e.get("kgPorGrupo") or {}).items():
        k.append([f"{t('kg_aco', lang)} — {t(g, lang)}", f"{num(v, 0, lang)} kg"])
    for p in res["placasResumo"]:
        k.append([p["nome"], f"{p['un']} un · {num(p['area'], 1, lang)} m²"])
    if tot:
        k.append([tx("total", lang) + " (" + ", ".join(f"{o}: {num(v, 2, lang)} €" for o, v in tot["por_origem"].items() if v) + ")",
                  f"{num(tot['total'], 2, lang)} €" + (f" + {tot['linhas_sem_preco']} {tx('sem_preco', lang)}" if tot["linhas_sem_preco"] else "")])
    E.append(_tbl([["", ""]] + k, [110 * mm, 64 * mm], acc, (1,), 8))
    if renders:
        nm, png = renders[0]
        im = Image(io.BytesIO(png), width=174 * mm, height=174 * mm * 9 / 16)
        E.append(Spacer(1, 4 * mm))
        E.append(KeepTogether([Paragraph(tx("render", lang), S["h2"]), im]))
    E.append(Paragraph(tx("hip", lang), S["h2"]))
    for h in res.get("hipoteses") or []:
        E.append(Paragraph("• " + _esc(h), S["p"]))
    E.append(Paragraph("• Perfis, espessuras, espaçamentos, ancoragens e regras de fixação: parâmetros do projeto (ver « "
                       + tx("regras", lang) + " »); a verificação estrutural (EN 1993-1-3, EN 1998-1) é do projeto de estabilidade.", S["p"]))
    if res.get("avisos"):
        E.append(Paragraph(tx("avisos", lang), S["h2"]))
        for a in res["avisos"][:80]:
            E.append(Paragraph("• " + _esc(a), S["warn"]))
    E.append(PageBreak())
    # mapa de quantidades
    E.append(Paragraph(tx("mapa", lang), S["h1"]))
    cats = []
    for l in lin:
        if l["cat"] not in cats:
            cats.append(l["cat"])
    for c in cats:
        rows = [["Código", "Designação", "Un.", "Quant.", "P. unit.", "Total"]]
        sub = 0.0
        for l in (x for x in lin if x["cat"] == c):
            pr = l.get("preco")
            orig = {"biblioteca": "B", "projeto": "P", "mercado": "M*"}.get((pr or {}).get("origem"), "")
            rows.append([Paragraph(_esc(l["code"]), S["s"]), Paragraph(_esc(l["designacao"]) + (f"<br/><font size=6.4 color='#5f6b77'>{_esc(l['detalhe'])}</font>" if l.get("detalhe") else ""), S["s"]),
                         l["un"], num(l["qtd"], 0 if l["un"] == "un" else 2, lang),
                         (num(pr["unit"], 2, lang) + " " + orig) if pr else tx("sem_preco", lang),
                         num(l["total"], 2, lang) if l.get("total") is not None else "—"])
            sub += l.get("total") or 0
        rows.append(["", Paragraph(f"<b>{_esc(c[2:].strip() if c[:2].strip().isdigit() else c)}</b>", S["s"]), "", "", "", num(sub, 2, lang) if sub else "—"])
        E.append(Paragraph(_esc(c.split(" ", 1)[1] if " " in c else c), S["h2"]))
        E.append(_tbl(rows, [30 * mm, 82 * mm, 9 * mm, 18 * mm, 18 * mm, 17 * mm], acc, (3, 4, 5), 7))
    E.append(Spacer(1, 2 * mm))
    E.append(Paragraph("B = biblioteca de preços da empresa · P = preço do projeto · M* = preço de mercado encontrado online, A ANALISAR "
                       "(fonte e data no Excel) · « a orçamentar » = sem preço na biblioteca: a linha conta no mapa mas não no total.", S["s"]))
    E.append(PageBreak())
    # lista de corte
    E.append(Paragraph(tx("corte", lang), S["h1"]))
    for p in res["perfis"]:
        rows = [["Peça", "Comprimento (mm)", "Qtd.", "IDs"]]
        for c in p["cortes"]:
            ids = ", ".join(c["ids"][:30]) + (" …" if len(c["ids"]) > 30 else "")
            rows.append([t(c["tipoPeca"], lang), num(c["L"], 1, lang), str(c["n"]), Paragraph(_esc(ids), S["s"])])
        E.append(Paragraph(f"{_esc(p['perfil'])} — {p['pecas']} peças · {num(p['metros'], 1, lang)} m · {num(p['kg'], 0, lang)} kg · "
                           f"{p['barras']} barras de {res.get('barraComercial', 6000)} mm" + (f" (+{p['pecasMaioresQueBarra']} peças > barra: perfiladora ou emenda)"
                                                                                               if p["pecasMaioresQueBarra"] else ""), S["h2"]))
        E.append(_tbl(rows, [46 * mm, 26 * mm, 12 * mm, 90 * mm], acc, (1, 2), 7))
    E.append(PageBreak())
    # regras
    E.append(Paragraph(tx("regras", lang), S["h1"]))
    rg = res.get("regras") or {}
    rows = [["Regra", "Valor", "Origem"]]
    for k_, v in rg.items():
        if k_ == "parafusoAco":
            continue
        rows.append([k_, str(v), Paragraph(_esc(REGRAS_FONTE.get(k_, "Parâmetro do projeto")), S["s"])])
    rows.append(["placas", "—", Paragraph(_esc(REGRAS_FONTE["placas"]), S["s"])])
    E.append(_tbl(rows, [40 * mm, 20 * mm, 114 * mm], acc, (1,), 7.4))
    E.append(Paragraph(tx("placas", lang), S["h2"]))
    rows = [["Placa", "Formato (mm)", "Peças", "Placas a comprar", "Desperdício"]]
    for c in res["planosCorte"]:
        pl = next((p for p in res["placasResumo"] if p["placa"] == c["chave"]), None)
        rows.append([c["nome"], f"{c['W']}×{c['H']}", str(c["pecas"]), str(len(c["folhas"])),
                     (num(pl["desperdicio"] * 100, 1, lang) + " %") if pl else "—"])
    E.append(_tbl(rows, [64 * mm, 26 * mm, 18 * mm, 30 * mm, 24 * mm], acc, (2, 3, 4), 7.4))
    doc.build(E, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


# --------------------------------------------------------------------------------------------------- desenhos (A3)
COR = {"Montante": "#5b84ad", "rei": "#2f5f8f", "apoio": "#2f5f8f", "curto": "#86a9cc", "Verga": "#c9772b", "Guia de verga": "#c9772b",
       "peitoril": "#b08a5a", "Guia": "#a9b6c3", "Bloqueador": "#8c9aa6", "Fita": "#c0392b"}


def _cor(tp):
    for k in ("rei", "apoio", "curto", "Guia de verga", "peitoril", "Verga", "Fita", "Bloqueador", "Guia", "Montante"):
        if k in tp:
            return colors.HexColor(COR[k])
    return colors.HexColor("#888888")


def _cartucho(c, W, H, acc, titulo, sub, empresa, folha, lang):
    c.setStrokeColor(acc)
    c.setLineWidth(1.2)
    c.rect(10 * mm, 10 * mm, W - 20 * mm, H - 20 * mm)
    bx = W - 10 * mm - 150 * mm
    c.setFillColor(acc)
    c.rect(bx, 10 * mm, 150 * mm, 22 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("LSF-B", 10.5)
    c.drawString(bx + 4 * mm, 25 * mm, titulo[:70])
    c.setFont("LSF-R", 7.5)
    c.drawString(bx + 4 * mm, 19.5 * mm, sub[:95])
    c.drawString(bx + 4 * mm, 14.5 * mm, ((empresa + " · ") if empresa else "") + f"{date.today().strftime('%d/%m/%Y')} · " + folha)
    c.setFillColor(colors.HexColor("#9a3d0a"))
    c.setFont("LSF-M", 6.8)
    c.drawString(14 * mm, 13 * mm, t("pre", lang)[:150])


def _alcado(c, res, w, acc, empresa, folha, lang, membros_por_id, placas):
    W, H = landscape(A3)
    _cartucho(c, W, H, acc, f"{tx('alcado', lang)} — {w['id']}" + (f" ({w.get('nivel')})" if w.get("nivel") else ""),
              f"{num(w['L'], 0, lang)} × {num(w['H'], 0, lang)} mm · {len(w['membros'])} peças · vista da face B → A", empresa, folha, lang)
    mem = [membros_por_id[i] for i in w["membros"] if i in membros_por_id and membros_por_id[i].get("elev")]
    area_w, area_h = W - 20 * mm - 140 * mm - 20 * mm, H - 20 * mm - 50 * mm
    xmin = min([0] + [p["cell"]["x0"] for p in placas])
    xmax = max([w["L"]] + [p["cell"]["x1"] for p in placas])
    htot = max([w["H"]] + [p["cell"]["z1"] for p in placas])
    s = min(area_w / (xmax - xmin), area_h / htot)
    ox = 20 * mm - xmin * s + (area_w - (xmax - xmin) * s) / 2
    oz = 50 * mm + (area_h - htot * s) / 2

    def X(x):
        return ox + x * s

    def Z(z):
        return oz + z * s

    for p in placas:
        c.setFillColor(colors.HexColor("#f6ead2"))
        c.setStrokeColor(colors.HexColor("#c9b089"))
        c.setLineWidth(0.4)
        for r in p["pecas"]:
            c.rect(X(r["x0"]), Z(r["z0"]), (r["x1"] - r["x0"]) * s, (r["z1"] - r["z0"]) * s, fill=1, stroke=0)
        c.rect(X(p["cell"]["x0"]), Z(p["cell"]["z0"]), (p["cell"]["x1"] - p["cell"]["x0"]) * s, (p["cell"]["z1"] - p["cell"]["z0"]) * s, fill=0, stroke=1)
        c.setFillColor(colors.HexColor("#8a6a2c"))
        c.setFont("LSF-R", 6)
        c.drawCentredString(X((p["cell"]["x0"] + p["cell"]["x1"]) / 2), Z(p["cell"]["z1"]) - 8, f"{p['parafusos']} paraf.")
    for m in sorted(mem, key=lambda m: -(m["elev"]["z1"] - m["elev"]["z0"])):
        e = m["elev"]
        c.setFillColor(_cor(m["tipoPeca"]))
        c.setStrokeColor(colors.HexColor("#1d2b38"))
        c.setLineWidth(0.3)
        c.rect(X(e["x0"]), Z(e["z0"]), max((e["x1"] - e["x0"]) * s, 0.6), max((e["z1"] - e["z0"]) * s, 0.6), fill=1, stroke=1)
    c.setFont("LSF-B", 5.2)
    for m in mem:
        e = m["elev"]
        tag = m["id"].split("-")[-1]
        c.setFillColor(colors.HexColor("#0d1a26"))
        if (e["z1"] - e["z0"]) > (e["x1"] - e["x0"]):
            c.saveState()
            c.translate(X((e["x0"] + e["x1"]) / 2) + 1.8, Z((e["z0"] + e["z1"]) / 2))
            c.rotate(90)
            c.drawCentredString(0, 0, tag)
            c.restoreState()
        else:
            c.drawCentredString(X((e["x0"] + e["x1"]) / 2), Z(e["z1"]) + 1.5, tag)
    for a in w["aberturas"]:
        c.setStrokeColor(colors.HexColor("#d9590b"))
        c.setDash(3, 2)
        c.setLineWidth(0.8)
        c.rect(X(a["x0"]), Z(a["z0"]), (a["x1"] - a["x0"]) * s, (a["z1"] - a["z0"]) * s)
        c.setDash()
        c.setFillColor(colors.HexColor("#d9590b"))
        c.setFont("LSF-M", 6.5)
        c.drawCentredString(X((a["x0"] + a["x1"]) / 2), Z((a["z0"] + a["z1"]) / 2), f"{a.get('id') or ''} {num(a['x1'] - a['x0'], 0, lang)}×{num(a['z1'] - a['z0'], 0, lang)}")
    # cotas acumuladas dos montantes inteiros
    xs = sorted({round((m["elev"]["x0"] + m["elev"]["x1"]) / 2, 1) for m in mem if m["tipoPeca"].startswith("Montante") and "curto" not in m["tipoPeca"]})
    yc = oz - 9 * mm
    c.setStrokeColor(colors.HexColor("#5f6b77"))
    c.setLineWidth(0.3)
    c.line(X(0), yc, X(w["L"]), yc)
    c.setFont("LSF-R", 5.2)
    c.setFillColor(colors.HexColor("#5f6b77"))
    for x in xs:
        c.line(X(x), yc - 2, X(x), yc + 2)
        c.saveState()
        c.translate(X(x) + 1.5, yc - 3)
        c.rotate(-90)
        c.drawString(0, 0, num(x, 0, lang))
        c.restoreState()
    # tabela de peças
    tx0 = W - 10 * mm - 140 * mm
    ty = H - 16 * mm
    c.setFillColor(acc)
    c.setFont("LSF-B", 8)
    c.drawString(tx0, ty, "ID   ·   peça   ·   perfil   ·   L (mm)")
    ty -= 4 * mm
    c.setFont("LSF-R", 6.2)
    grupos = {}
    for m in mem:
        grupos.setdefault((m["tipoPeca"], m["perfilNome"], m["L"]), []).append(m["id"].split("-")[-1])
    for (tp, pf, L), ids in sorted(grupos.items(), key=lambda kv: (kv[0][0], -kv[0][2])):
        txt = f"{','.join(ids)}  {t(tp, lang)}  {pf}  {num(L, 1, lang)}  ×{len(ids)}"
        while txt and ty > 36 * mm:
            c.setFillColor(colors.HexColor("#1d2630"))
            c.drawString(tx0, ty, txt[:118])
            txt = ("   " + txt[118:]) if len(txt) > 118 else ""
            ty -= 3.1 * mm
    c.showPage()


def _planta(c, res, nivel, paredes, acc, empresa, folha, lang):
    W, H = landscape(A3)
    _cartucho(c, W, H, acc, f"{tx('planta', lang)} — {nivel}", f"{len(paredes)} paredes · eixos e IDs = alçados de fabrico", empresa, folha, lang)
    pts = []
    for w in paredes:
        for x, y in ((0, w["y0"]), (w["L"], w["y0"]), (0, w["y0"] + w["Dt"]), (w["L"], w["y0"] + w["Dt"])):
            pts.append((w["A"][0] + x * w["d"][0] + y * w["n"][0], w["A"][1] + x * w["d"][1] + y * w["n"][1]))
    if not pts:
        c.showPage()
        return
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
    y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    s = min((W - 60 * mm) / max(x1 - x0, 1), (H - 80 * mm) / max(y1 - y0, 1))
    ox, oy = 30 * mm - x0 * s, 50 * mm - y0 * s
    for w in paredes:
        q = []
        for x, y in ((0, w["y0"]), (w["L"], w["y0"]), (w["L"], w["y0"] + w["Dt"]), (0, w["y0"] + w["Dt"])):
            q.append((ox + (w["A"][0] + x * w["d"][0] + y * w["n"][0]) * s, oy + (w["A"][1] + x * w["d"][1] + y * w["n"][1]) * s))
        p = c.beginPath()
        p.moveTo(*q[0])
        for a in q[1:]:
            p.lineTo(*a)
        p.close()
        c.setFillColor(acc if w.get("perimetro") else colors.HexColor("#c9772b"))
        c.setStrokeColor(colors.HexColor("#1d2b38"))
        c.setLineWidth(0.3)
        c.drawPath(p, fill=1, stroke=1)
        for a in w["aberturas"]:
            ym = w["y0"] + w["Dt"] / 2
            a0 = (ox + (w["A"][0] + a["x0"] * w["d"][0] + ym * w["n"][0]) * s, oy + (w["A"][1] + a["x0"] * w["d"][1] + ym * w["n"][1]) * s)
            a1 = (ox + (w["A"][0] + a["x1"] * w["d"][0] + ym * w["n"][0]) * s, oy + (w["A"][1] + a["x1"] * w["d"][1] + ym * w["n"][1]) * s)
            c.setStrokeColor(colors.HexColor("#d9590b"))
            c.setLineWidth(2.2)
            c.line(*a0, *a1)
        mx = w["A"][0] + w["d"][0] * w["L"] / 2 + w["n"][0] * (w["y0"] + w["Dt"] / 2 + 450)
        my = w["A"][1] + w["d"][1] * w["L"] / 2 + w["n"][1] * (w["y0"] + w["Dt"] / 2 + 450)
        c.setFillColor(colors.HexColor("#0d1a26"))
        c.setFont("LSF-B", 7)
        c.drawCentredString(ox + mx * s, oy + my * s, w["id"])
    c.showPage()


def _asna(c, res, acc, empresa, folha, lang):
    W, H = landscape(A3)
    mem = [m for m in res["membros"] if m["grupo"] == "Cobertura"]
    if not mem:
        return
    tag = mem[0]["asna"]
    am = [m for m in mem if m["asna"] == tag]
    cob = res["coberturas"][0]
    _cartucho(c, W, H, acc, f"{tx('asna', lang)} — {cob['id']}", f"Fink · vão {num(cob['S'], 0, lang)} mm · {cob['inclinacao']}° · {cob['n']} asnas", empresa, folha, lang)
    # projeção no plano (s, z): eixo do vão perpendicular ao plano da asna
    u = am[0]["u"]
    sd = [-u[1], u[0], 0] if abs(u[2]) < 0.5 else [1, 0, 0]
    pts = []
    for m in am:
        for k_ in (0, 1):
            for vv in (0, 1):
                P = [m["o"][i] + m["w"][i] * m["L"] * k_ + m["v"][i] * m["sec"]["h"] * vv for i in range(3)]
                pts.append((P[0] * sd[0] + P[1] * sd[1], P[2]))
    s0, s1 = min(p[0] for p in pts), max(p[0] for p in pts)
    z0, z1 = min(p[1] for p in pts), max(p[1] for p in pts)
    s = min((W - 60 * mm) / (s1 - s0), (H - 90 * mm) / (z1 - z0))
    ox, oz = 30 * mm - s0 * s, 60 * mm - z0 * s
    for m in am:
        q = []
        for k_, vv in ((0, 0), (1, 0), (1, 1), (0, 1)):
            P = [m["o"][i] + m["w"][i] * m["L"] * k_ + m["v"][i] * m["sec"]["h"] * vv for i in range(3)]
            q.append((ox + (P[0] * sd[0] + P[1] * sd[1]) * s, oz + P[2] * s))
        p = c.beginPath()
        p.moveTo(*q[0])
        for a in q[1:]:
            p.lineTo(*a)
        p.close()
        c.setFillColor(colors.HexColor("#a98fcf" if m["tipoPeca"] == "Diagonal" else "#7a5ea8"))
        c.setStrokeColor(colors.HexColor("#1d2b38"))
        c.setLineWidth(0.4)
        c.drawPath(p, fill=1, stroke=1)
        cx = sum(a[0] for a in q) / 4
        cy = sum(a[1] for a in q) / 4
        c.setFillColor(colors.HexColor("#0d1a26"))
        c.setFont("LSF-B", 7.5)
        c.drawCentredString(cx, cy + 6, f"{m['id'].split('.')[-1]} · {m['perfilNome']} · {num(m['L'], 1, lang)} mm")
    c.showPage()


def desenhos(res: dict, lang="pt", accent="#203B2D", empresa=None, max_alcados: int = 80) -> bytes:
    _fonts()
    acc = _hex(accent)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A3))
    mid = {m["id"]: m for m in res["membros"]}
    folhas = []
    niveis = []
    for w in res["paredes"]:
        nv = w.get("nivel") or "—"
        if nv not in niveis:
            niveis.append(nv)
    n_total = len(niveis) + min(len(res["paredes"]), max_alcados) + (1 if res["coberturas"] else 0)
    k = 0
    for nv in niveis:
        k += 1
        _planta(c, res, nv, [w for w in res["paredes"] if (w.get("nivel") or "—") == nv], acc, empresa, f"folha {k}/{n_total}", lang)
    for w in res["paredes"][:max_alcados]:
        k += 1
        pl = [p for p in res["placas"] if p["ref"] == w["id"] and p["grupo"] == "Paredes" and p["camada"] == 1
              and (p["face"] in ("exterior", "face B"))]
        _alcado(c, res, w, acc, empresa, f"folha {k}/{n_total}", lang, mid, pl)
    if res["coberturas"]:
        k += 1
        _asna(c, res, acc, empresa, f"folha {k}/{n_total}", lang)
    c.save()
    return buf.getvalue()


def capa(res: dict, br, lang="pt", renders=None, titulo=None, tot=None) -> bytes:
    """Capa A4: marca da empresa (logótipo, nome, cor), título, render da estrutura montada e 4 indicadores-chave."""
    _fonts()
    W, H = A4
    acc = br.accent
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFillColor(acc)
    c.rect(0, H - 92 * mm, W, 92 * mm, fill=1, stroke=0)
    x = 18 * mm
    if br.logo is not None:
        hh = 18 * mm
        ww = min(hh * br.logo_ratio, 70 * mm)
        c.setFillColor(colors.white)
        c.roundRect(x - 3 * mm, H - 32 * mm - 3 * mm, ww + 6 * mm, hh + 6 * mm, 2 * mm, fill=1, stroke=0)
        c.drawImage(br.logo, x, H - 32 * mm, ww, hh, mask="auto", preserveAspectRatio=True)
    c.setFillColor(colors.white)
    c.setFont("LSF-B", 11)
    c.drawString(x, H - 44 * mm, (br.name or "ConstruPilot")[:70])
    c.setFont("LSF-B" if lang == "uk" else "LSF-T", 25)
    tt = titulo or res.get("nome") or t("titulo", lang)
    linhas_t, cur = [], ""
    for wd in tt.split():
        if c.stringWidth(cur + " " + wd, "LSF-T", 25) > W - 36 * mm and cur:
            linhas_t.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    linhas_t.append(cur)
    y = H - 58 * mm
    for l in linhas_t[:2]:
        c.drawString(x, y, l)
        y -= 10 * mm
    c.setFont("LSF-R", 10)
    c.drawString(x, y - 1 * mm, t("titulo", lang)[:95])
    if renders:
        img = ImageReader(io.BytesIO(renders[0][1]))
        iw = W - 36 * mm
        ih = iw * 9 / 16
        c.drawImage(img, x, H - 100 * mm - ih, iw, ih)
        ytop = H - 108 * mm - ih
    else:
        ytop = H - 110 * mm
    e = res["estudo"]
    kp = [(t("kg_aco", lang), num(e["kgAco"], 0, lang), "kg"), (t("pecas", lang), num(e["nMembros"], 0, lang), ""),
          (t("parafusos", lang), num(e["nParafusos"], 0, lang), ""), (t("kg_m2", lang), num(e["kgPorM2"] or 0, 1, lang), "kg/m²")]
    if tot and tot.get("total"):
        kp[3] = (tx("total", lang), num(tot["total"], 0, lang), "€" + (" *" if tot["linhas_sem_preco"] else ""))
    bw = (W - 36 * mm - 3 * 4 * mm) / 4
    for i, (lab, val, un) in enumerate(kp):
        bx = x + i * (bw + 4 * mm)
        c.setFillColor(colors.HexColor("#f4f6f7"))
        c.rect(bx, ytop - 26 * mm, bw, 26 * mm, fill=1, stroke=0)
        c.setFillColor(acc)
        c.rect(bx, ytop - 26 * mm, 1.4 * mm, 26 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#5f6b77"))
        c.setFont("LSF-R", 8)
        c.drawString(bx + 4 * mm, ytop - 7 * mm, lab[:28])
        c.setFillColor(colors.HexColor("#16202a"))
        c.setFont("LSF-B", 17)
        c.drawString(bx + 4 * mm, ytop - 16 * mm, val)
        c.setFont("LSF-R", 8)
        c.setFillColor(colors.HexColor("#5f6b77"))
        c.drawString(bx + 4 * mm, ytop - 22 * mm, un)
    c.setFillColor(colors.HexColor("#9a3d0a"))
    c.setFont("LSF-M", 7.6)
    c.drawString(x, 24 * mm, t("pre", lang)[:140])
    c.setFillColor(colors.HexColor("#5f6b77"))
    c.setFont("LSF-R", 7.6)
    c.drawString(x, 18 * mm, f"{date.today().strftime('%d/%m/%Y')} · " + " · ".join(br.lines[:2])[:120])
    c.drawRightString(W - 18 * mm, 18 * mm, "ConstruPilot")
    c.showPage()
    c.save()
    return buf.getvalue()


def dossier(res: dict, lin: list[dict], tot: dict | None, lang="pt", branding: dict | None = None, renders=None, titulo=None) -> bytes:
    """Nota + desenhos + acabamento premium (capa, logótipo da empresa em todas as páginas, marca d'água, marcadores)."""
    import pymupdf
    from engines.bet_core.brand import from_branding
    br = from_branding(branding, res.get("country", "PT"))
    accent = "#" + br.hex
    empresa = br.name if br.is_client else None
    n = nota(res, lin, tot, lang, accent, empresa, renders, titulo)
    d = desenhos(res, lang, accent, empresa)
    out = pymupdf.open(stream=n, filetype="pdf")
    n_nota = out.page_count
    out.insert_pdf(pymupdf.open(stream=d, filetype="pdf"))
    cap = pymupdf.open(stream=capa(res, br, lang, renders, titulo, tot), filetype="pdf")
    cap.insert_pdf(out)
    toc = [[1, tx("sumario", lang), 2], [1, tx("mapa", lang), 3], [1, tx("corte", lang), 4]]
    toc.append([1, tx("planta", lang), n_nota + 2])
    try:
        cap.set_toc(toc)
    except Exception:  # noqa: BLE001
        pass
    cap.set_metadata({"title": titulo or res.get("nome") or "LSF", "author": br.name or "ConstruPilot", "subject": t("titulo", lang),
                      "creator": "ConstruPilot — motor LSF"})
    return cap.tobytes(deflate=True, garbage=3)
