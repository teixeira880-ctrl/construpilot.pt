"""Planches fluides et courants forts « comme un BET » : chaque réseau est DESSINÉ et COTÉ sur le fond de plan.

- Électricité : points normalisés, circuits numérotés tirés depuis la GTL / la colonne (conduits ICTA sous chape),
  liaisons de commande, hauteurs de pose, GTL et colonne cotées, schéma unifilaire du tableau ;
- Plomberie : appareils sanitaires dessinés et cotés (axes des attentes), pieuvre EF/ECS depuis la gaine,
  évacuations avec diamètre et pente vers les chutes, réservations dans les planchers ;
- Ventilation : bouches avec débits, conduits de chaque bouche jusqu'au plénum de la gaine, caisson, prise d'air / rejet ;
- Chauffage : boucles de plancher chauffant dessinées pièce par pièce (pas, longueur, débit), collecteur coté,
  schéma hydraulique PAC, coupe-type du plancher chauffant.
"""
from __future__ import annotations

import math

from .draw import Sheet, trunc
from .model import Model
from .sheets import _new, base_plan, fmt

EL_FILL = (1.0, 0.93, 0.80)


def _k(r):
    t = r["type"]
    return {"sdb": "salle_eau", "sde": "salle_eau", "degagement": "circulation"}.get(t, t)


def _room_at(m: Model, lid: str, x: float, y: float):
    for r in m.rooms(lid):
        for p in [r] + r.get("parts", []):
            if p["x0"] - 0.02 <= x <= p["x1"] + 0.02 and p["y0"] - 0.02 <= y <= p["y1"] + 0.02:
                return r
    return None


def _route(sh: Sheet, layer: str, a, b, lw=0.3, dash=None, first="h"):
    """Tracé orthogonal a → b (d'abord horizontal si first = 'h')."""
    if abs(a[0] - b[0]) < 1e-3 or abs(a[1] - b[1]) < 1e-3:
        sh.line(layer, a, b, lw=lw, dash=dash)
        return [a, b]
    mid = (b[0], a[1]) if first == "h" else (a[0], b[1])
    sh.poly(layer, [a, mid, b], lw=lw, dash=dash)
    return [a, mid, b]


def _gt(sh: Sheet, g: dict, label=True, resa=False):
    x0, y0 = g["x"] - g["w"] / 2, g["y"] - g["d"] / 2
    sh.rect("GAINE", x0, y0, x0 + g["w"], y0 + g["d"], lw=0.45, fill=(0.86, 0.94, 0.89))
    sh.line("GAINE", (x0, y0), (x0 + g["w"], y0 + g["d"]), lw=0.15)
    sh.line("GAINE", (x0, y0 + g["d"]), (x0 + g["w"], y0), lw=0.15)
    if label:
        sh.text("GAINE", (g["x"], y0 - 0.17), f"GT {int(g['w']*100)}×{int(g['d']*100)}", size=1.35, anchor="c", bold=True)
    if resa:
        sh.rect("RESA", x0 - 0.05, y0 - 0.05, x0 + g["w"] + 0.05, y0 + g["d"] + 0.05, lw=0.35, dash="dashed")


def _locate(sh: Sheet, m: Model, lid: str, x: float, y: float, off=0.18, size=1.2):
    """Cotes d'implantation d'un point depuis les deux nus de murs les plus proches de la pièce qui le contient."""
    r = _room_at(m, lid, x, y)
    if not r:
        return
    wx = r["x0"] if (x - r["x0"]) <= (r["x1"] - x) else r["x1"]
    wy = r["y0"] if (y - r["y0"]) <= (r["y1"] - y) else r["y1"]
    if abs(x - wx) > 0.04:
        sh.dim((min(wx, x), y + off), (max(wx, x), y + off), 0, size=size)
    if abs(y - wy) > 0.04:
        sh.dim((x + off, min(wy, y)), (x + off, max(wy, y)), 0, size=size)


def _sheet(code, title, subtitle, m, lid, rooms=True):
    sh = _new(code, title, subtitle=subtitle)
    base_plan(sh, m, lid, rooms=rooms, dims=False, axes=False, light=True)
    return sh


# ================================================================ électricité
def number_circuits(e: dict) -> dict:
    """Numéro de départ (C1…Cn) par circuit, dans l'ordre des interrupteurs différentiels du tableau."""
    num, k = {}, 1
    for rcd in e["rcds"]:
        for name in rcd["circuits"]:
            num[name] = f"C{k}"
            k += 1
    for c in e["circuits"]:
        if c["name"] not in num:
            num[c["name"]] = f"C{k}"
            k += 1
    return num


def _assign(e: dict, lid: str, lname: str):
    """Points du niveau → circuit (prises par 12, éclairage par 8, spécialisés un par un)."""
    pts = next(l["points"] for l in e["levels"] if l["level"] == lid)
    circ = {}
    pcs = [p for p in pts if p["kind"] == "PC"]
    pls = [p for p in pts if p["kind"] == "PL"]
    for i, p in enumerate(pcs):
        circ.setdefault(f"Prises {lname} n°{i // 12 + 1}", []).append(p)
    for i, p in enumerate(pls):
        circ.setdefault(f"Éclairage {lname} n°{i // 8 + 1}", []).append(p)
    from .mep import SPEC_CIRCUITS
    for p in pts:
        if p["kind"] == "SPEC" and p["code"] in SPEC_CIRCUITS:
            circ.setdefault(f"{SPEC_CIRCUITS[p['code']][0]} ({p['room']})", []).append(p)
    return pts, circ


def _chain_order(start, pts):
    rest, cur, out = list(pts), start, []
    while rest:
        nxt = min(rest, key=lambda p: abs(p["x"] - cur[0]) + abs(p["y"] - cur[1]))
        out.append(nxt)
        rest.remove(nxt)
        cur = (nxt["x"], nxt["y"])
    return out


