"""Génie climatique sur la même géométrie : déperditions pièce par pièce, plancher chauffant/rafraîchissant
alimenté par PAC air/eau, ventilation (VMC double flux ou simple flux hygro B), gaine technique.

Méthode (pré-dimensionnement BET, à confirmer par l'étude thermique RE 2020) :
- déperditions par transmission NF EN 12831 simplifiée : Σ U·A·ΔT par paroi extérieure de chaque pièce, + 10 % de
  ponts thermiques ; mitoyens chauffés = 0 ; parois enterrées avec coefficient de réduction 0,5 ;
- renouvellement d'air : 0,34 · q · (1 − η) (η = 0,85 en double flux) ;
- plancher chauffant NF DTU 65.14 : émission ≤ 100 W/m² (zones de séjour, 29 °C de surface), pas 10/15/20 cm,
  boucles ≤ 100 m liaisons comprises, ≤ 12 départs par collecteur ;
- ventilation : arrêté du 24 mars 1982 modifié (débits d'extraction selon le nombre de pièces principales).
"""
from __future__ import annotations

import math
import re

from .model import Model

DRY = {"sejour", "chambre", "bureau"}
WET = {"cuisine", "salle_eau", "sdb", "sde", "wc", "buanderie"}
UNHEATED = {"garage", "local_technique"}

# température de base (°C) — NF EN 12831/A1 annexe nationale, par département (défaut H1a : −7)
TBASE = {"75": -5, "92": -5, "93": -5, "94": -5, "77": -7, "78": -7, "91": -7, "95": -7, "13": -5, "06": -2, "33": -5,
         "69": -10, "67": -15, "68": -15, "59": -9, "62": -9, "44": -5, "35": -4, "31": -5, "34": -5, "38": -10, "63": -8}

# arrêté du 24/03/1982 : nombre de pièces principales → (cuisine base, cuisine pointe, total mini)
VMC_TABLE = {1: (20, 75, 35), 2: (30, 90, 60), 3: (45, 105, 75), 4: (45, 120, 90), 5: (45, 135, 105), 6: (45, 135, 120), 7: (45, 135, 135)}
PAC_SIZES = (4, 5, 6, 8, 10, 12, 14, 16, 20)


def _area(r):
    return sum((p["x1"] - p["x0"]) * (p["y1"] - p["y0"]) for p in [r] + r.get("parts", []))


def _kind(r):
    t = r["type"]
    return {"sdb": "salle_eau", "sde": "salle_eau", "degagement": "circulation"}.get(t, t)


# ------------------------------------------------------------------ options (hypothèses du client)
def options(m: Model) -> dict:
    """Systèmes retenus : champs explicites du relevé, sinon lecture déterministe des hypothèses du client, sinon défaut RE 2020."""
    uh = m.raw.get("user_hypotheses") or {}
    txt = " ".join(str(v) for v in [uh.get("_text", ""), uh.get("_source", "")] + [str(x) for x in (m.raw.get("_decisions") or [])]).lower()
    src = {}

    def pick(key, explicit, patterns, default):
        if explicit:
            src[key] = "relevé"
            return explicit
        for pat, val in patterns:
            if re.search(pat, txt):
                src[key] = "demande du client"
                return val
        src[key] = "hypothèse ConstruPilot"
        return default

    heating = pick("heating", uh.get("heating"), [(r"plancher[s]? chauffant|pc r[ée]versible|chauffage au sol", "pac_plancher_chauffant"),
                                                  (r"radiateur", "pac_radiateurs")], "pac_plancher_chauffant")
    vent = pick("ventilation", uh.get("ventilation"), [(r"double[- ]?fl[eu]|\bdf\b", "double_flux"), (r"simple[- ]?flux|hygro", "simple_flux_hygro_b")],
                "simple_flux_hygro_b")
    cooling = uh.get("cooling")
    if cooling is None:
        cooling = bool(re.search(r"r[ée]versible|rafra[iî]ch|clim", txt))
        src["cooling"] = "demande du client" if cooling else "hypothèse ConstruPilot"
    ins = uh.get("insulation_mm")
    if not ins:
        mm_ = re.search(r"isolation[^0-9]{0,25}(\d{2,3})|(\d{2,3})\s*(?:mm)?\s*(?:d['’]\s*)?isol", txt)
        ins = int(next(g for g in mm_.groups() if g)) if mm_ else 120
        src["insulation"] = "demande du client" if mm_ else "hypothèse ConstruPilot"
        if ins < 40:                      # « 16 » écrit en cm
            ins *= 10
    return {"heating": heating, "ventilation": vent, "cooling": bool(cooling), "insulation_mm": int(ins), "source": src}


