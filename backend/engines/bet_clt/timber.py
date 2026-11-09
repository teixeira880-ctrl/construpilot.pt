"""Vérifications élémentaires bois (EN 1995-1-1 et EN 1995-1-2), unités : N, mm, MPa sauf mention.

- Panneau CLT en flexion (bande de 1 m) : méthode γ (EN 1995-1-1 annexe B étendue au CLT, plis transversaux = liaison souple
  de raideur G_R·b / t̄), contraintes de flexion, cisaillement roulant, flèches instantanée / finale (k_def), vibrations
  (§7.3.3 : f1 ≥ 8 Hz et flèche sous 1 kN ≤ a), feu (carbonisation β0 = 0,65 mm/min, chute de pli → 2β0 sur 25 mm,
  d_ef = d_char + 7 mm, k_fi = 1,15).
- Poutre lamellé-collé isostatique : flexion (k_h), cisaillement (k_cr = 0,67), flèches (k_def = 0,6) dont effort tranchant,
  feu 3 faces (β_n = 0,7 mm/min).
- Poteau lamellé-collé : flambement (§6.3.2, β_c = 0,1), flexion composée (6.23/6.24), feu 4 faces.
- Vis entièrement filetées : arrachement (§8.7.2, éq. 8.38–8.40), cisaillement bois-acier plaque épaisse (§8.2.3, éq. 8.10).
"""
from __future__ import annotations

import math

from .mat import CLT, FLOOR_LAYUPS, GL, LAYUPS  # noqa: F401
from .norms import GAM_M, KDEF, KMOD

KFI = 1.15
BETA0_CLT, BETA_N_GL = 0.65, 0.70
D0 = 7.0


# ============================================================ CLT
def char_depth(R: int, layers: tuple, beta0: float = BETA0_CLT) -> float:
    """Profondeur carbonisée (mm) après R minutes depuis la face exposée, avec chute des plis carbonisés (EN 1995-1-2:2025,
    approche par plis) : un pli entièrement carbonisé tombe et le pli suivant carbonise à 2β0 sur ses 25 premiers mm."""
    d, tt, k = 0.0, 0.0, 0
    bounds = []
    acc = 0.0
    for th in layers[::-1]:                     # feu par-dessous : du dernier pli vers le premier
        acc += th
        bounds.append(acc)
    fast_until = 0.0
    dt = 0.1
    while tt < R - 1e-9:
        rate = 2 * beta0 if d < fast_until else beta0
        d += rate * dt
        tt += dt
        while k < len(bounds) and d >= bounds[k]:
            fast_until = bounds[k] + 25.0
            k += 1
    return d


def _clt_section(layers: tuple, remove_bottom: float = 0.0):
    """Plis restants (épaisseur, z du centre depuis le dessus, longitudinal ?) après suppression d'une épaisseur en sous-face."""
    out, z = [], 0.0
    total = sum(layers)
    keep_to = total - remove_bottom
    for k, th in enumerate(layers):
        top, bot = z, z + th
        z = bot
        if top >= keep_to:
            break
        bot = min(bot, keep_to)
        out.append((bot - top, (top + bot) / 2, k % 2 == 0))
    return out


