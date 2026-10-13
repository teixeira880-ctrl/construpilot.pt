"""Flèches en service (EN 1990 SLS) — poutres, liées à l'enveloppe caractéristique / quasi-permanente.

Déterministe : compare la flèche élastique déjà calculée (selon l'EI saisi, donc
dépendante du matériau béton/acier/bois) aux limites usuelles L/ratio. La portée L
vient AUTOMATIQUEMENT du plan (length_m) ; si le plan ne la marque pas, elle peut
être saisie manuellement (override `spans`). Rapports indicatifs, à valider.
"""
from __future__ import annotations

import math

from engines.structuro_check import DISCLAIMER, util_status

VERSION = "sls-deflection-0.1.0"


def cracked_long_term(w_elastic_mm: float, ei_ref_kn_m2: float, *, b_m: float, h_m: float, d_m: float,
                      as_mm2: float, m_qp_knm: float, fck: float = 25.0, phi_creep: float = 2.0,
                      beta: float = 0.5) -> dict:
    """Flèche long terme fissurée — EN 1992-1-1 §7.4.3 (méthode d'interpolation).

    Part de la flèche élastique `w_elastic_mm` calculée avec la rigidité de référence `ei_ref`
    (béton non fissuré, Ecm·Ig) et la corrige :
      Ec,eff = Ecm/(1+φ)                       (fluage, φ usuel 2,0 — à vérifier)
      I_I ≈ Ig = b·h³/12 (acier négligé, sécuritaire) ; I_II section fissurée, αe = Es/Ec,eff
      Mcr = fctm·b·h²/6 ; ζ = 1 − β·(Mcr/M)² si M > Mcr, sinon 0 ; β = 0,5 (longue durée)
      w = ζ·w_II + (1−ζ)·w_I  avec w ∝ 1/(E·I)
    Retrait non inclus (à ajouter par l'ingénieur). Indicatif, non exécutoire.
    """
    fcm = fck + 8.0
    ecm_mpa = 22000.0 * (fcm / 10.0) ** 0.3
    fctm = 0.30 * fck ** (2.0 / 3.0)
    ec_eff = ecm_mpa / (1.0 + phi_creep)
    b, h, d = b_m * 1000, h_m * 1000, d_m * 1000            # mm
    ig = b * h ** 3 / 12.0
    alpha = 200000.0 / ec_eff
    a_s = max(as_mm2, 1e-6)
    # Axe neutre fissuré : b·x²/2 = αe·As·(d−x)
    x = (-alpha * a_s + math.sqrt((alpha * a_s) ** 2 + 2 * b * alpha * a_s * d)) / b
    i2 = b * x ** 3 / 3.0 + alpha * a_s * (d - x) ** 2
    mcr = fctm * b * h * h / 6.0 / 1e6                      # kN·m
    m = abs(m_qp_knm)
    zeta = 0.0 if m <= mcr or m == 0 else 1.0 - beta * (mcr / m) ** 2
    ei_1 = ec_eff * 1e3 * ig * 1e-12                        # kN·m²  (MPa→kPa, mm⁴→m⁴)
    ei_2 = ec_eff * 1e3 * i2 * 1e-12
    w1 = w_elastic_mm * ei_ref_kn_m2 / ei_1
    w2 = w_elastic_mm * ei_ref_kn_m2 / ei_2
    w = zeta * w2 + (1 - zeta) * w1
    return {"w_long_term_mm": round(w, 2), "w_elastic_mm": round(w_elastic_mm, 2),
            "amplification": round(w / w_elastic_mm, 2) if w_elastic_mm else None,
            "zeta": round(zeta, 3), "mcr_knm": round(mcr, 2), "m_qp_knm": round(m, 2),
            "ec_eff_mpa": round(ec_eff, 0), "i_cracked_cm4": round(i2 / 1e4, 0), "i_gross_cm4": round(ig / 1e4, 0),
            "phi_creep": phi_creep,
            "formula": "w=ζ·w_II+(1−ζ)·w_I ; ζ=1−β(Mcr/M)² ; Ec,eff=Ecm/(1+φ) (EN 1992-1-1 §7.4.3)",
            "note": "Retrait non inclus ; φ=2,0 valeur usuelle à vérifier selon âge de chargement et humidité."}


def _max_defl(cases: list, prefix: str, eid: str):
    best = None
    for c in cases:
        if not str(c.get("id", "")).startswith(prefix):
            continue
        row = next((r for r in c.get("elements", []) if r["id"] == eid), None)
        if not row or row.get("deflection_sampled_mm") is None:
            continue
        v = abs(row["deflection_sampled_mm"])
        if best is None or v > best["value"]:
            best = {"case": c["id"], "label": c.get("label", c["id"]), "value": round(v, 3)}
    return best


def deflection_study(model: dict, result: dict, opts: dict) -> dict:
    cases = (result or {}).get("cases") or []
    spans = opts.get("spans") or {}
    rc = float(opts.get("ratio_char", 250))
    rq = float(opts.get("ratio_qp", 300))
    rows = []
    for e in (model or {}).get("elements", []):
        if e.get("kind") != "beam":
            continue
        eid = e["id"]
        plan_L = e.get("length_m")
        override = spans.get(eid)
        # Flèches : la portée est AUTOMATIQUE d'après la géométrie du plan (length_m) pour toutes
        # les poutres ; la saisie manuelle n'est qu'un recours si le plan ne la marque pas.
        if plan_L:
            L, span_source = plan_L, "plan (auto)"
        elif override is not None:
            L, span_source = override, "manuel"
        else:
            L, span_source = None, "manquant"
        if not L:
            rows.append({"id": eid, "status": "need_span", "span_source": span_source,
                         "message": "Portée absente du plan : saisir la portée pour vérifier la flèche."})
            continue
        wc = _max_defl(cases, "ELScar", eid)
        wq = _max_defl(cases, "ELSqp", eid)
        if wc is None and wq is None:
            rows.append({"id": eid, "status": "no_deflection", "span_m": round(float(L), 3), "span_source": span_source,
                         "message": "Flèche non calculée : définir l'EI (rigidité) de la poutre dans le modèle."})
            continue
        lim_c, lim_q = float(L) * 1000 / rc, float(L) * 1000 / rq
        rows.append({"id": eid, "status": "ok", "span_m": round(float(L), 3), "span_source": span_source,
                     "char": {"w_mm": wc["value"] if wc else None, "case": wc["label"] if wc else None,
                              "limit_mm": round(lim_c, 2), "ratio_label": f"L/{int(rc)}",
                              "utilisation": util_status(wc["value"] / lim_c if wc else None)},
                     "qp": {"w_mm": wq["value"] if wq else None, "case": wq["label"] if wq else None,
                            "limit_mm": round(lim_q, 2), "ratio_label": f"L/{int(rq)}",
                            "utilisation": util_status(wq["value"] / lim_q if wq else None)}})
    return {"version": VERSION, "elements": rows, "execution_ready": False,
            "note": "Flèches élastiques de l'enveloppe EN 1990 (caractéristique / quasi-permanente) "
                    "vs L/ratio. La flèche dépend de l'EI saisi (béton/acier/bois). " + DISCLAIMER}
