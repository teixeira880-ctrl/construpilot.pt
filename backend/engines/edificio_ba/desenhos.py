"""Desenhos de estrutura do estudo prévio — folhas A3 à escala (PT / FR) : fundações, lajes, piso-tipo, cobertura, quadros e corte.

Geometria, eixos, cotas e etiquetas gerados a partir do modelo e dos resultados ; escala escolhida para caber na folha.
API orientada a objetos do matplotlib (sem pyplot) : seguro em servidor.
"""
from __future__ import annotations

import math

from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.patches import Circle, Polygon, Rectangle

from . import estrutura as ES
from .textos import fmt as f2

MM = 1 / 25.4
INK, GREY, BLUE, RED, ORANGE, GREEN = "#1d2422", "#7a7a76", "#2a78d6", "#c8453c", "#eb6834", "#336a3a"
BRAND = "#17473f"
SCALES = [50, 75, 100, 125, 150, 200, 250, 300]
AREA = (22, 62, 398, 282)        # zona útil de desenho (mm) acima da faixa de notas


def axes_of(vals, tol=0.08):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(round(v, 2))
    return out


def grid_axes(S):
    xs = [0.0, S.L] + [c["x"] for c in S.columns] + [w["x0"] for w in S.walls if w["axis"] == "Y"]
    ys = [0.0, S.B] + [c["y"] for c in S.columns] + [w["y0"] for w in S.walls if w["axis"] == "X"]
    xs = [x for x in xs if -0.05 <= x <= S.L + 0.05]
    ys = [y for y in ys if -0.05 <= y <= S.B + 0.05]
    return axes_of(xs), axes_of(ys)