def elec_level(m: Model, e: dict, hv: dict, lid: str, code: str) -> Sheet:
    lv = m.level(lid)
    sh = _sheet(code, f"Électricité — {lv.name}", "NF C 15-100 : circuits numérotés, cheminements sous fourreaux ICTA, hauteurs de pose", m, lid)
    num = number_circuits(e)
    pts, circ = _assign(e, lid, lv.name)
    gt = hv["gtl"]
    col = (gt["x"], gt["y"])
    if gt["level"] == lid:
        sh.rect("ELEC", gt["x"] - 0.12, gt["y"] - 0.30, gt["x"] + 0.12, gt["y"] + 0.30, lw=0.6, fill=(1.0, 0.85, 0.55))
        sh.text("ELEC", (gt["x"] - 0.20, gt["y"] + 0.36), "GTL — tableau + coffret de communication", size=1.45, anchor="r", bold=True)
        sh.text("ELEC", (gt["x"] - 0.20, gt["y"] + 0.12), "larg. 0,60 · h 1,80 maxi organes de commande", size=1.15, anchor="r")
        _locate(sh, m, lid, gt["x"], gt["y"] - 0.30, off=-0.30)
    else:
        sh.circle("ELEC", col, 0.09, lw=0.5, fill=(1.0, 0.85, 0.55))
        sh.text("ELEC", (gt["x"] - 0.16, gt["y"] + 0.16), "colonne depuis GTL (fourreaux ICTA Ø25 en doublage)", size=1.15, anchor="r", bold=True)
        _locate(sh, m, lid, gt["x"], gt["y"], off=-0.25)
    # circuits : un tracé par départ, depuis la GTL / la colonne
    shift = 0.0
    for name, plist in circ.items():
        cid = num.get(name, "C?")
        start = (col[0] - 0.06 - shift, col[1] - 0.25 + shift)
        shift = (shift + 0.035) % 0.21
        prev = start
        for p in _chain_order(start, plist):
            _route(sh, "ELEC", prev, (p["x"], p["y"]), lw=0.18, dash="dashed" if p["kind"] == "PL" else None,
                   first="v" if abs(prev[1] - p["y"]) > abs(prev[0] - p["x"]) else "h")
            sh.text("ELEC", (p["x"] + 0.12, p["y"] - 0.20), cid, size=1.05, bold=True)
            prev = (p["x"], p["y"])
    # liaisons de commande (interrupteur → point lumineux de la pièce)
    for p in pts:
        if p["kind"] == "INT":
            pl = [q for q in pts if q["kind"] == "PL" and q["room"] == p["room"]]
            for q in pl:
                sh.poly("ELEC", [(p["x"], p["y"]), ((p["x"] + q["x"]) / 2 + 0.15, (p["y"] + q["y"]) / 2 + 0.15), (q["x"], q["y"])], lw=0.12, dash="dotted")
    # symboles par-dessus les tracés
    for p in pts:
        x, y = p["x"], p["y"]
        if p["kind"] == "PC":
            sh.circle("ELEC", (x, y), 0.10, lw=0.35, fill=(1, 1, 1))
            sh.line("ELEC", (x - 0.10, y), (x + 0.10, y), lw=0.35)
            r = _room_at(m, lid, x, y)
            if r and _k(r) == "cuisine":
                sh.text("ELEC", (x - 0.12, y + 0.13), "h 1,10", size=0.95, anchor="r")
        elif p["kind"] == "PL":
            sh.circle("ELEC", (x, y), 0.13, lw=0.35, fill=(1, 1, 1))
            sh.line("ELEC", (x - 0.09, y - 0.09), (x + 0.09, y + 0.09), lw=0.35)
            sh.line("ELEC", (x - 0.09, y + 0.09), (x + 0.09, y - 0.09), lw=0.35)
        elif p["kind"] == "INT":
            sh.circle("ELEC", (x, y), 0.06, lw=0.35, fill=(0.85, 0.45, 0.0))
            sh.line("ELEC", (x, y), (x + 0.15, y + 0.15), lw=0.35)
        elif p["kind"] == "RJ45":
            sh.poly("ELEC", [(x - 0.09, y - 0.07), (x + 0.09, y - 0.07), (x, y + 0.09)], lw=0.35, closed=True, fill=(1, 1, 1))
        elif p["kind"] == "SPEC":
            sh.rect("ELEC", x - 0.10, y - 0.10, x + 0.10, y + 0.10, lw=0.35, fill=EL_FILL)
            lbl = {"plaque_32A": "plaque 32 A", "four_20A": "four", "lave_vaisselle_20A": "LV", "lave_linge_20A": "LL", "seche_linge_20A": "SL",
                   "chauffe_eau_20A": "CET", "pac_32A": "PAC", "vmc": "VMC", "seche_serviettes": "sèche-serv.", "porte_garage": "porte gar."}.get(p["code"], p["code"][:10])
            sh.text("ELEC", (x - 0.14, y - 0.04), lbl, size=1.1, anchor="r")
    # thermostats d'ambiance (plancher chauffant) : 1 par pièce chauffée de vie
    if hv.get("pc"):
        for r in m.rooms(lid):
            if _k(r) in ("sejour", "chambre", "bureau", "salle_eau"):
                x, y = r["x0"] + 0.45, r["y0"] + 0.12
                sh.rect("ELEC", x - 0.08, y - 0.08, x + 0.08, y + 0.08, lw=0.35, fill=(1, 1, 1))
                sh.text("ELEC", (x, y - 0.045), "T", size=1.1, anchor="c", bold=True)
    names = [c for c in e["circuits"] if c["level"] == lid]
    sh.notes = [f"{num.get(c['name'], '')} — {c['name']} : {c['breaker']} A · {c['section']} mm² · {c['points']} pt(s) · {c.get('rcd', '')}" for c in names][:14] + [
        "Conduits ICTA Ø20 (1,5 mm²) / Ø25 (2,5 et 6 mm²) sous chape ou en doublage ; boîtes d'encastrement étanches à l'air.",
        "Hauteurs (axe) : prises 0,30 ; cuisine plan de travail 1,10 ; commandes et thermostats 0,90 à 1,30 ; salles d'eau hors volumes 0-1-2."]
    sh.legend = [("PC", "Prise 2P+T 16 A"), ("PL", "Point lumineux DCL"), ("INT", "Commande (interrupteur)"), ("RJ45", "Prise RJ45 grade 2TV"),
                 ("SPEC", "Sortie de câble / circuit spécialisé"), ("GTL", "GTL / tableau"), ("TH", "Thermostat d'ambiance"),
                 ("LINE:ELEC::0.5", "Circuit prises / spécialisé"), ("LINE:ELEC:dashed:0.5", "Circuit éclairage"), ("LINE:ELEC:dotted:0.4", "Liaison de commande")]
    return sh


