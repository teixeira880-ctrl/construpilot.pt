"""Étude thermique d'abord : quand le client ne fournit pas d'étude thermique, le moteur RE2020 (calc_lots/re2020.py)
dimensionne l'isolation qui fait passer les exigences (Bbio, Cep, Cep,nr, Ic énergie, DH), puis on en déduit l'épaisseur
réelle de chaque paroi : brique + doublage isolant → épaisseur totale des murs utilisée par les plans, le métré et le devis.

Déterministe, sans IA. L'enveloppe est mesurée sur le BuildingModel (murs par façade et par niveau chauffé, baies,
plancher bas sur sous-sol non chauffé ou terre-plein, plancher des combles ou rampants), les systèmes viennent de la
demande du client (hvac.options : PAC, plancher chauffant, VMC, rafraîchissement).
"""
from __future__ import annotations

import math
import re

from . import spec as SPEC
from .model import Model

LAMBDA_DOUBLAGE = 0.032           # PSE graphité (doublage collé « 10 + e »)
LAMBDA_COMBLES = 0.046            # laine minérale soufflée
LAMBDA_RAMPANTS = 0.035           # laine minérale en rouleaux
LAMBDA_SOUS_CHAPE = 0.022         # polyuréthane sous chape (plancher chauffant)
R_BRIQUE = {"brique_isobric_20": 1.00, "brique_porotherme_20": 1.05, "brique_20": 0.55}     # m².K/W (DoP fabricant à confirmer)
R_SI_SE = 0.13 + 0.04
R_ENDUIT, R_PLAQUE = 0.01, 0.04
PLAQUE = 0.013
MARGIN = 0.97                     # ≥ 3 % de marge sous chaque seuil RE2020


def _f(v: float, n: int = 2) -> str:
    return f"{v:.{n}f}".replace(".", ",")

# paliers d'isolation, du plus léger au plus performant : (doublage mm, combles mm, rampants mm, sous chape mm, Uw)
TIERS = [
    (100, 300, 200, 60, 1.3),
    (120, 320, 220, 80, 1.3),
    (140, 350, 240, 80, 1.3),
    (160, 400, 260, 100, 1.2),
    (180, 400, 280, 120, 1.1),
    (200, 450, 300, 140, 1.0),
]
ORIENT_WORDS = [("nord-est", "NE"), ("nord-ouest", "NO"), ("sud-est", "SE"), ("sud-ouest", "SO"), ("nord", "N"), ("sud", "S"),
                ("est", "E"), ("ouest", "O")]


def orientation(m: Model, side: str) -> str:
    sd = m.side(side)
    if sd.get("orientation"):
        return str(sd["orientation"]).upper().replace("W", "O")
    lab = (sd.get("label") or "").lower()
    for w, o in ORIENT_WORDS:
        if re.search(rf"\b{w}\b", lab):
            return o
    return "S"


def u_mur(m: Model, e_mm: int) -> float:
    rb = R_BRIQUE.get((m.raw.get("user_hypotheses") or {}).get("masonry"), 1.0)
    return 1.0 / (R_SI_SE + R_ENDUIT + rb + e_mm / 1000 / LAMBDA_DOUBLAGE + R_PLAQUE)


def u_combles(e_mm: int) -> float:
    return 1.0 / (0.10 + 0.10 + 0.15 + e_mm / 1000 / LAMBDA_COMBLES + R_PLAQUE)


def u_rampants(e_mm: int) -> float:
    return 1.0 / (0.10 + 0.10 + e_mm / 1000 / LAMBDA_RAMPANTS + R_PLAQUE) * 1.05        # + ponts des chevrons


def u_plancher_bas(e_mm: int) -> float:
    return 1.0 / (0.17 + 0.17 + 0.15 + 0.03 + e_mm / 1000 / LAMBDA_SOUS_CHAPE)


def heated_levels(m: Model) -> list:
    return [lv for lv in m.levels if lv.floor_top > -1.0 or "habit" in (lv.use or "")]


def sref(m: Model) -> float:
    excl = {"garage", "local_technique"}
    return round(sum((r["x1"] - r["x0"]) * (r["y1"] - r["y0"]) if not r.get("area_pc") else r["area_pc"]
                     for lv in heated_levels(m) for r in m.rooms(lv.id) if r["type"] not in excl), 1)