class Sheet:
    def __init__(self, pdf, S, code, title, extent, subtitle="", scale=None):
        self.pdf, self.S, self.code, self.title, self.subtitle = pdf, S, code, title, subtitle
        self.fig = Figure(figsize=(420 * MM, 297 * MM))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, 420)
        self.ax.set_ylim(0, 297)
        self.ax.axis("off")
        if extent:
            x0, y0, x1, y1 = extent
            w, h = AREA[2] - AREA[0] - 30, AREA[3] - AREA[1] - 24
            self.scale = scale or next((s for s in SCALES if (x1 - x0) * 1000 / s <= w and (y1 - y0) * 1000 / s <= h), SCALES[-1])
            self.ox = (AREA[0] + AREA[2]) / 2 - (x0 + x1) / 2 * 1000 / self.scale
            self.oy = (AREA[1] + AREA[3]) / 2 - (y0 + y1) / 2 * 1000 / self.scale
        else:
            self.scale, self.ox, self.oy = None, 0, 0
        self.frame()

    def p(self, x, y):
        return self.ox + x * 1000 / self.scale, self.oy + y * 1000 / self.scale

    def frame(self):
        a, S = self.ax, self.S
        a.add_patch(Rectangle((10, 10), 400, 277, fill=False, lw=0.8, ec=INK))
        x0, y0, w, h = 250, 10, 160, 44
        a.add_patch(Rectangle((x0, y0), w, h, fill=True, fc="white", lw=0.6, ec=INK))
        a.add_patch(Rectangle((x0, y0 + h - 9), w, 9, fill=True, fc=BRAND, lw=0))
        a.text(x0 + 3, y0 + h - 4.5, "ConstruPilot", color="white", fontsize=9, weight="bold", va="center")
        a.text(x0 + w - 3, y0 + h - 4.5, S.t("ESTUDO PRÉVIO DE ESTRUTURA", "ÉTUDE PRÉALABLE DE STRUCTURE"), color="white", fontsize=6.5, va="center", ha="right")
        a.text(x0 + 3, y0 + 29, (S.name + (" — " + S.address if S.address else ""))[:95], fontsize=5.8)
        a.text(x0 + 3, y0 + 25, S.t("Base : plantas de arquitetura fornecidas", "Base : plans d'architecte fournis"), fontsize=5.2, color=GREY)
        a.text(x0 + 3, y0 + 18, self.title, fontsize=8.5, weight="bold")
        if self.subtitle:
            a.text(x0 + 3, y0 + 13.5, self.subtitle[:110], fontsize=5.6, color=GREY)
        a.text(x0 + 3, y0 + 4, S.t(f"Betão {S.concrete} · Aço {S.prof['steel']} · Recobrimentos : lajes 2,5 cm, vigas/pilares 3,0 cm, fundações 5,0 cm",
                                   f"Béton {S.concrete} · Acier {S.prof['steel']} · Enrobages : dalles 2,5 cm, poutres/poteaux 3,0 cm, fondations 5,0 cm"),
               fontsize=4.6, color=GREY)
        a.add_patch(Rectangle((x0 + w - 34, y0), 34, 22, fill=False, lw=0.6, ec=INK))
        a.text(x0 + w - 17, y0 + 14, self.code, fontsize=15, weight="bold", ha="center", va="center", color=BRAND)
        a.text(x0 + w - 17, y0 + 5, (S.t("Escala 1:", "Échelle 1:") + str(self.scale)) if self.scale else S.t("Sem escala", "Sans échelle"),
               fontsize=5.5, ha="center")
        a.text(x0 + w - 36, y0 + 1.5, S.t("A validar pelo projetista", "À valider par le BET"), fontsize=4.4, ha="right", color=GREY)

    def poly(self, pts, **kw):
        self.ax.add_patch(Polygon([self.p(*q) for q in pts], closed=True, **kw))

    def rect(self, x0, y0, x1, y1, **kw):
        a, b = self.p(x0, y0)
        c, d = self.p(x1, y1)
        self.ax.add_patch(Rectangle((a, b), c - a, d - b, **kw))

    def line(self, x0, y0, x1, y1, **kw):
        a, b = self.p(x0, y0)
        c, d = self.p(x1, y1)
        self.ax.plot([a, c], [b, d], **kw)

    def text(self, x, y, s, **kw):
        a, b = self.p(x, y)
        kw.setdefault("fontsize", 4.6)
        kw.setdefault("ha", "center")
        kw.setdefault("va", "center")
        self.ax.text(a, b, s, **kw)

    def grid(self, xs, ys, xr, yr):
        for k, x in enumerate(xs):
            self.line(x, yr[0], x, yr[1], color=GREY, lw=0.3, ls=(0, (8, 2, 1, 2)))
            for yy, off in ((yr[0], -1), (yr[1], 1)):
                a, b = self.p(x, yy)
                dy = off * 3.1 + (off * 5.5 if k % 2 and len(xs) > 6 else 0)
                self.ax.add_patch(Circle((a, b + dy), 2.6, fill=True, fc="white", ec=INK, lw=0.5))
                self.ax.text(a, b + dy, str(k + 1), fontsize=5, ha="center", va="center")
        for k, y in enumerate(ys):
            self.line(xr[0], y, xr[1], y, color=GREY, lw=0.3, ls=(0, (8, 2, 1, 2)))
            for xx, off in ((xr[0], -1), (xr[1], 1)):
                a, b = self.p(xx, y)
                dx = off * 3.1 + (off * 5.5 if k % 2 and len(ys) > 6 else 0)
                self.ax.add_patch(Circle((a + dx, b), 2.6, fill=True, fc="white", ec=INK, lw=0.5))
                self.ax.text(a + dx, b, chr(65 + k) if k < 26 else f"A{k - 25}", fontsize=5, ha="center", va="center")

    def chain(self, vals, fixed, axis="x", off_mm=0.0):
        for a_, b_ in zip(vals, vals[1:]):
            if b_ - a_ < 0.05:
                continue
            if axis == "x":
                (x0, y0), (x1, _) = self.p(a_, fixed), self.p(b_, fixed)
                y0 += off_mm
                self.ax.annotate("", (x0, y0), (x1, y0), arrowprops=dict(arrowstyle="<|-|>", lw=0.35, color=INK, mutation_scale=4))
                self.ax.text((x0 + x1) / 2, y0 + 1.2, f2(b_ - a_), fontsize=4.4, ha="center", va="bottom")
            else:
                (x0, y0), (_, y1) = self.p(fixed, a_), self.p(fixed, b_)
                x0 += off_mm
                self.ax.annotate("", (x0, y0), (x0, y1), arrowprops=dict(arrowstyle="<|-|>", lw=0.35, color=INK, mutation_scale=4))
                self.ax.text(x0 - 1.2, (y0 + y1) / 2, f2(b_ - a_), fontsize=4.4, ha="right", va="center", rotation=90)

    def legend(self, items, x=14, y=50):
        a = self.ax
        a.text(x, y + 4, self.S.t("LEGENDA", "LÉGENDE"), fontsize=5.5, weight="bold")
        for k, (kind, label) in enumerate(items):
            yy = y - k * 4.3
            if kind == "col":
                a.add_patch(Rectangle((x, yy - 1), 3, 2, fc=INK))
            elif kind == "wall":
                a.add_patch(Rectangle((x, yy - 1), 6, 2, fc="#8e8e8a", ec=INK, lw=0.4, hatch="xxxx"))
            elif kind == "core":
                a.add_patch(Rectangle((x, yy - 1), 6, 2, fc="#b9b9b5", ec=INK, lw=0.4, hatch="////"))
            elif kind == "beam":
                a.plot([x, x + 6], [yy + 0.6, yy + 0.6], color=INK, lw=0.45, ls=(0, (4, 2)))
                a.plot([x, x + 6], [yy - 0.6, yy - 0.6], color=INK, lw=0.45, ls=(0, (4, 2)))
            elif kind == "fnd":
                a.add_patch(Rectangle((x, yy - 1.2), 6, 2.4, fc="#e8ddc8", ec=INK, lw=0.4, ls="--"))
            elif kind == "balc":
                a.add_patch(Rectangle((x, yy - 1.2), 6, 2.4, fc="#f6efe6", ec=INK, lw=0.4))
            elif kind == "muro":
                a.add_patch(Rectangle((x, yy - 0.7), 6, 1.4, fc="#5f5f5b", ec=INK, lw=0.3))
            a.text(x + 8, yy, label, fontsize=4.8, va="center")

    def notes(self, lines, x=80, y=54, title=None):
        self.ax.text(x, y, title or self.S.t("NOTAS", "NOTES"), fontsize=5.5, weight="bold")
        for k, t_ in enumerate(lines[:9]):
            self.ax.text(x, y - 4 - k * 3.5, t_[:150], fontsize=4.4, va="top")

    def save(self):
        self.pdf.savefig(self.fig)


