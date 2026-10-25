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

# Solutions constructives de référence : couches (désignation, épaisseur m, λ W/(m.K) ou None, R m².K/W si λ None), Rsi, Rse.
# U = 1 / (Rsi + Σ e/λ + Σ R + Rse) — NP EN ISO 6946 ; λ et R des alvenarias : ITE 50 (LNEC) / Th-U (CSTB).
SOLUTIONS = {
    "PT": {
        "parede": ("Parede exterior — alvenaria de tijolo 22 cm com ETICS (EPS 8 cm)", 0.13, 0.04,
                   [("Reboco delgado armado (ETICS)", 0.005, 0.70, None), ("EPS 100 — isolamento térmico", 0.080, 0.036, None),
                    ("Alvenaria de tijolo furado 30×20×22", 0.22, None, 0.52), ("Estuque projetado", 0.015, 0.40, None)]),
        "enu": ("Parede para espaço não útil (caixa de escada) — tijolo 15 cm + lã mineral 5 cm", 0.13, 0.13,
                [("Estuque projetado", 0.015, 0.40, None), ("Alvenaria de tijolo furado 30×20×15", 0.15, None, 0.39),
                 ("Lã mineral", 0.05, 0.037, None), ("Gesso cartonado", 0.0125, 0.25, None)]),
        "cobertura": ("Cobertura plana invertida — laje BA 20 cm + XPS 10 cm", 0.10, 0.04,
                      [("Estuque projetado", 0.015, 0.40, None), ("Laje maciça de betão armado", 0.20, 2.0, None),
                       ("Betão leve de enchimento (pendentes)", 0.05, 0.30, None), ("Membrana de impermeabilização", 0.004, 0.23, None),
                       ("XPS — isolamento térmico", 0.10, 0.034, None), ("Geotêxtil + seixo rolado", 0.05, 2.0, None)]),
        "pavimento": ("Pavimento sobre garagem (ENU) — laje BA 20 cm + lã mineral 10 cm no teto", 0.17, 0.17,
                      [("Revestimento de piso + betonilha", 0.05, 1.30, None), ("Laje maciça de betão armado", 0.20, 2.0, None),
                       ("Lã mineral (teto da garagem)", 0.10, 0.037, None), ("Placa de proteção (gesso hidrófugo)", 0.0125, 0.25, None)]),
        "pavimento_solo": ("Pavimento térreo — laje sobre solo + XPS 8 cm", 0.17, 0.0,
                           [("Revestimento de piso + betonilha", 0.05, 1.30, None), ("XPS — isolamento térmico", 0.08, 0.034, None),
                            ("Laje térrea de betão armado", 0.15, 2.0, None)]),
        "envidracado": ("Vão envidraçado — caixilharia de alumínio com rutura de ponte térmica, vidro duplo baixo-emissivo 6/16/4 (Ug 1,1)", 1.80, 0.45),
        "porta": ("Porta de entrada da fração — blindada com isolamento", 1.80, None),
    },
    "FR": {
        "parede": ("Mur extérieur — voile béton 18 cm + doublage PSE graphité 14 cm", 0.13, 0.04,
                   [("Enduit de façade", 0.015, 1.0, None), ("Voile béton armé", 0.18, 2.3, None),
                    ("PSE graphité Th32", 0.14, 0.032, None), ("Plaque de plâtre BA13", 0.0125, 0.25, None)]),
        "enu": ("Mur sur circulations communes — voile béton 18 cm + doublage PSE 8 cm", 0.13, 0.13,
                [("Voile béton armé", 0.18, 2.3, None), ("PSE Th32", 0.08, 0.032, None), ("Plaque de plâtre BA13", 0.0125, 0.25, None)]),
        "cobertura": ("Toiture-terrasse — dalle BA 20 cm + PUR 12 cm + étanchéité", 0.10, 0.04,
                      [("Dalle béton armé", 0.20, 2.3, None), ("Pare-vapeur", 0.003, 0.23, None), ("Panneau PUR Th22", 0.12, 0.022, None),
                       ("Étanchéité bicouche", 0.006, 0.23, None), ("Protection gravillons", 0.05, 2.0, None)]),
        "pavimento": ("Plancher bas sur parking — dalle BA 20 cm + laine minérale 15 cm en sous-face", 0.17, 0.17,
                      [("Chape + revêtement", 0.06, 1.30, None), ("Dalle béton armé", 0.20, 2.3, None), ("Laine minérale (sous-face)", 0.15, 0.036, None)]),
        "pavimento_solo": ("Plancher bas sur terre-plein — dallage + PSE 12 cm", 0.17, 0.0,
                           [("Chape + revêtement", 0.06, 1.30, None), ("PSE Th32 sous chape", 0.12, 0.032, None), ("Dallage béton", 0.15, 2.3, None)]),
        "envidracado": ("Baie — menuiserie PVC, double vitrage 4/16/4 argon faiblement émissif", 1.30, 0.45),
        "porta": ("Porte palière isolante", 1.50, None),
    },
}


