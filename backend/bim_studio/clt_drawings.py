"""Fabrication drawings of CLT pieces and cutting plans (ezdxf, MIT).

One DXF in millimetres with three groups of layouts placed side by side in
model space: the floor plan of the wall axes with piece labels, one elevation
per piece with its openings and dimensions, and the cutting plan of each
press blank. A PDF of the same drawing is produced through the ezdxf drawing
add-on with Matplotlib.

These are fabrication check drawings built from the measured quantities. They
are not structural execution drawings, which stay outside the pilot scope.
"""
from __future__ import annotations

import io

import ezdxf
from ezdxf.enums import TextEntityAlignment

LAYERS = {"CLT_EIXO": 1, "CLT_PECA": 5, "CLT_VAO": 3, "CLT_COTA": 8, "CLT_TEXTO": 7, "CLT_PAINEL": 6}
NOTE = "Desenho de conferência de fabrico gerado pela ConstruPilot. Não substitui o projeto de execução."


def _doc():
    doc = ezdxf.new("R2018", setup=True, units=ezdxf.units.MM)
    for name, colour in LAYERS.items():
        doc.layers.add(name, color=colour)
    return doc


def _text(msp, text, x, y, h=60, layer="CLT_TEXTO"):
    msp.add_text(text, height=h, dxfattribs={"layer": layer, "style": "OpenSans"}).set_placement(
        (x, y), align=TextEntityAlignment.BOTTOM_LEFT)


def _dim(msp, p1, p2, base, angle=0):
    msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, dimstyle="EZDXF",
                       override={"dimtxt": 60, "dimasz": 40, "dimdec": 0}, dxfattribs={"layer": "CLT_COTA"}).render()


def _plan(msp, title, name, walls, oy=0.0):
    xs = [v for w in walls for v in (w.x1, w.x2)]
    ys = [v for w in walls for v in (w.y1, w.y2)]
    ox, oy = -min(xs) * 1000, oy - min(ys) * 1000
    _text(msp, f"{title} · {name} · planta dos eixos CLT", ox + min(xs) * 1000,
          oy + max(ys) * 1000 + 400, 150)
    for w in walls:
        a = (ox + w.x1 * 1000, oy + w.y1 * 1000)
        b = (ox + w.x2 * 1000, oy + w.y2 * 1000)
        msp.add_line(a, b, dxfattribs={"layer": "CLT_EIXO"})
        msp.add_lwpolyline([(ox + x * 1000, oy + y * 1000) for x, y in w.footprint().exterior.coords],
                           close=True, dxfattribs={"layer": "CLT_PECA"})
        _text(msp, f"{w.id} · {w.thickness_mm:g} mm", (a[0] + b[0]) / 2, (a[1] + b[1]) / 2 + 80, 80)
    return oy + min(ys) * 1000


def _pieces(msp, pieces, y0):
    x0 = 0.0
    for p in pieces:
        L, H = p["comprimento_m"] * 1000, p["altura_m"] * 1000
        msp.add_lwpolyline([(x0, y0), (x0 + L, y0), (x0 + L, y0 + H), (x0, y0 + H)], close=True,
                           dxfattribs={"layer": "CLT_PECA"})
        for o in p["vaos"]:
            vx, vy = x0 + o["offset_m"] * 1000, y0 + o["sill_m"] * 1000
            vw, vh = o["width_m"] * 1000, o["height_m"] * 1000
            msp.add_lwpolyline([(vx, vy), (vx + vw, vy), (vx + vw, vy + vh), (vx, vy + vh)], close=True,
                               dxfattribs={"layer": "CLT_VAO"})
            msp.add_line((vx, vy), (vx + vw, vy + vh), dxfattribs={"layer": "CLT_VAO"})
            msp.add_line((vx + vw, vy), (vx, vy + vh), dxfattribs={"layer": "CLT_VAO"})
            _dim(msp, (x0, vy), (vx, vy), (x0, vy - 150))
            _dim(msp, (vx, vy), (vx + vw, vy), (vx, vy - 150))
            _dim(msp, (vx + vw, vy), (vx + vw, vy + vh), (vx + vw + 200, vy), angle=90)
            if o["sill_m"] > 0:
                _dim(msp, (vx, y0), (vx, vy), (vx - 200, y0), angle=90)
        _dim(msp, (x0, y0), (x0 + L, y0), (x0, y0 - 400))
        _dim(msp, (x0, y0), (x0, y0 + H), (x0 - 400, y0), angle=90)
        _text(msp, f"Peça {p['id']} · {p['espessura_mm']:g} mm {p['camadas']}c · "
                   f"{p['area_liquida_m2']:.2f} m² · {p['volume_liquido_m3']:.3f} m³", x0, y0 + H + 120, 90)
        x0 += L + 1500
        if x0 > 36000:  # wrap so each PDF page stays legible
            x0, y0 = 0.0, y0 - 5500
    return y0


