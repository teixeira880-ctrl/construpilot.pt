"""Folhas de EXECUÇÃO de obra (como os desenhos de execução de referência do ConstruPilot):
  GO-01 estrutura e alvenarias do piso (eixos, cadeias de cotas, pilares, vigas, lintéis, paredes tramadas, notas)
  GO-02 planta de montagem e cofragem da laje (painéis, armaduras, vigas, aberturas, cotas pelos eixos)
  GO-03 pormenores de execução 1:20 (sapatas tipo, pilares tipo, vigas tipo, viga de fundação, bordo de laje e platibanda)
Tudo a partir do mesmo modelo (geometria real + motor de estrutura). Cada folha tem o seu painel de NOTAS.
"""
from __future__ import annotations

import math
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from shapely.geometry import box
from shapely.ops import unary_union

from . import outputs
from .drawings import (BLUE, GREEN, GREY, INK, LIGHT, ORANGE, RED, WALL, Frame, _axes, _bounds, _letters, _n, _t)


# ----------------------------------------------------------------------------- comuns
def notes(f: Frame, lines: list[str]):
    f.heading("NOTAS")
    c = f.c
    c.setFont("Helvetica", 6.3)
    c.setFillColor(INK)
    for s in lines:
        words, cur = _t(s).split(), "• "
        for w in words:
            if c.stringWidth(cur + w + " ", "Helvetica", 6.3) > 106 * mm:
                c.drawString(f.W - 120 * mm, f.col_y - 3 * mm, cur)
                f.col_y -= 8.6
                cur = "  "
            cur += w + " "
        c.drawString(f.W - 120 * mm, f.col_y - 3 * mm, cur)
        f.col_y -= 9.4
    f.col_y -= 3 * mm


def grid_chains(f: Frame, b, ax, ay, big=False, chains=True):
    """Eixos estruturais (A, B… / 1, 2…) com bolhas nos dois lados e cadeias de cotas exteriores entre eixos + totais."""
    fp = b.footprint
    x0, y0, x1, y1 = fp.bounds
    ts = 6.4 if big else 5.4
    for i, x in enumerate(ax):
        f.line([(x, y0 - 2.6), (x, y1 + 2.6)], GREY, 0.3, dash=[6, 2, 1, 2])
        for yy in (y0 - 3.1, y1 + 3.1):
            f.circle(x, yy, 2.6 if big else 2.2, INK, colors.white, 0.5)
            f.text(x, yy - 0.08, _letters(i), ts + 0.6, INK, True)
    for j, y in enumerate(ay):
        f.line([(x0 - 2.6, y), (x1 + 2.6, y)], GREY, 0.3, dash=[6, 2, 1, 2])
        for xx in (x0 - 3.1, x1 + 3.1):
            f.circle(xx, y, 2.6 if big else 2.2, INK, colors.white, 0.5)
            f.text(xx, y - 0.08, str(j + 1), ts + 0.6, INK, True)
    if not chains:
        return
    xs = [x0] + list(ax) + [x1]
    for a_, b_ in zip(xs, xs[1:]):
        if b_ - a_ > 0.02:
            f.dim((a_, y1), (b_, y1), 1.8, _n(b_ - a_), size=ts, color=INK)
    f.dim((x0, y1), (x1, y1), 2.4, _n(x1 - x0), size=ts + 0.4, color=INK)
    ys = [y0] + list(ay) + [y1]
    for a_, b_ in zip(ys, ys[1:]):
        if b_ - a_ > 0.02:
            f.dim((x0, a_), (x0, b_), -1.8, _n(b_ - a_), size=ts, color=INK)
    f.dim((x0, y0), (x0, y1), -2.4, _n(y1 - y0), size=ts + 0.4, color=INK)


def hatch(f: Frame, g, step=0.12, color=GREY, width=0.25):
    """Tramado a 45° de uma superfície (paredes de alvenaria)."""
    x0, y0, x1, y1 = g.bounds
    d = -(y1 - y0)
    from shapely.geometry import LineString
    while d < (x1 - x0):
        ln = LineString([(x0 + d, y0), (x0 + d + (y1 - y0), y1)]).intersection(g)
        for s in getattr(ln, "geoms", [ln]):
            if s.geom_type == "LineString" and s.length > 0.01:
                f.line(s, color, width)
        d += step