def solutions(country: str) -> dict:
    """{clé: {name, layers [(nom, e, λ, R)], Rsi, Rse, U}} — U calculé couche par couche."""
    out = {}
    for k, v in SOLUTIONS["PT" if country == "PT" else "FR"].items():
        if len(v) == 3 and not isinstance(v[2], list):
            out[k] = {"name": v[0], "layers": [], "U": v[1], "g": v[2]}
            continue
        name, rsi, rse, layers = v
        rows, rt = [], rsi + rse
        for nm, e, lam, R in layers:
            r_ = R if lam is None else e / lam
            rt += r_
            rows.append((nm, e, lam, r_))
        out[k] = {"name": name, "layers": rows, "Rsi": rsi, "Rse": rse, "Rt": rt, "U": round(1 / rt, 3)}
    return out


_SPT = solutions("PT")
_SFR = solutions("FR")
U_PT = {"parede": _SPT["parede"]["U"], "enu": _SPT["enu"]["U"], "cobertura": _SPT["cobertura"]["U"], "pavimento": _SPT["pavimento"]["U"],
        "pavimento_solo": _SPT["pavimento_solo"]["U"], "envidracado": _SPT["envidracado"]["U"], "porta": _SPT["porta"]["U"], "g": _SPT["envidracado"]["g"]}
U_FR = {"mur": _SFR["parede"]["U"], "lnc": _SFR["enu"]["U"], "toit": _SFR["cobertura"]["U"], "plancher": _SFR["pavimento"]["U"],
        "plancher_tp": _SFR["pavimento_solo"]["U"], "baie": _SFR["envidracado"]["U"], "porte": _SFR["porta"]["U"]}
THETA_FR = -5.0              # température extérieure de base indicative (zone H2/H1 de plaine) si non fournie


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)).lower()


def _orient(m: Frame) -> dict:
    """Orientation des côtés de l'emprise. `project.north` = côté de l'emprise tourné vers le nord (N par défaut = y1)."""
    north = str((m.project or {}).get("north") or (m.raw.get("site") or {}).get("north") or "y1").lower()
    rot = {"y1": ("N", "S", "E", "O"), "y0": ("S", "N", "O", "E"), "x1": ("O", "E", "N", "S"), "x0": ("E", "O", "S", "N")}.get(north, ("N", "S", "E", "O"))
    return {"y1": rot[0], "y0": rot[1], "x1": rot[2], "x0": rot[3]}


def concelho(m: Frame) -> str | None:
    from . import _reh as reh
    txt = _norm(" ".join(str((m.project or {}).get(k) or "") for k in ("municipality", "concelho", "address", "name")))
    best = None
    for k in getattr(reh, "CONCELHOS", {}):
        if len(k) >= 4 and f" {k} " in f" {txt.replace(',', ' ').replace('-', ' ')} ":
            if best is None or len(k) > len(best):
                best = k
    return best


def _outside_len(m: Frame, side: str, un, d=0.5, n=12) -> float:
    """Longueur du côté de la fraction donnant sur l'extérieur (point décalé de d vers l'extérieur hors de l'emprise réelle)."""
    if side in ("y0", "y1"):
        y = (un.y0 - d) if side == "y0" else (un.y1 + d)
        pts = [(un.x0 + (k + 0.5) * (un.x1 - un.x0) / n, y) for k in range(n)]
        L = un.x1 - un.x0
    else:
        x = (un.x0 - d) if side == "x0" else (un.x1 + d)
        pts = [(x, un.y0 + (k + 0.5) * (un.y1 - un.y0) / n) for k in range(n)]
        L = un.y1 - un.y0
    out = sum(1 for p in pts if not m.point_in(*p) and not m.in_core(*p))
    return L * out / n


