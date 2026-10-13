"""EN 1992-1-1 §8.4 (ancrage) & §8.7 (recouvrement) : longueurs d'ancrage et d'emende des barres.

Déterministe, méthodologie PUBLIQUE EN 1992-1-1. À partir du ferraillage PROPOSÉ (Lot 2) :
Ø de barre, classe de béton, As,req / As,prov. Contrainte d'adhérence fbd (§8.4.2), longueur de
référence lb,rqd (§8.4.3), longueur d'ancrage de calcul lbd (§8.4.4, facteurs α1..α5) ≥ lb,min, et
longueur de recouvrement l0 (§8.7.3, α6=√(ρ1/25)) ≥ l0,min. Coefficients α éditables (défauts usuels
conservateurs : bonne adhérence, barres droites). Rapports indicatifs — à vérifier par l'ingénieur.
"""
from __future__ import annotations

import math

from engines.structuro_check import DISCLAIMER

VERSION = "ec2-anchorage-0.1.0"
SOURCE = "EN 1992-1-1 §8.4 (ancrage) & §8.7 (recouvrement) — méthodologie publique, AN FR — à vérifier"


def _r(x, n=1):
    return round(float(x), n)


def anchorage(bar_mm: float, *, fck: float = 25, fyk: float = 500, as_req_cm2: float = 0.0,
              as_prov_cm2: float = 0.0, cover_mm: float = 30.0, bond: str = "good",
              gamma_c: float = 1.5, gamma_s: float = 1.15, alpha_cc: float = 1.0,
              alpha1: float = 1.0, alpha3: float = 1.0, alpha4: float = 1.0, alpha5: float = 1.0,
              rho1_pct: float = 50.0) -> dict:
    """Ancrage/recouvrement d'une barre tendue (Ø en mm). Longueurs rendues en mm et m."""
    if fck > 50:
        raise ValueError("Ancrages couverts jusqu'à C50/60 (fctk0,05 = 0,7·fctm).")
    phi = float(bar_mm)
    fctm = 0.30 * fck ** (2.0 / 3.0)
    fctk05 = 0.7 * fctm
    fctd = alpha_cc * fctk05 / gamma_c                       # αct=αcc par défaut
    fyd = fyk / gamma_s
    eta1 = 1.0 if bond == "good" else 0.7                     # §8.4.2 (conditions d'adhérence)
    eta2 = 1.0 if phi <= 32 else (132 - phi) / 100.0          # §8.4.2 (Ø > 32)
    fbd = 2.25 * eta1 * eta2 * fctd                           # §8.4.2(2)
    # σsd : réduction possible par As,req/As,prov sinon pleine plastification
    ratio = (as_req_cm2 / as_prov_cm2) if (as_req_cm2 > 0 and as_prov_cm2 > 0) else 1.0
    ratio = min(max(ratio, 0.0), 1.0)
    sigma_sd_full = fyd
    lb_rqd = (phi / 4.0) * (sigma_sd_full / fbd) if fbd > 0 else 0.0   # §8.4.3 (σsd=fyd)
    # α2 : enrobage (barres droites) §8.4.4 Tableau 8.2 — cd = enrobage, borné 0,7..1,0
    cd = cover_mm
    alpha2 = min(max(1 - 0.15 * (cd - phi) / phi, 0.7), 1.0)
    prod = alpha1 * alpha2 * alpha3 * alpha4 * alpha5
    prod = max(prod, 0.7)                                     # produit α2·α3·α5 ≥ 0,7 (sécuritaire sur le produit)
    lbd_full = prod * lb_rqd
    lb_min = max(0.3 * lb_rqd, 10 * phi, 100.0)               # §8.4.4(1) tension
    lbd = max(lbd_full, lb_min)
    lbd_reduced = max(lbd * ratio, lb_min) if ratio < 1 else lbd  # §8.5 (As,req/As,prov)
    # Recouvrement §8.7.3
    rho1 = min(max(rho1_pct, 0.0), 100.0)
    alpha6 = min(max(math.sqrt(rho1 / 25.0), 1.0), 1.5)
    l0 = alpha1 * alpha2 * alpha3 * alpha5 * alpha6 * lb_rqd
    l0_min = max(0.3 * alpha6 * lb_rqd, 15 * phi, 200.0)
    l0 = max(l0, l0_min)
    return {"version": VERSION, "bar_mm": phi, "fck": fck, "fyk": fyk,
            "fbd_mpa": _r(fbd, 2), "fctd_mpa": _r(fctd, 3), "fyd_mpa": _r(fyd, 1),
            "eta1": eta1, "eta2": _r(eta2, 3), "bond": bond,
            "lb_rqd_mm": _r(lb_rqd), "lb_rqd_m": _r(lb_rqd / 1000, 3),
            "alpha2": _r(alpha2, 3), "alpha_prod": _r(prod, 3),
            "lbd_mm": _r(lbd), "lbd_m": _r(lbd / 1000, 3), "lbd_ratio_phi": _r(lbd / phi, 1),
            "lb_min_mm": _r(lb_min), "as_ratio": _r(ratio, 3), "lbd_reduced_mm": _r(lbd_reduced),
            "lbd_reduced_m": _r(lbd_reduced / 1000, 3),
            "alpha6": _r(alpha6, 3), "rho1_pct": rho1,
            "l0_mm": _r(l0), "l0_m": _r(l0 / 1000, 3), "l0_ratio_phi": _r(l0 / phi, 1), "l0_min_mm": _r(l0_min),
            "source": SOURCE, "execution_ready": False,
            "formula": "fbd=2.25·η1·η2·fctd ; lb,rqd=(Ø/4)·σsd/fbd ; lbd=α1α2α3α4α5·lb,rqd≥lb,min ; "
                       "l0=α1α2α3α5α6·lb,rqd≥l0,min, α6=√(ρ1/25)∈[1;1.5]"}


