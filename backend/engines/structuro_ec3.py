"""Lot 4 — EN 1993-1-1 : vérification de profils acier (flexion, cisaillement, déversement, N+M).

Méthodologie PUBLIQUE EN 1993-1-1 §6.2/§6.3. Catalogue de profils EN 10365 (IPE/HEA/HEB/UPN)
avec propriétés vérifiées et classe de section automatique (Table 5.2) — voir
`engines/structuro_profiles.py`. γM0=γM1=1.0 (AN FR), éditables.

Zéro hallucination : déversement calculé seulement si Mcr fourni/auto ; flexion composée des
poteaux par la MÉTHODE RÉGLEMENTAIRE §6.3.3 (méthode 2, Annexe B : facteurs kyy/kzy,
équations 6.61 & 6.62). Rapports Ed/Rd indicatifs, jamais un verdict réglementaire.
"""
from __future__ import annotations

import math

from engines.structuro_check import DISCLAIMER, util_status
from engines import structuro_profiles as profiles

VERSION = "ec3-member-0.2.0"
SOURCE = "EN 1993-1-1 §6.2 (section), §6.3.2 (déversement) & §6.3.3 méthode 2 Annexe B (N+M) — méthodologie publique, AN FR — à vérifier"

GRADES = profiles.GRADES
PROFILE_DATA = profiles.PROFILE_DATA
PROFILES = profiles._legacy_subset()  # rétrocompat (sous-ensemble de clés)
CURVES = {"a0": 0.13, "a": 0.21, "b": 0.34, "c": 0.49, "d": 0.76}  # αLT / α flambement
COL_CURVES = CURVES
ES_MPA = 210000.0
GS_MPA = 81000.0
C1_PRESETS = [{"label": "Moment uniforme", "value": 1.0},
              {"label": "Charge répartie (appuis simples)", "value": 1.12},
              {"label": "Charge ponctuelle centrée", "value": 1.35}]
# Facteurs de moment uniforme équivalent Cmy/CmLT (Annexe B, Table B.3) — presets usuels, éditables.
CM_PRESETS = [{"label": "Moment uniforme (ψ=1)", "value": 1.0},
              {"label": "Moment linéaire ψ=0", "value": 0.6},
              {"label": "Charge répartie (M mi-travée)", "value": 0.95},
              {"label": "Charge ponctuelle centrée", "value": 0.9}]


def mcr_elastic(iz_cm4: float, it_cm4: float, iw_cm6: float, L_m: float, c1: float = 1.0) -> float:
    """Moment critique élastique de déversement (poutre bi-appuyée, charge sans excentricité)."""
    Iz, It, Iw, L = iz_cm4 * 1e4, it_cm4 * 1e4, iw_cm6 * 1e6, L_m * 1000.0
    term1 = math.pi ** 2 * ES_MPA * Iz / (L * L)
    root = math.sqrt(Iw / Iz + (L * L) * GS_MPA * It / (math.pi ** 2 * ES_MPA * Iz))
    return c1 * term1 * root / 1e6


def _chi(lam: float, alpha: float) -> float:
    phi = 0.5 * (1 + alpha * (lam - 0.2) + lam * lam)
    return min(1.0 / (phi + math.sqrt(max(phi * phi - lam * lam, 0.0))), 1.0) if phi > 0 else 1.0


