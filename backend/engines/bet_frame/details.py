"""Planches d'exécution : pormenores de armaduras (vigas em alçado cotado + secção, secções de pilares, sapatas em planta e
corte armados), estudo térmico por fração (REH / bilan) e planta de climatização / aquecimento por piso.

Les planches de détails sont dessinées en coordonnées papier (mm, comme les tableaux) avec des échelles indiquées sur chaque
vue ; les vigas sont en alçado à échelle horizontale réduite et verticale 1:25 (convention des esquemas de armaduras).
"""
from __future__ import annotations

import math

from .calc import mesh_txt, num
from .lang import _
from .model import Frame
from .sheets import AREA, BA, BA_LIGHT, FOND, HEAD, S, UNIT_FILL, _new, _note, _plan_sheet, _slab_groups, _group_name, \
    columns as draw_columns, cores as draw_cores, grid, grid_dims, outline, table_sheets, u

W_AREA = AREA[2] - AREA[0]          # 289 mm
H_AREA = AREA[3] - AREA[1]          # 260 mm
HSCALES = (50, 75, 100, 125, 150, 200, 250, 300)
SV = 25                              # échelle verticale des alçados de vigas (1:25)
SX = 20                              # échelle des secções (1:20)


def _lb(phi: int) -> float:
    """Comprimento de amarração / emenda de cálculo simplificado : 40 Ø (boa aderência, C25/30)."""
    return 40 * phi / 1000


def _m(v: float) -> str:
    return num(v, 2)


# ================================================================ vigas
def _beam_sig(bm: dict) -> tuple:
    return (bm["b"], bm["h"], tuple(round(sp["L"], 2) for sp in bm["spans"]),
            tuple((sp["bot"]["txt"], sp["top_l"]["txt"], sp["top_r"]["txt"], sp["stirrups"]) for sp in bm["spans"]))