# ---------------------------------------------------------------- elementos
def draw_cores(s):
    S = s.S
    for c in S.cores:
        cs = ES.core_section(c)
        for (x0, y0, x1, y1) in cs["parts"]:
            s.rect(x0, y0, x1, y1, fc="#b9b9b5", ec=INK, lw=0.5, hatch="////")
        x0, y0, x1, y1 = c["box"]
        lab = S.t("NÚCLEO DE ESCADA", "NOYAU D'ESCALIER") if c["kind"] == "stair" else S.t("ELEV.", "ASC.")
        s.text((x0 + x1) / 2, (y0 + y1) / 2, f"{lab}\n{c['id']} · e = {f2(c['t'])}", fontsize=4.2)


def draw_walls(s):
    for w in s.S.walls:
        t = w["t"]
        s.rect(w["x0"] - t / 2, w["y0"] - t / 2, w["x1"] + t / 2, w["y1"] + t / 2, fc="#8e8e8a", ec=INK, lw=0.5, hatch="xxxx")
        lab = f"{w['id']}{' *' if w['proposed'] else ''}\n{int(round(t * 100))}×{int(round(w['Lw'] * 100))}"
        if w["axis"] == "Y":
            dx = 0.75 if w["x0"] < s.S.L / 2 else -0.75
            s.text(w["x0"] + dx, (w["y0"] + w["y1"]) / 2, lab, fontsize=4.4, color=RED, weight="bold", rotation=90)
        else:
            dy = 0.6 if w["y0"] < s.S.B / 2 else -0.6
            s.text((w["x0"] + w["x1"]) / 2, w["y0"] + dy, lab, fontsize=4.4, color=RED, weight="bold")


def draw_columns(s, cols, tag="base"):
    S = s.S
    for c in cols:
        d = c.get(tag) or c["base"]
        b, h = d["b"], d["h"]
        s.rect(c["x"] - b / 2, c["y"] - h / 2, c["x"] + b / 2, c["y"] + h / 2, fc=INK, ec=INK, lw=0.3)
        dx = 0.55 if c["x"] < S.L - 0.5 else -0.55
        dy = 0.7 if c["y"] < S.B / 2 else -0.7
        s.text(c["x"] + dx, c["y"] + dy, f"{c['id']}\n{int(round(b * 100))}×{int(round(h * 100))}", fontsize=4.1, color=BLUE, weight="bold")


def beam_label(S, R, line_id):
    seg = [b for b in R["beams"] if b["line"] == line_id]
    if not seg:
        return None
    hmax = max(b["h"] for b in seg)
    bars, _ = ES.beam_bars(max(b["As"] for b in seg))
    return f"{line_id} {int(seg[0]['b_w'] * 100)}×{int(hmax * 100)} · {bars}"


def draw_beams(s, R):
    S = s.S
    done = set()
    for b in R["beams"]:
        (x0, y0), (x1, y1) = b["a"], b["b"]
        horiz = abs(y1 - y0) < 1e-6
        w = b["b_w"]
        if horiz:
            s.line(x0, y0 - w / 2, x1, y1 - w / 2, color=INK, lw=0.45, ls=(0, (4, 2)))
            s.line(x0, y0 + w / 2, x1, y1 + w / 2, color=INK, lw=0.45, ls=(0, (4, 2)))
        else:
            s.line(x0 - w / 2, y0, x1 - w / 2, y1, color=INK, lw=0.45, ls=(0, (4, 2)))
            s.line(x0 + w / 2, y0, x1 + w / 2, y1, color=INK, lw=0.45, ls=(0, (4, 2)))
        if b["line"] in done:
            continue
        done.add(b["line"])
        segs = [x for x in R["beams"] if x["line"] == b["line"]]
        longest = max(segs, key=lambda x: x["L"])
        (a0, b0), (a1, b1) = longest["a"], longest["b"]
        mx, my = (a0 + a1) / 2, (b0 + b1) / 2
        lab = beam_label(S, R, b["line"])
        if horiz:
            off = -0.45 if my < 0.3 else (0.45 if my > S.B - 0.3 else 0.40)
            s.text(mx, my + off, lab, fontsize=3.9, color=ORANGE)
        else:
            off = -0.45 if mx < 0.3 else 0.45
            s.text(mx + off, my, lab, fontsize=3.9, color=ORANGE, rotation=90)


def draw_outline(s, R, balconies=True):
    S = s.S
    if balconies:
        for b in S.balconies:
            d = b["depth"]
            if b["side"] == "y0":
                s.rect(b["from"], -d, b["to"], 0, fc="#f6efe6", ec=INK, lw=0.7)
            elif b["side"] == "y1":
                s.rect(b["from"], S.B, b["to"], S.B + d, fc="#f6efe6", ec=INK, lw=0.7)
            elif b["side"] == "x0":
                s.rect(-d, b["from"], 0, b["to"], fc="#f6efe6", ec=INK, lw=0.7)
            else:
                s.rect(S.L, b["from"], S.L + d, b["to"], fc="#f6efe6", ec=INK, lw=0.7)
            cv = R["cant"].get(d)
            bars = ES.mesh(cv["as_cm2_m"])[0] if cv else ""
            txt = S.t(f"VARANDA EM CONSOLA {f2(d)} m · h = 0,20 → 0,15 · sup. {bars}", f"BALCON EN CONSOLE {f2(d)} m · h = 0,20 → 0,15 · sup. {bars}")
            if b["side"] in ("y0", "y1"):
                s.text((b["from"] + b["to"]) / 2, (-d / 2) if b["side"] == "y0" else S.B + d / 2, txt, fontsize=4.2)
            else:
                s.text((-d / 2) if b["side"] == "x0" else S.L + d / 2, (b["from"] + b["to"]) / 2, txt, fontsize=4.2, rotation=90)
    s.poly([(0, 0), (S.L, 0), (S.L, S.B), (0, S.B)], fill=False, ec=INK, lw=1.1)


