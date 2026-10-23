"""Pré-dimensionamento da estrutura de betão armado (Eurocódigos + Anexos Nacionais PT / FR).

Lajes maciças armadas em duas direções (structuro_slab2way), varandas em consola, descida de cargas por áreas de influência,
pilares à compressão (ν ≤ 0,65, NP/NF EN 1998-1 §5.4.3.2.1), vigas contínuas (structuro_ec2), ação sísmica pelo método das
forças laterais distribuída pela rigidez de núcleos e paredes com torção (EN 1998-1 §4.3.3.2 e §4.3.3.2.4), proposta automática
de paredes resistentes quando a torção não é controlada, muros de cave (impulso em repouso K0), sapatas e ensoleiramentos
(tensão de cálculo do estudo geotécnico ou presumida). Determinístico.
"""
from __future__ import annotations

import math

from engines import structuro_ec2 as ec2
from engines import structuro_slab2way as slab

from . import grelha, perfis
from .modelo import Spec, _wall

GC = 25.0
SECTIONS = [(0.25, 0.40), (0.25, 0.50), (0.30, 0.50), (0.30, 0.60), (0.30, 0.70), (0.35, 0.70), (0.40, 0.80), (0.45, 0.90), (0.50, 1.00)]
NU_MAX = 0.65


def mat(S: Spec) -> dict:
    fck = S.fck
    fcm = fck + 8
    Ecm = 22.0 * (fcm / 10) ** 0.3 * 1e6           # kPa
    return {"fck": fck, "fyk": S.fyk, "fcd": fck / 1.5, "fyd": S.fyk / 1.15, "Ec": Ecm}


# ------------------------------------------------------------------ cargas
def per_floor_loads(S: Spec) -> dict:
    Ld, h = S.loads, S.slab_h
    gb = 0.5 * (0.20 + 0.15) * GC + Ld["balcony"]["g2"]
    dmax = max([b["depth"] for b in S.balconies] or [1.0])
    return {"g_hab": h * GC + Ld["residential"]["g2"], "q_hab": Ld["residential"]["q"],
            "g_balc": gb + S.parapet_kn_m / dmax, "q_balc": Ld["balcony"]["q"],
            "g_roof": h * GC + Ld["roof"]["g2"], "q_roof": Ld["roof"]["q"],
            "g_gar": S.slab_hg * GC + Ld["garden"]["g2"], "q_gar": Ld["garden"]["q"], "g_fac": S.facade_kn_m}


def n_suspended(S: Spec) -> int:
    """Número de lajes de piso suspensas (sem a cobertura) : Piso 0 … Piso n−1 com cave, Piso 1 … Piso n−1 sem cave."""
    return S.n if S.basement else S.n - 1


# ------------------------------------------------------------------ 1. lajes e consolas
def slabs(S: Spec, pans: list[dict], gpans: list[dict]) -> list[dict]:
    M = mat(S)
    out = []
    for p, typ in [(p, "habitacao") for p in pans] + [(p, "jardim") for p in gpans]:
        a, b = p["x1"] - p["x0"], p["y1"] - p["y0"]
        e = p["edges"]
        lx, ly = min(a, b), max(a, b)
        ed = e if a <= b else {"x0": e["y0"], "x1": e["y1"], "y0": e["x0"], "y1": e["x1"]}
        key = "garden" if typ == "jardim" else "residential"
        hh = S.slab_hg if typ == "jardim" else S.slab_h
        Ld = S.loads[key]
        r = slab.design(lx, ly, hh, Ld["g2"], Ld["q"], ed, fck=M["fck"], fyk=M["fyk"], cover_m=0.025, psi2=Ld["psi2"])
        ok = bool(r.get("ok", True)) if isinstance(r, dict) else True
        out.append({**p, "lx": round(lx, 2), "ly": round(ly, 2), "h": hh, "type": typ, "r": r, "ok": ok})
    return out


def cantilever(S: Spec, depth: float, h_root=0.20) -> dict:
    M = mat(S)
    Ld = S.loads["balcony"]
    g = 0.5 * (h_root + 0.15) * GC + Ld["g2"]
    pu_ = 1.35 * g + 1.5 * Ld["q"]
    P = 1.35 * S.parapet_kn_m
    Med = pu_ * depth ** 2 / 2 + P * depth
    Ved = pu_ * depth + P
    r = ec2.design_section(Med, Ved, b_m=1.0, h_m=h_root, d_m=h_root - 0.035, fck=M["fck"], fyk=M["fyk"])
    gk, qk = g + S.parapet_kn_m / depth, Ld["q"]
    EI = M["Ec"] * h_root ** 3 / 12 / 2.5
    w = (gk * 3 + 0.3 * qk) * depth ** 4 / (8 * EI) * 1000
    return {"depth": depth, "h_root": h_root, "h_tip": 0.15, "pu": round(pu_, 2), "M_Ed": round(Med, 1), "V_Ed": round(Ved, 1),
            "as_cm2_m": r["flexure"]["as_cm2"], "w_mm": round(w, 1), "w_lim_mm": round(depth * 2 / 250 * 1000, 1), "vrdc": r["shear"]["vrdc_kn"]}


