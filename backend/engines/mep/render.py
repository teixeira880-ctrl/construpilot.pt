"""Rendu vectoriel des plans d'exécution : une même « scène » produit le SVG (interface)
et le dessin PDF (reportlab), sans dépendance externe.

Couleurs normalisées :
  • conducteurs (NF C 15-100 / IEC 60445) : phase marron, neutre bleu clair, PE vert/jaune ;
  • réseaux d'eau (convention des plans de plomberie) : eau froide bleue, eau chaude rouge,
    eaux usées grises, eaux vannes marron ;
  • symboles électriques en noir (NF EN 60617).
"""
from __future__ import annotations

import math
from html import escape

from . import geometry as G
from .equipment import FOOTPRINT
from .i18n import net, tr

PHASE = "#8B4513"
NEUTRAL = "#4FA3E0"
PE_GREEN = "#1E8E3E"
PE_YELLOW = "#F4C20D"
EF = "#1565C0"
ECS = "#D32F2F"
EU = "#7A7A7A"
EV = "#6D4C41"
INK = "#111111"
WALL = "#9AA0A6"
ROOM_FILL = "#FAFAF7"
BRAND = "#F97316"
NAVY = "#0F172A"
NET_COLOR = {"EF": EF, "ECS": ECS, "EU": EU, "EV": EV, "EU/EV": EV}


