"""Mise en page premium des livrables bois massif : rendu 3D du bâtiment (calculé sur la trame, sans IA) et page de
couverture A4 (visuel pleine largeur, chiffres clés, verdicts) en tête du dossier et du devis final.

Le rendu est une axonométrie peinte au pinceau numérique : volumes par étage (emprise réelle, retraits), bardage bois
et joints de panneaux CLT, baies vitrées en façade principale, toiture gravillonnée, ombre portée douce, ciel en dégradé.
"""
from __future__ import annotations

import io
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from .lang import num, t

C30, S30 = math.cos(math.radians(30)), math.sin(math.radians(30))
WOOD = (196, 150, 98)
WOOD_D = (160, 116, 70)
WOOD_L = (222, 184, 136)
ROOF = (88, 92, 96)
GLASS = (54, 92, 120)


_GR = {}


def _GRAVEL(W, H):
    """Texture de gravillons (bruit fin), mise en cache par taille."""
    if (W, H) not in _GR:
        import random
        rnd = random.Random(7)
        im = Image.new("RGB", (W, H), ROOF)
        px = im.load()
        for _ in range(W * H // 18):
            x, y = rnd.randrange(W), rnd.randrange(H)
            g = rnd.randint(70, 150)
            px[x, y] = (g, g, g - 4)
        _GR[(W, H)] = im
    return _GR[(W, H)]


def _cells(m, lid):
    nx, ny = len(m.gx) - 1, len(m.gy) - 1
    with m.at_storey(lid):
        return {(i, j) for i in range(nx) for j in range(ny) if m.cell_in(i, j)}


_ROT = {"x1": "y0", "y1": "x1", "x0": "y1", "y0": "x0"}      # côté d'origine → côté après rotation du plan de 90°


def _south(m) -> str:
    glaz = (m.raw.get("envelope") or {}).get("glazing") or {}
    return max(glaz, key=lambda k_: glaz[k_]) if glaz else "y1"


def main_view(m) -> int:
    """Rotation (0–3) qui place la façade principale (la plus vitrée) en façade avant éclairée."""
    s = _south(m)
    for v in range(4):
        if s == "y1":
            return v
        s = _ROT[s]
    return 0


def _scene(m, view: int):
    """Trame, niveaux (cellules occupées) et façade principale, tournés de view × 90° : la géométrie calculée reste
    exacte, seule la caméra change de côté."""
    from types import SimpleNamespace as NS
    gx, gy = list(m.gx), list(m.gy)
    lv = [NS(z=l.z, height=l.height, cells=_cells(m, l.id)) for l in m.levels]
    south = _south(m)
    for _ in range(view % 4):
        nx = len(gx) - 1
        gx, gy = gy, [gx[0] + gx[-1] - v for v in reversed(gx)]
        for l in lv:
            l.cells = {(j, nx - 1 - i) for (i, j) in l.cells}
        south = _ROT[south]
    return gx, gy, lv, south


VIEWS = ("main", "side_main", "rear", "side_other", "aerial")


def render_views(m, r, folder: str | Path, stem: str = "Vue") -> list[tuple[str, Path]]:
    """Rendus calculés sous plusieurs points de vue (même modèle, même géométrie) : principale, latérales, arrière,
    aérienne. Renvoie [(clé de vue, chemin PNG)]."""
    v0 = main_view(m)
    s = _south(m)
    for _ in range(v0 + 1):
        s = _ROT[s]
    side_main = (v0 + 1) % 4 if s == "x1" else (v0 + 3) % 4      # latérale où la façade principale reste visible
    rots = {"main": v0, "side_main": side_main, "rear": (v0 + 2) % 4, "side_other": (side_main + 2) % 4, "aerial": v0}
    folder = Path(folder)
    out = []
    for k in VIEWS:
        out.append((k, render_hero(m, r, folder / f"{stem}_{k}.png", view=rots[k], aerial=(k == "aerial"))))
    return out


def view_label(k: str) -> str:
    return {"main": t("Perspective principale", "Perspetiva principal", "Main perspective", "Основна перспектива"),
            "side_main": t("Perspective latérale", "Perspetiva lateral", "Side perspective", "Бічна перспектива"),
            "rear": t("Perspective arrière", "Perspetiva posterior", "Rear perspective", "Задня перспектива"),
            "side_other": t("Perspective latérale opposée", "Perspetiva lateral oposta", "Opposite side perspective", "Протилежна бічна перспектива"),
            "aerial": t("Vue aérienne", "Vista aérea", "Aerial view", "Вигляд з висоти")}[k]


def render_hero(m, r, path: str | Path, W: int = 3200, H: int = 1800, view: int | None = None, aerial: bool = False) -> Path:
    """Axonométrie du bâtiment, PNG haute définition. `view` : rotation 0–3 du point de vue (par défaut la façade
    principale devant) ; `aerial` : caméra plus haute (vue plongeante)."""
    view = main_view(m) if view is None else view
    KY, KZ = ((0.78, 0.62) if aerial else (S30, 1.0))           # profondeur / hauteur projetées
    S = 2                                                     # sur-échantillonnage (anticrénelage)
    Wp, Hp = W * S, H * S
    img = Image.new("RGB", (Wp, Hp))
    sky = ImageDraw.Draw(img)
    for y in range(Hp):                                       # ciel : bleu profond → horizon doré → sol clair
        k = y / Hp
        if k < 0.55:
            f = k / 0.55
            col = (int(120 + 125 * f), int(160 + 75 * f), int(205 + 20 * f))
        else:
            f = (k - 0.55) / 0.45
            col = (int(245 - 40 * f), int(235 - 25 * f), int(225 - 35 * f))
        sky.line([(0, y), (Wp, y)], fill=col)
    gx, gy, LV, south = _scene(m, view)
    zs = [lv.z for lv in LV] + [LV[-1].z + LV[-1].height]
    def proj(x, y, z):
        return ((x - y) * C30, (x + y) * KY - z * KZ)
    corners = [proj(x, y, z) for x in (gx[0], gx[-1]) for y in (gy[0], gy[-1]) for z in (0, zs[-1] + 0.3)]
    u0, u1 = min(c[0] for c in corners), max(c[0] for c in corners)
    v0, v1 = min(c[1] for c in corners), max(c[1] for c in corners)
    sc = min(Wp * 0.66 / (u1 - u0), Hp * 0.70 / (v1 - v0))
    cx0 = Wp * 0.5 - (u0 + u1) / 2 * sc
    cy0 = Hp * 0.53 - (v0 + v1) / 2 * sc

    def P(x, y, z):
        return (cx0 + (x - y) * C30 * sc, cy0 + (x + y) * KY * sc - z * KZ * sc)

    # sol + ombre portée douce
    ground = Image.new("L", (Wp, Hp), 0)
    gd = ImageDraw.Draw(ground)
    pad = 2.5
    gd.polygon([P(gx[0] - pad, gy[0] - pad, 0), P(gx[-1] + pad, gy[0] - pad, 0), P(gx[-1] + pad, gy[-1] + pad, 0), P(gx[0] - pad, gy[-1] + pad, 0)], fill=255)
    ground = ground.filter(ImageFilter.GaussianBlur(28 * S))
    img.paste(Image.new("RGB", (Wp, Hp), (205, 210, 196)), (0, 0), ground)
    sh = Image.new("L", (Wp, Hp), 0)
    sd = ImageDraw.Draw(sh)
    off = zs[-1] * 0.55
    for k, lv in enumerate(LV):
        for (i, j) in lv.cells:
            sd.polygon([P(gx[i] + off, gy[j] + off * 0.2, 0), P(gx[i + 1] + off, gy[j] + off * 0.2, 0), P(gx[i + 1] + off, gy[j + 1] + off * 0.2, 0),
                        P(gx[i] + off, gy[j + 1] + off * 0.2, 0), P(gx[i], gy[j + 1], 0), P(gx[i], gy[j], 0)], fill=110)
    sh = sh.filter(ImageFilter.GaussianBlur(22 * S))
    img.paste(Image.new("RGB", (Wp, Hp), (70, 74, 70)), (0, 0), sh)
    d = ImageDraw.Draw(img)
    def tree(x, y, h=6.5, rad=1.9):
        bx, by = P(x, y, 0)
        dd = ImageDraw.Draw(img)
        dd.ellipse([bx - rad * sc * 0.9, by - rad * sc * 0.35, bx + rad * sc * 0.9, by + rad * sc * 0.35], fill=(150, 156, 140))
        tx = P(x, y, h * 0.45)
        dd.line([P(x, y, 0), tx], fill=(92, 70, 50), width=int(0.25 * sc))
        for k_, (dz, rr, col) in enumerate(((0.55, 1.0, (64, 110, 70)), (0.75, 0.85, (82, 134, 84)), (0.92, 0.6, (108, 160, 100)))):
            cxp, cyp = P(x, y, h * dz)
            rp = rad * rr * sc
            dd.ellipse([cxp - rp, cyp - rp, cxp + rp, cyp + rp], fill=col)
    span_x, span_y = gx[-1] - gx[0], gy[-1] - gy[0]
    tree(gx[0] - 2.5, gy[0] - 1.0)                              # arbre à l'arrière (dessiné avant le bâtiment)
    tree(gx[-1] + 1.5, gy[0] + span_y * 0.25, h=5.5, rad=1.6)
    # terrasse bois devant la façade principale (de quelque côté qu'elle soit)
    dk = ImageDraw.Draw(img)
    def deck(c0, c1, a0, a1, horiz):
        Q = (lambda a, b, z: P(a, b, z)) if horiz else (lambda a, b, z: P(b, a, z))
        dk.polygon([Q(c0, a0, 0.05), Q(c1, a0, 0.05), Q(c1, a1, 0.05), Q(c0, a1, 0.05)], fill=(176, 132, 88))
        for q in range(1, 14):
            aa = a0 + (a1 - a0) * q / 14
            dk.line([Q(c0, aa, 0.06), Q(c1, aa, 0.06)], fill=(150, 108, 68), width=max(1, S))
    {"y1": lambda: deck(gx[0], gx[-1], gy[-1], gy[-1] + 2.6, True), "y0": lambda: deck(gx[0], gx[-1], gy[0] - 2.6, gy[0], True),
     "x1": lambda: deck(gy[0], gy[-1], gx[-1], gx[-1] + 2.6, False), "x0": lambda: deck(gy[0], gy[-1], gx[0] - 2.6, gx[0], False)}[south]()
    # volumes, du plus loin au plus proche
    boxes = []
    for k, lv in enumerate(LV):
        cells = lv.cells
        up = LV[k + 1].cells if k + 1 < len(LV) else set()
        for (i, j) in cells:
            boxes.append((lv.z, gx[i] + gy[j], i, j, k, cells, up))
    boxes.sort(key=lambda b: (b[1], b[0]))
    for z0, _d, i, j, k, cells, up in boxes:
        lv = LV[k]
        z1 = z0 + lv.height
        x0, x1, y0, y1 = gx[i], gx[i + 1], gy[j], gy[j + 1]
        # façade x1 (droite, ombrée) et y1 (gauche-avant, éclairée)
        faces = []
        if (i + 1, j) not in cells:
            faces.append(("x1", [P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1), P(x1, y0, z1)], WOOD_D, (y0, y1), x1))
        if (i, j + 1) not in cells:
            faces.append(("y1", [P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, z1), P(x0, y1, z1)], WOOD, (x0, x1), y1))
        for side, poly, col, (a0, a1), cst in faces:
            d.polygon(poly, fill=col)
            # joints de panneaux CLT / bardage (tous les 0,6 m)
            n = max(1, int((a1 - a0) / 0.6))
            for q in range(1, n):
                a = a0 + (a1 - a0) * q / n
                p0, p1 = (P(cst, a, z0), P(cst, a, z1)) if side == "x1" else (P(a, cst, z0), P(a, cst, z1))
                d.line([p0, p1], fill=tuple(max(0, c - 18) for c in col), width=max(1, S))
            # baies : grandes sur la façade principale, fenêtres ailleurs
            big = side == south                                 # grandes baies seulement sur la vraie façade vitrée
            wz0, wz1 = (z0 + 0.15, z1 - 0.45) if big else (z0 + 0.95, z1 - 0.55)
            step = 2.4 if big else 3.2
            nw = max(1, int((a1 - a0) / step))
            for q in range(nw):
                aa = a0 + (a1 - a0) * (q + 0.5) / nw
                hw = (a1 - a0) / nw * (0.42 if big else 0.22)
                pts = ([P(cst, aa - hw, wz0), P(cst, aa + hw, wz0), P(cst, aa + hw, wz1), P(cst, aa - hw, wz1)] if side == "x1"
                       else [P(aa - hw, cst, wz0), P(aa + hw, cst, wz0), P(aa + hw, cst, wz1), P(aa - hw, cst, wz1)])
                d.polygon(pts, fill=GLASS if side == "y1" else (40, 70, 92), outline=(40, 40, 38), width=max(1, S))
                # reflet
                d.line([pts[0], pts[2]], fill=(120, 160, 186), width=max(1, S))
            # nez de plancher
            d.line([P(*((cst, a0, z1) if side == "x1" else (a0, cst, z1))), P(*((cst, a1, z1) if side == "x1" else (a1, cst, z1)))],
                   fill=(70, 52, 34), width=3 * S)
        if (i, j) not in up:                                   # toiture (terrasse gravillonnée + acrotère)
            poly = [P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1)]
            d.polygon(poly, fill=ROOF)
            mask = Image.new("L", (Wp, Hp), 0)
            ImageDraw.Draw(mask).polygon(poly, fill=70)
            img.paste(_GRAVEL(Wp, Hp), (0, 0), mask)
            d = ImageDraw.Draw(img)
            roofs = {(a_, b_) for (a_, b_) in cells if (a_, b_) not in up}
            for (nb, a, b) in (((i, j + 1), (x0, y1), (x1, y1)), ((i + 1, j), (x1, y0), (x1, y1)),
                               ((i, j - 1), (x0, y0), (x1, y0)), ((i - 1, j), (x0, y0), (x0, y1))):
                if nb not in roofs:
                    d.polygon([P(a[0], a[1], z1), P(b[0], b[1], z1), P(b[0], b[1], z1 + 0.3), P(a[0], a[1], z1 + 0.3)], fill=WOOD_L)
    tree(gx[-1] + 4.5, gy[-1] - 0.5, h=7.0, rad=2.2)          # arbre au premier plan
    tree(gx[0] - 1.8, gy[-1] + 4.2, h=4.8, rad=1.5)
    out = img.resize((W, H), Image.LANCZOS)
    path = Path(path)
    out.save(path, "PNG", optimize=True)
    return path


