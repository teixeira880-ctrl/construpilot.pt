"""Lot 2 — EN 1992-1-1 : armatures de béton armé (déterministe, sourcé, à vérifier).

Applique la MÉTHODOLOGIE PUBLIQUE de l'EN 1992-1-1 (section rectangulaire,
diagramme rectangulaire simplifié λ/η) ; ne reproduit aucun texte normatif protégé.
Les coefficients pré-remplis sont les VALEURS USUELLES de l'Annexe Nationale
française (γc=1.5, γs=1.15, αcc=1.0), toutes éditables et marquées « à vérifier ».

Zéro hallucination : chaque sortie porte ses formules explicites et une source.
Le moteur ne valide AUCUNE sécurité : il restitue l'acier NÉCESSAIRE à vérifier
par un ingénieur. `execution_ready` reste toujours False.
"""
from __future__ import annotations

import math

VERSION = "ec2-rebar-0.1.0"
ES_MPA = 200000.0          # module d'élasticité de l'acier (EN 1992-1-1 §3.2.7)
EPS_CU3 = 0.0035           # déformation ultime du béton (fck ≤ 50 MPa), diagramme rect.
LAMBDA = 0.8               # hauteur du bloc de compression (fck ≤ 50 MPa)
SOURCE_DOC = ("NP EN 1992-1-1 §6.1 (flexão), §6.2.2/§6.2.3 (esforço transverso), §9.2.1/§9.2.2 (As mín./máx.) — valores usuais do Anexo Nacional português — a verificar")

CONCRETE = [
    {"key": "C20/25", "fck": 20},
    {"key": "C25/30", "fck": 25},
    {"key": "C30/37", "fck": 30},
    {"key": "C35/45", "fck": 35},
    {"key": "C40/50", "fck": 40},
    {"key": "C45/55", "fck": 45},
    {"key": "C50/60", "fck": 50},
]


def materials_catalog() -> dict:
    return {
        "version": VERSION,
        "concrete": CONCRETE,
        "steel": {"grade": "B500B", "fyk": 500, "es_mpa": ES_MPA},
        "factors": {"gamma_c": 1.5, "gamma_s": 1.15, "alpha_cc": 1.0},
        "note": "Valores usuais do Anexo Nacional português, editáveis. Nenhuma resistência validada — a verificar pelo engenheiro.",
    }


def _r(x: float, n: int = 2) -> float:
    return round(float(x), n)


