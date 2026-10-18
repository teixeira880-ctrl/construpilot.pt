"""Moteur structure (pré-dimensionnement BET) — Eurocodes + Annexes nationales françaises.

Logique (la même qu'un ingénieur) :
1. hypothèses de charges (EN 1991-1-1, -1-3) ;
2. planchers poutrelles-hourdis : sens de portée, système, moment à reprendre ;
3. descente de charges par file de murs, niveau par niveau ;
4. maçonnerie porteuse Porotherme 20 (EN 1996-1-1, méthode Φ) ;
5. linteaux, poteaux de trumeau, chaînages (EN 1992-1-1, NF DTU 20.1) ;
6. voiles enterrés (poussée au repos + surcharge des mitoyens, G2) ;
7. fondations superficielles (G2 : q ELS / ELU, largeurs vérifiées, ancrage) ;
8. dallage du sous-sol, escaliers ;
9. métré béton / acier.
Tous les nombres sortent de formules ; aucun n'est produit par un LLM.
"""
from __future__ import annotations

import math

from .model import Model

# ---------------------------------------------------------------- matériaux
FCK, FCD, FCTM = 25.0, 25.0 / 1.5, 2.6          # C25/30 (MPa)
FYK, FYD = 500.0, 500.0 / 1.15                  # B500B
GAMMA_BA = 25.0                                 # kN/m³
COVER = {"dalle": 0.025, "poutre": 0.030, "voile_enterre": 0.035, "fondation": 0.050}

BARS = [6, 8, 10, 12, 14, 16, 20]
AREA = {d: math.pi * (d / 1000) ** 2 / 4 * 1e4 for d in BARS}        # cm² par barre
MASS = {d: 0.00617 * d * d for d in BARS}                             # kg/m

# Porotherme 20 (brique terre cuite à perforations verticales, joint mince)
BRICK = {
    "name": "Brique terre cuite Porotherme 20 (R20 / Th+), joint mince",
    "t": 0.20, "fb": 10.0, "fk": 2.5, "gamma_m": 2.5, "density": 8.5,
    "note": "fk = 2,5 MPa et fb ≥ 10 MPa : valeurs de la DoP fabricant à confirmer à la commande",
}
WALL_G = 0.20 * BRICK["density"] + 0.27 + 0.15  # brique + enduit 15 mm + doublage → kN/m²

# Planchers poutrelles précontraintes + entrevous béton (valeurs courantes, à caler sur l'Avis Technique)
HOURDIS = [
    # (système, h totale, G propre kN/m², M_rd indicatif par nervure simple à 0,60 kN.m)
    ("16+4", 0.20, 2.65, 15.0),
    ("20+4", 0.24, 2.85, 23.0),
    ("20+5", 0.25, 3.05, 25.0),
    ("25+5", 0.30, 3.55, 34.0),
]
SLENDER_MAX = 27.0     # L / h maxi en isostatique (prédimensionnement poutrelles précontraintes)
G_FIN = 1.10 + 0.15    # chape + carrelage + plafond (kN/m²)
G_CLOIS = 1.00         # cloisons distribuées (EN 1991-1-1 6.3.1.2)
Q_USE = {"habitation": 1.5, "garage": 2.5, "annexe": 2.5, "comble_hab": 1.5}

SNOW_SK = {"A1": 0.45, "A2": 0.45, "B1": 0.55, "B2": 0.55, "C1": 0.65, "C2": 0.65, "D": 0.90, "E": 1.40}


def r2(x: float) -> float:
    return round(x, 2)


def choose_bars(as_cm2_per_m: float, min_cm2: float = 0.0, diams=(8, 10, 12, 14, 16)) -> dict:
    """Choix d'un treillis de barres « HAx e=y » couvrant As (cm²/m)."""
    need = max(as_cm2_per_m, min_cm2)
    for d in diams:
        for e in (0.25, 0.20, 0.175, 0.15, 0.125, 0.10):
            prov = AREA[d] / e
            if prov >= need:
                return {"d": d, "e": e, "As_prov": round(prov, 2), "As_req": round(need, 2), "label": f"HA{d} e={int(e*100)}"}
    return {"d": 16, "e": 0.10, "As_prov": round(AREA[16] / 0.10, 2), "As_req": round(need, 2), "label": "HA16 e=10 (à revoir)"}


def choose_n_bars(as_cm2: float, diams=(10, 12, 14, 16, 20), nmin=2, nmax=5) -> dict:
    for d in diams:
        for n in range(nmin, nmax + 1):
            if n * AREA[d] >= as_cm2:
                return {"n": n, "d": d, "As_prov": round(n * AREA[d], 2), "As_req": round(as_cm2, 2), "label": f"{n}HA{d}"}
    return {"n": nmax, "d": 20, "As_prov": round(nmax * AREA[20], 2), "As_req": round(as_cm2, 2), "label": f"{nmax}HA20 (à revoir)"}


# ---------------------------------------------------------------- 1. charges
def loads(m: Model) -> dict:
    roof = m.roof
    half = m.L / 2
    alpha = math.degrees(math.atan((roof["ridge_level"] - roof["eaves_level"]) / half))
    sk = SNOW_SK.get(m.raw["project"].get("snow_region", "A1"), 0.45)
    mu = 0.8 if alpha <= 30 else (0.8 * (60 - alpha) / 30 if alpha < 60 else 0.0)
    g_roof_slope = 0.45 + 0.05 + 0.08 + 0.12 + 0.13       # tuile méca, liteaux, chevrons, isolant, plafond rampant
    pr = m.raw["project"]
    if pr.get("country") == "PT":
        alt = pr.get("altitude_m", 0)
        cz = {"Z1": 0.30, "Z2": 0.20, "Z3": 0.10}.get(pr.get("snow_zone", "Z3"), 0.10)
        sk = round(cz * (1 + (alt / 500) ** 2), 2) if alt >= 200 else 0.0
        notes = [f"Neige : NP EN 1991-1-3 AN PT, zone {pr.get('snow_zone', 'Z3')}, altitude {alt} m → s_k = {sk:.2f} kN/m²".replace(".", ",") + (" (neige non considérée sous 200 m d'altitude)." if alt < 200 else "."),
                 f"Vent : NP EN 1991-1-4 AN PT, zone {pr.get('wind_zone', 'A')} ; non dimensionnant pour les éléments pré-dimensionnés ici ; contreventement de charpente à justifier par le charpentier.",
                 "Séisme : NP EN 1998-1 + AN PT — voir le chapitre « Action sismique » (méthode des forces latérales)."]
    else:
        has_mit = any(d["type"] == "mitoyen" for d in m.raw["sides"].values())
        notes = [
            f"Neige : région {pr['snow_region']}, altitude < 200 m → s_k = {str(sk).replace('.', ',')} kN/m² ; μ1 selon la pente (EN 1991-1-3 AN FR).",
            f"Vent : non dimensionnant pour les éléments pré-dimensionnés ici ({'maison mitoyenne' if has_mit else 'maison individuelle'}, région {pr.get('wind_region', 1)}) ; contreventement de charpente à justifier par le charpentier.",
            f"Séisme : zone {pr.get('seismic_zone', 1)} → aucune disposition parasismique exigée (arrêté du 22/10/2010)." if pr.get("seismic_zone", 1) <= 1 else
            f"Séisme : zone {pr.get('seismic_zone')} → règles PS-MI 89 révisées 92 ou NF EN 1998-1 à appliquer (arrêté du 22/10/2010).",
        ]
    return {
        "roof_pitch_deg": r2(alpha),
        "rafter_length": r2(half / math.cos(math.radians(alpha))),
        "snow_sk": sk, "snow_mu": r2(mu), "snow_s": r2(mu * sk),
        "g_roof_slope": r2(g_roof_slope),
        "g_roof_plan": r2(g_roof_slope / math.cos(math.radians(alpha)) + 0.15),   # + pannes
        "g_wall": r2(WALL_G),
        "g_fin": G_FIN, "g_clois": G_CLOIS,
        "q": Q_USE,
        "notes": notes,
    }