def _draw_beam(sh, m: Frame, r: dict, bm: dict, names: list[str], y0: float, row_h: float, sx: int):
    """Alçado cotado de uma viga contínua + secção a meio vão, dentro da faixa [y0, y0 + row_h] (mm)."""
    mt = r["mat"]
    cov = mt["cover_beam"]
    pos = bm["pos"]
    L0 = pos[0]
    X = lambda a: 6 + (a - L0) * 1000 / sx                        # noqa: E731 — abscisse papier (mm)
    hz = bm["h"] * 1000 / SV
    yb = y0 + 17                                                   # face inférieure de la poutre
    yt = yb + hz
    xe = X(pos[-1])
    # titre de la viga
    lab = names[0] if len(names) == 1 else f"{names[0]} (= {', '.join(names[1:])[:60]})"
    sh.text("TITRE", (2, y0 + row_h - 3.2), S(f"{lab} — {int(round(bm['b'] * 100))}×{int(round(bm['h'] * 100))} cm"), 2.3, bold=True)
    sh.text("TEXTE", (2 + 2.3 * 0.55 * (len(lab) + 14), y0 + row_h - 3.2),
            S(_(f"échelles : horizontale 1:{sx}, verticale 1:{SV} · section 1:{SX}", f"escalas: horizontal 1:{sx}, vertical 1:{SV} · secção 1:{SX}")), 1.5)
    # betão
    sh.rect("BA", X(pos[0]), yb, xe, yt, 0.35, BA_LIGHT)
    # apoios (pilares) : tronçons au-dessus et au-dessous
    col_w = {}
    for c in r["columns"]:
        col_w[(round(c["x"], 2), round(c["y"], 2))] = c["h"] if bm["axis"] == "x" else c["b"]
    for k, a in enumerate(pos):
        if bm["axis"] == "x":
            key = (round(a, 2), round(m.gy[bm["line"]], 2))
        else:
            key = (round(m.gx[bm["line"]], 2), round(a, 2))
        w = max(col_w.get(key, 0.30) * 1000 / sx, 1.6)
        sh.rect("BA", X(a) - w / 2, yb - 6, X(a) + w / 2, yb, 0.3, BA, hatch="ba")
        sh.rect("BA", X(a) - w / 2, yt, X(a) + w / 2, yt + 3.5, 0.3, BA, hatch="ba")
    # armaduras
    c_mm = (cov + 0.008) * 1000 / SV
    yi, ys = yb + c_mm + 0.5, yt - c_mm - 0.5
    hw = 0.55
    sh.line("ACIER", (X(pos[0]) + 0.8, ys - 0.9), (xe - 0.8, ys - 0.9), 0.25, "dashed")       # porta-estribos
    sh.text("ACIER", (X(pos[0]) + 1.5, ys - 2.6), S(_("2Ø12 de montage (filants)", "2Ø12 porta-estribos (contínuos)")), 1.3)
    n = len(bm["spans"])
    for k, sp in enumerate(bm["spans"]):
        a0, a1 = pos[k], pos[k + 1]
        bot = sp["bot"]
        ext = _lb(bot["phi"]) / 2
        xa, xb = X(a0 - (ext if k > 0 else 0.15)), X(a1 + (ext if k < n - 1 else 0.15))
        pts = [(xa, yi + (1.6 if k == 0 else 0)), (xa, yi)] if k == 0 else [(xa, yi)]
        pts += [(xb, yi)] + ([(xb, yi + 1.6)] if k == n - 1 else [])
        sh.poly("ACIER", pts, hw)
        Lbar = (a1 - a0) + (ext if k > 0 else 0.15) + (ext if k < n - 1 else 0.15) + (0.20 if k in (0, n - 1) else 0)
        sh.text("ACIER", ((X(a0) + X(a1)) / 2, yb - 10.6),
                S(f"{bot['txt']}" + (_(" (2 lits)", " (2 camadas)") if bot["layers"] > 1 else "") + f" L={_m(Lbar)}"), 1.45, "c", bold=True)
        # estribos : zonas críticas junto aos apoios (lcr = h) e zona corrente
        s = sp.get("s", 0.20)
        s_cr = max(0.075, min(s, math.floor(min(bm["h"] / 4, 0.15) / 0.025) * 0.025))
        lcr = max(bm["h"], 0.50)
        span = a1 - a0
        zones = [(a0 + 0.05, min(a0 + lcr, a0 + span / 2), s_cr), (a0 + lcr, a1 - lcr, s), (max(a1 - lcr, a0 + span / 2), a1 - 0.05, s_cr)]
        for za, zb, ss in zones:
            if zb <= za:
                continue
            step = max(ss * 1000 / sx, 0.9)
            x = X(za)
            while x <= X(zb) + 1e-6:
                sh.line("ACIER", (x, yi - 0.2), (x, ys + 0.2), 0.09)
                x += step
        mid = (X(a0) + X(a1)) / 2
        sh.text("ACIER", (mid, yb - 14.0), S(_(f"cadres Ø8//{num(s, 2)} · zones crit. {num(lcr, 2)} m : Ø8//{num(s_cr, 3)}",
                                               f"estribos Ø8//{num(s, 2)} · zonas crít. {num(lcr, 2)} m: Ø8//{num(s_cr, 3)}")), 1.3, "c")
    # armadura superior sobre apoios
    for k, a in enumerate(pos):
        left = bm["spans"][k - 1] if k > 0 else None
        right = bm["spans"][k] if k < n else None
        bars = [x for x in ((left or {}).get("top_r"), (right or {}).get("top_l")) if x]
        if not bars:
            continue
        tb = max(bars, key=lambda x: x["As"])
        Ll = 0.30 * left["L"] if left else 0.0
        Lr = 0.30 * right["L"] if right else 0.0
        if not left:
            Lr = max(0.25 * right["L"], 0.6)
        if not right:
            Ll = max(0.25 * left["L"], 0.6)
        xa = X(a - Ll) if left else X(a) - 0.6
        xb = X(a + Lr) if right else X(a) + 0.6
        pts = ([(xa, ys - 1.6)] if not left else []) + [(xa, ys), (xb, ys)] + ([(xb, ys - 1.6)] if not right else [])
        sh.poly("ACIER", pts, hw)
        Lbar = Ll + Lr + (0.25 if not left or not right else 0)
        sh.text("ACIER", ((xa + xb) / 2, yt + 4.4), S(f"{tb['txt']} L={_m(Lbar)}"), 1.4, "c", bold=True)
    # cotes : vãos entre eixos + total
    for k in range(n):
        sh.dim((X(pos[k]), yb - 6), (X(pos[k + 1]), yb - 6), -1.8, S(_m(pos[k + 1] - pos[k])), 1.5)
    # eixos
    labs = m.xl if bm["axis"] == "x" else m.yl
    gg = m.gx if bm["axis"] == "x" else m.gy
    for a in pos:
        j = min(range(len(gg)), key=lambda i: abs(gg[i] - a))
        sh.text("AXE", (X(a), yt + 8.4), S(labs[j]), 1.7, "c", bold=True)
    # secção a meio vão (maior armadura) 1:20
    spm = max(bm["spans"], key=lambda x: x["bot"]["As"])
    tops = max((x for sp in bm["spans"] for x in (sp["top_l"], sp["top_r"])), key=lambda x: x["As"])
    sx0 = W_AREA - 44
    bw, hh = bm["b"] * 1000 / SX, bm["h"] * 1000 / SX
    sy0 = y0 + 6
    sh.rect("BA", sx0, sy0, sx0 + bw, sy0 + hh, 0.35, BA_LIGHT)
    c2 = (cov) * 1000 / SX
    sh.rect("ACIER", sx0 + c2, sy0 + c2, sx0 + bw - c2, sy0 + hh - c2, 0.25)
    for nb, phi, yy in ((spm["bot"]["n"], spm["bot"]["phi"], sy0 + c2 + 0.9), (max(2, tops["n"]), tops["phi"], sy0 + hh - c2 - 0.9)):
        nb = max(2, min(nb, 8))
        for i in range(nb):
            xx = sx0 + c2 + 0.9 + i * (bw - 2 * c2 - 1.8) / (nb - 1)
            sh.circle("ACIER", (xx, yy), max(phi / SX / 2, 0.45), 0.2, (0.8, 0.1, 0.1))
    sh.text("TEXTE", (sx0 + bw + 1.5, sy0 + hh - 1.5), S(_("sup. ", "sup. ") + tops["txt"]), 1.4)
    sh.text("TEXTE", (sx0 + bw + 1.5, sy0 + 0.6), S(_("inf. ", "inf. ") + spm["bot"]["txt"]), 1.4)
    sh.text("TEXTE", (sx0 + bw + 1.5, sy0 + hh / 2 - 0.6), S(spm["stirrups"]), 1.4)
    sh.dim((sx0, sy0), (sx0 + bw, sy0), -2.0, S(str(int(round(bm["b"] * 100)))), 1.4)
    sh.dim((sx0, sy0), (sx0, sy0 + hh), 2.0, S(str(int(round(bm["h"] * 100)))), 1.4)
    # séparateur
    sh.line("TEXTE", (0, y0), (W_AREA - 2, y0), 0.15)