# ------------------------------------------------------------------ gaine technique et points de distribution
def gaine(m: Model, stacks: list[dict], fixtures: list[dict] | None = None) -> dict:
    """Gaine technique verticale (fluides, VMC, chauffage) accolée à la chute principale, à l'endroit qui ne recouvre
    aucun appareil sanitaire sur l'ensemble des niveaux ; colonne électrique séparée depuis la GTL."""
    cfg = (m.raw.get("mep") or {}).get("gaine")
    if cfg:
        return dict(cfg, w=cfg.get("w", 0.50), d=cfg.get("d", 0.40))
    st = stacks[0] if stacks else {"x": m.L / 2, "y": m.W - m.t_tot - 0.3}
    tt, w, d = m.t_tot, 0.50, 0.40
    boxes = []
    for f in fixtures or []:
        fw, fd = (f.get("w") or 0.6), (f.get("d") or 0.6)
        hor = f.get("wall") in ("y0", "y1", None)
        hw, hd = ((fw, fd) if hor else (fd, fw))
        boxes.append((f["x"] - hw / 2, f["y"] - hd / 2, f["x"] + hw / 2, f["y"] + hd / 2))
    walls = [(c["x"] - c["t"] / 2, c["y0"], c["x"] + c["t"] / 2, c["y1"]) for c in m.stair.get("cage_walls", [])]

    def cost(x, y):
        r = (x - w / 2, y - d / 2, x + w / 2, y + d / 2)
        if r[0] < tt or r[2] > m.L - tt or r[1] < tt or r[3] > m.W - tt:
            return 1e9
        ov = 0.0
        for b in boxes + walls:
            ix = max(0.0, min(r[2], b[2]) - max(r[0], b[0]))
            iy = max(0.0, min(r[3], b[3]) - max(r[1], b[1]))
            ov += ix * iy
        sx, sy = m.stair["x0"], m.stair["y0"]
        if m.stair["x0"] - 0.05 < x < m.stair["x1"] + 0.05 and m.stair["y0"] - 0.05 < y < m.stair["y1"] + 0.05:
            ov += 10
        return ov * 100 + abs(x - st["x"]) + abs(y - st["y"])
    cands = [(st["x"] + dx, st["y"] + dy) for dx in (-0.85, -0.55, -0.30, 0.0, 0.30, 0.55, 0.85) for dy in (-0.85, -0.55, -0.30, 0.0, 0.30)]
    cands += [(st["x"] + dx, m.W - tt - d / 2) for dx in (-1.2, -0.9, -0.6, 0.6, 0.9, 1.2)]
    x, y = min(cands, key=lambda c: cost(*c))
    if cost(x, y) >= 1e9:
        x, y = st["x"] + 0.30, min(max(st["y"], tt + 0.25), m.W - tt - 0.25)
    return {"x": round(x, 2), "y": round(y, 2), "w": w, "d": d,
            "content": "montées EF/ECS, départ/retour chauffage, conduits VMC Ø160, fourreaux courants faibles"}


def gtl(m: Model) -> dict:
    """GTL (NF C 15-100 §771.558) : dans l'entrée du niveau d'accès, contre la face intérieure d'un mur de façade."""
    cfg = (m.raw.get("mep") or {}).get("gtl")
    if cfg:
        return dict(cfg)
    tt = m.t_tot
    for lv in m.levels:
        if lv.floor_top < -1.0:
            continue
        rooms = m.rooms(lv.id)
        hall = next((r for r in rooms if _kind(r) == "entree"), None) or next((r for r in rooms if _kind(r) == "circulation"), None) or (rooms[0] if rooms else None)
        if not hall:
            break
        cy = (hall["y0"] + hall["y1"]) / 2
        if hall["x1"] >= m.L - tt - 0.05:
            return {"level": lv.id, "x": round(hall["x1"] - 0.12, 2), "y": round(cy, 2), "room": hall["name"], "wall": "x1"}
        if hall["x0"] <= tt + 0.05:
            return {"level": lv.id, "x": round(hall["x0"] + 0.12, 2), "y": round(cy, 2), "room": hall["name"], "wall": "x0"}
        return {"level": lv.id, "x": round(hall["x0"] + 0.12, 2), "y": round(cy, 2), "room": hall["name"], "wall": "x0"}
    return {"level": m.levels[0].id, "x": tt + 0.12, "y": m.W / 2, "room": "", "wall": "x0"}


