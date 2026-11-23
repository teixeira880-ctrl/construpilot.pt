"""Mapa de quantidades PREMIUM (PDF + Excel) : capa com indicadores, resumo por capítulo, medição por capítulo e POR PISO, e as
plantas de cada piso com cada elemento NUMERADO e marcado (paredes W, portas P, compartimentos C), alçados com os vãos V e cortes
com as alturas. Cada linha do mapa remete para os números do desenho : a empresa controla tudo, elemento a elemento.

Capítulos ordenados da fundação à cobertura. Capítulos que o desenho não permite medir aparecem como «a medir» com a origem —
nunca com valores por rácio. `extras` = linhas medidas noutros motores (estrutura, cobertura…) com a mesma forma."""
from __future__ import annotations

import io
import re
from collections import defaultdict
from datetime import datetime, timezone

from PIL import Image, ImageDraw

from .controlo import _bbox, _fonte

ORDEM = ["Estaleiro", "Movimento de terras", "Fundações", "Estrutura", "Alvenarias", "Fachadas e isolamento", "Cobertura",
         "Caixilharias e serralharias", "Portas e carpintarias", "Pavimentos", "Tetos", "Revestimentos", "Remates e águas pluviais"]
COR = {"fachada": (210, 60, 40), "interior": (40, 110, 200), "exterior / muro": (120, 120, 120)}


def _pref(i: int, piso: str) -> str:
    n = piso.lower()
    if "cave" in n or "sub" in n:
        return "-1"
    if "r" in n[:3] and ("ch" in n or "/c" in n or "rés" in n or "res" in n):
        return "0"
    m = re.search(r"(\d+)", n)
    if m:
        return m.group(1)
    if "s" in n[:2]:
        return "S"
    return str(i)


def _paredes_unidas(segs: list) -> list:
    """Troços colineares do mesmo tipo e espessura, seguidos, formam UMA parede numerada.
    Na fachada a parede continua através das janelas (falha ≤ 4,6 m) ; no interior através das portas (≤ 1,3 m).
    Comprimento = soma dos troços cheios (os vãos ficam de fora, como na medição)."""
    import math
    grupos = defaultdict(list)
    for w in segs:
        (a, b), n, t = w["eixo"], w.get("n", (0, 0)), w["espessura"]
        a = (a[0] + n[0] * t / 2, a[1] + n[1] * t / 2)              # eixo a meio da parede (as duas faces dão o mesmo eixo)
        b = (b[0] + n[0] * t / 2, b[1] + n[1] * t / 2)
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
        ang = round(ang) % 180
        ux, uy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
        off = round((-uy * a[0] + ux * a[1]) / 0.06)
        s0, s1 = sorted((ux * a[0] + uy * a[1], ux * b[0] + uy * b[1]))
        grupos[(w["tipo"], round(w["espessura"], 2), ang, off)].append((s0, s1, w))
    out = []
    for (tipo, e, ang, off), g in grupos.items():
        g.sort(key=lambda t: t[0])
        cur = None
        for s0, s1, w in g:
            if cur and s0 <= cur["_fim"] + (4.6 if tipo == "fachada" else 1.3):    # janelas na fachada / portas no interior
                cur["membros"].append(w)
                cur["_fim"] = max(cur["_fim"], s1)
            else:
                cur = {"tipo": tipo, "espessura": e, "membros": [w], "_fim": s1}
                out.append(cur)
    for u in out:
        u["comprimento"] = round(sum(m["comprimento"] for m in u["membros"]), 2)
    return out


