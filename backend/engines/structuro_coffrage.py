"""Dossier d'exécution BET (coffrage + ferraillage) — rendu vectoriel déterministe A3.

Depuis le modèle auto-pilote (éléments géométriques + ferraillage EC2 + métré), produit un
jeu de feuilles A3 paysage façon bureau d'études : cartouche CONSTRUPILOT, files d'axes cotées,
plans de coffrage par niveau, coupes de ferraillage (semelles, poteaux, voiles, poutres),
plans de nappes de dalles, ancrages/recouvrements, nomenclature et note de calcul.

NON EXÉCUTOIRE — PRÉ-DIMENSIONNEMENT À VISER PAR L'INGÉNIEUR / BUREAU DE CONTRÔLE.
"""
from __future__ import annotations

import io
import math

from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# ----------------------------------------------------------------- charte graphique ----
BRAND = colors.HexColor("#15803d")
INK = colors.HexColor("#1f2937")
MUT = colors.HexColor("#64748b")
LINE = colors.HexColor("#cbd5e1")
WARN = colors.HexColor("#9d3e26")
COTE = colors.HexColor("#b45309")
AXIS = colors.HexColor("#0f766e")
WALLF = colors.HexColor("#d8e0e6")
WALLE = colors.HexColor("#334155")
FOOTF = colors.HexColor("#dbeafe")
FOOTE = colors.HexColor("#1d4ed8")
COLF = colors.HexColor("#1f2937")
BEAM = colors.HexColor("#0f766e")
SLABF = colors.HexColor("#f1f5f4")
REBAR = colors.HexColor("#1d4ed8")
STIR = colors.HexColor("#c2410c")

PAGE_W, PAGE_H = landscape(A3)       # ~1190.6 x 841.9 pt
PAD = 20


def _r(x, n=2, d=0.0):
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return d


# ----------------------------------------------------------------- cadre / cartouche ----
class Sheet:
    """Dessine le cadre commun et expose la zone de dessin + colonne de notes."""

    def __init__(self, c, ctx, title, subtitle, code, feuille, echelle):
        self.c = c
        self.ctx = ctx
        self._frame(title, subtitle, code, feuille, echelle)

    def _frame(self, title, subtitle, code, feuille, echelle):
        c, ctx = self.c, self.ctx
        c.setLineWidth(0.8)
        c.setStrokeColor(INK)
        c.rect(PAD, PAD, PAGE_W - 2 * PAD, PAGE_H - 2 * PAD)
        top = PAGE_H - PAD
        # bandeau en-tête
        c.setFillColor(BRAND)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(PAD + 14, top - 28, "CONSTRUPILOT")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(PAGE_W - PAD - 14, top - 24, "STRUCTURE / AUTO-PILOTE BET")
        c.setFont("Helvetica-Bold", 15)
        c.drawString(PAD + 14, top - 52, title)
        c.setFont("Helvetica", 8.5)
        c.setFillColor(MUT)
        c.drawString(PAD + 14, top - 66, subtitle)
        # bandeau d'avertissement
        by = top - 86
        c.setFillColor(colors.HexColor("#fbeae5"))
        c.rect(PAD + 1, by, PAGE_W - 2 * PAD - 2, 15, stroke=0, fill=1)
        c.setFillColor(WARN)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(PAGE_W / 2, by + 4,
                            "PRÉ-DIMENSIONNEMENT AUTO-PILOTE — NON EXÉCUTOIRE — À VÉRIFIER PAR L'INGÉNIEUR / BUREAU DE CONTRÔLE")
        # cartouche bas
        self._cartouche(code, feuille, echelle)
        # zones utiles
        self.area = (PAD + 40, PAD + 92, PAGE_W - PAD - 300, by - 18)   # x0,y0,x1,y1
        self.notes_x = PAGE_W - PAD - 285
        self.notes_top = by - 24
        self.content_top = by - 10

    def _cartouche(self, code, feuille, echelle):
        c, ctx = self.c, self.ctx
        y = PAD + 72
        c.setStrokeColor(INK)
        c.setLineWidth(0.6)
        c.line(PAD, y, PAGE_W - PAD, y)
        # colonnes verticales
        xA, xB, xC, xD = PAD, PAD + 300, PAD + 600, PAGE_W - PAD - 150
        for xx in (xB, xC, xD):
            c.line(xx, PAD, xx, y)
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(xA + 10, y - 16, ctx.get("project", "Projet auto-pilote BET"))
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUT)
        c.drawString(xA + 10, y - 30, ctx.get("sub1", "Pré-dimensionnement généré automatiquement"))
        c.drawString(xA + 10, y - 42, ctx.get("sub2", ""))
        c.setFillColor(WARN)
        c.setFont("Helvetica", 7.5)
        c.drawString(xB + 10, y - 16, "Aucune validation BET / géotechnique / visa EXE")
        c.setFillColor(MUT)
        c.setFont("Helvetica", 7.5)
        c.drawString(xB + 10, y - 30, ctx.get("date", ""))
        c.drawString(xB + 10, y - 42, f"Indice {ctx.get('rev', 1)} | Auto-pilote ConstruPilot")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(xC + 10, y - 16, f"A3 paysage | Échelle {echelle}")
        c.setFont("Helvetica", 7.5)
        c.setFillColor(MUT)
        c.drawString(xC + 10, y - 30, "Cotes en m ; sections en cm ; aciers en mm")
        c.drawString(xC + 10, y - 42, "Imprimer à 100 % - ne pas mesurer sur écran")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString((xD + PAGE_W - PAD) / 2, y - 16, "CONCEPTION")
        c.setFillColor(WARN)
        c.drawCentredString((xD + PAGE_W - PAD) / 2, y - 28, "NON VALIDÉE")
        c.setFillColor(INK)
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString((xD + PAGE_W - PAD) / 2, y - 55, code)
        c.setFont("Helvetica", 7)
        c.setFillColor(MUT)
        c.drawCentredString((xD + PAGE_W - PAD) / 2, PAD + 8, f"Feuille {feuille}")

    # ---- notes column ----
    def notes(self, blocks):
        c = self.c
        x, y, w = self.notes_x, self.notes_top, 270
        for head, body in blocks:
            if y < PAD + 100:
                break
            c.setFillColor(BRAND)
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(x, y, head.upper())
            y -= 13
            c.setFillColor(INK)
            c.setFont("Helvetica", 8)
            for ln in _wrap(c, body, "Helvetica", 8, w):
                c.drawString(x, y, ln)
                y -= 11
            y -= 7
        return y