def collector_xy(m: Model, lid: str, g: dict) -> tuple[float, float]:
    """Collecteur de plancher chauffant de l'étage : niche dans le dégagement, au plus près de la gaine technique."""
    rooms = [r for r in m.rooms(lid) if _kind(r) in ("circulation", "entree")]
    if not rooms:
        return g["x"] - 0.45, g["y"]
    r = min(rooms, key=lambda r: abs((r["x0"] + r["x1"]) / 2 - g["x"]) + abs((r["y0"] + r["y1"]) / 2 - g["y"]))
    x = min(max(g["x"], r["x0"] + 0.45), r["x1"] - 0.45)
    y = r["y1"] - 0.10 if abs(r["y1"] - g["y"]) < abs(r["y0"] - g["y"]) else r["y0"] + 0.10
    return round(x, 2), round(y, 2)


# ------------------------------------------------------------------ déperditions
def _heated_level(m: Model, lv) -> bool:
    """Sous-sol hors volume chauffé quand une étude thermique l'a exclu (garage, cave) ; sinon comportement historique."""
    if not m.raw.get("thermal"):
        return True
    return lv.floor_top > -1.0 or "habit" in (lv.use or "")


def _u_values(opt: dict) -> dict:
    e = opt["insulation_mm"] / 1000
    u_wall = 1 / (0.13 + 0.04 + 1.0 + e / 0.032 + 0.01)       # brique 20 (R≈1,0) + doublage PSE graphité λ 0,032
    return {"wall": round(u_wall, 3), "window": 1.30, "door": 1.50, "roof": 0.14, "floor_ground": 0.25, "buried": 0.35}


