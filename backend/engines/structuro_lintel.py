"""EN 1992/1993 — Dimensionnement INDICATIF d'un linteau de reprise d'ouverture en mur porteur.

Déterministe, méthodologie publique. Charge au-dessus de l'ouverture par effet de voûte
(triangle de maçonnerie, angle éditable) OU modèle rectangulaire conservateur ; poutre
simplement appuyée (M, V exacts, EN 1990 : 1.35G+1.5Q, ELS caract. et quasi-permanent).
Propose la solution acier la plus légère qui passe (1 ou 2 profilés IPE/HEA/HEB, catalogue
EN 10365) ET une section béton armé (réutilise structuro_rebar.section_design), puis désigne
la moins chère (coûts matière éditables). Flèche (L/limite) et appui sur maçonnerie (about)
vérifiés. NON EXÉCUTOIRE — maintien latéral par la maçonnerie supposé ; à valider par l'ingénieur.
"""
from __future__ import annotations

import math

from engines import structuro_profiles as profiles
from engines.structuro_ec3 import CURVES as LT_CURVES, _chi as _chi_lt, mcr_elastic
from engines.structuro_rebar import Materials, Section, section_design

VERSION = "lintel-0.2.0"
E_STEEL = 210000.0  # MPa
STEEL_DENSITY = 7850.0  # kg/m³
DISCLAIMER = ("Dimensionamento INDICATIVO, não executório. Resistência da alvenaria, nembos, escoramento provisório e disposições construtivas a validar pelo engenheiro. A encurvadura lateral só é verificada se o travamento lateral pela alvenaria estiver desativado; caso contrário assume-se χLT=1.")


def _r(x, n=2):
    return round(float(x), n)


def _mv(components, fg, fq):
    """M (kN·m) à mi-portée et V (kN) à l'appui d'une poutre bi-appuyée, charges superposées."""
    m = v = 0.0
    for c in components:
        f = fg if c["nature"] == "G" else fq
        if f == 0:
            continue
        if c["type"] == "udl":          # charge uniforme w (kN/m)
            m += f * c["value"] * c["L"] ** 2 / 8.0
            v += f * c["value"] * c["L"] / 2.0
        else:                            # triangle symétrique, charge totale W (kN)
            m += f * c["value"] * c["L"] / 6.0
            v += f * c["value"] / 2.0
    return m, v


def _defl_mm(components, fg, fq, i_mm4, e_mpa, l_mm):
    """Flèche à mi-portée (mm). 1 kN/m == 1 N/mm ; W en kN -> ×1000 N."""
    if i_mm4 <= 0:
        return float("inf")
    d = 0.0
    for c in components:
        f = fg if c["nature"] == "G" else fq
        if f == 0:
            continue
        if c["type"] == "udl":
            w = f * c["value"]                       # N/mm
            d += 5.0 * w * l_mm ** 4 / (384.0 * e_mpa * i_mm4)
        else:
            w_tot = f * c["value"] * 1000.0          # N
            d += w_tot * l_mm ** 3 / (60.0 * e_mpa * i_mm4)
    return d


def _loads(opts):
    """Construit les composantes de charge sur le linteau + trace le modèle retenu."""
    L = float(opts["clear_span_m"])
    t = float(opts.get("wall_thickness_m", 0.2))
    gamma = float(opts.get("masonry_unit_weight_kn_m3", 20.0))
    w_face = gamma * t                                           # kN/m² de face de maçonnerie
    h_mas = float(opts.get("masonry_height_above_m", 10.0))
    model = opts.get("load_model", "arching")
    theta = float(opts.get("arch_angle_deg", 60.0))
    comps, notes = [], []
    h_apex = (L / 2.0) * math.tan(math.radians(theta))
    if model == "arching" and h_mas + 1e-9 >= h_apex:
        w_tri = 0.5 * L * h_apex * w_face                        # poids total du triangle (kN)
        comps.append({"name": f'Alvenaria (arco {theta:g}°, triangle h={_r(h_apex)} m)',
                      "nature": "G", "type": "tri", "value": w_tri, "L": L})
        masonry_model = "arching"
    else:
        if model == "arching":
            notes.append(f'Altura de alvenaria ({_r(h_mas)} m) < topo do arco ({_r(h_apex)} m): arco incompleto, recurso a carga retangular (do lado da segurança).')
        h_rect = min(h_mas, 10.0)
        comps.append({"name": f'Alvenaria retangular (h={_r(h_rect)} m)', "nature": "G",
                      "type": "udl", "value": h_rect * w_face, "L": L})
        masonry_model = "rectangular"
    g_line = float(opts.get("permanent_line_kn_m", 0.0))
    q_line = float(opts.get("variable_line_kn_m", 0.0))
    if g_line:
        comps.append({"name": "Cargas permanentes suportadas (pavimentos/cobertura)", "nature": "G",
                      "type": "udl", "value": g_line, "L": L})
    if q_line:
        comps.append({"name": "Sobrecargas de utilização suportadas", "nature": "Q",
                      "type": "udl", "value": q_line, "L": L})
    return L, comps, masonry_model, notes


