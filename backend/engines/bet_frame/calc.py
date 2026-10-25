"""Calculs déterministes de l'ossature BA (pré-dimensionnement EN 1990 / 1991 / 1992).

- Charges : poids propres, revêtements, cloisons, façades, balcons ; exploitation selon l'usage (EN 1991-1-1 + AN).
- Dalles pleines : panneaux entre poutres, moments par la méthode des panneaux (coefficients μx, μy, ν = 0) avec
  continuité ; aciers inférieurs et chapeaux ; flèche par l/d (EN 1992-1-1 7.4.2).
- Poutres : continues sur les poteaux, charges des panneaux (triangles / trapèzes), façade, balcons ; équation des
  trois moments, cas de charge alternés ; flexion, effort tranchant (6.2, bielle variable), flèche.
- Poteaux : descente de charges par réactions des poutres, moments de sous-portique (rive et charges alternées),
  imperfections, second ordre (courbure nominale), flexion composée par compatibilité des déformations, biaxial 5.8.9.
- Semelles isolées (méthode des bielles), regroupement en filantes si recouvrement, radier conseillé si > 50 %.
Les sections insuffisantes sont augmentées automatiquement et la décision est tracée.
"""
from __future__ import annotations

import math

from .lang import _, num
from .model import BALCONY_Q, BLOCK, USES, WARN, Frame, ceil_to

GAM_G, GAM_Q = 1.35, 1.5
GAM_C, GAM_S = 1.5, 1.15
ES = 200000.0
RHO_C = 25.0
SLAB_BARS = (8, 10, 12, 16)
SLAB_SPACING = (0.25, 0.20, 0.175, 0.15, 0.125, 0.10)
BEAM_BARS = (12, 16, 20, 25)
COL_BARS = (12, 16, 20, 25)


def area(phi_mm: float) -> float:
    """Section d'une barre (m²)."""
    return math.pi * (phi_mm / 1000) ** 2 / 4


def mat(m: Frame) -> dict:
    fck = m.fck
    return {"fck": fck, "fcd": fck / GAM_C, "fctm": 0.30 * fck ** (2 / 3), "fyk": 500.0, "fyd": 500.0 / GAM_S,
            "concrete": f"C{int(fck)}/{ {20: 25, 25: 30, 30: 37, 35: 45, 40: 50}.get(int(fck), int(fck * 1.25))}",
            "steel": m.steel, "cover_slab": 0.025, "cover_beam": 0.030, "cover_col": 0.030, "cover_fond": 0.050,
            "dcm": dcm(m)}


def dcm(m: Frame) -> bool:
    """Disposições construtivas sísmicas (NP EN 1998-1, classe de ductilidade média DCM) : projetos portugueses, salvo
    seismic.dcm = false ; projets français si seismic.dcm = true (zones de sismicité ≥ 3)."""
    seis = m.raw.get("seismic") or {}
    if "dcm" in seis:
        return bool(seis["dcm"])
    return m.country == "PT"


# ================================================================ charges
def slab_loads(m: Frame, use: str, h: float) -> dict:
    ld = m.raw.get("loads") or {}
    qfr, qpt, psi2, lfr, lpt = USES[use]
    q = float(ld.get("q", {}).get(use, qpt if m.country == "PT" else qfr)) if isinstance(ld.get("q"), dict) else (qpt if m.country == "PT" else qfr)
    roof = use in ("toiture", "terrasse")
    finishes = float(ld.get("roof_finishes", 2.5)) if roof else float(ld.get("finishes", 1.5))
    parts = 0.0 if use in ("toiture", "terrasse", "stationnement") else float(ld.get("partitions", 1.0))
    g = RHO_C * h + finishes + parts
    return {"use": use, "label": _(lfr, lpt), "g_self": round(RHO_C * h, 2), "g_fin": finishes, "g_part": parts,
            "g": round(g, 2), "q": q, "psi2": psi2, "p_uls": round(GAM_G * g + GAM_Q * q, 2)}


# ================================================================ armatures
def design_rect(M: float, b: float, d: float, mt: dict) -> dict:
    """Flexion simple ELU, rectangle b×d, diagramme rectangulaire. M en kN·m, retour As en m²."""
    fcd, fyd = mt["fcd"] * 1000, mt["fyd"] * 1000      # kN/m²
    mu = abs(M) / (b * d * d * fcd) if d > 0 else 9
    if mu > 0.2952:
        return {"mu": mu, "ok": False, "As": None}
    alpha = 1.25 * (1 - math.sqrt(1 - 2 * mu))
    z = d * (1 - 0.4 * alpha)
    As = abs(M) / (z * fyd)
    return {"mu": mu, "ok": True, "As": As, "z": z}


def as_min(b: float, d: float, mt: dict) -> float:
    return max(0.26 * mt["fctm"] / mt["fyk"] * b * d, 0.0013 * b * d)


def pick_mesh(As_m: float, h: float, main: bool = True) -> dict:
    """Treillis de barres par mètre : (Ø, espacement) d'aire mini ≥ As_m (m²/m), espacement ≤ 2h (≤ 3h en secondaire)."""
    smax = min(2 * h, 0.25) if main else min(3 * h, 0.40)
    best = None
    for phi in SLAB_BARS:
        for s in SLAB_SPACING:
            if s > smax + 1e-9:
                continue
            a = area(phi) / s
            if a + 1e-12 < As_m:
                continue
            key = (round(a, 7), -s)
            if best is None or key < best[0]:
                best = (key, phi, s, a)
    if best is None:
        phi, s = 16, 0.10
        return {"phi": phi, "s": s, "As": area(phi) / s, "ok": False}
    return {"phi": best[1], "s": best[2], "As": best[3], "ok": True}


def sp(s: float) -> str:
    """Espacement au format plan : 0,15 / 0,175."""
    return num(s, 3 if round(s * 1000) % 10 else 2)


def mesh_txt(x: dict) -> str:
    return f"Ø{x['phi']}//{sp(x['s'])}"


