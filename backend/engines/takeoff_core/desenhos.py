"""Dimensioned drawings of the measured walls, for any construction system (annex of every dossier).

Two outputs from the same geometry the quantities were computed from:
- DXF in millimetres (ezdxf, MIT): plan of the walls with every wall dimensioned, and one elevation per piece with
  its openings and dimension chains;
- PDF pages in A3 landscape drawn with ReportLab (BSD): the same plan and elevations, at a standard scale written
  in the title block, so the client can see where every dimension and every quantity comes from.

These are take-off check drawings. They do not replace the execution drawings (out of scope).
"""
from __future__ import annotations

import io
import math
import os

from .i18n import tr as _tr

A3 = (420 * 72 / 25.4, 297 * 72 / 25.4)
MM = 72 / 25.4
SCALES = (20, 25, 50, 75, 100, 125, 150, 200, 250, 500)
SYSTEM_GREY = {"clt": (0.80, 0.66, 0.45), "alvenaria_tijolo": (0.85, 0.55, 0.45), "alvenaria_bloco": (0.70, 0.70, 0.70),
               "betao_armado": (0.55, 0.55, 0.58), "ossatura_madeira": (0.88, 0.78, 0.55),
               "ossatura_metalica": (0.65, 0.72, 0.80), "divisoria_gesso": (0.92, 0.92, 0.88)}


