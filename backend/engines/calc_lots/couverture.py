"""Couverture : actions du vent (EN 1991-1-4 + AN FR / PT), neige (EN 1991-1-3 + AN) et pentes minimales des tuiles (DTU série 40.2).

Vent : qp(z) = [1 + 7·Iv(z)]·½·ρ·vm(z)², vm = cr·c0·vb, cr = kr·ln(z/z0), Iv = kl/[c0·ln(z/z0)] (kl de l'AN française, 1 au Portugal),
c0 = 1 (orographie non traitée), cdir = cseason = 1. Pressions extérieures cpe,10 (murs A–E ; toiture à deux versants F–J, θ = 0° et 90°),
pression nette avec cpi +0,2 / −0,3 ; soulèvement et arrachement des éléments de couverture à vérifier avec ces valeurs.
Neige : sk(A) région + altitude (AN FR) ou Cz·[1 + (H/500)²] (AN PT) ; s = μ1·Ce·Ct·sk, μ1 = 0,8 jusqu'à 30°, 0,8·(60−α)/30 jusqu'à 60°.
Tuiles (France) : pentes minimales par zone climatique 1/2/3, site protégé/normal/exposé, rampant, avec/sans écran (DTU 40.21, 40.22,
40.23, 40.24 — reproductions de fabricants) ; la pente réelle dépend du modèle (certificat NF / documentation du fabricant).
"""
from __future__ import annotations

import math

from . import climat

# ---------------------------------------------------------------------------------------------------------------------------------
VENT_REGION_FR = {**{d: 1 for d in "16 19 23 24 32 39 46 47 65 73 74 82 86 87".split()},
                  **{d: 2 for d in ("02 03 07 08 09 10 12 14 18 26 27 28 35 36 37 41 42 43 45 48 49 50 51 52 53 54 55 57 58 60 61 63 64 67 68 69 71 72 "
                                    "75 77 78 79 83 84 88 89 90 91 92 93 94 95").split()},
                  **{d: 3 for d in "13 22 29 34 56 66 85".split()}}
VENT_PARTAGE_FR = {**{d: (1, 2) for d in "01 04 05 06 15 21 25 31 33 38 40 70 81".split()}, **{d: (2, 3) for d in "11 30 44 59 62 76 80".split()},
                   "17": (1, 2, 3), "20": (3, 4)}
VB0_FR = {1: 22.0, 2: 24.0, 3: 26.0, 4: 28.0}
TERRAIN_FR = {"0": (0.005, 1.0), "II": (0.05, 2.0), "IIIa": (0.20, 5.0), "IIIb": (0.50, 9.0), "IV": (1.0, 15.0)}
TERRAIN_PT = {"I": (0.005, 1.0), "II": (0.05, 3.0), "III": (0.30, 8.0), "IV": (1.0, 15.0)}
MURS_CPE = {5: (-1.2, -0.8, -0.5, 0.8, -0.7), 1: (-1.2, -0.8, -0.5, 0.8, -0.5), 0.25: (-1.2, -0.8, -0.5, 0.7, -0.3)}
TOIT_0 = {5: ((-1.7, 0.0), (-1.2, 0.0), (-0.6, 0.0), (-0.6, 0.2), (-0.6, 0.2)), 15: ((-0.9, 0.2), (-0.8, 0.2), (-0.3, 0.2), (-0.4, 0.0), (-1.0, 0.0)),
          30: ((-0.5, 0.7), (-0.5, 0.7), (-0.2, 0.4), (-0.4, 0.0), (-0.5, 0.0)), 45: ((-0.0, 0.7), (-0.0, 0.7), (-0.0, 0.6), (-0.2, 0.0), (-0.3, 0.0))}
