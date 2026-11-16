"""Vector sheets and reusable CAD geometry for the perimeter strip checks."""
from __future__ import annotations

import io
import math
import zipfile

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from shapely.geometry import LineString, Polygon

from .strip_foundations import _edge_key

INK = HexColor("#172B32")
GREEN = HexColor("#216353")
PALE = HexColor("#E3F0EB")
GRID = HexColor("#BDCEC9")
ORANGE = HexColor("#994320")


def _num(value, places=2):
    return f"{value:.{places}f}".replace(".", ",")


def _text(c, x, y, value, size=11, *, bold=False, color=INK, center=False):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.setFillColor(color)
    (c.drawCentredString if center else c.drawString)(x, y, value)


def _frame(c, title, subtitle, page, demo):
    w, h = c._pagesize
    c.setFillColor(PALE)
    c.rect(0, h - 117, w, 117, fill=1, stroke=0)
    _text(c, 45, h - 34, "CONSTRUPILOT  /  FUNDAÇÕES  /  " + ("ENSAIO COM DADOS FICTÍCIOS" if demo else "ESTUDO DE PROJETO"), 11, bold=True, color=GREEN)
    _text(c, 45, h - 74, title, 33, bold=True)
    _text(c, 45, h - 99, subtitle, 12)
    c.setStrokeColor(GRID)
    c.line(45, 59, w - 45, 59)
    _text(c, 45, 37, "PRÉ-DIMENSIONAMENTO  /  REVISÃO ESTRUTURAL OBRIGATÓRIA ANTES DA EXECUÇÃO", 10, bold=True, color=ORANGE)
    _text(c, w - 125, 37, f"A3   F-{page:02d} / 03", 10, color=GREEN)


def _polygon(c, ring, xy, polygon=None):
    path = polygon or c.beginPath()
    for index, point in enumerate(ring.coords):
        (path.lineTo if index else path.moveTo)(*xy(point))
    path.close()
    return path


def _table(c, x, top, columns, header, rows, height=30):
    width = sum(columns)
    for index, row in enumerate([header, *rows]):
        y = top - index * height
        c.setFillColor(PALE if index == 0 else (HexColor("#F6FAF8") if index % 2 else white))
        c.rect(x, y - height, width, height, fill=1, stroke=0)
        offset = x
        for value, cell_width in zip(row, columns):
            _text(c, offset + 10, y - height / 2 - 4, str(value), 10, bold=index == 0)
            offset += cell_width


def _plan(c, design):
    outline, band = design["outline"], design["band"]
    a, b, d, e = band.bounds
    scale = next(s for s in (25, 50, 75, 100, 150, 200, 300, 500, 1000)
                 if (d-a)*1000*mm/s <= 630 and (e-b)*1000*mm/s <= 507)
    k = 1000 * mm / scale
    x0 = 75 + (630 - (d-a)*k)/2 - a*k
    y0 = 105 + (507 - (e-b)*k)/2 - b*k

    def xy(point):
        return x0 + point[0]*k, y0 + point[1]*k

    _frame(c, "Implantação das sapatas lineares", f"Contorno de origem e faixa de fundação unidos em L  /  1:{scale}",
           1, design["inputs"].demo)
    c.setFillColor(PALE)
    c.setStrokeColor(GREEN)
    c.setLineWidth(1.4)
    c.drawPath(_polygon(c, band.interiors[0], xy, _polygon(c, band.exterior, xy)), fill=1, stroke=1, fillMode=0)
    c.setDash(6, 3)
    c.setStrokeColor(INK)
    c.drawPath(_polygon(c, outline.exterior, xy), fill=0, stroke=1)
    c.setDash()
    rows = []
    for i, (start, end) in enumerate(design["edges"], 1):
        length = math.dist(start, end)
        vx, vy = (end[1]-start[1])/length, (start[0]-end[0])/length
        midpoint = tuple((p+q)/2 for p,q in zip(start, end))
        mx, my = xy(midpoint)
        offset = design["width_mm"] / 2000 * k + 16
        label = f"S{i:02d}  /  {_num(length)} m"
        c.saveState()
        c.translate(mx + vx*offset, my + vy*offset)
        if abs(vx) > .5:
            c.rotate(90)
        _text(c, 0, -3, label, 11, bold=True, color=GREEN, center=True)
        c.restoreState()
        rows.append((f"S{i:02d}", _num(length), f"{_num(start[0])} / {_num(start[1])}", f"{_num(end[0])} / {_num(end[1])}"))
    _table(c, 752, 679, (62, 72, 112, 112), ("Tramo", "Eixo (m)", "Início X / Y (m)", "Fim X / Y (m)"), rows)
    _text(c, 762, 425, f"Secção comum   {design['width_mm']} × {design['height_mm']} mm", 20, bold=True)
    _text(c, 762, 397, f"Contorno de origem   {_num(outline.area)} m²", 12)
    _text(c, 762, 375, f"Comprimento total no eixo   {_num(outline.length)} m", 12)
    _text(c, 762, 353, f"Área da faixa de betão   {_num(band.area)} m²", 12)
    _text(c, 762, 313, "Tracejado: eixos declarados no contorno de origem.", 11)
    _text(c, 762, 292, "Faixa verde: betão com os cantos unidos em planta.", 11)
    _text(c, 762, 271, "Armadura de canto e continuidade: pormenor por validar.", 11, bold=True, color=ORANGE)
    c.showPage()