# ---------------------------------------------------------------- 2. planchers
def floors(m: Model, ld: dict) -> dict:
    L = m.span_y_calc
    slabs = []
    # plancher haut de chaque niveau qui porte le niveau supérieur
    for below, above in zip(m.levels, m.levels[1:]):
        q = Q_USE["garage"] if any(rm["type"] == "garage" for rm in m.rooms(above.id)) else Q_USE["habitation"]
        best = None
        for name, h, g, mrd in HOURDIS:
            if L / h > SLENDER_MAX:
                continue
            G = g + G_FIN + G_CLOIS
            qu = 1.35 * G + 1.5 * q
            for ent, twin in ((0.60, False), (0.60, True)):
                m_rib = qu * ent * L ** 2 / 8
                cap = mrd * (1.9 if twin else 1.0)
                if m_rib <= cap:
                    best = {"system": name, "h": h, "g_self": g, "twin": twin, "G": r2(G), "Q": q,
                            "qu": r2(qu), "M_per_m": r2(qu * L ** 2 / 8), "M_rib": r2(m_rib), "Mrd_ind": r2(cap),
                            "V_per_m": r2(qu * L / 2), "slenderness": r2(L / h)}
                    break
            if best:
                break
        if best is None:
            raise ValueError(f"Aucun plancher poutrelles-hourdis ne couvre {L:.2f} m sous {above.name} : prévoir refend, poutre ou dalle BA")
        G = best["G"]
        slabs.append({
            "id": f"PH-{below.id}", "label": f"Plancher haut {below.name} (porte {above.name})",
            "level_top": above.floor_top, "span": L, "direction": "Y (de mitoyen à mitoyen)" if _mitoyen_bearing(m) else "Y (entre murs porteurs)",
            "R_G_per_m": r2(G * L / 2), "R_Q_per_m": r2(best["Q"] * L / 2), **best,
            "label_system": f"Poutrelles précontraintes + entrevous béton {best['system']}"
                            + (" — poutrelles jumelées (2 par nervure)" if best["twin"] else "") + ", entraxe 0,60",
            "compression_slab": "Table de compression 5 cm C25/30 + treillis soudé ST 15 C (Ø5 maille 150 × 300) min. ; chapeaux HA10 e=33 sur appuis (L = 0,25 L)",
            "deflection": "Flèche active ≤ L/500 (cloisons et carrelage) : à garantir par la note du fabricant",
        })
    pc_h = m.levels[1].slab if len(m.levels) > 1 else m.levels[0].slab
    thickest = max(s["h"] for s in slabs)
    return {
        "system": "poutrelles_hourdis",
        "span_calc": L,
        "clear_span": m.clear_span_y,
        "slabs": slabs,
        "pc_thickness": pc_h,
        "impact_heights": round(thickest - pc_h, 3),
        "variant": ("Variante respectant l'épaisseur du PC (25 cm) : dalles alvéolées précontraintes 20 cm + 5 cm de "
                    "table (portée 7 m courante, pose à la grue) ; ou refend porteur intermédiaire non prévu au PC."),
        "rules": [
            f"Portée de calcul L = {m.clear_span_y:.2f} m entre nus des briques + 0,10 m d'appuis = {L:.2f} m.",
            f"Élancement maxi retenu L/h ≤ {SLENDER_MAX:.0f} pour des poutrelles précontraintes en isostatique.",
            ("Les poutrelles portent de mitoyen à mitoyen : les murs mitoyens sont aveugles et continus, "
             "les façades sont percées de grandes baies et ne reçoivent que la rive.") if _mitoyen_bearing(m) else
            "Les poutrelles portent dans le sens de la plus petite portée, entre les deux murs longitudinaux porteurs ; les pignons ne reçoivent que la rive.",
            f"Trémie d'escalier {m.stair['x1'] - m.stair['x0']:.2f} × {m.stair['y1'] - m.stair['y0']:.2f} : chevêtre BA porté par les deux voiles de cage.".replace(".", ",", 2),
        ],
    }


# ---------------------------------------------------------------- 3. descente de charges
def _mitoyen_bearing(m: Model) -> bool:
    return any(m.side(s)["type"] == "mitoyen" for s in bearing_sides(m))


def has_mitoyen(m: Model) -> bool:
    return any(d["type"] == "mitoyen" for d in m.raw["sides"].values())


def bearing_sides(m: Model) -> list[str]:
    """Murs parallèles à X (axe 'y') : ils reçoivent les planchers (portée selon Y, la plus courte)."""
    return [s for s, d in m.raw["sides"].items() if d["axis"] == "y"]


def end_sides(m: Model) -> list[str]:
    return [s for s, d in m.raw["sides"].items() if d["axis"] == "x"]


def has_basement(m: Model) -> bool:
    return m.levels[0].floor_top < -1.0


