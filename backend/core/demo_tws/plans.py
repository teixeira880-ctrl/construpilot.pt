"""Gerador de plantas de execução para a empresa demo « Teste Websummit ».

Produz, a partir de uma geometria paramétrica coerente (mesmas dimensões em todas as folhas):
  - um PDF A3 multi-página « Projeto de execução » (arquitetura cotada, estrutura,
    eletricidade, canalização/drenagem, alçado principal, corte A-A), à escala indicada;
  - um DXF (metros) da planta de arquitetura com camadas e cotas, para a leitura CAD.

Nada é gerado por IA: é desenho vetorial determinístico.
"""
from __future__ import annotations

import io
from datetime import date

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

GREEN = (0.12, 0.42, 0.31)
COPPER = (0.72, 0.45, 0.23)
GREY = (0.45, 0.45, 0.45)

# --------------------------------------------------------------------------- geometrias
# Cada sala: (x, y, largura, profundidade, nome) em metros; origem no canto inferior esquerdo.
LAYOUTS = {
    "moradia": {
        "W": 16.0, "D": 11.0, "floors": 2, "floor_h": 3.0, "roof": "telhado", "title": "Moradia — piso térreo",
        "rooms": [
            (0, 0, 7, 6, "Sala comum"), (7, 0, 4.5, 6, "Cozinha"), (11.5, 0, 4.5, 3.4, "Escritório"),
            (11.5, 3.4, 4.5, 2.6, "Lavandaria"), (0, 6, 16, 1.4, "Circulação"), (0, 7.4, 5, 3.6, "Suite"),
            (5, 7.4, 2.4, 3.6, "WC suite"), (7.4, 7.4, 4, 3.6, "Quarto 2"), (11.4, 7.4, 2, 3.6, "WC"),
            (13.4, 7.4, 2.6, 3.6, "Quarto 3"),
        ],
    },
    "edificio": {
        "W": 20.0, "D": 13.0, "floors": 4, "floor_h": 2.9, "roof": "terraço", "title": "Edifício — piso tipo",
        "rooms": [
            (0, 0, 5.5, 5, "Sala A"), (5.5, 0, 3, 5, "Cozinha A"), (0, 5, 8.5, 1.2, "Corredor A"),
            (0, 6.2, 4, 6.8, "Quarto A1"), (4, 6.2, 2, 3, "WC A"), (4, 9.2, 2, 3.8, "Arrumos A"),
            (6, 6.2, 2.5, 6.8, "Quarto A2"),
            (8.5, 0, 3, 6.5, "Escada"), (8.5, 6.5, 3, 2.5, "Elevador"), (8.5, 9, 3, 4, "Patamar"),
            (11.5, 0, 3, 5, "Cozinha B"), (14.5, 0, 5.5, 5, "Sala B"), (11.5, 5, 8.5, 1.2, "Corredor B"),
            (11.5, 6.2, 2.5, 6.8, "Quarto B2"), (14, 6.2, 2, 3, "WC B"), (14, 9.2, 2, 3.8, "Arrumos B"),
            (16, 6.2, 4, 6.8, "Quarto B1"),
        ],
    },
    "hotel": {
        "W": 30.0, "D": 14.0, "floors": 4, "floor_h": 3.0, "roof": "terraço", "title": "Piso tipo — quartos",
        "rooms": [(i * 6, 0, 6, 6, f"Quarto {101 + i}") for i in range(5)]
        + [(0, 6, 30, 2, "Corredor")]
        + [(i * 6, 8, 6, 6, f"Quarto {106 + i}") for i in range(5)],
        "baths": True,
    },
    "apartamento": {
        "W": 12.0, "D": 9.2, "floors": 1, "floor_h": 3.2, "roof": "laje", "title": "Apartamento — planta",
        "rooms": [
            (0, 0, 6.5, 5, "Sala"), (6.5, 0, 3, 5, "Cozinha"), (9.5, 0, 2.5, 3, "Entrada"), (9.5, 3, 2.5, 2, "WC"),
            (0, 5, 12, 1.2, "Corredor"), (0, 6.2, 4.2, 3, "Quarto 1"), (4.2, 6.2, 2.6, 3, "Casa de banho"),
            (6.8, 6.2, 5.2, 3, "Quarto 2"),
        ],
    },
}