def heat_loss(m: Model, opt: dict) -> dict:
    proj = m.raw.get("project") or {}
    cp = re.search(r"\b(\d{5})\b", str(proj.get("address", "")))
    dep = cp.group(1)[:2] if cp else ""
    if not dep:
        d2 = re.search(r"\((\d{2})\)", str(proj.get("address", "")))
        dep = d2.group(1) if d2 else ""
    if not dep:
        dep = str(proj.get("code_postal") or "")[:2]
    tb = TBASE.get(dep, -7)
    ti = 20.0
    U = _u_values(opt)
    th = m.raw.get("thermal") or {}
    if th.get("U"):                                   # étude thermique faite : mêmes U que la RE2020
        U.update({"wall": th["U"]["mur"], "window": th["U"]["fenetre"], "door": th["U"]["porte"],
                  "roof": th["U"]["rampants"] if m.roof.get("habitable_attic") else th["U"]["combles"],
                  "floor_ground": th["U"]["plancher_bas"]})
    tt = m.t_tot
    eta = 0.85 if opt["ventilation"] == "double_flux" else 0.0
    vent = ventilation(m, opt)
    q_tot = vent["q_total_base"]
    heated = [(lv, r) for lv in m.levels for r in m.rooms(lv.id) if _kind(r) not in UNHEATED and _heated_level(m, lv)]
    a_heated = sum(_area(r) for _, r in heated) or 1.0
    sides = m.raw["sides"]
    rooms = []
    for lv, r in heated:
        h = m.storey_height(lv.id)
        buried = lv.floor_top < -1.0
        dT = ti - tb
        walls = 0.0
        win = 0.0
        exp = []
        for sid, sd in sides.items():
            mit = sd.get("type") == "mitoyen"
            if sd["axis"] == "x":                         # mur perpendiculaire à X (façade), longueur selon Y
                at = (r["x0"] <= tt + 0.05) if sd["pos"] < m.L / 2 else (r["x1"] >= m.L - tt - 0.05)
                a0, a1 = r["y0"], r["y1"]
            else:
                at = (r["y0"] <= tt + 0.05) if sd["pos"] < m.W / 2 else (r["y1"] >= m.W - tt - 0.05)
                a0, a1 = r["x0"], r["x1"]
            if not at:
                continue
            ops = [o for o in m.openings_on(sid, lv.id) if o.b > a0 + 0.05 and o.a < a1 - 0.05]
            a_op = sum(o.width * o.height for o in ops)
            gross = (a1 - a0) * h
            walls += max(gross - a_op, 0) * (U["buried"] * 0.5 if buried else U["wall"]) * (0.25 if mit else 1.0)   # mitoyen : voisin à 15 °C
            win += sum(o.width * o.height * (U["door"] if "porte" in o.kind else U["window"]) for o in ops)
            exp.append(sid)
        roof = _area(r) * 1.15 * U["roof"] if lv.id == m.levels[-1].id else 0.0
        floor = _area(r) * U["floor_ground"] * 0.5 if lv.id == m.levels[0].id else 0.0
        trans = (walls + win + roof + floor) * 1.10 * dT
        q_room = q_tot * _area(r) / a_heated
        inf = 0.15 * _area(r) * h                                # infiltrations (n = 0,15 vol/h, Q4 ≤ 0,6)
        ven = 0.34 * (q_room * (1 - eta) + inf) * dT
        phi = trans + ven
        rooms.append({"level": lv.id, "room": r["name"], "type": _kind(r), "area": round(_area(r), 2), "exposed": exp,
                      "phi_w": round(phi), "w_m2": round(phi / max(_area(r), 0.5)), "trans_w": round(trans), "vent_w": round(ven)})
    total = sum(x["phi_w"] for x in rooms)
    kw = total / 1000 * 1.10                                  # relance + marge 10 %
    pac = next((s for s in PAC_SIZES if s >= kw), PAC_SIZES[-1])
    cold = round(sum(x["area"] for x in rooms if x["type"] in DRY) * 30 / 1000, 1)
    return {"t_base": tb, "t_int": ti, "dept": dep or "?", "U": U, "rooms": rooms, "total_w": round(total), "a_heated": round(a_heated, 1),
            "w_m2": round(total / a_heated), "pac_kw": pac, "pac_need_kw": round(kw, 1), "cooling_kw": cold if opt["cooling"] else 0.0}


