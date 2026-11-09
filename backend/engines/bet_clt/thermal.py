"""Étude thermique d'une maison / d'un bâtiment à structure bois massif CLT (FR, PT ; livrables FR, PT, EN, UK).

Enveloppe relevée sur la trame, étage par étage (emprises en L, étages en retrait) :
  façades = contour de l'emprise de chaque étage (mur mitoyen `structure.party_wall` = adiabatique) ;
  toitures = cases d'un étage sans étage au-dessus (toiture-terrasse basse comprise) ;
  plancher bas = emprise du niveau le plus bas, sur terre-plein ou sur sous-sol non chauffé (`envelope.below`).
Parois : compositions du plan de détail du fabricant (`envelope.wall|roof|floor` = couches [nom, e (m), λ (W/m.K)]) ;
à défaut, compositions CLT courantes ci-dessous. U = 1 / (Rsi + Σ e/λ + Rse) — EN ISO 6946.
PT : pré-certificado REH (DL 101-D/2020, Portaria 138-I/2021), moradia. FR : pré-étude RE2020 maison individuelle
(Bbio, Cep, Cep,nr, DH, Ic) + puissance de chauffage (NF EN 12831 simplifiée). Déterministe, sans IA.
"""
from __future__ import annotations

import math

from engines.bet_frame.model import Frame

from .lang import num, t

# Compositions de référence (de l'intérieur vers l'extérieur) — λ : CLT 0,13 (fiche technique CLT Rezult), laine minérale 0,035,
# XPS 0,034, plaque de plâtre 0,25, béton léger 0,30, béton armé 2,0 (EN ISO 10456).
DEFAULT = {
    "wall": {"rsi": 0.13, "rse": 0.04, "layers": [["Plaque de plâtre BA13 ×2", 0.025, 0.25], ["CLT 100 mm 5 plis", 0.10, 0.13],
                                                  ["Laine minérale", 0.10, 0.035], ["Membrane pare-pluie", 0.0, None], ["Enduit / bardage", 0.01, 1.0]]},
    "roof": {"rsi": 0.10, "rse": 0.04, "layers": [["Plaque de plâtre BA15 (plafond suspendu)", 0.015, 0.25], ["Lame d'air 200 mm (plénum)", 0.0, 0.16],
                                                  ["CLT 140 mm 5 plis", 0.14, 0.13], ["XPS", 0.10, 0.034], ["Béton léger de forme", 0.10, 0.30],
                                                  ["Membrane PVC + galets", 0.0, None]]},
    "floor": {"rsi": 0.17, "rse": 0.17, "layers": [["Chape béton léger", 0.05, 0.30], ["Membrane Termi Floor", 0.0, None], ["Dalle béton armé", 0.15, 2.0],
                                                   ["XPS", 0.10, 0.034]]},
}
GLAZ_DEFAULT = 0.20
UW_DEFAULT, G_DEFAULT = 1.30, 0.50
PSI = {"floor_mid": 0.05, "openings": 0.05, "roof": 0.10, "floor_low": 0.20}      # W/(m.K) — CLT à isolation continue par l'extérieur
SIDES = ("x0", "x1", "y0", "y1")


def _comp(spec: dict) -> dict:
    rows, rt = [], spec["rsi"] + spec["rse"]
    for nm, e, lam in spec["layers"]:
        if lam is None:
            r_ = 0.0
        elif e == 0.0:
            r_ = float(lam)                    # couche donnée par sa résistance (lame d'air)
        else:
            r_ = e / lam
        rt += r_
        rows.append({"name": nm, "e": e, "lam": lam if e else None, "R": r_})
    return {"layers": rows, "Rsi": spec["rsi"], "Rse": spec["rse"], "Rt": rt, "U": round(1 / rt, 3)}


def solutions(m: Frame) -> dict:
    env = m.raw.get("envelope") or {}
    out = {k: _comp(dict(DEFAULT[k], **(env.get(k) or {}))) for k in ("wall", "roof", "floor")}
    out["window"] = {"U": float(env.get("uw") or UW_DEFAULT), "g": float(env.get("g") or G_DEFAULT), "layers": []}
    return out


