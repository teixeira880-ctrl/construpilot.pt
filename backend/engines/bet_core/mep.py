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
    "pac_32A": ("PAC air/eau (hypothèse chauffage)", 32, 6.0, "A"), "vmc": ("VMC hygro B", 2, 1.5, "AC"),
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


def electrical(m: Model) -> dict:
    levels = []
    circuits = []
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
                pts.append({"kind": "PL", "x": round(cx + dx, 2), "y": round(cy, 2), "room": r["name"]})
                pl_pts.append(r["name"])
            pts.append({"kind": "INT", "x": round(r["x0"] + 0.25, 2), "y": round(r["y0"] + 0.25, 2), "room": r["name"]})
            for k in range(rule["rj45"]):
                pts.append({"kind": "RJ45", "x": round(r["x1"] - 0.30 - 0.3 * k, 2), "y": round(r["y1"] - 0.15, 2), "room": r["name"]})
            for j, sp in enumerate(rule["spec"]):
                if sp in SPEC_CIRCUITS:
                    pts.append({"kind": "SPEC", "code": sp, "x": round(r["x1"] - 0.25, 2), "y": round(r["y0"] + 0.35 + 0.35 * j, 2), "room": r["name"]})
                    circuits.append({"level": lv.id, "name": f"{SPEC_CIRCUITS[sp][0]} ({r['name']})", "breaker": SPEC_CIRCUITS[sp][1],
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


def plumbing(m: Model) -> dict:
    cfg = m.raw.get("mep") or {}
    stacks = [dict(s, d=s.get("d", 100)) for s in cfg["stacks"]] if cfg.get("stacks") else [
        {"id": "CH1", "x": 7.65, "y": 6.85, "serves": "SDB comble, WC + SDB étage, cuisine RDC", "d": 100},
        {"id": "CH2", "x": 5.30, "y": 0.50, "serves": "SDB P étage, SDE RDC", "d": 100},
    ]
    collector = dict(cfg["collector"], id="COL", path=[tuple(p) for p in cfg["collector"]["path"]]) if cfg.get("collector") else \
        {"id": "COL", "path": [(7.65, 6.85), (10.79, 6.85)], "exit": "traversée du voile façade rue à -0,80 (fourreau étanche) puis branchement au réseau public"}
    nourrice = dict(cfg["nourrice"]) if cfg.get("nourrice") else {"x": 4.20, "y": 6.60, "level": "SS", "room": "Local technique"}
    ext = cfg.get("outdoor_tap") or {"level": "RDC", "room": "Façade rue", "x": 11.0, "y": 6.0}
    ids = [l.id for l in m.levels]
    bsmt = m.levels[0].floor_top < -1.0
    fixtures = []
    for lv in m.levels:
        for r in m.rooms(lv.id):
            names = list(r.get("fixtures", []))
            if r["type"] == "buanderie":
                names = ["lave_linge", "evier"]
            for k, f in enumerate(names):
                spec = FIX[f]
                fx = r["x0"] + 0.35 + 0.65 * k
                fy = r["y1"] - 0.35 if r["y1"] >= m.W - m.t_tot - 0.1 else r["y0"] + 0.35
                stack = min(stacks, key=lambda s: math.hypot(s["x"] - fx, s["y"] - fy))
                dist = abs(stack["x"] - fx) + abs(stack["y"] - fy)
                fixtures.append({"level": lv.id, "room": r["name"], "fixture": f, "label": spec["label"], "x": round(min(fx, r["x1"] - 0.3), 2),
                                 "y": round(fy, 2), "q": spec["q"], "alim": _pipe_for(spec["d_alim"]), "ecs": spec["ecs"],
                                 "evac": f"PVC Ø{spec['d_evac']}" if spec["d_evac"] else "—", "stack": stack["id"],
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
                     "spec": "Poste de relevage eaux grises/vannes en buanderie (cuve 60 L, clapet anti-retour, refoulement Ø40 jusqu'au collecteur en plafond du sous-sol)" if relevage else ""},
        "ventilation": "Chutes Ø100 prolongées en ventilation primaire hors toiture (sorties tuiles à douille) ; clapets aérateurs interdits en substitution unique",
        "rain": cfg.get("rain", "Gouttières zinc demi-rondes 33 sur les deux égouts, 2 descentes Ø80 par façade, dauphins fonte côté rue ; rejet EP selon PLU (infiltration à la parcelle à vérifier)"),
        "warnings": warn,
        "rules": [
            "Diamètres intérieurs mini d'alimentation (DTU 60.11) : évier, douche 12 mm ; lavabo, WC, lave-linge 10 mm ; baignoire 13 mm.",
            "Évacuations : lavabo Ø32, évier/douche/baignoire/lave-linge Ø40, WC Ø100 ; pente 1 à 3 % ; longueur ≤ 3 m sans ventilation (≤ 4 m pour WC Ø100).",
            ("Chutes EU/EV unique Ø100 alignées sur les pièces humides superposées (" + " ; ".join(f"{s['id']} : {s['serves']}" for s in stacks) + ").") if cfg.get("stacks") else
            "Chutes EU/EV unique Ø100 alignées sur les pièces humides superposées (CH1 : WC étage / SDB comble / cuisine ; CH2 : SDB P / SDE).",
            f"Coefficient de simultanéité y = 0,8/√(x−1) = {y:.3f} pour x = {x} appareils → débit probable {qp:.2f} l/s.",
        ] + (["Sous-sol sous le niveau de la rue : appareils du sous-sol raccordés par poste de relevage (réseau public présumé plus haut)."] if relevage else
             ["Évacuations gravitaires jusqu'au regard de branchement en limite de propriété (pente ≥ 2 %)."]),
    }
