"""Lots techniques (France) de l'immeuble : pré-étude RE2020 du bâtiment, plomberie (NF DTU 60.11) et électricité (NF C 15-100 /
NF C 14-100). Moteurs ConstruPilot FR : calc_lots.re2020, plomberie, electricite. Études préalables indicatives.

Codes de pièces du modèle (rooms[].kind) : sala → séjour, quarto → chambre, cozinha → cuisine, casa_de_banho → salle de bains,
lavandaria → cellier, corredor → dégagement, escritorio → bureau, arrumos → rangement.
"""
from __future__ import annotations

import math
from pathlib import Path

from reportlab.lib.units import mm

from .textos import fmt as f

W = mm
KIND_FR = {"sala": "sejour", "quarto": "chambre", "cozinha": "cuisine", "casa_de_banho": "salle_de_bain", "lavandaria": "cellier",
           "corredor": "degagement", "escritorio": "bureau", "arrumos": "rangement"}
COEF = [(4, 1.00), (9, 0.78), (14, 0.63), (19, 0.53), (24, 0.49), (29, 0.46), (34, 0.44), (39, 0.42), (49, 0.41), (10 ** 6, 0.38)]   # NF C 14-100
IZ = [(10, 60), (16, 80), (25, 101), (35, 126), (50, 153), (70, 196), (95, 238), (120, 276), (150, 319), (185, 364), (240, 430)]
PE = [(32, 26.2), (40, 32.6), (50, 40.8), (63, 51.4), (75, 61.4), (90, 73.6), (110, 90.0)]


def _mods():
    from engines.calc_lots import electricite, plomberie, re2020
    return re2020, plomberie, electricite


def _area(u):
    return sum(float(r.get("area") or 0) for r in u.get("rooms") or [])


def _tip(u) -> int:
    t = str(u.get("typology") or "")
    if t.upper().startswith("T") and t[1:2].isdigit():
        return int(t[1])
    return max(1, sum(1 for r in u.get("rooms") or [] if r.get("kind") == "quarto"))


def _n_wc(u):
    return max(1, sum(1 for r in u.get("rooms") or [] if r.get("kind") == "casa_de_banho"))


# ------------------------------------------------------------------ thermique (bâtiment)
def thermique_params(S) -> dict:
    ch = S.clear_h
    ot = S.opening_types
    walls, wins = {}, {}
    common = 0.0
    for u in S.units:
        glaz = {}
        for o in u.get("openings") or []:
            d = ot.get(o["type"]) or {}
            glaz[o.get("facade")] = glaz.get(o.get("facade"), 0.0) + int(o.get("count") or 1) * float(d.get("width") or 0) * float(d.get("height") or 0)
        for fa in u.get("facades") or []:
            o = (fa.get("orientation") or "S").upper().replace("W", "O")
            walls[o] = walls.get(o, 0.0) + max(float(fa.get("length") or 0) * ch - glaz.get(o, 0.0), 0.0)
        for o, a in glaz.items():
            wins[o] = wins.get(o, 0.0) + a
        common += float(u.get("common_wall_m") or 0) * ch
    parois = [{"type": "mur", "surface_m2": round(a, 1), "U": 0.20, "orientation": o} for o, a in walls.items() if a > 0.5]
    for o, a in wins.items():
        side = S.side_of_orientation(o)
        parois.append({"type": "fenetre", "surface_m2": round(a, 1), "U": 1.2, "orientation": o, "protection": "volets",
                       "debord": any(b["side"] == side for b in S.balconies) if side else False})
    if common > 0.5:
        parois.append({"type": "mur", "surface_m2": round(common, 1), "U": 0.35, "cote": "local_non_chauffe"})
    parois.append({"type": "toiture", "surface_m2": round(S.area_floor, 1), "U": 0.13})
    parois.append({"type": "plancher_bas", "surface_m2": round(S.area_floor, 1), "U": 0.18, "cote": "garage" if S.basement else "terre_plein"})
    pv = S.systems.get("pv_kwp")
    p = {"type_batiment": "collectif", "sref_m2": round(sum(_area(u) for u in S.units), 1), "nb_logements": len(S.units),
         "code_postal": (S.raw.get("project") or {}).get("postal_code"), "altitude_m": S.altitude, "niveaux": S.n, "hauteur_m": ch,
         "structure": "beton_banche", "parois": parois, "chauffage": S.systems.get("heating_fr") or "pac_air_eau",
         "ecs": S.systems.get("dhw_fr") or "cet", "ventilation": "vmc_sf_hygro_b", "ratio_psi": 0.22}
    if pv:
        p["pv_kwc"] = float(pv)
    return p