def _cutting(msp, g, y0):
    _text(msp, f"Plano de corte · CLT {g['espessura_mm']:g} mm {g['camadas']}c · {g['paineis']} painéis · "
               f"desperdício {g['desperdicio_percent']} % · {g['motor']}", 0, y0 + 300, 150)
    for b in g["layout"]:
        L, W = b["comprimento_usado_m"] * 1000, b["largura_m"] * 1000
        y0 -= W + 1200
        msp.add_lwpolyline([(0, y0), (L, y0), (L, y0 + W), (0, y0 + W)], close=True,
                           dxfattribs={"layer": "CLT_PAINEL"})
        _text(msp, f"Painel {b['painel']} · {b['comprimento_usado_m']:.2f} × {b['largura_m']:.2f} m · "
                   f"aproveitamento {b['aproveitamento_percent']} %", 0, y0 + W + 80, 90)
        for p in b["pecas"]:
            px, py = p["x_m"] * 1000, y0 + p["y_m"] * 1000
            pl, pw = p["comprimento_m"] * 1000, p["largura_m"] * 1000
            msp.add_lwpolyline([(px, py), (px + pl, py), (px + pl, py + pw), (px, py + pw)], close=True,
                               dxfattribs={"layer": "CLT_PECA"})
            _text(msp, p["id"], px + 100, py + pw / 2, 120)
    return y0


def build(floors, nesting=None, *, title="ConstruPilot CLT"):
    """floors: list of (name, walls, pieces). Returns {"dxf": bytes, "pdf": bytes, "folhas": [...]}.

    The DXF holds every sheet in model space, one under the other. The PDF has
    one A3 page per sheet: plan, piece elevations of each floor, and the
    cutting plan of each build-up.
    """
    doc = _doc()
    msp = doc.modelspace()
    pages, sheets = [], []
    y = 0.0
    for name, walls, pieces in floors:
        bottom = _plan(msp, title, name, walls, y)
        y = _pieces(msp, pieces, bottom - 5000) - 7000
        page = _doc()
        _plan(page.modelspace(), title, name, walls)
        _text(page.modelspace(), NOTE, 0, -1500, 100)
        pages.append(page)
        page = _doc()
        last = _pieces(page.modelspace(), pieces, 0)
        _text(page.modelspace(), f"{title} · {name} · alçados de fabrico das peças CLT", 0, 4500, 150)
        _text(page.modelspace(), NOTE, 0, last - 1500, 100)
        pages.append(page)
        sheets.append({"folha": f"{name} · planta dos eixos", "pecas": len(walls)})
        sheets.append({"folha": f"{name} · alçados de fabrico", "pecas": len(pieces),
                       "vaos": sum(len(p["vaos"]) for p in pieces)})
    for g in (nesting or {}).get("grupos", []):
        y = _cutting(msp, g, y) - 2500
        page = _doc()
        _cutting(page.modelspace(), g, 0)
        _text(page.modelspace(), NOTE, 0, -sum(b["largura_m"] * 1000 + 1200 for b in g["layout"]) - 1500, 100)
        pages.append(page)
        sheets.append({"folha": f"Plano de corte CLT {g['espessura_mm']:g} mm {g['camadas']}c", "paineis": g["paineis"]})
    _text(msp, NOTE, 0, y - 600, 120)
    stream = io.StringIO()
    doc.write(stream)
    return {"dxf": stream.getvalue().encode("utf-8"), "pdf": _pdf(pages), "folhas": sheets}


def _pdf(docs):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from matplotlib.backends.backend_pdf import PdfPages

    config = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK)
    out = io.BytesIO()
    with PdfPages(out) as pdf:
        for doc in docs:
            fig = plt.figure(figsize=(16.54, 11.69))  # A3 landscape
            ax = fig.add_axes([0.03, 0.03, 0.94, 0.94])
            ax.set_axis_off()
            Frontend(RenderContext(doc), MatplotlibBackend(ax), config=config).draw_layout(doc.modelspace(), finalize=True)
            pdf.savefig(fig)
            plt.close(fig)
    return out.getvalue()