def clt_props(layers: tuple, span_mm: float, remove_bottom: float = 0.0, E: float = CLT["E0"], GR: float = CLT["GR"]) -> dict:
    """Raideur efficace EI_ef (N·mm² par mètre de largeur) par la méthode γ, et facteurs pour contraintes / cisaillement roulant."""
    b = 1000.0
    sec = _clt_section(layers, remove_bottom)
    longs = [(t_, z, k) for k, (t_, z, lg) in enumerate(sec) if lg and t_ > 0.5]
    if not longs:
        return {"EI": 1.0, "ok": False}
    h = sum(t_ for t_, _z, _l in sec)
    zmid = h / 2
    gam = []
    for (t_, z, k) in longs:
        top, bot = z - t_ / 2, z + t_ / 2
        if top <= zmid <= bot:
            gam.append(1.0)
            continue
        tbar = 0.0
        for (tc, zc, lg) in sec:
            if lg:
                continue
            ct, cb = zc - tc / 2, zc + tc / 2
            lo, hi = (min(z, zmid), max(z, zmid))
            ov = max(0.0, min(cb, hi) - max(ct, lo))
            tbar += ov
        A = b * t_
        gam.append(1.0 / (1.0 + math.pi ** 2 * E * A * tbar / (GR * b * span_mm ** 2)) if tbar > 0 else 1.0)
    num_ = sum(g * E * b * t_ * z for g, (t_, z, _k) in zip(gam, longs))
    den = sum(g * E * b * t_ for g, (t_, z, _k) in zip(gam, longs))
    z0 = num_ / den
    EI = sum(E * b * t_ ** 3 / 12 + g * E * b * t_ * (z - z0) ** 2 for g, (t_, z, _k) in zip(gam, longs))
    # contrainte de flexion max : σ = M/EI · E · (γ|a| + t/2)
    smax = max(E * (g * abs(z - z0) + t_ / 2) for g, (t_, z, _k) in zip(gam, longs)) / EI
    # cisaillement roulant : τ = V·S/(EI·b), S = moment statique (pondéré γ) des plis longitudinaux au-dessus du pli transversal
    srs = 0.0
    for (tc, zc, lg) in sec:
        if lg:
            continue
        S = sum(g * E * b * t_ * (z0 - z) for g, (t_, z, _k) in zip(gam, longs) if z < zc)
        srs = max(srs, abs(S))
    tau_r = srs / (EI * b)
    # cisaillement longitudinal au niveau de l'axe neutre (dans un pli longitudinal s'il le traverse)
    S0 = sum(g * E * b * t_ * (z0 - z) for g, (t_, z, _k) in zip(gam, longs) if z + t_ / 2 <= z0)
    tau_v = abs(S0) / (EI * b)
    # raideur transversale (plis transversaux, sans glissement — pour la largeur efficace en vibrations)
    cross = [(t_, z) for (t_, z, lg) in sec if not lg]
    if cross:
        zc0 = sum(t_ * z for t_, z in cross) / sum(t_ for t_, z in cross)
        EIT = sum(E * b * t_ ** 3 / 12 + E * b * t_ * (z - zc0) ** 2 for t_, z in cross)
    else:
        EIT = 0.0
    return {"EI": EI, "EIT": EIT, "s_fac": smax, "tr_fac": tau_r, "tv_fac": tau_v, "gamma": [round(g, 3) for g in gam], "h": h, "ok": True}


def design_clt(span: float, g: float, q: float, psi1: float, psi2: float, R: int, *, q_dur="medium", defl=(300, 250),
               a_vib=1.5, continuous=True, layups=FLOOR_LAYUPS, g_self_in=False) -> dict | None:
    """Plus petite composition CLT vérifiant ELU, ELS, vibrations et feu. span en m, g / q en kN/m² (g sans poids propre CLT).
    Bande de 1 m ; panneau continu sur au moins 2 appuis → effort tranchant d'appui intermédiaire 0,625·q·L."""
    L = span * 1000.0
    for name, lay in layups:
        res = check_clt(name, lay, span, g, q, psi1, psi2, R, q_dur=q_dur, defl=defl, a_vib=a_vib, continuous=continuous)
        if res["ok"]:
            return res
    res = check_clt(*layups[-1], span, g, q, psi1, psi2, R, q_dur=q_dur, defl=defl, a_vib=a_vib, continuous=continuous)
    res["ok"] = False
    return res if L > 0 else None