def draw_panels(s, R, typ="habitacao"):
    for sl in R["slabs"]:
        if sl["type"] != typ:
            continue
        r = sl["r"]
        try:
            bx = ES.mesh(r["span"]["x"]["as_req_cm2_m"])[0]
            by = ES.mesh(r["span"]["y"]["as_req_cm2_m"])[0]
            bs = ES.mesh(max([v["as_req_cm2_m"] for v in r["supports"].values()] or [1.0]))[0]
        except (KeyError, TypeError, ValueError):
            bx = by = bs = "—"
        cx, cy = (sl["x0"] + sl["x1"]) / 2, (sl["y0"] + sl["y1"]) / 2
        small = (sl["x1"] - sl["x0"]) < 3.0 or (sl["y1"] - sl["y0"]) < 3.0
        txt = f"{sl['name']} h = {f2(sl['h'])}" if small else f"{sl['name']}  h = {f2(sl['h'])}\ninf. {bx} (x) / {by} (y)\nsup. {bs}"
        s.text(cx, cy, txt, fontsize=3.9 if small else 4.1, color=GREEN)


def draw_voids(s):
    for c in s.S.cores:
        x0, y0, x1, y1 = c["box"]
        s.line(x0 + .2, y0 + .2, x1 - .2, y1 - .2, color=GREY, lw=0.3)
        s.line(x0 + .2, y1 - .2, x1 - .2, y0 + .2, color=GREY, lw=0.3)


def _extent(S, garage=False, balconies=True):
    xs, ys = [0.0, S.L], [0.0, S.B]
    if balconies:
        for b in S.balconies:
            if b["side"] in ("y0", "y1"):
                xs += [b["from"], b["to"]]
                ys.append(-b["depth"] if b["side"] == "y0" else S.B + b["depth"])
            else:
                ys += [b["from"], b["to"]]
                xs.append(-b["depth"] if b["side"] == "x0" else S.L + b["depth"])
    if garage and S.basement:
        xs += [p[0] for p in S.bpoly]
        ys += [p[1] for p in S.bpoly]
    return (min(xs) - 2.0, min(ys) - 2.0, max(xs) + 2.0, max(ys) + 2.0)


# ---------------------------------------------------------------- folhas
def sheet_foundations(pdf, S, R):
    ext = _extent(S, garage=True, balconies=False)
    s = Sheet(pdf, S, "E01", S.t("Planta de fundações e muros de cave" if S.basement else "Planta de fundações", "Plan des fondations et voiles enterrés"
                                  if S.basement else "Plan des fondations"), ext,
              S.t("Sapatas isoladas, ensoleiramentos sob núcleos e paredes, sapatas contínuas dos muros",
                  "Semelles isolées, radiers sous noyaux et voiles, semelles filantes des voiles enterrés"))
    if S.basement:
        s.poly(S.bpoly, fill=True, fc="#fbfaf7", ec="none")
    for w in R["bwalls"]:
        (x0, y0), (x1, y1) = w["p0"], w["p1"]
        nx, ny = -(y1 - y0), x1 - x0
        ln = math.hypot(nx, ny) or 1
        nx, ny = nx / ln * 0.5, ny / ln * 0.5
        s.poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], fill=True, fc="#e8ddc8", ec=INK, lw=0.25, ls="--", alpha=0.6)
        s.line(x0, y0, x1, y1, color="#5f5f5b", lw=max(w["t"] * 1000 / s.scale * 2.8, 0.8), solid_capstyle="butt")
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        horiz = abs(y1 - y0) < abs(x1 - x0)
        lab = f"{w['name'].split(' — ')[0]} e = {f2(w['t'])}" + (S.t(f" · terras {f2(w['ht'], 1)} m", f" · terres {f2(w['ht'], 1)} m") if w["ht"] else "")
        s.text(mx + (0 if horiz else (-1.1 if mx < S.L / 2 else 1.1)), my + ((1.0 if my > S.B / 2 else -1.0) if horiz else 0), lab, fontsize=4.0,
               rotation=0 if horiz else 90)
    for fz in R["fnd"]:
        s.rect(fz["x0"], fz["y0"], fz["x1"], fz["y1"], fc="#e8ddc8", ec=INK, lw=0.6, ls="--")
        s.text(fz["x0"] + 0.15, fz["y1"] - 0.35, f"{fz['id']}  {f2(fz['L'])} × {f2(fz['B'])} × {f2(fz['h'])}", fontsize=4.1, ha="left", color=BRAND, weight="bold")
    for fo in R["foots"]:
        s.rect(fo["x0"], fo["y0"], fo["x1"], fo["y1"], fc="#e8ddc8", ec=INK, lw=0.6, ls="--")
        s.text((fo["x0"] + fo["x1"]) / 2, fo["y0"] - 0.45, f"S{fo['id'].lstrip('P')} {f2(fo['x1'] - fo['x0'])}×{f2(fo['y1'] - fo['y0'])}×{f2(fo['h'])}",
               fontsize=3.8, color=BRAND)
    draw_cores(s)
    draw_walls(s)
    draw_columns(s, R["cols"])
    xs, ys = grid_axes(S)
    s.grid(xs, ys, (ext[0] + 0.8, ext[2] - 0.8), (ext[1] + 0.8, ext[3] - 0.8))
    s.chain(xs, ext[1] + 1.6, "x")
    s.chain(ys, ext[0] + 1.6, "y")
    s.legend([("col", S.t("Pilar (secção na base)", "Poteau (section en pied)")), ("wall", S.t("Parede resistente BA (* proposta)", "Voile BA (* proposé)")),
              ("core", S.t("Núcleo BA", "Noyau BA")), ("fnd", S.t("Sapata / ensoleiramento", "Semelle / radier")), ("muro", S.t("Muro de cave BA", "Voile enterré BA"))])
    so = S.soil
    s.notes([S.t(f"1. Tensão resistente de cálculo do terreno {'(estudo geotécnico)' if so['report'] else 'ADMITIDA'} : σRd = {f2(so['sigma_rd'], 0)} kPa (ELU) / "
                 f"{f2(so['sigma_sls'], 0)} kPa (serviço).", f"1. Contrainte de calcul du sol {'(étude G2)' if so['report'] else 'ADMISE'} : σRd = {f2(so['sigma_rd'], 0)} kPa "
                 f"(ELU) / {f2(so['sigma_sls'], 0)} kPa (ELS).")]
            + ([S.t("   SEM ESTUDO GEOTÉCNICO : fundações a confirmar por sondagens e ensaios (EN 1997-1/-2).",
                    "   SANS ÉTUDE DE SOL : fondations à confirmer par une mission G2 (NF P 94-500).")] if not so["report"] else [])
            + [S.t("2. Betão de limpeza com 0,10 m sob todas as fundações. Recobrimento 5,0 cm.", "2. Béton de propreté de 0,10 m sous toutes les fondations. Enrobage 5,0 cm."),
               S.t("3. Muros enterrados : impermeabilização + membrana drenante + dreno Ø160.", "3. Voiles enterrés : étanchéité + nappe drainante + drain Ø160."),
               S.t("4. Armaduras das sapatas e ensoleiramentos : ver quadro E05.", "4. Armatures des semelles et radiers : voir tableau E05.")])
    s.save()


