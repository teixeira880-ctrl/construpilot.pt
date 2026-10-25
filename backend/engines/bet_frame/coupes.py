"""Coupes de coffrage verticales (1:25) — comme le cahier de coupes d'un BET structure :
coupe de rive et coupe courante sur poutre de chaque plancher, balcon, voile de noyau, mur de sous-sol, semelle de chaque type.
Chaque coupe : béton coupé hachuré, revêtements, arases brutes « b » et niveaux finis « f », cotes en cm
(épaisseurs, retombées, hauteurs libres, entre-planchers), repère d'axe. Les repères C1, C2… sont reportés sur les plans de coffrage."""
from __future__ import annotations

from .calc import mesh_txt, num
from .lang import _
from .model import Frame
from .sheets import AREA, BA_LIGHT, REV, S, SOIL, _group_name, _new, _note, _slab_groups, cm, lev, tw

SCALE = 25
CELL_W = (AREA[2] - AREA[0]) / 2          # 2 coupes par planche A3
CELL_H = AREA[3] - AREA[1]
CONC = (0.88, 0.88, 0.89)
SL = 1.05                                 # demi-longueur de dalle représentée de part et d'autre de l'élément coupé (m)
FIN = (0.97, 0.94, 0.86)


def _u(mm: float, sc: int | None = None) -> float:
    return mm * (sc or SCALE) / 1000


# ------------------------------------------------------------------ inventaire des coupes (partagé avec les plans de coffrage)
def specs(m: Frame, r: dict) -> list[dict]:
    """Liste ordonnée des coupes : id C1…, nature, plancher, élément coupé. Déterministe (mêmes repères sur plans et coupes)."""
    out = []
    groups = _slab_groups(r)
    zs = sorted({fl["slab"].z for fl in r["floors"]})
    for g in groups:
        fl = g[0]
        s = fl["slab"]
        cand = [z for z in zs + [m.levels[0].z] if z < s.z - 1e-6]
        below = max(cand) if cand else None
        seen = set()
        for bm in fl["beams"]:
            n_lines = len(m.gy) if bm["axis"] == "x" else len(m.gx)
            rive = bm["line"] in (0, n_lines - 1)
            key = (round(bm["b"], 2), round(bm["h"], 2), rive)
            if key in seen:
                continue
            seen.add(key)
            k = max(range(len(bm["spans"])), key=lambda i: bm["pos"][i + 1] - bm["pos"][i])
            out.append({"kind": "beam", "slab": s, "group": g, "beam": bm, "span": k, "rive": rive, "z_below": below,
                        "out_neg": bm["line"] == 0})
        if s.id != "COB":
            for bc in r.get("balconies") or []:
                if (not bc["levels"] or s.id in bc["levels"]) and not any(o["kind"] == "balcony" and o["slab"] is s for o in out):
                    side = bc["side"]
                    ax, ln = ("x", 0 if side == "S" else len(m.gy) - 1) if side in ("S", "N") else ("y", 0 if side == "W" else len(m.gx) - 1)
                    eb = next((b_ for b_ in fl["beams"] if b_["axis"] == ax and b_["line"] == ln), None)
                    lab = (m.yl[ln] if ax == "x" else m.xl[ln])
                    out.append({"kind": "balcony", "slab": s, "group": g, "bc": bc, "z_below": below, "edge_beam": eb, "axis_lab": lab})
        if m.cores and below is not None and not any(o["kind"] == "core" for o in out):
            out.append({"kind": "core", "slab": s, "group": g, "core": m.cores[0], "z_below": below})
    if r.get("basement"):
        out.append({"kind": "basement", "bas": r["basement"]})
    seen = set()
    for p in sorted(r["foundations"]["pads"], key=lambda q: (-q["h"], -q["B"])):
        key = round(p["h"], 2)        # une coupe type par épaisseur de semelle (B variable → quadro/tableau EST-T4)
        if key not in seen:
            seen.add(key)
            grp = [q for q in r["foundations"]["pads"] if round(q["h"], 2) == key]
            out.append({"kind": "pad", "pad": p, "same": [q["name"] for q in grp],
                        "B_range": (min(q["B"] for q in grp), max(q["B"] for q in grp))})
    for i, o in enumerate(out, 1):
        o["id"] = f"C{i}"
    return out