def _wrap(c, text, font, size, width):
    out, cur = [], ""
    for word in str(text).split():
        trial = (cur + " " + word).strip()
        if c.stringWidth(trial, font, size) <= width:
            cur = trial
        else:
            if cur:
                out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


# ----------------------------------------------------------------- géométrie / échelle ----
def _bounds(els):
    xs, ys = [], []
    for e in els:
        x, y = e.get("x_m") or 0, e.get("y_m") or 0
        lx, wy = e.get("length_m") or 0, e.get("width_m") or 0
        k = e.get("kind"); eid = e.get("id", "")
        if k == "slab":
            xs += [x, x + lx]; ys += [y, y + wy]
        elif k == "footing":
            if eid.startswith("SFY"):         # filante sens Y
                xs += [x - (wy or 0.6) / 2, x + (wy or 0.6) / 2]; ys += [y, y + lx]
            elif eid.startswith("SF"):        # filante sens X
                xs += [x, x + lx]; ys += [y - (wy or 0.6) / 2, y + (wy or 0.6) / 2]
            else:                             # isolée : centrée
                xs += [x - lx / 2, x + lx / 2]; ys += [y - wy / 2, y + wy / 2]
        elif k == "beam":
            if eid.startswith("BY"):          # poutre sens Y
                xs += [x - (wy or 0.2) / 2, x + (wy or 0.2) / 2]; ys += [y, y + lx]
            else:
                xs += [x, x + lx]; ys += [y - (wy or 0.2) / 2, y + (wy or 0.2) / 2]
        elif k == "wall":
            if eid.startswith("WY"):
                xs += [x - (wy or 0.2) / 2, x + (wy or 0.2) / 2]; ys += [y, y + lx]
            else:
                xs += [x, x + lx]; ys += [y - (wy or 0.2) / 2, y + (wy or 0.2) / 2]
        else:                                 # column
            xs += [x - (lx or 0.3) / 2, x + (lx or 0.3) / 2]; ys += [y - (wy or 0.3) / 2, y + (wy or 0.3) / 2]
    if not xs:
        return None
    return min(xs), max(xs), min(ys), max(ys)


def _mk_scale(els, area):
    b = _bounds(els)
    if not b:
        return None
    minx, maxx, miny, maxy = b
    x0, y0, x1, y1 = area
    m = 44
    spanx, spany = max(maxx - minx, 0.5), max(maxy - miny, 0.5)
    sc = min((x1 - x0 - 2 * m) / spanx, (y1 - y0 - 2 * m) / spany)
    ox = x0 + m + (x1 - x0 - 2 * m - spanx * sc) / 2
    oy = y0 + m + (y1 - y0 - 2 * m - spany * sc) / 2
    return {"sc": sc, "minx": minx, "miny": miny, "ox": ox, "oy": oy,
            "maxx": maxx, "maxy": maxy, "x0": x0, "y0": y0, "x1": x1, "y1": y1}


def _P(s, mx, my):
    return (s["ox"] + (mx - s["minx"]) * s["sc"], s["oy"] + (my - s["miny"]) * s["sc"])


def _hatch(c, x, y, w, h, fill, edge=WALLE, step=5.0):
    c.setFillColor(fill)
    c.setStrokeColor(edge)
    c.setLineWidth(0.8)
    c.rect(x, y, w, h, stroke=1, fill=1)
    c.setStrokeColor(colors.HexColor("#aab6c2"))
    c.setLineWidth(0.3)
    off = step
    while off < w + h:
        x1 = x + max(0.0, off - h); y1 = y + min(off, h)
        x2 = x + min(off, w); y2 = y + max(0.0, off - w)
        c.line(x1, y1, x2, y2)
        off += step


def _axes(c, s, xs, ys):
    """Bulles de files + lignes d'axe en pointillé."""
    letters = "ABCDEFGHIJK"
    c.setFont("Helvetica-Bold", 8)
    for i, xv in enumerate(xs):
        px, _ = _P(s, xv, s["miny"])
        top = s["y1"] - 20
        c.setStrokeColor(AXIS); c.setLineWidth(0.4)
        c.setDash(3, 3)
        c.line(px, s["oy"] - 8, px, top - 9)
        c.setDash()
        c.setFillColor(colors.white); c.setStrokeColor(AXIS); c.setLineWidth(0.8)
        c.circle(px, top, 9, stroke=1, fill=1)
        c.setFillColor(AXIS)
        c.drawCentredString(px, top - 3, letters[i] if i < len(letters) else str(i + 1))
    for j, yv in enumerate(ys):
        _, py = _P(s, s["minx"], yv)
        left = s["ox"] - 24
        c.setStrokeColor(AXIS); c.setLineWidth(0.4)
        c.setDash(3, 3)
        c.line(left + 9, py, s["x1"] - 20, py)
        c.setDash()
        c.setFillColor(colors.white); c.setStrokeColor(AXIS); c.setLineWidth(0.8)
        c.circle(left, py, 9, stroke=1, fill=1)
        c.setFillColor(AXIS)
        c.drawCentredString(left, py - 3, str(j + 1))


def _dim_chain(c, s, coords, vertical=False):
    coords = sorted(set(round(v, 3) for v in coords))
    if len(coords) < 2:
        if coords:
            coords = [coords[0], coords[0]]
        else:
            return
    c.setStrokeColor(COTE); c.setLineWidth(0.5)
    c.setFillColor(COTE); c.setFont("Helvetica", 7)
    if vertical:
        x = s["ox"] - 40
        for v in coords:
            _, py = _P(s, 0, v)
            c.line(x - 3, py, x + 3, py)
        c.line(x, _P(s, 0, coords[0])[1], x, _P(s, 0, coords[-1])[1])
        for a, b in zip(coords, coords[1:]):
            ya, yb = _P(s, 0, a)[1], _P(s, 0, b)[1]
            c.saveState(); c.translate(x - 5, (ya + yb) / 2); c.rotate(90)
            c.drawCentredString(0, 0, f"{b - a:.3f}".rstrip("0").rstrip("."))
            c.restoreState()
        # cote totale
        xt = s["ox"] - 54
        c.line(xt, _P(s, 0, coords[0])[1], xt, _P(s, 0, coords[-1])[1])
        c.saveState(); c.translate(xt - 5, (_P(s, 0, coords[0])[1] + _P(s, 0, coords[-1])[1]) / 2); c.rotate(90)
        c.setFont("Helvetica-Bold", 7); c.drawCentredString(0, 0, f"{coords[-1] - coords[0]:.2f}")
        c.restoreState()
    else:
        y = s["oy"] - 24
        for v in coords:
            px, _ = _P(s, v, 0)
            c.line(px, y - 3, px, y + 3)
        c.line(_P(s, coords[0], 0)[0], y, _P(s, coords[-1], 0)[0], y)
        for a, b in zip(coords, coords[1:]):
            xa, xb = _P(s, a, 0)[0], _P(s, b, 0)[0]
            c.drawCentredString((xa + xb) / 2, y - 9, f"{b - a:.3f}".rstrip("0").rstrip("."))
        yt = s["oy"] - 38
        c.line(_P(s, coords[0], 0)[0], yt, _P(s, coords[-1], 0)[0], yt)
        c.setFont("Helvetica-Bold", 7)
        c.drawCentredString((_P(s, coords[0], 0)[0] + _P(s, coords[-1], 0)[0]) / 2, yt - 9, f"{coords[-1] - coords[0]:.2f}")