def systems(m: Model) -> dict:
    from . import hvac as _hvac
    o = _hvac.options(m)
    vent = "vmc_df" if o["ventilation"] == "double_flux" else "vmc_sf_hygro_b"
    return {"chauffage": "pac_air_eau", "rendement_chauffage": 4.0 if o["heating"] == "pac_plancher_chauffant" else 3.6,
            "ecs": "cet", "rendement_ecs": 2.8, "ventilation": vent,
            "refroidissement": "pac_reversible" if o["cooling"] else None, "eer": 4.0 if o["cooling"] else None,
            "_opts": o}


def params(m: Model, tier: tuple, annee: int = 2026) -> dict:
    e_mur, e_comb, e_ramp, e_pb, uw = tier
    U_MUR, U_DOOR = u_mur(m, e_mur), 1.5
    hl = heated_levels(m)
    parois = []
    attic_hab = bool(m.roof.get("habitable_attic"))
    for side, sd in m.raw["sides"].items():
        if sd.get("type") == "mitoyen":
            continue                               # mitoyen chauffé : paroi sans déperdition
        ori = orientation(m, side)
        length = m.side_length(side)
        for lv in hl:
            h = m.storey_height(lv.id)
            gross = length * h
            if side in (m.roof.get("gables") or []) and lv.id == m.levels[-1].id and attic_hab:
                gross += length * (m.roof["ridge_level"] - m.roof["eaves_level"]) / 2
            ops = [o for o in m.openings_on(side, lv.id) if "garage" not in o.kind.lower()]
            gar = [r for r in m.rooms(lv.id) if r["type"] == "garage"]
            if gar:                                # garage dans le volume d'un niveau chauffé : sa portion de façade est hors volume
                gross -= sum(((r["x1"] - r["x0"]) if sd["axis"] == "y" else (r["y1"] - r["y0"])) * h
                             for r in gar if (sd["axis"] == "y" and abs((r["y0"] if sd["pos"] < 1 else r["y1"]) - sd["pos"]) < 0.6)
                             or (sd["axis"] == "x" and abs((r["x0"] if sd["pos"] < 1 else r["x1"]) - sd["pos"]) < 0.6))
            a_ops = sum(o.width * o.height for o in ops)
            if gross - a_ops > 0.5:
                parois.append({"type": "mur", "surface_m2": round(gross - a_ops, 2), "U": round(U_MUR, 3), "cote": "exterieur", "orientation": ori})
            for o in ops:
                porte = "porte" in o.kind.lower() and "fen" not in o.kind.lower()
                parois.append({"type": "porte" if porte else "fenetre", "surface_m2": round(o.width * o.height, 2),
                               "U": U_DOOR if porte else uw, "cote": "exterieur", "orientation": ori,
                               "g": None if porte else 0.45, "protection": None if porte else "volets"})
    # toiture
    if attic_hab:
        tan_a = (m.roof["ridge_level"] - m.roof["eaves_level"]) / max(m.roof_run, 0.1)
        ramp = 2 * m.roof_run / math.cos(math.atan(tan_a)) * m.ridge_length
        parois.append({"type": "toiture", "surface_m2": round(ramp, 2), "U": round(u_rampants(e_ramp), 3), "cote": "exterieur", "orientation": "H"})
    else:
        parois.append({"type": "plafond", "surface_m2": round((m.L - 0.4) * (m.W - 0.4), 2), "U": round(u_combles(e_comb), 3),
                       "cote": "comble_perdu", "orientation": "H"})
    for rw in m.roof.get("roof_windows") or []:
        if attic_hab:
            parois.append({"type": "fenetre", "surface_m2": round(rw.get("w", 0.78) * rw.get("h", 0.98), 2), "U": uw, "cote": "exterieur",
                           "orientation": "H", "g": 0.45, "protection": "volets"})
    # plancher bas
    low = hl[0]
    below = [lv for lv in m.levels if lv.floor_top < low.floor_top]
    a_gar = sum((r["x1"] - r["x0"]) * (r["y1"] - r["y0"]) for r in m.rooms(low.id) if r["type"] == "garage")
    parois.append({"type": "plancher_bas", "surface_m2": round((m.L - 0.4) * (m.W - 0.4) - a_gar, 2), "U": round(u_plancher_bas(e_pb), 3),
                   "cote": "local_non_chauffe" if below else "terre_plein", "orientation": None})
    if a_gar:
        parois.append({"type": "plafond", "surface_m2": round(a_gar, 2), "U": 0.22, "cote": "garage", "orientation": None})
    sy = systems(m)
    pr = m.raw["project"]
    cp = str(pr.get("code_postal") or "")
    if not cp:
        mt = re.search(r"\((\d{2})\)|\b(\d{5})\b", str(pr.get("address", "")))
        cp = (mt.group(2) or (mt.group(1) + "000")) if mt else "75000"
    h_tot = m.roof["ridge_level"] - m.levels[0].floor_top
    p = {"type_batiment": "maison", "sref_m2": sref(m), "nb_logements": 1, "code_postal": cp, "altitude_m": pr.get("altitude_m", 40),
         "annee_permis": annee, "niveaux": len(hl), "hauteur_m": round(sum(lv.hsp for lv in hl) / len(hl), 2),
         "structure": "brique", "inertie": "lourde", "parois": parois, "protections_solaires": "volets", "q4pa_surf": 0.6,
         "ventilation": sy["ventilation"], "ouverture_nocturne": "traversant", "chauffage": sy["chauffage"],
         "rendement_chauffage": sy["rendement_chauffage"], "ecs": sy["ecs"], "rendement_ecs": sy["rendement_ecs"]}
    if sy["refroidissement"]:
        p.update({"refroidissement": sy["refroidissement"], "eer": sy["eer"]})
    p["_h_tot"] = h_tot
    return p