def numerar(modelo: dict) -> None:
    """Dá um número a cada elemento : W<piso>.<n> paredes, P<piso>.<n> portas, C<piso>.<n> compartimentos, V-<vista><n> vãos."""
    for i, p in enumerate(modelo["pisos"]):
        k = _pref(i, p["piso"])
        p["_k"] = k
        p["_paredes_un"] = _paredes_unidas(p["paredes"])
        for j, u in enumerate(sorted(p["_paredes_un"], key=lambda w: (w["tipo"], -w["comprimento"])), 1):
            u["id"] = f"W{k}.{j:02d}"
            for m in u["membros"]:
                m["id"] = u["id"]
        for j, d in enumerate(sorted(p["portas"], key=lambda d: (d["y"], d["x"])), 1):
            d["id"] = f"P{k}.{j:02d}"
        for j, c in enumerate(sorted(p["compartimentos"], key=lambda c: (c["exterior"], -c["area"])), 1):
            c["id"] = f"C{k}.{j:02d}"
    usadas = set()
    for v in modelo["alcados"]:
        pal = [w for w in re.sub(r"\(.*?\)|al[cç]ado|/.*|\.", " ", v["vista"], flags=re.I).split() if w[0].isalpha()]
        ini = ("".join(w[0] for w in pal) if len(pal) > 1 else (pal[0][:2] if pal else "A")).upper()[:3]
        while ini in usadas:
            ini += "X"
        usadas.add(ini)
        v["_ini"] = ini
        for j, d in enumerate(v["vaos"], 1):
            d["id"] = f"V-{ini}{j:02d}"


def _ids(lista, n=6) -> str:
    def chave(i):
        m = re.search(r"(\d+)$", i)
        return (re.sub(r"\d+$", "", i), int(m.group(1)) if m else 0)
    ids = sorted({x["id"] for x in lista if x.get("id")}, key=chave)
    if len(ids) <= n:
        return ", ".join(ids)
    return f"{ids[0]} … {ids[-1]} ({len(ids)})"


def linhas(modelo: dict, extras: list | None = None) -> list:
    """[{capitulo, piso, designacao, descricao, qtd, un, refs, estado}] — da fundação à cobertura."""
    out = []
    for p in modelo["pisos"]:
        piso, h = p["piso"], p.get("altura")
        comps = p["compartimentos"]
        inter = [c for c in comps if not c["exterior"] and c["nome"] != "Caixa do elevador"]
        ext = [c for c in comps if c["exterior"]]
        san = [c for c in inter if re.search(r"instala[cç][aã]o sanit|\bi\.?s\.?\b|wc|casa de banho", c["nome"], re.I)]
        if inter:
            out.append(dict(capitulo="Pavimentos", piso=piso, designacao="Pavimento interior (área útil, sem caixa do elevador)",
                            descricao="soma dos compartimentos fechados, à face interior das paredes", qtd=sum(c["area"] for c in inter),
                            un="m²", refs=_ids(inter)))
            out.append(dict(capitulo="Tetos", piso=piso, designacao="Teto interior", descricao="igual ao pavimento interior",
                            qtd=sum(c["area"] for c in inter), un="m²", refs=_ids(inter)))
        if san:
            out.append(dict(capitulo="Revestimentos", piso=piso, designacao="Instalações sanitárias — pavimento",
                            descricao=", ".join(f"{c['id']} {c['area']:.2f}" for c in san), qtd=sum(c["area"] for c in san), un="m²",
                            refs=_ids(san)))
        if ext:
            out.append(dict(capitulo="Pavimentos", piso=piso, designacao="Varandas e terraços", descricao="áreas exteriores fechadas",
                            qtd=sum(c["area"] for c in ext), un="m²", refs=_ids(ext)))
        grupos = defaultdict(list)
        for w in p.get("_paredes_un") or p["paredes"]:
            grupos[(w["tipo"], round(w["espessura"] * 20) / 20)].append(w)
        for (tipo, e), ws in sorted(grupos.items()):
            L = sum(w["comprimento"] for w in ws)
            cap = "Alvenarias"
            nome = {"fachada": "Parede exterior (fachada)", "interior": "Parede interior / divisória",
                    "exterior / muro": "Parede exterior não confinante / muro"}[tipo]
            if h:
                out.append(dict(capitulo=cap, piso=piso, designacao=f"{nome} e = {e:.2f} m", descricao=f"{L:.2f} m × {h:.2f} m (altura do piso)",
                                qtd=L * h, un="m²", refs=_ids(ws)))
            else:
                out.append(dict(capitulo=cap, piso=piso, designacao=f"{nome} e = {e:.2f} m", descricao="altura por indicar", qtd=L, un="m",
                                refs=_ids(ws), estado="altura a confirmar"))
        por = defaultdict(list)
        for d in p["portas"]:
            if d["tipo"] == "interior":
                por[d["L"]].append(d)
        for L, ds in sorted(por.items()):
            out.append(dict(capitulo="Portas e carpintarias", piso=piso, designacao=f"Porta interior de batente {L:.2f} m",
                            descricao="largura = raio do arco de abertura na planta", qtd=len(ds), un="un", refs=_ids(ds)))
    for v in modelo["alcados"]:
        por = defaultdict(list)
        for d in v["vaos"]:
            por[(d["L"], d["H"])].append(d)
        for (L, H), ds in sorted(por.items(), key=lambda t: -t[0][0] * t[0][1]):
            tipo = "Portão" if L >= 2.8 and H <= 2.6 and any(d["nivel"] == max(x["nivel"] for x in v["vaos"]) for d in ds) else "Vão exterior"
            out.append(dict(capitulo="Caixilharias e serralharias", piso=v["vista"], designacao=f"{tipo} {L:.2f} × {H:.2f} m",
                            descricao=f"{len(ds)} × {L * H:.2f} m²", qtd=L * H * len(ds), un="m²", refs=_ids(ds)))
    out += list(extras or [])
    for r in out:
        r.setdefault("estado", "medido")
        r["qtd"] = round(float(r["qtd"]), 2) if r.get("qtd") is not None else None
    ordem = {c: i for i, c in enumerate(ORDEM)}
    return sorted(out, key=lambda r: (ordem.get(r["capitulo"], 99), r["capitulo"]))


