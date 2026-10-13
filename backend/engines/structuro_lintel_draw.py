"""Schéma indicatif d'un linteau de reprise d'ouverture (élévation + coupe) pour le dossier BET.

Dessin vectoriel schématique (reportlab.graphics), NON COTÉ POUR EXÉCUTION. Construit à partir
du résultat déterministe de structuro_lintel.lintel_design (clé 'geometry').
"""
from __future__ import annotations

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors

_DK = colors.HexColor("#1f2937")
_MUT = colors.HexColor("#6b7280")
_FILL = colors.HexColor("#e5e7eb")
_STEEL = colors.HexColor("#334155")
_RC = colors.HexColor("#d1d5db")
_BAR = colors.HexColor("#b91c1c")


def _hatch(d, x, y, w, h):
    d.add(Rect(x, y, w, h, strokeColor=_DK, strokeWidth=0.6, fillColor=_FILL))
    step = 6.0
    off = 0.0
    while off < w + h:
        x1 = x + max(0.0, off - h); y1 = y + min(off, h)
        x2 = x + min(off, w); y2 = y + max(0.0, off - w)
        d.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#9ca3af"), strokeWidth=0.3))
        off += step


def _elevation(d, geom, ox, oy, w, h):
    L = float(geom.get("clear_span_m") or 1.0)
    a = float(geom.get("bearing_m") or 0.2)
    pier = 0.35
    total_m = L + 2 * a + 2 * pier
    sc = (w - 20) / total_m if total_m > 0 else 1.0
    base = oy + 26
    op_h = h - 70
    x = ox + 10
    # piers (trumeaux) hachurés
    _hatch(d, x, base, pier * sc, op_h)
    xr = x + (pier + L + 2 * a) * sc
    _hatch(d, xr, base, pier * sc, op_h)
    # ouverture (vide)
    opx = x + pier * sc
    d.add(Rect(opx, base, (L + 2 * a) * sc, op_h, strokeColor=colors.HexColor("#d1d5db"),
               strokeWidth=0.4, fillColor=colors.white))
    # linteau au-dessus de l'ouverture (déborde de a de chaque côté)
    lint_y = base + op_h
    d.add(Rect(opx, lint_y, (L + 2 * a) * sc, 12, strokeColor=_DK, strokeWidth=1.0, fillColor=_STEEL))
    # maçonnerie au-dessus (voûte triangle ou rectangle)
    top = lint_y + 12
    cx = opx + (L + 2 * a) * sc / 2.0
    if geom.get("masonry_model") == "arching":
        apex = min(top + (L / 2.0) * 1.0 * sc, oy + h - 4)
        d.add(Line(opx + a * sc, top, cx, apex, strokeColor=_MUT, strokeWidth=0.6))
        d.add(Line(cx, apex, opx + (a + L) * sc, top, strokeColor=_MUT, strokeWidth=0.6))
    else:
        d.add(Rect(opx + a * sc, top, L * sc, min(28, oy + h - 4 - top),
                   strokeColor=_MUT, strokeWidth=0.4, fillColor=colors.HexColor("#f3f4f6")))
    # bearings + cote portée
    d.add(Line(x + pier * sc, base - 8, opx + (a + L + a) * sc, base - 8, strokeColor=_DK, strokeWidth=0.5))
    d.add(String(cx, base - 18, f"L = {L:g} m", fontSize=8, fillColor=_DK, textAnchor="middle"))
    d.add(String(opx + a * sc / 2, lint_y - 10, f"a={a:g}", fontSize=6, fillColor=_MUT, textAnchor="middle"))
    d.add(String(ox + 10, oy + h - 8, "Alçado (esquema)", fontSize=7.5, fillColor=_MUT))