# ------------------------------------------------------------------ 2. descida de cargas
def load_takedown(S: Spec, trib: dict) -> list[dict]:
    f = per_floor_loads(S)
    nf = n_suspended(S)
    rows = []
    for eid, a in trib.items():
        G_floor = a["hab"] * f["g_hab"] + a["balc"] * f["g_balc"] + a["fac"] * f["g_fac"]
        Q_floor = a["hab"] * f["q_hab"] + a["balc"] * f["q_balc"]
        G_roof = (a["hab"] + a["balc"]) * f["g_roof"] + a["fac"] * S.parapet_kn_m
        Q_roof = (a["hab"] + a["balc"]) * f["q_roof"]
        if a["hab"] + a["balc"] + a["fac"] == 0:
            G_floor = Q_floor = G_roof = Q_roof = 0.0
        G_gar, Q_gar = a["gar"] * f["g_gar"], a["gar"] * f["q_gar"]
        rows.append({"id": eid, "A_hab": a["hab"], "A_balc": a["balc"], "L_fac": a["fac"], "A_gar": a["gar"],
                     "G_floor": round(G_floor, 1), "Q_floor": round(Q_floor, 1), "G_roof": round(G_roof, 1), "Q_roof": round(Q_roof, 1),
                     "G_gar": round(G_gar, 1), "Q_gar": round(Q_gar, 1),
                     "G": round(nf * G_floor + G_roof + G_gar, 1), "Q": round(nf * Q_floor + Q_roof + Q_gar, 1)})
    return rows


def storeys(S: Spec) -> list[int]:
    """Índices dos pisos estruturais (troços de pilar) de baixo para cima : −1 (cave) … n−1."""
    return list(range(-1 if S.basement else 0, S.n))


def _floors_above(S: Spec, j: int) -> int:
    """Número de lajes de piso suspensas acima do troço j (sem a cobertura)."""
    return S.n if j == -1 else S.n - 1 - j