def _steel(opts, L, comps, m_ed, v_ed, psi2, load_kind="udl"):
    grade = opts.get("steel_grade", "S235")
    fy = profiles.GRADES.get(grade, 235)
    gm0 = float(opts.get("gamma_m0", 1.0))
    gm1 = float(opts.get("gamma_m1", 1.0))
    restrained = bool(opts.get("lateral_restraint_masonry", True))
    c1 = float(opts.get("ltb_c1") or (1.12 if load_kind == "udl" else 1.13))
    families = set(opts.get("steel_families") or ["IPE", "HEA", "HEB"])
    max_n = int(opts.get("max_profiles", 2))
    lim_t = float(opts.get("deflection_limit_total", 300))
    lim_q = float(opts.get("deflection_limit_qp", 500))
    price = float(opts.get("steel_eur_per_kg", 3.0))
    l_mm = L * 1000.0
    best = None
    for name, p in profiles.PROFILE_DATA.items():
        if p["family"] not in families:
            continue
        if not restrained and p.get("mono"):
            continue  # section mono-symétrique (U) : Mcr non calculable automatiquement
        cls = profiles.classify(name, fy, "bending")["section_class"]
        if cls == 4:
            continue
        w_mod = p["Wpl"] if cls in (1, 2) else p["Wel"]          # cm³
        for n in range(1, max_n + 1):
            mrd = w_mod * n * fy / (1000.0 * gm0)                # kN·m — résistance de section
            vrd = p["Av"] * n * fy / (10.0 * math.sqrt(3.0) * gm0)  # kN
            i_mm4 = p["Iy"] * n * 1e4
            # Déversement EN 1993-1-1 §6.3.2 (par profilé isolé, groupe = n×Mb,Rd)
            ltb = None
            mb_rd = mrd
            if restrained:
                mb_rd = mrd
            else:
                mcr = mcr_elastic(p["Iz"], p["It"], p["Iw"], L, c1)   # kN·m, profilé unique
                myrk = w_mod * fy / 1000.0                            # kN·m, profilé unique
                lam_lt = math.sqrt(myrk / mcr) if mcr > 0 else 0.0
                curve_lt = profiles.buckling_curves(name, fy)["lt"]
                chi_lt = _chi_lt(lam_lt, LT_CURVES.get(curve_lt, 0.21))
                mb_rd = chi_lt * w_mod * n * fy / (1000.0 * gm1)     # kN·m, groupe de n profilés
                ltb = {"mcr_knm": _r(mcr), "lambda_lt": _r(lam_lt, 3), "chi_lt": _r(chi_lt, 3),
                       "mb_rd_knm": _r(mb_rd), "curve": curve_lt, "c1": c1}
            d_char = _defl_mm(comps, 1.0, 1.0, i_mm4, E_STEEL, l_mm)
            d_qp = _defl_mm(comps, 1.0, psi2, i_mm4, E_STEEL, l_mm)
            ok = (m_ed <= mb_rd and v_ed <= vrd and d_char <= l_mm / lim_t and d_qp <= l_mm / lim_q)
            if not ok:
                continue
            mass = p["A"] * 1e-4 * STEEL_DENSITY * L * n            # kg
            cand = {"profile": name, "family": p["family"], "count": n, "grade": grade,
                    "section_class": cls, "mrd_knm": _r(mrd), "vrd_kn": _r(vrd),
                    "mb_rd_knm": _r(mb_rd), "lateral_restraint": restrained, "ltb": ltb,
                    "defl_char_mm": _r(d_char, 1), "defl_qp_mm": _r(d_qp, 1),
                    "defl_char_limit_mm": _r(l_mm / lim_t, 1), "defl_qp_limit_mm": _r(l_mm / lim_q, 1),
                    "mass_kg": _r(mass, 1), "cost_eur": _r(mass * price, 0),
                    "label": f"{n}×{name}" if n > 1 else name}
            if best is None or mass < best["mass_kg"]:
                best = cand
    if best is None:
        msg = ("Nenhum perfil do catálogo verifica; aumente o número de perfis, a classe do aço ou reduza o vão.")
        if not restrained:
            msg += " A encurvadura lateral (travamento lateral desativado) é muitas vezes condicionante: "
            msg += "preveja um travamento ou perfis mais compactos (HEA/HEB)."
        return {"status": "no_solution", "message": msg}
    note = ("Perfil mais leve que verifica flexão (Wpl/Wel·fy/γM0), esforço transverso (Av) e flecha. ")
    note += ("Encurvadura lateral verificada (§6.3.2): travamento lateral pela alvenaria desativado, Mcr automático."
             if not restrained else
             "Encurvadura lateral não verificada (travamento lateral pela alvenaria assumido, χLT=1).")
    return {"status": "ok", **best, "note": note}


