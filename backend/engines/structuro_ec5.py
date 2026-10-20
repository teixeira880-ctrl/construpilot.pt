"""Lot 5 — EN 1995-1-1 : vérification de poutres bois (flexion, cisaillement, déversement).

Méthodologie PUBLIQUE EN 1995-1-1 §6.1.6/§6.1.7/§6.3.3. Les valeurs caractéristiques
sont les valeurs PUBLIQUES normalisées EN 338 (bois massif) / EN 14080 (lamellé-collé),
éditables et à vérifier. kmod (durée × classe de service) et γM par défaut recommandés.

Zéro hallucination : le déversement n'est calculé que si lef (longueur efficace) est
fournie. Rapports Ed/Rd indicatifs, jamais un verdict réglementaire.
"""
from __future__ import annotations

import math

from engines.structuro_check import DISCLAIMER, util_status

VERSION = "ec5-member-0.1.0"
SOURCE = ("EN 1995-1-1 §6.1.6 (flexion), §6.1.7 (cisaillement, kcr), §6.3.3 (déversement) ; "
          "valeurs EN 338 / EN 14080 publiques — à vérifier")

CLASSES = {
    "C18": {"fm_k": 18, "fv_k": 3.4, "E0_mean": 9000, "E0_05": 6000, "rho_k": 320, "kind": "solid"},
    "C24": {"fm_k": 24, "fv_k": 4.0, "E0_mean": 11000, "E0_05": 7400, "rho_k": 350, "kind": "solid"},
    "C30": {"fm_k": 30, "fv_k": 4.0, "E0_mean": 12000, "E0_05": 8000, "rho_k": 380, "kind": "solid"},
    "GL24h": {"fm_k": 24, "fv_k": 3.5, "E0_mean": 11500, "E0_05": 9600, "rho_k": 385, "kind": "glulam"},
    "GL28h": {"fm_k": 28, "fv_k": 3.5, "E0_mean": 12600, "E0_05": 10500, "rho_k": 425, "kind": "glulam"},
}
KMOD = {"1-2": {"permanent": 0.60, "long": 0.70, "medium": 0.80, "short": 0.90, "instantaneous": 1.10},
        "3": {"permanent": 0.50, "long": 0.55, "medium": 0.65, "short": 0.70, "instantaneous": 0.90}}
GAMMA_M = {"solid": 1.3, "glulam": 1.25}


def catalog() -> dict:
    return {"version": VERSION, "classes": [{"key": k, **v} for k, v in CLASSES.items()],
            "kmod": KMOD, "gamma_m": GAMMA_M, "service_classes": ["1", "2", "3"],
            "load_durations": list(KMOD["1-2"]),
            "note": "Classes EN 338 (massif) / EN 14080 (lamellé-collé). " + DISCLAIMER}


def kmod_value(service_class, load_duration) -> float:
    key = "3" if str(service_class) == "3" else "1-2"
    return KMOD[key].get(load_duration, 0.6)


def _kh(h_mm: float, kind: str) -> float:
    if kind == "glulam":
        return min((600.0 / h_mm) ** 0.1, 1.1) if h_mm < 600 else 1.0
    return min((150.0 / h_mm) ** 0.2, 1.3) if h_mm < 150 else 1.0


def verify(med_knm: float, ved_kn: float = 0.0, *, b_m: float, h_m: float, fm_k: float, fv_k: float,
           E0_05: float, kmod: float, gamma_m: float, kind: str = "solid", lef_m: float | None = None,
           kcr: float = 0.67, ksys: float = 1.0) -> dict:
    b, h = b_m * 1000, h_m * 1000
    fm_d = kmod * fm_k / gamma_m
    fv_d = kmod * fv_k / gamma_m
    kh = _kh(h, kind)
    W = b * h * h / 6.0
    sm = med_knm * 1e6 / W
    bending = {"sigma_m_d_mpa": round(sm, 2), "fm_d_mpa": round(fm_d, 2), "kh": round(kh, 3),
               "utilisation": util_status(sm / (kh * ksys * fm_d) if fm_d > 0 else None),
               "formula": "σm,d=M/W, W=b·h²/6 ; σm,d ≤ kh·ksys·fm,d ; fm,d=kmod·fm,k/γM"}
    tau = 1.5 * ved_kn * 1000 / (kcr * b * h)
    shear = {"tau_d_mpa": round(tau, 3), "fv_d_mpa": round(fv_d, 2), "kcr": kcr,
             "utilisation": util_status(tau / fv_d if fv_d > 0 else None),
             "formula": "τd=1.5·V/(kcr·b·h) ; τd ≤ fv,d ; fv,d=kmod·fv,k/γM"}
    if lef_m and lef_m > 0:
        sig_crit = 0.78 * b * b * E0_05 / (h * lef_m * 1000)
        lam = math.sqrt(fm_k / sig_crit)
        kcrit = 1.0 if lam <= 0.75 else (1.56 - 0.75 * lam) if lam <= 1.4 else 1.0 / (lam * lam)
        stab = {"sigma_m_crit_mpa": round(sig_crit, 2), "lambda_rel_m": round(lam, 3), "kcrit": round(kcrit, 3),
                "utilisation": util_status(sm / (kcrit * fm_d) if fm_d > 0 else None),
                "formula": "σm,crit=0.78·b²·E0,05/(h·lef) ; λrel,m=√(fm,k/σm,crit) ; σm,d ≤ kcrit·fm,d"}
    else:
        stab = {"utilisation": util_status(None),
                "note": "Déversement non calculé : fournir la longueur efficace lef (ou maintien latéral)."}
    return {"version": VERSION, "bending": bending, "shear": shear, "lateral_torsional": stab,
            "params": {"kmod": kmod, "gamma_m": gamma_m}, "source": SOURCE, "execution_ready": False}


def design_study(model: dict, result: dict, opts: dict) -> dict:
    from engines import structuro_eurocode as eurocode
    env = eurocode.design_envelope(result or {})
    cls = CLASSES.get(opts.get("strength_class", "C24"))
    kmod = kmod_value(opts.get("service_class", "1"), opts.get("load_duration", "medium"))
    gm = float(opts.get("gamma_m") or GAMMA_M.get((cls or {}).get("kind", "solid"), 1.3))
    by = {e.get("id"): e for e in (model or {}).get("elements", [])}
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
        b, h = el.get("width_m"), el.get("height_m")
        if not b or not h or not cls:
            rows.append({"id": rid, "status": "missing_section",
                         "message": "Largeur, hauteur et classe de résistance requises."})
            continue
        res = verify(m["value"], (v or {}).get("value", 0.0), b_m=b, h_m=h, fm_k=cls["fm_k"], fv_k=cls["fv_k"],
                     E0_05=cls["E0_05"], kmod=kmod, gamma_m=gm, kind=cls["kind"],
                     lef_m=float(opts["lef_m"]) if opts.get("lef_m") else None,
                     kcr=float(opts.get("kcr", 0.67)), ksys=float(opts.get("ksys", 1.0)))
        rows.append({"id": rid, "status": "ok", "strength_class": opts.get("strength_class", "C24"),
                     "b_m": round(b, 3), "h_m": round(h, 3), "med_case": m.get("label"), "result": res})
    return {"version": VERSION, "elements": rows, "execution_ready": False,
            "note": f"kmod={kmod} (classe de service {opts.get('service_class', '1')}, "
                    f"durée {opts.get('load_duration', 'medium')}). " + DISCLAIMER}