def size_columns(S: Spec, rows: list[dict]) -> list[dict]:
    """Pilares : N_Ed no troço inferior de cada grupo (base e topo) ; ν = N_Ed/(Ac·fcd) ≤ 0,65 ; secção ≥ secção de arquitetura."""
    M = mat(S)
    by = {r["id"]: r for r in rows}
    st = storeys(S)
    j_split = max(st[0] + 1, S.n // 2) if len(st) > 2 else None
    groups = [("base", st[0])] + ([("topo", j_split)] if j_split is not None and j_split > st[0] else [])
    out = []
    for c in grelha.free_columns(S) + [dict(c, b=None, h=None, garage=True) for c in S.bcols]:
        r = by.get(c["id"])
        if not r:
            continue
        res = {}
        for tag, j in groups:
            if c.get("garage") and tag != "base":
                continue
            nfl = _floors_above(S, j)
            G = nfl * r["G_floor"] + r["G_roof"] + (r["G_gar"] if j == -1 else 0.0)
            Q = nfl * r["Q_floor"] + r["Q_roof"] + (r["Q_gar"] if j == -1 else 0.0)
            if c.get("garage"):
                G, Q = r["G_gar"], r["Q_gar"]
            n_seg = (S.n - j) if not c.get("garage") else 1
            b0, h0 = c.get("b") or 0.0, c.get("h") or 0.0
            cand = [(b, h) for b, h in SECTIONS if b >= b0 - 1e-6 and h >= h0 - 1e-6] or [(max(b0, 0.25), max(h0, 0.40))]
            if c.get("garage"):
                cand = [(0.30, 0.30)] + cand
            for b, h in cand:
                selfw = b * h * GC * S.H * n_seg
                Ned = 1.35 * (G + selfw) + 1.5 * Q
                nu = Ned / (b * h * M["fcd"] * 1000)
                if nu <= NU_MAX or (b, h) == cand[-1]:
                    break
            Nser = G + selfw + Q
            as_min = max(0.10 * Ned / (M["fyd"] * 1000) * 1e4, 0.01 * b * h * 1e4)
            res[tag] = {"b": b, "h": h, "N_Ed": round(Ned, 0), "N_ser": round(Nser, 0), "nu": round(nu, 3), "As_cm2": round(as_min, 1),
                        "from": j, "ok": nu <= NU_MAX + 1e-9}
        if "topo" not in res and len(groups) > 1 and not c.get("garage"):
            res["topo"] = res["base"]
        out.append({"id": c["id"], "x": c["x"], "y": c["y"], "garage": bool(c.get("garage")), "arch": (c.get("b"), c.get("h")),
                    "groups": [g for g in groups if g[0] in res], **res})
    return out


def bars(as_cm2, n_min=4, diams=(12, 16, 20, 25)):
    for d in diams:
        a1 = math.pi * d * d / 400
        n = max(n_min, math.ceil(as_cm2 / a1))
        if n % 2:
            n += 1
        if n <= 12:
            return f"{n}Ø{d}", round(n * a1, 1)
    n = math.ceil(as_cm2 / 4.91)
    return f"{n}Ø25", round(n * 4.91, 1)


def beam_bars(as_cm2):
    for d in (12, 16, 20, 25):
        a1 = math.pi * d * d / 400
        n = max(2, math.ceil(as_cm2 / a1))
        if n <= 5:
            return f"{n}Ø{d}", round(n * a1, 1)
    n = math.ceil(as_cm2 / 4.91)
    return f"{n}Ø25", round(n * 4.91, 1)


def mesh(as_cm2_m, diams=(8, 10, 12, 16, 20), s_max=25.0):
    """Armadura por metro : menor diâmetro com espaçamento ≥ 10 cm (múltiplo de 2,5 cm, máx. 25 cm) → (« Ø8//0,20 », cm²/m)."""
    for d in diams:
        a1 = math.pi * d * d / 400
        s_cm = min(math.floor(a1 / max(as_cm2_m, 1e-6) * 100 / 2.5) * 2.5, s_max)
        if s_cm >= 10:
            lab = f"{s_cm / 100:.3f}".rstrip("0")
            if len(lab.split(".")[1]) < 2:
                lab += "0"
            return f"Ø{d}//{lab.replace('.', ',')}", round(a1 / s_cm * 100, 2)
    return "Ø20//0,10", 31.42


# ------------------------------------------------------------------ 3. vigas
def _beam_trib(seg, pans) -> float:
    """Largura de influência equivalente (m) dos painéis adjacentes a um troço de viga (cargas trapezoidais/triangulares)."""
    (ax, ay), (bx, by) = seg["a"], seg["b"]
    horiz = abs(ay - by) < 1e-6
    w = 0.0
    lo, hi = (min(ax, bx), max(ax, bx)) if horiz else (min(ay, by), max(ay, by))
    for p in pans:
        if horiz:
            touch = abs(p["y0"] - ay) < 0.15 or abs(p["y1"] - ay) < 0.15
            ov = min(hi, p["x1"]) - max(lo, p["x0"])
            par, perp = p["x1"] - p["x0"], p["y1"] - p["y0"]
        else:
            touch = abs(p["x0"] - ax) < 0.15 or abs(p["x1"] - ax) < 0.15
            ov = min(hi, p["y1"]) - max(lo, p["y0"])
            par, perp = p["y1"] - p["y0"], p["x1"] - p["x0"]
        if not touch or ov < 0.3:
            continue
        lx, ly = min(par, perp), max(par, perp)
        if par >= perp:          # viga ao longo do lado maior : trapézio
            w += lx / 2 * (1 - (lx / ly) ** 2 / 3)
        else:                    # viga no lado menor : triângulo
            w += lx / 3
    return max(w, 0.5)


def beams(S: Spec, segs: list[dict], pans: list[dict]) -> list[dict]:
    M = mat(S)
    f = per_floor_loads(S)
    h = S.slab_h
    out = []
    for sg in segs:
        tw = _beam_trib(sg, pans)
        facade = sg["facade"] is not None
        balc = None
        if facade:
            for bb in S.balconies:
                if bb["side"] == sg["facade"]:
                    lo, hi = (min(sg["a"][0], sg["b"][0]), max(sg["a"][0], sg["b"][0])) if sg["facade"] in ("y0", "y1") else \
                        (min(sg["a"][1], sg["b"][1]), max(sg["a"][1], sg["b"][1]))
                    if min(hi, bb["to"]) - max(lo, bb["from"]) > 0.5 * (hi - lo):
                        balc = bb
        g = tw * f["g_hab"] + (f["g_fac"] if facade else 0) + (balc["depth"] * f["g_balc"] if balc else 0)
        q = tw * f["q_hab"] + (balc["depth"] * f["q_balc"] if balc else 0)
        b = 0.25
        span, cont = sg["L"], sg["cont"]
        for hb in (0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.80):
            if hb < h + 0.15:
                continue
            gs = b * (hb - h) * GC
            p = 1.35 * (g + gs) + 1.5 * q
            M_sp = p * span ** 2 / (11 if cont else 8)
            M_sup = p * span ** 2 / 10 if cont else p * span ** 2 / 24
            V = (0.6 if cont else 0.5) * p * span
            d = hb - 0.05
            r = ec2.design_section(max(M_sp, M_sup), V, b_m=b, h_m=hb, d_m=d, fck=M["fck"], fyk=M["fyk"])
            ps = g + gs + 0.3 * q
            EI = M["Ec"] * b * hb ** 3 / 12 / 2.0
            w = 5 * ps * span ** 4 / (384 * EI) * (0.6 if cont else 1.0) * 3 * 1000
            ok = r["flexure"].get("ok", True) and w <= span / 250 * 1000 and r["flexure"]["as_cm2"] / (b * d * 1e4) < 0.02
            if ok:
                break
        out.append({"name": sg["name"], "line": sg["line"], "a": sg["a"], "b": sg["b"], "L": span, "b_w": b, "h": hb, "trib": round(tw, 2),
                    "w_kNm": round(p, 1), "M_sp": round(M_sp, 1), "M_sup": round(M_sup, 1), "V": round(V, 1), "As": r["flexure"]["as_cm2"],
                    "Asw": r["shear"].get("asw_s_cm2_m"), "w_mm": round(w, 1), "facade": facade, "ok": bool(ok)})
    return out


# ------------------------------------------------------------------ 4. sismo
def _sd(T, ag, S_, TB, TC, TD, q, beta=0.2):
    if T < TB:
        v = ag * S_ * (2 / 3 + T / TB * (2.5 / q - 2 / 3))
    elif T <= TC:
        v = ag * S_ * 2.5 / q
    elif T <= TD:
        v = ag * S_ * 2.5 / q * TC / T
    else:
        v = ag * S_ * 2.5 / q * TC * TD / T ** 2
    return max(v, beta * ag)


def spectra(S: Spec) -> list[dict]:
    """Ações sísmicas regulamentares : PT → tipo 1 e tipo 2 ; FR → espectro da zona. [{label, ag, S, TB, TC, TD}]"""
    se, gt = S.seismic, S.soil["ground"]
    if S.country == "FR":
        z = se["zone"]
        agr = perfis.AGR_FR.get(z, 0.7)
        ag = perfis.GAMMA_I_FR.get(se["importance"], 1.0) * agr
        Sx, TB, TC, TD = perfis.SOIL_FR["5" if z == "5" else "1-4"].get(gt, perfis.SOIL_FR["1-4"]["B"])
        return [{"label": f"zone {z}", "type": z, "zone": z, "agR": agr, "ag": ag, "S": Sx, "TB": TB, "TC": TC, "TD": TD}]
    out = []
    for typ, zone in ((1, se["zone1"]), (2, se["zone2"])):
        agr = perfis.AGR_PT.get(zone, 0.35 if typ == 1 else 0.8)
        ag = perfis.GAMMA_I_PT[typ].get(se["importance"], 1.0) * agr
        Smax, TB, TC, TD = perfis.SOIL_PT[typ].get(gt, perfis.SOIL_PT[typ]["B"])
        Sx = Smax if ag <= 1 else (1.0 if ag >= 4 else Smax - (Smax - 1) * (ag - 1) / 3)
        out.append({"label": f"tipo {typ} (zona {zone})", "type": typ, "zone": zone, "agR": agr, "ag": ag, "S": Sx, "TB": TB, "TC": TC, "TD": TD})
    return out


def seismic_required(S: Spec) -> bool:
    if S.country == "FR":
        z = int(S.seismic["zone"])
        imp = S.seismic["importance"]
        return z >= 3 or (z == 2 and imp in ("III", "IV"))
    return True


def _rect(x0, y0, x1, y1):
    a = (x1 - x0) * (y1 - y0)
    return a, (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) * (y1 - y0) ** 3 / 12, (y1 - y0) * (x1 - x0) ** 3 / 12


def core_section(core: dict) -> dict:
    x0, y0, x1, y1 = core["box"]
    t = core["t"]
    parts = [(x0, y0, x1, y0 + t), (x0, y1 - t, x1, y1), (x0, y0 + t, x0 + t, y1 - t), (x1 - t, y0 + t, x1, y1 - t)]
    door, side = core.get("door") or 0.0, core.get("door_side")
    if door > 0 and side:
        if side == "x1":
            parts[3] = (x1 - t, y0 + t, x1, max(y0 + t, y1 - t - door))
        elif side == "x0":
            parts[2] = (x0, min(y1 - t, y0 + t + door), x0 + t, y1 - t)
        elif side == "y0":
            parts[0] = (x0, y0, max(x0, x1 - door), y0 + t)
        elif side == "y1":
            parts[1] = (min(x1, x0 + door), y1 - t, x1, y1)
    parts = [p for p in parts if p[2] - p[0] > 1e-6 and p[3] - p[1] > 1e-6]
    A = sum(_rect(*p)[0] for p in parts)
    cx = sum(_rect(*p)[0] * _rect(*p)[1] for p in parts) / A
    cy = sum(_rect(*p)[0] * _rect(*p)[2] for p in parts) / A
    Ix = sum(r[3] + r[0] * (r[2] - cy) ** 2 for r in (_rect(*p) for p in parts))
    Iy = sum(r[4] + r[0] * (r[1] - cx) ** 2 for r in (_rect(*p) for p in parts))
    return {"A": A, "cx": cx, "cy": cy, "Ix": Ix, "Iy": Iy, "Lx": x1 - x0, "Ly": y1 - y0, "parts": parts}


def lateral_elements(S: Spec) -> list[dict]:
    els = []
    for c in S.cores:
        cs = core_section(c)
        els.append({"id": c["id"], "kind": "core", "x": cs["cx"], "y": cs["cy"], "Ix": cs["Ix"], "Iy": cs["Iy"], "A": cs["A"],
                    "Lx": cs["Lx"], "Ly": cs["Ly"], "t": c["t"]})
    for w in S.walls:
        Lw, t = w["Lw"], w["t"]
        x, y = (w["x0"] + w["x1"]) / 2, (w["y0"] + w["y1"]) / 2
        if w["axis"] == "Y":
            els.append({"id": w["id"], "kind": "wall", "axis": "Y", "x": x, "y": y, "Ix": t * Lw ** 3 / 12, "Iy": Lw * t ** 3 / 12, "A": t * Lw,
                        "Lx": t, "Ly": Lw, "t": t})
        else:
            els.append({"id": w["id"], "kind": "wall", "axis": "X", "x": x, "y": y, "Ix": Lw * t ** 3 / 12, "Iy": t * Lw ** 3 / 12, "A": t * Lw,
                        "Lx": Lw, "Ly": t, "t": t})
    return els


def storey_masses(S: Spec) -> list[dict]:
    """Pesos sísmicos (G + ψ2·Q) das lajes acima da base sísmica (Piso 0 com cave rígida, terreno sem cave)."""
    f = per_floor_loads(S)
    Ld = S.loads
    A_hab, A_balc, per = S.area_floor, S.balcony_area(), 2 * (S.L + S.B)
    n_col = len(grelha.free_columns(S))
    vert = 0.25 * 0.45 * GC * S.H * n_col + sum(core_section(c)["A"] for c in S.cores) * GC * S.H + \
        sum(w["Lw"] * w["t"] for w in S.walls) * GC * S.H
    out = []
    for k in range(1, S.n + 1):
        roof = k == S.n
        if roof:
            W = (A_hab + A_balc) * (f["g_roof"] + Ld["roof"]["psi2"] * f["q_roof"]) + per * S.parapet_kn_m + per * f["g_fac"] / 2 + vert / 2
        else:
            W = A_hab * (f["g_hab"] + Ld["residential"]["psi2"] * f["q_hab"]) + A_balc * (f["g_balc"] + Ld["balcony"]["psi2"] * f["q_balc"]) + \
                per * f["g_fac"] + vert
        out.append({"k": k, "level": S.lname(k), "z": k * S.H, "W": round(W, 0)})
    return out


def regularity(S: Spec, els: list[dict]) -> dict:
    KX = sum(e["Iy"] for e in els)
    KY = sum(e["Ix"] for e in els)
    if KX <= 0 or KY <= 0:
        return {"ok": False, "KX": KX, "KY": KY}
    xr = sum(e["Ix"] * e["x"] for e in els) / KY
    yr = sum(e["Iy"] * e["y"] for e in els) / KX
    xm, ym = S.L / 2, S.B / 2
    J = sum(e["Iy"] * (e["y"] - yr) ** 2 + e["Ix"] * (e["x"] - xr) ** 2 for e in els)
    if J <= 1e-9 or KX <= 1e-6 or KY <= 1e-6:
        return {"ok": False, "KX": KX, "KY": KY, "score": 99.0}
    r_x, r_y = math.sqrt(J / KX), math.sqrt(J / KY)
    ls = math.sqrt((S.L ** 2 + S.B ** 2) / 12)
    e0x, e0y = abs(xm - xr), abs(ym - yr)
    strong_x = sum(1 for e in els if e["Lx"] >= 1.0)            # elementos com rigidez real segundo X (núcleos, paredes X)
    strong_y = sum(1 for e in els if e["Ly"] >= 1.0)
    ok = e0x <= 0.30 * r_x and e0y <= 0.30 * r_y and r_x >= ls and r_y >= ls and strong_x > 0 and strong_y > 0
    score = max(e0x / (0.30 * r_x), e0y / (0.30 * r_y), ls / r_x, ls / r_y) + (10.0 if not strong_x else 0.0) + (10.0 if not strong_y else 0.0)
    return {"ok": ok, "strong_x": strong_x, "strong_y": strong_y, "KX": KX, "KY": KY, "xr": xr, "yr": yr, "xm": xm, "ym": ym, "J": J, "r_x": r_x, "r_y": r_y, "ls": ls,
            "e0x": e0x, "e0y": e0y, "score": score}


def wall_candidates(S: Spec) -> list[dict]:
    """Paredes possíveis entre pilares consecutivos alinhados (2,0 a 5,0 m), de preferência nas empenas."""
    cols = S.columns
    cands = []
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            if abs(a["x"] - b["x"]) < 0.05:
                d = abs(a["y"] - b["y"])
                axis = "Y"
            elif abs(a["y"] - b["y"]) < 0.05:
                d = abs(a["x"] - b["x"])
                axis = "X"
            else:
                continue
            if not 2.0 <= d <= 5.0:
                continue
            between = [c for c in cols if c is not a and c is not b and grelha.dist_seg(c["x"], c["y"], (a["x"], a["y"]), (b["x"], b["y"])) < 0.10]
            if between:
                continue
            mid = ((a["x"] + b["x"]) / 2, (a["y"] + b["y"]) / 2)
            if grelha._inside_core(S, *mid, margin=-0.3):
                continue
            if any(grelha.dist_seg(mid[0], mid[1], (w["x0"], w["y0"]), (w["x1"], w["y1"])) < 0.3 for w in S.walls):
                continue
            on_gable = (axis == "Y" and (abs(a["x"]) < 0.05 or abs(a["x"] - S.L) < 0.05)) or \
                       (axis == "X" and (abs(a["y"]) < 0.05 or abs(a["y"] - S.B) < 0.05))
            side = None
            if on_gable:
                side = ("x0" if abs(a["x"]) < 0.05 else "x1") if axis == "Y" else ("y0" if abs(a["y"]) < 0.05 else "y1")
            cands.append({"a": a, "b": b, "axis": axis, "L": d, "gable": on_gable, "side": side})
    return cands


def propose_walls(S: Spec, max_walls: int = 4) -> list[dict]:
    """Proposta gulosa de paredes resistentes (e = 0,25) que traz o centro de rigidez para o centro de massa e cumpre r ≥ ls."""
    added = []
    glazed = {(o.get("facade") or "").upper() for u in S.units for o in u.get("openings") or []}
    for _ in range(max_walls):
        els = lateral_elements(S)
        reg = regularity(S, els) if els else {"ok": False, "score": 99}
        if reg.get("ok"):
            break
        best = None
        for c in wall_candidates(S):
            w = _wall(f"W{len(S.walls) + 1}", c["a"]["x"], c["a"]["y"], c["b"]["x"], c["b"]["y"], 0.25, True)
            S.walls.append(w)
            r2 = regularity(S, lateral_elements(S))
            S.walls.pop()
            # preferência : empena sem vãos < parede interior < fachada com vãos
            pen = 0.10 if not c["gable"] else (0.25 if S.side_orientation(c["side"]) in glazed else 0.0)
            sc = r2.get("score", 99) + pen
            if best is None or sc < best[0]:
                best = (sc, w)
        if best is None:
            break
        S.walls.append(best[1])
        added.append(best[1])
    return added


def seismic(S: Spec, rows: list[dict]) -> dict:
    M = mat(S)
    q = S.seismic["q"]
    sts = storey_masses(S)
    Wt = sum(s["W"] for s in sts)
    H = S.n * S.H
    T1 = 0.05 * H ** 0.75
    acts = []
    for sp in spectra(S):
        sd = _sd(T1, sp["ag"], sp["S"], sp["TB"], sp["TC"], sp["TD"], q)
        lam = 0.85 if (T1 <= 2 * sp["TC"] and S.n > 2) else 1.0
        acts.append({**sp, "Sd": round(sd, 3), "lam": lam, "Fb": round(sd / 9.81 * Wt * lam, 0)})
    gov = max(acts, key=lambda a: a["Fb"])
    req = seismic_required(S)
    sz = sum(s["z"] * s["W"] for s in sts) or 1.0
    for s in sts:
        s["F"] = round(gov["Fb"] * s["z"] * s["W"] / sz, 1)
    M0 = sum(s["F"] * s["z"] for s in sts)
    Fd, M0d = {"X": gov["Fb"], "Y": gov["Fb"]}, {"X": M0, "Y": M0}
    wind = None
    if not req:
        # sem exigência sísmica regulamentar : contraventamento verificado ao vento (forfait c_f·q_p, EN 1991-1-4)
        qp = float((S.raw.get("wind") or {}).get("qp_kpa") or (0.8 if S.country == "FR" else 0.9))
        Fd = {"X": round(1.3 * qp * S.B * H, 0), "Y": round(1.3 * qp * S.L * H, 0)}
        M0d = {d: Fd[d] * H / 2 for d in Fd}
        wind = {"qp": qp, "cf": 1.3, "Fx": Fd["X"], "Fy": Fd["Y"]}
        gov = dict(gov, label=S.t("vento (forfait)", "vent (forfait)"), Fb=max(Fd.values()))
        for s in sts:
            s["F"] = round(max(Fd.values()) * (S.H if s["k"] < S.n else S.H / 2) / H, 1)
    els = lateral_elements(S)
    reg = regularity(S, els)
    if not els or not reg.get("KX") or not reg.get("KY"):
        return {"ok": False, "reason": "no_lateral", "q": q, "H": H, "T1": T1, "W": Wt, "storeys": sts, "acts": acts, "gov": gov, "elems": els}
    KX, KY, J, xr, yr = reg["KX"], reg["KY"], reg["J"], reg["xr"], reg["yr"]
    dist = {}
    for d, K in (("X", KX), ("Y", KY)):
        e0 = (reg["ym"] - yr) if d == "X" else (reg["xm"] - xr)
        ea = 0.05 * (S.B if d == "X" else S.L)
        shares = []
        for e in els:
            k = e["Iy"] if d == "X" else e["Ix"]
            ki = e["Iy"] * (e["y"] - yr) if d == "X" else e["Ix"] * (e["x"] - xr)
            tors = max(abs(e0 + ea), abs(e0 - ea)) * abs(ki) / J
            sh = k / K + tors
            shares.append({"id": e["id"], "share": round(sh, 3), "V": round(sh * Fd[d], 0), "M": round(sh * M0d[d], 0)})
        dist[d] = {"e0": round(e0, 2), "ea": round(ea, 2), "elems": shares}
    drift = {}
    for d, K in (("X", KX), ("Y", KY)):
        EI = 0.5 * M["Ec"] * K
        dtop = 11 * Fd[d] * H ** 3 / (60 * EI) * 1.3
        ds = (q if req else 1.0) * dtop
        dr = ds / S.n * 1.4
        nu_r = 0.5 if S.country == "FR" else 0.5
        drift[d] = {"d_e_mm": round(dtop * 1000, 1), "d_s_mm": round(ds * 1000, 1), "dr_mm": round(dr * 1000, 1),
                    "nu_dr_mm": round(nu_r * dr * 1000, 1), "lim_mm": round(0.005 * S.H * 1000, 1)}
    by = {r["id"]: r for r in rows}
    core_design, wall_design = [], []
    for e in els:
        r = by.get(e["id"], {"G": 0.0, "Q": 0.0})
        n_seg = len(storeys(S))
        G = r["G"] + e["A"] * GC * S.H * n_seg
        N = G + 0.3 * r["Q"]
        out = {"id": e["id"], "kind": e["kind"], "N_sis": round(N, 0), "t": e["t"],
               "nu": round((1.35 * G + 1.5 * r["Q"]) / (e["A"] * M["fcd"] * 1000), 3)}
        for d in ("X", "Y"):
            Mx = next(s["M"] for s in dist[d]["elems"] if s["id"] == e["id"])
            V = next(s["V"] for s in dist[d]["elems"] if s["id"] == e["id"])
            Lw = e["Lx"] if d == "X" else e["Ly"]
            webs = 2 if e["kind"] == "core" else 1
            z = 0.8 * Lw
            As_end = max((Mx / z - N / 2) / (M["fyd"] * 1000) * 1e4, 0.005 * e["t"] * max(0.15 * Lw, 1.5 * e["t"]) * 1e4)
            vrdc = 0.35 * 1000 * e["t"] * 0.9 * Lw * webs
            rho_h = max((V * 1.5 - vrdc) / (webs * e["t"] * 0.9 * Lw * M["fyd"] * 1000), 0.0)
            out[d] = {"M": Mx, "V": V, "Lw": round(Lw, 2), "As_ext_cm2": round(As_end, 1), "VRdc": round(vrdc, 0), "rho_h": round(max(rho_h, 0.002), 4)}
        (core_design if e["kind"] == "core" else wall_design).append(out)
    return {"ok": True, "required": req, "wind": wind, "q": q, "H": H, "T1": round(T1, 3), "W": Wt, "storeys": sts, "acts": acts, "gov": gov,
            "M0": round(M0, 0), "elems": els, "reg": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in reg.items()},
            "dist": dist, "drift": drift, "cores": core_design, "walls": wall_design}