def elec_unifilaire(m: Model, e: dict, hv: dict, code: str) -> Sheet:
    """Schéma unifilaire du tableau de répartition : AGCP, parafoudre, interrupteurs différentiels, disjoncteurs divisionnaires."""
    sh = Sheet(code, "Schéma unifilaire du tableau de répartition", 1000, origin=(0, 0), subtitle=e["standard"])
    num = number_circuits(e)
    circ_by = {c["name"]: c for c in e["circuits"]}
    order = [(rcd, [circ_by[n] for n in rcd["circuits"] if n in circ_by]) for rcd in e["rcds"]]
    n = sum(len(cs) for _, cs in order)
    X0, X1 = 26.0, 282.0
    pitch = min(11.0, (X1 - X0 - 6 * len(order)) / max(n, 1))
    ytop, ybus, yid, ysub, ybrk, yend = 210.0, 190.0, 168.0, 150.0, 132.0, 96.0
    sh.text("TITRE", (0, 222), "TABLEAU DE RÉPARTITION — " + e["panel"]["head"], size=3.2, bold=True)
    # arrivée + AGCP
    sh.line("ELEC", (8, ytop + 8), (8, ybus), lw=0.9)
    sh.rect("ELEC", 3, ytop - 9, 13, ytop + 1, lw=0.6, fill=EL_FILL)
    sh.line("ELEC", (3, ytop - 9), (13, ytop + 1), lw=0.3)
    sh.text("TEXTE", (15, ytop - 2), "AGCP 500 mA — 15/45 A", size=2.0, bold=True)
    sh.text("TEXTE", (15, ytop - 6), "réglage selon abonnement (à confirmer Enedis)", size=1.6)
    sh.text("TEXTE", (11, ytop + 8), "Arrivée Enedis (CCPI en limite de propriété)", size=1.7)
    sh.line("ELEC", (8, ybus), (X1, ybus), lw=1.2)
    sh.text("TEXTE", (X1 - 2, ybus + 2), "jeu de barres / peignes", size=1.5, anchor="r")
    # parafoudre + contacteur HP/HC
    for k, (lbl, sub) in enumerate((("Parafoudre type 2", "Iₙ 5 kA · 1P+N (zone AQ2)"), ("Contacteur HC", "25 A · ballon ECS / CET"))):
        x = 80 + k * 40
        sh.line("ELEC", (x, ybus), (x, ybus + 8), lw=0.5)
        sh.rect("ELEC", x - 3, ybus + 8, x + 3, ybus + 14, lw=0.5, fill=(1, 1, 1))
        sh.text("TEXTE", (x + 4, ybus + 12), lbl, size=1.6, bold=True)
        sh.text("TEXTE", (x + 4, ybus + 9), sub, size=1.4)
    x = X0 + 4
    for rcd, cs in order:
        if not cs:
            continue
        xa, xb = x, x + pitch * (len(cs) - 1)
        xm = (xa + xb) / 2
        sh.line("ELEC", (xm, ybus), (xm, yid + 6), lw=0.7)
        sh.rect("ELEC", xm - 5, yid - 4, xm + 5, yid + 6, lw=0.6, fill=(0.93, 0.96, 1.0))
        sh.circle("ELEC", (xm, yid + 1), 2.2, lw=0.4)
        sh.text("ELEC", (xm, yid - 2.6), "ID", size=1.6, anchor="c", bold=True)
        sh.text("TEXTE", (xm + 6, yid + 3), f"{rcd['id']} — {rcd['rating']} A 30 mA type {rcd['type']}", size=1.6, bold=True)
        sh.line("ELEC", (xm, yid - 4), (xm, ysub), lw=0.7)
        sh.line("ELEC", (xa, ysub), (xb, ysub), lw=0.9)
        for c in cs:
            sh.line("ELEC", (x, ysub), (x, ybrk + 5), lw=0.45)
            sh.rect("ELEC", x - 1.8, ybrk - 3, x + 1.8, ybrk + 5, lw=0.45, fill=(1, 1, 1))
            sh.line("ELEC", (x - 1.8, ybrk - 3), (x + 1.8, ybrk + 5), lw=0.25)
            sh.line("ELEC", (x, ybrk - 3), (x, yend), lw=0.45)
            sh.text("ELEC", (x, ybrk + 6.2), num.get(c["name"], ""), size=1.5, anchor="c", bold=True)
            sh.text("TEXTE", (x + 0.6, yend - 2), trunc(f"{c['breaker']} A · {c['section']} mm² · {c['name']}", 46), size=1.55, rot=-90)
            sh.circle("ELEC", (x, yend), 0.6, lw=0.3, fill=(1, 1, 1))
            x += pitch
        x += 6
    pac = hv["pac"]
    sh.text("TEXTE", (0, 20), f"Coffret {e['panel']['rows']} rangées × 13 modules — {e['panel']['modules']} modules utilisés + {e['panel']['spare']} — {e['panel']['location']}", size=1.9)
    sh.text("TEXTE", (0, 15), trunc(e["panel"]["earth"], 175), size=1.7)
    sh.text("TEXTE", (0, 10), trunc(f"{pac['label']} : {pac['power']}", 175), size=1.7)
    sh.text("TEXTE", (0, 5), "Différentiels type A : plaque de cuisson, lave-linge, PAC, IRVE (type F ou A-EV) ; parafoudre obligatoire si PAC/équipement de sécurité (NF C 15-100 §443).", size=1.7)
    sh.legend = [("LINE:ELEC::1.2", "Jeu de barres"), ("LINE:ELEC::0.45", "Départ divisionnaire")]
    sh.dxf = False
    return sh


# ================================================================ plomberie
def _fixture_symbol(sh: Sheet, f: dict):
    x, y, w, d, wall = f["x"], f["y"], f.get("w") or 0.5, f.get("d") or 0.5, f.get("wall") or "y1"
    hor = wall in ("y0", "y1")
    W_, D_ = (w, d) if hor else (d, w)
    x0, y0, x1, y1 = x - W_ / 2, y - D_ / 2, x + W_ / 2, y + D_ / 2
    fx = f["fixture"]
    fill = (0.95, 0.97, 1.0)
    if fx == "douche":
        sh.rect("PLOMB_EF", x0, y0, x1, y1, lw=0.35, fill=fill)
        sh.line("PLOMB_EF", (x0, y0), (x1, y1), lw=0.12)
        sh.line("PLOMB_EF", (x0, y1), (x1, y0), lw=0.12)
        sh.circle("PLOMB_EV", (x, y), 0.04, lw=0.3)
    elif fx == "baignoire":
        sh.rect("PLOMB_EF", x0, y0, x1, y1, lw=0.35, fill=fill)
        i = 0.07
        sh.rect("PLOMB_EF", x0 + i, y0 + i, x1 - i, y1 - i, lw=0.2)
        sh.circle("PLOMB_EV", (x0 + 0.2 if hor else x, y if hor else y0 + 0.2), 0.035, lw=0.3)
    elif fx == "wc":
        # réservoir contre le mur + cuvette ovale
        bw = 0.40
        if wall == "y1":
            sh.rect("PLOMB_EF", x - bw / 2, y1 - 0.18, x + bw / 2, y1, lw=0.35, fill=fill)
            sh.poly("PLOMB_EF", _oval(x, y1 - 0.40, 0.18, 0.24), lw=0.35, closed=True, fill=fill)
        elif wall == "y0":
            sh.rect("PLOMB_EF", x - bw / 2, y0, x + bw / 2, y0 + 0.18, lw=0.35, fill=fill)
            sh.poly("PLOMB_EF", _oval(x, y0 + 0.40, 0.18, 0.24), lw=0.35, closed=True, fill=fill)
        elif wall == "x1":
            sh.rect("PLOMB_EF", x1 - 0.18, y - bw / 2, x1, y + bw / 2, lw=0.35, fill=fill)
            sh.poly("PLOMB_EF", _oval(x1 - 0.40, y, 0.24, 0.18), lw=0.35, closed=True, fill=fill)
        else:
            sh.rect("PLOMB_EF", x0, y - bw / 2, x0 + 0.18, y + bw / 2, lw=0.35, fill=fill)
            sh.poly("PLOMB_EF", _oval(x0 + 0.40, y, 0.24, 0.18), lw=0.35, closed=True, fill=fill)
    elif fx in ("lavabo", "lave_mains"):
        sh.rect("PLOMB_EF", x0, y0, x1, y1, lw=0.3, fill=fill)
        sh.poly("PLOMB_EF", _oval(x, y, W_ * 0.36, D_ * 0.32), lw=0.25, closed=True)
    elif fx == "evier":
        sh.rect("PLOMB_EF", x0, y0, x1, y1, lw=0.3, fill=fill)
        if hor:
            sh.rect("PLOMB_EF", x0 + 0.08, y0 + 0.08, x - 0.04, y1 - 0.08, lw=0.2)
        else:
            sh.rect("PLOMB_EF", x0 + 0.08, y0 + 0.08, x1 - 0.08, y - 0.04, lw=0.2)
    else:   # lave-linge / lave-vaisselle
        sh.rect("PLOMB_EF", x0, y0, x1, y1, lw=0.3, fill=(1, 1, 1))
        sh.circle("PLOMB_EF", (x, y), min(W_, D_) * 0.32, lw=0.2)
    sh.text("PLOMB_EF", (x, y - 0.03), {"lave_vaisselle": "LV", "lave_linge": "LL", "lave_mains": "LM"}.get(fx, ""), size=1.1, anchor="c", bold=True)


def _oval(cx, cy, rx, ry, n=20):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _outlet(f: dict):
    """Point d'attente (alimentation + évacuation) au mur derrière l'appareil."""
    x, y, w, d, wall = f["x"], f["y"], f.get("w") or 0.5, f.get("d") or 0.5, f.get("wall") or "y1"
    return {"y1": (x, y + d / 2 - 0.05), "y0": (x, y - d / 2 + 0.05), "x1": (x + d / 2 - 0.05, y), "x0": (x - d / 2 + 0.05, y)}[wall]