TOIT_90 = {5: (-1.6, -1.3, -0.7, -0.6), 15: (-1.3, -1.3, -0.6, -0.5), 30: (-1.1, -1.4, -0.8, -0.5), 45: (-1.1, -1.4, -0.9, -0.5)}
NEIGE_FR = {"A1": (0.45, None), "A2": (0.45, 1.00), "B1": (0.55, 1.00), "B2": (0.55, 1.35), "C1": (0.65, None), "C2": (0.65, 1.35), "D": (0.90, 1.80), "E": (1.40, None)}
NEIGE_PT = {"Z1": 0.30, "Z2": 0.20, "Z3": 0.10}
# DTU 40.21 : [site][zone] → (≤ 6,5 m, ≤ 9,5 m, ≤ 12 m)
TUILE_4021_ECRAN = {"protege": {1: (19, 22, 23), 2: (21, 24, 26), 3: (23, 26, 30)}, "normal": {1: (21, 24, 27), 2: (23, 27, 30), 3: (26, 31, 34)},
                    "expose": {1: (28, 30, 36), 2: (32, 33, 39), 3: (34, 37, 43)}}
TUILE_4021_SANS = {"protege": {1: (25, 28, 32), 2: (27, 32, 35), 3: (30, 36, 40)}, "normal": {1: (25, 28, 32), 2: (27, 32, 35), 3: (30, 36, 40)},
                   "expose": {1: (33, 35, 42), 2: (37, 39, 45), 3: (40, 43, 50)}}
TUILE_4022 = {"protege": {1: 24, 2: 27, 3: 30}, "normal": {1: 27, 2: 30, 3: 33}, "expose": {1: 30, 2: 33, 3: 35}}           # canal, sans écran
TUILE_4023 = {"sans": {"protege": {1: 70, 2: 70, 3: 80}, "normal": {1: 80, 2: 90, 3: 100}, "expose": {1: 100, 2: 110, 3: 115}},  # plates, recouvrement courant
              "ecran": {"protege": {1: 60, 2: 60, 3: 70}, "normal": {1: 70, 2: 80, 3: 85}, "expose": {1: 85, 2: 95, 3: 100}}}
TUILE_4024 = {"ecran": {"protege": 25, "normal": 25, "expose": 29}, "sans": {"protege": 29, "normal": 29, "expose": 35}}           # béton (fiche fabricant)


def _interp(table: dict, x: float):
    ks = sorted(table)
    x = max(ks[0], min(ks[-1], x))
    lo = max(k for k in ks if k <= x)
    hi = min(k for k in ks if k >= x)
    if lo == hi:
        return table[lo]
    t = (x - lo) / (hi - lo)
    a, b = table[lo], table[hi]
    if isinstance(a, tuple) and isinstance(a[0], tuple):
        return tuple(tuple(u + (v - u) * t for u, v in zip(p, q)) for p, q in zip(a, b))
    return tuple(u + (v - u) * t for u, v in zip(a, b))