# ------------------------------------------------------------------ 5. muros de cave e fundações
def basement_walls(S: Spec, t=0.25, gamma=20.0, K0=0.50, surcharge=10.0) -> list[dict]:
    M = mat(S)
    out = []
    for w in S.bwalls:
        (x0, y0), (x1, y1) = S.bpoly[w["i0"]], S.bpoly[w["i1"]]
        ln = math.hypot(x1 - x0, y1 - y0)
        ht = w["ht"]
        if ht <= 0:
            out.append({"name": w["name"], "L": round(ln, 2), "ht": 0.0, "t": 0.20, "M": 0.0, "As": 4.0, "p0": (x0, y0), "p1": (x1, y1)})
            continue
        h = S.H
        pt = K0 * gamma * ht
        pq = K0 * surcharge
        Med = 1.35 * 0.064 * pt * h ** 2 * (ht / h) + 1.5 * pq * h ** 2 / 8
        Ved = 1.35 * pt * ht / 3 + 1.5 * pq * h / 2
        r = ec2.design_section(Med, Ved, b_m=1.0, h_m=t, d_m=t - 0.05, fck=M["fck"], fyk=M["fyk"])
        out.append({"name": w["name"], "L": round(ln, 2), "ht": ht, "t": t, "M": round(Med, 1), "V": round(Ved, 1),
                    "As": max(r["flexure"]["as_cm2"], 0.002 * t * 1e4), "vrdc": r["shear"]["vrdc_kn"], "p0": (x0, y0), "p1": (x1, y1)})
    return out