def plumb_level(m: Model, p: dict, hv: dict, lid: str, code: str) -> Sheet:
    lv = m.level(lid)
    first = lid == m.levels[0].id
    sh = _sheet(code, f"Plomberie sanitaire — {lv.name}",
                "Attentes cotées, alimentation EF/ECS en pieuvre (multicouche sous fourreau), évacuations PVC avec pentes, chutes Ø100", m, lid)
    g = hv["gaine"]
    _gt(sh, g, resa=not first)
    at_nourrice = first and p["nourrice"].get("level", lid) == lid
    fx = [f for f in p["fixtures"] if f["level"] == lid and f["fixture"] != "robinet_ext"]
    risers = set()
    for k, f in enumerate(fx):
        _fixture_symbol(sh, f)
        o = _outlet(f)
        stk = next((s for s in p["stacks"] if s["id"] == f["stack"]), p["stacks"][0] if p["stacks"] else {"x": g["x"], "y": g["y"]})
        if at_nourrice:
            src = (p["nourrice"]["x"], p["nourrice"]["y"])
        else:                                    # montée EF/ECS accolée à la chute qui dessert l'appareil
            src = (stk["x"] + 0.22, stk["y"])
            risers.add((round(src[0], 2), round(src[1], 2), stk.get("id", "")))
        off = 0.035 * (k % 6)
        # EF (trait plein bleu) et ECS (trait plein rouge), en parallèle
        _route(sh, "PLOMB_EF", (src[0] - off, src[1] - off), (o[0] - 0.03, o[1]), lw=0.45, first="h" if f.get("wall") in ("x0", "x1") else "v")
        if f["ecs"]:
            _route(sh, "PLOMB_ECS", (src[0] - off + 0.05, src[1] - off + 0.05), (o[0] + 0.03, o[1]), lw=0.45,
                   first="h" if f.get("wall") in ("x0", "x1") else "v")
        # robinet d'arrêt à l'attente
        sh.poly("PLOMB_EF", [(o[0] - 0.06, o[1] - 0.04), (o[0] + 0.06, o[1] + 0.04), (o[0] + 0.06, o[1] - 0.04), (o[0] - 0.06, o[1] + 0.04)], lw=0.25, closed=True)
        # évacuation vers la chute
        st = next((s for s in p["stacks"] if s["id"] == f["stack"]), None)
        if st:
            path = _route(sh, "PLOMB_EV", o, (st["x"], st["y"]), lw=1.0 if f.get("d_evac", 40) >= 100 else 0.7,
                          first="h" if f.get("wall") in ("y0", "y1") else "v")
            a, b = path[0], path[1]
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            horiz = abs(a[1] - b[1]) < 1e-3
            sh.text("PLOMB_EV", (mx, my + (0.06 if horiz else 0)) if horiz else (mx + 0.07, my), f"Ø{f.get('d_evac', 40)} — 2 %",
                    size=1.0, anchor="c", rot=0 if horiz else 90)
        sh.text("PLOMB_EF", (o[0] + 0.10, o[1] + 0.10), f["alim"].replace("multicouche ", "MC "), size=0.95)
        _locate(sh, m, lid, o[0], o[1], off=0.22, size=1.05)
    for rx, ry, sid in risers:
        sh.rect("PLOMB_EF", rx - 0.06, ry - 0.06, rx + 0.12, ry + 0.06, lw=0.45, fill=(0.75, 0.85, 1.0))
        sh.text("PLOMB_EF", (rx + 0.16, ry - 0.20), f"montée EF/ECS ({sid})", size=1.1)
    for s in p["stacks"]:
        sh.circle("PLOMB_EV", (s["x"], s["y"]), 0.10, lw=0.6, fill=(0.55, 0.42, 0.25))
        sh.text("PLOMB_EV", (s["x"] + 0.15, s["y"] + 0.13), f"{s['id']} Ø{s['d']}", size=1.5, bold=True)
        if not first:
            sh.rect("RESA", s["x"] - 0.11, s["y"] - 0.11, s["x"] + 0.11, s["y"] + 0.11, lw=0.3, dash="dashed")
        _locate(sh, m, lid, s["x"], s["y"], off=-0.22, size=1.1)
    if first:
        n = p["nourrice"]
        sh.rect("PLOMB_EF", n["x"] - 0.45, n["y"] - 0.12, n["x"] + 0.45, n["y"] + 0.12, lw=0.5, fill=(0.75, 0.85, 1.0))
        sh.text("PLOMB_EF", (n["x"], n["y"] - 0.30), "nourrices EF / ECS", size=1.35, anchor="c", bold=True)
        sh.circle("PLOMB_ECS", (n["x"] + 0.75, n["y"] - 0.25), 0.30, lw=0.5, fill=(1.0, 0.92, 0.90))
        sh.text("PLOMB_ECS", (n["x"] + 0.75, n["y"] - 0.28), "CET 200 L", size=1.1, anchor="c", bold=True)
        col = p["collector"]["path"]
        sh.poly("PLOMB_EV", col, lw=0.9)
        for br in p["collector"].get("branches") or []:
            sh.poly("PLOMB_EV", br, lw=0.7)
        sh.text("PLOMB_EV", ((col[0][0] + col[-1][0]) / 2, col[0][1] + 0.10), "collecteur Ø100 — pente 2 % → regard de branchement", size=1.25, anchor="c")
        if p["relevage"]["needed"]:
            rv = p["relevage"].get("xy", (m.L - 1.3, 0.9))
            sh.rect("PLOMB_EV", rv[0] - 0.3, rv[1] - 0.3, rv[0] + 0.3, rv[1] + 0.3, lw=0.5, fill=(0.85, 0.75, 0.6))
            sh.text("PLOMB_EV", (rv[0], rv[1] + 0.38), "poste de relevage", size=1.25, anchor="c", bold=True)
    for f in [f for f in p["fixtures"] if f["level"] == lid and f["fixture"] == "robinet_ext"]:
        sh.poly("PLOMB_EF", [(f["x"] - 0.08, f["y"] - 0.05), (f["x"] + 0.08, f["y"] + 0.05), (f["x"] + 0.08, f["y"] - 0.05), (f["x"] - 0.08, f["y"] + 0.05)], lw=0.3, closed=True)
        sh.text("PLOMB_EF", (f["x"] + 0.12, f["y"] - 0.2), "robinet de puisage ext. (hors gel)", size=1.1)
    sh.notes = [p["distribution"], p["rules"][0], p["rules"][1]] + \
               ([p["relevage"]["spec"]] if first and p["relevage"]["needed"] else []) + \
               (["Réservations dans le plancher : chutes 20×20, gaine technique " + f"{int(g['w']*100+10)}×{int(g['d']*100+10)} (cotées sur ce plan)."] if not first else []) + \
               ["Cotes d'implantation des attentes depuis les nus finis des murs ; hauteurs des attentes selon fiches fabricants."]
    sh.legend = [("LINE:PLOMB_EF::0.6", "Eau froide (EF)"), ("LINE:PLOMB_ECS::0.6", "Eau chaude sanitaire (ECS)"),
                 ("LINE:PLOMB_EV::1.0", "Évacuation EU/EV PVC"), ("CHUTE", "Chute EU/EV Ø100"), ("VANNE", "Robinet d'arrêt à l'attente"),
                 ("GT", "Gaine technique"), ("RESA", "Réservation dans le plancher")]
    return sh