def anchorage_study(model: dict, result: dict, opts: dict, auto: dict | None = None) -> dict:
    """Ancrages/recouvrements par poutre, à partir du ferraillage EN 1992 proposé (Lot 2)."""
    from engines import structuro_ec2 as ec2
    ec2_out = ec2.design_study(model, result, opts, auto)
    bond = opts.get("bond", "good")
    rho1 = float(opts.get("rho1_pct", 50.0))
    cover_mm = float(opts.get("cover_m", 0.05)) * 1000.0
    a1 = float(opts.get("alpha1", 1.0))
    a3 = float(opts.get("alpha3", 1.0))
    a4 = float(opts.get("alpha4", 1.0))
    a5 = float(opts.get("alpha5", 1.0))
    rows = []
    for r in ec2_out.get("elements", []):
        if r.get("status") != "ok":
            rows.append({"id": r.get("id"), "status": r.get("status", "skip"),
                         "message": r.get("message", "Pas de ferraillage EN 1992 calculé.")})
            continue
        scheme = r.get("scheme") or {}
        longi = scheme.get("longitudinal") or {}
        bar_mm = longi.get("bar_mm") or int(opts.get("bar_mm", 16))
        as_req = r["design"]["flexure"]["as_req_cm2"]
        as_prov = longi.get("as_provided_cm2") or as_req
        try:
            anc = anchorage(bar_mm, fck=float(opts.get("fck", 25)), fyk=float(opts.get("fyk", 500)),
                            as_req_cm2=as_req, as_prov_cm2=as_prov, cover_mm=cover_mm, bond=bond,
                            gamma_c=float(opts.get("gamma_c", 1.5)), gamma_s=float(opts.get("gamma_s", 1.15)),
                            alpha_cc=float(opts.get("alpha_cc", 1.0)),
                            alpha1=a1, alpha3=a3, alpha4=a4, alpha5=a5, rho1_pct=rho1)
        except ValueError as exc:
            rows.append({"id": r["id"], "status": "invalid", "message": str(exc)})
            continue
        rows.append({"id": r["id"], "status": "ok", "bar_label": longi.get("label"),
                     "reinforcement_source": r.get("reinforcement_source"),
                     "as_req_cm2": as_req, "as_prov_cm2": as_prov, "result": anc})
    reinjected = bool(ec2_out.get("reinjected_from_automation"))
    return {"version": VERSION, "elements": rows, "execution_ready": False,
            "reinjected_from_automation": reinjected,
            "note": "Longueurs d'ancrage lbd (§8.4) et de recouvrement l0 (§8.7) du ferraillage proposé "
                    "(bonne adhérence/barres droites par défaut, α éditables)."
                    + (" Ø et As,prov issus des aciers CHOISIS par la chaîne automatique (réinjectés §8)." if reinjected else "")
                    + " " + DISCLAIMER}