WET = ("WC", "Cozinha", "Lavandaria", "Casa de banho", "Quarto 1")  # Quarto só nos hotéis (casa de banho interior)
CIRC = ("Circulação", "Corredor", "Patamar", "Entrada", "Escada", "Elevador")

SHEETS = [
    ("EXE-01", "Planta de arquitetura cotada"),
    ("EXE-02", "Planta de estrutura — fundações, pilares e vigas"),
    ("EXE-03", "Planta de eletricidade e telecomunicações"),
    ("EXE-04", "Planta de canalização e drenagem"),
    ("EXE-05", "Alçado principal"),
    ("EXE-06", "Corte A-A"),
]


def _is_wet(name: str, baths: bool) -> bool:
    if baths and name.startswith("Quarto"):
        return True
    return any(name.startswith(w) for w in WET if w != "Quarto 1")


def _openings(layout: dict) -> tuple[list, list]:
    """Janelas nas fachadas exteriores e portas para a circulação."""
    W, D = layout["W"], layout["D"]
    windows, doors = [], []
    for x, y, w, h, name in layout["rooms"]:
        if name in CIRC:
            continue
        if y == 0:
            ln = min(1.8, w * 0.45)
            windows.append(((x + w / 2 - ln / 2, 0), (x + w / 2 + ln / 2, 0)))
        if abs(y + h - D) < 1e-6:
            ln = min(1.8, w * 0.45)
            windows.append(((x + w / 2 - ln / 2, D), (x + w / 2 + ln / 2, D)))
        # porta: lado virado para o centro do edifício
        dy = y + h if y + h <= D / 2 + 0.01 else y
        if 0 < dy < D:
            doors.append(((x + min(0.4, w * 0.2), dy), (x + min(0.4, w * 0.2) + 0.9, dy)))
    return windows, doors


def _grid(layout: dict) -> tuple[list[float], list[float]]:
    W, D = layout["W"], layout["D"]
    xs = sorted({0.0, W, *[round(r[0], 2) for r in layout["rooms"]]})
    ys = sorted({0.0, D, *[round(r[1], 2) for r in layout["rooms"]]})
    # pilares no máximo a cada ~6 m
    def thin(vals, total):
        out = [vals[0]]
        for v in vals[1:]:
            if v - out[-1] >= 2.9 or v == total:
                out.append(v)
        return out
    return thin(xs, W), thin(ys, D)


# --------------------------------------------------------------------------- PDF
class _Sheet:
    def __init__(self, c: canvas.Canvas, layout: dict, scale: int, height_m: float | None = None):
        self.c, self.L, self.scale = c, layout, scale
        pw, ph = landscape(A3)
        self.pw, self.ph = pw, ph
        k = 1000.0 / scale * mm  # pontos por metro
        self.k = k
        draw_w = layout["W"] * k
        self.ox = 25 * mm + (pw - 135 * mm - draw_w) / 2
        draw_h = (height_m if height_m is not None else layout["D"]) * k
        self.oy = max(40 * mm, (ph - draw_h) / 2 - 8 * mm)

    def P(self, x, y):
        return self.ox + x * self.k, self.oy + y * self.k

    def line(self, a, b, w=0.5, color=(0, 0, 0), dash=None):
        c = self.c
        c.setStrokeColorRGB(*color)
        c.setLineWidth(w)
        c.setDash(list(dash)) if dash else c.setDash()
        c.line(*self.P(*a), *self.P(*b))
        c.setDash()

    def rect(self, x, y, w, h, lw=0.5, color=(0, 0, 0), fill=None, dash=None):
        c = self.c
        c.setStrokeColorRGB(*color)
        c.setLineWidth(lw)
        c.setDash(list(dash)) if dash else c.setDash()
        if fill:
            c.setFillColorRGB(*fill)
        px, py = self.P(x, y)
        c.rect(px, py, w * self.k, h * self.k, stroke=1, fill=1 if fill else 0)
        c.setDash()

    def text(self, x, y, s, size=7, color=(0, 0, 0), center=True, font="Helvetica"):
        c = self.c
        c.setFillColorRGB(*color)
        c.setFont(font, size)
        px, py = self.P(x, y)
        (c.drawCentredString if center else c.drawString)(px, py, s)

    def circle(self, x, y, r_m, fill=None, color=(0, 0, 0)):
        c = self.c
        c.setStrokeColorRGB(*color)
        c.setLineWidth(0.5)
        if fill:
            c.setFillColorRGB(*fill)
        c.circle(*self.P(x, y), r_m * self.k, stroke=1, fill=1 if fill else 0)

    def dim_h(self, x1, x2, y, label=None):
        self.line((x1, y), (x2, y), 0.3, GREY)
        for x in (x1, x2):
            self.line((x, y - 0.15), (x, y + 0.15), 0.3, GREY)
        self.text((x1 + x2) / 2, y + 0.12, label or f"{x2 - x1:.2f}", 6, GREY)

    def dim_v(self, y1, y2, x, label=None):
        self.line((x, y1), (x, y2), 0.3, GREY)
        for y in (y1, y2):
            self.line((x - 0.15, y), (x + 0.15, y), 0.3, GREY)
        c = self.c
        c.saveState()
        px, py = self.P(x - 0.12, (y1 + y2) / 2)
        c.translate(px, py)
        c.rotate(90)
        c.setFont("Helvetica", 6)
        c.setFillColorRGB(*GREY)
        c.drawCentredString(0, 0, label or f"{y2 - y1:.2f}")
        c.restoreState()