def _orient(m: Frame) -> dict:
    north = str((m.project or {}).get("north") or "y1").lower()
    rot = {"y1": ("N", "S", "E", "O"), "y0": ("S", "N", "O", "E"), "x1": ("O", "E", "N", "S"), "x0": ("E", "O", "S", "N")}.get(north, ("N", "S", "E", "O"))
    return {"y1": rot[0], "y0": rot[1], "x1": rot[2], "x0": rot[3]}


def geometry(m: Frame) -> dict:
    """Surfaces d'enveloppe par étage, mesurées sur la trame."""
    pw = (m.st.get("party_wall") or {}).get("side")
    gx, gy = m.gx, m.gy
    nx, ny = len(gx) - 1, len(gy) - 1
    ids = [l.id for l in m.levels]
    storeys = []
    for k, lv in enumerate(m.levels):
        with m.at_storey(lv.id):
            cells = {(i, j) for i in range(nx) for j in range(ny) if m.cell_in(i, j)}
        up = set()
        if k + 1 < len(ids):
            with m.at_storey(ids[k + 1]):
                up = {(i, j) for i in range(nx) for j in range(ny) if m.cell_in(i, j)}
        fac = {s: 0.0 for s in SIDES}
        adiab = 0.0
        for (i, j) in cells:
            for side, nb, L, edge in (("x0", (i - 1, j), gy[j + 1] - gy[j], i == 0), ("x1", (i + 1, j), gy[j + 1] - gy[j], i == nx - 1),
                                      ("y0", (i, j - 1), gx[i + 1] - gx[i], j == 0), ("y1", (i, j + 1), gx[i + 1] - gx[i], j == ny - 1)):
                if nb in cells:
                    continue
                if edge and side == pw:
                    adiab += L
                else:
                    fac[side] += L
        area = sum((gx[i + 1] - gx[i]) * (gy[j + 1] - gy[j]) for i, j in cells)
        roof = sum((gx[i + 1] - gx[i]) * (gy[j + 1] - gy[j]) for i, j in cells - up)
        storeys.append({"id": lv.id, "name": lv.name, "h": lv.height, "area": round(area, 2), "roof": round(roof, 2),
                        "fac": {s: round(v, 2) for s, v in fac.items()}, "party": round(adiab, 2)})
    return {"storeys": storeys, "ground": storeys[0]["area"] if storeys else 0.0}


def compute(m: Frame) -> dict | None:
    if m.country not in ("PT", "FR"):
        return None
    env = m.raw.get("envelope") or {}
    sol = solutions(m)
    geo = geometry(m)
    ori = _orient(m)
    glaz = {s: float((env.get("glazing") or {}).get(s, GLAZ_DEFAULT)) for s in SIDES}
    below = str(env.get("below") or "ground")                      # ground | unheated (sous-sol non chauffé)
    walls, wins, hp = {}, {}, 0.0
    psi = []
    for st in geo["storeys"]:
        for s, L in st["fac"].items():
            if L <= 0:
                continue
            A = L * st["h"]
            aw = A * glaz[s]
            walls[ori[s]] = walls.get(ori[s], 0.0) + A - aw
            wins[ori[s]] = wins.get(ori[s], 0.0) + aw
            n_v = max(1, round(aw / 3.0)) if aw > 0 else 0
            lv_ = n_v * 4 * math.sqrt(aw / n_v) if n_v else 0.0
            psi.append(("floor_mid", L))
            psi.append(("openings", lv_))
    roof = sum(st["roof"] for st in geo["storeys"])
    per0 = sum(geo["storeys"][0]["fac"].values()) if geo["storeys"] else 0.0
    psi.append(("roof", sum(sum(st["fac"].values()) for st in geo["storeys"][-1:]) + (per0 if len(geo["storeys"]) > 1 else 0.0) * 0.4))
    psi.append(("floor_low", per0))
    hp = sum(PSI[k] * L for k, L in psi)
    floor = geo["ground"]
    gross = sum(st["area"] for st in geo["storeys"])
    ap = round(gross * float(env.get("net_ratio") or 0.85), 1)       # surface utile / habitable ≈ 85 % de l'emprise brute
    ch = round(max(2.40, min(st["h"] for st in geo["storeys"]) - 0.40), 2)
    res = {"country": m.country, "solutions": sol, "geometry": geo, "walls": walls, "windows": wins, "roof": round(roof, 2), "floor": round(floor, 2),
           "below": below, "psi": psi, "hp": round(hp, 1), "Ap": ap, "gross": round(gross, 1), "ch": ch, "glazing": glaz, "orient": ori}
    res.update(_pt(m, res) if m.country == "PT" else _fr(m, res))
    return res


