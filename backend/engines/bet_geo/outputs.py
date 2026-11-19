"""Peças desenhadas (PDF A3 à escala + DXF), nota de cálculo (PDF A4) e mapa de quantidades (XLSX)
sobre a geometria REAL. Mesmas primitivas para PDF e DXF."""
from __future__ import annotations

import datetime as _dt
import math
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .model import Building
from .structure import Result

INK = colors.HexColor("#1f2933")
BLUE = colors.HexColor("#1d4ed8")
RED = colors.HexColor("#c0262d")
GREY = colors.HexColor("#9aa5b1")
GREEN = colors.HexColor("#0f766e")
_SAFE = {"→": "->", "←": "<-", "≤": "<=", "≥": ">=", "≈": "~", "−": "-", "’": "'", "⁻¹": "-1", "⁻": "-", "θ": "t", "Φ": "Phi ",
         "Δ": "D", "σ": "s", "η": "eta", "λ": "lambda", "★": "*", "·": "·", "Σ": "Soma "}


def _t(s) -> str:
    s = str(s)
    for a, b in _SAFE.items():
        s = s.replace(a, b)
    return s


def _n(x, d=2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


# ----------------------------------------------------------------------------- folha A3
class _Sheet:
    def __init__(self, c: canvas.Canvas, b: Building, scale: int, title: str, number: str, meta: dict):
        self.c, self.b = c, b
        W, H = landscape(A3)
        self.W, self.H = W, H
        self.k = 1000 / scale * mm               # pontos por metro real
        x0, y0, x1, y1 = b.roof_slab.bounds
        self.ox = 20 * mm + (W - 130 * mm - (x1 - x0) * self.k) / 2 - x0 * self.k
        self.oy = 20 * mm + (H - 40 * mm - (y1 - y0) * self.k) / 2 - y0 * self.k
        self._frame(title, number, scale, meta)

    def p(self, x, y):
        return self.ox + x * self.k, self.oy + y * self.k

    def _frame(self, title, number, scale, meta):
        c, W, H = self.c, self.W, self.H
        c.setStrokeColor(INK)
        c.setLineWidth(0.8)
        c.rect(10 * mm, 10 * mm, W - 20 * mm, H - 20 * mm)
        bx = W - 110 * mm
        c.rect(bx, 10 * mm, 100 * mm, 60 * mm)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(bx + 5 * mm, 60 * mm, _t(title))
        c.setFont("Helvetica", 8.5)
        lines = [f"Obra: {meta.get('obra', '-')}", f"Escala 1:{scale}  ·  Folha {number}",
                 f"Data: {_dt.date.today().strftime('%d/%m/%Y')}",
                 "Pré-dimensionamento ConstruPilot — geometria real lida das plantas",
                 "A validar e assinar por engenheiro civil (projeto de estabilidade)"]
        for i, ln in enumerate(lines):
            c.drawString(bx + 5 * mm, (52 - 7 * i) * mm, _t(ln))

    def poly(self, g, stroke=INK, width=0.6, fill=None, dash=None):
        c = self.c
        for p in getattr(g, "geoms", [g]):
            for ring in [p.exterior, *p.interiors]:
                path = c.beginPath()
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
                c.drawPath(path, stroke=1, fill=1 if fill is not None else 0)
                c.setDash()

    def line(self, ls, stroke=INK, width=0.6, dash=None):
        c = self.c
        cs = [self.p(*q) for q in ls.coords]
        c.setStrokeColor(stroke)
        c.setLineWidth(width)
        c.setDash(*(dash or []))
        for a, b in zip(cs, cs[1:]):
            c.line(a[0], a[1], b[0], b[1])
        c.setDash()

    def text(self, x, y, s, size=6.5, color=INK, bold=False, angle=0.0):
        c = self.c
        c.saveState()
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        X, Y = self.p(x, y)
        c.translate(X, Y)
        c.rotate(angle)
        c.drawCentredString(0, 0, _t(s))
        c.restoreState()

    def legend(self, rows):
        c = self.c
        x, y = self.W - 110 * mm, 80 * mm + len(rows) * 5 * mm
        c.setFont("Helvetica-Bold", 8.5)
        c.setFillColor(INK)
        c.drawString(x, y + 5 * mm, "Legenda")
        c.setFont("Helvetica", 7.5)
        for i, (col, txt) in enumerate(rows):
            yy = y - i * 5 * mm
            c.setFillColor(col)
            c.rect(x, yy - 1, 6 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(INK)
            c.drawString(x + 8 * mm, yy, _t(txt))


def _angle(ls):
    (x0, y0), (x1, y1) = ls.coords[0], ls.coords[-1]
    a = math.degrees(math.atan2(y1 - y0, x1 - x0))
    return a + 180 if a > 90 else a - 180 if a < -90 else a


def _pick_scale(b: Building) -> int:
    x0, y0, x1, y1 = b.roof_slab.bounds
    for s in (50, 75, 100, 125, 150, 200, 250, 500):
        if (x1 - x0) * 1000 / s <= 270 and (y1 - y0) * 1000 / s <= 240:
            return s
    return 500


def write_plans_pdf(b: Building, R: Result, path: Path, meta: dict) -> Path:
    c = canvas.Canvas(str(path), pagesize=landscape(A3))
    c.setTitle(_t(f"Estrutura - {meta.get('obra', '')}"))
    draw_structure(c, b, R, meta)
    c.save()
    return path


def draw_structure(c, b: Building, R: Result, meta: dict) -> None:
    """E01 + E02 num canvas já aberto (também usado pelo conjunto completo de desenhos)."""
    scale = _pick_scale(b)

    # ---- E01 planta estrutural da cobertura
    s = _Sheet(c, b, scale, "Planta estrutural da cobertura", "E01", meta)
    s.poly(b.roof_slab, stroke=INK, width=0.9, fill=colors.HexColor("#f5f7fa"))
    s.poly(b.footprint, stroke=GREY, width=0.4, dash=[3, 2])
    for w in b.walls:
        s.poly(w.line.buffer(w.t / 2, cap_style=2), stroke=GREY, width=0.2, fill=colors.HexColor("#d9dee5"))
    for p in R.panels:
        g = p["geom"]
        q = g.representative_point()
        s.text(q.x, q.y + 0.25, f"{p['id']}  e={_n(R.slab['h'])}", 6.5, GREEN, True)
        lab = f"inf. {p['inf']['label']}" + (f" · sup. {p['sup']['label']}" if p.get("sup") else "")
        s.text(q.x, q.y - 0.2, lab, 5.5, GREEN)
    for v in R.beams:
        s.line(v["geom"], BLUE, 1.6)
        m = v["geom"].interpolate(0.5, normalized=True)
        s.text(m.x, m.y + 0.12, f"{v['id']} {int(v['b'] * 100)}x{int(v['h'] * 100)}", 5.5, BLUE, angle=_angle(v["geom"]))
    for col in R.columns:
        a = col["a"]
        s.poly(_sq(col["x"], col["y"], a), stroke=RED, width=0.4, fill=RED)
        s.text(col["x"] + a / 2 + 0.35, col["y"] + a / 2 + 0.1, col["id"], 5.5, RED, True)
    s.legend([(colors.HexColor("#f5f7fa"), f"Laje maciça C30/37, e = {_n(R.slab['h'])} m"),
              (BLUE, "Viga (b x h, cm)"), (RED, "Pilar"), (colors.HexColor("#d9dee5"), "Paredes lidas da arquitetura"),
              (GREEN, "Painel de laje e armaduras (A500 NR)")])
    c.showPage()

    # ---- E02 planta de fundações
    s = _Sheet(c, b, scale, "Planta de fundações", "E02", meta)
    s.poly(b.footprint, stroke=GREY, width=0.5, dash=[3, 2])
    for v in R.tie_beams:
        s.poly(v["geom"].buffer(v["b"] / 2, cap_style=2), stroke=BLUE, width=0.3, fill=colors.HexColor("#dbe6fb"))
    for m in R.retaining:
        s.poly(m["geom"].buffer(m["t"] / 2, cap_style=2), stroke=INK, width=0.5, fill=colors.HexColor("#7b8794"))
        q = m["geom"].interpolate(0.5, normalized=True)
        s.text(q.x, q.y - 0.55, f"{m['id']}: muro e={_n(m['t'])} · terras {_n(m['H_terras'])} m · sapata {_n(m['sapata_B'])} m", 6, INK, True)
    for f in R.footings:
        s.poly(_sq(f["x"], f["y"], f["B"]), stroke=INK, width=0.6, fill=colors.HexColor("#fde68a"))
        s.text(f["x"], f["y"] - f["B"] / 2 - 0.3, f"{f['id']} {_n(f['B'])}x{_n(f['B'])}x{_n(f['h'])}", 5.2, INK)
    for col in R.columns:
        s.poly(_sq(col["x"], col["y"], col["a"]), stroke=RED, width=0.3, fill=RED)
    s.legend([(colors.HexColor("#fde68a"), "Sapata isolada (B x B x h, m)"),
              (colors.HexColor("#dbe6fb"), "Viga de fundação 30x40 (paredes)"),
              (colors.HexColor("#7b8794"), "Muro de suporte"), (RED, "Arranque de pilar")])
    c.showPage()


def _sq(x, y, a):
    from shapely.geometry import box
    return box(x - a / 2, y - a / 2, x + a / 2, y + a / 2)


# ----------------------------------------------------------------------------- DXF
def write_dxf(b: Building, R: Result, path: Path) -> Path:
    import ezdxf

    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.M
    msp = doc.modelspace()
    for name, col in (("CONTORNO", 8), ("LAJE", 7), ("VIGAS", 5), ("PILARES", 1), ("SAPATAS", 30),
                      ("VIGAS_FUNDACAO", 4), ("MUROS", 252), ("PAREDES_ARQ", 9), ("TEXTO", 7)):
        doc.layers.add(name, color=col)

    def poly(g, layer):
        for p in getattr(g, "geoms", [g]):
            for ring in [p.exterior, *p.interiors]:
                msp.add_lwpolyline(list(ring.coords), close=True, dxfattribs={"layer": layer})

    poly(b.footprint, "CONTORNO")
    poly(b.roof_slab, "LAJE")
    for w in b.walls:
        poly(w.line.buffer(w.t / 2, cap_style=2), "PAREDES_ARQ")
    for v in R.beams:
        msp.add_line(v["geom"].coords[0], v["geom"].coords[-1], dxfattribs={"layer": "VIGAS"})
        m = v["geom"].interpolate(0.5, normalized=True)
        msp.add_text(f"{v['id']} {int(v['b'] * 100)}x{int(v['h'] * 100)}", height=0.12,
                     dxfattribs={"layer": "TEXTO", "insert": (m.x, m.y + 0.1), "rotation": _angle(v["geom"])})
    for c in R.columns:
        poly(_sq(c["x"], c["y"], c["a"]), "PILARES")
        msp.add_text(c["id"], height=0.12, dxfattribs={"layer": "TEXTO", "insert": (c["x"] + 0.2, c["y"] + 0.2)})
    for f in R.footings:
        poly(_sq(f["x"], f["y"], f["B"]), "SAPATAS")
        msp.add_text(f"{f['id']} {f['B']}x{f['B']}x{f['h']}", height=0.10,
                     dxfattribs={"layer": "TEXTO", "insert": (f["x"] - f["B"] / 2, f["y"] - f["B"] / 2 - 0.2)})
    for v in R.tie_beams:
        poly(v["geom"].buffer(v["b"] / 2, cap_style=2), "VIGAS_FUNDACAO")
    for m in R.retaining:
        poly(m["geom"].buffer(m["t"] / 2, cap_style=2), "MUROS")
    doc.saveas(str(path))
    return path


# ----------------------------------------------------------------------------- XLSX
def write_quantities_xlsx(R: Result, path: Path, meta: dict) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Quantidades"
    ws.append([f"Mapa de quantidades — {meta.get('obra', '')}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Pré-dimensionamento sobre a geometria real lida das plantas. Preços unitários a preencher (coluna F)."])
    ws.append([])
    hdr = ["Lote", "Artigo", "Un.", "Quantidade", "Aço A500 (kg)", "Preço unit. (€)", "Total (€)", "Nota"]
    ws.append(hdr)
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F2933")
    first = ws.max_row + 1
    for q in R.quantities:
        r = ws.max_row + 1
        ws.append([q["lote"], q["item"], q["un"], q["qtd"], q["aco_kg"] or None, None, f"=D{r}*F{r}", q.get("nota", "")])
    last = ws.max_row
    r = last + 1
    ws.append(["", "Aço A500 NR (total)", "kg", f"=SUM(E{first}:E{last})", None, None, f"=D{r}*F{r}", ""])
    ws.append(["", "TOTAL", "", "", "", "", f"=SUM(G{first}:G{r})", ""])
    ws.cell(ws.max_row, 2).font = Font(bold=True)
    for col, w in zip("ABCDEFGH", (16, 70, 6, 12, 14, 14, 14, 40)):
        ws.column_dimensions[col].width = w
    wb.save(str(path))
    return path


# ----------------------------------------------------------------------------- nota de cálculo
def write_report_pdf(b: Building, R: Result, path: Path, meta: dict) -> Path:
    st = {
        "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, leading=19, spaceAfter=6, textColor=INK),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4, textColor=INK),
        "p": ParagraphStyle("p", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=INK),
        "w": ParagraphStyle("w", fontName="Helvetica", fontSize=8.5, leading=11.5, textColor=RED),
    }
    P = lambda s, k="p": Paragraph(_t(s), st[k])  # noqa: E731

    def table(rows, widths=None):
        t = Table([[P(str(x)) for x in r] for r in rows], colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e4e7eb")),
                               ("GRID", (0, 0), (-1, -1), 0.3, GREY), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        return t

    E = []
    E.append(P("Nota de cálculo — pré-dimensionamento estrutural", "h1"))
    E.append(P(f"Obra: {meta.get('obra', '-')} · {_dt.date.today().strftime('%d/%m/%Y')} · ConstruPilot (motor de geometria real)"))
    E.append(Spacer(1, 4 * mm))
    E.append(P("1. Geometria lida das peças desenhadas", "h2"))
    E.append(P("A geometria é a forma REAL do edifício (polígono qualquer, com pátios), lida diretamente das plantas "
               "vetoriais à escala. Nenhuma simplificação retangular é usada."))
    rows = [["Grandeza", "Valor", "Fonte / método"]]
    for ck in b.checks:
        v = ck.get("valor", "")
        v = _n(v) if isinstance(v, (int, float)) else v
        rows.append([ck["item"], f"{v} {ck.get('unidade', '')}", (ck.get("metodo") or ck.get("fonte", "")).replace("390.50", "390,50")])
    rows.append(["Área da laje de cobertura (inclui palas)", f"{_n(R.slab['area'])} m²", "contorno + áreas exteriores cobertas"])
    rows.append(["Pé-direito estrutural", f"{_n(b.storey_height)} m", ", ".join(b.sources) or "-"])
    E.append(table(rows, [60 * mm, 32 * mm, 88 * mm]))
    E.append(P("2. Materiais e ações", "h2"))
    L = R.loads
    E.append(table([["Item", "Valor"],
                    ["Betão", "C30/37 (fck 30 MPa, fcd 20 MPa); laje térrea C25/30; limpeza C12/15"],
                    ["Aço", "A500 NR (fyd 435 MPa)"],
                    ["Peso próprio da laje", f"{_n(L['g_laje'])} kN/m²"],
                    ["Restantes cargas permanentes (cobertura invertida)", f"{_n(L['g_revestimentos'])} kN/m²"],
                    ["Sobrecarga / neve (o maior)", f"{_n(L['q_sobrecarga'])} kN/m²"],
                    ["Carga de cálculo ELU (1,35 G + 1,5 Q)", f"{_n(L['p_Ed_laje'])} kN/m²"],
                    ["Tensão admissível do terreno", "200 kPa (hipótese — confirmar por estudo geotécnico)"]],
                   [90 * mm, 90 * mm]))
    E.append(P("3. Método", "h2"))
    E.append(P("Linhas de apoio = contorno da laje, pátios e paredes interiores com espessura >= 14 cm, prolongadas até à "
               "linha seguinte. Pilares nos cantos, encontros e extremos, e intermédios apenas sobre paredes (nunca a meio de "
               "um envidraçado). Cada ponto da laje (malha de 0,20 m) descarrega na viga mais próxima — áreas de influência "
               "válidas para qualquer polígono. Vão equivalente de cada painel = 2 x maior distância a um apoio; "
               "esbelteza L/d <= 30 (contínua) e <= 10 (consola), EC2 7.4.2."))
    E.append(P("4. Laje de cobertura", "h2"))
    rows = [["Painel", "Área (m²)", "Tipo", "Vão eq. (m)", "M+ / M- (kNm/m)", "Inferior", "Superior"]]
    for p in R.panels:
        rows.append([p["id"], _n(p["area"]), p["tipo"], _n(p["Lx_eq"]), f"{_n(p['m_pos'], 1)} / {_n(p['m_neg'], 1)}",
                     p["inf"]["label"], p["sup"]["label"] if p.get("sup") else "-"])
    E.append(table(rows, [15 * mm, 18 * mm, 38 * mm, 20 * mm, 30 * mm, 28 * mm, 28 * mm]))
    E.append(P(f"Espessura única adotada: e = {_n(R.slab['h'])} m (governada pelo painel mais exigente)."))
    E.append(PageBreak())
    E.append(P("5. Vigas de cobertura", "h2"))
    rows = [["Viga", "Vão (m)", "b x h (cm)", "w_Ed (kN/m)", "M_Ed (kNm)", "V_Ed (kN)", "Inferior", "Superior", "Estribos"]]
    for v in R.beams:
        rows.append([v["id"], _n(v["L"]), f"{int(v['b'] * 100)}x{int(v['h'] * 100)}", _n(v["w_Ed"], 1), _n(v["M_Ed"], 1),
                     _n(v["V_Ed"], 1), v["inf"]["label"], v["sup"]["label"], v["estribos"]])
    E.append(table(rows, [13 * mm, 15 * mm, 18 * mm, 20 * mm, 19 * mm, 18 * mm, 20 * mm, 20 * mm, 20 * mm]))
    E.append(P("6. Pilares e sapatas", "h2"))
    fby = {f["pilar"]: f for f in R.footings}
    rows = [["Pilar", "Secção (cm)", "N_Ed (kN)", "Armadura", "Sapata", "B x B x h (m)", "σ serviço (kPa)", "Armadura sapata"]]
    for c in R.columns:
        f = fby.get(c["id"], {})
        rows.append([c["id"], f"{int(c['a'] * 100)}x{int(c['b'] * 100)}", _n(c["N_Ed"], 1),
                     f"{c['armadura']['label']} + {c['estribos']}", f.get("id", "-"),
                     f"{_n(f.get('B', 0))}x{_n(f.get('B', 0))}x{_n(f.get('h', 0))}", _n(f.get("sigma_sls", 0), 0),
                     f.get("armadura", "-")])
    E.append(table(rows, [13 * mm, 18 * mm, 18 * mm, 32 * mm, 15 * mm, 28 * mm, 22 * mm, 34 * mm]))
    if R.retaining:
        E.append(P("7. Muros de suporte", "h2"))
        rows = [["Muro", "Comp. (m)", "Terras (m)", "e (m)", "M_Ed (kNm/m)", "Vertical (terras)", "Vertical (outra)", "Horizontal", "Sapata (m)"]]
        for m in R.retaining:
            rows.append([m["id"], _n(m["L"]), _n(m["H_terras"]), _n(m["t"]), _n(m["M_Ed"], 1), m["vertical_terras"],
                         m["vertical_outra"], m["horizontal"], f"{_n(m['sapata_B'])} x {_n(m['sapata_h'])}"])
        E.append(table(rows))
    E.append(P("8. Laje térrea e vigas de fundação", "h2"))
    g = R.ground_slab
    E.append(P(f"Laje térrea C25/30, e = {_n(g['h'])} m, {g['armadura']}, sobre 0,20 m de tout-venant compactado "
               f"({_n(g['area'])} m²). Vigas de fundação 30x40 sob todas as linhas de vigas, a receber as alvenarias."))
    E.append(PageBreak())
    E.append(P("9. Mapa de quantidades", "h2"))
    rows = [["Lote", "Artigo", "Un.", "Quantidade", "Aço (kg)"]]
    for q in R.quantities:
        rows.append([q["lote"], q["item"], q["un"], _n(q["qtd"]), _n(q["aco_kg"], 0) if q["aco_kg"] else "-"])
    rows.append(["", "Aço A500 NR total", "kg", _n(sum(q["aco_kg"] for q in R.quantities), 0), ""])
    E.append(table(rows, [26 * mm, 95 * mm, 10 * mm, 24 * mm, 22 * mm]))
    E.append(P("10. Confrontação com rácios de referência (2.ª fonte)", "h2"))
    rows = [["Indicador", "Valor", "Referência", "Estado"]]
    for ck in R.checks:
        rows.append([ck["item"], f"{_n(ck['valor'], 3)} {ck['un']}", ck["referencia"], "OK" if ck["ok"] else "REVER"])
    E.append(table(rows, [85 * mm, 30 * mm, 30 * mm, 20 * mm]))
    E.append(P("11. Avisos e pontos a validar", "h2"))
    for w in R.warnings:
        E.append(P("• " + w, "w"))
    E.append(Spacer(1, 4 * mm))
    E.append(P("Documento de pré-dimensionamento gerado automaticamente. Não dispensa o projeto de estabilidade "
               "elaborado e assinado por engenheiro civil inscrito na Ordem dos Engenheiros."))
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=14 * mm,
                      bottomMargin=14 * mm, title=_t(f"Nota de cálculo - {meta.get('obra', '')}")).build(E)
    return path


def write_full_xlsx(lines: list[dict], R: Result, lay, path: Path, meta: dict) -> Path:
    """Medições e orçamento completos (todas as especialidades) + quantidades de estrutura + quadro de áreas + mapa de vãos.
    Totais em fórmulas (o cliente altera um preço e tudo se recalcula)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Medições e orçamento"
    ws.append([f"Medições e orçamento — {meta.get('obra', '')}"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append(["Quantidades medidas na geometria real e calculadas pelos motores; preços de referência sem IVA (substituir pela biblioteca da empresa)."])
    ws.append([])
    ws.append(["Capítulo", "Designação", "Un.", "Quantidade", "Preço unit. (€)", "Total (€)", "Origem da quantidade"])
    for c in ws[4]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="0F3D2E")
    first = ws.max_row + 1
    for l in lines:
        r = ws.max_row + 1
        ws.append([l["lot"], l["label"], l["unit"], l["qty"], l["pu"], f"=D{r}*E{r}", l.get("note", "")])
    last = ws.max_row
    ws.append(["", "TOTAL (sem IVA)", "", "", "", f"=SUM(F{first}:F{last})", ""])
    ws.append(["", "IVA 23 %", "", "", "", f"=F{last + 1}*0.23", "taxa a confirmar (6 % em obras abrangidas pela verba 2.32/2.27 da Lista I do CIVA)"])
    ws.append(["", "TOTAL (com IVA)", "", "", "", f"=F{last + 1}+F{last + 2}", ""])
    for rr in range(last + 1, last + 4):
        ws.cell(rr, 2).font = Font(bold=True)
        ws.cell(rr, 6).font = Font(bold=True)
    for col, w in zip("ABCDEFG", (24, 80, 6, 12, 14, 14, 60)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=first, max_row=last + 3, min_col=4, max_col=6):
        for c in row:
            c.number_format = "#,##0.00"
    s2 = wb.create_sheet("Estrutura")
    s2.append(["Lote", "Artigo", "Un.", "Quantidade", "Aço A500 (kg)", "Nota"])
    for q in R.quantities:
        s2.append([q["lote"], q["item"], q["un"], q["qtd"], q["aco_kg"] or None, q.get("nota", "")])
    s3 = wb.create_sheet("Áreas")
    s3.append(["N.º", "Divisão", "Área (m²)", "Uso", "Aquecida", "Origem"])
    for r in lay.rooms:
        s3.append([r.number, r.name, r.area, r.type, "sim" if r.heated else "não", r.source])
    if lay.windows:
        s4 = wb.create_sheet("Vãos")
        s4.append(["Vão", "Largura (m)", "Altura (m)", "Qtd.", "Área (m²)", "Divisão", "Orientação"])
        for w in lay.windows:
            s4.append([w.name, w.w, w.h, w.qty, w.area, w.room, w.orient])
    wb.save(str(path))
    return path