def _passes(o: dict) -> bool:
    s = o["seuils"]
    dh_ok = next((c["ok"] for c in o["controles"] if c["ref"].startswith("DH")), True)
    k = MARGIN                                    # marge de conception (le calcul réglementaire final varie de quelques %)
    return (o["Bbio"] <= k * s["Bbio_max"] and o["Cep_nr"] <= k * s["Cep_nr_max"] and o["Cep"] <= k * s["Cep_max"]
            and o["Ic_energie"] <= s["Ic_energie_max"] and dh_ok is not False)


def requested_insulation(m: Model) -> int | None:
    """Épaisseur imposée par le client (« isolation 120 », « doublage 10+100 ») ; None = à dimensionner."""
    uh = m.raw.get("user_hypotheses") or {}
    if uh.get("insulation_mm"):
        return int(uh["insulation_mm"])
    txt = str(uh.get("_text", "")).lower()
    mt = re.search(r"(?:isolation|doublage|isolant)[^0-9]{0,20}(?:10\s*\+\s*)?(\d{2,3})\s*(?:mm)?", txt)
    if mt:
        v = int(mt.group(1))
        return v * 10 if v < 40 else v
    return None


def candidates(m: Model, forced: int | None):
    """Solutions dans l'ordre où un BET les essaie (de la moins chère / la moins épaisse à la plus lourde) :
    isolant courant, puis VMC double flux et rupteurs de ponts thermiques, et seulement ensuite des doublages plus épais.
    La ventilation n'est changée que si le client ne l'a pas imposée."""
    o = systems(m)["_opts"]
    vent_free = o["source"].get("ventilation") == "hypothèse ConstruPilot"
    vents = ["sf", "df"] if vent_free else (["df"] if o["ventilation"] == "double_flux" else ["sf"])
    tiers = TIERS
    if forced is not None:
        base = min(TIERS, key=lambda t: abs(t[0] - forced))
        tiers = [(forced,) + base[1:]]
    out = []
    for t in tiers[:3] if forced is None else tiers:
        for v in vents:
            for psi in (0.22, 0.15):
                out.append((t, v, psi))
    for t in (tiers[3:] if forced is None else []):
        for v in vents:
            out.append((t, v, 0.15))
    return out