# ------------------------------------------------------------------ cellule de dessin (coordonnées locales s, z → planche)
class Cell:
    def __init__(self, sh, k: int, s0: float, s1: float, z0: float, z1: float, span: int = 1):
        self.sh = sh
        W, H = _u(CELL_W), _u(CELL_H - 16)
        self.ox = k * W + span * W / 2 - (s0 + s1) / 2
        self.oy = H / 2 - (z0 + z1) / 2 + _u(2)
        self.W, self.H, self.k = W, H, k

    def p(self, s, z):
        return (s + self.ox, z + self.oy)

    def rect(self, layer, s0, z0, s1, z1, lw=0.35, fill=None, hatch=None, dash=None):
        a, b = self.p(s0, z0), self.p(s1, z1)
        self.sh.rect(layer, a[0], a[1], b[0], b[1], lw, fill, hatch, dash)

    def line(self, layer, a, b, lw=0.25, dash=None):
        self.sh.line(layer, self.p(*a), self.p(*b), lw, dash)

    def text(self, layer, a, s, size=1.8, anchor="l", rot=0.0, bold=False):
        self.sh.text(layer, self.p(*a), S(s), size, anchor, rot, bold)

    def vdim(self, s, za, zb, size=1.6):
        if zb - za >= 0.01:
            self.sh.dim(self.p(s, za), self.p(s, zb), 0, text=S(cm(zb - za)), size=size)

    def vchain(self, s, zs, size=1.6):
        q = []
        for v in sorted(zs):
            if not q or v - q[-1] >= 0.005:
                q.append(v)
        for a, b in zip(q, q[1:]):
            self.vdim(s, a, b, size)

    def hchain(self, z, ss, size=1.6):
        q = []
        for v in sorted(ss):
            if not q or v - q[-1] >= 0.005:
                q.append(v)
        for a, b in zip(q, q[1:]):
            self.sh.dim(self.p(a, z), self.p(b, z), 0, text=S(cm(b - a)), size=size)

    def level(self, s, z, label):
        """Repère de niveau : triangle pointé sur l'arase, valeur en m + b / f / As (au format du livrable)."""
        a = self.p(s, z)
        h, w = _u(2.0), _u(1.3)
        self.sh.poly("NIVEAU", [a, (a[0] - w, a[1] + h), (a[0] + w, a[1] + h)], 0.2, True, (0.05, 0.05, 0.05))
        txt = f"{lev(z)} {label}"
        self.sh.line("NIVEAU", (a[0] - w, a[1] + h), (a[0] + _u(2.2 + tw(txt, 1.7)), a[1] + h), 0.25)
        self.sh.text("NIVEAU", (a[0] + _u(1.8), a[1] + h + _u(0.6)), S(txt), 1.7, "l")

    def brk(self, s, z0, z1):
        """Ligne de coupure (zigzag) verticale en s, de z0 à z1."""
        zm, d = (z0 + z1) / 2, _u(1.2)
        pts = [self.p(s, z0 - _u(1)), self.p(s, zm - d), self.p(s + d, zm - d / 2), self.p(s - d, zm + d / 2), self.p(s, zm + d), self.p(s, z1 + _u(1))]
        self.sh.poly("BA", pts, 0.25)

    def hbrk(self, z, s0, s1):
        sm, d = (s0 + s1) / 2, _u(1.2)
        pts = [self.p(s0 - _u(1), z), self.p(sm - d, z), self.p(sm - d / 2, z + d), self.p(sm + d / 2, z - d), self.p(sm + d, z), self.p(s1 + _u(1), z)]
        self.sh.poly("BA", pts, 0.25)

    def axis(self, s, z_top, label):
        self.line("AXE", (s, z_top + _u(2)), (s, z_top - _u(40)), 0.18, "axis")
        c = self.p(s, z_top + _u(6.5))
        self.sh.circle("AXE", c, _u(3.6), 0.3, (1, 1, 1))
        self.sh.text("AXE", (c[0], c[1] - _u(1.1)), S(label), 2.6, "c", bold=True)

    def title(self, ident: str, txt: str, sub: str = ""):
        x = self.k * self.W + _u(4)
        y = _u(CELL_H - 7)
        self.sh.text("TITRE", (x, y), S(f"{ident} — {txt}"), 2.6, "l", bold=True)
        wl = _u(min(CELL_W - 10, tw(f"{ident} — {txt}", 2.9)))
        self.sh.line("TITRE", (x, y - _u(1.6)), (x + wl, y - _u(1.6)), 0.4)
        if sub:
            self.sh.text("TEXTE", (x, y - _u(5.2)), S(sub), 1.7, "l")