class Scene:
    def __init__(self):
        self.ops: list[tuple] = []

    def line(self, pts, color=INK, w=0.02, dash=None):
        self.ops.append(("line", [tuple(p) for p in pts], color, w, dash))

    def poly(self, pts, fill=None, stroke=INK, w=0.02):
        self.ops.append(("poly", [tuple(p) for p in pts], fill, stroke, w))

    def circle(self, c, r, fill=None, stroke=INK, w=0.02):
        self.ops.append(("circle", tuple(c), r, fill, stroke, w))

    def arc(self, c, r, a0, a1, stroke=INK, w=0.02):
        self.ops.append(("arc", tuple(c), r, a0, a1, stroke, w))

    def text(self, p, s, size=0.18, color=INK, anchor="middle", bold=False):
        self.ops.append(("text", tuple(p), str(s), size, color, anchor, bold))

    def bounds(self):
        xs, ys = [], []
        for op in self.ops:
            if op[0] in ("line", "poly"):
                for x, y in op[1]:
                    xs.append(x)
                    ys.append(y)
            elif op[0] in ("circle", "arc", "text"):
                xs.append(op[1][0])
                ys.append(op[1][1])
        if not xs:
            return 0, 0, 1, 1
        return min(xs), min(ys), max(xs), max(ys)

    # ---------------------------------------------------------------- SVG
    def to_svg(self, px_per_m=60, margin=0.8, title=None) -> str:
        x0, y0, x1, y1 = self.bounds()
        x0, y0, x1, y1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
        W, H = (x1 - x0) * px_per_m, (y1 - y0) * px_per_m
        k = px_per_m
        tx = lambda x: (x - x0) * k  # noqa: E731
        ty = lambda y: (y - y0) * k  # noqa: E731
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
               f'width="{W:.0f}" height="{H:.0f}" font-family="DejaVu Sans, Arial, sans-serif">']
        if title:
            out.append(f"<title>{escape(title)}</title>")
        out.append(f'<rect width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>')
        for op in self.ops:
            kind = op[0]
            if kind == "line":
                _, pts, color, w, dash = op
                d = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in pts)
                da = f' stroke-dasharray="{" ".join(str(round(v * k, 1)) for v in dash)}"' if dash else ""
                out.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{w * k:.2f}"'
                           f' stroke-linejoin="round" stroke-linecap="round"{da}/>')
            elif kind == "poly":
                _, pts, fill, stroke, w = op
                d = " ".join(f"{tx(x):.1f},{ty(y):.1f}" for x, y in pts)
                out.append(f'<polygon points="{d}" fill="{fill or "none"}" stroke="{stroke or "none"}"'
                           f' stroke-width="{w * k:.2f}"/>')
            elif kind == "circle":
                _, c, r, fill, stroke, w = op
                out.append(f'<circle cx="{tx(c[0]):.1f}" cy="{ty(c[1]):.1f}" r="{r * k:.1f}" '
                           f'fill="{fill or "none"}" stroke="{stroke or "none"}" stroke-width="{w * k:.2f}"/>')
            elif kind == "arc":
                _, c, r, a0, a1, stroke, w = op
                p0 = (c[0] + r * math.cos(a0), c[1] + r * math.sin(a0))
                p1 = (c[0] + r * math.cos(a1), c[1] + r * math.sin(a1))
                large = 1 if (a1 - a0) % (2 * math.pi) > math.pi else 0
                out.append(f'<path d="M{tx(p0[0]):.1f},{ty(p0[1]):.1f} A{r * k:.1f},{r * k:.1f} 0 {large} 1 '
                           f'{tx(p1[0]):.1f},{ty(p1[1]):.1f}" fill="none" stroke="{stroke}" stroke-width="{w * k:.2f}"/>')
            elif kind == "text":
                _, p, s, size, color, anchor, bold = op
                fw = ' font-weight="bold"' if bold else ""
                out.append(f'<text x="{tx(p[0]):.1f}" y="{ty(p[1]) + size * k * 0.35:.1f}" font-size="{size * k:.1f}" '
                           f'fill="{color}" text-anchor="{anchor}"{fw}>{escape(s)}</text>')
        out.append("</svg>")
        return "\n".join(out)

    # ---------------------------------------------------------------- PDF (reportlab)
    def draw(self, canvas, ox, oy, width, height, font="Helvetica", font_bold="Helvetica-Bold", margin=0.5,
             max_scale=None, align_top=False):
        """Dessine la scène dans le cadre (ox, oy, width, height) en points PDF, à l'échelle maximale."""
        from reportlab.lib.colors import HexColor
        x0, y0, x1, y1 = self.bounds()
        x0, y0, x1, y1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
        k = min(width / (x1 - x0), height / (y1 - y0))
        if max_scale:
            k = min(k, max_scale)
        dx = ox + (width - (x1 - x0) * k) / 2
        dy = oy + (height - (y1 - y0) * k) / 2
        if align_top:
            dx = ox
            dy = oy + height - (y1 - y0) * k
        X = lambda x: dx + (x - x0) * k  # noqa: E731
        Y = lambda y: dy + (y1 - y) * k  # noqa: E731
        c = canvas
        c.saveState()
        c.setLineJoin(1)
        c.setLineCap(1)
        for op in self.ops:
            kind = op[0]
            if kind == "line":
                _, pts, color, w, dash = op
                c.setStrokeColor(HexColor(color))
                c.setLineWidth(max(0.2, w * k))
                c.setDash([v * k for v in dash] if dash else [])
                p = c.beginPath()
                p.moveTo(X(pts[0][0]), Y(pts[0][1]))
                for x, y in pts[1:]:
                    p.lineTo(X(x), Y(y))
                c.drawPath(p, stroke=1, fill=0)
                c.setDash([])
            elif kind == "poly":
                _, pts, fill, stroke, w = op
                p = c.beginPath()
                p.moveTo(X(pts[0][0]), Y(pts[0][1]))
                for x, y in pts[1:]:
                    p.lineTo(X(x), Y(y))
                p.close()
                if fill:
                    c.setFillColor(HexColor(fill))
                if stroke:
                    c.setStrokeColor(HexColor(stroke))
                    c.setLineWidth(max(0.2, w * k))
                c.drawPath(p, stroke=1 if stroke else 0, fill=1 if fill else 0)
            elif kind == "circle":
                _, cc, r, fill, stroke, w = op
                if fill:
                    c.setFillColor(HexColor(fill))
                if stroke:
                    c.setStrokeColor(HexColor(stroke))
                    c.setLineWidth(max(0.2, w * k))
                c.circle(X(cc[0]), Y(cc[1]), r * k, stroke=1 if stroke else 0, fill=1 if fill else 0)
            elif kind == "arc":
                _, cc, r, a0, a1, stroke, w = op
                c.setStrokeColor(HexColor(stroke))
                c.setLineWidth(max(0.2, w * k))
                # repère PDF : y vers le haut → angles inversés
                start = -math.degrees(a1)
                extent = math.degrees(a1 - a0)
                c.arc(X(cc[0]) - r * k, Y(cc[1]) - r * k, X(cc[0]) + r * k, Y(cc[1]) + r * k, start, extent)
            elif kind == "text":
                _, p, s, size, color, anchor, bold = op
                c.setFillColor(HexColor(color))
                fs = size * k
                c.setFont(font_bold if bold else font, fs)
                yy = Y(p[1]) - fs * 0.35
                if anchor == "middle":
                    c.drawCentredString(X(p[0]), yy, s)
                elif anchor == "end":
                    c.drawRightString(X(p[0]), yy, s)
                else:
                    c.drawString(X(p[0]), yy, s)
        c.restoreState()
        return k