def vent(p: dict) -> dict:
    pays = p.get("pays") or "pt"
    hyp, ctl = [], []
    if pays == "pt":
        zona = (p.get("zona_vento") or ("B" if p.get("ilhas") or p.get("faixa_costeira_5km") or float(p.get("altitude_m") or 0) > 600 else "A")).upper()
        vb0 = 30.0 if zona == "B" else 27.0
        cat = p.get("categorie_terrain") or "III"
        if cat not in TERRAIN_PT:
            raise ValueError("categoria de terreno PT: I, II, III ou IV")
        z0, zmin = TERRAIN_PT[cat]
        kl = 1.0
        lieu = f"zona {zona} (vb,0 = {vb0:g} m/s)"
    else:
        reg = p.get("region_vent")
        d = climat.departement(p.get("code_postal"))
        if reg is None:
            if d in VENT_REGION_FR:
                reg = VENT_REGION_FR[d]
            elif d in VENT_PARTAGE_FR:
                reg = max(VENT_PARTAGE_FR[d])
                hyp.append(f"département {d} partagé entre les régions {VENT_PARTAGE_FR[d]} (par canton) : région la plus défavorable ({reg}) retenue — préciser selon la commune")
            else:
                raise ValueError("région de vent (1 à 4) ou code postal métropolitain requis")
        reg = int(reg)
        vb0 = VB0_FR[reg]
        cat = p.get("categorie_terrain") or "IIIa"
        if cat not in TERRAIN_FR:
            raise ValueError("catégorie de terrain FR : 0, II, IIIa, IIIb ou IV")
        z0, zmin = TERRAIN_FR[cat]
        kl = 1 - 2e-4 * (math.log10(z0) + 3) ** 6
        lieu = f"région {reg} (vb,0 = {vb0:g} m/s)"
    h = float(p.get("hauteur_m") or 7.0)
    z = max(h, zmin)
    kr = 0.19 * (z0 / 0.05) ** 0.07
    cr = kr * math.log(z / z0)
    vm = cr * vb0
    iv = kl / math.log(z / z0)
    qb = 0.5 * 1.225 * vb0 ** 2
    qp = (1 + 7 * iv) * 0.5 * 1.225 * vm ** 2
    b = float(p.get("largeur_m") or 10)
    dprof = float(p.get("profondeur_m") or 8)
    hd = h / dprof
    murs = _interp(MURS_CPE, hd)
    alpha = float(p.get("pente_deg") or 30)
    t0 = _interp(TOIT_0, min(45, max(5, alpha)))
    t90 = _interp(TOIT_90, min(45, max(5, alpha)))
    e = min(b, 2 * h)
    cpi = (0.2, -0.3)
    w_toit_min = qp * (min(min(x[0] for x in t0), min(t90)) - cpi[0]) / 1000      # soulèvement maximal (kN/m²), zone F
    w_toit_courant = qp * (min(t0[2][0], t90[2]) - cpi[0]) / 1000                  # zone H
    w_mur_d = qp * (murs[3] - cpi[1]) / 1000
    w_mur_a = qp * (murs[0] - cpi[0]) / 1000
    ctl.append({"ref": "Soulèvement de la couverture (zones de rive F, cpe,10)", "exigence": "fixations / poids propre ≥ dépression nette (EN 1991-1-4 §7.2.5)",
                "valeur": f"{w_toit_min:.2f} kN/m² en rive (bande e/10 = {e / 10:.1f} m), {w_toit_courant:.2f} kN/m² en partie courante", "ok": None,
                "note": "à comparer au poids propre de la couverture et à la résistance des fixations (DTU série 40, règles NV / fabricant)"})
    if alpha < 5:
        hyp.append("pente < 5° : coefficients de toiture-terrasse non traités (valeurs à 5° utilisées)")
    hyp += [f"vent : {lieu}, catégorie de terrain {cat}, z = {z:g} m, c0 = 1 (pas d'effet de relief), cdir = cseason = 1",
            f"pression intérieure cpi = +0,2 / −0,3 (bâtiment sans face dominante)"]
    return {"pays": pays, "vb0": vb0, "qb_pa": qb, "categorie": cat, "z_m": z, "kr": kr, "cr": cr, "Iv": iv, "kl": kl, "qp_pa": qp, "ce": qp / qb,
            "murs_cpe10": dict(zip("ABCDE", murs)), "toiture_cpe10_0": dict(zip("FGHIJ", t0)), "toiture_cpe10_90": dict(zip("FGHI", t90)), "e_m": e,
            "pression_mur_D_kn_m2": w_mur_d, "depression_mur_A_kn_m2": w_mur_a, "depression_toiture_rive_kn_m2": w_toit_min,
            "depression_toiture_courante_kn_m2": w_toit_courant, "controles": ctl, "hypotheses": hyp}