def _slab_part(c: Cell, s0: float, s1: float, z: float, hs: float, br0=True, br1=True, label=True):
    """Dalle coupée (béton hachuré) + revêtements, arase brute b / niveau fini f."""
    zb = z - REV
    c.rect("BA", s0, zb - hs, s1, zb, 0.4, CONC, "ba")
    c.rect("TEXTE", s0, zb, s1, z, 0.15, FIN)
    if br0:
        c.brk(s0, zb - hs, z)
    if br1:
        c.brk(s1, zb - hs, z)
    if label:
        c.level(s1 - _u(16), z, "f")
        c.level(s1 - _u(34), zb, "b")


# ------------------------------------------------------------------ coupes
def beam_cut(c: Cell, sp: dict, axis_lab: str):
    s, bm = sp["slab"], sp["beam"]
    b, h, hs, z = bm["b"], bm["h"], s.h, s.z
    zb = z - REV
    zl = sp["z_below"]
    neg = sp["rive"] and sp["out_neg"]
    pos = sp["rive"] and not sp["out_neg"]
    s0 = -b / 2 if neg else -1.05
    s1 = b / 2 if pos else 1.05
    c.axis(0.0, z, axis_lab)
    # plancher bas (dalle de l'étage inférieur), même épaisseur à défaut
    if zl is not None:
        _slab_part(c, s0, s1, zl, hs, br0=not neg, br1=not pos, label=False)
        c.level(s1 - _u(16), zl, "f")
    # dalle de part et d'autre + poutre (béton monolithe), revêtements continus
    if not neg:
        c.rect("BA", s0, zb - hs, -b / 2, zb, 0.4, CONC, "ba")
        c.brk(s0, zb - hs, z)
    if not pos:
        c.rect("BA", b / 2, zb - hs, s1, zb, 0.4, CONC, "ba")
        c.brk(s1, zb - hs, z)
    c.rect("BA", -b / 2, zb - h, b / 2, zb, 0.4, CONC, "ba")
    c.rect("TEXTE", s0, zb, s1, z, 0.15, FIN)
    c.level(s1 - _u(16), z, "f")
    c.level(s1 - _u(34), zb, "b")
    c.level(b / 2 + _u(3), zb - h, "b")
    side = _("Extérieur", "Exterior")
    if neg:
        c.text("TEXTE", (-b / 2 - _u(14), zb - h / 2), side, 1.8, "r")
        c.line("BA", (-b / 2, zb - h - _u(10)), (-b / 2, zb + _u(10)), 0.5)
    if pos:
        c.text("TEXTE", (b / 2 + _u(14), zb - h / 2), side, 1.8, "l")
        c.line("BA", (b / 2, zb - h - _u(10)), (b / 2, zb + _u(10)), 0.5)
    lab_x = (b / 2 + _u(3), "l") if not neg else (-b / 2 - _u(3), "r")
    c.text("TEXTE", (lab_x[0], zb - h - _u(5.5)), f"{bm['name']}.{sp['span'] + 1}  {cm(b)}x{cm(h)}ht", 2.0, lab_x[1], bold=True)
    c.text("TEXTE", (lab_x[0], zb - h - _u(9)), f"(Ai:{lev(zb - h)})", 1.6, lab_x[1])
    c.text("PLANCHER", ((b / 2 + s1) / 2 if not pos else (s0 - b / 2) / 2, zb - hs - _u(4)),
           _(f"Dalle pleine e={cm(hs)}", f"Laje maciça e={cm(hs)}"), 1.7, "c")
    # cotes
    c.hchain(zb - h - _u(14), [-b / 2, 0, b / 2])
    sr = s1 + _u(9)
    pts = [zb - hs, zb, z]
    if zl is not None:
        pts += [zl, zl - REV]
        c.vchain(sr, pts)
        c.vdim(sr + _u(8), zl, z, 1.8)                    # entre-planchers (fini à fini)
        c.vdim(-b / 2 - _u(8) if not neg else b / 2 + _u(8), zl, zb - h, 1.7)   # hauteur libre sous poutre
        hl = zb - hs - zl
        c.text("TEXTE", ((b / 2 + s1) / 2 if not pos else (s0 - b / 2) / 2, zl + hl / 2), _(f"HSP {cm(hl)}", f"PD livre {cm(hl)}"), 1.6, "c")
    else:
        c.vchain(sr, pts)
    c.vchain(-b / 2 - _u(4) if not neg else b / 2 + _u(4), [zb - h, zb - hs, zb])
    return _("Coupe sur poutre de rive" if sp["rive"] else "Coupe sur poutre courante",
             "Corte por viga de bordadura" if sp["rive"] else "Corte por viga corrente")