def sheet_floor(pdf, S, R, code, title, subtitle, k, roof=False, level0=False):
    ext = _extent(S, garage=level0, balconies=not level0)
    s = Sheet(pdf, S, code, title, ext, subtitle)
    if level0 and S.basement:
        s.poly(S.bpoly, fill=True, fc="#f3f7f0", ec=INK, lw=0.8)
        for sl in R["slabs"]:
            if sl["type"] == "jardim":
                s.rect(sl["x0"], sl["y0"], sl["x1"], sl["y1"], fill=False, ec=GREEN, lw=0.3, ls=":")
        for gb in R.get("gbeam_design") or []:
            s.line(*gb["a"], *gb["b"], color=INK, lw=0.45, ls=(0, (4, 2)))
            mx, my = (gb["a"][0] + gb["b"][0]) / 2, (gb["a"][1] + gb["b"][1]) / 2
            horiz = abs(gb["a"][1] - gb["b"][1]) < 1e-6
            s.text(mx + (0 if horiz else 0.4), my + (0.4 if horiz else 0), f"{gb['name']} {int(gb['b_w'] * 100)}×{int(gb['h'] * 100)} · {ES.beam_bars(gb['As'])[0]}",
                   fontsize=3.8, color=ORANGE, rotation=0 if horiz else 90)
        draw_panels(s, R, "jardim")
    draw_outline(s, R, balconies=not level0)
    draw_panels(s, R, "habitacao")
    draw_beams(s, R)
    draw_cores(s)
    draw_walls(s)
    draw_voids(s)
    tag = "base" if k <= 0 else ("topo" if any(c.get("topo") and k >= c["topo"]["from"] for c in R["cols"] if not c["garage"]) else "base")
    cols = [c for c in R["cols"] if not c["garage"] or level0]
    draw_columns(s, cols, tag)
    xs, ys = grid_axes(S)
    s.grid(xs, ys, (ext[0] + 0.8, ext[2] - 0.8), (ext[1] + 0.8, ext[3] - 0.8))
    s.chain(xs, ext[1] + 1.6, "x")
    s.chain(ys, ext[0] + 1.6, "y")
    s.legend([("col", S.t("Pilar (ver quadro E05)", "Poteau (voir tableau E05)")), ("wall", S.t("Parede resistente BA", "Voile BA")),
              ("core", S.t("Núcleo BA", "Noyau BA")), ("beam", S.t("Viga sob a laje (b × h total)", "Poutre (b × h total)"))]
             + ([("balc", S.t("Varanda em consola", "Balcon en console"))] if not level0 and S.balconies else []))
    nt = [S.t(f"1. Lajes maciças armadas em duas direções, h = {f2(S.slab_h)} ; armaduras inferiores e superiores (apoios) por painel.",
              f"1. Dalles pleines portant dans deux directions, h = {f2(S.slab_h)} ; aciers inférieurs et supérieurs (appuis) par panneau.")]
    if roof:
        nt.append(S.t("2. Cobertura em terraço : forma de pendentes, isolamento, impermeabilização e proteção (ver estudo térmico).",
                      "2. Toiture-terrasse : forme de pente, isolant, étanchéité et protection (voir étude thermique)."))
    if level0 and S.basement:
        nt.append(S.t(f"2. Laje sobre a cave fora do edifício h = {f2(S.slab_hg)} (terraços / jardins, G2 = {f2(S.loads['garden']['g2'], 1)}, Q = {f2(S.loads['garden']['q'], 1)} kN/m²).",
                      f"2. Dalle sur sous-sol hors bâtiment h = {f2(S.slab_hg)} (terrasses / jardins, G2 = {f2(S.loads['garden']['g2'], 1)}, Q = {f2(S.loads['garden']['q'], 1)} kN/m²)."))
    if S.balconies and not level0:
        nt.append(S.t("3. Varandas em consola : armadura superior amarrada ≥ 1,5 m na laje ; rotura térmica recomendada.",
                      "3. Balcons en console : aciers supérieurs ancrés ≥ 1,5 m dans la dalle ; rupteurs thermiques recommandés."))
    if any(w["proposed"] for w in S.walls):
        nt.append(S.t("4. Paredes assinaladas com * PROPOSTAS por este estudo (torção sísmica) : a compatibilizar com a arquitetura.",
                      "4. Voiles repérés * PROPOSÉS par cette étude (torsion sismique) : à coordonner avec l'architecte."))
    s.notes(nt)
    s.save()