def _isection(d, cx, base, bf, hh, n):
    """Silhouette de profilé(s) en I."""
    tf = max(3.0, hh * 0.08)
    tw = max(2.0, bf * 0.12)
    gap = 6.0
    tot = n * bf + (n - 1) * gap
    x0 = cx - tot / 2.0
    for i in range(n):
        bx = x0 + i * (bf + gap)
        d.add(Rect(bx, base + hh - tf, bf, tf, strokeColor=_DK, strokeWidth=0.6, fillColor=_STEEL))
        d.add(Rect(bx, base, bf, tf, strokeColor=_DK, strokeWidth=0.6, fillColor=_STEEL))
        d.add(Rect(bx + bf / 2 - tw / 2, base, tw, hh, strokeColor=_DK, strokeWidth=0.6, fillColor=_STEEL))


def _section(d, geom, ox, oy, w, h):
    mat = geom.get("recommended")
    steel, rc = geom.get("steel"), geom.get("rc")
    cx = ox + w / 2.0
    base = oy + 30
    d.add(String(ox + 6, oy + h - 8, "Corte (esquema)", fontSize=7.5, fillColor=_MUT))
    if mat == "steel" and steel and steel.get("status") == "ok":
        hh = min(h - 55, 70)
        bf = min(w * 0.22, 26)
        _isection(d, cx, base, bf, hh, int(steel.get("count", 1)))
        bp = steel.get("bearing_plate") or {}
        if bp:
            pw = min(w * 0.6, 90)
            d.add(Rect(cx - pw / 2, base - 8, pw, 5, strokeColor=_DK, strokeWidth=0.7, fillColor=colors.HexColor("#94a3b8")))
            d.add(String(cx, base - 18, f"platine {int(bp.get('length_mm',0))}×{int(bp.get('width_mm',0))}×{int(bp.get('thickness_mm',0))} mm",
                         fontSize=6, fillColor=_MUT, textAnchor="middle"))
        d.add(String(cx, base + hh + 8, steel.get("label", ""), fontSize=8, fillColor=_DK, textAnchor="middle"))
    elif rc and rc.get("status") == "ok":
        b = float(rc.get("b_mm", 200)); hmm = float(rc.get("h_mm", 300))
        sc = min((w * 0.5) / max(b, 1), (h - 55) / max(hmm, 1))
        bw, bh = b * sc, hmm * sc
        x0 = cx - bw / 2.0
        d.add(Rect(x0, base, bw, bh, strokeColor=_DK, strokeWidth=1.0, fillColor=_RC))
        d.add(Rect(x0 + 4, base + 4, bw - 8, bh - 8, strokeColor=_BAR, strokeWidth=0.6, fillColor=None))  # cadre
        for k in range(3):
            d.add(String(0, 0, "", fontSize=1))
            cxk = x0 + 8 + k * (bw - 16) / 2.0
            d.add(Rect(cxk - 1.6, base + 6, 3.2, 3.2, strokeColor=_BAR, strokeWidth=0.8, fillColor=_BAR))
        d.add(String(cx, base + bh + 8, rc.get("label", ""), fontSize=7.5, fillColor=_DK, textAnchor="middle"))
        det = (rc.get("detailing") or {}).get("anchorage") or {}
        if det:
            d.add(String(cx, base - 10, f"ancrage {int(det.get('straight_mm',0))} mm (crochet {int(det.get('hook_mm',0))} mm)",
                         fontSize=6, fillColor=_MUT, textAnchor="middle"))


def lintel_figure(lint: dict, width: float = 460, height: float = 200) -> Drawing:
    d = Drawing(width, height)
    geom = (lint or {}).get("geometry") or {}
    d.add(Rect(0, 0, width, height, strokeColor=colors.HexColor("#e5e7eb"), strokeWidth=0.5, fillColor=colors.white))
    _elevation(d, geom, 0, 0, width * 0.56, height)
    d.add(Line(width * 0.57, 10, width * 0.57, height - 10, strokeColor=colors.HexColor("#e5e7eb"), strokeWidth=0.5))
    _section(d, geom, width * 0.58, 0, width * 0.42, height)
    return d