def design_section(med_knm: float, ved_kn: float = 0.0, *, b_m: float, h_m: float, d_m: float,
                   d_prime_m: float = 0.05, fck: float = 25, fyk: float = 500,
                   gamma_c: float = 1.5, gamma_s: float = 1.15, alpha_cc: float = 1.0,
                   cot_theta: float = 2.5) -> dict:
    """Ferraillage d'une section rectangulaire sous M et V dimensionnants (ELU).

    Unités d'entrée : M en kN·m, V en kN, dimensions en m, résistances en MPa.
    Sorties d'acier en cm² (flexion) et cm²/m (effort tranchant).
    """
    if d_m <= 0 or d_m >= h_m:
        raise ValueError("A altura útil d deve estar estritamente entre 0 e h.")
    if fck > 50:
        raise ValueError("Este capítulo cobre os betões até C50/60 (diagrama retangular λ=0.8).")

    # Résistances de calcul
    fcd = alpha_cc * fck / gamma_c
    fyd = fyk / gamma_s
    fywd = fyk / gamma_s
    fctm = 0.30 * fck ** (2.0 / 3.0)
    eps_yd = fyd / ES_MPA

    # Conversions en N et mm
    b_mm, h_mm, d_mm, dp_mm = b_m * 1000, h_m * 1000, d_m * 1000, d_prime_m * 1000
    M_Nmm = med_knm * 1e6
    V_N = ved_kn * 1000.0

    # ---- Flexion ----
    warn_fx: list[str] = []
    mu = M_Nmm / (b_mm * d_mm ** 2 * fcd) if M_Nmm > 0 else 0.0
    xi_lim = EPS_CU3 / (EPS_CU3 + eps_yd)
    mu_lim = LAMBDA * xi_lim * (1 - LAMBDA * xi_lim / 2)

    as_comp_mm2 = 0.0
    sigma_sc = None
    if mu <= mu_lim:
        mode = "simple"
        alpha = 1.25 * (1 - math.sqrt(max(0.0, 1 - 2 * mu)))
        z_mm = d_mm * (1 - 0.4 * alpha)
        as_mm2 = M_Nmm / (z_mm * fyd) if z_mm > 0 else 0.0
    else:
        mode = "double"
        alpha = xi_lim
        z_mm = d_mm * (1 - 0.4 * xi_lim)
        m1 = mu_lim * b_mm * d_mm ** 2 * fcd            # repris par béton + As1
        as1 = m1 / (z_mm * fyd)
        dm = M_Nmm - m1                                  # repris par acier comprimé + As2
        x_mm = xi_lim * d_mm
        if dp_mm >= x_mm:
            warn_fx.append("Recobrimento d\' superior à altura comprimida x: hipótese de armadura comprimida inválida, rever a secção (a verificar).")
            sigma_sc = fyd
        else:
            eps_sc = EPS_CU3 * (x_mm - dp_mm) / x_mm
            sigma_sc = min(eps_sc * ES_MPA, fyd)
            if eps_sc < eps_yd:
                warn_fx.append("Aço comprimido não plastificado (σ\'sc < fyd): tensão reduzida aplicada (a verificar).")
        as2 = dm / ((d_mm - dp_mm) * fyd)
        as_comp_mm2 = dm / ((d_mm - dp_mm) * sigma_sc)
        as_mm2 = as1 + as2
        warn_fx.append("Momento > momento limite de secção simplesmente armada: armadura de compressão necessária.")

    as_min_mm2 = max(0.26 * fctm / fyk * b_mm * d_mm, 0.0013 * b_mm * d_mm)
    as_max_mm2 = 0.04 * b_mm * h_mm
    as_req_mm2 = max(as_mm2, as_min_mm2)
    if as_mm2 > as_max_mm2:
        warn_fx.append("As de flexão superior ao máximo 0,04·Ac: secção insuficiente (a verificar).")

    flexure = {
        "med_knm": _r(med_knm, 3), "mu": _r(mu, 4), "mu_lim": _r(mu_lim, 4), "mode": mode,
        "z_m": _r(z_mm / 1000, 4), "as_cm2": _r(as_mm2 / 100), "as_comp_cm2": _r(as_comp_mm2 / 100),
        "as_min_cm2": _r(as_min_mm2 / 100), "as_max_cm2": _r(as_max_mm2 / 100),
        "as_req_cm2": _r(as_req_mm2 / 100),
        "sigma_sc_mpa": _r(sigma_sc, 1) if sigma_sc is not None else None,
        "formula": "μ=M/(b·d²·fcd) ; α=1.25(1−√(1−2μ)) ; z=d(1−0.4α) ; As=M/(z·fyd) ; "
                   "si μ>μlim → armature double (As1+As2 tendue, As' comprimée).",
        "warnings": warn_fx,
    }

    # ---- Effort tranchant (§6.2) ----
    warn_v: list[str] = []
    k = min(1 + math.sqrt(200.0 / d_mm), 2.0)
    rho_l = min(as_req_mm2 / (b_mm * d_mm), 0.02)
    c_rdc = 0.18 / gamma_c
    v_min = 0.035 * k ** 1.5 * math.sqrt(fck)
    vrdc_stress = max(c_rdc * k * (100 * rho_l * fck) ** (1.0 / 3.0), v_min)
    vrdc_N = vrdc_stress * b_mm * d_mm

    z_v_mm = 0.9 * d_mm
    nu1 = 0.6 * (1 - fck / 250)
    needs = V_N > vrdc_N
    cot = max(1.0, min(cot_theta, 2.5))
    asw_s_mm = 0.0
    vrdmax_N = 1.0 * b_mm * z_v_mm * nu1 * fcd / (cot + 1 / cot)
    if needs:
        if V_N > vrdmax_N:
            # augmenter θ (réduire cotθ vers 1) pour relever V_Rd,max
            s = b_mm * z_v_mm * nu1 * fcd / V_N
            if s < 2.0:
                warn_v.append("Esforço transverso superior a V_Rd,max mesmo com θ=45°: secção/bw/fck insuficientes (a verificar).")
                cot = 1.0
            else:
                cot = (s + math.sqrt(s * s - 4)) / 2
                cot = max(1.0, min(cot, 2.5))
            vrdmax_N = 1.0 * b_mm * z_v_mm * nu1 * fcd / (cot + 1 / cot)
        asw_s_mm = V_N / (z_v_mm * fywd * cot)

    rho_w_min = 0.08 * math.sqrt(fck) / fyk
    asw_s_min_mm = rho_w_min * b_mm
    asw_s_req_mm = max(asw_s_mm, asw_s_min_mm)
    s_max_mm = 0.75 * d_mm

    shear = {
        "ved_kn": _r(ved_kn, 3), "vrdc_kn": _r(vrdc_N / 1000, 2), "needs_stirrups": needs,
        "vrdmax_kn": _r(vrdmax_N / 1000, 2), "cot_theta": _r(cot, 3), "k": _r(k, 3), "rho_l": _r(rho_l, 5),
        "asw_s_cm2_m": _r(asw_s_mm * 10), "asw_s_min_cm2_m": _r(asw_s_min_mm * 10),
        "asw_s_req_cm2_m": _r(asw_s_req_mm * 10), "s_max_m": _r(s_max_mm / 1000, 3),
        "formula": "V_Rd,c=[0.18/γc·k·(100·ρl·fck)^⅓]·bw·d ; se V_Ed>V_Rd,c → treliça : Asw/s=V_Ed/(z·fywd·cotθ), z=0.9d ; V_Rd,max=bw·z·ν1·fcd/(cotθ+tanθ).",
        "warnings": warn_v,
    }

    return {
        "version": VERSION,
        "inputs": {"b_m": _r(b_m, 3), "h_m": _r(h_m, 3), "d_m": _r(d_m, 4), "d_prime_m": _r(d_prime_m, 4),
                   "fck": fck, "fyk": fyk, "fcd_mpa": _r(fcd, 3), "fyd_mpa": _r(fyd, 2), "fctm_mpa": _r(fctm, 3),
                   "gamma_c": gamma_c, "gamma_s": gamma_s, "alpha_cc": alpha_cc},
        "flexure": flexure,
        "shear": shear,
        "source": SOURCE_DOC,
        "execution_ready": False,
        "warnings": warn_fx + warn_v,
    }


