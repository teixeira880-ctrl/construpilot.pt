"""Dossier PDF da construção tradicional — nota (A4) + desenhos (A3) + acabamento premium (capa, logótipo, cores da empresa).

Rastreio: cada elemento tem um ID (pilares P, vigas V, sapatas S, vigas de fundação VF, vergas VG, lajes, paredes) que é o mesmo
no mapa de quantidades, no quadro de armaduras, nas plantas, nos alçados de cada parede (fiadas e unidades contadas), no Excel
e no visualizador 3D.
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from engines.clt.pdf import _poly
from engines.lsf.i18n import num
from engines.lsf.pdf import _esc, _fonts, _hex, _styles, _tbl

from .defaults import REGRAS_FONTE

PRE = "PRÉ-DIMENSIONAMENTO E QUANTIDADES — a verificar e assinar por engenheiro de estruturas (NP EN 1992-1-1, NP EN 1997-1) antes da execução"
TIT = "Construção tradicional — estrutura de betão armado e alvenarias: estudo e mapa de quantidades"


def nota(res, lin, tot, lang="pt", accent="#203B2D", empresa=None, renders=None, titulo=None, aviso_precos=None) -> bytes:
    _fonts()
    acc = _hex(accent)
    S = _styles(acc, lang)
    buf = io.BytesIO()
    W, H = A4

    def deco(c, d):
        c.saveState()
        c.setFont("LSF-R", 7)
        c.setFillColor(colors.HexColor("#6b7680"))
        c.drawString(18 * mm, 10 * mm, (empresa + " · " if empresa else "") + (titulo or res.get("nome") or "")[:90])
        c.drawRightString(W - 18 * mm, 10 * mm, f"{d.page}")
        c.setStrokeColor(acc)
        c.line(18 * mm, 13 * mm, W - 18 * mm, 13 * mm)
        c.restoreState()

    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title=titulo or res.get("nome") or "", author=empresa or "ConstruPilot")
    E = [Paragraph(_esc(titulo or res.get("nome") or TIT), S["h1"]), Paragraph(_esc(TIT) + f" · {date.today().strftime('%d/%m/%Y')}", S["s"]),
         Spacer(1, 3 * mm), Paragraph(_esc(PRE), S["warn"])]
    if aviso_precos:
        E.append(Paragraph(_esc(aviso_precos), S["warn"]))
    e = res["estudo"]
    E.append(Paragraph("Síntese — quantidades totais", S["h2"]))
    k = [["Betão armado (todos os elementos)", f"{num(e['m3Betao'], 2)} m³"], ["Aço A500 (varões e malhas calculados)", f"{num(e['kgAco'], 0)} kg"],
         ["Alvenaria", f"{num(e['m2Alvenaria'], 1)} m² · {num(e['unidadesAlvenaria'], 0)} unidades"],
         ["Pilares / vigas / sapatas", f"{e['nPilares']} / {e['nVigas']} / {e['nSapatas']}"], ["Escavação", f"{num(e['escavacao'], 2)} m³"],
         ["Área de implantação dos pisos", f"{num(e['areaPisos'], 1)} m²"]]
    if tot:
        k.append(["Total com preço", f"{num(tot['total'], 2)} €" + (f" + {tot['linhas_sem_preco']} a orçamentar" if tot["linhas_sem_preco"] else "")])
    E.append(_tbl([["", ""]] + k, [100 * mm, 74 * mm], acc, (1,), 8))
    for nm, png in (renders or [])[:2]:
        E += [Spacer(1, 4 * mm), KeepTogether([Paragraph("Estrutura montada" + (" — fotorrealista" if nm == "fotorrealista" else " — render calculado"), S["h2"]),
                                                 Image(io.BytesIO(png), width=174 * mm, height=174 * mm * 9 / 16)])]
    E.append(Paragraph("Hipóteses adotadas (a validar)", S["h2"]))
    E += [Paragraph("• " + _esc(h), S["p"]) for h in res.get("hipoteses") or []]
    if res.get("avisos"):
        E.append(Paragraph("Pontos a verificar", S["h2"]))
        E += [Paragraph("• " + _esc(a), S["warn"]) for a in res["avisos"][:60]]
    E.append(PageBreak())
    E.append(Paragraph("Mapa de quantidades — por piso, das fundações à cobertura", S["h1"]))
    cats = []
    for l in lin:
        if l["cat"] not in cats:
            cats.append(l["cat"])
    for c in cats:
        rows = [["Código", "Designação", "Un.", "Quant.", "P. unit.", "Total"]]
        sub = 0.0
        for l in (x for x in lin if x["cat"] == c):
            p = l.get("preco")
            rows.append([Paragraph(_esc(l["code"]), S["s"]),
                         Paragraph(_esc(l["designacao"]) + (f"<br/><font size=6.4 color='#5f6b77'>{_esc(l['detalhe'])}</font>" if l.get("detalhe") else ""), S["s"]),
                         l["un"], num(l["qtd"], 0 if l["un"] == "un" else 2), num(p["unit"], 2) if p else "a orçamentar",
                         num(l["total"], 2) if l.get("total") is not None else "—"])
            sub += l.get("total") or 0
        E.append(Paragraph(_esc(c.split(" ", 1)[1]), S["h2"]))
        E.append(_tbl(rows, [32 * mm, 80 * mm, 9 * mm, 18 * mm, 18 * mm, 17 * mm], acc, (3, 4, 5), 7))
    E.append(PageBreak())
    E.append(Paragraph("Quadro de elementos e armaduras (dimensionamento elemento a elemento)", S["h1"]))
    rows = [["ID", "Nível", "Secção", "Armadura", "Estribos", "m³", "kg"]]
    for p in res["pilares"]:
        rows.append([p["id"], p.get("nivel") or "", f"{p['b']:.0f}×{p['h']:.0f}", p["armadura"], Paragraph(_esc(p["estribos"]), S["s"]), num(p["m3"], 3), num(p["kg"], 1)])
    for v in res["vigas"]:
        rows.append([v["id"], v.get("nivel") or "", f"{v['b']:.0f}×{v['h']:.0f} · L {v['L']:.0f}", v["armadura"], Paragraph(_esc(v["estribos"]), S["s"]),
                     num(v["m3"], 3), num(v["kg"], 1)])
    for s in res["sapatas"]:
        rows.append([s["id"], s["pilar"], f"{s['B']:.0f}×{s['B']:.0f}×{s['hs']:.0f}", Paragraph(_esc(s["armadura"]), S["s"]), "—", num(s["m3"], 3), num(s["kg"], 1)])
    for v in res["vigasFundacao"]:
        rows.append([v["id"], v["parede"], f"{v['b']:.0f}×{v['h']:.0f} · L {v['L']:.0f}", v["armadura"], Paragraph(_esc(v["estribos"]), S["s"]), num(v["m3"], 3), num(v["kg"], 1)])
    for g in res["vergas"]:
        rows.append([g["id"], g["parede"], f"{g['b']:.0f}×{g['h']:.0f} · L {g['L']:.0f}", Paragraph(_esc(g["armadura"]), S["s"]), "—", num(g["m3"], 3), num(g["kg"], 1)])
    for f in res["lajes"]:
        rows.append([f["id"], f.get("grupo") or "", Paragraph(_esc(f["seccao"]), S["s"]), "malhas calculadas", "—", num(f["m3"], 3), num(f["kg"], 1)])
    E.append(_tbl(rows, [26 * mm, 22 * mm, 30 * mm, 36 * mm, 30 * mm, 14 * mm, 16 * mm], acc, (5, 6), 6.6))
    E.append(Paragraph("Paredes — alvenaria contada fiada a fiada", S["h2"]))
    rows = [["Parede", "Nível", "Unidade", "L × H alv. (mm)", "Fiadas", "Unidades", "m²"]]
    for w in res["paredes"]:
        rows.append([w["id"], w.get("nivel") or "", Paragraph(_esc(w["unidade"]), S["s"]), f"{w['L']:.0f} × {w['Halv']:.0f}", str(w["fiadas"]), str(w["unidades"]),
                     num(w["areaAlv"], 2)])
    E.append(_tbl(rows, [22 * mm, 20 * mm, 50 * mm, 30 * mm, 14 * mm, 18 * mm, 18 * mm], acc, (4, 5, 6), 6.8))
    E.append(Paragraph("Regras e parâmetros", S["h2"]))
    rows = [["Regra", "Valor", "Origem"]] + [[k_, str(v), Paragraph(_esc(REGRAS_FONTE.get(k_, "Parâmetro do projeto")), S["s"])] for k_, v in res["regras"].items()]
    E.append(_tbl(rows, [40 * mm, 20 * mm, 114 * mm], acc, (1,), 7))
    doc.build(E, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()


def _cart(c, W, H, acc, titulo, sub, empresa, folha):
    c.setStrokeColor(acc)
    c.setLineWidth(1.2)
    c.rect(10 * mm, 10 * mm, W - 20 * mm, H - 20 * mm)
    bx = W - 160 * mm
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
    c.drawString(14 * mm, 13 * mm, PRE[:150])


def _planta(c, res, nivel, acc, empresa, folha):
    W, H = landscape(A3)
    ws = [w for w in res["paredes"] if w.get("nivel") == nivel]
    ps = [p for p in res["pilares"] if p.get("nivel") == nivel]
    ids = {w["id"] for w in ws}
    vs = [v for v in res["vigas"] if v["parede"] in ids]
    _cart(c, W, H, acc, f"Planta estrutural — {nivel}", f"{len(ws)} paredes · {len(ps)} pilares · {len(vs)} vigas · IDs = quadro de armaduras", empresa, folha)
    pts = []
    for w in ws:
        for x, y in ((0, w["y0"]), (w["L"], w["y0"] + w["Dt"])):
            pts.append((w["A"][0] + x * w["d"][0] + y * w["n"][0], w["A"][1] + x * w["d"][1] + y * w["n"][1]))
    if not pts:
        c.showPage()
        return
    x0, x1 = min(p[0] for p in pts) - 600, max(p[0] for p in pts) + 600
    y0, y1 = min(p[1] for p in pts) - 600, max(p[1] for p in pts) + 600
    s = min((W - 60 * mm) / (x1 - x0), (H - 80 * mm) / (y1 - y0))
    ox, oy = 30 * mm - x0 * s, 45 * mm - y0 * s

    def P(w, x, y):
        return (ox + (w["A"][0] + x * w["d"][0] + y * w["n"][0]) * s, oy + (w["A"][1] + x * w["d"][1] + y * w["n"][1]) * s)

    for w in ws:
        _poly(c, [P(w, 0, w["y0"]), P(w, w["L"], w["y0"]), P(w, w["L"], w["y0"] + w["Dt"]), P(w, 0, w["y0"] + w["Dt"])],
              "#d9c7b0" if w["resistente"] else "#ece3d6", "#5a4630", 0.4)
        for a in w["aberturas"]:
            ym = w["y0"] + w["Dt"] / 2
            c.setStrokeColor(colors.HexColor("#d9590b"))
            c.setLineWidth(2.2)
            c.line(*P(w, a["x0"], ym), *P(w, a["x1"], ym))
        mx, my = P(w, w["L"] / 2, w["y0"] + w["Dt"] / 2 + 520)
        c.setFillColor(colors.HexColor("#0d1a26"))
        c.setFont("LSF-B", 7)
        c.drawCentredString(mx, my, w["id"])
    wid = {w["id"]: w for w in ws}
    for v in vs:
        w = wid[v["parede"]]
        ym = w["y0"] + w["Dt"] / 2
        c.setStrokeColor(colors.HexColor("#2f5f8f"))
        c.setLineWidth(1.0)
        c.setDash(4, 2)
        c.line(*P(w, v["x0"], ym), *P(w, v["x1"], ym))
        c.setDash()
        mx, my = P(w, (v["x0"] + v["x1"]) / 2, ym - 380)
        c.setFillColor(colors.HexColor("#2f5f8f"))
        c.setFont("LSF-M", 6)
        c.drawCentredString(mx, my, f"{v['id']} {v['b'] / 10:.0f}×{v['h'] / 10:.0f}")
    for p in ps:
        bx, by = ox + p["x"] * s, oy + p["y"] * s
        c.setFillColor(colors.HexColor("#3d4b57"))
        c.rect(bx - p["h"] * s / 2, by - p["h"] * s / 2, p["h"] * s, p["h"] * s, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#b0221b"))
        c.setFont("LSF-B", 6.5)
        c.drawString(bx + p["h"] * s / 2 + 2, by + 2, p["pilar"])
    c.showPage()


def _fundacoes(c, res, acc, empresa, folha):
    W, H = landscape(A3)
    S, VF = res["sapatas"], res["vigasFundacao"]
    _cart(c, W, H, acc, "Planta de fundações", f"{len(S)} sapatas · {len(VF)} vigas de fundação", empresa, folha)
    if not S:
        c.showPage()
        return
    x0, x1 = min(s["x"] - s["B"] for s in S), max(s["x"] + s["B"] for s in S)
    y0, y1 = min(s["y"] - s["B"] for s in S), max(s["y"] + s["B"] for s in S)
    sc = min((W - 60 * mm) / (x1 - x0), (H - 80 * mm) / (y1 - y0))
    ox, oy = 30 * mm - x0 * sc, 45 * mm - y0 * sc
    for s in S:
        c.setFillColor(colors.HexColor("#cfd6dc"))
        c.setStrokeColor(colors.HexColor("#3d4b57"))
        c.rect(ox + (s["x"] - s["B"] / 2) * sc, oy + (s["y"] - s["B"] / 2) * sc, s["B"] * sc, s["B"] * sc, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#0d1a26"))
        c.setFont("LSF-B", 7)
        c.drawCentredString(ox + s["x"] * sc, oy + s["y"] * sc + 3, f"{s['id']} ({s['pilar']})")
        c.setFont("LSF-R", 5.8)
        c.drawCentredString(ox + s["x"] * sc, oy + s["y"] * sc - 5, f"{s['B'] / 1000:.2f}×{s['B'] / 1000:.2f}×{s['hs'] / 1000:.2f}")
    c.showPage()


def _alcado(c, res, w, acc, empresa, folha):
    W, H = landscape(A3)
    _cart(c, W, H, acc, f"Alçado de parede — {w['id']} ({w.get('nivel') or ''})",
          f"{w['unidade']} · {w['fiadas']} fiadas · {w['unidades']} unidades · {num(w['areaAlv'], 2)} m²", empresa, folha)
    aw, ah = W - 60 * mm, H - 90 * mm
    s = min(aw / max(w["L"], 1), ah / max(w["H"], 1))
    ox, oz = 30 * mm, 55 * mm

    def X(x):
        return ox + x * s

    def Z(z):
        return oz + z * s

    _poly(c, [(X(0), Z(0)), (X(w["L"]), Z(0)), (X(w["L"]), Z(w["H"])), (X(0), Z(w["H"]))], "#e9d2b4", "#5a4630", 0.5)
    c.setStrokeColor(colors.HexColor("#c7a77f"))
    c.setLineWidth(0.15)
    k = 1
    while k * 210 < w["Halv"]:
        c.line(X(0), Z(k * 210), X(w["L"]), Z(k * 210))
        k += 1
    for x0, x1 in w.get("pilaresX") or []:
        _poly(c, [(X(x0), Z(0)), (X(x1), Z(0)), (X(x1), Z(w["H"])), (X(x0), Z(w["H"]))], "#9aa6b0", "#3d4b57", 0.5)
    for vid in w.get("vigas") or []:
        v = next(x for x in res["vigas"] if x["id"] == vid)
        _poly(c, [(X(v["x0"]), Z(w["H"] - v["h"])), (X(v["x1"]), Z(w["H"] - v["h"])), (X(v["x1"]), Z(w["H"])), (X(v["x0"]), Z(w["H"]))], "#b9c7d4", "#2f5f8f", 0.5)
        c.setFillColor(colors.HexColor("#1d3b5a"))
        c.setFont("LSF-B", 7)
        c.drawCentredString(X((v["x0"] + v["x1"]) / 2), Z(w["H"] - v["h"] / 2) - 2, f"{v['id']} {v['b'] / 10:.0f}×{v['h'] / 10:.0f} · {v['armadura']}")
    for g in res["vergas"]:
        if g["parede"] != w["id"]:
            continue
        _poly(c, [(X(g["x0"]), Z(g["z0"])), (X(g["x0"] + g["L"]), Z(g["z0"])), (X(g["x0"] + g["L"]), Z(g["z0"] + g["h"])), (X(g["x0"]), Z(g["z0"] + g["h"]))],
              "#c9d3dc", "#2f5f8f", 0.4)
    for a in w["aberturas"]:
        _poly(c, [(X(a["x0"]), Z(a["z0"])), (X(a["x1"]), Z(a["z0"])), (X(a["x1"]), Z(a["z1"])), (X(a["x0"]), Z(a["z1"]))], "#ffffff", "#d9590b", 0.9)
        c.setFillColor(colors.HexColor("#d9590b"))
        c.setFont("LSF-M", 6.6)
        c.drawCentredString(X((a["x0"] + a["x1"]) / 2), Z((a["z0"] + a["z1"]) / 2), f"{a.get('id') or ''} {a['x1'] - a['x0']:.0f}×{a['z1'] - a['z0']:.0f}")
    c.setFillColor(colors.HexColor("#5f6b77"))
    c.setFont("LSF-R", 6)
    xs = sorted({0.0, w["L"], *[v for a in w["aberturas"] for v in (a["x0"], a["x1"])], *[v for p in w.get("pilaresX") or [] for v in p]})
    for x in xs:
        c.saveState()
        c.translate(X(x) + 1.5, oz - 6 * mm)
        c.rotate(-90)
        c.drawString(0, 0, f"{x:.0f}")
        c.restoreState()
    c.showPage()


def desenhos(res, accent="#203B2D", empresa=None, max_alcados=120) -> bytes:
    _fonts()
    acc = _hex(accent)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A3))
    n_total = 1 + len(res["niveis"]) + min(len(res["paredes"]), max_alcados)
    k = 1
    _fundacoes(c, res, acc, empresa, f"folha {k}/{n_total}")
    for nv in res["niveis"]:
        k += 1
        _planta(c, res, nv, acc, empresa, f"folha {k}/{n_total}")
    for w in res["paredes"][:max_alcados]:
        k += 1
        _alcado(c, res, w, acc, empresa, f"folha {k}/{n_total}")
    c.save()
    return buf.getvalue()


def dossier(res, lin, tot, branding=None, renders=None, titulo=None, aviso_precos=None) -> bytes:
    import pymupdf
    from engines.bet_core.brand import from_branding
    br = from_branding(branding, res.get("country", "PT"))
    accent = "#" + br.hex
    empresa = br.name if br.is_client else None
    out = pymupdf.open(stream=nota(res, lin, tot, "pt", accent, empresa, renders, titulo, aviso_precos), filetype="pdf")
    n_nota = out.page_count
    out.insert_pdf(pymupdf.open(stream=desenhos(res, accent, empresa), filetype="pdf"))
    cap = pymupdf.open(stream=_capa(res, br, renders, titulo, tot), filetype="pdf")
    cap.insert_pdf(out)
    try:
        cap.set_toc([[1, "Síntese", 2], [1, "Mapa de quantidades", 3], [1, "Planta de fundações", n_nota + 2]])
    except Exception:  # noqa: BLE001
        pass
    cap.set_metadata({"title": titulo or res.get("nome") or "", "author": br.name or "ConstruPilot", "subject": TIT, "creator": "ConstruPilot — motor de construção tradicional"})
    return cap.tobytes(deflate=True, garbage=3)


def _capa(res, br, renders=None, titulo=None, tot=None) -> bytes:
    """Capa A4 premium: marca da empresa, título, render e 4 indicadores (betão, aço, alvenaria, total)."""
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
        c.roundRect(x - 3 * mm, H - 35 * mm, ww + 6 * mm, hh + 6 * mm, 2 * mm, fill=1, stroke=0)
        c.drawImage(br.logo, x, H - 32 * mm, ww, hh, mask="auto", preserveAspectRatio=True)
    c.setFillColor(colors.white)
    c.setFont("LSF-B", 11)
    c.drawString(x, H - 44 * mm, (br.name or "ConstruPilot")[:70])
    c.setFont("LSF-T", 24)
    c.drawString(x, H - 58 * mm, (titulo or res.get("nome") or "")[:48])
    c.setFont("LSF-R", 10)
    c.drawString(x, H - 68 * mm, TIT[:95])
    if renders:
        iw = W - 36 * mm
        ih = iw * 9 / 16
        c.drawImage(ImageReader(io.BytesIO(renders[0][1])), x, H - 100 * mm - ih, iw, ih)
        ytop = H - 108 * mm - ih
    else:
        ytop = H - 110 * mm
    e = res["estudo"]
    kp = [("Betão armado", num(e["m3Betao"], 1), "m³"), ("Aço A500", num(e["kgAco"], 0), "kg"), ("Alvenaria", num(e["unidadesAlvenaria"], 0), "unidades"),
          ("Escavação", num(e["escavacao"], 1), "m³")]
    if tot and tot.get("total"):
        kp[3] = ("Total", num(tot["total"], 0), "€" + (" *" if tot["linhas_sem_preco"] else ""))
    bw = (W - 36 * mm - 12 * mm) / 4
    for i, (lab, val, un) in enumerate(kp):
        bx = x + i * (bw + 4 * mm)
        c.setFillColor(colors.HexColor("#f4f6f7"))
        c.rect(bx, ytop - 26 * mm, bw, 26 * mm, fill=1, stroke=0)
        c.setFillColor(acc)
        c.rect(bx, ytop - 26 * mm, 1.4 * mm, 26 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#5f6b77"))
        c.setFont("LSF-R", 8)
        c.drawString(bx + 4 * mm, ytop - 7 * mm, lab)
        c.setFillColor(colors.HexColor("#16202a"))
        c.setFont("LSF-B", 16)
        c.drawString(bx + 4 * mm, ytop - 16 * mm, val)
        c.setFont("LSF-R", 8)
        c.setFillColor(colors.HexColor("#5f6b77"))
        c.drawString(bx + 4 * mm, ytop - 22 * mm, un)
    c.setFillColor(colors.HexColor("#9a3d0a"))
    c.setFont("LSF-M", 7.2)
    c.drawString(x, 24 * mm, PRE[:150])
    c.setFillColor(colors.HexColor("#5f6b77"))
    c.setFont("LSF-R", 7.6)
    c.drawString(x, 18 * mm, f"{date.today().strftime('%d/%m/%Y')} · " + " · ".join(br.lines[:2])[:120])
    c.drawRightString(W - 18 * mm, 18 * mm, "ConstruPilot")
    c.showPage()
    c.save()
    return buf.getvalue()