def struct_axes(R):
    pts = [(c["x"], c["y"]) for c in R.columns] + [(s["x"], s["y"]) for s in R.footings]
    return _axes([p[0] for p in pts], 0.30), _axes([p[1] for p in pts], 0.30)


# ----------------------------------------------------------------------------- GO-01 estrutura e alvenarias
def sheet_structure_masonry(c, b, R, lay, meta, slab_h):
    ax, ay = struct_axes(R)
    f = Frame(c, "Desenho de execução da estrutura e alvenarias — piso térreo", "GO-01", meta, _bounds(b, 4.2))
    f.clip_on()
    fp = b.footprint
    f.poly(fp, INK, 0.9, fill=colors.white)
    for q in b.hypotheses.get("faces") or []:
        f.line([(q[0], q[1]), (q[2], q[3])], INK, 0.3)
    walls = unary_union([w.line.buffer(w.t / 2, cap_style=2) for w in b.walls if w.retained_height <= 0]) if b.walls else None
    if walls is not None and not walls.is_empty:
        f.poly(walls, INK, 0.4, fill=colors.HexColor("#f3e8e8"))
        hatch(f, walls, 0.10, colors.HexColor("#c0262d"), 0.2)
    for v in R.beams:                                                # vigas (acima — tracejado)
        f.line(v["geom"].parallel_offset(v["b"] / 2, "left"), BLUE, 0.4, dash=[4, 2])
        f.line(v["geom"].parallel_offset(v["b"] / 2, "right"), BLUE, 0.4, dash=[4, 2])
        m = v["geom"].interpolate(0.5, normalized=True)
        f.text(m.x, m.y + 0.14, f"{v['id']} {int(v['b'] * 100)}×{int(v['h'] * 100)}", 4.8, BLUE, angle=outputs._angle(v["geom"]))
    for col in R.columns:
        a = col["a"]
        f.poly(box(col["x"] - a / 2, col["y"] - a / 2, col["x"] + a / 2, col["y"] + a / 2), RED, 0.4, fill=RED)
        f.text(col["x"] + a / 2 + 0.3, col["y"] + a / 2 + 0.08, f"{col['id']} {int(a * 100)}×{int(col['b'] * 100)}", 4.8, RED, True)
    for o in lay.openings:                                            # lintéis sobre os vãos
        m = o.edge.interpolate(0.5, normalized=True)
        L = round(o.width + 0.40, 2)
        f.text(m.x, m.y - 0.35, f"lintel L={_n(L)}", 4.4, GREEN)
    for r in lay.rooms:
        if r.placed:
            f.text(r.x, r.y, (r.number + ". " if r.number else "") + r.name, 5.4, GREY, True)
    for d in b.hypotheses.get("dims_text") or []:                     # cotas reais do projeto
        if d.get("ok"):
            f.dim(tuple(d["a"]), tuple(d["b"]), 0.0, _n(d["v"]), size=5.0, color=INK)
    grid_chains(f, b, ax, ay)
    f.clip_off()
    notes(f, [f"Paredes exteriores em tijolo térmico 20 cm; divisórias em tijolo 11 cm; argamassa M5. ETICS conforme estudo térmico.",
              f"Pilares C30/37, A500 NR (secções e armaduras no quadro E03 e pormenores GO-03); recobrimento 30 mm.",
              f"Vigas da laje de cobertura a tracejado (b × h em cm, por baixo da laje e = {_n(slab_h)} m).",
              "Lintéis BA sobre todos os vãos: apoio ≥ 0,20 m de cada lado; vãos > 3,0 m: viga calculada (E01).",
              "Cintas horizontais 20×20 ao nível da laje em todas as paredes de alvenaria (4Ø10, Ø6//0,20).",
              "Cotas em metros, a partir das faces acabadas das paredes; cotas do projeto confirmadas pela geometria desenhada.",
              "TODAS AS COTAS DEVEM SER CONFIRMADAS EM OBRA ANTES DA EXECUÇÃO."])
    f.legend([(colors.HexColor("#f3e8e8"), "Alvenaria (tramada)", "box"), (RED, "Pilar BA (id a×b cm)", "box"),
              (BLUE, "Viga sobre o piso (b×h cm)", "dash"), (GREEN, "Lintel sobre vão", "line"), (GREY, "Eixos estruturais", "dash")])
    c.showPage()