def _section(c, design):
    inputs = design["inputs"].values
    _frame(c, "Armaduras da secção corrente", "Corte transversal 1:10  /  Disposição inferior nos troços retos", 2, design["inputs"].demo)
    width, height, phi = (design[k] for k in ("width_mm", "height_mm", "bar_mm"))
    cover, wall = inputs["recobrimento_mm"], 1000*inputs["largura_parede_m"]
    k, x, y = mm / 10, 132, 395
    cx = x + width*k/2
    c.setStrokeColor(GREEN)
    c.setFillColor(PALE)
    c.setLineWidth(1.3)
    c.rect(x, y, width*k, height*k, fill=1, stroke=1)
    c.rect(cx-wall*k/2, y+height*k, wall*k, 100, fill=0, stroke=1)
    c.setDash(6, 3)
    c.line(cx, y-18, cx, y+height*k+122)
    c.setDash()
    c.setStrokeColor(ORANGE)
    c.setFillColor(ORANGE)
    c.setLineWidth(phi*k)
    c.setLineCap(1)
    c.line(x+(cover+phi/2)*k, y+(cover+phi/2)*k, x+(width-cover-phi/2)*k, y+(cover+phi/2)*k)
    c.setLineCap(0)
    for i in range(design["long_count"]):
        centre = cover + phi/2 + i * design["long_spacing_mm"]
        c.circle(x+centre*k, y+(cover+1.5*phi)*k, phi*k/2, fill=1, stroke=0)
    c.setStrokeColor(INK)
    c.setLineWidth(.8)
    c.line(x, y-27, x+width*k, y-27)
    c.line(x, y-34, x, y-18)
    c.line(x+width*k, y-34, x+width*k, y-18)
    c.line(x-26, y, x-26, y+height*k)
    c.line(x-32, y, x-19, y)
    c.line(x-32, y+height*k, x-19, y+height*k)
    _text(c, cx, y-47, f"B = {width} mm", 12, bold=True, center=True)
    _text(c, x-28, y+height*k+13, f"h = {height} mm", 11, center=True)
    _text(c, 132, 255, "TRAÇO LARANJA  /  Varão transversal T1", 12, bold=True, color=ORANGE)
    _text(c, 132, 230, "PONTOS LARANJA  /  Varões longitudinais L1, acima de T1", 12, bold=True, color=ORANGE)
    rows = [
        ("T1", f"Ø{phi} / {design['spacing_mm']} mm", "Inferior, transversal"),
        ("L1", f"{design['long_count']} Ø{phi} / {_num(design['long_spacing_mm'], 1)} mm", "Inferior, longitudinal de distribuição"),
        ("c_nom", f"{cover:g} mm", "Recobrimento indicado na ficha"),
        ("Parede", f"{wall:g} mm", "Contínua, centrada na secção"),
        ("Fundação", f"-{_num(inputs['profundidade_m'])} m", "Cota da base face à referência da ficha"),
    ]
    _table(c, 620, 666, (95, 149, 263), ("Marca", "Armadura / cota", "Aplicação"), rows, 36)
    _text(c, 630, 397, "PORMENORES A VALIDAR EM PROJETO", 13, bold=True, color=ORANGE)
    for n, value in enumerate(("Continuidade, emendas e dobragens nos seis cantos.",
                               "Flexão longitudinal, fendas e assentamentos diferenciais.",
                               "Exposição, durabilidade, deslizamento e ação sísmica.")):
        _text(c, 630, 369-22*n, value, 11)
    c.showPage()