def check_clt(name, lay, span, g, q, psi1, psi2, R, *, q_dur="medium", defl=(300, 250), a_vib=1.5, continuous=True) -> dict:
    L = span * 1000.0
    h = sum(lay)
    gself = 5.0 * h / 1000                                  # kN/m² (ρ = 500 kg/m³ prudent, humidité comprise)
    G = g + gself
    p = props = clt_props(lay, L)
    kv = 0.625 if continuous else 0.5
    # ELU : deux combinaisons (G seul, k_mod permanent) et (G + Q, k_mod de l'action variable)
    combos = [(1.35 * G, KMOD["permanent"]), (1.35 * G + 1.5 * q, KMOD[q_dur])]
    fmd = lambda km: km * CLT["fm"] / GAM_M["CLT"]
    frd = lambda km: km * CLT["fR"] / GAM_M["CLT"]
    fvd = lambda km: km * CLT["fv"] / GAM_M["CLT"]
    um = ur = uv = 0.0
    for w, km in combos:
        M = w * span ** 2 / 8 * 1e6          # N·mm (bande 1 m)
        V = kv * w * span * 1e3              # N
        um = max(um, M * p["s_fac"] / fmd(km))
        ur = max(ur, V * p["tr_fac"] / frd(km))
        uv = max(uv, V * p["tv_fac"] / fvd(km))
    EI = p["EI"]                              # N·mm² (1 m)
    wG = 5 * G * L ** 4 / (384 * EI)          # G en kN/m² = N/mm par m de largeur ✓
    wQ = 5 * q * L ** 4 / (384 * EI)
    kdef = KDEF["CLT"]
    w_inst = wQ
    w_fin = wG * (1 + kdef) + wQ * (1 + psi2 * kdef)
    lim_i, lim_f = L / defl[0], L / defl[1]
    # vibrations (planchers d'habitation / bureaux)
    m_kg = G * 1000 / 9.81
    EI_m = EI * 1e-6                          # N·mm² → N·m² (par m)
    f1 = math.pi / (2 * span ** 2) * math.sqrt(EI_m / m_kg)
    b_ef = span / 1.1 * ((p["EIT"] / EI) ** 0.25 if p["EIT"] > 0 else 0.5)
    w1 = 1000 * span ** 3 / (48 * EI_m * max(b_ef, 0.5)) * 1000        # mm sous 1 kN
    vib_ok = (f1 >= 8.0 and w1 <= a_vib) if a_vib else True
    # feu (exposition en sous-face) : E_fi = G + ψ1·Q, f_fi = k_fi·f_k, γ_M,fi = 1
    fire = None
    if R:
        dch = char_depth(R, lay)
        dfe = dch + (D0 if R >= 20 else D0 * R / 20)
        pf = clt_props(lay, L, remove_bottom=dfe)
        if not pf["ok"]:
            fire = {"R": R, "d_char": dch, "d_ef": dfe, "u": 9.9}
        else:
            wfi = G + psi1 * q
            Mfi = wfi * span ** 2 / 8 * 1e6
            Vfi = kv * wfi * span * 1e3
            ufi = max(Mfi * pf["s_fac"] / (KFI * CLT["fm"]), Vfi * pf["tr_fac"] / (KFI * CLT["fR"]))
            fire = {"R": R, "d_char": round(dch, 1), "d_ef": round(dfe, 1), "u": round(ufi, 3), "h_res": round(pf["h"], 1)}
    ok = um <= 1 and ur <= 1 and uv <= 1 and w_inst <= lim_i and w_fin <= lim_f and vib_ok and (fire is None or fire["u"] <= 1)
    gov = max([("flexion", um), ("roulant", ur), ("cisaillement", uv), ("w_inst", w_inst / lim_i), ("w_fin", w_fin / lim_f),
               ("feu", fire["u"] if fire else 0.0)] + ([("vibration", max(8.0 / f1, w1 / a_vib))] if a_vib else []), key=lambda x: x[1])
    return {"ok": ok, "name": name, "layers": lay, "h": h, "span": span, "g_self": round(gself, 2), "G": round(G, 2), "q": q,
            "u_m": round(um, 3), "u_r": round(ur, 3), "u_v": round(uv, 3), "w_inst": round(w_inst, 1), "w_fin": round(w_fin, 1),
            "lim_inst": round(lim_i, 1), "lim_fin": round(lim_f, 1), "f1": round(f1, 2), "w1": round(w1, 2), "b_ef": round(b_ef, 2),
            "a_vib": a_vib, "fire": fire, "EI": EI, "gamma": props["gamma"], "governing": gov[0], "u_max": round(gov[1], 3),
            "p_uls": round(1.35 * G + 1.5 * q, 2)}