def balcony_cut(c: Cell, sp: dict, axis_lab: str):
    s, bc = sp["slab"], sp["bc"]
    hs, z = s.h, s.z
    zb = z - REV
    d, hb = bc["depth"], bc["h"]
    bm = sp.get("edge_beam")
    bb, bh = (bm["b"], bm["h"]) if bm else (0.0, hs)
    zbal = z - 0.02                                         # ressaut de 2 cm au seuil
    c.axis(0.0, z, axis_lab)
    c.rect("BA", bb / 2, zb - hs, SL, zb, 0.4, CONC, "ba")
    c.brk(SL, zb - hs, z)
    c.rect("TEXTE", bb / 2 if bm else 0.0, zb, SL, z, 0.15, FIN)
    if bm:                                                  # poutre de rive sous le seuil
        c.rect("BA", -bb / 2, zb - bh, bb / 2, zb, 0.4, CONC, "ba")
        c.rect("TEXTE", -bb / 2, zb, bb / 2, z, 0.15, FIN)
        c.text("TEXTE", (bb / 2 + _u(3), zb - bh - _u(5)), f"{bm['name']}  {cm(bb)}x{cm(bh)}ht", 1.8, "l", bold=True)
        c.level(bb / 2 + _u(3), zb - bh, "b")
    c.level(SL - _u(16), z, "f")
    c.level(SL - _u(34), zb, "b")
    c.rect("BA", -d, zbal - REV - hb, -bb / 2, zbal - REV, 0.45, CONC, "ba")
    c.rect("TEXTE", -d, zbal - REV, -bb / 2, zbal, 0.15, FIN)
    c.line("BA", (-d + _u(1.6), zbal - REV - hb), (-d + _u(1.6), zbal - REV - hb + _u(0.8)), 0.3)   # goutte d'eau
    c.text("TEXTE", (-d, zbal - REV - hb - _u(3.5)), _("goutte d'eau", "pingadeira"), 1.4, "l")
    c.level(-d + _u(4), zbal, "f")
    c.level(-d / 2, zbal - REV, "b")
    c.text("PLANCHER", (-(d + bb / 2) / 2, zbal - REV - hb - _u(4)), _(f"Balcon e={cm(hb)}", f"Varanda e={cm(hb)}"), 1.7, "c")
    c.text("TEXTE", (-(d + bb / 2) / 2, zbal - REV - hb - _u(8.5)), _(f"Chapeaux {mesh_txt(bc['top'])} ancrés dans la dalle",
                                                                 f"Armadura superior {mesh_txt(bc['top'])} amarrada na laje"), 1.5, "c")
    c.text("TEXTE", (bb / 2 + _u(3), zb - bh - _u(13)), _("Rupteur thermique selon étude thermique", "Corte térmico segundo o estudo térmico"), 1.4, "l")
    c.hchain(min(zb - bh, zbal - REV - hb) - _u(16), [-d, -bb / 2, bb / 2])
    c.vchain(-d - _u(6), [zbal - REV - hb, zbal - REV, zbal])
    c.vchain(SL + _u(8), [zb - bh, zb - hs, zb, z])
    return _("Coupe sur balcon en console", "Corte pela varanda em consola")


def core_cut(c: Cell, sp: dict, axis_lab: str):
    s, core = sp["slab"], sp["core"]
    t, hs, z, zl = core["wall"], s.h, s.z, sp["z_below"]
    zb = z - REV
    c.axis(0.0, z, axis_lab)
    _slab_part(c, t / 2, SL, z, hs, br0=False)
    _slab_part(c, t / 2, SL, zl, hs, br0=False, label=False)
    c.rect("BA", -t / 2, zl - REV - hs - 0.25, t / 2, zb, 0.5, CONC, "ba")
    c.hbrk(zl - REV - hs - 0.25, -t / 2, t / 2)
    c.text("TEXTE", (-t / 2 - _u(3), (zl + zb) / 2), _(f"Voile BA e={cm(t)} (noyau)", f"Parede BA e={cm(t)} (núcleo)"), 1.7, "r", rot=0)
    c.text("TEXTE", (-t / 2 - _u(3), (zl + zb) / 2 - _u(4)), _("Intérieur noyau", "Interior do núcleo"), 1.5, "r")
    c.level(SL - _u(16), zl, "f")
    c.hchain(zl - REV - hs - _u(10), [-t / 2, t / 2])
    c.vchain(SL + _u(9), [zl - REV - hs, zl - REV, zl, zb - hs, zb, z])
    c.vdim(SL + _u(17), zl, z, 1.8)
    return _("Coupe sur voile de noyau", "Corte pela parede do núcleo")