def size(m: Model) -> dict:
    """Dimensionne l'isolation au plus juste qui passe la RE2020 ; renvoie le palier, les U, les épaisseurs et le calcul."""
    from engines.calc_lots import re2020
    forced = requested_insulation(m)
    tried, chosen, last = [], None, None
    for t, v, psi in candidates(m, forced):
        p = params(m, t)
        p.pop("_h_tot", None)
        p["ventilation"] = "vmc_df" if v == "df" else "vmc_sf_hygro_b"
        p["ratio_psi"] = psi
        o = re2020.calculer(p)
        ok = _passes(o)
        tried.append({"tier": t, "ventilation": p["ventilation"], "psi": psi, "Bbio": round(o["Bbio"], 1), "Cep_nr": round(o["Cep_nr"], 1), "ok": ok})
        last = (t, p, o)
        if ok:
            chosen = last
            break
    t, p, o = chosen or last
    e_mur, e_comb, e_ramp, e_pb, uw = t
    lining = math.ceil((e_mur + PLAQUE * 1000 + 2) / 10) / 100          # doublage collé 10 + e (+ 2 mm de colle), arrondi au cm
    sy = {k: v for k, v in systems(m).items() if not k.startswith("_")}
    sy["ventilation"] = p["ventilation"]
    baies = sum(l["A"] for l in o["parois"] if l["type"] == "fenetre")
    return {"tier": t, "params": p, "result": o, "tried": tried, "forced": forced, "ok": _passes(o),
            "ventilation": p["ventilation"], "psi": p["ratio_psi"], "baies_m2": round(baies, 1),
            "baies_manque_m2": round(max(p["sref_m2"] / 6 - baies, 0.0), 1),
            "wall_insulation_mm": e_mur, "lining": round(lining, 2), "wall_total": round(m.t_str + lining, 2),
            "U": {"mur": round(u_mur(m, e_mur), 3), "combles": round(u_combles(e_comb), 3), "rampants": round(u_rampants(e_ramp), 3),
                  "plancher_bas": round(u_plancher_bas(e_pb), 3), "fenetre": uw, "porte": 1.5},
            "thickness_mm": {"doublage": e_mur, "combles": e_comb, "rampants": e_ramp, "sous_chape": e_pb},
            "sref": p["sref_m2"], "systems": sy}


def describe(th: dict, m: Model) -> list[str]:
    """Lignes « Hypothèses / décisions » lisibles par le client."""
    o, U, e = th["result"], th["U"], th["thickness_mm"]
    s = o["seuils"]
    attic_hab = bool(m.roof.get("habitable_attic"))
    lines = [
        f"Étude thermique RE2020 faite d'abord (pas d'étude fournie) : isolation dimensionnée au plus juste — "
        f"Bbio {o['Bbio']:.0f} / {s['Bbio_max']:.0f}, Cep,nr {o['Cep_nr']:.0f} / {s['Cep_nr_max']:.0f}, Cep {o['Cep']:.0f} / {s['Cep_max']:.0f}, "
        f"Ic énergie {o['Ic_energie']:.0f} / {s['Ic_energie_max']:.0f}, classe {o['classement']['dpe']}.",
        f"Murs : {SPEC.of(m)['brick']} + doublage PSE graphité λ 0,032 « 10 + {e['doublage']} » → U = {_f(U['mur'], 3)} W/m².K ; "
        f"épaisseur totale des murs {_f(th['wall_total'])} m (brique 0,20 + doublage {_f(th['lining'])}) + enduit 15 mm.",
        (f"Rampants : laine minérale {e['rampants']} mm → U = {_f(U['rampants'], 3)}" if attic_hab else
         f"Plancher des combles : laine soufflée {e['combles']} mm → U = {_f(U['combles'], 3)}") + " W/m².K.",
        f"Plancher bas : polyuréthane {e['sous_chape']} mm sous chape → U = {_f(U['plancher_bas'], 3)} W/m².K ; menuiseries Uw {_f(U['fenetre'], 1)}, volets roulants.",
    ]
    lines.append(("VMC double flux (η 75 %)" if th["ventilation"] == "vmc_df" else "VMC simple flux hygroréglable B")
                 + (" et rupteurs de ponts thermiques en about de planchers (ψ ≤ 0,15 W/m²Sref.K)" if th["psi"] <= 0.15 else "")
                 + " retenus par l'étude" + (" (levier le moins coûteux pour passer le Bbio)." if th["ventilation"] == "vmc_df" or th["psi"] <= 0.15 else "."))
    if th["baies_manque_m2"] > 0:
        lines.append(f"Surface de baies {_f(th['baies_m2'], 1)} m² < 1/6 de la surface habitable ({_f(th['sref'] / 6, 1)} m²) : exigence de moyens RE2020 "
                     f"non tenue — ajouter ≈ {_f(th['baies_manque_m2'], 1)} m² de vitrage (de préférence au Sud), à valider avec l'architecte.")
    if th.get("forced"):
        lines.insert(1, f"Épaisseur d'isolant imposée par la demande : {th['forced']} mm.")
    if not th["ok"]:
        lines.append("ATTENTION : même au palier le plus performant, au moins une exigence RE2020 n'est pas tenue — revoir systèmes / baies.")
    return lines


