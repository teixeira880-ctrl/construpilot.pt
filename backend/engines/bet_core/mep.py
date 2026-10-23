"""Moteurs Électricité (NF C 15-100) et Plomberie (NF DTU 60.11) sur la même géométrie.

Électricité : équipement minimal par pièce → placement des points le long des murs
de la pièce → regroupement en circuits (règles de nombre de points par circuit) →
tableau (différentiels 30 mA, disjoncteurs, sections) → quantitatif.
Plomberie : appareils par pièce → diamètres d'alimentation et d'évacuation (DTU 60.11)
→ chutes alignées sur les pièces humides superposées → nourrice + ECS → quantitatif.
"""
from __future__ import annotations

import math

from .model import Model

# ------------------------------------------------------------------ ÉLECTRICITÉ
# Équipement minimal par type de pièce (NF C 15-100 §10.1 — logement)
ROOM_RULES = {
    "sejour":      {"pc": lambda a: max(5, min(8, math.ceil(a / 4))), "pl": 1, "rj45": 2, "spec": []},
    "chambre":     {"pc": lambda a: 3, "pl": 1, "rj45": 1, "spec": ["volet"]},
    "cuisine":     {"pc": lambda a: 6, "pl": 1, "rj45": 0, "spec": ["plaque_32A", "four_20A", "lave_vaisselle_20A"]},
    "salle_eau":   {"pc": lambda a: 1, "pl": 2, "rj45": 0, "spec": ["seche_serviettes"]},
    "wc":          {"pc": lambda a: 0, "pl": 1, "rj45": 0, "spec": []},
    "entree":      {"pc": lambda a: 1, "pl": 2, "rj45": 0, "spec": ["gtl", "sonnette"]},
    "circulation": {"pc": lambda a: 1 if a >= 4 else 0, "pl": 1, "rj45": 0, "spec": []},
    "dressing":    {"pc": lambda a: 1, "pl": 1, "rj45": 0, "spec": []},
    "garage":      {"pc": lambda a: 1, "pl": 1, "rj45": 0, "spec": ["porte_garage"]},
    "buanderie":   {"pc": lambda a: 1, "pl": 1, "rj45": 0, "spec": ["lave_linge_20A", "seche_linge_20A"]},
    "local_technique": {"pc": lambda a: 1, "pl": 1, "rj45": 0, "spec": ["chauffe_eau_20A", "vmc", "pac_32A"]},
    "annexe_seche": {"pc": lambda a: 3 if a > 15 else 1, "pl": 1, "rj45": 0, "spec": []},
}
SPEC_CIRCUITS = {
    "plaque_32A": ("Plaque de cuisson", 32, 6.0, "A"), "four_20A": ("Four", 20, 2.5, "A"),
    "lave_vaisselle_20A": ("Lave-vaisselle", 20, 2.5, "A"), "lave_linge_20A": ("Lave-linge", 20, 2.5, "A"),
    "seche_linge_20A": ("Sèche-linge", 20, 2.5, "AC"), "chauffe_eau_20A": ("Chauffe-eau thermodynamique 200 L", 20, 2.5, "AC"),
    "pac_32A": ("PAC air/eau", 32, 6.0, "A"), "vmc": ("VMC hygro B", 2, 1.5, "AC"),
    "seche_serviettes": ("Sèche-serviettes", 16, 1.5, "AC"), "porte_garage": ("Porte de garage motorisée", 16, 1.5, "AC"),
}


def _area(r):
    return sum((p["x1"] - p["x0"]) * (p["y1"] - p["y0"]) for p in [r] + r.get("parts", []))


def _perimeter_points(r, n, inset=0.12, skip_corners=0.35):
    """n points répartis sur le périmètre intérieur d'une pièce (prises en plinthe)."""
    x0, y0, x1, y1 = r["x0"] + inset, r["y0"] + inset, r["x1"] - inset, r["y1"] - inset
    per = 2 * ((x1 - x0) + (y1 - y0))
    pts = []
    for k in range(n):
        s = (k + 0.5) * per / n
        if s < x1 - x0:
            pts.append((x0 + s, y0))
        elif s < (x1 - x0) + (y1 - y0):
            pts.append((x1, y0 + s - (x1 - x0)))
        elif s < 2 * (x1 - x0) + (y1 - y0):
            pts.append((x1 - (s - (x1 - x0) - (y1 - y0)), y1))
        else:
            pts.append((x0, y1 - (s - 2 * (x1 - x0) - (y1 - y0))))
    return [(round(x, 2), round(y, 2)) for x, y in pts]


