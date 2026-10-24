"""Editor de volumes — planta de implantação, corte, alçado e axonometria a partir de dimensões simples.

Geometria 100 % determinística, em metros. Convenção: origem no canto frente-esquerda do terreno,
x → ao longo da frente (via pública), y → para o tardoz. O terreno é um retângulo
`plot_l_m` (frente) × `plot_w_m` (profundidade).

Os desenhos são ESQUEMÁTICOS: servem de base às peças desenhadas (planta de implantação, cortes,
alçados) e têm de ser verificados, cotados e assinados por técnico habilitado antes da submissão.
Sem fundo cadastral automático: em Portugal não há serviço cadastral gratuito e universal
equivalente ao francês; a planta de localização é carregada pelo utilizador.
"""
from __future__ import annotations

import io
import math
import os

from PIL import Image, ImageDraw, ImageFont

GREEN = (31, 79, 150)   # cobalto (identidade .pt)
INK = (31, 41, 51)
RED = (190, 40, 40)
GREY = (130, 136, 140)
SKY = (228, 238, 246)
GROUND = (210, 198, 176)
BUILD = (214, 236, 230)
ANNEX = (240, 150, 100)
ROOF = (198, 112, 86)
WATER = (120, 190, 225)

_HERE = os.path.dirname(os.path.abspath(__file__))
_FONT_PATHS = [
    os.path.join(_HERE, "..", "..", "assets", "fonts", "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]
_FONT_CACHE: dict = {}

FOOTER = "Desenho esquemático gerado pelo ConstruPilot — a verificar, cotar e assinar por técnico habilitado antes da submissão."

ROOF_TYPES = {"duas_aguas": "Duas águas", "uma_agua": "Uma água", "plana": "Cobertura plana"}
# Compatibilidade com dados no formato do módulo francês.
_ROOF_ALIASES = {"deux_pentes": "duas_aguas", "monopente": "uma_agua", "toit_plat": "plana"}


def _font(sz: int):
    if sz in _FONT_CACHE:
        return _FONT_CACHE[sz]
    f = None
    for p in _FONT_PATHS:
        try:
            f = ImageFont.truetype(p, sz)
            break
        except Exception:  # noqa: BLE001
            continue
    _FONT_CACHE[sz] = f or ImageFont.load_default()
    return _FONT_CACHE[sz]


def _num(v, d=0.0):
    try:
        if v is None or v == "":
            return d
        return float(v)
    except (TypeError, ValueError):
        return d


def fmt(v, nd=2) -> str:
    """Número em formato português (vírgula decimal)."""
    try:
        return f"{float(v):.{nd}f}".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


def roof_type(volume: dict) -> str:
    r = (volume or {}).get("roof_type") or "duas_aguas"
    r = _ROOF_ALIASES.get(r, r)
    return r if r in ROOF_TYPES else "duas_aguas"


def _png(img) -> bytes:
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _header(dr, w, title):
    dr.rectangle([0, 0, w, 36], fill=(15, 43, 87))
    dr.text((12, 9), title, fill=(255, 255, 255), font=_font(16))


def _footer(dr, w, h, extra=""):
    dr.text((12, h - 34), FOOTER, fill=GREY, font=_font(11))
    if extra:
        dr.text((12, h - 18), extra, fill=GREY, font=_font(11))


def _north(dr, x, y):
    dr.line([x, y + 10, x, y + 46], fill=INK, width=3)
    dr.polygon([(x - 7, y + 20), (x + 7, y + 20), (x, y + 4)], fill=INK)
    dr.text((x - 6, y + 48), "N", fill=INK, font=_font(13))
    dr.text((x - 30, y + 64), "(indicativo)", fill=GREY, font=_font(10))


def _dash_line(dr, a, b, color, dash=8, gap=5, width=2):
    (x1, y1), (x2, y2) = a, b
    seg = math.hypot(x2 - x1, y2 - y1)
    if seg < 1e-6:
        return
    n = int(seg // (dash + gap)) + 1
    for i in range(n):
        t0 = (i * (dash + gap)) / seg
        t1 = min(1.0, (i * (dash + gap) + dash) / seg)
        if t0 >= 1:
            break
        dr.line([(x1 + (x2 - x1) * t0, y1 + (y2 - y1) * t0), (x1 + (x2 - x1) * t1, y1 + (y2 - y1) * t1)],
                fill=color, width=width)


def _arrow_head(dr, tip, frm, color, size=7):
    ang = math.atan2(tip[1] - frm[1], tip[0] - frm[0])
    for s in (-1, 1):
        a = ang + math.pi - s * 0.4
        dr.line([tip, (tip[0] + size * math.cos(a), tip[1] + size * math.sin(a))], fill=color, width=2)


def _cota(dr, a, b, label, color=RED, offset=(4, -16)):
    """Linha de cota com setas nas duas extremidades e texto ao centro."""
    if math.hypot(b[0] - a[0], b[1] - a[1]) < 2:
        return
    dr.line([a, b], fill=color, width=2)
    _arrow_head(dr, a, b, color)
    _arrow_head(dr, b, a, color)
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dr.text((mx + offset[0], my + offset[1]), label, fill=color, font=_font(12))


# ---------------------------------------------------------------- geometria da construção ----
def building_polygons(volume: dict) -> list[dict]:
    """Contorno(s) da construção em metros (origem canto frente-esquerda do terreno).

    Formas: retângulo, L ou T, e volumes anexos (`blocks`). Cada polígono:
    {"pts": [(x, y)...], "name": str, "annexe": bool, "h_m": float | None}.
    """
    v = volume or {}
    L = max(1.0, _num(v.get("footprint_l_m"), 8))
    W = max(1.0, _num(v.get("footprint_w_m"), 6))
    ss = max(0.0, _num(v.get("setback_side_m"), 3))
    sf = max(0.0, _num(v.get("setback_front_m"), 5))
    shape = (v.get("shape") or "rectangle").lower()
    x0, y0 = ss, sf
    polys: list[dict] = []
    if shape == "l":
        wl = _num(v.get("wing_l_m"), 0) or L * 0.45
        wh = _num(v.get("wing_w_m"), 0) or W * 0.45
        wl = min(max(wl, 0.5), L - 0.5)
        wh = min(max(wh, 0.5), W - 0.5)
        pts = [(x0, y0), (x0 + L, y0), (x0 + L, y0 + W - wh),
               (x0 + L - wl, y0 + W - wh), (x0 + L - wl, y0 + W), (x0, y0 + W)]
        polys.append({"pts": pts, "name": "Construção (L)", "annexe": False, "h_m": None})
    elif shape == "t":
        td = _num(v.get("wing_w_m"), 0) or W * 0.45   # profundidade da barra (no tardoz)
        sw = _num(v.get("wing_l_m"), 0) or L * 0.4    # largura do corpo central
        td = min(max(td, 0.5), W - 0.5)
        sw = min(max(sw, 0.5), L - 0.5)
        bar = [(x0, y0 + W - td), (x0 + L, y0 + W - td), (x0 + L, y0 + W), (x0, y0 + W)]
        sx = x0 + (L - sw) / 2
        stem = [(sx, y0), (sx + sw, y0), (sx + sw, y0 + W - td), (sx, y0 + W - td)]
        polys.append({"pts": bar, "name": "Construção (T)", "annexe": False, "h_m": None})
        polys.append({"pts": stem, "name": "", "annexe": False, "h_m": None})
    else:
        polys.append({"pts": [(x0, y0), (x0 + L, y0), (x0 + L, y0 + W), (x0, y0 + W)],
                      "name": "Construção", "annexe": False, "h_m": None})
    for b in (v.get("blocks") or [])[:6]:
        bl = max(0.5, _num(b.get("l_m"), 4))
        bw = max(0.5, _num(b.get("w_m"), 3))
        bx = _num(b.get("x_m"), x0)
        by = _num(b.get("y_m"), y0)
        hb = _num(b.get("h_m"), 0) or None
        polys.append({"pts": [(bx, by), (bx + bl, by), (bx + bl, by + bw), (bx, by + bw)],
                      "name": b.get("name") or "Anexo", "annexe": True, "h_m": hb})
    return polys


def main_rects(volume: dict) -> list[tuple]:
    """Decomposição da construção principal em retângulos (x0, y0, x1, y1) — usada para as coberturas."""
    rects = []
    for p in building_polygons(volume):
        if p["annexe"]:
            continue
        pts = p["pts"]
        if len(pts) == 4:
            xs, ys = [x for x, _ in pts], [y for _, y in pts]
            rects.append((min(xs), min(ys), max(xs), max(ys)))
        else:  # L: corpo à frente (largura total) + ala no tardoz
            (xa, ya), (xb, _), (_, yc), (xd, _), _, (_, yf) = pts
            rects.append((xa, ya, xb, yc))
            rects.append((xa, yc, xd, yf))
    return rects


def _shoelace(pts) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def union_area(polys: list[dict]) -> float:
    """Área da união dos polígonos (sobreposições contadas uma só vez)."""
    if not polys:
        return 0.0
    try:
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        return float(unary_union([Polygon(p["pts"]) for p in polys]).area)
    except Exception:  # noqa: BLE001 — sem shapely: soma simples
        return sum(_shoelace(p["pts"]) for p in polys)


def bbox(polys: list[dict]):
    xs = [x for p in polys for x, _ in p["pts"]]
    ys = [y for p in polys for _, y in p["pts"]]
    if not xs:
        return 0.0, 0.0, 0.0, 0.0
    return min(xs), min(ys), max(xs), max(ys)


def heights(volume: dict) -> dict:
    """Alturas: piso a piso, altura da fachada (até ao beirado/platibanda) e altura total (cumeeira)."""
    v = volume or {}
    levels = max(1, int(_num(v.get("levels"), 1)))
    sh = max(0.5, _num(v.get("storey_h_m"), 2.8))
    wall_h = levels * sh
    rt = roof_type(v)
    total = _num(v.get("total_h_m"), 0)
    if total <= 0:
        total = wall_h + (0.0 if rt == "plana" else 2.0)
    total = max(total, wall_h)
    return {"levels": levels, "storey_h_m": sh, "altura_fachada_m": round(wall_h, 2),
            "altura_total_m": round(total, 2), "roof_h_m": round(total - wall_h, 2), "roof_type": rt}


# ---------------------------------------------------------------- planta de implantação ----
def planta_implantacao(volume: dict, terreno: dict | None = None, quadro: dict | None = None) -> bytes:
    v = volume or {}
    plot_l = max(1.0, _num(v.get("plot_l_m"), 20))
    plot_w = max(1.0, _num(v.get("plot_w_m"), 15))
    polys = building_polygons(v)
    W, H = 1000, 860
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img, "RGBA")
    _header(dr, W, "Planta de implantação (esquemática)")
    ox, oy, draww, drawh = 110, 90, 700, 470
    scale = min(draww / plot_l, drawh / plot_w)
    pw, ph = plot_l * scale, plot_w * scale

    def m2px(xm, ym):
        return ox + xm * scale, oy + ph - ym * scale

    # terreno + via pública (frente = y 0, em baixo)
    dr.rectangle([ox, oy, ox + pw, oy + ph], outline=INK, width=3, fill=(247, 250, 246))
    dr.rectangle([ox - 30, oy + ph + 30, ox + pw + 30, oy + ph + 62], fill=(225, 226, 232))
    dr.text((ox + 8, oy + ph + 38), "Via pública (frente do terreno)", fill=(90, 90, 100), font=_font(12))
    dr.text((ox + pw / 2 - 60, oy + ph + 8), f"Frente: {fmt(plot_l)} m", fill=INK, font=_font(13))
    dr.text((ox - 100, oy + ph / 2 - 8), f"{fmt(plot_w)} m", fill=INK, font=_font(13))
    dr.text((ox + 6, oy + 6), "Limite do terreno", fill=GREY, font=_font(11))

    for p in polys:
        pp = [m2px(x, y) for x, y in p["pts"]]
        fill = (ANNEX + (170,)) if p["annexe"] else (BUILD + (235,))
        dr.polygon(pp, fill=fill)
        dr.line(pp + [pp[0]], fill=RED if p["annexe"] else GREEN, width=3)
        if p["name"]:
            cx = sum(x for x, _ in pp) / len(pp)
            cy = sum(y for _, y in pp) / len(pp)
            dr.text((cx - 34, cy - 7), p["name"], fill=INK, font=_font(12))

    main = [p for p in polys if not p["annexe"]]
    mnx, mny, mxx, mxy = bbox(main)
    # cotas de afastamento (construção principal → limites)
    cx_m, cy_m = (mnx + mxx) / 2, (mny + mxy) / 2
    _cota(dr, m2px(cx_m, 0), m2px(cx_m, mny), f"{fmt(mny)} m", offset=(6, -8))
    _cota(dr, m2px(cx_m, mxy), m2px(cx_m, plot_w), f"{fmt(plot_w - mxy)} m", offset=(6, -8))
    _cota(dr, m2px(0, cy_m), m2px(mnx, cy_m), f"{fmt(mnx)} m", offset=(-22, -18))
    _cota(dr, m2px(mxx, cy_m), m2px(plot_l, cy_m), f"{fmt(plot_l - mxx)} m", offset=(-22, -18))
    # dimensões da construção
    a, b = m2px(mnx, mxy), m2px(mxx, mxy)
    _cota(dr, (a[0], a[1] - 14), (b[0], b[1] - 14), f"{fmt(mxx - mnx)} m", color=GREEN, offset=(-24, -18))

    _north(dr, W - 70, 50)
    # escala gráfica 5 m
    sb = 5 * scale
    dr.rectangle([ox, oy + ph + 78, ox + sb, oy + ph + 84], fill=INK)
    dr.text((ox, oy + ph + 88), "0", fill=INK, font=_font(11))
    dr.text((ox + sb - 14, oy + ph + 88), "5 m", fill=INK, font=_font(11))

    q = quadro or {}
    info = []
    if q:
        info.append(f"Área do terreno: {fmt(q.get('area_terreno_m2'))} m²   ·   Área de implantação: {fmt(q.get('area_implantacao_m2'))} m²")
        info.append(f"Área de construção: {fmt(q.get('area_construcao_m2'))} m²   ·   Índice de ocupação: {fmt(q.get('indice_ocupacao_pct'), 1)} %"
                    f"   ·   Índice de utilização: {fmt(q.get('indice_utilizacao'), 2)}")
    else:
        info.append(f"Área de implantação: {fmt(union_area(polys))} m²")
    ter = terreno or {}
    if ter.get("artigo_matricial") or ter.get("descricao_predial"):
        info.append(f"Artigo matricial: {ter.get('artigo_matricial') or '—'}   ·   Descrição predial: {ter.get('descricao_predial') or '—'}")
    yy = oy + ph + 108
    for t in info:
        dr.text((ox, yy), t, fill=INK, font=_font(13))
        yy += 22
    # legenda
    lx, ly = W - 175, 160
    dr.rectangle([lx, ly, lx + 18, ly + 12], fill=BUILD, outline=GREEN)
    dr.text((lx + 24, ly - 1), "Construção", fill=INK, font=_font(11))
    dr.rectangle([lx, ly + 22, lx + 18, ly + 34], fill=ANNEX, outline=RED)
    dr.text((lx + 24, ly + 21), "Anexo", fill=INK, font=_font(11))
    dr.line([lx, ly + 50, lx + 18, ly + 50], fill=RED, width=2)
    dr.text((lx + 24, ly + 43), "Afastamento", fill=INK, font=_font(11))
    _footer(dr, W, H, "Terreno representado como retângulo — a substituir pelo levantamento topográfico.")
    return _png(img)


# ---------------------------------------------------------------- corte ----
def _floor_label(i: int) -> str:
    return "R/C" if i == 0 else f"{i}.º piso"


def corte(volume: dict) -> bytes:
    """Corte transversal A-A (perpendicular à frente): pisos, lajes, cobertura e cotas de altura."""
    v = volume or {}
    hh = heights(v)
    levels, sh, wall_h, total_h, rt = hh["levels"], hh["storey_h_m"], hh["altura_fachada_m"], hh["altura_total_m"], hh["roof_type"]
    slab = min(max(_num(v.get("espessura_laje_m"), 0.30), 0.0), sh - 0.5)
    main = [p for p in building_polygons(v) if not p["annexe"]]
    mnx, mny, mxx, mxy = bbox(main)
    depth = max(mxy - mny, 1.0)
    W, H = 1000, 720
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    _header(dr, W, "Corte transversal A-A (esquemático)")
    gx, gy, gw = 170, 560, 620
    scale = min(gw / depth, 420 / max(total_h, 1))
    bw = depth * scale
    bx = gx + (gw - bw) / 2
    dr.rectangle([gx - 80, 52, gx + gw + 80, gy], fill=SKY)
    dr.rectangle([gx - 80, gy, gx + gw + 80, gy + 46], fill=GROUND)
    dr.line([gx - 80, gy, gx + gw + 80, gy], fill=INK, width=2)
    dr.text((gx - 76, gy + 6), "Frente / via pública", fill=(90, 80, 60), font=_font(11))
    dr.text((gx + gw - 20, gy + 6), "Tardoz", fill=(90, 80, 60), font=_font(11))
    dr.text((bx - 4, gy + 22), "Cota de soleira ±0,00", fill=INK, font=_font(11))
    wall_px = wall_h * scale
    dr.rectangle([bx, gy - wall_px, bx + bw, gy], outline=INK, width=3, fill=(246, 242, 234))
    for i in range(levels):
        y_floor = gy - i * sh * scale
        if i > 0:
            dr.rectangle([bx, y_floor - slab * scale, bx + bw, y_floor], fill=(170, 170, 175))
        dr.text((bx + 6, y_floor - (slab * scale if i > 0 else 0) - 18), _floor_label(i), fill=GREY, font=_font(11))
    # laje de cobertura / teto do último piso
    dr.rectangle([bx, gy - wall_px, bx + bw, gy - wall_px + max(2, slab * scale)], fill=(170, 170, 175))
    roof_px = (total_h - wall_h) * scale
    top = gy - wall_px
    if rt == "plana":
        dr.rectangle([bx - 4, top - 10, bx + bw + 4, top], fill=INK)
    elif rt == "uma_agua":
        dr.polygon([(bx, top), (bx + bw, top), (bx + bw, top - roof_px)], outline=INK, fill=ROOF)
    else:
        dr.polygon([(bx - 10, top + 4), (bx + bw + 10, top + 4), (bx + bw / 2, top - roof_px)], outline=INK, fill=ROOF)
    # cotas: piso a piso + pé-direito livre (esquerda), altura da fachada e total (direita)
    _cota(dr, (bx - 30, gy), (bx - 30, gy - sh * scale), f"{fmt(sh)} m", offset=(-80, -8))
    dr.text((bx - 150, gy - sh * scale / 2 + 10), "piso a piso", fill=RED, font=_font(10))
    pdl = sh - slab
    if levels > 1 or slab > 0:
        y1 = gy - sh * scale + slab * scale
        _cota(dr, (bx + bw * 0.25, gy), (bx + bw * 0.25, y1), f"p.d. livre {fmt(pdl)} m", color=GREEN, offset=(6, -8))
    _cota(dr, (bx + bw + 30, gy), (bx + bw + 30, gy - wall_px), f"{fmt(wall_h)} m", offset=(8, -8))
    dr.text((bx + bw + 38, gy - wall_px / 2 + 10), "altura da fachada", fill=RED, font=_font(10))
    if total_h > wall_h + 0.01:
        _cota(dr, (bx + bw + 120, gy), (bx + bw + 120, gy - total_h * scale), f"{fmt(total_h)} m", offset=(8, -8))
        dr.text((bx + bw + 128, gy - total_h * scale / 2 + 10), "altura total", fill=RED, font=_font(10))
    dr.text((gx - 76, gy + 54),
            f"Profundidade {fmt(depth)} m · {levels} piso(s) acima do solo · laje + revestimentos {fmt(slab)} m (valor de cálculo editável) · {ROOF_TYPES[rt]}",
            fill=INK, font=_font(12))
    _footer(dr, W, H)
    return _png(img)


# ---------------------------------------------------------------- alçado principal ----
def alcado(volume: dict) -> bytes:
    """Alçado principal (frente): envolvente da construção e anexos, com cotas de altura."""
    v = volume or {}
    hh = heights(v)
    wall_h, total_h, rt, sh = hh["altura_fachada_m"], hh["altura_total_m"], hh["roof_type"], hh["storey_h_m"]
    plot_l = max(1.0, _num(v.get("plot_l_m"), 20))
    polys = building_polygons(v)
    main = [p for p in polys if not p["annexe"]]
    mnx, _, mxx, _ = bbox(main)
    W, H = 1000, 640
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    _header(dr, W, "Alçado principal (esquemático)")
    gx, gy, gw = 110, 500, 760
    scale = min(gw / plot_l, 380 / max(total_h, 1))

    def X(xm):
        return gx + xm * scale

    dr.rectangle([gx - 20, 52, gx + gw + 20, gy], fill=SKY)
    dr.rectangle([gx - 20, gy, gx + gw + 20, gy + 30], fill=GROUND)
    dr.line([gx - 20, gy, gx + gw + 20, gy], fill=INK, width=2)
    dr.line([X(0), gy - 6, X(0), gy + 6], fill=INK, width=2)
    dr.line([X(plot_l), gy - 6, X(plot_l), gy + 6], fill=INK, width=2)
    dr.text((X(0) + 2, gy + 8), "limite", fill=GREY, font=_font(10))
    dr.text((X(plot_l) - 36, gy + 8), "limite", fill=GREY, font=_font(10))
    annex_labels = []
    for p in polys:
        if not p["annexe"]:
            continue
        ax0 = min(x for x, _ in p["pts"])
        ax1 = max(x for x, _ in p["pts"])
        ah = p["h_m"] or min(sh, wall_h)
        dr.rectangle([X(ax0), gy - ah * scale, X(ax1), gy], outline=RED, width=2, fill=(250, 214, 190))
        annex_labels.append((X(ax0), gy - ah * scale - 16, f"{p['name']} ({fmt(ah)} m)"))
    x0, x1 = X(mnx), X(mxx)
    top = gy - wall_h * scale
    dr.rectangle([x0, top, x1, gy], outline=INK, width=3, fill=(246, 242, 234))
    for i in range(1, hh["levels"]):
        yy = gy - i * sh * scale
        _dash_line(dr, (x0, yy), (x1, yy), GREY, width=1)
    roof_px = (total_h - wall_h) * scale
    if rt == "plana":
        dr.rectangle([x0 - 3, top - 10, x1 + 3, top], fill=INK)
        dr.text((x0, top - 26), "platibanda", fill=GREY, font=_font(10))
    elif roof_px > 1:
        dr.polygon([(x0 - 8, top), (x1 + 8, top), (x1, top - roof_px), (x0, top - roof_px)], outline=INK, fill=ROOF)
        for k in range(1, 6):
            yy = top - roof_px * k / 6
            dr.line([(x0, yy), (x1, yy)], fill=(170, 90, 70), width=1)
    for lx, ly, lt in annex_labels:
        tw = dr.textlength(lt, font=_font(10))
        dr.rectangle([lx + 2, ly - 1, lx + 6 + tw, ly + 13], fill=(255, 255, 255))
        dr.text((lx + 4, ly), lt, fill=RED, font=_font(10))
    _cota(dr, (x1 + 26, gy), (x1 + 26, top), f"{fmt(wall_h)} m", offset=(8, -8))
    if total_h > wall_h + 0.01:
        _cota(dr, (x1 + 100, gy), (x1 + 100, gy - total_h * scale), f"{fmt(total_h)} m", offset=(8, -8))
    _cota(dr, (x0, gy + 46), (x1, gy + 46), f"{fmt(mxx - mnx)} m", color=GREEN, offset=(-20, 4))
    dr.text((gx, gy + 76), f"Altura da fachada {fmt(wall_h)} m · altura total {fmt(total_h)} m · {ROOF_TYPES[rt]}",
            fill=INK, font=_font(12))
    _footer(dr, W, H, "Alçado simplificado pela envolvente — vãos, materiais e cores a definir no projeto de arquitetura.")
    return _png(img)


# ---------------------------------------------------------------- axonometria ----
_ISO = math.radians(30)
_COS, _SIN = math.cos(_ISO), math.sin(_ISO)


def _iso(x, y, z):
    """Projeção isométrica vista da frente-direita (fachada principal y = mín. e lado x = máx. visíveis)."""
    return (x + y) * _COS, (x - y) * _SIN - z


def _shade(rgb, f):
    return tuple(max(0, min(255, int(c * f))) for c in rgb)


def _box_faces(x0, y0, x1, y1, h, roof, roof_h, wall_rgb, top_rgb):
    """Faces visíveis de um prisma retangular (frente, lado direito, cobertura), por ordem de desenho."""
    front = [(x0, y0, 0), (x1, y0, 0), (x1, y0, h), (x0, y0, h)]
    right = [(x1, y0, 0), (x1, y1, 0), (x1, y1, h), (x1, y0, h)]
    faces = [(front, _shade(wall_rgb, 0.86)), (right, wall_rgb)]
    if roof == "duas_aguas" and roof_h > 0.2:
        ym = (y0 + y1) / 2
        faces.append(([(x0, ym, h + roof_h), (x1, ym, h + roof_h), (x1, y1, h), (x0, y1, h)], _shade(ROOF, 0.85)))
        faces.append(([(x1, y0, h), (x1, y1, h), (x1, ym, h + roof_h)], wall_rgb))
        faces.append(([(x0, y0, h), (x1, y0, h), (x1, ym, h + roof_h), (x0, ym, h + roof_h)], ROOF))
    elif roof == "uma_agua" and roof_h > 0.2:
        faces.append(([(x1, y0, h), (x1, y1, h), (x1, y1, h + roof_h)], wall_rgb))
        faces.append(([(x0, y0, h), (x1, y0, h), (x1, y1, h + roof_h), (x0, y1, h + roof_h)], ROOF))
    else:
        faces.append(([(x0, y0, h), (x1, y0, h), (x1, y1, h), (x0, y1, h)], top_rgb))
    return faces


def axonometria(volume: dict) -> bytes:
    """Vista axonométrica (isométrica) do volume: retângulos da construção extrudidos, anexos e cobertura.

    Algoritmo do pintor por objeto (do mais afastado ao mais próximo) com eliminação das faces traseiras.
    """
    v = volume or {}
    hh = heights(v)
    sh, wall_h, total_h, rt = hh["storey_h_m"], hh["altura_fachada_m"], hh["altura_total_m"], hh["roof_type"]
    roof_h = max(0.0, total_h - wall_h)
    polys = building_polygons(v)
    objects = []
    for (x0, y0, x1, y1) in main_rects(v):
        objects.append(((x0 + x1) / 2 - (y0 + y1) / 2,
                        _box_faces(x0, y0, x1, y1, wall_h, rt, roof_h, (236, 232, 224), (248, 246, 240))))
    for p in polys:
        if not p["annexe"]:
            continue
        xs, ys = [x for x, _ in p["pts"]], [y for _, y in p["pts"]]
        h = p["h_m"] or min(wall_h, sh * 1.1)
        objects.append(((min(xs) + max(xs)) / 2 - (min(ys) + max(ys)) / 2,
                        _box_faces(min(xs), min(ys), max(xs), max(ys), h, "plana", 0, (210, 150, 120), (235, 185, 160))))
    objects.sort(key=lambda o: o[0])
    faces = [f for _, fs in objects for f in fs]
    projected = [[_iso(x, y, z) for x, y, z in pts] for pts, _ in faces]
    allp = [pt for f in projected for pt in f]
    minx = min(x for x, _ in allp)
    maxx = max(x for x, _ in allp)
    miny = min(y for _, y in allp)
    maxy = max(y for _, y in allp)
    W, Hh, pad = 1000, 720, 80
    scale = min((W - 2 * pad) / max(maxx - minx, 0.1), (Hh - 2 * pad - 50) / max(maxy - miny, 0.1))
    ox = pad + ((W - 2 * pad) - (maxx - minx) * scale) / 2 - minx * scale
    oy = pad + 36 - miny * scale
    img = Image.new("RGB", (W, Hh), (245, 247, 248))
    dr = ImageDraw.Draw(img, "RGBA")
    _header(dr, W, "Vista axonométrica do volume (esquemática)")
    for (pts, fill), pr in zip(faces, projected):
        pts2d = [(ox + x * scale, oy + y * scale) for x, y in pr]
        dr.polygon(pts2d, fill=fill + (255,))
        dr.line(pts2d + [pts2d[0]], fill=INK, width=2)
    dr.text((20, Hh - 76), "Vista a partir da frente (via pública) e do lado direito.", fill=GREY, font=_font(11))
    dr.text((20, Hh - 58), f"Altura total ≈ {fmt(total_h)} m · {hh['levels']} piso(s) · área de implantação {fmt(union_area(polys))} m²",
            fill=INK, font=_font(13))
    _footer(dr, W, Hh)
    return _png(img)


# ================================================================ MURO DE VEDAÇÃO / SUPORTE ====
MATERIAIS_MURO = {
    "alvenaria_rebocada": "Alvenaria rebocada e pintada",
    "pedra": "Pedra",
    "rede": "Rede metálica",
    "muro_baixo_gradeamento": "Muro baixo com gradeamento",
    "ripado": "Ripado (madeira / compósito)",
}
IMPLANTACOES_MURO = {"frente": "Na frente (via pública)", "laterais": "Nos limites laterais", "frente_e_laterais": "Frente e laterais"}


def _params(spec):
    return (spec or {}).get("parametros") or (spec or {}).get("parametres") or {}


def _na(v, suffix=""):
    return f"{fmt(v)}{suffix}" if isinstance(v, (int, float)) and not isinstance(v, bool) else "a indicar"


def muro_planta(spec: dict) -> bytes:
    p = _params(spec)
    lin = _num(p.get("comprimento_m"), 0)
    plot_l = max(lin * 1.25, 24.0) if lin else 24.0
    plot_w = 16.0
    impl = p.get("implantacao") or "frente"
    portao = bool(p.get("portao"))
    pl = _num(p.get("portao_largura_m"), 0)
    ppos = _num(p.get("portao_posicao_m"), 0)
    W, H = 1000, 760
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img, "RGBA")
    _header(dr, W, "Planta de implantação — muro (esquemática)")
    ox, oy, draww, drawh = 100, 90, 780, 460
    scale = min(draww / plot_l, drawh / plot_w)
    pw, ph = plot_l * scale, plot_w * scale
    dr.rectangle([ox, oy, ox + pw, oy + ph], outline=INK, width=2, fill=(247, 250, 246))
    dr.rectangle([ox - 30, oy + ph + 26, ox + pw + 30, oy + ph + 56], fill=(225, 226, 232))
    dr.text((ox + 6, oy + ph + 33), "Via pública", fill=(90, 90, 100), font=_font(12))

    def seg(a, b, label, dy=-22):
        dr.line([a, b], fill=RED, width=7)
        dr.text(((a[0] + b[0]) / 2 - 40, (a[1] + b[1]) / 2 + dy), label, fill=RED, font=_font(12))

    if impl in ("frente", "frente_e_laterais"):
        seg((ox, oy + ph), (ox + pw, oy + ph), f"Muro na frente — {_na(lin or None, ' m')}")
    if impl in ("laterais", "frente_e_laterais"):
        seg((ox, oy), (ox, oy + ph), "Limite lateral", dy=0)
        seg((ox + pw, oy), (ox + pw, oy + ph), "Limite lateral", dy=0)
    if portao:
        gwid = (pl or 4) * scale
        gx = ox + min(max(ppos * scale, 0), pw - gwid)
        dr.rectangle([gx, oy + ph - 6, gx + gwid, oy + ph + 6], fill=(255, 255, 255))
        dr.line([(gx, oy + ph), (gx + gwid, oy + ph)], fill=GREEN, width=8)
        dr.text((gx, oy + ph - 26), f"Portão {_na(pl or None, ' m')}", fill=GREEN, font=_font(12))
    _north(dr, W - 64, 46)
    info = [f"Implantação: {IMPLANTACOES_MURO.get(impl, impl)}",
            f"Tipo: {'muro de suporte de terras' if p.get('subtipo') == 'suporte' else 'muro de vedação'}",
            f"Material: {MATERIAIS_MURO.get(p.get('material'), 'a indicar')}",
            f"Altura: {_na(p.get('altura_m'), ' m')}"]
    yy = oy + ph + 72
    for t in info:
        dr.text((ox, yy), t, fill=INK, font=_font(13))
        yy += 21
    _footer(dr, W, H, "Terreno esquemático — implantar sobre o levantamento topográfico.")
    return _png(img)


def muro_alcado(spec: dict) -> bytes:
    p = _params(spec)
    h = _num(p.get("altura_m"), 0) or 1.8
    lin = _num(p.get("comprimento_m"), 0) or 10.0
    cap = bool(p.get("capeamento"))
    portao = bool(p.get("portao"))
    pl = _num(p.get("portao_largura_m"), 0) or (4.0 if portao else 0)
    W, H = 1000, 560
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    _header(dr, W, "Alçado do muro (esquemático)")
    gx, gy, gw = 110, 430, 760
    scale = min(gw / max(lin, pl + 2), 290 / max(h, 1))
    wall_h = h * scale
    dr.line([gx - 20, gy, gx + gw + 20, gy], fill=(120, 110, 90), width=3)
    dr.text((gx - 20, gy + 8), "Terreno natural", fill=(120, 110, 90), font=_font(11))
    wall_w = max(40, min(((lin - pl) if portao else lin) * scale, gw))
    dr.rectangle([gx, gy - wall_h, gx + wall_w, gy], outline=INK, width=2, fill=(224, 214, 198))
    for xx in (gx, gx + wall_w):
        dr.rectangle([xx - 7, gy - wall_h - (10 if cap else 0), xx + 7, gy], outline=INK, width=2, fill=(206, 196, 180))
    if cap:
        dr.rectangle([gx - 6, gy - wall_h - 10, gx + wall_w + 6, gy - wall_h], fill=(150, 140, 125))
        dr.text((gx + 6, gy - wall_h - 28), "Capeamento", fill=(110, 100, 85), font=_font(11))
    if portao and pl:
        px0 = gx + wall_w + 6
        pwid = pl * scale
        dr.rectangle([px0, gy - wall_h, px0 + pwid, gy], outline=GREEN, width=3)
        for i in range(1, 6):
            dr.line([(px0 + i * pwid / 6, gy - wall_h), (px0 + i * pwid / 6, gy)], fill=(120, 170, 140), width=2)
        dr.text((px0 + 4, gy - wall_h - 20), f"Portão {fmt(pl)} m", fill=GREEN, font=_font(12))
    _cota(dr, (gx - 34, gy), (gx - 34, gy - wall_h), f"{fmt(h)} m", offset=(-70, -8))
    dr.text((gx, gy + 30), f"Comprimento ≈ {fmt(lin)} m · material: {MATERIAIS_MURO.get(p.get('material'), 'a indicar')}",
            fill=INK, font=_font(12))
    _footer(dr, W, H)
    return _png(img)


def muro_corte(spec: dict) -> bytes:
    p = _params(spec)
    h = _num(p.get("altura_m"), 0) or 1.8
    cap = bool(p.get("capeamento"))
    suporte = p.get("subtipo") == "suporte"
    W, H = 820, 600
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    _header(dr, W, "Corte-tipo do muro (esquemático)")
    cx, gy = W // 2, 440
    scale = min(250 / max(h, 1), 120)
    wall_h = h * scale
    t = 0.20 * scale
    fnd_w, fnd_h = 0.50 * scale, 0.40 * scale
    dr.rectangle([40, gy, W - 40, gy + 50], fill=GROUND)
    dr.line([40, gy, W - 40, gy], fill=(120, 110, 90), width=2)
    if suporte:
        dr.polygon([(cx + t / 2, gy), (cx + t / 2, gy - wall_h + 6), (W - 40, gy - wall_h + 6), (W - 40, gy)], fill=GROUND)
        dr.text((cx + t / 2 + 20, gy - wall_h + 14), "Terras suportadas", fill=(110, 100, 80), font=_font(11))
    dr.text((50, gy + 54), "Exterior / via", fill=(110, 100, 80), font=_font(11))
    dr.text((W - 200, gy + 54), "Interior do lote", fill=(110, 100, 80), font=_font(11))
    dr.rectangle([cx - fnd_w / 2, gy, cx + fnd_w / 2, gy + fnd_h], outline=INK, width=2, fill=(210, 210, 215))
    dr.text((cx + fnd_w / 2 + 8, gy + fnd_h / 2 - 6), "Sapata corrida em betão", fill=INK, font=_font(11))
    dr.rectangle([cx - t / 2, gy - wall_h, cx + t / 2, gy], outline=INK, width=2, fill=(224, 214, 198))
    if cap:
        dr.rectangle([cx - t / 2 - 6, gy - wall_h - 10, cx + t / 2 + 6, gy - wall_h], fill=(150, 140, 125))
        dr.text((cx + t / 2 + 12, gy - wall_h - 8), "Capeamento", fill=(110, 100, 85), font=_font(11))
    _cota(dr, (cx - t / 2 - 34, gy), (cx - t / 2 - 34, gy - wall_h), f"{fmt(h)} m", offset=(-70, -8))
    dr.text((40, H - 70), "Espessura indicativa 0,20 m · fundação a dimensionar em função do terreno"
            + (" · muro de suporte: verificar estabilidade (projeto de estabilidade)" if suporte else ""),
            fill=INK, font=_font(11))
    _footer(dr, W, H)
    return _png(img)


# ================================================================ PISCINA ====
def piscina_planta(spec: dict) -> bytes:
    p = _params(spec)
    L = _num(p.get("comprimento_m"), 0) or 8.0
    Wb = _num(p.get("largura_m"), 0) or 4.0
    dist = _num(p.get("distancia_limites_m"), 0) or 3.0
    plot_l = max(L + 2 * dist + 4, 16.0)
    plot_w = max(Wb + 2 * dist + 4, 12.0)
    W, H = 1000, 760
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img, "RGBA")
    _header(dr, W, "Planta de implantação — piscina (esquemática)")
    ox, oy, draww, drawh = 110, 90, 740, 460
    scale = min(draww / plot_l, drawh / plot_w)
    pw, ph = plot_l * scale, plot_w * scale
    dr.rectangle([ox, oy, ox + pw, oy + ph], outline=INK, width=2, fill=(247, 250, 246))
    dr.text((ox + pw / 2 - 30, oy + ph + 8), f"{fmt(plot_l)} m", fill=INK, font=_font(13))
    bx = ox + dist * scale
    by = oy + ph - (dist + Wb) * scale
    dr.rectangle([bx, by, bx + L * scale, by + Wb * scale], outline=(20, 90, 140), width=3, fill=WATER + (180,))
    dr.text((bx + 6, by + 6), f"Tanque {fmt(L)} × {fmt(Wb)} m", fill=(10, 60, 100), font=_font(13))
    _cota(dr, (ox, by + Wb * scale / 2), (bx, by + Wb * scale / 2), f"{fmt(dist)} m", offset=(-20, -20))
    _cota(dr, (bx + L * scale / 2, by + Wb * scale), (bx + L * scale / 2, oy + ph), f"{fmt(dist)} m", offset=(6, -8))
    _north(dr, W - 64, 46)
    info = [f"Área do plano de água: {fmt(L * Wb)} m²",
            f"Distância aos limites (indicada): {_na(p.get('distancia_limites_m'), ' m')}",
            f"Cobertura amovível: {'sim (' + _na(p.get('cobertura_h_m'), ' m') + ')' if p.get('cobertura') else 'não'}"]
    yy = oy + ph + 40
    for t in info:
        dr.text((ox, yy), t, fill=INK, font=_font(13))
        yy += 21
    _footer(dr, W, H, "Terreno esquemático — posicionar o tanque sobre o levantamento topográfico.")
    return _png(img)