# ------------------------------------------------------------------ plomberie
def _appareils(u):
    n = _n_wc(u)
    ap = [{"type": "lavabo", "nombre": n}, {"type": "wc", "nombre": n}, {"type": "douche", "nombre": 1}, {"type": "evier", "nombre": 1},
          {"type": "lave_linge", "nombre": 1}, {"type": "lave_vaisselle", "nombre": 1}]
    if n >= 2:
        ap.append({"type": "baignoire", "nombre": 1})
    return ap


def _tube(q, vmax=1.5):
    for dn, di in PE:
        v = q / 1000 / (math.pi * (di / 1000) ** 2 / 4)
        if v <= vmax:
            return dn, di, v
    dn, di = PE[-1]
    return dn, di, q / 1000 / (math.pi * (di / 1000) ** 2 / 4)


def _j(q, di):
    v = q / 1000 / (math.pi * (di / 1000) ** 2 / 4)
    Re = max(v * di / 1000 / 1.3e-6, 1)
    lam = 0.3164 / Re ** 0.25
    return lam / (di / 1000) * v * v / 2 / 9.81


def plomberie(S):
    _, PL, _ = _mods()
    A = PL.APPAREILS
    lots = []
    for u in S.units:
        ap = _appareils(u)
        r = PL.calculer({"appareils": ap, "personnes": {0: 2, 1: 2, 2: 3, 3: 4}.get(_tip(u), 5), "longueur_m": 15})
        lots.append({"id": u["id"], "level": int(u["level"]), "tip": f"T{_tip(u)}", "ap": ap, "r": r,
                     "n_app": sum(a["nombre"] for a in ap), "sq": sum(max(A[a["type"]]["ef"], A[a["type"]]["ecs"]) * a["nombre"] for a in ap)})
    x = sum(l_["n_app"] for l_ in lots)
    qp = max(PL.simultaneite(x) * sum(l_["sq"] for l_ in lots), 0.5)
    br = _tube(qp)
    col = []
    for k in range(S.n):
        sel = [l_ for l_ in lots if l_["level"] >= k]
        xk = sum(l_["n_app"] for l_ in sel)
        qk = max(PL.simultaneite(xk) * sum(l_["sq"] for l_ in sel), 0.3)
        dn, di, v = _tube(qk)
        col.append({"troncon": ("Branchement → " if k == 0 else S.lname(k - 1) + " → ") + S.lname(k), "x": xk, "q": qk, "dn": dn, "v": v,
                    "L": S.H if k else 6.0, "j": _j(qk, di)})
    P = float(S.network.get("water_pressure_kpa") or 300.0)
    zst = float(S.network.get("street_level") or S.z0)
    top = max(lots, key=lambda l_: l_["level"]) if lots else None
    dz = (S.z0 + S.H * top["level"] + 1.8 - zst) if top else 0.0
    Jt = (_j(qp, br[1]) * 25 * 1.2 + sum(c["j"] * c["L"] for c in col) * 1.2 + 3.0)
    p_top = P - (Jt + dz) * 9.81
    p_low = P - (2.1 - (zst - S.z0)) * 9.81
    roof = S.area_floor + S.balcony_area()
    n_ep = max(2, math.ceil(roof / 78))
    d_ep = next((d for d in (80, 100, 125, 160) if math.pi * (d / 10) ** 2 / 4 >= roof / n_ep), 160)     # 1 cm² de descente par m² (DTU 60.11)
    return {"lots": lots, "qp": qp, "br": br, "col": col, "P": P, "p_top": p_top, "p_low": p_low, "dz": dz, "top": top["id"] if top else None,
            "ep": {"surface": roof, "n": n_ep, "d": d_ep, "q": 0.05 * roof}}


