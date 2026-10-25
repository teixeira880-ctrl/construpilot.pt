"""Comportement thermique par fraction / logement.

PT : pré-certificado REH (engines.calc_lots.reh — DL 101-D/2020, Portaria 138-I/2021) par fração : Nic/Ni, Nvc/Nv, Ntc/Nt,
classe energética, potência de aquecimento de projeto (θe REH).
FR : bilan simplifié des déperditions (U de référence RE2020 / garde-fous, θe de base) et besoin indicatif ; l'étude RE2020
réglementaire reste à faire par le thermicien.

Envolvente relevée sur la trame : côtés des rectangles de fractions situés sur le périmètre = façades extérieures,
côtés contre un noyau = paroi sur espace non utile (circulations), autres côtés = mitoyen chauffé (sans échange).
"""
from __future__ import annotations

import math
import unicodedata

from .calc import num
from .lang import _
from .model import Frame

GLAZ = 0.22                  # part vitrée des façades (hypothèse si non relevée)
U_PT = {"parede": 0.35, "enu": 0.62, "cobertura": 0.30, "pavimento": 0.35, "envidracado": 1.80, "porta": 1.80, "g": 0.45}
U_FR = {"mur": 0.23, "lnc": 0.50, "toit": 0.15, "plancher": 0.25, "baie": 1.30, "porte": 1.50}
THETA_FR = -5.0              # température extérieure de base indicative (zone H2/H1 de plaine) si non fournie


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()


def _orient(m: Frame) -> dict:
    """Orientation des côtés de l'emprise. `project.north` = côté de l'emprise tourné vers le nord (N par défaut = y1)."""
    north = str((m.project or {}).get("north") or (m.raw.get("site") or {}).get("north") or "y1").lower()
    rot = {"y1": ("N", "S", "E", "O"), "y0": ("S", "N", "O", "E"), "x1": ("O", "E", "N", "S"), "x0": ("E", "O", "S", "N")}.get(north, ("N", "S", "E", "O"))
    return {"y1": rot[0], "y0": rot[1], "x1": rot[2], "x0": rot[3]}


def concelho(m: Frame) -> str | None:
    from engines.calc_lots import reh
    txt = _norm(" ".join(str((m.project or {}).get(k) or "") for k in ("municipality", "concelho", "address", "name")))
    best = None
    for k in getattr(reh, "CONCELHOS", {}):
        if len(k) >= 4 and f" {k} " in f" {txt.replace(',', ' ').replace('-', ' ')} ":
            if best is None or len(k) > len(best):
                best = k
    return best


def _sides(m: Frame, un, tol=0.35):
    """[(côté, longueur, nature)] nature : ext | core | int."""
    x0, x1, y0, y1 = m.gx[0], m.gx[-1], m.gy[0], m.gy[-1]
    out = []
    for side, L, on_edge, pos in (("y0", un.x1 - un.x0, abs(un.y0 - y0) < tol, ("y", un.y0)), ("y1", un.x1 - un.x0, abs(un.y1 - y1) < tol, ("y", un.y1)),
                                  ("x0", un.y1 - un.y0, abs(un.x0 - x0) < tol, ("x", un.x0)), ("x1", un.y1 - un.y0, abs(un.x1 - x1) < tol, ("x", un.x1))):
        if on_edge:
            out.append((side, L, "ext"))
            continue
        touch = 0.0
        for c in m.cores:
            if pos[0] == "y" and (abs(c["y0"] - pos[1]) < tol or abs(c["y1"] - pos[1]) < tol):
                touch += max(0.0, min(un.x1, c["x1"]) - max(un.x0, c["x0"]))
            if pos[0] == "x" and (abs(c["x0"] - pos[1]) < tol or abs(c["x1"] - pos[1]) < tol):
                touch += max(0.0, min(un.y1, c["y1"]) - max(un.y0, c["y0"]))
        if touch > 0.5:
            out.append((side, touch, "core"))
    return out


def _habitable(m: Frame) -> list[str]:
    return [lv.id for lv in m.levels if m.units_on(lv.id)]


def _balcony_sides(m: Frame, lid: str) -> set:
    mp = {"S": "y0", "N": "y1", "W": "x0", "O": "x0", "E": "x1"}
    return {mp.get(str(b.get("side", "")).upper()) for b in m.balconies if not b.get("levels") or lid in b.get("levels")}


def compute(m: Frame) -> dict | None:
    if not m.units:
        return None
    return _pt(m) if m.country == "PT" else _fr(m)