def _scale_bar(c, s):
    x0 = s["ox"]; y0 = s["y0"] + 6
    unit = s["sc"]
    c.setFont("Helvetica", 7); c.setFillColor(INK)
    for i in range(5):
        xx = x0 + i * unit
        c.setFillColor(INK if i % 2 == 0 else colors.white)
        c.setStrokeColor(INK); c.setLineWidth(0.5)
        c.rect(xx, y0, unit, 4, stroke=1, fill=1)
    c.setFillColor(INK)
    c.drawCentredString(x0, y0 - 8, "0")
    c.drawCentredString(x0 + unit, y0 - 8, "1")
    c.drawCentredString(x0 + 5 * unit, y0 - 8, "5 m")


# ----------------------------------------------------------------- plan de coffrage ----
def _coffrage_sheet(c, ctx, level, els, marks, code, feuille, foundation=False):
    title = ("Plan de fondations" if foundation else "Plan de coffrage") + f" — {level}"
    sub = "Dessin vectoriel coté / repères communs aux feuilles de ferraillage"
    sh = Sheet(c, ctx, title, sub, code, feuille, "1:50")
    s = _mk_scale(els, sh.area)
    if not s:
        return
    # emprise dalle
    slabs = [e for e in els if e.get("kind") == "slab"]
    if slabs:
        sx = min(e["x_m"] for e in slabs); sy = min(e["y_m"] for e in slabs)
        ex = max(e["x_m"] + e["length_m"] for e in slabs); ey = max(e["y_m"] + e["width_m"] for e in slabs)
        p0 = _P(s, sx, sy); p1 = _P(s, ex, ey)
        c.setFillColor(SLABF); c.setStrokeColor(MUT); c.setLineWidth(0.6)
        c.setDash(4, 2)
        c.rect(p0[0], p0[1], p1[0] - p0[0], p1[1] - p0[1], stroke=1, fill=1)
        c.setDash()
    gx, gy = set(), set()
    for e in els:
        x, y = e.get("x_m") or 0, e.get("y_m") or 0
        lx, wy = e.get("length_m") or 0, e.get("width_m") or 0
        k = e.get("kind"); mk = marks.get(e["id"]); eid = e.get("id", "")
        if k == "beam":
            vertical = eid.startswith("BY")
            c.setFillColor(colors.HexColor("#cde8e4")); c.setStrokeColor(BEAM); c.setLineWidth(1.0)
            if vertical:
                p = _P(s, x - (wy or 0.2) / 2, y)
                c.rect(p[0], p[1], max((wy or 0.2) * s["sc"], 3), lx * s["sc"], stroke=1, fill=1)
                gy.update([round(y, 3), round(y + lx, 3)]); gx.add(round(x, 3))
            else:
                p = _P(s, x, y - (wy or 0.2) / 2)
                c.rect(p[0], p[1], lx * s["sc"], max((wy or 0.2) * s["sc"], 3), stroke=1, fill=1)
                if mk:
                    c.setFillColor(BEAM); c.setFont("Helvetica", 5.5)
                    c.drawCentredString(p[0] + lx * s["sc"] / 2, p[1] + 2, mk)
                gx.update([round(x, 3), round(x + lx, 3)]); gy.add(round(y, 3))
        elif k == "wall":
            if eid.startswith("WY"):
                p = _P(s, x - (wy or 0.2) / 2, y)
                _hatch(c, p[0], p[1], max((wy or 0.2) * s["sc"], 3), lx * s["sc"], WALLF)
                gy.update([round(y, 3), round(y + lx, 3)]); gx.add(round(x, 3))
            else:
                p = _P(s, x, y - (wy or 0.2) / 2)
                _hatch(c, p[0], p[1], lx * s["sc"], max((wy or 0.2) * s["sc"], 3), WALLF)
                if mk:
                    c.setFillColor(WALLE); c.setFont("Helvetica", 5.5)
                    c.drawCentredString(p[0] + lx * s["sc"] / 2, p[1] + 3, mk)
                gx.update([round(x, 3), round(x + lx, 3)]); gy.add(round(y, 3))
        elif k == "column":
            side = max((lx or 0.3) * s["sc"], 6.0)
            p = _P(s, x, y)
            c.setFillColor(COLF); c.setStrokeColor(INK); c.setLineWidth(0.6)
            c.rect(p[0] - side / 2, p[1] - side / 2, side, side, stroke=1, fill=1)
            gx.add(round(x, 3)); gy.add(round(y, 3))
        elif k == "footing":
            if eid.startswith("SFY"):          # filante sens Y (verticale)
                p = _P(s, x - (wy or 0.6) / 2, y)
                c.setFillColor(FOOTF); c.setStrokeColor(FOOTE); c.setLineWidth(1.0)
                c.rect(p[0], p[1], max((wy or 0.6) * s["sc"], 4), lx * s["sc"], stroke=1, fill=1)
                c.saveState(); c.setFillColor(FOOTE); c.setFont("Helvetica", 6)
                c.translate(p[0] - 4, p[1] + lx * s["sc"] / 2); c.rotate(90)
                c.drawCentredString(0, 0, f"{e['id'].replace('SFY_','SFY')} {int(round((wy or 0.6)*100))} cm")
                c.restoreState()
                gy.update([round(y, 3), round(y + lx, 3)]); gx.add(round(x, 3))
            elif eid.startswith("SF"):         # filante sens X (horizontale)
                p = _P(s, x, y - (wy or 0.6) / 2)
                c.setFillColor(FOOTF); c.setStrokeColor(FOOTE); c.setLineWidth(1.0)
                c.rect(p[0], p[1], lx * s["sc"], max((wy or 0.6) * s["sc"], 4), stroke=1, fill=1)
                c.setFillColor(FOOTE); c.setFont("Helvetica", 6)
                c.drawCentredString(p[0] + lx * s["sc"] / 2, p[1] - 9,
                                    f"{e['id'].replace('SF_','SF')} {int(round((wy or 0.6)*100))} cm")
                gx.update([round(x, 3), round(x + lx, 3)]); gy.add(round(y, 3))
            else:
                sd = max((lx or 0.6) * s["sc"], 8.0)
                p = _P(s, x, y)
                c.setFillColor(FOOTF); c.setStrokeColor(FOOTE); c.setLineWidth(1.0)
                c.rect(p[0] - sd / 2, p[1] - sd / 2, sd, sd, stroke=1, fill=1)
                c.setFillColor(FOOTE); c.setFont("Helvetica", 5.5)
                c.drawCentredString(p[0], p[1] - sd / 2 - 8, f"{int(round((lx or .6)*100))}×{int(round((wy or .6)*100))}")
                gx.add(round(x, 3)); gy.add(round(y, 3))
    _axes(c, s, sorted(gx), sorted(gy))
    _dim_chain(c, s, gx)
    _dim_chain(c, s, gy, vertical=True)
    _scale_bar(c, s)
    # notes
    nb = []
    reps = sorted({marks.get(e["id"]) for e in els if marks.get(e["id"])})
    nb.append(("Repères", ", ".join(reps) if reps else "—"))
    kinds = {e["kind"] for e in els}
    if "wall" in kinds:
        nb.append(("Voiles / murs porteurs", f"Épaisseur {int(round((next(e for e in els if e['kind']=='wall').get('width_m') or 0.2)*100))} cm. Chaînages et linteaux à détailler par l'ingénieur."))
    if "column" in kinds:
        nb.append(("Poteaux", "Sections carrées sur files ; voir feuille de ferraillage F-POT."))
    if "beam" in kinds:
        nb.append(("Poutres", "Retombées sous dalle ; ferraillage feuille F-PTR."))
    if foundation:
        nb.append(("Fondations", "Semelles dimensionnées sur la contrainte admissible G2 (voir note de calcul)."))
    nb.append(("Dalle", f"Épaisseur {int(round((slabs[0].get('height_m') or 0.2)*100)) if slabs else '—'} cm ; nappes sur feuille de ferraillage dalles."))
    nb.append(("Statut", "Pré-dimensionnement automatique. Cotes lues/estimées à vérifier sur plan d'architecte."))
    sh.notes(nb)