# ------------------------------------------------------------------ plancher chauffant
def floor_heating(m: Model, opt: dict, loss: dict, g: dict) -> dict:
    levels = []
    for lv in m.levels:
        cx, cy = collector_xy(m, lv.id, g)
        loops = []
        for r in m.rooms(lv.id):
            if _kind(r) in UNHEATED or not _heated_level(m, lv):
                continue
            info = next((x for x in loss["rooms"] if x["level"] == lv.id and x["room"] == r["name"]), None)
            if not info:
                continue
            q = info["w_m2"]
            pitch = 0.10 if q > 70 or _kind(r) == "salle_eau" else (0.15 if (q > 35 or opt["cooling"]) else 0.20)
            for k, part in enumerate([r] + r.get("parts", [])):
                w, h = part["x1"] - part["x0"], part["y1"] - part["y0"]
                a = w * h
                d = abs((part["x0"] + part["x1"]) / 2 - cx) + abs((part["y0"] + part["y1"]) / 2 - cy)
                a_max = max(2.0, (100 - 2 * d) * pitch * 0.92)
                n = max(1, math.ceil(a / a_max))
                for j in range(n):                            # découpe en bandes le long du plus grand côté
                    if w >= h:
                        sx0 = part["x0"] + w * j / n
                        rect = (sx0, part["y0"], sx0 + w / n, part["y1"])
                    else:
                        sy0 = part["y0"] + h * j / n
                        rect = (part["x0"], sy0, part["x1"], sy0 + h / n)
                    la = (rect[2] - rect[0]) * (rect[3] - rect[1])
                    L = la / pitch + 2 * d
                    flow = (info["w_m2"] * la) / (1.163 * 5) if la else 0
                    loops.append({"room": r["name"], "rect": tuple(round(v, 3) for v in rect), "area": round(la, 2), "pitch": pitch,
                                  "length_m": round(L), "flow_lh": round(flow), "w_m2": q, "dist": round(d, 2)})
        for i, lp in enumerate(loops):
            lp["id"] = f"{lv.id}-B{i+1}"
        ncol = max(1, math.ceil(len(loops) / 12))
        if loops:
            levels.append({"level": lv.id, "collector": (cx, cy), "loops": loops, "collectors": ncol,
                           "outputs": len(loops), "tube_m": sum(l["length_m"] for l in loops)})
    total_loops = sum(len(l["loops"]) for l in levels)
    return {"system": "Plancher chauffant" + ("/rafraîchissant" if opt["cooling"] else "") + " hydraulique basse température, tube PER-BAO Ø16 × 1,5 (barrière O₂)",
            "levels": levels, "loops": total_loops, "tube_m": sum(l["tube_m"] for l in levels),
            "regime": "départ 35 °C / retour 30 °C à −{:d} °C extérieur (loi d'eau)".format(-loss["t_base"]) +
                      (" ; rafraîchissement départ 18 °C mini, sonde d'hygrométrie (point de rosée)" if opt["cooling"] else ""),
            "build_up": [("Revêtement (carrelage collé ou parquet collé R ≤ 0,15)", 1.0), ("Chape fluide anhydrite (≥ 3 cm au-dessus des tubes)", 5.0),
                         ("Tubes PER Ø16 sur plaque à plots", 0.0), ("Isolant à plots PSE (film intégré)", 3.0),
                         ("Isolant PU / PSE graphité sous plancher", 7.0 if True else 0.0), ("Plancher porteur poutrelles-hourdis 25+5", 30.0)],
            "rules": ["Boucles ≤ 100 m liaisons comprises ; ≤ 12 départs par collecteur ; débitmètres et vannes d'équilibrage sur chaque départ.",
                      "Bande périphérique 8 mm sur tout le pourtour ; joints de fractionnement > 40 m² ou côté > 8 m et au droit des portes.",
                      "Essai d'étanchéité 6 bar 24 h avant coulage (PV) ; première mise en chauffe 7 jours après coulage, montée 5 °C/jour.",
                      "Température de surface ≤ 28 °C (séjours/chambres), ≤ 33 °C en salle d'eau ; pas réduit (10 cm) en salle d'eau et le long des baies."]}