def _walls(s: _Sheet, light: bool = False):
    L = s.L
    col = (0.55, 0.55, 0.55) if light else (0, 0, 0)
    s.rect(0, 0, L["W"], L["D"], lw=2.2 if not light else 1.2, color=col)
    for x, y, w, h, name in L["rooms"]:
        s.rect(x, y, w, h, lw=0.9 if not light else 0.4, color=col)
        if L.get("baths") and name.startswith("Quarto"):
            by = y + h - 2.6 if y > L["D"] / 2 else y + h - 2.6
            bx = x + w - 2.2
            s.rect(bx, by if y < L["D"] / 2 else y, 2.2, 2.6, lw=0.6 if not light else 0.3, color=col)


def _titleblock(c, pw, ph, meta, code, title, scale, page, total):
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1.2)
    c.rect(10 * mm, 10 * mm, pw - 20 * mm, ph - 20 * mm)
    x0 = pw - 125 * mm
    c.setLineWidth(0.8)
    c.rect(x0, 10 * mm, 115 * mm, 95 * mm)
    c.setFillColorRGB(*GREEN)
    c.rect(x0, 85 * mm, 115 * mm, 20 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(x0 + 5 * mm, 96 * mm, "TESTE WEBSUMMIT")
    c.setFont("Helvetica", 7.5)
    c.drawString(x0 + 5 * mm, 89.5 * mm, "Engenharia & Construção · PT · FR · UK · US")
    rows = [
        ("Obra", meta["site"]), ("Cliente", meta["client"]), ("Local", meta["place"]),
        ("Folha", f"{code} — {title}"), ("Escala", f"1:{scale}  (A3)"),
        ("Fase", "Projeto de execução"), ("Data", meta.get("date") or date.today().strftime("%d/%m/%Y")),
        ("Desenhou", "Inês Duarte, arq."), ("Verificou", "Pedro Almeida, eng."),
        ("Página", f"{page}/{total}"),
    ]
    c.setFillColorRGB(0, 0, 0)
    y = 80 * mm
    for k, v in rows:
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x0 + 4 * mm, y, k)
        c.setFont("Helvetica", 7)
        c.drawString(x0 + 24 * mm, y, (v or "")[:70])
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.3)
        c.line(x0, y - 2.2 * mm, x0 + 115 * mm, y - 2.2 * mm)
        y -= 6.8 * mm
    c.setFillColorRGB(*COPPER)
    c.setFont("Helvetica-Oblique", 6.5)
    c.drawString(x0 + 4 * mm, 12.5 * mm, "Documento de demonstração ConstruPilot — dados fictícios.")
    # título grande
    c.setFillColorRGB(*GREEN)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, ph - 24 * mm, f"{code} · {title}")
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, ph - 30 * mm, f"{meta['site']} — {meta['layout_title']}")