# ----------------------------------------------------------------- coupes de ferraillage ----
def _rebar_section(c, x, y, w, h, n_bot, n_top, label, section_txt, annots=None):
    """Coupe BA : béton hachuré + cadre + barres (points). (x,y) coin bas-gauche.
    `annots` = liste de (texte, couleur) affichée à DROITE de la coupe (pas de chevauchement)."""
    _hatch(c, x, y, w, h, colors.HexColor("#eef2f1"), edge=INK, step=6)
    cov = min(w, h) * 0.12
    c.setStrokeColor(REBAR); c.setLineWidth(1.0)
    c.rect(x + cov, y + cov, w - 2 * cov, h - 2 * cov, stroke=1, fill=0)
    c.setFillColor(REBAR)
    r = 2.0
    def row(ny, n):
        n = max(n, 2)
        xs = [x + cov + 2 * r + i * (w - 2 * cov - 4 * r) / (n - 1) for i in range(n)]
        for xx in xs:
            c.circle(xx, ny, r, stroke=0, fill=1)
    row(y + cov + 2 * r, n_bot)
    row(y + h - cov - 2 * r, n_top)
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(x + w / 2, y + h / 2 + 2, label)
    # cote largeur sous la coupe
    c.setStrokeColor(COTE); c.setFillColor(COTE); c.setFont("Helvetica", 6.5)
    c.line(x, y - 6, x + w, y - 6)
    c.drawCentredString(x + w / 2, y - 14, section_txt)
    # annotations à droite
    ax, ay = x + w + 12, y + h - 4
    for txt, col in (annots or []):
        c.setFillColor(col); c.setFont("Helvetica", 7)
        c.drawString(ax, ay, txt)
        ay -= 12


def _stirrup_elevation(c, x, y, w, h, zones, caption):
    c.setFillColor(colors.HexColor("#eef2f1")); c.setStrokeColor(INK); c.setLineWidth(0.8)
    c.rect(x, y, w, h, stroke=1, fill=1)
    c.setStrokeColor(REBAR); c.setLineWidth(1.2)
    c.line(x + 4, y + h - 5, x + w - 4, y + h - 5)
    c.line(x + 4, y + 5, x + w - 4, y + 5)
    total = sum(z[0] for z in zones) or 1.0
    xx = x
    c.setFont("Helvetica", 6.5)
    for (lz, spac) in zones:
        wz = w * lz / total
        n = max(int(lz / spac), 1)
        c.setStrokeColor(STIR); c.setLineWidth(0.5)
        for i in range(n + 1):
            lxp = xx + i * wz / max(n, 1)
            if lxp <= xx + wz + 0.5:
                c.line(lxp, y + 4, lxp, y + h - 4)
        c.setStrokeColor(COTE); c.setLineWidth(0.4)
        c.line(xx, y - 6, xx + wz, y - 6)
        c.setFillColor(COTE)
        c.drawCentredString(xx + wz / 2, y - 14, f"{lz:.2f} : e{int(spac*1000)}")
        xx += wz
    c.setFillColor(MUT); c.setFont("Helvetica", 7)
    c.drawString(x, y + h + 6, caption)


