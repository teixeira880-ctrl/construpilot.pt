"""Noyau de dessin : une planche = une liste de primitives en coordonnées « modèle » (mètres).

Les mêmes primitives sont rendues en PDF A3 (reportlab, à l'échelle exacte) et en DXF
(ezdxf, en mètres, un calque par famille). C'est ce qui garantit que le PDF et le DXF
montrent exactement la même chose.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .i18n import tr as _tr

_LANG = ["fr"]


class _Trunc(str):
    """Texte tronqué APRÈS traduction (la troncature avant traduction casserait le gabarit)."""
    n: int = 0


def trunc(s: str, n: int) -> str:
    t = _Trunc(s)
    t.n = n
    return t


def T(s):
    """Traduction au rendu dans la langue courante du livrable."""
    n = getattr(s, "n", 0)
    out = _tr(str(s), _LANG[0])
    return out[:n] if n else out

from . import brand as B  # noqa: E402 — enregistre les polices (Inter / Barlow) sous DV, DVB, TT…

LAYERS = {
    "BA": (0.20, 0.20, 0.22), "BRIQUE": (0.75, 0.30, 0.25), "DOUBLAGE": (0.80, 0.80, 0.80), "CLOISON": (0.45, 0.45, 0.45),
    "BAIE": (0.10, 0.35, 0.80), "COTE": (0.10, 0.10, 0.10), "TEXTE": (0.05, 0.05, 0.05), "AXE": (0.30, 0.45, 0.80),
    "FOND": (0.15, 0.50, 0.30), "ACIER": (0.80, 0.10, 0.10), "PLANCHER": (0.20, 0.45, 0.75), "CHARPENTE": (0.55, 0.35, 0.15),
    "ELEC": (0.85, 0.45, 0.00), "PLOMB_EF": (0.10, 0.40, 0.90), "PLOMB_ECS": (0.85, 0.15, 0.15), "PLOMB_EV": (0.35, 0.25, 0.10),
    "TERRAIN": (0.60, 0.50, 0.35), "TITRE": (0.10, 0.30, 0.20), "ESCALIER": (0.35, 0.35, 0.35), "NIVEAU": (0.10, 0.10, 0.10),
}
DXF_COLOR = {"BA": 7, "BRIQUE": 1, "DOUBLAGE": 8, "CLOISON": 8, "BAIE": 5, "COTE": 7, "TEXTE": 7, "AXE": 4, "FOND": 3,
             "ACIER": 1, "PLANCHER": 5, "CHARPENTE": 30, "ELEC": 30, "PLOMB_EF": 5, "PLOMB_ECS": 1, "PLOMB_EV": 34,
             "TERRAIN": 42, "TITRE": 3, "ESCALIER": 8, "NIVEAU": 7}
BRAND = colors.Color(0.12, 0.42, 0.27)


@dataclass
class Sheet:
    code: str
    title: str
    scale: int                       # 50 pour 1:50
    origin: tuple[float, float] = (0.0, 0.0)  # point modèle placé en bas-gauche de la zone utile
    items: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    subtitle: str = ""
    area_mm: tuple[float, float, float, float] = (18, 52, 298, 280)   # zone dessin (x0, y0, x1, y1) en mm

    # ---- primitives (coordonnées modèle en m)
    def line(self, layer, p1, p2, lw=0.25, dash=None):
        self.items.append(("line", layer, p1, p2, lw, dash))

    def poly(self, layer, pts, lw=0.25, closed=False, fill=None, dash=None):
        self.items.append(("poly", layer, pts, lw, closed, fill, dash))

    def rect(self, layer, x0, y0, x1, y1, lw=0.25, fill=None, hatch=None, dash=None):
        self.items.append(("rect", layer, x0, y0, x1, y1, lw, fill, hatch, dash))

    def circle(self, layer, c, r, lw=0.25, fill=None):
        self.items.append(("circle", layer, c, r, lw, fill))

    def text(self, layer, p, s, size=2.5, anchor="l", rot=0.0, bold=False, color=None):
        self.items.append(("text", layer, p, s, size, anchor, rot, bold, color))

    def dim(self, p1, p2, offset, text=None, size=2.0):
        """Cote alignée entre p1 et p2, décalée de `offset` (m, perpendiculaire)."""
        self.items.append(("dim", "COTE", p1, p2, offset, text, size))

    def chain(self, pts, axis, at, offset_sign=1, size=1.8):
        """Chaîne de cotes le long d'un axe ('x' ou 'y'), positions `pts` (triées), ligne de cote à `at`."""
        q = []
        for v in sorted(pts):
            if not q or v - q[-1] >= 0.015:
                q.append(v)
        for a, b in zip(q, q[1:]):
            if axis == "x":
                self.dim((a, at), (b, at), 0, size=size)
            else:
                self.dim((at, a), (at, b), 0, size=size)

    def level_mark(self, p, value, label=""):
        self.items.append(("level", "NIVEAU", p, value, label))