def _legend(c, pw, items):
    x0 = pw - 125 * mm
    y = 112 * mm
    c.setFont("Helvetica-Bold", 8)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(x0, y + len(items) * 5 * mm + 2 * mm, "Legenda")
    for color, label in items:
        c.setFillColorRGB(*color)
        c.rect(x0, y, 4 * mm, 3 * mm, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica", 7)
        c.drawString(x0 + 6 * mm, y + 0.6 * mm, label)
        y += 5 * mm


def _sheet_arch(s: _Sheet):
    L = s.L
    _walls(s)
    windows, doors = _openings(L)
    for a, b in windows:
        s.line(a, b, 3.2, (0.35, 0.6, 0.85))
    for a, b in doors:
        s.line(a, b, 3.2, (1, 1, 1))
        s.line(a, (a[0], a[1] + (0.9 if a[1] < L["D"] / 2 else -0.9)), 0.4, COPPER)
    for x, y, w, h, name in L["rooms"]:
        s.text(x + w / 2, y + h / 2 + 0.15, name, 7.5, (0.1, 0.1, 0.1), font="Helvetica-Bold")
        s.text(x + w / 2, y + h / 2 - 0.35, f"{w * h:.1f} m²", 6.5, GREY)
    # cotas gerais e parciais
    xs = sorted({r[0] for r in L["rooms"] if r[1] == 0} | {L["W"]})
    prev = 0.0
    for x in xs:
        if x > prev:
            s.dim_h(prev, x, -0.8)
        prev = x
    s.dim_h(0, L["W"], -1.6, f"{L['W']:.2f}")
    ys = sorted({r[1] for r in L["rooms"] if r[0] == 0} | {L["D"]})
    prev = 0.0
    for y in ys:
        if y > prev:
            s.dim_v(prev, y, -0.8)
        prev = y
    s.dim_v(0, L["D"], -1.6, f"{L['D']:.2f}")
    area = sum(r[2] * r[3] for r in L["rooms"])
    s.text(0, L["D"] + 1.0, f"Área bruta do piso: {L['W'] * L['D']:.1f} m²   ·   Área útil: {area:.1f} m²   ·   Pé-direito: {L['floor_h'] - 0.3:.2f} m",
           8, (0, 0, 0), center=False)
    # linha de corte A-A
    s.line((L["W"] * 0.62, -2.3), (L["W"] * 0.62, L["D"] + 0.6), 0.8, (0.8, 0.1, 0.1), dash=(6, 3))
    s.text(L["W"] * 0.62, -2.8, "A", 10, (0.8, 0.1, 0.1), font="Helvetica-Bold")
    s.text(L["W"] * 0.62, L["D"] + 0.8, "A", 10, (0.8, 0.1, 0.1), font="Helvetica-Bold")


def _sheet_struct(s: _Sheet):
    L = s.L
    _walls(s, light=True)
    xs, ys = _grid(L)
    n = 0
    for gx in xs:
        s.line((gx, -1.0), (gx, L["D"] + 1.0), 0.3, GREY, dash=(4, 2, 1, 2))
    for gy in ys:
        s.line((-1.0, gy), (L["W"] + 1.0, gy), 0.3, GREY, dash=(4, 2, 1, 2))
    for i, gx in enumerate(xs):
        s.text(gx, L["D"] + 1.4, chr(65 + i), 8, GREEN, font="Helvetica-Bold")
    for j, gy in enumerate(ys):
        s.text(-1.5, gy - 0.1, str(j + 1), 8, GREEN, font="Helvetica-Bold")
    for gy in ys:
        s.line((0, gy), (L["W"], gy), 2.0, (0.55, 0.3, 0.15))
    for gx in xs:
        s.line((gx, 0), (gx, L["D"]), 2.0, (0.55, 0.3, 0.15))
    for gx in xs:
        for gy in ys:
            n += 1
            s.rect(gx - 0.8, gy - 0.8, 1.6, 1.6, lw=0.4, color=GREY, dash=(3, 2))
            s.rect(gx - 0.15, gy - 0.15, 0.3, 0.3, lw=0.6, fill=(0.1, 0.1, 0.1))
            s.text(gx + 0.55, gy + 0.25, f"P{n}", 5.5, (0.1, 0.1, 0.1))
    s.text(0, L["D"] + 2.2,
           f"Pilares P1-P{n}: 0,30×0,30 m C30/37 · Vigas V: 0,25×0,50 m · Sapatas S: 1,60×1,60×0,60 m C25/30 · Laje e=0,25 m · Aço A500 NR",
           7.5, (0, 0, 0), center=False)


def _sheet_elec(s: _Sheet):
    L = s.L
    _walls(s, light=True)
    windows, doors = _openings(L)
    for x, y, w, h, name in L["rooms"]:
        s.circle(x + w / 2, y + h / 2, 0.22, color=(0.85, 0.65, 0.0))
        s.line((x + w / 2 - 0.16, y + h / 2 - 0.16), (x + w / 2 + 0.16, y + h / 2 + 0.16), 0.5, (0.85, 0.65, 0.0))
        s.line((x + w / 2 - 0.16, y + h / 2 + 0.16), (x + w / 2 + 0.16, y + h / 2 - 0.16), 0.5, (0.85, 0.65, 0.0))
        if name in CIRC:
            continue
        for px, py in ((x + 0.35, y + h / 2), (x + w - 0.35, y + h / 2), (x + w / 2, y + 0.35 if y > 0 else y + h - 0.35)):
            s.rect(px - 0.14, py - 0.1, 0.28, 0.2, lw=0.5, color=(0.15, 0.35, 0.8), fill=(0.75, 0.85, 1))
    for a, _ in doors:
        s.circle(a[0] - 0.25, a[1] + (0.3 if a[1] < L["D"] / 2 else -0.3), 0.1, fill=(0.2, 0.2, 0.2))
    circ = next((r for r in L["rooms"] if r[4] in CIRC), L["rooms"][0])
    qx, qy = circ[0] + 0.6, circ[1] + circ[3] / 2
    s.rect(qx - 0.35, qy - 0.25, 0.7, 0.5, lw=0.8, fill=(0.85, 0.2, 0.2))
    s.text(qx, qy - 0.65, "Q.E.", 6.5, (0.85, 0.2, 0.2), font="Helvetica-Bold")
    for x, y, w, h, name in L["rooms"]:
        s.line((qx, qy), (x + w / 2, qy), 0.4, (0.85, 0.65, 0.0), dash=(2, 2))
        s.line((x + w / 2, qy), (x + w / 2, y + h / 2), 0.4, (0.85, 0.65, 0.0), dash=(2, 2))
    s.text(0, L["D"] + 1.0, "Circuitos: C1 iluminação (1,5 mm²) · C2-C4 tomadas (2,5 mm²) · C5 cozinha (6 mm²) · "
           "Diferenciais 30 mA · ITED: ATI no Q.E.", 7.5, (0, 0, 0), center=False)


def _sheet_plumb(s: _Sheet):
    L = s.L
    _walls(s, light=True)
    riser = (L["W"] / 2, L["D"] / 2)
    s.rect(riser[0] - 0.3, riser[1] - 0.3, 0.6, 0.6, lw=1, color=(0.1, 0.3, 0.7))
    s.text(riser[0], riser[1] - 0.8, "Coluna montante / tubo de queda", 6, (0.1, 0.3, 0.7))
    baths = L.get("baths")
    for x, y, w, h, name in L["rooms"]:
        if not _is_wet(name, baths):
            continue
        fx, fy = x + w - 1.0, y + (h - 1.0 if y > L["D"] / 2 else 1.0)
        s.circle(fx, fy, 0.25, color=(0.1, 0.3, 0.7), fill=(0.85, 0.92, 1))
        s.rect(fx - 0.9, fy - 0.2, 0.5, 0.4, lw=0.5, color=(0.1, 0.3, 0.7))
        # água fria (azul), quente (vermelho), esgoto (castanho tracejado)
        s.line(riser, (fx, riser[1]), 0.9, (0.1, 0.4, 0.9))
        s.line((fx, riser[1]), (fx, fy), 0.9, (0.1, 0.4, 0.9))
        s.line((riser[0], riser[1] + 0.15), (fx + 0.15, riser[1] + 0.15), 0.9, (0.85, 0.15, 0.15))
        s.line((fx + 0.15, riser[1] + 0.15), (fx + 0.15, fy), 0.9, (0.85, 0.15, 0.15))
        s.line((fx - 0.15, fy), (fx - 0.15, riser[1] - 0.15), 1.4, (0.45, 0.3, 0.15), dash=(4, 2))
        s.line((fx - 0.15, riser[1] - 0.15), riser, 1.4, (0.45, 0.3, 0.15), dash=(4, 2))
    s.text(0, L["D"] + 1.0, "Abastecimento PEX multicamada Ø16-26 · Esgotos PVC Ø40-110, inclinação mínima 1 % · "
           "Ventilação primária na cobertura", 7.5, (0, 0, 0), center=False)


def _sheet_elev(s: _Sheet):
    L = s.L
    H = L["floors"] * L["floor_h"]
    s.rect(0, 0, L["W"], H, lw=1.6, fill=(0.96, 0.94, 0.9))
    for f in range(1, L["floors"]):
        s.line((0, f * L["floor_h"]), (L["W"], f * L["floor_h"]), 0.4, GREY, dash=(3, 2))
    windows, _ = _openings(L)
    front = [w for w in windows if w[0][1] == 0]
    for f in range(L["floors"]):
        for a, b in front:
            wy = f * L["floor_h"] + 0.9
            s.rect(a[0], wy, b[0] - a[0], 1.4, lw=0.8, color=(0.2, 0.35, 0.55), fill=(0.75, 0.86, 0.95))
    if L["roof"] == "telhado":
        c = s.c
        c.setStrokeColorRGB(0.55, 0.25, 0.15)
        c.setFillColorRGB(0.72, 0.38, 0.25)
        p = c.beginPath()
        p.moveTo(*s.P(-0.4, H))
        p.lineTo(*s.P(L["W"] / 2, H + 2.6))
        p.lineTo(*s.P(L["W"] + 0.4, H))
        p.close()
        c.drawPath(p, fill=1, stroke=1)
    else:
        s.rect(-0.2, H, L["W"] + 0.4, 0.4, lw=0.8, fill=(0.8, 0.8, 0.8))
    s.line((-2, 0), (L["W"] + 2, 0), 1.2, (0.3, 0.2, 0.1))
    for f in range(L["floors"] + 1):
        s.text(L["W"] + 1.6, f * L["floor_h"] - 0.1, f"+{f * L['floor_h']:.2f}", 7, GREEN, center=False)
    s.text(L["W"] / 2, -1.2, "Revestimento: ETICS acabamento acrílico areado · Caixilharia alumínio RPT antracite", 7.5)


def _sheet_section(s: _Sheet):
    L = s.L
    D = L["D"]
    for f in range(L["floors"] + 1):
        y = f * L["floor_h"]
        s.rect(0, y - 0.25 if f else -0.25, D, 0.25, lw=0.6, fill=(0.7, 0.7, 0.7))
    s.rect(-0.3, 0, 0.3, L["floors"] * L["floor_h"], lw=0.8, fill=(0.85, 0.82, 0.78))
    s.rect(D, 0, 0.3, L["floors"] * L["floor_h"], lw=0.8, fill=(0.85, 0.82, 0.78))
    for xf in (0.5, D / 2, D - 0.5):
        s.rect(xf - 0.8, -1.25, 1.6, 0.6, lw=0.6, fill=(0.6, 0.6, 0.6))
        s.line((xf, -0.65), (xf, -0.25), 2.0, (0.4, 0.4, 0.4))
    s.line((-2, 0), (D + 2, 0), 1.2, (0.3, 0.2, 0.1))
    for f in range(L["floors"]):
        s.dim_v(f * L["floor_h"], (f + 1) * L["floor_h"] - 0.25, D + 1.2, f"{L['floor_h'] - 0.25:.2f}")
    s.dim_h(0, D, -2.0, f"{D:.2f}")
    s.text(D / 2, L["floors"] * L["floor_h"] + 0.8, f"Cobertura em {L['roof']} · Isolamento XPS 80 mm", 7.5)


def build_execution_pdf(kind: str, meta: dict) -> bytes:
    L = LAYOUTS[kind]
    meta = {**meta, "layout_title": L["title"]}
    scale = 100 if L["W"] <= 22 else 150
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A3))
    c.setTitle(f"Projeto de execução — {meta['site']}")
    c.setAuthor("Teste Websummit")
    pw, ph = landscape(A3)
    drawers = [_sheet_arch, _sheet_struct, _sheet_elec, _sheet_plumb, _sheet_elev, _sheet_section]
    legends = [
        [((0.35, 0.6, 0.85), "Janela"), (COPPER, "Porta (abertura)"), ((0.8, 0.1, 0.1), "Linha de corte")],
        [((0.1, 0.1, 0.1), "Pilar 0,30×0,30"), ((0.55, 0.3, 0.15), "Viga 0,25×0,50"), (GREY, "Sapata (tracejado)")],
        [((0.85, 0.65, 0.0), "Ponto de luz / circuito"), ((0.15, 0.35, 0.8), "Tomada"), ((0.85, 0.2, 0.2), "Quadro elétrico")],
        [((0.1, 0.4, 0.9), "Água fria"), ((0.85, 0.15, 0.15), "Água quente"), ((0.45, 0.3, 0.15), "Esgoto")],
        [((0.75, 0.86, 0.95), "Vãos envidraçados"), ((0.96, 0.94, 0.9), "Fachada ETICS")],
        [((0.7, 0.7, 0.7), "Lajes"), ((0.6, 0.6, 0.6), "Fundações")],
    ]
    for i, ((code, title), draw) in enumerate(zip(SHEETS, drawers)):
        sc = scale if i < 4 else (100 if max(L["W"], L["floors"] * L["floor_h"]) <= 22 else 150)
        h_m = L["floors"] * L["floor_h"] + 2.6 if i == 4 else (L["floors"] * L["floor_h"] if i == 5 else None)
        s = _Sheet(c, L, sc, h_m)
        draw(s)
        _legend(c, pw, legends[i])
        _titleblock(c, pw, ph, meta, code, title, sc, i + 1, len(SHEETS))
        c.showPage()
    c.save()
    return buf.getvalue()