# ======================================================================================
# Fonds de plan
# ======================================================================================
def _base(scene, level, lang):
    for r in level["rooms"]:
        scene.poly(r["polygon"], fill=ROOM_FILL, stroke=WALL, w=0.05)
    for o in level["openings"]:
        a, b = o["a"], o["b"]
        if o["kind"] in ("fenetre", "baie"):
            scene.line([a, b], color="#5B9BD5", w=0.05)
            scene.line([a, b], color="#FFFFFF", w=0.015)
        elif o["kind"] == "passage":
            scene.line([a, b], color="#C7CCD1", w=0.02, dash=[0.08, 0.08])
        elif o["kind"] == "porte_garage":
            scene.line([a, b], color="#FFFFFF", w=0.08)
            scene.line([a, b], color="#B0B5BA", w=0.015, dash=[0.15, 0.1])
        else:
            scene.line([a, b], color="#FFFFFF", w=0.08)
            L = G.dist(a, b)
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            scene.arc(a, L, ang, ang + math.pi / 2, stroke="#B0B5BA", w=0.012)
    for r in level["rooms"]:
        poly = [tuple(p) for p in r["polygon"]]
        c = G.centroid(poly)
        t = (c[0], c[1] - 0.55)
        if not G.point_in_polygon(t, poly):
            t = G.interior_point_near(t, poly)
        scene.text((t[0], t[1] - 0.1), r["name"], 0.20, "#55595F", bold=True)
        scene.text((t[0], t[1] + 0.15), f'{r["area_m2"]:.2f} m²'.replace(".", ","), 0.14, "#7B8086")


def _north_and_scale(scene, level):
    xs = [p[0] for r in level["rooms"] for p in r["polygon"]]
    ys = [p[1] for r in level["rooms"] for p in r["polygon"]]
    x0, y1 = min(xs), max(ys)
    y = y1 + 0.6
    scene.line([(x0, y), (x0 + 1, y)], INK, 0.03)
    scene.line([(x0, y - 0.08), (x0, y + 0.08)], INK, 0.02)
    scene.line([(x0 + 1, y - 0.08), (x0 + 1, y + 0.08)], INK, 0.02)
    scene.text((x0 + 0.5, y + 0.25), "1 m", 0.16)