def _co2(r) -> float:
    q = r["quantities"]
    return round((q["clt_m3"] + q["wall_m3"] + q["gl_beams_m3"] + q["gl_cols_m3"]) * 0.9, 1)   # ≈ 0,9 t CO₂ stockées / m³ de résineux


def cover(path, m, r, kpis: list[tuple[str, str]], title: str, subtitle: str, hero: Path | None = None) -> Path:
    """Page de couverture A4 pleine page : bandeau couleur de l'entreprise, visuel 3D, chiffres clés."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    from engines.bet_core import brand as B
    br = B.get()
    W, H = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    # fond : couleur d'accent en dégradé vertical
    a = br.accent
    for k in range(120):
        f = k / 119
        c.setFillColor(colors.Color(a.red * (1 - 0.35 * f), a.green * (1 - 0.35 * f), a.blue * (1 - 0.35 * f)))
        c.rect(0, H - (k + 1) * H / 120, W, H / 120 + 0.5, stroke=0, fill=1)
    B.draw_logo(c, 18 * mm, H - 30 * mm, 70 * mm, 16 * mm, br, on_dark=True)
    c.setFillColor(colors.white)
    c.setFont("DV", 8.5)
    c.drawRightString(W - 18 * mm, H - 20 * mm, t("Bureau d'études intégré", "Gabinete de engenharia integrado", "Integrated engineering office",
                                                  "Інтегроване проєктне бюро"))
    c.drawRightString(W - 18 * mm, H - 25 * mm, __import__("datetime").date.today().strftime("%d/%m/%Y"))
    # visuel
    if hero and Path(hero).exists():
        hw = W - 24 * mm
        hh = hw * 1350 / 2400
        y = H - 40 * mm - hh
        c.saveState()
        p = c.beginPath()
        p.roundRect(12 * mm, y, hw, hh, 6 * mm)
        c.clipPath(p, stroke=0, fill=0)
        c.drawImage(str(hero), 12 * mm, y, hw, hh)
        c.restoreState()
    else:
        y = H - 120 * mm
    # titres
    c.setFillColor(colors.white)
    c.setFont("TT", 30)
    c.drawString(18 * mm, y - 18 * mm, title[:48])
    c.setFont("DVM", 12)
    c.drawString(18 * mm, y - 26 * mm, subtitle[:95])
    c.setFont("DV", 9)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.8))
    c.drawString(18 * mm, y - 32 * mm, f"{m.project.get('name', '')} — {m.project.get('address', '')}"[:110])
    # cartes de chiffres clés (2 × 3)
    cw, ch = (W - 36 * mm - 2 * 6 * mm) / 3, 24 * mm
    top = y - 42 * mm
    for n, (lab, val) in enumerate(kpis[:6]):
        col, row = n % 3, n // 3
        x0 = 18 * mm + col * (cw + 6 * mm)
        y0 = top - (row + 1) * ch - row * 5 * mm
        c.setFillColor(colors.Color(1, 1, 1, alpha=0.10))
        c.setStrokeColor(colors.Color(1, 1, 1, alpha=0.25))
        c.roundRect(x0, y0, cw, ch, 3 * mm, stroke=1, fill=1)
        c.setFillColor(br.accent2)
        c.rect(x0, y0 + ch - 1.2 * mm, cw, 1.2 * mm, stroke=0, fill=1)
        c.setFillColor(colors.Color(1, 1, 1, alpha=0.75))
        c.setFont("DVM", 7.6)
        c.drawString(x0 + 4 * mm, y0 + ch - 7 * mm, lab.upper()[:38])
        c.setFillColor(colors.white)
        size = 17
        while size > 9 and c.stringWidth(val, "TT", size) > cw - 8 * mm:
            size -= 0.5
        c.setFont("TT", size)
        c.drawString(x0 + 4 * mm, y0 + 5.5 * mm, val)
    c.setFont("DV", 7)
    c.setFillColor(colors.Color(1, 1, 1, alpha=0.65))
    c.drawString(18 * mm, 12 * mm, t("Pré-dimensionnement déterministe EN 1995 — à viser par un ingénieur structure habilité avant exécution.",
                                     "Pré-dimensionamento determinístico EN 1995 — a verificar por engenheiro de estruturas habilitado antes da execução.",
                                     "Deterministic EN 1995 preliminary design — to be checked by a licensed structural engineer before construction.",
                                     "Детермінований попередній розрахунок EN 1995 — перевіряє атестований інженер-конструктор."))
    c.drawRightString(W - 18 * mm, 12 * mm, (br.name or "ConstruPilot")[:40])
    c.showPage()
    c.save()
    return Path(path)


def study_kpis(m, r, tot, rev) -> list[tuple[str, str]]:
    q = r["quantities"]
    th = r.get("thermal") or {}
    k = [(t("Bois massif CLT / GL", "Madeira maciça CLT / GL", "Mass timber CLT / GL", "Масивна деревина CLT / GL"),
          f"{num(q['clt_m3'] + q['wall_m3'] + q['gl_beams_m3'] + q['gl_cols_m3'], 1)} m³"),
         (t("CO₂ stocké (≈)", "CO₂ armazenado (≈)", "CO₂ stored (≈)", "Накопичений CO₂ (≈)"), f"{num(_co2(r), 0)} t"),
         (t("Surface de plancher", "Área de pavimento", "Floor area", "Площа перекриттів"),
          f"{num(sum(f['area'] for f in r['floors'] if not f['roof']) + (r['floors'][0]['area'] if r['floors'] else 0), 0)} m²")]
    if th.get("reh"):
        k.append((t("Classe énergétique", "Classe energética", "Energy class", "Енергетичний клас"), str(th["reh"]["classe"])))
    elif th.get("re2020") and "error" not in th["re2020"]:
        k.append(("RE2020", f"Bbio {num(th['re2020']['Bbio'], 0)} · " + (t("conforme", "conforme", "compliant", "відповідає") if th["re2020"].get("conforme")
                                                                       else t("à reprendre", "a rever", "to revise", "доопрацювати"))))
    else:
        k.append((t("Résistance au feu", "Resistência ao fogo", "Fire rating", "Вогнестійкість"), f"R{r['R']}"))
    k.append((t("Structure + fondations", "Estrutura + fundações", "Structure + foundations", "Конструкції + фундаменти"),
              f"{num(tot['ht'], 0)} € " + t("HT", "s/IVA", "excl. VAT", "без ПДВ")))
    k.append((t("Contrôle", "Controlo", "Check", "Перевірка"), str(rev["status"])[:22]))
    return k


def estimate_chart(e: dict, path: str | Path) -> Path:
    """Anneau de répartition du devis par lot (PNG)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from engines.bet_core import brand as B
    br = B.get()
    lots = {}
    for x in e["lines"]:
        lots[x["lot"]] = lots.get(x["lot"], 0.0) + x["tot"]
    for x in e["extra"]:
        lots[x["lab"]] = x["tot"]
    labs, vals = list(lots), list(lots.values())
    base = (br.accent.red, br.accent.green, br.accent.blue)
    pal = [tuple(min(1, c + (1 - c) * k / (len(vals) + 1)) for c in base) for k in range(len(vals))]
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=220)
    wedges, _ = ax.pie(vals, colors=pal, startangle=90, counterclock=False, wedgeprops={"width": 0.36, "edgecolor": "white", "linewidth": 1.4})
    ax.text(0, 0.08, f"{e['ht'] / 1e6:.2f} M".replace(".", ","), ha="center", va="center", fontsize=17, fontweight="bold", color=base)
    ax.text(0, -0.16, t("грн HT", "грн s/IVA", "UAH excl. VAT", "грн без ПДВ"), ha="center", va="center", fontsize=9, color="#555")
    ax.legend(wedges, [f"{100 * v / e['ht']:.0f} %  {lab.split('. ', 1)[-1][:40]}" for lab, v in zip(labs, vals)], loc="center left", bbox_to_anchor=(1.0, 0.5),
              frameon=False, fontsize=7.4)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(str(path), transparent=True)
    plt.close(fig)
    return Path(path)