def _rc(opts, L, comps, m_ed, v_ed, psi2):
    b_mm = float(opts.get("rc_width_m") or opts.get("wall_thickness_m") or 0.2) * 1000.0
    cover = float(opts.get("cover_m", 0.03)) * 1000.0
    bar = float(opts.get("bar_mm", 12))
    fck = float(opts.get("fck", 25))
    mat = Materials(fck_mpa=fck, fyk_mpa=float(opts.get("fyk", 500)),
                    fctm_mpa=0.30 * fck ** (2.0 / 3.0), gamma_c=float(opts.get("gamma_c", 1.5)),
                    gamma_s=float(opts.get("gamma_s", 1.15)), alpha_cc=float(opts.get("alpha_cc", 1.0)),
                    source="Materiais usuais do Anexo Nacional português — a verificar")
    cot = float(opts.get("cot_theta", 2.5))
    sd_limit = float(opts.get("rc_span_depth_limit", 20.0))
    fixed_h = opts.get("rc_height_m")
    heights = [float(fixed_h) * 1000.0] if fixed_h else [h for h in range(200, 851, 50)]
    a_m = float(opts.get("bearing_length_m", 0.2))
    price_c = float(opts.get("concrete_eur_per_m3", 180.0))
    price_s = float(opts.get("rebar_eur_per_kg", 2.0))
    for h in heights:
        d = h - cover - bar / 2.0
        if d <= 10:
            continue
        sec = Section(id="LINT", kind="beam", b_mm=b_mm, h_mm=h, d_mm=d, med_knm=m_ed,
                      ved_kn=v_ed, ned_kn=0.0, torsion_knm=0.0, materials=mat,
                      as_provided_mm2=None, cot_theta=cot, source="Padieira de betão armado — a verificar", case="ELU")
        res = section_design(sec)
        as_req = res.get("as_required_mm2")
        if as_req is None or res["status"] == "out_of_scope":
            continue
        if as_req > res.get("as_max_mm2", 0):
            continue
        if (L * 1000.0 / d) > sd_limit and not fixed_h:
            continue                                            # pré-dimensionnement flèche (portée/hauteur utile)
        asw = res.get("asw_required_mm2_m", 0.0)
        vol = (b_mm / 1000.0) * (h / 1000.0) * (L + 2 * a_m)    # m³ (y compris abouts)
        rebar_kg = (as_req * 1e-6 * (L + 2 * a_m) * STEEL_DENSITY) * 1.3  # +30 % étriers/recouvrements (estimé)
        cost = vol * price_c + rebar_kg * price_s
        return {"status": "ok", "b_mm": _r(b_mm, 0), "h_mm": _r(h, 0), "d_mm": _r(d, 0),
                "as_required_cm2": _r(as_req / 100.0), "as_min_cm2": _r(res.get("as_min_mm2", 0) / 100.0),
                "asw_required_cm2_m": _r(asw / 100.0), "bar_mm": int(bar),
                "span_depth_ratio": _r(L * 1000.0 / d, 1), "span_depth_limit": sd_limit,
                "concrete_m3": _r(vol, 3), "rebar_kg": _r(rebar_kg, 1), "cost_eur": _r(cost, 0),
                "fck": fck, "label": f"BA {int(b_mm)}×{int(h)} mm — As {_r(as_req / 100.0)} cm²",
                "note": "Secção mínima de betão armado que verifica a flexão EN 1992 + pré-dimensionamento da flecha vão/altura útil ≤ limite. Armaduras de extremidade/amarração a pormenorizar."}
    return {"status": "no_solution", "message": "Nenhuma secção de betão armado razoável verifica; aumente a altura, a largura ou a classe do betão."}