def basement_cut(c: Cell, sp: dict, m: Frame, r: dict, axis_lab: str):
    bas = sp["bas"]
    t, H, zg = bas["t"], bas["H"], bas["ground_z"]
    z0 = m.levels[0].z
    fb, fh = bas["footing"]
    s1 = r["floors"][0]["slab"]
    zt = s1.z
    zf = z0 - 0.15 - fh                                      # assise de la semelle filante sous le dallage
    c.axis(0.0, zt, axis_lab)
    c.rect("TERRAIN", -1.0, zf - 0.25, -t / 2, zg, 0.0, SOIL)
    c.rect("TERRAIN", -t / 2, zf - 0.25, SL, z0 - 0.15, 0.0, SOIL)
    c.rect("BA", -t / 2 - (fb - t) / 2, zf, t / 2 + (fb - t) / 2, zf + fh, 0.45, CONC, "ba")
    c.rect("BA", -t / 2, zf + fh, t / 2, zt - REV, 0.5, CONC, "ba")
    _slab_part(c, t / 2, SL, zt, s1.h, br0=False)
    c.rect("BA", t / 2, z0 - 0.15, SL, z0 - REV, 0.35, CONC, "ba")
    c.rect("TEXTE", t / 2, z0 - REV, SL, z0, 0.15, FIN)
    c.brk(SL, z0 - 0.15, z0)
    c.level(-0.8, zg, "TN")
    c.level(SL - _u(16), z0, "f")
    c.level(t / 2 + (fb - t) / 2 + _u(2), zf, "b")
    c.text("TEXTE", (-t / 2 - _u(3), (zf + zg) / 2), _("Terre", "Terreno"), 1.6, "r")
    c.text("TEXTE", (-t / 2 - _u(3), (zf + zg) / 2 - _u(4)), _("drain + étanchéité", "dreno + impermeabilização"), 1.4, "r")
    c.text("TEXTE", (t / 2 + _u(3), (z0 + zt) / 2), _(f"Mur BA e={cm(t)}", f"Muro BA e={cm(t)}"), 1.8, "l", bold=True)
    c.text("TEXTE", (t / 2 + _u(3), (z0 + zt) / 2 - _u(4)), _(f"vert. int. {mesh_txt(bas['vert'])} · ext. {mesh_txt(bas['outer'])}",
                                                              f"vert. int. {mesh_txt(bas['vert'])} · ext. {mesh_txt(bas['outer'])}"), 1.5, "l")
    c.text("TEXTE", (fb / 2 + _u(3), z0 - 0.15 - _u(4)), _("Dallage e=15 sur hérisson", "Laje térrea e=15 sobre enrocamento"), 1.5, "l")
    c.hchain(zf - _u(6), [-fb / 2, -t / 2, t / 2, fb / 2])
    c.vchain(SL + _u(9), [zf, zf + fh, z0 - 0.15, z0, zt - REV - s1.h, zt - REV, zt])
    c.vdim(SL + _u(17), z0, zt, 1.8)
    return _("Coupe sur mur de sous-sol", "Corte pelo muro de cave")