def descent(m: Model, ld: dict, fl: dict) -> dict:
    """Charges linéiques (kN/m) en pied de chaque niveau, pour chaque mur et pour les voiles de cage."""
    gw = ld["g_wall"]
    eaves, ridge = m.roof["eaves_level"], m.roof["ridge_level"]
    gables = set(m.roof.get("gables", []))
    roof_area = (m.L + 0.60) * m.W
    roof_G_line = ld["g_roof_plan"] * roof_area / 2 / m.L
    roof_S_line = ld["snow_s"] * roof_area / 2 / m.L
    chain = GAMMA_BA * 0.20 * 0.30
    sabl_G = 0.40 * ld["rafter_length"] / 3 * ld["g_roof_slope"] * 2.2
    sabl_S = 0.40 * ld["rafter_length"] / 3 * ld["snow_s"] * 2.2
    rows = []
    for side in bearing_sides(m) + end_sides(m):
        bearing = side in bearing_sides(m)
        is_gable = side in gables
        length = m.side_length(side)
        top = eaves + (ridge - eaves) / 2 if is_gable else eaves
        for lv in reversed(m.levels):
            base = lv.floor_top
            if base < -1.0:
                wall = GAMMA_BA * 0.20 * (0.0 - base + 0.20)
                mat = "voile BA 20"
            else:
                open_area = sum(o.width * o.height for o in m.openings_on(side) if m.level(o.level).floor_top >= base - 1e-6)
                wall = gw * max((top - base) * length - open_area, 0.0) / length
                mat = "Porotherme 20"
            floors_above = [s for s in fl["slabs"] if s["level_top"] > base + 1e-6]
            if bearing:
                G = wall + sum(s["R_G_per_m"] + chain for s in floors_above)
                Q = sum(s["R_Q_per_m"] for s in floors_above)
            else:
                G = wall + sum(0.30 * s["G"] + chain for s in floors_above)
                Q = sum(0.30 * s["Q"] for s in floors_above)
            if is_gable:
                G += roof_G_line
                S = roof_S_line
            else:
                G += sabl_G
                S = sabl_S
            rows.append({"side": side, "file": m.side(side)["label"], "level": lv.id, "base": base, "material": mat,
                         "bearing": bearing, "G": r2(G), "Q": r2(Q), "S": r2(S), "ELS": r2(G + Q + S),
                         "ELU": r2(1.35 * G + 1.5 * Q + 0.75 * 1.5 * S)})
    st = m.stair
    Bt = st["x1"] - st["x0"]
    trem_len = st["y1"] - st["y0"]
    top_cage = m.levels[-1].floor_top + m.levels[-1].hsp
    for lv in reversed(m.levels):
        base = lv.floor_top
        floors_above = [s for s in fl["slabs"] if s["level_top"] > base + 1e-6]
        G_pt = sum(s["G"] * Bt * (m.span_y_calc - trem_len) / 2 / 2 for s in floors_above)
        Q_pt = sum(s["Q"] * Bt * (m.span_y_calc - trem_len) / 2 / 2 for s in floors_above)
        wallG = GAMMA_BA * 0.15 * (top_cage - base) * trem_len + 0.25 * trem_len * 0.5 * 25 * len(floors_above)
        G = (G_pt + wallG) / trem_len
        Q = Q_pt / trem_len
        rows.append({"side": "cage", "file": "Voiles BA 15 de cage d'escalier", "level": lv.id, "base": base, "material": "voile BA 15",
                     "bearing": False, "G": r2(G), "Q": r2(Q), "S": 0.0, "ELS": r2(G + Q), "ELU": r2(1.35 * G + 1.5 * Q),
                     "point_G_chevetre": r2(G_pt), "point_Q_chevetre": r2(Q_pt)})
    return {"rows": rows, "roof_G_per_gable": r2(roof_G_line), "roof_S_per_gable": r2(roof_S_line)}


def row(desc: dict, side: str, level: str) -> dict:
    return next(r for r in desc["rows"] if r["side"] == side and r["level"] == level)


# ---------------------------------------------------------------- 4. maçonnerie Porotherme
def masonry(m: Model, desc: dict, fl: dict) -> dict:
    t = BRICK["t"]
    fd = BRICK["fk"] / BRICK["gamma_m"] * 1000  # kN/m²
    E = 1000 * BRICK["fk"]
    out = []
    for side in bearing_sides(m) + end_sides(m):
        for lv in [l for l in m.levels if l.floor_top > -1.0]:
            r = row(desc, side, lv.id)
            last = lv.id == m.levels[-1].id
            h = (m.roof["eaves_level"] - lv.floor_top) if last else m.storey_height(lv.id) - lv.slab
            hef = 0.75 * h
            slab_above = next((s for s in fl["slabs"] if abs(s["level_top"] - (lv.floor_top + m.storey_height(lv.id))) < 0.01), None)
            if r["bearing"] and slab_above:
                N_floor = 1.35 * slab_above["R_G_per_m"] + 1.5 * slab_above["R_Q_per_m"]
            else:
                N_floor = 0.3 * (1.35 * fl["slabs"][-1]["G"] + 1.5 * 1.5)
            N_top = max(r["ELU"] - 1.35 * WALL_G * h, 1.0)
            e_init = hef / 450
            e_i = max(N_floor * t / 6 / N_top + e_init, 0.05 * t)
            phi_i = max(1 - 2 * e_i / t, 0.0)
            e_m = max(0.6 * (e_i - e_init) + e_init, 0.05 * t)
            lam = hef / t * math.sqrt(BRICK["fk"] / E)
            u = (lam - 0.063) / (0.73 - 1.17 * e_m / t)
            phi_m = (1 - 2 * e_m / t) * math.exp(-u * u / 2)
            phi = min(phi_i, phi_m)
            if phi <= 0.05:
                # dernier niveau peu chargé : poids propre net des ouvertures (sinon N en tête ≈ 0 et excentricité infinie)
                length = m.side_length(side)
                net = WALL_G * max(h * length - sum(o.width * o.height for o in m.openings_on(side, lv.id)), 0.0) / length
                N_top = max(r["ELU"] - 1.35 * net, 1.0)
                e_i = min(max(N_floor * t / 6 / N_top + e_init, 0.05 * t), 0.40 * t)
                phi_i = max(1 - 2 * e_i / t, 0.0)
                e_m = max(0.6 * (e_i - e_init) + e_init, 0.05 * t)
                u = (lam - 0.063) / (0.73 - 1.17 * e_m / t)
                phi_m = (1 - 2 * e_m / t) * math.exp(-u * u / 2)
                phi = max(min(phi_i, phi_m), 0.05)
            NRd = phi * t * fd
            out.append({"side": side, "file": r["file"], "level": lv.id, "h": r2(h), "hef_t": r2(hef / t), "N_Ed": r["ELU"],
                        "phi": round(phi, 3), "N_Rd": r2(NRd), "ratio": round(r["ELU"] / NRd, 3), "ok": r["ELU"] <= NRd})
    worst = max(out, key=lambda x: x["ratio"])
    return {"material": "brique_porotherme_20", "brick": BRICK, "fd_MPa": round(fd / 1000, 2), "checks": out,
            "worst": worst, "ok": all(c["ok"] for c in out),
            "method": "NF EN 1996-1-1 §6.1.2 : N_Rd = Φ · t · f_d ; Φ en tête (1 − 2e_i/t) et à mi-hauteur (annexe G) ; "
                      "h_ef = 0,75 h (mur tenu en tête et en pied par les planchers) ; e_init = h_ef/450 ; "
                      "réaction du plancher supérieur excentrée de t/6."}