UNIQUE_SPECS = {"chauffe_eau_20A", "vmc", "pac_32A"}     # un seul appareil par maison, même s'il y a plusieurs locaux techniques


def electrical(m: Model) -> dict:
    levels = []
    circuits = []
    placed = set()
    df = str((m.raw.get("user_hypotheses") or {}).get("ventilation", "")).startswith("double")
    totals = {"pc": 0, "pl": 0, "rj45": 0, "spec": 0, "inter": 0}
    for lv in m.levels:
        pts = []
        pc_pts, pl_pts = [], []
        for r in m.rooms(lv.id):
            rule = ROOM_RULES.get(r["type"], ROOM_RULES["annexe_seche"])
            a = _area(r)
            n_pc = rule["pc"](a)
            if r["type"] == "cuisine":
                n_pc_plan = 4
            cx, cy = (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2
            for p in _perimeter_points(r, n_pc):
                pts.append({"kind": "PC", "x": p[0], "y": p[1], "room": r["name"]})
                pc_pts.append(r["name"])
            for k in range(rule["pl"]):
                dx = 0 if rule["pl"] == 1 else (-0.4 if k == 0 else 0.4)
                ply = cy - 0.55 if (r["y1"] - r["y0"]) > 2.0 else cy        # décalé sous l'étiquette de la pièce
                pts.append({"kind": "PL", "x": round(cx + dx, 2), "y": round(ply, 2), "room": r["name"]})
                pl_pts.append(r["name"])
            pts.append({"kind": "INT", "x": round(r["x0"] + 0.25, 2), "y": round(r["y0"] + 0.25, 2), "room": r["name"]})
            for k in range(rule["rj45"]):
                pts.append({"kind": "RJ45", "x": round(r["x1"] - 0.30 - 0.3 * k, 2), "y": round(r["y1"] - 0.15, 2), "room": r["name"]})
            for j, sp in enumerate(rule["spec"]):
                if sp in UNIQUE_SPECS:
                    if sp in placed:
                        continue
                    placed.add(sp)
                if sp in SPEC_CIRCUITS:
                    pts.append({"kind": "SPEC", "code": sp, "x": round(r["x1"] - 0.25, 2), "y": round(r["y0"] + 0.35 + 0.35 * j, 2), "room": r["name"]})
                    lab = "VMC double flux" if (sp == "vmc" and df) else SPEC_CIRCUITS[sp][0]
                    circuits.append({"level": lv.id, "name": f"{lab} ({r['name']})", "breaker": SPEC_CIRCUITS[sp][1],
                                     "section": SPEC_CIRCUITS[sp][2], "rcd_type": SPEC_CIRCUITS[sp][3], "points": 1, "kind": "spécialisé"})
            totals["pc"] += n_pc
            totals["pl"] += rule["pl"]
            totals["rj45"] += rule["rj45"]
            totals["inter"] += 1
        # circuits prises : 20 A / 2,5 mm² ≤ 12 socles ; éclairage 16 A / 1,5 mm² ≤ 8 points
        for k in range(math.ceil(len(pc_pts) / 12) if pc_pts else 0):
            n = min(12, len(pc_pts) - 12 * k)
            circuits.append({"level": lv.id, "name": f"Prises {lv.name} n°{k+1}", "breaker": 20, "section": 2.5,
                             "rcd_type": "AC", "points": n, "kind": "prises"})
        for k in range(math.ceil(len(pl_pts) / 8) if pl_pts else 0):
            n = min(8, len(pl_pts) - 8 * k)
            circuits.append({"level": lv.id, "name": f"Éclairage {lv.name} n°{k+1}", "breaker": 16, "section": 1.5,
                             "rcd_type": "AC", "points": n, "kind": "éclairage"})
        if lv.floor_top > -1.0:
            circuits.append({"level": lv.id, "name": f"Volets roulants {lv.name}", "breaker": 16, "section": 1.5,
                             "rcd_type": "AC", "points": len([o for o in m.openings if o.level == lv.id and 'porte' not in o.kind]), "kind": "volets"})
        levels.append({"level": lv.id, "name": lv.name, "points": pts})
    totals["spec"] = len([c for c in circuits if c["kind"] == "spécialisé"])
    hab = sum(_area(r) for lv in m.levels if lv.floor_top > -1.0 for r in m.rooms(lv.id))
    ids = [l.id for l in m.levels]
    n_rcd = 4 if hab > 100 else (3 if hab > 35 else 2)
    # répartition sur les interrupteurs différentiels : type A d'abord pour les circuits qui l'exigent
    rcds = [{"id": f"ID{i+1}", "rating": 40, "type": "A" if i < 2 else "AC", "circuits": []} for i in range(n_rcd)]
    for c in sorted(circuits, key=lambda c: 0 if c["rcd_type"] == "A" else 1):
        pool = [r for r in rcds if (r["type"] == "A" or c["rcd_type"] == "AC") and len(r["circuits"]) < 8]
        tgt = min(pool, key=lambda r: len(r["circuits"]))
        tgt["circuits"].append(c["name"])
        c["rcd"] = tgt["id"]
    modules = 2 + n_rcd * 2 + len(circuits) + 4
    rows = math.ceil(modules * 1.2 / 13)
    cable = {1.5: 0, 2.5: 0, 6.0: 0}
    for c in circuits:
        L = 12 + 4 * c["points"] + 6 * ids.index(c["level"])
        cable[c["section"]] = cable.get(c["section"], 0) + L
    return {
        "standard": "NF C 15-100 (logement neuf) — équipements minimaux, circuits, protections",
        "levels": levels, "circuits": circuits, "rcds": rcds, "totals": totals,
        "habitable_area": round(hab, 1),
        "panel": {"location": "GTL dans le hall RDC (près de l'entrée), largeur ≥ 0,60 m", "rows": rows, "modules": modules,
                  "head": "Disjoncteur de branchement 500 mA 15/45 A (Enedis, 12 kVA mono à confirmer)",
                  "spare": "20 % de réserve", "earth": "Prise de terre : boucle à fond de fouille en câblette Cu 25 mm² sous les semelles, barrette de mesure en LT, R ≤ 100 Ω"},
        "cables_m": {f"{k} mm²": round(v) for k, v in cable.items()},
        "rules": [
            "Prises : circuits 20 A en 2,5 mm² de 12 socles maxi ; éclairage : 16 A en 1,5 mm², 8 points maxi.",
            "Cuisine : 6 prises dont 4 au-dessus du plan de travail ; circuits spécialisés plaque 32 A (6 mm²), four 20 A, lave-vaisselle 20 A.",
            "Salles d'eau : appareillage hors volumes 0-1-2, liaison équipotentielle supplémentaire, prise rasoir ou PC 16 A en volume 2 interdite.",
            f"Surface habitable {hab:.0f} m² {'>' if hab > 100 else '≤'} 100 m² → {n_rcd} interrupteurs différentiels 40 A 30 mA (dont 2 de type A : plaque, lave-linge, lave-vaisselle, four, PAC).",
            "Communication : 1 RJ45 par chambre, 2 dans le séjour ; coffret de communication grade 2TV dans la GTL.",
            "Garage, buanderie, sous-sol : appareillage IP 44 mini, IK 07." if (any(l.floor_top < -1 for l in m.levels) or any(r["type"] in ("garage", "buanderie") for l in m.levels for r in m.rooms(l.id))) else
            "Locaux humides et extérieurs : appareillage IP 44 mini, IK 07.",
        ],
    }


# ------------------------------------------------------------------ PLOMBERIE
# NF DTU 60.11 P1-1 : débits de base (l/s) et diamètres intérieurs mini d'alimentation (mm)
FIX = {
    "evier":          {"q": 0.20, "d_alim": 12, "d_evac": 40, "ecs": True,  "label": "Évier"},
    "lavabo":         {"q": 0.20, "d_alim": 10, "d_evac": 32, "ecs": True,  "label": "Lavabo"},
    "lave_mains":     {"q": 0.10, "d_alim": 10, "d_evac": 32, "ecs": False, "label": "Lave-mains"},
    "douche":         {"q": 0.20, "d_alim": 12, "d_evac": 40, "ecs": True,  "label": "Douche"},
    "baignoire":      {"q": 0.33, "d_alim": 13, "d_evac": 40, "ecs": True,  "label": "Baignoire"},
    "wc":             {"q": 0.12, "d_alim": 10, "d_evac": 100, "ecs": False, "label": "WC"},
    "lave_vaisselle": {"q": 0.10, "d_alim": 10, "d_evac": 40, "ecs": False, "label": "Lave-vaisselle"},
    "lave_linge":     {"q": 0.20, "d_alim": 10, "d_evac": 40, "ecs": False, "label": "Lave-linge"},
    "robinet_ext":    {"q": 0.33, "d_alim": 13, "d_evac": 0, "ecs": False, "label": "Robinet de puisage extérieur"},
}
PIPE_PER = [(12, 16), (16, 20), (20, 25), (26, 32)]   # diamètre intérieur → extérieur multicouche


def _pipe_for(d_int):
    for di, de in PIPE_PER:
        if di >= d_int:
            return f"multicouche {de} × {(de - di)//2 if de - di > 2 else 2}"
    return "multicouche 32 × 3"


# encombrement des appareils (largeur le long du mur, profondeur) en m
SIZE = {"evier": (1.20, 0.60), "lavabo": (0.60, 0.45), "lave_mains": (0.40, 0.30), "douche": (0.90, 0.90), "baignoire": (1.70, 0.75),
        "wc": (0.40, 0.65), "lave_vaisselle": (0.60, 0.60), "lave_linge": (0.60, 0.60), "robinet_ext": (0.20, 0.10)}


def _layout(m: Model, r: dict, names: list[str]) -> list[tuple]:
    """Implante les appareils en file contre un mur de la pièce (mur d'enveloppe de préférence), puis sur le mur en retour
    à partir de l'angle commun, puis sur le mur opposé. Renvoie (x centre, y centre, largeur, profondeur, mur)."""
    tt = m.t_tot
    x0, y0, x1, y1 = r["x0"], r["y0"], r["x1"], r["y1"]
    if y1 >= m.W - tt - 0.1:
        prim = "y1"
    elif y0 <= tt + 0.1:
        prim = "y0"
    else:
        prim = "y1" if (x1 - x0) >= (y1 - y0) else "x1"
    opp = {"y0": "y1", "y1": "y0", "x0": "x1", "x1": "x0"}
    side = ["x1", "x0"] if prim in ("y0", "y1") else ["y1", "y0"]
    seq = [prim] + side + [opp[prim]]
    out, wi, cur, depth, pdepth = [], 0, 0.05, 0.0, 0.0

    def length(w):
        return (x1 - x0) if w in ("y0", "y1") else (y1 - y0)
    for f in names:
        w, d = SIZE.get(f, (0.6, 0.6))
        while wi < len(seq) - 1 and cur > 0.06 and cur + w > length(seq[wi]) - 0.05:
            wi += 1
            if wi == 1:
                pdepth = depth
            cur = 0.05 + (pdepth + 0.05 if seq[wi] in side else 0.0)
            depth = 0.0
        wall = seq[wi]
        L = length(wall)
        w_eff = min(w, max(L - cur - 0.05, 0.3))
        a = cur + w_eff / 2
        if wall in ("y0", "y1"):
            cx = (x0 + a) if (wall == prim or prim in ("y0", "y1") or prim == "x0") else (x1 - a)
            cy = y0 + d / 2 if wall == "y0" else y1 - d / 2
        else:                                     # mur en X : on part de l'angle commun avec le mur principal
            from_top = prim == "y1"
            cy = (y1 - a) if from_top else (y0 + a)
            cx = x0 + d / 2 if wall == "x0" else x1 - d / 2
        out.append((round(cx, 3), round(cy, 3), round(w_eff, 2), d, wall))
        cur += w_eff + 0.10
        depth = max(depth, d)
    return out


WET = {"salle_eau", "wc", "cuisine", "buanderie", "sdb"}


def _street_side(m: Model) -> str:
    sides = m.raw["sides"]
    for sid, sd in sides.items():
        if "rue" in (sd.get("label", "") + sid).lower() and sd.get("type") != "mitoyen":
            return sid
    return next((sid for sid, sd in sides.items() if sd.get("type") != "mitoyen"), next(iter(sides)))


def _garden_side(m: Model, street: str) -> str:
    sides = m.raw["sides"]
    for sid, sd in sides.items():
        if "jardin" in (sd.get("label", "") + sid).lower():
            return sid
    st = sides[street]
    return next((sid for sid, sd in sides.items() if sd["axis"] == st["axis"] and sid != street and sd.get("type") != "mitoyen"), street)


def auto_network(m: Model) -> dict:
    """Chutes EU/EV, collecteur, nourrice et robinet extérieur déduits du plan quand le relevé ne les donne pas :
    chutes posées dans un angle de pièce humide, au point qui dessert le plus de pièces humides superposées
    (≤ 3 m d'évacuation), sans tomber dans la trémie ni sur une baie ; collecteur vers la façade sur rue ;
    nourrice dans le local technique du niveau le plus bas (sinon buanderie / garage)."""
    tt, st = m.t_tot, m.stair
    wet = [(lv, r) for lv in m.levels for r in m.rooms(lv.id) if r["type"] in WET or r.get("fixtures")]
    wet = [(lv, r) for lv, r in wet if r["type"] != "garage"]

    def inside(px, py, r, pad=0.0):
        return r["x0"] - pad <= px <= r["x1"] + pad and r["y0"] - pad <= py <= r["y1"] + pad

    def in_stair(px, py):
        return st["x0"] - 0.25 <= px <= st["x1"] + 0.25 and st["y0"] - 0.25 <= py <= st["y1"] + 0.25

    cands = []
    for _, r in wet:
        for cx in (r["x0"] + 0.15, r["x1"] - 0.15):
            for cy in (r["y0"] + 0.15, r["y1"] - 0.15):
                if not in_stair(cx, cy):
                    cands.append((round(cx, 2), round(cy, 2)))
    remaining = list(wet)
    stacks = []
    while remaining and len(stacks) < 3 and cands:
        def served(c):
            return [(lv, r) for lv, r in remaining if inside(c[0], c[1], r, 0.05) or
                    (abs(c[0] - (r["x0"] + r["x1"]) / 2) + abs(c[1] - (r["y0"] + r["y1"]) / 2) <= 3.0 and
                     any(inside(c[0], c[1], r2, 0.05) for lv2, r2 in wet if lv2.id == lv.id))]
        def on_fixture_wall(c, r):
            """Angle situé sur le mur où _layout aligne les appareils (mur de façade de la pièce)."""
            if r["y1"] >= m.W - tt - 0.1:
                return abs(c[1] - (r["y1"] - 0.15)) < 0.02
            if r["y0"] <= tt + 0.1:
                return abs(c[1] - (r["y0"] + 0.15)) < 0.02
            return False
        best = max(cands, key=lambda c: (len(served(c)), sum(on_fixture_wall(c, r) for _, r in served(c)),
                                         -min(abs(c[0] - tt), abs(c[0] - (m.L - tt)), abs(c[1] - tt), abs(c[1] - (m.W - tt)))))
        sv = served(best)
        if not sv:
            break
        stacks.append({"id": f"CH{len(stacks) + 1}", "x": best[0], "y": best[1], "d": 100,
                       "serves": ", ".join(f"{r['name']} {lv.id}" for lv, r in sv)})
        remaining = [x for x in remaining if x not in sv]
        cands = [c for c in cands if abs(c[0] - best[0]) + abs(c[1] - best[1]) > 1.5]
    if not stacks:
        stacks = [{"id": "CH1", "x": round(m.L / 2, 2), "y": round(tt + 0.15, 2), "d": 100, "serves": "pièces humides"}]
    street = _street_side(m)
    sd = m.side(street)
    s0 = min(stacks, key=lambda s: abs((s["x"] if sd["axis"] == "x" else s["y"]) - sd["pos"]))
    if sd["axis"] == "x":
        exit_pt = (0.0 if sd["pos"] < m.L / 2 else m.L, s0["y"])
    else:
        exit_pt = (s0["x"], 0.0 if sd["pos"] < m.W / 2 else m.W)
    # tronc commun parallèle à la façade sur rue, sur la file qui regroupe le plus de chutes ; antennes orthogonales
    along = "y" if sd["axis"] == "x" else "x"                 # coordonnée constante du tronc
    key = (lambda q: q["y"]) if along == "y" else (lambda q: q["x"])
    vals = [round(key(q), 2) for q in stacks]
    c_trunk = max(set(vals), key=lambda v: (vals.count(v), -abs(v - key(s0))))
    far = max(stacks, key=lambda q: abs((q["x"] if sd["axis"] == "x" else q["y"]) - sd["pos"]))
    if along == "y":
        path = [(far["x"], c_trunk), (exit_pt[0], c_trunk)]
        branches = [[(q["x"], q["y"]), (q["x"], c_trunk)] for q in stacks if abs(q["y"] - c_trunk) > 0.01]
    else:
        path = [(c_trunk, far["y"]), (c_trunk, exit_pt[1])]
        branches = [[(q["x"], q["y"]), (c_trunk, q["y"])] for q in stacks if abs(q["x"] - c_trunk) > 0.01]
    low = m.levels[0]
    bsmt = low.floor_top < -1.0
    collector = {"id": "COL", "path": path, "branches": branches,
                 "exit": (f"collecteur en plafond du sous-sol puis traversée de la {sd['label'].lower()} (fourreau étanche) vers le regard de branchement"
                          if bsmt else f"sous dallage vers la {sd['label'].lower()} puis regard de branchement en limite de propriété")}
    host = next((r for r in m.rooms(low.id) if r["type"] == "local_technique"), None) or \
        next((r for r in m.rooms(low.id) if r["type"] in ("buanderie", "garage", "cellier", "annexe_seche")), None) or \
        next((r for lv in m.levels for r in m.rooms(lv.id) if r["type"] in ("buanderie", "local_technique")), None)
    if host:
        nourrice = {"x": round(host["x0"] + 0.40, 2), "y": round(host["y1"] - 0.30, 2), "level": low.id if host in m.rooms(low.id) else
                    next(lv.id for lv in m.levels if host in m.rooms(lv.id)), "room": host["name"]}
    else:
        nourrice = {"x": round(stacks[0]["x"] + 0.5, 2), "y": stacks[0]["y"], "level": low.id, "room": "Local technique"}
    gs = m.side(_garden_side(m, street))
    first = next((lv for lv in m.levels if lv.floor_top > -1.0), low)
    if gs["axis"] == "x":
        ext = {"level": first.id, "room": gs["label"], "x": round(0.25 if gs["pos"] < m.L / 2 else m.L - 0.25, 2), "y": round(m.W - 1.0, 2)}
    else:
        ext = {"level": first.id, "room": gs["label"], "x": round(m.L - 1.0, 2), "y": round(0.25 if gs["pos"] < m.W / 2 else m.W - 0.25, 2)}
    return {"stacks": stacks, "collector": collector, "nourrice": nourrice, "outdoor_tap": ext}


def plumbing(m: Model) -> dict:
    cfg = m.raw.get("mep") or {}
    auto = None if (cfg.get("stacks") and cfg.get("collector") and cfg.get("nourrice")) else auto_network(m)
    stacks = [dict(s, d=s.get("d", 100)) for s in cfg["stacks"]] if cfg.get("stacks") else auto["stacks"]
    collector = dict(cfg["collector"], id="COL", path=[tuple(p) for p in cfg["collector"]["path"]]) if cfg.get("collector") else auto["collector"]
    nourrice = dict(cfg["nourrice"]) if cfg.get("nourrice") else auto["nourrice"]
    ext = cfg.get("outdoor_tap") or (auto or auto_network(m))["outdoor_tap"]
    ids = [l.id for l in m.levels]
    bsmt = m.levels[0].floor_top < -1.0
    fixtures = []
    for lv in m.levels:
        for r in m.rooms(lv.id):
            names = list(r.get("fixtures", []))
            if r["type"] == "buanderie":
                names = ["lave_linge", "evier"]
            for f, (fx, fy, w, d, wall) in zip(names, _layout(m, r, names)):
                spec = FIX[f]
                stack = min(stacks, key=lambda s: math.hypot(s["x"] - fx, s["y"] - fy))
                dist = abs(stack["x"] - fx) + abs(stack["y"] - fy)
                fixtures.append({"level": lv.id, "room": r["name"], "fixture": f, "label": spec["label"], "x": round(fx, 2),
                                 "y": round(fy, 2), "w": w, "d": d, "wall": wall, "q": spec["q"], "alim": _pipe_for(spec["d_alim"]), "ecs": spec["ecs"],
                                 "evac": f"PVC Ø{spec['d_evac']}" if spec["d_evac"] else "—", "d_evac": spec["d_evac"], "stack": stack["id"],
                                 "horiz_m": round(dist, 2),
                                 "slope_ok": dist <= (4.0 if spec["d_evac"] >= 100 else 3.0),
                                 "supply_m": round(abs(nourrice["x"] - fx) + abs(nourrice["y"] - fy) + 3.0 * ids.index(lv.id) + 2, 1)})
    fixtures.append({"level": ext["level"], "room": ext["room"], "fixture": "robinet_ext", "label": "Robinet de puisage extérieur", "x": ext["x"], "y": ext["y"],
                     "q": 0.33, "alim": _pipe_for(13), "ecs": False, "evac": "—", "stack": "—", "horiz_m": 0, "slope_ok": True, "supply_m": 12})
    x = len(fixtures)
    qtot = sum(f["q"] for f in fixtures)
    y = 0.8 / math.sqrt(x - 1) if x > 5 else 1.0
    qp = qtot * y
    d_main = math.sqrt(4 * qp / 1000 / (math.pi * 2.0)) * 1000   # V ≤ 2 m/s
    relevage = [f for f in fixtures if bsmt and f["level"] == m.levels[0].id]
    warn = []
    for f in fixtures:
        if not f["slope_ok"]:
            warn.append(f"{f['label']} ({f['room']}) à {f['horiz_m']} m de la chute {f['stack']} : collecteur Ø{100 if f['fixture']=='wc' else 50} avec pente 2 % et ventilation secondaire")
    return {
        "standard": "NF DTU 60.11 (calcul des réseaux), NF DTU 60.1 (plomberie sanitaire), NF DTU 60.33 (PVC évacuation)",
        "fixtures": fixtures, "stacks": stacks, "collector": collector, "nourrice": nourrice,
        "flow": {"n": x, "q_total": round(qtot, 2), "y": round(y, 3), "q_probable": round(qp, 2), "d_main_min_mm": round(d_main, 1),
                 "main": "Alimentation générale PEHD 32 depuis le compteur (regard en limite de propriété) → réducteur de pression 3 bar + clapet EA + filtre en LT"},
        "ecs": f"Chauffe-eau thermodynamique 200 L en {nourrice.get('room', 'local technique').lower() if not bsmt else 'local technique (sous-sol)'} ; bouclage non nécessaire si la distance au point le plus éloigné < 8 m de tuyauterie de diamètre ≤ 16 (sinon mitigeur thermostatique et retour) ; groupe de sécurité + bac de rétention",
        "distribution": "Distribution en pieuvre depuis nourrices EF et ECS (multicouche sous fourreau dans les dalles de compression et doublages) ; une vanne d'arrêt par pièce d'eau",
        "relevage": {"needed": bool(relevage), "items": [f"{f['label']} ({f['room']})" for f in relevage],
                     **({"xy": cfg["relevage_xy"]} if cfg.get("relevage_xy") else
                        {"xy": (round(min(nourrice["x"] + 1.4, m.L - m.t_tot - 0.4), 2), round(nourrice["y"], 2))} if auto else {}),
                     "spec": "Poste de relevage eaux grises/vannes en buanderie (cuve 60 L, clapet anti-retour, refoulement Ø40 jusqu'au collecteur en plafond du sous-sol)" if relevage else ""},
        "ventilation": "Chutes Ø100 prolongées en ventilation primaire hors toiture (sorties tuiles à douille) ; clapets aérateurs interdits en substitution unique",
        "rain": cfg.get("rain", "Gouttières zinc demi-rondes 33 sur les deux égouts, 2 descentes Ø80 par façade, dauphins fonte côté rue ; rejet EP selon PLU (infiltration à la parcelle à vérifier)"),
        "warnings": warn,
        "rules": [
            "Diamètres intérieurs mini d'alimentation (DTU 60.11) : évier, douche 12 mm ; lavabo, WC, lave-linge 10 mm ; baignoire 13 mm.",
            "Évacuations : lavabo Ø32, évier/douche/baignoire/lave-linge Ø40, WC Ø100 ; pente 1 à 3 % ; longueur ≤ 3 m sans ventilation (≤ 4 m pour WC Ø100).",
            "Chutes EU/EV unique Ø100 alignées sur les pièces humides superposées (" + " ; ".join(f"{s['id']} : {s['serves']}" for s in stacks) + ").",
            f"Coefficient de simultanéité y = 0,8/√(x−1) = {y:.3f} pour x = {x} appareils → débit probable {qp:.2f} l/s.",
        ] + (["Sous-sol sous le niveau de la rue : appareils du sous-sol raccordés par poste de relevage (réseau public présumé plus haut)."] if relevage else
             ["Évacuations gravitaires jusqu'au regard de branchement en limite de propriété (pente ≥ 2 %)."]),
    }
