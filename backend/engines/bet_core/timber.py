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


def compute(m: Model, ld: dict) -> dict:
    roof = m.roof
    alpha = math.radians(ld["roof_pitch_deg"])
    half = m.L / 2
    n_inter = 2
    spacing_h = half / (n_inter + 1)                    # espacement horizontal des pannes
    spacing_r = spacing_h / math.cos(alpha)              # le long du rampant
    L_panne = m.W - 2 * 0.20 + 0.15                      # entre nus des pignons + appuis
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
        xs += [round(k * spacing_h, 3), round(m.L - k * spacing_h, 3)]
    pannes = [{"id": "PF", "role": "faîtière", "x": round(half, 3), "z": roof["ridge_level"] - 0.25}] + \
             [{"id": f"PI{i+1}", "role": "intermédiaire", "x": x,
               "z": round(roof["eaves_level"] + (x if x < half else m.L - x) * math.tan(alpha) - 0.20, 3)} for i, x in enumerate(sorted(xs))]
    n_chev = 2 * (math.floor((m.W - 0.40) / ent) + 1)
    dormers = []
    for d in roof["dormers"]:
        w = d["y1"] - d["y0"]
        dormers.append({"id": d["id"], "side": d["side"], "width": w, "y0": d["y0"], "y1": d["y1"],
                        "chevetre": "Chevêtre 2 × 75 × 200 C24 + chevrons de rive doublés de part et d'autre",
                        "frame": f"Lucarne jacobine {w:.2f} m : jambages ossature bois 45 × 145, linteau 75 × 200, toiture 2 pans ; "
                                 f"le front repose sur l'arase de façade (chaînage {_f(roof['eaves_level'])})"})
    mit = any(m.side(g)["type"] == "mitoyen" for g in roof.get("gables", []))
    attic = roof.get("habitable_attic", "omble" in m.levels[-1].name and m.levels[-1].floor_top >= roof["eaves_level"] - 1.5)
    return {
        "type": "Charpente traditionnelle à pannes sur pignons mitoyens maçonnés" if mit else "Charpente traditionnelle à pannes sur pignons maçonnés",
        "pitch_deg": ld["roof_pitch_deg"], "rafter_length": ld["rafter_length"],
        "panne_span": round(L_panne, 2), "panne_spacing_slope": round(spacing_r, 2),
        "panne_section": panne, "pannes": pannes, "panne_material": "Lamellé-collé GL24h, classe de service 1, traitement classe 2",
        "chevron_section": chevron, "chevron_spacing": ent, "chevron_count": n_chev,
        "sabliere": f"Sablières 75 × 200 C24 sur les deux arases de façade ({_f(roof['eaves_level'])}), fixées par feuillards/tiges scellées tous les 1,20 m",
        "ceiling": (f"Plafond du comble à {_f(roof['ceiling_level'])} : entraits retroussés (moises 2 × 38 × 175) un couple de chevrons sur deux + suspentes" if attic else
                    f"Plafond du dernier niveau à {_f(roof['ceiling_level'])} : solives de plafond 63 × 175 C24 e=0,60 accrochées aux pannes et aux sablières (comble perdu isolé)"),
        "bearings": "Appuis des pannes : sommiers BA 0,20 × 0,20 × 0,40 dans les pignons, platines + ancrages ; profondeur d'appui ≥ 0,15 m ; "
                    + ("désolidarisation vis-à-vis du mur voisin (pignon mitoyen) par feutre bitumineux" if mit else "calage sur feutre bitumineux"),
        "bracing": "Contreventement des versants par bandes de feuillard en croix sur chevrons (ou panneaux OSB 12 mm) — à justifier au vent par le charpentier",
        "covering": f"Tuile mécanique terre cuite sur liteaux 27 × 38 et contre-liteaux, écran HPV ; pente {_f(ld['roof_pitch_deg'], 1)}° compatible (DTU 40.21)",
        "insulation": "Isolation sous rampants R ≥ 8 (laine minérale 140 entre chevrons + 160 sous chevrons), pare-vapeur, plaque de plâtre" if attic else
                      "Isolation du plancher de comble perdu R ≥ 7 (laine soufflée 300 mm), pare-vapeur, plaque de plâtre",
        "dormers": dormers,
        "checks": [
            f"Pannes : M_Ed = {panne['M_Ed']} kN.m, σ = {panne['sigma']} MPa ≤ f_m,d = {panne['f_md']} MPa ; flèche finale {panne['w_fin_mm']} mm ≤ L/200 = {panne['w_lim_mm']} mm" if panne else "Pannes : aucune section standard ne passe — revoir",
            f"Chevrons {chevron['label']} : σ = {chevron['sigma']} MPa ≤ {chevron['f_md']} MPa ; flèche {chevron['w_fin_mm']} mm ≤ {chevron['w_lim_mm']} mm" if chevron else "Chevrons : revoir",
        ],
    }