# ---------------------------------------------------------------- 5. linteaux, poteaux, chaînages
def lintels(m: Model, ld: dict, fl: dict) -> dict:
    gw = ld["g_wall"]
    out, posts = [], []
    eaves = m.roof["eaves_level"]
    bearing = set(bearing_sides(m))
    for side in m.raw["sides"]:
        for lv in [l for l in m.levels if l.floor_top > -1.0]:
            ops = sorted(m.openings_on(side, lv.id), key=lambda o: o.a)
            for o in ops:
                Lc = o.width + 0.20
                top = lv.floor_top + o.sill + o.height
                h_wall = max(eaves - top, 0.3)
                above = [p for p in m.openings_on(side) if m.level(p.level).floor_top > lv.floor_top and p.a < o.b and p.b > o.a]
                void = sum((min(p.b, o.b) - max(p.a, o.a)) * p.height for p in above)
                g_w = gw * max(h_wall * Lc - void, 0.3 * Lc) / Lc
                floors_above = [s for s in fl["slabs"] if s["level_top"] > top]
                if side in bearing:
                    G = g_w + sum(s["R_G_per_m"] for s in floors_above) + 1.0
                    Q = sum(s["R_Q_per_m"] for s in floors_above) + 0.3
                else:
                    G = g_w + sum(0.30 * s["G"] for s in floors_above) + 1.0
                    Q = sum(0.30 * s["Q"] for s in floors_above) + 0.3
                b = 0.20
                h = max(0.20, math.ceil(Lc / 10 / 0.05) * 0.05)
                if Lc > 2.0 or side in bearing:
                    h = max(h, 0.30)
                for _ in range(6):
                    Gt = G + GAMMA_BA * b * h
                    qu = 1.35 * Gt + 1.5 * Q
                    M = qu * Lc ** 2 / 8
                    V = qu * Lc / 2
                    d = h - COVER["poutre"] - 0.008 - 0.006
                    mu = M / (b * d ** 2 * FCD * 1000)
                    if mu <= 0.30 and V / (b * 0.9 * d) / 1000 <= 1.2:
                        break
                    h = round(h + 0.05, 2)
                As = M / (0.9 * d * FYD * 1000) * 1e4
                As_min = 0.26 * FCTM / FYK * b * d * 1e4
                low = choose_n_bars(max(As, As_min), diams=(10, 12, 14, 16, 20), nmin=2, nmax=4)
                tau = V / (b * 0.9 * d) / 1000
                out.append({"id": "L-" + o.id[2:], "opening": o.id, "level": lv.id, "side": side, "y0": o.a, "y1": o.b,
                            "span": r2(Lc), "b": b, "h": r2(h), "qu": r2(qu), "M_Ed": r2(M), "V_Ed": r2(V),
                            "As_req": r2(max(As, As_min)), "bottom": low["label"], "top": "2HA10",
                            "stirrups": "cadres HA6 e=15" if tau < 0.6 else "cadres HA8 e=10", "tau_MPa": round(tau, 2),
                            "bearing": "appuis ≥ 0,20 m de part et d'autre, ancrés dans les chaînages verticaux"})
            for p, q in zip(ops, ops[1:]):
                pier = q.a - p.b
                if pier < 0.60:
                    Lp = next(x for x in out if x["opening"] == p.id)
                    Lq = next(x for x in out if x["opening"] == q.id)
                    N = Lp["V_Ed"] + Lq["V_Ed"]
                    width = max(0.20, round(pier, 2))
                    Ac = 0.20 * width
                    h_post = max(p.height + p.sill, q.height + q.sill)
                    lam = 0.7 * h_post * math.sqrt(12) / 0.20
                    NRd = 0.8 * (Ac * FCD * 1000 + 4 * AREA[12] * 1e-4 * FYD * 1000) * (0.86 if lam > 30 else 1.0)
                    posts.append({"id": f"P-{lv.id}-{len(posts)+1}", "level": lv.id, "side": side,
                                  "y0": p.b, "y1": q.a, "section": f"0,20 × {width:.2f}", "height": r2(h_post),
                                  "N_Ed": r2(N), "N_Rd": r2(NRd), "lambda": r2(lam), "steel": "4HA12 + cadres HA6 e=15",
                                  "ok": N <= NRd})
    chain = {
        "horizontal": "Chaînage horizontal BA 0,20 × 0,30 à chaque plancher, sur tous les murs porteurs : 4HA10 + cadres HA6 e=20, recouvrements 50 Ø, angles en équerre HA10.",
        "vertical": "Chaînages verticaux 0,20 × 0,20 (dans les briques d'angle Porotherme) : 4HA10 + cadres HA6 e=20 aux 4 angles, aux jonctions avec les voiles de cage, et de part et d'autre de chaque baie ≥ 1,80 m ; attentes depuis les voiles ou les semelles.",
        "rampant": "Chaînage rampant BA 0,20 × 0,20 sur les pignons (4HA10 + cadres HA6 e=20) recevant les sommiers des pannes.",
        "sommiers": "Sommiers BA 0,20 × 0,20 × 0,40 sous chaque appui de panne (2HA10 + 3 cadres HA6).",
    }
    return {"lintels": out, "posts": posts, "chainages": chain}