# ============================================================ poutre lamellé-collé isostatique
def beam_actions(L: float, wg: float, wq: float, Pg: list, Pq: list):
    """M max et V max (kN·m, kN) d'une poutre isostatique sous charge répartie et charges ponctuelles (a, P)."""
    def MV(w, P):
        Ra = w * L / 2 + sum(p * (L - a) / L for a, p in P)
        Rb = w * L / 2 + sum(p * a / L for a, p in P)
        Mmax = 0.0
        for k in range(101):
            x = L * k / 100
            M = Ra * x - w * x * x / 2 - sum(p * (x - a) for a, p in P if a < x)
            Mmax = max(Mmax, M)
        for a, _p in P:
            M = Ra * a - w * a * a / 2 - sum(p * (a - aa) for aa, p in P if aa < a)
            Mmax = max(Mmax, M)
        return Mmax, max(Ra, Rb), Ra, Rb
    return MV


def _defl_mid(L, w, P, EI, GA):
    """Flèche à mi-portée (mm) : flexion (formules exactes) + effort tranchant (κ = 1,2). L en m, w kN/m, P kN, EI N·mm², GA N."""
    Lm = L * 1000
    wb = 5 * w * Lm ** 4 / (384 * EI)
    for a, p in P:
        aa = min(a, L - a) * 1000
        wb += p * 1000 * aa * (3 * Lm ** 2 - 4 * aa ** 2) / (48 * EI)
    Mmid = w * L ** 2 / 8 + sum(p * min(a, L - a) / 2 for a, p in P)       # kN·m
    ws = 1.2 * Mmid * 1e6 / GA
    return wb + ws