def beam_sheets(m: Frame, r: dict) -> list:
    out = []
    groups = _slab_groups(r)
    for gi, g in enumerate(groups):
        fl = g[0]
        uniq = {}
        for bm in fl["beams"]:
            uniq.setdefault(_beam_sig(bm), []).append(bm)
        beams = [(v[0], [x["name"] for x in v]) for v in uniq.values()]
        row_h = 60.0
        per = int((H_AREA - 4) // row_h)
        chunks = [beams[i:i + per] for i in range(0, len(beams), per)]
        for ci, chunk in enumerate(chunks):
            code = f"EST-A{gi + 1}" + (chr(97 + ci) if len(chunks) > 1 else "")
            sh = _new(code, _("Ferraillage des poutres — dalle ", "Armaduras das vigas — laje ") + _group_name(g), 1000, (0, 0),
                      _("Élévations cotées, aciers, longueurs, cadres et sections", "Alçados cotados, armaduras, comprimentos, estribos e secções"), "detail_beam", fl["slab"].id)
            sh.dxf = False
            for k, (bm, names) in enumerate(chunk):
                Ltot = bm["pos"][-1] - bm["pos"][0]
                sx = next((s for s in HSCALES if Ltot * 1000 / s <= W_AREA - 62), HSCALES[-1])
                _draw_beam(sh, m, r, bm, names, H_AREA - (k + 1) * row_h - 2, row_h, sx)
            _note(sh, _(f"Béton {r['mat']['concrete']}, aciers {r['mat']['steel']}, enrobage 3 cm ; longueurs de barres L en m (ancrages droits / coudes inclus).",
                        f"Betão {r['mat']['concrete']}, aço {r['mat']['steel']}, recobrimento 3 cm; comprimentos dos varões L em m (amarrações incluídas)."),
                  _("Aciers inférieurs prolongés au-delà des appuis de 20 Ø (recouvrement 40 Ø décalé) ; ancrages d'extrémité par crosse.",
                    "Armadura inferior prolongada sobre os apoios (emenda de 40 Ø desfasada); amarrações de extremidade com dobra."),
                  _("Chapeaux sur appuis intermédiaires : 0,30 × portée de chaque côté ; appuis de rive : 0,25 × portée + crosse.",
                    "Armadura superior nos apoios intermédios: 0,30 × vão para cada lado; apoios de extremidade: 0,25 × vão + dobra."),
                  _("Zones critiques (DCM) : cadres resserrés sur max(h ; 0,50 m) à chaque nu d'appui.",
                    "Zonas críticas (NP EN 1998-1, DCM): estribos apertados em max(h; 0,50 m) junto a cada apoio."),
                  _("Poutres identiques regroupées (repères entre parenthèses).", "Vigas iguais agrupadas (referências entre parênteses)."))
            out.append(sh)
    return out


# ================================================================ pilares
def _bars_layout(n: int, b: float, h: float) -> list[tuple[float, float]]:
    """Positions normalisées (0..1) de n barres réparties sur le périmètre (4 coins + intermédiaires)."""
    n = max(4, n + (n % 2))
    nb = max(2, round((n / 2) * b / (b + h)) + 1)
    nh = max(2, (n - 2 * nb) // 2 + 2)
    while 2 * nb + 2 * nh - 4 < n:
        nh += 1
    pts = set()
    for i in range(nb):
        pts.add((i / (nb - 1), 0.0))
        pts.add((i / (nb - 1), 1.0))
    for j in range(nh):
        pts.add((0.0, j / (nh - 1)))
        pts.add((1.0, j / (nh - 1)))
    return sorted(pts)[:max(n, 4)] if len(pts) > n else sorted(pts)


def column_sheets(m: Frame, r: dict) -> list:
    types = {}
    for c in r["columns"]:
        key = (c["b"], c["h"], tuple((s["level"], s.get("txt"), s.get("ties")) for s in c["segs"]))
        types.setdefault(key, []).append(c)
    cells = []
    for t, (key, cs) in enumerate(sorted(types.items(), key=lambda kv: (-kv[0][0], kv[1][0]["name"]))):
        cmax = max(cs, key=lambda c: c["segs"][0]["NEd"])
        runs = []
        for sg in cmax["segs"]:
            sig = (sg.get("txt"), sg.get("ties"))
            if runs and runs[-1][0] == sig:
                runs[-1][1].append(sg)
            else:
                runs.append([sig, [sg]])
        for k, (_sig, segs) in enumerate(runs):
            lv = segs[0]["level_name"] if len(segs) == 1 else f"{segs[0]['level_name']} {_('à', 'a')} {segs[-1]['level_name']}"
            cells.append({"type": f"P{t + 1}", "names": [c["name"] for c in cs], "b": cs[0]["b"], "h": cs[0]["h"], "lv": lv, "s": segs[0],
                          "H": max(m.level(sg["level"]).height for sg in segs)})
    cw, ch = 57.0, 62.0
    per_row = int((W_AREA - 2) // cw)
    rows = int((H_AREA - 4) // ch)
    per = per_row * rows
    out = []
    chunks = [cells[i:i + per] for i in range(0, len(cells), per)] or [[]]
    for ci, chunk in enumerate(chunks):
        sh = _new("EST-P1" + (chr(97 + ci) if len(chunks) > 1 else ""), _("Ferraillage des poteaux", "Armaduras dos pilares"), 1000, (0, 0),
                  _("Sections armées par type et par tronçon — échelle 1:20", "Secções armadas por tipo e por troço — escala 1:20"), "detail_col")
        sh.dxf = False
        for k, c in enumerate(chunk):
            col, row = k % per_row, k // per_row
            x0 = col * cw + 2
            ytop = H_AREA - 2 - row * ch
            sh.rect("TEXTE", x0, ytop - ch + 2, x0 + cw - 2, ytop, 0.15)
            sh.text("TITRE", (x0 + 2, ytop - 4.2), S(f"{c['type']} — {int(round(c['b'] * 100))}×{int(round(c['h'] * 100))}"), 2.2, bold=True)
            sh.text("TEXTE", (x0 + 2, ytop - 7.4), S(c["lv"][:40]), 1.4)
            sh.text("TEXTE", (x0 + 2, ytop - 10.0), S(", ".join(c["names"])[:46]), 1.2)
            bw, hh = c["b"] * 1000 / SX, c["h"] * 1000 / SX
            sx0 = x0 + (cw - 2 - bw) / 2
            sy0 = ytop - 14 - hh - 4
            sh.rect("BA", sx0, sy0, sx0 + bw, sy0 + hh, 0.35, BA_LIGHT)
            cv = 0.030 * 1000 / SX
            sh.rect("ACIER", sx0 + cv, sy0 + cv, sx0 + bw - cv, sy0 + hh - cv, 0.25)
            s = c["s"]
            phi = int(s.get("phi") or 16)
            for (px, py) in _bars_layout(int(s.get("n") or 4), c["b"], c["h"]):
                xx = sx0 + cv + 0.9 + px * (bw - 2 * cv - 1.8)
                yy = sy0 + cv + 0.9 + py * (hh - 2 * cv - 1.8)
                sh.circle("ACIER", (xx, yy), max(phi / SX / 2, 0.45), 0.2, (0.8, 0.1, 0.1))
            sh.dim((sx0, sy0), (sx0 + bw, sy0), -2.0, S(str(int(round(c["b"] * 100)))), 1.4)
            sh.dim((sx0 + bw, sy0), (sx0 + bw, sy0 + hh), -2.0, S(str(int(round(c["h"] * 100)))), 1.4)
            yt = ytop - ch + 13.5
            sh.text("ACIER", (x0 + 2, yt), S(_("Longitudinaux : ", "Longitudinal: ") + str(s.get("txt", "—"))), 1.45, bold=True)
            sh.text("ACIER", (x0 + 2, yt - 2.9), S(_("Cadres courants : ", "Cintas correntes: ") + str(s.get("ties", "—"))), 1.35)
            lcr = max(c["h"], c["b"], c["H"] / 6, 0.45)
            sh.text("ACIER", (x0 + 2, yt - 5.6), S(_(f"Zones crit. {num(lcr, 2)} m : ", f"Zonas crít. {num(lcr, 2)} m: ") + str(s.get("ties_crit", "—"))), 1.35)
            Lb = c["H"] + _lb(phi)
            sh.text("TEXTE", (x0 + 2, yt - 8.3), S(_(f"Barres L = {_m(Lb)} m (recouvrement 40 Ø en pied)", f"Varões L = {_m(Lb)} m (emenda 40 Ø no pé)")), 1.25)
        _note(sh, _("Sections à l'échelle 1:20 ; enrobage 3 cm ; barres réparties sur le périmètre, une barre dans chaque angle tenue par un cadre.",
                    "Secções à escala 1:20; recobrimento 3 cm; varões distribuídos no perímetro, um varão em cada canto travado por cinta."),
              _("Cadres : 135° avec retours de 10 Ø ; épingles pour toute barre à plus de 15 cm d'une barre tenue.",
                "Cintas: dobras a 135° com 10 Ø; ganchos para todo o varão a mais de 15 cm de um varão travado."),
              _("Recouvrements en pied de tronçon (40 Ø), hors zones critiques si possible.", "Emendas no pé de cada troço (40 Ø), fora das zonas críticas se possível."))
        out.append(sh)
    return out


# ================================================================ sapatas
def footing_sheets(m: Frame, r: dict) -> list:
    f = r["foundations"]
    cols = {c["node"]: c for c in r["columns"]}
    types = {}
    for p in f["pads"]:
        types.setdefault((p["B"], p["h"], mesh_txt(p["mesh"])), []).append(p)
    items = sorted(types.items(), key=lambda kv: -kv[0][0])
    cw, ch = 95.0, 82.0
    per_row = int((W_AREA - 2) // cw)
    per = per_row * int((H_AREA - 4) // ch)
    out = []
    chunks = [items[i:i + per] for i in range(0, len(items), per)] or [[]]
    for ci, chunk in enumerate(chunks):
        sh = _new("EST-F1" + (chr(97 + ci) if len(chunks) > 1 else ""), _("Ferraillage des semelles", "Armaduras das sapatas"), 1000, (0, 0),
                  _("Plan et coupe armés par type (échelles indiquées)", "Planta e corte armados por tipo (escalas indicadas)"), "detail_fond")
        sh.dxf = False
        for k, ((B, hf, ms), ps) in enumerate(chunk):
            col, row = k % per_row, k // per_row
            x0 = col * cw + 2
            ytop = H_AREA - 2 - row * ch
            sh.rect("TEXTE", x0, ytop - ch + 2, x0 + cw - 2, ytop, 0.15)
            sh.text("TITRE", (x0 + 2, ytop - 4.2), S(f"S{len(out) * per + k + 1} — {num(B)} × {num(B)} × {num(hf)} m"), 2.2, bold=True)
            sh.text("TEXTE", (x0 + 2, ytop - 7.4), S(", ".join(p["name"] for p in ps)[:80]), 1.25)
            c = cols.get(ps[0]["node"])
            a = (c["b"] if c else 0.30)
            sc = 50
            Bm = B * 1000 / sc
            if Bm > 38:
                sc = 100
                Bm = B * 1000 / sc
            # planta
            px0, py0 = x0 + 4, ytop - 12 - Bm
            sh.rect("FOND", px0, py0, px0 + Bm, py0 + Bm, 0.4, FOND)
            am = a * 1000 / sc
            sh.rect("BA", px0 + (Bm - am) / 2, py0 + (Bm - am) / 2, px0 + (Bm + am) / 2, py0 + (Bm + am) / 2, 0.3, BA, hatch="ba")
            mesh = ps[0]["mesh"]
            n = max(3, int(B / mesh["s"]))
            for i in range(n + 1):
                t = 0.05 * 1000 / sc + i * (Bm - 0.10 * 1000 / sc) / n
                sh.line("ACIER", (px0 + t, py0 + 0.6), (px0 + t, py0 + Bm - 0.6), 0.15)
                sh.line("ACIER", (px0 + 0.6, py0 + t), (px0 + Bm - 0.6, py0 + t), 0.15)
            sh.dim((px0, py0), (px0 + Bm, py0), -2.2, S(num(B)), 1.4)
            sh.text("TEXTE", (px0, py0 - 6.0), S(_(f"plan 1:{sc}", f"planta 1:{sc}")), 1.3)
            # corte
            cx0 = px0 + Bm + 8
            hm = hf * 1000 / sc
            cy0 = ytop - 14 - hm - 18
            sh.rect("FOND", cx0 - 0.05 * 1000 / sc, cy0 - 0.10 * 1000 / sc, cx0 + Bm + 0.05 * 1000 / sc, cy0, 0.2, (0.8, 0.8, 0.8))
            sh.rect("FOND", cx0, cy0, cx0 + Bm, cy0 + hm, 0.4, FOND)
            sh.rect("BA", cx0 + (Bm - am) / 2, cy0 + hm, cx0 + (Bm + am) / 2, cy0 + hm + 14, 0.3, BA)
            cv = 0.05 * 1000 / sc
            sh.poly("ACIER", [(cx0 + cv, cy0 + cv + 2.4), (cx0 + cv, cy0 + cv), (cx0 + Bm - cv, cy0 + cv), (cx0 + Bm - cv, cy0 + cv + 2.4)], 0.45)
            cb = c["segs"][0] if c else {}
            for side in (-1, 1):
                xx = cx0 + Bm / 2 + side * (am / 2 - 0.6)
                sh.poly("ACIER", [(xx + side * 3.0, cy0 + cv + 0.6), (xx, cy0 + cv + 0.6), (xx, cy0 + hm + 14)], 0.4)
            sh.dim((cx0, cy0), (cx0 + Bm, cy0), -3.2, S(num(B)), 1.3)
            sh.dim((cx0 + Bm, cy0), (cx0 + Bm, cy0 + hm), -2.0, S(num(hf)), 1.3)
            sh.text("TEXTE", (cx0, cy0 - 7.5), S(_(f"coupe 1:{sc} · béton de propreté 10 cm", f"corte 1:{sc} · betão de limpeza 10 cm")), 1.3)
            yt = ytop - ch + 13
            sh.text("ACIER", (x0 + 2, yt), S(_("Nappe inférieure 2 sens : ", "Malha inferior 2 direções: ") + ms), 1.45, bold=True)
            sh.text("ACIER", (x0 + 2, yt - 2.8), S(_(f"Barres L = {_m(B - 0.10 + 2 * 0.15)} m avec retours 15 cm", f"Varões L = {_m(B - 0.10 + 2 * 0.15)} m com dobras de 15 cm")), 1.3)
            sh.text("ACIER", (x0 + 2, yt - 5.6), S(_("Attentes poteau : ", "Arranques do pilar: ") + str(cb.get("txt", "—")) + _(" avec pattes 30 cm", " com patas de 30 cm")), 1.3)
            sh.text("TEXTE", (x0 + 2, yt - 8.4), S(_(f"N ELS max {int(round(max(p['N'] for p in ps)))} kN · σ ≤ {num(f['sigma_kpa'] / 1000, 2)} MPa",
                                                     f"N ELS máx {int(round(max(p['N'] for p in ps)))} kN · σ ≤ {num(f['sigma_kpa'] / 1000, 2)} MPa")), 1.3)
        _note(sh, _("Enrobage 5 cm sur béton de propreté ; nappe inférieure dans les deux directions, retours relevés 15 cm.",
                    "Recobrimento 5 cm sobre betão de limpeza; malha inferior nas duas direções, dobras de 15 cm."),
              _("Attentes du poteau ancrées jusqu'à la nappe inférieure avec pattes ; cadres de maintien dans la semelle.",
                "Arranques do pilar amarrados até à malha inferior com patas; cintas de posicionamento na sapata."),
              _("Fond de fouille à réceptionner par le géotechnicien avant bétonnage.", "Fundo da escavação a receber pelo geotécnico antes da betonagem."))
        out.append(sh)
    return out


# ================================================================ térmica / climatização
def thermal_sheets(m: Frame, t: dict) -> list:
    if not t:
        return []
    pt = t["country"] == "PT"
    rows = []
    for x in t["units"]:
        if pt:
            rows.append([x["name"], x["level_name"], x["typology"], num(x["Ap"], 1), num(x["Nic"], 1), num(x["Ni"], 1), num(x["Ntc"], 1),
                         num(x["Nt"], 1), num(x["RNt"], 2), x["classe"], num(x["phi_w"] / 1000, 2),
                         "OK" if x["ok"] else ", ".join(x["fails"])[:30]])
        else:
            rows.append([x["name"], x["level_name"], x["typology"], num(x["Ap"], 1), num(x["bch"], 1), num(x["phi_w"] / 1000, 2), "—"])
    if pt:
        head = [("Fração", 26), ("Piso", 30), ("Tip.", 12), ("Ap (m²)", 16), ("Nic\n(kWh/m².a)", 20), ("Ni", 16), ("Ntc\n(kWhEP/m².a)", 22),
                ("Nt", 16), ("RNt", 14), ("Classe", 14), ("Φ aquec.\n(kW)", 18), ("Requisitos", 40)]
        title, sub = "Estudo térmico — pré-certificado REH por fração", "Necessidades de aquecimento, energia primária, classe energética e potência de projeto"
    else:
        head = [("Logement", 30), ("Niveau", 34), ("Typo.", 14), ("Su (m²)", 18), ("Besoin chauffage\n(kWh/m².an)", 32), ("Φ chauffage\n(kW)", 22), ("RE2020", 30)]
        title, sub = "Étude thermique — déperditions et besoins par logement", "Puissances de chauffage pour le dimensionnement des émetteurs"
    return table_sheets("TER-01", title, sub, head, rows, "thermal", notes=t["hyp"])


def hvac_plans(m: Frame, t: dict, r: dict) -> list:
    if not t:
        return []
    from .thermal import emitters
    em = {x["id"]: x for x in emitters(t)["rows"]}
    out = []
    lv_groups = []
    for lv in m.levels:
        us = m.units_on(lv.id)
        if not us:
            continue
        key = tuple((un.name, round(un.x0, 2), round(un.y0, 2), round(un.x1, 2), round(un.y1, 2), round(em[un.id]["kw"], 1)) for un in us)
        if lv_groups and lv_groups[-1][0] == key:
            lv_groups[-1][1].append(lv.id)
        else:
            lv_groups.append((key, [lv.id]))
    pt = m.country == "PT"
    for k, (_key, lids) in enumerate(lv_groups):
        name = m.level(lids[0]).name if len(lids) == 1 else f"{m.level(lids[0]).name} {_('à', 'a')} {m.level(lids[-1]).name}"
        sh = _plan_sheet(m, f"AVAC-{k + 1:02d}", _("Chauffage, ventilation — ", "Climatização e ventilação — ") + name,
                         _("Puissance de chauffage par logement, émetteurs, VMC", "Potência de aquecimento por fração, emissores, ventilação"), "hvac", lids[0])
        grid(sh, m, dims=False)
        outline(sh, m, 0.5)
        draw_cores(sh, m, cut=False)
        draw_columns(sh, m, r, tags=False)
        for i, un in enumerate(m.units_on(lids[0])):
            x = em[un.id]
            sh.rect("CHAUF_A", un.x0 + 0.15, un.y0 + 0.15, un.x1 - 0.15, un.y1 - 0.15, 0.35, None)
            cx, cy = un.center
            sh.text("TEXTE", (cx, cy + u(sh, 5)), S(f"{un.name} ({un.typology})"), 1.9, "c", bold=True)
            sh.text("CHAUF_A", (cx, cy + u(sh, 2)), S(f"Φ = {num(x['kw'], 2)} kW" + (f" · {_('classe', 'classe')} {x['classe']}" if pt else "")), 1.6, "c", bold=True)
            sh.text("CHAUF_A", (cx, cy - u(sh, 0.8)), S(f"{x['system']} : {x['units_txt']}"), 1.4, "c")
            sh.text("VMC_E", (cx, cy - u(sh, 3.4)), S(_("VMC hygro B : extraction cuisine + SdB/WC", "VMC: extração cozinha + instalações sanitárias")), 1.3, "c")
            # unidade exterior / coletor sur la façade la plus proche
            ex = un.x0 + 0.6 if abs(un.x0 - m.gx[0]) < abs(un.x1 - m.gx[-1]) else un.x1 - 0.6
            sh.rect("CHAUF_A", ex - 0.35, cy - 0.25, ex + 0.35, cy + 0.25, 0.3, (1.0, 0.92, 0.9))
            sh.text("CHAUF_A", (ex, cy - u(sh, 2.6)), S(_("UE", "UE")), 1.2, "c")
        for ri in [x for x in m.risers if x.get("kind") == "VENT"]:
            sh.circle("VMC_E", (float(ri["x"]), float(ri["y"])), u(sh, 1.6), 0.35, (0.92, 0.86, 0.96))
            sh.text("VMC_E", (float(ri["x"]) + u(sh, 2), float(ri["y"])), S(str(ri.get("id") or "VMC")), 1.3)
        grid_dims(sh, m)
        _note(sh, _("Puissances de projet issues de l'étude thermique (TER-01), majoration de relance 15 % pour le choix des émetteurs.",
                    "Potências de projeto do estudo térmico (TER-01), majoração de 15 % para a escolha dos emissores."),
              _("Unités extérieures (UE) en façade / loggia ; condensats raccordés aux EU.", "Unidades exteriores (UE) em fachada / varanda; condensados ligados aos esgotos."),
              _("Extraction par conduit collectif en gaine technique jusqu'en toiture ; entrées d'air dans les pièces sèches.",
                "Extração por conduta coletiva em courette até à cobertura; admissão de ar nos compartimentos principais."),
              _("Tracés de principe : à développer au projet d'exécution AVAC.", "Traçados de princípio: a desenvolver no projeto de execução AVAC."))
        out.append(sh)
    return out