# ---------------------------------------------------------------- desenhos numerados
def _imagem(linhas_fundo, titulo, desenhar, bbox, px=3000):
    x0, y0, x1, y1 = bbox
    S = min(px / max(x1 - x0, 1e-6), 2000 / max(y1 - y0, 1e-6))
    W, H = int((x1 - x0) * S) + 80, int((y1 - y0) * S) + 120
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im, "RGBA")
    T = lambda p: ((p[0] - x0) * S + 40, (p[1] - y0) * S + 90)
    for pl in linhas_fundo:
        dr.line([T(q) for q in pl], fill=(185, 185, 185), width=1)
    desenhar(dr, T, S)
    dr.text((40, 18), titulo, fill=(20, 30, 40), font=_fonte(30))
    return im


def desenhos(modelo: dict, titulo: str) -> list:
    pags = []
    for p in modelo["pisos"]:
        pts = [q for pl in p.get("_linhas", []) for q in pl]
        if not pts:
            continue
        fn, fs = _fonte(22), _fonte(17)

        _maior = {}
        for w in p["paredes"]:
            if w.get("id") and (w["id"] not in _maior or w["comprimento"] > _maior[w["id"]]["comprimento"]):
                _maior[w["id"]] = w

        def plan(dr, T, S, p=p, _maior=_maior):
            for c in p["compartimentos"]:
                pol = c["_poly"][0]
                dr.polygon([T(q) for q in pol], fill=(190, 215, 250, 110) if c["exterior"] else (215, 235, 220, 120))
                cx = sum(q[0] for q in pol) / len(pol)
                cy = sum(q[1] for q in pol) / len(pol)
                x, y = T((cx, cy))
                dr.text((x - 40, y - 10), f"{c['id']}\n{c['nome'][:20]}\n{c['area']:.2f} m²", fill=(10, 60, 30), font=fs)
            for w in p["paredes"]:
                (a, b), n, t = w["eixo"], w["n"], w["espessura"]
                q = [a, b, (b[0] + n[0] * t, b[1] + n[1] * t), (a[0] + n[0] * t, a[1] + n[1] * t)]
                cor = COR.get(w["tipo"], (0, 0, 0))
                dr.polygon([T(z) for z in q], fill=cor + (170,))
                if w is _maior.get(w.get("id")):
                    m = T(((a[0] + b[0]) / 2 + n[0] * t / 2, (a[1] + b[1]) / 2 + n[1] * t / 2))
                    dr.text((m[0] + 3, m[1] + 2), w["id"], fill=cor, font=fs)
            for d in p["portas"]:
                r = d["L"] * S / 2
                x, y = T((d["x"], d["y"]))
                cor = (180, 0, 150) if d["tipo"] == "interior" else (0, 90, 220)
                dr.ellipse([x - r, y - r, x + r, y + r], outline=cor, width=3)
                dr.text((x - 18, y - 8), d["id"], fill=cor, font=fn)
        t = f"{titulo} — Planta {p['piso']} : paredes W (vermelho fachada, azul interior, cinza muro), portas P, compartimentos C"
        pags.append((t, _imagem(p.get("_linhas", []), t, plan, _bbox(pts))))
    for v in modelo["alcados"]:
        z = v["zona"]

        def alc(dr, T, S, v=v):
            fn = _fonte(14)
            for d, b in zip(v["vaos"], v.get("_caixas_ord") or []):
                dr.rectangle([T(b[:2]), T(b[2:])], fill=(255, 80, 60, 70), outline=(200, 0, 0), width=3)
                dr.text((T(b[:2])[0] + 3, T(b[:2])[1] + 3), f"{d['id']}\n{d['L']:.2f}×{d['H']:.2f}", fill=(150, 0, 0), font=fn)
        t = f"{titulo} — {v['vista']} : vãos V ({len(v['vaos'])})"
        pags.append((t, _imagem(v.get("_linhas", []), t, alc, (z[0] - 1, z[1] - 1, z[2] + 1, z[3] + 1))))
    for p in modelo["pisos"]:
        pc = p.get("perfil_cobertura")
        if pc and pc.get("_poly"):
            def corte(dr, T, S, pc=pc):
                dr.polygon([T(q) for q in pc["_poly"]], fill=(255, 140, 0, 90), outline=(220, 90, 0))
                x0 = pc["_x"][0]
                yb = max(q[1] for q in pc["_poly"])
                dr.text(T((x0, yb + 0.3)), f"beirado {pc['h_min']:.2f} · cumeeira {pc['h_max']:.2f} · média {pc['h_media']:.2f} · "
                                           f"empena {pc['area_perfil']:.2f} m²", fill=(150, 60, 0), font=_fonte(22))
            t = f"{titulo} — {pc['corte']} : {p['piso']}, da laje à face inferior da cobertura"
            pags.append((t, _imagem(pc["_linhas"], t, corte, pc["_caixa"])))
    return pags