def footings(S: Spec, cols: list[dict]) -> list[dict]:
    M = mat(S)
    srd, sels = S.soil["sigma_rd"], S.soil["sigma_sls"]
    out = []
    for c in cols:
        N, Ns = c["base"]["N_Ed"], c["base"]["N_ser"]
        A_req = max(N / srd, Ns / sels)
        b, h = c["base"]["b"], c["base"]["h"]
        a = math.sqrt(A_req * h / b)
        bb = A_req / a
        Ls = max(math.ceil(a / 0.05) * 0.05, 1.20)
        Bs = max(math.ceil(bb / 0.05) * 0.05, 1.20)
        hs = max(0.50, math.ceil(max(Ls - h, Bs - b) / 4 / 0.05) * 0.05 + 0.05)
        p = N / (Ls * Bs)
        Mx = p * Bs * ((Ls - h) / 2) ** 2 / 2
        r = ec2.design_section(Mx, 0, b_m=Bs, h_m=hs, d_m=hs - 0.06, fck=M["fck"], fyk=M["fyk"])
        out.append({"id": c["id"], "x": c["x"], "y": c["y"], "N_Ed": N, "N_ser": Ns, "L": round(Ls, 2), "B": round(Bs, 2), "h": round(hs, 2),
                    "sigma_Ed": round(p, 0), "As_cm2": round(max(r["flexure"]["as_cm2"], 0.0015 * Bs * hs * 1e4), 1),
                    "x0": round(c["x"] - Bs / 2, 2), "y0": round(c["y"] - Ls / 2, 2), "x1": round(c["x"] + Bs / 2, 2), "y1": round(c["y"] + Ls / 2, 2)})
    return out