def sheet_tables(pdf, S, R):
    s = Sheet(pdf, S, "E05", S.t("Quadros de pilares, paredes, vigas e fundações", "Tableaux des poteaux, voiles, poutres et fondations"), None,
              S.t("Secções e armaduras de pré-dimensionamento", "Sections et armatures de prédimensionnement"))
    a = s.ax

    def table(x, y, title, head, rows, widths, fs=4.4, max_rows=40):
        a.text(x, y + 3, title, fontsize=6, weight="bold", color=BRAND)
        rh = 3.8
        cx = x
        for w, h in zip(widths, head):
            a.add_patch(Rectangle((cx, y - rh), w, rh, fc=BRAND, ec="white", lw=0.3))
            a.text(cx + w / 2, y - rh / 2, h, fontsize=fs, color="white", ha="center", va="center", weight="bold")
            cx += w
        for k, r in enumerate(rows[:max_rows]):
            cx = x
            yy = y - rh * (k + 2)
            for w, v in zip(widths, r):
                a.add_patch(Rectangle((cx, yy), w, rh, fc="#f4f4f1" if k % 2 else "white", ec="#d0d0cc", lw=0.3))
                a.text(cx + w / 2, yy + rh / 2, str(v)[:40], fontsize=fs, ha="center", va="center")
                cx += w
        return y - rh * (min(len(rows), max_rows) + 1)

    rows = []
    for c in R["cols"]:
        b = c["base"]
        bb, _ = ES.bars(b["As_cm2"])
        t_ = c.get("topo") if c.get("topo") is not c["base"] else None
        rows.append([c["id"], f"{int(round(b['b'] * 100))}×{int(round(b['h'] * 100))}", f2(b["N_Ed"], 0), f2(b["nu"]), bb,
                     S.t("Ø8//0,10 (zona crítica) / 0,15", "HA8 e=10 (zone critique) / 15"),
                     f"{int(round(t_['b'] * 100))}×{int(round(t_['h'] * 100))}" if t_ else "—", ES.bars(t_["As_cm2"])[0] if t_ else "—"])
    lo = S.lname(ES.storeys(S)[0])
    y = table(14, 262, S.t("QUADRO DE PILARES", "TABLEAU DES POTEAUX"),
              [S.t("Pilar", "Poteau"), S.t(f"Base ({lo})", f"Pied ({lo})"), "N_Ed (kN)", "ν", S.t("Armad. long.", "Aciers long."), S.t("Cintas", "Cadres"),
               S.t("Topo", "Tête"), S.t("Armad. long.", "Aciers long.")], rows, [14, 22, 20, 12, 20, 38, 18, 20], max_rows=24)
    rows = []
    se = R["seis"]
    for w in se.get("walls") or []:
        d = "Y" if next(x for x in S.walls if x["id"] == w["id"])["axis"] == "Y" else "X"
        be, _ = ES.bars(max(w[d]["As_ext_cm2"], 6.0))
        rows.append([w["id"], f"{int(round(w['t'] * 100))}×{int(round(w[d]['Lw'] * 100))}", f2(w["N_sis"], 0), f2(w[d]["M"], 0), f2(w[d]["V"], 0),
                     be + S.t(" cada extremo", " chaque about"), S.t("Ø10//0,20 (2 faces)", "HA10 e=20 (2 faces)"), S.t("Ø8//0,20 (2 faces)", "HA8 e=20 (2 faces)")])
    for c in se.get("cores") or []:
        be, _ = ES.bars(max(c["X"]["As_ext_cm2"], c["Y"]["As_ext_cm2"], 8.0) / 2)
        rows.append([c["id"], f"e = {f2(c['t'])}", f2(c["N_sis"], 0), f"{f2(c['X']['M'], 0)} / {f2(c['Y']['M'], 0)}", f"{f2(c['X']['V'], 0)} / {f2(c['Y']['V'], 0)}",
                     f"2×{be}" + S.t(" cada canto", " chaque angle"), S.t("Ø10//0,20 (2 faces)", "HA10 e=20 (2 faces)"),
                     S.t("Ø8//0,15 (2 faces)", "HA8 e=15 (2 faces)") if max(c["X"]["rho_h"], c["Y"]["rho_h"]) > 0.002 else S.t("Ø8//0,20 (2 faces)", "HA8 e=20 (2 faces)")])
    y = table(14, y - 9, S.t("PAREDES E NÚCLEOS (base, situação sísmica)", "VOILES ET NOYAUX (pied, situation sismique)"),
              [S.t("Elemento", "Élément"), S.t("Secção", "Section"), "N (kN)", "M (kN.m) X/Y", "V (kN) X/Y", S.t("Extremidades", "Abouts"),
               S.t("Vertical", "Verticaux"), S.t("Horizontal", "Horizontaux")], rows, [18, 16, 14, 24, 22, 34, 26, 26], max_rows=14)
    rows = []
    for fo in R["foots"]:
        m, _ = ES.mesh(fo["As_cm2"] / max(fo["x1"] - fo["x0"], fo["y1"] - fo["y0"]))
        rows.append([f"S{fo['id'].lstrip('P')}", f"{f2(fo['x1'] - fo['x0'])} × {f2(fo['y1'] - fo['y0'])}", f2(fo["h"]), f2(fo["N_Ed"], 0), f2(fo["sigma_Ed"], 0),
                     m + S.t(" (2 dir., inf.)", " (2 dir., inf.)")])
    for fz in R["fnd"]:
        rows.append([fz["id"], f"{f2(fz['L'])} × {f2(fz['B'])}", f2(fz["h"]), "—", f2(fz.get("sigma_grav") or 0, 0),
                     S.t("Ø16//0,15 inf. e sup. (2 dir.)", "HA16 e=15 inf. et sup. (2 dir.)")])
    table(214, 262, S.t("QUADRO DE FUNDAÇÕES", "TABLEAU DES FONDATIONS"), ["Ref.", "B × L (m)", "h (m)", "N_Ed (kN)", "σ (kPa)", S.t("Armadura", "Armatures")],
          rows, [14, 26, 12, 18, 16, 50], max_rows=24)
    rows = [[b["name"], f2(b["L"]), f"{int(b['b_w'] * 100)}×{int(b['h'] * 100)}", f2(b["M_sup"], 0), f2(b["V"], 0), ES.beam_bars(b["As"])[0],
             (S.t("Ø8//0,10", "HA8 e=10") if (b["Asw"] or 0) > 4.0 else S.t("Ø8//0,15", "HA8 e=15")) + S.t(" (2 ramos)", " (2 brins)"), f2(b["w_mm"], 0)]
            for b in R["beams"] + (R.get("gbeam_design") or [])]
    head = [S.t("Viga", "Poutre"), S.t("Vão (m)", "Portée (m)"), "b×h", "M_Ed (kN.m)", "V_Ed (kN)", S.t("Armad. inf./sup.", "Aciers inf./sup."),
            S.t("Estribos", "Étriers"), S.t("Flecha (mm)", "Flèche (mm)")]
    w_ = [16, 14, 14, 18, 16, 22, 30, 16]
    half = (len(rows) + 1) // 2
    y2 = min(y - 9, 140)
    table(14, y2, S.t("QUADRO DE VIGAS (todos os pisos)", "TABLEAU DES POUTRES (tous niveaux)"), head, rows[:min(half, 18)], w_, fs=4.0)
    if len(rows) > half:
        table(214, y2 if y2 < 150 else 140, "", head, rows[half:half + 18], w_, fs=4.0)
    s.save()


