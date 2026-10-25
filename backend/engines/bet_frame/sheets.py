"""Planches A3 de l'ossature BA : fondations, coffrage par plancher, tableaux, coupe, plans de niveaux, réseaux,
schémas verticaux des colonnes. Mêmes primitives que bet_core (PDF à l'échelle exacte + DXF)."""
from __future__ import annotations

from engines.bet_core.draw import Sheet

from .calc import mesh_txt, num
from .lang import _
from .model import Frame

NAT: set[str] = set()            # textes déjà rédigés dans la langue du livrable (le rendu ne les retraduit pas)
AREA = (14, 22, 303, 282)        # zone de dessin (mm), le cartouche et les notes restent à droite
SCALES = (50, 75, 100, 125, 150, 200, 250, 300, 400, 500)
BA = (0.55, 0.56, 0.60)
BA_LIGHT = (0.88, 0.88, 0.90)
FOND = (0.85, 0.93, 0.87)
SOIL = (0.93, 0.89, 0.80)
HEAD = (0.90, 0.93, 0.95)
UNIT_FILL = [(0.97, 0.95, 0.90), (0.91, 0.95, 0.97), (0.93, 0.97, 0.92), (0.98, 0.93, 0.93), (0.95, 0.93, 0.98), (0.97, 0.97, 0.90)]


def S(x) -> str:
    x = str(x)
    NAT.add(x)
    return x


def _new(code, title, scale, origin, subtitle="", kind="", level=None) -> Sheet:
    sh = Sheet(code=code, title=S(title), scale=scale, origin=origin, subtitle=S(subtitle))
    sh.area_mm = AREA
    sh.kind, sh.level = kind, level
    return sh


def _note(sh: Sheet, *lines):
    sh.notes += [S(x) for x in lines if x]


def u(sh: Sheet, mm: float) -> float:
    """mm papier → m modèle."""
    return mm * sh.scale / 1000


def plan_scale(m: Frame, extra=6.0) -> int:
    w = AREA[2] - AREA[0]
    h = AREA[3] - AREA[1]
    for s in SCALES:
        if (m.L + extra) * 1000 / s <= w and (m.W + extra) * 1000 / s <= h:
            return s
    return SCALES[-1]