# ------------------------------------------------------------------ électricité
def electricite(S):
    _, _, EL = _mods()
    lots = []
    for u in S.units:
        pieces = [{"nom": r.get("name") or r.get("kind"), "type": KIND_FR.get(r.get("kind"), "autre"), "surface_m2": float(r.get("area") or 0)}
                  for r in u.get("rooms") or []]
        r = EL.calculer({"pieces": pieces, "equipements": {"plaque": "mono", "four": True, "lave_linge": True, "lave_vaisselle": True,
                                                           "chauffe_eau_w": 1800, "vmc": True},
                         "pac": {"p_absorbee_kw": 1.5 + 0.3 * _tip(u), "appoint_kw": 0, "alimentation": "mono"}})
        lots.append({"id": u["id"], "tip": f"T{_tip(u)}", "r": r, "kva": r["abonnement_kva"]})
    n = len(lots)
    coef = next(c for lim, c in COEF if n <= lim)
    p_lots = sum(l_["kva"] for l_ in lots)
    p_col = p_lots * coef
    lifts = sum(1 for c in S.cores if c["kind"] == "lift")
    SG = []
    if lifts:
        SG.append((f"Ascenseur × {lifts}", 7.5 * lifts))
    SG.append(("Éclairage des parties communes (LED + BAES)", 0.25 * (S.n + 1)))
    if S.basement:
        A_c = S.basement_area()
        SG += [(f"Éclairage du parc de stationnement ({f(A_c, 0)} m²)", round(A_c * 0.005, 1)), ("Ventilation / désenfumage du parc", round(max(2.2, A_c / 140), 1)),
               ("Porte automatique du parking", 0.75), ("Poste de relevage (2 pompes)", 2.2)]
    SG += [("SSI / détection CO, interphonie, courants faibles", 0.8), ("Surpresseur (si nécessaire)", 2.2)]
    if S.parking:
        SG.append((f"IRVE — {S.parking} places, pilotage dynamique (décret 2020-1696)", round(max(7.4, 1.1 * S.parking), 1)))
    p_sg = sum(p for _, p in SG)
    p_ed = p_col + p_sg / 0.9 * 0.8
    I_col = p_col * 1000 / (math.sqrt(3) * 400)
    In = next((c for c in (63, 80, 100, 125, 160, 200, 250, 315, 400) if c >= I_col), 400)
    Lc = 4.0 + S.H * S.n
    for s_, iz in IZ:
        du = math.sqrt(3) * (0.0225 * Lc / s_ * 0.95) * I_col / 400 * 100
        if iz >= In and du <= 1.0:
            break
    return {"lots": lots, "coef": coef, "p_lots": p_lots, "p_col": p_col, "SG": SG, "p_sg": p_sg, "p_ed": p_ed,
            "col": {"I": I_col, "In": In, "s": s_, "iz": iz, "du": du, "L": Lc}}


def calcular(S, R) -> dict:
    re2020, _, _ = _mods()
    TP = thermique_params(S)
    TH = re2020.note(TP)
    PL = plomberie(S)
    EL = electricite(S)
    return {"TH": TH, "TP": TP, "PL": PL, "EL": EL,
            "summary": {"re2020_conforme": bool(TH.get("conforme")), "Bbio": round(TH["Bbio"], 1), "Cep_nr": round(TH["Cep_nr"], 1),
                        "dpe": TH.get("classement", {}).get("dpe"), "qp_l_s": round(PL["qp"], 2), "p_dernier_niveau_kpa": round(PL["p_top"], 0),
                        "kva_immeuble": round(EL["p_ed"], 0)}}