def _ferr_semelles_sheet(c, ctx, footings, code, feuille):
    sh = Sheet(c, ctx, "Semelles — ferraillage et coupes types",
               "Coupes BA, aciers filants et chaînage — longueurs à l'axe", code, feuille, "1:20")
    x0, y0, x1, y1 = sh.area
    reps = {}
    if footings and not any(f.get("dim_m") for f in footings):
        # Sol non confirmé : aucune semelle dimensionnée → aucune coupe inventée.
        c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 10)
        c.drawString(x0 + 10, y1 - 20, "Fondations non dimensionnées : contrainte de sol G2 à confirmer.")
        return
    for f in footings:
        if not f.get("dim_m"):
            continue
        key = (f.get("type"), f.get("dim_m"))
        reps.setdefault(key, f)
    reps = list(reps.values())[:3]
    bx = x0 + 10
    for i, f in enumerate(reps):
        dim = f.get("dim_m") or f.get("side_m") or f.get("width_m") or 0.6
        typ = f.get("type")
        n = max(4, int(round(dim / 0.15)) + 1)
        w = 150; h = 70
        cx = bx + i * 320
        cy = y1 - 120
        c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 9)
        c.drawString(cx, y1 - 20, f"{'SF (filante)' if typ=='filante' else 'S (isolée)'} — {f.get('id','')}")
        sect = f"{dim:.2f} × 0.40 m" if typ == 'filante' else f"{dim:.2f} × {dim:.2f} × 0.40 m"
        _rebar_section(c, cx, cy, w, h, n, 3, f"S0{i+1}", sect, annots=[
            ("Nappe inf. HA12 e150", REBAR),
            ("Chaînage 2 HA12", STIR),
            ("Enrobage c = 50 mm", MUT),
            (f"N_ELU = {f.get('n_elu_kn','—')} kN", INK),
        ])
    sh.notes([
        ("Aciers", "Nappe inférieure croisée HA12 e150 (semelle isolée) ou filants HA12 + chaînage (filante). Aciers de peau et attentes de poteaux/murs à ajouter."),
        ("Enrobage", "c,nom = 50 mm (classe XC2, fissuration). À confirmer selon exposition et béton de propreté."),
        ("Ancrages", "Longueurs d'ancrage lbd : voir feuille des ancrages/recouvrements."),
        ("Limites", "Portance, tassement, poinçonnement et moment de la semelle à valider par l'ingénieur à partir de la G2 réelle."),
    ])


def _ferr_lineaires_sheet(c, ctx, columns, walls, code, feuille):
    sh = Sheet(c, ctx, "Poteaux & voiles — ferraillage",
               "Coupes BA et zones de cadres — familles gouvernantes par niveau", code, feuille, "1:10 / 1:25")
    x0, y0, x1, y1 = sh.area
    gc = max(columns, key=lambda z: z.get("n_ed_kn", 0)) if columns else None
    gw = max(walls, key=lambda z: z.get("n_ed_kn", 0)) if walls else None
    if gc:
        c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 10)
        c.drawString(x0 + 10, y1 - 10, f"POT {gc.get('id','')} — {int(round(gc['b_m']*100))}×{int(round(gc['h_m']*100))} cm (N_Ed={gc['n_ed_kn']} kN)")
        nb = 2
        try:
            nb = max(2, int(str(gc.get("long_bars", "4Ø16")).split("Ø")[0]) // 2)
        except Exception:
            nb = 2
        _rebar_section(c, x0 + 10, y1 - 130, 90, 90, nb, nb, "POT",
                       f"{int(round(gc['b_m']*100))}×{int(round(gc['h_m']*100))} cm", annots=[
                           (f"{gc.get('long_bars','')}", REBAR),
                           (f"Cadres {gc.get('ties','')}", STIR),
                           ("Enrobage c = 30 mm", MUT),
                       ])
    if gw:
        c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 10)
        c.drawString(x0 + 10, y1 - 150, f"VOI {gw.get('id','')} — ép. {int(round(gw['thickness_m']*100))} cm (N_Ed={gw['n_ed_kn']} kN)")
        wsc = min(260.0, gw["length_m"] * 26)
        _hatch(c, x0 + 10, y1 - 215, wsc, 28, WALLF, edge=INK)
        c.setStrokeColor(REBAR); c.setLineWidth(0.8)
        nvert = max(4, int(gw["length_m"] / 0.25))
        for i in range(nvert + 1):
            xx = x0 + 10 + i * wsc / nvert
            c.line(xx, y1 - 213, xx, y1 - 189)
        c.setFillColor(INK); c.setFont("Helvetica", 7)
        c.drawString(x0 + 10, y1 - 228, f"Vert. {gw.get('as_vert_cm2')} cm² + horiz. {gw.get('as_horiz_cm2')} cm² (2 faces)")
    # table all levels
    c.setFillColor(INK); c.setFont("Helvetica-Bold", 8.5)
    c.drawString(x0 + 10, y0 + 170, "Familles par niveau")
    rows = [["Niveau", "Élément", "Section", "N_Ed (kN)", "Aciers / statut"]]
    for cc in columns:
        rows.append([cc.get("level"), f"POT {cc.get('id','')}", f"{int(round(cc['b_m']*100))}×{int(round(cc['h_m']*100))}",
                     cc.get("n_ed_kn"), f"{cc.get('long_bars')} / {'OK' if cc.get('status')=='ok' else 'à revoir'}"])
    for ww in walls:
        rows.append([ww.get("level"), f"VOI {ww.get('id','')}", f"ép.{int(round(ww['thickness_m']*100))}×{ww.get('length_m')}",
                     ww.get("n_ed_kn"), f"V {ww.get('as_vert_cm2')} / H {ww.get('as_horiz_cm2')} cm²"])
    _grid_table(c, x0 + 10, y0 + 162, rows, [70, 95, 90, 70, 180])
    sh.notes([
        ("Poteaux", "Aciers longitudinaux As,min = max(0,10·N/fyd ; 0,002·Ac), cadres Ø≥6 espacés ≤ min(20Ølong ; côté ; 400). Flambement et moments N-M non vérifiés."),
        ("Voiles", "Aciers minimaux §9.6, répartis deux faces. Chaînages de rive et linteaux au-dessus des baies à détailler."),
        ("Nœuds", "Recouvrements, attentes et continuités à concevoir (voir feuille des ancrages)."),
    ])