def neige(p: dict) -> dict:
    pays = p.get("pays") or "pt"
    A = float(p.get("altitude_m") or 0)
    alpha = float(p.get("pente_deg") or 30)
    hyp = []
    if pays == "pt":
        zona = (p.get("zona_neve") or "Z3").upper()
        if not p.get("zona_neve"):
            hyp.append("zona de neve não indicada: Z3 (litoral e sul) retida — Z1 no nordeste montanhoso (Bragança, Vila Real, Guarda, Serra da Estrela)")
        if A < 200 and not p.get("forcar_neve"):
            sk, sad = 0.0, None
            hyp.append("neve não considerada abaixo de 200 m de altitude (prática corrente, AN a confirmar)")
        else:
            sk, sad = NEIGE_PT[zona] * (1 + (A / 500) ** 2), None
        reg = zona
    else:
        reg = (p.get("region_neige") or "A2").upper()
        if not p.get("region_neige"):
            hyp.append("région de neige non fournie : A2 retenue — vérifier sur la carte de l'AN (NF EN 1991-1-3/NA)")
        if reg not in NEIGE_FR:
            raise ValueError("région de neige : A1, A2, B1, B2, C1, C2, D ou E")
        sk200, sad = NEIGE_FR[reg]
        if A <= 200:
            ds = 0.0
        elif reg != "E":
            ds = A / 1000 - 0.20 if A <= 500 else 1.5 * A / 1000 - 0.45 if A <= 1000 else 3.5 * A / 1000 - 2.45
        else:
            ds = 1.5 * A / 1000 - 0.30 if A <= 500 else 3.5 * A / 1000 - 1.30 if A <= 1000 else 7 * A / 1000 - 4.80
        sk = sk200 + ds
        if A > 2000:
            hyp.append("altitude > 2 000 m : hors domaine de l'AN, étude spécifique")
    mu1 = 0.8 if alpha <= 30 else 0.8 * (60 - alpha) / 30 if alpha < 60 else 0.0
    s = mu1 * sk
    if pays == "fr" and alpha < 1.7:       # pente < 3 %
        s += 0.2
        hyp.append("toiture de pente < 3 % : majoration de 0,2 kN/m² (AN française)")
    return {"pays": pays, "region": reg, "sk_kn_m2": sk, "mu1": mu1, "s_kn_m2": s, "sad_kn_m2": sad, "hypotheses": hyp}


def zone_tuile(p: dict) -> int:
    A = float(p.get("altitude_m") or 0)
    za = 1 if A < 200 else 2 if A < 500 else 3
    zg = 3 if p.get("cote_manche_atlantique_nord_20km") else 2 if p.get("cote_atlantique_sud_ou_20_40km") else 1
    return max(za, zg, int(p.get("zone_climatique") or 1))


def pente_tuiles(p: dict) -> dict:
    typ = p.get("type_tuile") or "emboitement"
    site = p.get("site") or "normal"
    if site not in ("protege", "normal", "expose"):
        raise ValueError("site : protege, normal ou expose")
    zone = zone_tuile(p)
    ecran = bool(p.get("ecran_sous_toiture"))
    L = float(p.get("rampant_m") or 6.0)
    hyp = []
    if float(p.get("altitude_m") or 0) > 900:
        raise ValueError("altitude > 900 m : climat de montagne hors DTU (règles « montagne » / étude)")
    if typ == "emboitement":
        if L > 12:
            raise ValueError("rampant > 12 m : étude particulière (DTU 40.21)")
        i = 0 if L <= 6.5 else 1 if L <= 9.5 else 2
        pmin = (TUILE_4021_ECRAN if ecran else TUILE_4021_SANS)[site][zone][i]
        ref = "NF DTU 40.21 (tuiles à emboîtement / à glissement à relief)"
        hyp.append("tableau du DTU 40.21 complété par les règles professionnelles « faible pente » (reproduit par les fabricants) : la pente minimale du modèle (certificat NF) prévaut")
    elif typ == "canal":
        pmin = TUILE_4022[site][zone]
        ref = "NF DTU 40.22 (tuiles canal, sans écran)"
        if ecran:
            hyp.append("tuiles canal avec écran / sur plaques support : pentes réduites selon l'Avis Technique du système (valeur sans écran conservée)")
    elif typ == "plate":
        pmin = TUILE_4023["ecran" if ecran else "sans"][site][zone]
        ref = "NF DTU 40.23 (tuiles plates, recouvrement courant)"
        if L > 8:
            hyp.append("rampant > 8 m en tuiles plates : étude particulière")
    elif typ == "beton":
        pmin = TUILE_4024["ecran" if ecran else "sans"][site]
        ref = "NF DTU 40.24 (tuiles béton, fiche fabricant, sans modulation par zone)"
    else:
        raise ValueError("type de tuile : emboitement, canal, plate ou beton")
    pente = p.get("pente_pct")
    if pente is None and p.get("pente_deg") is not None:
        pente = math.tan(math.radians(float(p["pente_deg"]))) * 100
    ctl = [{"ref": ref, "exigence": f"pente ≥ {pmin:g} % (zone {zone}, site {site}, rampant {L:g} m, {'avec' if ecran else 'sans'} écran)",
            "valeur": f"{float(pente):.0f} %" if pente is not None else "pente non fournie", "ok": (float(pente) >= pmin - 1e-9) if pente is not None else None,
            "note": ("ajouter un écran sous-toiture homologué ou augmenter la pente" if pente is not None and float(pente) < pmin and not ecran else None)}]
    return {"type": typ, "zone": zone, "site": site, "ecran": ecran, "pente_min_pct": pmin, "pente_min_deg": math.degrees(math.atan(pmin / 100)),
            "controles": ctl, "hypotheses": hyp}