def _pt(m: Frame) -> dict:
    from engines.calc_lots import aquecimento, reh
    hyp = []
    conc = concelho(m)
    nuts = None
    if not conc:
        nuts = "Grande Lisboa"
        hyp.append("Concelho não identificado na morada : clima de referência Grande Lisboa (a corrigir com o concelho da obra).")
    ori = _orient(m)
    habs = _habitable(m)
    lowest, highest = habs[0], habs[-1]
    below_lowest = m.levels[[l.id for l in m.levels].index(lowest) - 1] if [l.id for l in m.levels].index(lowest) > 0 else None
    clear_h = None
    out = []
    te_h = []
    ap_tot = sum(u.area * 0.85 for u in m.units) or 1.0
    roof = m.L * m.W - sum((c["x1"] - c["x0"]) * (c["y1"] - c["y0"]) for c in m.cores)
    pv = float((m.raw.get("mep") or {}).get("pv_kwp") or round(min(0.6 * len(m.units), 0.5 * roof / 5.5), 1))
    e_pv = pv * 1520.0 * 0.60
    for un in m.units:
        lv = m.level(un.level)
        ch = round(max(2.40, lv.height - m.slab_h(lv.id) - 0.12), 2)
        clear_h = clear_h or ch
        env, Lf, hp = [], 0.0, 0.0
        shade = _balcony_sides(m, un.level)
        for side, L, nat in _sides(m, un):
            if nat == "ext":
                o = ori[side]
                A = L * ch
                aw = round(GLAZ * A, 2)
                env.append({"tipo": "parede", "area_m2": round(A - aw, 2), "U": U_PT["parede"], "orientacao": o})
                env.append({"tipo": "envidracado", "area_m2": aw, "U": U_PT["envidracado"], "orientacao": o, "g": U_PT["g"],
                            "Fs": 0.60 if side in shade else 0.85, "Fs_v": 0.45 if side in shade else 0.80})
                n_v = max(1, round(aw / 3.6))
                hp += 0.25 * L + 0.10 * n_v * 4 * math.sqrt(aw / n_v)
                Lf += L
            elif nat == "core":
                env.append({"tipo": "parede", "area_m2": round(max(L * ch - 2.0, 0.5), 2), "U": U_PT["enu"], "fronteira": "enu", "btr": 0.6})
                env.append({"tipo": "porta", "area_m2": 2.0, "U": U_PT["porta"], "fronteira": "enu", "btr": 0.6})
        ap = round(un.area * 0.85, 1)              # área útil ≈ 85 % do retângulo bruto (paredes, courettes)
        if un.level == highest:
            env.append({"tipo": "cobertura", "area_m2": round(un.area, 1), "U": U_PT["cobertura"], "orientacao": "H"})
            hp += 0.30 * Lf
        if un.level == lowest:
            if below_lowest is not None:
                env.append({"tipo": "pavimento", "area_m2": round(un.area, 1), "U": U_PT["pavimento"], "fronteira": "enu", "btr": 0.9})
            else:
                env.append({"tipo": "pavimento", "area_m2": round(un.area, 1), "U": U_PT["pavimento"], "fronteira": "solo"})
            hp += 0.20 * Lf
        if not any(e["tipo"] == "envidracado" for e in env):
            env.append({"tipo": "envidracado", "area_m2": round(0.15 * ap, 1), "U": U_PT["envidracado"], "orientacao": "S", "g": U_PT["g"], "Fs": 0.7, "Fs_v": 0.6})
        tip = int(un.typology[1]) if un.typology[:1].upper() == "T" and un.typology[1:2].isdigit() else max(1, int(ap // 30))
        p = {"area_util_m2": ap, "pe_direito_m": ch, "tipo": "apartamento", "obra": "nova", "concelho": conc, "nuts": nuts,
             "envolvente": env, "pontes_termicas_w_c": round(hp, 2), "inercia": "forte", "tipologia": tip, "rph": 0.6,
             "ventilacao_mecanica": True, "aquecimento": {"tipo": "split_ar_ar", "eficiencia": 4.0}, "arrefecimento": {"eer": 4.0},
             "aqs": {"tipo": "bomba_calor", "eficiencia": 3.0}}
        if e_pv:
            p["renovavel_kwh"] = round(e_pv * ap / ap_tot, 0)
            p["renovavel_tipo"] = "fotovoltaico"
        r = reh.calcular(p)
        h2 = []
        te, _src = aquecimento.theta_projeto({"concelho": conc, "nuts": nuts}, h2)
        te_h = te_h or h2
        phi = (r["Htr"] + r["Hve"]) * (20 - te)
        out.append({"id": un.id, "name": un.name, "level": un.level, "level_name": lv.name, "typology": un.typology or f"T{tip}",
                    "Ap": ap, "Nic": r["Nic"], "Ni": r["Ni"], "Nvc": r["Nvc"], "Nv": r["Nv"], "Ntc": r["Ntc"], "Nt": r["Nt"],
                    "RNt": r["RNt"], "classe": r["classe"], "phi_w": phi, "te": te, "ok": all(c.get("ok") is not False for c in r["controles"]),
                    "fails": [c["lib"] for c in r["controles"] if c.get("ok") is False], "x0": un.x0, "y0": un.y0, "x1": un.x1, "y1": un.y1})
    c = reh.clima(conc, nuts, None)
    hyp += [f"Clima : {c['nuts']} — zonas {c['zona_i']} / {c['zona_v']} (GD = {c['GD']:.0f} °C.dia).",
            f"Envolvente de referência (Portaria 138-I/2021) : paredes U = {num(U_PT['parede'])}, cobertura U = {num(U_PT['cobertura'])}, "
            f"pavimento U = {num(U_PT['pavimento'])}, vãos Uw = {num(U_PT['envidracado'])} W/m²K, fator solar g = {num(U_PT['g'])}.",
            f"Vãos envidraçados : {int(GLAZ * 100)} % das fachadas (a substituir pelo mapa de vãos da arquitetura) ; sombreamento das varandas.",
            "Sistemas : bomba de calor ar-ar (COP 4), AQS por bomba de calor (COP 3), ventilação mecânica Rph 0,6 h⁻¹.",
            f"Renováveis : fotovoltaico coletivo {num(pv, 1)} kWp na cobertura (≈ {e_pv:.0f} kWh/ano autoconsumidos, repartidos pela área útil).",
            *te_h[:1],
            "Pré-certificado indicativo : não substitui o projeto de comportamento térmico nem o certificado SCE (Perito Qualificado ADENE)."]
    return {"country": "PT", "units": out, "hyp": hyp, "climate": c, "clear_h": clear_h, "pv_kwp": pv}


def _fr(m: Frame) -> dict:
    ori = _orient(m)
    habs = _habitable(m)
    lowest, highest = habs[0], habs[-1]
    te = float((m.raw.get("site") or {}).get("theta_base") or THETA_FR)
    out = []
    for un in m.units:
        lv = m.level(un.level)
        ch = round(max(2.40, lv.height - m.slab_h(lv.id) - 0.12), 2)
        H = 0.0
        for side, L, nat in _sides(m, un):
            A = L * ch
            if nat == "ext":
                H += (1 - GLAZ) * A * U_FR["mur"] + GLAZ * A * U_FR["baie"] + 0.30 * L
            else:
                H += 0.5 * (A * U_FR["lnc"])
        if un.level == highest:
            H += un.area * U_FR["toit"]
        if un.level == lowest:
            H += un.area * U_FR["plancher"] * 0.8
        ap = round(un.area * 0.85, 1)
        Hv = 0.34 * 0.5 * ap * ch * 0.3            # VMC hygro B, débit moyen ~0,5 vol/h, récupération nulle → coefficient réduit
        phi = (H + Hv) * (19 - te)
        bch = (H + Hv) * 24 * 2200 / 1000 / ap     # besoin de chauffage indicatif kWh/m².an (DJU 2200)
        out.append({"id": un.id, "name": un.name, "level": un.level, "level_name": lv.name, "typology": un.typology, "Ap": ap,
                    "phi_w": phi, "te": te, "bch": bch, "classe": "—", "Nic": bch, "Ni": None, "Ntc": None, "Nt": None, "RNt": None,
                    "ok": True, "fails": [], "x0": un.x0, "y0": un.y0, "x1": un.x1, "y1": un.y1})
    hyp = [f"Température extérieure de base {te:.0f} °C (à adapter à la zone et à l'altitude, NF EN 12831).",
           f"Parois : murs U = {U_FR['mur']}, toiture U = {U_FR['toit']}, plancher bas U = {U_FR['plancher']}, baies Uw = {U_FR['baie']} W/m²K ; "
           f"{int(GLAZ * 100)} % de baies en façade.",
           "Puissances de chauffage pour dimensionner les émetteurs ; l'étude RE2020 (Bbio, Cep, Ic) reste à produire par le thermicien."]
    return {"country": "FR", "units": out, "hyp": hyp, "climate": None, "clear_h": None}


def emitters(t: dict) -> dict:
    """Proposition d'émetteurs par fraction à partir de la puissance de projet."""
    rows = []
    for x in t["units"]:
        kw = x["phi_w"] / 1000
        if t["country"] == "PT":
            sys = _("PAC air-air multisplit", "Bomba de calor ar-ar multisplit")
            n = max(1, round(x["Ap"] / 25))
            txt = f"{n} × {num(math.ceil(kw / n * 1.15 * 10) / 10, 1)} kW"
        else:
            sys = _("PAC air-eau + plancher chauffant", "Bomba de calor ar-água + piso radiante")
            txt = f"{num(math.ceil(kw * 1.15 * 2) / 2, 1)} kW · {int(round(x['Ap'] * 0.85))} m² PC"
        rows.append({**x, "kw": kw, "system": sys, "units_txt": txt})
    return {"rows": rows}