def _pt(m: Frame, d: dict) -> dict:
    from engines.bet_frame import _aquec as aquecimento, _reh as reh
    from engines.bet_frame.thermal import concelho
    env_cfg = m.raw.get("envelope") or {}
    sol = d["solutions"]
    conc = concelho(m)
    nuts = None if conc else str(env_cfg.get("nuts") or "Grande Lisboa")
    env = []
    for o, A in d["walls"].items():
        env.append({"tipo": "parede", "area_m2": round(A, 2), "U": sol["wall"]["U"], "orientacao": o})
    for o, A in d["windows"].items():
        if A > 0:
            env.append({"tipo": "envidracado", "area_m2": round(A, 2), "U": sol["window"]["U"], "orientacao": o, "g": sol["window"]["g"],
                        "Fs": 0.75, "Fs_v": 0.55})
    env.append({"tipo": "cobertura", "area_m2": d["roof"], "U": sol["roof"]["U"], "orientacao": "H"})
    env.append({"tipo": "pavimento", "area_m2": d["floor"], "U": sol["floor"]["U"],
                "fronteira": "enu" if d["below"] == "unheated" else "solo"})
    pv = float(env_cfg.get("pv_kwp") or 2.0)
    p = {"area_util_m2": d["Ap"], "pe_direito_m": d["ch"], "tipo": "moradia", "obra": "nova", "concelho": conc, "nuts": nuts, "envolvente": env,
         "pontes_termicas_w_c": d["hp"], "inercia": "media", "tipologia": int(str(env_cfg.get("tipologia") or "T4")[1:] or 4), "rph": 0.6,
         "ventilacao_mecanica": True, "aquecimento": {"tipo": "bomba_calor", "eficiencia": 3.8}, "arrefecimento": {"eer": 4.0},
         "aqs": {"tipo": "bomba_calor", "eficiencia": 3.0}, "renovavel_kwh": round(pv * 1520 * 0.60), "renovavel_tipo": "fotovoltaico",
         "pisos": len(d["geometry"]["storeys"])}
    r = reh.calcular(p)
    hy = []
    te, _src = aquecimento.theta_projeto({"concelho": conc, "nuts": nuts}, hy)
    phi = (r["Htr"] + r["Hve"]) * (20 - te)
    c = r["clima"]
    ri = c.get("ri", 0)
    lim = {"wall": reh.UMAX["parede"][ri], "roof": reh.UMAX["cobertura"][ri], "floor": reh.UMAX["pavimento"][ri], "window": reh.UW_MAX[ri]}
    ref = {"wall": reh.UREF["parede"][ri], "roof": reh.UREF["cobertura"][ri], "floor": reh.UREF["pavimento"][ri], "window": reh.UREF["envidracado"][ri]}
    return {"reh": {k: r[k] for k in ("Nic", "Ni", "Nvc", "Nv", "Ntc", "Nt", "RNt", "classe", "Htr", "Hve", "Qtr", "Qve", "Qint", "Qsol", "controles")},
            "climate": c, "concelho": conc, "nuts": nuts, "te": te, "phi_w": phi, "pv_kwp": pv, "Umax": lim, "Uref": ref,
            "ok": all(x.get("ok") is not False for x in r["controles"]), "fails": [x.get("lib") or x.get("ref") for x in r["controles"] if x.get("ok") is False]}