def sheet_section(pdf, S, R):
    lv = S.levels()
    z_lo, z_hi = lv[0][2] - 1.5, lv[-1][2] + 1.5
    ys = [-max([b["depth"] for b in S.balconies if b["side"] == "y0"] or [0]) - 3, S.B + max([b["depth"] for b in S.balconies if b["side"] == "y1"] or [0]) + 3]
    if S.basement:
        ys += [p[1] for p in S.bpoly]
    ext = (min(ys) - 4, z_lo - lv[0][2], max(ys) + 2, z_hi - lv[0][2])
    s = Sheet(pdf, S, "E06", S.t("Corte esquemático e pormenor-tipo", "Coupe schématique et détail type"), ext,
              S.t("Corte transversal (direção Y) : níveis, lajes, fachadas, núcleo e fundações", "Coupe transversale (direction Y) : niveaux, dalles, façades, noyau et fondations"))
    base = lv[0][2]

    def P(y, z):
        return s.p(y, z - base)
    a = s.ax
    stair = next((c for c in S.cores if c["kind"] == "stair"), None)
    for k, name, z in lv:
        thick = S.slab_h if k >= 0 or not S.basement else 0.15
        y0 = -max([b["depth"] for b in S.balconies if b["side"] == "y0"] or [0]) if k >= 1 else 0.0
        y1 = S.B + (max([b["depth"] for b in S.balconies if b["side"] == "y1"] or [0]) if k >= 1 else 0.0)
        if S.basement and k in (-1, 0):
            y0 = min(p[1] for p in S.bpoly)
            y1 = max(p[1] for p in S.bpoly)
        (x0, yy0), (x1, yy1) = P(y0, z - thick), P(y1, z)
        a.add_patch(Rectangle((x0, yy0), x1 - x0, yy1 - yy0, fc="#b9b9b5", ec=INK, lw=0.4))
        xl, yl = P(min(ys) - 3.5, z)
        a.text(xl, yl, f"{name}\n{f2(z)}", fontsize=4.6, ha="left", va="center")
    for y in (0.0, S.B):
        for k, name, z in lv[:-1]:
            if k < 0:
                continue
            (x0, yy0), (x1, yy1) = P(y - 0.15, z), P(y + 0.15, z + S.H - S.slab_h)
            a.add_patch(Rectangle((x0, yy0), x1 - x0, yy1 - yy0, fc="white", ec=INK, lw=0.4))
    if stair:
        for y0_, y1_ in ((stair["box"][1], stair["box"][1] + stair["t"]), (stair["box"][3] - stair["t"], stair["box"][3])):
            (x0, z0), (x1, z1) = P(y0_, base), P(y1_, lv[-1][2])
            a.add_patch(Rectangle((x0, z0), x1 - x0, z1 - z0, fc="#b9b9b5", ec=INK, lw=0.4, hatch="////"))
        mid = (stair["box"][1] + stair["box"][3]) / 2
        xt, zt = P(mid, base + (lv[-1][2] - base) * 0.55)
        a.text(xt, zt, S.t("NÚCLEO\nDE ESCADA", "NOYAU\nD'ESCALIER"), fontsize=4.6, ha="center")
    if S.basement:
        for y in (min(p[1] for p in S.bpoly), max(p[1] for p in S.bpoly)):
            (x0, z0), (x1, z1) = P(y - 0.125, base - 0.15), P(y + 0.125, lv[1][2])
            a.add_patch(Rectangle((x0, z0), x1 - x0, z1 - z0, fc="#5f5f5b", ec=INK, lw=0.4))
            (x0, z0), (x1, z1) = P(y - 0.5, base - 0.55), P(y + 0.5, base - 0.15)
            a.add_patch(Rectangle((x0, z0), x1 - x0, z1 - z0, fc="#e8ddc8", ec=INK, lw=0.4, ls="--"))
    for fz in R["fnd"][:1]:
        (x0, z0), (x1, z1) = P(fz["y0"], base - 0.15 - fz["h"]), P(fz["y1"], base - 0.15)
        a.add_patch(Rectangle((x0, z0), x1 - x0, z1 - z0, fc="#e8ddc8", ec=INK, lw=0.5, ls="--"))
        a.text((x0 + x1) / 2, (z0 + z1) / 2, S.t(f"Ensoleiramento {fz['id']} h = {f2(fz['h'])}", f"Radier {fz['id']} h = {f2(fz['h'])}"), fontsize=4.2, ha="center",
               va="center")
    xa = P(max(ys) + 1.0, 0)[0]
    for (k1, n1, z1_), (k2, n2, z2_) in zip(lv, lv[1:]):
        a.annotate("", (xa, P(0, z1_)[1]), (xa, P(0, z2_)[1]), arrowprops=dict(arrowstyle="<|-|>", lw=0.35, color=INK, mutation_scale=4))
        a.text(xa + 1.2, (P(0, z1_)[1] + P(0, z2_)[1]) / 2, f2(z2_ - z1_), fontsize=4.6, va="center")
    xs_, zs_ = P(0.0, lv[-1][2] + 0.9)
    a.text(xs_, zs_, S.t("Fachada principal", "Façade principale"), fontsize=4.6, ha="center")
    xs_, zs_ = P(S.B, lv[-1][2] + 0.9)
    a.text(xs_, zs_, S.t("Tardoz", "Façade arrière"), fontsize=4.6, ha="center")
    s.notes([S.t("1. Corte esquemático para leitura dos níveis e do sistema estrutural ; não substitui os cortes de arquitetura.",
                 "1. Coupe schématique de lecture des niveaux et du système porteur ; ne remplace pas les coupes d'architecte."),
             S.t(f"2. Pé-direito estrutural {f2(S.H)} m (laje {f2(S.slab_h)}) — confirmar com tetos falsos e acabamentos.",
                 f"2. Hauteur d'étage {f2(S.H)} m (dalle {f2(S.slab_h)}) — à confirmer avec faux plafonds et finitions."),
             S.t("3. Terreno e cotas exteriores a confirmar pelo levantamento topográfico.", "3. Terrain et cotes extérieures à confirmer par le relevé topographique.")])
    s.save()