# ---------------------------------------------------------------- rendu PDF
def _xf(sh: Sheet):
    x0, y0 = sh.area_mm[0] * mm, sh.area_mm[1] * mm
    k = 1000.0 / sh.scale * mm      # 1 m modèle → points papier
    ox, oy = sh.origin

    def f(p):
        return x0 + (p[0] - ox) * k, y0 + (p[1] - oy) * k
    return f, k


def _set_dash(c, dash):
    if dash == "axis":
        c.setDash([6, 2, 1, 2])
    elif dash == "dashed":
        c.setDash([3, 2])
    elif dash == "dotted":
        c.setDash([1, 2])
    else:
        c.setDash([])


def _hatch(c, x0, y0, x1, y1, step=1.6 * mm, ang=45):
    p = c.beginPath()
    p.rect(x0, y0, x1 - x0, y1 - y0)
    c.saveState()
    c.clipPath(p, stroke=0, fill=0)
    w, h = x1 - x0, y1 - y0
    n = int((w + h) / step) + 2
    for i in range(n):
        d = i * step
        if ang == 45:
            c.line(x0 + d - h, y0, x0 + d, y0 + h)
        else:
            c.line(x0 + d, y0, x0 + d - h, y0 + h)
    c.restoreState()


def _render_items(c, sh: Sheet):
    f, k = _xf(sh)
    for it in sh.items:
        kind, layer = it[0], it[1]
        col = B.get().accent if layer == "TITRE" else colors.Color(*LAYERS.get(layer, (0, 0, 0)))
        c.setStrokeColor(col)
        c.setFillColor(col)
        if kind == "line":
            _, _, p1, p2, lw, dash = it
            c.setLineWidth(lw)
            _set_dash(c, dash)
            a, b = f(p1), f(p2)
            c.line(a[0], a[1], b[0], b[1])
        elif kind == "poly":
            _, _, pts, lw, closed, fill, dash = it
            c.setLineWidth(lw)
            _set_dash(c, dash)
            path = c.beginPath()
            q = [f(p) for p in pts]
            path.moveTo(*q[0])
            for p in q[1:]:
                path.lineTo(*p)
            if closed:
                path.close()
            if fill:
                c.setFillColor(colors.Color(*fill))
            c.drawPath(path, stroke=1, fill=1 if fill else 0)
        elif kind == "rect":
            _, _, x0, y0, x1, y1, lw, fill, hatch, dash = it
            a, b = f((x0, y0)), f((x1, y1))
            c.setLineWidth(lw)
            _set_dash(c, dash)
            if fill:
                c.setFillColor(colors.Color(*fill))
            c.rect(a[0], a[1], b[0] - a[0], b[1] - a[1], stroke=1 if lw > 0 else 0, fill=1 if fill else 0)
            if hatch:
                c.setLineWidth(0.15)
                c.setStrokeColor(col)
                _set_dash(c, None)
                _hatch(c, a[0], a[1], b[0], b[1], ang=45 if hatch == "brique" else -45)
        elif kind == "circle":
            _, _, cc, r, lw, fill = it
            a = f(cc)
            c.setLineWidth(lw)
            _set_dash(c, None)
            if fill:
                c.setFillColor(colors.Color(*fill))
            c.circle(a[0], a[1], r * k, stroke=1, fill=1 if fill else 0)
        elif kind == "text":
            _, _, p, s, size, anchor, rot, bold, color = it
            a = f(p)
            c.setFillColor(colors.Color(*color) if color else col)
            c.saveState()
            c.translate(*a)
            c.rotate(rot)
            c.setFont("TT" if layer == "TITRE" else ("DVB" if bold else "DV"), size * 2.835 * (1.12 if layer == "TITRE" else 1.0))
            s = T(s)
            if anchor == "c":
                c.drawCentredString(0, 0, s)
            elif anchor == "r":
                c.drawRightString(0, 0, s)
            else:
                c.drawString(0, 0, s)
            c.restoreState()
        elif kind == "dim":
            _, _, p1, p2, off, text, size = it
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            L = math.hypot(dx, dy)
            if L < 1e-6:
                continue
            nx, ny = -dy / L, dx / L
            q1 = (p1[0] + nx * off, p1[1] + ny * off)
            q2 = (p2[0] + nx * off, p2[1] + ny * off)
            a, b = f(q1), f(q2)
            c.setLineWidth(0.18)
            _set_dash(c, None)
            c.setStrokeColor(colors.black)
            c.line(a[0], a[1], b[0], b[1])
            for q in (a, b):
                c.line(q[0] - 1.1, q[1] - 1.1, q[0] + 1.1, q[1] + 1.1)
            for p, q in ((p1, a), (p2, b)):
                pp = f(p)
                if off:
                    c.line(pp[0], pp[1], q[0], q[1])
            s = T(text) if text is not None else (f"{L*100:.0f}" if L < 1 else (f"{L:.2f}".replace(".", ",") if _LANG[0] == "pt" else f"{L:.2f}"))
            ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
            if ang > 90.1 or ang < -89.9:
                ang += 180
            c.saveState()
            c.translate((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            c.rotate(ang)
            c.setFillColor(colors.black)
            c.setFont("DV", size * 2.835)
            c.drawCentredString(0, 1.0, s)
            c.restoreState()
        elif kind == "level":
            _, _, p, value, label = it
            a = f(p)
            c.setLineWidth(0.3)
            _set_dash(c, None)
            c.setStrokeColor(colors.black)
            c.setFillColor(colors.black)
            path = c.beginPath()
            path.moveTo(a[0], a[1])
            path.lineTo(a[0] - 2.2, a[1] + 3.0)
            path.lineTo(a[0] + 2.2, a[1] + 3.0)
            path.close()
            c.drawPath(path, stroke=1, fill=1)
            c.line(a[0] - 6, a[1], a[0] + 14, a[1])
            c.setFont("DV", 5.6)
            v = f"{value:+.2f}".replace("+0.00", "±0.00")
            if _LANG[0] == "pt":
                v = v.replace(".", ",")
            c.drawString(a[0] + 3.5, a[1] + 1.2, v + (f"  {T(label)}" if label else ""))


def _frame(c, sh: Sheet, project: dict, idx: int, total: int):
    W, H = landscape(A3)
    br = B.get()
    ink = colors.Color(0.13, 0.15, 0.18)
    grey = colors.Color(0.45, 0.47, 0.50)
    c.setDash([])
    # cadre : double filet
    c.setStrokeColor(ink)
    c.setLineWidth(0.9)
    c.rect(10 * mm, 10 * mm, W - 20 * mm, H - 20 * mm)
    c.setLineWidth(0.25)
    c.rect(11.6 * mm, 11.6 * mm, W - 23.2 * mm, H - 23.2 * mm)
    # cartouche (même encombrement que l'ancien : 102 × 62 mm)
    x0, y0, w, h = W - 112 * mm, 10 * mm, 102 * mm, 62 * mm
    c.setFillColor(colors.white)
    c.setLineWidth(0.6)
    c.rect(x0, y0, w, h, stroke=1, fill=1)
    # bandeau identité : logo + nom + coordonnées
    band = 16 * mm
    c.setFillColor(br.tint2)
    c.rect(x0, y0 + h - band, w, band, stroke=0, fill=1)
    B.draw_logo(c, x0 + 3 * mm, y0 + h - band + 2.2 * mm, 34 * mm, band - 4.4 * mm, br)
    tx = x0 + 40 * mm
    c.setFillColor(ink)
    c.setFont("TTS", 8.6)
    c.drawString(tx, y0 + h - 4.8 * mm, (br.name or "ConstruPilot")[:34])
    c.setFont("DV", 5.2)
    c.setFillColor(grey)
    yy = y0 + h - 7.9 * mm
    for ln in (br.lines or [T("Bureau d'études intégré")])[:3]:
        c.drawString(tx, yy, ln[:64])
        yy -= 2.6 * mm
    c.setFillColor(br.accent)
    c.rect(x0, y0 + h - band - 1.1 * mm, w, 1.1 * mm, stroke=0, fill=1)
    c.setFillColor(br.accent2)
    c.rect(x0, y0 + h - band - 1.1 * mm, 24 * mm, 1.1 * mm, stroke=0, fill=1)
    # titre de planche
    from reportlab.pdfbase.pdfmetrics import stringWidth as _sw

    def fit(txt, font, size, maxw):
        while size > 3.6 and _sw(txt, font, size) > maxw:
            size -= 0.2
        return size
    tw = w - 6 * mm
    c.setFillColor(ink)
    yy = y0 + h - band - 5.6 * mm
    for ln in _wrap(T(sh.title), 56 if _LANG[0] == "fr" else 52)[:2]:
        c.setFont("TT", fit(ln, "TT", 9.6, tw))
        c.drawString(x0 + 3 * mm, yy, ln)
        yy -= 3.9 * mm
    c.setFillColor(grey)
    if sh.subtitle:
        st_ = T(sh.subtitle)
        c.setFont("DV", fit(st_, "DV", 5.6, tw))
        c.drawString(x0 + 3 * mm, yy, st_)
        yy -= 3.0 * mm
    if _LANG[0] == "pt":
        ref = f"Arq. {T(project['pc_ref'])[:38]} · Geot. {T(project['g2_ref'])[:30]}"
    else:
        ref = f"PC {project['pc_ref']} · G2 {project['g2_ref'][:34]}"
    for txt, font, size in ((T(project["name"]), "DVM", 5.8), (T(project["address"]), "DV", 5.4), (ref, "DV", 5.4)):
        if yy < y0 + 20.5 * mm:
            break
        c.setFillColor(ink if font == "DVM" else grey)
        c.setFont(font, fit(txt, font, size, tw))
        c.drawString(x0 + 3 * mm, yy, txt)
        yy -= 2.7 * mm
    # avertissement
    warn = T("PRÉ-DIMENSIONNEMENT — À VISER ET SIGNER PAR UN") + " " + T("INGÉNIEUR STRUCTURE AVANT EXÉCUTION")
    c.setFillColor(colors.Color(0.70, 0.12, 0.10))
    c.setFont("DVB", fit(warn, "DVB", 5.0, tw))
    c.drawString(x0 + 3 * mm, y0 + 17.4 * mm, warn)
    # pied : planche / échelle / indice
    c.setStrokeColor(colors.Color(0.80, 0.81, 0.83))
    c.setLineWidth(0.3)
    c.line(x0, y0 + 16 * mm, x0 + w, y0 + 16 * mm)
    c.line(x0 + 34 * mm, y0 + 2 * mm, x0 + 34 * mm, y0 + 14 * mm)
    c.line(x0 + 62 * mm, y0 + 2 * mm, x0 + 62 * mm, y0 + 14 * mm)
    c.setFillColor(grey)
    c.setFont("DV", 5.6)
    c.drawString(x0 + 3 * mm, y0 + 12.4 * mm, T("Planche").upper())
    c.drawString(x0 + 37 * mm, y0 + 12.4 * mm, T("Échelle").upper())
    c.drawString(x0 + 65 * mm, y0 + 12.4 * mm, T("Indice / date").upper())
    c.setFillColor(br.accent)
    c.setFont("TT", 17)
    c.drawString(x0 + 3 * mm, y0 + 3.6 * mm, sh.code)
    c.setFillColor(ink)
    c.setFont("TT", 13)
    c.drawString(x0 + 37 * mm, y0 + 4.2 * mm, f"1:{sh.scale}" if sh.scale and sh.scale < 1000 else "s.e.")
    c.setFont("DVM", 7.2)
    c.drawString(x0 + 65 * mm, y0 + 7.4 * mm, f"A · {project.get('date', '')}")
    c.setFont("DV", 5.6)
    c.setFillColor(grey)
    c.drawString(x0 + 65 * mm, y0 + 3.8 * mm, f"{idx} / {total}" + ("  ·  " + T("étude ConstruPilot") if br.is_client else ""))
    c.setFillColor(colors.black)
    # notes
    if sh.notes:
        nx, ny = W - 112 * mm, H - 17 * mm
        c.setFillColor(br.accent)
        c.setFont("TT", 10)
        c.drawString(nx, ny, T("NOTES"))
        c.setFillColor(br.accent2)
        c.rect(nx, ny - 2.0 * mm, 12 * mm, 0.7 * mm, stroke=0, fill=1)
        c.setFillColor(ink)
        c.setFont("DV", 6.3)
        ny -= 6.0 * mm
        for n in sh.notes:
            first = True
            for ln in _wrap(T(n), 80):
                if ny < 78 * mm:
                    break
                if first:
                    c.setFillColor(br.accent)
                    c.circle(nx + 0.8 * mm, ny + 0.75 * mm, 0.55 * mm, stroke=0, fill=1)
                    c.setFillColor(ink)
                c.drawString(nx + 2.6 * mm, ny, ln)
                first = False
                ny -= 2.9 * mm
            ny -= 1.0 * mm


def _wrap(s: str, n: int) -> list[str]:
    words, out, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > n:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


def render_pdf(sheets: list[Sheet], path: str | Path, project: dict, lang: str = "fr"):
    _LANG[0] = lang
    try:
        c = canvas.Canvas(str(path), pagesize=landscape(A3))
        c.setTitle(T(project["name"]))
        for i, sh in enumerate(sheets, 1):
            _render_items(c, sh)
            _frame(c, sh, project, i, len(sheets))
            c.showPage()
        c.save()
    finally:
        _LANG[0] = "fr"


# ---------------------------------------------------------------- rendu DXF
def render_dxf(sheets: list[Sheet], out_dir: str | Path, lang: str = "fr") -> list[Path]:
    _LANG[0] = lang
    try:
        return _render_dxf(sheets, out_dir)
    finally:
        _LANG[0] = "fr"


def _render_dxf(sheets: list[Sheet], out_dir: str | Path) -> list[Path]:
    import ezdxf
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for sh in sheets:
        if not getattr(sh, "dxf", True):
            continue
        doc = ezdxf.new("R2010", setup=True)
        doc.units = ezdxf.units.M
        for name, col in DXF_COLOR.items():
            if name not in doc.layers:
                doc.layers.add(name, color=col)
        msp = doc.modelspace()
        ts = sh.scale / 1000.0
        for it in sh.items:
            kind, layer = it[0], it[1]
            att = {"layer": layer}
            if kind == "line":
                msp.add_line(it[2], it[3], dxfattribs=att)
            elif kind == "poly":
                msp.add_lwpolyline(it[2], close=it[4], dxfattribs=att)
            elif kind == "rect":
                _, _, x0, y0, x1, y1, *_ = it
                msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs=att)
                if it[8]:
                    h = msp.add_hatch(color=DXF_COLOR.get(layer, 7), dxfattribs={"layer": layer})
                    h.set_pattern_fill("ANSI31", scale=0.02 * sh.scale / 50)
                    h.paths.add_polyline_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], is_closed=True)
            elif kind == "circle":
                msp.add_circle(it[2], it[3], dxfattribs=att)
            elif kind == "text":
                _, _, p, s, size, anchor, rot, *_ = it
                t = msp.add_text(T(s), dxfattribs={"layer": layer, "height": size * ts, "rotation": rot})
                t.set_placement(p, align={"l": ezdxf.enums.TextEntityAlignment.LEFT,
                                          "c": ezdxf.enums.TextEntityAlignment.CENTER,
                                          "r": ezdxf.enums.TextEntityAlignment.RIGHT}[anchor])
            elif kind == "dim":
                _, _, p1, p2, off, text, size = it
                dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                L = math.hypot(dx, dy)
                if L < 1e-6:
                    continue
                nx, ny = -dy / L, dx / L
                base = ((p1[0] + p2[0]) / 2 + nx * off, (p1[1] + p2[1]) / 2 + ny * off)
                ang = math.degrees(math.atan2(dy, dx))
                d = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=ang, dimstyle="EZDXF",
                                       override={"dimtxt": size * ts, "dimasz": size * ts * 0.6, "dimexe": 0.02, "dimexo": 0.0},
                                       dxfattribs={"layer": "COTE"})
                if text:
                    d.dimension.dxf.text = T(text)
                d.render()
            elif kind == "level":
                _, _, p, value, label = it
                msp.add_line((p[0] - 0.3, p[1]), (p[0] + 0.7, p[1]), dxfattribs={"layer": "NIVEAU"})
                t = msp.add_text(f"{value:+.2f} {T(label)}", dxfattribs={"layer": "NIVEAU", "height": 2.0 * ts})
                t.set_placement((p[0] + 0.15, p[1] + 0.05))
        f = out_dir / f"{sh.code}.dxf"
        doc.saveas(f)
        files.append(f)
    return files