# ======================================================================================
# Symboles électriques (NF EN 60617 simplifiés)
# ======================================================================================
def _sym_elec(scene, p, kind, label=None):
    x, y = p["x"], p["y"]
    r = 0.12
    if kind in ("prise", "prise_plan_travail", "prise_specialisee"):
        scene.arc((x, y), r, math.pi, 2 * math.pi, stroke=INK, w=0.025)
        scene.line([(x - r, y), (x + r, y)], INK, 0.025)
        scene.line([(x, y), (x, y + 0.12)], INK, 0.025)
        if kind == "prise_plan_travail":
            scene.line([(x - r, y - 0.17), (x + r, y - 0.17)], INK, 0.02)
        if kind == "prise_specialisee":
            scene.text((x, y - 0.25), {"lave_linge": "LL", "lave_vaisselle": "LV", "four": "F",
                                       "seche_linge": "SL", "congelateur": "CG"}.get(p.get("use"), "S"), 0.14, INK, bold=True)
    elif kind == "sortie_cable":
        scene.poly(G.rect_footprint((x, y), 0.26, 0.2), fill="#FFFFFF", stroke=INK, w=0.025)
        scene.text((x, y), {"plaque": "32A", "chauffe_eau": "CE", "vmc": "VMC", "irve": "VE"}.get(p.get("use"), "20A"), 0.10, INK, bold=True)
    elif kind in ("point_lumineux", "point_lumineux_ext"):
        scene.circle((x, y), 0.15, fill="#FFFFFF", stroke=INK, w=0.025)
        d = 0.105
        scene.line([(x - d, y - d), (x + d, y + d)], INK, 0.025)
        scene.line([(x - d, y + d), (x + d, y - d)], INK, 0.025)
    elif kind in ("interrupteur", "va_et_vient"):
        scene.circle((x, y), 0.06, fill=INK, stroke=None)
        scene.line([(x, y), (x + 0.16, y - 0.16)], INK, 0.025)
        scene.line([(x + 0.16, y - 0.16), (x + 0.22, y - 0.1)], INK, 0.025)
        if kind == "va_et_vient":
            scene.line([(x, y), (x - 0.16, y + 0.16)], INK, 0.025)
            scene.line([(x - 0.16, y + 0.16), (x - 0.22, y + 0.1)], INK, 0.025)
    elif kind == "rj45":
        scene.poly([(x - 0.12, y + 0.1), (x + 0.12, y + 0.1), (x, y - 0.12)], fill="#FFFFFF", stroke=INK, w=0.025)
        scene.text((x, y + 0.24), "RJ", 0.11, INK)
    elif kind == "tableau":
        scene.poly(G.rect_footprint((x, y), 0.6, 0.25), fill=INK, stroke=INK)
        if label:
            scene.text((x, y - 0.3), label, 0.13, INK, bold=True)
    elif kind == "coffret_com":
        scene.poly(G.rect_footprint((x, y + 0.3), 0.5, 0.2), fill="#FFFFFF", stroke=INK, w=0.025)
        scene.text((x, y + 0.3), "COM", 0.11, INK, bold=True)
    elif kind == "daaf":
        scene.circle((x, y), 0.13, fill="#FFFFFF", stroke="#C62828", w=0.03)
        scene.text((x, y), "D", 0.13, "#C62828", bold=True)
    elif kind == "les":
        scene.circle((x, y), 0.11, fill=PE_YELLOW, stroke=PE_GREEN, w=0.04)
        scene.text((x, y + 0.24), "LES", 0.10, PE_GREEN, bold=True)


def elec_scene(study, level_id) -> Scene:
    lang = study["lang"]
    lv = next(level for level in study["levels"] if level["id"] == level_id)
    sc = Scene()
    _base(sc, lv, lang)
    pts = {p["id"]: p for p in study["points"]}
    board = study["electrical"]["board"]
    # commandes → points lumineux (pointillé)
    for p in study["points"]:
        if p["level_id"] == level_id and p["kind"] in ("interrupteur", "va_et_vient"):
            for lid in p.get("controls") or []:
                lt = pts.get(lid)
                if lt:
                    sc.line([(p["x"], p["y"]), (lt["x"], lt["y"])], PHASE, 0.012, dash=[0.04, 0.06])
    for p in study["points"]:
        if p["level_id"] != level_id:
            continue
        _sym_elec(sc, p, p["kind"], "TGBT / GTL")
        if p.get("circuit_id") and p["kind"] not in ("tableau",):
            sc.text((p["x"] + 0.22, p["y"] + 0.2), p["circuit_id"], 0.11, PHASE, anchor="start")
    _north_and_scale(sc, lv)
    return sc


# ======================================================================================
# Plomberie
# ======================================================================================
def _sym_fixture(scene, f, lang, rules_fx):
    w, d = FOOTPRINT.get(f["kind"], (0.5, 0.5))
    fp = G.rect_footprint((f["x"], f["y"]), w * 0.8, d * 0.8)
    scene.poly(fp, fill="#FFFFFF", stroke="#424242", w=0.02)
    lab = (rules_fx.get(f["kind"]) or {}).get("label") or {"plaque": "Plaque", "four": "Four",
                                                           "chauffe_eau": "CE"}.get(f["kind"], f["kind"])
    scene.text((f["x"], f["y"]), lab, 0.11, "#424242")