def build(S, R, path):
    with PdfPages(path) as pdf:
        sheet_foundations(pdf, S, R)
        if S.basement:
            sheet_floor(pdf, S, R, "E02", S.t(f"Planta estrutural — laje do {S.lname(0)} (teto da cave)", f"Plan de structure — dalle du {S.lname(0)} (plancher haut du sous-sol)"),
                        S.t(f"Laje h = {f2(S.slab_h)} sob o edifício e h = {f2(S.slab_hg)} sobre a cave exterior", f"Dalle h = {f2(S.slab_h)} sous le bâtiment, h = {f2(S.slab_hg)} sur le sous-sol extérieur"),
                        0, level0=True)
        rng = f"{S.lname(1)} a {S.lname(S.n - 1)}" if S.n > 2 else S.lname(1)
        if S.n >= 2:
            sheet_floor(pdf, S, R, "E03", S.t(f"Planta estrutural — {rng} (piso-tipo)", f"Plan de structure — {rng.replace(' a ', ' à ')} (niveau courant)"),
                        S.t(f"Lajes maciças h = {f2(S.slab_h)}", f"Dalles pleines h = {f2(S.slab_h)}"), 1)
        sheet_floor(pdf, S, R, "E04", S.t("Planta estrutural — Cobertura", "Plan de structure — Toiture-terrasse"),
                    S.t(f"Laje de cobertura h = {f2(S.slab_h)}", f"Dalle de toiture h = {f2(S.slab_h)}"), S.n, roof=True)
        sheet_tables(pdf, S, R)
        sheet_section(pdf, S, R)
    return path