def _fr(m: Frame, d: dict) -> dict:
    from engines.bet_frame import _re2020
    env_cfg = m.raw.get("envelope") or {}
    sol = d["solutions"]
    zone = str((m.raw.get("site") or {}).get("zone") or env_cfg.get("zone") or "H2b")
    te = float((m.raw.get("site") or {}).get("theta_base") or {"H1a": -9, "H1b": -10, "H1c": -9, "H2a": -4, "H2b": -5, "H2c": -4, "H2d": -6,
                                                               "H3": -2}.get(zone, -5))
    parois = [{"type": "mur", "surface_m2": round(A, 2), "U": sol["wall"]["U"], "orientation": o} for o, A in d["walls"].items() if A > 0]
    parois += [{"type": "fenetre", "surface_m2": round(A, 2), "U": sol["window"]["U"], "orientation": o, "g": sol["window"]["g"]}
               for o, A in d["windows"].items() if A > 0]
    parois.append({"type": "toiture", "surface_m2": d["roof"], "U": sol["roof"]["U"], "cote": "exterieur"})
    parois.append({"type": "plancher_bas", "surface_m2": d["floor"], "U": sol["floor"]["U"],
                   "cote": "local_non_chauffe" if d["below"] == "unheated" else "terre_plein"})
    params = {"type_batiment": "maison", "sref_m2": d["Ap"], "zone": zone, "niveaux": len(d["geometry"]["storeys"]), "hauteur_m": d["ch"],
              "structure": "bois_massif", "parois": parois, "psi_total_w_k": d["hp"], "annee_permis": __import__("datetime").date.today().year,
              "chauffage": env_cfg.get("heating") or "pac_air_eau", "ecs": env_cfg.get("dhw") or "cet", "ventilation": env_cfg.get("ventilation") or "vmc_sf_hygro_b",
              "code_postal": (m.project or {}).get("postal_code")}
    try:
        re = _re2020.calculer(params)
    except Exception as exc:  # noqa: BLE001
        re = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    H = sum(A * sol["wall"]["U"] for A in d["walls"].values()) + sum(A * sol["window"]["U"] for A in d["windows"].values()) \
        + d["roof"] * sol["roof"]["U"] + d["floor"] * sol["floor"]["U"] * (0.5 if d["below"] == "unheated" else 0.45) + d["hp"]
    Hv = 0.34 * 0.6 * d["Ap"] * d["ch"] / 2.5
    phi = (H + Hv) * (19 - te)
    lim = {"wall": 0.20, "roof": 0.13, "floor": 0.18, "window": 1.2}               # garde-fous de conception RE2020 (U neuf courant)
    return {"re2020": re, "zone": zone, "te": te, "phi_w": phi, "H": H, "Hv": Hv, "Umax": lim, "Uref": lim,
            "ok": bool(re.get("conforme")) if "error" not in re else False,
            "fails": [c["libelle"] if "libelle" in c else str(c.get("indicateur") or c) for c in (re.get("controles") or []) if c.get("ok") is False]}