# ----------------------------------------------------------------------------- GO-02 cofragem da laje
def sheet_slab_formwork(c, b, R, meta, slab_h):
    ax, ay = struct_axes(R)
    f = Frame(c, "Planta de montagem e cofragem — laje de cobertura", "GO-02", meta, _bounds(b, 4.2))
    f.clip_on()
    f.poly(b.roof_slab, INK, 0.9, fill=colors.HexColor("#f7f7f2"))
    for p in R.panels:
        g = p["geom"]
        f.poly(g, GREEN, 0.3)
        q = g.representative_point()
        f.text(q.x, q.y + 0.45, f"{p['id']} — laje maciça e = {_n(slab_h)}", 5.8, GREEN, True)
        f.text(q.x, q.y + 0.1, f"inf. {p['inf']['label']} (2 dir.)" + (f" · sup. {p['sup']['label']}" if p.get("sup") else ""), 5.0, GREEN)
        f.text(q.x, q.y - 0.22, f"vão eq. {_n(p['Lx_eq'])} m · {p['tipo']}", 4.8, GREY)
    for v in R.beams:
        f.poly(v["geom"].buffer(v["b"] / 2, cap_style=2), BLUE, 0.4, fill=colors.HexColor("#dbe6fb"))
        m = v["geom"].interpolate(0.5, normalized=True)
        f.text(m.x, m.y + 0.18, f"{v['id']} {int(v['b'] * 100)}×{int(v['h'] * 100)} · {v['inf']['label']} / {v['sup']['label']}", 4.6, BLUE,
               angle=outputs._angle(v["geom"]))
        a, e = v["geom"].coords[0], v["geom"].coords[-1]
        off = 0.45
        f.dim(a, e, off, _n(v["L"]), size=4.6, color=BLUE)
    for col in R.columns:
        a = col["a"]
        f.poly(box(col["x"] - a / 2, col["y"] - a / 2, col["x"] + a / 2, col["y"] + a / 2), RED, 0.3, fill=RED)
    for h in b.footprint.interiors:                                   # aberturas (pátios) — cruz
        from shapely.geometry import Polygon
        P = Polygon(h)
        x0, y0, x1, y1 = P.bounds
        f.line([(x0, y0), (x1, y1)], INK, 0.4)
        f.line([(x0, y1), (x1, y0)], INK, 0.4)
        q = P.representative_point()
        f.text(q.x, q.y + 0.15, "ABERTURA (pátio)", 5.4, INK, True)
        f.text(q.x, q.y - 0.25, f"{_n(x1 - x0)} × {_n(y1 - y0)}", 5.4, INK)
    grid_chains(f, b, ax, ay)
    f.clip_off()
    notes(f, [f"Laje maciça de betão C30/37, e = {_n(slab_h)} m, aço A500 NR; recobrimento 25 mm (XC1), 35 mm na face superior (cobertura).",
              "Armadura inferior nas duas direções em toda a laje; armadura superior sobre vigas e apoios contínuos (comprimento 0,30 L de cada lado).",
              "Reforço de aberturas: 2Ø12 em cada bordo, prolongados 0,60 m para lá dos cantos + 2Ø10 a 45° nos cantos.",
              "Cofragem: escoramento a cada 1,20 m máx.; descofragem ≥ 21 dias (fundos) salvo verificação.",
              "Vigas: armaduras inferior / superior indicadas; estribos conforme quadro E03 e pormenores GO-03.",
              "Platibanda BA h = 0,50 m em todo o contorno com capeamento e pingadeira.",
              "TODAS AS COTAS DEVEM SER CONFIRMADAS EM OBRA ANTES DA EXECUÇÃO."])
    f.legend([(colors.HexColor("#f7f7f2"), "Laje maciça (painéis Ln)", "box"), (colors.HexColor("#dbe6fb"), "Viga BA (b×h cm, L)", "box"),
              (RED, "Pilar", "box"), (GREY, "Eixos estruturais", "dash")])
    c.showPage()


# ----------------------------------------------------------------------------- GO-03 pormenores 1:20
_BAR = re.compile(r"(\d+)\s*Ø\s*(\d+)")