def plumb_scene(study, level_id, rules) -> Scene:
    lang = study["lang"]
    lv = next(level for level in study["levels"] if level["id"] == level_id)
    pl = study["plumbing"]
    fx_rules = rules["plumbing"]["fixtures"]
    sc = Scene()
    _base(sc, lv, lang)
    for f in study["equipment"]:
        if f["level_id"] == level_id and f["kind"] in (*fx_rules.keys(), "chauffe_eau"):
            _sym_fixture(sc, f, lang, fx_rules)
    # évacuations (dessous), puis alimentations
    if pl.get("collector") and level_id == study["levels"][0]["id"]:
        sc.line(pl["collector"]["path"], EV, 0.07)
        mid = pl["collector"]["path"][len(pl["collector"]["path"]) // 2]
        sc.text((mid[0] + 0.15, mid[1]), f'COL Ø{pl["collector"]["diameter_mm"]} — {round(pl["collector"]["slope"] * 100, 1)} %',
                0.13, EV, anchor="start", bold=True)
    for d in pl["drains"]:
        if d["level_id"] != level_id:
            continue
        col = NET_COLOR.get(d["net"], EU)
        sc.line(d["path"], col, 0.045)
        a = d["path"][0]
        sc.text((a[0], a[1] + 0.32), f'Ø{d["diameter_mm"]}', 0.11, col)
    for s in pl["supplies"]:
        if s["level_id"] != level_id:
            continue
        sc.line(s["path"], NET_COLOR[s["net"]], 0.03)
    for f in study["equipment"]:
        if f["level_id"] != level_id:
            continue
        ss = [s for s in pl["supplies"] if s["fixture_id"] == f["id"]]
        for s in ss:
            end = s["path"][-1]
            sc.circle(end, 0.05, fill=NET_COLOR[s["net"]], stroke=None)
        if ss:
            sc.text((f["x"], f["y"] + 0.42), " / ".join(f'{net(lang, s["net"])} {s["pipe_ext_mm"]}' for s in ss), 0.10, "#37474F")
    for m in pl["manifolds"]:
        if m["level_id"] != level_id:
            continue
        sc.poly(G.rect_footprint((m["x"], m["y"]), 0.5, 0.22), fill="#FFFFFF", stroke=EF, w=0.04)
        sc.line([(m["x"] - 0.22, m["y"] + 0.07), (m["x"] + 0.22, m["y"] + 0.07)], ECS, 0.04)
        sc.text((m["x"], m["y"] - 0.3), f'{tr(lang, "manifold")} {m["outlets_ef"]}{net(lang, "EF")}/{m["outlets_ecs"]}{net(lang, "ECS")}', 0.12, INK, bold=True)
    for st in pl["stacks"]:
        sc.circle((st["x"], st["y"]), 0.14, fill=EV, stroke=INK, w=0.02)
        sc.text((st["x"] + 0.25, st["y"] - 0.2), f'{tr(lang, "stack")} Ø{st["diameter_mm"]}', 0.13, EV, anchor="start", bold=True)
    ground_id = study["levels"][0]["id"]
    mans = {m["id"]: m for m in pl["manifolds"]}
    for r in pl["risers"]:
        off = 0.2 if r["net"] == "ECS" else -0.2
        top = (r["x"] + off, r["y"] + 0.35)
        if level_id == ground_id and r["from"] in mans:
            g = mans[r["from"]]
            sc.line(G.manhattan_path((g["x"] + off / 3, g["y"] + off / 3), top), NET_COLOR[r["net"]], 0.035)
        if level_id == ground_id or r["to"].endswith(level_id):
            sc.circle(top, 0.08, fill=NET_COLOR[r["net"]], stroke=INK, w=0.01)
    if pl["risers"] and level_id == ground_id:
        r0 = pl["risers"][0]
        sc.text((r0["x"], r0["y"] + 0.7), tr(lang, "riser"), 0.12, INK, bold=True)
    if pl.get("exit") and level_id == study["levels"][0]["id"]:
        e = pl["exit"]
        sc.poly(G.rect_footprint((e["x"], e["y"]), 0.3, 0.3), fill="#FFFFFF", stroke=EV, w=0.04)
        sc.text((e["x"], e["y"] + 0.35), tr(lang, "exit"), 0.12, EV)
    if pl.get("main") and pl["main"].get("entry") and level_id == study["levels"][0]["id"]:
        en = pl["main"]["entry"]
        m = next(m for m in pl["manifolds"] if m["id"] == pl["main"]["to"])
        sc.line(G.manhattan_path(tuple(en), (m["x"], m["y"])), EF, 0.06)
        sc.text((en[0], en[1] + 0.35), f'{net(lang, "AEP")} Ø{pl["main"]["pipe_ext_mm"]}', 0.12, EF, bold=True)
    _north_and_scale(sc, lv)
    return sc


# ======================================================================================
# Schéma unifilaire
# ======================================================================================
def unifilar_scene(study) -> Scene:
    lang = study["lang"]
    el = study["electrical"]
    circ = {c["id"]: c for c in el["circuits"]}
    sc = Scene()
    step = 0.9
    ncols = sum(len(r["circuits"]) for r in el["rcds"])
    width = max(6, ncols * step + len(el["rcds"]) * 0.6 + 2)
    # arrivée / AGCP
    sc.poly(G.rect_footprint((0.8, 0.6), 1.2, 0.6), fill="#FFFFFF", stroke=INK, w=0.03)
    sc.text((0.8, 0.6), "AGCP 500 mA", 0.14, INK, bold=True)
    sc.text((0.8, 1.15), "(branchement)", 0.11, "#555")
    y_bus = 1.6
    sc.line([(0.8, 0.9), (0.8, y_bus)], PHASE, 0.04)
    sc.line([(0.95, 0.9), (0.95, y_bus + 0.12)], NEUTRAL, 0.04)
    sc.line([(0.8, y_bus), (width, y_bus)], PHASE, 0.05)
    sc.line([(0.95, y_bus + 0.12), (width, y_bus + 0.12)], NEUTRAL, 0.05)
    x = 1.6
    y_rcd = 2.4
    y_brk = 3.6
    for r in el["rcds"]:
        n = len(r["circuits"])
        xr = x + (n - 1) * step / 2
        sc.line([(xr, y_bus), (xr, y_rcd - 0.3)], PHASE, 0.03)
        sc.line([(xr + 0.12, y_bus + 0.12), (xr + 0.12, y_rcd - 0.3)], NEUTRAL, 0.03)
        sc.poly(G.rect_footprint((xr + 0.06, y_rcd), 0.7, 0.55), fill="#FFF7ED", stroke=BRAND, w=0.03)
        sc.text((xr + 0.06, y_rcd - 0.1), r["id"], 0.13, INK, bold=True)
        sc.text((xr + 0.06, y_rcd + 0.12), f'{r["rating_a"]}A 30mA {r["type"]}', 0.10, INK)
        sc.line([(x, y_rcd + 0.55), (x + (n - 1) * step, y_rcd + 0.55)], PHASE, 0.03)
        sc.line([(xr, y_rcd + 0.28), (xr, y_rcd + 0.55)], PHASE, 0.03)
        for i, cid in enumerate(r["circuits"]):
            c = circ[cid]
            cx = x + i * step
            sc.line([(cx, y_rcd + 0.55), (cx, y_brk - 0.25)], PHASE, 0.025)
            sc.poly(G.rect_footprint((cx, y_brk), 0.42, 0.5), fill="#FFFFFF", stroke=INK, w=0.025)
            sc.line([(cx - 0.1, y_brk + 0.1), (cx + 0.1, y_brk - 0.1)], INK, 0.02)
            sc.text((cx - 0.25, y_brk + 0.02), f'{c["breaker_a"]}A', 0.12, INK, anchor="end", bold=True)
            sc.line([(cx, y_brk + 0.25), (cx, y_brk + 0.9)], PHASE, 0.025)
            sc.line([(cx + 0.08, y_brk + 0.6), (cx + 0.08, y_brk + 0.9)], NEUTRAL, 0.025)
            sc.line([(cx + 0.16, y_brk + 0.6), (cx + 0.16, y_brk + 0.9)], PE_GREEN, 0.025)
            sc.line([(cx + 0.16, y_brk + 0.6), (cx + 0.16, y_brk + 0.9)], PE_YELLOW, 0.025, dash=[0.04, 0.04])
            sc.text((cx, y_brk + 1.1), cid, 0.13, INK, bold=True)
            sc.text((cx, y_brk + 1.32), f'{str(c["section_mm2"]).replace(".0", "").replace(".", ",")} mm²', 0.10, INK)
            sc.text((cx, y_brk + 1.52), tr(lang, f'c.{c["kind"]}')[:12], 0.09, "#444")
            short = (c.get("use") and study["electrical"].get("_labels", {}).get(c["use"])) or c["label"].split("—")[-1].strip()
            sc.text((cx, y_brk + 1.7), short[:14], 0.085, "#666")
        x += n * step + 0.6
    # barrette de terre
    yt = y_brk + 2.1
    sc.line([(1.4, yt), (x - 0.6, yt)], PE_GREEN, 0.06)
    sc.line([(1.4, yt), (x - 0.6, yt)], PE_YELLOW, 0.06, dash=[0.12, 0.12])
    sc.text((1.4, yt + 0.3), f'{tr(lang, "earth")} — barrette / prise de terre', 0.12, PE_GREEN, anchor="start", bold=True)
    # légende conducteurs
    ly = yt + 0.9
    for i, (col, key) in enumerate(((PHASE, "phase"), (NEUTRAL, "neutral"), (PE_GREEN, "earth"))):
        lx = 1.4 + i * 2.6
        sc.line([(lx, ly), (lx + 0.6, ly)], col, 0.06)
        if col == PE_GREEN:
            sc.line([(lx, ly), (lx + 0.6, ly)], PE_YELLOW, 0.06, dash=[0.1, 0.1])
        sc.text((lx + 0.75, ly), tr(lang, key), 0.13, INK, anchor="start")
    return sc


def legend_elec(lang) -> Scene:
    sc = Scene()
    items = ["prise", "prise_plan_travail", "prise_specialisee", "sortie_cable", "point_lumineux",
             "interrupteur", "va_et_vient", "rj45", "tableau", "daaf", "les"]
    for i, k in enumerate(items):
        y = i * 0.55
        _sym_elec(sc, {"x": 0.3, "y": y, "use": "lave_linge" if k == "prise_specialisee" else "plaque"}, k)
        sc.text((0.7, y), tr(lang, f"k.{k}"), 0.15, INK, anchor="start")
    y = len(items) * 0.55
    sc.line([(0.05, y), (0.55, y)], PHASE, 0.03)
    sc.text((0.7, y), "Câblage (phase : marron)" if lang == "fr" else "Cablagem (fase: castanho)", 0.15, INK, anchor="start")
    sc.line([(0.05, y + 0.5), (0.55, y + 0.5)], PHASE, 0.02, dash=[0.04, 0.06])
    sc.text((0.7, y + 0.5), "Commande → point lumineux" if lang == "fr" else "Comando → ponto de luz", 0.15, INK, anchor="start")
    sc.text((0.05, y + 1.1), "C1, C2… : n° de circuit" if lang == "fr" else "C1, C2…: n.º do circuito", 0.15, PHASE, anchor="start")
    return sc


def legend_plumb(lang) -> Scene:
    sc = Scene()
    rows = [(EF, "n.EF", 0.03), (ECS, "n.ECS", 0.03), (EU, "n.EU", 0.045), (EV, "n.EV", 0.045)]
    for i, (col, key, w) in enumerate(rows):
        y = i * 0.5
        sc.line([(0.05, y), (0.6, y)], col, w * 1.6)
        lab = f'{net(lang, key[2:])} — {tr(lang, key)}' if lang == "pt" else tr(lang, key)
        sc.text((0.8, y), lab, 0.17, INK, anchor="start")
    y = len(rows) * 0.5
    sc.poly(G.rect_footprint((0.32, y), 0.5, 0.22), fill="#FFFFFF", stroke=EF, w=0.04)
    sc.text((0.8, y), tr(lang, "manifold"), 0.17, INK, anchor="start")
    sc.circle((0.32, y + 0.5), 0.14, fill=EV, stroke=INK, w=0.02)
    sc.text((0.8, y + 0.5), tr(lang, "stack"), 0.17, INK, anchor="start")
    sc.poly(G.rect_footprint((0.32, y + 1.0), 0.3, 0.3), fill="#FFFFFF", stroke=EV, w=0.04)
    sc.text((0.8, y + 1.0), tr(lang, "exit"), 0.17, INK, anchor="start")
    return sc