PAPERS = (("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841))
EXE_MARGIN = 66          # mm papier autour de l'emprise : axes, bulles, trois chaînes de cotes


def exe_format(m: Frame) -> tuple[str, int, tuple]:
    """Plus petit format où l'ouvrage tient à 1:50, 1:75 ou 1:100 (échelles d'exécution) ; sinon A0 à l'échelle qui tient."""
    for name, W, H in PAPERS:
        area = (14, 22, W - 117, H - 15)
        for sc in (50, 75, 100):
            if m.L * 1000 / sc + EXE_MARGIN <= area[2] - area[0] and m.W * 1000 / sc + EXE_MARGIN <= area[3] - area[1]:
                return name, sc, area
    name, W, H = PAPERS[-1]
    area = (14, 22, W - 117, H - 15)
    sc = next((s for s in SCALES if m.L * 1000 / s + EXE_MARGIN <= area[2] - area[0] and m.W * 1000 / s + EXE_MARGIN <= area[3] - area[1]), SCALES[-1])
    return name, sc, area


def _exe_sheet(m: Frame, code, title, subtitle="", kind="", level=None) -> Sheet:
    """Planche d'exécution (coffrage, fondations) : grand format et échelle 1:50 / 1:100 comme un plan de BET."""
    from reportlab.lib.units import mm as _mm
    name, sc, area = exe_format(m)
    W, H = next((w, h) for n, w, h in PAPERS if n == name)
    w = (area[2] - area[0]) * sc / 1000
    h = (area[3] - area[1]) * sc / 1000
    ox = m.gx[0] - (w - m.L) / 2
    oy = m.gy[0] - (h - m.W) / 2
    sh = _new(code, title, sc, (ox, oy), subtitle, kind, level)
    sh.area_mm = area
    sh.page = (W * _mm, H * _mm)
    sh.paper = name
    return sh


def _plan_sheet(m: Frame, code, title, subtitle="", kind="", level=None) -> Sheet:
    sc = plan_scale(m)
    w = (AREA[2] - AREA[0]) * sc / 1000
    h = (AREA[3] - AREA[1]) * sc / 1000
    ox = m.gx[0] - (w - m.L) / 2
    oy = m.gy[0] - (h - m.W) / 2
    return _new(code, title, sc, (ox, oy), subtitle, kind, level)


# ================================================================ éléments communs
def grid(sh: Sheet, m: Frame, dims=True):
    """Axes + bulles ; les chaînes de cotes sont dessinées par grid_dims() en fin de planche (au-dessus des remplissages)."""
    sh._grid_dims = dims
    ext = u(sh, 16)
    r = u(sh, 3.2)
    x0, x1, y0, y1 = m.gx[0], m.gx[-1], m.gy[0], m.gy[-1]
    for x, lab in zip(m.gx, m.xl):
        sh.line("AXE", (x, y0 - ext), (x, y1 + ext), 0.18, "axis")
        for yy in (y0 - ext - r, y1 + ext + r):
            sh.circle("AXE", (x, yy), r, 0.3, (1, 1, 1))
            sh.text("AXE", (x, yy - u(sh, 1.0)), S(lab), 2.6, "c", bold=True)
    for y, lab in zip(m.gy, m.yl):
        sh.line("AXE", (x0 - ext, y), (x1 + ext, y), 0.18, "axis")
        for xx in (x0 - ext - r, x1 + ext + r):
            sh.circle("AXE", (xx, y), r, 0.3, (1, 1, 1))
            sh.text("AXE", (xx, y - u(sh, 1.0)), S(lab), 2.6, "c", bold=True)


def grid_dims(sh: Sheet, m: Frame):
    if not getattr(sh, "_grid_dims", False):
        return
    x0, x1, y0, y1 = m.gx[0], m.gx[-1], m.gy[0], m.gy[-1]
    bs = max([b.get("depth", 0) for b in m.balconies if str(b.get("side", "")).upper() == "S"] or [0])
    bw = max([b.get("depth", 0) for b in m.balconies if str(b.get("side", "")).upper() == "W"] or [0])
    oy = max(u(sh, 6), bs + u(sh, 3))
    ox = max(u(sh, 6), bw + u(sh, 3))
    sh.chain(m.gx, "x", y0 - oy, size=1.9)
    sh.dim((x0, y0), (x1, y0), -(oy + u(sh, 4.5)), size=2.0)
    sh.chain(m.gy, "y", x0 - ox, size=1.9)
    sh.dim((x0, y0), (x0, y1), ox + u(sh, 4.5), size=2.0)


def tw(s: str, size: float) -> float:
    """Largeur approchée d'un texte (mm papier)."""
    return len(s) * 0.53 * size


def _dominant(vals):
    from collections import Counter
    return Counter(vals).most_common(1)[0][0] if vals else None


def columns(sh: Sheet, m: Frame, r: dict, tags=True):
    """Poteaux ; étiquette = repère seul, section ajoutée seulement si elle diffère de la section courante (note de planche)."""
    z = _z_sheet(sh, m)
    floor = getattr(sh, "kind", "") == "floor"
    cols = [c for c in r["columns"] if z is None or c.get("z_top") is None or
            (c["z_top"] >= z - 1e-6 if floor else c["z_top"] > z + 1e-6)]       # poteaux présents à ce niveau
    dom = _dominant([(int(round(c["b"] * 100)), int(round(c["h"] * 100))) for c in cols])
    for c in cols:
        b, h = c["b"], c["h"]
        sh.rect("BA", c["x"] - b / 2, c["y"] - h / 2, c["x"] + b / 2, c["y"] + h / 2, 0.4, BA)
        if tags:
            sec = (int(round(b * 100)), int(round(h * 100)))
            if getattr(sh, "paper", None):
                sh.text("TEXTE", (c["x"] + b / 2 + u(sh, 0.7), c["y"] + h / 2 + u(sh, 0.6)), S(c["name"]), 1.8, bold=True)
                sh.text("TEXTE", (c["x"] + b / 2 + u(sh, 0.7), c["y"] + h / 2 - u(sh, 1.4)), S(f"{sec[0]}x{sec[1]}"), 1.4)
                continue
            lab = c["name"] + ("" if sec == dom else f" {sec[0]}×{sec[1]}")
            sh.text("TEXTE", (c["x"] + b / 2 + u(sh, 0.6), c["y"] + h / 2 + u(sh, 0.5)), S(lab), 1.45, bold=sec != dom)
    if tags and dom:
        sh._col_dom = dom


def cores(sh: Sheet, m: Frame, cut=True):
    for c in m.cores:
        t = c["wall"]
        for (a, b_, cc, d) in ((c["x0"], c["y0"], c["x1"], c["y0"] + t), (c["x0"], c["y1"] - t, c["x1"], c["y1"]),
                               (c["x0"], c["y0"], c["x0"] + t, c["y1"]), (c["x1"] - t, c["y0"], c["x1"], c["y1"])):
            sh.rect("BA", a, b_, cc, d, 0.35, BA, hatch="ba" if cut else None)
        if cut:
            sh.line("TEXTE", (c["x0"] + t, c["y0"] + t), (c["x1"] - t, c["y1"] - t), 0.15)
            sh.line("TEXTE", (c["x0"] + t, c["y1"] - t), (c["x1"] - t, c["y0"] + t), 0.15)
        sh.text("TEXTE", ((c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2 + u(sh, 1.2)), S(c.get("label") or c.get("id") or ""), 1.7, "c", bold=True)
        sh.text("TEXTE", ((c["x0"] + c["x1"]) / 2, (c["y0"] + c["y1"]) / 2 - u(sh, 2.0)),
                S(_("voiles BA e=", "paredes BA e=") + num(t)), 1.5, "c")


def _ctx(sh: Sheet, m: Frame):
    """Contexte d'emprise de la planche : dalle (plans de coffrage) ou étage (plans de niveaux, réseaux, AVAC)."""
    lid = getattr(sh, "level", None)
    if not lid or not (m.has_setbacks or m.voids):
        return m._Ctx(m, m.voids)
    if getattr(sh, "kind", "") == "floor":
        return m.at_slab(lid)
    if lid in [l.id for l in m.levels]:
        return m.at_storey(lid)
    return m._Ctx(m, m.voids)


def outline(sh: Sheet, m: Frame, lw=0.5):
    with _ctx(sh, m):
        if not m.voids:
            sh.rect("BA", m.gx[0], m.gy[0], m.gx[-1], m.gy[-1], lw)
            return
        for a, b in m.boundary_edges():          # emprise réelle (L, U, cour, étage en retrait)
            sh.line("BA", a, b, lw)
    if m.has_setbacks and getattr(sh, "kind", "") != "floor":   # emprise du niveau inférieur en trait fin (terrasses / sous-sol)
        for a, b in m.boundary_edges():
            sh.line("FOND_PLAN", a, b, 0.18, "dashed")


def _z_sheet(sh: Sheet, m: Frame):
    lid = getattr(sh, "level", None)
    if not lid:
        return None
    if lid == "COB":
        return m.slabs[-1].z
    lv = next((l for l in m.levels if l.id == lid), None)
    return lv.z if lv else None


def _balcony_rect(m: Frame, bc: dict):
    """Rectangle du balcon, limité à la façade réellement construite (emprise de la dalle courante)."""
    d = bc["depth"]
    a0, a1 = max(bc["a0"], 0.0), min(bc["a1"], m.L if bc["side"] in ("S", "N") else m.W)
    side = bc["side"]
    if side in ("S", "N"):
        j = 0 if side == "S" else len(m.gy) - 2
        xs = [(m.gx[i] - m.gx[0], m.gx[i + 1] - m.gx[0]) for i in range(len(m.gx) - 1) if m.cell_in(i, j)]
        if xs:
            a0, a1 = max(a0, min(x for x, _x in xs)), min(a1, max(x for _x, x in xs))
    else:
        i = 0 if side == "W" else len(m.gx) - 2
        ys = [(m.gy[j] - m.gy[0], m.gy[j + 1] - m.gy[0]) for j in range(len(m.gy) - 1) if m.cell_in(i, j)]
        if ys:
            a0, a1 = max(a0, min(y for y, _y in ys)), min(a1, max(y for _y, y in ys))
    if bc["side"] == "S":
        return m.gx[0] + a0, m.gy[0] - d, m.gx[0] + a1, m.gy[0]
    if bc["side"] == "N":
        return m.gx[0] + a0, m.gy[-1], m.gx[0] + a1, m.gy[-1] + d
    if bc["side"] == "W":
        return m.gx[0] - d, m.gy[0] + a0, m.gx[0], m.gy[0] + a1
    return m.gx[-1], m.gy[0] + a0, m.gx[-1] + d, m.gy[0] + a1



# ================================================================ conventions des plans d'exécution (cotes en cm, niveaux en m)
GREY_BEAM = (0.80, 0.80, 0.82)
REV = 0.05                     # épaisseur réservée aux revêtements : arase brute = niveau fini − 5 cm


def cm(v: float) -> str:
    c = v * 100
    return f"{c:.0f}" if abs(c - round(c)) < 0.05 else num(c, 1)


def lev(z: float) -> str:
    return ("+" if z >= 0 else "") + num(z, 2)


def dim_cm(sh: Sheet, p1, p2, off=0.0, size=1.6):
    if ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5 >= 0.01:
        sh.dim(p1, p2, off, text=S(cm(((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5)), size=size)


def chain_cm(sh: Sheet, pts, axis: str, at: float, size=1.6):
    q = []
    for v in sorted(pts):
        if not q or v - q[-1] >= 0.015:
            q.append(v)
    for a, b in zip(q, q[1:]):
        if axis == "x":
            dim_cm(sh, (a, at), (b, at), 0, size)
        else:
            dim_cm(sh, (at, a), (at, b), 0, size)


def _cols_here(sh: Sheet, m: Frame, r: dict) -> list[dict]:
    z = _z_sheet(sh, m)
    floor = getattr(sh, "kind", "") == "floor"
    return [c for c in r["columns"] if z is None or c.get("z_top") is None or
            (c["z_top"] >= z - 1e-6 if floor else c["z_top"] > z + 1e-6)]


def exe_dims(sh: Sheet, m: Frame, r: dict, faces: list[tuple[float, float]] | None = None):
    """Trois chaînes en bas et à gauche (cm) : nus des poteaux / voiles de rive, entraxes, hors-tout."""
    x0, x1, y0, y1 = m.gx[0], m.gx[-1], m.gy[0], m.gy[-1]
    bs = max([b.get("depth", 0) for b in m.balconies if str(b.get("side", "")).upper() == "S"] or [0])
    bw = max([b.get("depth", 0) for b in m.balconies if str(b.get("side", "")).upper() == "W"] or [0])
    cols = _cols_here(sh, m, r)
    fx = [x0, x1] + [v for c in cols if abs(c["y"] - y0) < 0.05 for v in (c["x"] - c["b"] / 2, c["x"] + c["b"] / 2)]
    fy = [y0, y1] + [v for c in cols if abs(c["x"] - x0) < 0.05 for v in (c["y"] - c["h"] / 2, c["y"] + c["h"] / 2)]
    if faces:
        fx += [a for a, _b in faces]
        fy += [b for _a, b in faces]
    oy = max(u(sh, 5), bs + u(sh, 3))
    ox = max(u(sh, 5), bw + u(sh, 3))
    chain_cm(sh, [v for v in fx if x0 - 1 <= v <= x1 + 1], "x", y0 - oy)
    chain_cm(sh, m.gx, "x", y0 - oy - u(sh, 5), 1.8)
    dim_cm(sh, (x0, y0 - oy - u(sh, 10)), (x1, y0 - oy - u(sh, 10)), 0, 2.0)
    chain_cm(sh, [v for v in fy if y0 - 1 <= v <= y1 + 1], "y", x0 - ox)
    chain_cm(sh, m.gy, "y", x0 - ox - u(sh, 5), 1.8)
    dim_cm(sh, (x0 - ox - u(sh, 10), y0), (x0 - ox - u(sh, 10), y1), 0, 2.0)


def _arrow(sh: Sheet, a, b, layer="TEXTE", head=1.4):
    sh.line(layer, a, b, 0.25)
    import math as _m
    L = _m.hypot(b[0] - a[0], b[1] - a[1])
    if L < 1e-6:
        return
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    hh, hw = u(sh, head), u(sh, head * 0.45)
    for (px, py), sg in ((b, 1), (a, -1)):
        bx, by = px - sg * ux * hh, py - sg * uy * hh
        sh.poly(layer, [(px, py), (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)], 0.1, True, (0.1, 0.1, 0.1))


def slab_bubble(sh: Sheet, c, z_fini: float, h: float, kind="DP"):
    """Bulle de dalle (arase brute b / épaisseur cm / type) + étiquette du niveau fini f."""
    R = u(sh, 4.2)
    sh.circle("TEXTE", c, R, 0.3, (1, 1, 1))
    sh.line("TEXTE", (c[0] - R, c[1]), (c[0] + R, c[1]), 0.2)
    sh.text("TEXTE", (c[0], c[1] + u(sh, 1.2)), S(lev(z_fini - REV) + "b"), 1.45, "c")
    sh.text("TEXTE", (c[0], c[1] - u(sh, 2.6)), S(f"{cm(h)} {kind}"), 1.45, "c", bold=True)
    w = u(sh, 1.45 * 0.56 * (len(lev(z_fini)) + 1) + 2.4)
    bx = c[0] + R + u(sh, 1.2)
    sh.rect("TEXTE", bx, c[1] - u(sh, 1.6), bx + w, c[1] + u(sh, 1.6), 0.25, (1, 1, 1))
    sh.text("TEXTE", (bx + w / 2, c[1] - u(sh, 0.55)), S(lev(z_fini) + "f"), 1.45, "c")
    return R, w


def cof_legend(sh: Sheet):
    sh.legend = [(k, S(v)) for k, v in (
        ("COF_POUTRE", _("Poutre béton (retombée)", "Viga de betão")),
        ("COF_POTEAU", _("Poteau BA", "Pilar de betão armado")),
        ("COF_VOILE", _("Voile BA / noyau", "Parede BA / núcleo")),
        ("COF_RESA", _("Réservation / trémie", "Negativo / courette")),
        ("COF_DALLE", _("Arase brute b / ép. cm / type", "Cota bruta b / esp. cm / tipo")),
        ("COF_ARASE", _("Niveau fini f", "Cota de acabamento f")),
        ("COF_PORTEE", _("Sens de portée de la dalle", "Direção de vão da laje")),
    )]


def hypotheses(m: Frame, r: dict) -> list[str]:
    mt, f = r["mat"], r["foundations"]
    sig = num(f["sigma_kpa"] / 1000, 2)
    ref = (m.project or {}).get("pc_ref") or ""
    return [
        _("HYPOTHÈSES DE CALCUL (sauf indication contraire) — cotes en cm, niveaux en m.",
          "HIPÓTESES DE CÁLCULO (salvo indicação em contrário) — cotas em cm, níveis em m."),
        _(f"Sol : contrainte admissible {sig} MPa à l'ELS" + (" (hypothèse, à confirmer par l'étude G2)." if f["assumed"] else "."),
          f"Terreno: tensão admissível {sig} MPa" + (" (hipótese, a confirmar pelo estudo geotécnico)." if f["assumed"] else ".")),
        _(f"Aciers : HA {mt['steel']} ; treillis soudés B500A.", f"Aço: {mt['steel']} nervurado; redes eletrossoldadas B500A."),
        _(f"Béton : propreté C16/20 X0 ; fondations, longrines {mt['concrete']} XC2 ; poteaux, voiles, planchers, poutres {mt['concrete']} XC1 ; balcons, voiles extérieurs {mt['concrete']} XC4.",
          f"Betão: limpeza C16/20 X0; fundações, vigas de fundação {mt['concrete']} XC2; pilares, paredes, lajes, vigas {mt['concrete']} XC1; varandas, paredes exteriores {mt['concrete']} XC4."),
        _("Enrobage : ouvrages contre terre 4 cm (5 cm si cuvelage) ; poutres et poteaux 3 cm ; dalles 2,5 cm.",
          "Recobrimento: elementos contra o terreno 4 cm (5 cm se impermeabilizados); vigas e pilares 3 cm; lajes 2,5 cm."),
        _("Degré coupe-feu : selon la famille du bâtiment (habitation 3e famille : R 60) — à confirmer par la notice de sécurité.",
          "Resistência ao fogo: segundo a categoria de risco (RT-SCIE) — a confirmar pelo projeto de segurança contra incêndio."),
        _("b = arase brute de dalle, f = niveau fini (5 cm de revêtements), Ai = arase inférieure de poutre, As = arase supérieure de fondation.",
          "b = cota bruta da laje, f = cota de acabamento (5 cm de revestimentos), Ai = cota inferior da viga, As = cota superior da fundação."),
        (_(f"Plans de référence : architecte {ref}.", f"Desenhos de referência: arquitetura {ref}.") if ref else ""),
    ]


# ================================================================ tableaux (coordonnées papier en mm, échelle 1:1000)
def _fit(txt: str, w: float, size: float, cw=0.53) -> tuple[str, float]:
    """Texte de cellule tenant dans la largeur w (mm) : police réduite jusqu'à 1,35 puis coupure « … »."""
    if not txt or len(txt) * cw * size <= w:
        return txt, size
    sz = max(1.35, w / (len(txt) * cw))
    if len(txt) * cw * sz <= w:
        return txt, sz
    n = max(3, int(w / (cw * sz)) - 1)
    return txt[:n].rstrip() + "…", sz


def table_sheets(code, title, subtitle, head: list[tuple[str, float]], rows: list[list], kind: str, notes=(), row_h=4.4, size=1.85,
                 groups: list[int] | None = None) -> list[Sheet]:
    hh = row_h * 1.6
    cap = int((AREA[3] - AREA[1] - hh - 4) // row_h)
    out = []
    chunks = [rows[i:i + cap] for i in range(0, len(rows), cap)] or [[]]
    for k, chunk in enumerate(chunks):
        sh = _new(code + (chr(97 + k) if len(chunks) > 1 else ""), title, 1000, (0, 0), subtitle, kind)
        sh.dxf = False
        W = sum(w for _h, w in head)
        y = AREA[3] - AREA[1] - 2
        sh.rect("TEXTE", 0, y - hh, W, y, 0.35, HEAD)
        x = 0
        for txt, w in head:
            lines = str(txt).split("\n")
            for li, ln in enumerate(lines):
                sh.text("TEXTE", (x + w / 2, y - hh / 2 + (len(lines) - 1) * 1.3 - li * 2.6 - 0.7), S(ln), size, "c", bold=True)
            x += w
        y -= hh
        for ri, row in enumerate(chunk):
            fill = (0.975, 0.98, 0.985) if ri % 2 else None
            sh.rect("TEXTE", 0, y - row_h, W, y, 0.12, fill)
            x = 0
            for (txt, w), cell in zip(head, row):
                anchor = "l" if x == 0 else "c"
                px = x + 1.4 if anchor == "l" else x + w / 2
                txt, sz = _fit(str(cell), w - 2.0, size)
                sh.text("TEXTE", (px, y - row_h + 1.25), S(txt), sz, anchor, bold=(x == 0))
                x += w
            y -= row_h
        x = 0
        for _h, w in head:
            sh.line("TEXTE", (x, AREA[3] - AREA[1] - 2), (x, y), 0.2)
            x += w
        sh.line("TEXTE", (W, AREA[3] - AREA[1] - 2), (W, y), 0.2)
        _note(sh, *notes)
        out.append(sh)
    return out


# ================================================================ planches
def foundations(m: Frame, r: dict) -> Sheet:
    f = r["foundations"]
    sh = _exe_sheet(m, "EST-01", _("Plan des fondations — coffrage", "Planta de fundações — cofragem"),
                    _("EXE · STR · FON — semelles isolées, longrines, radier des noyaux", "EXE · EST · FUN — sapatas isoladas, vigas de fundação, ensoleiramento dos núcleos"), "fond")
    grid(sh, m, dims=False)
    z_as = m.levels[0].z - f["depth"]           # arase inférieure des semelles (sous le niveau bas)
    for c in f["core_rafts"]:
        sh.rect("FOND", c["x0"], c["y0"], c["x1"], c["y1"], 0.35, FOND)
        sh.text("FOND", ((c["x0"] + c["x1"]) / 2, c["y0"] + u(sh, 1.6)), S(_("Radier noyau e=", "Ensoleiramento núcleo e=") + num(c["h"])), 1.5, "c")
    cols = {p["node"]: p for p in f["pads"]}
    tb, th = f["ties"]
    n_ln = 0
    for (i, j), p in sorted(cols.items()):  # longrines entre semelles voisines, repérées LNn  b x h ht (Ai)
        for di, dj in ((1, 0), (0, 1)):
            q = cols.get((i + di, j + dj))
            if not q:
                continue
            n_ln += 1
            lab, sec = f"LN{n_ln:02d}", f"{cm(tb)}x{cm(th)}ht"
            if di:
                a0, a1 = p["x"] + p["B"] / 2, q["x"] - q["B"] / 2
                sh.rect("FOND", a0, p["y"] - tb / 2, a1, p["y"] + tb / 2, 0.25, None, dash="dashed")
                if tw(lab + sec, 1.6) + 3 <= (a1 - a0) * 1000 / sh.scale:
                    sh.text("TEXTE", ((a0 + a1) / 2 - u(sh, 0.5), p["y"] + tb / 2 + u(sh, 0.8)), S(lab), 1.7, "r", bold=True)
                    sh.text("TEXTE", ((a0 + a1) / 2 + u(sh, 0.5), p["y"] + tb / 2 + u(sh, 0.8)), S(sec), 1.35, "l")
            else:
                a0, a1 = p["y"] + p["B"] / 2, q["y"] - q["B"] / 2
                sh.rect("FOND", p["x"] - tb / 2, a0, p["x"] + tb / 2, a1, 0.25, None, dash="dashed")
                if tw(lab + sec, 1.6) + 3 <= (a1 - a0) * 1000 / sh.scale:
                    sh.text("TEXTE", (p["x"] - tb / 2 - u(sh, 0.8), (a0 + a1) / 2 - u(sh, 0.5)), S(lab), 1.7, "r", rot=90, bold=True)
                    sh.text("TEXTE", (p["x"] - tb / 2 - u(sh, 0.8), (a0 + a1) / 2 + u(sh, 0.5)), S(sec), 1.35, "l", rot=90)
    for p in f["pads"]:
        B = p["B"]
        x0, x1, y0, y1 = p["x"] - B / 2, p["x"] + B / 2, p["y"] - B / 2, p["y"] + B / 2
        sh.rect("FOND", x0, y0, x1, y1, 0.45, FOND)
        # repère  S n — B x B x h ht — (As) : arase supérieure de la semelle
        sh.text("TEXTE", (x1 + u(sh, 1.0), y1 - u(sh, 2.0)), S(p["name"]), 2.0, "l", bold=True)
        sh.text("TEXTE", (x1 + u(sh, 1.0), y1 - u(sh, 4.0)), S(f"{cm(B)}x{cm(B)}x{cm(p['h'])}ht"), 1.4, "l")
        sh.text("TEXTE", (x1 + u(sh, 1.0), y1 - u(sh, 5.9)), S(f"(As:{lev(z_as + p['h'])})"), 1.3, "l")
        if B * 1000 / sh.scale >= 12:            # cotes de la semelle par rapport aux axes
            chain_cm(sh, [x0, p["x"], x1], "x", y0 - u(sh, 3), 1.4)
            chain_cm(sh, [y0, p["y"], y1], "y", x0 - u(sh, 3), 1.4)
            sh.text("TEXTE", (p["x"], y0 + u(sh, 1.6)), S(mesh_txt(p["mesh"]) + " " + _("2 dir.", "2 dir.")), 1.3, "c")
    bas = r.get("basement")
    if bas:
        t = bas["t"]
        x0, x1, y0, y1 = m.gx[0], m.gx[-1], m.gy[0], m.gy[-1]
        for a_, b_, c_, d_ in ((x0 - t / 2, y0 - t / 2, x1 + t / 2, y0 + t / 2), (x0 - t / 2, y1 - t / 2, x1 + t / 2, y1 + t / 2),
                               (x0 - t / 2, y0 - t / 2, x0 + t / 2, y1 + t / 2), (x1 - t / 2, y0 - t / 2, x1 + t / 2, y1 + t / 2)):
            sh.rect("BA", a_, b_, c_, d_, 0.35, BA)
        sh.text("TEXTE", (x0 + m.L / 2, y0 + t / 2 + u(sh, 1.0)),
                S(_(f"Mur de sous-sol BA e={num(t)} sur semelle filante {num(bas['footing'][0])}×{num(bas['footing'][1])}",
                    f"Muro de cave BA e={num(t)} sobre sapata contínua {num(bas['footing'][0])}×{num(bas['footing'][1])}")), 1.5, "c")
    columns(sh, m, r, tags=False)
    cores(sh, m, cut=False)
    exe_dims(sh, m, r)
    sh.legend = [(k, S(v)) for k, v in (("COF_POTEAU", _("Poteau BA (amorce)", "Pilar BA (arranque)")),
                                         ("COF_VOILE", _("Voile / radier de noyau", "Parede / ensoleiramento do núcleo")))]
    sig = num(f["sigma_kpa"] / 1000, 2)
    _note(sh, *hypotheses(m, r),
          _(f"Contrainte admissible du sol : {sig} MPa" + (" (HYPOTHÈSE — à confirmer par l'étude G2)" if f["assumed"] else f" ({m.geo.get('source', 'étude de sol')})"),
            f"Tensão admissível do terreno: {sig} MPa" + (" (HIPÓTESE — a confirmar pelo estudo geotécnico)" if f["assumed"] else f" ({m.geo.get('source', 'estudo geotécnico')})")),
          _(f"Assise à {num(f['depth'])} m sous le terrain naturel ; béton de propreté 10 cm.", f"Cota de fundação a {num(f['depth'])} m abaixo do terreno natural; betão de limpeza 10 cm."),
          _(f"Béton {r['mat']['concrete']} XC2, enrobage 5 cm, aciers {r['mat']['steel']}.", f"Betão {r['mat']['concrete']} XC2, recobrimento 5 cm, aço {r['mat']['steel']}."),
          _(f"Semelles : côté B × B × hauteur (m), ferraillage inférieur dans les 2 directions (méthode des bielles).",
            f"Sapatas: lado B × B × altura (m), armadura inferior nas 2 direções (método das bielas)."),
          _(f"Longrines {num(tb)}×{num(th)} entre semelles : 4Ø16, cadres Ø8//0,20.", f"Vigas de fundação {num(tb)}×{num(th)} entre sapatas: 4Ø16, estribos Ø8//0,20."),
          (_("Semelles filantes à prévoir sous les files où les semelles se recouvrent.", "Sapatas contínuas a prever nos alinhamentos onde as sapatas se sobrepõem.") if f["strips"] else ""),
          (_("Radier général conseillé (semelles > 50 % de l'emprise).", "Ensoleiramento geral aconselhado (sapatas > 50 % da implantação).") if f["kind"] == "radier" else ""),
          _("Tableau des semelles : planche EST-T4.", "Quadro de sapatas: desenho EST-T4."),
          (_(f"Murs de sous-sol : H = {num(bas['H'])} m, poussée au repos K0 = {num(bas['K0'])}, surcharge {int(bas['q'])} kPa ; "
             f"aciers verticaux face intérieure {mesh_txt(bas['vert'])}, face terre {mesh_txt(bas['outer'])}, horizontaux {mesh_txt(bas['hor'])}.",
             f"Muros de cave: H = {num(bas['H'])} m, impulso em repouso K0 = {num(bas['K0'])}, sobrecarga {int(bas['q'])} kPa; "
             f"armadura vertical face interior {mesh_txt(bas['vert'])}, face terreno {mesh_txt(bas['outer'])}, horizontal {mesh_txt(bas['hor'])}.") if bas else ""),
          (_("Drainage périphérique + étanchéité des murs enterrés.", "Drenagem periférica + impermeabilização dos muros enterrados.") if bas else ""))
    return sh


def _slab_groups(r: dict) -> list[list[dict]]:
    groups = []
    for fl in r["floors"]:
        key = (round(fl["slab"].h, 3), fl["loads"]["use"],
               tuple((b["name"], b["b"], b["h"], tuple((s["bot"]["txt"], s["top_l"]["txt"], s["top_r"]["txt"], s["stirrups"]) for s in b["spans"])) for b in fl["beams"]),
               tuple((p["id"], mesh_txt(p["mesh_short"]), mesh_txt(p["mesh_long"])) for p in fl["panels"]))
        if groups and groups[-1][0] == key:
            groups[-1][1].append(fl)
        else:
            groups.append((key, [fl]))
    return [g for _k, g in groups]


def _group_name(g: list[dict]) -> str:
    if len(g) == 1:
        return g[0]["slab"].name
    return f"{g[0]['slab'].name} {_('à', 'a')} {g[-1]['slab'].name}"


def framing(m: Frame, r: dict, g: list[dict], code: str, e: dict) -> Sheet:
    """Plan de coffrage d'exécution : poutres grisées repérées (n°, b x h, arase inférieure), poteaux repérés et sectionnés,
    dalles avec bulle d'arase / épaisseur / type, sens de portée, diagonales de panneau, cotes en cm, réservations."""
    fl = g[0]
    s = fl["slab"]
    zs = ", ".join(("+" if x["slab"].z >= 0 else "") + num(x["slab"].z) for x in g)
    sh = _exe_sheet(m, code, _("Plan de coffrage — plancher haut ", "Planta de estrutura — laje ") + _group_name(g),
                    _(f"EXE · STR · COF — dalle pleine BA e={cm(s.h)} cm — niveaux finis {zs}",
                      f"EXE · EST · COF — laje maciça BA e={cm(s.h)} cm — cotas de acabamento {zs}"), "floor", s.id)
    grid(sh, m, dims=False)
    # balcons
    for bc in r.get("balconies") or []:
        if bc["levels"] and s.id not in bc["levels"]:
            continue
        if s.id == "COB":
            continue
        with _ctx(sh, m):
            x0, y0, x1, y1 = _balcony_rect(m, bc)
        if x1 - x0 < 0.3 or y1 - y0 < 0.3:
            continue
        sh.rect("BA", x0, y0, x1, y1, 0.35, None)
        sh.line("FOND_PLAN", (x0, y0), (x1, y1), 0.13)
        sh.line("FOND_PLAN", (x0, y1), (x1, y0), 0.13)
        c = ((x0 + x1) / 2, (y0 + y1) / 2)
        if (x1 - x0) * 1000 / sh.scale > 40 and (y1 - y0) * 1000 / sh.scale > 11:
            slab_bubble(sh, (c[0] - u(sh, 8), c[1]), s.z - 0.02, bc["h"], _("BAL", "VAR"))
        sh.text("TEXTE", (c[0] + u(sh, 14), c[1] - u(sh, 0.6)),
                S(_(f"Balcon console {cm(bc['depth'])} — chapeaux {mesh_txt(bc['top'])}", f"Varanda consola {cm(bc['depth'])} — sup. {mesh_txt(bc['top'])}")), 1.4, "l")
        dim_cm(sh, (x1, y0), (x1, y1), -u(sh, 3))
    outline(sh, m, 0.6)
    # demi-largeurs des poutres par file → nus des panneaux
    hb_x = {i: 0.0 for i in range(len(m.gx))}
    hb_y = {j: 0.0 for j in range(len(m.gy))}
    for bm in fl["beams"]:
        if bm["axis"] == "x":
            hb_y[bm["line"]] = max(hb_y[bm["line"]], bm["b"] / 2)
        else:
            hb_x[bm["line"]] = max(hb_x[bm["line"]], bm["b"] / 2)
    # poutres : bande grisée + repère n° / b x h ht / (Ai)
    z_brut = s.z - REV
    for bm in fl["beams"]:
        b, hgt = bm["b"], bm["h"]
        sec = f"{cm(b)}x{cm(hgt)}ht"
        ai = S(f"(Ai:{lev(z_brut - hgt)})")
        for k, _sp in enumerate(bm["spans"]):
            a0, a1 = bm["pos"][k], bm["pos"][k + 1]
            room = (a1 - a0 - 0.5) * 1000 / sh.scale
            lab = f"{bm['name']}.{k + 1}"
            full = tw(lab, 2.0) + tw(sec, 1.5) + 1.2 <= room
            if bm["axis"] == "x":
                y = m.gy[bm["line"]]
                sh.rect("BA", a0, y - b / 2, a1, y + b / 2, 0.3, GREY_BEAM)
                mid = (a0 + a1) / 2
                if full:
                    sh.text("TEXTE", (mid - u(sh, 0.6), y + b / 2 + u(sh, 0.8)), S(lab), 2.0, "r", bold=True)
                    sh.text("TEXTE", (mid + u(sh, 0.6), y + b / 2 + u(sh, 0.8)), S(sec), 1.5, "l")
                    sh.text("TEXTE", (mid, y - b / 2 - u(sh, 2.3)), ai, 1.35, "c")
                elif tw(lab, 1.8) <= room:
                    sh.text("TEXTE", (mid, y + b / 2 + u(sh, 0.8)), S(lab), 1.8, "c", bold=True)
            else:
                x = m.gx[bm["line"]]
                sh.rect("BA", x - b / 2, a0, x + b / 2, a1, 0.3, GREY_BEAM)
                mid = (a0 + a1) / 2
                if full:
                    sh.text("TEXTE", (x - b / 2 - u(sh, 0.8), mid - u(sh, 0.6)), S(lab), 2.0, "r", rot=90, bold=True)
                    sh.text("TEXTE", (x - b / 2 - u(sh, 0.8), mid + u(sh, 0.6)), S(sec), 1.5, "l", rot=90)
                    sh.text("TEXTE", (x + b / 2 + u(sh, 2.3), mid), ai, 1.35, "c", rot=90)
                elif tw(lab, 1.8) <= room:
                    sh.text("TEXTE", (x - b / 2 - u(sh, 0.8), mid), S(lab), 1.8, "c", rot=90, bold=True)
    # panneaux de dalle
    for p in fl["panels"]:
        i, j = p["i"], p["j"]
        x0, x1 = p["x0"] + hb_x.get(i, 0), p["x1"] - hb_x.get(i + 1, 0)
        y0, y1 = p["y0"] + hb_y.get(j, 0), p["y1"] - hb_y.get(j + 1, 0)
        wmm, hmm = (x1 - x0) * 1000 / sh.scale, (y1 - y0) * 1000 / sh.scale
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if p["core"]:                       # panneau avec noyau : la bulle va dans la plus grande partie libre
            core = next(c_ for c_ in m.cores if c_.get("id") == p["core"])
            parts = [(x0, y0, max(x0, core["x0"]), y1), (min(x1, core["x1"]), y0, x1, y1),
                     (x0, y0, x1, max(y0, core["y0"])), (x0, min(y1, core["y1"]), x1, y1)]
            bx0, by0, bx1, by1 = max(parts, key=lambda q: (q[2] - q[0]) * (q[3] - q[1]))
            cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
            wmm, hmm = (bx1 - bx0) * 1000 / sh.scale, (by1 - by0) * 1000 / sh.scale
        else:
            sh.line("FOND_PLAN", (x0, y0), (x1, y1), 0.12)
            sh.line("FOND_PLAN", (x0, y1), (x1, y0), 0.12)
        for ri in e["risers"]:
            if abs(ri["x"] - cx) < u(sh, 20) and -u(sh, 7) < ri["y"] - cy < u(sh, 7):
                cy = ri["y"] + (u(sh, 9) if ri["y"] <= (y0 + y1) / 2 else -u(sh, 9))
        # cotes intérieures (nu à nu) : en haut et à droite du panneau
        if not p["core"] and wmm >= 16 and hmm >= 12:
            dim_cm(sh, (x0, y0 + u(sh, 6)), (x1, y0 + u(sh, 6)), 0, 1.5)
            dim_cm(sh, (x0 + u(sh, 6), y0), (x0 + u(sh, 6), y1), 0, 1.5)
        short_x = p["dx"] <= p["dy"]
        sx = mesh_txt(p["mesh_short"] if short_x else p["mesh_long"])
        sy = mesh_txt(p["mesh_long"] if short_x else p["mesh_short"])
        tops = " / ".join(sorted({mesh_txt(t) for t in p["top"].values()}))
        l2 = _(f"inf. x {sx} · y {sy}", f"inf. x {sx} · y {sy}")
        l3 = _("chapeaux ", "sup. ") + tops
        if wmm >= 34 and hmm >= 26:
            R, wf = slab_bubble(sh, (cx - u(sh, 3), cy + u(sh, 4)), s.z, s.h)
            sh.text("PLANCHER", (cx - u(sh, 3) - R - u(sh, 1.0), cy + u(sh, 6.6)), S(p["id"]), 1.9, "r", bold=True)
            L = min(u(sh, 14), 0.35 * min(x1 - x0, y1 - y0))
            ay = cy + u(sh, 4) - R - u(sh, 3.2)
            if short_x:
                _arrow(sh, (cx - L / 2, ay), (cx + L / 2, ay))
            else:
                _arrow(sh, (cx, ay - L + u(sh, 1.5)), (cx, ay + u(sh, 1.5)))
                ay -= L - u(sh, 1.5)
            if wmm >= max(tw(l2, 1.35), tw(l3, 1.35)) + 4:
                sh.text("PLANCHER", (cx, ay - u(sh, 3.4)), S(l2), 1.35, "c")
                sh.text("PLANCHER", (cx, ay - u(sh, 5.6)), S(l3), 1.35, "c")
        elif wmm >= tw(p["id"], 1.6) and hmm >= 3:
            sh.text("PLANCHER", (cx, cy - u(sh, 0.6)), S(p["id"]), 1.6, "c", bold=True)
        elif hmm >= tw(p["id"], 1.6) and wmm >= 3:
            sh.text("PLANCHER", (cx + u(sh, 0.6), cy), S(p["id"]), 1.6, "c", bold=True, rot=90)
    cores(sh, m)
    columns(sh, m, r)
    # réservations / trémies (colonnes techniques)
    for ri in e["risers"]:
        k = ri["kind"]
        if k == "EP":
            continue
        d = ri["sections"][0]["d"] if ri["sections"] and "d" in ri["sections"][0] else None
        w = 0.30 if k != "ELEC" else 0.40
        a, b_ = (ri["x"] - w / 2, ri["y"] - w / 2), (ri["x"] + w / 2, ri["y"] + w / 2)
        sh.rect("RESA", a[0], a[1], b_[0], b_[1], 0.3, None)
        sh.line("RESA", a, b_, 0.15)
        sh.line("RESA", (a[0], b_[1]), (b_[0], a[1]), 0.15)
        sh.text("RESA", (b_[0] + u(sh, 0.6), ri["y"] + u(sh, 0.4)), S(ri["id"] + (" " + dn_txt(k, d) if d else "")), 1.3)
        sh.text("RESA", (b_[0] + u(sh, 0.6), ri["y"] - u(sh, 1.6)), S(f"{cm(w)}x{cm(w)}"), 1.25)
    exe_dims(sh, m, r)
    from . import coupes
    coupes.plan_marks(sh, m, r, s.id)
    cof_legend(sh)
    ld = fl["loads"]
    _note(sh, *hypotheses(m, r),
          _(f"Charges : G = {num(ld['g'])} kN/m² (dalle {num(ld['g_self'])} + revêtements {num(ld['g_fin'])} + cloisons {num(ld['g_part'])}), Q = {num(ld['q'])} kN/m² — {ld['label']}.",
            f"Ações: G = {num(ld['g'])} kN/m² (laje {num(ld['g_self'])} + revestimentos {num(ld['g_fin'])} + divisórias {num(ld['g_part'])}), Q = {num(ld['q'])} kN/m² — {ld['label']}."),
          _("Poutres : repère n°.travée, largeur x hauteur totale (ht, cm), Ai = arase inférieure. Ferraillage : planches EST-A et tableau EST-T2.",
            "Vigas: referência n.º.tramo, largura x altura total (cm), Ai = cota inferior. Armaduras: desenhos EST-A e quadro EST-T2."),
          _("Poteaux : repère et section (cm). Ferraillage : planche EST-P1, tableau EST-T1.", "Pilares: referência e secção (cm). Armaduras: desenho EST-P1, quadro EST-T1."),
          _("Dalles : aciers inférieurs dans les deux sens, chapeaux sur appuis sur 0,25 × portée (tableau EST-T3).",
            "Lajes: armadura inferior nas duas direções, superior nos apoios em 0,25 × vão (quadro EST-T3)."),
          _("Réservations (magenta) : à caler avec l'architecte et les lots techniques avant coulage.",
            "Negativos (magenta): a confirmar com a arquitetura e as especialidades antes da betonagem."),
          _("Étaiement : ne décoffrer qu'après 7 j minimum (contrôle de la résistance).", "Escoramento: descofrar só após 7 dias no mínimo (controlo da resistência)."))
    return sh


def section(m: Frame, r: dict) -> Sheet:
    i_cut = min(range(len(m.gx)), key=lambda i: abs(m.gx[i] - (m.gx[0] + m.L * 0.30)))
    z0 = m.levels[0].z
    ztop = r["floors"][-1]["slab"].z + 1.2
    dep = r["foundations"]["depth"]
    total_h = ztop - (z0 - dep - 1.0)
    for sc in SCALES:
        if (m.W + 7) * 1000 / sc <= (AREA[2] - AREA[0]) and (total_h + 3) * 1000 / sc <= (AREA[3] - AREA[1]):
            break
    w = (AREA[2] - AREA[0]) * sc / 1000
    hgt = (AREA[3] - AREA[1]) * sc / 1000
    sh = _new("EST-05", _(f"Coupe transversale sur la file {m.xl[i_cut]}", f"Corte transversal pelo alinhamento {m.xl[i_cut]}"), sc,
              (m.gy[0] - (w - m.W) / 2, (z0 - dep - 1.0) - (hgt - total_h) / 2), _("Ossature, niveaux et fondations", "Estrutura, cotas e fundações"), "coupe")
    Y0, Y1 = m.gy[0], m.gy[-1]
    bas = r.get("basement")
    zg = bas["ground_z"] if bas else z0
    sh.rect("TERRAIN", Y0 - 3.0, z0 - dep - 1.0, Y1 + 3.0, z0 - 0.02, 0.0, SOIL)
    if bas:
        t = bas["t"]
        sh.rect("TERRAIN", Y0 - 3.0, z0 - 0.02, Y0 - t / 2, zg, 0.0, SOIL)
        sh.rect("TERRAIN", Y1 + t / 2, z0 - 0.02, Y1 + 3.0, zg, 0.0, SOIL)
        for yy in (Y0, Y1):
            sh.rect("FOND", yy - bas["footing"][0] / 2, z0 - 0.15 - bas["footing"][1], yy + bas["footing"][0] / 2, z0 - 0.15, 0.35, FOND)
            sh.rect("BA", yy - t / 2, z0 - 0.15, yy + t / 2, zg, 0.35, BA, hatch="ba")
        sh.text("TEXTE", (Y0 + 0.4, z0 + (zg - z0) * 0.55), S(_(f"mur e={num(t)}", f"muro e={num(t)}")), 1.6)
    sh.line("TERRAIN", (Y0 - 3.0, zg), (Y0 - (bas["t"] / 2 if bas else 0), zg), 0.5)
    sh.line("TERRAIN", (Y1 + (bas["t"] / 2 if bas else 0), zg), (Y1 + 3.0, zg), 0.5)
    sh.text("TERRAIN", (Y0 - 2.9, zg + 0.15), S(_("terrain", "terreno")), 1.5)
    # dallage
    sh.rect("BA", Y0, z0 - 0.15, Y1, z0, 0.3, BA_LIGHT)
    pads = {p["node"]: p for p in r["foundations"]["pads"]}
    colsx = {c["node"]: c for c in r["columns"]}
    zf = z0 - dep
    for j, y in enumerate(m.gy):
        p = pads.get((i_cut, j))
        c = colsx.get((i_cut, j))
        if p:
            sh.rect("FOND", y - p["B"] / 2, zf - p["h"], y + p["B"] / 2, zf, 0.4, FOND)
            sh.rect("FOND", y - p["B"] / 2 - 0.05, zf - p["h"] - 0.10, y + p["B"] / 2 + 0.05, zf - p["h"], 0.2, (0.8, 0.8, 0.8))
            sh.text("TEXTE", (y, zf - p["h"] - u(sh, 4.5)), S(f"{p['name']} {num(p['B'])}×{num(p['h'])}"), 1.5, "c")
        if c:
            sh.rect("BA", y - c["h"] / 2, zf, y + c["h"] / 2, r["floors"][-1]["slab"].z - r["floors"][-1]["slab"].h, 0.35, BA)
    for fl in r["floors"]:
        s = fl["slab"]
        sh.rect("BA", Y0, s.z - s.h, Y1, s.z, 0.35, BA)
        for bm in fl["beams"]:
            if bm["axis"] != "x":
                continue
            y = m.gy[bm["line"]]
            sh.rect("BA", y - bm["b"] / 2, s.z - bm["h"], y + bm["b"] / 2, s.z, 0.35, BA)
        for bc in r.get("balconies") or []:
            if s.id == "COB" or (bc["levels"] and s.id not in bc["levels"]):
                continue
            if bc["side"] == "S":
                sh.rect("BA", Y0 - bc["depth"], s.z - bc["h"], Y0, s.z, 0.35, BA)
                sh.line("BA", (Y0 - bc["depth"] + 0.05, s.z), (Y0 - bc["depth"] + 0.05, s.z + 1.10), 0.3)
            elif bc["side"] == "N":
                sh.rect("BA", Y1, s.z - bc["h"], Y1 + bc["depth"], s.z, 0.35, BA)
                sh.line("BA", (Y1 + bc["depth"] - 0.05, s.z), (Y1 + bc["depth"] - 0.05, s.z + 1.10), 0.3)
        sh.level_mark((Y1 + 2.4, s.z), s.z - 0.0, S(s.name))
    top = r["floors"][-1]["slab"]
    sh.rect("BA", Y0, top.z, Y0 + 0.15, top.z + 1.0, 0.3, BA_LIGHT)
    sh.rect("BA", Y1 - 0.15, top.z, Y1, top.z + 1.0, 0.3, BA_LIGHT)
    sh.level_mark((Y1 + 2.4, z0), z0, S(m.levels[0].name))
    sh.level_mark((Y1 + 2.4, zf), zf, S(_("Assise des fondations", "Cota de fundação")))
    zs = [zf, z0] + [fl["slab"].z for fl in r["floors"]]
    sh.chain(zs, "y", Y0 - 2.6, size=1.9)
    sh.dim((Y0, zf), (Y0, top.z), 3.6, size=2.0)
    for y, lab in zip(m.gy, m.yl):
        sh.line("AXE", (y, zf - 1.0), (y, ztop + 0.6), 0.15, "axis")
        rr = u(sh, 3.0)
        sh.circle("AXE", (y, ztop + 0.6 + rr), rr, 0.3, (1, 1, 1))
        sh.text("AXE", (y, ztop + 0.6 + rr - u(sh, 1.0)), S(lab), 2.5, "c", bold=True)
    sh.chain(m.gy, "x", zf - 1.6, size=1.9)
    _note(sh, _("Coupe de principe de l'ossature (poteaux, poutres de la file, dalles, consoles) — cotes en m, niveaux bruts.",
                "Corte de princípio da estrutura (pilares, vigas do alinhamento, lajes, consolas) — cotas em m, cotas em tosco."),
          _("Hauteurs d'étage et niveaux : à recaler sur les coupes de l'architecte.", "Pés-direitos e cotas: a confirmar com os cortes da arquitetura."))
    return sh


def level_plan(m: Frame, lids: list[str], code: str, e: dict, r: dict) -> Sheet:
    lv = m.level(lids[0])
    name = lv.name if len(lids) == 1 else f"{m.level(lids[0]).name} {_('à', 'a')} {m.level(lids[-1]).name}"
    sh = _plan_sheet(m, code, _("Plan du niveau ", "Planta do ") + name,
                     _("Fractions, noyaux, colonnes techniques", "Frações, núcleos, colunas técnicas"), "level", lids[0])
    grid(sh, m, dims=True)
    units = m.units_on(lids[0])
    for k, un in enumerate(units):
        sh.rect("CLOISON", un.x0, un.y0, un.x1, un.y1, 0.45, UNIT_FILL[k % len(UNIT_FILL)])
        cx, cy = un.center
        sh.text("TITRE", (cx, cy + u(sh, 2.6)), S(un.name), 2.4, "c")
        sh.text("TEXTE", (cx, cy - u(sh, 0.6)), S(f"{un.typology} · {num(un.area, 1)} m²"), 1.8, "c")
    if not units:
        use = lv.use
        if use == "stationnement":
            n = int((m.footprint - sum((c["x1"] - c["x0"]) * (c["y1"] - c["y0"]) for c in m.cores)) / 25)
            sh.text("TITRE", (m.gx[0] + m.L / 2, m.gy[0] + m.W / 2 - u(sh, 18)),
                    S(_(f"Parking — env. {n} places (25 m²/place, circulation comprise)", f"Estacionamento — cerca de {n} lugares (25 m²/lugar, com circulação)")), 2.2, "c")
    outline(sh, m, 0.7)
    cores(sh, m)
    columns(sh, m, r, tags=False)
    for ri in e["risers"]:
        _riser_symbol(sh, ri)
    grid_dims(sh, m)
    _note(sh, _("Rectangles des fractions = enveloppes relevées sur les plans de l'architecte (surfaces indicatives).",
                "Retângulos das frações = envolventes relevadas nas plantas de arquitetura (áreas indicativas)."),
          (_("Niveaux identiques : ", "Pisos iguais: ") + ", ".join(m.level(x).name for x in lids)) if len(lids) > 1 else "")
    return sh


RISER_STYLE = {"AF": ("PLOMB_EF", (0.82, 0.90, 1.0)), "ECS": ("PLOMB_ECS", (1.0, 0.88, 0.88)), "EU": ("PLOMB_EV", (0.86, 0.78, 0.66)),
               "EP": ("PLOMB_EV", (0.92, 0.92, 0.92)), "ELEC": ("ELEC", (1.0, 0.92, 0.78)), "VENT": ("VMC_E", (0.92, 0.86, 0.96)),
               "GAZ": ("CHAUF_A", (1.0, 1.0, 0.8))}


PVC_OD = {90: 90, 100: 110, 125: 125, 150: 160, 200: 200}


def dn_txt(kind: str, d: int) -> str:
    """Chutes : diamètre extérieur PVC (PT : DN100 → Ø110 ; FR : Ø100). Eau : diamètre extérieur."""
    if kind == "EU":
        return f"Ø{PVC_OD.get(d, d) if _('fr', 'pt') == 'pt' else d}"
    return f"Ø{d}"


def _riser_symbol(sh: Sheet, ri: dict, label=True):
    layer, fill = RISER_STYLE.get(ri["kind"], ("TEXTE", (1, 1, 1)))
    rr = u(sh, 1.6)
    if ri["kind"] == "ELEC":
        sh.rect(layer, ri["x"] - rr, ri["y"] - rr, ri["x"] + rr, ri["y"] + rr, 0.35, fill)
    else:
        sh.circle(layer, (ri["x"], ri["y"]), rr, 0.35, fill)
    if label:
        sh.text(layer, (ri["x"] + rr + u(sh, 0.5), ri["y"] + u(sh, 0.6)), S(ri["id"]), 1.4, bold=True)


def networks(m: Frame, lids: list[str], code: str, e: dict, r: dict) -> Sheet:
    lv = m.level(lids[0])
    name = lv.name if len(lids) == 1 else f"{m.level(lids[0]).name} {_('à', 'a')} {m.level(lids[-1]).name}"
    sh = _plan_sheet(m, code, _("Réseaux d'eau et d'évacuation — ", "Redes de águas e esgotos — ") + name,
                     _("Colonnes montantes, chutes et branchements des fractions", "Colunas montantes, tubos de queda e ramais das frações"), "plumb", lids[0])
    grid(sh, m, dims=False)
    outline(sh, m, 0.5)
    cores(sh, m, cut=False)
    columns(sh, m, r, tags=False)
    units = {x["id"]: x for x in e["units"] if x["level"] == lids[0]}
    ris = {x["id"]: x for x in e["risers"]}
    for un in m.units_on(lids[0]):
        sh.rect("FOND_PLAN", un.x0, un.y0, un.x1, un.y1, 0.25, None)
        info = units.get(un.id)
        if not info:
            continue
        cx, cy = un.center
        sh.text("TEXTE", (cx, cy + u(sh, 5)), S(f"{un.name} ({un.typology})"), 1.9, "c", bold=True)
        sh.text("TEXTE", (cx, cy + u(sh, 2)), S(_(f"EF Ø{info['d_ef']} · Q = {num(info['q_ef'])} l/s", f"AF Ø{info['d_ef']} · Q = {num(info['q_ef'])} l/s")), 1.5, "c")
        sh.text("TEXTE", (cx, cy - u(sh, 0.6)), S(_(f"ECS Ø{info['d_ecs']} · EU ΣDU = {num(info['du'], 1)}", f"AQS Ø{info['d_ecs']} · esgoto ΣDU = {num(info['du'], 1)}")), 1.5, "c")
        for key, layer, dash, off in (("af", "PLOMB_EF", None, 0.0), ("eu", "PLOMB_EV", "dashed", 0.0), ("ecs", "PLOMB_ECS", None, 0.25)):
            rid = info.get(key)
            if not rid or rid not in ris:
                continue
            rx, ry = ris[rid]["x"], ris[rid]["y"]
            inside = un.x0 <= rx <= un.x1 and un.y0 <= ry <= un.y1
            if inside:          # colonne dans la fraction : branchement court vers le centre des pièces d'eau
                ex, ey = rx + (0.9 if rx < cx else -0.9), ry
            else:               # colonne en gaine commune : branchement jusqu'à la limite de la fraction (compteur)
                ex, ey = min(max(rx, un.x0), un.x1), min(max(ry, un.y0), un.y1)
            if key == "ecs":
                ey += off
            sh.poly(layer, [(rx, ry), (ex, ry), (ex, ey)], 0.45 if key != "eu" else 0.6, dash=dash)
            if key == "af" and not inside:
                sh.rect(layer, ex - u(sh, 1.0), ey - u(sh, 0.7), ex + u(sh, 1.0), ey + u(sh, 0.7), 0.3, (1, 1, 1))
                sh.text(layer, (ex, ey + u(sh, 1.4)), S(_(f"compteur Ø{info['d_ef']}", f"contador Ø{info['d_ef']}")), 1.3, "c")
    for ri in e["risers"]:
        _riser_symbol(sh, ri)
        if ri["sections"]:
            s0 = next((s for s in ri["sections"] if s["level"] == lids[0]), ri["sections"][0])
            txt = (dn_txt(ri["kind"], s0["d"]) if "d" in s0 else f"{s0['sec']} mm²")
            sh.text(RISER_STYLE.get(ri["kind"], ("TEXTE",))[0], (ri["x"] + u(sh, 2.2), ri["y"] - u(sh, 2.0)), S(txt), 1.3)
    sh.legend = [("LINE:PLOMB_EF::0.45", S(_("Eau froide (EF)", "Água fria (AF)"))), ("LINE:PLOMB_ECS::0.45", S(_("Eau chaude (ECS)", "Água quente (AQS)"))),
                 ("LINE:PLOMB_EV:dashed:0.6", S(_("Eaux usées (EU)", "Esgotos domésticos"))), ("CHUTE", S(_("Chute / colonne", "Tubo de queda / coluna")))]
    _note(sh, _("Débits de pointe : courbe de simultanéité habitation (EN 806-3) — diamètres extérieurs PEX/PPR, v ≤ 2 m/s en branchement.",
                "Caudais de cálculo: curva de simultaneidade habitação (EN 806-3) — diâmetros exteriores PEX/PPR, v ≤ 2 m/s nos ramais."),
          _("Tracés de principe : les cheminements réels suivent les gaines de l'architecte (plans d'exécution du plombier).",
            "Traçados de princípio: os percursos reais seguem as courettes da arquitetura (projeto de execução da especialidade)."),
          *[x for x in e["notes"]])
    return sh


def riser_diagram(m: Frame, e: dict, r: dict, code: str) -> Sheet:
    sh = _new(code, _("Schéma vertical des colonnes montantes", "Esquema vertical das colunas montantes"), 1000, (0, 0),
              _("Eau froide, eau chaude, eaux usées, électricité — par niveau", "Água fria, água quente, esgotos, eletricidade — por piso"), "plumb_riser")
    sh.dxf = False
    ris = [x for x in e["risers"] if x["kind"] in ("AF", "ECS", "EU", "ELEC") and x["sections"]]
    nl = len(m.levels)
    H = AREA[3] - AREA[1] - 30
    step = min(34.0, H / (nl + 1))
    y0 = 16.0
    zlev = {lv.id: y0 + k * step for k, lv in enumerate(m.levels)}
    xs = {}
    col_w = min(46.0, (AREA[2] - AREA[0] - 40) / max(len(ris), 1))
    for k, ri in enumerate(ris):
        xs[ri["id"]] = 34 + k * col_w
    for lv in m.levels:
        y = zlev[lv.id]
        sh.line("NIVEAU", (0, y), (AREA[2] - AREA[0] - 2, y), 0.2, "dashed")
        sh.text("TEXTE", (1, y + 1.2), S(lv.name), 2.0, bold=True)
        sh.text("TEXTE", (1, y - 2.6), S(("+" if lv.z >= 0 else "") + num(lv.z)), 1.6)
    ytop = y0 + nl * step
    sh.line("NIVEAU", (0, ytop), (AREA[2] - AREA[0] - 2, ytop), 0.3)
    sh.text("TEXTE", (1, ytop + 1.2), S(_("Toiture", "Cobertura")), 2.0, bold=True)
    units_by = {}
    for un in e["units"]:
        units_by.setdefault(un["level"], []).append(un)
    for ri in ris:
        x = xs[ri["id"]]
        layer = RISER_STYLE.get(ri["kind"], ("TEXTE",))[0]
        lvls = [s["level"] for s in ri["sections"]]
        ya, yb = zlev[lvls[0]], zlev[lvls[-1]] + step * 0.55
        if ri["kind"] == "EU":
            yb = ytop + 6
            sh.text(layer, (x + 1, ytop + 7), S(_("ventilation primaire", "ventilação primária")), 1.4)
        sh.line(layer, (x, ya - 6), (x, yb), 0.9 if ri["kind"] != "ELEC" else 0.7, "dashed" if ri["kind"] == "EU" else None)
        sh.text(layer, (x, ya - 11), S(ri["id"]), 2.0, "c", bold=True)
        base = {"AF": _("depuis compteur général / réseau public", "do contador geral / rede pública"),
                "ECS": _("depuis production collective", "da produção coletiva"),
                "EU": _("vers collecteur enterré → regard", "para coletor enterrado → câmara de ramal"),
                "ELEC": _("depuis coffret de coupure / comptage", "da portinhola / quadro de colunas")}[ri["kind"]]
        sh.text(layer, (x, ya - 14), S(base), 1.3, "c")
        for s in ri["sections"]:
            y = zlev[s["level"]]
            if ri["kind"] in ("AF", "ECS"):
                t = f"Ø{s['d']} · {num(s['q'])} l/s"
            elif ri["kind"] == "EU":
                t = f"{dn_txt('EU', s['d'])} · {num(s['q'])} l/s"
            else:
                t = f"{s['sec']} mm² · {int(round(s['I']))} A"
            sh.text(layer, (x - 1.2, y + step * 0.28), S(t), 1.4, "r", rot=0)
            for un in units_by.get(s["level"], []):
                key = {"AF": "af", "ECS": "ecs", "EU": "eu", "ELEC": "elec"}[ri["kind"]]
                if un.get(key) != ri["id"]:
                    continue
                k = [x_["id"] for x_ in units_by[s["level"]] if x_.get(key) == ri["id"]].index(un["id"])
                yy = y + step * 0.55 - k * 3.6
                sh.line(layer, (x, yy), (x + 8, yy), 0.45)
                lab = {"AF": f"{un['name']} Ø{un['d_ef']}", "ECS": f"{un['name']} Ø{un['d_ecs']}",
                       "EU": f"{un['name']} ΣDU {num(un['du'], 1)}", "ELEC": f"{un['name']} {num(un['kva'])} kVA"}[ri["kind"]]
                sh.text(layer, (x + 8.6, yy - 0.6), S(lab), 1.3)
    sh.legend = [("LINE:PLOMB_EF::0.9", S(_("Colonne eau froide", "Coluna de água fria"))), ("LINE:PLOMB_ECS::0.9", S(_("Colonne eau chaude", "Coluna de água quente"))),
                 ("LINE:PLOMB_EV:dashed:0.9", S(_("Chute eaux usées", "Tubo de queda de esgotos"))), ("LINE:ELEC::0.7", S(_("Colonne électrique", "Coluna montante elétrica")))]
    _note(sh, _("Diamètre de chaque tronçon = débit cumulé des fractions desservies au-dessus (eau) ou au-dessus et au niveau (chutes).",
                "Diâmetro de cada troço = caudal acumulado das frações servidas acima (água) ou acima e no piso (tubos de queda)."),
          _("Chutes : EN 12056-2 système I, K = 0,5, ventilation primaire prolongée en toiture ; WC → Ø100 minimum.",
            "Tubos de queda: EN 12056-2 sistema I, K = 0,5, ventilação primária prolongada à cobertura; sanitas → Ø110 (DN100) mínimo."),
          _("Colonne électrique : puissance par logement × coefficient de simultanéité (NF C 14-100), 400 V tri, cuivre.",
            "Coluna elétrica: potência por fração × coeficiente de simultaneidade (RTIEBT 803), 400 V trifásico, cobre."),
          _("Organes : vanne d'arrêt et clapet en pied de colonne, compteurs individuels en gaine palière ou batterie au RDC.",
            "Órgãos: válvula de seccionamento em pé de coluna, contadores individuais em courette de patamar ou bateria no piso 0."),
          *e["notes"])
    return sh


def all_sheets(m: Frame, r: dict, e: dict, t: dict | None = None) -> list[Sheet]:
    from . import details
    NAT.clear()
    out = [foundations(m, r)]
    groups = _slab_groups(r)
    for k, g in enumerate(groups):
        out.append(framing(m, r, g, f"EST-{k + 2:02d}", e))
    out.append(section(m, r))
    out[-1].code = f"EST-{len(groups) + 2:02d}"
    from . import coupes
    out += coupes.sheets(m, r)
    out += tables(m, r)
    out += details.beam_sheets(m, r)
    out += details.column_sheets(m, r)
    out += details.footing_sheets(m, r)
    # plans de niveaux / réseaux, regroupés par niveaux identiques
    lv_groups = []
    for lv in m.levels:
        key = (lv.use, tuple(sorted(m.storey_voids(lv.id))),
               tuple((un.name, un.typology, round(un.x0, 2), round(un.y0, 2), round(un.x1, 2), round(un.y1, 2)) for un in m.units_on(lv.id)))
        if lv_groups and lv_groups[-1][0] == key:
            lv_groups[-1][1].append(lv.id)
        else:
            lv_groups.append((key, [lv.id]))
    for k, (_key, lids) in enumerate(lv_groups):
        out.append(level_plan(m, lids, f"ARQ-{k + 1:02d}", e, r))
    n = 1
    for _key, lids in lv_groups:
        if m.units_on(lids[0]):
            out.append(networks(m, lids, f"RED-{n:02d}", e, r))
            n += 1
    if any(x["sections"] for x in e["risers"]):
        out.append(riser_diagram(m, e, r, f"RED-{n:02d}"))
        out += elec_table(m, e, f"ELE-01")
    try:                                   # plans d'exécution par logement type (moteurs électricité / plomberie / VMC éprouvés)
        from . import dwelling
        out += dwelling.sheets_for(m)
    except Exception:  # noqa: BLE001 — un logement atypique ne doit jamais faire échouer l'étude de l'immeuble
        import logging
        logging.getLogger(__name__).warning("bet_frame: plans par logement non produits", exc_info=True)
    out += details.thermal_sheets(m, t)
    out += details.hvac_plans(m, t, r)
    return out


# ================================================================ tableaux
def tables(m: Frame, r: dict) -> list[Sheet]:
    out = []
    # --- poteaux (types)
    types = {}
    for c in r["columns"]:
        key = (c["b"], c["h"], tuple((s["level"], s.get("txt"), s.get("ties")) for s in c["segs"]))
        types.setdefault(key, []).append(c)
    rws = []
    for t, (key, cs) in enumerate(sorted(types.items(), key=lambda kv: (-kv[0][0], kv[1][0]["name"]))):
        cmax = max(cs, key=lambda c: c["segs"][0]["NEd"])
        runs = []                                   # tronçons consécutifs de même ferraillage (du bas vers le haut)
        for sg in cmax["segs"]:
            sig = (sg.get("txt"), sg.get("ties"))
            if runs and runs[-1][0] == sig:
                runs[-1][1].append(sg)
            else:
                runs.append([sig, [sg]])
        for k, (_sig, segs) in enumerate(runs):
            s0 = segs[0]
            lv = s0["level_name"] if len(segs) == 1 else f"{segs[0]['level_name']} {_('à', 'a')} {segs[-1]['level_name']}"
            rws.append([f"P{t + 1}" if k == 0 else "", (", ".join(c["name"] for c in cs) if k == 0 else "")[:46],
                        f"{int(round(cs[0]['b'] * 100))}×{int(round(cs[0]['h'] * 100))}" if k == 0 else "", lv,
                        f"{int(round(max(x['NEd'] for x in segs)))}", num(max(x["nu"] for x in segs)), s0.get("txt", "—"), s0.get("ties", "—"),
                        s0.get("ties_crit", "—"), num(max(x.get("util", 0) for x in segs))])
    out += table_sheets("EST-T1", _("Tableau des poteaux", "Quadro de pilares"), _("Sections, efforts et ferraillages par tronçon", "Secções, esforços e armaduras por troço"),
                        [(_("Type", "Tipo"), 14), (_("Poteaux", "Pilares"), 78), (_("Section\n(cm)", "Secção\n(cm)"), 18), (_("Tronçons", "Troços"), 52),
                         ("NEd max\n(kN)", 20), ("ν", 12), (_("Aciers\nlongitudinaux", "Armadura\nlongitudinal"), 24), (_("Cadres\ncourants", "Cintas\ncorrente"), 22),
                         (_("Cadres zones\ncritiques", "Cintas zonas\ncríticas"), 24), (_("Taux\nM/MRd", "Taxa\nM/MRd"), 16)], rws, "table",
                        notes=[_("Flexion composée déviée (EN 1992-1-1 5.8.9), imperfections l0/400, second ordre par courbure nominale si λ > λlim.",
                                 "Flexão composta desviada (NP EN 1992-1-1 5.8.9), imperfeições l0/400, 2.ª ordem por curvatura nominal se λ > λlim."),
                               _("Moments : sous-portique (encastrement partiel des poutres de rive, charges d'exploitation alternées).",
                                 "Momentos: subpórtico (encastramento parcial das vigas de bordo, sobrecargas alternadas)."),
                               _("Zones critiques : 1,5 × la plus grande dimension en tête et en pied de chaque tronçon." if not r["mat"].get("dcm") else
                                 "Zones critiques (EN 1998-1 DCM) : max(hc ; lcl/6 ; 0,45 m) aux nœuds ; s ≤ min(b0/2 ; 175 ; 8 Øl) ; νd ≤ 0,65 ; 1 % ≤ ρl ≤ 4 %, une barre intermédiaire par face.",
                                 "Zonas críticas (NP EN 1998-1 DCM): max(hc; lcl/6; 0,45 m) junto aos nós; s ≤ min(b0/2; 175; 8 Øl); νd ≤ 0,65; 1 % ≤ ρl ≤ 4 %, um varão intermédio por face.")])
    # --- poutres
    groups_ = _slab_groups(r)
    for gi, g in enumerate(groups_):
        suf = chr(97 + gi) if len(groups_) > 1 else ""
        fl = g[0]
        rows = []
        for bm in fl["beams"]:
            for k, sp in enumerate(bm["spans"]):
                rows.append([f"{bm['name']}.{k + 1}", f"{int(round(bm['b'] * 100))}×{int(round(bm['h'] * 100))}", num(sp["L"]),
                             f"{int(round(sp['M_span']))}", sp["bot"]["txt"] + (" (2 lits)" if sp["bot"]["layers"] > 1 else ""),
                             f"{int(round(sp['M_left']))} / {int(round(sp['M_right']))}", f"{sp['top_l']['txt']} / {sp['top_r']['txt']}",
                             f"{int(round(sp['V']))}", sp["stirrups"], sp.get("stirrups_crit", sp["stirrups"]),
                             f"{num(sp['ld'], 1)} ≤ {num(sp['ld_lim'], 1)}"])
        out += table_sheets("EST-T2" + suf, _("Tableau des poutres — dalle ", "Quadro de vigas — laje ") + _group_name(g),
                            _("Poutres continues : moments ELU, aciers, cadres, flèche (l/d)", "Vigas contínuas: momentos ELU, armaduras, estribos, flecha (l/d)"),
                            [(_("Poutre", "Viga"), 22), ("b×h\n(cm)", 18), ("L\n(m)", 14), ("M+ ELU\n(kN·m)", 20), (_("Aciers\ninférieurs", "Armadura\ninferior"), 30),
                             ("M− g/d\n(kN·m)", 24), (_("Chapeaux\ngauche / droite", "Armadura sup.\nesq. / dir."), 42), ("VEd\n(kN)", 16),
                             (_("Cadres\n2 brins", "Estribos\n2 ramos"), 22), (_("Cadres zones\ncritiques", "Estribos zonas\ncríticas"), 24),
                             ("l/d ≤ lim", 24)], rows, "table",
                            notes=[_("Équation des trois moments, cas de charge alternés (1,35 G + 1,5 Q).", "Equação dos três momentos, casos de carga alternados (1,35 G + 1,5 Q)."),
                                   _("Charges des panneaux en triangles / trapèzes, façades et balcons sur les poutres de rive.",
                                     "Cargas dos painéis em triângulos / trapézios, fachadas e varandas nas vigas de bordo."),
                                   _("Effort tranchant : EN 1992-1-1 6.2, bielle variable (cot θ ≤ 2,5).", "Esforço transverso: NP EN 1992-1-1 6.2, biela variável (cot θ ≤ 2,5)."),
                                   _("Appuis de rive : chapeaux ≥ 15 % du moment en travée (9.2.1.2).", "Apoios de extremidade: armadura superior ≥ 15 % do momento a meio vão (9.2.1.2)."),
                                   _("Zones critiques (EN 1998-1 DCM) : lcr = h à chaque nu d'appui, s ≤ min(h/4 ; 24 Øw ; 225 ; 8 Øl), 1er cadre à 5 cm ; ρmin = 0,5 fctm/fyk, aciers comprimés ≥ 50 % des tendus.",
                                     "Zonas críticas (NP EN 1998-1 DCM): lcr = h junto a cada apoio, s ≤ min(h/4; 24 Øw; 225; 8 Øl), 1.º estribo a 5 cm; ρmin = 0,5 fctm/fyk, armadura comprimida ≥ 50 % da tracionada.")
                                   if r["mat"].get("dcm") else ""])
        # --- dalles
        rows = []
        for p in fl["panels"]:
            top = p["top"]
            rows.append([p["id"], f"{num(p['dx'])} × {num(p['dy'])}", num(fl["slab"].h), _("2 sens", "2 dir.") if p["two_way"] else _("1 sens", "1 dir."),
                         f"{num(p['Mtx'], 1)} / {num(p['Mty'], 1)}", mesh_txt(p["mesh_short"]), mesh_txt(p["mesh_long"]),
                         " ".join(f"{k}:{mesh_txt(v)}" for k, v in top.items()), f"{num(p['ld'], 1)} ≤ {num(p['ld_lim'], 1)}",
                         (_("noyau ", "núcleo ") + p["core"]) if p["core"] else ""])
        out += table_sheets("EST-T3" + suf, _("Tableau des dalles — ", "Quadro de lajes — ") + _group_name(g),
                            _("Panneaux de dalle pleine : moments, aciers inférieurs et chapeaux", "Painéis de laje maciça: momentos, armaduras inferiores e superiores"),
                            [(_("Panneau", "Painel"), 18), ("lx × ly (m)", 28), ("e (m)", 14), (_("Portée", "Funciona"), 16), ("Mx / My\n(kN·m/m)", 26),
                             (_("Inf. sens\ncourt", "Inf. vão\nmenor"), 24), (_("Inf. sens\nlong", "Inf. vão\nmaior"), 24),
                             (_("Chapeaux (O E S N)", "Superior (O E S N)"), 82), ("l/d ≤ lim", 26), ("", 20)], rows, "table",
                            notes=[_("Méthode des panneaux (μx, μy, ν = 0) avec continuité : travée 0,75 / 0,85 / 1,0 M0, appuis 0,5 M0 (continus) et 0,3 M0 (rive).",
                                     "Método dos painéis (μx, μy, ν = 0) com continuidade: vão 0,75 / 0,85 / 1,0 M0, apoios 0,5 M0 (contínuos) e 0,3 M0 (bordo)."),
                                   _("Flèche : EN 1992-1-1 7.4.2 (l/d) sur la petite portée ; espacements ≤ 2h (principal) et 3h (secondaire).",
                                     "Flecha: NP EN 1992-1-1 7.4.2 (l/d) no vão menor; espaçamentos ≤ 2h (principal) e 3h (secundário).")])
    # --- semelles
    f = r["foundations"]
    groups = {}
    for p in f["pads"]:
        groups.setdefault((p["B"], p["h"], mesh_txt(p["mesh"])), []).append(p)
    rows = []
    for k, ((B, h, ms), ps) in enumerate(sorted(groups.items(), key=lambda kv: -kv[0][0])):
        rows.append([f"S{k + 1}", ", ".join(p["name"] for p in ps)[:60], f"{num(B)} × {num(B)}", num(h), ms + _(" 2 sens", " 2 dir."),
                     f"{int(round(max(p['N'] for p in ps)))}", num(max(p["sigma"] for p in ps) / 1000, 3), str(len(ps))])
    out += table_sheets("EST-T4", _("Tableau des semelles", "Quadro de sapatas"), _("Dimensions, ferraillage et contraintes", "Dimensões, armaduras e tensões"),
                        [(_("Type", "Tipo"), 14), (_("Semelles", "Sapatas"), 92), ("B × B (m)", 26), ("h (m)", 16), (_("Aciers inférieurs", "Armadura inferior"), 40),
                         ("N ELS max\n(kN)", 22), ("σ (MPa)", 18), ("Nb", 12)], rows, "table",
                        notes=[_(f"σ admissible : {num(f['sigma_kpa'] / 1000, 2)} MPa ; poids propre de la semelle et des terres +10 %.",
                                 f"σ admissível: {num(f['sigma_kpa'] / 1000, 2)} MPa; peso próprio da sapata e terras +10 %."),
                               _("Hauteur ≥ (B − a)/4 + 5 cm (semelle rigide) ; aciers : As = NEd (B − a) / (8 d fyd).",
                                 "Altura ≥ (B − a)/4 + 5 cm (sapata rígida); armadura: As = NEd (B − a) / (8 d fyd).")])
    return out


def elec_table(m: Frame, e: dict, code: str) -> list[Sheet]:
    rows = []
    for un in e["units"]:
        rows.append([f"{un['name']}", m.level(un["level"]).name, un["typology"], num(un["area"], 1), num(un["kva"]),
                     _("mono 230 V" if un["kva"] <= 12 else "tri 400 V", "mono 230 V" if un["kva"] <= 13.8 else "tri 400 V"),
                     un.get("elec") or "—", f"Ø{un['d_ef']}", f"Ø{un['d_ecs']}", num(un["du"], 1), un.get("eu") or "—"])
    return table_sheets(code, _("Tableau des fractions — puissances et branchements", "Quadro de frações — potências e ramais"),
                        _("Électricité, eau froide, eau chaude, eaux usées par fraction", "Eletricidade, água fria, água quente e esgotos por fração"),
                        [(_("Fraction", "Fração"), 28), (_("Niveau", "Piso"), 30), (_("Typo.", "Tipol."), 14), ("S (m²)", 16), ("P (kVA)", 16),
                         (_("Alimentation", "Alimentação"), 24), (_("Colonne élec.", "Coluna elétr."), 24), (_("EF", "AF"), 14), (_("ECS", "AQS"), 14),
                         ("ΣDU (l/s)", 18), (_("Chute", "Tubo de queda"), 24)], rows, "elec_table",
                        notes=[_("Puissance par logement : 9 kVA (T1-T2), 12 kVA (T3 et +) — à ajuster avec le maître d'ouvrage.",
                                 "Potência por fração: 6,90 kVA (T0-T1), 10,35 kVA (T2-T3), 13,80 kVA (T4+) — a ajustar com o dono de obra.")])
