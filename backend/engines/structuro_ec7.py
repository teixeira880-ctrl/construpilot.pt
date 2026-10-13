"""Lot 3 — EN 1997-1 Annexe D : portance des semelles superficielles (déterministe).

Méthodologie PUBLIQUE de l'Annexe D (charge verticale centrée, semelle rectangulaire) ;
aucun texte normatif protégé n'est reproduit. Facteurs partiels par défaut : approche
de calcul DA2 de l'AN FR (γR;v=1.4, γφ=γc=γcu=1.0), tous éditables et à vérifier.

Zéro hallucination : si une donnée de sol indispensable manque, le calcul s'arrête et
la réclame (inconnu n'est pas zéro). Le rapport Ed/Rd est indicatif, jamais un verdict.
"""
from __future__ import annotations

import math

from engines.structuro_check import DISCLAIMER, util_status

VERSION = "ec7-bearing-0.1.0"
SOURCE = "EN 1997-1 Annexe D (méthodologie publique) — approche DA2 AN FR par défaut — à vérifier"
DEFAULTS = {"design_approach": "DA2", "gamma_Rv": 1.4, "gamma_phi": 1.0, "gamma_c": 1.0, "gamma_cu": 1.0}


def catalog() -> dict:
    return {"version": VERSION, "defaults": DEFAULTS, "modes": ["drained", "undrained"],
            "note": "Semelle rectangulaire, charge verticale centrée, Annexe D. " + DISCLAIMER}


def bearing(mode: str, b_m: float, l_m: float, *, q_ed_kpa: float = 0.0, d_m: float = 0.0,
            gamma_soil: float = 0.0, c_kpa: float = 0.0, phi_deg: float = 0.0, cu_kpa: float = 0.0,
            gamma_Rv: float = 1.4, gamma_phi: float = 1.0, gamma_c: float = 1.0,
            gamma_cu: float = 1.0) -> dict:
    if b_m <= 0 or l_m <= 0:
        raise ValueError("Dimensions de semelle invalides")
    B, L = min(b_m, l_m), max(b_m, l_m)
    q_ov = gamma_soil * d_m

    if mode == "drained":
        missing = []
        if phi_deg <= 0:
            missing.append("angle de frottement φ'")
        if gamma_soil <= 0:
            missing.append("poids volumique du sol γ")
        if missing:
            return {"version": VERSION, "mode": mode, "status": "missing",
                    "message": "Données de sol manquantes : " + ", ".join(missing), "source": SOURCE}
        phi_d = math.atan(math.tan(math.radians(phi_deg)) / gamma_phi)
        c_d = c_kpa / gamma_c
        Nq = math.exp(math.pi * math.tan(phi_d)) * math.tan(math.pi / 4 + phi_d / 2) ** 2
        Nc = (Nq - 1) / math.tan(phi_d) if phi_d > 1e-6 else 5.14
        Ng = 2 * (Nq - 1) * math.tan(phi_d)
        sq = 1 + (B / L) * math.sin(phi_d)
        sg = 1 - 0.3 * (B / L)
        sc = (sq * Nq - 1) / (Nq - 1) if Nq > 1 else 1.0
        R_A = c_d * Nc * sc + q_ov * Nq * sq + 0.5 * gamma_soil * B * Ng * sg
        factors = {"Nc": round(Nc, 3), "Nq": round(Nq, 3), "Ngamma": round(Ng, 3),
                   "sc": round(sc, 3), "sq": round(sq, 3), "sgamma": round(sg, 3),
                   "phi_d_deg": round(math.degrees(phi_d), 2), "c_d_kpa": round(c_d, 2),
                   "q_overburden_kpa": round(q_ov, 2)}
        formula = "R/A'=c'·Nc·sc+q'·Nq·sq+0.5·γ·B·Nγ·sγ (EN 1997-1 D.4, drainé)"
    elif mode == "undrained":
        if cu_kpa <= 0:
            return {"version": VERSION, "mode": mode, "status": "missing",
                    "message": "Donnée de sol manquante : cohésion non drainée cu", "source": SOURCE}
        cu_d = cu_kpa / gamma_cu
        sc = 1 + 0.2 * (B / L)
        R_A = (math.pi + 2) * cu_d * sc + q_ov
        factors = {"(pi+2)": round(math.pi + 2, 3), "sc": round(sc, 3),
                   "cu_d_kpa": round(cu_d, 2), "q_overburden_kpa": round(q_ov, 2)}
        formula = "R/A'=(π+2)·cu·sc+q (EN 1997-1 D.3, non drainé)"
    else:
        raise ValueError("Mode : drained ou undrained")

    q_Rd = R_A / gamma_Rv
    ratio = q_ed_kpa / q_Rd if q_Rd > 0 else None
    return {"version": VERSION, "mode": mode, "status": "ok", "q_ed_kpa": round(q_ed_kpa, 2),
            "R_A_kpa": round(R_A, 2), "q_Rd_kpa": round(q_Rd, 2), "gamma_Rv": gamma_Rv,
            "B_m": round(B, 3), "L_m": round(L, 3), "factors": factors,
            "utilisation": util_status(ratio), "formula": formula, "source": SOURCE,
            "execution_ready": False}


def design_study(model: dict, result: dict, opts: dict) -> dict:
    from engines import structuro_eurocode as eurocode
    env = eurocode.design_envelope(result or {})
    by = {e.get("id"): e for e in (model or {}).get("elements", [])}
    rows = []
    for ee in env.get("elements", []):
        if ee.get("kind") != "footing":
            continue
        rid = ee["id"]
        el = by.get(rid) or {}
        p = (ee.get("uls") or {}).get("pressure_kpa")
        if not p:
            rows.append({"id": rid, "status": "no_envelope",
                         "message": "Générez d'abord les combinaisons EN 1990 (pression dimensionnante manquante)."})
            continue
        b, l = el.get("width_m"), el.get("length_m")
        if not b or not l:
            rows.append({"id": rid, "status": "missing_section",
                         "message": "Longueur et largeur de semelle requises dans le modèle."})
            continue
        res = bearing(opts.get("mode", "drained"), b, l, q_ed_kpa=p["value"],
                      d_m=float(opts.get("d_m", 0)), gamma_soil=float(opts.get("gamma_soil", 0)),
                      c_kpa=float(opts.get("c_kpa", 0)), phi_deg=float(opts.get("phi_deg", 0)),
                      cu_kpa=float(opts.get("cu_kpa", 0)), gamma_Rv=float(opts.get("gamma_Rv", 1.4)),
                      gamma_phi=float(opts.get("gamma_phi", 1.0)), gamma_c=float(opts.get("gamma_c", 1.0)),
                      gamma_cu=float(opts.get("gamma_cu", 1.0)))
        rows.append({"id": rid, "status": res.get("status", "ok"), "b_m": round(b, 3), "l_m": round(l, 3),
                     "q_ed_case": p.get("label"), "message": res.get("message"), "result": res})
    return {"version": VERSION, "elements": rows, "execution_ready": False, "note": DISCLAIMER}