def _sides(m: Frame, un, tol=0.35):
    """[(côté, longueur, nature)] nature : ext | core | int — façades jugées sur l'emprise de l'étage de la fraction."""
    with m.at_storey(un.level):
        return _sides0(m, un, tol)


def _exposure(m: Frame, un, n=8) -> dict:
    """Parts de la surface de la fraction : sous toiture (pas d'étage au-dessus), sur extérieur (pas d'étage en dessous),
    sur espace non chauffé (étage inférieur sans logement : cave, parking), sur le sol (niveau le plus bas)."""
    ids = [l.id for l in m.levels]
    k = ids.index(un.level)
    up = ids[k + 1] if k + 1 < len(ids) else None
    dn = ids[k - 1] if k > 0 else None
    pts = [(un.x0 + (a + 0.5) * (un.x1 - un.x0) / n, un.y0 + (b + 0.5) * (un.y1 - un.y0) / n) for a in range(n) for b in range(n)]

    def frac(lid):
        if lid is None:
            return 0.0
        with m.at_storey(lid):
            return sum(1 for p in pts if m.point_in(*p)) / len(pts)
    roof = 1.0 - frac(up)
    if dn is None:
        return {"roof": roof, "ground": 1.0, "enu": 0.0, "ext": 0.0}
    below = frac(dn)
    heated_below = bool(m.units_on(dn))
    return {"roof": roof, "ground": 0.0, "enu": 0.0 if heated_below else below, "ext": 1.0 - below}