def _auto_provided(auto_design: dict, as_req_cm2: float, asw_s_req_cm2_m: float) -> dict:
    """Réinjecte les aciers CHOISIS par la chaîne automatique dans la vérif EN 1992.

    Ne recalcule pas l'acier nécessaire (fourni par EN 1992) : il compare l'acier
    RÉELLEMENT disposé par la chaîne automatique à l'acier nécessaire (flexion + cisaillement)
    pour un dossier BET unifié. Dispositions constructives toujours à vérifier.
    """
    phi = int(auto_design["diameter_mm"])
    n = int(auto_design["count"])
    as_prov = float(auto_design["as_provided_mm2"]) / 100.0  # mm² -> cm²
    longitudinal = {
        "bar_mm": phi, "count": n, "as_provided_cm2": _r(as_prov),
        "as_req_cm2": _r(as_req_cm2), "label": f"{n}Ø{phi}",
        "ok": as_prov + 1e-9 >= as_req_cm2,
        "note": "Aços escolhidos pela cadeia automática, reinjetados na verificação NP EN 1992."}
    stirrups = None
    s_mm = auto_design.get("stirrup_diameter_mm")
    if s_mm:
        asw_prov = float(auto_design.get("asw_provided_mm2_m", 0.0)) / 100.0  # mm²/m -> cm²/m
        s_adopt = float(auto_design.get("stirrup_spacing_mm", 0.0)) / 1000.0  # mm -> m
        stirrups = {
            "stirrup_mm": int(s_mm), "legs": 2, "s_adopt_m": _r(s_adopt, 3),
            "asw_s_prov_cm2_m": _r(asw_prov), "asw_s_req_cm2_m": _r(asw_s_req_cm2_m),
            "ok": asw_prov + 1e-9 >= asw_s_req_cm2_m,
            "label": f'Ø{int(s_mm)} (2 ramos) e={_r(s_adopt, 3)} m'}
    return {"version": VERSION, "origin": "automation", "longitudinal": longitudinal,
            "stirrups": stirrups, "execution_ready": False,
            "source": "Aços reinjetados da cadeia automática — disposições construtivas a verificar."}