def check_gl_beam(b: int, h: int, grade: str, L: float, wg: float, wq: float, Pg: list, Pq: list, *, psi1=0.5, psi2=0.3,
                  q_dur="medium", R=0, defl=(300, 250), sides=3) -> dict:
    mt = GL[grade]
    sw = 4.6 * b * h / 1e6                       # kN/m
    wg2 = wg + sw
    MV = beam_actions(L, 0, 0, [], [])
    Mg, Vg, Rga, Rgb = MV(wg2, Pg)
    Mq, Vq, Rqa, Rqb = MV(wq, Pq)
    W = b * h ** 2 / 6
    A = b * h
    kh = min((600 / h) ** 0.1, 1.1) if h < 600 else 1.0
    fmd = lambda km: km * kh * mt["fm"] / GAM_M["GL"]
    fvd = lambda km: km * mt["fv"] / GAM_M["GL"]
    um = uv = 0.0
    for (cg, cq, km) in ((1.35, 0.0, KMOD["permanent"]), (1.35, 1.5, KMOD[q_dur])):
        M = (cg * Mg + cq * Mq) * 1e6
        V = (cg * Vg + cq * Vq) * 1e3
        um = max(um, M / W / fmd(km))
        uv = max(uv, 1.5 * V / (0.67 * A) / fvd(km))
    I = b * h ** 3 / 12
    EI = mt["E0"] * I
    GA = mt["G"] * A
    wG = _defl_mid(L, wg2, Pg, EI, GA)
    wQ = _defl_mid(L, wq, Pq, EI, GA)
    kdef = KDEF["GL"]
    w_inst, w_fin = wQ, wG * (1 + kdef) + wQ * (1 + psi2 * kdef)
    lim_i, lim_f = L * 1000 / defl[0], L * 1000 / defl[1]
    fire = None
    if R:
        def_ = BETA_N_GL * R + D0
        bf, hf = b - 2 * def_, h - def_ * (1 if sides == 3 else 2)
        if bf <= 20 or hf <= 20:
            fire = {"R": R, "d_ef": def_, "u": 9.9}
        else:
            Mfi = (Mg + psi1 * Mq) * 1e6
            Vfi = (Vg + psi1 * Vq) * 1e3
            ufi = max(Mfi / (bf * hf ** 2 / 6) / (KFI * mt["fm"]), 1.5 * Vfi / (0.67 * bf * hf) / (KFI * mt["fv"]))
            fire = {"R": R, "d_ef": round(def_, 1), "b_fi": round(bf), "h_fi": round(hf), "u": round(ufi, 3)}
    ok = um <= 1 and uv <= 1 and w_inst <= lim_i and w_fin <= lim_f and (fire is None or fire["u"] <= 1)
    gov = max([("flexion", um), ("cisaillement", uv), ("w_inst", w_inst / lim_i), ("w_fin", w_fin / lim_f), ("feu", fire["u"] if fire else 0)],
              key=lambda x: x[1])
    return {"ok": ok, "b": b, "h": h, "grade": grade, "L": L, "sw": round(sw, 3), "M_Ed": round(1.35 * Mg + 1.5 * Mq, 1),
            "V_Ed": round(1.35 * Vg + 1.5 * Vq, 1), "u_m": round(um, 3), "u_v": round(uv, 3), "w_inst": round(w_inst, 1), "w_fin": round(w_fin, 1),
            "lim_inst": round(lim_i, 1), "lim_fin": round(lim_f, 1), "fire": fire, "kh": round(kh, 3), "governing": gov[0], "u_max": round(gov[1], 3),
            "R_g": (round(Rga, 2), round(Rgb, 2)), "R_q": (round(Rqa, 2), round(Rqb, 2)),
            "R_uls": (round(1.35 * Rga + 1.5 * Rqa, 1), round(1.35 * Rgb + 1.5 * Rqb, 1))}


def design_gl_beam(L, wg, wq, Pg, Pq, sizes, grades=("GL24h", "GL28h"), **kw) -> dict:
    best = None
    for grade in grades:
        for b, h in sizes:
            r = check_gl_beam(b, h, grade, L, wg, wq, Pg, Pq, **kw)
            if r["ok"]:
                if best is None or b * h < best["b"] * best["h"]:
                    best = r
                break
    if best is None:
        b, h = sizes[-1]
        best = check_gl_beam(b, h, grades[-1], L, wg, wq, Pg, Pq, **kw)
    return best


