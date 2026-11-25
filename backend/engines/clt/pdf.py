"""Dossier PDF do estudo CLT — nota (A4) + desenhos de fabrico (A3) + acabamento premium (capa, logótipo, cores da empresa).

Rastreio do que foi calculado: cada parede tem o seu alçado de fabrico com os painéis numerados (o mesmo ID da lista de
painéis, do Excel e do visualizador 3D), os recortes dos vãos cotados, as posições dos esquadros, hold-downs e pontos de
elevação; a planta de cada piso identifica paredes e juntas; lajes e cobertura são desenhadas painel a painel; o plano de
prensa mostra cada painel bruto com os painéis encaixados.
"""
from __future__ import annotations

import io
import math
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from engines.lsf.pdf import _esc, _fonts, _hex, _styles, _tbl

from .defaults import REGRAS_FONTE
from .i18n import num, t, tx

COR = {"parede": "#c99a5b", "laje": "#b5834a", "cobertura": "#9c6b3a", "empena": "#d8b27a"}


def _kpis(res, lang, tot=None):
    e = res["estudo"]
    k = [[t("m3liq", lang), f"{num(e['m3Liq'], 2, lang)} m³"], [t("m3prensa", lang), f"{num(e['m3Prensa'], 2, lang)} m³"],
         [t("perda", lang), f"{num(e['desperdicio'] * 100, 1, lang)} %"], [t("paineis", lang), num(e["nPaineis"], 0, lang)],
         [t("massa", lang), f"{num(e['kg'] / 1000, 1, lang)} t"], [t("parafusos", lang), num(e["nParafusos"], 0, lang)],
         [t("conectores", lang), num(e["nConectores"], 0, lang)]]
    if e.get("m3PorM2"):
        k.append([t("m3m2", lang), f"{num(e['m3PorM2'], 3, lang)} m³/m²"])
    for u, v in (e.get("porUso") or {}).items():
        k.append([f"{t(u, lang)}", f"{v['n']} · {num(v['m2'], 1, lang)} m² · {num(v['m3'], 2, lang)} m³"])
    k.append(["Vãos recortados", f"{num(e['m2Vaos'], 1, lang)} m² · {num(e['m3Vaos'], 2, lang)} m³"])
    if tot:
        k.append([tx("total", lang) + " (" + ", ".join(f"{o}: {num(v, 2, lang)} €" for o, v in tot["por_origem"].items() if v) + ")",
                  f"{num(tot['total'], 2, lang)} €" + (f" + {tot['linhas_sem_preco']} {tx('sem_preco', lang)}" if tot["linhas_sem_preco"] else "")])
    return k