def rafts(S: Spec, seis: dict, rows: list[dict]) -> list[dict]:
    """Ensoleiramentos sob núcleos e paredes : N gravítico (ELU) e N + M sísmico (largura efetiva de Meyerhof)."""
    srd = S.soil["sigma_rd"]
    by = {r["id"]: r for r in rows}
    boxes = {c["id"]: c["box"] for c in S.cores}
    for w in S.walls:
        t = w["t"]
        boxes[w["id"]] = (w["x0"] - t / 2, w["y0"] - t / 2, w["x1"] + t / 2, w["y1"] + t / 2)
    areas = {e["id"]: e["A"] for e in seis.get("elems") or []}
    items = []
    for dsg in (seis.get("cores") or []) + (seis.get("walls") or []):
        items.append((dsg["id"], boxes[dsg["id"]], dsg["N_sis"], dsg["X"]["M"], dsg["Y"]["M"], dsg["kind"]))
    out = []
    n_seg = len(storeys(S))
    for nm, box, Nsis, MX, MY, kind in items:
        x0, y0, x1, y1 = box
        r = by.get(nm, {"G": 0.0, "Q": 0.0})
        G = r["G"] + areas.get(nm, 0.0) * GC * S.H * n_seg
        Ned_g = 1.35 * G + 1.5 * r["Q"]
        best = None
        core = kind == "core"
        for mx in [k * 0.10 for k in range(3, 50)]:
            my = mx if core else 0.50
            Lr, Br = (x1 - x0) + 2 * mx, (y1 - y0) + 2 * my
            if not core:                         # parede : alargamento perpendicular à parede
                wall = next(w for w in S.walls if w["id"] == nm)
                if wall["axis"] == "Y":
                    Lr, Br = (x1 - x0) + 2 * mx, (y1 - y0) + 2 * 0.50
                else:
                    Lr, Br = (x1 - x0) + 2 * 0.50, (y1 - y0) + 2 * mx
            hr = 1.00 if core else 0.80
            Wr = Lr * Br * hr * GC
            ok = (Ned_g + 1.35 * Wr) / (Lr * Br) <= srd
            for Mm, Ld_, Lo in ((MX, Lr, Br), (MY, Br, Lr)):
                e = Mm / (Nsis + Wr)
                Beff = Ld_ - 2 * e
                if Beff <= 0.3 * Ld_ or (Nsis + Wr) / (Beff * Lo) > srd:
                    ok = False
            if ok:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                best = {"id": nm, "x0": round(cx - Lr / 2, 2), "y0": round(cy - Br / 2, 2), "x1": round(cx + Lr / 2, 2), "y1": round(cy + Br / 2, 2),
                        "L": round(Lr, 2), "B": round(Br, 2), "h": hr, "sigma_grav": round((Ned_g + 1.35 * Wr) / (Lr * Br), 0), "members": [nm]}
                break
        out.append(best or {"id": nm, "L": None, "members": [nm], "fail": True})
    return out


