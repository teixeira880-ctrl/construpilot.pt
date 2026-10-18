"""Planches d'exécution : gros œuvre entièrement coté, planchers, coupes, façades, détails,
charpente, électricité, plomberie.

Règles de cotation (comme un dessinateur BET) :
- 3 chaînes extérieures par mur : baies, structure (épaisseurs + refends), hors tout ;
- chaînes intérieures dans chaque bande de pièces (nus des murs et cloisons) ;
- chaque baie : largeur × hauteur + allège ; chaque pièce : dimensions + surface + HSP ;
- niveaux finis, épaisseurs de murs, réservations (chutes, gaines) cotées depuis les axes ;
- coupes : chaîne verticale complète (fondation → faîtage) ; façades : allèges et hauteurs.
"""
from __future__ import annotations

import math

from .draw import Sheet, trunc
from .model import Model
from .structure import bearing_sides, end_sides, has_basement

BRICK_FILL = (0.97, 0.86, 0.82)
BA_FILL = (0.62, 0.62, 0.64)
LINING_FILL = (0.93, 0.93, 0.93)
CLOIS_FILL = (0.80, 0.80, 0.80)
SOIL_FILL = (0.93, 0.89, 0.80)
CONC_FILL = (0.86, 0.86, 0.87)
FOND_FILL = (0.85, 0.93, 0.87)
PLAN_AREA = (14, 22, 303, 282)      # zone dessin des plans (mm) — le cartouche reste à droite
OFF = (0.45, 0.80, 1.15)            # décalages des 3 chaînes extérieures (m)


def fmt(v: float) -> str:
    return f"{v:.2f}".replace(".", ",")


def _new(code, title, scale=50, origin=(-1.75, -1.85), subtitle="", area=PLAN_AREA):
    sh = Sheet(code=code, title=title, scale=scale, origin=origin, subtitle=subtitle)
    sh.area_mm = area
    return sh


# ================================================================ géométrie des murs
def _side_geom(m: Model, side: str):
    """(axe, position, a0, a1, extérieur vers +1/-1) : mur le long de X (axe 'y') ou de Y (axe 'x')."""
    d = m.side(side)
    if d["axis"] == "y":
        out = -1 if d["pos"] < m.W / 2 else 1
        return "y", (0.0 if out < 0 else m.W - m.t_str), 0.0, m.L, out
    out = -1 if d["pos"] < m.L / 2 else 1
    return "x", (0.0 if out < 0 else m.L - m.t_str), m.t_str, m.W - m.t_str, out


def _wall_rect(axis, pos, a, b, t):
    return (a, pos, b, pos + t) if axis == "y" else (pos, a, pos + t, b)


def _ext_walls(sh: Sheet, m: Model, lid: str, light=False, lining=True):
    ts, tt = m.t_str, m.t_tot
    buried = m.level(lid).floor_top < -1.0
    lay = "BA" if buried else "BRIQUE"
    fill, hatch = (BA_FILL, None) if buried else (BRICK_FILL, "brique")
    if light:
        fill, hatch = (0.9, 0.9, 0.9), None
    for side in m.raw["sides"]:
        axis, pos, a0, a1, out = _side_geom(m, side)
        ops = sorted(m.openings_on(side, lid), key=lambda o: o.a)
        cuts = [(a0, a0)] + [(o.a, o.b) for o in ops] + [(a1, a1)]
        for (_, e0), (s1, _) in zip(cuts, cuts[1:]):
            if s1 - e0 > 0.005:
                sh.rect(lay, *_wall_rect(axis, pos, e0, s1, ts), lw=0.4, fill=fill, hatch=hatch)
                if lining:
                    lpos = pos + ts if out < 0 else pos - (tt - ts)
                    la, lb = max(e0, tt), min(s1, (m.L if axis == "y" else m.W) - tt)
                    if lb > la:
                        sh.rect("DOUBLAGE", *_wall_rect(axis, lpos, la, lb, tt - ts), lw=0.1, fill=LINING_FILL)
        for o in ops:
            for v in (o.a, o.b):
                p1 = (v, pos) if axis == "y" else (pos, v)
                p2 = (v, pos + ts) if axis == "y" else (pos + ts, v)
                sh.line("BAIE", p1, p2, lw=0.3)
            for dz in (ts / 2 - 0.025, ts / 2 + 0.025):
                if axis == "y":
                    sh.line("BAIE", (o.a, pos + dz), (o.b, pos + dz), lw=0.35)
                else:
                    sh.line("BAIE", (pos + dz, o.a), (pos + dz, o.b), lw=0.35)


def _stair(sh: Sheet, m: Model, lid: str):
    s = m.stair
    for w in s["cage_walls"]:
        sh.rect("BA", w["x"] - w["t"] / 2, w["y0"], w["x"] + w["t"] / 2, w["y1"], lw=0.4, fill=BA_FILL)
    x0, x1, y0, y1 = s["x0"], s["x1"], s["y0"], s["y1"]
    xm = (x0 + x1) / 2
    sh.rect("ESCALIER", xm - 0.05, y0 + 0.2, xm + 0.05, y1 - 0.9, lw=0.2, fill=CLOIS_FILL)
    for k in range(9):
        yy = y0 + 0.2 + k * 0.24
        if yy < y1 - 0.9:
            sh.line("ESCALIER", (x0, yy), (xm - 0.05, yy), lw=0.15)
            sh.line("ESCALIER", (xm + 0.05, yy), (x1, yy), lw=0.15)
    cy = y1 - 0.9
    for a in range(0, 181, 30):
        r = math.radians(a)
        sh.line("ESCALIER", (xm, cy), (xm - math.cos(r) * 0.9, cy + math.sin(r) * 0.85), lw=0.15)
    if lid != m.levels[0].id:
        sh.line("ESCALIER", (x0, y0), (x1, y1), lw=0.15, dash="dashed")
    sh.text("ESCALIER", (xm, y0 + 0.08), "Escalier ¼ + ¼ tournant", size=1.5, anchor="c")


def _interior(sh: Sheet, m: Model, lid: str):
    for w in m.raw["interior_walls"].get(lid, []):
        sh.rect("CLOISON", w["x0"], w["y0"], w["x1"], w["y1"], lw=0.15, fill=CLOIS_FILL)