# ============================================================================================ texte de la note
def lines_hyp(th: dict) -> list[str]:
    s = th["solutions"]
    g = th["glazing"]
    gl = ", ".join(f"{th['orient'][k]} {int(round(v * 100))} %" for k, v in g.items() if v > 0)
    out = [t(f"Parois du plan de détail : mur CLT U = {num(s['wall']['U'], 3)}, toiture U = {num(s['roof']['U'], 3)}, plancher bas U = {num(s['floor']['U'], 3)} W/m²K "
             f"(EN ISO 6946, couche par couche) ; menuiseries Uw = {num(s['window']['U'])} W/m²K, g = {num(s['window']['g'])} (hypothèse — carnet de baies à fournir).",
             f"Elementos da planta de pormenor: parede CLT U = {num(s['wall']['U'], 3)}, cobertura U = {num(s['roof']['U'], 3)}, pavimento U = {num(s['floor']['U'], 3)} W/m²K "
             f"(EN ISO 6946, camada a camada); caixilharia Uw = {num(s['window']['U'])} W/m²K, g = {num(s['window']['g'])} (hipótese — mapa de vãos a fornecer).",
             f"Envelope from the detail drawing: CLT wall U = {num(s['wall']['U'], 3)}, roof U = {num(s['roof']['U'], 3)}, lowest floor U = {num(s['floor']['U'], 3)} W/m²K "
             f"(EN ISO 6946, layer by layer); windows Uw = {num(s['window']['U'])} W/m²K, g = {num(s['window']['g'])} (assumption — window schedule to be supplied).",
             f"Огороджувальні конструкції з креслення вузла: стіна CLT U = {num(s['wall']['U'], 3)}, покрівля U = {num(s['roof']['U'], 3)}, підлога U = {num(s['floor']['U'], 3)} Вт/м²К "
             f"(EN ISO 6946, пошарово); вікна Uw = {num(s['window']['U'])} Вт/м²К, g = {num(s['window']['g'])} (припущення — потрібна відомість вікон)."),
           t(f"Vitrages : {gl} des façades (hypothèse, terrasse vitrée).",
             f"Vãos: {gl} das fachadas (hipótese, terraço envidraçado).",
             f"Glazing: {gl} of façades (assumption, glazed terrace front).",
             f"Засклення: {gl} фасадів (припущення, засклений фасад тераси)."),
           t(f"Ponts thermiques linéiques : Σψ·L = {num(th['hp'], 1)} W/K (CLT isolé par l'extérieur, ψ 0,05 à 0,20 W/m.K).",
             f"Pontes térmicas lineares: Σψ·L = {num(th['hp'], 1)} W/K (CLT com isolamento pelo exterior, ψ 0,05 a 0,20 W/m.K).",
             f"Linear thermal bridges: Σψ·L = {num(th['hp'], 1)} W/K (CLT with continuous external insulation, ψ 0.05 to 0.20 W/m.K).",
             f"Лінійні теплові містки: Σψ·L = {num(th['hp'], 1)} Вт/К (CLT із зовнішнім утепленням, ψ 0,05–0,20 Вт/м.К)."),
           t(f"Plancher bas : {'sur sous-sol non chauffé (niveau -1)' if th['below'] == 'unheated' else 'sur terre-plein'} ; surface utile {num(th['Ap'], 1)} m² (85 % de {num(th['gross'], 1)} m² bruts).",
             f"Pavimento inferior: {'sobre cave não aquecida (piso -1)' if th['below'] == 'unheated' else 'sobre o terreno'}; área útil {num(th['Ap'], 1)} m² (85 % de {num(th['gross'], 1)} m² brutos).",
             f"Lowest floor: {'over unheated basement (level -1)' if th['below'] == 'unheated' else 'slab on ground'}; useful area {num(th['Ap'], 1)} m² (85 % of {num(th['gross'], 1)} m² gross).",
             f"Підлога: {'над неопалюваним підвалом (рівень -1)' if th['below'] == 'unheated' else 'по ґрунту'}; корисна площа {num(th['Ap'], 1)} м² (85 % від {num(th['gross'], 1)} м² загальної).")]
    if th["country"] == "PT":
        c = th["climate"]
        out.append(t(f"Climat : {c['nuts']} — zones {c['zona_i']} / {c['zona_v']}, GD = {c['GD']:.0f} °C.j" + ("" if th["concelho"] else " (concelho non indiqué : à corriger)") + ".",
                     f"Clima: {c['nuts']} — zonas {c['zona_i']} / {c['zona_v']}, GD = {c['GD']:.0f} °C.dia" + ("" if th["concelho"] else " (concelho não indicado: a corrigir)") + ".",
                     f"Climate: {c['nuts']} — zones {c['zona_i']} / {c['zona_v']}, HDD = {c['GD']:.0f} °C.d" + ("" if th["concelho"] else " (municipality not given: to be corrected)") + ".",
                     f"Клімат: {c['nuts']} — зони {c['zona_i']} / {c['zona_v']}, ГД = {c['GD']:.0f} °C.доба" + ("" if th["concelho"] else " (муніципалітет не вказано)") + "."))
        out.append(t(f"Systèmes : PAC air-eau (COP 3,8), ECS par PAC (COP 3), VMC Rph 0,6 h⁻¹, photovoltaïque {num(th['pv_kwp'], 1)} kWc.",
                     f"Sistemas: bomba de calor ar-água (COP 3,8), AQS por bomba de calor (COP 3), ventilação mecânica Rph 0,6 h⁻¹, fotovoltaico {num(th['pv_kwp'], 1)} kWp.",
                     f"Systems: air-to-water heat pump (COP 3.8), heat-pump DHW (COP 3), mechanical ventilation 0.6 ach, PV {num(th['pv_kwp'], 1)} kWp.",
                     f"Системи: тепловий насос повітря-вода (COP 3,8), ГВП тепловим насосом (COP 3), механічна вентиляція 0,6 год⁻¹, СЕС {num(th['pv_kwp'], 1)} кВт."))
    else:
        out.append(t(f"Zone climatique {th['zone']} (hypothèse : commune non indiquée), température de base {num(th['te'], 0)} °C (NF EN 12831).",
                     f"Zona climática {th['zone']} (hipótese: comuna não indicada), temperatura de base {num(th['te'], 0)} °C (NF EN 12831).",
                     f"Climate zone {th['zone']} (assumption: municipality not given), design temperature {num(th['te'], 0)} °C (NF EN 12831).",
                     f"Кліматична зона {th['zone']} (припущення: громада не вказана), розрахункова температура {num(th['te'], 0)} °C (NF EN 12831)."))
    return out