def verify_column(ned_kn: float, med_knm: float = 0.0, *, A_cm2: float, iy_cm4: float, iz_cm4: float,
                  it_cm4: float, iw_cm6: float, wpl_y_cm3: float, wel_y_cm3: float, b_fl_mm: float,
                  h_mm: float, tf_mm: float, fy_mpa: float, lcr_y_m: float, lcr_z_m: float | None = None,
                  section_class: int = 1, gamma_m0: float = 1.0, gamma_m1: float = 1.0,
                  curve_y: str = "b", curve_z: str = "c", curve_lt: str = "a",
                  cmy: float = 0.9, cm_lt: float = 0.9, lateral_restraint: bool = False,
                  mono: bool = False) -> dict:
    """Poteau acier : flambement §6.3.1 (deux axes) + flexion composée N+M **méthode 2 Annexe B** (§6.3.3)."""
    lcr_z_m = lcr_z_m if lcr_z_m else lcr_y_m
    A = A_cm2 * 100.0
    W = (wpl_y_cm3 if section_class in (1, 2) else wel_y_cm3) * 1000.0
    NRk_kn = A * fy_mpa / 1000.0
    MyRk_knm = W * fy_mpa / 1e6
    Npl_kn = NRk_kn / gamma_m0
    Mc_knm = MyRk_knm / gamma_m0

    def chi_axis(I_cm4, lcr_m, curve):
        I = I_cm4 * 1e4
        Ncr = math.pi ** 2 * ES_MPA * I / ((lcr_m * 1000.0) ** 2) / 1000.0  # kN
        lam = math.sqrt(A * fy_mpa / (Ncr * 1000.0)) if Ncr > 0 else 0.0
        return _chi(lam, COL_CURVES.get(curve, 0.49)), lam, Ncr

    chi_y, lam_y, Ncr_y = chi_axis(iy_cm4, lcr_y_m, curve_y)
    chi_z, lam_z, Ncr_z = chi_axis(iz_cm4, lcr_z_m, curve_z)
    Nb_y = chi_y * NRk_kn / gamma_m1
    Nb_z = chi_z * NRk_kn / gamma_m1
    Nb_min = min(Nb_y, Nb_z)
    warnings = []
    if section_class == 4:
        warnings.append("Section de classe 4 : propriétés efficaces (voilement local) non calculées "
                        "— résistance surestimée, à vérifier.")
    out = {"version": VERSION, "ned_kn": round(ned_kn, 2), "npl_rd_kn": round(Npl_kn, 2),
           "ncr_kn": round(min(Ncr_y, Ncr_z), 2), "section_class": section_class,
           "lambda_bar": round(max(lam_y, lam_z), 3), "lambda_y": round(lam_y, 3), "lambda_z": round(lam_z, 3),
           "chi": round(min(chi_y, chi_z), 3), "chi_y": round(chi_y, 3), "chi_z": round(chi_z, 3),
           "nb_rd_kn": round(Nb_min, 2), "nb_rd_y_kn": round(Nb_y, 2), "nb_rd_z_kn": round(Nb_z, 2),
           "lcr_y_m": round(lcr_y_m, 3), "lcr_z_m": round(lcr_z_m, 3), "lcr_m": round(lcr_y_m, 3),
           "curve_y": curve_y, "curve_z": curve_z, "curve": curve_z, "mc_rd_knm": round(Mc_knm, 2),
           "buckling": {"utilisation": util_status(ned_kn / Nb_min if Nb_min > 0 else None),
                        "formula": "Nb,Rd=χ·A·fy/γM1 (min des axes y,z) ; λ̄=√(A·fy/Ncr) ; Ncr=π²·E·I/Lcr²"},
           "source": SOURCE, "execution_ready": False, "warnings": warnings}
    if med_knm and med_knm > 0:
        n = ned_kn / Npl_kn if Npl_kn > 0 else 0.0
        a = min((A - 2 * b_fl_mm * tf_mm) / A, 0.5)
        MNy = min(Mc_knm * (1 - n) / (1 - 0.5 * a) if (1 - 0.5 * a) > 0 else Mc_knm, Mc_knm)
        out["cross_section"] = {"mn_y_rd_knm": round(MNy, 2), "med_knm": round(med_knm, 2),
                                "n": round(n, 3), "a": round(a, 3),
                                "utilisation": util_status(med_knm / MNy if MNy > 0 else None),
                                "formula": "MN,y,Rd=Mpl,y·(1−n)/(1−0.5a), n=N/Npl, a=(A−2·b·tf)/A≤0.5 (§6.2.9)"}
        # Déversement χLT
        if lateral_restraint:
            chi_lt, mcr = 1.0, None
        elif mono or iw_cm6 <= 0:
            chi_lt, mcr = 1.0, None
            warnings.append("Profilé en U / section mono-symétrique : Mcr non calculé automatiquement "
                            "(χLT=1 supposé) — prévoir un maintien latéral ou fournir Mcr.")
        else:
            mcr = mcr_elastic(iz_cm4, it_cm4, iw_cm6, lcr_z_m, 1.0)
            lam_lt = math.sqrt(W * fy_mpa / (mcr * 1e6)) if mcr > 0 else 0.0
            chi_lt = _chi(lam_lt, CURVES.get(curve_lt, 0.21))
        MLT = chi_lt * MyRk_knm / gamma_m1
        n_y = ned_kn / Nb_y if Nb_y > 0 else 0.0
        n_z = ned_kn / Nb_z if Nb_z > 0 else 0.0
        den = max(cm_lt - 0.25, 1e-6)
        if section_class in (1, 2):
            kyy = min(cmy * (1 + (lam_y - 0.2) * n_y), cmy * (1 + 0.8 * n_y))
            if lam_z < 0.4:
                kzy = min(0.6 + lam_z, 1 - (0.1 * lam_z) / den * n_z)
            else:
                kzy = max(1 - (0.1 * lam_z) / den * n_z, 1 - 0.1 / den * n_z)
        else:
            kyy = min(cmy * (1 + 0.6 * lam_y * n_y), cmy * (1 + 0.6 * n_y))
            kzy = max(1 - (0.05 * lam_z) / den * n_z, 1 - 0.05 / den * n_z)
        eq661 = (ned_kn / Nb_y if Nb_y > 0 else 0.0) + (kyy * med_knm / MLT if MLT > 0 else 0.0)
        eq662 = (ned_kn / Nb_z if Nb_z > 0 else 0.0) + (kzy * med_knm / MLT if MLT > 0 else 0.0)
        gov = max(eq661, eq662)
        out["interaction"] = {"value": round(gov, 3), "utilisation": util_status(gov),
                              "eq_661": round(eq661, 3), "eq_662": round(eq662, 3),
                              "kyy": round(kyy, 3), "kzy": round(kzy, 3), "cmy": cmy, "cm_lt": cm_lt,
                              "chi_lt": round(chi_lt, 3), "mcr_knm": round(mcr, 2) if mcr else None,
                              "mlt_rd_knm": round(MLT, 2), "lateral_restraint": lateral_restraint,
                              "method": "EN 1993-1-1 §6.3.3 méthode 2 (Annexe B)",
                              "formula": "(6.61) N/(χy·NRk/γM1)+kyy·My/(χLT·MyRk/γM1) ; "
                                         "(6.62) N/(χz·NRk/γM1)+kzy·My/(χLT·MyRk/γM1) ≤ 1"}
    return out