def pick_bars(As: float, b: float, cover: float, stirrup: float = 0.008) -> dict:
    """n Ø (une ou deux lits) d'aire mini ≥ As, qui tiennent dans la largeur b."""
    best = None
    for phi in BEAM_BARS:
        for n in range(2, 13):
            a = n * area(phi)
            if a + 1e-12 < As:
                continue
            clear = max(phi / 1000, 0.025)
            per_layer = max(2, int((b - 2 * (cover + stirrup) + clear) // (phi / 1000 + clear)))
            layers = math.ceil(n / per_layer)
            if layers > 2:
                continue
            key = (layers, a * (1 + 0.04 * n))
            if best is None or key < best[0]:
                best = (key, n, phi, a, layers)
            break
    if best is None:
        return {"n": 0, "phi": 25, "As": 0.0, "layers": 3, "ok": False, "txt": "—"}
    _, n, phi, a, layers = best
    return {"n": n, "phi": phi, "As": a, "layers": layers, "ok": True, "txt": f"{n}Ø{phi}"}


# ================================================================ dalles
def panels(m: Frame) -> list[dict]:
    gx, gy = m.gx, m.gy
    out = []
    for j in range(len(gy) - 1):
        for i in range(len(gx) - 1):
            if not m.cell_in(i, j):
                continue
            x0, x1, y0, y1 = gx[i], gx[i + 1], gy[j], gy[j + 1]
            core = next((c for c in m.cores if c["x0"] < x1 - 0.01 and c["x1"] > x0 + 0.01 and c["y0"] < y1 - 0.01 and c["y1"] > y0 + 0.01), None)
            out.append({"id": f"L{j + 1}.{i + 1}", "i": i, "j": j, "x0": x0, "x1": x1, "y0": y0, "y1": y1,
                        "dx": round(x1 - x0, 3), "dy": round(y1 - y0, 3),
                        "cont": {"W": m.cell_in(i - 1, j), "E": m.cell_in(i + 1, j), "S": m.cell_in(i, j - 1), "N": m.cell_in(i, j + 1)},
                        "core": core.get("id") if core else None})
    return out


def _span_coef(c1: bool, c2: bool) -> float:
    return 0.75 if (c1 and c2) else (0.85 if (c1 or c2) else 1.0)


def design_panel(p: dict, ld: dict, h: float, mt: dict, brittle: bool) -> dict:
    lx, ly = min(p["dx"], p["dy"]), max(p["dx"], p["dy"])
    short_is_x = p["dx"] <= p["dy"]
    a = lx / ly
    pu = ld["p_uls"]
    if a < 0.4:
        mux, muy = 1 / 8, 0.0
    else:
        mux, muy = 1 / (8 * (1 + 2.4 * a ** 3)), a ** 3 * (1.9 - 0.9 * a)
    M0x = mux * pu * lx ** 2
    M0y = max(muy * M0x, 0.25 * M0x if a >= 0.4 else 0.0)
    # continuité : sens court = portée entre les deux côtés longs
    c_short = (p["cont"]["W"], p["cont"]["E"]) if short_is_x else (p["cont"]["S"], p["cont"]["N"])
    c_long = (p["cont"]["S"], p["cont"]["N"]) if short_is_x else (p["cont"]["W"], p["cont"]["E"])
    Mtx, Mty = _span_coef(*c_short) * M0x, _span_coef(*c_long) * M0y
    sup = {}
    for side in ("W", "E", "S", "N"):
        along_short = (side in ("W", "E")) == short_is_x
        M0 = M0x if along_short else M0y
        sup[side] = (0.5 if p["cont"][side] else 0.3) * M0
    dx_ = h - mt["cover_slab"] - 0.005
    dy_ = dx_ - 0.010
    res = {"lx": lx, "ly": ly, "alpha": round(a, 3), "two_way": a >= 0.4, "Mtx": Mtx, "Mty": Mty, "sup": sup, "d": dx_}
    asx = design_rect(Mtx, 1.0, dx_, mt)
    asy = design_rect(Mty, 1.0, dy_, mt)
    ok = asx["ok"] and asy["ok"]
    Ax = max(asx["As"] or 0, as_min(1.0, dx_, mt))
    Ay = max(asy["As"] or 0, as_min(1.0, dy_, mt) if a >= 0.4 else 0.2 * Ax)
    res["As_x"], res["As_y"] = Ax, Ay
    res["mesh_short"] = pick_mesh(Ax, h, True)
    res["mesh_long"] = pick_mesh(Ay, h, a >= 0.4)
    res["top"] = {}
    for side, M in sup.items():
        dd = dx_
        r = design_rect(M, 1.0, dd, mt)
        ok = ok and r["ok"]
        res["top"][side] = pick_mesh(max(r["As"] or 0, as_min(1.0, dd, mt) * 0.5), h, True)
    # flèche (sens court)
    nc = sum(c_short)
    K = {0: 1.0, 1: 1.3, 2: 1.5}[nc]
    rho = Ax / dx_
    rho0 = math.sqrt(mt["fck"]) * 1e-3
    fck = mt["fck"]
    if rho <= rho0:
        base = 11 + 1.5 * math.sqrt(fck) * rho0 / rho + 3.2 * math.sqrt(fck) * (rho0 / rho - 1) ** 1.5
    else:
        base = 11 + 1.5 * math.sqrt(fck) * rho0 / rho
    lim = min(K * base, 1.5 * 20 * K) * min(1.5, res["mesh_short"]["As"] / Ax)   # plafond : 1,5 × tab. 7.4N (ρ = 0,5 %)
    if brittle and lx > 7.0:
        lim *= 7.0 / lx
    res["ld"], res["ld_lim"] = lx / dx_, lim
    res["defl_ok"] = lx / dx_ <= lim
    res["ok"] = ok and res["defl_ok"] and res["mesh_short"]["ok"]
    return res


# ================================================================ poutres continues (équation des trois moments)
def _three_moment(L: list[float], w: list[float]) -> list[float]:
    """Moments sur appuis (négatifs = chapeaux) d'une poutre continue sur appuis simples, inertie constante."""
    n = len(L)
    if n == 1:
        return [0.0, 0.0]
    m_ = n - 1
    a = [0.0] * m_
    bb = [0.0] * m_
    c = [0.0] * m_
    rhs = [0.0] * m_
    for k in range(m_):                 # appui intérieur k+1 entre travées k et k+1
        a[k] = L[k]
        bb[k] = 2 * (L[k] + L[k + 1])
        c[k] = L[k + 1]
        rhs[k] = -(w[k] * L[k] ** 3 + w[k + 1] * L[k + 1] ** 3) / 4
    for k in range(1, m_):              # Thomas
        f = a[k] / bb[k - 1]
        bb[k] -= f * c[k - 1]
        rhs[k] -= f * rhs[k - 1]
    x = [0.0] * m_
    x[-1] = rhs[-1] / bb[-1]
    for k in range(m_ - 2, -1, -1):
        x[k] = (rhs[k] - c[k] * x[k + 1]) / bb[k]
    return [0.0] + x + [0.0]


def _spans_state(L, w, Ms):
    out = []
    for k, (l, q) in enumerate(zip(L, w)):
        Ma, Mb = Ms[k], Ms[k + 1]
        Ra = q * l / 2 + (Mb - Ma) / l
        Rb = q * l - Ra
        x0 = Ra / q if q > 0 else l / 2
        Mmax = Ma + Ra * x0 - q * x0 ** 2 / 2 if 0 <= x0 <= l else max(Ma, Mb)
        out.append({"Ra": Ra, "Rb": Rb, "Mmax": Mmax})
    return out


def cont_beam(L: list[float], wG_M, wQ_M, wG_V, wQ_V) -> dict:
    """Enveloppe ELU (cas alternés) + réactions caractéristiques G et Q (toutes travées chargées)."""
    n = len(L)
    cases = [[True] * n, [k % 2 == 0 for k in range(n)], [k % 2 == 1 for k in range(n)]]
    for s in range(1, n):
        cases.append([k in (s - 1, s) for k in range(n)])
    span_M = [0.0] * n
    sup_M = [0.0] * (n + 1)
    V = [[0.0, 0.0] for _ in range(n)]
    for cs in cases:
        wM = [GAM_G * g + (GAM_Q * q if on else 0.0) for g, q, on in zip(wG_M, wQ_M, cs)]
        wV = [GAM_G * g + (GAM_Q * q if on else 0.0) for g, q, on in zip(wG_V, wQ_V, cs)]
        Ms = _three_moment(L, wM)
        for k, st in enumerate(_spans_state(L, wM, Ms)):
            span_M[k] = max(span_M[k], st["Mmax"])
        for k in range(n + 1):
            sup_M[k] = min(sup_M[k], Ms[k])
        Mv = _three_moment(L, wV)
        for k, st in enumerate(_spans_state(L, wV, Mv)):
            V[k][0] = max(V[k][0], st["Ra"])
            V[k][1] = max(V[k][1], st["Rb"])
    reac = {}
    for key, w in (("G", wG_V), ("Q", wQ_V)):
        Ms = _three_moment(L, w)
        st = _spans_state(L, w, Ms)
        r = [0.0] * (n + 1)
        for k, s_ in enumerate(st):
            r[k] += s_["Ra"]
            r[k + 1] += s_["Rb"]
        reac[key] = r
    return {"span_M": span_M, "sup_M": sup_M, "V": V, "R_G": reac["G"], "R_Q": reac["Q"]}


def _side_load(p_dx: float, p_dy: float, along_x: bool, pload: float) -> tuple[float, float]:
    """Charge linéique équivalente (moment, tranchant) transmise par un panneau à son côté. along_x : côté parallèle à x."""
    side, other = (p_dx, p_dy) if along_x else (p_dy, p_dx)
    if side >= other:                       # côté long → trapèze, lx = other
        lx, ly = other, side
        return pload * lx / 2 * (1 - lx ** 2 / (3 * ly ** 2)), pload * lx / 2 * (1 - lx / (2 * ly))
    lx = side                               # côté court → triangle
    return pload * lx / 3, pload * lx / 4


def beam_lines(m: Frame, slab, ld: dict, h_beam: dict, pans: list[dict]) -> list[dict]:
    """Poutres d'un plancher : une ligne par file de la trame portant ≥ 2 poteaux, interrompue là où aucune case
    adjacente ne porte de plancher (emprise en L / U / cour) ; les travées en bord de vide reçoivent la façade."""
    cols = set(m.columns)
    gx, gy = m.gx, m.gy
    fac = m.raw.get("facade") or {}
    fac_w = float(fac.get("weight", 2.8 if m.country == "PT" else 2.5))
    lv_above = next((l for l in m.levels if l.id == slab.id), None)
    out = []
    for axis in ("x", "y"):
        lines = range(len(gy)) if axis == "x" else range(len(gx))
        for t in lines:
            if axis == "x":
                sup_all = [i for i in range(len(gx)) if (i, t) in cols]
                g_along = gx
                base = f"V{m.yl[t]}"
            else:
                sup_all = [j for j in range(len(gy)) if (t, j) in cols]
                g_along = gy
                base = f"V{m.xl[t]}"
            if len(sup_all) < 2:
                continue
            outer = t in (0, (len(gy) if axis == "x" else len(gx)) - 1)
            side_lbl = None
            if outer:
                side_lbl = ("S" if t == 0 else "N") if axis == "x" else ("W" if t == 0 else "E")

            def sides(i0, i1):
                cells = range(i0, i1)
                if axis == "x":
                    return any(m.cell_in(k, t - 1) for k in cells), any(m.cell_in(k, t) for k in cells)
                return any(m.cell_in(t - 1, k) for k in cells), any(m.cell_in(t, k) for k in cells)
            runs, cur = [], []
            for a, b in zip(sup_all, sup_all[1:]):
                s1, s2 = sides(a, b)
                if not (s1 or s2):
                    if len(cur) >= 1:
                        runs.append(cur)
                    cur = []
                    continue
                cur.append((a, b, not (s1 and s2)))
            if cur:
                runs.append(cur)
            for ri, run in enumerate(runs):
                name = base if len(runs) == 1 else f"{base}{chr(97 + ri)}"
                sup_idx = [run[0][0]] + [b for _a, b, _e in run]
                pos = [g_along[k] for k in sup_idx]
                b, h = h_beam.get(name, h_beam.get(base, m.beam_section))
                perim = any(e for _a, _b, e in run)
                L, wGM, wQM, wGV, wQV = [], [], [], [], []
                for (ia, ib, edge), a0, a1 in zip(run, pos, pos[1:]):
                    l = a1 - a0
                    gM = qM = gV = qV = 0.0
                    for p in pans:
                        if axis == "x":
                            adj = abs(p["y0"] - gy[t]) < 1e-6 or abs(p["y1"] - gy[t]) < 1e-6
                            ov = max(0.0, min(p["x1"], a1) - max(p["x0"], a0))
                        else:
                            adj = abs(p["x0"] - gx[t]) < 1e-6 or abs(p["x1"] - gx[t]) < 1e-6
                            ov = max(0.0, min(p["y1"], a1) - max(p["y0"], a0))
                        if not adj or ov <= 1e-6:
                            continue
                        fm, fv = _side_load(p["dx"], p["dy"], axis == "x", 1.0)
                        k = ov / l
                        gM += fm * ld["g"] * k
                        qM += fm * ld["q"] * k
                        gV += fv * ld["g"] * k
                        qV += fv * ld["q"] * k
                    sw = RHO_C * b * max(h - slab.h, 0.0)
                    line_g = sw
                    if edge:
                        hw = (lv_above.height - h) if lv_above else 1.0
                        line_g += fac_w * max(hw, 0.0)
                    if outer:
                        for bc in m.balconies:
                            if str(bc.get("side", "")).upper() != side_lbl:
                                continue
                            lvls = bc.get("levels") or []
                            if lvls and slab.id not in lvls:
                                continue
                            if slab.id == "COB":
                                continue
                            ov = max(0.0, min(float(bc.get("a1", 1e9)), a1) - max(float(bc.get("a0", -1e9)), a0))
                            if ov <= 0:
                                continue
                            dpt = float(bc.get("depth", 1.2))
                            gb = (RHO_C * float(bc.get("slab", 0.18)) + 1.2) * dpt + 1.0      # dalle + revêtement + garde-corps
                            line_g += gb * ov / l
                            qM += BALCONY_Q * dpt * ov / l
                            qV += BALCONY_Q * dpt * ov / l
                    L.append(l)
                    wGM.append(gM + line_g)
                    wQM.append(qM)
                    wGV.append(gV + line_g)
                    wQV.append(qV)
                out.append({"name": name, "axis": axis, "line": t, "sup_idx": sup_idx, "pos": pos, "b": b, "h": h, "L": L,
                            "wGM": wGM, "wQM": wQM, "wGV": wGV, "wQV": wQV, "perim": perim})
    return out


def design_beam(bl: dict, mt: dict, brittle: bool) -> dict:
    r = cont_beam(bl["L"], bl["wGM"], bl["wQM"], bl["wGV"], bl["wQV"])
    b, h = bl["b"], bl["h"]
    d = h - mt["cover_beam"] - 0.008 - 0.010
    n = len(bl["L"])
    spans, ok, why = [], True, []
    fck, fcd = mt["fck"], mt["fcd"] * 1000
    for k in range(n):
        Ms = r["span_M"][k]
        Mleft = -r["sup_M"][k] if k > 0 else 0.15 * Ms
        Mright = -r["sup_M"][k + 1] if k < n - 1 else 0.15 * Ms
        bot = design_rect(Ms, b, d, mt)
        tl, tr_ = design_rect(Mleft, b, d, mt), design_rect(Mright, b, d, mt)
        if not (bot["ok"] and tl["ok"] and tr_["ok"]):
            ok = False
            why.append("flexion")
        amin = as_min(b, d, mt)
        if mt.get("dcm"):      # EC8 5.4.3.1.2(5) : ρmin = 0,5 fctm/fyk na face tracionada ; compressão ≥ 0,5 da tração nas zonas críticas
            amin = max(amin, 0.5 * mt["fctm"] / mt["fyk"] * b * d)
        As_b = max(bot["As"] or 0, amin)
        As_l, As_r = max(tl["As"] or 0, amin), max(tr_["As"] or 0, amin)
        if mt.get("dcm"):
            As_b = max(As_b, 0.5 * max(As_l, As_r))
        bars_b = pick_bars(As_b, b, mt["cover_beam"])
        bars_l, bars_r = pick_bars(As_l, b, mt["cover_beam"]), pick_bars(As_r, b, mt["cover_beam"])
        if not (bars_b["ok"] and bars_l["ok"] and bars_r["ok"]):
            ok = False
            why.append("ferraillage")
        # tranchant
        wU = GAM_G * bl["wGV"][k] + GAM_Q * bl["wQV"][k]
        VEd = max(r["V"][k]) - wU * (0.175 + d)
        z = 0.9 * d
        kk = min(2.0, 1 + math.sqrt(0.2 / d))
        rho = min(bars_b["As"] / (b * d), 0.02)
        vrdc = max(0.12 * kk * (100 * rho * fck) ** (1 / 3), 0.035 * kk ** 1.5 * fck ** 0.5) * 1000 * b * d
        nu1 = 0.6 * (1 - fck / 250)
        cot = None
        for ct in (2.5, 2.0, 1.5, 1.0):
            vmax = b * z * nu1 * fcd / (ct + 1 / ct)
            if VEd <= vmax:
                cot = ct
                break
        if cot is None:
            ok = False
            why.append("bielle")
            cot = 1.0
        Asw = 2 * area(8)
        need = VEd / (z * mt["fyd"] * 1000 * cot) if VEd > vrdc else 0.0
        need = max(need, 0.08 * math.sqrt(fck) / mt["fyk"] * b)
        s = min(Asw / need if need > 0 else 0.30, 0.75 * d, 0.30)
        s = max(math.floor(s / 0.025 + 1e-6) * 0.025, 0.075)
        # flèche l/d
        K = 1.0 if n == 1 else (1.3 if k in (0, n - 1) else 1.5)
        rho_l = As_b / (b * d)
        rho0 = math.sqrt(fck) * 1e-3
        if rho_l <= rho0:
            base = 11 + 1.5 * math.sqrt(fck) * rho0 / rho_l + 3.2 * math.sqrt(fck) * (rho0 / rho_l - 1) ** 1.5
        else:
            base = 11 + 1.5 * math.sqrt(fck) * rho0 / rho_l
        lim = min(K * base, 1.5 * 14 * K) * min(1.5, bars_b["As"] / As_b)   # plafond : 1,5 × tab. 7.4N (ρ = 1,5 %)
        if brittle and bl["L"][k] > 7.0:
            lim *= 7.0 / bl["L"][k]
        dok = bl["L"][k] / d <= lim
        if not dok:
            ok = False
            why.append("flèche")
        if mt.get("dcm"):      # EC8 5.4.3.1.2(6) : s ≤ min(hw/4 ; 24 dbw ; 225 ; 8 dbL) em lcr = hw ; 1.º estribo a ≤ 50 mm da face
            dbl = min([bars_b.get("phi") or 12, bars_l.get("phi") or 12, bars_r.get("phi") or 12])
            scr = min(h / 4, 24 * 0.008, 0.225, 8 * dbl / 1000, s)
            scr = max(math.floor(scr * 100 + 1e-6) / 100, 0.05)
        else:
            scr = s
        spans.append({"k": k, "L": bl["L"][k], "M_span": Ms, "M_left": Mleft, "M_right": Mright, "V": VEd, "cot": cot,
                      "stirrups_crit": f"Ø8//{sp(scr)}", "s_crit": scr, "lcr": h,
                      "bot": bars_b, "top_l": bars_l, "top_r": bars_r, "stirrups": f"Ø8//{sp(s)}",
                      "s": s, "ld": bl["L"][k] / d, "ld_lim": lim, "defl_ok": dok, "pU": wU})
    return {"name": bl["name"], "axis": bl["axis"], "line": bl["line"], "b": b, "h": h, "pos": bl["pos"], "sup_idx": bl["sup_idx"],
            "perim": bl["perim"], "spans": spans, "R_G": r["R_G"], "R_Q": r["R_Q"], "ok": ok, "why": sorted(set(why)),
            "wGM": bl["wGM"], "wQM": bl["wQM"]}


# ================================================================ poteaux : flexion composée
def _nm(b, h, As_face, x, mt, dp):
    fcd, fyd = mt["fcd"] * 1000, mt["fyd"] * 1000
    a = min(0.8 * x, h)
    Nc = a * b * fcd

    def eps(y):
        if x <= h:
            return 0.0035 * (x - y) / x
        return 0.002 * (x - y) / (x - 3 * h / 7)
    s1 = max(-fyd, min(fyd, ES * 1000 * eps(dp)))
    s2 = max(-fyd, min(fyd, ES * 1000 * eps(h - dp)))
    N = Nc + As_face * (s1 + s2)
    M = Nc * (h / 2 - a / 2) + As_face * (s1 - s2) * (h / 2 - dp)
    return N, M


def mrd(b, h, As_face, N, mt, dp=0.05) -> float | None:
    """Moment résistant (kN·m) sous N (kN, compression +) — None si N dépasse la capacité."""
    lo, hi = 1e-4, 30 * h
    if _nm(b, h, As_face, hi, mt, dp)[0] < N:
        return None
    if _nm(b, h, As_face, lo, mt, dp)[0] > N:
        return _nm(b, h, As_face, lo, mt, dp)[1]
    for _i in range(70):
        mid = (lo + hi) / 2
        if _nm(b, h, As_face, mid, mt, dp)[0] < N:
            lo = mid
        else:
            hi = mid
    return _nm(b, h, As_face, (lo + hi) / 2, mt, dp)[1]


RHO_MAX = 0.03          # taux pratique (EN 1992 : 4 % hors recouvrements) — au-delà on agrandit la section
NU_MAX = 0.85           # effort normal réduit NEd / (Ac·fcd) maximal retenu
NU_DCM = 0.65           # NP EN 1998-1 5.4.3.2.1(3) : effort normal réduit de calcul des pilares sísmicos primários (DCM)
ARRANGE = ((4, 2), (8, 3), (12, 4), (16, 5))       # (barres, barres par face)


def design_column(b, h, NEd, Mx, My, mt) -> dict:
    """Choisit le ferraillage longitudinal (n Ø) vérifiant N + Mx + My (5.8.9, exposant a)."""
    Ac = b * h
    fcd, fyd = mt["fcd"] * 1000, mt["fyd"] * 1000
    nu = NEd / (Ac * fcd)
    seis = mt.get("dcm")
    As_min = max(0.10 * NEd / fyd, 0.002 * Ac, 0.01 * Ac if seis else 0.0)       # EC8 5.4.3.2.2(1) : 1 % ≤ ρl ≤ 4 %
    As_max = (0.04 if seis else RHO_MAX) * Ac
    if nu > (NU_DCM if seis else NU_MAX):                                         # EC8 5.4.3.2.1(3) : νd ≤ 0,65
        return {"ok": False, "nu": nu}
    per_face_min = max(3 if seis else 2, math.ceil((max(b, h) - 2 * 0.05) / 0.30) + 1)   # EC8 : une barre intermédiaire par face
    best = None
    NRd0 = None
    for nbar, pf in ARRANGE:
        if pf < per_face_min:
            continue
        for phi in COL_BARS:
            As = nbar * area(phi)
            if As + 1e-12 < As_min or As > As_max:
                continue
            face = pf * area(phi)
            NRd = Ac * fcd + As * min(fyd, 400000.0)
            if NEd > 0.98 * NRd:
                continue
            mrx, mry = mrd(b, h, face, NEd, mt), mrd(h, b, face, NEd, mt)
            if mrx is None or mry is None or mrx <= 0 or mry <= 0:
                continue
            r = NEd / NRd                       # exposant a de 5.8.9 (4) : 1,0 à 0,1 ; 1,5 à 0,7 ; 2,0 à 1,0
            ea = 1.0 if r <= 0.1 else (1.0 + (r - 0.1) / 0.6 * 0.5 if r <= 0.7 else 1.5 + (r - 0.7) / 0.3 * 0.5)
            util = (abs(Mx) / mrx) ** ea + (abs(My) / mry) ** ea
            if util > 1.0:
                continue
            key = (round(As, 7), -phi)
            if best is None or key < best[0]:
                best = (key, nbar, phi, As, util, mrx, mry)
                NRd0 = NRd
    if best is None:
        return {"ok": False, "nu": nu}
    _, nbar, phi, As, util, mrx, mry = best
    phit = 8 if phi >= 20 else 6
    st = min(20 * phi / 1000, min(b, h), 0.40)
    st = math.floor(st / 0.025 + 1e-6) * 0.025
    if seis:      # EC8 5.4.3.2.2(11) : s ≤ min(b0/2 ; 175 mm ; 8 dbL) nas zonas críticas
        b0 = min(b, h) - 2 * mt["cover_col"] - phit / 1000
        sc = min(b0 / 2, 0.175, 8 * phi / 1000)
        sc = max(math.floor(sc * 100 + 1e-6) / 100, 0.05)
        if sc < 0.075 and phit == 6:
            phit = 8
    else:
        sc = math.floor(0.6 * st / 0.025 + 1e-6) * 0.025
    return {"ok": True, "nu": nu, "n": nbar, "phi": phi, "As": As, "util": util, "MRdx": mrx, "MRdy": mry, "NRd": NRd0,
            "ties": f"Ø{phit}//{sp(st)}", "ties_crit": f"Ø{phit}//{sp(sc)}", "s_crit": sc,
            "txt": f"{nbar}Ø{phi}", "rho": As / Ac}


# ================================================================ calcul global
def compute(m: Frame) -> dict:
    mt = mat(m)
    decisions, issues = [], []
    brittle = any(s.use in ("habitation", "bureaux") for s in m.slabs)
    pans_of = {}
    for s0 in m.slabs:                               # panneaux de chaque dalle (étages en retrait : dalle propre à chaque niveau)
        with m.at_slab(s0.id):
            pans_of[s0.id] = panels(m)
    slab_h = {s.id: s.h for s in m.slabs}
    beam_sec: dict = {}
    col_sec = {(i, j): m.col_section(i, j) for (i, j) in m.columns}
    braced = bool(m.cores)
    beam_why: dict = {}
    for it in range(8):
        changed = False
        floors = []
        for s in m.slabs:
            s.h = slab_h[s.id]
            ld = slab_loads(m, s.use, s.h)
            pans = pans_of[s.id]
            if not pans:
                continue
            pd = [dict(p, **design_panel(p, ld, s.h, mt, brittle)) for p in pans]
            bad = [p for p in pd if not p["ok"] and not p["core"]]
            if bad and s.h < 0.32:
                req = max(p["lx"] / p["ld_lim"] + mt["cover_slab"] + 0.005 for p in bad if p["ld_lim"] > 0)
                nh = min(0.32, max(ceil_to(req, 0.01), s.h + 0.01))
                slab_h[s.id] = nh
                changed = True
                continue
            key_sec = {}
            for name in {f"V{l}" for l in m.yl} | {f"V{l}" for l in m.xl}:
                key_sec[name] = beam_sec.get((s.id, name), m.beam_section)
            for (sid, name), sec in beam_sec.items():
                if sid == s.id:
                    key_sec[name] = sec
            with m.at_slab(s.id):
                bls = beam_lines(m, s, ld, key_sec, pans)
            beams = [design_beam(bl, mt, brittle) for bl in bls]
            for bm in beams:
                if not bm["ok"]:
                    b, h = bm["b"], bm["h"]
                    if h >= 1.20:
                        issues.append({"code": "BEAM-NOK", "level": BLOCK,
                                       "message": _(f"Poutre {bm['name']} ({s.name}) : section maximale atteinte sans vérifier ({', '.join(bm['why'])}).",
                                                    f"Viga {bm['name']} ({s.name}): secção máxima atingida sem verificar ({', '.join(bm['why'])})."),
                                       "fix": _("Ajouter un poteau ou revoir la trame.", "Acrescentar um pilar ou rever a trama.")})
                        continue
                    nh = round(h + 0.05, 2)
                    nb = round(b + 0.05, 2) if nh / b > 3.0 else b
                    beam_sec[(s.id, bm["name"])] = (nb, nh)
                    beam_why.setdefault((s.name, bm["name"]), set()).update(bm["why"])
                    changed = True
            floors.append({"slab": s, "loads": ld, "panels": pd, "beams": beams})
        if changed:
            continue
        # ---------------- descente de charges
        node = {c: {"G": [0.0] * len(m.slabs), "Q": [0.0] * len(m.slabs), "Mx": [0.0] * len(m.slabs), "My": [0.0] * len(m.slabs)} for c in m.columns}
        sidx = {s_.id: k for k, s_ in enumerate(m.slabs)}
        for fl in floors:
            si = sidx[fl["slab"].id]
            for bm in fl["beams"]:
                for k, idx in enumerate(bm["sup_idx"]):
                    c = (idx, bm["line"]) if bm["axis"] == "x" else (bm["line"], idx)
                    if c not in node:
                        continue
                    node[c]["G"][si] += bm["R_G"][k]
                    node[c]["Q"][si] += bm["R_Q"][k]
                    # moment de sous-portique (rive : moment d'encastrement partiel ; intérieur : charge Q alternée)
                    n = len(bm["spans"])
                    if k in (0, n):
                        sp = bm["spans"][0 if k == 0 else n - 1]
                        l = sp["L"]
                        w = sp["pU"]
                        Mfe = w * l * l / 12
                    else:
                        l = max(bm["spans"][k - 1]["L"], bm["spans"][k]["L"])
                        qq = max(bm["wQM"][k - 1], bm["wQM"][k])
                        Mfe = GAM_Q * qq * l * l / 12
                    key = "Mx" if bm["axis"] == "x" else "My"
                    node[c][key][si] = max(node[c][key][si], Mfe)
        cols = []
        ncols_fail = []
        nl = len(m.levels)
        for c in m.columns:
            b, h = col_sec[c]
            segs = []
            ok_all = True
            loaded = [si for si in range(len(m.slabs)) if node[c]["G"][si] > 0]
            z_top = max((m.slabs[si].z for si in loaded), default=None)          # le poteau s'arrête sous la plus haute dalle qu'il porte
            for k, lv in enumerate(m.levels):
                above = [si for si, s in enumerate(m.slabs) if s.z > lv.z + 1e-6 and (z_top is None or s.z <= z_top + 1e-6)]
                if not above or z_top is None or lv.z >= z_top - 1e-6:
                    continue
                NG = sum(node[c]["G"][si] for si in above) + RHO_C * b * h * sum(m.levels[q].height for q in range(k, nl) if m.levels[q].z < z_top - 1e-6)
                NQ = sum(node[c]["Q"][si] for si in above)
                NEd = GAM_G * NG + GAM_Q * NQ
                si_top = min(above, key=lambda s_: m.slabs[s_].z)
                # rigidités : poteau de l'étage, poteau au-dessus, poutre
                Hk = lv.height
                Ic = b * h ** 3 / 12
                kc_below = Ic / Hk
                kc_above = Ic / m.levels[k + 1].height if k + 1 < nl else 0.0
                bb_, hb_ = m.beam_section
                kb = (bb_ * hb_ ** 3 / 12) / 6.0
                share = kc_below / (kc_below + kc_above + kb)
                M0x = node[c]["Mx"][si_top] * share
                M0y = node[c]["My"][si_top] * share
                l0 = (0.7 if braced else 1.2) * Hk
                res_axes = {}
                for ax, dim, M0 in (("x", h, M0x), ("y", b, M0y)):
                    lam = l0 * math.sqrt(12) / dim
                    nrel = NEd / (b * h * mt["fcd"] * 1000)
                    lam_lim = 10.78 / math.sqrt(max(nrel, 0.05))
                    e0 = max(dim / 30, 0.02)
                    ei = l0 / 400
                    e2 = 0.0
                    if lam > lam_lim:
                        dd = dim - 0.05
                        e2 = 1.25 * (mt["fyd"] / ES) / (0.45 * dd) * l0 ** 2 / 10
                    Med = max(M0 + NEd * (ei + e2), NEd * e0)
                    res_axes[ax] = {"lam": lam, "lam_lim": lam_lim, "M0": M0, "e2": e2, "MEd": Med}
                dc = design_column(b, h, NEd, res_axes["x"]["MEd"], res_axes["y"]["MEd"], mt)
                if not dc["ok"]:
                    ok_all = False
                segs.append({"level": lv.id, "level_name": lv.name, "NG": NG, "NQ": NQ, "NEd": NEd, "Nser": NG + NQ,
                             "axes": res_axes, **dc})
            if not ok_all:
                if max(b, h) >= 0.90:
                    issues.append({"code": "COL-NOK", "level": BLOCK,
                                   "message": _(f"Poteau {m.node_name(*c)} : section maximale atteinte sans vérifier.",
                                                f"Pilar {m.node_name(*c)}: secção máxima atingida sem verificar."),
                                   "fix": _("Revoir la trame ou le béton.", "Rever a trama ou a classe de betão.")})
                else:
                    nb_, nh_ = round(b + 0.05, 2), round(h + 0.05, 2)
                    col_sec[c] = (nb_, nh_)
                    ncols_fail.append((m.node_name(*c), b, h, nb_, nh_))
                    changed = True
            if not segs:                                  # aucune dalle portée : pas de poteau à cette intersection
                continue
            cols.append({"node": c, "name": m.node_name(*c), "x": m.gx[c[0]], "y": m.gy[c[1]], "b": b, "h": h, "segs": segs,
                         "z_top": z_top})
        if changed:
            continue
        break
    else:
        issues.append({"code": "CALC-ITER", "level": WARN, "message": _("Redimensionnement non stabilisé après 8 itérations.",
                                                                       "Redimensionamento não estabilizado após 8 iterações.")})
    for sl in m.slabs:
        if abs(slab_h[sl.id] - sl.h) > 1e-6:
            decisions.append(_("Dalle {0} : épaisseur {1} → {2} m (flèche / flexion EN 1992-1-1)",
                               "Laje {0}: espessura {1} → {2} m (flecha / flexão NP EN 1992-1-1)").format(sl.name, num(sl.h), num(slab_h[sl.id])))
    WHY = {"flexion": ("flexion", "flexão"), "flèche": ("flèche", "flecha"), "bielle": ("effort tranchant", "esforço transverso"),
           "ferraillage": ("ferraillage", "armaduras")}
    b0, h0 = m.beam_section
    for (sname, bname), why in beam_why.items():
        sid = next(x.id for x in m.slabs if x.name == sname)
        nb, nh = beam_sec[(sid, bname)]
        decisions.append(_("Poutre {0} ({1}) : {2}×{3} → {4}×{5} ({6})", "Viga {0} ({1}): {2}×{3} → {4}×{5} ({6})").format(
            bname, sname, num(b0), num(h0), num(nb), num(nh), ", ".join(_(*WHY.get(w, (w, w))) for w in sorted(why))))
    grp: dict = {}
    for c, (b, h) in col_sec.items():
        b1, h1 = m.col_section(*c)
        if (b, h) != (b1, h1):
            grp.setdefault((b1, h1, b, h), []).append(m.node_name(*c))
    for (b1, h1, b, h), names in sorted(grp.items(), key=lambda kv: -kv[0][2]):
        decisions.append((_("Poteaux {0} : {1}×{2} → {3}×{4} (flexion composée, ν ≤ 0,85, ρ ≤ 3 %)",
                            "Pilares {0}: {1}×{2} → {3}×{4} (flexão composta, ν ≤ 0,85, ρ ≤ 3 %)") if not mt.get("dcm") else
                          _("Poteaux {0} : {1}×{2} → {3}×{4} (flexion composée, EC8 DCM : νd ≤ 0,65, 1 % ≤ ρ ≤ 4 %)",
                            "Pilares {0}: {1}×{2} → {3}×{4} (flexão composta, NP EN 1998-1 DCM: νd ≤ 0,65, 1 % ≤ ρ ≤ 4 %)")).format(
            ", ".join(sorted(names)), num(b1), num(h1), num(b), num(h)))
    balc = []
    for bc in m.balconies:
        l = float(bc.get("depth", 1.2))
        hb = float(bc.get("slab", 0.18))
        g = RHO_C * hb + 1.2
        Med = (GAM_G * g + GAM_Q * BALCONY_Q) * l * l / 2 + GAM_G * 1.0 * l + GAM_Q * 1.0 * 1.0   # dalle + garde-corps 1 kN/m + main courante 1 kN/m à 1 m
        d = hb - mt["cover_slab"] - 0.006
        r_ = design_rect(Med, 1.0, d, mt)
        As = max(r_["As"] or 0, as_min(1.0, d, mt))
        balc.append({"side": str(bc.get("side", "")).upper(), "depth": l, "h": hb, "a0": float(bc.get("a0", 0)), "a1": float(bc.get("a1", m.L)),
                     "levels": bc.get("levels") or [], "MEd": Med, "ok": r_["ok"], "top": pick_mesh(As, hb, True),
                     "ld": l / d, "ld_ok": l / d <= 8 * 1.5})
        if not r_["ok"] or l / d > 12:
            issues.append({"code": "BALC", "level": WARN, "message": _(f"Balcon {bc.get('side')} : console de {num(l)} m à épaissir.",
                                                                       f"Varanda {bc.get('side')}: consola de {num(l)} m a aumentar de espessura.")})
    fnd = foundations(m, cols, mt, issues)
    bas = basement(m, mt, issues)
    checks = review_checks(m, floors, cols, fnd, mt)
    seismic = seismic_estimate(m, floors, cols)
    return {"mat": mt, "floors": floors, "columns": cols, "foundations": fnd, "balconies": balc, "basement": bas, "decisions": list(dict.fromkeys(decisions)),
            "issues": issues, "checks": checks, "seismic": seismic, "braced": braced, "slab_h": slab_h}


# ================================================================ fondations
def foundations(m: Frame, cols: list[dict], mt: dict, issues: list) -> dict:
    geo = m.geo
    sigma = geo.get("sigma_adm_mpa")
    assumed = sigma in (None, "", 0)
    sigma = float(sigma or 0.20) * 1000.0      # kPa
    depth = float(geo.get("depth", 1.0) or 1.0)
    if assumed:
        issues.append({"code": "GEO-HYP", "level": WARN,
                       "message": _("Pas d'étude de sol : contrainte admissible 0,20 MPa et assise à 1,00 m retenues par défaut.",
                                    "Sem estudo geotécnico: tensão admissível 0,20 MPa e cota de fundação 1,00 m admitidas."),
                       "fix": _("Joindre l'étude G2 (contrainte admissible, niveau d'assise, eau).",
                                "Juntar o estudo geotécnico (tensão admissível, cota de fundação, nível freático).")})
    pads = []
    for c in cols:
        base = c["segs"][0]
        a, bcol = c["b"], c["h"]
        N = base["Nser"]
        Nu = base["NEd"]
        B = math.sqrt(N * 1.10 / sigma)
        B = max(0.80, ceil_to(B, 0.05))
        hf = max(0.40, ceil_to((B - min(a, bcol)) / 4 + 0.05, 0.05))
        d = hf - mt["cover_fond"] - 0.010
        As = Nu * (B - min(a, bcol)) / (8 * d * mt["fyd"] * 1000)
        As = max(As, 0.0010 * B * hf)
        mesh = pick_mesh(As / B, hf, False)
        if mesh["s"] > 0.25:
            mesh = pick_mesh(As / B, 0.125, True)
        pads.append({"name": "S" + c["name"], "node": c["node"], "x": c["x"], "y": c["y"], "B": B, "h": hf, "N": N, "NEd": Nu,
                     "sigma": N * 1.10 / (B * B), "As": As, "mesh": mesh})
    # recouvrements
    clash = 0
    by = {}
    for p in pads:
        by.setdefault(p["node"][1], []).append(p)
    strips = []
    for j, row in by.items():
        row.sort(key=lambda p: p["x"])
        for p1, p2 in zip(row, row[1:]):
            if (p2["x"] - p1["x"]) - (p1["B"] + p2["B"]) / 2 < 0.30:
                clash += 1
                strips.append((j, p1["name"], p2["name"]))
    total = sum(p["B"] ** 2 for p in pads)
    ratio = total / m.footprint
    kind = "isolees"
    if ratio > 0.50:
        kind = "radier"
        issues.append({"code": "FND-RAD", "level": WARN,
                       "message": _(f"Semelles isolées = {ratio * 100:.0f} % de l'emprise : un radier général est plus adapté.",
                                    f"Sapatas isoladas = {ratio * 100:.0f} % da implantação: um ensoleiramento geral é mais adequado."),
                       "fix": _("Faire confirmer par l'étude de sol (G2 PRO).", "Confirmar com o estudo geotécnico.")})
    elif clash:
        kind = "mixte"
        issues.append({"code": "FND-STRIP", "level": WARN,
                       "message": _(f"{clash} paires de semelles trop proches (< 0,30 m) : semelles filantes sous ces files.",
                                    f"{clash} pares de sapatas demasiado próximas (< 0,30 m): sapatas contínuas nesses alinhamentos."),
                       "fix": ""})
    cores = []
    for c in m.cores:
        cores.append({"id": c.get("id"), "x0": c["x0"] - 0.50, "x1": c["x1"] + 0.50, "y0": c["y0"] - 0.50, "y1": c["y1"] + 0.50,
                      "h": 0.60, "mesh": pick_mesh(0.0013 * 0.60, 0.60, False)})
    return {"sigma_kpa": sigma, "assumed": assumed, "depth": depth, "pads": pads, "strips": strips, "kind": kind,
            "ratio": ratio, "core_rafts": cores, "ties": [0.30, 0.50]}


# ================================================================ vérifications réglementaires simples
def review_checks(m: Frame, floors, cols, fnd, mt) -> list[dict]:
    out = []

    def ok(level, fr, pt):
        out.append({"level": level, "message": _(fr, pt)})
    h_top = max(l.z for l in m.levels if l.use not in ("toiture",)) - m.levels[0].z
    rf = "R60" if h_top <= 28 else "R90"
    need_col = 0.25 if rf == "R60" else 0.35
    need_slab = 0.08 if rf == "R60" else 0.10
    small = [c["name"] for c in cols if min(c["b"], c["h"]) < need_col]
    ok("OK" if not small else "avertissement",
       f"Feu {rf} (dernier plancher à {num(h_top, 1)} m) : poteaux ≥ {int(need_col * 100)} cm (EN 1992-1-2 tab. 5.2a)" + (f" — à épaissir : {', '.join(small[:8])}" if small else " — vérifié"),
       f"Fogo {rf} (último piso a {num(h_top, 1)} m): pilares ≥ {int(need_col * 100)} cm (NP EN 1992-1-2 quadro 5.2a)" + (f" — a aumentar: {', '.join(small[:8])}" if small else " — verificado"))
    thin = [fl["slab"].name for fl in floors if fl["slab"].h < need_slab]
    ok("OK" if not thin else "avertissement", f"Feu {rf} : dalles ≥ {int(need_slab * 100)} cm" + (" — non : " + ", ".join(thin) if thin else " — vérifié"),
       f"Fogo {rf}: lajes ≥ {int(need_slab * 100)} cm" + (" — não: " + ", ".join(thin) if thin else " — verificado"))
    if any(u for u in m.units):
        acou = [fl["slab"].name for fl in floors if fl["slab"].h < 0.18 and fl["slab"].use == "habitation"]
        ok("OK" if not acou else "avertissement",
           "Acoustique : dalles entre logements ≥ 18 cm" + (" — à épaissir : " + ", ".join(acou) if acou else " — vérifié"),
           "Acústica: lajes entre frações ≥ 18 cm (RRAE)" + (" — a aumentar: " + ", ".join(acou) if acou else " — verificado"))
    ok("avertissement",       # jamais « OK » : les noyaux ne sont pas dimensionnés ici
       "Contreventement : " + ("assuré par les noyaux BA (escaliers / ascenseur) — à justifier par un modèle 3D" if m.cores else
                               "AUCUN noyau relevé : portiques autostables, à justifier impérativement"),
       "Contraventamento: " + ("assegurado pelos núcleos BA (escadas / elevador) — a justificar com modelo 3D" if m.cores else
                               "NENHUM núcleo relevado: pórticos, a justificar obrigatoriamente"))
    return out


def seismic_estimate(m: Frame, floors, cols) -> dict:
    """Masse sismique et période fondamentale estimée (EN 1998-1 4.3.3.2.2) ; effort tranchant si ag est fourni."""
    mass = []
    for fl in floors:
        s = fl["slab"]
        ld = fl["loads"]
        with m.at_slab(s.id):
            fp = m.footprint
        g = ld["g"] * fp
        for bm in fl["beams"]:
            g += RHO_C * bm["b"] * max(bm["h"] - s.h, 0) * sum(x["L"] for x in bm["spans"])
        g += sum(RHO_C * c["b"] * c["h"] * 3.0 for c in cols)
        psi = {"habitation": 0.3, "bureaux": 0.3}.get(ld["use"], 0.6 if ld["use"] in ("commerce", "stationnement", "public") else 0.0)
        mass.append({"slab": s.name, "z": s.z - m.levels[0].z, "W_kN": g + psi * 0.8 * ld["q"] * fp})
    H = m.height_total
    if m.levels[0].z < -0.5:      # EC8 4.3.3.2.2 / 4.3.1(5) : H et masses comptés au-dessus de la cave rigide (piso 0)
        z0 = min((l.z for l in m.levels if l.z > -0.5), default=m.levels[0].z) - m.levels[0].z
        H = max(H - z0, 3.0)
        mass = [x for x in mass if x["z"] > z0 + 0.05] or mass
    T1 = 0.075 * H ** 0.75 if not m.cores else 0.05 * H ** 0.75
    seis = m.raw.get("seismic") or {}
    out = {"T1": T1, "H": H, "W_total": sum(x["W_kN"] for x in mass), "levels": mass, "ag": seis.get("ag")}
    if seis.get("ag"):
        ag = float(seis["ag"])
        q = float(seis.get("q", 3.0))
        S, TB, TC, TD = 1.2, 0.15, 0.5, 2.0
        if T1 <= TC:
            Sd = ag * S * 2.5 / q
        elif T1 <= TD:
            Sd = max(ag * S * 2.5 / q * TC / T1, 0.2 * ag)
        else:
            Sd = max(ag * S * 2.5 / q * TC * TD / T1 ** 2, 0.2 * ag)
        lam = 0.85 if (T1 <= 2 * TC and len(m.levels) > 2) else 1.0
        out["Fb_kN"] = Sd / 9.81 * out["W_total"] * lam
        out["Sd"] = Sd
    return out


# ================================================================ murs de sous-sol (poussée des terres)
def ground_z(m: Frame) -> float:
    if m.raw.get("terrain_z") is not None:
        return float(m.raw["terrain_z"])
    lv = m.levels
    if len(lv) > 1 and lv[0].on_grade and lv[0].use in ("stationnement", "technique"):
        return lv[1].z
    return lv[0].z


def basement(m: Frame, mt: dict, issues: list) -> dict | None:
    """Mur périphérique BA tenu en tête par le plancher et en pied par la semelle / le dallage (poutre bi-appuyée verticale),
    poussée des terres au repos K0 = 1 − sin φ' (φ' = 30°), γ = 20 kN/m³, surcharge 10 kPa."""
    zt = ground_z(m)
    H = round(zt - m.levels[0].z, 3)
    if H < 0.8:
        return None
    geo = m.geo
    phi = math.radians(float(geo.get("phi_deg", 30)))
    K0 = 1 - math.sin(phi)
    gam = float(geo.get("gamma", 20.0))
    q = 10.0
    water = bool(geo.get("water_level") not in (None, "", False))
    t = max(0.25, ceil_to(H / 12, 0.05))
    p_tri = K0 * gam * H
    p_uni = K0 * q
    M = GAM_G * 0.0642 * p_tri * H * H + GAM_Q * p_uni * H * H / 8
    V = GAM_G * p_tri * H / 3 + GAM_Q * p_uni * H / 2
    d = t - 0.040 - 0.006
    r = design_rect(M, 1.0, d, mt)
    while not r["ok"] and t < 0.60:
        t = round(t + 0.05, 2)
        d = t - 0.046
        r = design_rect(M, 1.0, d, mt)
    As = max(r["As"] or 0, as_min(1.0, d, mt))
    vert = pick_mesh(As, t, True)
    hor = pick_mesh(max(0.25 * vert["As"], 0.001 * t), t, False)
    outer = pick_mesh(max(0.5 * as_min(1.0, d, mt), 0.0015 * t), t, False)
    if water:
        issues.append({"code": "BAS-WATER", "level": WARN,
                       "message": _("Nappe signalée : murs et radier du sous-sol à justifier sous pression d'eau (cuvelage).",
                                    "Nível freático assinalado: muros e laje de fundo da cave a justificar com pressão de água (estanqueidade)."),
                       "fix": ""})
    return {"H": H, "t": t, "K0": K0, "gamma": gam, "q": q, "M": M, "V": V, "vert": vert, "hor": hor, "outer": outer,
            "ok": r["ok"], "ground_z": zt, "footing": (0.80, 0.40)}
