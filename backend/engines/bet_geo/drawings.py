"""Peças desenhadas de EXECUÇÃO sobre a geometria real (PDF A3, à escala, cotadas).

  A01 planta de arquitetura cotada (divisões, áreas, pé-direito, vãos, cotas parciais e totais, quadro de áreas)
  A02 cortes AA' e BB' (níveis, laje, vigas, fundações, isolamentos)
  A03 alçados (4 fachadas projetadas do modelo 3D real)
  E01 planta estrutural da cobertura · E02 fundações · E03 quadros de armaduras
  EL01 eletricidade (tomadas, iluminação, quadro) · EL02 esquema unifilar
  AG01 águas e esgotos · VT01 ventilação · AQ01 piso radiante · AQ02 esquema hidráulico
Tudo vem dos motores (estrutura, REH, especialidades); nada é desenhado sem número calculado por trás.
"""
from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from . import outputs
from .model import Building
from .rooms import Layout, _room_of

INK = colors.HexColor("#1f2933")
GREY = colors.HexColor("#9aa5b1")
LIGHT = colors.HexColor("#e5e7eb")
WALL = colors.HexColor("#4b5563")
BLUE = colors.HexColor("#1d4ed8")
RED = colors.HexColor("#c0262d")
GREEN = colors.HexColor("#0f766e")
ORANGE = colors.HexColor("#c2410c")
BROWN = colors.HexColor("#7c4a1e")
VIOLET = colors.HexColor("#7c3aed")
_t, _n = outputs._t, outputs._n
SCALES = (20, 25, 50, 75, 100, 125, 150, 200, 250, 500, 1000)