def _ferr_poutres_sheet(c, ctx, beams, code, feuille):
    sh = Sheet(c, ctx, "Poutres — ferraillage",
               "Coupe BA + élévation des zones de cadres — poutre gouvernante par niveau", code, feuille, "1:10 / 1:25")
    x0, y0, x1, y1 = sh.area
    gb = max(beams, key=lambda z: z.get("as_req_cm2", 0)) if beams else None
    if gb:
        c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 10)
        c.drawString(x0 + 10, y1 - 10, f"PTR {gb.get('id','')} — {int(round(gb['b_m']*100))}×{int(round(gb['h_m']*100))} cm (M_Ed={gb.get('med_knm')} kN·m)")
        n_bot = max(2, int(math.ceil((gb.get("as_req_cm2") or 2) / 2.0)))
        _rebar_section(c, x0 + 10, y1 - 150, 70, 120, min(n_bot, 6), 2, "PTR",
                       f"{int(round(gb['b_m']*100))}×{int(round(gb['h_m']*100))} cm", annots=[
                           (f"{min(n_bot,6)} HA16 inf.", REBAR),
                           ("2 HA12 sup.", STIR),
                           ("Cadres Ø8", MUT),
                       ])
        span = 4.0
        zones = [(span * 0.25, 0.10), (span * 0.5, 0.15), (span * 0.25, 0.10)]
        _stirrup_elevation(c, x0 + 160, y1 - 110, 420, 56, zones,
                           f"Élévation d'armature — cadres Ø8, As,w/s ≈ {gb.get('asw_s_req_cm2_m','—')} cm²/m")
    rows = [["Niveau", "Poutre", "b×h (cm)", "M_Ed (kN·m)", "V_Ed (kN)", "As req (cm²)", "Asw/s (cm²/m)"]]
    for b in beams:
        rows.append([b.get("level"), f"PTR {b.get('id','')}", f"{int(round(b['b_m']*100))}×{int(round(b['h_m']*100))}",
                     b.get("med_knm"), b.get("ved_kn"), b.get("as_req_cm2"), b.get("asw_s_req_cm2_m")])
    _grid_table(c, x0 + 10, y0 + 190, rows, [60, 80, 70, 85, 70, 80, 90])
    sh.notes([
        ("Flexion", "As calculé en section rectangulaire simple (EN 1992-1-1 §6.1). Aciers supérieurs sur appuis forfaitaires."),
        ("Effort tranchant", "Cadres verticaux (treillis, cot θ=2,5). Densifiés aux appuis."),
        ("Non vérifié", "Torsion, continuité, redistribution et flèche à valider par l'ingénieur."),
    ])


# ----------------------------------------------------------------- dalles / nappes ----
def _dalle_sheet(c, ctx, level, els, code, feuille):
    slabs = [e for e in els if e.get("kind") == "slab"]
    if not slabs:
        return False
    sh = Sheet(c, ctx, f"Dalle {level} — nappes et repérage",
               "Nappe inférieure X/Y et chapeaux de rive (disposition d'exemple)", code, feuille, "1:50")
    s = _mk_scale(slabs, sh.area)
    sx = min(e["x_m"] for e in slabs); sy = min(e["y_m"] for e in slabs)
    ex = max(e["x_m"] + e["length_m"] for e in slabs); ey = max(e["y_m"] + e["width_m"] for e in slabs)
    p0 = _P(s, sx, sy); p1 = _P(s, ex, ey)
    w = p1[0] - p0[0]; h = p1[1] - p0[1]
    c.setFillColor(SLABF); c.setStrokeColor(INK); c.setLineWidth(1.0)
    c.rect(p0[0], p0[1], w, h, stroke=1, fill=1)
    # nappe : lignes X et Y
    c.setLineWidth(0.3)
    c.setStrokeColor(colors.HexColor("#1d4ed8"))
    stepx = max(w / 60, 3)
    xx = p0[0] + stepx
    while xx < p1[0]:
        c.line(xx, p0[1] + 3, xx, p1[1] - 3); xx += stepx
    c.setStrokeColor(colors.HexColor("#c2410c"))
    yy = p0[1] + stepx
    while yy < p1[1]:
        c.line(p0[0] + 3, yy, p1[0] - 3, yy); yy += stepx
    th = int(round((slabs[0].get("height_m") or 0.2) * 100))
    c.setFillColor(INK); c.setFont("Helvetica", 7.5)
    c.drawString(p0[0] + 6, p0[1] + h / 2, f"Nappe inf. Y — HA12 e150")
    c.drawRightString(p1[0] - 6, p0[1] + h / 2 - 12, "Nappe inf. X — HA10 e200")
    _dim_chain(c, s, [sx, ex])
    _dim_chain(c, s, [sy, ey], vertical=True)
    _scale_bar(c, s)
    sh.notes([
        ("Section courante", f"Dalle pleine {th} cm ; nappe inférieure croisée HA12/HA10. Section comparée au calcul de descente de charges."),
        ("Chapeaux", "Chapeaux de rive HA12 e150 sur bandes ~1,5 m (disposition d'exemple, hors calcul de moments d'appui)."),
        ("Trémies", "Renforts au pourtour des trémies à ajouter par l'ingénieur."),
        ("Enrobage", "c = 20 mm (intérieur). Recouvrements et arrêts de barres à détailler."),
    ])
    return True


# ----------------------------------------------------------------- ancrages / façonnage ----
def _lbd_table(fck=25, fyk=500, eta1=0.7):
    fctk = 1.8 if fck == 25 else 0.21 * fck ** (2 / 3)
    fctd = fctk / 1.5
    fbd = 2.25 * eta1 * 1.0 * fctd
    fyd = fyk / 1.15
    rows = [["HA (mm)", "lbd (mm)", "l0 recouvrement α6=1,5 (mm)"]]
    for dia in (8, 10, 12, 14, 16, 20, 25):
        lbd = (dia / 4.0) * (fyd / fbd)
        lbd = int(math.ceil(lbd / 10.0) * 10)
        rows.append([str(dia), str(lbd), str(int(math.ceil(1.5 * lbd / 10.0) * 10))])
    return rows