def merge_foundations(rafts_: list[dict], foots: list[dict]) -> tuple[list[dict], list[dict]]:
    """Ensoleiramentos sobrepostos fundidos ; sapatas isoladas que tocam um ensoleiramento são absorvidas. → (ensoleiramentos, sapatas)."""
    boxes = [dict(r) for r in rafts_ if r.get("L")]
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a["x0"] < b["x1"] and b["x0"] < a["x1"] and a["y0"] < b["y1"] and b["y0"] < a["y1"]:
                    m = {"x0": min(a["x0"], b["x0"]), "y0": min(a["y0"], b["y0"]), "x1": max(a["x1"], b["x1"]), "y1": max(a["y1"], b["y1"]),
                         "h": max(a["h"], b["h"]), "members": a["members"] + b["members"]}
                    boxes = [bx for k, bx in enumerate(boxes) if k not in (i, j)] + [m]
                    changed = True
                    break
            if changed:
                break
    left = []
    for f in foots:
        hit = next((b for b in boxes if f["x0"] < b["x1"] and b["x0"] < f["x1"] and f["y0"] < b["y1"] and b["y0"] < f["y1"]), None)
        if hit:
            hit.update(x0=min(hit["x0"], f["x0"]), y0=min(hit["y0"], f["y0"]), x1=max(hit["x1"], f["x1"]), y1=max(hit["y1"], f["y1"]))
            hit["members"] = hit["members"] + [f["id"]]
        else:
            left.append(f)
    boxes.sort(key=lambda b: (b["x0"], b["y0"]))
    for k, b in enumerate(boxes):
        b["id"] = f"E{k + 1}"
        b["L"], b["B"] = round(b["x1"] - b["x0"], 2), round(b["y1"] - b["y0"], 2)
    return boxes, left
