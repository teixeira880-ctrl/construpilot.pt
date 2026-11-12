"""Vista 3D (axonometria pintada) e mapa das paredes calculadas de uma moradia, a partir do modelo do edifício lido
pelo Estudo BET (engines/bet_core: envelope, sides, levels, roof, openings, interior_walls).

Sem IA nem dependências novas (Pillow): volumes por piso, telhado de duas/quatro águas ou cobertura plana com platibanda,
vãos nas fachadas visíveis, sombra projetada e céu em degradé — o mesmo espírito da capa da conta CLT.
"""
from __future__ import annotations

import io
import math

WALL = (236, 230, 218)
WALL_DARK = (214, 205, 190)
ROOF_TILE = (172, 82, 58)
ROOF_FLAT = (120, 124, 128)
GLASS = (58, 92, 120)
DOOR = (112, 78, 52)
GROUND = (206, 214, 196)


def _num(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def _levels(raw: dict) -> list[dict]:
    lv = [l for l in raw.get("levels") or [] if isinstance(l, dict) and isinstance(l.get("floor_top"), (int, float))]
    return sorted(lv, key=lambda l: l["floor_top"])


def _level_height(lvls: list[dict], i: int, eaves: float) -> float:
    if i + 1 < len(lvls):
        return lvls[i + 1]["floor_top"] - lvls[i]["floor_top"]
    l = lvls[i]
    h = _num(l.get("ceiling_height"), 2.6) + _num(l.get("slab_thickness"), 0.2)
    return max(h, eaves - l["floor_top"]) if eaves > l["floor_top"] else h


def _sides(raw: dict, L: float, W: float) -> dict:
    """{nome: (eixo, pos, comprimento, normal(x,y), tipo)} — eixo = coordenada constante do plano da fachada."""
    out = {}
    for name, s in (raw.get("sides") or {}).items():
        if not isinstance(s, dict) or s.get("axis") not in ("x", "y"):
            continue
        pos = _num(s.get("pos"))
        if s["axis"] == "x":
            n = (1.0, 0.0) if pos > L / 2 else (-1.0, 0.0)
            out[name] = ("x", pos, W, n, s.get("type") or "facade", s.get("label") or name)
        else:
            n = (0.0, 1.0) if pos > W / 2 else (0.0, -1.0)
            out[name] = ("y", pos, L, n, s.get("type") or "facade", s.get("label") or name)
    if len(out) < 4:                                              # relevé incompleto: quatro fachadas genéricas
        out = {"S": ("y", 0.0, L, (0.0, -1.0), "facade", "Sul"), "N": ("y", W, L, (0.0, 1.0), "facade", "Norte"),
               "O": ("x", 0.0, W, (-1.0, 0.0), "facade", "Oeste"), "E": ("x", L, W, (1.0, 0.0), "facade", "Este")}
    return out


# ------------------------------------------------------------------ 3D
VIEWS = ("main", "side", "rear", "side_other", "aerial")


def render_png(raw: dict, width: int = 1800, height: int = 1100, view: str = "main", mask: bool = False) -> bytes:
    """Axonometria pintada (mesma linguagem visual dos rendus da conta CLT: céu → horizonte dourado, sol difuso,
    árvores, sombra projetada, anti-serrilhado) com a geometria REAL da moradia: pisos, telhado, vãos.
    mask=True: mesma câmara, só a geometria (fundo 0, um tom por face, vãos 40) — serve para verificar que a
    versão fotorrealista respeita 100 % a geometria (engines.geometry_lock)."""
    from PIL import Image, ImageDraw, ImageFilter
    SS = 2                                                        # sobre-amostragem (anti-serrilhado)
    out_w, out_h = width, height
    width, height = width * SS, height * SS
    env = raw.get("envelope") or {}
    L, W = _num(env.get("length_x"), 10), _num(env.get("width_y"), 8)
    lvls = _levels(raw) or [{"id": "RC", "floor_top": 0.0, "ceiling_height": 2.6}]
    roof = raw.get("roof") or {}
    top_floor = lvls[-1]["floor_top"]
    eaves = _num(roof.get("eaves_level"), top_floor + _num(lvls[-1].get("ceiling_height"), 2.6) + 0.3)
    ridge = _num(roof.get("ridge_level"), eaves)
    sides = _sides(raw, L, W)
    pitched = ridge > eaves + 0.3 and "plat" not in str(roof.get("type") or "") and "terras" not in str(roof.get("type") or "")
    # vista: fachada principal + uma lateral visíveis
    names = list(sides)
    main = next((k for k in names if "princ" in k.lower() or "front" in k.lower()), names[0])
    nm = sides[main][3]
    lat = next((k for k in names if abs(sides[k][3][0] * nm[0] + sides[k][3][1] * nm[1]) < 0.1), names[1])
    nl = sides[lat][3]
    vx, vy = -(nm[0] * 0.78 + nl[0] * 0.62), -(nm[1] * 0.78 + nl[1] * 0.62)        # direção do olhar (horizontal)
    k = math.hypot(vx, vy)
    vx, vy = vx / k, vy / k
    rot = {"main": 0, "aerial": 0, "side": 1, "rear": 2, "side_other": 3}.get(view, 0)
    for _ in range(rot):                                                              # câmara à volta da casa (90°)
        vx, vy = -vy, vx
    rx, ry = -vy, vx                                                                  # direita no ecrã
    el = math.radians(46 if view == "aerial" else 27)
    cx, cy = L / 2, W / 2

    def P(x, y, z):
        u = (x - cx) * rx + (y - cy) * ry
        d = (x - cx) * vx + (y - cy) * vy
        return u, -(z * math.cos(el)) - d * math.sin(el), d

    faces = []                                                    # (profundidade, pontos3d, cor, contorno)
    light = (-0.55, -0.35)

    def shade(col, n):
        f = 0.80 + 0.20 * max(-1, min(1, -(n[0] * light[0] + n[1] * light[1])))
        return tuple(int(c * f) for c in col)

    def visible(n):
        return n[0] * vx + n[1] * vy < -0.05

    # paredes exteriores (até ao beirado) + empenas
    for name, (ax, pos, length, n, kind, _lab) in sides.items():
        if not visible(n):
            continue
        if ax == "x":
            quad = [(pos, 0, 0), (pos, W, 0), (pos, W, eaves), (pos, 0, eaves)]
        else:
            quad = [(0, pos, 0), (L, pos, 0), (L, pos, eaves), (0, pos, eaves)]
        wall_face = (quad, shade(WALL, n), 0, [])
        faces.append(wall_face)
        gable_face = None
        gable = pitched and str(roof.get("type") or "deux_pans").startswith("deux") and (
            (str(roof.get("ridge_axis") or ("y" if W > L else "x")) == "y") == (ax == "y"))
        if gable:
            if ax == "y":
                rxp = _num(roof.get("ridge_x"), L / 2) if roof.get("ridge_axis") == "y" else L / 2
                gable_face = ([(0, pos, eaves), (L, pos, eaves), (rxp, pos, ridge)], shade(WALL, n), 0, [])
                faces.append(gable_face)
            else:
                ryp = _num(roof.get("ridge_y"), W / 2)
                gable_face = ([(pos, 0, eaves), (pos, W, eaves), (pos, ryp, ridge)], shade(WALL, n), 0, [])
                faces.append(gable_face)
        # vãos desta fachada
        for o in raw.get("openings") or []:
            if not isinstance(o, dict) or o.get("side") != name:
                continue
            lv = next((l for l in lvls if l.get("id") == o.get("level")), None)
            if lv is None:
                continue
            a, b = _num(o.get("from")), _num(o.get("to"))
            if b <= a:
                continue
            z0 = lv["floor_top"] + _num(o.get("sill"))
            z1 = z0 + _num(o.get("height"), 1.2)
            if z1 <= 0.05:                                       # vão enterrado (cave): não visível
                continue
            z0 = max(z0, 0.0)
            target = wall_face
            if z0 >= eaves - 0.1:                                # acima do beirado: só numa empena
                if gable_face is None:
                    continue
                target = gable_face
            eps = 0.02 * (1 if (n[0] + n[1]) > 0 else -1)
            if ax == "x":
                q = [(pos + eps, a, z0), (pos + eps, b, z0), (pos + eps, b, z1), (pos + eps, a, z1)]
            else:
                q = [(a, pos + eps, z0), (b, pos + eps, z0), (b, pos + eps, z1), (a, pos + eps, z1)]
            door = _num(o.get("sill")) < 0.05 and "jan" not in str(o.get("kind") or "").lower()
            target[3].append((q, DOOR if door else GLASS))
    # lajes de piso (faixa) na fachada
    # cobertura
    ov = 0.45
    if pitched:
        if str(roof.get("ridge_axis") or ("y" if W > L else "x")) == "y":
            rxp = _num(roof.get("ridge_x"), L / 2)
            p1 = [(-ov, -ov, eaves - 0.3), (rxp, -ov, ridge), (rxp, W + ov, ridge), (-ov, W + ov, eaves - 0.3)]
            p2 = [(L + ov, -ov, eaves - 0.3), (rxp, -ov, ridge), (rxp, W + ov, ridge), (L + ov, W + ov, eaves - 0.3)]
            n1, n2 = (-1.0, 0.0), (1.0, 0.0)
        else:
            ryp = _num(roof.get("ridge_y"), W / 2)
            p1 = [(-ov, -ov, eaves - 0.3), (-ov, ryp, ridge), (L + ov, ryp, ridge), (L + ov, -ov, eaves - 0.3)]
            p2 = [(-ov, W + ov, eaves - 0.3), (-ov, ryp, ridge), (L + ov, ryp, ridge), (L + ov, W + ov, eaves - 0.3)]
            n1, n2 = (0.0, -1.0), (0.0, 1.0)
        for poly, n in ((p1, n1), (p2, n2)):
            col = shade(ROOF_TILE, n) if visible(n) else tuple(int(c * 0.72) for c in ROOF_TILE)
            faces.append((poly, col, 2, []))
    else:
        faces.append(([(0, 0, eaves), (L, 0, eaves), (L, W, eaves), (0, W, eaves)], ROOF_FLAT, 2, []))
        par = 0.45
        for name, (ax, pos, length, n, kind, _l) in sides.items():
            if not visible(n):
                continue
            q = ([(pos, 0, eaves), (pos, W, eaves), (pos, W, eaves + par), (pos, 0, eaves + par)] if ax == "x"
                 else [(0, pos, eaves), (L, pos, eaves), (L, pos, eaves + par), (0, pos, eaves + par)])
            faces.append((q, shade(WALL_DARK, n), 3, []))

    # projeção e enquadramento
    pts = [P(*p) for f in faces for p in f[0]] + [P(x, y, 0) for x in (-2, L + 2) for y in (-2, W + 2)]
    minx, maxx = min(p[0] for p in pts), max(p[0] for p in pts)
    miny, maxy = min(p[1] for p in pts), max(p[1] for p in pts)
    sc = min(width * 0.78 / (maxx - minx), height * 0.74 / (maxy - miny))
    ox = width / 2 - sc * (minx + maxx) / 2
    oy = height * 0.53 - sc * (miny + maxy) / 2

    def S(p):
        u, v, _d = P(*p)
        return (ox + sc * u, oy + sc * v)

    def depth_(f):
        ds = [P(*p)[2] for p in f[0]]
        return sum(ds) / len(ds)

    if mask:
        img = Image.new("L", (width, height), 0)
        dr = ImageDraw.Draw(img)
        for i_, (poly, col, layer, kids) in enumerate(sorted(faces, key=lambda f: (-depth_(f), f[2]))):
            dr.polygon([S(p) for p in poly], fill=130 + (i_ * 47) % 125)       # um tom por face → todas as arestas contam
            for q, _kc in kids:
                dr.polygon([S(p) for p in q], fill=40)
        img = img.resize((out_w, out_h), Image.NEAREST)
        buf = io.BytesIO()
        img.save(buf, "PNG", optimize=True)
        return buf.getvalue()
    img = Image.new("RGB", (width, height))
    dr = ImageDraw.Draw(img)
    for yy in range(height):                                       # céu: azul profundo → horizonte dourado (estilo CLT)
        k_ = yy / height
        if k_ < 0.55:
            f_ = k_ / 0.55
            col = (int(120 + 125 * f_), int(160 + 75 * f_), int(205 + 20 * f_))
        else:
            f_ = (k_ - 0.55) / 0.45
            col = (int(245 - 40 * f_), int(235 - 25 * f_), int(225 - 35 * f_))
        dr.line([(0, yy), (width, yy)], fill=col)
    gm = Image.new("L", (width, height), 0)                        # relvado suave à volta
    ImageDraw.Draw(gm).polygon([S((-4, -4, 0)), S((L + 4, -4, 0)), S((L + 4, W + 4, 0)), S((-4, W + 4, 0))], fill=255)
    gm = gm.filter(ImageFilter.GaussianBlur(26 * SS))
    img.paste(Image.new("RGB", (width, height), (198, 208, 186)), (0, 0), gm)
    sh = Image.new("L", (width, height), 0)                       # sombra projetada suave
    sd = ImageDraw.Draw(sh)
    off = max(eaves, ridge) * 0.55
    sd.polygon([S((0 + off * 0.6, 0 + off * 0.4, 0)), S((L + off * 0.6, 0 + off * 0.4, 0)), S((L + off * 0.6, W + off * 0.4, 0)),
                S((0 + off * 0.6, W + off * 0.4, 0)), S((0, W, 0)), S((0, 0, 0))], fill=110)
    sh = sh.filter(ImageFilter.GaussianBlur(22 * SS))
    img.paste((70, 74, 70), (0, 0), sh)
    dr = ImageDraw.Draw(img)

    def tree(x, y, h=6.5, rad=1.9):
        bx, by = S((x, y, 0))
        dr.ellipse([bx - rad * sc * 0.9, by - rad * sc * 0.35, bx + rad * sc * 0.9, by + rad * sc * 0.35], fill=(150, 156, 140))
        dr.line([S((x, y, 0)), S((x, y, h * 0.45))], fill=(92, 70, 50), width=max(2, int(0.25 * sc)))
        for dz, rr, col_ in ((0.55, 1.0, (64, 110, 70)), (0.75, 0.85, (82, 134, 84)), (0.92, 0.6, (108, 160, 100))):
            cxp, cyp = S((x, y, h * dz))
            rp = rad * rr * sc
            dr.ellipse([cxp - rp, cyp - rp, cxp + rp, cyp + rp], fill=col_)
    corners = sorted([(x_, y_) for x_ in (-2.6, L + 2.6) for y_ in (-2.6, W + 2.6)], key=lambda c: P(c[0], c[1], 0)[2])
    far, near = corners[-1], corners[0]
    tree(far[0], far[1])                                           # árvore atrás (antes da casa)

    def depth(f):
        ds = [P(*p)[2] for p in f[0]]
        return (sum(ds) / len(ds), f[2])
    lw = max(1, SS)
    for poly, col, layer, kids in sorted(faces, key=lambda f: (-depth(f)[0], f[2])):
        dr.polygon([S(p) for p in poly], fill=col, outline=tuple(max(0, c - 40) for c in col))
        if layer == 2 and col != ROOF_FLAT and len(poly) == 4:     # fiadas de telha paralelas ao beirado
            a0, b0, b1, a1 = poly[0], poly[1], poly[2], poly[3]
            for q in range(1, 12):
                t_ = q / 12
                p0 = tuple(a0[i_] + (b0[i_] - a0[i_]) * t_ for i_ in range(3))
                p1 = tuple(a1[i_] + (b1[i_] - a1[i_]) * t_ for i_ in range(3))
                dr.line([S(p0), S(p1)], fill=tuple(max(0, c - 22) for c in col), width=lw)
        for q, kc in kids:                                         # vãos sempre por cima da própria parede
            pts_ = [S(p) for p in q]
            dr.polygon(pts_, fill=kc, outline=(48, 48, 46), width=lw * 2)
            if kc == GLASS:
                dr.line([pts_[0], pts_[2]], fill=(120, 160, 186), width=lw)   # reflexo
                mid_a = ((pts_[0][0] + pts_[1][0]) / 2, (pts_[0][1] + pts_[1][1]) / 2)
                mid_b = ((pts_[3][0] + pts_[2][0]) / 2, (pts_[3][1] + pts_[2][1]) / 2)
                dr.line([mid_a, mid_b], fill=(235, 235, 230), width=lw)            # caixilho
    # linhas dos pisos (faixas de laje) nas fachadas visíveis
    for name, (ax, pos, length, n, kind, _l) in sides.items():
        if not visible(n):
            continue
        for lv in lvls[1:]:
            z = lv["floor_top"]
            a, b = ((pos, 0, z), (pos, W, z)) if ax == "x" else ((0, pos, z), (L, pos, z))
            dr.line([S(a), S(b)], fill=WALL_DARK, width=max(2, int(sc * 0.06)))
    # árvore à frente, ao lado da casa (nunca à frente da fachada principal)
    side_pt = max([(x_, y_) for x_ in (-3.2, L + 3.2) for y_ in (-3.2, W + 3.2)], key=lambda c: P(c[0], c[1], 0)[0])
    tree(side_pt[0], side_pt[1], h=5.2, rad=1.5)
    img = img.resize((out_w, out_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------------ paredes calculadas
def walls(raw: dict) -> dict:
    """Mapa das paredes calculadas a partir do modelo: exteriores por piso e fachada (vãos deduzidos), empenas e
    paredes interiores. Áreas em m², comprimentos em m."""
    env = raw.get("envelope") or {}
    L, W = _num(env.get("length_x"), 10), _num(env.get("width_y"), 8)
    t_tot, t_str = _num(env.get("wall_total_thickness"), 0.30), _num(env.get("wall_structural_thickness"), 0.20)
    lvls = _levels(raw)
    roof = raw.get("roof") or {}
    eaves = _num(roof.get("eaves_level"), (lvls[-1]["floor_top"] + 2.9) if lvls else 2.9)
    ridge = _num(roof.get("ridge_level"), eaves)
    sides = _sides(raw, L, W)
    ext, intr = [], []
    for i, lv in enumerate(lvls):
        h = _level_height(lvls, i, eaves)
        for name, (ax, pos, length, n, kind, label) in sides.items():
            ops = [o for o in raw.get("openings") or [] if isinstance(o, dict) and o.get("side") == name and o.get("level") == lv.get("id")]
            a_op = sum(max(0.0, _num(o.get("to")) - _num(o.get("from"))) * _num(o.get("height")) for o in ops)
            gross = length * h
            ext.append({"level": lv.get("name") or lv.get("id"), "wall": label, "type": "meeira" if kind == "mitoyen" else "fachada",
                        "length": round(length, 2), "height": round(h, 2), "thickness": t_tot, "structural": t_str,
                        "openings": len(ops), "openings_m2": round(a_op, 2), "gross_m2": round(gross, 2), "net_m2": round(gross - a_op, 2)})
        for w in (raw.get("interior_walls") or {}).get(lv.get("id"), []) or []:
            try:
                dx, dy = abs(_num(w["x1"]) - _num(w["x0"])), abs(_num(w["y1"]) - _num(w["y0"]))
            except (KeyError, TypeError):
                continue
            length, th = max(dx, dy), max(0.07, min(dx, dy))
            hc = _num(lv.get("ceiling_height"), 2.6)
            intr.append({"level": lv.get("name") or lv.get("id"), "wall": str(w.get("kind") or "parede interior"),
                         "length": round(length, 2), "height": round(hc, 2), "thickness": round(th, 2),
                         "net_m2": round(length * hc, 2), "bearing": "porteur" in str(w.get("kind") or "") or th >= 0.15})
    gables = []
    if ridge > eaves + 0.3 and str(roof.get("type") or "deux_pans").startswith("deux"):
        ax_r = str(roof.get("ridge_axis") or ("y" if W > L else "x"))
        for name, (ax, pos, length, n, kind, label) in sides.items():
            if (ax_r == "y") == (ax == "y"):
                gables.append({"wall": f"Empena — {label}", "base": round(length, 2), "height": round(ridge - eaves, 2),
                               "net_m2": round(length * (ridge - eaves) / 2, 2)})
    tot = {"ext_net_m2": round(sum(x["net_m2"] for x in ext), 2), "ext_gross_m2": round(sum(x["gross_m2"] for x in ext), 2),
           "openings_m2": round(sum(x["openings_m2"] for x in ext), 2), "gables_m2": round(sum(g["net_m2"] for g in gables), 2),
           "int_m2": round(sum(x["net_m2"] for x in intr), 2), "int_bearing_m2": round(sum(x["net_m2"] for x in intr if x["bearing"]), 2),
           "ext_length_m": round(2 * (L + W), 2)}
    return {"exterior": ext, "interior": intr, "gables": gables, "totals": tot, "L": L, "W": W, "levels": len(lvls)}


def walls_flowables(raw: dict, accent: str = "#15803D", lang: str = "pt", views: dict | None = None) -> list:
    """Páginas « Perspetivas do projeto » e « Paredes calculadas » (planta das paredes, corte 3D, mapa por parede e
    verificação cruzada por três métodos) — a mesma apresentação que o dossier da conta CLT, para qualquer moradia."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle

    from engines.pdf_fonts import F
    fr = str(lang or "").lower().startswith("fr-") or lang == "fr_true"
    T = (lambda pt, f: f if fr else pt)
    views = views or {}
    acc = colors.HexColor(accent if str(accent).startswith("#") and len(str(accent)) == 7 else "#15803D")
    rgb = tuple(int(str(accent).lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)) if str(accent).startswith("#") and len(str(accent)) == 7 else (21, 128, 61)
    H1 = ParagraphStyle("w1", fontName=F("Helvetica-Bold"), fontSize=15, leading=19, textColor=acc, spaceAfter=4)
    H2 = ParagraphStyle("w2", fontName=F("Helvetica-Bold"), fontSize=11, leading=14, textColor=colors.HexColor("#1f2937"), spaceBefore=6, spaceAfter=4)
    P = ParagraphStyle("wp", fontName=F("Helvetica"), fontSize=8.5, leading=11.5, textColor=colors.HexColor("#374151"))
    CAP = ParagraphStyle("wc", fontName=F("Helvetica"), fontSize=7.5, leading=9.5, textColor=colors.HexColor("#6b7280"), alignment=1)

    def n(v, d=2):
        return f"{v:,.{d}f}".replace(",", " ").replace(".", ",")

    def img(data, w_mm):
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        return RLImage(io.BytesIO(data), width=w_mm * mm, height=w_mm * mm * im.height / im.width)

    def table(rows, widths, total=None):
        data = rows + ([total] if total else [])
        tb = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
        st = [("BACKGROUND", (0, 0), (-1, 0), acc), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("FONTNAME", (0, 0), (-1, 0), F("Helvetica-Bold")), ("FONTNAME", (0, 1), (-1, -1), F("Helvetica")),
              ("FONTSIZE", (0, 0), (-1, -1), 7.4), ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F6F5")]),
              ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
              ("TOPPADDING", (0, 0), (-1, -1), 2.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2)]
        if total:
            st += [("FONTNAME", (0, -1), (-1, -1), F("Helvetica-Bold")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E8EEEA"))]
        tb.setStyle(TableStyle(st))
        return tb

    s = []
    # ---- Perspetivas (mesma geometria, fotorrealistas quando disponíveis)
    persp = [(k, views[k]) for k in ("main", "side", "rear", "aerial") if views.get(k)]
    if persp:
        s += [PageBreak(), Paragraph(T("Perspetivas do projeto", "Perspectives du projet"), H1),
              Paragraph(T("Vistas calculadas a partir da geometria lida nas plantas (pisos, cobertura, vãos); versões fotorrealistas "
                          "com a geometria bloqueada.", "Vues calculées à partir de la géométrie relevée sur les plans (niveaux, toiture, "
                          "baies) ; versions photoréalistes à géométrie verrouillée."), P), Spacer(1, 4)]
        lab = {"main": T("Perspetiva principal", "Perspective principale"), "side": T("Perspetiva lateral", "Perspective latérale"),
               "rear": T("Perspetiva posterior", "Perspective arrière"), "aerial": T("Vista aérea", "Vue aérienne")}
        s.append(img(persp[0][1], 174))
        s.append(Paragraph(lab[persp[0][0]], CAP))
        rest = persp[1:]
        if rest:
            cells = [[img(v, 56) for _k, v in rest], [Paragraph(lab[k], CAP) for k, _v in rest]]
            s += [Spacer(1, 4), Table(cells, colWidths=[58 * mm] * len(rest))]
    # ---- Paredes calculadas (motor de paredes da conta CLT)
    floors = takeoff(raw)
    good = [f for f in floors if not f.get("error")]
    s += [PageBreak(), Paragraph(T("Paredes calculadas", "Murs calculés"), H1),
          Paragraph(T("Mesmo motor de medição que a conta CLT: eixos das paredes lidos nas plantas, juntas L / T / X resolvidas sem "
                      "contagem dupla e verificação cruzada por três métodos (eixos desenhados, união das plantas GEOS, peças). "
                      "Vãos deduzidos parede a parede. Valores a confirmar com o projeto de execução.",
                      "Même moteur de métré que le compte CLT : axes des murs relevés sur les plans, jonctions L / T / X résolues sans "
                      "double compte et vérification croisée par trois méthodes (axes dessinés, union des plans GEOS, pièces). "
                      "Baies déduites mur par mur. Valeurs à confirmer avec le projet d'exécution."), P), Spacer(1, 4)]
    if good:
        kp = [[T("Paredes (líquido)", "Murs (net)"), T("Vãos deduzidos", "Baies déduites"), T("Volume de parede", "Volume de mur"),
               T("Contagem dupla evitada", "Double compte évité"), T("Pisos", "Niveaux")],
              [f"{n(sum(f['net_m2'] for f in good), 1)} m²", f"{n(sum(f['openings_m2'] for f in good), 1)} m²",
               f"{n(sum(f['volume_m3'] for f in good), 1)} m³", f"{n(sum(f['double_count_m3'] for f in good), 2)} m³", str(len(good))]]
        kt = Table(kp, colWidths=[35 * mm] * 5)
        kt.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), F("Helvetica")), ("FONTSIZE", (0, 0), (-1, 0), 7),
                                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#6b7280")), ("FONTNAME", (0, 1), (-1, 1), F("Helvetica-Bold")),
                                ("FONTSIZE", (0, 1), (-1, 1), 12), ("LINEBEFORE", (0, 0), (0, -1), 3, acc),
                                ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")), ("TOPPADDING", (0, 0), (-1, -1), 4),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        s.append(kt)
    for k, f in enumerate(floors):
        if f.get("error"):
            s.append(Paragraph(f"{f['level']}: " + T("medição automática impossível neste piso", "métré automatique impossible sur ce niveau")
                               + f" ({f['error']})", P))
            continue
        if k:
            s.append(PageBreak())
        s.append(Paragraph(f"{T('Piso', 'Niveau')} — {f['level']}", H2))
        cut = views.get(f"cut_{k}")
        pics = [[img(plan_png(raw, f, 1300, rgb), 86), img(cut or cutaway_png(raw, f, 1300, 820), 86)],
                [Paragraph(T("Planta das paredes medidas", "Plan des murs mesurés"), CAP),
                 Paragraph(T("Corte 3D do piso (geometria real)", "Coupe 3D du niveau (géométrie réelle)"), CAP)]]
        s.append(Table(pics, colWidths=[88 * mm, 88 * mm]))
        ck = f["check"]
        jn = " / ".join(f"{a} {b}" for a, b in sorted(f["joints"].items()))
        s.append(Paragraph(
            T(f"<b>Verificação</b> — eixos desenhados {n(f['drawn_m'])} m · união das plantas (GEOS) {n(f['union_m'])} m · peças {n(f['pieces_m'])} m"
              f" · volume: diferença {n(ck.get('error_percent', 0), 3)} % → <b>{'conforme' if ck.get('passed') else 'a rever'}</b>"
              f" · juntas {jn} · contagem dupla evitada {n(f['double_count_m3'])} m³.",
              f"<b>Vérification</b> — axes dessinés {n(f['drawn_m'])} m · union des plans (GEOS) {n(f['union_m'])} m · pièces {n(f['pieces_m'])} m"
              f" · volume : écart {n(ck.get('error_percent', 0), 3)} % → <b>{'conforme' if ck.get('passed') else 'à revoir'}</b>"
              f" · jonctions {jn} · double compte évité {n(f['double_count_m3'])} m³."), P))
        rows = [[T("Parede", "Mur"), T("Origem", "Origine"), T("Compr. m", "Long. m"), T("Esp. mm", "Ép. mm"), T("Alt. m", "Haut. m"),
                 T("Vãos", "Baies"), T("Vãos m²", "Baies m²"), T("Líquido m²", "Net m²"), T("Volume m³", "Volume m³")]]
        for p_ in f["pieces"]:
            src = next((w.source for w in f["axes"] if w.id == p_["parede"]), "")
            rows.append([p_["id"][:16], str(src)[:30], n(p_["comprimento_m"]), str(int(p_["espessura_mm"])), n(p_["altura_m"]),
                         str(len(p_["vaos"])), n(p_["area_vaos_m2"]), n(p_["area_liquida_m2"]), n(p_["volume_liquido_m3"], 3)])
        s.append(table(rows, (20, 44, 15, 13, 13, 11, 15, 19, 19),
                       ["Total", "", n(f["pieces_m"]), "", "", "", n(f["openings_m2"]), n(f["net_m2"]), n(f["volume_m3"], 3)]))
    wd = walls(raw)
    if wd["gables"]:
        s.append(Paragraph(T("Empenas (alvenaria acima do beirado)", "Pignons (maçonnerie au-dessus de l'égout)"), H2))
        s.append(table([[T("Empena", "Pignon"), T("Base m", "Base m"), T("Altura m", "Hauteur m"), T("Área m²", "Surface m²")]]
                       + [[g["wall"][:60], n(g["base"]), n(g["height"]), n(g["net_m2"])] for g in wd["gables"]], (100, 25, 25, 24)))
    return s


# ------------------------------------------------------------------ geometria real das plantas (motor de paredes CLT)
def wall_floors(raw: dict) -> list[tuple[dict, list]]:
    """Eixos das paredes de cada piso a partir das plantas lidas (fachadas = contorno exterior, paredes interiores =
    retângulos desenhados), no formato do motor de paredes da conta CLT (bim_studio.clt_walls.WallAxis)."""
    from bim_studio.clt_walls import Opening, WallAxis
    env = raw.get("envelope") or {}
    L, W = _num(env.get("length_x"), 10), _num(env.get("width_y"), 8)
    t = min(0.5, _num(env.get("wall_total_thickness"), 0.30))
    lvls = _levels(raw)
    roof = raw.get("roof") or {}
    eaves = _num(roof.get("eaves_level"), (lvls[-1]["floor_top"] + 2.9) if lvls else 2.9)
    sides = _sides(raw, L, W)
    h_in = t / 2
    out = []
    for i, lv in enumerate(lvls):
        h = round(_level_height(lvls, i, eaves), 3)
        axes = []
        for name, (ax, pos, length, n, kind, label) in sides.items():
            if ax == "x":
                c = min(max(pos, h_in), L - h_in)
                x1, y1, x2, y2 = c, h_in, c, W - h_in
            else:
                c = min(max(pos, h_in), W - h_in)
                x1, y1, x2, y2 = h_in, c, L - h_in, c
            start = y1 if ax == "x" else x1
            span = math.hypot(x2 - x1, y2 - y1)
            ops = []
            for o in raw.get("openings") or []:
                if not isinstance(o, dict) or o.get("side") != name or o.get("level") != lv.get("id"):
                    continue
                a, b = sorted((_num(o.get("from")), _num(o.get("to"))))
                off, wd = max(0.0, a - start), b - a
                sill, oh = max(0.0, _num(o.get("sill"))), _num(o.get("height"), 1.2)
                if wd <= 0.05 or off + wd > span or sill + oh > h:
                    continue
                if any(off < e and off + wd > s for s, e in ((p.offset_m, p.offset_m + p.width_m) for p in ops)):
                    continue
                door = sill < 0.05 and "jan" not in str(o.get("kind") or "").lower()
                ops.append(Opening(offset_m=round(off, 3), width_m=round(wd, 3), sill_m=round(sill, 3), height_m=round(oh, 3),
                                   kind="porta" if door else "janela", label=str(o.get("id") or "")[:60]))
            try:
                axes.append(WallAxis(id=f"E-{name}"[:40], x1=x1, y1=y1, x2=x2, y2=y2, thickness_mm=round(t * 1000), height_m=h,
                                     base_z_m=lv["floor_top"], openings=ops, source=f"fachada {label}"[:200]))
            except ValueError:
                pass
        for k, w in enumerate((raw.get("interior_walls") or {}).get(lv.get("id"), []) or []):
            try:
                x0, y0, x1_, y1_ = (_num(w[c]) for c in ("x0", "y0", "x1", "y1"))
            except (KeyError, TypeError):
                continue
            dx, dy = abs(x1_ - x0), abs(y1_ - y0)
            th = max(0.05, min(dx, dy, 0.5))
            if dx >= dy:
                cy_ = (y0 + y1_) / 2
                a = (min(x0, x1_), cy_, max(x0, x1_), cy_)
            else:
                cx_ = (x0 + x1_) / 2
                a = (cx_, min(y0, y1_), cx_, max(y0, y1_))
            try:
                axes.append(WallAxis(id=f"I{k + 1}-{lv.get('id')}"[:40], x1=a[0], y1=a[1], x2=a[2], y2=a[3], thickness_mm=round(th * 1000),
                                     height_m=round(_num(lv.get("ceiling_height"), 2.6), 3), base_z_m=lv["floor_top"],
                                     source=str(w.get("kind") or "parede interior")[:200]))
            except ValueError:
                pass
        if axes:
            out.append((lv, axes))
    return out


def takeoff(raw: dict) -> list[dict]:
    """Medição das paredes piso a piso com o motor da conta CLT: juntas L/T/X resolvidas (sem contagem dupla), peças,
    e verificação cruzada (eixos desenhados / união das plantas GEOS / peças) — sem o limite de formato de prensa CLT."""
    from shapely import union_all

    from bim_studio import clt_walls as CW
    from bim_studio.clt_geometry import reconciliation
    out = []
    for lv, axes in wall_floors(raw):
        try:
            floor = CW.Floor(name=str(lv.get("name") or lv.get("id"))[:60], walls=axes)
            production, _splits = CW.pieces(floor, max_length_m=1000.0)
            feet = CW.footprints(floor.walls)
            by_t = {}
            for w in floor.walls:
                by_t.setdefault(w.thickness_mm, []).append(w)
            union_length = sum(union_all([feet[w.id] for w in g]).area / (tm / 1000) for tm, g in by_t.items())
            gross_volume = sum(feet[w.id].area * w.height_m for w in floor.walls)
            fp_volume = gross_volume - CW._overlap_volume(floor.walls, feet)
            piece_volume = sum(p["volume_bruto_m3"] for p in production)
            check = reconciliation(piece_volume, fp_volume, zero_tolerance=1e-6)
            joints = CW._junctions(floor.walls)
            kinds = {}
            for j in joints:
                kinds[j.get("tipo") or j.get("type") or "?"] = kinds.get(j.get("tipo") or j.get("type") or "?", 0) + 1
            out.append({"level": floor.name, "axes": axes, "feet": feet, "pieces": production, "joints": kinds,
                        "drawn_m": round(sum(w.length for w in floor.walls), 3), "union_m": round(union_length, 3),
                        "pieces_m": round(sum(p["comprimento_m"] for p in production), 3),
                        "double_count_m3": round(gross_volume - fp_volume, 4), "check": check,
                        "gross_m2": round(sum(p["area_bruta_m2"] for p in production), 3),
                        "openings_m2": round(sum(p["area_vaos_m2"] for p in production), 3),
                        "net_m2": round(sum(p["area_liquida_m2"] for p in production), 3),
                        "volume_m3": round(sum(p["volume_liquido_m3"] for p in production), 4)})
        except Exception as exc:  # noqa: BLE001 — um piso ilegível não impede os outros
            out.append({"level": str(lv.get("name") or lv.get("id")), "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
    return out


def plan_png(raw: dict, floor: dict, width: int = 1500, accent=(21, 128, 61)) -> bytes:
    """Planta das paredes medidas de um piso (pegadas reais, vãos, divisões), como a « planta das paredes CLT »."""
    from PIL import Image, ImageDraw, ImageFont
    env = raw.get("envelope") or {}
    L, W = _num(env.get("length_x"), 10), _num(env.get("width_y"), 8)
    m = 110
    sc = (width - 2 * m) / max(L, W * 1.0)
    H = int(W * sc + 2 * m)
    img = Image.new("RGB", (width, H), (250, 249, 246))
    d = ImageDraw.Draw(img)
    try:
        from engines.calc_lots.gros_oeuvre import _fontes
        fr, fb = _fontes()
        f1, f2 = ImageFont.truetype(fr, 20), ImageFont.truetype(fb, 22)
    except Exception:  # noqa: BLE001
        f1 = f2 = ImageFont.load_default()

    def T(x, y):
        return (m + x * sc, m + (W - y) * sc)
    lv = next((l for l in _levels(raw) if str(l.get("name") or l.get("id")) == floor["level"]), None)
    for r in (raw.get("rooms") or {}).get((lv or {}).get("id"), []) or []:
        try:
            a, b = T(_num(r["x0"]), _num(r["y1"])), T(_num(r["x1"]), _num(r["y0"]))
            d.rectangle([a, b], fill=(240, 236, 226))
            nm = str(r.get("name") or "")[:22]
            if abs(b[0] - a[0]) < 120 or abs(b[1] - a[1]) < 60:
                nm = nm[:10]
            area = _num(r.get("area_pc")) or abs((_num(r["x1"]) - _num(r["x0"])) * (_num(r["y1"]) - _num(r["y0"])))
            cxp, cyp = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            d.text((cxp, cyp - 12), nm, fill=(80, 80, 80), font=f1, anchor="mm")
            d.text((cxp, cyp + 14), f"{area:.1f} m²".replace(".", ","), fill=(120, 120, 120), font=f1, anchor="mm")
        except (KeyError, TypeError, ValueError):
            continue
    for w in floor.get("axes") or []:
        poly = floor["feet"][w.id]
        d.polygon([T(x, y) for x, y in poly.exterior.coords], fill=(52, 56, 60) if w.id.startswith("E-") else (110, 116, 120))
        ux, uy = w.direction()
        nx_, ny_ = -uy, ux
        for o in w.openings:
            s0, s1 = o.offset_m, o.offset_m + o.width_m
            hw = w.thickness_m / 2 + 0.01
            q = [(w.x1 + ux * s0 + nx_ * hw, w.y1 + uy * s0 + ny_ * hw), (w.x1 + ux * s1 + nx_ * hw, w.y1 + uy * s1 + ny_ * hw),
                 (w.x1 + ux * s1 - nx_ * hw, w.y1 + uy * s1 - ny_ * hw), (w.x1 + ux * s0 - nx_ * hw, w.y1 + uy * s0 - ny_ * hw)]
            d.polygon([T(*p) for p in q], fill=(255, 255, 255) if o.kind == "porta" else (150, 196, 222))
        mx, my = (w.x1 + w.x2) / 2, (w.y1 + w.y2) / 2
        if w.id.startswith("E-"):
            ox_, oy_ = (mx - L / 2), (my - W / 2)
            k_ = math.hypot(ox_, oy_) or 1
            lab = (w.source or w.id).replace("fachada ", "")
            lab = (lab.split("(")[0].strip() or w.id)[:24]
            d.text(T(mx + ox_ / k_ * 0.0, my + oy_ / k_ * 0.0), "", font=f2)
            px, py = T(mx, my)
            px += (ox_ / k_) * 40
            py -= (oy_ / k_) * 40
            d.text((px, py), lab, fill=accent, font=f2, anchor="mm")
    d.line([T(0, -0.35), T(L, -0.35)], fill=(90, 90, 90), width=2)                  # cota geral
    d.text(T(L / 2, -0.55), f"{L:.2f} m".replace(".", ","), fill=(60, 60, 60), font=f1, anchor="mm")
    d.line([T(L + 0.35, 0), T(L + 0.35, W)], fill=(90, 90, 90), width=2)
    d.text(T(L + 0.75, W / 2), f"{W:.2f} m".replace(".", ","), fill=(60, 60, 60), font=f1, anchor="mm")
    b = io.BytesIO()
    img.save(b, "PNG", optimize=True)
    return b.getvalue()


def cutaway_png(raw: dict, floor: dict, width: int = 1600, height: int = 1000) -> bytes:
    """Vista 3D em corte do piso (paredes reais extrudidas, sem cobertura) — a planta em volume."""
    from PIL import Image, ImageDraw, ImageFilter
    SS = 2
    Wp, Hp = width * SS, height * SS
    env = raw.get("envelope") or {}
    L, W = _num(env.get("length_x"), 10), _num(env.get("width_y"), 8)
    C, Sn = math.cos(math.radians(30)), math.sin(math.radians(30))
    axes = floor.get("axes") or []
    hmax = max((w.height_m for w in axes), default=2.7)
    cut = min(hmax, 2.2)                                           # paredes cortadas a 2,20 m para ver o interior

    def proj(x, y, z):
        return ((x - y) * C, (x + y) * Sn * 0.9 - z * 1.0)
    pts = [proj(x, y, z) for x in (0, L) for y in (0, W) for z in (0, cut)]
    u0, u1 = min(p[0] for p in pts), max(p[0] for p in pts)
    v0, v1 = min(p[1] for p in pts), max(p[1] for p in pts)
    sc = min(Wp * 0.8 / (u1 - u0), Hp * 0.78 / (v1 - v0))
    ox, oy = Wp / 2 - (u0 + u1) / 2 * sc, Hp * 0.52 - (v0 + v1) / 2 * sc

    def P(x, y, z):
        u, v = proj(x, y, z)
        return (ox + u * sc, oy + v * sc)
    img = Image.new("RGB", (Wp, Hp))
    dr = ImageDraw.Draw(img)
    for yy in range(Hp):
        k_ = yy / Hp
        dr.line([(0, yy), (Wp, yy)], fill=(int(236 - 12 * k_), int(238 - 12 * k_), int(240 - 14 * k_)))
    sh = Image.new("L", (Wp, Hp), 0)
    ImageDraw.Draw(sh).polygon([P(0.4, 0.4, -0.05), P(L + 0.6, 0.4, -0.05), P(L + 0.6, W + 0.8, -0.05), P(0.4, W + 0.8, -0.05)], fill=120)
    img.paste((90, 94, 98), (0, 0), sh.filter(ImageFilter.GaussianBlur(24 * SS)))
    dr = ImageDraw.Draw(img)
    dr.polygon([P(0, 0, 0), P(L, 0, 0), P(L, W, 0), P(0, W, 0)], fill=(206, 186, 150))           # pavimento
    for q in range(1, int(L / 0.2)):                                                              # réguas do flutuante
        x_ = q * 0.2
        dr.line([P(x_, 0, 0.001), P(x_, W, 0.001)], fill=(194, 172, 134), width=SS)
    lv = next((l for l in _levels(raw) if str(l.get("name") or l.get("id")) == floor["level"]), None)
    blocks = []
    for w in axes:
        poly = floor["feet"][w.id]
        cs = list(poly.exterior.coords)[:-1]
        top = [(x, y, cut) for x, y in cs]
        dep = sum(x + y for x, y in cs) / len(cs)
        blocks.append((dep, w, cs, top))
    for dep, w, cs, top in sorted(blocks, key=lambda b: b[0]):
        ext = w.id.startswith("E-")
        side = (214, 206, 192) if ext else (232, 228, 220)
        for a, b in zip(cs, cs[1:] + cs[:1]):
            nx_, ny_ = (b[1] - a[1]), -(b[0] - a[0])
            if nx_ + ny_ <= 0:                                         # só as faces voltadas para a câmara
                continue
            shade = 0.86 if nx_ > ny_ else 1.0
            dr.polygon([P(a[0], a[1], 0), P(b[0], b[1], 0), P(b[0], b[1], cut), P(a[0], a[1], cut)],
                       fill=tuple(int(c * shade) for c in side))
        dr.polygon([P(*p) for p in top], fill=(70, 74, 78) if ext else (120, 124, 128))          # corte da parede
    b = io.BytesIO()
    img.resize((width, height), Image.LANCZOS).save(b, "PNG", optimize=True)
    return b.getvalue()


def plans_flowables(images: list, accent: str, lang: str = "") -> list:
    """Páginas « Plantas do projeto »: cada página das plantas juntas, em grande, com o nome do ficheiro."""
    from io import BytesIO

    from PIL import Image
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import PageBreak, Paragraph, Spacer
    from engines.pdf_fonts import F
    lg = str(lang or "").lower()
    fr = lg.startswith("fr") or lg == "fr_true"
    en = lg.startswith("en")
    title = "Plans du projet" if fr else ("Project drawings" if en else "Plantas do projeto")
    sub = ("Plans joints à la demande, utilisés pour le métré et le devis." if fr else
           "Drawings attached to the request, used for the take-off and the quote." if en else
           "Plantas juntas ao pedido, usadas na medição e no orçamento.")
    H1 = ParagraphStyle("pl_h1", fontName=F("Helvetica-Bold"), fontSize=16, leading=20,
                        textColor=colors.HexColor("#1B2430"), spaceAfter=4)
    CAP = ParagraphStyle("pl_cap", fontName=F("Helvetica"), fontSize=8, leading=10,
                         textColor=colors.HexColor("#5B6573"))
    s: list = [PageBreak(), Paragraph(title, H1), Paragraph(sub, CAP), Spacer(1, 3 * mm)]
    maxw, maxh = 180 * mm, 225 * mm
    for i, (name, data) in enumerate(images):
        try:
            w, h = Image.open(BytesIO(data)).size
        except Exception:  # noqa: BLE001
            continue
        k = min(maxw / w, maxh / h)
        if i:
            s.append(PageBreak())
        s += [RLImage(BytesIO(data), width=w * k, height=h * k), Spacer(1, 2 * mm), Paragraph(str(name)[:120], CAP)]
    return s