def _ancrage_sheet(c, ctx, code, feuille):
    sh = Sheet(c, ctx, "Ancrages, recouvrements et croquis de façonnage",
               "Longueurs à l'axe des barres — aucune autorisation de fabrication", code, feuille, "schématique")
    x0, y0, x1, y1 = sh.area
    c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 + 10, y1 - 10, "01 / ANCRAGE DROIT & RECOUVREMENT — C25/30, B500")
    _grid_table(c, x0 + 10, y1 - 30, _lbd_table(), [70, 90, 210])
    c.setFillColor(MUT); c.setFont("Helvetica", 7)
    c.drawString(x0 + 10, y1 - 190, "fctk0,05=1,8 MPa ; γc=1,5 ; fbd=2,25·η1·fctd (η1=0,7 défavorable). Choix conservateur ; confinement et % recouvrement à vérifier.")
    # croquis formes
    c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 + 10, y0 + 150, "02 / CROQUIS DES FORMES (à l'axe)")
    bx = x0 + 20; by = y0 + 60
    c.setStrokeColor(REBAR); c.setLineWidth(1.4)
    # L
    c.line(bx, by, bx + 70, by); c.line(bx + 70, by, bx + 70, by + 45)
    c.setFillColor(INK); c.setFont("Helvetica", 7); c.drawString(bx, by - 12, "L : a + b, 1 coude")
    # U
    ux = bx + 150
    c.setStrokeColor(REBAR); c.line(ux, by + 45, ux, by); c.line(ux, by, ux + 70, by); c.line(ux + 70, by, ux + 70, by + 45)
    c.setFillColor(INK); c.drawString(ux, by - 12, "U : a + 2b, 2 coudes")
    # cadre
    cx = bx + 320
    c.setStrokeColor(REBAR); c.rect(cx, by, 60, 45, stroke=1, fill=0)
    c.setFillColor(INK); c.drawString(cx, by - 12, "C : cadre fermé")
    c.setFillColor(MUT); c.setFont("Helvetica", 7)
    c.drawString(x0 + 10, y0 + 20, "Mandrin 4Ø (Ø≤16) / 7Ø au-delà. Longueur développée = segments droits + arcs à l'axe.")
    sh.notes([
        ("Usage", "Tableau indicatif d'ancrage et de recouvrement par diamètre, pour la mise en page du dossier."),
        ("À vérifier", "Position de bétonnage, confinement, pression sous coude et pourcentage de barres recouvertes au même endroit."),
        ("Formes", "Les familles I/L/U/C servent au calcul des longueurs de la nomenclature."),
    ])


# ----------------------------------------------------------------- nomenclature / métré ----
def _grid_table(c, x, y_top, rows, widths, fs=7.2, rh=14):
    c.setFont("Helvetica", fs)
    yy = y_top
    for ri, row in enumerate(rows):
        xx = x
        if ri == 0:
            c.setFillColor(INK)
            c.rect(x, yy - rh, sum(widths), rh, stroke=0, fill=1)
        elif ri % 2 == 0:
            c.setFillColor(colors.HexColor("#f6f8fa"))
            c.rect(x, yy - rh, sum(widths), rh, stroke=0, fill=1)
        for ci, cell in enumerate(row):
            c.setFillColor(colors.white if ri == 0 else INK)
            c.setFont("Helvetica-Bold" if ri == 0 else "Helvetica", fs)
            c.drawString(xx + 4, yy - rh + 4, str(cell) if cell is not None else "—")
            xx += widths[ci]
        c.setStrokeColor(LINE); c.setLineWidth(0.3)
        c.line(x, yy - rh, x + sum(widths), yy - rh)
        yy -= rh
    c.setStrokeColor(LINE)
    xx = x
    for w in widths:
        c.line(xx, y_top, xx, yy); xx += w
    c.line(xx, y_top, xx, yy)
    c.line(x, y_top, x + sum(widths), y_top)
    return yy


def _nomenclature_sheet(c, ctx, metre_data, code, feuille):
    sh = Sheet(c, ctx, "Nomenclature des aciers & métré", "Longueurs à l'axe, poids théoriques et estimation matière",
               code, feuille, "sans")
    x0, y0, x1, y1 = sh.area
    steel = (metre_data or {}).get("steel", {})
    rows = [["Repère", "Ouvrage", "Niveau", "Section", "Aciers", "Nb", "Lg (m)", "Poids (kg)"]]
    for rrow in steel.get("schedule", []):
        rows.append([rrow.get("mark"), rrow.get("type"), rrow.get("level"), rrow.get("section"),
                     rrow.get("bars"), rrow.get("count"),
                     rrow.get("unit_length_m") if rrow.get("unit_length_m") is not None else "—", rrow.get("weight_kg")])
    rows.append(["", "", "", "", "TOTAL acier", "", f"{steel.get('ratio_kg_m3','')} kg/m³", steel.get("total_kg")])
    yend = _grid_table(c, x0 + 10, y1 - 6, rows, [70, 70, 70, 95, 160, 40, 55, 70])
    # métré béton + coût (sous le tableau)
    conc = (metre_data or {}).get("concrete", {})
    vt = conc.get("by_type_m3", {})
    LBL = {"slab": "Dalles", "beam": "Poutres", "column": "Poteaux", "wall": "Voiles", "footing": "Semelles"}
    crows = [["Béton par ouvrage", "m³"]] + [[LBL.get(k, k), round(v, 2)] for k, v in vt.items()]
    crows.append(["TOTAL béton", conc.get("total_m3")])
    _grid_table(c, x0 + 10, yend - 18, crows, [160, 70])
    cost = (metre_data or {}).get("cost", {})
    krows = [["Estimation matière", "Qté", "PU", "Coût (€)"],
             ["Béton", f"{conc.get('total_m3')} m³", f"{cost.get('concrete_eur_m3')} €/m³", cost.get("concrete_eur")],
             ["Acier", f"{steel.get('total_kg')} kg", f"{cost.get('steel_eur_kg')} €/kg", cost.get("steel_eur")],
             ["TOTAL", "", "", cost.get("total_eur")]]
    _grid_table(c, x0 + 260, yend - 18, krows, [90, 80, 80, 80])
    sh.notes([
        ("Conventions", "I=barre droite ; L=1 retour ; U=2 retours ; C=cadre. Poids = longueur à l'axe × masse (7850 kg/m³)."),
        ("Périmètre", "Quantités du ferraillage gouvernant par niveau + forfait semelles. Hors chutes, aciers de peau et recouvrements détaillés."),
        ("Usage", "Métré indicatif pour chiffrage ; non contractuel pour la fabrication."),
    ])