class Frame:
    """Folha A3 horizontal: área de desenho à esquerda, coluna de 115 mm à direita (quadros, legenda, carimbo)."""

    def __init__(self, c, title, number, meta, bounds, scale=None, area=None, logo=None):
        self.c = c
        W, H = landscape(A3)
        self.W, self.H = W, H
        ax0, ay0, ax1, ay1 = area or (15 * mm, 15 * mm, W - 130 * mm, H - 15 * mm)
        x0, y0, x1, y1 = bounds
        if scale is None:
            scale = next((s for s in SCALES if (x1 - x0) * 1000 / s * mm <= (ax1 - ax0) and (y1 - y0) * 1000 / s * mm <= (ay1 - ay0)), SCALES[-1])
        self.scale = scale
        self.k = 1000 / scale * mm
        self.ox = ax0 + ((ax1 - ax0) - (x1 - x0) * self.k) / 2 - x0 * self.k
        self.oy = ay0 + ((ay1 - ay0) - (y1 - y0) * self.k) / 2 - y0 * self.k
        self.col_y = H - 15 * mm                       # cursor da coluna direita (de cima para baixo)
        self._frame(title, number, meta)

    # ---- moldura e carimbo
    def _frame(self, title, number, meta):
        c, W, H = self.c, self.W, self.H
        c.setStrokeColor(INK)
        c.setLineWidth(0.9)
        c.rect(8 * mm, 8 * mm, W - 16 * mm, H - 16 * mm)
        c.setLineWidth(0.4)
        c.line(W - 123 * mm, 8 * mm, W - 123 * mm, H - 8 * mm)
        bx, by = W - 120 * mm, 11 * mm
        c.setFillColor(colors.HexColor("#0f3d2e"))
        c.rect(bx, by + 40 * mm, 109 * mm, 9 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(bx + 3 * mm, by + 43 * mm, _t(meta.get("company") or "ConstruPilot"))
        c.setFont("Helvetica-Bold", 16)
        c.drawRightString(bx + 106 * mm, by + 42.5 * mm, number)
        c.setFillColor(INK)
        fs = 11.5
        while c.stringWidth(_t(title), "Helvetica-Bold", fs) > 103 * mm and fs > 7:
            fs -= 0.5
        c.setFont("Helvetica-Bold", fs)
        c.drawString(bx + 3 * mm, by + 33 * mm, _t(title))
        c.setFont("Helvetica", 7.6)
        rows = [f"Obra: {meta.get('obra', '-')}"[:80],
                f"Local: {meta.get('local') or '-'}"[:80],
                f"Escala 1:{self.scale}   ·   Data {_dt.date.today().strftime('%d/%m/%Y')}   ·   Fase: projeto de execução (pré-dim.)",
                "Geometria real lida das peças do cliente — cotas em metros",
                "A validar e assinar pelos técnicos autores dos projetos de especialidade"]
        for i, s in enumerate(rows):
            c.drawString(bx + 3 * mm, by + (27 - 5.2 * i) * mm, _t(s))
        c.rect(bx, by, 109 * mm, 49 * mm)

    # ---- mundo → folha
    def p(self, x, y):
        return self.ox + x * self.k, self.oy + y * self.k

    def poly(self, g, stroke=INK, width=0.5, fill=None, dash=None):
        c = self.c
        for p in getattr(g, "geoms", [g]):
            if p.is_empty or p.geom_type != "Polygon":
                continue
            path = c.beginPath()
            for ring in [p.exterior, *p.interiors]:
                pts = [self.p(*q) for q in ring.coords]
                path.moveTo(*pts[0])
                for q in pts[1:]:
                    path.lineTo(*q)
                path.close()
            c.setStrokeColor(stroke)
            c.setLineWidth(width)
            c.setDash(*(dash or []))
            if fill is not None:
                c.setFillColor(fill)
            c.drawPath(path, stroke=1 if width > 0 else 0, fill=1 if fill is not None else 0, fillMode=0)
            c.setDash()

    def line(self, pts, stroke=INK, width=0.5, dash=None):
        c = self.c
        cs = [self.p(*q) for q in (pts.coords if hasattr(pts, "coords") else pts)]
        c.setStrokeColor(stroke)
        c.setLineWidth(width)
        c.setDash(*(dash or []))
        path = c.beginPath()
        path.moveTo(*cs[0])
        for q in cs[1:]:
            path.lineTo(*q)
        c.drawPath(path, stroke=1, fill=0)
        c.setDash()

    def text(self, x, y, s, size=6.5, color=INK, bold=False, angle=0.0, align="c"):
        c = self.c
        c.saveState()
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        X, Y = self.p(x, y)
        c.translate(X, Y)
        c.rotate(angle)
        {"c": c.drawCentredString, "l": c.drawString, "r": c.drawRightString}[align](0, 0, _t(s))
        c.restoreState()

    def circle(self, x, y, r_mm, stroke=INK, fill=None, width=0.4):
        X, Y = self.p(x, y)
        self.c.setStrokeColor(stroke)
        self.c.setLineWidth(width)
        if fill is not None:
            self.c.setFillColor(fill)
        self.c.circle(X, Y, r_mm * mm, stroke=1, fill=1 if fill is not None else 0)

    def dim(self, a, b, off, text=None, size=5.6, color=INK):
        """Cota alinhada entre a e b, deslocada `off` metros para a esquerda do sentido a→b."""
        (x0, y0), (x1, y1) = a, b
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-6:
            return
        nx, ny = -(y1 - y0) / L, (x1 - x0) / L
        A, B = (x0 + nx * off, y0 + ny * off), (x1 + nx * off, y1 + ny * off)
        self.line([(x0 + nx * 0.15 * math.copysign(1, off), y0 + ny * 0.15 * math.copysign(1, off)), (A[0] + nx * 0.15 * math.copysign(1, off), A[1] + ny * 0.15 * math.copysign(1, off))], GREY, 0.25)
        self.line([(x1 + nx * 0.15 * math.copysign(1, off), y1 + ny * 0.15 * math.copysign(1, off)), (B[0] + nx * 0.15 * math.copysign(1, off), B[1] + ny * 0.15 * math.copysign(1, off))], GREY, 0.25)
        self.line([A, B], color, 0.35)
        t = 0.12
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        for P in (A, B):
            self.line([(P[0] - (ux + nx) * t, P[1] - (uy + ny) * t), (P[0] + (ux + nx) * t, P[1] + (uy + ny) * t)], color, 0.6)
        ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
        if ang > 90:
            ang -= 180
        elif ang <= -90:
            ang += 180
        mx, my = (A[0] + B[0]) / 2 + nx * 0.12 * math.copysign(1, off), (A[1] + B[1]) / 2 + ny * 0.12 * math.copysign(1, off)
        self.text(mx, my, text or _n(L), size, color, angle=ang)

    # ---- coluna direita
    def heading(self, s):
        self.c.setFont("Helvetica-Bold", 8.5)
        self.c.setFillColor(INK)
        self.c.drawString(self.W - 120 * mm, self.col_y - 4 * mm, _t(s))
        self.col_y -= 7 * mm

    def table(self, header, rows, widths_mm, size=6.3, max_rows=40):
        c = self.c
        x0 = self.W - 120 * mm
        lh = size * 1.45
        rows = rows[:max_rows]
        y = self.col_y
        c.setFillColor(colors.HexColor("#e8efe9"))
        c.rect(x0, y - lh, sum(widths_mm) * mm, lh, stroke=0, fill=1)
        for i, row in enumerate([header] + rows):
            x = x0
            c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", size)
            c.setFillColor(INK)
            for v, w in zip(row, widths_mm):
                s = _t(v)
                while c.stringWidth(s, "Helvetica", size) > w * mm - 1.5 and len(s) > 3:
                    s = s[:-2]
                c.drawString(x + 0.8 * mm, y - lh + 1.6, s)
                x += w * mm
            y -= lh
            c.setStrokeColor(LIGHT)
            c.setLineWidth(0.3)
            c.line(x0, y, x0 + sum(widths_mm) * mm, y)
        self.col_y = y - 4 * mm

    def legend(self, items):
        c = self.c
        x0 = self.W - 120 * mm
        for col, txt, kind in items:
            y = self.col_y - 3 * mm
            c.setStrokeColor(col)
            c.setFillColor(col)
            if kind == "line":
                c.setLineWidth(1.2)
                c.line(x0, y + 1, x0 + 7 * mm, y + 1)
            elif kind == "dash":
                c.setLineWidth(1.0)
                c.setDash(3, 2)
                c.line(x0, y + 1, x0 + 7 * mm, y + 1)
                c.setDash()
            elif kind == "dot":
                c.circle(x0 + 3.5 * mm, y + 1, 1.3 * mm, stroke=0, fill=1)
            else:
                c.rect(x0, y - 0.5 * mm, 7 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica", 6.8)
            c.drawString(x0 + 9 * mm, y, _t(txt)[:75])
            self.col_y -= 4.6 * mm
        self.col_y -= 2 * mm

    def para(self, lines, size=6.5):
        c = self.c
        c.setFont("Helvetica", size)
        c.setFillColor(INK)
        for s in lines:
            c.drawString(self.W - 120 * mm, self.col_y - 3 * mm, _t(s)[:95])
            self.col_y -= size * 1.45
        self.col_y -= 2 * mm

    def north(self, deg=90.0):
        c = self.c
        X, Y = self.W - 132 * mm, self.H - 28 * mm
        a = math.radians(deg)
        c.setFillColor(INK)
        c.setStrokeColor(INK)
        c.circle(X, Y, 7 * mm, stroke=1, fill=0)
        tip = (X + 6 * mm * math.cos(a), Y + 6 * mm * math.sin(a))
        l = (X + 2.5 * mm * math.cos(a + 2.5), Y + 2.5 * mm * math.sin(a + 2.5))
        r = (X + 2.5 * mm * math.cos(a - 2.5), Y + 2.5 * mm * math.sin(a - 2.5))
        p = c.beginPath()
        p.moveTo(*tip)
        p.lineTo(*l)
        p.lineTo(X, Y)
        p.lineTo(*r)
        p.close()
        c.drawPath(p, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(tip[0] + 3 * mm * math.cos(a), tip[1] + 3 * mm * math.sin(a) - 1, "N")


def _bounds(b: Building, pad=3.5):
    x0, y0, x1, y1 = b.roof_slab.bounds
    return x0 - pad, y0 - pad, x1 + pad, y1 + pad


def _base(f: Frame, b: Building, walls_fill=WALL, ghost=False):
    """Contorno, pátios, palas e paredes."""
    f.poly(b.footprint, INK if not ghost else GREY, 0.9 if not ghost else 0.5, fill=colors.white)
    for cv in b.covered:
        f.poly(cv, GREY, 0.4, dash=[3, 2])
    wl = unary_union([w.line.buffer(w.t / 2, cap_style=2) for w in b.walls]) if b.walls else None
    if wl is not None:
        f.poly(wl, walls_fill if not ghost else GREY, 0.2, fill=walls_fill if not ghost else LIGHT)
    for h in b.footprint.interiors:
        c = __import__("shapely.geometry", fromlist=["Polygon"]).Polygon(h)
        q = c.representative_point()
        f.text(q.x, q.y, "PÁTIO", 6.5, GREY, True)


# ----------------------------------------------------------------------------- A01 arquitetura
def sheet_architecture(c, b: Building, lay: Layout, esp: dict, meta: dict):
    f = Frame(c, "Planta de arquitetura — piso térreo (cotada)", "A01", meta, _bounds(b, 4.5))
    _base(f, b)
    for o in lay.openings:                                        # vãos: caixilho (linha dupla fina)
        (x0, y0), (x1, y1) = o.edge.coords[0], o.edge.coords[-1]
        L = o.edge.length
        nx, ny = -(y1 - y0) / L * 0.06, (x1 - x0) / L * 0.06
        f.line([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny)], BLUE, 0.5)
        f.line([(x0 - nx, y0 - ny), (x1 - nx, y1 - ny)], BLUE, 0.5)
    hsp = esp["env"].hsp
    for r in lay.rooms:
        if not r.placed:
            continue
        lab = (r.number + ". " if r.number else "") + r.name
        f.text(r.x, r.y + 0.28, lab, 6.2, INK, True)
        f.text(r.x, r.y - 0.12, f"{_n(r.area)} m²" + ("" if r.type == "exterior" else f" · p.d. {_n(hsp)}"), 5.6, GREEN)
    # cotas parciais de cada aresta + totais
    fp = b.footprint
    ccw = fp.exterior.is_ccw
    coords = list(fp.exterior.coords)
    for a, bb in zip(coords, coords[1:]):
        if math.dist(a, bb) >= 0.4:
            f.dim(a, bb, -1.3 if ccw else 1.3)                    # para fora do contorno
    for h in fp.interiors:
        hc = list(h.coords)
        hccw = __import__("shapely.geometry", fromlist=["LinearRing"]).LinearRing(h).is_ccw
        for a, bb in zip(hc, hc[1:]):
            if math.dist(a, bb) >= 0.6:
                f.dim(a, bb, 0.7 if hccw else -0.7, size=5.0, color=GREY)
    x0, y0, x1, y1 = fp.bounds
    f.dim((x0, y0), (x1, y0), -3.0, size=6.5)
    f.dim((x1, y0), (x1, y1), -3.0, size=6.5)
    # espessuras de parede (amostra: as mais compridas)
    for w in sorted(b.walls, key=lambda w: -w.length)[:12]:
        m = w.line.interpolate(0.5, normalized=True)
        f.text(m.x, m.y, f"e={_n(w.t)}", 4.4, colors.white, angle=outputs._angle(w.line))
    f.north(float(b.hypotheses.get("north_deg") or 90.0))
    f.legend([(WALL, "Paredes lidas (espessura e= m)", "box"), (BLUE, "Troço de fachada sem parede lida — vão envidraçado", "line")])
    f.heading("Quadro de áreas")
    rows = [[(r.number or "-"), r.name, _n(r.area), r.type.replace("_", " "), "sim" if r.heated else "não"] for r in lay.rooms]
    f.table(["N.º", "Divisão", "Área m²", "Uso", "Aquec."], rows, [9, 46, 15, 24, 13], size=6.0, max_rows=30)
    f.para([f"Área de construção (contorno lido): {_n(fp.area)} m²",
            f"Área útil aquecida: {_n(lay.useful_area)} m² · pé-direito livre {_n(hsp)} m",
            f"Vãos exteriores: {len(lay.windows) or len(lay.openings)} ({_n(sum(w.area for w in lay.windows) or esp['env'].glazing_total)} m²)"])
    if lay.windows:
        f.heading("Mapa de vãos exteriores")
        f.table(["Vão", "L × H (m)", "Divisão", "Or."], [[w.name, f"{_n(w.w)} × {_n(w.h)}", w.room, w.orient or "-"] for w in lay.windows],
                [14, 22, 62, 9], size=5.8, max_rows=24)
    c.showPage()


# ----------------------------------------------------------------------------- A02 cortes
def _section(b: Building, R, axis: str, at: float, slab_h: float):
    fp = b.footprint
    x0, y0, x1, y1 = fp.bounds
    ln = LineString([(x0 - 1, at), (x1 + 1, at)]) if axis == "x" else LineString([(at, y0 - 1), (at, y1 + 1)])
    cut = ln.intersection(fp)
    segs = []
    for g in getattr(cut, "geoms", [cut]):
        if g.geom_type == "LineString" and g.length > 0.2:
            (a, _), (bq, _) = sorted([(g.coords[0][0], 0), (g.coords[-1][0], 0)]) if axis == "x" else sorted([(g.coords[0][1], 0), (g.coords[-1][1], 0)])
            segs.append((a, bq))
    beams = []
    for v in R.beams:
        hit = v["geom"].intersection(ln)
        if not hit.is_empty and hit.geom_type == "Point":
            beams.append(((hit.x if axis == "x" else hit.y), v))
    walls = []
    for w in b.walls:
        hit = w.line.intersection(ln)
        if not hit.is_empty and hit.geom_type == "Point":
            walls.append(((hit.x if axis == "x" else hit.y), w))
    return segs, beams, walls


def _draw_section(f: Frame, b, R, segs, beams, walls, slab_h, env, sol, ox, oz, title):
    fl, top = b.floor_level, b.roof_level
    par = 0.5
    s_min = min(a for a, _ in segs)
    s_max = max(bq for _, bq in segs)

    def P(s, z):
        return (ox + s - s_min, oz + z)
    # terreno e fundações
    f.line([P(s_min - 2, fl - 0.20), P(s_max + 2, fl - 0.20)], BROWN, 0.6)
    for a, bq in segs:
        # laje térrea + XPS + betonilha
        f.poly(box(*P(a, fl - 0.35), *P(bq, fl - 0.20)), GREY, 0.2, fill=colors.HexColor("#f1e7d0"))      # enrocamento
        f.poly(box(*P(a, fl - 0.20), *P(bq, fl - 0.05)), INK, 0.3, fill=colors.HexColor("#c7ccd3"))       # laje térrea
        f.poly(box(*P(a, fl - 0.05), *P(bq, fl)), INK, 0.2, fill=colors.HexColor("#fde68a"))              # XPS + betonilha
        # laje de cobertura + isolamento + parapeito
        f.poly(box(*P(a - 0.15, top - slab_h), *P(bq + 0.15, top)), INK, 0.4, fill=colors.HexColor("#9ca3af"))
        f.poly(box(*P(a - 0.15, top), *P(bq + 0.15, top + sol.roof / 1000 + 0.05)), INK, 0.2, fill=colors.HexColor("#fde68a"))
        for s in (a, bq):
            f.poly(box(*P(s - 0.10, top), *P(s + 0.10, top + par)), INK, 0.3, fill=colors.HexColor("#9ca3af"))
            # parede exterior + ETICS + viga de fundação
            inner = 1 if s == a else -1
            f.poly(box(*P(min(s, s + inner * 0.20), fl), *P(max(s, s + inner * 0.20), top - slab_h)), INK, 0.3, fill=colors.HexColor("#d6c7b0"))
            f.poly(box(*P(min(s, s - inner * sol.etics / 1000), fl - 0.2), *P(max(s, s - inner * sol.etics / 1000), top + par)),
                   GREY, 0.2, fill=colors.HexColor("#fde68a"))
            f.poly(box(*P(min(s, s + inner * 0.30), fl - 0.80), *P(max(s, s + inner * 0.30), fl - 0.20)), INK, 0.3, fill=colors.HexColor("#c7ccd3"))
    for s, w in walls:
        if not w.exterior and any(a + 0.3 < s < bq - 0.3 for a, bq in segs):
            f.poly(box(*P(s - w.t / 2, fl), *P(s + w.t / 2, top - slab_h)), INK, 0.2, fill=colors.HexColor("#e5dccd"))
    for s, v in beams:
        f.poly(box(*P(s - v["b"] / 2, top - v["h"]), *P(s + v["b"] / 2, top - slab_h)), BLUE, 0.4, fill=colors.HexColor("#bfdbfe"))
        f.text(*P(s, top - v["h"] - 0.25), f"{v['id']} {int(v['b'] * 100)}×{int(v['h'] * 100)}", 4.8, BLUE)
    # níveis
    xl = P(s_min - 1.6, 0)[0]
    for z, lab in ((fl, f"{fl:+.2f} pavimento"), (fl + env.hsp, f"{fl + env.hsp:+.2f} teto"), (top, f"{top:+.2f} laje"),
                   (top + par, f"{top + par:+.2f} platibanda"), (fl - 0.80, f"{fl - 0.80:+.2f} fundação")):
        f.line([(xl - 0.6, oz + z), (P(s_max + 0.6, 0)[0], oz + z)], GREY, 0.2, dash=[1, 2])
        f.text(xl - 0.7, oz + z + 0.06, lab.replace(".", ","), 5.4, INK, align="r")
    f.dim(P(s_min, 0), P(s_max, 0), -1.2)
    f.dim((P(s_max, 0)[0] + 1.0, oz + fl), (P(s_max, 0)[0] + 1.0, oz + top), 0.0, _n(top - fl))
    f.text(ox + (s_max - s_min) / 2, oz + top + par + 0.8, title, 8.5, INK, True)


def sheet_sections(c, b: Building, R, esp: dict, meta: dict, slab_h: float):
    fp = b.footprint
    x0, y0, x1, y1 = fp.bounds
    cy, cx = fp.centroid.y, fp.centroid.x
    sa = _section(b, R, "x", cy, slab_h)
    sb = _section(b, R, "y", cx, slab_h)
    H = b.roof_level + 1.5
    wa, wb = x1 - x0, y1 - y0
    bounds = (-3, -2.0, max(wa, wb) + 3, 2 * (H + 3.5))
    f = Frame(c, "Cortes AA' e BB'", "A02", meta, bounds)
    env, sol = esp["env"], esp["solution"]
    if sa[0]:
        _draw_section(f, b, R, *sa, slab_h, env, sol, 0.0, H + 3.0, f"CORTE AA' (y = {_n(cy)})")
    if sb[0]:
        _draw_section(f, b, R, *sb, slab_h, env, sol, 0.0, 0.0, f"CORTE BB' (x = {_n(cx)})")
    f.heading("Constituição")
    U = sol.U
    f.table(["Elemento", "Solução", "U W/m²K"],
            [["Parede exterior", f"tijolo 20 + ETICS EPS {sol.etics} mm", _n(U["parede"])],
             ["Cobertura", f"laje {_n(slab_h)} + XPS {sol.roof} mm invertida", _n(U["cobertura"])],
             ["Pavimento térreo", f"laje 0,15 + XPS {sol.floor} mm + betonilha", _n(U["pavimento"])],
             ["Caixilharia", f"alumínio RPT, Uw {sol.uw:g}, g {sol.g:g}".replace(".", ","), _n(sol.uw)]], [28, 56, 18])
    f.legend([(colors.HexColor("#9ca3af"), "Betão armado C30/37 (laje, platibanda)", "box"),
              (colors.HexColor("#c7ccd3"), "Laje térrea / vigas de fundação", "box"),
              (colors.HexColor("#fde68a"), "Isolamento térmico (ETICS, XPS)", "box"),
              (colors.HexColor("#bfdbfe"), "Vigas (b × h cm)", "box"), (BROWN, "Terreno", "line")])
    c.showPage()


# ----------------------------------------------------------------------------- A03 alçados
KIND_COL = {"wall": (0.95, 0.94, 0.91), "glass": (0.36, 0.50, 0.65), "lintel": (0.95, 0.94, 0.91), "slab_edge": (0.61, 0.64, 0.69),
            "parapet": (0.61, 0.64, 0.69), "frame": (0.22, 0.25, 0.32), "sill": (0.82, 0.84, 0.86), "plinth": (0.42, 0.45, 0.50)}


def _elevation_polys(b: Building, slab_h: float, view: str):
    """Faces 3D do modelo real projetadas ortogonalmente: view ∈ S, N, E, O (fachada vista de fora)."""
    from . import views as V
    fs = V.faces(b, slab_h=slab_h, details=True)
    out = []
    see = {"S": (0, -1), "N": (0, 1), "E": (1, 0), "O": (-1, 0)}[view]
    for item in fs:
        pts, kind, nrm = item[0], item[1], item[2]
        col = KIND_COL.get(kind, (0.85, 0.85, 0.85))
        if nrm[0] * see[0] + nrm[1] * see[1] <= 0.05:
            continue                                     # face virada para o outro lado (ou horizontal)
        if view == "S":
            pr = [(x, z) for x, y, z in pts]
            depth = sum(y for _, y, _ in pts) / len(pts)
        elif view == "N":
            pr = [(-x, z) for x, y, z in pts]
            depth = -sum(y for _, y, _ in pts) / len(pts)
        elif view == "E":
            pr = [(y, z) for x, y, z in pts]
            depth = -sum(x for x, _, _ in pts) / len(pts)
        else:
            pr = [(-y, z) for x, y, z in pts]
            depth = sum(x for x, _, _ in pts) / len(pts)
        xs = [p[0] for p in pr]
        zs = [p[1] for p in pr]
        if max(xs) - min(xs) < 1e-3 or max(zs) - min(zs) < 1e-3:
            continue                                     # face de perfil
        out.append((depth, pr, kind, col))
    out.sort(key=lambda t: -t[0])                       # pintor: do mais longe para o mais perto
    return out


def sheet_elevations(c, b: Building, esp: dict, meta: dict, slab_h: float):
    x0, y0, x1, y1 = b.roof_slab.bounds
    w = max(x1 - x0, y1 - y0)
    H = b.roof_level + 1.2
    for num, pair in (("A03", ("S", "N")), ("A04", ("E", "O"))):
        f = Frame(c, "Alçados " + " e ".join({"S": "Sul", "N": "Norte", "E": "Nascente", "O": "Poente"}[v] for v in pair), num, meta,
                  (-1, -1.5, w + 1, 2 * H + 3.5))
        for i, v in enumerate(pair):
            oz = (H + 3.0) if i == 0 else 0.0
            polys = _elevation_polys(b, slab_h, v)
            if not polys:
                continue
            mnx = min(p[0] for _, pr, _, _ in polys for p in pr)
            for _, pr, kind, col in polys:
                from shapely.geometry import Polygon
                g = Polygon([(p[0] - mnx, p[1] + oz) for p in pr])
                if not g.is_valid:
                    g = g.buffer(0)
                fill = colors.Color(*col[:3]) if isinstance(col, (tuple, list)) else LIGHT
                f.poly(g, INK, 0.25, fill=fill)
            mxx = max(p[0] for _, pr, _, _ in polys for p in pr) - mnx
            f.line([(-0.8, oz + b.floor_level - 0.2), (mxx + 0.8, oz + b.floor_level - 0.2)], BROWN, 0.8)
            for z, lab in ((b.floor_level, "±0,00"), (b.roof_level, f"{b.roof_level:+.2f}".replace(".", ",")),
                           (b.roof_level + 0.5, f"{b.roof_level + 0.5:+.2f}".replace(".", ","))):
                f.text(mxx + 1.0, oz + z, lab, 5.6, INK, align="l")
                f.line([(mxx + 0.2, oz + z), (mxx + 0.9, oz + z)], INK, 0.3)
            f.dim((0, oz - 0.6), (mxx, oz - 0.6), -0.0)
            f.text(mxx / 2, oz + H + 0.4, "ALÇADO " + {"S": "SUL", "N": "NORTE", "E": "NASCENTE", "O": "POENTE"}[v], 8.5, INK, True)
        f.legend([(colors.HexColor("#f2efe8"), "Reboco / ETICS acabamento areado", "box"),
                  (colors.HexColor("#5b7fa6"), "Vão envidraçado (caixilharia alumínio RPT)", "box"),
                  (colors.HexColor("#9ca3af"), "Platibanda e laje", "box")])
        f.para(["Projeção ortogonal do modelo 3D construído com a geometria real lida nas plantas.",
                "Orientações segundo o Norte do desenho (a confirmar pela planta de implantação)."])
        c.showPage()


# ----------------------------------------------------------------------------- E03 quadros de armaduras
def sheet_rebar(c, b: Building, R, meta: dict):
    f = Frame(c, "Quadros de armaduras e betões", "E03", meta, (0, 0, 1, 1), scale=100,
              area=(15 * mm, 15 * mm, landscape(A3)[0] - 130 * mm, landscape(A3)[1] - 15 * mm))
    c.setFont("Helvetica-Bold", 9)
    W, H = landscape(A3)

    def tbl(x, y, title, header, rows, widths):
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(INK)
        c.drawString(x, y, _t(title))
        y -= 3 * mm
        lh = 9.0
        for i, row in enumerate([header] + rows):
            xx = x
            if i == 0:
                c.setFillColor(colors.HexColor("#e8efe9"))
                c.rect(x, y - lh, sum(widths) * mm, lh, stroke=0, fill=1)
            c.setFillColor(INK)
            c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 6.4)
            for v, w in zip(row, widths):
                c.drawString(xx + 1, y - lh + 2.5, _t(v)[:int(w / 1.25)])
                xx += w * mm
            y -= lh
            if y < 20 * mm:
                break
        return y - 6 * mm
    x, y = 15 * mm, H - 20 * mm
    y = tbl(x, y, f"Lajes (betão C30/37, aço A500 NR, recobrimento 25 mm) — e = {_n(R.slab['h'])} m", ["Painel", "Área m²", "Inferior", "Superior"],
            [[p["id"], _n(p["area"], 1), p["inf"]["label"], (p["sup"] or {}).get("label", "—")] for p in R.panels][:26], [16, 18, 40, 40])
    y = tbl(x, y, "Vigas", ["Viga", "b×h cm", "L m", "Inferior", "Superior", "Estribos"],
            [[v["id"], f"{int(v['b'] * 100)}×{int(v['h'] * 100)}", _n(v["L"]), v["inf"]["label"], v["sup"]["label"], str(v.get("estribos") or f"Ø8//{_n(v['s_st'])}")[:22]]
             for v in R.beams][:28], [14, 16, 12, 30, 30, 22])
    x2, y2 = 165 * mm, H - 20 * mm
    y2 = tbl(x2, y2, "Pilares", ["Pilar", "a×b cm", "H m", "N Ed kN", "Armadura", "Cintas"],
             [[p["id"], f"{int(p['a'] * 100)}×{int(p['b'] * 100)}", _n(p["H"]), f"{p.get('N_Ed', 0):.0f}", p["armadura"]["label"], str(p.get("estribos") or "Ø6//0,15")[:18]]
              for p in R.columns][:30], [14, 16, 12, 16, 30, 18])
    y2 = tbl(x2, y2, "Sapatas (σadm em hipótese — confirmar com estudo geotécnico)", ["Sapata", "B×B×h m", "Armadura (2 sentidos)"],
             [[s["id"], f"{_n(s['B'])}×{_n(s['B'])}×{_n(s['h'])}", str(s.get("armadura") or f"{_n(s['as_m'], 1)} cm²/m")] for s in R.footings][:24], [16, 30, 50])
    if R.retaining:
        tbl(x2, y2, "Muros de suporte", ["Muro", "e m", "Terras m", "Sapata m"],
            [[m["id"], _n(m["t"]), _n(m["H_terras"]), f"{_n(m['sapata_B'])}×{_n(m['sapata_h'])}"] for m in R.retaining], [16, 14, 16, 26])
    f.heading("Notas gerais")
    f.para(["Betão C30/37 XC2 (fundações) / XC1 (interiores); aço A500 NR.", "Recobrimentos: fundações 40 mm, vigas/pilares 30 mm, lajes 25 mm.",
            "Amarrações e emendas: 50 Ø (EC2 §8.4, boa aderência).", "Cargas: peso próprio + revestimentos 2,0 kN/m² + sobrecarga 1,0 kN/m² (cob.).",
            "Combinação ELU 1,35 G + 1,5 Q (EN 1990). Sismo: a verificar (EC8)."])
    c.showPage()


# ----------------------------------------------------------------------------- especialidades: base comum
def _mep_base(c, b, lay, meta, title, num):
    f = Frame(c, title, num, meta, _bounds(b, 3.0))
    _base(f, b, ghost=True)
    for r in lay.rooms:
        if r.placed:
            f.text(r.x, r.y + 0.55, r.name, 5.2, GREY)
    return f


def _quadro(lay, b):
    from .especialidades import _quadro_pos
    return _quadro_pos(lay, b)


def _inside_points(r, n, inset=0.45):
    """n pontos ao longo do limite interior da zona da divisão (para tomadas)."""
    if r.zone is None or n <= 0:
        return []
    ring = r.zone.buffer(-inset)
    if ring.is_empty:
        ring = r.zone
    ring = max(getattr(ring, "geoms", [ring]), key=lambda g: g.area)
    L = ring.exterior.length
    return [ring.exterior.interpolate(L * (i + 0.5) / n).coords[0] for i in range(n)]


def sheet_electrical(c, b, lay, esp, meta):
    el = (esp.get("mep") or {}).get("eletricidade") or {}
    f = _mep_base(c, b, lay, meta, "Eletricidade — tomadas, iluminação e quadro (RTIEBT)", "EL01")
    qx, qy, qn = _quadro(lay, b)
    f.poly(box(qx - 0.35, qy - 0.2, qx + 0.35, qy + 0.2), RED, 0.5, fill=RED)
    f.text(qx, qy - 0.55, "QE", 6.5, RED, True)
    pts = {p["divisao"]: p for p in el.get("pontos") or []}
    for r in lay.rooms:
        if not r.placed:
            continue
        p = pts.get(r.name)
        if not p:
            continue
        for i in range(int(p.get("pontos_luz") or 0)):
            dx = (i - (p["pontos_luz"] - 1) / 2) * 1.2
            f.circle(r.x + dx, r.y, 1.4, ORANGE, None, 0.6)
            f.text(r.x + dx, r.y - 0.06, "×", 7, ORANGE, True)
        for (x, y) in _inside_points(r, int(p.get("tomadas") or 0)):
            f.circle(x, y, 0.9, BLUE, BLUE)
        f.line([(qx, qy), (qx, r.y), (r.x, r.y)], GREY, 0.25, dash=[1, 1.5])
    f.heading("Circuitos")
    f.table(["Circuito", "Disj.", "S mm²", "L m", "ΔU %", "Dif."],
            [[cc["nome"], f"{cc['disjuntor']} A", _n(cc["seccao"], 1), _n(cc["comprimento_m"], 1), _n(cc["du"], 2), cc["diferencial"]]
             for cc in el.get("circuitos") or []], [38, 13, 13, 13, 13, 11], size=6.0, max_rows=26)
    f.para([f"Alimentação {el.get('alimentacao', '-')} · potência a contratar {_n(el.get('potencia_contratada_kva', 0), 1)} kVA",
            f"{el.get('tomadas', 0)} tomadas 16 A · {el.get('pontos_luz', 0)} pontos de luz · {el.get('diferenciais', 0)} diferenciais 30 mA"])
    f.legend([(BLUE, "Tomada 16 A com terra (h = 0,30 m; 1,10 m em bancadas)", "dot"), (ORANGE, "Ponto de luz no teto", "dot"),
              (RED, f"Quadro elétrico ({qn})", "box"), (GREY, "Encaminhamento indicativo", "dash")])
    c.showPage()

    # EL02 unifilar
    f = Frame(c, "Esquema unifilar do quadro elétrico", "EL02", meta, (0, 0, 40, 26))
    W = 40
    f.line([(2, 23), (W - 2, 23)], INK, 1.4)
    f.text(1.5, 23.6, f"Entrada {el.get('alimentacao', '')} — disjuntor geral {int(round(el.get('corrente_contrato_a') or 40))} A",
           7, INK, True, align="l")
    difs = el.get("diferenciais_lista") or []
    circ = {cc["nome"]: cc for cc in el.get("circuitos") or []}
    n_tot = sum(len(d["circuitos"]) for d in difs) or 1
    step = (W - 4) / n_tot
    x = 2 + step / 2
    for d in difs:
        xs = x
        xe = x + step * (len(d["circuitos"]) - 1)
        xm = (xs + xe) / 2
        f.line([(xm, 23), (xm, 20.5)], INK, 0.8)
        f.poly(box(xm - 0.7, 19.3, xm + 0.7, 20.5), INK, 0.6, fill=colors.HexColor("#fef3c7"))
        f.text(xm, 19.7, f"ID {d['calibre']}A {d['sensibilidade_ma']}mA tipo {d['tipo']}", 5.2, INK, True)
        f.line([(xs, 19.3), (xe, 19.3)] if xe > xs else [(xs, 19.3), (xs + 0.01, 19.3)], INK, 0.8)
        for name in d["circuitos"]:
            cc = circ.get(name, {})
            f.line([(x, 19.3), (x, 12)], INK, 0.6)
            f.poly(box(x - 0.35, 15.5, x + 0.35, 16.6), INK, 0.5, fill=colors.white)
            f.text(x + 0.05, 13.4, f"{cc.get('disjuntor', '')}A  {_n(cc.get('seccao', 0), 1)}mm²", 5.0, INK, angle=90)
            f.text(x + 0.05, 6.0, name[:34], 5.4, INK, angle=90)
            x += step
    f.para(["Disjuntores curva C, poder de corte 6 kA.", "Cabos H07V-U / XV em tubo VD (RTIEBT secção 52).",
            "Quedas de tensão verificadas circuito a circuito (nota das especialidades)."])
    c.showPage()


def sheet_plumbing(c, b, lay, esp, meta):
    can = (esp.get("mep") or {}).get("canalizacao") or {}
    f = _mep_base(c, b, lay, meta, "Águas (AF/AQ) e esgotos — DR 23/95", "AG01")
    fp = b.footprint
    qx, qy, _ = _quadro(lay, b)
    entry = fp.exterior.interpolate(fp.exterior.project(Point(qx, qy)))
    ex, ey = entry.x, entry.y
    f.poly(box(ex - 0.3, ey - 0.3, ex + 0.3, ey + 0.3), BLUE, 0.5, fill=colors.HexColor("#dbeafe"))
    f.text(ex, ey - 0.75, "contador", 5.5, BLUE, True)
    aqs = next((r for r in lay.rooms if r.type in ("tecnico", "lavandaria") and r.placed), None)
    if aqs:
        f.circle(aqs.x + 0.8, aqs.y - 0.6, 2.2, RED, colors.HexColor("#fee2e2"), 0.6)
        f.text(aqs.x + 0.8, aqs.y - 0.68, "AQS", 5.5, RED, True)
    cv = []
    for r in lay.rooms:
        if r.type not in ("casa_de_banho", "cozinha", "lavandaria") or not r.placed:
            continue
        f.line([(ex, ey), (ex, r.y - 0.15), (r.x, r.y - 0.15)], BLUE, 0.7)
        if aqs:
            f.line([(aqs.x + 0.8, aqs.y - 0.6), (aqs.x + 0.8, r.y + 0.15), (r.x, r.y + 0.15)], RED, 0.7)
        ring = fp.buffer(1.0, join_style=2).exterior
        near = fp.exterior.interpolate(fp.exterior.project(Point(r.x, r.y)))
        out = ring.interpolate(ring.project(near))
        f.line([(r.x, r.y), (near.x, near.y), (out.x, out.y)], BROWN, 0.9, dash=[4, 2])
        f.poly(box(out.x - 0.3, out.y - 0.3, out.x + 0.3, out.y + 0.3), BROWN, 0.5, fill=colors.HexColor("#f5e6d3"))
        cv.append(ring.project(out))
        f.circle(r.x, r.y, 1.6, BROWN, colors.white, 0.6)
        f.text(r.x, r.y - 0.07, "TQ" if r.type == "casa_de_banho" else "R", 4.6, BROWN, True)
    if len(cv) > 1:                                   # coletor predial exterior, pelo perímetro, entre as caixas
        from shapely.ops import substring
        ring = LineString(fp.buffer(1.0, join_style=2).exterior.coords)
        cv.sort()
        gaps = [(cv[(i + 1) % len(cv)] - cv[i]) % ring.length for i in range(len(cv))]
        k = max(range(len(cv)), key=lambda i: gaps[i])       # o maior intervalo fica sem coletor
        start, end = cv[(k + 1) % len(cv)], cv[k]
        seg = substring(ring, start, end) if end > start else unary_union([substring(ring, start, ring.length), substring(ring, 0, end)])
        for g in getattr(seg, "geoms", [seg]):
            if g.geom_type == "LineString" and g.length > 0.1:
                f.line(g, BROWN, 1.2, dash=[6, 2])
    f.heading("Dispositivos e caudais")
    f.table(["Dispositivo", "n.º", "Qi l/s", "AQ", "Ramal desc."],
            [[d["dispositivo"].replace("_", " "), d["n"], _n(d["q"], 2), "sim" if d["aq"] else "-", f"Ø{d['ramal_descarga']}"] for d in can.get("dispositivos") or []],
            [36, 10, 14, 10, 20])
    f.para([f"Caudal acumulado {_n(can.get('qa_l_s', 0), 2)} l/s → de cálculo {_n(can.get('qc_l_s', 0), 2)} l/s",
            f"Tubo AF {can.get('tubo_af', '-')} · AQ {can.get('tubo_aq', '-')} · pressão {_n(can.get('pressao_kpa', 0), 0)} kPa",
            f"Drenagem: tubo de queda Ø{can.get('tubo_queda_mm', '-')}, coletor Ø{can.get('coletor_mm', '-')} a i ≥ 1 %"])
    f.legend([(BLUE, "Água fria (PEX/multicamada)", "line"), (RED, "Água quente sanitária", "line"),
              (BROWN, "Drenagem de águas residuais → caixas de visita", "dash"), (colors.HexColor("#f5e6d3"), "Caixa de visita", "box")])
    c.showPage()


def sheet_ventilation(c, b, lay, esp, meta):
    v = (esp.get("vent") or {}).get("ventilacao") or {}
    f = _mep_base(c, b, lay, meta, "Ventilação — admissão e extração (Portaria 138-I/2021, NP 1037-1)", "VT01")
    adm = dict(v.get("grelhas") or [])
    for r in lay.rooms:
        if not r.placed:
            continue
        if r.name in adm or r.type in ("sala", "quarto", "escritorio"):
            q = adm.get(r.name, 25)
            f.line([(r.x - 1.2, r.y), (r.x - 0.2, r.y)], GREEN, 1.0)
            f.line([(r.x - 0.45, r.y + 0.2), (r.x - 0.2, r.y), (r.x - 0.45, r.y - 0.2)], GREEN, 1.0)
            f.text(r.x, r.y - 0.4, f"admissão {q} m³/h", 5.4, GREEN, True)
        elif r.type in ("casa_de_banho", "cozinha", "lavandaria"):
            q = {"cozinha": 4.0, "casa_de_banho": 4.0, "lavandaria": 4.0}[r.type] * r.area * esp["env"].hsp
            f.circle(r.x, r.y, 1.8, VIOLET, colors.HexColor("#ede9fe"), 0.7)
            f.text(r.x, r.y - 0.07, "E", 5.5, VIOLET, True)
            f.text(r.x, r.y - 0.5, f"extração {q:.0f} m³/h → cobertura", 5.2, VIOLET)
    f.heading("Caudais")
    f.para([f"Volume ventilado {_n(v.get('volume_m3', 0), 0)} m³ · caudal de projeto {_n(v.get('caudal_m3h', 0), 0)} m³/h",
            f"Rph = {_n(v.get('rph', 0), 2)} h⁻¹ (mínimo 0,50 h⁻¹ — Portaria 138-I/2021)"])
    f.table(["Divisão", "Admissão m³/h", "Grelhas 25 m³/h"], [[n, q, math.ceil(q / 25)] for n, q in v.get("grelhas") or []], [50, 24, 26])
    f.legend([(GREEN, "Grelha autorregulável no caixilho (admissão)", "line"), (VIOLET, "Boca de extração + conduta individual à cobertura", "dot")])
    f.para(["Passagem de ar sob as portas interiores ≥ 1 cm (folga) ou grelha de transferência.",
            "Cozinha: exaustor com conduta independente Ø125 até à cobertura."])
    c.showPage()


def sheet_heating(c, b, lay, esp, meta):
    mep = esp.get("mep") or {}
    pr, bc = mep.get("piso_radiante") or {}, mep.get("bomba_calor") or {}
    sol = esp["solution"]
    f = _mep_base(c, b, lay, meta, "Aquecimento — piso radiante por circuitos (NP EN 1264)" if sol.system == "bc"
                  else "Aquecimento — emissores", "AQ01")
    pal = [colors.HexColor(h) for h in ("#fecaca", "#fed7aa", "#fef08a", "#bbf7d0", "#bae6fd", "#ddd6fe", "#fbcfe8")]
    rows = {d["nome"]: d for d in pr.get("divisoes") or []}
    qx, qy, _ = _quadro(lay, b)
    col_pos = []
    for i, r in enumerate([r for r in lay.rooms if r.placed and r.zone is not None and r.heated]):
        d = rows.get(r.name)
        if not d:
            continue
        z = r.zone.buffer(-0.25)
        if z.is_empty:
            continue
        f.poly(z, ORANGE, 0.3, fill=pal[i % len(pal)])
        f.text(r.x, r.y - 0.1, f"{d['circuitos']} circ. · passo {d['passo']} cm", 5.4, ORANGE, True)
        f.text(r.x, r.y - 0.45, f"{d['phi_w']:.0f} W · θF {d['tf']:.1f} °C".replace(".", ","), 5.0, INK)
    n_col = int(pr.get("coletores") or 1)
    corr = [r for r in lay.rooms if r.type == "corredor" and r.placed] or [r for r in lay.rooms if r.placed]
    for k in range(min(n_col, len(corr))):
        r = corr[k]
        f.poly(box(r.x - 0.5, r.y + 0.8, r.x + 0.5, r.y + 1.1), RED, 0.5, fill=RED)
        f.text(r.x, r.y + 1.3, f"coletor C{k + 1}", 5.6, RED, True)
        col_pos.append((r.x, r.y + 0.95))
    if bc:
        out = b.footprint.exterior.interpolate(b.footprint.exterior.project(Point(qx, qy)) + 3.0)
        f.poly(box(out.x - 0.6, out.y - 0.35, out.x + 0.6, out.y + 0.35), BLUE, 0.6, fill=colors.HexColor("#dbeafe"))
        f.text(out.x, out.y - 0.8, f"BC {bc.get('p_nominal_kw', 0):g} kW (exterior)", 5.8, BLUE, True)
        for cp in col_pos:
            f.line([(out.x, out.y), (out.x, cp[1]), cp], RED, 0.8)
    f.legend([(ORANGE, "Zona de cada divisão (posição lida; contorno aproximado) — tubos PE-RT 16×2", "box"),
              (RED, "Coletor (caixa de embutir com atuadores)", "box"), (BLUE, "Unidade exterior da bomba de calor", "box")])
    f.heading("Piso radiante")
    f.table(["Divisão", "Φ W", "Passo", "Circ.", "θF °C"],
            [[d["nome"], f"{d['phi_w']:.0f}", d["passo"], d["circuitos"], _n(d["tf"], 1)] for d in pr.get("divisoes") or []], [44, 14, 12, 12, 14],
            size=6.0, max_rows=24)
    f.para([f"Perdas de projeto {_n((mep.get('aquecimento') or {}).get('phi_total', 0) / 1000, 1)} kW a θe "
            f"{_n((mep.get('aquecimento') or {}).get('theta_e', 0), 1)} °C (EN 12831-1)",
            f"Ida {_n(pr.get('theta_ida', 0), 1)} °C · {pr.get('circuitos', 0)} circuitos · {_n(pr.get('tubo_total_m', 0), 0)} m de tubo PE-RT 16×2"])
    c.showPage()

    # AQ02 esquema hidráulico
    f = Frame(c, "Esquema hidráulico de princípio — produção e emissão", "AQ02", meta, (0, 0, 40, 24))
    f.poly(box(1, 9, 7, 15), BLUE, 0.8, fill=colors.HexColor("#dbeafe"))
    f.text(4, 12.4, "BOMBA DE CALOR", 7, BLUE, True)
    f.text(4, 11.4, f"ar-água {bc.get('p_nominal_kw', 0):g} kW", 6.5, BLUE)
    f.text(4, 10.5, f"SCOP {_n(bc.get('scop', 0), 2)} · {bc.get('classe_erp', '')}", 6, BLUE)
    f.text(4, 16, "EXTERIOR", 7, GREY, True)
    f.line([(9, 2), (9, 22)], GREY, 0.6, dash=[4, 3])
    f.text(10, 21.5, "INTERIOR", 7, GREY, True, align="l")
    f.line([(7, 14), (14, 14)], RED, 1.6)
    f.line([(7, 10), (14, 10)], BLUE, 1.6)
    f.circle(11, 14, 3.0, INK, colors.white, 0.6)
    f.text(11, 13.85, "B", 6, INK, True)
    f.poly(box(11.5, 16, 13, 18), INK, 0.6, fill=colors.HexColor("#fef3c7"))
    f.text(12.25, 18.5, f"vaso {bc.get('volume_instalacao_l', 0):.0f} L inst.", 5.5, INK)
    f.line([(12.25, 14), (12.25, 16)], INK, 0.6)
    n_col = int(pr.get("coletores") or 1)
    for k in range(n_col):
        y = 18 - k * 8
        f.poly(box(16, y - 3, 17.2, y + 1), RED, 0.6, fill=colors.HexColor("#fee2e2"))
        f.text(16.6, y + 1.5, f"Coletor C{k + 1}", 6, RED, True)
        f.line([(14, 14), (15, 14), (15, y), (16, y)], RED, 1.0)
        f.line([(14, 10), (15.5, 10), (15.5, y - 2), (16, y - 2)], BLUE, 1.0)
        n_c = max(1, int(pr.get("circuitos") or 1) // n_col)
        for j in range(min(n_c, 12)):
            yy = y + 0.6 - j * 0.32
            f.line([(17.2, yy), (24, yy)], ORANGE, 0.5)
        f.text(25, y - 1, f"{n_c} circuitos piso radiante", 6, ORANGE, align="l")
    f.poly(box(30, 4, 34, 11), RED, 0.8, fill=colors.HexColor("#fee2e2"))
    f.text(32, 8, "AQS", 8, RED, True)
    f.text(32, 7, "BC 200 L", 6, RED)
    f.line([(32, 11), (32, 13), (36, 13)], RED, 0.9)
    f.text(36.2, 13, "AQ → dispositivos", 5.6, RED, align="l")
    f.line([(32, 4), (32, 2.5), (36, 2.5)], BLUE, 0.9)
    f.text(36.2, 2.5, "AF ← rede", 5.6, BLUE, align="l")
    f.legend([(RED, "Ida / água quente", "line"), (BLUE, "Retorno / água fria", "line"), (ORANGE, "Circuitos de piso radiante", "line")])
    f.para([f"Caudal {_n(bc.get('caudal_lh', 0), 0)} l/h, Δt {_n(bc.get('delta_t_k', 5), 0)} K · ida {_n(bc.get('temperatura_ida', 0), 1)} °C",
            f"Apoio {_n(bc.get('apoio_kw', 0), 1)} kW ({str(bc.get('tipo_apoio', '')).replace('_', ' ')})",
            "Purgadores nos pontos altos, válvulas de seccionamento e filtro na entrada da BC."])
    c.showPage()


# ----------------------------------------------------------------------------- tudo
def write_drawings(b: Building, R, lay: Layout, esp: dict, path: Path, meta: dict, slab_h: float) -> tuple[Path, list[str]]:
    c = canvas.Canvas(str(path), pagesize=landscape(A3))
    c.setTitle(_t(f"Desenhos de execução - {meta.get('obra', '')}"))
    done, errs = [], []
    steps = [("A01 Planta de arquitetura cotada", lambda: sheet_architecture(c, b, lay, esp, meta)),
             ("A02 Cortes", lambda: sheet_sections(c, b, R, esp, meta, slab_h)),
             ("A03/A04 Alçados", lambda: sheet_elevations(c, b, esp, meta, slab_h)),
             ("E01/E02 Estrutura e fundações", lambda: outputs.draw_structure(c, b, R, meta)),
             ("E03 Quadros de armaduras", lambda: sheet_rebar(c, b, R, meta)),
             ("EL01/EL02 Eletricidade", lambda: sheet_electrical(c, b, lay, esp, meta)),
             ("AG01 Águas e esgotos", lambda: sheet_plumbing(c, b, lay, esp, meta)),
             ("VT01 Ventilação", lambda: sheet_ventilation(c, b, lay, esp, meta)),
             ("AQ01/AQ02 Aquecimento", lambda: sheet_heating(c, b, lay, esp, meta))]
    for name, fn in steps:
        try:
            fn()
            done.append(name)
        except Exception as exc:  # noqa: BLE001 — uma folha que falha não impede as outras
            import logging
            logging.getLogger(__name__).warning("bet_geo drawing %s failed", name, exc_info=True)
            errs.append(f"{name}: {type(exc).__name__}: {str(exc)[:120]}")
            c.showPage()
    c.save()
    return path, done if not errs else done + [f"(falhou) {e}" for e in errs]