def prepend(cover_pdf: Path, target_pdf: Path) -> None:
    from pypdf import PdfReader, PdfWriter
    w = PdfWriter()
    for f in (cover_pdf, target_pdf):
        for pg in PdfReader(str(f)).pages:
            w.add_page(pg)
    tmp = Path(str(target_pdf) + ".tmp")
    with open(tmp, "wb") as fh:
        w.write(fh)
    tmp.replace(target_pdf)


PHOTO_PROMPT = (
    "Photorealistic architectural exterior visualization of EXACTLY the building in the first reference image. "
    "GEOMETRY IS LOCKED: keep the exact massing, footprint, proportions, number of storeys, every setback and roof terrace, "
    "the roof outline, the position, count and size of every window and glazed bay, and the very same camera position, "
    "angle and framing as the first reference image. Do not add, remove, move or resize any volume, opening or storey; "
    "where the reference shows a blind wall keep a blind wall. Contemporary cross-laminated-timber (CLT) building: natural "
    "larch vertical timber cladding, floor-to-ceiling glazing with slim black aluminium frames where the reference shows "
    "large glazing, flat gravel roof with thin timber parapet, timber deck where the reference shows a deck, landscaped "
    "garden with lawn, gravel path and mature trees, warm golden-hour sunlight, soft realistic shadows, warm interior "
    "lights behind the glass, blue sky with soft clouds. Indistinguishable from a real photograph: shot on a full-frame "
    "camera, 24 mm tilt-shift lens, f/8, natural colour grading, real-world imperfections (subtle weathering, varied "
    "grass, natural foliage), physically accurate reflections and global illumination, magazine-grade architectural "
    "photography (Archdaily / Dezeen style). Not a 3D render look, no CGI plastic look. No text, no watermark, no people."
)
VIEW_HINT = {
    "main": "",
    "side_main": " This is a side three-quarter view of the same project.",
    "rear": " This is the rear three-quarter view of the same project.",
    "side_other": " This is the opposite side three-quarter view of the same project.",
    "aerial": " This is a high aerial (drone) view of the same project, looking down at the roofs.",
}
MATCH_HINT = (" The second reference image is the approved photorealistic render of the SAME building from another angle: "
              "match its materials, colours, landscaping and lighting exactly, but keep the geometry and camera of the first image.")