# ---------------------------------------------------------------- 6. voiles enterrés
def basement_walls(m: Model) -> dict:
    if not has_basement(m):
        return {"thickness": 0.0, "walls": [], "method": "Pas de niveau enterré.", "execution": [], "note_neighbour": ""}
    g = m.geo["retaining"]
    q_n = g["neighbour_surcharge_kpa"]
    depth = -m.levels[0].floor_top
    H = depth - 0.10
    span = depth - m.levels[1].slab / 2
    k = {L["name"]: L for L in g["layers"]}
    layers = sorted(g["layers"], key=lambda L: L["base_m"])

    def p(z, q):
        for L in layers:
            if z <= L["base_m"]:
                return L["k0"] * (q + L["gamma"] * z)
        L = layers[-1]
        return L["k0"] * (q + L["gamma"] * z)

    out = []
    has_mit = any(d["type"] == "mitoyen" for d in m.raw["sides"].values())
    cases = ([("Voiles sur mitoyens (avec surcharge des fondations voisines)", q_n)] if has_mit else []) + \
            [("Voiles sous façades (surcharge de chantier/voirie 10 kPa)", 10.0)]
    for name, q in cases:
        p_top, p_bot = p(0.10, q), p(H, q)
        M = p_top * span ** 2 / 8 + (p_bot - p_top) * span ** 2 / (9 * math.sqrt(3))
        Mu = 1.35 * M
        d = 0.20 - COVER["voile_enterre"] - 0.006
        As = Mu / (0.9 * d * FYD * 1000) * 1e4
        As_min = max(0.26 * FCTM / FYK * d * 1e4, 0.0013 * d * 1e4)
        ext = choose_bars(As, As_min, diams=(10, 12))
        out.append({"name": name, "q_kpa": q, "p_top": r2(p_top), "p_bot": r2(p_bot), "span": r2(span),
                    "M_ser": r2(M), "M_Ed": r2(Mu), "As_req": r2(max(As, As_min)), "face_terre": ext["label"],
                    "face_interieure": "HA8 e=20", "horizontaux": "HA8 e=20 (2 faces)"})
    return {
        "thickness": 0.20, "walls": out,
        "method": "Poussée au repos K0 par couche (G2) + surcharge ; voile appuyé en pied sur le dallage et en tête sur le plancher bas du RDC (bi-appuyé).",
        "execution": [
            "Au droit des mitoyens : terrassement par passes alternées ≤ 2,0 m de large × 1,5 m de haut sous blindage, "
            "butonnage à l'avancement, voile coulé par plots contre le terrain (G2).",
            f"Ailleurs : talus si la fouille test le valide ; travaux en période favorable ({g.get('works_period', 'saison sèche')}).",
            "Béton hydrofugé dans la masse + joints de reprise avec bande hydrogonflante ; enduit d'imperméabilisation "
            "côté terre là où il est accessible ; drain périphérique côté façades vers regard.",
        ],
        "note_neighbour": g.get("neighbour_surcharge_note", ""),
    }


# ---------------------------------------------------------------- 7. fondations
def foundations(m: Model, desc: dict) -> dict:
    geo = m.geo
    q_els, q_elu = geo["q_els_kpa"], geo["q_elu_kpa"]
    Bmin = geo["verified_widths_m"]["filante"]
    low = m.levels[0].id
    out = []
    groups = []
    for side in bearing_sides(m) + end_sides(m):
        d = m.side(side)
        exc = d["type"] == "mitoyen" or bool(d.get("on_boundary"))
        length = m.side_length(side) - (0.40 if side in end_sides(m) else 0.0)
        groups.append((side, f"Semelle {'excentrée' if exc else 'filante'} sous {d['label']}", exc, 1, length))
    groups.append(("cage", "Semelles sous voiles de cage d'escalier", False, 2, m.stair["y1"] - m.stair["y0"]))
    for side, label, excentric, count, length in groups:
        r = row(desc, side, low)
        b_wall = 0.15 if side == "cage" else 0.20
        B = Bmin
        while True:
            h = 0.35 if excentric else 0.30
            self_w = GAMMA_BA * B * h + 20 * (B - b_wall) * 0.20
            Nels, Nelu = r["ELS"] + self_w, r["ELU"] + 1.35 * self_w
            if Nels / B <= 0.90 * q_els and Nelu / B <= 0.90 * q_elu:
                break
            B = round(B + 0.05, 2)
        console = (B - b_wall) if excentric else (B - b_wall) / 2
        d = max(h - COVER["fondation"] - 0.010, console / 2)
        h = max(h, round(math.ceil((d + COVER["fondation"] + 0.01) / 0.05) * 0.05, 2))
        d = h - COVER["fondation"] - 0.010
        sig_u = Nelu / B
        Mc = sig_u * console ** 2 / 2
        As = Mc / (0.9 * d * FYD * 1000) * 1e4
        trans = choose_bars(As, 2.0, diams=(10, 12, 14))
        out.append({"side": side, "label": label, "file": r["file"], "count": count, "length": r2(length), "B": B, "h": h,
                    "N_ELS": r2(Nels), "N_ELU": r2(Nelu), "sigma_ELS": r2(Nels / B), "sigma_ELU": r2(Nelu / B),
                    "ratio_ELS": round(Nels / B / q_els, 3), "ratio_ELU": round(Nelu / B / q_elu, 3),
                    "excentric": excentric, "M_console": r2(Mc), "transversal": trans["label"],
                    "longitudinal": "4HA12 (chaînage de semelle)" if excentric else "3HA10",
                    "settlement": f"≈ {geo.get('settlement_mm_B060', '?')} mm (G2, B = {Bmin:.2f} m)" if B <= Bmin + 0.05 else "à recalculer en G2 PRO"})
    return {
        "type": "Semelles filantes BA C25/30 coulées en pleine fouille sur béton de propreté 5 cm",
        "base_depth": geo["foundation_base_depth_m"], "anchorage": geo["anchorage_m"],
        "q_els": q_els, "q_elu": q_elu, "items": out,
        "rules": [
            f"Arase inférieure vers {geo['foundation_base_depth_m']:.2f} m/TN avec ancrage ≥ {geo['anchorage_m']:.2f} m dans {geo['bearing_layer']} (G2).",
            f"Largeur mini retenue {Bmin:.2f} m = largeur dont la G2 a vérifié la portance et le tassement.",
            "Taux de travail ≤ 90 % de q ELS et de q ELU.",
        ] + ([
            "Semelles en limite (mitoyens, alignement) excentrées : le moment d'excentrement est repris par le couple dallage (en pied) / plancher (en tête).",
        ] if any(i["excentric"] for i in out) else []) + [
            "Purge des poches molles et remplacement par du gros béton ; réception des fonds de fouille par le géotechnicien (point d'arrêt).",
            "Redans 1V/3H entre semelles filantes d'arases différentes.",
        ],
    }


# ---------------------------------------------------------------- 8. dallage + escaliers
def slab_on_grade(m: Model) -> dict:
    if not has_basement(m):
        return {
            "type": "Dallage BA 15 cm C25/30 sur film polyane 200 µm + 20 cm de GNT 0/31,5 compactée, isolant sous dallage selon étude thermique",
            "steel": "Treillis ST 25 C en nappe supérieure ; renforts HA10 en périphérie et aux angles rentrants",
            "rule": "Dallage sur terre-plein après décapage de la terre végétale et compactage du fond de forme (étude géotechnique).",
            "joints": "Joints de retrait sciés ≤ 25 m² (maille ≈ 5 × 5 m) ; désolidarisation le long des murs par bande compressible.",
            "q": "Charge d'exploitation 1,5 kN/m² (habitation) — garage éventuel 2,5 kN/m²",
        }
    return {
        "type": "Dallage BA 20 cm C25/30 sur film polyane 200 µm + 20 cm de GNT 0/31,5 compactée (après purge des remblais)",
        "steel": "Treillis ST 25 C en nappe inférieure et supérieure (tirant d'équilibre des semelles excentrées) ; renforts HA10 en périphérie",
        "rule": "G2 §7 : dallage admis sous réserve de purge des remblais résiduels et couche de forme GNT ; tassements négligeables (déchargement de la fouille).",
        "joints": "Joints de retrait sciés ≤ 25 m² (maille ≈ 5 × 5 m) ; désolidarisation le long des voiles par bande compressible.",
        "q": "Charge d'exploitation 2,5 kN/m² (sous-sol, buanderie, rangement)",
    }


