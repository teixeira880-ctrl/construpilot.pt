"""Dalles pleines BA portant dans une ou deux directions — méthode française usuelle (déterministe).

Méthode (pratique BET française, cohérente EN 1992-1-1 + AN FR) :
  • ρ = lx/ly (lx = petite portée). ρ < 0,40 → dalle portant dans un seul sens : M0x = pu·lx²/8.
  • ρ ≥ 0,40 → panneau articulé sur 4 côtés, coefficients de Pigeaud simplifiés (BAEL 91 Annexe E3,
    ν = 0 à l'ELU, ν = 0,2 à l'ELS) : M0x = μx·p·lx² ; M0y = μy·M0x avec μy ≥ 0,25.
  • Continuité (règle forfaitaire) : en travée Mt + (Mw + Me)/2 ≥ 1,25·M0, avec
      appui continu sur panneau voisin      : Ma = 0,50·M0 (pris en compte dans la règle),
      appui de rive sur voile/poutre (« rive »): Ma = 0,15·M0 minimum constructif — NON déduit de la
        travée (sécuritaire, pratique des logiciels de BET : Mt = 1,25·M0 pour un panneau de rive),
      bord libre                              : Ma = 0.
  • Aciers : flexion simple EN 1992-1-1 §6.1 (structuro_ec2.design_section), As,min §9.3.1.1.
  • Treillis soudés : catalogue ADETS (sections principales, valeurs à confirmer fournisseur).
  • Flèche : vérification simplifiée L/d EN 1992-1-1 §7.4.2 (éq. 7.16a/b), K selon Tableau 7.4N,
    correction As,prov/As,req ≤ 1,5 (§7.4.2(2)) et 7/L si L > 7 m.

Toutes les valeurs restent un PRÉ-DIMENSIONNEMENT à viser par l'ingénieur ; execution_ready = False.
Référence de validation : notes « Dalle EC2 » du BET CONSTRUIRE (affaire 25-029), tests dédiés.
"""
from __future__ import annotations

import math

from engines import structuro_ec2 as ec2

VERSION = "slab2way-0.1.0"

# BAEL 91 Annexe E3 — ρ : (μx ELU ν=0, μy ELU ν=0, μx ELS ν=0,2, μy ELS ν=0,2)
MU_TABLE = [
    (0.40, 0.1101, 0.2500, 0.1121, 0.2854),
    (0.45, 0.1036, 0.2500, 0.1063, 0.3234),
    (0.50, 0.0966, 0.2500, 0.1000, 0.3671),
    (0.55, 0.0894, 0.2500, 0.0936, 0.4150),
    (0.60, 0.0822, 0.2948, 0.0870, 0.4672),
    (0.65, 0.0751, 0.3613, 0.0805, 0.5235),
    (0.70, 0.0684, 0.4320, 0.0743, 0.5817),
    (0.75, 0.0621, 0.5105, 0.0684, 0.6447),
    (0.80, 0.0561, 0.5959, 0.0628, 0.7111),
    (0.85, 0.0506, 0.6864, 0.0576, 0.7794),
    (0.90, 0.0456, 0.7834, 0.0528, 0.8502),
    (0.95, 0.0410, 0.8875, 0.0483, 0.9236),
    (1.00, 0.0368, 1.0000, 0.0441, 1.0000),
]

# Treillis soudés ADETS (section principale cm²/m) — catalogue usuel, À CONFIRMER fournisseur.
MESHES = [
    ("ST10", 1.19), ("ST15C", 1.42), ("ST20", 1.89), ("ST10+PAF10", 2.38), ("ST25", 2.57), ("ST25C", 2.57),
    ("ST35", 3.85), ("ST40C", 3.85), ("ST50", 5.03), ("ST50C", 5.03), ("ST60", 6.36), ("ST65C", 6.36),
]

EDGE_TYPES = ("rive", "continu", "libre")
SUPPORT_COEF = {"rive": 0.15, "continu": 0.50, "libre": 0.0}


def mu_coefficients(rho: float) -> dict:
    """Interpolation linéaire du tableau BAEL E3."""
    if rho < 0.40:
        return {"one_way": True}
    rho = min(rho, 1.0)
    for a, b in zip(MU_TABLE, MU_TABLE[1:]):
        if a[0] <= rho <= b[0]:
            t = (rho - a[0]) / (b[0] - a[0])
            vals = [a[i] + t * (b[i] - a[i]) for i in range(1, 5)]
            return {"one_way": False, "mux_elu": vals[0], "muy_elu": max(vals[1], 0.25),
                    "mux_els": vals[2], "muy_els": max(vals[3], 0.25)}
    raise ValueError("ρ hors tableau")