# ============================================================ poteau lamellé-collé
def check_gl_column(b: int, h: int, grade: str, Lc: float, Ng: float, Nq: float, Mg: float, Mq: float, *, psi1=0.5, q_dur="medium",
                    R=0, top=False) -> dict:
    """N en kN (compression), M en kN·m (axe fort), Lc hauteur libre (m), articulé-articulé (L_ef = Lc)."""
    mt = GL[grade]
    A = b * h
    i_min = min(b, h) / math.sqrt(12)

    def kc(Lef, i, E05, fc0k):
        lam = Lef / i
        lr = lam / math.pi * math.sqrt(fc0k / E05)
        k = 0.5 * (1 + 0.1 * (lr - 0.3) + lr ** 2)
        return (1.0 if lr <= 0.3 else 1 / (k + math.sqrt(k * k - lr * lr))), lr
    kcv, lr = kc(Lc * 1000, i_min, mt["E05"], mt["fc0"])
    W = b * h ** 2 / 6
    u = 0.0
    for (cg, cq, km) in ((1.35, 0.0, KMOD["permanent"]), (1.35, 1.5, KMOD[q_dur])):
        N = (cg * Ng + cq * Nq) * 1e3
        M = (cg * Mg + cq * Mq) * 1e6
        fc = km * mt["fc0"] / GAM_M["GL"]
        fm = km * mt["fm"] / GAM_M["GL"]
        u = max(u, N / A / (kcv * fc) + M / W / fm)
    fire = None
    if R:
        def_ = BETA_N_GL * R + D0
        bf, hf = b - 2 * def_, h - 2 * def_
        if bf <= 40 or hf <= 40:
            fire = {"R": R, "d_ef": def_, "u": 9.9}
        else:
            kcf, _ = kc((0.7 if not top else 1.0) * Lc * 1000, min(bf, hf) / math.sqrt(12), KFI * mt["E05"], KFI * mt["fc0"])
            Nfi = (Ng + psi1 * Nq) * 1e3
            Mfi = (Mg + psi1 * Mq) * 1e6
            ufi = Nfi / (bf * hf) / (kcf * KFI * mt["fc0"]) + Mfi / (bf * hf ** 2 / 6) / (KFI * mt["fm"])
            fire = {"R": R, "d_ef": round(def_, 1), "b_fi": round(bf), "h_fi": round(hf), "u": round(ufi, 3)}
    ok = u <= 1 and (fire is None or fire["u"] <= 1)
    return {"ok": ok, "b": b, "h": h, "grade": grade, "Lc": Lc, "kc": round(kcv, 3), "lam_rel": round(lr, 3), "u": round(u, 3),
            "N_Ed": round(1.35 * Ng + 1.5 * Nq, 1), "N_ser": round(Ng + Nq, 1), "fire": fire,
            "u_max": round(max(u, fire["u"] if fire else 0), 3), "governing": "feu" if fire and fire["u"] > u else "flambement"}


# ============================================================ vis entièrement filetées (EN 1995-1-1 §8.7)
def screw_axial(d: float, lef: float, rho_k: float, alpha_deg: float = 90.0, kmod: float = 0.8) -> dict:
    """Résistance à l'arrachement d'une vis (N) — éq. (8.38)–(8.40a), α = angle vis / fil."""
    fax = 0.52 * d ** -0.5 * lef ** -0.1 * rho_k ** 0.8
    kd = min(d / 8, 1.0)
    a = math.radians(alpha_deg)
    Rk = fax * d * lef * kd / (1.2 * math.cos(a) ** 2 + math.sin(a) ** 2)
    ftens = {6: 11000.0, 8: 20000.0, 10: 30000.0, 12: 40000.0}.get(int(d), 20000.0)       # f_tens,k usuelle (ETA)
    Rd = min(kmod * Rk / GAM_M["CONN"], ftens / GAM_M["STEEL2"])
    return {"fax_k": round(fax, 2), "R_k": round(Rk), "R_d": round(Rd), "f_tens_d": round(ftens / GAM_M["STEEL2"])}


def screw_shear_steel(d: float, t1: float, rho_k: float, kmod: float = 0.8, Fax_Rk: float = 0.0) -> dict:
    """Vis d'assemblage bois-acier plaque épaisse, simple cisaillement — éq. (8.10) c/d ; d_ef = 1,1 × d_noyau (≈ 0,66 d)."""
    def_ = 0.66 * d
    fh = 0.082 * rho_k * def_ ** -0.3 if d <= 6 else 0.082 * (1 - 0.01 * def_) * rho_k
    My = 0.3 * 1000 * def_ ** 2.6
    jc = fh * t1 * def_ * (math.sqrt(2 + 4 * My / (fh * def_ * def_ * t1)) - 1)
    jd = 2.3 * math.sqrt(My * fh * def_)
    Rk = min(jc + min(Fax_Rk / 4, jc), jd + min(Fax_Rk / 4, jd))       # effet de corde ≤ 100 % (vis)
    return {"fh_k": round(fh, 2), "My_k": round(My), "R_k": round(Rk), "R_d": round(kmod * Rk / GAM_M["CONN"])}