def _note(c, design):
    inputs = design["inputs"]
    _frame(c, "Memória de cálculo das fundações", "Pressões brutas de contacto, flexão transversal, esforço transverso e amarração", 3, inputs.demo)
    _text(c, 45, 685, f"Geotecnia   {inputs.soil_reference}", 12, bold=True)
    _text(c, 45, 661, f"Reações   {inputs.load_reference}", 12, bold=True)
    v = inputs.values
    _text(c, 45, 637, (f"Limites ELU / ELS {_num(v['qrd_kpa'],1)} / {_num(v['qlim_els_kpa'],1)} kPa   |   "
                      f"fck / fyk {v['fck_mpa']:g} / {v['fyk_mpa']:g} MPa   |   "
                      f"γc {v['gamma_c']:g}    γs {v['gamma_s']:g}    αcc {v['alpha_cc']:g}    αct {v['alpha_ct']:g}    γG {v['gamma_g']:g}"), 11)
    _text(c, 45, 615, (f"Peso volúmico do betão {v['peso_betao_kn_m3']:g} kN/m³   |   "
                      f"Sobrecarga permanente do aterro {v['aterro_kpa']:g} kPa   |   "
                      f"Agregado {v['agregado_mm']:g} mm   |   Aderência desfavorável"), 11)
    rows = []
    for i, ((start, end), check) in enumerate(zip(design["edges"], design["checks"]), 1):
        action = inputs.actions[_edge_key(start, end)]
        values = [action.ned, action.med, action.nser, action.mser, check['q_ed'], check['q_ser'],
                  check['m_ed'], check['v_ed'], check['v_rd'], check['as_req'], check['as_prov'], check['l_bd_mm']]
        rows.append((f"S{i:02d}", *(_num(n, 1) for n in values)))
    _table(c, 45, 585, (60, 74, 72, 72, 72, 79, 79, 76, 65, 65, 76, 79, 68),
           ("Tramo", "N_Ed", "M_Ed", "N_ser", "M_ser", "q_ELU", "q_ELS", "m_Ed,t", "V_Ed", "V_Rd,c", "As,req", "As,disp", "l_bd"), rows, 33)
    _text(c, 45, 337, "N kN/m  ·  M kNm/m  ·  q kPa  ·  m_Ed,t kNm/m  ·  V kN/m  ·  As cm²/m  ·  l_bd mm", 11)
    values = [f"Menor pressão ELU / ELS: {_num(min(r['q_min_ed'] for r in design['checks']),1)} / {_num(min(r['q_min_ser'] for r in design['checks']),1)} kPa.",
              f"Comprimento reto disponível: {_num(min(r['l_av_mm'] for r in design['checks']),1)} mm nos dois lados da parede.",
              f"Armadura longitudinal de distribuição: {_num(design['checks'][0]['as_long_prov'])} cm². Mínimo geométrico: {_num(design['checks'][0]['as_long_min'])} cm².",
              "Pressão nas bordas = N/B + peso próprio + aterro ± 6M/B². Flexão por integração da pressão em cada consola.",
              "Esforço transverso na secção à distância d da face do muro. Amarração reta verificada a partir da face do muro.",
              "Motivos de revisão: combinações completas, resistência do terreno, assentamentos, cantos e apoios interiores.",
              "Referência de cálculo: NP EN 1992-1-1 (secções 6, 8 e 9). Limites geotécnicos introduzidos na ficha do estudo."]
    for i, value in enumerate(values):
        _text(c, 45, 294-i*25, value, 11)
    c.showPage()


def write_pdf(design, path):
    canvas = Canvas(str(path), pagesize=landscape(A3))
    canvas.setTitle("Fundações e armaduras - pré-dimensionamento em L")
    _plan(canvas, design)
    _section(canvas, design)
    _note(canvas, design)
    canvas.save()


def write_cad(design, path):
    import ezdxf
    from ezdxf import units

    cad = ezdxf.new("R2010", units=units.M)
    model = cad.modelspace()
    rings = {"CONTORNO_ORIGEM": design["outline"].exterior, "FUNDACAO_EXTERIOR": design["band"].exterior,
             "FUNDACAO_INTERIOR": design["band"].interiors[0]}
    for name, ring in rings.items():
        cad.layers.new(name)
        model.add_lwpolyline(list(ring.coords)[:-1], close=True, dxfattribs={"layer": name})
    for i, (a, b) in enumerate(design["edges"], 1):
        layer = f"EIXO_S{i:02d}"
        cad.layers.new(layer)
        model.add_line(a, b, dxfattribs={"layer": layer})
    model.add_text("PRE-DIMENSIONAMENTO A VALIDAR - NAO USAR EM OBRA").set_placement((0, -1.5))
    data = io.StringIO()
    cad.write(data)
    reopened = ezdxf.read(io.StringIO(data.getvalue())).modelspace()
    contours = {e.dxf.layer: list(e.get_points("xy")) for e in reopened.query("LWPOLYLINE") if e.closed}
    if set(contours) != set(rings) or not Polygon(contours['CONTORNO_ORIGEM']).equals(design["outline"]) or not Polygon(
        contours['FUNDACAO_EXTERIOR'], [contours['FUNDACAO_INTERIOR']]
    ).equals(design["band"]):
        raise ValueError("DXF com contornos diferentes do cálculo de sapatas.")
    axes = sorted(reopened.query("LINE"), key=lambda e: e.dxf.layer)
    if len(axes) != len(design["edges"]) or any(not LineString((line.dxf.start, line.dxf.end)).equals(LineString(edge))
                                               for line, edge in zip(axes, design["edges"])):
        raise ValueError("DXF com eixos diferentes do cálculo de sapatas.")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("F01_Sapatas_pre_dimensionamento.dxf", data.getvalue().encode("utf-8"))
