"""Charpente traditionnelle sur pignons mitoyens (NF EN 1995-1-1 + AN, NF DTU 31.1).

Logique : le comble est habité (chambres sous rampants) → pas de fermettes en W qui
encombrent le volume. Les deux murs mitoyens sont des pignons maçonnés : on y pose
des pannes (faîtière + intermédiaires) qui portent les chevrons. Les façades ne
reçoivent qu'une sablière.
"""
from __future__ import annotations

import math

from .model import Model

GL24H = {"fm": 24.0, "E": 11500.0, "rho": 4.2}      # MPa, MPa, kN/m³
C24 = {"fm": 24.0, "E": 11000.0, "rho": 4.2}
KMOD_SHORT, GAMMA_M_GL, GAMMA_M_C = 0.90, 1.25, 1.30
KDEF = 0.60


def _section(L: float, qG: float, qS: float, mat: dict, gm: float, sizes, limit=200.0):
    for b, h in sizes:
        self_w = mat["rho"] * b * h / 1e6
        G = qG + self_w
        qu = 1.35 * G + 1.5 * qS
        M = qu * L ** 2 / 8
        W = b * h ** 2 / 6
        sig = M * 1e6 / W
        fmd = KMOD_SHORT * mat["fm"] / gm
        I = b * h ** 3 / 12
        w_inst = 5 * (G + qS) * (L * 1000) ** 4 / (384 * mat["E"] * I)
        w_fin = w_inst + KDEF * 5 * G * (L * 1000) ** 4 / (384 * mat["E"] * I)
        if sig <= 0.9 * fmd and w_fin <= 0.9 * L * 1000 / limit:
            return {"b": b, "h": h, "M_Ed": round(M, 2), "sigma": round(sig, 1), "f_md": round(fmd, 1),
                    "ratio_M": round(sig / fmd, 2), "w_fin_mm": round(w_fin, 1), "w_lim_mm": round(L * 1000 / limit, 1),
                    "label": f"{b} × {h}"}
    return None


def _f(v: float, n: int = 2) -> str:
    return f"{v:.{n}f}".replace(".", ",")


def dormer_geometry(m: Model, d: dict) -> dict:
    """Géométrie d'une lucarne jacobine : front dans le plan de la façade, jouées jusqu'à la rencontre avec le versant."""
    roof = m.roof
    sd = m.side(d["side"])
    at0 = sd["pos"] < m.L / 2
    run = m.roof_run if at0 else m.L - m.roof_run
    tan_a = (roof["ridge_level"] - roof["eaves_level"]) / max(run, 0.1)
    w = d["y1"] - d["y0"]
    he = d.get("front_h", d.get("window_h", 1.10) + 0.25)            # hauteur du front (égout de la lucarne) au-dessus de l'arase
    hr = d.get("ridge_h", he + w / 2 * math.tan(math.radians(d.get("pitch_deg", 33.7))))
    de, dr = he / tan_a, hr / tan_a                                     # profondeur des jouées / du faîtage de lucarne
    return {"id": d["id"], "side": d["side"], "x_face": 0.0 if at0 else m.L, "dir": 1 if at0 else -1, "y0": d["y0"], "y1": d["y1"],
            "w": round(w, 3), "he": round(he, 3), "hr": round(hr, 3), "de": round(de, 3), "dr": round(dr, 3), "run": run,
            "tan_a": tan_a, "window_w": d.get("window_w", w - 0.40), "window_h": d.get("window_h", 1.10)}