def stairs(m: Model) -> dict:
    from .checks import stair_walking_line
    s = m.stair
    B, Lc = s["x1"] - s["x0"], s["y1"] - s["y0"]
    walk = stair_walking_line(B, Lc)
    out = []
    for f in s["flights"]:
        H = m.level(f["to"]).floor_top - m.level(f["from"]).floor_top
        n = math.ceil(H / 0.18)
        h = H / n
        g = min(walk / (n - 1), 0.29)
        out.append({"from": f["from"], "to": f["to"], "H": r2(H), "risers": n, "h_mm": round(h * 1000), "g_mm": round(g * 1000),
                    "blondel_mm": round((2 * h + g) * 1000), "ok": g >= 0.21})
    return {"type": s["type"], "cage": f"{B:.2f} × {Lc:.2f} m", "walking_line_m": r2(walk), "flights": out,
            "structure": "Escalier béton préfabriqué (ou coulé en place) à deux quarts tournants, paillasse 15 cm armée HA10 e=15 + répartition HA8 e=20, "
                         "encastré dans les voiles BA 15 de la cage et le limon central ; dimensionnement final par l'escaliéteur."}


# ---------------------------------------------------------------- 9. métré
def quantities(m: Model, fl: dict, lin: dict, fnd: dict, bw: dict, ld: dict | None = None) -> dict:
    L, W = m.L, m.W
    q = []

    def add(lot, item, unit, qty, steel_kg=0.0):
        q.append({"lot": lot, "item": item, "unit": unit, "qty": round(qty, 2), "steel_kg": round(steel_kg, 1)})

    area = L * W
    bsmt = has_basement(m)
    dig = round(-m.levels[0].floor_top + 0.40, 2) if bsmt else 0.30
    dig_s = f"{-dig:.2f}".replace(".", ",")
    if bsmt:
        add("Terrassement", f"Décapage et fouille en pleine masse du sous-sol (jusqu'à {dig_s})", "m³", area * dig * 1.15)
    else:
        add("Terrassement", "Décapage de la terre végétale (30 cm) sur l'emprise + 1 m", "m³", (L + 2) * (W + 2) * dig)
    if has_mitoyen(m) and bsmt:
        add("Terrassement", "Blindage + butonnage au droit des mitoyens (G2)", "m²", 2 * L * round(m.geo["foundation_base_depth_m"] + 0.10, 2))
    add("Terrassement", "Fouilles en rigole des semelles", "m³", sum(i["B"] * i["h"] * i["length"] * i["count"] for i in fnd["items"]))
    add("Terrassement", "Évacuation des terres en décharge (foisonnement 1,25)", "m³",
        (area * dig if bsmt else (L + 2) * (W + 2) * dig + sum(i["B"] * i["h"] * i["length"] * i["count"] for i in fnd["items"])) * 1.25)
    for i in fnd["items"]:
        v = i["B"] * i["h"] * i["length"] * i["count"]
        add("Fondations", f"{i['label']} B = {i['B']:.2f} × h = {i['h']:.2f}", "m³", v, v * 45)
    add("Fondations", "Béton de propreté 5 cm", "m²", sum(i["B"] * i["length"] * i["count"] for i in fnd["items"]))
    hb = round(-m.levels[0].floor_top + 0.20, 2)
    if bsmt:
        vv = 0.20 * hb * (2 * L + 2 * (W - 0.40))
        add("Sous-sol", "Voiles BA 20 enterrés (périphérie)", "m³", vv, vv * 65)
        add("Sous-sol", "Coffrage 2 faces des voiles", "m²", 2 * hb * (2 * L + 2 * (W - 0.40)))
    top, low = m.levels[-1], m.levels[0]
    vc = 0.15 * (top.floor_top + top.hsp - low.floor_top) * (m.stair["y1"] - m.stair["y0"]) * 2
    last_name = "comble" if "omble" in top.name else top.id
    add("Gros œuvre", f"Voiles BA 15 de cage d'escalier ({low.id} → {last_name})", "m³", vc, vc * 50)
    lot_d = "Sous-sol" if bsmt else "Dallage"
    add(lot_d, "GNT 0/31,5 compactée 20 cm + polyane", "m²", (L - 0.4) * (W - 0.4))
    td = 0.20 if bsmt else 0.15
    vd = td * (L - 0.4) * (W - 0.4)
    if bsmt:
        add(lot_d, "Dallage BA 20 cm + 2 nappes ST 25 C", "m³", vd, (L - 0.4) * (W - 0.4) * 2 * 2.70)
        add(lot_d, "Imperméabilisation + drain côté façades", "ml", 2 * W)
    else:
        add(lot_d, "Dallage BA 15 cm sur terre-plein + 1 nappe ST 25 C", "m³", vd, (L - 0.4) * (W - 0.4) * 2.70)
    trem = (m.stair["x1"] - m.stair["x0"]) * (m.stair["y1"] - m.stair["y0"])
    for s in fl["slabs"]:
        a = (L - 0.40) * (W - 0.40) - trem
        add("Planchers", f"{s['label']} — {s['label_system']}", "m²", a, a * (2.0 + 1.6))
    wall_area = 0.0
    for lv in [l for l in m.levels if l.floor_top > -1.0]:
        h = m.storey_height(lv.id)
        gross = 2 * L * h + 2 * W * h
        voids = sum(o.width * o.height for o in m.openings if o.level == lv.id)
        wall_area += gross - voids
    gables = m.roof.get("gables", [])
    gable = len(gables) * (L * (m.roof["ridge_level"] - m.roof["eaves_level"]) / 2)
    mit = has_mitoyen(m)
    first = next(l for l in m.levels if l.floor_top > -1.0)
    add("Maçonnerie", f"Murs Porotherme 20 joint mince ({'façades + mitoyens' if mit else 'façades'}, {first.id} → égout)", "m²", wall_area)
    gmit = any(m.side(g)["type"] == "mitoyen" for g in gables)
    add("Maçonnerie", f"Pignons{' mitoyens' if gmit else ''} Porotherme 20 (triangles égout → faîtage)", "m²", gable)
    perim = 2 * (L + W)
    n_ch = len([s_ for s_ in fl["slabs"] if s_["level_top"] > 0.01]) + 1
    add("Béton armé", f"Chaînages horizontaux 20 × 30 ({n_ch} niveaux)", "ml", perim * n_ch, perim * n_ch * 4 * MASS[10] * 1.1 + perim * n_ch * 5 * 0.82 * MASS[6])
    nvert = 4 + 4 + 2 * len([o for o in m.openings if o.width >= 1.80])
    hv = m.roof["eaves_level"]
    add("Béton armé", "Chaînages verticaux 20 × 20", "ml", nvert * hv, nvert * hv * (4 * MASS[10] + 5 * 0.72 * MASS[6]))
    raf = ld["rafter_length"] if ld else 6.86
    add("Béton armé", "Chaînages rampants des pignons", "ml", 2 * len(gables) * raf, 2 * len(gables) * raf * (4 * MASS[10] + 5 * 0.72 * MASS[6]))
    for l in lin["lintels"]:
        add("Béton armé", f"Linteau {l['id']} {l['b']:.2f} × {l['h']:.2f}, L = {l['span']+0.20:.2f}", "u", 1,
            (l["span"] + 0.4) * (AREA_KG(l["bottom"]) + 2 * MASS[10]) + (l["span"] / 0.15) * 2 * (l["b"] + l["h"]) * MASS[6])
    for p in lin["posts"]:
        add("Béton armé", f"Poteau {p['id']} {p['section']}, h = {p['height']:.2f}", "u", 1, p["height"] * 4 * MASS[12] + p["height"] / 0.15 * 1.4 * MASS[6])
    nf = len(m.stair["flights"])
    add("Escalier", f"Escalier béton 2 quarts tournants ({nf} volée{'s' if nf > 1 else ''} {m.stair['flights'][0]['from']}→{last_name})", "u", nf)
    return {"items": q, "steel_total_kg": round(sum(i["steel_kg"] for i in q)), "concrete_total_m3": round(sum(i["qty"] for i in q if i["unit"] == "m³" and i["lot"] in ("Fondations", "Sous-sol", "Dallage", "Gros œuvre")), 1)}