def _sides0(m: Frame, un, tol=0.35):
    out = []
    for side, L, pos in (("y0", un.x1 - un.x0, ("y", un.y0)), ("y1", un.x1 - un.x0, ("y", un.y1)),
                         ("x0", un.y1 - un.y0, ("x", un.x0)), ("x1", un.y1 - un.y0, ("x", un.x1))):
        ext = _outside_len(m, side, un)
        if ext > 0.5:
            out.append((side, ext, "ext"))
            if ext > L - 0.5:
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
    from . import _aquec as aquecimento, _reh as reh
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
    roof = m.footprint - sum((c["x1"] - c["x0"]) * (c["y1"] - c["y0"]) for c in m.cores)
    pv = float((m.raw.get("mep") or {}).get("pv_kwp") or round(min(0.6 * len(m.units), 0.5 * roof / 5.5), 1))
    e_pv = pv * 1520.0 * 0.60
    used = set()
    for un in m.units:
        lv = m.level(un.level)
        ch = round(max(2.40, lv.height - m.slab_h(lv.id) - 0.12), 2)
        clear_h = clear_h or ch
        env, Lf, hp = [], 0.0, 0.0
        psi = []
        shade = _balcony_sides(m, un.level)
        for side, L, nat in _sides(m, un):
            if nat == "ext":
                o = ori[side]
                A = L * ch
                aw = round(GLAZ * A, 2)
                env.append({"tipo": "parede", "sol": "parede", "area_m2": round(A - aw, 2), "U": U_PT["parede"], "orientacao": o})
                env.append({"tipo": "envidracado", "sol": "envidracado", "area_m2": aw, "U": U_PT["envidracado"], "orientacao": o, "g": U_PT["g"],
                            "Fs": 0.60 if side in shade else 0.85, "Fs_v": 0.45 if side in shade else 0.80})
                n_v = max(1, round(aw / 3.6))
                lv_ = n_v * 4 * math.sqrt(aw / n_v)
                hp += 0.25 * L + 0.10 * lv_
                psi += [("Fachada / pavimento intermédio", 0.25, L), (f"Contorno dos vãos {o}", 0.10, lv_)]
                Lf += L
                used.update({"parede", "envidracado"})
            elif nat == "core":
                env.append({"tipo": "parede", "sol": "enu", "area_m2": round(max(L * ch - 2.0, 0.5), 2), "U": U_PT["enu"], "fronteira": "enu", "btr": 0.6})
                env.append({"tipo": "porta", "sol": "porta", "area_m2": 2.0, "U": U_PT["porta"], "fronteira": "enu", "btr": 0.6})
                used.update({"enu", "porta"})
        ap = round(un.area * 0.85, 1)              # área útil ≈ 85 % do retângulo bruto (paredes, courettes)
        ex = _exposure(m, un)
        if ex["roof"] > 0.02:
            env.append({"tipo": "cobertura", "sol": "cobertura", "area_m2": round(un.area * ex["roof"], 1), "U": U_PT["cobertura"], "orientacao": "H"})
            hp += 0.30 * Lf * ex["roof"]
            psi.append(("Fachada / cobertura", 0.30, Lf * ex["roof"]))
            used.add("cobertura")
        if ex["enu"] > 0.02:
            env.append({"tipo": "pavimento", "sol": "pavimento", "area_m2": round(un.area * ex["enu"], 1), "U": U_PT["pavimento"], "fronteira": "enu", "btr": 0.9})
            used.add("pavimento")
        if ex["ext"] > 0.02:
            env.append({"tipo": "pavimento", "sol": "pavimento", "area_m2": round(un.area * ex["ext"], 1), "U": U_PT["pavimento"], "orientacao": "H"})
            used.add("pavimento")
        if ex["ground"] > 0.02:
            env.append({"tipo": "pavimento", "sol": "pavimento_solo", "area_m2": round(un.area * ex["ground"], 1), "U": U_PT["pavimento_solo"], "fronteira": "solo"})
            used.add("pavimento_solo")
        fl_ = ex["enu"] + ex["ext"] + ex["ground"]
        if fl_ > 0.02:
            hp += 0.20 * Lf * fl_
            psi.append(("Fachada / pavimento sobre ENU, exterior ou solo", 0.20, Lf * fl_))
        if not any(e["tipo"] == "envidracado" for e in env):
            env.append({"tipo": "envidracado", "sol": "envidracado", "area_m2": round(0.15 * ap, 1), "U": U_PT["envidracado"], "orientacao": "S",
                        "g": U_PT["g"], "Fs": 0.7, "Fs_v": 0.6})
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
        rows = []
        for e in env:
            btr = float(e["btr"]) if e.get("btr") is not None else reh.BTR.get(e.get("fronteira") or "exterior", 1.0)
            rows.append({**e, "btr": btr, "H": btr * float(e["U"]) * float(e["area_m2"])})
        out.append({"id": un.id, "name": un.name, "level": un.level, "level_name": lv.name, "typology": un.typology or f"T{tip}",
                    "Ap": ap, "Nic": r["Nic"], "Ni": r["Ni"], "Nvc": r["Nvc"], "Nv": r["Nv"], "Ntc": r["Ntc"], "Nt": r["Nt"],
                    "RNt": r["RNt"], "classe": r["classe"], "phi_w": phi, "te": te, "ok": all(c.get("ok") is not False for c in r["controles"]),
                    "fails": [c["lib"] for c in r["controles"] if c.get("ok") is False], "x0": un.x0, "y0": un.y0, "x1": un.x1, "y1": un.y1,
                    "env": rows, "psi": psi, "hp": hp, "ch": ch, "tip": tip,
                    "calc": {k: r[k] for k in ("Htr", "Hve", "Qtr", "Qve", "Qint", "Qsol", "eta_i", "eta_v", "Qa", "ocupantes", "RenHab", "rph", "ntc_usos",
                                               "controles", "Htr_ref")},
                    "ren_kwh": p.get("renovavel_kwh", 0)})
    c = reh.clima(conc, nuts, None)
    hyp += [f"Clima : {c['nuts']} — zonas {c['zona_i']} / {c['zona_v']} (GD = {c['GD']:.0f} °C.dia).",
            f"Envolvente (soluções construtivas da secção 2, U calculado camada a camada — NP EN ISO 6946) : paredes U = {num(U_PT['parede'])}, "
            f"cobertura U = {num(U_PT['cobertura'])}, pavimento U = {num(U_PT['pavimento'])}, vãos Uw = {num(U_PT['envidracado'])} W/m²K, fator solar g = {num(U_PT['g'])}.",
            f"Vãos envidraçados : {int(GLAZ * 100)} % das fachadas (a substituir pelo mapa de vãos da arquitetura) ; sombreamento das varandas.",
            "Sistemas : bomba de calor ar-ar (COP 4), AQS por bomba de calor (COP 3), ventilação mecânica Rph 0,6 h⁻¹.",
            f"Renováveis : fotovoltaico coletivo {num(pv, 1)} kWp na cobertura (≈ {e_pv:.0f} kWh/ano autoconsumidos, repartidos pela área útil).",
            *te_h[:1],
            "Pré-certificado indicativo : não substitui o projeto de comportamento térmico nem o certificado SCE (Perito Qualificado ADENE)."]
    sols = {k: v for k, v in _SPT.items() if k in used}
    ri = c.get("ri", 0)
    for k, v in sols.items():
        t = {"parede": "parede", "enu": "parede", "cobertura": "cobertura", "pavimento": "pavimento", "pavimento_solo": "pavimento"}.get(k)
        if t:
            inner = k == "enu"
            v["Umax"] = (reh.UMAX_INT if inner else reh.UMAX)[t][ri]
            v["Uref"] = (reh.UREF_INT if inner else reh.UREF)[t][ri]
        elif k == "envidracado":
            v["Umax"], v["Uref"] = reh.UW_MAX[ri], reh.UREF["envidracado"][ri]
    return {"country": "PT", "units": out, "hyp": hyp, "climate": c, "clear_h": clear_h, "pv_kwp": pv, "e_pv": e_pv, "solutions": sols,
            "concelho": conc}