def _anchorage(phi_mm, fck, fyk, gamma_c, gamma_s):
    """Longueurs d'ancrage droite/crochet des barres de flexion aux appuis (§8.4)."""
    fctm = 0.30 * fck ** (2.0 / 3.0)
    fctd = 1.0 * (0.7 * fctm) / gamma_c
    fbd = 2.25 * fctd                                   # bonne adhérence, Ø ≤ 32
    fyd = fyk / gamma_s
    lb_rqd = (phi_mm / 4.0) * (fyd / fbd)
    lb_min = max(10.0 * phi_mm, 100.0)
    return {"fbd_mpa": _r(fbd), "lb_rqd_mm": _r(lb_rqd, 0),
            "straight_mm": _r(max(lb_rqd, lb_min), 0),
            "hook_mm": _r(max(0.7 * lb_rqd, lb_min), 0),
            "note": "Amarração dos varões inferiores nos apoios (§8.4); gancho α1=0,7. Armaduras de espera/superiores a pormenorizar."}


def _bearing_plate(v_ed, t_m, allow_mpa, seat_m):
    """Platine de répartition indicative sous linteau acier (diffusion sur la maçonnerie)."""
    allow_kpa = allow_mpa * 1000.0
    a_req = v_ed / allow_kpa if allow_kpa > 0 else float("inf")   # m²
    b_p = t_m
    l_p = max(a_req / b_p if b_p > 0 else 0.0, seat_m, 0.10)
    sigma = v_ed / (b_p * l_p) if b_p > 0 and l_p > 0 else float("inf")  # kPa
    c = max((l_p - seat_m) / 2.0, 0.02)                           # porte-à-faux (m)
    fyp = 235.0
    t_p = c * math.sqrt(3.0 * (sigma / 1000.0) / fyp) * 1000.0    # mm
    t_p = max(8.0, 2.0 * math.ceil(t_p / 2.0))                    # arrondi pair ≥ 8 mm
    return {"width_mm": _r(b_p * 1000, 0), "length_mm": _r(l_p * 1000, 0), "thickness_mm": _r(t_p, 0),
            "sigma_kpa": _r(sigma, 1), "allow_kpa": _r(allow_kpa, 1),
            "status": "ok" if sigma <= allow_kpa else "fails_check",
            "note": "Chapa de apoio indicativa: área ≥ reação ELU / resistência da alvenaria; espessura pela flexão da consola. Soldaduras, reforços e selagens a estudar."}