def compute(m: Model, ld: dict) -> dict:
    roof = m.roof
    alpha = math.radians(ld["roof_pitch_deg"])
    half = m.roof_run                                    # projection d'un versant (égout → faîtage)
    span_c = m.gable_length                              # portée de la toiture (perpendiculaire au faîtage)
    n_inter = 2 if half > 3.2 else 1
    spacing_h = half / (n_inter + 1)                    # espacement horizontal des pannes
    spacing_r = spacing_h / math.cos(alpha)              # le long du rampant
    trusses = m.trusses
    if trusses:                                          # pannes de pignon à ferme (travées ≈ égales)
        L_panne = m.ridge_length / (len(trusses) + 1) + 0.15
    else:
        L_panne = m.ridge_length - 2 * 0.20 + 0.15       # entre nus des pignons + appuis
    gs, s = ld["g_roof_slope"], ld["snow_s"]
    qG = gs * spacing_r                                  # kN/m (vertical, par m de panne)
    qS = s * spacing_h
    gl_sizes = [(b, h) for h in range(240, 481, 40) for b in (100, 115, 140, 160, 185) if h / b <= 3.2]
    gl_sizes.sort(key=lambda bh: bh[0] * bh[1])
    panne = _section(L_panne, qG, qS, GL24H, GAMMA_M_GL, gl_sizes)
    # chevrons C24 continus sur pannes (calcul en travée isostatique, sécuritaire), entraxe 0,60
    ent = 0.60
    qGc = gs * ent * math.cos(alpha)
    qSc = s * ent * math.cos(alpha) ** 2
    ch_sizes = [(63, 150), (63, 175), (75, 175), (75, 200)]
    chevron = _section(spacing_r, qGc, qSc, C24, GAMMA_M_C, ch_sizes, limit=200.0)
    xs = []
    for k in range(1, n_inter + 1):
        xs += [round(k * spacing_h, 3), round(span_c - k * spacing_h, 3)]
    pannes = [{"id": "PF", "role": "faîtière", "x": round(half, 3), "z": roof["ridge_level"] - 0.25}] + \
             [{"id": f"PI{i+1}", "role": "intermédiaire", "x": x,
               "z": round(roof["eaves_level"] + (x if x < half else span_c - x) * math.tan(alpha) - 0.20, 3)} for i, x in enumerate(sorted(xs))]
    n_chev = 2 * (math.floor((m.ridge_length - 0.40) / ent) + 1)
    # fermes intermédiaires (pannes trop longues de pignon à pignon) : charge apportée par les pannes
    q_roof = (ld["g_roof_plan"] + ld["snow_s"]) * (span_c + 0.60)
    qu_roof = (1.35 * ld["g_roof_plan"] + 1.5 * ld["snow_s"]) * (span_c + 0.60)
    span_t = m.ridge_length / (len(trusses) + 1) if trusses else 0.0
    ferme_list = [{"id": f"F{i + 1}", "pos": t, "load_ELS_kN": round(q_roof * span_t, 1), "load_ELU_kN": round(qu_roof * span_t, 1),
                   "support_kN_ELU": round(qu_roof * span_t / 2, 1)} for i, t in enumerate(trusses)]
    dormers = []
    for d in (roof.get("dormers") or []) if not m.ridge_along_x else []:
        w = d["y1"] - d["y0"]
        g = dormer_geometry(m, d)
        L_up = max(g["run"] - g["dr"], 0.3) / math.cos(alpha)           # rampant au-dessus de la lucarne porté par le chevêtre
        chev = _section(w + 0.10, gs * L_up / 2, s * L_up * math.cos(alpha) / 2, C24, GAMMA_M_C,
                        [(150, 200), (150, 225), (150, 250), (180, 250)], limit=300.0)
        bh = panne["h"] / 1000 if panne else 0.36
        crossing = [p for p in [{"id": "PF", "x": half}] + [{"id": f"PI{i+1}", "x": x} for i, x in enumerate(sorted(
            [round(k * spacing_h, 3) for k in range(1, n_inter + 1)] + [round(m.L - k * spacing_h, 3) for k in range(1, n_inter + 1)]))]
                    if abs(p["x"] - g["x_face"]) < g["dr"]]
        notes = []
        for p in crossing:
            zp = roof["eaves_level"] + abs(p["x"] - g["x_face"]) * g["tan_a"] - 0.20 - bh / 2
            free = zp - m.levels[-1].floor_top
            notes.append(f"panne {p['id']} traverse la lucarne (sous-face {_f(zp)}, hauteur libre {_f(free)} m) : "
                         + ("conservée, habillée" if free >= 1.90 else "à chevêtrer ou à relever — hauteur libre < 1,90 m"))
        dormers.append({"id": d["id"], "side": d["side"], "width": w, "y0": d["y0"], "y1": d["y1"], "geometry": g,
                        "chevetre_section": chev, "upper_rafter": round(L_up, 2), "pannes": notes,
                        "chevetre": (f"Chevêtre haut C24 2 × {chev['b'] // 2} × {chev['h']}, portée {_f(w + 0.10)} : "
                                     f"M_Ed = {chev['M_Ed']} kN.m, σ = {chev['sigma']} ≤ {chev['f_md']} MPa, flèche {chev['w_fin_mm']} ≤ {chev['w_lim_mm']} mm ; "
                                     "chevrons de rive doublés de part et d'autre") if chev else "Chevêtre : section à justifier par le charpentier",
                        "frame": f"Lucarne jacobine {w:.2f} m : jambages ossature bois 45 × 145, linteau 75 × 200, toiture 2 pans ; "
                                 f"le front repose sur l'arase de façade (chaînage {_f(roof['eaves_level'])})"})
    mit = any(m.side(g)["type"] == "mitoyen" for g in roof.get("gables", []))
    attic = roof.get("habitable_attic", "omble" in m.levels[-1].name and m.levels[-1].floor_top >= roof["eaves_level"] - 1.5)
    attic_floor = bool(roof.get("attic_floor"))
    sec_f = "2 × 75 × 225" if span_c <= 8.5 else "2 × 75 × 250"
    return {
        "type": ("Charpente traditionnelle à pannes sur pignons mitoyens maçonnés" if mit else "Charpente traditionnelle à pannes sur pignons maçonnés")
                + (f" et {len(trusses)} ferme{'s' if len(trusses) > 1 else ''} intermédiaire{'s' if len(trusses) > 1 else ''}" if trusses else ""),
        "ridge_along_x": m.ridge_along_x, "run": round(half, 3), "span": round(span_c, 3),
        "pitch_deg": ld["roof_pitch_deg"], "rafter_length": ld["rafter_length"],
        "panne_span": round(L_panne, 2), "panne_spacing_slope": round(spacing_r, 2),
        "panne_section": panne, "pannes": pannes, "panne_material": "Lamellé-collé GL24h, classe de service 1, traitement classe 2",
        "chevron_section": chevron, "chevron_spacing": ent, "chevron_count": n_chev,
        "sabliere": f"Sablières 75 × 200 C24 sur les deux arases de façade ({_f(roof['eaves_level'])}), fixées par feuillards/tiges scellées tous les 1,20 m",
        "ceiling": (f"Plafond du comble à {_f(roof['ceiling_level'])} : entraits retroussés (moises 2 × 38 × 175) un couple de chevrons sur deux + suspentes" if attic else
                    "Combles aménageables : plancher porté en poutrelles-hourdis (voir planche des planchers) — aucun entrait ni fermette dans le volume, "
                    "charpente à pannes laissant le comble libre" if attic_floor else
                    f"Plafond du dernier niveau à {_f(roof['ceiling_level'])} : solives de plafond 63 × 175 C24 e=0,60 accrochées aux pannes et aux sablières (comble perdu isolé)"),
        "trusses": ferme_list,
        "truss_text": (f"{len(trusses)} ferme{'s' if len(trusses) > 1 else ''} intermédiaire{'s' if len(trusses) > 1 else ''} à entrait retroussé "
                       f"(arbalétriers GL24h {sec_f}, entrait retroussé moisé 2 × 63 × 200 à 2,00 m au-dessus du plancher des combles, poinçon 150 × 150) "
                       f"aux abscisses {', '.join(_f(t) for t in trusses)} : pannes de {_f(span_t)} m entre appuis ; "
                       f"charge apportée par ferme ≈ {ferme_list[0]['load_ELU_kN']} kN à l'ELU, {ferme_list[0]['support_kN_ELU']} kN par appui sur les murs d'égout "
                       "(sabots + platines, sommier BA sous chaque pied)") if trusses else "",
        "bearings": "Appuis des pannes : sommiers BA 0,20 × 0,20 × 0,40 dans les pignons, platines + ancrages ; profondeur d'appui ≥ 0,15 m ; "
                    + ("désolidarisation vis-à-vis du mur voisin (pignon mitoyen) par feutre bitumineux" if mit else "calage sur feutre bitumineux"),
        "bracing": "Contreventement des versants par bandes de feuillard en croix sur chevrons (ou panneaux OSB 12 mm) — à justifier au vent par le charpentier",
        "covering": f"Tuile mécanique terre cuite sur liteaux 27 × 38 et contre-liteaux, écran HPV ; pente {_f(ld['roof_pitch_deg'], 1)}° compatible (DTU 40.21)",
        "insulation": "Isolation sous rampants R ≥ 8 (laine minérale 140 entre chevrons + 160 sous chevrons), pare-vapeur, plaque de plâtre" if attic else
                      "Isolation sur le plancher des combles aménageables (laine soufflée ou panneaux) selon l'étude thermique ; rampants isolables lors de l'aménagement" if attic_floor else
                      "Isolation du plancher de comble perdu R ≥ 7 (laine soufflée 300 mm), pare-vapeur, plaque de plâtre",
        "dormers": dormers,
        "checks": [
            f"Pannes : M_Ed = {panne['M_Ed']} kN.m, σ = {panne['sigma']} MPa ≤ f_m,d = {panne['f_md']} MPa ; flèche finale {panne['w_fin_mm']} mm ≤ L/200 = {panne['w_lim_mm']} mm" if panne else "Pannes : aucune section standard ne passe — revoir",
            f"Chevrons {chevron['label']} : σ = {chevron['sigma']} MPa ≤ {chevron['f_md']} MPa ; flèche {chevron['w_fin_mm']} mm ≤ {chevron['w_lim_mm']} mm" if chevron else "Chevrons : revoir",
        ] + ([f"Fermes : {len(trusses)} intermédiaire(s), portée des pannes {_f(span_t)} m — note de fabrication du charpentier"] if trusses else [])
          + [f"Lucarne {d['id']} : {d['chevetre']}" for d in dormers[:1]] + sorted({n for d in dormers for n in d["pannes"]}),
    }