async def photoreal(base_png: bytes, timeout: float = 240.0, view: str = "main", style_ref: bytes | None = None) -> bytes | None:
    """Rendu photoréaliste du bâtiment à partir de l'axonométrie calculée (même volumétrie, même cadrage) — cascade
    GPT Image 2 / Nano Banana Pro / Runway Gen-4 / Nano Banana 3.1 (engines.photoreal), en 4K ; None si aucun moteur ne
    répond (le rendu calculé reste utilisé).
    `style_ref` : rendu photoréaliste déjà validé (autre point de vue) pour garder matériaux et lumière identiques."""
    try:
        from engines import photoreal as PR
        prompt = PHOTO_PROMPT + VIEW_HINT.get(view, "") + (MATCH_HINT if style_ref else "")
        res = await PR.render(base_png, prompt, style_ref=style_ref, feature="bet_clt_render", session_id="bet_clt")
        return res[0] if res else None
    except Exception:  # noqa: BLE001 — rendu IA facultatif
        return None


async def photoreal_views(bases: list[tuple[str, Path]], folder: str | Path, say=None) -> list[tuple[str, Path]]:
    """Version photoréaliste de chaque point de vue : la principale d'abord, puis les autres en parallèle en s'alignant
    sur elle. Toute vue non obtenue garde son rendu calculé (géométrie exacte)."""
    import asyncio
    folder = Path(folder)
    def keep(k, p, data):
        if not data:
            return (k, Path(p))
        ext = ".jpg" if data[:3] == b"\xff\xd8\xff" else ".png"
        q = folder / f"photo_{k}{ext}"
        q.write_bytes(data)
        return (k, q)
    base = dict(bases)
    main = await photoreal(Path(base["main"]).read_bytes(), view="main")
    res = {"main": keep("main", base["main"], main)}
    others = [k for k, _ in bases if k != "main"]
    outs = await asyncio.gather(*(photoreal(Path(base[k]).read_bytes(), view=k, style_ref=main) for k in others))
    for k, data in zip(others, outs):
        res[k] = keep(k, base[k], data)
    if say:
        n = sum(1 for k in res if res[k][1].name.startswith("photo_"))
        await say(f"Rendus photoréalistes : {n}/{len(res)} vues (les autres en rendu calculé, géométrie exacte)")
    return [res[k] for k, _ in bases]