# ================================================================ ventilation
def vmc_level(m: Model, hv: dict, lid: str, code: str) -> Sheet:
    lv = m.level(lid)
    v = hv["vmc"]
    sh = _sheet(code, f"Ventilation — {lv.name}", v["system"], m, lid)
    g = hv["gaine"]
    first = lid == m.levels[0].id
    _gt(sh, g, resa=not first)
    plen = (g["x"], g["y"] - g["d"] / 2 - 0.25)
    sh.rect("VMC_S" if v["double_flux"] else "VMC_E", plen[0] - 0.35, plen[1] - 0.12, plen[0] + 0.35, plen[1] + 0.12, lw=0.45, fill=(0.88, 0.97, 0.97))
    sh.text("VMC_E", (plen[0] + 0.42, plen[1] - 0.04), "plénum" + (" soufflage / reprise" if v["double_flux"] else " de reprise"), size=1.15)
    bs = [b for b in v["bouches"] if b["level"] == lid]
    for k, b in enumerate(bs):
        lay = "VMC_E" if b["kind"] == "extraction" else "VMC_S"
        start = (plen[0] - 0.30 + 0.06 * (k % 10), plen[1] - 0.12)
        n_cond = max(1, math.ceil(b["q_pointe"] / 45)) if b["kind"] == "extraction" else max(1, math.ceil(b["q"] / 30))
        _route(sh, lay, start, (b["x"], b["y"]), lw=0.45, dash="dashed" if b["kind"] == "soufflage" else None, first="v")
        sh.circle(lay, (b["x"], b["y"]), 0.13, lw=0.45, fill=(1, 1, 1))
        sh.circle(lay, (b["x"], b["y"]), 0.06, lw=0.3)
        tag = ("E " if b["kind"] == "extraction" else "S ") + (f"{b['q']}/{b['q_pointe']}" if b["q_pointe"] != b["q"] else f"{b['q']}") + " m³/h"
        sh.text(lay, (b["x"] + 0.17, b["y"] + 0.08), tag, size=1.25, bold=True)
        sh.text(lay, (b["x"] + 0.17, b["y"] - 0.13), (f"{n_cond} × Ø75 PEHD" if v["double_flux"] else f"Ø{b['d']} souple isolé"), size=1.0)
        _locate(sh, m, lid, b["x"], b["y"], off=-0.25, size=1.05)
    if not v["double_flux"]:
        for r in m.rooms(lid):
            if _k(r) in ("sejour", "chambre", "bureau"):
                ops = [o for o in m.openings if o.level == lid]
                sh.text("VMC_S", (r["x0"] + 0.15, r["y1"] - 0.25), "EA hygro 5-35 m³/h en menuiserie", size=1.0)
    c = v["caisson"]
    if c["level"] == lid:
        sh.rect("VMC_E", c["x"] - 0.40, c["y"] - 0.30, c["x"] + 0.40, c["y"] + 0.30, lw=0.6, fill=(0.95, 0.92, 0.97))
        sh.line("VMC_E", (c["x"] - 0.40, c["y"] - 0.30), (c["x"] + 0.40, c["y"] + 0.30), lw=0.2)
        sh.line("VMC_E", (c["x"] - 0.40, c["y"] + 0.30), (c["x"] + 0.40, c["y"] - 0.30), lw=0.2)
        sh.text("VMC_E", (c["x"], c["y"] + 0.38), "Caisson " + ("double flux" if v["double_flux"] else "VMC hygro B"), size=1.4, anchor="c", bold=True)
        _route(sh, "VMC_E", (c["x"] + 0.40, c["y"]), (g["x"] - g["w"] / 2, g["y"]), lw=0.7)
        sh.text("VMC_E", (c["x"] + 0.5, c["y"] + 0.08), "Ø160 → GT → rejet toiture", size=1.05)
        if v["double_flux"]:
            tt = m.t_tot
            wx = tt if c["x"] < m.L / 2 else m.L - tt
            _route(sh, "VMC_S", (c["x"] - 0.40, c["y"] - 0.15), (wx, c["y"] - 0.15), lw=0.7)
            sh.text("VMC_S", ((c["x"] + wx) / 2, c["y"] - 0.32), "air neuf Ø160 isolé — grille façade", size=1.05, anchor="c")
        _locate(sh, m, lid, c["x"], c["y"], off=-0.45, size=1.1)
    tot_e = sum(b["q"] for b in bs if b["kind"] == "extraction")
    tot_s = sum(b["q"] for b in bs if b["kind"] == "soufflage")
    sh.notes = [v["network"], f"Niveau : extraction {tot_e} m³/h" + (f", soufflage {tot_s} m³/h" if v["double_flux"] else "") +
                f" — total logement {v['q_total_base']} m³/h (cuisine pointe {v['q_kitchen_peak']} m³/h)."] + v["rules"][:3]
    sh.legend = [("BOUCHE_E", "Bouche d'extraction"), ("BOUCHE_S", "Bouche de soufflage"), ("LINE:VMC_E::0.8", "Conduit d'extraction"),
                 ("LINE:VMC_S:dashed:0.8", "Conduit de soufflage"), ("GT", "Gaine technique"), ("RESA", "Réservation dans le plancher")]
    return sh


