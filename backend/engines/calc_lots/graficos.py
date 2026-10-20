"""(Versão PT) Graphiques vectoriels des notes de calcul (reportlab.graphics) — communs à tous les moteurs, sans dépendance au texte de la langue.

Palette catégorielle validée (ordre fixe : bleu, orange, aqua, jaune, magenta, vert, violet, rouge) ; couleurs d'état réservées aux
verdicts (conforme / à vérifier / non conforme), toujours accompagnées d'un libellé. Les étiquettes A→G suivent la convention du DPE.
Chaque fonction renvoie un Drawing de largeur `w` (points) prêt à insérer dans la note via le bloc ("chart", drawing[, légende]).
"""
from __future__ import annotations

import math

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String, Wedge
from reportlab.lib import colors
from reportlab.lib.units import mm

from . import rendu

C = lambda h: colors.HexColor(h)
SERIES = [C(h) for h in ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")]
OK, WARN, KO = C("#1f8a52"), C("#c98500"), C("#c8453c")
INK, INK2, MUTED, GRID, SURF = C("#1d2422"), C("#52514e"), C("#8a8a86"), C("#e3e3df"), C("#fafaf8")
BRAND = rendu.VERT
DPE_COULEURS = {"A": "#009c6d", "B": "#52b153", "C": "#a5cc74", "D": "#f4e70f", "E": "#f0b50f", "F": "#eb8235", "G": "#d7221f"}
GES_COULEURS = {"A": "#f6edfd", "B": "#e4c7fb", "C": "#d4a9f6", "D": "#cb95f3", "E": "#ba72ef", "F": "#a53ae4", "G": "#8a19c2"}
REH_COULEURS = {"A+": "#00804a", "A": "#2b9a3e", "B": "#8cc63f", "B-": "#cddc39", "C": "#fff200", "D": "#fbb03b", "E": "#f15a24", "F": "#c1272d"}
W_DEF = 180 * mm
LIB_USAGE = {"ecs": "AQS", "aqs": "AQS", "eclairage": "Iluminação", "auxiliaires": "Auxiliares", "chauffage": "Aquecimento", "aquecimento": "Aquecimento", "refroidissement": "Arrefecimento", "arrefecimento": "Arrefecimento"}


def usage(u):
    return LIB_USAGE.get(u, str(u).replace("_", " ").capitalize())


def _s(x, y, t, size=7, col=INK, anchor="start", bold=False):
    rendu.fonts()
    return String(x, y, rendu.txt(t), fontName="CP-Bold" if bold else "CP", fontSize=size, fillColor=col, textAnchor=anchor)


def _nice(v):
    """Borne supérieure « ronde » d'un axe."""
    if v <= 0:
        return 1.0
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * e + 1e-12:
            return m * e
    return 10 * e


def _fmt(v, dec=None):
    if dec is None:
        dec = 0 if abs(v) >= 100 else (1 if abs(v) >= 10 else 2)
    return f"{v:,.{dec}f}".replace(",", " ").replace(".", ",") if dec else f"{v:,.0f}".replace(",", " ")


def _titre(d, w, h, titre, unite=None):
    if titre:
        d.add(_s(0, h - 9, titre, 8.5, INK, bold=True))
        if unite:
            d.add(_s(w, h - 9, unite, 7, INK2, "end"))


def _legende(d, x, y, items, w):
    """Légende en ligne : pastille + libellé (l'identité n'est jamais portée par la seule couleur)."""
    cx = x
    for lab, col in items:
        tw = len(rendu.txt(lab)) * 3.7 + 16
        if cx + tw > x + w:
            cx, y = x, y - 10
        d.add(Rect(cx, y - 1, 7, 7, fillColor=col, strokeColor=None, rx=1.5, ry=1.5))
        d.add(_s(cx + 10, y, lab, 6.8, INK2))
        cx += tw
    return y


def barres_h(items, titre=None, unite=None, w=W_DEF, ref=None, dec=None, couleur=None):
    """Barres horizontales. items = [(libellé, valeur[, couleur])] ; ref = (valeur, libellé) trace une limite verticale."""
    items = [i for i in items if i[1] is not None]
    n = max(1, len(items))
    bar, gap, lab_w = 11, 6, min(62 * mm, w * 0.36)
    h = 18 + n * (bar + gap) + 14
    d = Drawing(w, h)
    _titre(d, w, h, titre, unite)
    vmax = _nice(max([abs(i[1]) for i in items] + ([ref[0]] if ref else []) + [1e-9]) * 1.08)
    x0, x1 = lab_w, w - 34
    sc = (x1 - x0) / vmax
    top = h - 20
    for k in range(5):
        gx = x0 + (x1 - x0) * k / 4
        d.add(Line(gx, 10, gx, top + 2, strokeColor=GRID, strokeWidth=0.5))
        d.add(_s(gx, 2, _fmt(vmax * k / 4), 6, MUTED, "middle"))
    for i, it in enumerate(items):
        y = top - (i + 1) * (bar + gap) + gap
        col = it[2] if len(it) > 2 and it[2] is not None else (couleur or SERIES[0])
        lab = rendu.txt(it[0])
        d.add(_s(x0 - 5, y + 3, lab if len(lab) <= 38 else lab[:36] + "…", 7, INK, "end"))
        L = max(0.0, it[1]) * sc
        if L > 0.5:
            d.add(Rect(x0, y, L, bar, fillColor=col, strokeColor=None, rx=2, ry=2))
        d.add(_s(x0 + L + 3, y + 3, _fmt(it[1], dec), 6.8, INK2))
    if ref:
        rx = x0 + ref[0] * sc
        d.add(Line(rx, 8, rx, top + 4, strokeColor=KO, strokeWidth=1.1, strokeDashArray=[3, 2]))
        d.add(_s(min(rx + 2, w - 2), top + 5, ref[1], 6.5, KO, "start" if rx < w - 60 else "end"))
    return d


def empile_h(lignes, series, titre=None, unite=None, w=W_DEF, total=True):
    """Barres horizontales empilées. lignes = [(libellé, [v1, v2, …])], series = [noms] (couleurs dans l'ordre catégoriel)."""
    n = max(1, len(lignes))
    bar, gap, lab_w = 11, 6, min(55 * mm, w * 0.32)
    h = 30 + n * (bar + gap) + 14
    d = Drawing(w, h)
    _titre(d, w, h, titre, unite)
    _legende(d, lab_w, h - 22, [(s, SERIES[i % 8]) for i, s in enumerate(series)], w - lab_w)
    vmax = _nice(max([sum(max(0, v) for v in l[1]) for l in lignes] + [1e-9]) * 1.06)
    x0, x1 = lab_w, w - 36
    sc = (x1 - x0) / vmax
    top = h - 32
    for k in range(5):
        gx = x0 + (x1 - x0) * k / 4
        d.add(Line(gx, 10, gx, top + 2, strokeColor=GRID, strokeWidth=0.5))
        d.add(_s(gx, 2, _fmt(vmax * k / 4), 6, MUTED, "middle"))
    for i, (lab, vals) in enumerate(lignes):
        y = top - (i + 1) * (bar + gap) + gap
        lab = rendu.txt(lab)
        d.add(_s(x0 - 5, y + 3, lab if len(lab) <= 34 else lab[:32] + "…", 7, INK, "end"))
        x = x0
        for j, v in enumerate(vals):
            L = max(0.0, v) * sc
            if L > 0.3:
                d.add(Rect(x, y, max(0.0, L - 1), bar, fillColor=SERIES[j % 8], strokeColor=None))
            x += L
        if total:
            d.add(_s(x + 3, y + 3, _fmt(sum(vals)), 6.8, INK2))
    return d


def colonnes(categories, series, titre=None, unite=None, w=W_DEF, h=58 * mm, ligne=None, empile=False, couleurs=None):
    """Colonnes verticales groupées (ou empilées). series = [(nom, [valeurs])] ; ligne = (nom, [valeurs]) superposée, même unité."""
    d = Drawing(w, h)
    _titre(d, w, h, titre, unite)
    leg = [(s[0], (couleurs or SERIES)[i % 8]) for i, s in enumerate(series)] + ([(ligne[0], INK)] if ligne else [])
    if len(leg) > 1:
        _legende(d, 34, h - 22, leg, w - 34)
    nc = max(1, len(categories))
    if empile:
        vmax = max([sum(max(0, s[1][k]) for s in series) for k in range(nc)] + [1e-9])
    else:
        vmax = max([max([0] + list(s[1])) for s in series] + [1e-9])
    if ligne:
        vmax = max(vmax, max(ligne[1]))
    vmax = _nice(vmax * 1.06)
    x0, x1, y0, y1 = 34, w - 6, 16, h - (32 if len(leg) > 1 else 18)
    sy = (y1 - y0) / vmax
    for k in range(5):
        gy = y0 + (y1 - y0) * k / 4
        d.add(Line(x0, gy, x1, gy, strokeColor=GRID, strokeWidth=0.5))
        d.add(_s(x0 - 3, gy - 2, _fmt(vmax * k / 4), 6, MUTED, "end"))
    cw = (x1 - x0) / nc
    ns = 1 if empile else max(1, len(series))
    bw = min(16, cw * 0.72 / ns)
    for k, cat in enumerate(categories):
        cx = x0 + cw * k + cw / 2
        d.add(_s(cx, y0 - 9, cat, 6.2, INK2, "middle"))
        if empile:
            yy = y0
            for j, s in enumerate(series):
                v = max(0.0, s[1][k]) * sy
                if v > 0.3:
                    d.add(Rect(cx - bw / 2, yy, bw, max(0.0, v - 0.8), fillColor=(couleurs or SERIES)[j % 8], strokeColor=None))
                yy += v
        else:
            for j, s in enumerate(series):
                v = max(0.0, s[1][k]) * sy
                bx = cx - ns * bw / 2 + j * bw
                if v > 0.3:
                    d.add(Rect(bx + 0.6, y0, bw - 1.2, v, fillColor=(couleurs or SERIES)[j % 8], strokeColor=None, rx=1.5, ry=1.5))
    if ligne:
        pts = [(x0 + cw * k + cw / 2, y0 + max(0.0, v) * sy) for k, v in enumerate(ligne[1])]
        for a, b in zip(pts, pts[1:]):
            d.add(Line(a[0], a[1], b[0], b[1], strokeColor=INK, strokeWidth=1.4))
        for p in pts:
            d.add(Circle(p[0], p[1], 2.2, fillColor=INK, strokeColor=colors.white, strokeWidth=0.8))
    d.add(Line(x0, y0, x1, y0, strokeColor=INK2, strokeWidth=0.6))
    return d


def courbes(x, series, titre=None, unite=None, w=W_DEF, h=58 * mm, xlab=None, marques=None, zero=True, labels_x=None):
    """Courbes (x numérique). series = [(nom, [y], couleur|None)] ; marques = [(x, y, texte)] points annotés."""
    d = Drawing(w, h)
    _titre(d, w, h, titre, unite)
    if len(series) > 1:
        _legende(d, 34, h - 22, [(s[0], s[2] or SERIES[i % 8]) for i, s in enumerate(series)], w - 34)
    ys = [v for s in series for v in s[1] if v is not None]
    lo = min(ys + ([0] if zero else []))
    hi = max(ys + [lo + 1e-9])
    if not zero:
        lo = lo - (hi - lo) * 0.08
    step = _nice((hi - lo) / 4 or 1)
    lo_n = math.floor(lo / step + 1e-9) * step
    hi_n = math.ceil(hi / step - 1e-9) * step
    if hi_n <= lo_n:
        hi_n = lo_n + step
    nt = int(round((hi_n - lo_n) / step))
    xmin, xmax = min(x), max(x)
    x0, x1, y0, y1 = 36, w - 8, 18, h - (32 if len(series) > 1 else 18)
    fx = lambda v: x0 + (v - xmin) / ((xmax - xmin) or 1) * (x1 - x0)
    fy = lambda v: y0 + (v - lo_n) / ((hi_n - lo_n) or 1) * (y1 - y0)
    for k in range(nt + 1):
        gv = lo_n + step * k
        d.add(Line(x0, fy(gv), x1, fy(gv), strokeColor=GRID if abs(gv) > 1e-9 else INK2, strokeWidth=0.5 if abs(gv) > 1e-9 else 0.7))
        d.add(_s(x0 - 3, fy(gv) - 2, _fmt(gv), 6, MUTED, "end"))
    ticks = labels_x or [(v, _fmt(v)) for v in (x if len(x) <= 13 else [xmin + (xmax - xmin) * k / 6 for k in range(7)])]
    for v, t in ticks:
        d.add(_s(fx(v), y0 - 10, t, 6.2, INK2, "middle"))
    if xlab:
        d.add(_s(x1, y0 - 18, xlab, 6.2, MUTED, "end"))
    for i, s in enumerate(series):
        col = s[2] or SERIES[i % 8]
        pts = [(fx(a), fy(b)) for a, b in zip(x, s[1]) if b is not None]
        for a, b in zip(pts, pts[1:]):
            d.add(Line(a[0], a[1], b[0], b[1], strokeColor=col, strokeWidth=1.6))
    for m in marques or []:
        px, py = fx(m[0]), fy(m[1])
        d.add(Circle(px, py, 3, fillColor=KO, strokeColor=colors.white, strokeWidth=1))
        d.add(_s(px + 5, py + 4, m[2], 6.6, INK, "start" if px < w - 90 else "end"))
    return d


def donut(parts, titre=None, centre=None, sous_centre=None, w=88 * mm, h=52 * mm):
    """Anneau de répartition. parts = [(libellé, valeur[, couleur])] ; légende à droite avec les % (jamais la couleur seule)."""
    d = Drawing(w, h)
    _titre(d, w, h, titre)
    parts = [p for p in parts if p[1] and p[1] > 0]
    tot = sum(p[1] for p in parts) or 1
    r = min(h - 20, w * 0.45) / 2
    cx, cy = r + 4, (h - 12) / 2
    a = 90.0
    for i, p in enumerate(parts):
        ang = 360 * p[1] / tot
        col = p[2] if len(p) > 2 and p[2] is not None else SERIES[i % 8]
        if ang >= 359.9:
            d.add(Circle(cx, cy, r, fillColor=col, strokeColor=None))
        else:
            d.add(Wedge(cx, cy, r, a - ang, a, fillColor=col, strokeColor=colors.white, strokeWidth=1.2))
        a -= ang
    d.add(Circle(cx, cy, r * 0.58, fillColor=colors.white, strokeColor=None))
    if centre:
        d.add(_s(cx, cy - (0 if sous_centre else 3), centre, 10, INK, "middle", True))
    if sous_centre:
        d.add(_s(cx, cy - 10, sous_centre, 6.2, INK2, "middle"))
    lx, ly = cx + r + 10, cy + min(r, len(parts) * 6)
    for i, p in enumerate(parts):
        col = p[2] if len(p) > 2 and p[2] is not None else SERIES[i % 8]
        d.add(Rect(lx, ly - 1, 7, 7, fillColor=col, strokeColor=None, rx=1.5, ry=1.5))
        d.add(_s(lx + 10, ly, f"{rendu.txt(p[0])} — {100 * p[1] / tot:.0f} %", 6.8, INK))
        ly -= 11
    return d


def etiquette(classes, actives, titre=None, w=88 * mm, couleurs=None):
    """Échelle d'étiquette énergétique (flèches de longueur croissante). classes = [(classe, plage texte)] dans l'ordre du meilleur au pire ;
    actives = {classe: libellé du marqueur} (ex. {"F": "Avant 412", "B": "Après 98"})."""
    cols = couleurs or DPE_COULEURS
    n = len(classes)
    bh, gap = 10.5, 2.5
    h = 16 + n * (bh + gap) + 4
    d = Drawing(w, h)
    _titre(d, w, h, titre)
    top = h - 16
    wmin, wmax = 26, w * 0.52
    for i, (cl, plage) in enumerate(classes):
        y = top - (i + 1) * (bh + gap) + gap
        L = max(wmin + (wmax - wmin) * i / max(1, n - 1), 4 + len(cl) * 5.2 + len(rendu.txt(plage)) * 3.1 + 8)
        col = C(cols.get(cl, "#999999"))
        d.add(Polygon([0, y, L, y, L + 6, y + bh / 2, L, y + bh, 0, y + bh], fillColor=col, strokeColor=None))
        dark = cl in ("A", "A+", "G", "F") and cols is not GES_COULEURS or (cols is GES_COULEURS and cl in ("E", "F", "G"))
        d.add(_s(4, y + 2.6, cl, 7.5, colors.white if dark else INK, bold=True))
        d.add(_s(L - 3, y + 2.8, plage, 5.6, colors.white if dark else INK2, "end"))
        if cl in actives:
            mx = wmax + 18
            d.add(Polygon([mx, y + bh / 2, mx + 7, y + bh + 1.5, w - 2, y + bh + 1.5, w - 2, y - 1.5, mx + 7, y - 1.5], fillColor=INK, strokeColor=None))
            d.add(_s(mx + 10, y + 2.4, actives[cl], 7, colors.white, bold=True))
    return d


def jauges(items, titre=None, w=W_DEF, dec=2):
    """Taux d'utilisation / ratios exigence. items = [(libellé, ratio, texte)] ; 1,0 = limite. Couleur d'état + texte (jamais la couleur seule)."""
    n = max(1, len(items))
    bar, gap, lab_w = 9, 9, min(66 * mm, w * 0.38)
    h = 20 + n * (bar + gap) + 12
    d = Drawing(w, h)
    _titre(d, w, h, titre)
    rmax = max(1.25, min(2.0, max([i[1] for i in items if i[1] is not None] + [0]) * 1.08))
    x0, x1 = lab_w, w - 70
    sc = (x1 - x0) / rmax
    top = h - 20
    lim = x0 + sc
    for i, (lab, r, t) in enumerate(items):
        y = top - (i + 1) * (bar + gap) + gap
        lab = rendu.txt(lab)
        d.add(_s(x0 - 5, y + 1.5, lab if len(lab) <= 42 else lab[:40] + "…", 7, INK, "end"))
        d.add(Rect(x0, y, x1 - x0, bar, fillColor=SURF, strokeColor=GRID, strokeWidth=0.4, rx=2, ry=2))
        if r is None:
            d.add(_s(x0 + 4, y + 1.6, "a precisar", 6.4, MUTED))
            continue
        col = OK if r <= 0.9 else (WARN if r <= 1.0 + 1e-9 else KO)
        d.add(Rect(x0, y, min(r, rmax) * sc, bar, fillColor=col, strokeColor=None, rx=2, ry=2))
        d.add(_s(x1 + 4, y + 1.6, f"{_fmt(r * 100, 0)} %" + (f"  {t}" if t else ""), 6.6, INK2))
    d.add(Line(lim, 8, lim, top + 4, strokeColor=INK, strokeWidth=0.9, strokeDashArray=[2, 2]))
    d.add(_s(lim, 1, "100 % = limite", 6, INK2, "middle"))
    return d


def cote_a_cote(*drawings, w=W_DEF, gap=6 * mm):
    """Assemble plusieurs petits graphiques sur une ligne."""
    h = max(dr.height for dr in drawings)
    d = Drawing(w, h)
    x = 0
    for dr in drawings:
        dr.translate(x, h - dr.height)
        d.add(dr)
        x += dr.width + gap
    return d


def barres_signe(items, titre=None, unite=None, w=W_DEF, lib_pos="pressão", lib_neg="sucção", dec=2):
    """Barres horizontales de part et d'autre de zéro (ex. pressions / dépressions de vent). items = [(libellé, valeur)]."""
    n = max(1, len(items))
    bar, gap, lab_w = 10, 5, min(48 * mm, w * 0.3)
    h = 30 + n * (bar + gap) + 12
    d = Drawing(w, h)
    _titre(d, w, h, titre, unite)
    _legende(d, lab_w, h - 22, [(lib_pos, SERIES[0]), (lib_neg, SERIES[1])], w - lab_w)
    vmax = _nice(max([abs(v) for _, v in items] + [1e-9]) * 1.1)
    x0, x1 = lab_w, w - 8
    xm = (x0 + x1) / 2
    sc = (x1 - xm - 26) / vmax
    top = h - 32
    for k in (-1, -0.5, 0, 0.5, 1):
        gx = xm + k * vmax * sc
        d.add(Line(gx, 10, gx, top + 2, strokeColor=INK2 if k == 0 else GRID, strokeWidth=0.7 if k == 0 else 0.5))
        d.add(_s(gx, 2, _fmt(k * vmax, dec), 6, MUTED, "middle"))
    for i, (lab, v) in enumerate(items):
        y = top - (i + 1) * (bar + gap) + gap
        d.add(_s(x0 - 5, y + 2.5, lab, 7, INK, "end"))
        L = abs(v) * sc
        col = SERIES[0] if v >= 0 else SERIES[1]
        xs = xm if v >= 0 else xm - L
        if L > 0.3:
            d.add(Rect(xs, y, L, bar, fillColor=col, strokeColor=None, rx=2, ry=2))
        d.add(_s(xm + L + 3 if v >= 0 else xm - L - 3, y + 2.5, _fmt(v, dec), 6.6, INK2, "start" if v >= 0 else "end"))
    return d