def apply(raw: dict, m: Model, th: dict) -> None:
    """Reporte l'étude dans le relevé : épaisseur des murs, isolant (lu par hvac/devis), décisions et hypothèses tracées."""
    env = raw["envelope"]
    old = env.get("wall_total_thickness")
    env["wall_total_thickness"] = th["wall_total"]
    if old is not None:
        _reflow(raw, float(old), th["wall_total"])
    env["lining_thickness"] = th["lining"]
    uh = raw.setdefault("user_hypotheses", {})
    uh.setdefault("insulation_mm", th["wall_insulation_mm"])
    if th["ventilation"] == "vmc_df" and not uh.get("ventilation"):
        uh["ventilation"] = "double_flux"
    o = th["result"]
    raw["thermal"] = {"source": "étude thermique RE2020 ConstruPilot (pré-étude)", "U": th["U"], "thickness_mm": th["thickness_mm"],
                      "wall_total": th["wall_total"], "lining": th["lining"], "sref": th["sref"], "ok": th["ok"],
                      "Bbio": round(o["Bbio"], 1), "Bbio_max": round(o["seuils"]["Bbio_max"], 1), "Cep": round(o["Cep"], 1),
                      "Cep_max": round(o["seuils"]["Cep_max"], 1), "Cep_nr": round(o["Cep_nr"], 1), "Cep_nr_max": round(o["seuils"]["Cep_nr_max"], 1),
                      "Ic_energie": round(o["Ic_energie"], 1), "Ic_energie_max": round(o["seuils"]["Ic_energie_max"], 1),
                      "DH": round(o["DH"]), "DH_max": round(o["seuils"]["DH_max"]), "classe": o["classement"]["dpe"],
                      "cep_dpe": o["classement"]["cep"], "ges": o["classement"]["ges"], "zone": o["zone"],
                      "systems": th["systems"], "tried": th["tried"], "ventilation": th["ventilation"], "psi": th["psi"],
                      "baies_m2": th["baies_m2"], "baies_manque_m2": th["baies_manque_m2"]}
    dec = raw.setdefault("_decisions", [])
    dec += describe(th, m)
    if old is not None and abs(float(old) - th["wall_total"]) > 0.005:
        dec.append(f"Épaisseur des murs portée de {float(old):.2f} à {th['wall_total']:.2f} m par l'étude thermique (cotes intérieures à reprendre "
                   "avec l'architecte : surfaces habitables légèrement modifiées).".replace(".", ",", 2))
    raw.setdefault("hypotheses", []).append({"field": "épaisseur des murs", "value": f"{th['wall_total']:.2f} m (étude thermique)", "source": "hypothese"})


def _reflow(raw: dict, old_t: float, new_t: float) -> None:
    """Les pièces et cloisons qui s'appuient sur le doublage des murs extérieurs suivent la nouvelle épaisseur."""
    L, W = raw["envelope"]["length_x"], raw["envelope"]["width_y"]
    tol = 0.03

    def fix(r):
        if abs(r["x0"] - old_t) <= tol:
            r["x0"] = new_t
        if abs(r["y0"] - old_t) <= tol:
            r["y0"] = new_t
        if abs(r["x1"] - (L - old_t)) <= tol:
            r["x1"] = round(L - new_t, 3)
        if abs(r["y1"] - (W - old_t)) <= tol:
            r["y1"] = round(W - new_t, 3)
    for lst in list((raw.get("rooms") or {}).values()) + list((raw.get("interior_walls") or {}).values()):
        for r in lst:
            if all(k in r for k in ("x0", "y0", "x1", "y1")):
                fix(r)
                for part in r.get("parts") or []:
                    fix(part)


def has_client_study(raw: dict) -> bool:
    uh = raw.get("user_hypotheses") or {}
    return bool(raw.get("thermal") or uh.get("thermal_study") or re.search(r"\b(étude|etude) thermique (jointe|fournie|ci-jointe)\b",
                                                                              str(uh.get("_text", "")).lower()))