def choose_mesh(as_req_cm2: float) -> dict:
    for name, a in MESHES:
        if a + 1e-9 >= as_req_cm2:
            return {"type": "treillis", "label": name, "as_cm2_m": a}
    # au-delà du plus fort treillis : barres HA
    for dia in (10, 12, 14, 16):
        for s in (20, 15, 12.5, 10):
            a = math.pi * dia ** 2 / 4 / 100 * 100 / s
            if a + 1e-9 >= as_req_cm2:
                return {"type": "barres", "label": f"HA{dia} e={s:g}", "as_cm2_m": round(a, 2)}
    return {"type": "barres", "label": "a rever (espessura insuficiente)", "as_cm2_m": None}


def k_factor(edges: dict, one_way: bool) -> float:
    """EN 1992-1-1 Tableau 7.4N. Dalle sur 4 côtés appuyés : 1,5 (pratique BET, panneau de rive
    portant dans 2 directions) ; 3 côtés : 1,3 ; dalle un seul sens : 1,0 / 1,3 / 1,5 selon continuité."""
    supported = [t for t in edges.values() if t != "libre"]
    n_cont = sum(1 for t in edges.values() if t == "continu")
    if one_way:
        return 1.5 if n_cont >= 2 else (1.3 if n_cont == 1 else 1.0)
    if len(supported) >= 4:
        return 1.5
    if len(supported) == 3:
        return 1.3
    return 1.0


def ld_check(span_m: float, d_m: float, as_req_cm2: float, as_prov_cm2: float, fck: float, K: float,
             fragile_partitions: bool = False) -> dict:
    """Flèche par élancement limite, EN 1992-1-1 §7.4.2 (7.16a/b).
    Le facteur 7/L (§7.4.2(2)) ne s'applique que si la dalle porte des cloisons fragiles et L > 7 m."""
    rho0 = math.sqrt(fck) * 1e-3
    rho = max(as_req_cm2 * 1e-4 / (1.0 * d_m), 1e-6)
    if rho <= rho0:
        base = 11 + 1.5 * math.sqrt(fck) * rho0 / rho + 3.2 * math.sqrt(fck) * (rho0 / rho - 1) ** 1.5
    else:   # éq. 7.16b avec ρ' = 0
        base = 11 + 1.5 * math.sqrt(fck) * rho0 / rho
    corr = min(as_prov_cm2 / as_req_cm2, 1.5) if as_req_cm2 > 0 and as_prov_cm2 else 1.0
    lim = K * base * corr * (7.0 / span_m if (fragile_partitions and span_m > 7.0) else 1.0)
    actual = span_m / d_m
    return {"l_over_d": round(actual, 2), "limit": round(lim, 2), "K": K, "correction": round(corr, 3),
            "ok": actual <= lim, "rho": round(rho, 5), "rho0": rho0,
            "formula": "L/d ≤ K[11 + 1,5√fck·ρ0/ρ + 3,2√fck(ρ0/ρ − 1)^1,5] × As,prov/As,req (§7.4.2)"}