def build_architecture_dxf(kind: str, meta: dict) -> bytes:
    """Planta de arquitetura em DXF (unidades: metros) com camadas e cotas."""
    import ezdxf
    from ezdxf import units

    L = LAYOUTS[kind]
    doc = ezdxf.new("R2010", setup=True)
    doc.units = units.M
    for name, color in (("PAREDES", 7), ("JANELAS", 5), ("PORTAS", 30), ("TEXTO", 3), ("COTAS", 8), ("ESTRUTURA", 1)):
        doc.layers.add(name, color=color)
    msp = doc.modelspace()
    W, D = L["W"], L["D"]
    msp.add_lwpolyline([(0, 0), (W, 0), (W, D), (0, D)], close=True, dxfattribs={"layer": "PAREDES", "const_width": 0.25})
    for x, y, w, h, name in L["rooms"]:
        msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True,
                           dxfattribs={"layer": "PAREDES", "const_width": 0.11})
        msp.add_text(name, height=0.25, dxfattribs={"layer": "TEXTO"}).set_placement((x + w / 2, y + h / 2 + 0.1),
                                                                                     align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
        msp.add_text(f"{w * h:.1f} m2", height=0.18, dxfattribs={"layer": "TEXTO"}).set_placement(
            (x + w / 2, y + h / 2 - 0.35), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    windows, doors = _openings(L)
    for a, b in windows:
        msp.add_line(a, b, dxfattribs={"layer": "JANELAS"})
    for a, b in doors:
        msp.add_line(a, b, dxfattribs={"layer": "PORTAS"})
    xs, ys = _grid(L)
    for gx in xs:
        for gy in ys:
            msp.add_lwpolyline([(gx - 0.15, gy - 0.15), (gx + 0.15, gy - 0.15), (gx + 0.15, gy + 0.15), (gx - 0.15, gy + 0.15)],
                               close=True, dxfattribs={"layer": "ESTRUTURA"})
    msp.add_linear_dim(base=(0, -1.5), p1=(0, 0), p2=(W, 0), dimstyle="EZDXF", dxfattribs={"layer": "COTAS"}).render()
    msp.add_linear_dim(base=(-1.5, 0), p1=(0, 0), p2=(0, D), angle=90, dimstyle="EZDXF",
                       dxfattribs={"layer": "COTAS"}).render()
    msp.add_text(f"{meta['site']} — Planta de arquitetura (Teste Websummit, demo)", height=0.35,
                 dxfattribs={"layer": "TEXTO"}).set_placement((0, D + 1.2))
    out = io.StringIO()
    doc.write(out)
    return out.getvalue().encode("utf-8")


def mep_input(kind: str, country: str, name: str, levels: int = 1) -> dict:
    """Entrada do motor MEP (engines.mep) a partir da mesma geometria das plantas de execução."""
    L = LAYOUTS[kind]
    windows, doors = _openings(L)
    out = []
    for i in range(levels):
        out.append({
            "id": f"N{i}", "name": "Piso 0" if i == 0 else f"Piso {i}",
            "elevation_m": i * L["floor_h"], "height_m": L["floor_h"] - 0.3,
            "rooms": [{"name": n, "polygon": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]}
                      for x, y, w, h, n in L["rooms"]],
            "openings": [{"kind": "fenetre", "a": list(a), "b": list(b)} for a, b in windows]
            + [{"kind": "porte", "a": list(a), "b": list(b)} for a, b in doors],
        })
    return {"country": country, "project": {"name": name}, "levels": out}