def catalog() -> dict:
    return {"version": VERSION, "grades": GRADES,
            "profiles": profiles.catalog_rows(), "families": profiles.families(),
            "curves": list(CURVES), "col_curves": list(COL_CURVES), "c1_presets": C1_PRESETS,
            "cm_presets": CM_PRESETS,
            "defaults": {"gamma_m0": 1.0, "gamma_m1": 1.0, "section_class": None, "buckling_curve": "a",
                         "c1": 1.0, "k_buckling": 1.0, "cmy": 0.9, "cm_lt": 0.9, "lateral_restraint": False},
            "note": "Propriétés EN 10365 vérifiées ; classe de section automatique (Table 5.2). " + DISCLAIMER}


def verify(med_knm: float, ved_kn: float = 0.0, *, wpl_y_cm3: float, wel_y_cm3: float,
           av_cm2: float, fy_mpa: float, section_class: int = 1, gamma_m0: float = 1.0,
           gamma_m1: float = 1.0, mcr_knm: float | None = None, buckling_curve: str = "a",
           tw_mm: float | None = None, h_mm: float | None = None, tf_mm: float | None = None) -> dict:
    W_mm3 = (wpl_y_cm3 if section_class in (1, 2) else wel_y_cm3) * 1000.0
    Mc = W_mm3 * fy_mpa / gamma_m0 / 1e6
    Av = av_cm2 * 100.0
    Vpl = Av * fy_mpa / math.sqrt(3) / gamma_m0 / 1000.0
    warn = []
    if section_class == 4:
        warn.append("Section de classe 4 : propriétés efficaces non calculées (voilement local) — à vérifier.")
    mv = False
    mc_eff = Mc
    if Vpl > 0 and ved_kn > 0.5 * Vpl:
        if section_class in (1, 2) and tw_mm and h_mm and tf_mm:
            rho = (2 * ved_kn / Vpl - 1) ** 2
            aw = (h_mm - 2 * tf_mm) * tw_mm
            wpl_eff = max(W_mm3 - rho * aw * aw / (4 * tw_mm), 0.0)
            mc_eff = wpl_eff * fy_mpa / gamma_m0 / 1e6
            mv = True
            warn.append(f"V_Ed > 0,5·V_pl,Rd : interaction M-V appliquée (ρ={round(rho, 3)}) ; "
                        f"M_c,Rd réduit de {round(Mc, 1)} à {round(mc_eff, 1)} kN·m (EN 1993-1-1 §6.2.8).")
        else:
            warn.append("V_Ed > 0,5·V_pl,Rd : interaction M-V à considérer (réduction non calculée : "
                        "fournir tw, h, tf et une section de classe 1/2).")

    if mcr_knm and mcr_knm > 0:
        lam = math.sqrt(W_mm3 * fy_mpa / (mcr_knm * 1e6))
        a = CURVES.get(buckling_curve, 0.21)
        phi = 0.5 * (1 + a * (lam - 0.2) + lam * lam)
        chi = min(1.0 / (phi + math.sqrt(max(phi * phi - lam * lam, 0.0))), 1.0) if phi > 0 else 1.0
        Mb = chi * W_mm3 * fy_mpa / gamma_m1 / 1e6
        ltb = {"lambda_lt": round(lam, 3), "chi_lt": round(chi, 3), "mb_rd_knm": round(Mb, 2),
               "mcr_knm": round(mcr_knm, 2),
               "utilisation": util_status(med_knm / Mb if Mb > 0 else None),
               "formula": "λ̄LT=√(Wy·fy/Mcr) ; χLT (courbe EN 1993-1-1 §6.3.2.2) ; Mb,Rd=χLT·Wy·fy/γM1"}
    else:
        ltb = {"utilisation": util_status(None),
               "note": "Déversement non calculé : fournir la portée (Mcr auto) ou Mcr, ou prévoir un maintien latéral."}

    return {"version": VERSION,
            "section": {"W_cm3": round(W_mm3 / 1000, 1), "fy_mpa": fy_mpa, "section_class": section_class},
            "bending": {"mc_rd_knm": round(Mc, 2), "mc_rd_eff_knm": round(mc_eff, 2), "mv_interaction": mv,
                        "med_knm": round(med_knm, 2),
                        "utilisation": util_status(med_knm / mc_eff if mc_eff > 0 else None),
                        "formula": "M_c,Rd=W·fy/γM0 ; si V_Ed>0,5·V_pl,Rd : M_y,V,Rd=[Wpl−ρ·Aw²/(4tw)]·fy/γM0 (§6.2.8)"},
            "shear": {"vpl_rd_kn": round(Vpl, 2), "ved_kn": round(ved_kn, 2),
                      "utilisation": util_status(ved_kn / Vpl if Vpl > 0 else None),
                      "formula": "V_pl,Rd=Av·(fy/√3)/γM0"},
            "lateral_torsional": ltb, "warnings": warn, "source": SOURCE, "execution_ready": False}