def vmc_schema(m: Model, hv: dict, code: str) -> Sheet:
    v = hv["vmc"]
    sh = Sheet(code, "Schéma de principe de la ventilation", 1000, origin=(0, 0), subtitle=v["system"])
    sh.text("TITRE", (0, 222), ("VMC DOUBLE FLUX" if v["double_flux"] else "VMC SIMPLE FLUX HYGRO B") + " — synoptique des réseaux et débits", size=3.2, bold=True)
    ids = [lv.id for lv in m.levels]
    zs = {lid: 40 + i * 150 / max(1, len(ids) - 1) for i, lid in enumerate(ids)} if len(ids) > 1 else {ids[0]: 110}
    cx, cy = 150, 20
    # caisson
    sh.rect("VMC_E", cx - 22, cy - 2, cx + 22, cy + 14, lw=0.8, fill=(0.95, 0.92, 0.97))
    if v["double_flux"]:
        sh.line("VMC_E", (cx - 22, cy - 2), (cx + 22, cy + 14), lw=0.4)
        sh.line("VMC_E", (cx - 22, cy + 14), (cx + 22, cy - 2), lw=0.4)
        sh.text("VMC_E", (cx, cy + 15.5), "CAISSON DOUBLE FLUX — échangeur ≥ 85 %, by-pass", size=1.8, anchor="c", bold=True)
    else:
        sh.text("VMC_E", (cx, cy + 15.5), "CAISSON VMC HYGRO B", size=1.8, anchor="c", bold=True)
    sh.text("TEXTE", (cx, cy - 5), f"{v['caisson']['room']} ({m.level(v['caisson']['level']).name})", size=1.6, anchor="c")
    # colonnes
    xe, xs = cx + 50, cx - 50
    sh.line("VMC_E", (cx + 22, cy + 6), (xe, cy + 6), lw=1.0)
    sh.line("VMC_E", (xe, cy + 6), (xe, 205), lw=1.0)
    sh.text("VMC_E", (xe + 2, 207), "rejet Ø160 en toiture (sortie de toit)", size=1.7, bold=True)
    sh.poly("VMC_E", [(xe - 2, 203), (xe, 207), (xe + 2, 203)], lw=0.6)
    if v["double_flux"]:
        sh.line("VMC_S", (cx - 22, cy + 6), (xs, cy + 6), lw=1.0, dash="dashed")
        sh.line("VMC_S", (xs, cy + 6), (xs, 205), lw=1.0, dash="dashed")
        sh.line("VMC_S", (cx - 22, cy + 1), (12, cy + 1), lw=1.0)
        sh.text("VMC_S", (12, cy + 3), "air neuf Ø160 — grille façade + filtre F7", size=1.6, bold=True)
    for lid, z in zs.items():
        sh.line("NIVEAU", (0, z - 6), (290, z - 6), lw=0.2, dash="axis")
        sh.text("NIVEAU", (0, z - 4.5), m.level(lid).name, size=2.2, bold=True)
        bs = [b for b in v["bouches"] if b["level"] == lid]
        ex = [b for b in bs if b["kind"] == "extraction"]
        so = [b for b in bs if b["kind"] == "soufflage"]
        for k, b in enumerate(ex):
            x = xe + 12 + k * 22
            sh.line("VMC_E", (xe, z), (x, z), lw=0.5)
            sh.circle("VMC_E", (x, z), 2.2, lw=0.5, fill=(1, 1, 1))
            sh.text("TEXTE", (x, z - 5), trunc(b["room"], 14), size=1.5, anchor="c")
            sh.text("VMC_E", (x, z + 3.2), f"{b['q']}" + (f"/{b['q_pointe']}" if b["q_pointe"] != b["q"] else "") + " m³/h", size=1.5, anchor="c", bold=True)
        for k, b in enumerate(so):
            x = xs - 12 - k * 20
            sh.line("VMC_S", (xs, z), (x, z), lw=0.5, dash="dashed")
            sh.circle("VMC_S", (x, z), 2.2, lw=0.5, fill=(1, 1, 1))
            sh.text("TEXTE", (x, z - 5), trunc(b["room"], 14), size=1.5, anchor="c")
            sh.text("VMC_S", (x, z + 3.2), f"{b['q']} m³/h", size=1.5, anchor="c", bold=True)
    sh.text("TEXTE", (0, 8), f"Débit total extrait (base) : {v['q_total_base']} m³/h ; pointe cuisine {v['q_kitchen_peak']} m³/h ; "
                             + (f"insufflé : {v['q_insufflation']} m³/h (équilibré à ±10 %)." if v["double_flux"] else "entrées d'air hygroréglables en menuiseries."), size=1.8)
    sh.text("TEXTE", (0, 3), trunc(v["rules"][1], 180), size=1.7)
    sh.legend = [("BOUCHE_E", "Bouche d'extraction"), ("BOUCHE_S", "Bouche de soufflage"), ("LINE:VMC_E::0.8", "Air extrait / rejeté"),
                 ("LINE:VMC_S:dashed:0.8", "Air neuf / soufflé")]
    sh.dxf = False
    return sh


# ================================================================ plancher chauffant
def _spiral(sh: Sheet, rect, pitch, inset=0.15):
    """Boucle bifilaire en escargot (aller rouge / retour bleu) au pas réel."""
    x0, y0, x1, y1 = rect[0] + inset, rect[1] + inset, rect[2] - inset, rect[3] - inset
    if x1 - x0 < 0.3 or y1 - y0 < 0.3:
        return
    i = 0
    while True:
        o = i * pitch
        a0, b0, a1, b1 = x0 + o, y0 + o, x1 - o, y1 - o
        if a1 - a0 < pitch * 1.2 or b1 - b0 < pitch * 1.2:
            break
        sh.rect("CHAUF_A" if i % 2 == 0 else "CHAUF_R", a0, b0, a1, b1, lw=0.18)
        i += 1