def pdfs(S, R, MEP, out: Path, stem: str) -> dict:
    from engines.calc_lots import rendu
    files = {}
    p = out / f"Etude_thermique_RE2020_{stem}.pdf"
    p.write_bytes(MEP["TH"]["pdf"])
    files["termico"] = p
    PL, EL = MEP["PL"], MEP["EL"]
    sub = f"{S.name} · {S.municipality} · {len(S.units)} logements"
    b = [("kpis", [{"label": "Débit probable immeuble", "value": f(PL["qp"], 2), "unit": "L/s"}, {"label": "Branchement", "value": f"PE Ø{PL['br'][0]}"},
                   {"label": "Pression au dernier niveau", "value": f(PL["p_top"], 0), "unit": "kPa", "ok": PL["p_top"] >= 100},
                   {"label": "Descentes EP", "value": f"{PL['ep']['n']} × Ø{PL['ep']['d']}"}])]
    b.append(("p", "Étude préalable de plomberie (NF DTU 60.11) : appareils par logement, débit probable (y = 0,8/√(x−1)), colonne montante, "
                   "pression au point de puisage le plus défavorisé, eaux pluviales de la toiture-terrasse. Ne remplace pas l'étude d'exécution."))
    rows = []
    for t_ in sorted({l_["tip"] for l_ in PL["lots"]}):
        l_ = next(x for x in PL["lots"] if x["tip"] == t_)
        r = l_["r"]
        rows.append([t_, ", ".join(f"{a['type'].replace('_', ' ')} {a['nombre']}" for a in l_["ap"]), f(r["q_probable_ls"], 2),
                     f"{r['alimentation_generale']} / ECS {r['alimentation_ecs']}"])
    b.append(("table", ["Type", "Appareils", "Qp L/s", "Alimentation"], rows, [14 * W, 110 * W, 20 * W, 36 * W]))
    rows = [["Branchement", "", f(PL["qp"], 2), f"PE Ø{PL['br'][0]}", f(PL["br"][2], 2)]] + \
           [[c["troncon"], str(c["x"]), f(c["q"], 2), f"PE Ø{c['dn']}", f(c["v"], 2)] for c in PL["col"]]
    b.append(("table", ["Tronçon", "Appareils", "Qp L/s", "Tube", "v m/s"], rows, [70 * W, 22 * W, 22 * W, 34 * W, 22 * W]))
    b.append(("controls", [{"ref": "Pression au puisage le plus défavorisé (logement " + str(PL["top"]) + ")", "exigence": "≥ 100 kPa conseillé (≥ 30 kPa mini)",
                            "valeur": f"{f(PL['p_top'], 0)} kPa", "ok": PL["p_top"] >= 100, "note": None if PL["p_top"] >= 100 else "prévoir un surpresseur"},
                           {"ref": "Pression statique", "exigence": "≤ 400 kPa sans réducteur", "valeur": f"{f(PL['p_low'], 0)} kPa", "ok": PL["p_low"] <= 400,
                            "note": None if PL["p_low"] <= 400 else "réducteur de pression en pied de colonne"}]))
    b.append(("p", f"Eaux pluviales : toiture-terrasse {f(PL['ep']['surface'], 0)} m², i = 3 L/min/m² → {f(PL['ep']['q'], 1)} L/s ; {PL['ep']['n']} descentes Ø{PL['ep']['d']} "
                   "(règle de 1 cm² de section par m² de toiture desservie) ; chutes EU/EV DN 100 avec ventilation primaire hors toiture."))
    p = out / f"Etude_plomberie_{stem}.pdf"
    p.write_bytes(rendu.build_pdf("Étude de plomberie — immeuble", sub, b, footer="ConstruPilot — étude préalable (NF DTU 60.11)."))
    files["pichelaria"] = p
    col = EL["col"]
    b = [("kpis", [{"label": "Puissance des logements", "value": f(EL["p_lots"], 0), "unit": "kVA"},
                   {"label": f"Colonne (foisonnement {f(EL['coef'], 2)})", "value": f(EL["p_col"], 0), "unit": "kVA"},
                   {"label": "Services généraux", "value": f(EL["p_sg"], 1), "unit": "kW"}, {"label": "Demande Enedis", "value": f(EL["p_ed"], 0), "unit": "kVA"}])]
    b.append(("p", "Étude préalable électricité : équipement NF C 15-100 par logement, colonne électrique NF C 14-100 (coefficients de foisonnement), "
                   "services généraux. Ne remplace pas l'étude d'exécution ni la demande de raccordement Enedis."))
    rows = []
    for t_ in sorted({l_["tip"] for l_ in EL["lots"]}):
        l_ = next(x for x in EL["lots"] if x["tip"] == t_)
        r = l_["r"]
        rows.append([t_, str(len(r["circuits"])), str(len(r["differentiels"])), f"{r['abonnement_kva']:g} kVA", r["alimentation"]])
    b.append(("table", ["Type", "Circuits", "Interr. diff.", "Abonnement", "Alim."], rows, [20 * W, 30 * W, 30 * W, 40 * W, 30 * W]))
    b.append(("table", ["Services généraux", "kW"], [[n_, f(p_, 2)] for n_, p_ in EL["SG"]] + [["Total", f(EL["p_sg"], 2)]], [140 * W, 30 * W]))
    b.append(("table", ["Colonne électrique", "Valeur"], [["Logements / coefficient", f"{len(EL['lots'])} / {f(EL['coef'], 2)}"], ["Courant", f"{f(col['I'], 0)} A"],
                                                         ["Protection", f"{col['In']} A"], ["Câble", f"4 × {col['s']} mm² Cu (Iz {col['iz']} A)"],
                                                         ["Chute de tension", f"{f(col['du'], 2)} % (L = {f(col['L'], 0)} m)"]], [90 * W, 90 * W]))
    p = out / f"Etude_electricite_{stem}.pdf"
    p.write_bytes(rendu.build_pdf("Étude électricité — immeuble", sub, b, footer="ConstruPilot — étude préalable (NF C 15-100 / NF C 14-100)."))
    files["eletricidade"] = p
    return files