def _caixas_ordenadas(modelo):
    """As caixas dos vãos na mesma ordem que a lista de vãos (para o número ficar no sítio certo)."""
    for v in modelo["alcados"]:
        cx = v.get("_caixas") or []
        ordem = []
        for d in v["vaos"]:
            b = min(cx, key=lambda b: abs(b[0] - d["x"]) + abs((b[2] - b[0]) - d["L"]) + abs((b[3] - b[1]) - d["H"]), default=None)
            ordem.append(b)
        v["_caixas_ord"] = [b for b in ordem if b]


def _capa(pags) -> bytes | None:
    alc = [im for t, im in pags if "Alçado" in t or "Alcado" in t] or [im for _, im in pags]
    if not alc:
        return None
    im = alc[0].convert("RGB")
    im.thumbnail((1600, 1100))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


NAO_MEDIDO_PADRAO = [
    {"capitulo": "Movimento de terras", "designacao": "Escavação geral e para fundações", "descricao": "cotas do terreno + planta de fundação (projeto de estrutura)", "un": "m³"},
    {"capitulo": "Fundações", "designacao": "Sapatas isoladas — betão, cofragem, betão de limpeza, aço", "descricao": "juntar o PDF do projeto de estrutura (quadro de elementos de fundação)", "un": "m³", "_chave": "sapatas"},
    {"capitulo": "Fundações", "designacao": "Muros de suporte, sapatas lineares, vigas de fundação, laje térrea", "descricao": "planta de fundação do projeto de estrutura", "un": "m³"},
    {"capitulo": "Estrutura", "designacao": "Pilares, vigas, lajes — betão e cofragem", "descricao": "plantas de estrutura (ferramenta medir_planta_estrutural)", "un": "m³"},
    {"capitulo": "Estrutura", "designacao": "Aço A500 — armaduras peça a peça", "descricao": "desenhos de armaduras do projeto de estrutura", "un": "kg"},
]