def _rooms(sh: Sheet, m: Model, lid: str, dims=True, size=1.9):
    hsp = m.level(lid).hsp
    for r in m.rooms(lid):
        cx, cy = (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2
        w, h = r["x1"] - r["x0"], r["y1"] - r["y0"]
        if w < 1.2 or h < 1.2:
            sh.text("TEXTE", (cx, cy - 0.05), trunc(r["name"], 10), size=1.3, anchor="c", color=(0.15, 0.25, 0.55))
            continue
        sh.text("TEXTE", (cx, cy + 0.18), r["name"], size=size, anchor="c", bold=True, color=(0.15, 0.25, 0.55))
        if r.get("area_pc"):
            sh.text("TEXTE", (cx, cy - 0.12), f"{fmt(r['area_pc'])} m²", size=size * 0.85, anchor="c", color=(0.15, 0.25, 0.55))
        if dims:
            sh.text("TEXTE", (cx, cy - 0.40), f"{fmt(w)} × {fmt(h)} · HSP {fmt(hsp)}", size=1.35, anchor="c", color=(0.35, 0.35, 0.35))


def _axes(sh: Sheet, m: Model, ring=1.50):
    L, W = m.L, m.W
    for name, y in (("A", m.t_str / 2), ("B", W - m.t_str / 2)):
        sh.line("AXE", (-ring + 0.25, y), (L + ring - 0.25, y), lw=0.13, dash="axis")
        sh.circle("AXE", (-ring, y), 0.20, lw=0.25)
        sh.text("AXE", (-ring, y - 0.07), name, size=2.2, anchor="c", bold=True)
    xs = [("1", m.t_str / 2)] + [(f"S{i+1}", w["x"]) for i, w in enumerate(m.stair["cage_walls"])] + [("2", L - m.t_str / 2)]
    for name, x in xs:
        sh.line("AXE", (x, -ring + 0.25), (x, W + ring - 0.25), lw=0.13, dash="axis")
        sh.circle("AXE", (x, W + ring), 0.20, lw=0.25)
        sh.text("AXE", (x, W + ring - 0.07), name, size=2.0, anchor="c", bold=True)


def _chain_side(sh: Sheet, m: Model, side: str, lid: str):
    """3 chaînes extérieures : baies / structure / hors tout."""
    axis, pos, a0, a1, out = _side_geom(m, side)
    full = m.L if axis == "y" else m.W
    base = 0.0 if out < 0 else (m.W if axis == "y" else m.L)
    ops = sorted(m.openings_on(side, lid), key=lambda o: o.a)
    pts1 = [0.0] + [v for o in ops for v in (o.a, o.b)] + [full]
    pts2 = [0.0, m.t_str, m.t_tot]
    if axis == "y":
        pts2 += [v for w in m.stair["cage_walls"] for v in (w["x"] - w["t"] / 2, w["x"] + w["t"] / 2)]
    pts2 += [full - m.t_tot, full - m.t_str, full]
    pts2 = sorted(set(round(v, 3) for v in pts2))
    for k, pts in enumerate((pts1, pts2, [0.0, full])):
        if k == 0 and not ops:
            continue
        at = base + out * OFF[k]
        sh.chain(pts, "x" if axis == "y" else "y", at, size=1.6 if k < 2 else 2.0)
    for o in ops:
        mid = (o.a + o.b) / 2
        txt = f"{fmt(o.width)} × {fmt(o.height)}  all. {fmt(o.sill)}"
        if axis == "y":
            sh.text("BAIE", (mid, base + out * 0.22 - 0.05), txt, size=1.3, anchor="c")
        else:
            sh.text("BAIE", (base + out * 0.22 + 0.05, mid), txt, size=1.3, anchor="c", rot=90)


def _interior_chains(sh: Sheet, m: Model, lid: str):
    """Chaînes intérieures : nus de tous les murs coupés par des lignes horizontales et verticales."""
    walls = [(w["x0"], w["y0"], w["x1"], w["y1"]) for w in m.raw["interior_walls"].get(lid, [])]
    walls += [(c["x"] - c["t"] / 2, c["y0"], c["x"] + c["t"] / 2, c["y1"]) for c in m.stair["cage_walls"]]
    tt = m.t_tot
    for yc in (tt + 0.55, m.W - tt - 0.55):
        pts = [tt, m.L - tt]
        for (x0, y0, x1, y1) in walls:
            if y0 - 0.01 <= yc <= y1 + 0.01 and (y1 - y0) > (x1 - x0):
                pts += [x0, x1]
        sh.chain(sorted(set(round(p, 3) for p in pts)), "x", yc, size=1.35)
    xs = [tt + 0.55, m.L / 2 - 0.9, m.L - tt - 0.55]
    for xc in xs:
        pts = [tt, m.W - tt]
        for (x0, y0, x1, y1) in walls:
            if x0 - 0.01 <= xc <= x1 + 0.01 and (x1 - x0) > (y1 - y0):
                pts += [y0, y1]
        sh.chain(sorted(set(round(p, 3) for p in pts)), "y", xc, size=1.35)


def _wall_tags(sh: Sheet, m: Model, lid: str):
    buried = m.level(lid).floor_top < -1.0
    for side in m.raw["sides"]:
        axis, pos, a0, a1, out = _side_geom(m, side)
        txt = ("voile BA 20" if buried else "Porotherme 20") + f" + doublage {int(round((m.t_tot - m.t_str) * 100))}"
        if axis == "y":
            sh.text("TEXTE", (m.L * 0.30, pos + m.t_tot + 0.10 if out < 0 else pos - (m.t_tot - m.t_str) - 0.17), txt, size=1.3, color=(0.45, 0.2, 0.15))


def base_plan(sh: Sheet, m: Model, lid: str, rooms=True, dims=True, axes=True, light=False):
    _ext_walls(sh, m, lid, light=light)
    _interior(sh, m, lid)
    _stair(sh, m, lid)
    if rooms:
        _rooms(sh, m, lid, dims=dims)
    if axes:
        _axes(sh, m)
    if dims:
        for side in m.raw["sides"]:
            _chain_side(sh, m, side, lid)
        _interior_chains(sh, m, lid)
        _wall_tags(sh, m, lid)
    lv = m.level(lid)
    sh.level_mark((m.t_tot + 0.6, m.t_tot + 1.3), lv.floor_top, "fini")
    sh.text("TITRE", (0, m.W + 1.85), f"{lv.name.upper()} — niveau fini " + f"{lv.floor_top:+.2f}".replace(".", ","), size=3.8, bold=True)


def _reservations(sh: Sheet, m: Model, lid: str, stacks: list[dict]):
    for st in stacks:
        sh.circle("PLOMB_EV", (st["x"], st["y"]), 0.0625, lw=0.4, fill=(1, 1, 1))
        sh.line("PLOMB_EV", (st["x"] - 0.09, st["y"] - 0.09), (st["x"] + 0.09, st["y"] + 0.09), lw=0.25)
        sh.text("PLOMB_EV", (st["x"] + 0.12, st["y"] - 0.20), f"Résa Ø125 {st['id']} (x {fmt(st['x'])} ; y {fmt(st['y'])})", size=1.25)


# ================================================================ gros œuvre — niveaux
def go_level(m: Model, r: dict, lid: str, code: str, stacks: list[dict]) -> Sheet:
    lv = m.level(lid)
    buried = lv.floor_top < -1.0
    sh = _new(code, f"Plan d'exécution gros œuvre — {lv.name}",
              subtitle="Voiles BA 20 enterrés + voiles BA 15 de cage" if buried else "Murs Porotherme 20 joint mince, chaînages, linteaux, poteaux")
    base_plan(sh, m, lid)
    L, W = m.L, m.W
    if not buried:
        for l in r["lintels"]["lintels"]:
            if l["level"] != lid:
                continue
            axis, pos, a0, a1, out = _side_geom(m, l["side"])
            mid = (l["y0"] + l["y1"]) / 2
            lab = f"{l['id']} {int(l['b']*100)}×{int(l['h']*100)} {l['bottom']}"
            if axis == "y":
                sh.text("ACIER", (mid, pos + (m.t_tot + 0.38 if out < 0 else -(m.t_tot - m.t_str) - 0.45)), lab, size=1.3, anchor="c", bold=True)
            else:
                sh.text("ACIER", (pos + (m.t_tot + 0.40 if out < 0 else -(m.t_tot - m.t_str) - 0.30), mid), lab, size=1.3, anchor="c", rot=90, bold=True)
        for p in r["lintels"]["posts"]:
            if p["level"] != lid:
                continue
            axis, pos, a0, a1, out = _side_geom(m, p["side"])
            rect = _wall_rect(axis, pos, p["y0"], p["y1"], m.t_str)
            sh.rect("ACIER", *rect, lw=0.4, fill=(0.85, 0.2, 0.2))
        cv = [(0, 0), (L - 0.2, 0), (0, W - 0.2), (L - 0.2, W - 0.2)]
        for side in m.raw["sides"]:
            axis, pos, a0, a1, out = _side_geom(m, side)
            for o in m.openings_on(side, lid):
                if o.width >= 1.75:
                    for v in (o.a - 0.20, o.b):
                        cv.append((v, pos) if axis == "y" else (pos, v))
        for w in m.stair["cage_walls"]:
            cv.append((w["x"] - 0.10, W - 0.20))
        for (x, y) in cv:
            sh.rect("ACIER", x, y, x + 0.20, y + 0.20, lw=0.3, fill=(0.75, 0.1, 0.1))
    _reservations(sh, m, lid, stacks)
    notes = []
    if buried:
        notes = ["Voiles périphériques BA 20 C25/30 hydrofugé : face terre " + r["basement"]["walls"][0]["face_terre"] + ", face intérieure HA8 e=20, horizontaux HA8 e=20 (2 faces).",
                 "Contre les mitoyens : coulage par plots alternés sous blindage et butonnage (G2), voile coulé contre terrain.",
                 "Voiles de cage d'escalier BA 15 continus jusqu'au dernier niveau (portent les chevêtres des trémies).",
                 "Cloisons du sous-sol en blocs 20 non porteurs sur épaississement du dallage.",
                 f"Dallage BA 20 cm sur polyane + GNT 20 cm, dessus fini {lv.floor_top:+.2f}.".replace(".", ",")]
    else:
        ratio = max([c["ratio"] for c in r["masonry"]["checks"] if c["level"] == lid] or [0])
        notes = [f"Murs porteurs Porotherme 20 joint mince, f_k = {r['masonry']['brick']['fk']} MPa (DoP à confirmer) : taux maxi {ratio*100:.0f} %.",
                 "Rouge plein : chaînages verticaux 20×20 4HA10 + cadres HA6 e=20 (angles, cage, tableaux des baies ≥ 1,80 m). Rouge clair : poteaux BA de trumeau.",
                 "Repères L-… : linteaux BA b × h et aciers inférieurs (sup. 2HA10, cadres HA6 e=15 sauf indication). Appuis ≥ 0,20 m.",
                 "Chaînage horizontal 20×30 4HA10 + cadres HA6 e=20 en tête des murs sous chaque plancher.",
                 "Cotes des baies : largeur × hauteur de tableau + allège depuis le sol fini ; tolérance ± 1 cm."]
    notes += ["Cotes en mètres (≥ 1 m) et centimètres (< 1 m), aux nus bruts de maçonnerie ; doublages 15 non porteurs.",
              "Réservations Ø125 des chutes à positionner depuis les axes 1 et A avant coulage des planchers.",
              "TOUTES LES COTES SONT À VÉRIFIER SUR SITE AVANT EXÉCUTION."]
    if r.get("seismic") and lid == next(l.id for l in m.levels if l.floor_top > -1.0):
        sz = r["seismic"]
        notes.append(f"Séisme (NP EN 1998-1) : effort tranchant à la base F_b = {fmt(sz['Fb_kN'])} kN ; murs de contreventement : taux maxi {sz['worst_ratio']*100:.0f} % ; "
                     "chaînages horizontaux et verticaux obligatoires (voir note de calcul).")
    if any(rm["type"] == "garage" for rm in m.rooms(lid)):
        notes.append("Murs du garage : 20 cm, coupe-feu ½ h (EI 30) avec porte EI 30 vers le logement.")
    sh.notes = notes
    return sh


# ================================================================ fondations
def go_foundations(m: Model, r: dict) -> Sheet:
    sh = _new("GO-01", "Plan d'exécution des fondations — semelles filantes BA",
              subtitle=f"Arase inférieure ≈ {-(r['foundations']['base_depth'] + 0.10):+.2f} ; ancrage ≥ {fmt(r['foundations']['anchorage'])} dans le bon sol (G2)")
    L, W = m.L, m.W
    items = {i["side"]: i for i in r["foundations"]["items"]}
    zb = -(r["foundations"]["base_depth"] + 0.10)
    rects = []
    for side in m.raw["sides"]:
        it = items[side]
        axis, pos, a0, a1, out = _side_geom(m, side)
        B = it["B"]
        if it["excentric"]:
            c0 = 0.0 if out < 0 else (W if axis == "y" else L) - B
        else:
            c0 = pos + m.t_str / 2 - B / 2
        if axis == "y":
            rect = (0.0 if out > 0 or True else 0.0, c0, L, c0 + B)
        else:
            yb0 = items[bearing_sides(m)[0]]["B"] if bearing_sides(m) else 0
            rect = (c0, yb0, c0 + B, W - yb0)
        rects.append((side, rect, it))
        sh.rect("FOND", *rect, lw=0.4, fill=FOND_FILL)
    cage = items["cage"]
    yb_top = W - items[bearing_sides(m)[-1]]["B"] if bearing_sides(m) else W
    for w in m.stair["cage_walls"]:
        sh.rect("FOND", w["x"] - cage["B"] / 2, w["y0"] - 0.30, w["x"] + cage["B"] / 2, yb_top, lw=0.4, fill=FOND_FILL)
    # voiles / murs au-dessus
    for side in m.raw["sides"]:
        axis, pos, a0, a1, out = _side_geom(m, side)
        sh.rect("BA", *_wall_rect(axis, pos, a0, a1, m.t_str), lw=0.3, fill=BA_FILL)
    for w in m.stair["cage_walls"]:
        sh.rect("BA", w["x"] - w["t"] / 2, w["y0"], w["x"] + w["t"] / 2, W - m.t_str, lw=0.3, fill=BA_FILL)
    _axes(sh, m)
    # repères et cotes de chaque semelle
    for k, (side, rect, it) in enumerate(rects, 1):
        axis, pos, a0, a1, out = _side_geom(m, side)
        tag = f"SF{k} — B {fmt(it['B'])} × h {fmt(it['h'])} — {it['transversal']} + {it['longitudinal']}" + (" — EXCENTRÉE" if it["excentric"] else "")
        x0, y0, x1, y1 = rect
        if axis == "y":
            sh.text("FOND", ((x0 + x1) / 2, (y0 + y1) / 2 - 0.06), tag, size=1.6, anchor="c", bold=True)
            sh.chain([y0, pos, pos + m.t_str, y1] if not it["excentric"] else ([y0, y0 + m.t_str, y1] if out < 0 else [y0, y1 - m.t_str, y1]),
                     "y", L + 0.45 + 0.0 * k, size=1.4)
        else:
            sh.text("FOND", ((x0 + x1) / 2 + 0.06, (y0 + y1) / 2), tag, size=1.5, anchor="c", rot=90, bold=True)
            sh.chain([x0, x1] if it["excentric"] else [x0, pos, pos + m.t_str, x1], "x", -0.45, size=1.4)
    for w in m.stair["cage_walls"]:
        sh.text("FOND", (w["x"] + 0.06, (w["y0"] + yb_top) / 2), f"SF cage B {fmt(cage['B'])} × h {fmt(cage['h'])}", size=1.3, anchor="c", rot=90, bold=True)
    sh.chain([0.0] + sorted(v for w in m.stair["cage_walls"] for v in (w["x"] - cage["B"] / 2, w["x"] + cage["B"] / 2)) + [L], "x", W + 0.45, size=1.4)
    axes_x = [0.0, m.t_str / 2] + [w["x"] for w in m.stair["cage_walls"]] + [L - m.t_str / 2, L]
    sh.chain(axes_x, "x", -0.85, size=1.5)
    sh.text("COTE", (-0.15, -0.80), "axes", size=1.3, anchor="r")
    sh.dim((0, -1.20), (L, -1.20), 0, size=2.0)
    sh.chain([0.0, m.t_str / 2, W - m.t_str / 2, W], "y", L + 0.85, size=1.5)
    sh.dim((L + 1.20, 0), (L + 1.20, W), 0, size=2.0)
    cw = m.stair["cage_walls"][0]
    sh.chain([0.0, cw["y0"] - 0.30, yb_top, W], "y", cw["x"] - cage["B"] / 2 - 0.35, size=1.4)
    for z, lab, p in ((zb, "arase inf. semelles", (m.t_tot + 0.8, W / 2 + 0.6)), (zb + 0.35, "arase sup. semelles", (m.t_tot + 0.8, W / 2 - 0.2)),
                      (m.levels[0].floor_top, "fini dallage", (m.t_tot + 0.8, W / 2 - 1.0))):
        sh.level_mark(p, z, lab)
    sh.line("COTE", (3.0, -0.3), (3.0, W + 0.3), lw=0.4, dash="dashed")
    sh.text("COTE", (3.05, W + 0.32), "D1", size=2.4, bold=True)
    sh.line("COTE", (-0.3, 3.0), (0.9, 3.0), lw=0.4, dash="dashed")
    sh.text("COTE", (-0.3, 3.08), "D2", size=2.4, bold=True)
    sh.text("TITRE", (0, W + 1.85), "PLAN DES FONDATIONS", size=3.8, bold=True)
    worst = max(r["foundations"]["items"], key=lambda i: i["ratio_ELS"])
    sh.notes = [
        f"Contrainte admissible G2 : q ELS = {r['foundations']['q_els']} kPa, q ELU = {r['foundations']['q_elu']} kPa.",
        f"Semelle la plus chargée ({worst['label']}) : σ ELS = {worst['sigma_ELS']} kPa = {worst['ratio_ELS']*100:.0f} % de q ELS.",
    ] + ([
        "Semelles excentrées en limite (mitoyens, alignement) : le moment est repris par le couple dallage armé (pied) / plancher (tête).",
    ] if any(i["excentric"] for i in r["foundations"]["items"]) else []) + [
        "Cotes des semelles depuis les nus extérieurs des voiles ; axes 1, 2, A, B, S1, S2 implantés par le géomètre.",
        "Béton de propreté 5 cm ; enrobage 5 cm ; attentes HA10 e=25 des voiles (recouvrement 50 Ø) ; redans 1V/3H entre arases différentes.",
        "Purge des poches molles au gros béton ; RÉCEPTION DES FONDS DE FOUILLE PAR LE GÉOTECHNICIEN (point d'arrêt).",
        "Boucle de terre en câblette Cu nu 25 mm² en fond de fouille, remontée au local technique.",
        "Détails D1 / D2 : planche {DETAILS}.",
    ]
    return sh


# ================================================================ planchers
def go_floor(m: Model, r: dict, slab: dict, code: str, stacks: list[dict]) -> Sheet:
    sh = _new(code, f"Plan de pose et de coffrage — {slab['label']}", subtitle=slab["label_system"])
    L, W, ts = m.L, m.W, m.t_str
    for side in m.raw["sides"]:
        axis, pos, a0, a1, out = _side_geom(m, side)
        sh.rect("BRIQUE", *_wall_rect(axis, pos, a0, a1, ts), lw=0.4, fill=BRICK_FILL, hatch="brique")
    s = m.stair
    for w in s["cage_walls"]:
        sh.rect("BA", w["x"] - w["t"] / 2, w["y0"], w["x"] + w["t"] / 2, w["y1"], lw=0.3, fill=BA_FILL)
    sh.rect("ACIER", 0.03, 0.03, L - 0.03, W - 0.03, lw=0.4, dash="dashed")
    xs, n_full, n_cut = [], 0, 0
    x = ts + 0.30
    while x < L - ts - 0.05:
        in_trem = s["x0"] - 0.02 < x < s["x1"] + 0.02
        xs.append((x, in_trem))
        y_top = s["y0"] - 0.20 if in_trem else W - ts + 0.08
        for dx in ((-0.03, 0.03) if slab["twin"] else (0.0,)):
            sh.line("PLANCHER", (x + dx, ts - 0.08), (x + dx, y_top), lw=0.35)
        if in_trem:
            n_cut += 1
        else:
            n_full += 1
        x += 0.60
    sh.rect("BA", s["x0"] - 0.075, s["y0"] - 0.20, s["x1"] + 0.075, s["y0"], lw=0.4, fill=(0.75, 0.75, 0.78))
    sh.rect("COTE", s["x0"], s["y0"], s["x1"], s["y1"], lw=0.3)
    sh.line("COTE", (s["x0"], s["y0"]), (s["x1"], s["y1"]), lw=0.2)
    sh.line("COTE", (s["x0"], s["y1"]), (s["x1"], s["y0"]), lw=0.2)
    sh.text("TEXTE", ((s["x0"] + s["x1"]) / 2, s["y0"] + 0.95), "TRÉMIE", size=1.9, anchor="c", bold=True)
    sh.text("TEXTE", ((s["x0"] + s["x1"]) / 2, s["y0"] + 0.65), f"{fmt(s['x1']-s['x0'])} × {fmt(s['y1']-s['y0'])}", size=1.7, anchor="c")
    sh.rect("COTE", s["x0"] - 1.9, s["y0"] - 0.62, s["x1"] + 1.9, s["y0"] - 0.28, lw=0.1, fill=(1, 1, 1))
    sh.text("ACIER", ((s["x0"] + s["x1"]) / 2, s["y0"] - 0.50), "Chevêtre BA 20×30 : 3HA12 inf. + 2HA10 sup., cadres HA6 e=15, sur voiles de cage", size=1.4, anchor="c")
    # cotes : entraxes, trémie, rives
    sh.chain([0.0, ts] + [round(v, 3) for v, _ in xs] + [L - ts, L], "x", -0.45, size=1.15)
    sh.chain([0.0, s["x0"], s["x1"], L], "x", -0.80, size=1.5)
    sh.dim((0, -1.15), (L, -1.15), 0, size=2.0)
    sh.chain([0.0, ts, s["y0"] - 0.20, s["y0"], s["y1"], W - ts, W], "y", L + 0.45, size=1.5)
    sh.dim((L + 0.85, ts), (L + 0.85, W - ts), 0, text=f"portée libre {fmt(m.clear_span_y)}")
    sh.dim((L + 1.15, 0), (L + 1.15, W), 0, size=2.0)
    _axes(sh, m)
    _reservations(sh, m, "", stacks)
    sh.rect("PLANCHER", 0.9, 2.55, 4.7, 4.75, lw=0.3, fill=(1, 1, 1))
    for i, t in enumerate([slab["system"] + (" — poutrelles jumelées" if slab["twin"] else ""),
                           f"entraxe 0,60 — portée de calcul {fmt(slab['span'])}",
                           f"{n_full} nervures pleine portée L = {fmt(m.clear_span_y + 0.10)}",
                           f"{n_cut} nervures coupées (trémie) L = {fmt(s['y0'] - 0.20 - ts + 0.05)}",
                           f"M_Ed = {slab['M_per_m']} kN.m/m · V_Ed = {slab['V_per_m']} kN/m",
                           f"G = {slab['G']} · Q = {slab['Q']} kN/m² · L/h = {slab['slenderness']}",
                           "Table 5 cm C25/30 + treillis ST 15 C"]):
        sh.text("PLANCHER", (2.8, 4.45 - 0.30 * i), t, size=2.2 if i == 0 else 1.6, anchor="c", bold=i == 0)
    sh.level_mark((L / 2 + 1.2, 1.0), slab["level_top"], "dessus table")
    sh.level_mark((L / 2 + 1.2, 0.6), slab["level_top"] - slab["h"], "sous-face")
    sh.text("TITRE", (0, W + 1.85), slab["label"].upper(), size=3.6, bold=True)
    sh.notes = [
        f"Poutrelles précontraintes de mur porteur à mur porteur (sens Y), appui ≥ 5 cm + chaînage ; {n_full + n_cut} nervures {'jumelées ' if slab['twin'] else ''}à 0,60.",
        f"Charges : poids propre {slab['g_self']} + finitions 1,25 + cloisons 1,00 = G {slab['G']} kN/m² ; Q = {slab['Q']} kN/m².",
        f"Moment par nervure : {slab['M_rib']} kN.m — NOTE ET PLAN DE POSE DU FABRICANT (Avis Technique) OBLIGATOIRES avant commande.",
        "Flèche active ≤ L/500 ; étaiement à mi-portée (et aux tiers si L > 6 m) maintenu 21 jours.",
        "Chapeaux sur appuis : HA10 e=33 (1 par nervure), L = 1,80 m ; rive : HA8 dans le chaînage.",
        "Renforts de trémie : 2HA10 sur chaque bord dans la table, barres de coin à 45°.",
        f"Épaisseur {int(slab['h']*100)} cm (PC : {int(m.level(m.levels[1].id).slab*100)} cm) : écart de {int(round(r['floors']['impact_heights']*100))} cm à valider avec l'architecte.",
        "Réservations Ø125 des chutes positionnées depuis les axes (voir cotes) ; fourreaux électriques dans la table.",
    ]
    return sh


# ================================================================ coupes
XB = None


def go_sections(m: Model, r: dict, tim: dict) -> Sheet:
    sh = _new("GO-09", "Coupes A-A et B-B cotées", scale=100, origin=(-2.2, -8.0), subtitle="Chaînes verticales : fondations → faîtage")
    L, W = m.L, m.W
    a = math.radians(r["loads"]["roof_pitch_deg"])
    eav, rid = m.roof["eaves_level"], m.roof["ridge_level"]
    zb = -(r["foundations"]["base_depth"] + 0.10)
    slabs = r["floors"]["slabs"]
    st = m.stair
    xb = (st["x0"] + st["x1"]) / 2

    def ground(x0, span):
        sh.rect("TERRAIN", x0 - 1.0, zb - 0.4, x0 + span + 1.0, -0.10, lw=0.0, fill=SOIL_FILL)
        if has_basement(m):
            sh.rect("TERRAIN", x0 + 0.2, m.levels[0].floor_top - 0.40, x0 + span - 0.2, -0.10, lw=0.0, fill=(1, 1, 1))
        sh.line("TERRAIN", (x0 - 1.0, -0.10), (x0 + span + 1.0, -0.10), lw=0.5)

    def body(x0, span, top_left, top_right, foot_B):
        ground(x0, span)
        for xs, B in ((x0, foot_B[0]), (x0 + span - foot_B[1], foot_B[1])):
            sh.rect("FOND", xs, zb, xs + B, zb + 0.35, lw=0.35, fill=FOND_FILL)
        z_low = m.levels[0].floor_top
        if has_basement(m):
            sh.rect("BA", x0 + 0.2, z_low - 0.20, x0 + span - 0.2, z_low, lw=0.3, fill=CONC_FILL)
            sh.rect("TERRAIN", x0 + 0.2, z_low - 0.40, x0 + span - 0.2, z_low - 0.20, lw=0.1, fill=(0.85, 0.80, 0.70))
            for xw in (x0, x0 + span - 0.20):
                sh.rect("BA", xw, zb + 0.35, xw + 0.20, 0.0, lw=0.35, fill=BA_FILL)
        for xw, top in ((x0, top_left), (x0 + span - 0.20, top_right)):
            sh.rect("BRIQUE", xw, 0.0, xw + 0.20, top, lw=0.35, fill=BRICK_FILL, hatch="brique")
        for s in slabs:
            z = s["level_top"]
            sh.rect("PLANCHER", x0 + 0.20, z - s["h"], x0 + span - 0.20, z, lw=0.3, fill=(0.80, 0.88, 0.97))
            for xw in (x0, x0 + span - 0.20):
                sh.rect("ACIER", xw, z - s["h"], xw + 0.20, z, lw=0.3, fill=(0.80, 0.80, 0.82))
        for lv in m.levels:
            sh.level_mark((x0 + span + 0.7, lv.floor_top), lv.floor_top, lv.name)
        sh.level_mark((x0 + span + 0.7, zb), zb, "arase inf. semelles")

    def vchain(x, extra=()):
        pts = [zb, zb + 0.35]
        if has_basement(m):
            pts += [m.levels[0].floor_top - 0.20, m.levels[0].floor_top]
        for s in slabs:
            pts += [s["level_top"] - s["h"], s["level_top"]]
        pts += [eav] + list(extra)
        sh.chain(sorted(set(round(p, 3) for p in pts)), "y", x, size=1.4)

    # ---- A-A : coupe selon X à y = 2,95
    yA = 2.95
    gab = m.roof.get("gables", [])
    ops_l = [o for s in end_sides(m) if _side_geom(m, s)[1] == 0.0 for o in m.openings_on(s) if o.a <= yA <= o.b]
    ops_r = [o for s in end_sides(m) if _side_geom(m, s)[1] > 0.0 for o in m.openings_on(s) if o.a <= yA <= o.b]
    body(0.0, L, eav, eav, (0.6, 0.6))
    for xw, ops in ((0.0, ops_l), (L - 0.20, ops_r)):
        for o in ops:
            z0 = m.level(o.level).floor_top + o.sill
            sh.rect("BAIE", xw - 0.01, z0, xw + 0.21, z0 + o.height, lw=0.3, fill=(0.85, 0.92, 1.0))
    sh.poly("CHARPENTE", [(-0.35, eav - 0.35 * math.tan(a)), (m.roof["ridge_x"], rid), (L + 0.35, eav - 0.35 * math.tan(a))], lw=0.8)
    for p in tim["pannes"]:
        b, h = tim["panne_section"]["b"] / 1000, tim["panne_section"]["h"] / 1000
        sh.rect("CHARPENTE", p["x"] - b / 2, p["z"] - h / 2, p["x"] + b / 2, p["z"] + h / 2, lw=0.3, fill=(0.85, 0.70, 0.50))
    sh.line("CHARPENTE", (0.2, m.roof["ceiling_level"]), (L - 0.2, m.roof["ceiling_level"]), lw=0.25, dash="dashed")
    sh.level_mark((L + 0.7, eav), eav, "égout")
    sh.level_mark((L + 0.7, rid), rid, "faîtage")
    vchain(-0.55, (rid,))
    ops_z = sorted({round(v, 3) for o in ops_r for v in (m.level(o.level).floor_top + o.sill, m.level(o.level).floor_top + o.sill + o.height)} | {0.0})
    if len(ops_z) > 1:
        sh.chain(ops_z, "y", L + 0.35, size=1.3)
    sh.dim((0, zb - 0.6), (L, zb - 0.6), 0, size=1.8)
    sh.text("TITRE", (0, rid + 0.9), f"COUPE A-A (y = {fmt(yA)})", size=3.4, bold=True)
    # ---- B-B : coupe selon Y à travers la cage
    xo = L + 4.2
    z_top = rid - abs(xb - m.roof["ridge_x"]) * math.tan(a)
    body(xo, W, z_top, z_top, (0.6, 0.6))
    for z in [s["level_top"] for s in slabs]:
        sh.rect("COTE", xo + st["y0"], z - 0.30, xo + st["y1"] - 0.20, z + 0.001, lw=0.2, fill=(1, 1, 1))
        sh.text("COTE", (xo + (st["y0"] + st["y1"]) / 2, z - 0.20), "trémie", size=1.2, anchor="c")
    sh.rect("CHARPENTE", xo + 0.20, z_top - 0.05, xo + W - 0.20, z_top + 0.05, lw=0.5, fill=(0.85, 0.65, 0.45))
    sh.text("PLANCHER", (xo + W / 2, 1.2), "poutrelles de mur porteur à mur porteur", size=1.4, anchor="c")
    vchain(xo - 0.55, (z_top,))
    sh.chain([0.0, 0.20, st["y0"], st["y1"], W - 0.20, W], "x", zb - 0.6, size=1.4) if False else \
        sh.chain([xo, xo + 0.20, xo + st["y0"], xo + st["y1"], xo + W - 0.20, xo + W], "x", zb - 0.6, size=1.4)
    sh.text("TITRE", (xo, rid + 0.9), f"COUPE B-B (x = {fmt(xb)}, cage d'escalier)", size=3.4, bold=True)
    sh.notes = [
        "Niveaux en mètres, 0,00 = sol fini RDC. Chaînes verticales : arases de semelles, dallage, sous-faces et dessus des planchers, égout, faîtage.",
        f"Planchers {slabs[0]['system']} (h = {int(slabs[0]['h']*100)} cm) portant de mur porteur à mur porteur.",
        f"Charpente : pente {r['loads']['roof_pitch_deg']}°, pannes GL24h {tim['panne_section']['label']} de pignon à pignon.",
        "Coupe A-A : baies de la façade de droite cotées (allège / hauteur).",
    ]
    return sh


# ================================================================ façades
def _facade_coord(m: Model, side: str, a: float) -> float:
    axis, pos, *_ , out = _side_geom(m, side)
    full = m.L if axis == "y" else m.W
    if axis == "x":
        return a if out > 0 else full - a
    return a if out < 0 else full - a


def go_facades(m: Model, r: dict) -> list[Sheet]:
    eav, rid = m.roof["eaves_level"], m.roof["ridge_level"]
    lin = {l["opening"]: l for l in r["lintels"]["lintels"]}
    sides = [s for s in m.raw["sides"] if m.openings_on(s)]
    sheets = []
    for k in range(0, len(sides), 2):
        sh = _new(f"GO-10{chr(97 + k // 2) if len(sides) > 2 else ''}", "Élévations cotées des façades — baies, allèges, linteaux", scale=75, origin=(-1.6, -3.6))
        xo = 0.0
        for side in sides[k:k + 2]:
            axis, pos, a0, a1, out = _side_geom(m, side)
            full = m.L if axis == "y" else m.W
            gable = side in m.roof.get("gables", [])
            sh.rect("BRIQUE", xo, 0, xo + full, eav, lw=0.4, fill=(0.99, 0.96, 0.94))
            if gable:
                sh.poly("BRIQUE", [(xo, eav), (xo + full / 2, rid), (xo + full, eav)], lw=0.4, closed=True, fill=(0.99, 0.96, 0.94))
            else:
                sh.poly("CHARPENTE", [(xo - 0.3, eav), (xo + full + 0.3, eav), (xo + full + 0.3, rid), (xo - 0.3, rid)], lw=0.5, closed=True, fill=(0.95, 0.80, 0.78))
            if has_basement(m):
                sh.rect("BA", xo, m.levels[0].floor_top - 0.20, xo + full, 0, lw=0.3, fill=CONC_FILL, dash="dashed")
            hpts = [0.0, full]
            for o in m.openings_on(side):
                z = m.level(o.level).floor_top + o.sill
                u0 = xo + min(_facade_coord(m, side, o.a), _facade_coord(m, side, o.b))
                sh.rect("BAIE", u0, z, u0 + o.width, z + o.height, lw=0.35, fill=(0.85, 0.92, 1.0))
                sh.text("BAIE", (u0 + o.width / 2, z + o.height / 2), f"{fmt(o.width)}×{fmt(o.height)}", size=1.4, anchor="c")
                sh.chain([m.level(o.level).floor_top, z, z + o.height], "y", u0 + o.width + 0.12, size=1.2) if o.sill > 0.01 else \
                    sh.dim((u0 + o.width + 0.12, z), (u0 + o.width + 0.12, z + o.height), 0, size=1.2)
                hpts += [u0 - xo, u0 - xo + o.width]
                l = lin.get(o.id)
                if l:
                    sh.rect("ACIER", u0 - 0.20, z + o.height, u0 + o.width + 0.20, z + o.height + l["h"], lw=0.3, fill=(0.95, 0.75, 0.75))
                    sh.text("ACIER", (u0 + o.width / 2, z + o.height + l["h"] + 0.08), l["id"], size=1.3, anchor="c", bold=True)
            for d in m.roof["dormers"]:
                if d["side"] != side:
                    continue
                u0 = xo + min(_facade_coord(m, side, d["y0"]), _facade_coord(m, side, d["y1"]))
                wd = d["y1"] - d["y0"]
                sh.rect("BRIQUE", u0, eav, u0 + wd, eav + 1.35, lw=0.35, fill=(0.99, 0.96, 0.94))
                sh.poly("CHARPENTE", [(u0 - 0.1, eav + 1.35), (u0 + wd / 2, eav + 1.95), (u0 + wd + 0.1, eav + 1.35)], lw=0.4, closed=True, fill=(0.92, 0.65, 0.62))
                sh.rect("BAIE", u0 + 0.20, eav, u0 + wd - 0.20, eav + d["window_h"], lw=0.35, fill=(0.85, 0.92, 1.0))
                sh.text("CHARPENTE", (u0 + wd / 2, eav + 1.45), d["id"], size=1.3, anchor="c")
            for p in r["lintels"]["posts"]:
                if p["side"] == side:
                    u0 = xo + min(_facade_coord(m, side, p["y0"]), _facade_coord(m, side, p["y1"]))
                    sh.rect("ACIER", u0, 0, u0 + (p["y1"] - p["y0"]), p["height"], lw=0.35, fill=(0.85, 0.2, 0.2))
            for lv in m.levels[1:]:
                sh.line("NIVEAU", (xo - 0.5, lv.floor_top), (xo + full + 0.5, lv.floor_top), lw=0.13, dash="axis")
            for z, lab in [(lv.floor_top, lv.name) for lv in m.levels if lv.floor_top > -1] + [(eav, "égout"), (rid, "faîtage")]:
                sh.level_mark((xo + full + 0.55, z), z, lab)
            zc = (m.levels[0].floor_top - 0.20) if has_basement(m) else 0.0
            sh.chain([xo + v for v in sorted(set(round(h, 3) for h in hpts))], "x", zc - 0.45, size=1.3)
            sh.dim((xo, zc - 0.90), (xo + full, zc - 0.90), 0, size=1.8)
            sh.chain([0.0] + [lv.floor_top for lv in m.levels[1:] if lv.floor_top > 0] + [eav, rid], "y", xo - 0.45, size=1.3)
            sh.text("TITRE", (xo, rid + 0.7), m.side(side)["label"].upper(), size=3.0, bold=True)
            xo += full + 3.0
        sh.notes = ["Élévations vues de l'extérieur. Cotes des baies : allège depuis le sol fini, hauteur et largeur de tableau.",
                    "Rose : linteaux BA (repères et aciers sur les plans de niveau). Rouge : poteaux BA de trumeau.",
                    "Lucarnes : front sur l'arase d'égout, chevêtres en charpente (CH-01).",
                    "Enduit, menuiseries et teintes : selon PC."]
        sheets.append(sh)
    return sheets


# ================================================================ détails
def go_details(m: Model, r: dict) -> Sheet:
    sh = _new("GO-11", "Détails d'exécution cotés — fondations, voiles, chaînages, linteaux, poteaux", scale=20, origin=(-0.45, -3.25), area=(18, 40, 298, 282))
    items = r["foundations"]["items"]
    exc = max([i for i in items if i["excentric"]] or items, key=lambda i: i["ratio_ELS"])
    cen = next((i for i in items if not i["excentric"] and i["side"] != "cage"), items[0])
    vw = (r["basement"]["walls"] or [{"face_terre": "—"}])[0]
    zb = -(r["foundations"]["base_depth"] + 0.10)
    z_dal = m.levels[0].floor_top if has_basement(m) else 0.0
    base = -2.90

    def Z(z):  # niveau réel → repère du détail
        return base + (z - zb)

    def bar(p, q, lw=0.6):
        sh.line("ACIER", p, q, lw=lw)

    def dot(p, d=0.012):
        sh.circle("ACIER", p, d, lw=0.2, fill=(0.8, 0.1, 0.1))

    ox, B, h = 0.0, exc["B"], exc["h"]
    top_v = Z(0.0)
    c = 0.05
    if not has_basement(m):
        _detail_d1_ground(sh, m, r, exc, base, Z, bar, dot)
    else:
        _detail_d1_basement(sh, m, r, exc, vw, base, Z, zb, z_dal, bar, dot)
    _details_rest(sh, m, r, cen, base, bar, dot)
    return sh


def _detail_d1_ground(sh, m, r, exc, base, Z, bar, dot):
    ox, B, h, c = 0.0, exc["B"], exc["h"], 0.05
    xw = ox if exc["excentric"] else ox + (B - 0.20) / 2
    zb = -(r["foundations"]["base_depth"] + 0.10)
    top = Z(0.0)
    sh.rect("TERRAIN", ox - 0.45, base - 0.1, xw, Z(-0.10), lw=0.0, fill=SOIL_FILL)
    sh.rect("FOND", ox, base, ox + B, base + h, lw=0.4, fill=CONC_FILL)
    sh.rect("BA", xw, base + h, xw + 0.20, top, lw=0.4, fill=CONC_FILL)
    sh.rect("BRIQUE", xw, top, xw + 0.20, top + 0.70, lw=0.4, fill=BRICK_FILL, hatch="brique")
    sh.rect("BA", xw + 0.20, top - 0.15, ox + B + 1.35, top, lw=0.4, fill=CONC_FILL)
    sh.rect("TERRAIN", xw + 0.20, top - 0.35, ox + B + 1.35, top - 0.15, lw=0.1, fill=(0.85, 0.80, 0.70))
    sh.rect("TERRAIN", xw + 0.20, base + h, ox + B + 1.35, top - 0.35, lw=0.0, fill=SOIL_FILL)
    bar((ox + c, base + c), (ox + B - c, base + c))
    bar((ox + c, base + c), (ox + c, base + h - c))
    bar((ox + B - c, base + c), (ox + B - c, base + h - c))
    for k in range(4):
        dot((ox + c + 0.03 + k * (B - 2 * c - 0.06) / 3, base + c + 0.03))
    bar((xw + 0.04, base + c), (xw + 0.04, top + 0.55))
    bar((xw + 0.16, base + c), (xw + 0.16, top + 0.55))
    bar((xw + 0.25, top - 0.04), (ox + B + 1.2, top - 0.04), lw=0.4)
    sh.text("ACIER", (ox + B + 0.05, base + 0.04), f"transv. {exc['transversal']} (lit inf.)", size=1.8)
    sh.text("ACIER", (ox + B + 0.05, base + 0.18), f"long. {exc['longitudinal']}", size=1.8)
    sh.text("ACIER", (xw + 0.30, (base + h + top) / 2), "mur de soubassement BA 20 : HA10 e=20 verticaux + HA8 e=20 horizontaux", size=1.8)
    sh.text("ACIER", (xw + 0.30, top + 0.05), "dallage 15 : ST25C en nappe supérieure", size=1.8)
    sh.text("ACIER", (xw + 0.30, top + 0.45), "chaînage 4HA10 + amorces des chaînages verticaux", size=1.8)
    sh.dim((ox, base - 0.10), (ox + B, base - 0.10), 0, text=fmt(B))
    sh.chain([ox, xw, xw + 0.20, ox + B], "x", base - 0.25, size=1.6)
    sh.chain([base, base + h, top - 0.15, top], "y", ox - 0.55, size=1.6)
    for z, lab in ((zb, "arase inf."), (zb + h, "arase sup."), (0.0, "dallage fini")):
        sh.text("NIVEAU", (ox + B + 1.40, Z(z) - 0.02), f"{z:+.2f} {lab}".replace(".", ","), size=1.6)
    sh.text("TITRE", (ox, top + 0.95), "D1 — SEMELLE " + ("EXCENTRÉE" if exc["excentric"] else "FILANTE") + " + SOUBASSEMENT + DALLAGE", size=2.8, bold=True)


def _detail_d1_basement(sh, m, r, exc, vw, base, Z, zb, z_dal, bar, dot):
    ox, B, h = 0.0, exc["B"], exc["h"]
    top_v = Z(0.0)
    sh.rect("TERRAIN", ox - 0.35, base - 0.1, ox, top_v, lw=0.0, fill=SOIL_FILL)
    sh.text("TERRAIN", (ox - 0.25, (base + top_v) / 2), "LIMITE / MITOYEN", size=2.0, rot=90)
    sh.rect("FOND", ox, base, ox + B, base + h, lw=0.4, fill=CONC_FILL)
    sh.rect("BA", ox, base + h, ox + 0.20, top_v, lw=0.4, fill=CONC_FILL)
    sh.rect("BA", ox + 0.20, Z(z_dal) - 0.20, ox + 1.35, Z(z_dal), lw=0.4, fill=CONC_FILL)
    sh.rect("TERRAIN", ox + 0.20, Z(z_dal) - 0.40, ox + 1.35, Z(z_dal) - 0.20, lw=0.1, fill=(0.85, 0.80, 0.70))
    s0 = r["floors"]["slabs"][0]
    sh.rect("PLANCHER", ox + 0.20, top_v - s0["h"], ox + 1.35, top_v, lw=0.3, fill=(0.80, 0.88, 0.97))
    c = 0.05
    bar((ox + c, base + c), (ox + B - c, base + c))
    bar((ox + B - c, base + c), (ox + B - c, base + h - c))
    bar((ox + c, base + c), (ox + c, base + h + 0.6))
    for k in range(4):
        dot((ox + c + 0.03 + k * (B - 2 * c - 0.06) / 3, base + c + 0.03))
    bar((ox + 0.04, base + c), (ox + 0.04, top_v - 0.05))
    bar((ox + 0.16, base + h - 0.10), (ox + 0.16, top_v - 0.05), lw=0.4)
    bar((ox + 0.16, Z(z_dal) - 0.10), (ox + 0.9, Z(z_dal) - 0.10), lw=0.4)
    bar((ox + 0.04, top_v - 0.05), (ox + 0.9, top_v - 0.05), lw=0.4)
    sh.text("ACIER", (ox + B + 0.05, base + 0.04), f"transv. {exc['transversal']} (lit inf.)", size=1.8)
    sh.text("ACIER", (ox + B + 0.05, base + 0.18), f"long. {exc['longitudinal']}", size=1.8)
    sh.text("ACIER", (ox + 0.25, (Z(z_dal) + top_v) / 2 + 0.1), f"voile BA 20 : {vw['face_terre']} face terre", size=1.8)
    sh.text("ACIER", (ox + 0.25, (Z(z_dal) + top_v) / 2 - 0.05), "HA8 e=20 face int. + horiz. HA8 e=20", size=1.8)
    sh.text("ACIER", (ox + 0.25, Z(z_dal) + 0.06), "dallage 20 : ST25C sup. + inf. (tirant)", size=1.8)
    sh.text("ACIER", (ox + 0.25, top_v + 0.05), "plancher + chaînage 4HA10 en tête de voile", size=1.8)
    sh.dim((ox, base - 0.10), (ox + B, base - 0.10), 0, text=fmt(B))
    sh.dim((ox, base - 0.25), (ox + 0.20, base - 0.25), 0, size=1.6)
    sh.chain([base, base + h, Z(z_dal) - 0.20, Z(z_dal), top_v - s0["h"], top_v], "y", ox - 0.42, size=1.6)
    for z, lab in ((zb, "arase inf."), (zb + h, "arase sup."), (z_dal, "dallage fini"), (0.0, "RDC fini")):
        sh.text("NIVEAU", (ox + 1.40, Z(z) - 0.02), f"{z:+.2f} {lab}".replace(".", ","), size=1.6)
    sh.text("TITRE", (ox, top_v + 0.35), "D1 — SEMELLE EXCENTRÉE + VOILE + DALLAGE", size=2.8, bold=True)


def _details_rest(sh, m, r, cen, base, bar, dot):
    c = 0.05
    # D2
    ox = 2.55
    B2, h2 = cen["B"], cen["h"]
    sh.rect("FOND", ox, base, ox + B2, base + h2, lw=0.4, fill=CONC_FILL)
    xw = ox + (B2 - 0.20) / 2
    sh.rect("BA", xw, base + h2, xw + 0.20, base + h2 + 1.6, lw=0.4, fill=CONC_FILL)
    bar((ox + c, base + c), (ox + B2 - c, base + c))
    for k in range(3):
        dot((ox + c + 0.03 + k * (B2 - 2 * c - 0.06) / 2, base + c + 0.03))
    bar((xw + 0.04, base + c), (xw + 0.04, base + h2 + 1.6))
    bar((xw + 0.16, base + c), (xw + 0.16, base + h2 + 1.6))
    sh.text("ACIER", (ox + B2 + 0.05, base + 0.05), f"{cen['transversal']} + {cen['longitudinal']}", size=1.8)
    sh.text("TERRAIN", (ox - 0.15, base + h2 + 0.9), "drain Ø100 + géotextile + imperméabilisation", size=1.6, rot=90)
    sh.chain([ox, xw, xw + 0.20, ox + B2], "x", base - 0.12, size=1.6)
    sh.dim((ox + B2 + 0.25, base), (ox + B2 + 0.25, base + h2), 0, text=fmt(h2))
    sh.text("TITRE", (ox - 0.2, base + h2 + 1.95), "D2 — SEMELLE CENTRÉE", size=2.8, bold=True)
    # D3 sections types
    items3 = [("CHAÎNAGE HORIZ. 20×30", 0.20, 0.30, ["4HA10", "cadres HA6 e=20"]),
              ("CHAÎNAGE VERT. 20×20", 0.20, 0.20, ["4HA10", "cadres HA6 e=20"])]
    big = max(r["lintels"]["lintels"], key=lambda l: l["M_Ed"]) if r["lintels"]["lintels"] else None
    if big:
        items3.append((f"LINTEAU {big['id']} {int(big['b']*100)}×{int(big['h']*100)}", big["b"], big["h"], [f"{big['bottom']} inf. + {big['top']} sup.", big["stirrups"], f"portée {fmt(big['span'])}"]))
    for p in r["lintels"]["posts"][:1]:
        items3.append((f"POTEAU {p['id']} {p['section']}", 0.20, 0.40, [p["steel"]]))
    xx, rowi = 3.75, 0
    for title, b, hh, txt in items3:
        if xx > 4.9:
            xx, rowi = 3.75, rowi + 1
        br = base + 2.6 - rowi * 1.25
        sh.rect("BA", xx, br, xx + b, br + hh, lw=0.4, fill=CONC_FILL)
        cc = 0.03
        sh.rect("ACIER", xx + cc, br + cc, xx + b - cc, br + hh - cc, lw=0.4)
        for (px, py) in ((xx + cc + 0.012, br + cc + 0.012), (xx + b - cc - 0.012, br + cc + 0.012),
                         (xx + cc + 0.012, br + hh - cc - 0.012), (xx + b - cc - 0.012, br + hh - cc - 0.012)):
            dot((px, py))
        sh.dim((xx, br - 0.05), (xx + b, br - 0.05), 0, size=1.4)
        sh.dim((xx + b + 0.05, br), (xx + b + 0.05, br + hh), 0, size=1.4)
        sh.text("TITRE", (xx, br + hh + 0.10), title, size=1.8, bold=True)
        for i, t in enumerate(txt):
            sh.text("ACIER", (xx, br - 0.20 - 0.10 * i), t, size=1.6)
        xx += 1.15
    bs = has_basement(m)
    exc_any = any(i["excentric"] for i in r["foundations"]["items"])
    mit = any(d["type"] == "mitoyen" for d in m.raw["sides"].values())
    sh.notes = [
        ("Béton C25/30 ; acier B500B ; enrobages : fondations 5 cm, voiles enterrés 3,5 cm, poutres/chaînages 3 cm, dalles 2,5 cm." if bs else
         "Béton C25/30 ; acier B500B ; enrobages : fondations 5 cm, soubassements 3,5 cm, poutres/chaînages 3 cm, dalles 2,5 cm."),
        "Recouvrements 50 Ø ; ancrages des aciers de semelle par retour d'équerre ; façonnage selon NF EN 1992-1-1 §8.",
    ] + (["D1 : l'équilibre de la semelle excentrée est assuré par le dallage armé (pied) et le plancher (tête) : ne pas supprimer ni scier le dallage le long du voile."] if exc_any else []) + \
        (["Voiles contre mitoyens : passes ≤ 2 m sous blindage ; joints de reprise avec bande hydrogonflante."] if bs and mit else []) + [
        "Linteaux : appuis ≥ 20 cm ancrés dans les chaînages verticaux ; aucune saignée dans le BA.",
        "Escalier : plan de ferraillage par l'escaliéteur (paillasse 15 cm, HA10 e=15).",
    ]


# ================================================================ charpente
def charpente(m: Model, r: dict, tim: dict) -> Sheet:
    sh = _new("CH-01", "Charpente traditionnelle — plan coté des pannes, chevrons et lucarnes", scale=75, origin=(-1.6, -6.4),
              subtitle=f"Pannes GL24h {tim['panne_section']['label']} sur pignons · chevrons C24 {tim['chevron_section']['label']} e=0,60")
    L, W = m.L, m.W
    sh.rect("BRIQUE", -0.30, 0, L + 0.30, W, lw=0.3)
    sh.line("CHARPENTE", (m.roof["ridge_x"], -0.2), (m.roof["ridge_x"], W + 0.2), lw=0.25, dash="axis")
    for side in bearing_sides(m):
        axis, pos, a0, a1, out = _side_geom(m, side)
        sh.rect("BRIQUE", *_wall_rect(axis, pos, a0, a1, m.t_str), lw=0.3, fill=BRICK_FILL, hatch="brique")
    b = tim["panne_section"]["b"] / 1000
    for p in tim["pannes"]:
        sh.rect("CHARPENTE", p["x"] - b / 2, 0.05, p["x"] + b / 2, W - 0.05, lw=0.4, fill=(0.88, 0.72, 0.52))
        sh.text("CHARPENTE", (p["x"] - b / 2 - 0.08, W / 2), f"{p['id']} {p['role']} GL24h {tim['panne_section']['label']} · dessous {fmt(p['z'] - tim['panne_section']['h']/2000)}", size=1.5, anchor="c", rot=90, bold=True)
        for y in (0.10, W - 0.10):
            sh.rect("BA", p["x"] - 0.10, y - 0.10, p["x"] + 0.10, y + 0.10, lw=0.3, fill=BA_FILL)
    for x in (0.10, L - 0.10):
        sh.rect("CHARPENTE", x - 0.0375, 0.20, x + 0.0375, W - 0.20, lw=0.3, fill=(0.92, 0.80, 0.65))
    dorm = m.roof["dormers"]

    def dormer_x(d):
        xa = 0.0 if _side_geom(m, d["side"])[1] == 0.0 else L - 1.6
        return xa, xa + 1.6

    y = 0.30
    ys = []
    while y < W - 0.25:
        ys.append(y)
        cuts = sorted(dormer_x(d) for d in dorm if d["y0"] < y < d["y1"])
        pts = [-0.30]
        for c0, c1 in cuts:
            pts += [max(c0, -0.30), min(c1, L + 0.30)]
        pts.append(L + 0.30)
        for a, bb in zip(pts[::2], pts[1::2]):
            if bb - a > 0.05:
                sh.line("CHARPENTE", (a, y), (bb, y), lw=0.2)
        y += 0.60
    for d in dorm:
        xa, xb = dormer_x(d)
        sh.rect("CHARPENTE", xa, d["y0"], xb, d["y1"], lw=0.5, fill=(0.98, 0.93, 0.85))
        xc = xb if xa == 0.0 else xa
        sh.rect("CHARPENTE", xc - 0.04, d["y0"] - 0.04, xc + 0.04, d["y1"] + 0.04, lw=0.4, fill=(0.75, 0.55, 0.30))
        sh.text("CHARPENTE", ((xa + xb) / 2, (d["y0"] + d["y1"]) / 2), d["id"], size=1.8, anchor="c", bold=True)
        sh.text("CHARPENTE", ((xa + xb) / 2, (d["y0"] + d["y1"]) / 2 - 0.25), "chevêtre 2×75×200", size=1.2, anchor="c")
        sh.chain([d["y0"], d["y1"]], "y", (xa + xb) / 2 - 0.55 if xa == 0.0 else (xa + xb) / 2 + 0.55, size=1.3)
    sh.chain([0.0] + sorted(p["x"] for p in tim["pannes"]) + [L], "x", W + 0.45, size=1.4)
    sh.dim((-0.30, W + 0.85), (L + 0.30, W + 0.85), 0, text=f"{fmt(L + 0.60)} débords compris", size=1.6)
    sh.chain([0.0] + ys[:3] + [W], "y", L + 0.55, size=1.2)
    sh.dim((L + 0.95, 0), (L + 0.95, W), 0, text=f"portée pannes {fmt(tim['panne_span'])}", size=1.5)
    sh.text("TITRE", (0, W + 1.3), "PLAN DE CHARPENTE (vue de dessus)", size=3.4, bold=True)
    zo = -5.5
    a = math.radians(r["loads"]["roof_pitch_deg"])
    eav, rid = m.roof["eaves_level"], m.roof["ridge_level"]
    f = lambda z: zo + (z - eav)
    sh.poly("CHARPENTE", [(-0.35, f(eav) - 0.35 * math.tan(a)), (m.roof["ridge_x"], f(rid)), (L + 0.35, f(eav) - 0.35 * math.tan(a))], lw=0.8)
    for xw in (0, L - m.t_str):
        sh.rect("BRIQUE", xw, f(m.levels[-1].floor_top), xw + m.t_str, f(eav), lw=0.4, fill=BRICK_FILL, hatch="brique")
    sh.line("PLANCHER", (0, f(m.levels[-1].floor_top)), (L, f(m.levels[-1].floor_top)), lw=1.0)
    sh.line("CHARPENTE", (0.2, f(m.roof["ceiling_level"])), (L - 0.2, f(m.roof["ceiling_level"])), lw=0.25, dash="dashed")
    for p in tim["pannes"]:
        hh = tim["panne_section"]["h"] / 1000
        sh.rect("CHARPENTE", p["x"] - b / 2, f(p["z"]) - hh / 2, p["x"] + b / 2, f(p["z"]) + hh / 2, lw=0.3, fill=(0.88, 0.72, 0.52))
    sh.chain([f(v) for v in sorted({m.levels[-1].floor_top, eav, m.roof["ceiling_level"], rid})], "y", -0.6, size=1.3)
    sh.dim((0, f(m.levels[-1].floor_top) - 0.4), (m.roof["ridge_x"], f(m.levels[-1].floor_top) - 0.4), 0, size=1.4)
    sh.text("CHARPENTE", (L / 2 + 0.5, f(rid) - 1.4), f"pente {r['loads']['roof_pitch_deg']}° · rampant {fmt(r['loads']['rafter_length'])}", size=1.6)
    sh.text("TITRE", (0, f(rid) + 0.3), "COUPE TRANSVERSALE DE LA CHARPENTE", size=2.8, bold=True)
    for z, lab in ((eav, "égout"), (rid, "faîtage"), (m.roof["ceiling_level"], "plafond"), (m.levels[-1].floor_top, m.levels[-1].name)):
        sh.level_mark((L + 0.6, f(z)), z, lab)
    pn, ch = tim["panne_section"], tim["chevron_section"]
    sh.notes = [
        "Comble habité : charpente à pannes sur pignons maçonnés, AUCUNE fermette en W (volume libre jusqu'au plafond).",
        f"Pannes GL24h {pn['label']} : portée {fmt(tim['panne_span'])}, M_Ed = {pn['M_Ed']} kN.m, σ = {pn['sigma']} ≤ {pn['f_md']} MPa, flèche {pn['w_fin_mm']} ≤ {pn['w_lim_mm']} mm.",
        f"Chevrons C24 {ch['label']} entraxe 0,60 ({tim['chevron_count']} u) ; sablières 75×200 sur les arases d'égout.",
        "Appuis des pannes : sommiers BA 20×20×40 dans les pignons + étriers ; feutre de désolidarisation côté voisin.",
        "Lucarnes : chevêtres 2 × 75×200 C24, chevrons de rive doublés, ossature 45×145.",
        tim["bracing"], tim["covering"], tim["insulation"],
        "Bois traités classe 2, humidité ≤ 18 % ; assemblages et organes à justifier par le charpentier (EN 1995).",
    ]
    return sh


# ================================================================ électricité
def elec_level(m: Model, e: dict, lid: str, code: str) -> Sheet:
    lv = m.level(lid)
    sh = _new(code, f"Électricité — {lv.name}", subtitle="NF C 15-100 : prises, éclairage, commandes, communication, circuits spécialisés")
    base_plan(sh, m, lid, dims=False, axes=False, light=True)
    pts = next(l["points"] for l in e["levels"] if l["level"] == lid)
    for p in pts:
        x, y = p["x"], p["y"]
        if p["kind"] == "PC":
            sh.circle("ELEC", (x, y), 0.10, lw=0.35, fill=(1, 1, 1))
            sh.line("ELEC", (x - 0.10, y), (x + 0.10, y), lw=0.35)
        elif p["kind"] == "PL":
            sh.circle("ELEC", (x, y), 0.13, lw=0.35)
            sh.line("ELEC", (x - 0.09, y - 0.09), (x + 0.09, y + 0.09), lw=0.35)
            sh.line("ELEC", (x - 0.09, y + 0.09), (x + 0.09, y - 0.09), lw=0.35)
        elif p["kind"] == "INT":
            sh.circle("ELEC", (x, y), 0.06, lw=0.35, fill=(0.85, 0.45, 0.0))
            sh.line("ELEC", (x, y), (x + 0.15, y + 0.15), lw=0.35)
        elif p["kind"] == "RJ45":
            sh.poly("ELEC", [(x - 0.09, y - 0.07), (x + 0.09, y - 0.07), (x, y + 0.09)], lw=0.35, closed=True)
        elif p["kind"] == "SPEC":
            sh.rect("ELEC", x - 0.10, y - 0.10, x + 0.10, y + 0.10, lw=0.35, fill=(1, 0.93, 0.80))
            sh.text("ELEC", (x - 0.14, y - 0.04), p["code"].split("_")[0][:10], size=1.2, anchor="r")
    gtl = e.get("panel_xy")
    if gtl and gtl["level"] == lid:
        sh.rect("ELEC", gtl["x"] - 0.15, gtl["y"] - 0.30, gtl["x"] + 0.15, gtl["y"] + 0.30, lw=0.5, fill=(1.0, 0.85, 0.55))
        sh.text("ELEC", (gtl["x"] - 0.2, gtl["y"]), "GTL / tableau", size=1.5, anchor="r", bold=True)
    circ = [c for c in e["circuits"] if c["level"] == lid]
    sh.notes = ["Légende : ⊖ prise 16 A · ⊗ point lumineux · ● commande · ▲ RJ45 · ▢ circuit spécialisé."] + \
               [f"{c['name']} : {c['breaker']} A — {c['section']} mm² — {c['points']} pt(s) — {c.get('rcd','')}" for c in circ][:16] + \
               ["Hauteurs : prises 0,30 (1,10 au-dessus des plans de travail), commandes 0,90 à 1,30 ; salles d'eau : volumes 0-1-2."]
    return sh


def elec_panel(m: Model, e: dict) -> Sheet:
    sh = Sheet("EL-05", "Schéma du tableau électrique et liste des circuits", 1000, origin=(0, 0), subtitle=e["standard"])
    y = 222
    sh.text("TITRE", (0, y), "TABLEAU DE RÉPARTITION — " + e["panel"]["head"], size=3.4, bold=True)
    y -= 8
    sh.text("TEXTE", (0, y), f"Coffret {e['panel']['rows']} rangées × 13 modules ({e['panel']['modules']} modules + {e['panel']['spare']}) — {e['panel']['location']}", size=2.5)
    y -= 6
    sh.text("TEXTE", (0, y), e["panel"]["earth"], size=2.3)
    y -= 9
    for col, rcd in enumerate(e["rcds"]):
        x0 = col * 70
        sh.rect("ELEC", x0, y - 5, x0 + 66, y + 2, lw=0.4, fill=(1, 0.93, 0.80))
        sh.text("ELEC", (x0 + 2, y - 3), f"{rcd['id']} — ID {rcd['rating']} A 30 mA type {rcd['type']}", size=2.2, bold=True)
        yy = y - 10
        for name in rcd["circuits"]:
            c = next(cc for cc in e["circuits"] if cc["name"] == name)
            sh.line("ELEC", (x0 + 4, yy + 1), (x0 + 4, yy + 5), lw=0.3)
            sh.text("TEXTE", (x0 + 6, yy + 1.5), trunc(f"{c['breaker']} A · {c['section']} mm² · {name}", len(f"{c['breaker']} A · {c['section']} mm² · ") + 38), size=1.9)
            yy -= 6.5
    sh.text("TEXTE", (0, 40), "Totaux : " + ", ".join(f"{k} = {v}" for k, v in e["totals"].items()) + f" ; surface habitable {e['habitable_area']} m²", size=2.3)
    sh.text("TEXTE", (0, 33), "Câbles estimés : " + ", ".join(f"{k} : {v} m" for k, v in e["cables_m"].items()), size=2.3)
    for i, ru in enumerate(e["rules"]):
        sh.text("TEXTE", (0, 25 - 4.2 * i), trunc("• " + ru, 152), size=1.9)
    sh.dxf = False
    return sh


# ================================================================ plomberie
def plumb_level(m: Model, p: dict, lid: str, code: str) -> Sheet:
    lv = m.level(lid)
    sh = _new(code, f"Plomberie sanitaire — {lv.name}", subtitle="Alimentation EF/ECS (multicouche en pieuvre), évacuations EU/EV PVC, chutes Ø100")
    base_plan(sh, m, lid, dims=False, axes=False, light=True)
    for s in p["stacks"]:
        sh.circle("PLOMB_EV", (s["x"], s["y"]), 0.11, lw=0.6, fill=(0.55, 0.42, 0.25))
        sh.text("PLOMB_EV", (s["x"] + 0.16, s["y"] + 0.12), f"{s['id']} Ø{s['d']}", size=1.8, bold=True)
    riser = {s["id"]: (s["x"] + 0.20, s["y"]) for s in p["stacks"]}
    for f in [f for f in p["fixtures"] if f["level"] == lid]:
        x, y = f["x"], f["y"]
        sh.rect("PLOMB_EF", x - 0.18, y - 0.14, x + 0.18, y + 0.14, lw=0.35, fill=(0.92, 0.96, 1.0))
        sh.text("PLOMB_EF", (x, y - 0.05), trunc(f["label"], 12), size=1.2, anchor="c")
        if f["stack"] in riser:
            st = next(s for s in p["stacks"] if s["id"] == f["stack"])
            sh.poly("PLOMB_EV", [(x, y), (x, st["y"]), (st["x"], st["y"])], lw=0.5)
            sh.text("PLOMB_EV", ((x + st["x"]) / 2, st["y"] + 0.06), f["evac"], size=1.15, anchor="c")
            rx, ry = riser[f["stack"]]
            sh.poly("PLOMB_EF", [(rx, ry), (rx, y + 0.05), (x, y + 0.05)], lw=0.35, dash="dashed")
            if f["ecs"]:
                sh.poly("PLOMB_ECS", [(rx + 0.07, ry), (rx + 0.07, y + 0.11), (x, y + 0.11)], lw=0.35, dash="dashed")
            sh.text("PLOMB_EF", (x + 0.22, y + 0.18), f["alim"].replace("multicouche ", "MC "), size=1.1)
    for rid, (rx, ry) in riser.items():
        sh.rect("PLOMB_EF", rx - 0.06, ry - 0.06, rx + 0.13, ry + 0.06, lw=0.4, fill=(0.75, 0.85, 1.0))
        sh.text("PLOMB_EF", (rx + 0.18, ry - 0.20), f"montée EF/ECS {rid}", size=1.25)
    if lid == m.levels[0].id:
        n = p["nourrice"]
        sh.rect("PLOMB_EF", n["x"] - 0.4, n["y"] - 0.15, n["x"] + 0.4, n["y"] + 0.15, lw=0.5, fill=(0.75, 0.85, 1.0))
        sh.text("PLOMB_EF", (n["x"], n["y"] + 0.22), "nourrices EF/ECS + CET 200 L", size=1.5, anchor="c", bold=True)
        col = p["collector"]["path"]
        sh.poly("PLOMB_EV", col, lw=0.8)
        sh.text("PLOMB_EV", ((col[0][0] + col[-1][0]) / 2, col[0][1] + 0.10), "collecteur Ø100 → réseau public", size=1.4, anchor="c")
        if p["relevage"]["needed"]:
            rv = p["relevage"].get("xy", (m.L - 1.3, 0.9))
            sh.rect("PLOMB_EV", rv[0] - 0.3, rv[1] - 0.3, rv[0] + 0.3, rv[1] + 0.3, lw=0.5, fill=(0.85, 0.75, 0.6))
            sh.text("PLOMB_EV", (rv[0], rv[1] + 0.4), "poste de relevage", size=1.3, anchor="c", bold=True)
    sh.notes = ["Bleu : eau froide · rouge : eau chaude sanitaire · marron : évacuations EU/EV (pente 1 à 3 %)."] + p["rules"][:4] + \
               ([p["relevage"]["spec"]] if lid == m.levels[0].id and p["relevage"]["needed"] else []) + \
               (["Réservations Ø125 au droit des chutes, fourreaux dans les tables de compression."] if lid != m.levels[0].id else [])
    return sh


def plumb_riser(m: Model, p: dict) -> Sheet:
    sh = Sheet("PL-05", "Schéma de principe des colonnes EF/ECS et des chutes EU/EV", 1000, subtitle=p["standard"])
    sh.text("TITRE", (0, 222), "SCHÉMA VERTICAL — chutes, montées EF/ECS", size=3.4, bold=True)
    ids = [lv.id for lv in m.levels]
    z = {lid: 40 + i * (155 / max(1, len(ids) - 1)) for i, lid in enumerate(ids)}
    for lid, y in z.items():
        sh.line("NIVEAU", (0, y), (260, y), lw=0.2, dash="axis")
        sh.text("NIVEAU", (0, y + 1.5), m.level(lid).name, size=2.5, bold=True)
    for k, st in enumerate(p["stacks"]):
        x = 70 + 110 * k
        sh.line("PLOMB_EV", (x, 25), (x, 215), lw=1.6)
        sh.text("PLOMB_EV", (x - 4, 217), f"{st['id']} Ø100 — ventilation primaire hors toiture", size=2.1, bold=True)
        sh.line("PLOMB_EF", (x + 10, 40), (x + 10, 200), lw=0.8)
        sh.line("PLOMB_ECS", (x + 14, 40), (x + 14, 200), lw=0.8)
        for f in [f for f in p["fixtures"] if f["stack"] == st["id"]]:
            same = [g for g in p["fixtures"] if g["stack"] == st["id"] and g["level"] == f["level"]]
            y = z[f["level"]] + 6 + 5 * same.index(f)
            sh.line("PLOMB_EV", (x, y - 2), (x - 30, y), lw=0.6)
            sh.text("TEXTE", (x - 31, y), f"{f['label']} ({f['room']}) {f['evac']}", size=1.6, anchor="r")
            sh.line("PLOMB_EF", (x + 10, y), (x + 40, y), lw=0.4)
            sh.text("TEXTE", (x + 41, y - 0.6), f["alim"], size=1.5)
    sh.text("TEXTE", (0, 18), f"Débit probable : {p['flow']['q_probable']} l/s pour {p['flow']['n']} appareils (y = {p['flow']['y']}) — alimentation générale : {p['flow']['main']}", size=1.9)
    sh.text("TEXTE", (0, 12), trunc(p["ecs"], 170), size=1.9)
    sh.text("TEXTE", (0, 7), trunc(p["rain"], 170), size=1.9)
    sh.dxf = False
    return sh


def _tag(sh: Sheet, kind: str, level: str | None = None) -> Sheet:
    sh.kind, sh.level = kind, level
    return sh


def all_sheets(m: Model, r: dict, tim: dict, e: dict, p: dict) -> list[Sheet]:
    from .i18n import protect
    protect(m)
    stacks = p["stacks"]
    fnd = _tag(go_foundations(m, r), "fond")
    sh = [fnd]
    for k, lv in enumerate(m.levels):
        sh.append(_tag(go_level(m, r, lv.id, f"GO-{k+2:02d}", stacks), "level", lv.id))
    n = len(sh) + 1
    for k, s in enumerate(r["floors"]["slabs"]):
        sh.append(_tag(go_floor(m, r, s, f"GO-{n+k:02d}", stacks), "floor"))
    nsec = n + len(r["floors"]["slabs"])
    sec = _tag(go_sections(m, r, tim), "coupe")
    sec.code = f"GO-{nsec:02d}"
    sh.append(sec)
    facs = go_facades(m, r)
    for k, f in enumerate(facs):
        f.code = f"GO-{nsec + 1:02d}" + (chr(97 + k) if len(facs) > 1 else "")
        sh.append(_tag(f, "facade"))
    det = _tag(go_details(m, r), "detail")
    det.code = f"GO-{nsec + 2:02d}"
    fnd.notes = [x.replace("{DETAILS}", det.code) for x in fnd.notes]
    sh += [det, _tag(charpente(m, r, tim), "charpente")]
    for k, lv in enumerate(m.levels):
        sh.append(_tag(elec_level(m, e, lv.id, f"EL-{k+1:02d}"), "elec", lv.id))
    pn = _tag(elec_panel(m, e), "elec_panel")
    pn.code = f"EL-{len(m.levels)+1:02d}"
    sh.append(pn)
    for k, lv in enumerate(m.levels):
        sh.append(_tag(plumb_level(m, p, lv.id, f"PL-{k+1:02d}"), "plumb", lv.id))
    pr = _tag(plumb_riser(m, p), "plumb_riser")
    pr.code = f"PL-{len(m.levels)+1:02d}"
    sh.append(pr)
    return sh