def lintel_design(opts: dict) -> dict:
    """Dimensionnement indicatif d'un linteau de reprise d'ouverture (acier et/ou BA)."""
    L, comps, masonry_model, notes = _loads(opts)
    psi2 = float(opts.get("psi2", 0.3))
    m_g, v_g = _mv(comps, 1.0, 0.0)
    m_q, v_q = _mv(comps, 0.0, 1.0)
    m_ed, v_ed = _mv(comps, 1.35, 1.5)
    m_char = m_g + m_q
    material = opts.get("material", "both")
    load_kind = "udl" if all(c["type"] == "udl" for c in comps) else "tri"
    steel = _steel(opts, L, comps, m_ed, v_ed, psi2, load_kind) if material in ("steel", "both") else None
    rc = _rc(opts, L, comps, m_ed, v_ed, psi2) if material in ("rc", "both") else None
    # Appui sur maçonnerie (about)
    t = float(opts.get("wall_thickness_m", 0.2))
    a = float(opts.get("bearing_length_m", 0.2))
    allow_mpa = float(opts.get("masonry_comp_strength_mpa", 0.6))
    allow_kpa = allow_mpa * 1000.0
    sigma = v_ed / (a * t) if a > 0 and t > 0 else float("inf")
    a_req = v_ed / (allow_kpa * t) if allow_kpa > 0 and t > 0 else float("inf")
    a_adopt = max(a, a_req, 0.10)
    bearing = {"reaction_kn": _r(v_ed), "bearing_length_m": a, "wall_thickness_m": t,
               "sigma_kpa": _r(sigma, 1), "allow_kpa": _r(allow_kpa, 1),
               "required_length_m": _r(a_req, 3), "adopted_length_m": _r(a_adopt, 3),
               "status": "ok" if sigma <= allow_kpa else "fails_check",
               "note": "Pressão de apoio = reação ELU / (entrega × espessura da parede) comparada com a resistência introduzida da alvenaria. Entrega adotada = máx(introduzida, necessária, 0,10 m)."}
    # Détails d'exécution BA (crochets/ancrages) + platine acier
    if rc and rc.get("status") == "ok":
        rc["detailing"] = {"bearing": {"adopted_length_m": _r(a_adopt, 3)},
                           "anchorage": _anchorage(float(opts.get("bar_mm", 12)), rc["fck"],
                                                   float(opts.get("fyk", 500)), float(opts.get("gamma_c", 1.5)),
                                                   float(opts.get("gamma_s", 1.15)))}
    if steel and steel.get("status") == "ok":
        steel["bearing_plate"] = _bearing_plate(v_ed, t, allow_mpa, a_adopt)
    # Recommandation économique
    options = []
    if steel and steel["status"] == "ok":
        options.append(("steel", steel["cost_eur"]))
    if rc and rc["status"] == "ok":
        options.append(("rc", rc["cost_eur"]))
    recommended = None
    if options:
        recommended = min(options, key=lambda o: (o[1], 0 if o[0] == "steel" else 1))[0]
    reco = None
    if recommended:
        reco = {"material": recommended,
                "reason": "Custo de material estimado mais baixo" + (" (empate → aço)" if len(options) == 2 and
                          options[0][1] == options[1][1] else ""),
                "label": (steel if recommended == "steel" else rc)["label"],
                "cost_eur": (steel if recommended == "steel" else rc)["cost_eur"]}
    reactions = {"g_kn": _r(v_g), "q_kn": _r(v_q), "ed_kn": _r(v_ed),
                 "note": "Reação característica por apoio (metade da carga), a reintroduzir como carga pontual em cada nembo para fechar a descida de cargas."}
    geometry = {"clear_span_m": _r(L, 3), "wall_thickness_m": t, "bearing_m": _r(a_adopt, 3),
                "masonry_model": masonry_model,
                "recommended": recommended, "steel": steel, "rc": rc}
    return {"version": VERSION, "execution_ready": False, "clear_span_m": _r(L, 3),
            "load_model": masonry_model, "notes": notes,
            "actions": {"m_g_knm": _r(m_g), "m_q_knm": _r(m_q), "v_g_kn": _r(v_g), "v_q_kn": _r(v_q),
                        "m_ed_knm": _r(m_ed), "v_ed_kn": _r(v_ed), "m_char_knm": _r(m_char),
                        "combination": "ELU 1.35G+1.5Q ; flecha ELS característica e quase-permanente (ψ2)",
                        "components": [{"name": c["name"], "nature": c["nature"], "type": c["type"],
                                        "value": _r(c["value"], 2)} for c in comps]},
            "steel": steel, "rc": rc, "bearing": bearing, "reactions": reactions,
            "recommendation": reco, "geometry": geometry, "note": DISCLAIMER}