def design_study(model: dict, result: dict, opts: dict) -> dict:
    from engines import structuro_eurocode as eurocode
    env = eurocode.design_envelope(result or {})
    pname = opts.get("profile", "IPE300")
    prof = PROFILE_DATA.get(pname)
    grade = opts.get("grade", "S235")
    fy = GRADES.get(grade, 235)
    by = {e.get("id"): e for e in (model or {}).get("elements", [])}
    spans = opts.get("spans") or {}
    c1 = float(opts.get("c1", 1.0))
    manual_mcr = float(opts["mcr_knm"]) if opts.get("mcr_knm") else None
    manual_class = opts.get("section_class")
    curves = profiles.buckling_curves(pname, fy) if prof else {"y": "b", "z": "c", "lt": "a"}
    cls_bend = profiles.classify(pname, fy, "bending") if prof else {"section_class": 1}
    cls_comp = profiles.classify(pname, fy, "compression") if prof else {"section_class": 1}
    sc_bend = int(manual_class) if manual_class else cls_bend["section_class"]
    sc_comp = int(manual_class) if manual_class else cls_comp["section_class"]
    ltb_curve = opts.get("buckling_curve") or curves["lt"]
    rows = []
    for ee in env.get("elements", []):
        if ee.get("kind") != "beam":
            continue
        rid = ee["id"]
        el = by.get(rid) or {}
        m = (ee.get("uls") or {}).get("moment_knm")
        v = (ee.get("uls") or {}).get("shear_kn")
        if not m:
            rows.append({"id": rid, "status": "no_envelope",
                         "message": "Générez d'abord les combinaisons EN 1990 (moment dimensionnant manquant)."})
            continue
        if not prof:
            rows.append({"id": rid, "status": "missing_section", "message": "Profil inconnu."})
            continue
        plan_L = el.get("length_m")
        override = spans.get(rid)
        L = override if override is not None else plan_L
        span_source = "manuel" if override is not None else ("plan" if plan_L else "manquant")
        mono = bool(prof.get("mono"))
        if manual_mcr:
            mcr, mcr_source = manual_mcr, "manuel"
        elif mono:
            mcr, mcr_source = None, "profilé en U — Mcr non auto (section mono-symétrique)"
        elif L:
            mcr = round(mcr_elastic(prof["Iz"], prof["It"], prof["Iw"], float(L), c1), 2)
            mcr_source = "auto (plan)" if span_source == "plan" else "auto (saisi)"
        else:
            mcr, mcr_source = None, "portée manquante"
        res = verify(m["value"], (v or {}).get("value", 0.0), wpl_y_cm3=prof["Wpl"], wel_y_cm3=prof["Wel"],
                     av_cm2=prof["Av"], fy_mpa=fy, section_class=sc_bend,
                     gamma_m0=float(opts.get("gamma_m0", 1.0)), gamma_m1=float(opts.get("gamma_m1", 1.0)),
                     mcr_knm=mcr, buckling_curve=ltb_curve,
                     tw_mm=prof["tw"], h_mm=prof["h"], tf_mm=prof["tf"])
        rows.append({"id": rid, "status": "ok", "profile": pname, "grade": grade,
                     "span_m": round(float(L), 3) if L else None, "span_source": span_source,
                     "mcr_knm": mcr, "mcr_source": mcr_source, "c1": c1,
                     "section_class": sc_bend, "class_detail": cls_bend, "class_mode": "manuel" if manual_class else "auto",
                     "med_case": m.get("label"), "ved_case": (v or {}).get("label"), "result": res})

    col_rows = []
    if prof:
        k_buck = float(opts.get("k_buckling", 1.0))
        lcr_opt = float(opts["lcr_m"]) if opts.get("lcr_m") else None
        med_col = float(opts.get("med_col_knm") or 0)
        cmy = float(opts.get("cmy", 0.9))
        cm_lt = float(opts.get("cm_lt", 0.9))
        lat = bool(opts.get("lateral_restraint", False))
        mono = bool(prof.get("mono"))
        for ee in env.get("elements", []):
            if ee.get("kind") != "column":
                continue
            rid = ee["id"]
            el = by.get(rid) or {}
            n = (ee.get("uls") or {}).get("axial_kn")
            if not n:
                col_rows.append({"id": rid, "status": "no_envelope",
                                 "message": "Générez d'abord les combinaisons EN 1990 (effort normal manquant)."})
                continue
            h = el.get("height_m")
            lcr = lcr_opt if lcr_opt else (k_buck * h if h else None)
            lcr_source = "manuel" if lcr_opt else ("plan (K×h)" if h else "manquant")
            if not lcr:
                col_rows.append({"id": rid, "status": "need_length",
                                 "message": "Hauteur du poteau absente du plan : saisir Lcr."})
                continue
            res = verify_column(n["value"], med_col, A_cm2=prof["A"], iy_cm4=prof["Iy"], iz_cm4=prof["Iz"],
                                it_cm4=prof["It"], iw_cm6=prof["Iw"], wpl_y_cm3=prof["Wpl"], wel_y_cm3=prof["Wel"],
                                b_fl_mm=prof["b"], h_mm=prof["h"], tf_mm=prof["tf"], fy_mpa=fy,
                                lcr_y_m=float(lcr), section_class=sc_comp,
                                gamma_m0=float(opts.get("gamma_m0", 1.0)), gamma_m1=float(opts.get("gamma_m1", 1.0)),
                                curve_y=curves["y"], curve_z=curves["z"], curve_lt=ltb_curve,
                                cmy=cmy, cm_lt=cm_lt, lateral_restraint=lat, mono=mono)
            col_rows.append({"id": rid, "status": "ok", "profile": pname, "grade": grade,
                             "ned_kn": n["value"], "ned_case": n.get("label"),
                             "lcr_m": round(float(lcr), 3), "lcr_source": lcr_source,
                             "section_class": sc_comp, "class_detail": cls_comp,
                             "class_mode": "manuel" if manual_class else "auto", "result": res})
    return {"version": VERSION, "elements": rows, "columns": col_rows, "execution_ready": False, "note": DISCLAIMER}
