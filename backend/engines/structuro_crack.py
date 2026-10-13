"""EN 1992-1-1 §7.3 : maîtrise de la fissuration du béton (As,min + ouverture wk).

Méthodologie PUBLIQUE §7.3.2 (As,min de fissuration) et §7.3.4 (ouverture de fissures),
sous moment QUASI-PERMANENT (enveloppe ELSqp). Utilise l'As PROPOSÉ par le ferraillage
(Lot 2). Simplifications documentées (hc,ef, σs=Mqp/(As·0.9d)). Rapports indicatifs, à vérifier.
"""
from __future__ import annotations

from engines.structuro_check import DISCLAIMER, util_status

VERSION = "ec2-crack-0.1.0"
SOURCE = "EN 1992-1-1 §7.3.2 (As,min) & §7.3.4 (ouverture de fissures) — méthodologie publique — à vérifier"
ES = 200000.0


def _ecm(fck):
    return 22000 * ((fck + 8) / 10) ** 0.3


def _fctm(fck):
    return 0.30 * fck ** (2.0 / 3.0)


def _k_h(h_mm):
    if h_mm <= 300:
        return 1.0
    if h_mm >= 800:
        return 0.65
    return 1.0 - 0.35 * (h_mm - 300) / 500


def _max_moment(cases, prefix, eid):
    best = None
    for c in cases:
        if not str(c.get("id", "")).startswith(prefix):
            continue
        row = next((r for r in c.get("elements", []) if r["id"] == eid), None)
        if not row or row.get("moment_max_knm") is None:
            continue
        v = abs(row["moment_max_knm"])
        if best is None or v > best["value"]:
            best = {"case": c["id"], "label": c.get("label", c["id"]), "value": round(v, 3)}
    return best


def crack_study(model: dict, result: dict, opts: dict, auto: dict | None = None) -> dict:
    from engines import structuro_ec2 as ec2
    ec2_out = ec2.design_study(model, result, opts, auto)
    designs = {r["id"]: r for r in ec2_out.get("elements", []) if r.get("status") == "ok"}
    cases = (result or {}).get("cases") or []
    fck, fyk = float(opts.get("fck", 25)), float(opts.get("fyk", 500))
    cover, bar = float(opts.get("cover_m", 0.05)), int(opts.get("bar_mm", 16))
    wmax, kt = float(opts.get("w_max_mm", 0.3)), float(opts.get("kt", 0.4))
    fctm, ae = _fctm(fck), ES / _ecm(fck)
    rows = []
    for e in (model or {}).get("elements", []):
        if e.get("kind") != "beam":
            continue
        eid = e["id"]
        d = designs.get(eid)
        if not d:
            rows.append({"id": eid, "status": "no_design",
                         "message": "Pas d'armature EN 1992 calculée (voir panneau béton)."})
            continue
        mqp = _max_moment(cases, "ELSqp", eid)
        if not mqp:
            rows.append({"id": eid, "status": "need_sls",
                         "message": "Générez les combinaisons ELS quasi-permanentes (moment de service manquant)."})
            continue
        b, h, dd = d["b_m"] * 1000, d["h_m"] * 1000, d["d_m"] * 1000
        scheme = d.get("scheme") or {}
        longi = scheme.get("longitudinal") or {}
        bar_used = int(longi.get("bar_mm") or bar)
        src = d.get("reinforcement_source")
        as_prov = longi.get("as_provided_cm2") or d["design"]["flexure"]["as_req_cm2"]
        As = as_prov * 100.0
        z = 0.9 * dd
        sigma_s = mqp["value"] * 1e6 / (As * z)
        hc_ef = min(2.5 * (h - dd), h / 2)
        rho = As / (b * hc_ef) if hc_ef > 0 else 0.0
        eps = max((sigma_s - kt * fctm / rho * (1 + ae * rho)) / ES, 0.6 * sigma_s / ES) if rho > 0 else 0.6 * sigma_s / ES
        sr = 3.4 * (cover * 1000) + (0.8 * 0.5 * 0.425 * bar_used / rho if rho > 0 else 0.0)
        wk = sr * eps
        as_min = 0.4 * _k_h(h) * fctm * (b * h / 2) / fyk / 100.0
        rows.append({"id": eid, "status": "ok", "mqp_knm": mqp["value"], "mqp_case": mqp["label"],
                     "sigma_s_mpa": round(sigma_s, 1), "rho_p_eff": round(rho, 5), "sr_max_mm": round(sr, 1),
                     "eps_sm_ecm": round(eps, 6), "wk_mm": round(wk, 3), "wmax_mm": wmax,
                     "bar_mm": bar_used, "reinforcement_source": src,
                     "as_prov_cm2": round(as_prov, 2), "as_min_fiss_cm2": round(as_min, 2),
                     "utilisation": util_status(wk / wmax if wmax > 0 else None),
                     "formula": "wk=sr,max·(εsm−εcm) ; sr,max=3.4c+0.8·0.5·0.425·φ/ρp,eff ; "
                                "As,min=kc·k·fct,eff·Act/σs (§7.3)"})
    reinjected = bool(ec2_out.get("reinjected_from_automation"))
    return {"version": VERSION, "elements": rows, "execution_ready": False,
            "reinjected_from_automation": reinjected,
            "note": "Ouverture de fissures sous moment quasi-permanent ELSqp (As,prov du ferraillage proposé ; "
                    "hc,ef simplifié ; σs=Mqp/(As·0.9d))."
                    + (" Ø issu des aciers CHOISIS par la chaîne automatique (réinjectés §7.3)." if reinjected else "")
                    + " " + DISCLAIMER}