def _bars(label):
    m = _BAR.search(str(label or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (4, 12)


def sheet_details(c, b, R, meta, slab_h):
    """Pormenores à escala 1:20 desenhados com as dimensões e armaduras CALCULADAS (tipos agrupados)."""
    W, H = landscape(A3)
    f = Frame(c, "Pormenores de execução — fundações, pilares, vigas, laje", "GO-03", meta, (0, 0, 1, 1), scale=20,
              area=(15 * mm, 15 * mm, W - 130 * mm, H - 15 * mm))
    k = 1000 / 20 * mm                                                 # pontos por metro a 1:20
    cv = f.c

    def rect(x, y, w, h, fill=None, stroke=INK, lw=0.6):
        cv.setStrokeColor(stroke)
        cv.setLineWidth(lw)
        if fill is not None:
            cv.setFillColor(fill)
        cv.rect(x, y, w, h, stroke=1, fill=1 if fill is not None else 0)

    def label(x, y, s, size=6.4, bold=False, color=INK, align="l"):
        cv.setFillColor(color)
        cv.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        {"l": cv.drawString, "c": cv.drawCentredString, "r": cv.drawRightString}[align](x, y, _t(s))

    def hdim(x0, x1, y, txt):
        cv.setStrokeColor(INK)
        cv.setLineWidth(0.35)
        cv.line(x0, y, x1, y)
        for X in (x0, x1):
            cv.line(X - 2, y - 2, X + 2, y + 2)
            cv.line(X, y - 4, X, y + 4)
        label((x0 + x1) / 2, y + 2, txt, 5.8, align="c")

    def vdim(x, y0, y1, txt):
        cv.setStrokeColor(INK)
        cv.setLineWidth(0.35)
        cv.line(x, y0, x, y1)
        for Y in (y0, y1):
            cv.line(x - 2, Y - 2, x + 2, Y + 2)
            cv.line(x - 4, Y, x + 4, Y)
        cv.saveState()
        cv.translate(x - 3, (y0 + y1) / 2)
        cv.rotate(90)
        label(0, 0, txt, 5.8, align="c")
        cv.restoreState()

    def dot(x, y, phi):
        cv.setFillColor(RED)
        cv.circle(x, y, max(1.3, phi / 1000 * k / 2 * 1.4), stroke=0, fill=1)

    # tipos
    ftypes = {}
    for s_ in R.footings:
        ftypes.setdefault((s_["B"], s_["h"], s_["armadura"]), []).append(s_["id"])
    ctypes = {}
    for p in R.columns:
        ctypes.setdefault((p["a"], p["b"], p["armadura"]["label"], str(p.get("estribos"))), []).append(p["id"])
    btypes = {}
    for v in R.beams:
        btypes.setdefault((v["b"], v["h"], v["inf"]["label"], v["sup"]["label"], str(v.get("estribos"))), []).append(v["id"])
    # ---- sapatas tipo (até 4)
    x, y_top = 18 * mm, H - 22 * mm
    label(x, y_top, "SAPATAS ISOLADAS — corte tipo (1:20)", 8.5, True)
    cx = x
    for i, ((B, h, arm), ids) in enumerate(sorted(ftypes.items(), key=lambda kv: -kv[0][0])[:4]):
        w = B * k
        base = y_top - 8 * mm - (h + 0.30) * k
        rect(cx - 0.05 * k, base - 0.10 * k, w + 0.10 * k, 0.10 * k, colors.HexColor("#e5e7eb"))
        rect(cx, base, w, h * k, colors.HexColor("#fde68a"))
        a = 0.25 * k
        rect(cx + w / 2 - a / 2, base + h * k, a, 0.3 * k, colors.HexColor("#fecaca"))
        cv.setStrokeColor(RED)
        cv.setLineWidth(0.9)
        cv.line(cx + 0.04 * k, base + 0.05 * k, cx + w - 0.04 * k, base + 0.05 * k)
        cv.line(cx + 0.04 * k, base + 0.05 * k, cx + 0.04 * k, base + h * k - 0.05 * k)
        cv.line(cx + w - 0.04 * k, base + 0.05 * k, cx + w - 0.04 * k, base + h * k - 0.05 * k)
        for xx in (cx + w / 2 - a / 2 + 0.04 * k, cx + w / 2 + a / 2 - 0.04 * k):
            cv.line(xx, base + 0.06 * k, xx, base + h * k + 0.3 * k)
            cv.line(xx, base + 0.06 * k, xx + (0.15 * k if xx > cx + w / 2 else -0.15 * k), base + 0.06 * k)
        hdim(cx, cx + w, base - 0.10 * k - 7, f"B = {_n(B)}")
        vdim(cx - 6, base, base + h * k, f"h = {_n(h)}")
        label(cx, base - 0.10 * k - 16, f"SI{i + 1}: {', '.join(ids[:6])}{'…' if len(ids) > 6 else ''}", 5.8, True)
        label(cx, base - 0.10 * k - 23, f"{arm} · recobr. 40 mm", 5.6, color=RED)
        cx += max(w, 30 * mm) + 14 * mm
    # ---- pilares tipo
    y2 = y_top - 72 * mm
    label(x, y2, "PILARES — secções tipo (1:20)", 8.5, True)
    cx = x
    for i, ((a_, b_, arm, est), ids) in enumerate(sorted(ctypes.items())[:5]):
        w, hh = a_ * k, b_ * k
        y0 = y2 - 10 * mm - hh
        rect(cx, y0, w, hh, colors.HexColor("#f3f4f6"))
        cv.setStrokeColor(RED)
        cv.setLineWidth(0.8)
        cv.rect(cx + 0.03 * k, y0 + 0.03 * k, w - 0.06 * k, hh - 0.06 * k, stroke=1, fill=0)
        n, phi = _bars(arm)
        per_side = max(2, n // 4 + 1)
        pts = set()
        for t in range(per_side):
            u = t / (per_side - 1)
            for X, Y in ((u, 0), (u, 1), (0, u), (1, u)):
                pts.add((round(X, 3), round(Y, 3)))
        for X, Y in list(pts)[:n] if len(pts) > n else pts:
            dot(cx + (0.045 + X * (a_ - 0.09)) * k, y0 + (0.045 + Y * (b_ - 0.09)) * k, phi)
        hdim(cx, cx + w, y0 - 7, f"{int(a_ * 100)}")
        vdim(cx - 6, y0, y0 + hh, f"{int(b_ * 100)}")
        label(cx, y0 - 16, f"P{i + 1}: {arm} · cintas {est}", 5.8, True)
        label(cx, y0 - 23, ", ".join(ids[:5]) + ("…" if len(ids) > 5 else ""), 5.4, color=GREY)
        cx += max(w, 24 * mm) + 22 * mm
    # ---- vigas tipo
    y3 = y2 - 62 * mm
    label(x, y3, "VIGAS — secções tipo (1:20)", 8.5, True)
    cx = x + 0.25 * k + 4 * mm
    for i, ((bw, hb, inf, sup, est), ids) in enumerate(sorted(btypes.items(), key=lambda kv: -len(kv[1]))[:5]):
        w, hh = bw * k, hb * k
        y0 = y3 - 10 * mm - hh
        rect(cx - 0.25 * k, y0 + hh - slab_h * k, w + 0.5 * k, slab_h * k, colors.HexColor("#e5e7eb"))   # laje colaborante
        rect(cx, y0, w, hh, colors.HexColor("#f3f4f6"))
        cv.setStrokeColor(RED)
        cv.setLineWidth(0.8)
        cv.rect(cx + 0.03 * k, y0 + 0.03 * k, w - 0.06 * k, hh - 0.06 * k, stroke=1, fill=0)
        n1, p1 = _bars(inf)
        n2, p2 = _bars(sup)
        for j in range(n1 if n1 <= 4 else 4):
            dot(cx + (0.045 + j * (bw - 0.09) / max(1, min(n1, 4) - 1)) * k, y0 + 0.045 * k, p1)
        if n1 > 4:
            for j in range(min(n1 - 4, 4)):
                dot(cx + (0.045 + j * (bw - 0.09) / max(1, min(n1 - 4, 4) - 1)) * k, y0 + 0.09 * k, p1)
        for j in range(min(n2, 4)):
            dot(cx + (0.045 + j * (bw - 0.09) / max(1, min(n2, 4) - 1)) * k, y0 + hh - 0.045 * k, p2)
        hdim(cx, cx + w, y0 - 7, f"{int(bw * 100)}")
        vdim(cx - 6, y0, y0 + hh, f"{int(hb * 100)}")
        label(cx - 0.25 * k, y0 - 16, f"V{i + 1}: inf. {inf} · sup. {sup} · est. {est}", 5.8, True)
        label(cx - 0.25 * k, y0 - 23, ", ".join(ids[:6]) + ("…" if len(ids) > 6 else ""), 5.4, color=GREY)
        cx += max(w + 0.5 * k, 30 * mm) + 18 * mm
    # ---- viga de fundação + bordo de laje / platibanda
    y4 = y3 - 62 * mm
    label(x, y4, "VIGA DE FUNDAÇÃO e BORDO DA LAJE / PLATIBANDA (1:20)", 8.5, True)
    if R.tie_beams:
        t = R.tie_beams[0]
        w, hh = t["b"] * k, t["h"] * k
        y0 = y4 - 12 * mm - hh
        rect(x, y0, w, hh, colors.HexColor("#c7ccd3"))
        cv.setStrokeColor(RED)
        cv.rect(x + 0.03 * k, y0 + 0.03 * k, w - 0.06 * k, hh - 0.06 * k, stroke=1, fill=0)
        for j in range(2):
            dot(x + (0.045 + j * (t["b"] - 0.09)) * k, y0 + 0.045 * k, _bars(t["inf"]["label"])[1])
            dot(x + (0.045 + j * (t["b"] - 0.09)) * k, y0 + hh - 0.045 * k, _bars(t["sup"]["label"])[1])
        hdim(x, x + w, y0 - 7, f"{int(t['b'] * 100)}")
        vdim(x - 6, y0, y0 + hh, f"{int(t['h'] * 100)}")
        label(x, y0 - 16, f"VF: inf. {t['inf']['label']} · sup. {t['sup']['label']} · est. {t['estribos']}", 5.8, True)
    # bordo de laje + platibanda + ETICS
    WL = 0.40                                                              # parede visível sob a laje
    bx0, by0 = x + 70 * mm, y4 - 8 * mm - (WL + slab_h + 0.5) * k
    rect(bx0, by0, 0.20 * k, WL * k, colors.HexColor("#d6c7b0"))                        # parede
    rect(bx0 - 0.12 * k, by0, 0.12 * k, (WL + slab_h + 0.5) * k, colors.HexColor("#fde68a"))   # ETICS
    rect(bx0, by0 + WL * k, 1.4 * k, slab_h * k, colors.HexColor("#9ca3af"))            # laje
    rect(bx0, by0 + (WL + slab_h) * k, 0.15 * k, 0.5 * k, colors.HexColor("#9ca3af"))   # platibanda
    rect(bx0 + 0.15 * k, by0 + (WL + slab_h) * k, 1.25 * k, 0.14 * k, colors.HexColor("#fde68a"))   # XPS
    cv.setStrokeColor(colors.HexColor("#111827"))
    cv.setLineWidth(1.4)
    cv.line(bx0 + 0.15 * k, by0 + (WL + slab_h) * k + 0.01 * k, bx0 + 1.4 * k, by0 + (WL + slab_h) * k + 0.01 * k)   # impermeab.
    vdim(bx0 + 1.55 * k, by0 + WL * k, by0 + (WL + slab_h) * k, f"e = {_n(slab_h)}")
    vdim(bx0 - 0.25 * k, by0 + (WL + slab_h) * k, by0 + (WL + slab_h + 0.5) * k, "0,50")
    label(bx0 + 0.3 * k, by0 + (WL + slab_h) * k + 0.18 * k, "XPS + membrana + gravilha (cobertura invertida)", 5.6)
    label(bx0 + 0.3 * k, by0 + WL * k - 9, "laje maciça C30/37 · ETICS contínuo até ao capeamento da platibanda", 5.6)
    notes(f, ["Betão C30/37 (XC2 fundações, XC1 interiores, XC3 platibandas); aço A500 NR; recobrimentos: sapatas 40, vigas/pilares 30, lajes 25 mm.",
              "Sapatas sobre betão de limpeza C12/15 e = 0,10 m; assentamento −0,80 m mínimo, a confirmar com o estudo geotécnico.",
              "Arranques dos pilares com dobra de 0,15 m na malha da sapata; emendas por sobreposição 50 Ø.",
              "Estribos fechados com ganchos a 135°; primeiro estribo a 5 cm da face do apoio.",
              "Tipos agrupados pelos valores calculados (dimensões e armaduras iguais); lista completa no quadro E03.",
              "TODAS AS COTAS DEVEM SER CONFIRMADAS EM OBRA ANTES DA EXECUÇÃO."])
    f.legend([(colors.HexColor("#fde68a"), "Sapata / isolamento térmico", "box"), (colors.HexColor("#f3f4f6"), "Secção de betão", "box"),
              (RED, "Armaduras (varões e estribos)", "line")])
    c.showPage()