def note(params: dict) -> dict:
    from . import notes
    W = notes.W
    blocs, hyp, out, n = [("p", "Valeurs indicatives (Eurocodes et DTU reproduits par des sources secondaires) — vérifier la norme et la documentation du fabricant.")], [], {}, 1
    if params.get("vent"):
        r = vent(params["vent"])
        out["vent"] = r
        rows = [["qb / qp(z)", f"{r['qb_pa']:.0f} Pa / {r['qp_pa']:.0f} Pa (ce {r['ce']:.2f}, z {r['z_m']:g} m, cat. {r['categorie']})"],
                ["Murs cpe,10 A/B/C/D/E", " / ".join(f"{v:+.2f}" for v in r["murs_cpe10"].values())],
                ["Toiture θ=0° F/G/H/I/J (dépression ; pression)", " / ".join(f"{a:+.2f};{b:+.2f}" for a, b in r["toiture_cpe10_0"].values())],
                ["Toiture θ=90° F/G/H/I", " / ".join(f"{v:+.2f}" for v in r["toiture_cpe10_90"].values())],
                ["Pression nette mur au vent (D)", f"{r['pression_mur_D_kn_m2']:.2f} kN/m²"],
                ["Dépression nette toiture rive / courante", f"{r['depression_toiture_rive_kn_m2']:.2f} / {r['depression_toiture_courante_kn_m2']:.2f} kN/m²"]]
        blocs += [("h2", f"{n}. Vent"), ("table", ["Grandeur", "Valeur"], rows, [70 * W, 105 * W]), ("controls", r["controles"])]
        hyp += r["hypotheses"]; n += 1
    if params.get("neige"):
        r = neige(params["neige"])
        out["neige"] = r
        blocs += [("h2", f"{n}. Neige"), ("p", f"Région {r['region']} : sk = {r['sk_kn_m2']:.2f} kN/m², μ1 = {r['mu1']:.2f} → s = {r['s_kn_m2']:.2f} kN/m²"
                                                 + (f" ; neige accidentelle sAd = {r['sad_kn_m2']:.2f} kN/m²" if r.get("sad_kn_m2") else ""))]
        hyp += r["hypotheses"]; n += 1
    if params.get("tuiles"):
        r = pente_tuiles(params["tuiles"])
        out["tuiles"] = r
        blocs += [("h2", f"{n}. Pente minimale de couverture"), ("controls", r["controles"])]
        hyp += r["hypotheses"]
    if not out:
        raise ValueError("renseigner au moins : vent, neige ou tuiles")
    titre = "Nota de cobertura — " + ", ".join({"vent": "vento", "neige": "neve", "tuiles": "telhas (regras francesas DTU)"}[k] for k in ("vent", "neige", "tuiles") if k in out)
    pdf, png = notes.pdf(titre, "Eurocódigo 1 (vento, neve) — NP EN 1991-1-3/1-4 e Anexos Nacionais", blocs, hyp)
    return {**out, "titre": titre, "pdf": pdf, "png": png}