def _cp(m: Frame) -> str | None:
    import re
    txt = " ".join(str((m.project or {}).get(k) or "") for k in ("postal_code", "code_postal", "address", "municipality"))
    mm = re.search(r"\b(\d{5})\b", txt)
    return mm.group(1) if mm else None


def _fr(m: Frame) -> dict:
    ori = _orient(m)
    habs = _habitable(m)
    lowest, highest = habs[0], habs[-1]
    below = [l.id for l in m.levels].index(lowest) > 0
    te = float((m.raw.get("site") or {}).get("theta_base") or THETA_FR)
    out, parois, used = [], {}, set()
    clear_h = None

    # part vitrée : au moins 1/6 de la surface habitable (exigence de moyens RE2020), au plus 45 % des façades
    fac = sum(L * round(max(2.40, m.level(un.level).height - m.slab_h(un.level) - 0.12), 2)
              for un in m.units for _s, L, nat in _sides(m, un) if nat == "ext")
    sref0 = sum(un.area * 0.85 for un in m.units)
    glaz = max(GLAZ, min(0.45, 1.05 * sref0 / 6 / fac)) if fac > 0 else GLAZ

    def add(t, A, U, o=None, cote="exterieur"):
        k = (t, o, cote, round(U, 3))
        parois[k] = parois.get(k, 0.0) + A

    for un in m.units:
        lv = m.level(un.level)
        ch = round(max(2.40, lv.height - m.slab_h(lv.id) - 0.12), 2)
        clear_h = clear_h or ch
        rows, psi, Lf = [], [], 0.0
        for side, L, nat in _sides(m, un):
            A = L * ch
            if nat == "ext":
                o = ori[side]
                ab = glaz * A
                rows += [{"label": f"Mur extérieur {o}", "sol": "parede", "A": A - ab, "U": U_FR["mur"], "b": 1.0},
                         {"label": f"Baies {o}", "sol": "envidracado", "A": ab, "U": U_FR["baie"], "b": 1.0}]
                add("mur", A - ab, U_FR["mur"], o)
                add("fenetre", ab, U_FR["baie"], o)
                psi += [("Liaison façade / plancher intermédiaire", 0.30, L)]
                Lf += L
                used.update({"parede", "envidracado"})
            else:
                rows += [{"label": "Mur sur circulations", "sol": "enu", "A": max(A - 2.0, 0.5), "U": U_FR["lnc"], "b": 0.5},
                         {"label": "Porte palière", "sol": "porta", "A": 2.0, "U": U_FR["porte"], "b": 0.5}]
                add("mur", max(A - 2.0, 0.5), U_FR["lnc"], None, "local_non_chauffe")
                add("porte", 2.0, U_FR["porte"], None, "local_non_chauffe")
                used.update({"enu", "porta"})
        ex = _exposure(m, un)
        if ex["roof"] > 0.02:
            A = un.area * ex["roof"]
            rows.append({"label": "Toiture-terrasse", "sol": "cobertura", "A": A, "U": U_FR["toit"], "b": 1.0})
            add("toiture", A, U_FR["toit"])
            psi.append(("Liaison façade / toiture", 0.40, Lf * ex["roof"]))
            used.add("cobertura")
        for key, lab, sol, U, b, cote in (("enu", "Plancher bas sur parking / cave", "pavimento", U_FR["plancher"], 0.8, "garage"),
                                          ("ext", "Plancher bas sur extérieur", "pavimento", U_FR["plancher"], 1.0, "exterieur"),
                                          ("ground", "Plancher bas sur terre-plein", "pavimento_solo", U_FR["plancher_tp"], 0.45, "terre_plein")):
            if ex[key] > 0.02:
                A = un.area * ex[key]
                rows.append({"label": lab, "sol": sol, "A": A, "U": U, "b": b})
                add("plancher_bas", A, U, None, cote)
                used.add(sol)
        fl_ = ex["enu"] + ex["ext"] + ex["ground"]
        if fl_ > 0.02:
            psi.append(("Liaison façade / plancher bas", 0.40, Lf * fl_))
        for x in rows:
            x["H"] = x["A"] * x["U"] * x["b"]
        hp = sum(v * L for _n, v, L in psi)
        H = sum(x["H"] for x in rows) + hp
        ap = round(un.area * 0.85, 1)
        Hv = 0.34 * 0.6 * ap                       # VMC hygro B : débit conventionnel 0,6 m³/h par m² (sans récupération)
        phi = (H + Hv) * (19 - te)
        bch = (H + Hv) * 24 * 2200 / 1000 / ap     # besoin de chauffage indicatif kWh/m².an (DJU 2200)
        out.append({"id": un.id, "name": un.name, "level": un.level, "level_name": lv.name, "typology": un.typology, "Ap": ap,
                    "phi_w": phi, "te": te, "bch": bch, "classe": "—", "Nic": bch, "Ni": None, "Ntc": None, "Nt": None, "RNt": None,
                    "ok": True, "fails": [], "x0": un.x0, "y0": un.y0, "x1": un.x1, "y1": un.y1, "rows": rows, "psi": psi, "hp": hp,
                    "H": H, "Hv": Hv, "ch": ch})
    # étude RE2020 du bâtiment (moteur de pré-étude ConstruPilot)
    re = None
    try:
        from . import _re2020
        sref = sum(x["Ap"] for x in out)
        pl = [{"type": t, "surface_m2": round(A, 2), "U": U, "orientation": o, "cote": cote} for (t, o, cote, U), A in parois.items() if A > 0.05]
        params = {"type_batiment": "collectif", "sref_m2": round(sref, 1), "nb_logements": len(out), "code_postal": _cp(m),
                  "niveaux": len(habs), "hauteur_m": clear_h or 2.5, "structure": "beton_banche", "parois": pl,
                  "psi_total_w_k": round(sum(x["hp"] for x in out), 1), "annee_permis": __import__("datetime").date.today().year,
                  "chauffage": "pac_air_eau", "ecs": "cet", "ventilation": "vmc_sf_hygro_b", "_blocs_only": True}
        re = _re2020.note(params)
    except Exception as exc:  # noqa: BLE001 — la note RE2020 est un complément : son échec n'arrête pas l'étude
        re = {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    hyp = [f"Température extérieure de base {te:.0f} °C (à adapter à la zone et à l'altitude, NF EN 12831).",
           f"Parois (solutions constructives de la section 2, U calculé couche par couche — NF EN ISO 6946) : murs U = {num(U_FR['mur'])}, "
           f"toiture U = {num(U_FR['toit'])}, plancher bas U = {num(U_FR['plancher'])}, baies Uw = {num(U_FR['baie'])} W/m²K ; {int(round(glaz * 100))} % de baies en façade "
           "(au moins 1/6 de la surface habitable — à remplacer par le carnet de baies de l'architecte).",
           "Puissances de chauffage pour dimensionner les émetteurs ; l'étude RE2020 réglementaire (Th-BCE, ACV) reste à produire par le thermicien."]
    return {"country": "FR", "units": out, "hyp": hyp, "climate": None, "clear_h": clear_h, "re2020": re,
            "solutions": {k: v for k, v in _SFR.items() if k in used}}


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