def pad_cut(c: Cell, sp: dict, m: Frame, r: dict, axis_lab: str):
    p = sp["pad"]
    f = r["foundations"]
    B, hp = p["B"], p["h"]
    z0 = m.levels[0].z
    za = z0 - f["depth"]
    col = next((q for q in r["columns"] if abs(q["x"] - p["x"]) < 1e-6 and abs(q["y"] - p["y"]) < 1e-6), None)
    cb = col["b"] if col else 0.30
    tb, th = f["ties"]
    top = z0 + 0.9
    c.axis(0.0, top, axis_lab)
    c.rect("TERRAIN", -B / 2 - 0.35, za - 0.35, B / 2 + 0.6, z0 - 0.15, 0.0, SOIL)
    c.rect("BA", -B / 2 - 0.05, za - 0.10, B / 2 + 0.05, za, 0.25, (0.93, 0.93, 0.93))       # béton de propreté
    c.rect("BA", -B / 2, za, B / 2, za + hp, 0.5, CONC, "ba")
    c.rect("BA", B / 2, za + hp - th, B / 2 + 0.6, za + hp, 0.4, CONC, "ba")                # longrine
    c.brk(B / 2 + 0.6, za + hp - th, za + hp)
    c.rect("BA", -B / 2 - 0.35, z0 - 0.15, B / 2 + 0.6, z0 - REV, 0.35, CONC, "ba")          # dallage
    c.rect("TEXTE", -B / 2 - 0.35, z0 - REV, B / 2 + 0.6, z0, 0.15, FIN)
    c.rect("BA", -cb / 2, za + hp, cb / 2, top, 0.5, CONC, "ba")                            # poteau (traverse le dallage)
    c.hbrk(top, -cb / 2, cb / 2)
    c.level(B / 2 + 0.6 - _u(14), z0, "f")
    c.level(-B / 2 - _u(1), za + hp, "As")
    c.level(B / 2 + _u(2), za, "b")
    c.text("TEXTE", (-B / 2 - _u(2), za + hp / 2 - _u(0.7)), f"{p['name']}  {cm(B)}x{cm(B)}x{cm(hp)}ht", 2.0, "r", bold=True)
    others = [n for n in sp["same"] if n != p["name"]]
    b0, b1 = sp.get("B_range") or (B, B)
    if others:
        c.text("TEXTE", (-B / 2 - _u(2), za + hp / 2 - _u(4.2)), _("idem ", "idem ") + ", ".join(others[:6]) + ("…" if len(others) > 6 else ""), 1.5, "r")
    if b1 - b0 > 0.01:
        c.text("TEXTE", (-B / 2 - _u(2), za + hp / 2 - _u(7.4)),
               _(f"B = {cm(b0)} à {cm(b1)} : voir tableau EST-T4", f"B = {cm(b0)} a {cm(b1)}: ver quadro EST-T4"), 1.5, "r")
    c.text("TEXTE", (0.0, za + _u(2)), mesh_txt(p["mesh"]) + _(" 2 dir. (nappe inf.)", " 2 dir. (malha inf.)"), 1.5, "c")
    if col:
        c.text("TEXTE", (cb / 2 + _u(2), top - _u(6)), f"{col['name']} {cm(col['b'])}x{cm(col['h'])}", 1.8, "l", bold=True)
    c.text("TEXTE", (B / 2 + 0.3, za + hp + _u(2)), f"LN {cm(tb)}x{cm(th)}ht", 1.5, "c")
    c.text("TEXTE", (B / 2 + 0.3, za - _u(5)), _(f"σadm {num(f['sigma_kpa'] / 1000, 2)} MPa", f"σadm {num(f['sigma_kpa'] / 1000, 2)} MPa"), 1.5, "c")
    c.hchain(za - 0.10 - _u(7), [-B / 2, -cb / 2, cb / 2, B / 2])
    c.hchain(za - 0.10 - _u(13), [-B / 2, B / 2], 1.8)
    c.vchain(B / 2 + 0.6 + _u(9), [za - 0.10, za, za + hp - th, za + hp, z0 - 0.15, z0])
    c.vdim(B / 2 + 0.6 + _u(17), za, z0, 1.8)
    return _("Coupe sur semelle isolée", "Corte pela sapata isolada")


def _bbox(sp: dict, m: Frame, r: dict):
    """Encombrement (s0, s1, z0, z1) d'une coupe, cotes comprises."""
    e = 0.45
    if sp["kind"] == "beam":
        s, bm = sp["slab"], sp["beam"]
        zb = s.z - REV
        zl = sp["z_below"]
        lo = (zl - REV - s.h) if zl is not None else zb - bm["h"] - _u(20)
        return -1.05 - e, 1.05 + e, min(lo, zb - bm["h"] - _u(20)) - _u(4), s.z + _u(12)
    if sp["kind"] == "balcony":
        s, bc = sp["slab"], sp["bc"]
        bh = sp["edge_beam"]["h"] if sp.get("edge_beam") else s.h
        return -bc["depth"] - e, SL + e, s.z - REV - max(bh, bc["h"]) - _u(24), s.z + _u(12)
    if sp["kind"] == "core":
        s = sp["slab"]
        return -0.9 - e, SL + e, sp["z_below"] - REV - s.h - 0.25 - _u(14), s.z + _u(12)
    if sp["kind"] == "basement":
        bas = sp["bas"]
        z0 = m.levels[0].z
        return -1.0 - e, SL + e, z0 - 0.15 - bas["footing"][1] - 0.25 - _u(10), r["floors"][0]["slab"].z + _u(12)
    p = sp["pad"]
    z0 = m.levels[0].z
    za = z0 - r["foundations"]["depth"]
    return -p["B"] / 2 - 0.35 - e, p["B"] / 2 + 0.6 + e, za - 0.45 - _u(16), z0 + 0.9 + _u(12)