def views_page(path, views: list[tuple[str, Path]], title: str) -> Path:
    """Planche A4 « Perspectives » : vue aérienne en grand + principale, latérales et arrière (même modèle calculé)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas

    from engines.bet_core import brand as B
    br = B.get()
    W, H = A4
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setFillColor(colors.Color(0.98, 0.97, 0.95))
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(br.accent)
    c.rect(0, H - 26 * mm, W, 26 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("TT", 20)
    c.drawString(14 * mm, H - 16 * mm, title[:60])
    c.setFont("DV", 8.5)
    c.drawRightString(W - 14 * mm, H - 16 * mm, t("Même modèle calculé, géométrie respectée", "Mesmo modelo calculado, geometria respeitada",
                                                  "Same computed model, geometry preserved", "Та сама розрахункова модель, геометрія збережена"))
    vd = dict(views)
    def tile(k, x0, y0, w, h):
        c.saveState()
        pa = c.beginPath()
        pa.roundRect(x0, y0, w, h, 3 * mm)
        c.clipPath(pa, stroke=0, fill=0)
        c.drawImage(str(vd[k]), x0, y0, w, h, preserveAspectRatio=False)
        c.restoreState()
        c.setFillColor(br.accent)
        c.rect(x0, y0 - 6.5 * mm, 1.2 * mm, 5 * mm, stroke=0, fill=1)
        c.setFillColor(colors.Color(0.15, 0.15, 0.15))
        c.setFont("DVM", 9)
        c.drawString(x0 + 3 * mm, y0 - 5.2 * mm, view_label(k))
    full = W - 28 * mm
    y = H - 32 * mm
    if "aerial" in vd:                                  # vue aérienne en grand, puis grille 2 × 2
        hh = full * 9 / 16 * 0.82
        y -= hh
        tile("aerial", 14 * mm, y, full, hh)
        y -= 12 * mm
    gap = 6 * mm
    cw = (full - gap) / 2
    ch = cw * 9 / 16
    for n, k in enumerate([k for k in ("main", "side_main", "rear", "side_other") if k in vd]):
        col, row = n % 2, n // 2
        tile(k, 14 * mm + col * (cw + gap), y - (row + 1) * ch - row * 12 * mm, cw, ch)
    c.setFont("DV", 7)
    c.setFillColor(colors.Color(0.4, 0.4, 0.4))
    c.drawString(14 * mm, 12 * mm, t("Visuels d'ambiance générés à partir du modèle structurel : volumes, niveaux et baies identiques au calcul.",
                                     "Imagens de ambiente geradas a partir do modelo estrutural: volumes, pisos e vãos idênticos ao cálculo.",
                                     "Mood images generated from the structural model: volumes, storeys and openings identical to the calculation.",
                                     "Візуалізації створені з конструктивної моделі: об'єми, поверхи та прорізи як у розрахунку."))
    c.drawRightString(W - 14 * mm, 12 * mm, (br.name or "ConstruPilot")[:40])
    c.showPage()
    c.save()
    return Path(path)