def font_paths():
    """DejaVu (Cyrillic for the Ukrainian dossier): the repository copy, else the one shipped with Matplotlib."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [os.path.join(here, "..", "..", "assets", "fonts")]
    try:
        import matplotlib
        candidates.append(os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf"))
    except ImportError:
        pass
    for d in candidates:
        r, b = os.path.join(d, "DejaVuSans.ttf"), os.path.join(d, "DejaVuSans-Bold.ttf")
        if os.path.exists(r) and os.path.exists(b):
            return r, b
    return None, None


def register_fonts():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    if "TKC" in pdfmetrics.getRegisteredFontNames():
        return "TKC", "TKC-B"
    r, b = font_paths()
    if not r:
        return "Helvetica", "Helvetica-Bold"
    pdfmetrics.registerFont(TTFont("TKC", r))
    pdfmetrics.registerFont(TTFont("TKC-B", b))
    return "TKC", "TKC-B"


# ---------------------------------------------------------------------------------------------------------------- DXF

LAYERS = {"EIXO": 1, "PAREDE": 5, "VAO": 3, "COTA": 8, "TEXTO": 7}


def dxf(networks, *, title="ConstruPilot", lang="pt"):
    """networks: [(floor name, walls, pieces)] → DXF bytes (mm). Plans one under the other, then the elevations."""
    import ezdxf
    from ezdxf.enums import TextEntityAlignment

    t = lambda s: _tr(s, lang)  # noqa: E731
    doc = ezdxf.new("R2018", setup=True, units=ezdxf.units.MM)
    for name, colour in LAYERS.items():
        doc.layers.add(name, color=colour)
    msp = doc.modelspace()
    style = {"dimtxt": 60, "dimasz": 40, "dimdec": 0, "dimlfac": 1, "dimexe": 30, "dimexo": 20}

    def text(s, x, y, h=80, rot=0, align=TextEntityAlignment.BOTTOM_LEFT):
        msp.add_text(s, height=h, rotation=rot, dxfattribs={"layer": "TEXTO", "style": "OpenSans"}).set_placement((x, y), align=align)

    y_cursor = 0.0
    for name, walls, pieces in networks:
        xs = [v for w in walls for v in (w.x1, w.x2)]
        ys = [v for w in walls for v in (w.y1, w.y2)]
        ox, oy = -min(xs) * 1000, y_cursor - max(ys) * 1000
        text(f"{title} · {name} · {t('planta das paredes, cotada (mm)')}", 0, y_cursor + 600, 150)
        for w in walls:
            a = (ox + w.x1 * 1000, oy + w.y1 * 1000)
            b = (ox + w.x2 * 1000, oy + w.y2 * 1000)
            msp.add_line(a, b, dxfattribs={"layer": "EIXO"})
            msp.add_lwpolyline([(ox + x * 1000, oy + y * 1000) for x, y in w.footprint().exterior.coords], close=True,
                               dxfattribs={"layer": "PAREDE"})
            if w.length >= 0.3:
                msp.add_aligned_dim(p1=a, p2=b, distance=w.thickness_mm / 2 + 250, dimstyle="EZDXF", override=style,
                                    dxfattribs={"layer": "COTA"}).render()
            ux, uy = w.direction()
            ang = math.degrees(math.atan2(uy, ux))
            ang = ang - 180 if ang > 90 else ang + 180 if ang <= -90 else ang
            text(f"{w.id} · {w.thickness_mm:g}", (a[0] + b[0]) / 2 + uy * (w.thickness_mm / 2 + 120),
                 (a[1] + b[1]) / 2 - ux * (w.thickness_mm / 2 + 120), 70, ang, TextEntityAlignment.MIDDLE_CENTER)
        y_cursor = oy + min(ys) * 1000 - 2500
        x0 = 0.0
        for p in pieces:
            L, H = p["comprimento_m"] * 1000, p["altura_m"] * 1000
            y0 = y_cursor - H
            msp.add_lwpolyline([(x0, y0), (x0 + L, y0), (x0 + L, y0 + H), (x0, y0 + H)], close=True, dxfattribs={"layer": "PAREDE"})
            for o in p["vaos"]:
                vx, vy = x0 + o["offset_m"] * 1000, y0 + o["sill_m"] * 1000
                vw, vh = o["width_m"] * 1000, o["height_m"] * 1000
                msp.add_lwpolyline([(vx, vy), (vx + vw, vy), (vx + vw, vy + vh), (vx, vy + vh)], close=True, dxfattribs={"layer": "VAO"})
                msp.add_linear_dim(base=(vx, y0 - 250), p1=(vx, vy), p2=(vx + vw, vy), dimstyle="EZDXF", override=style,
                                   dxfattribs={"layer": "COTA"}).render()
                msp.add_linear_dim(base=(vx + vw + 250, vy), p1=(vx + vw, vy), p2=(vx + vw, vy + vh), angle=90, dimstyle="EZDXF",
                                   override=style, dxfattribs={"layer": "COTA"}).render()
            msp.add_linear_dim(base=(x0, y0 - 600), p1=(x0, y0), p2=(x0 + L, y0), dimstyle="EZDXF", override=style,
                               dxfattribs={"layer": "COTA"}).render()
            msp.add_linear_dim(base=(x0 - 400, y0), p1=(x0, y0), p2=(x0, y0 + H), angle=90, dimstyle="EZDXF", override=style,
                               dxfattribs={"layer": "COTA"}).render()
            text(f"{p['id']} · {p['espessura_mm']:g} mm · {p['area_liquida_m2']:.2f} m²", x0, y0 + H + 120, 90)
            x0 += max(L, 2500) + 1500
        y_cursor -= 6000
    text(t("Desenho cotado gerado pela ConstruPilot a partir das medições. Não substitui o projeto de execução."), 0, y_cursor, 100)
    out = io.StringIO()
    doc.write(out)
    return out.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------------------------------------- PDF annex

def _scale_for(width_m, height_m, box_w, box_h):
    for s in SCALES:
        if width_m * 1000 / s * MM <= box_w and height_m * 1000 / s * MM <= box_h:
            return s
    return SCALES[-1]


def _dim(c, p1, p2, offset, label, size=6.5):
    """Aligned dimension: extension lines, a dimension line with ticks, the text above it."""
    (x1, y1), (x2, y2) = p1, p2
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 1:
        return
    ux, uy = (x2 - x1) / L, (y2 - y1) / L
    nx, ny = -uy, ux
    a = (x1 + nx * offset, y1 + ny * offset)
    b = (x2 + nx * offset, y2 + ny * offset)
    c.setLineWidth(0.25)
    c.setStrokeColorRGB(0.35, 0.35, 0.35)
    s = 1 if offset >= 0 else -1
    c.line(x1 + nx * s * 1.5, y1 + ny * s * 1.5, a[0] + nx * s * 2, a[1] + ny * s * 2)
    c.line(x2 + nx * s * 1.5, y2 + ny * s * 1.5, b[0] + nx * s * 2, b[1] + ny * s * 2)
    c.line(*a, *b)
    for px, py in (a, b):  # architectural ticks
        c.line(px - (ux + nx) * 1.8, py - (uy + ny) * 1.8, px + (ux + nx) * 1.8, py + (uy + ny) * 1.8)
    ang = math.degrees(math.atan2(uy, ux))
    flip = ang > 90 or ang <= -90
    if flip:
        ang -= 180 if ang > 0 else -180
    c.saveState()
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    c.translate(mx, my)
    c.rotate(ang)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(register_fonts()[0], size)
    c.drawCentredString(0, 1.2 if not flip or offset < 0 else 1.2, label)
    c.restoreState()


def _frame(c, fonts, title, subtitle, scale, page, pages, brand, lang):
    r, b = fonts
    W, H = A3
    t = lambda s: _tr(s, lang)  # noqa: E731
    c.setStrokeColorRGB(0.1, 0.1, 0.1)
    c.setLineWidth(0.8)
    c.rect(10 * MM, 10 * MM, W - 20 * MM, H - 20 * MM)
    # title block bottom right
    bw, bh = 150 * MM, 30 * MM
    x0, y0 = W - 10 * MM - bw, 10 * MM
    c.rect(x0, y0, bw, bh)
    colour = brand.get("cor") or (0.09, 0.29, 0.22)
    c.setFillColorRGB(*colour)
    c.rect(x0, y0 + bh - 7 * MM, bw, 7 * MM, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont(b, 9)
    c.drawString(x0 + 3 * MM, y0 + bh - 5 * MM, brand.get("nome") or "ConstruPilot")
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.setFont(b, 9)
    c.drawString(x0 + 3 * MM, y0 + bh - 12 * MM, title[:80])
    c.setFont(r, 7.5)
    c.drawString(x0 + 3 * MM, y0 + bh - 17 * MM, subtitle[:110])
    c.drawString(x0 + 3 * MM, y0 + bh - 22 * MM, f"{t('Escala')} 1:{scale}  ·  {t('cotas em mm')}  ·  A3  ·  {t('folha')} {page}/{pages}")
    c.setFont(r, 6)
    c.drawString(x0 + 3 * MM, y0 + 3 * MM, t("Desenho cotado gerado pela ConstruPilot a partir das medições. Não substitui o projeto de execução.")[:150])


def _plan_page(c, fonts, name, walls, pieces, brand, title, lang, page, pages, floor_meta):
    W, H = A3
    t = lambda s: _tr(s, lang)  # noqa: E731
    xs = [v for w in walls for v in (w.x1, w.x2)]
    ys = [v for w in walls for v in (w.y1, w.y2)]
    pad = 1.6
    span_x, span_y = max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad
    box_w, box_h = W - 40 * MM, H - 75 * MM
    scale = _scale_for(span_x, span_y, box_w, box_h)
    k = 1000 / scale * MM  # points per metre
    ox = 20 * MM + (box_w - span_x * k) / 2 - (min(xs) - pad) * k
    oy = 45 * MM + (box_h - span_y * k) / 2 - (min(ys) - pad) * k
    P = lambda x, y: (ox + x * k, oy + y * k)  # noqa: E731
    cx, cy = P((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    r, b = fonts
    for w in walls:
        col = SYSTEM_GREY.get(w.sistema or "", (0.8, 0.8, 0.8))
        c.setFillColorRGB(*col)
        c.setStrokeColorRGB(0.1, 0.1, 0.1)
        c.setLineWidth(0.5)
        coords = [P(x, y) for x, y in w.footprint().exterior.coords]
        path = c.beginPath()
        path.moveTo(*coords[0])
        for q in coords[1:]:
            path.lineTo(*q)
        path.close()
        c.drawPath(path, stroke=1, fill=1)
        ux, uy = w.direction()
        for o in w.openings:  # openings in white on the plan, with their width
            s0, s1 = o.offset_m, o.offset_m + o.width_m
            half = w.thickness_m / 2 + 0.01
            quad = [(w.x1 + ux * s - uy * h, w.y1 + uy * s + ux * h) for s, h in ((s0, -half), (s1, -half), (s1, half), (s0, half))]
            pq = [P(*q) for q in quad]
            c.setFillColorRGB(1, 1, 1)
            path = c.beginPath()
            path.moveTo(*pq[0])
            for q in pq[1:]:
                path.lineTo(*q)
            path.close()
            c.drawPath(path, stroke=1, fill=1)
        a, bb = P(w.x1, w.y1), P(w.x2, w.y2)
        mx, my = (a[0] + bb[0]) / 2, (a[1] + bb[1]) / 2
        nx, ny = -uy, ux
        side = 1 if (mx - cx) * nx + (my - cy) * ny >= 0 else -1
        off = side * (w.thickness_m / 2 * k + 7)
        if w.length * k > 14:
            _dim(c, a, bb, off, f"{w.length * 1000:.0f}", 6)
        # chain of openings on the inner side
        if w.openings:
            marks = [0.0] + [v for o in w.openings for v in (o.offset_m, o.offset_m + o.width_m)] + [w.length]
            for s0, s1 in zip(marks, marks[1:]):
                if s1 - s0 > 0.05 and (s1 - s0) * k > 10:
                    _dim(c, P(w.x1 + ux * s0, w.y1 + uy * s0), P(w.x1 + ux * s1, w.y1 + uy * s1),
                         -side * (w.thickness_m / 2 * k + 6), f"{(s1 - s0) * 1000:.0f}", 5)
        c.saveState()
        ang = math.degrees(math.atan2(uy, ux))
        ang = ang - 180 if ang > 90 else ang + 180 if ang <= -90 else ang
        lx, ly = mx - side * nx * (w.thickness_m / 2 * k + (14 if w.openings else 5)), my - side * ny * (w.thickness_m / 2 * k + (14 if w.openings else 5))
        c.translate(lx, ly)
        c.rotate(ang)
        c.setFillColorRGB(0.15, 0.15, 0.6)
        c.setFont(r, 5.5)
        c.drawCentredString(0, -2, f"{w.id} · {w.thickness_mm:g}")
        c.restoreState()
    x0p, y0p = P(min(xs), min(ys))
    x1p, y1p = P(max(xs), max(ys))
    _dim(c, (x0p, y0p), (x1p, y0p), -(pad * k * 0.75), f"{(max(xs) - min(xs)) * 1000:.0f}", 7.5)
    _dim(c, (x0p, y1p), (x0p, y0p), -(pad * k * 0.75), f"{(max(ys) - min(ys)) * 1000:.0f}", 7.5)
    c.setFont(b, 13)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawString(15 * MM, H - 20 * MM, f"{name} · {t('planta das paredes, cotada')}")
    c.setFont(r, 8)
    c.drawString(15 * MM, H - 26 * MM, floor_meta[:200])
    # legend of systems
    used = sorted({w.sistema for w in walls if w.sistema})
    lx = 15 * MM
    for sid in used:
        c.setFillColorRGB(*SYSTEM_GREY.get(sid, (0.8, 0.8, 0.8)))
        c.rect(lx, 15 * MM, 6 * MM, 3.5 * MM, stroke=1, fill=1)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(r, 7)
        label = t("sistema." + sid)
        c.drawString(lx + 8 * MM, 15.8 * MM, label)
        lx += 12 * MM + c.stringWidth(label, r, 7)
    _frame(c, fonts, title, f"{name} · {t('planta das paredes, cotada')}", scale, page, pages, brand, lang)


def _elevation_pages(pieces, per_page=6):
    return [pieces[i:i + per_page] for i in range(0, len(pieces), per_page)] or []


def _elevation_page(c, fonts, name, chunk, brand, title, lang, page, pages, part):
    W, H = A3
    t = lambda s: _tr(s, lang)  # noqa: E731
    r, b = fonts
    cols, rows = 3, 2
    cell_w, cell_h = (W - 30 * MM) / cols, (H - 80 * MM) / rows
    longest = max(p["comprimento_m"] for p in chunk)
    tallest = max(p["altura_m"] for p in chunk)
    scale = _scale_for(longest + 1.2, tallest + 1.2, cell_w - 10 * MM, cell_h - 18 * MM)
    k = 1000 / scale * MM
    for i, p in enumerate(chunk):
        col, row_ = i % cols, i // cols
        x0 = 15 * MM + col * cell_w + 14 * MM
        y0 = H - 40 * MM - (row_ + 1) * cell_h + 20 * MM
        L, Hh = p["comprimento_m"] * k, p["altura_m"] * k
        c.setStrokeColorRGB(0.1, 0.1, 0.1)
        c.setFillColorRGB(*SYSTEM_GREY.get(p.get("sistema") or "", (0.85, 0.85, 0.85)))
        c.setLineWidth(0.6)
        c.rect(x0, y0, L, Hh, stroke=1, fill=1)
        marks = [0.0]
        for o in sorted(p["vaos"], key=lambda o: o["offset_m"]):
            vx, vy, vw, vh = x0 + o["offset_m"] * k, y0 + o["sill_m"] * k, o["width_m"] * k, o["height_m"] * k
            c.setFillColorRGB(1, 1, 1)
            c.rect(vx, vy, vw, vh, stroke=1, fill=1)
            c.setLineWidth(0.25)
            c.line(vx, vy, vx + vw, vy + vh)
            c.line(vx + vw, vy, vx, vy + vh)
            c.setLineWidth(0.6)
            _dim(c, (vx + vw, vy), (vx + vw, vy + vh), -5, f"{o['height_m'] * 1000:.0f}", 5)
            if o["sill_m"] > 0:
                _dim(c, (vx, y0), (vx, vy), 5, f"{o['sill_m'] * 1000:.0f}", 5)
            marks += [o["offset_m"], o["offset_m"] + o["width_m"]]
        marks.append(p["comprimento_m"])
        for s0, s1 in zip(marks, marks[1:]):
            if s1 - s0 > 0.01:
                _dim(c, (x0 + s0 * k, y0), (x0 + s1 * k, y0), -6, f"{(s1 - s0) * 1000:.0f}", 5)
        _dim(c, (x0, y0), (x0 + L, y0), -14, f"{p['comprimento_m'] * 1000:.0f}", 6.5)
        _dim(c, (x0, y0 + Hh), (x0, y0), -6, f"{p['altura_m'] * 1000:.0f}", 6.5)
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont(b, 8)
        c.drawString(x0, y0 + Hh + 9, f"{t('Peça')} {p['id']}")
        c.setFont(r, 6.5)
        c.drawString(x0, y0 + Hh + 2.5, f"{p['espessura_mm']:g} mm · {t('líquida')} {p['area_liquida_m2']:.2f} m² · "
                                       f"{p['volume_liquido_m3']:.3f} m³ · {t('vãos')} {len(p['vaos'])}")
    c.setFont(b, 13)
    c.drawString(15 * MM, H - 20 * MM, f"{name} · {t('alçados das paredes, cotados')}{part}")
    _frame(c, fonts, title, f"{name} · {t('alçados das paredes, cotados')}{part}", scale, page, pages, brand, lang)


def annex_pdf(networks, floors_meta, *, title, brand, lang="pt"):
    """networks: [(floor, walls, pieces)]; floors_meta: {floor: text}. Returns (pdf bytes, sheet list)."""
    from reportlab.pdfgen import canvas

    fonts = register_fonts()
    plan = []
    for name, walls, pieces in networks:
        plan.append(("plan", name, walls, pieces, ""))
        chunks = _elevation_pages(pieces)
        for n, chunk in enumerate(chunks, 1):
            plan.append(("elev", name, walls, chunk, f" ({n}/{len(chunks)})" if len(chunks) > 1 else ""))
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=A3)
    c.setTitle(title)
    sheets = []
    for i, (kind, name, walls, pieces, part) in enumerate(plan, 1):
        if kind == "plan":
            _plan_page(c, fonts, name, walls, pieces, brand, title, lang, i, len(plan), floors_meta.get(name, ""))
            sheets.append(f"{name} · {_tr('planta das paredes, cotada', lang)}")
        else:
            _elevation_page(c, fonts, name, pieces, brand, title, lang, i, len(plan), part)
            sheets.append(f"{name} · {_tr('alçados das paredes, cotados', lang)}{part}")
        c.showPage()
    c.save()
    return out.getvalue(), sheets