# ---------------------------------------------------------------- PDF
def gerar_pdf(modelo: dict, caminho: str, titulo: str, extras: list | None = None, branding: dict | None = None,
              nao_medido: list | None = None) -> str:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image as RLImage, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from engines import pdf_premium as PP
    numerar(modelo)
    _caixas_ordenadas(modelo)
    L = linhas(modelo, extras)
    accent = colors.HexColor(PP.cor_empresa(branding))
    dark = colors.HexColor("#1B2430")
    ss = getSampleStyleSheet()
    small = ss["BodyText"].clone("s", fontSize=7.5, leading=9.5)
    h2 = ss["Heading2"].clone("h2", textColor=dark, spaceBefore=2, spaceAfter=6)
    buf = io.BytesIO()
    W, H = landscape(A4)
    doc = SimpleDocTemplate(buf, pagesize=(W, H), leftMargin=12 * mm, rightMargin=12 * mm, topMargin=14 * mm, bottomMargin=16 * mm,
                            title=f"Mapa de quantidades — {titulo}")
    head = [("BACKGROUND", (0, 0), (-1, 0), dark), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("LINEBELOW", (0, 0), (-1, 0), 1.6, accent),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#D7DCE3")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F8")])]
    nm = list(nao_medido or [])
    caps = defaultdict(list)
    for r in L + [{**n, "piso": n.get("piso") or "—", "qtd": None, "estado": "a medir", "refs": n.get("refs") or ""} for n in nm]:
        caps[r["capitulo"]].append(r)
    story = [Paragraph("Resumo por capítulo — da fundação à cobertura", h2),
             Paragraph(escape(f"{titulo} · {datetime.now(timezone.utc).date().isoformat()} · medição sobre os desenhos do projeto ; cada linha "
                              "remete para os números marcados nas plantas e alçados deste documento"), small), Spacer(1, 3 * mm)]
    res = [["Capítulo", "Linhas", "Pisos / vistas", "Estado"]]
    for c in sorted(caps, key=lambda c: (ORDEM.index(c) if c in ORDEM else 99, c)):
        rs = caps.get(c, [])
        est = ("medido" if all(r["estado"] == "medido" for r in rs) else
               "a medir" if all(r["estado"] == "a medir" for r in rs) else "medido / a confirmar")
        res.append([Paragraph(escape(c), small), str(sum(1 for r in rs if r["estado"] != "a medir")), Paragraph(escape(", ".join(dict.fromkeys(r["piso"] for r in rs))[:120]), small),
                    Paragraph(escape(est), small)])
    t = Table(res, colWidths=[70 * mm, 20 * mm, 140 * mm, 40 * mm], repeatRows=1)
    t.setStyle(TableStyle(head + [("ALIGN", (1, 1), (1, -1), "RIGHT")]))
    story += [t]
    # medição detalhada
    story += [PageBreak(), Paragraph("Medição — por capítulo e por piso", h2)]
    data = [["Capítulo / piso", "Designação", "Descrição / cálculo", "Elementos (no desenho)", "Quantidade", "Un", "Estado"]]
    marcas = []
    for c in sorted(caps, key=lambda c: (ORDEM.index(c) if c in ORDEM else 99, c)):
        data.append([Paragraph(f"<b>{escape(c)}</b>", small), "", "", "", "", "", ""])
        marcas.append(len(data) - 1)
        for r in caps[c]:
            q = "—" if r["qtd"] is None else f"{r['qtd']:,.2f}".replace(",", " ")
            est = f"<b>{escape(r['estado'])}</b>" if r["estado"] == "a medir" else escape(r["estado"])
            data.append([Paragraph(escape(r["piso"]), small), Paragraph(escape(r["designacao"]), small),
                         Paragraph(escape(r.get("descricao") or ""), small), Paragraph(escape(r.get("refs") or ""), small), q, r["un"],
                         Paragraph(est, small)])
    tb = LongTable(data, colWidths=[30 * mm, 62 * mm, 70 * mm, 48 * mm, 22 * mm, 10 * mm, 26 * mm], repeatRows=1)
    tb.setStyle(TableStyle(head + [("ALIGN", (4, 1), (4, -1), "RIGHT")] + [("SPAN", (0, i), (-1, i)) for i in marcas]
                           + [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#E9EDF1")) for i in marcas]
                           + [("LINEBELOW", (0, i), (-1, i), 0.8, accent) for i in marcas]))
    story += [tb]
    # pressupostos e alturas
    story += [PageBreak(), Paragraph("Pressupostos, alturas e origem das medidas", h2)]
    pa = [["Piso", "Cota do pavimento", "Altura usada", "Origem"]]
    for p in modelo["pisos"]:
        c = (p.get("cota") or {}).get("valor")
        pa.append([p["piso"], "—" if c is None else f"{c:.2f}", "—" if not p.get("altura") else f"{p['altura']:.2f} m",
                   Paragraph(escape(p.get("altura_origem") or ""), small)])
    tp = Table(pa, colWidths=[35 * mm, 35 * mm, 30 * mm, 170 * mm], repeatRows=1)
    tp.setStyle(TableStyle(head))
    story += [tp, Spacer(1, 4 * mm)] + [Paragraph("• " + escape(x), small) for x in modelo.get("pressupostos", [])]
    # desenhos numerados
    pags = desenhos(modelo, titulo)
    for tt, im in pags:
        bio = io.BytesIO()
        im.save(bio, "PNG", optimize=True)
        bio.seek(0)
        iw, ih = ImageReader(bio).getSize()
        bio.seek(0)
        s = min((W - 26 * mm) / iw, (H - 36 * mm) / ih)
        story += [PageBreak(), RLImage(bio, iw * s, ih * s)]
    # anexos : lista de elementos numerados
    story += [PageBreak(), Paragraph("Anexo — elementos numerados", h2)]
    an = [["N.º", "Piso", "Elemento", "Medidas", "Quantidade"]]
    for p in modelo["pisos"]:
        for c in sorted(p["compartimentos"], key=lambda c: c["id"]):
            an.append([c["id"], p["piso"], Paragraph(escape(c["nome"]), small), f"perímetro {c['perimetro']:.2f} m"
                       + (f" · desenho {c['area_no_desenho']:.2f}" if c.get("area_no_desenho") else ""), f"{c['area']:.2f} m²"])
        for w in sorted(p.get("_paredes_un") or p["paredes"], key=lambda w: w["id"]):
            hh = p.get("altura")
            an.append([w["id"], p["piso"], f"parede {w['tipo']} e = {w['espessura']:.2f}", f"{w['comprimento']:.2f} m"
                       + (f" × {hh:.2f} m" if hh else ""), f"{w['comprimento'] * hh:.2f} m²" if hh else f"{w['comprimento']:.2f} m"])
        for d in sorted(p["portas"], key=lambda d: d["id"]):
            an.append([d["id"], p["piso"], f"porta {d['tipo']}", f"{d['L']:.2f} m", "1 un"])
    for v in modelo["alcados"]:
        for d in v["vaos"]:
            an.append([d["id"], v["vista"][:30], "vão exterior", f"{d['L']:.2f} × {d['H']:.2f} m (nível {d['nivel']})", f"{d['L'] * d['H']:.2f} m²"])
    ta = LongTable(an, colWidths=[22 * mm, 55 * mm, 70 * mm, 80 * mm, 30 * mm], repeatRows=1)
    ta.setStyle(TableStyle(head + [("ALIGN", (4, 1), (4, -1), "RIGHT")]))
    story += [ta]
    doc.build(story)
    raw = buf.getvalue()
    n_pisos = len(modelo["pisos"])
    capa = {"tipo": "Mapa de quantidades", "titulo": titulo, "subtitulo": "Da fundação à cobertura — elementos numerados e marcados",
            "local": "", "data": datetime.now(timezone.utc).date().isoformat(),
            "kpis": [("Artigos", str(len(L)), ""), ("Capítulos", str(len(set(r["capitulo"] for r in L) | set(n["capitulo"] for n in nm))), ""),
                     ("Pisos", str(n_pisos), ""), ("A medir", str(len(nm)), "")],
            "indice": ["Resumo por capítulo — da fundação à cobertura", "Medição — por capítulo e por piso",
                       "Pressupostos, alturas e origem das medidas", "Anexo — elementos numerados"],
            "imagem": _capa(pags)}
    out = PP.acabar(raw, capa, PP.com_cor(branding) if branding is not None else {}, "pt", paginas="completo")
    with open(caminho, "wb") as fh:
        fh.write(out)
    return caminho


# ---------------------------------------------------------------- Excel
def gerar_xlsx(modelo: dict, caminho: str, titulo: str, extras: list | None = None, nao_medido: list | None = None) -> str:
    from openpyxl import Workbook

    from engines.mapa_estrutura.excel import N2, _folha, _linha
    import os

    from openpyxl import load_workbook
    numerar(modelo)
    L = linhas(modelo, extras)
    if os.path.exists(caminho):
        wb = load_workbook(caminho)
        for nome in ("Mapa", "Elementos numerados"):
            if nome in wb.sheetnames:
                wb[nome].title = nome + " (resumo)" if nome == "Mapa" else nome + " (old)"
    else:
        wb = Workbook()
        wb.remove(wb.active)
    AZ = "Cada linha remete para os números marcados nas plantas (folha Controlo e PDF). Azul = medido ; preto = fórmula."
    ws = _folha(wb, "Mapa", ["Capítulo", "Piso / vista", "Designação", "Descrição / cálculo", "Elementos", "Quantidade", "Un", "Estado"],
                [22, 20, 44, 44, 30, 13, 6, 16], f"{titulo} — {AZ}")
    r = 5
    cap_rows = defaultdict(list)
    for x in L:
        _linha(ws, r, [x["capitulo"], x["piso"], x["designacao"], x.get("descricao"), x.get("refs"), x["qtd"], x["un"], x["estado"]], {6: N2}, (6,))
        cap_rows[(x["capitulo"], x["un"])].append(r)
        r += 1
    for n in nao_medido or []:
        _linha(ws, r, [n["capitulo"], n.get("piso"), n["designacao"], n.get("descricao"), n.get("refs"), None, n.get("un"), "a medir"])
        r += 1
    r += 1
    _linha(ws, r, ["TOTAIS POR CAPÍTULO E UNIDADE"], negrito=True)
    r += 1
    for (c, u), rows in cap_rows.items():
        _linha(ws, r, [c, None, None, None, None, "=" + "+".join(f"F{i}" for i in rows[:200]), u, None], {6: N2}, negrito=False)
        r += 1
    wp = _folha(wb, "Elementos numerados", ["N.º", "Piso", "Elemento", "Espessura (m)", "Comprimento (m)", "Altura (m)", "Quantidade", "Un"],
                [10, 16, 40, 12, 14, 11, 13, 6], AZ)
    r = 5
    for p in modelo["pisos"]:
        for c in sorted(p["compartimentos"], key=lambda c: c["id"]):
            _linha(wp, r, [c["id"], p["piso"], c["nome"], None, c["perimetro"], None, c["area"], "m²"], {5: N2, 7: N2}, (7,)); r += 1
        for w in sorted(p.get("_paredes_un") or p["paredes"], key=lambda w: w["id"]):
            hh = p.get("altura")
            _linha(wp, r, [w["id"], p["piso"], f"parede {w['tipo']}", w["espessura"], w["comprimento"], hh,
                           f"=E{r}*F{r}" if hh else f"=E{r}", "m²" if hh else "m"], {4: N2, 5: N2, 6: N2, 7: N2}, (4, 5, 6)); r += 1
        for d in sorted(p["portas"], key=lambda d: d["id"]):
            _linha(wp, r, [d["id"], p["piso"], f"porta {d['tipo']}", None, d["L"], None, 1, "un"], {5: N2}, (5,)); r += 1
    for v in modelo["alcados"]:
        for d in v["vaos"]:
            _linha(wp, r, [d["id"], v["vista"], "vão exterior", None, d["L"], d["H"], f"=E{r}*F{r}", "m²"], {5: N2, 6: N2, 7: N2}, (5, 6)); r += 1
    wb.move_sheet("Mapa", offset=-wb.sheetnames.index("Mapa"))
    wb.move_sheet("Elementos numerados", offset=1 - wb.sheetnames.index("Elementos numerados"))
    wb.save(caminho)
    return caminho