def design_study(model: dict, result: dict, opts: dict, auto: dict | None = None) -> dict:
    """Lie l'enveloppe dimensionnante EN 1990 (M, V) à chaque poutre béton du modèle.

    Si `auto` (rapport de la chaîne automatique) est fourni ET à jour (même empreinte
    que le résultat gravitaire), les aciers CHOISIS par l'automatisation sont réinjectés
    dans la vérification EN 1992 à la place de la proposition Ø générique — dossier BET unifié.
    """
    from engines import structuro_eurocode as eurocode
    from engines import structuro_rebar_scheme as rebar_scheme
    env = eurocode.design_envelope(result or {})
    by_id = {e.get("id"): e for e in (model or {}).get("elements", [])}
    cover = float(opts.get("cover_m", 0.05))
    auto_designs: dict[str, dict] = {}
    fresh = bool(auto) and auto.get("output_input_hash") and (result or {}).get("input_hash") \
        and auto["output_input_hash"] == result.get("input_hash")
    if fresh:
        auto_designs = {d["element_id"]: d for d in auto.get("designs", []) if d.get("kind") == "beam"}
    rows: list[dict] = []
    for ee in env.get("elements", []):
        if ee.get("kind") != "beam":
            continue
        rid = ee["id"]
        el = by_id.get(rid) or {}
        m = (ee.get("uls") or {}).get("moment_knm")
        v = (ee.get("uls") or {}).get("shear_kn")
        if not m:
            rows.append({"id": rid, "status": "no_envelope",
                         "message": "Gere primeiro as combinações NP EN 1990 (momento condicionante em falta)."})
            continue
        b, h = el.get("width_m"), el.get("height_m")
        if not b or not h:
            rows.append({"id": rid, "status": "missing_section",
                         "message": "Largura e altura da viga obrigatórias no modelo."})
            continue
        d = round(h - cover, 4)
        if d <= 0:
            rows.append({"id": rid, "status": "missing_section",
                         "message": "Recobrimento superior à altura: altura útil d inválida."})
            continue
        try:
            design = design_section(
                med_knm=m["value"], ved_kn=(v or {}).get("value", 0.0),
                b_m=b, h_m=h, d_m=d, d_prime_m=cover,
                fck=float(opts.get("fck", 25)), fyk=float(opts.get("fyk", 500)),
                gamma_c=float(opts.get("gamma_c", 1.5)), gamma_s=float(opts.get("gamma_s", 1.15)),
                alpha_cc=float(opts.get("alpha_cc", 1.0)), cot_theta=float(opts.get("cot_theta", 2.5)))
        except ValueError as exc:
            rows.append({"id": rid, "status": "invalid", "message": str(exc)})
            continue
        ad = auto_designs.get(rid)
        if ad:
            scheme = _auto_provided(ad, design["flexure"]["as_req_cm2"], design["shear"]["asw_s_req_cm2_m"])
            reinforcement_source = "automation"
            provided_ok = scheme["longitudinal"]["ok"] and (scheme["stirrups"]["ok"] if scheme["stirrups"] else True)
        else:
            try:
                scheme = rebar_scheme.scheme(
                    design["flexure"]["as_req_cm2"], design["shear"]["asw_s_req_cm2_m"],
                    bar_mm=int(opts.get("bar_mm", 16)), stirrup_mm=int(opts.get("stirrup_mm", 8)),
                    legs=int(opts.get("legs", 2)), s_max_m=design["shear"]["s_max_m"])
            except ValueError:
                scheme = None
            reinforcement_source = "proposal"
            provided_ok = None
        rows.append({"id": rid, "status": "ok", "b_m": _r(b, 3), "h_m": _r(h, 3), "d_m": d,
                     "med_knm": m["value"], "med_case": m.get("label"),
                     "ved_kn": (v or {}).get("value"), "ved_case": (v or {}).get("label"),
                     "design": design, "scheme": scheme,
                     "reinforcement_source": reinforcement_source, "provided_ok": provided_ok})
    note = ("Aço NECESSÁRIO proveniente da envolvente NP EN 1990. Apenas esforços; altura útil d = h − recobrimento (hipótese). Nenhuma disposição construtiva, amarração, fendilhação nem flecha verificadas. A validar pelo engenheiro.")
    if auto_designs:
        note += (" As vigas marcadas «auto» comparam os aços ESCOLHIDOS pela cadeia automática com o aço necessário NP EN 1992 (processo de engenharia unificado).")
    return {"version": VERSION, "elements": rows, "execution_ready": False,
            "reinjected_from_automation": bool(auto_designs), "note": note}