def design(lx: float, ly: float, h: float, g2_kn_m2: float, q_kn_m2: float, edges: dict | None = None,
           *, fck: float = 25.0, fyk: float = 500.0, cover_m: float = 0.025, d_m: float | None = None,
           d_defl_m: float | None = None, density: float = 25.0, gamma_g: float = 1.35, gamma_q: float = 1.5,
           psi2: float = 0.3, fragile_partitions: bool = False) -> dict:
    """Dalle rectangulaire lx × ly (m), épaisseur h (m), charges G2 et Q (kN/m²).

    edges : {"x0": type, "x1": type, "y0": type, "y1": type} — côtés perpendiculaires à x (x0/x1, portée lx)
    et à y (y0/y1, portée ly) ; types : « rive » (voile/poutre de rive), « continu », « libre ».
    d_m : hauteur utile flexion (défaut h − enrobage − 5 mm) ; d_defl_m : hauteur utile pour L/d (défaut d_m).
    """
    if lx <= 0 or ly <= 0 or h <= 0:
        raise ValueError("Dimensões inválidas")
    if lx > ly:
        raise ValueError("lx deve ser o vão menor")
    edges = {"x0": "rive", "x1": "rive", "y0": "rive", "y1": "rive", **(edges or {})}
    if any(t not in EDGE_TYPES for t in edges.values()):
        raise ValueError(f'Tipo de bordo desconhecido (esperado: {EDGE_TYPES})')
    d = d_m if d_m is not None else round(h - cover_m - 0.005, 4)
    d_defl = d_defl_m if d_defl_m is not None else d
    g = h * density + g2_kn_m2
    pu = gamma_g * g + gamma_q * q_kn_m2
    ps = g + q_kn_m2
    pqp = g + psi2 * q_kn_m2
    rho = lx / ly
    mu = mu_coefficients(rho)
    if mu["one_way"]:
        m0x, m0y = pu * lx ** 2 / 8, 0.0
        m0x_s, m0x_qp = ps * lx ** 2 / 8, pqp * lx ** 2 / 8
    else:
        m0x = mu["mux_elu"] * pu * lx ** 2
        m0y = mu["muy_elu"] * m0x
        m0x_s = mu["mux_els"] * ps * lx ** 2
        m0x_qp = mu["mux_els"] * pqp * lx ** 2

    def span_moment(m0, e1, e2):
        cont = [SUPPORT_COEF[e] if e == "continu" else 0.0 for e in (e1, e2)]
        return max(1.25 * m0 - (cont[0] + cont[1]) / 2 * m0, 0.75 * m0) if m0 else 0.0

    # x : portée lx, appuis x0/x1 ; y : portée ly, appuis y0/y1
    mtx = span_moment(m0x, edges["x0"], edges["x1"])
    mty = span_moment(m0y, edges["y0"], edges["y1"])
    m_sup = max(m0x, m0y)            # appuis : référence au plus grand M0 (règle usuelle)
    supports = {k: round(SUPPORT_COEF[t] * m_sup, 3) for k, t in edges.items()}

    def steel(m):
        if m <= 0:
            return 0.0, None
        r = ec2.design_section(m, 0.0, b_m=1.0, h_m=h, d_m=d, fck=fck, fyk=fyk)
        return r["flexure"]["as_cm2"], r["flexure"]
    fctm = 0.30 * fck ** (2 / 3)
    as_min = max(0.26 * fctm / fyk, 0.0013) * 1.0 * d * 1e4          # cm²/m
    asx, fx = steel(mtx)
    asy, fy = steel(mty)
    as_x = max(asx, as_min)
    # sens secondaire : ≥ 20 % du principal (§9.3.1.1(2)) et ≥ As,min
    as_y = max(asy, 0.2 * as_x, as_min if not mu["one_way"] else 0.0)
    mesh_x = choose_mesh(as_x)
    mesh_y = choose_mesh(as_y)
    sup_out = {}
    for k, m in supports.items():
        if edges[k] == "libre":
            sup_out[k] = {"type": "libre", "m_knm": 0.0, "as_req_cm2_m": 0.0, "mesh": None}
            continue
        a, _ = steel(m)
        req = max(a, as_min)
        span = lx if k.startswith("x") else ly
        sup_out[k] = {"type": edges[k], "m_knm": round(-m, 3), "as_req_cm2_m": round(req, 2),
                      "mesh": choose_mesh(req), "length_from_face_m": round(max(0.2 * span, 0.25 * lx), 2)}
    # effort tranchant (bande de 1 m, réaction maximale, BAEL E3 : V = pu·lx/2 · 1/(1+ρ/2))
    v = pu * lx / 2 / (1 + rho / 2) if not mu["one_way"] else pu * lx / 2
    vrd = ec2.design_section(max(mtx, 1e-6), v, b_m=1.0, h_m=h, d_m=d, fck=fck, fyk=fyk)["shear"]
    K = k_factor(edges, mu["one_way"])
    ld = ld_check(lx, d_defl, as_x, mesh_x["as_cm2_m"] or as_x, fck, K, fragile_partitions)
    warnings = []
    if not ld["ok"]:
        warnings.append(f"Esbelteza L/d = {ld['l_over_d']} > {ld['limit']}: cálculo detalhado da flecha necessário (§7.4.3) ou espessura a aumentar.")
    if v > vrd["vrdc_kn"]:
        warnings.append("V_Ed > V_Rd,c: armaduras de esforço transverso ou espessura a rever.")
    return {
        "version": VERSION, "execution_ready": False,
        "inputs": {"lx": lx, "ly": ly, "h": h, "d": d, "g2": g2_kn_m2, "q": q_kn_m2, "edges": edges,
                   "fck": fck, "fyk": fyk},
        "loads": {"g_kn_m2": round(g, 3), "pu": round(pu, 3), "ps": round(ps, 3), "pqp": round(pqp, 3)},
        "rho": round(rho, 4), "one_way": mu["one_way"],
        "mu": {k: round(v_, 4) for k, v_ in mu.items() if k != "one_way"},
        "m0": {"x": round(m0x, 3), "y": round(m0y, 3), "x_els": round(m0x_s, 3), "x_qp": round(m0x_qp, 3)},
        "span": {"x": {"m_knm": round(mtx, 3), "as_calc_cm2_m": round(asx, 2), "as_req_cm2_m": round(as_x, 2),
                       "mesh": mesh_x},
                 "y": {"m_knm": round(mty, 3), "as_calc_cm2_m": round(asy, 2), "as_req_cm2_m": round(as_y, 2),
                       "mesh": mesh_y}},
        "supports": sup_out, "as_min_cm2_m": round(as_min, 2),
        "shear": {"v_ed_kn_m": round(v, 2), "vrdc_kn_m": vrd["vrdc_kn"], "ok": v <= vrd["vrdc_kn"]},
        "deflection_ld": ld, "warnings": warnings,
        "method": ("Método de Pigeaud (BAEL 91 Anexo E3) + regra forfetária de continuidade Mt + (Mw+Me)/2 ≥ 1,25·M0; armaduras EN 1992-1-1 §6.1 e §9.3; flecha L/d §7.4.2."),
    }