# ----------------------------------------------------------------- note de calcul ----
def _calc_sheet(c, ctx, model, summary, soil, code, feuille):
    sh = Sheet(c, ctx, "Note de calcul — références et limites",
               "Résultats déterministes (EN 1990/1991/1992/1997) — hypothèses du pré-modèle", code, feuille, "sans")
    x0, y0, x1, y1 = sh.area
    c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 + 10, y1 - 8, "FONDATIONS — contrainte admissible G2")
    frows = [["Semelle", "Type", "N_ELS (kN)", "N_ELU (kN)", "Dim (m)", "Statut"]]
    for f in (summary or {}).get("footings", [])[:10]:
        ok = f.get("dim_m") is not None
        frows.append([f.get("id"), f.get("type"), f.get("n_els_kn"), f.get("n_elu_kn"),
                      f.get("dim_m") if ok else "—", "dimensionnée" if ok else "sol G2 à confirmer"])
    yend = _grid_table(c, x0 + 10, y1 - 22, frows, [90, 70, 80, 80, 70, 90])
    c.setFillColor(BRAND); c.setFont("Helvetica-Bold", 9)
    c.drawString(x0 + 10, yend - 16, "SUPERSTRUCTURE — efforts gouvernants")
    ss = (summary or {}).get("superstructure") or {}
    srows = [["Élément", "Niveau", "Section", "Sollicitation", "Aciers"]]
    for b in ss.get("beams", [])[:6]:
        top = f" / sup {b['as_top_req_cm2']} cm²" if b.get("as_top_req_cm2") is not None else ""
        srows.append([f"PTR {b.get('id','')}", b.get("level"), f"{int(round(b['b_m']*100))}×{int(round(b['h_m']*100))}",
                      f"M={b.get('med_knm')} kN·m", f"inf {b.get('as_req_cm2')} cm²{top}"])
    for cc in ss.get("columns", [])[:4]:
        srows.append([f"POT {cc.get('id','')}", cc.get("level"), f"{int(round(cc['b_m']*100))}×{int(round(cc['h_m']*100))}",
                      f"N={cc.get('n_ed_kn')} kN", cc.get("long_bars")])
    for ww in ss.get("walls", [])[:4]:
        srows.append([f"VOI {ww.get('id','')}", ww.get("level"), f"ép.{int(round(ww['thickness_m']*100))}",
                      f"N={ww.get('n_ed_kn')} kN", f"V {ww.get('as_vert_cm2')} cm²"])
    _grid_table(c, x0 + 10, yend - 30, srows, [90, 70, 80, 120, 110])
    notes = [
        ("Sol (G2)", f"q_ELS={soil.get('q_els_kpa','—')} kPa ; q_ELU={soil.get('q_elu_kpa','—')} kPa ; "
                     f"{soil.get('foundation_type','—')} ; ancrage {soil.get('anchorage_depth_m','—')} m ; "
                     f"{soil.get('soil_class','—')}."),
        ("Descente de charges", f"Réaction au sol ELU ≈ {(summary or {}).get('ground_reaction_elu_kn','—')} kN. "
                                "Combinaisons EN 1990 (ELU/ELS), charges EN 1991-1-1."),
        ("Hypothèses", "Trame régulière, transferts centrés, pas d'action horizontale (vent/séisme) ni second ordre. "
                       + ("Poutres en files continues (trois moments, Q alternées), chapeaux sur appuis, "
                          "flèche fissurée long terme ; poteaux majorés de la continuité."
                          if ss.get("continuity") else "Poutres isostatiques.")),
        ("Limites", "Pré-dimensionnement automatique NON EXÉCUTOIRE. Stabilité d'ensemble, nœuds, flèches, "
                    "poinçonnement, tassements et détails constructifs à valider par l'ingénieur."),
    ]
    sh.notes(notes)


# ----------------------------------------------------------------- orchestrateur ----
def _levels_bottom_up(model):
    seen = []
    for e in model.get("elements", []):
        lv = e.get("level", "?")
        if lv != "Fondations" and lv not in seen:
            seen.append(lv)
    # seen est top-down (Toiture..RDC) → on remonte RDC -> Toiture
    return list(reversed(seen))


def build_coffrage_pdf(model: dict, revision: int, title: str, superstructure: dict | None = None,
                       metre_data: dict | None = None, marks: dict | None = None,
                       summary: dict | None = None, soil: dict | None = None, inputs: dict | None = None) -> bytes:
    marks = marks or {}
    superstructure = superstructure or {}
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=landscape(A3))
    ctx = {"project": title, "rev": revision,
           "sub1": "Pré-dimensionnement généré automatiquement (auto-pilote BET)",
           "sub2": (inputs or {}).get("building", {}).get("destination", "").capitalize() if inputs else "",
           "date": "Dossier auto-pilote ConstruPilot"}
    elements = model.get("elements", [])

    # 1) Coffrage fondations
    fnd = [e for e in elements if e.get("level") == "Fondations"]
    nsheet = 1
    if fnd:
        _coffrage_sheet(c, ctx, "Fondations", fnd, marks, "C01", nsheet, foundation=True); c.showPage(); nsheet += 1
    # 2) Coffrage par niveau (bas -> haut)
    for i, lv in enumerate(_levels_bottom_up(model), start=2):
        els = [e for e in elements if e.get("level") == lv]
        if els:
            _coffrage_sheet(c, ctx, lv, els, marks, f"C{i:02d}", nsheet); c.showPage(); nsheet += 1
    # 3) Ferraillage semelles
    footings = (summary or {}).get("footings") or []
    if footings:
        _ferr_semelles_sheet(c, ctx, footings, "F01", nsheet); c.showPage(); nsheet += 1
    # 4) Poteaux & voiles
    if superstructure.get("columns") or superstructure.get("walls"):
        _ferr_lineaires_sheet(c, ctx, superstructure.get("columns") or [], superstructure.get("walls") or [], "F02", nsheet)
        c.showPage(); nsheet += 1
    # 5) Poutres
    if superstructure.get("beams"):
        _ferr_poutres_sheet(c, ctx, superstructure.get("beams"), "F03", nsheet); c.showPage(); nsheet += 1
    # 6) Dalles / nappes (niveau courant représentatif)
    lv_up = _levels_bottom_up(model)
    if lv_up:
        rep_lv = lv_up[0]
        if _dalle_sheet(c, ctx, rep_lv, [e for e in elements if e.get("level") == rep_lv], "F04", nsheet):
            c.showPage(); nsheet += 1
    # 7) Ancrages
    _ancrage_sheet(c, ctx, "D01", nsheet); c.showPage(); nsheet += 1
    # 8) Nomenclature + métré
    if metre_data:
        _nomenclature_sheet(c, ctx, metre_data, "N01", nsheet); c.showPage(); nsheet += 1
    # 9) Note de calcul
    _calc_sheet(c, ctx, model, summary or {}, soil or {}, "G01", nsheet); c.showPage()

    c.save()
    return out.getvalue()