def pc_level(m: Model, hv: dict, lid: str, code: str) -> Sheet:
    lv = m.level(lid)
    pc = hv["pc"]
    data = next((l for l in pc["levels"] if l["level"] == lid), None)
    sh = _sheet(code, f"Plancher chauffant{'/rafraîchissant' if hv['options']['cooling'] else ''} — {lv.name}",
                "Plan de pose : boucles, pas, longueurs et débits, collecteur coté — NF DTU 65.14", m, lid, rooms=False)
    g = hv["gaine"]
    _gt(sh, g, label=True)
    for r in m.rooms(lid):
        if _k(r) in ("garage", "local_technique"):
            sh.rect("FOND_PLAN", r["x0"] + 0.05, r["y0"] + 0.05, r["x1"] - 0.05, r["y1"] - 0.05, lw=0.1, hatch="beton")
            sh.text("TEXTE", ((r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2), f"{r['name']} — non chauffé", size=1.4, anchor="c", color=(0.4, 0.4, 0.4))
            continue
        for part in [r] + r.get("parts", []):
            sh.rect("FOND_PLAN", part["x0"] + 0.04, part["y0"] + 0.04, part["x1"] - 0.04, part["y1"] - 0.04, lw=0.2, dash="dashed")
    if not data:
        return sh
    cx, cy = data["collector"]
    for k, lp in enumerate(data["loops"]):
        _spiral(sh, lp["rect"], lp["pitch"])
        x0, y0, x1, y1 = lp["rect"]
        # liaisons collecteur → boucle (aller / retour)
        tx, ty = min(max(cx, x0 + 0.2), x1 - 0.2), (y1 - 0.15 if cy > y1 else (y0 + 0.15 if cy < y0 else min(max(cy, y0 + 0.2), y1 - 0.2)))
        off = 0.03 * k
        _route(sh, "CHAUF_A", (cx - 0.25 + off, cy), (tx, ty), lw=0.25, first="v")
        _route(sh, "CHAUF_R", (cx - 0.22 + off, cy), (tx + 0.04, ty), lw=0.25, first="v")
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        w = 1.7
        sh.rect("FOND_PLAN", mx - 0.75, my - 0.30, mx + 0.75, my + 0.30, lw=0.25, fill=(1, 1, 1))
        sh.text("CHAUF_A", (mx, my + 0.12), f"{lp['id'].split('-')[-1]} · {trunc(lp['room'], 16)}", size=1.25, anchor="c", bold=True)
        sh.text("TEXTE", (mx, my - 0.06), f"{fmt(lp['area'])} m² · pas {int(lp['pitch']*100)} · {lp['length_m']} m", size=1.1, anchor="c")
        sh.text("TEXTE", (mx, my - 0.22), f"{lp['flow_lh']} l/h · {lp['w_m2']} W/m²", size=1.0, anchor="c")
    sh.rect("CHAUF_A", cx - 0.35, cy - 0.07, cx + 0.35, cy + 0.07, lw=0.6, fill=(1.0, 0.90, 0.88))
    sh.text("CHAUF_A", (cx, cy + 0.14 if cy < m.W / 2 else cy - 0.25), f"Collecteur {lv.id} — {data['outputs']} départs", size=1.35, anchor="c", bold=True)
    _locate(sh, m, lid, cx, cy, off=-0.30, size=1.15)
    sh.notes = [pc["system"], pc["regime"], f"Niveau : {data['outputs']} boucles, {data['tube_m']} m de tube ; collecteur avec débitmètres, vannes motorisées et purgeurs."] + pc["rules"][:3]
    sh.legend = [("BOUCLE", "Boucle (aller / retour)"), ("COLL", "Collecteur / nourrice"), ("LINE:CHAUF_A::0.6", "Départ (aller)"),
                 ("LINE:CHAUF_R::0.6", "Retour"), ("GT", "Gaine technique"), ("LINE:FOND_PLAN:dashed:0.4", "Bande périphérique 8 mm")]
    return sh


def hydro_schema(m: Model, hv: dict, code: str) -> Sheet:
    pac, pc = hv["pac"], hv["pc"]
    sh = Sheet(code, "Schéma hydraulique — PAC air/eau, plancher chauffant, ECS", 1000, origin=(0, 0),
               subtitle=pac["label"] + " — départ basse température, loi d'eau")
    sh.text("TITRE", (0, 222), "SCHÉMA HYDRAULIQUE DE PRINCIPE", size=3.2, bold=True)
    # limite extérieur / intérieur
    sh.line("TEXTE", (52, 15), (52, 210), lw=0.3, dash="axis")
    sh.text("TEXTE", (40, 205), "EXTÉRIEUR", size=1.8, anchor="c", bold=True)
    sh.text("TEXTE", (64, 205), "INTÉRIEUR", size=1.8, anchor="c", bold=True)
    # PAC
    sh.rect("TEXTE", 10, 120, 44, 160, lw=0.8, fill=(0.95, 0.96, 0.97))
    sh.circle("TEXTE", (27, 145), 9, lw=0.5)
    for a in range(0, 360, 60):
        r_ = math.radians(a)
        sh.line("TEXTE", (27, 145), (27 + 8 * math.cos(r_), 145 + 8 * math.sin(r_)), lw=0.3)
    sh.text("TEXTE", (27, 125), f"PAC {pac['kw']} kW", size=2.0, anchor="c", bold=True)
    sh.text("TEXTE", (27, 113), "monobloc air/eau" + (" réversible" if hv["options"]["cooling"] else ""), size=1.5, anchor="c")
    # liaisons
    ya, yr = 150, 132
    sh.line("CHAUF_A", (44, ya), (90, ya), lw=0.9)
    sh.line("CHAUF_R", (44, yr), (90, yr), lw=0.9)
    sh.text("TEXTE", (58, ya + 2), "départ Ø32 isolé", size=1.5)
    sh.text("TEXTE", (58, yr - 4), "retour Ø32 isolé", size=1.5)
    # pot de boues + vase + soupape
    sh.circle("CHAUF_R", (70, yr), 3, lw=0.5, fill=(1, 1, 1))
    sh.text("TEXTE", (70, yr - 9), "pot à boues magnétique", size=1.3, anchor="c")
    sh.line("CHAUF_A", (80, ya), (80, ya + 12), lw=0.5)
    sh.circle("CHAUF_A", (80, ya + 17), 5, lw=0.5, fill=(0.95, 0.97, 1))
    sh.text("TEXTE", (86, ya + 18), "vase d'expansion 12 L", size=1.3)
    sh.text("TEXTE", (86, ya + 14), "soupape 3 bar + manomètre", size=1.3)
    # ballon tampon
    bx = 100
    sh.rect("TEXTE", bx, 118, bx + 18, 168, lw=0.8, fill=(0.97, 0.95, 0.93))
    sh.text("TEXTE", (bx + 9, 171), f"ballon tampon {pac['buffer_l']} L", size=1.6, anchor="c", bold=True)
    sh.line("CHAUF_A", (90, ya), (bx, ya), lw=0.9)
    sh.line("CHAUF_R", (90, yr), (bx, yr), lw=0.9)
    # circulateur + vanne 3 voies → collecteurs
    x2 = bx + 18
    sh.line("CHAUF_A", (x2, 160), (150, 160), lw=0.9)
    sh.line("CHAUF_R", (x2, 126), (150, 126), lw=0.9)
    sh.circle("CHAUF_A", (132, 160), 3.5, lw=0.6, fill=(1, 1, 1))
    sh.poly("CHAUF_A", [(130.5, 158), (130.5, 162), (134.5, 160)], lw=0.4, closed=True)
    sh.text("TEXTE", (132, 165), "circulateur HE", size=1.3, anchor="c")
    sh.poly("CHAUF_A", [(140, 157), (146, 163), (146, 157), (140, 163)], lw=0.5, closed=True)
    sh.line("CHAUF_A", (143, 160), (143, 126), lw=0.4, dash="dashed")
    sh.text("TEXTE", (143, 166), "V3V mélangeuse", size=1.3, anchor="c")
    sh.text("TEXTE", (150, 152), "sonde départ", size=1.2)
    # colonnes vers collecteurs
    levels = pc["levels"] if pc else []
    ys = [100 + k * (100 / max(1, len(levels) - 1)) for k in range(len(levels))] if len(levels) > 1 else [150]
    sh.line("CHAUF_A", (150, 160), (150, min(ys)), lw=0.9)
    sh.line("CHAUF_A", (150, 160), (150, max(ys + [160])), lw=0.9)
    sh.line("CHAUF_R", (150, 126), (156, 126), lw=0.9)
    sh.line("CHAUF_R", (156, min(ys + [126]) - 4), (156, max(ys + [126]) - 4), lw=0.9)
    for k, lvd in enumerate(levels):
        y = ys[k]
        sh.line("CHAUF_A", (150, y), (175, y), lw=0.6)
        sh.line("CHAUF_R", (156, y - 4), (175, y - 4), lw=0.6)
        sh.rect("CHAUF_A", 175, y - 6, 181, y + 2, lw=0.6, fill=(1, 0.9, 0.88))
        n = lvd["outputs"]
        for j in range(n):
            x = 186 + j * 8
            if x > 280:
                break
            sh.rect("CHAUF_A", x, y - 5, x + 5, y + 1, lw=0.3)
            sh.rect("CHAUF_R", x + 1, y - 4, x + 4, y, lw=0.25)
        sh.text("TEXTE", (175, y + 4), f"Collecteur {m.level(lvd['level']).name} : {n} boucles — {lvd['tube_m']} m — débitmètres + têtes thermiques", size=1.5, bold=True)
    # ECS
    ex = 70
    sh.rect("PLOMB_ECS", ex - 10, 30, ex + 10, 80, lw=0.8, fill=(1.0, 0.95, 0.94))
    sh.text("PLOMB_ECS", (ex, 83), "CET 200 L (ECS)", size=1.7, anchor="c", bold=True)
    sh.line("PLOMB_EF", (20, 35), (ex - 10, 35), lw=0.7)
    sh.text("PLOMB_EF", (20, 37), "EF réseau → réducteur 3 bar → groupe de sécurité", size=1.3)
    sh.line("PLOMB_ECS", (ex + 10, 72), (120, 72), lw=0.7)
    sh.rect("PLOMB_ECS", 120, 68, 128, 76, lw=0.5, fill=(1, 1, 1))
    sh.text("PLOMB_ECS", (130, 71), "mitigeur thermostatique 50 °C → nourrice ECS", size=1.3)
    # régulation
    sh.rect("ELEC", 200, 30, 280, 58, lw=0.5, fill=(1, 0.96, 0.88))
    sh.text("ELEC", (204, 52), "RÉGULATION", size=1.8, bold=True)
    sh.text("TEXTE", (204, 47), "sonde extérieure façade nord (loi d'eau)", size=1.4)
    sh.text("TEXTE", (204, 43), "thermostats d'ambiance par pièce → têtes thermiques", size=1.4)
    if hv["options"]["cooling"]:
        sh.text("TEXTE", (204, 39), "rafraîchissement : sonde d'hygrométrie, départ ≥ 18 °C", size=1.4)
        sh.text("TEXTE", (204, 35), f"puissance froid estimée {pac['cooling_kw']} kW (≈ 30 W/m² pièces sèches)", size=1.4)
    loss = hv["loss"]
    sh.text("TEXTE", (0, 8), f"Déperditions : {loss['total_w']} W pour {loss['a_heated']} m² chauffés ({loss['w_m2']} W/m²) à Tbase {loss['t_base']} °C — "
                             f"besoin PAC {pac['need_kw']} kW → {pac['kw']} kW retenus.", size=1.8)
    sh.text("TEXTE", (0, 3), trunc(pac["outdoor"], 180), size=1.6)
    sh.legend = [("LINE:CHAUF_A::0.9", "Départ chauffage"), ("LINE:CHAUF_R::0.9", "Retour chauffage"),
                 ("LINE:PLOMB_EF::0.7", "Eau froide"), ("LINE:PLOMB_ECS::0.7", "Eau chaude sanitaire")]
    sh.dxf = False
    return sh


def pc_detail(m: Model, hv: dict, code: str) -> Sheet:
    """Coupe-type du plancher chauffant (horizontale, à l'échelle 1:5) + tableau des déperditions par pièce."""
    pc = hv["pc"]
    sh = Sheet(code, "Coupe-type du plancher chauffant et déperditions par pièce", 10, origin=(0.0, 0.0),
               subtitle="Détail 1:10 — composition du sol, bande périphérique, tubes au pas")
    sh.area_mm = (22, 60, 300, 280)
    tt = m.t_tot
    # mur + doublage à gauche
    H = 0.62
    sh.rect("BRIQUE", 0.0, 0.0, 0.20, H, lw=0.5, fill=(0.97, 0.86, 0.82), hatch="brique")
    ins = hv["options"]["insulation_mm"] / 1000
    sh.rect("DOUBLAGE", 0.20, 0.30, 0.20 + ins, H, lw=0.3, fill=(0.98, 0.93, 0.70))
    sh.rect("CLOISON", 0.20 + ins, 0.30, 0.20 + ins + 0.013, H, lw=0.3, fill=(0.85, 0.85, 0.85))
    xw = 0.20 + ins + 0.013
    # couches (du bas vers le haut)
    y = 0.0
    layers = [("Plancher poutrelles-hourdis 25+5", 0.30, (0.80, 0.80, 0.82), "beton"),
              ("Isolant PU 70 mm (R ≥ 3,15)", 0.07, (0.98, 0.93, 0.70), None),
              ("Isolant à plots PSE 30 mm + film", 0.03, (0.99, 0.96, 0.82), None),
              ("Chape fluide anhydrite 50 mm (30 mm sur tube)", 0.05, (0.90, 0.88, 0.84), None),
              ("Revêtement collé 10 mm", 0.01, (0.75, 0.62, 0.45), None)]
    X1 = 0.80
    for name, th, col, hatch in layers:
        x0 = 0.20 if th != 0.30 else 0.0
        sh.rect("BA", 0.20 if y >= 0.30 else 0.20, y, X1, y + th, lw=0.3, fill=col, hatch=hatch)
        y += th
    y_slab, y_ins, y_plot, y_chape, y_rev = 0.30, 0.37, 0.40, 0.45, 0.46
    # hourdis stylisés
    for k in range(3):
        hx = 0.28 + k * 0.18
        sh.rect("BA", hx, 0.04, hx + 0.14, 0.24, lw=0.25, fill=(0.92, 0.92, 0.92))
    # bande périphérique
    sh.rect("CHAUF_R", xw, y_ins, xw + 0.008, y_rev + 0.02, lw=0.3, fill=(0.6, 0.75, 0.95))
    # tubes au pas
    p = 0.15 if hv["options"]["cooling"] else 0.15
    xt = xw + 0.10
    k = 0
    while xt < X1 - 0.03:
        sh.circle("CHAUF_A" if k % 2 == 0 else "CHAUF_R", (xt, y_plot + 0.009), 0.008, lw=0.5, fill=(1, 1, 1))
        xt += p / 2
        k += 1
    # plinthe
    sh.rect("CHARPENTE", xw + 0.008, y_rev, xw + 0.018, y_rev + 0.07, lw=0.3, fill=(0.85, 0.72, 0.55))
    # étiquettes à droite + chaîne de cotes
    lab = [(y_rev - 0.005, "Revêtement collé (carrelage / parquet R ≤ 0,15 m².K/W)"), (y_chape - 0.025, "Chape fluide anhydrite ≥ 30 mm au-dessus des tubes"),
           (y_plot + 0.009, f"Tubes PER-BAO Ø16 × 1,5 au pas de {int(p*100)} cm (aller / retour alternés)"),
           (y_plot - 0.015, "Plaque isolante à plots PSE 30 mm + film PE"), (y_slab + 0.035, "Isolant PU 70 mm — R total ≥ 3,15 sous chape (RE 2020)"),
           (0.15, "Plancher porteur poutrelles-hourdis 25+5")]
    for k, (yy, txt) in enumerate(lab):
        ty = 0.62 - k * 0.075
        sh.line("TEXTE", (X1 - 0.05, yy), (X1 + 0.06, ty), lw=0.2)
        sh.line("TEXTE", (X1 + 0.06, ty), (X1 + 0.10, ty), lw=0.2)
        sh.text("TEXTE", (X1 + 0.11, ty - 0.004), txt, size=2.0)
    sh.line("CHAUF_R", (xw + 0.004, y_rev + 0.01), (xw + 0.10, y_rev + 0.13), lw=0.2)
    sh.text("CHAUF_R", (xw + 0.11, y_rev + 0.13), "bande périphérique 8 mm + plinthe", size=1.8)
    sh.chain([0.0, 0.30, 0.37, 0.40, 0.45, 0.46], "y", -0.06, size=1.8)
    sh.text("TEXTE", (0.0, -0.08), "Composition totale ≈ 46 cm (plancher compris) — réservation de 16 cm au-dessus de la dalle porteuse", size=2.0)
    # tableau des déperditions
    loss = hv["loss"]
    sh.text("TITRE", (0.0, -0.20), "DÉPERDITIONS PAR PIÈCE (W) — Tint 20 °C, Tbase " + f"{loss['t_base']} °C", size=2.8, bold=True)
    rows = loss["rooms"]
    ncol = 2
    per = math.ceil(len(rows) / ncol)
    for k, rr in enumerate(rows):
        cx_ = 0.0 + (k // per) * 1.15
        cy_ = -0.28 - (k % per) * 0.034
        sh.text("TEXTE", (cx_, cy_), f"{rr['level']} · {rr['room'][:26]}", size=1.6)
        sh.text("TEXTE", (cx_ + 0.95, cy_), f"{rr['phi_w']} W · {rr['w_m2']} W/m²", size=1.6, anchor="r")
    sh.text("TEXTE", (0.0, -0.32 - per * 0.034), f"Total {loss['total_w']} W — U murs {str(loss['U']['wall']).replace('.', ',')} ; menuiseries 1,30 ; toiture 0,14 W/m².K "
                                                  f"(isolation {hv['options']['insulation_mm']} mm intérieure).", size=1.8)
    sh.origin = (-0.10, -0.32 - per * 0.034 - 0.08)
    lab = {"heating": "chauffage", "ventilation": "ventilation", "cooling": "rafraîchissement", "insulation": "isolation"}
    sh.notes = ["Origine des choix : " + " ; ".join(f"{lab.get(k, k)} — {v}" for k, v in hv["options"]["source"].items()) + ".",
                "Pré-dimensionnement à confirmer par l'étude thermique RE 2020 réglementaire (Bbio, Cep, DH) et le calcul NF EN 12831 complet."]
    if pc:
        sh.notes += pc["rules"][1:]
    sh.dxf = False
    return sh