def _scale_for(bb, cells: int = 1) -> int:
    for sc in (25, 50, 75, 100):
        if (bb[1] - bb[0]) * 1000 / sc <= CELL_W * cells - 6 and (bb[3] - bb[2]) * 1000 / sc <= CELL_H - 18:
            return sc
    return 100


def layout(m: Frame, r: dict, sp_all: list[dict]) -> list[tuple[int, list[dict]]]:
    """Planches : deux coupes côte à côte si chacune tient au 1:25 (ou 1:20), sinon une coupe sur toute la planche."""
    pages, cur = [], []
    for sp in sp_all:
        half = _scale_for(_bbox(sp, m, r), 1) <= (50 if sp["kind"] in ("pad", "basement") else 25)   # semelles : 1:50 suffit, deux par planche
        if half:
            if cur and (cur[0]["kind"] in ("pad", "basement")) != (sp["kind"] in ("pad", "basement")):
                pages.append(cur)       # pas de coupe de poutre au 1:50 à côté d'une semelle
                cur = []
            cur.append(sp)
            if len(cur) == 2:
                pages.append(cur)
                cur = []
        else:
            if cur:
                pages.append(cur)
                cur = []
            pages.append([sp])
    if cur:
        pages.append(cur)
    out = []
    for pg in pages:
        cells = 1 if len(pg) == 2 else 2
        out.append((max(_scale_for(_bbox(sp, m, r), cells) for sp in pg), pg))
    return out


def _kind_txt(sp: dict) -> str:
    return {"beam": _("poutre de rive" if sp.get("rive") else "poutre courante", "viga de bordadura" if sp.get("rive") else "viga corrente"),
            "balcony": _("balcon", "varanda"), "core": _("voile de noyau", "parede do núcleo"),
            "basement": _("mur de sous-sol", "muro de cave"), "pad": _("semelle isolée", "sapata isolada")}[sp["kind"]]


def _where(sp: dict) -> str:
    if sp["kind"] in ("beam", "balcony", "core"):
        el = f" — {sp['beam']['name']}.{sp['span'] + 1} {cm(sp['beam']['b'])}x{cm(sp['beam']['h'])}" if sp["kind"] == "beam" else ""
        return _("Plancher haut ", "Laje ") + _group_name(sp["group"]) + el
    if sp["kind"] == "pad":
        return ", ".join(sp["same"][:8]) + ("…" if len(sp["same"]) > 8 else "")
    return _("Périphérie", "Periferia")