def piscina_corte(spec: dict) -> bytes:
    p = _params(spec)
    L = _num(p.get("comprimento_m"), 0) or 8.0
    prof = _num(p.get("profundidade_m"), 0) or 1.5
    cover_h = _num(p.get("cobertura_h_m"), 0) if p.get("cobertura") else 0
    W, H = 1000, 580
    img = Image.new("RGB", (W, H), (255, 255, 255))
    dr = ImageDraw.Draw(img, "RGBA")
    _header(dr, W, "Corte da piscina (esquemático)")
    gx, gy, gw = 130, 300, 720
    scale = min(gw / max(L, 1), 160 / max(prof + max(cover_h, 0.5), 1))
    bw = L * scale
    bx = gx + (gw - bw) / 2
    dr.rectangle([gx - 30, gy, gx + gw + 30, gy + 190], fill=GROUND)
    dr.line([gx - 30, gy, gx + gw + 30, gy], fill=(120, 110, 90), width=2)
    dr.rectangle([bx, gy, bx + bw, gy + prof * scale], outline=(20, 90, 140), width=3, fill=WATER + (200,))
    dr.text((bx + 6, gy + 6), "Água", fill=(10, 60, 100), font=_font(12))
    dr.rectangle([bx - 14, gy - 8, bx + bw + 14, gy], fill=(225, 220, 210))
    dr.text((bx - 14, gy - 26), "Bordadura", fill=GREY, font=_font(10))
    _cota(dr, (bx - 34, gy), (bx - 34, gy + prof * scale), f"{fmt(prof)} m", offset=(-70, -8))
    if cover_h:
        ch = cover_h * scale
        dr.arc([bx, gy - ch, bx + bw, gy + ch], 180, 360, fill=(90, 120, 150), width=3)
        dr.text((bx + bw / 2 - 40, gy - ch - 18), f"Cobertura {fmt(cover_h)} m", fill=(60, 90, 130), font=_font(12))
    dr.text((bx, gy + prof * scale + 30), f"Comprimento do tanque {fmt(L)} m", fill=INK, font=_font(12))
    _footer(dr, W, H)
    return _png(img)