def AREA_KG(label: str) -> float:
    n, d = label.split("HA")
    return int(n) * MASS[int(d)]


# ---------------------------------------------------------------- 10. séisme (Portugal, NP EN 1998-1 + AN)
AGR_PT = {"1.1": 2.5, "1.2": 2.0, "1.3": 1.5, "1.4": 1.0, "1.5": 0.6, "1.6": 0.35,
          "2.1": 2.5, "2.2": 2.0, "2.3": 1.7, "2.4": 1.1, "2.5": 0.8}            # a_gR (m/s²), Quadro NA.I
SOIL_PT = {1: {"A": (1.0, 0.1, 0.6, 2.0), "B": (1.35, 0.1, 0.6, 2.0), "C": (1.6, 0.1, 0.6, 2.0), "D": (2.0, 0.1, 0.8, 2.0), "E": (1.8, 0.1, 0.6, 2.0)},
           2: {"A": (1.0, 0.1, 0.25, 2.0), "B": (1.35, 0.1, 0.25, 2.0), "C": (1.6, 0.1, 0.25, 2.0), "D": (2.0, 0.1, 0.3, 2.0), "E": (1.8, 0.1, 0.25, 2.0)}}
GAMMA_I = {"I": 0.65, "II": 1.0, "III": 1.45, "IV": 1.95}                       # ação tipo 1 (tipo 2 : 0,75 / 1,0 / 1,25 / 1,50)
GAMMA_I2 = {"I": 0.75, "II": 1.0, "III": 1.25, "IV": 1.50}


def _sd(T, ag, S, TB, TC, TD, q, beta=0.2):
    if T < TB:
        v = ag * S * (2 / 3 + T / TB * (2.5 / q - 2 / 3))
    elif T <= TC:
        v = ag * S * 2.5 / q
    elif T <= TD:
        v = ag * S * 2.5 / q * TC / T
    else:
        v = ag * S * 2.5 / q * TC * TD / T ** 2
    return max(v, beta * ag)