# ------------------------------------------------------------------ ventilation
def ventilation(m: Model, opt: dict) -> dict:
    rooms = [(lv, r) for lv in m.levels for r in m.rooms(lv.id)]
    n_pp = max(1, min(7, sum(1 for _, r in rooms if _kind(r) in DRY)))
    cb, cp_, total_min = VMC_TABLE[n_pp]
    wets = [(lv, r) for lv, r in rooms if _kind(r) in ("cuisine", "salle_eau", "wc", "buanderie")]
    n_wc = sum(1 for _, r in rooms if _kind(r) == "wc")
    bouches = []
    first_bath = True
    for lv, r in wets:
        k = _kind(r)
        if k == "cuisine":
            q, qp, d = cb, cp_, 125
        elif k == "salle_eau":
            q = 30 if (first_bath and n_pp >= 3) else 15
            first_bath = False
            qp, d = q, 80
        elif k == "wc":
            q = 30 if (n_wc == 1 and n_pp >= 4) else 15
            qp, d = q, 80
        else:
            q, qp, d = 15, 15, 80
        cx, cy = (r["x0"] + r["x1"]) / 2, (r["y0"] + r["y1"]) / 2
        bouches.append({"level": lv.id, "room": r["name"], "kind": "extraction", "q": q, "q_pointe": qp, "d": d, "x": round(cx, 2), "y": round(cy, 2)})
    q_ex = sum(b["q"] for b in bouches)
    q_ex = max(q_ex, total_min)
    if opt["ventilation"] == "double_flux":
        dry = [(lv, r) for lv, r in rooms if _kind(r) in DRY]
        weights = [(lv, r, 2 if _kind(r) == "sejour" else 1) for lv, r in dry]
        wsum = sum(w for *_, w in weights) or 1
        for lv, r, w in weights:
            q = round(q_ex * w / wsum / 5) * 5
            for j in range(w):
                fx = r["x0"] + (r["x1"] - r["x0"]) * (j + 1) / (w + 1)
                bouches.append({"level": lv.id, "room": r["name"], "kind": "soufflage", "q": round(q / w), "q_pointe": round(q / w),
                                "d": 80, "x": round(fx, 2), "y": round(r["y0"] + (r["y1"] - r["y0"]) * 0.62, 2)})
    lt = next(((lv, r) for lv, r in rooms if _kind(r) == "local_technique"), None)
    top = m.levels[-1]
    if lt:
        cais = {"level": lt[0].id, "room": lt[1]["name"], "x": round(lt[1]["x0"] + 0.55, 2), "y": round(lt[1]["y1"] - 0.45, 2)}
    else:
        rr = next((r for r in m.rooms(top.id) if _kind(r) == "circulation"), (m.rooms(top.id) or [{"name": "", "x0": 1, "y0": 1, "x1": 2, "y1": 2}])[0])
        cais = {"level": top.id, "room": rr["name"], "x": round((rr["x0"] + rr["x1"]) / 2, 2), "y": round((rr["y0"] + rr["y1"]) / 2, 2)}
    df = opt["ventilation"] == "double_flux"
    return {"system": ("VMC double flux haut rendement (échangeur ≥ 85 %, moteurs basse consommation, by-pass été)" if df else
                       "VMC simple flux hygroréglable type B (entrées d'air hygro en menuiseries)"),
            "double_flux": df, "n_pp": n_pp, "bouches": bouches, "q_total_base": q_ex, "q_kitchen_peak": cp_,
            "q_insufflation": sum(b["q"] for b in bouches if b["kind"] == "soufflage"), "caisson": cais,
            "network": ("Réseau pieuvre : plénums de répartition par niveau, conduits semi-rigides PEHD Ø75/Ø90 (1 conduit par 30 m³/h), "
                        "collecteurs verticaux Ø160 isolés en gaine technique" if df else
                        "Conduits souples isolés Ø80 (pièces d'eau) et Ø125 (cuisine) vers le caisson, rejet Ø160 en toiture"),
            "rules": [f"Arrêté du 24/03/1982 : {n_pp} pièces principales → cuisine {cb}/{cp_} m³/h, total mini {total_min} m³/h.",
                      "Rejet d'air vicié en toiture (sortie de toit), prise d'air neuf à ≥ 8 m du rejet ou en façade opposée, filtres G4 (extraction) / F7 (air neuf)." if df else
                      "Rejet en toiture par sortie de toit Ø160 ; entrées d'air hygroréglables dans les menuiseries des pièces principales.",
                      "Conduits en volume chauffé (sinon isolés 50 mm) ; trappes d'accès au caisson et aux plénums ; détalonnage des portes 2 cm.",
                      "Équilibrage et mesure des débits à la réception (protocole Promevent / RE 2020)."]}


def hvac(m: Model, stacks: list[dict], fixtures: list[dict] | None = None) -> dict:
    opt = options(m)
    if fixtures is None:
        from .mep import plumbing
        fixtures = plumbing(m)["fixtures"]
    g = gaine(m, stacks, fixtures)
    loss = heat_loss(m, opt)
    v = ventilation(m, opt)
    pc = floor_heating(m, opt, loss, g) if opt["heating"] == "pac_plancher_chauffant" else None
    return {"options": opt, "gaine": g, "gtl": gtl(m), "loss": loss, "vmc": v, "pc": pc,
            "pac": {"kw": loss["pac_kw"], "need_kw": loss["pac_need_kw"], "cooling_kw": loss["cooling_kw"],
                    "label": f"PAC air/eau {'réversible ' if opt['cooling'] else ''}{loss['pac_kw']} kW (Tbase {loss['t_base']} °C)",
                    "outdoor": "Unité extérieure sur plots anti-vibratiles, façade jardin, à ≥ 0,50 m du mur et ≥ 3 m des baies voisines (bruit)",
                    "buffer_l": 50 if loss["pac_kw"] <= 8 else 100,
                    "power": "Alimentation dédiée depuis le tableau, disjoncteur courbe D, interrupteur de proximité (NF C 15-100)"},
            "ecs": "Chauffe-eau thermodynamique 200 L (ou ballon ECS sur PAC double service) en local technique"}