def sheets(m: Frame, r: dict) -> list:
    from .sheets import table_sheets
    sp_all = specs(m, r)
    pages = layout(m, r, sp_all)
    where = {sp["id"]: f"EST-C{n + 1:02d}" for n, (_sc, pg) in enumerate(pages) for sp in pg}
    rows = [[sp["id"], _kind_txt(sp), _where(sp), where[sp["id"]]] for sp in sp_all]
    out = table_sheets("EST-C00", _("Nomenclature des coupes de coffrage", "Lista dos cortes de cofragem"),
                       _("Cahier de coupes verticales — repères reportés sur les plans de coffrage", "Caderno de cortes verticais — referências nas plantas de cofragem"),
                       [(_("Coupe", "Corte"), 22), (_("Élément coupé", "Elemento cortado"), 60), (_("Plancher / repères", "Laje / referências"), 150), (_("Planche", "Desenho"), 30)],
                       rows, "coupe")
    for k, (sc, pair) in enumerate(pages):
        global SCALE
        prev, SCALE = SCALE, sc
        try:
            ids = " · ".join(sp["id"] for sp in pair)
            sh = _new(f"EST-C{k + 1:02d}", _("Coupes de coffrage ", "Cortes de cofragem ") + ids,
                      sc, (0.0, 0.0), _(f"EXE · STR · COF — coupes verticales 1:{sc}, cotes en cm, niveaux en m",
                                        f"EXE · EST · COF — cortes verticais 1:{sc}, cotas em cm, níveis em m"), "coupe")
            for i, sp in enumerate(pair):
                bb = _bbox(sp, m, r)
                c = Cell(sh, i, *bb, span=1 if len(pair) == 2 else 2)
                lab = {"beam": lambda: m.yl[sp["beam"]["line"]] if sp["beam"]["axis"] == "x" else m.xl[sp["beam"]["line"]]}.get(sp["kind"], lambda: "")()
                if sp["kind"] == "beam":
                    t = beam_cut(c, sp, lab)
                    sub = _("Plancher haut ", "Laje ") + _group_name(sp["group"]) + f" — {sp['beam']['name']}.{sp['span'] + 1}"
                elif sp["kind"] == "balcony":
                    t = balcony_cut(c, sp, sp.get("axis_lab") or "")
                    sub = _("Plancher haut ", "Laje ") + _group_name(sp["group"]) + _(f" — façade {sp['bc']['side']}", f" — fachada {sp['bc']['side']}")
                elif sp["kind"] == "core":
                    t = core_cut(c, sp, sp["core"].get("id") or "N")
                    sub = _("Plancher haut ", "Laje ") + _group_name(sp["group"]) + " — " + str(sp["core"].get("label") or "")
                elif sp["kind"] == "basement":
                    t = basement_cut(c, sp, m, r, m.yl[0])
                    sub = _("Périphérie du sous-sol", "Periferia da cave")
                else:
                    p = sp["pad"]
                    near = min(range(len(m.gx)), key=lambda q: abs(m.gx[q] - p["x"]))
                    t = pad_cut(c, sp, m, r, m.xl[near])
                    sub = _("Semelle ", "Sapata ") + p["name"] + (_(" (type)", " (tipo)") if len(sp["same"]) > 1 else "")
                c.title(sp["id"], t, sub)
            if len(pair) == 2:
                sh.line("TEXTE", (_u(CELL_W), _u(4)), (_u(CELL_W), _u(CELL_H - 2)), 0.2)
            _note(sh,
                  _("Cotes en cm, niveaux en m. b = arase brute, f = niveau fini (5 cm de revêtements), As = arase supérieure de fondation.",
                    "Cotas em cm, níveis em m. b = cota bruta, f = cota de acabamento (5 cm de revestimentos), As = cota superior da fundação."),
                  _("Béton coupé hachuré ; revêtements en jaune pâle. Repères de coupe reportés sur les plans de coffrage EST-01 à EST-0n.",
                    "Betão cortado a tracejado; revestimentos a amarelo-pálido. Referências dos cortes indicadas nas plantas EST-01 a EST-0n."),
                  _("HSP = hauteur sous plafond brute (sous dalle) ; entre-planchers de fini à fini.",
                    "PD livre = pé-direito bruto (sob a laje); entre pisos de acabamento a acabamento."),
                  _("Ferraillage : planches EST-A (poutres), EST-P (poteaux), EST-F (semelles) et tableaux EST-T.",
                    "Armaduras: desenhos EST-A (vigas), EST-P (pilares), EST-F (sapatas) e quadros EST-T."))
            out.append(sh)
        finally:
            SCALE = prev
    return out


def plan_marks(sh, m: Frame, r: dict, slab_id: str):
    """Repères de coupe (trait mixte épais + bulles C n) sur le plan de coffrage du plancher."""
    from .sheets import u
    for sp in specs(m, r):
        if sp["kind"] != "beam" or sp["slab"].id != slab_id:
            continue
        bm, k = sp["beam"], sp["span"]
        a = bm["pos"][k] + 0.62 * (bm["pos"][k + 1] - bm["pos"][k])
        L = bm["b"] / 2 + u(sh, 9)
        if bm["axis"] == "x":
            y = m.gy[bm["line"]]
            p0, p1 = (a, y - L), (a, y + L)
        else:
            x = m.gx[bm["line"]]
            p0, p1 = (x - L, a), (x + L, a)
        sh.line("TITRE", p0, p1, 0.6, "axis")
        for pp in (p0, p1):
            sh.circle("TITRE", pp, u(sh, 2.6), 0.35, (1, 1, 1))
            sh.text("TITRE", (pp[0], pp[1] - u(sh, 0.8)), S(sp["id"]), 1.8, "c", bold=True)