def seismic(m: Model, ld: dict, fl: dict, desc: dict) -> dict | None:
    pr = m.raw["project"]
    if pr.get("country") != "PT":
        return None
    from .i18n import native
    f2 = lambda v, n=2: f"{v:.{n}f}".replace(".", ",")  # noqa: E731
    z1, z2 = str(pr.get("seismic_zone_type1", "1.6")), str(pr.get("seismic_zone_type2", "2.5"))
    soil = pr.get("ground_type", "B")
    cls = pr.get("importance_class", "II")
    q = float(pr.get("behaviour_factor_q", 1.5))
    eaves = m.roof["eaves_level"]
    H = eaves - max(0.0, m.levels[0].floor_top)
    T1 = 0.05 * H ** 0.75
    gw = ld["g_wall"]
    perim = 2 * (m.L + m.W)
    area = m.L * m.W
    storeys = []
    above = [s_ for s_ in fl["slabs"] if s_["level_top"] > 0.01]
    lvl_z = [s_["level_top"] for s_ in above] + [eaves]
    for k, z in enumerate(lvl_z):
        z_below = lvl_z[k - 1] if k else 0.0
        z_above = lvl_z[k + 1] if k + 1 < len(lvl_z) else z
        walls = gw * perim * ((z - z_below) / 2 + (z_above - z) / 2)
        if k < len(above):
            s_ = above[k]
            W_ = (s_["G"] + 0.3 * s_["Q"]) * area + walls
            name = next((lv.name for lv in m.levels if abs(lv.floor_top - z) < 0.01), f"z = {f2(z)}")
        else:
            gab = len(m.roof.get("gables", [])) * gw * m.L * (m.roof["ridge_level"] - eaves) / 2 / 2
            W_ = ld["g_roof_plan"] * (m.L + 0.6) * m.W + walls + gab
            name = "Cobertura (beirado)"
        storeys.append({"level": name, "z": round(z, 2), "W_kN": round(W_, 1), "m_t": round(W_ / 9.81, 1)})
    Wtot = sum(x["W_kN"] for x in storeys)
    acts = []
    for typ, zone, gtab in ((1, z1, GAMMA_I), (2, z2, GAMMA_I2)):
        agR = AGR_PT.get(zone, 0.35 if typ == 1 else 0.8)
        ag = gtab.get(cls, 1.0) * agR
        Smax, TB, TC, TD = SOIL_PT[typ].get(soil, SOIL_PT[typ]["B"])
        S = Smax if ag <= 1 else (1.0 if ag >= 4 else Smax - (Smax - 1) * (ag - 1) / 3)
        sd = _sd(T1, ag, S, TB, TC, TD, q)
        lam = 0.85 if (T1 <= 2 * TC and len(storeys) > 2) else 1.0
        Fb = sd / 9.81 * Wtot * lam
        acts.append({"type": typ, "zone": zone, "agR": agR, "ag": round(ag, 3), "S": round(S, 3), "TB": TB, "TC": TC, "TD": TD,
                     "Sd": round(sd, 3), "lambda": lam, "Fb": round(Fb, 1)})
    gov = max(acts, key=lambda a: a["Fb"])
    sz = sum(x["z"] * x["W_kN"] for x in storeys)
    for x in storeys:
        x["F_kN"] = round(gov["Fb"] * x["z"] * x["W_kN"] / sz, 1)
    # résistance au cisaillement des murs du rez-de-chaussée (NP EN 1996-1-1 §6.2 ; f_vk = f_vk0 + 0,4 σ_d)
    first = next(lv for lv in m.levels if lv.floor_top > -1.0)
    fvk0, gm, t = 0.20, BRICK["gamma_m"], BRICK["t"]
    dirs = []
    for label, sides in (("X (paredes longitudinais)", bearing_sides(m)), ("Y (paredes de empena / transversais)", end_sides(m))):
        Lnet, VRd = 0.0, 0.0
        for sd_ in sides:
            ln = m.side_length(sd_) - sum(o.width for o in m.openings_on(sd_, first.id))
            rw = row(desc, sd_, first.id)
            sigma = rw["G"] / t / 1000                      # MPa (charges permanentes, situação sísmica)
            fvk = min(fvk0 + 0.4 * sigma, 0.065 * BRICK["fb"])
            VRd += fvk / gm * 1000 * t * ln                 # kN
            Lnet += ln
        pA = Lnet * t / area * 100
        if label.startswith("Y"):
            for w in m.stair["cage_walls"]:          # voiles BA 15 de la cage (parallèles à Y), v_Rd,c min ≈ 0,45 MPa
                VRd += 0.45 * 1000 * w["t"] * (w["y1"] - w["y0"])
        dirs.append({"dir": label, "length_m": round(Lnet, 2), "pA": round(pA, 2), "V_Ed": gov["Fb"], "V_Rd": round(VRd, 1),
                     "ratio": round(gov["Fb"] / VRd, 3) if VRd else 9.99})
    worst = max(d["ratio"] for d in dirs)
    table = [
        ("Zona sísmica (a confirmar)", z1, z2),
        ("a_gR (m/s²)", f2(acts[0]["agR"]), f2(acts[1]["agR"])),
        (f"Classe de importância {cls} : γ_I", f2(GAMMA_I.get(cls, 1.0)), f2(GAMMA_I2.get(cls, 1.0))),
        ("a_g = γ_I · a_gR (m/s²)", f2(acts[0]["ag"], 3), f2(acts[1]["ag"], 3)),
        (f"Terreno tipo {soil} : S", f2(acts[0]["S"], 3), f2(acts[1]["S"], 3)),
        ("T_B / T_C / T_D (s)", f"{f2(acts[0]['TB'], 1)} / {f2(acts[0]['TC'], 2)} / {f2(acts[0]['TD'], 1)}", f"{f2(acts[1]['TB'], 1)} / {f2(acts[1]['TC'], 2)} / {f2(acts[1]['TD'], 1)}"),
        (f"S_d(T_1) com q = {f2(q, 1)} (m/s²)", f2(acts[0]["Sd"], 3), f2(acts[1]["Sd"], 3)),
        ("F_b = S_d · m · λ (kN)", f2(acts[0]["Fb"], 1), f2(acts[1]["Fb"], 1)),
    ]
    table = [tuple(native(c) for c in rw_) for rw_ in table]
    intro = native(f"Edifício de alvenaria de {len(above) + 1} piso(s), altura H = {f2(H)} m acima do terreno. Período fundamental estimado "
                   f"T_1 = C_t · H^(3/4) = 0,05 × {f2(H)}^0,75 = {f2(T1, 3)} s (NP EN 1998-1 §4.3.3.2.2). Peso sísmico W = Σ (G + ψ_E·Q) = {f2(Wtot, 0)} kN "
                   f"(ψ_E = 0,3, conservativo). Coeficiente de comportamento q = {f2(q, 1)} admitido para alvenaria confinada por cintas e "
                   f"pilaretes de betão armado (hipótese a validar). Ação condicionante : tipo {gov['type']} — F_b = {f2(gov['Fb'], 1)} kN.")
    notes = [
        native("Regras simplificadas para edifícios de alvenaria (NP EN 1998-1 §9.7) : planta aproximadamente retangular "
               f"(L/B = {f2(m.L / m.W)} ≤ 4), paredes resistentes em duas direções ortogonais, pavimentos rígidos (laje aligeirada com lâmina de compressão "
               "e cintas em todas as paredes) ; área mínima de paredes p_A,min a confirmar no Quadro 9.3 do Anexo Nacional."),
        native(f"Resistência ao corte das paredes do {first.name} : f_vd = (f_vk0 + 0,4·σ_d)/γ_M com f_vk0 = {f2(fvk0)} MPa e γ_M = {f2(gm, 1)} "
               "(valor conservativo ; o EC8 permite γ_M = 2/3 do valor corrente, ≥ 1,5) ; aberturas do piso descontadas, divisórias interiores desprezadas ; "
               "na direção Y somam-se as paredes de betão armado da caixa de escada (v_Rd,c ≈ 0,45 MPa)."),
        native("Zonamento sísmico, classe de terreno e classe de importância : valores do concelho a CONFIRMAR pelo projetista (Anexo Nacional, Quadro NA.I) "
               "e pelo estudo geotécnico."),
        native("Pormenorização sísmica : cintas de betão armado em todos os pisos, pilaretes nos cunhais, nos encontros de paredes e de cada lado das aberturas ≥ 1,50 m, "
               "ligação laje-parede contínua ; tijolo de furação vertical (grupo 2) com f_b ≥ 5 MPa."),
    ]
    return {"method": "NP EN 1998-1 + AN — método das forças laterais", "q": q, "T1": round(T1, 3), "H": round(H, 2),
            "W_kN": round(Wtot, 1), "actions": acts, "governing": gov["type"], "Fb_kN": gov["Fb"], "storeys": storeys,
            "directions": dirs, "worst_ratio": worst, "ok": worst <= 1.0, "table": table, "intro": intro, "notes": notes}


def compute(m: Model) -> dict:
    ld = loads(m)
    fl = floors(m, ld)
    desc = descent(m, ld, fl)
    mas = masonry(m, desc, fl)
    lin = lintels(m, ld, fl)
    bw = basement_walls(m)
    fnd = foundations(m, desc)
    sz = seismic(m, ld, fl, desc)
    extra = {"seismic": sz} if sz else {}
    return {**extra, "loads": ld, "floors": fl, "descent": desc, "masonry": mas, "lintels": lin, "basement": bw,
            "foundations": fnd, "slab_on_grade": slab_on_grade(m), "stairs": stairs(m),
            "quantities": quantities(m, fl, lin, fnd, bw, ld)}