# ---------------------------------------------------------------------------------------------------------------- nota
def nota(res: dict, lin: list[dict], tot: dict | None, lang: str = "pt", accent="#203B2D", empresa: str | None = None,
         renders: list | None = None, titulo: str | None = None, aviso_precos: str | None = None) -> bytes:
    _fonts()
    acc = _hex(accent)
    S = _styles(acc, lang)
    buf = io.BytesIO()
    W, H = A4

    def deco(c, d):
        c.saveState()
        c.setFont("LSF-R", 7)
        c.setFillColor(colors.HexColor("#6b7680"))
        c.drawString(18 * mm, 10 * mm, (empresa + " · " if empresa else "") + (titulo or res.get("nome") or "CLT")[:90])
        c.drawRightString(W - 18 * mm, 10 * mm, f"{d.page}")
        c.setStrokeColor(acc)
        c.setLineWidth(0.6)
        c.line(18 * mm, 13 * mm, W - 18 * mm, 13 * mm)
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=titulo or res.get("nome") or "CLT", author=empresa or "ConstruPilot")
    E = []
    pr = res.get("produto") or {}
    E.append(Paragraph(_esc(titulo or res.get("nome") or t("titulo", lang)), S["h1"]))
    E.append(Paragraph(_esc(t("titulo", lang)) + f" · {date.today().strftime('%d/%m/%Y')}", S["s"]))
    E.append(Paragraph(_esc(f"Produto: {pr.get('nome')} — classe {pr.get('classe')} — {pr.get('eta')} · prensa {num(pr['prensa']['L'], 0, lang)} × "
                            f"{num(pr['prensa']['W'], 0, lang)} mm · {num(pr['densidade'], 0, lang)} kg/m³"
                            + (" · SÓ CLT (sem camadas de isolamento / membranas)" if res.get("soClt") else "")), S["s"]))
    E.append(Spacer(1, 3 * mm))
    E.append(Paragraph(_esc(t("pre", lang)), S["warn"]))
    if aviso_precos:
        E.append(Paragraph(_esc(aviso_precos), S["warn"]))
    E.append(Paragraph(tx("sumario", lang), S["h2"]))
    E.append(_tbl([["", ""]] + _kpis(res, lang, tot), [100 * mm, 74 * mm], acc, (1,), 8))
    E.append(Spacer(1, 2 * mm))
    rows = [["Composição", "Camadas (mm)", "Painéis", "m² líq.", "m³ líq.", "m³ envolv.", "m³ prensa", "Perda"]]
    for r in res["paineisResumo"]:
        rows.append([r["painel"], "-".join(str(int(c)) for c in r["camadas"]), str(r["n"]), num(r["areaLiq"], 1, lang), num(r["volLiq"], 2, lang),
                     num(r["volBruto"], 2, lang), num(r["volPrensa"], 2, lang), num(r["desperdicio"] * 100, 1, lang) + " %"])
    E.append(_tbl(rows, [24 * mm, 30 * mm, 14 * mm, 20 * mm, 20 * mm, 22 * mm, 22 * mm, 20 * mm], acc, (2, 3, 4, 5, 6, 7), 7.4))
    if renders:
        for nm, png in renders[:3]:
            im = Image(io.BytesIO(png), width=174 * mm, height=174 * mm * 9 / 16)
            E.append(Spacer(1, 4 * mm))
            E.append(KeepTogether([Paragraph(tx("render", lang) + (f" — {nm}" if nm and nm not in ("estrutura",) else ""), S["h2"]), im]))
    E.append(Paragraph(tx("hip", lang), S["h2"]))
    for h in res.get("hipoteses") or []:
        E.append(Paragraph("• " + _esc(h), S["p"]))
    E.append(Paragraph("• Composições, dimensões de prensa, conectores e passos de ligação: parâmetros do projeto (ver « " + tx("regras", lang)
                       + " »); a verificação estrutural (EN 1995-1-1, EN 1998-1, ETA do painel e dos conectores) é do projeto de estabilidade.", S["p"]))
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
            p = l.get("preco")
            orig = {"biblioteca": "B", "projeto": "P", "mercado": "M*"}.get((p or {}).get("origem"), "")
            rows.append([Paragraph(_esc(l["code"]), S["s"]),
                         Paragraph(_esc(l["designacao"]) + (f"<br/><font size=6.4 color='#5f6b77'>{_esc(l['detalhe'])}</font>" if l.get("detalhe") else ""), S["s"]),
                         l["un"], num(l["qtd"], 0 if l["un"] == "un" else 2, lang),
                         (num(p["unit"], 2, lang) + " " + orig) if p else tx("sem_preco", lang),
                         num(l["total"], 2, lang) if l.get("total") is not None else "—"])
            sub += l.get("total") or 0
        rows.append(["", Paragraph(f"<b>{_esc(c.split(' ', 1)[1] if ' ' in c else c)}</b>", S["s"]), "", "", "", num(sub, 2, lang) if sub else "—"])
        E.append(Paragraph(_esc(c.split(" ", 1)[1] if " " in c else c), S["h2"]))
        E.append(_tbl(rows, [30 * mm, 82 * mm, 9 * mm, 18 * mm, 18 * mm, 17 * mm], acc, (3, 4, 5), 7))
    E.append(Spacer(1, 2 * mm))
    E.append(Paragraph("B = biblioteca de preços da empresa · P = preço do projeto · M* = preço de mercado encontrado online, A ANALISAR "
                       "(fonte e data no Excel) · « a orçamentar » = sem preço: a linha conta no mapa mas não no total. "
                       "O CLT é medido em m³ de prensa (o que é fabricado); líquido, envolvente e perda no detalhe.", S["s"]))
    E.append(PageBreak())
    # lista de painéis
    E.append(Paragraph(tx("lista", lang), S["h1"]))
    rows = [["ID", "Uso", "Composição", "L × H (mm)", "Recortes", "m² líq.", "m³ líq.", "kg", "Esq./HD"]]
    for p in res["paineis"]:
        rec = ", ".join(f"{r.get('id') or ''} {num(r['x1'] - r['x0'], 0, lang)}×{num(r['z1'] - r['z0'], 0, lang)}" for r in p.get("recortes") or [])
        rows.append([p["id"], t(p["tipo"], lang), p["painel"], f"{num(p['L'], 0, lang)} × {num(p['H'], 0, lang)}", Paragraph(_esc(rec or "—"), S["s"]),
                     num(p["areaLiq"], 2, lang), num(p["volLiq"], 3, lang), num(p["kg"], 0, lang),
                     f"{p.get('esquadros', '—')}/{p.get('holdDowns', '—')}" if p["tipo"] == "parede" else "—"])
    E.append(_tbl(rows, [20 * mm, 16 * mm, 20 * mm, 26 * mm, 36 * mm, 15 * mm, 15 * mm, 13 * mm, 13 * mm], acc, (5, 6, 7), 6.6))
    if res.get("vaos"):
        E.append(Paragraph(tx("vaos", lang), S["h2"]))
        rows = [["Parede", "Nível", "Vão", "Tipo", "L × H (mm)", "m²", "m³ recortado"]]
        for v in res["vaos"]:
            rows.append([v["parede"], v.get("nivel") or "", v.get("id") or "", v["tipo"], f"{num(v['largura'], 0, lang)} × {num(v['altura'], 0, lang)}",
                         num(v["m2"], 2, lang), num(v["m3Recorte"], 3, lang)])
        E.append(_tbl(rows, [24 * mm, 22 * mm, 20 * mm, 18 * mm, 32 * mm, 20 * mm, 24 * mm], acc, (5, 6), 7))
    E.append(PageBreak())
    # regras + plano de prensa (tabela)
    E.append(Paragraph(tx("regras", lang), S["h1"]))
    rows = [["Regra", "Valor", "Origem"]]
    for k_, v in (res.get("regras") or {}).items():
        rows.append([k_, str(v), Paragraph(_esc(REGRAS_FONTE.get(k_, "Parâmetro do projeto")), S["s"])])
    for k_ in ("composicoes", "prensa"):
        rows.append([k_, "—", Paragraph(_esc(REGRAS_FONTE[k_]), S["s"])])
    E.append(_tbl(rows, [40 * mm, 20 * mm, 114 * mm], acc, (1,), 7.4))
    E.append(Paragraph(tx("prensa", lang), S["h2"]))
    rows = [["Composição", "Bruto (L × l mm)", "Painéis encaixados"]]
    for pl in res["planosPrensa"]:
        for i, f in enumerate(pl["folhas"]):
            rows.append([f"{pl['painel']} #{i + 1}", f"{num(f['comprimento'], 0, lang)} × {num(f['largura'], 0, lang)}",
                         Paragraph(_esc(", ".join(x["ref"] + (" (rodado)" if x.get("rodada") else "") for x in f["pecas"])), S["s"])])
    E.append(_tbl(rows, [34 * mm, 36 * mm, 104 * mm], acc, (), 7.2))
    doc.build(E, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


# --------------------------------------------------------------------------------------------------- desenhos (A3)
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


def _poly(c, pts, fill, stroke="#3b2a17", lw=0.5):
    p = c.beginPath()
    p.moveTo(*pts[0])
    for a in pts[1:]:
        p.lineTo(*a)
    p.close()
    c.setFillColor(colors.HexColor(fill))
    c.setStrokeColor(colors.HexColor(stroke))
    c.setLineWidth(lw)
    c.drawPath(p, fill=1, stroke=1)


def _marcas(c, X, Z, p, R):
    """Esquadros (▲ na base), hold-downs (■ nos extremos / vãos) e pontos de elevação (○ no topo) do painel de parede."""
    from .engine import n_linha
    L = p["L"]
    portas = [(r["x0"], r["x1"]) for r in p.get("recortes") or [] if r["z0"] <= 1]
    segs = [(0.0, L)]
    for a, b in portas:
        ns = []
        for s0, s1 in segs:
            if b <= s0 or a >= s1:
                ns.append((s0, s1))
                continue
            if a > s0:
                ns.append((s0, a))
            if b < s1:
                ns.append((b, s1))
        segs = ns
    c.setFillColor(colors.HexColor("#2f5f8f"))
    for s0, s1 in segs:
        ls = s1 - s0
        if ls < 300:
            continue
        n = max(1, n_linha(ls, R["esquadroPasso"], R["esquadroExtremo"]))
        xs = [s0 + ls / 2] if n == 1 else [s0 + R["esquadroExtremo"] + k * (ls - 2 * R["esquadroExtremo"]) / (n - 1) for k in range(n)]
        for x in xs:
            q = [(X(x) - 3, Z(0) - 5), (X(x) + 3, Z(0) - 5), (X(x), Z(0) - 0.5)]
            _poly(c, q, "#2f5f8f", "#2f5f8f", 0.2)
    hd = [60.0, L - 60.0] + [v for r in p.get("recortes") or [] if (r["x1"] - r["x0"]) >= R["holdDownVaoMin"] and 0 < r["x0"] and r["x1"] < L
                             for v in (r["x0"] - 60, r["x1"] + 60)]
    c.setFillColor(colors.HexColor("#c0392b"))
    for x in hd:
        c.rect(X(x) - 2.6, Z(0) + 1, 5.2, 9, fill=1, stroke=0)
    c.setStrokeColor(colors.HexColor("#1d6f42"))
    c.setLineWidth(0.8)
    for k in (1, 3):
        c.circle(X(L * k / 4), Z(p["H"]) - 5, 2.4, stroke=1, fill=0)


def _alcado_parede(c, res, w, acc, empresa, folha, lang, pid):
    W, H = landscape(A3)
    ps = [pid[i] for i in w["paineis"] if i in pid]
    _cartucho(c, W, H, acc, f"{tx('alcado', lang)} — {w['id']}" + (f" ({w.get('nivel')})" if w.get("nivel") else ""),
              f"{num(w['L'], 0, lang)} × {num(w['H'], 0, lang)} mm · {w['painel']} · {len(ps)} painel(éis) · vista pela face exterior", empresa, folha, lang)
    area_w, area_h = W - 20 * mm - 125 * mm - 20 * mm, H - 20 * mm - 60 * mm
    s = min(area_w / max(w["L"], 1), area_h / max(w["H"], 1))
    ox = 20 * mm + (area_w - w["L"] * s) / 2
    oz = 58 * mm + (area_h - w["H"] * s) / 2
    R = res["regras"]
    for p in ps:
        x0 = p["xParede"]

        def X(x, x0=x0):
            return ox + (x0 + x) * s

        def Z(z):
            return oz + z * s

        _poly(c, [(X(0), Z(0)), (X(p["L"]), Z(0)), (X(p["L"]), Z(p["H"])), (X(0), Z(p["H"]))], COR["parede"])
        # textura das lamelas exteriores (verticais)
        c.setStrokeColor(colors.HexColor("#b48850"))
        c.setLineWidth(0.15)
        xx = 160.0
        while xx < p["L"]:
            c.line(X(xx), Z(0), X(xx), Z(p["H"]))
            xx += 160.0
        for r in p.get("recortes") or []:
            _poly(c, [(X(r["x0"]), Z(r["z0"])), (X(r["x1"]), Z(r["z0"])), (X(r["x1"]), Z(r["z1"])), (X(r["x0"]), Z(r["z1"]))], "#ffffff", "#d9590b", 0.9)
            c.setFillColor(colors.HexColor("#d9590b"))
            c.setFont("LSF-M", 6.6)
            c.drawCentredString(X((r["x0"] + r["x1"]) / 2), Z((r["z0"] + r["z1"]) / 2) + 3,
                                f"{r.get('id') or ''} {num(r['x1'] - r['x0'], 0, lang)} × {num(r['z1'] - r['z0'], 0, lang)}")
            c.setFont("LSF-R", 5.6)
            c.drawCentredString(X((r["x0"] + r["x1"]) / 2), Z((r["z0"] + r["z1"]) / 2) - 5,
                                f"x {num(r['x0'], 0, lang)} · z {num(r['z0'], 0, lang)}")
        _marcas(c, X, Z, p, R)
        c.setFillColor(colors.HexColor("#0d1a26"))
        c.setFont("LSF-B", 11)
        c.drawCentredString(X(p["L"] / 2), Z(p["H"]) - 16, p["id"])
        c.setFont("LSF-R", 6.5)
        c.drawCentredString(X(p["L"] / 2), Z(p["H"]) - 25, f"{num(p['L'], 0, lang)} × {num(p['H'], 0, lang)} · {num(p['volLiq'], 3, lang)} m³ · {num(p['kg'], 0, lang)} kg")
    # cotas
    c.setStrokeColor(colors.HexColor("#5f6b77"))
    c.setLineWidth(0.3)
    c.setFont("LSF-R", 6)
    c.setFillColor(colors.HexColor("#5f6b77"))
    yc = oz - 14 * mm
    xs = sorted({0.0, w["L"], *w.get("juntas", []), *[v for a in w["aberturas"] for v in (a["x0"], a["x1"])]})
    c.line(ox, yc, ox + w["L"] * s, yc)
    for x in xs:
        c.line(ox + x * s, yc - 2, ox + x * s, yc + 2)
        c.saveState()
        c.translate(ox + x * s + 1.5, yc - 3)
        c.rotate(-90)
        c.drawString(0, 0, num(x, 0, lang))
        c.restoreState()
    c.line(ox - 8 * mm, oz, ox - 8 * mm, oz + w["H"] * s)
    c.saveState()
    c.translate(ox - 10 * mm, oz + w["H"] * s / 2)
    c.rotate(90)
    c.drawCentredString(0, 0, f"{num(w['H'], 0, lang)}")
    c.restoreState()
    # legenda + tabela
    tx0 = W - 10 * mm - 120 * mm
    ty = H - 18 * mm
    c.setFillColor(acc)
    c.setFont("LSF-B", 8.5)
    c.drawString(tx0, ty, "Painéis desta parede")
    ty -= 5 * mm
    c.setFont("LSF-R", 6.8)
    for p in ps:
        c.setFillColor(colors.HexColor("#1d2630"))
        c.drawString(tx0, ty, f"{p['id']}  {p['painel']}  {num(p['L'], 0, lang)}×{num(p['H'], 0, lang)}  {num(p['volLiq'], 3, lang)} m³  "
                              f"{num(p['kg'], 0, lang)} kg  esq. {p.get('esquadros', 0)} · HD {p.get('holdDowns', 0)}")
        ty -= 3.6 * mm
    ty -= 3 * mm
    leg = [("#2f5f8f", "▲ esquadro de corte (base)"), ("#c0392b", "■ hold-down"), ("#1d6f42", "○ ponto de elevação"),
           ("#d9590b", "recorte CNC do vão (cotas desde o canto inferior esquerdo do painel)")]
    for col, txt in leg:
        c.setFillColor(colors.HexColor(col))
        c.drawString(tx0, ty, txt)
        ty -= 3.6 * mm
    if w.get("perimetro"):
        c.setFillColor(colors.HexColor("#5f6b77"))
        c.drawString(tx0, ty - 2 * mm, "Canto: " + ("painel atravessa no início" if w["perimetro"].get("sC") else "topo contra a parede anterior"))
    c.showPage()


def _planta(c, res, nivel, paredes, acc, empresa, folha, lang):
    W, H = landscape(A3)
    _cartucho(c, W, H, acc, f"{tx('planta', lang)} — {nivel}", f"{len(paredes)} paredes · IDs = alçados de fabrico · juntas de painel a tracejado", empresa,
              folha, lang)
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

    def P(w, x, y):
        return (ox + (w["A"][0] + x * w["d"][0] + y * w["n"][0]) * s, oy + (w["A"][1] + x * w["d"][1] + y * w["n"][1]) * s)

    for w in paredes:
        q = [P(w, 0, w["y0"]), P(w, w["L"], w["y0"]), P(w, w["L"], w["y0"] + w["Dt"]), P(w, 0, w["y0"] + w["Dt"])]
        _poly(c, q, "#c99a5b" if w.get("perimetro") else "#e0bd8a", "#3b2a17", 0.4)
        c.setStrokeColor(colors.HexColor("#1d2b38"))
        c.setDash(2, 1.5)
        c.setLineWidth(0.6)
        for j in w.get("juntas", []):
            c.line(*P(w, j, w["y0"] - 80), *P(w, j, w["y0"] + w["Dt"] + 80))
        c.setDash()
        for a in w["aberturas"]:
            ym = w["y0"] + w["Dt"] / 2
            c.setStrokeColor(colors.HexColor("#d9590b"))
            c.setLineWidth(2.2)
            c.line(*P(w, a["x0"], ym), *P(w, a["x1"], ym))
        mx, my = P(w, w["L"] / 2, w["y0"] + w["Dt"] / 2 + 450)
        c.setFillColor(colors.HexColor("#0d1a26"))
        c.setFont("LSF-B", 7)
        c.drawCentredString(mx, my, w["id"])
    c.showPage()


def _proj_top(p, u_, v_):
    o, u, v = p["o"], p["u"], p["v"]
    return [(o[0] + u[0] * a + v[0] * b, o[1] + u[1] * a + v[1] * b) for a, b in u_]


def _lajes(c, res, grupo, ps, acc, empresa, folha, lang, titulo):
    W, H = landscape(A3)
    _cartucho(c, W, H, acc, f"{titulo} — {grupo}", f"{len(ps)} painéis · seta = direção das lamelas exteriores (vão)", empresa, folha, lang)
    polys = []
    for p in ps:
        q = [(p["o"][0] + p["u"][0] * a + p["v"][0] * b, p["o"][1] + p["u"][1] * a + p["v"][1] * b) for a, b in p["contorno"]]
        polys.append((p, q))
    xs = [x for _, q in polys for x, _ in q]
    ys = [y for _, q in polys for _, y in q]
    s = min((W - 60 * mm) / max(max(xs) - min(xs), 1), (H - 80 * mm) / max(max(ys) - min(ys), 1))
    ox, oy = 30 * mm - min(xs) * s, 50 * mm - min(ys) * s
    for p, q in polys:
        qq = [(ox + x * s, oy + y * s) for x, y in q]
        _poly(c, qq, COR.get(p["tipo"], "#c99a5b"), "#3b2a17", 0.6)
        cx = sum(a[0] for a in qq) / len(qq)
        cy = sum(a[1] for a in qq) / len(qq)
        c.setStrokeColor(colors.HexColor("#3b2a17"))
        c.setLineWidth(0.7)
        du = (p["u"][0], p["u"][1])
        ln = math.hypot(*du) or 1
        du = (du[0] / ln, du[1] / ln)
        c.line(cx - du[0] * 22, cy - du[1] * 22, cx + du[0] * 22, cy + du[1] * 22)
        c.line(cx + du[0] * 22, cy + du[1] * 22, cx + du[0] * 16 - du[1] * 4, cy + du[1] * 16 + du[0] * 4)
        c.setFillColor(colors.HexColor("#0d1a26"))
        c.setFont("LSF-B", 8)
        c.drawCentredString(cx, cy + 8, p["id"])
        c.setFont("LSF-R", 6)
        c.drawCentredString(cx, cy - 14, f"{p['painel']} · {num(p['L'], 0, lang)}×{num(p['H'], 0, lang)} · {num(p['volLiq'], 2, lang)} m³")
    c.showPage()


def _empena(c, res, p, acc, empresa, folha, lang):
    W, H = landscape(A3)
    _cartucho(c, W, H, acc, f"{tx('alcado', lang)} — {p['id']} ({t('empena', lang)})",
              f"{p['painel']} · base {num(p['L'], 0, lang)} · altura {num(p['H'], 0, lang)} mm · {num(p['volLiq'], 3, lang)} m³", empresa, folha, lang)
    s = min((W - 80 * mm) / p["L"], (H - 100 * mm) / max(p["H"], 1))
    ox, oz = 40 * mm, 70 * mm
    _poly(c, [(ox + x * s, oz + z * s) for x, z in p["contorno"]], COR["empena"])
    for r in p.get("recortes") or []:
        _poly(c, [(ox + r["x0"] * s, oz + r["z0"] * s), (ox + r["x1"] * s, oz + r["z0"] * s), (ox + r["x1"] * s, oz + r["z1"] * s),
                  (ox + r["x0"] * s, oz + r["z1"] * s)], "#ffffff", "#d9590b", 0.9)
        c.setFillColor(colors.HexColor("#d9590b"))
        c.setFont("LSF-M", 7)
        c.drawString(ox + r["x1"] * s + 4, oz + (r["z0"] + r["z1"]) / 2 * s, f"bolsa da viga {num(r['x1'] - r['x0'], 0, lang)} × {num(r['z1'] - r['z0'], 0, lang)}")
    c.setFillColor(colors.HexColor("#0d1a26"))
    c.setFont("LSF-B", 12)
    c.drawCentredString(ox + p["L"] / 2 * s, oz + p["H"] / 3 * s, p["id"])
    c.showPage()


def _prensa(c, res, pl, acc, empresa, folha, lang):
    W, H = landscape(A3)
    fl = pl["folhas"]
    _cartucho(c, W, H, acc, f"{tx('prensa', lang)[:40]} — {pl['painel']}", f"{len(fl)} bruto(s) · prensa {num(pl['L'], 0, lang)} × {num(pl['W'], 0, lang)} mm",
              empresa, folha, lang)
    if not fl:
        c.showPage()
        return
    Lm = max(f["comprimento"] for f in fl)
    tot_h = sum(f["largura"] for f in fl) + 600 * (len(fl) - 1)
    s = min((W - 60 * mm) / Lm, (H - 75 * mm) / max(tot_h, 1))
    y = H - 22 * mm
    pid = {p["id"]: p for p in res["paineis"]}
    for i, f in enumerate(fl):
        y -= f["largura"] * s
        c.setFillColor(colors.HexColor("#f3ead9"))
        c.setStrokeColor(colors.HexColor("#8a6a2c"))
        c.setLineWidth(0.6)
        c.rect(30 * mm, y, f["comprimento"] * s, f["largura"] * s, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#5f6b77"))
        c.setFont("LSF-R", 6.4)
        c.drawString(30 * mm, y + f["largura"] * s + 2, f"#{i + 1} · {num(f['comprimento'], 0, lang)} × {num(f['largura'], 0, lang)} mm")
        for x in f["pecas"]:
            _poly(c, [(30 * mm + x["x"] * s, y + x["y"] * s), (30 * mm + (x["x"] + x["w"]) * s, y + x["y"] * s),
                      (30 * mm + (x["x"] + x["w"]) * s, y + (x["y"] + x["h"]) * s), (30 * mm + x["x"] * s, y + (x["y"] + x["h"]) * s)],
                  COR.get((pid.get(x["ref"]) or {}).get("tipo"), "#c99a5b"), "#3b2a17", 0.4)
            c.setFillColor(colors.HexColor("#0d1a26"))
            c.setFont("LSF-B", 6.6)
            c.drawCentredString(30 * mm + (x["x"] + x["w"] / 2) * s, y + (x["y"] + x["h"] / 2) * s - 2, x["ref"])
        y -= 600 * s
    c.showPage()


def desenhos(res: dict, lang="pt", accent="#203B2D", empresa=None, max_alcados: int = 120) -> bytes:
    _fonts()
    acc = _hex(accent)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A3))
    pid = {p["id"]: p for p in res["paineis"]}
    niveis = []
    for w in res["paredes"]:
        nv = w.get("nivel") or "—"
        if nv not in niveis:
            niveis.append(nv)
    grupos = {}
    for p in res["paineis"]:
        if p["tipo"] in ("laje", "cobertura"):
            grupos.setdefault((p["tipo"], (p["ref"].rsplit("-", 1)[0] if p["tipo"] == "laje" else p["ref"])), []).append(p)
    empenas = [p for p in res["paineis"] if p["tipo"] == "empena"]
    n_total = len(niveis) + min(len(res["paredes"]), max_alcados) + len(grupos) + len(empenas) + len(res["planosPrensa"])
    k = 0
    for nv in niveis:
        k += 1
        _planta(c, res, nv, [w for w in res["paredes"] if (w.get("nivel") or "—") == nv], acc, empresa, f"folha {k}/{n_total}", lang)
    for w in res["paredes"][:max_alcados]:
        k += 1
        _alcado_parede(c, res, w, acc, empresa, f"folha {k}/{n_total}", lang, pid)
    for (tp, g), ps in grupos.items():
        k += 1
        _lajes(c, res, g, ps, acc, empresa, f"folha {k}/{n_total}", lang, tx("lajes", lang) if tp == "laje" else tx("cobertura", lang))
    for p in empenas:
        k += 1
        _empena(c, res, p, acc, empresa, f"folha {k}/{n_total}", lang)
    for pl in res["planosPrensa"]:
        k += 1
        _prensa(c, res, pl, acc, empresa, f"folha {k}/{n_total}", lang)
    c.save()
    return buf.getvalue()