def blocks(th: dict, H, P, SM, tbl, esc) -> list:
    """Section « Étude thermique » de la note (flowables reportlab)."""
    from reportlab.platypus import Paragraph, Spacer
    s = [H(t("Étude thermique", "Comportamento térmico", "Thermal study", "Теплотехнічний розрахунок"))]
    for x in lines_hyp(th):
        s.append(Paragraph("• " + esc(x), SM))
    s.append(Spacer(1, 3))
    names = {"wall": t("Mur extérieur CLT", "Parede exterior CLT", "External CLT wall", "Зовнішня стіна CLT"),
             "roof": t("Toiture-terrasse CLT", "Cobertura plana CLT", "CLT flat roof", "Плоска покрівля CLT"),
             "floor": t("Plancher bas", "Pavimento inferior", "Lowest floor", "Підлога першого поверху")}
    for k in ("wall", "roof", "floor"):
        c = th["solutions"][k]
        rows = [[t("Couche", "Camada", "Layer", "Шар"), "e (m)", "λ (W/m.K)", "R (m².K/W)"]]
        rows += [[ly["name"], num(ly["e"], 3) if ly["e"] else "—", num(ly["lam"], 3) if ly["lam"] else "—", num(ly["R"], 3)] for ly in c["layers"]]
        rows.append([f"Rsi + Rse", "", "", num(c["Rsi"] + c["Rse"], 2)])
        rows.append([f"U = 1 / Rt  ({names[k]})", "", "", f"{num(c['U'], 3)} W/m²K  (U max {num(th['Umax'][k], 2)})"])
        s.append(Paragraph(f"<b>{esc(names[k])}</b>", P))
        s.append(tbl(rows, (82, 20, 26, 46)))
        s.append(Spacer(1, 3))
    rows = [[t("Paroi", "Elemento", "Element", "Елемент"), t("Orientation", "Orientação", "Orientation", "Орієнтація"), "A (m²)", "U", "H = A·U (W/K)"]]
    for o, A in th["walls"].items():
        rows.append([names["wall"], o, num(A, 1), num(th["solutions"]["wall"]["U"], 3), num(A * th["solutions"]["wall"]["U"], 1)])
    for o, A in th["windows"].items():
        if A > 0:
            rows.append([t("Baies", "Vãos envidraçados", "Windows", "Вікна"), o, num(A, 1), num(th["solutions"]["window"]["U"]), num(A * th["solutions"]["window"]["U"], 1)])
    rows.append([names["roof"], "H", num(th["roof"], 1), num(th["solutions"]["roof"]["U"], 3), num(th["roof"] * th["solutions"]["roof"]["U"], 1)])
    rows.append([names["floor"], "—", num(th["floor"], 1), num(th["solutions"]["floor"]["U"], 3), num(th["floor"] * th["solutions"]["floor"]["U"], 1)])
    rows.append([t("Ponts thermiques", "Pontes térmicas", "Thermal bridges", "Теплові містки"), "", "", "", num(th["hp"], 1)])
    s.append(tbl(rows, (56, 24, 24, 22, 48)))
    s.append(Spacer(1, 3))
    if th["country"] == "PT":
        r = th["reh"]
        rows = [[t("Indicateur REH", "Indicador REH", "REH indicator", "Показник REH"), t("Valeur", "Valor", "Value", "Значення"),
                 t("Référence", "Referência", "Reference", "Еталон"), "Nic/Ni"],
                [t("Besoin de chauffage Nic", "Necessidades de aquecimento Nic", "Heating need Nic", "Потреба в опаленні Nic"), f"{num(r['Nic'], 1)} kWh/m².an",
                 f"Ni = {num(r['Ni'], 1)}", num(r["Nic"] / r["Ni"], 2) if r["Ni"] else "—"],
                [t("Besoin de refroidissement Nvc", "Necessidades de arrefecimento Nvc", "Cooling need Nvc", "Потреба в охолодженні Nvc"), f"{num(r['Nvc'], 1)} kWh/m².an",
                 f"Nv = {num(r['Nv'], 1)}", num(r["Nvc"] / r["Nv"], 2) if r["Nv"] else "—"],
                [t("Énergie primaire Ntc", "Energia primária Ntc", "Primary energy Ntc", "Первинна енергія Ntc"), f"{num(r['Ntc'], 1)} kWhEP/m².an",
                 f"Nt = {num(r['Nt'], 1)}", f"RNt = {num(r['RNt'], 2)}"],
                [t("Classe énergétique", "Classe energética", "Energy class", "Енергетичний клас"), str(r["classe"]), "SCE", ""],
                [t("Puissance de chauffage de projet", "Potência de aquecimento de projeto", "Design heating load", "Розрахункова потужність опалення"),
                 f"{num(th['phi_w'] / 1000, 1)} kW", f"θe = {num(th['te'], 1)} °C", ""]]
        s.append(tbl(rows, (66, 40, 34, 34)))
        verdict = t("Exigences REH respectées." if th["ok"] else "Exigences REH non respectées : " + ", ".join(th["fails"]),
                    "Requisitos REH cumpridos." if th["ok"] else "Requisitos REH não cumpridos: " + ", ".join(th["fails"]),
                    "REH requirements met." if th["ok"] else "REH requirements not met: " + ", ".join(th["fails"]),
                    "Вимоги REH виконано." if th["ok"] else "Вимоги REH не виконано: " + ", ".join(th["fails"]))
        s.append(Paragraph(f"<b>{esc(verdict)}</b> " + esc(t("Pré-certificat indicatif : le certificat SCE est délivré par un Perito Qualificado (ADENE).",
                                                             "Pré-certificado indicativo: o certificado SCE é emitido por Perito Qualificado (ADENE).",
                                                             "Indicative pre-certificate: the SCE certificate is issued by an ADENE qualified expert.",
                                                             "Орієнтовний попередній сертифікат: сертифікат SCE видає кваліфікований експерт ADENE.")), SM))
    else:
        re = th.get("re2020") or {}
        if "error" in re or not re:
            s.append(Paragraph(esc(t("Pré-étude RE2020 impossible : ", "Pré-estudo RE2020 impossível: ", "RE2020 pre-study failed: ", "Попередній розрахунок RE2020 неможливий: ")
                                   + str(re.get("error", "—"))), SM))
        else:
            sx = re["seuils"]
            rows = [[t("Indicateur RE2020", "Indicador RE2020", "RE2020 indicator", "Показник RE2020"), t("Valeur", "Valor", "Value", "Значення"),
                     t("Seuil", "Limite", "Threshold", "Поріг"), ""]]
            for lab, v, mx, u in (("Bbio", re["Bbio"], sx["Bbio_max"], "pts"), ("Cep,nr", re["Cep_nr"], sx["Cep_nr_max"], "kWhep/m².an"),
                                  ("Cep", re["Cep"], sx["Cep_max"], "kWhep/m².an"), ("DH", re["DH"], sx["DH_max"], "°C.h"),
                                  ("Ic énergie", re["Ic_energie"], sx["Ic_energie_max"], "kgCO2/m²"), ("Ic construction", re["Ic_construction"], sx["Ic_construction_max"], "kgCO2/m²")):
                rows.append([lab, f"{num(v, 1)} {u}", num(mx, 1), "OK" if v <= mx + 1e-9 else t("NON", "NÃO", "NO", "НІ")])
            rows.append([t("Puissance de chauffage", "Potência de aquecimento", "Heating load", "Потужність опалення"), f"{num(th['phi_w'] / 1000, 1)} kW",
                         f"θb = {num(th['te'], 0)} °C", ""])
            s.append(tbl(rows, (60, 46, 34, 34)))
            s.append(Paragraph(esc(t("Pré-étude indicative : l'étude RE2020 réglementaire (Th-BCE 2020, ACV avec FDES) reste à produire par le thermicien.",
                                     "Pré-estudo indicativo: o estudo RE2020 regulamentar (Th-BCE 2020, ACV) deve ser produzido pelo térmico.",
                                     "Indicative pre-study: the regulatory RE2020 study (Th-BCE 2020, LCA with EPDs) must be produced by the energy consultant.",
                                     "Орієнтовний розрахунок: нормативне дослідження RE2020 (Th-BCE 2020, LCA) виконує теплотехнік.")), SM))
    return s