def capa(res: dict, br, lang="pt", renders=None, titulo=None, tot=None) -> bytes:
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
    fn = "LSF-B" if lang == "uk" else "LSF-T"
    c.setFont(fn, 25)
    tt = titulo or res.get("nome") or t("titulo", lang)
    linhas_t, cur = [], ""
    for wd in tt.split():
        if c.stringWidth(cur + " " + wd, fn, 25) > W - 36 * mm and cur:
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
    kp = [(t("m3liq", lang), num(e["m3Liq"], 1, lang), "m³"), (t("paineis", lang), num(e["nPaineis"], 0, lang), ""),
          (t("parafusos", lang), num(e["nParafusos"], 0, lang), ""), (t("perda", lang), num(e["desperdicio"] * 100, 1, lang), "%")]
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


def dossier(res: dict, lin: list[dict], tot: dict | None, lang="pt", branding: dict | None = None, renders=None, titulo=None,
            aviso_precos: str | None = None) -> bytes:
    import pymupdf
    from engines.bet_core.brand import from_branding
    br = from_branding(branding, res.get("country", "PT"))
    accent = "#" + br.hex
    empresa = br.name if br.is_client else None
    n = nota(res, lin, tot, lang, accent, empresa, renders, titulo, aviso_precos)
    d = desenhos(res, lang, accent, empresa)
    out = pymupdf.open(stream=n, filetype="pdf")
    n_nota = out.page_count
    out.insert_pdf(pymupdf.open(stream=d, filetype="pdf"))
    cap = pymupdf.open(stream=capa(res, br, lang, renders, titulo, tot), filetype="pdf")
    cap.insert_pdf(out)
    toc = [[1, tx("sumario", lang), 2], [1, tx("mapa", lang), 3], [1, tx("planta", lang), n_nota + 2]]
    try:
        cap.set_toc(toc)
    except Exception:  # noqa: BLE001
        pass
    cap.set_metadata({"title": titulo or res.get("nome") or "CLT", "author": br.name or "ConstruPilot", "subject": t("titulo", lang),
                      "creator": "ConstruPilot — motor CLT"})
    return cap.tobytes(deflate=True, garbage=3)
