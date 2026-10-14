"""Estudo estrutural de MORADIA / pequeno edifício (paredes resistentes ou pórtico) — Portugal.

Generaliza o método aplicado à mão nos estudos Courbevoie / La Courneuve com os motores ConstruPilot:
- lajes armadas em 2 direções por painel (structuro_slab2way, Pigeaud + continuidade, L/d EC2 §7.4.2);
- descida de cargas por alinhamento de parede (reações de laje BAEL E3), cobertura, alvenaria;
- verificação simplificada de alvenaria NP EN 1996-3 §4.2.2 (ou parede de betão);
- sapatas contínuas a partir da tensão do estudo geotécnico (sem estudo → tabela de larguras, nada definitivo);
- lintéis por abertura (structuro_ec2.design_section + structuro_calc.beam_response);
- cintas e pilaretes de confinamento (pormenorização construtiva mínima);
- muros de cave (impulso em repouso K0);
- escadas na caixa (stair_engine.cage_solver + laje da escada);
- medições de betão e aço (inclui lajes, cintas, pilaretes, lintéis, sapatas, muros, escadas).

Normas: NP EN 1990 / 1991-1-1 / 1992-1-1 / 1996-3 / 1997-1 com Anexos Nacionais portugueses
(valores marcados "a confirmar pelo projetista"). Ação sísmica NP EN 1998-1 NÃO verificada.
Resultado = PRÉ-DIMENSIONAMENTO, nunca um projeto de execução assinado.
"""
from __future__ import annotations

import copy
import math

from engines import structuro_ec2 as ec2
from engines import structuro_slab2way as s2
from engines.structuro_calc import beam_response

VERSION = "house-1.0.0"
FCK, FYK, ALPHA_CC = 25.0, 500.0, 0.85          # C25/30, A500, αcc AN PT (a confirmar)
CONCRETE = 25.0
KG_M = {6: 0.222, 8: 0.395, 10: 0.617, 12: 0.888, 14: 1.208, 16: 1.578, 20: 2.466}

# Sobrecargas NP EN 1991-1-1 (AN PT, a confirmar) e ψ2
USE_Q = {"habitacao": (2.0, 0.3), "garagem": (2.5, 0.6), "comercio": (4.0, 0.6), "escritorios": (3.0, 0.3),
         "esteira": (0.4, 0.0), "cobertura_plana": (0.4, 0.0), "terraco": (2.0, 0.3)}
USE_LABEL = {"habitacao": "Habitação (cat. A)", "garagem": "Garagem (cat. F)", "comercio": "Comércio (cat. D1)",
             "escritorios": "Escritórios (cat. B)", "esteira": "Esteira sob cobertura (cat. H)",
             "cobertura_plana": "Cobertura plana não acessível (cat. H)", "terraco": "Terraço acessível (cat. A)"}

DEFAULT = {
    "name": "Moradia",
    "outer_L_m": 10.0, "outer_W_m": 8.0,
    "wall_thickness_m": 0.20,                    # parede resistente (estrutural)
    "structure": "alvenaria",                    # alvenaria | betao | portico
    "levels": [{"name": "R/C", "storey_height_m": 2.80, "use": "habitacao"},
               {"name": "1.º piso", "storey_height_m": 2.70, "use": "habitacao"}],
    "basement": {"present": False, "height_m": 2.50},
    "roof": {"type": "inclinada", "ridge_height_m": 3.0},   # inclinada | laje_plana
    "interior_walls_x": [],                      # posições (m, a partir da fachada esquerda) de paredes resistentes paralelas a Y
    "interior_walls_y": [],                      # posições (m, a partir da fachada da frente) de paredes paralelas a X
    "openings": [],                              # {level, facade: frente|tras|esquerda|direita, width_m, label}
    "stair": {"present": False, "cage_length_m": 2.30, "cage_width_m": 1.80},
    "loads": {"g2_floor_kn_m2": 2.0, "roof_g_kn_m2": 1.2, "snow_kn_m2": 0.0, "masonry_kn_m2": 3.4},
    "soil": {"q_els_kpa": None, "q_elu_kpa": None, "phi_deg": 30.0, "gamma_kn_m3": 20.0, "confirmed": False},
}


# ------------------------------------------------------------------ utilidades
def merge(base: dict, patch: dict | None) -> dict:
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        elif v is not None:
            out[k] = v
    return out


def normalize(geo: dict | None) -> dict:
    g = merge(DEFAULT, geo or {})
    g["outer_L_m"] = max(3.0, min(60.0, float(g["outer_L_m"])))
    g["outer_W_m"] = max(3.0, min(40.0, float(g["outer_W_m"])))
    if g["outer_W_m"] > g["outer_L_m"]:
        g["outer_L_m"], g["outer_W_m"] = g["outer_W_m"], g["outer_L_m"]
        g["interior_walls_x"], g["interior_walls_y"] = g.get("interior_walls_y") or [], g.get("interior_walls_x") or []
    t = g["wall_thickness_m"] = max(0.15, min(0.40, float(g["wall_thickness_m"])))
    g["interior_walls_x"] = sorted({round(float(x), 3) for x in g.get("interior_walls_x") or [] if t < float(x) < g["outer_L_m"] - t})
    g["interior_walls_y"] = sorted({round(float(y), 3) for y in g.get("interior_walls_y") or [] if t < float(y) < g["outer_W_m"] - t})
    levels = [lv for lv in g.get("levels") or [] if isinstance(lv, dict)] or copy.deepcopy(DEFAULT["levels"])
    for lv in levels:
        lv["storey_height_m"] = max(2.2, min(6.0, float(lv.get("storey_height_m") or 2.7)))
        lv["use"] = lv.get("use") if lv.get("use") in USE_Q else "habitacao"
        lv["name"] = str(lv.get("name") or "Piso")
    g["levels"] = levels[:6]
    if g["structure"] not in ("alvenaria", "betao", "portico"):
        g["structure"] = "alvenaria"
    if g["roof"].get("type") not in ("inclinada", "laje_plana"):
        g["roof"]["type"] = "inclinada"
    return g


def _bars_for(as_cm2: float, dias=(10, 12, 14, 16, 20), max_n=4, min_n=2) -> tuple[int, int, float]:
    for d in dias:
        n = max(min_n, math.ceil(as_cm2 / (math.pi * d ** 2 / 400)))
        if n <= max_n:
            return n, d, round(n * math.pi * d ** 2 / 400, 2)
    d = dias[-1]
    n = math.ceil(as_cm2 / (math.pi * d ** 2 / 400))
    return n, d, round(n * math.pi * d ** 2 / 400, 2)


def pt_mesh(label: str | None) -> str:
    """'HA10 e=20' → 'Ø10//0,20' ; malhas mantêm a designação."""
    if not label:
        return "—"
    if label.startswith("HA"):
        try:
            dia, s = label[2:].split(" e=")
            return f"Ø{dia}//{float(s) / 100:.2f}".replace(".", ",")
        except ValueError:
            return label.replace("HA", "Ø")
    return label


def fmt_s(s_m: float) -> str:
    """Espaçamento em m no formato português: 0,20 / 0,175 / 0,125."""
    txt = f"{s_m:.3f}"
    if txt.endswith("0"):
        txt = txt[:-1]
    return txt.replace(".", ",")


def pt_bars(as_cm2_m: float, min_dia: int = 8) -> dict:
    """Varões A500 por metro (prática portuguesa): menor peso que cobre As, espaçamento 0,10–0,25 m."""
    best = None
    for dia in (8, 10, 12, 16):
        if dia < min_dia:
            continue
        for s in (0.25, 0.20, 0.175, 0.15, 0.125, 0.10):
            a = math.pi * dia ** 2 / 4 / 100 / s
            if a + 1e-9 >= as_cm2_m:
                kg = KG_M[dia] / s
                if best is None or kg < best["kg_m2"] - 1e-9:
                    best = {"dia": dia, "s": s, "as_cm2_m": round(a, 2), "kg_m2": round(kg, 3),
                            "label": f"Ø{dia}//{fmt_s(s)}"}
                break
    return best or {"dia": 16, "s": 0.10, "as_cm2_m": 20.1, "kg_m2": 15.8, "label": "Ø16//0,10 (rever espessura)"}


def _mesh_kg_m2(m: dict | None) -> float:
    if not m:
        return 0.0
    if "kg_m2" in m:
        return m["kg_m2"]
    return (m.get("as_cm2_m") or 0) * 0.785


# ------------------------------------------------------------------ lajes
def panels(g: dict) -> list[dict]:
    t = g["wall_thickness_m"]
    xs = [t / 2] + g["interior_walls_x"] + [g["outer_L_m"] - t / 2]
    ys = [t / 2] + g["interior_walls_y"] + [g["outer_W_m"] - t / 2]
    out = []
    for i in range(len(xs) - 1):
        for j in range(len(ys) - 1):
            ax, ay = xs[i + 1] - xs[i], ys[j + 1] - ys[j]
            edges_x = {"x0": "continu" if i > 0 else "rive", "x1": "continu" if i < len(xs) - 2 else "rive"}
            edges_y = {"y0": "continu" if j > 0 else "rive", "y1": "continu" if j < len(ys) - 2 else "rive"}
            out.append({"id": f"{chr(65 + j)}{i + 1}", "x0": xs[i], "x1": xs[i + 1], "y0": ys[j], "y1": ys[j + 1],
                        "span_x": round(ax, 3), "span_y": round(ay, 3), "edges_xy": {**edges_x, **edges_y}})
    return out


def design_panel(p: dict, use: str, g2: float) -> dict:
    q, psi2 = USE_Q[use]
    # slab2way exige lx = vão menor; mapear os bordos
    if p["span_x"] <= p["span_y"]:
        lx, ly = p["span_x"], p["span_y"]
        edges = {"x0": p["edges_xy"]["x0"], "x1": p["edges_xy"]["x1"], "y0": p["edges_xy"]["y0"], "y1": p["edges_xy"]["y1"]}
        short_dir = "X"
    else:
        lx, ly = p["span_y"], p["span_x"]
        edges = {"x0": p["edges_xy"]["y0"], "x1": p["edges_xy"]["y1"], "y0": p["edges_xy"]["x0"], "y1": p["edges_xy"]["x1"]}
        short_dir = "Y"
    res = None
    for h in (0.18, 0.20, 0.22, 0.24, 0.25, 0.28, 0.30):
        res = s2.design(lx, ly, h, g2, q, edges, fck=FCK, fyk=FYK, cover_m=0.025, psi2=psi2)
        if res["deflection_ld"]["ok"] and res["shear"]["ok"]:
            break
    rho = res["rho"]
    pu, ps = res["loads"]["pu"], res["loads"]["ps"]
    g_tot = res["loads"]["g_kn_m2"]
    k_long = 1 / (1 + rho / 2) / 2 if not res["one_way"] else 0.5
    k_short = 1 / 3 if not res["one_way"] else 0.0
    # reações por bordo (kN/m): bordos paralelos ao vão maior recebem k_long
    reac = {}
    for side in ("x0", "x1", "y0", "y1"):
        # bordos x0/x1 (perpendiculares a lx) são os bordos CURTOS → k_short ; y0/y1 → k_long
        k = k_short if side.startswith("x") else k_long
        reac[side] = {"g": round(g_tot * lx * k, 2), "q": round(q * lx * k, 2)}
    # voltar ao referencial do edifício
    if short_dir == "X":
        r_xy = {"left": reac["x0"], "right": reac["x1"], "front": reac["y0"], "back": reac["y1"]}
    else:
        r_xy = {"front": reac["x0"], "back": reac["x1"], "left": reac["y0"], "right": reac["y1"]}
    span_short, span_long = res["span"]["x"], res["span"]["y"]
    return {
        "id": p["id"], "use": use, "q": q, "g2": g2, "h": res["inputs"]["h"], "lx": lx, "ly": ly,
        "short_dir": short_dir, "rho": rho, "one_way": res["one_way"], "pu": pu, "ps": ps,
        "as_short": span_short["as_req_cm2_m"], "mesh_short": pt_bars(span_short["as_req_cm2_m"]),
        "as_long": span_long["as_req_cm2_m"], "mesh_long": pt_bars(span_long["as_req_cm2_m"]),
        "supports": {k: {"type": v["type"], "as": v["as_req_cm2_m"],
                         "mesh": pt_bars(v["as_req_cm2_m"]) if v["type"] != "libre" else None, "len": v.get("length_from_face_m")}
                     for k, v in res["supports"].items()},
        "ld": res["deflection_ld"], "shear": res["shear"], "warnings": res["warnings"],
        "reactions": r_xy, "geom": p,
    }


def slab_levels(g: dict) -> list[dict]:
    """Lista das lajes a calcular, de baixo para cima."""
    out = []
    lvls = g["levels"]
    if g["basement"]["present"]:
        out.append({"name": f"Laje do teto da cave (piso {lvls[0]['name']})", "use": lvls[0]["use"], "below": "Cave",
                    "elev_index": -1})
    for i, lv in enumerate(lvls):
        top = i == len(lvls) - 1
        if top:
            use = "esteira" if g["roof"]["type"] == "inclinada" else "cobertura_plana"
            name = "Laje de esteira (teto do último piso)" if use == "esteira" else "Laje de cobertura"
        else:
            use = lvls[i + 1]["use"]
            name = f"Laje do piso {lvls[i + 1]['name']}"
        out.append({"name": name, "use": use, "below": lv["name"], "elev_index": i})
    return out


# ------------------------------------------------------------------ alvenaria NP EN 1996-3
def masonry_capacity(t: float, h_storey: float, fb: float, fm: float = 10.0, K: float = 0.45, gamma_m: float = 2.5) -> dict:
    fk = K * fb ** 0.7 * fm ** 0.3
    fd = fk / gamma_m
    hef = 0.75 * h_storey
    phi = max(0.0, 0.85 - 0.0011 * (hef / t) ** 2)
    return {"fb": fb, "fk": round(fk, 3), "fd": round(fd, 3), "hef": round(hef, 2), "phi": round(phi, 3),
            "nrd_kn_m": round(phi * fd * t * 1000, 1)}


# ------------------------------------------------------------------ lintéis
def design_lintel(rep: str, clear: float, g_line: float, q_line: float, s_line: float, b: float) -> dict:
    L = clear + 0.20
    last = None
    for h in (0.20, 0.25, 0.30, 0.40, 0.50, 0.60):
        g = g_line + b * h * CONCRETE
        p = 1.35 * g + 1.5 * q_line + 0.75 * s_line
        m, v = p * L ** 2 / 8, p * L / 2
        d = h - 0.03 - 0.006 - 0.006
        des = ec2.design_section(m, v, b_m=b, h_m=h, d_m=d, fck=FCK, fyk=FYK, alpha_cc=ALPHA_CC)
        last = (h, g, m, v, des)
        if des["flexure"]["mode"] != "simple" or des["flexure"]["mu"] > 0.30 or des["shear"]["vrdmax_kn"] < v:
            continue
        n, dia, as_prov = _bars_for(des["flexure"]["as_req_cm2"], max_n=3)
        if n > 3:
            continue
        asw = des["shear"]["asw_s_req_cm2_m"]
        smax = des["shear"]["s_max_m"] * 100
        s_ = min(2 * 0.283 / asw * 100 if asw else smax, smax, 20)
        s_ = max(math.floor(s_ / 2.5) * 2.5, 7.5)
        ei = 22000 * 3.3 ** 0.3 * 1e3 * b * h ** 3 / 12
        w = beam_response(L, g + 0.3 * q_line, [], ei)["deflection_sampled_mm"]
        return {"rep": rep, "clear": round(clear, 2), "L": round(L, 2), "b": b, "h": h,
                "g": round(g, 1), "q": round(q_line, 1), "s": round(s_line, 1), "m": round(m, 2), "v": round(v, 2),
                "as_req": des["flexure"]["as_req_cm2"], "bot": f"{n}Ø{dia}", "bot_n": n, "bot_d": dia, "as_prov": as_prov,
                "top": "2Ø10", "stirrups": f"Ø6//{fmt_s(s_ / 100)}", "st_s": s_,
                "w_el_mm": round(w, 2), "w_lim_mm": round(L * 1000 / 500, 1), "bearing_m": 0.25, "ok": True}
    h, g, m, v, des = last
    return {"rep": rep, "clear": round(clear, 2), "L": round(L, 2), "b": b, "h": h, "m": round(m, 2), "v": round(v, 2),
            "ok": False, "note": "Vão/carga fora do âmbito de um lintel corrente — viga a dimensionar em detalhe."}


# ------------------------------------------------------------------ escadas
def design_stairs(g: dict, slab_h: float) -> list[dict]:
    st = g.get("stair") or {}
    if not st.get("present"):
        return []
    from stair_engine.cage_solver import CageStairInput, solve_cage
    out = []
    heights = [lv["storey_height_m"] for lv in g["levels"][:-1]]
    if g["basement"]["present"]:
        heights = [g["basement"]["height_m"]] + heights
    for k, fh in enumerate(heights):
        try:
            r = solve_cage(CageStairInput(floor_height_mm=fh * 1000 + slab_h * 1000, cage_length_mm=st["cage_length_m"] * 1000,
                                          cage_width_mm=st["cage_width_m"] * 1000, slab_thickness_mm=slab_h * 1000,
                                          flight_thickness_mm=150))
        except Exception as e:  # noqa: BLE001
            out.append({"lanco": k + 1, "error": str(e)[:200]})
            continue
        t = 0.15
        hh, gg = r.riser_mm / 1000, r.giron_mm / 1000
        cos_a = math.cos(math.radians(r.slope_deg))
        span = st["cage_length_m"] + 0.10
        G = t / cos_a * CONCRETE + hh / 2 * CONCRETE + 1.0
        Q = 3.0                                  # escadas habitação (AN PT, a confirmar)
        pu = 1.35 * G + 1.5 * Q
        m, v = pu * span ** 2 / 8, pu * span / 2
        d = t - 0.020 - 0.005
        des = ec2.design_section(m, v, b_m=1.0, h_m=t, d_m=d, fck=FCK, fyk=FYK, alpha_cc=ALPHA_CC)
        as_req = des["flexure"]["as_req_cm2"]
        main = None
        for dia, sp in ((8, 20), (10, 20), (10, 15), (12, 20), (12, 15), (12, 12.5)):
            a = math.pi * dia ** 2 / 4 / 100 * 100 / sp
            if a >= as_req:
                ld = s2.ld_check(span, d, as_req, a, FCK, 1.0)
                if ld["ok"]:
                    main = {"dia": dia, "s": sp, "as": round(a, 2), "label": f"Ø{dia}//{fmt_s(sp / 100)}"}
                    break
        reds = [a.code for a in r.alerts if a.level == "red"]
        out.append({"lanco": k + 1, "floor_height_m": round(fh + slab_h, 2), "risers": r.num_risers,
                    "riser_mm": round(r.riser_mm, 1), "giron_mm": round(r.giron_mm, 1), "blondel_mm": round(r.blondel_mm, 1),
                    "slope_deg": round(r.slope_deg, 1), "mode": r.mode, "buildable": r.is_buildable, "red_alerts": reds,
                    "span_m": round(span, 2), "t_m": t, "pu": round(pu, 2), "m_elu": round(m, 2), "as_req": as_req,
                    "main": main or {"label": "a rever (espessura)", "dia": 12, "s": 12.5},
                    "dist": "Ø8//0,25", "chapeaux": "Ø8//0,20",
                    "width_m": st["cage_width_m"] / 2})
    return out


# ------------------------------------------------------------------ cálculo completo
def compute(geo: dict | None) -> dict:
    g = normalize(geo)
    L, W, t = g["outer_L_m"], g["outer_W_m"], g["wall_thickness_m"]
    ld_ = g["loads"]
    w_mas = ld_["masonry_kn_m2"] if g["structure"] == "alvenaria" else t * CONCRETE + 0.6
    warnings: list[str] = []

    # 1) Lajes
    pnls = panels(g)
    slabs = []
    for sl in slab_levels(g):
        g2 = ld_["g2_floor_kn_m2"] if sl["use"] not in ("esteira", "cobertura_plana") else (0.8 if sl["use"] == "esteira" else 2.5)
        designs = [design_panel(p, sl["use"], g2) for p in pnls]
        h = max(d["h"] for d in designs)
        for d in designs:
            warnings += [f"{sl['name']} — painel {d['id']}: {w}" for w in d["warnings"]]
        slabs.append({**sl, "g2": g2, "h": h, "panels": designs})

    # 2) Descida de cargas por alinhamento (por metro), do topo para a base
    lines = {"frente": {"kind": "fachada", "axis": "X", "pos": 0.0}, "tras": {"kind": "fachada", "axis": "X", "pos": W},
             "esquerda": {"kind": "empena", "axis": "Y", "pos": 0.0}, "direita": {"kind": "empena", "axis": "Y", "pos": L}}
    for k, x in enumerate(g["interior_walls_x"]):
        lines[f"PX{k + 1}"] = {"kind": "interior", "axis": "Y", "pos": x}
    for k, y in enumerate(g["interior_walls_y"]):
        lines[f"PY{k + 1}"] = {"kind": "interior", "axis": "X", "pos": y}

    def slab_reaction_on(line_key: str, sl: dict) -> tuple[float, float]:
        """Reação (g, q) por metro da laje sl no alinhamento: média ponderada dos painéis adjacentes."""
        ln = lines[line_key]
        gs, qs = [], []
        for d in sl["panels"]:
            p = d["geom"]
            if ln["axis"] == "Y":
                if abs(p["x0"] - (ln["pos"] if ln["kind"] == "interior" else (t / 2 if ln["pos"] == 0 else L - t / 2))) < 1e-6:
                    gs.append(d["reactions"]["left"]["g"]); qs.append(d["reactions"]["left"]["q"])
                if abs(p["x1"] - (ln["pos"] if ln["kind"] == "interior" else (t / 2 if ln["pos"] == 0 else L - t / 2))) < 1e-6:
                    gs.append(d["reactions"]["right"]["g"]); qs.append(d["reactions"]["right"]["q"])
            else:
                if abs(p["y0"] - (ln["pos"] if ln["kind"] == "interior" else (t / 2 if ln["pos"] == 0 else W - t / 2))) < 1e-6:
                    gs.append(d["reactions"]["front"]["g"]); qs.append(d["reactions"]["front"]["q"])
                if abs(p["y1"] - (ln["pos"] if ln["kind"] == "interior" else (t / 2 if ln["pos"] == 0 else W - t / 2))) < 1e-6:
                    gs.append(d["reactions"]["back"]["g"]); qs.append(d["reactions"]["back"]["q"])
        # dois lados (interior) somam; média por painel ao longo do alinhamento
        if not gs:
            return 0.0, 0.0
        n_side = 2 if ln["kind"] == "interior" else 1
        n_pan = max(1, len(gs) // n_side)
        return round(sum(gs) / n_pan, 2), round(sum(qs) / n_pan, 2)

    roof = g["roof"]
    roof_g = ld_["roof_g_kn_m2"] * W / 2 if roof["type"] == "inclinada" else 0.0
    roof_s = ld_["snow_kn_m2"] * W / 2 if roof["type"] == "inclinada" else 0.0
    gable_h = (roof.get("ridge_height_m") or 0.0) / 2 if roof["type"] == "inclinada" else 0.0

    descent = {}
    n_lv = len(g["levels"])
    for key, ln in lines.items():
        rows = []
        G = Q = S = 0.0
        # cobertura inclinada: asnas apoiadas nas fachadas frente/trás; empenas recebem triângulo de alvenaria
        if roof["type"] == "inclinada":
            if key in ("frente", "tras"):
                G += roof_g; S += roof_s
            if key in ("esquerda", "direita"):
                G += w_mas * gable_h
        for i in range(n_lv - 1, -1, -1):
            lv = g["levels"][i]
            # laje no topo deste piso
            sl = next(s for s in slabs if s["elev_index"] == i)
            sg, sq = slab_reaction_on(key, sl)
            G += sg + (0.20 * 0.20 * CONCRETE if g["structure"] == "alvenaria" else 0.0)   # cinta
            Q += sq
            top = {"g": round(G, 1), "q": round(Q, 1), "s": round(S, 1)}
            G += w_mas * lv["storey_height_m"]
            rows.append({"level": lv["name"], "top_of_wall": top, "base": {"g": round(G, 1), "q": round(Q, 1), "s": round(S, 1)},
                         "n_els": round(G + Q + 0.5 * S, 1), "n_elu": round(1.35 * G + 1.5 * Q + 0.75 * S, 1),
                         "storey_height_m": lv["storey_height_m"]})
        if g["basement"]["present"]:
            sl = next(s for s in slabs if s["elev_index"] == -1)
            sg, sq = slab_reaction_on(key, sl)
            G += sg + 0.20 * (g["basement"]["height_m"] + 0.25) * CONCRETE
            Q += sq
            rows.append({"level": "Cave", "base": {"g": round(G, 1), "q": round(Q, 1), "s": round(S, 1)},
                         "n_els": round(G + Q + 0.5 * S, 1), "n_elu": round(1.35 * G + 1.5 * Q + 0.75 * S, 1),
                         "storey_height_m": g["basement"]["height_m"]})
        found = {"g": round(G, 1), "q": round(Q, 1), "s": round(S, 1), "n_els": round(G + Q + 0.5 * S, 1),
                 "n_elu": round(1.35 * G + 1.5 * Q + 0.75 * S, 1)}
        length = W if ln["axis"] == "Y" else L
        descent[key] = {**ln, "length_m": round(length, 2), "levels": rows, "foundation": found}

    # 3) Alvenaria resistente
    walls_check = {}
    if g["structure"] == "alvenaria":
        for key, d in descent.items():
            lv0 = next((r for r in d["levels"] if r["level"] == g["levels"][0]["name"]), d["levels"][-1])
            n_elu = lv0["n_elu"]
            choice = None
            caps = {}
            for cls, fb in (("fb 4", 4.0), ("fb 6", 6.0), ("fb 8", 8.0), ("fb 10", 10.0)):
                caps[cls] = masonry_capacity(t, lv0["storey_height_m"], fb)
                if choice is None and caps[cls]["nrd_kn_m"] >= n_elu:
                    choice = cls
            walls_check[key] = {"n_elu_kn_m": n_elu, "capacities": caps,
                                "choice": choice or "parede de betão armado (alvenaria insuficiente)"}
            if not choice:
                warnings.append(f"Alinhamento {key}: alvenaria insuficiente ({n_elu} kN/m) — prever parede de betão armado.")

    # 4) Fundações (sapatas contínuas)
    soil = g["soil"]
    q_els = soil.get("q_els_kpa")
    q_elu = soil.get("q_elu_kpa") or (q_els * 1.5 if q_els else None)
    footings = {}
    table = []
    for q in (150, 200, 250, 300):
        row = {"q_els": q}
        for key, d in descent.items():
            f = d["foundation"]
            row[key] = math.ceil(max(f["n_els"] / q, f["n_elu"] / (1.5 * q), 0.40) * 20) / 20
        table.append(row)
    if q_els and soil.get("confirmed"):
        for key, d in descent.items():
            f = d["foundation"]
            b = math.ceil(max(f["n_els"] / q_els, f["n_elu"] / q_elu, t + 0.20, 0.40) * 20) / 20
            h = max(0.30, math.ceil(((b - t) / 4 + 0.05) * 20) / 20)
            dd = h - 0.05 - 0.006
            fyd = FYK / 1.15
            as_t = f["n_elu"] * (b - t) / (8 * dd * fyd * 1000) * 1e4 if b > t else 0.0   # cm²/m (bielas)
            as_t = max(as_t, 2.0)
            spacing = 0.20
            dia = 10 if as_t <= 3.93 else 12 if as_t <= 5.65 else 16
            footings[key] = {"b_m": b, "h_m": h, "as_transv_cm2_m": round(as_t, 2),
                             "transv": f"Ø{dia}//{fmt_s(spacing)}", "transv_dia": dia, "long": "4Ø10",
                             "sigma_els_kpa": round(f["n_els"] / b, 1), "q_els_kpa": q_els,
                             "length_m": d["length_m"], "n_els": f["n_els"], "n_elu": f["n_elu"]}
    else:
        warnings.insert(0, "Sem estudo geotécnico com tensão admissível confirmada: sapatas NÃO dimensionadas "
                           "(apresenta-se apenas a tabela de larguras necessárias em função de q_ELS).")

    # 5) Lintéis
    lintels = []
    facade_key = {"frente": "frente", "tras": "tras", "esquerda": "esquerda", "direita": "direita"}
    names = [lv["name"] for lv in g["levels"]]
    for k, op in enumerate(g.get("openings") or []):
        try:
            clear = float(op.get("width_m") or 0)
        except (TypeError, ValueError):
            continue
        if clear <= 0.3:
            continue
        key = facade_key.get(op.get("facade"), "frente")
        lvl = op.get("level") if op.get("level") in names else names[0]
        row = next((r for r in descent[key]["levels"] if r["level"] == lvl), None)
        if not row:
            continue
        tw = row["top_of_wall"]
        # carga sobre o lintel = tudo o que chega ao topo da parede deste piso + alvenaria acima da abertura (≈0,6 m)
        g_line = tw["g"] + w_mas * 0.6
        lin = design_lintel(f"L{k + 1:02d}", clear, g_line, tw["q"], tw["s"], t)
        lin.update({"level": lvl, "facade": key, "label": op.get("label") or "abertura"})
        lintels.append(lin)
        if not lin["ok"]:
            warnings.append(f"Lintel {lin['rep']} ({lvl}, {key}, vão {clear} m): {lin['note']}")

    # 6) Muros de cave
    retaining = None
    if g["basement"]["present"]:
        phi = float(soil.get("phi_deg") or 30.0)
        gam = float(soil.get("gamma_kn_m3") or 20.0)
        k0 = 1 - math.sin(math.radians(phi))
        Hs = g["basement"]["height_m"] + 0.25
        n = 200
        pts = [(k0 * (10.0 + gam * (i + 0.5) * Hs / n) * Hs / n, (i + 0.5) * Hs / n) for i in range(n)]
        r_ = beam_response(Hs, 0.0, pts)
        m_e, v_e = 1.35 * r_["moment_max_knm"], 1.35 * r_["shear_max_kn"]
        dv = ec2.design_section(m_e, v_e, b_m=1.0, h_m=0.20, d_m=0.20 - 0.035 - 0.005, fck=FCK, fyk=FYK, alpha_cc=ALPHA_CC)
        a = dv["flexure"]["as_req_cm2"]
        lab = next((f"Ø{d}//{fmt_s(s / 100)}" for d, s in ((10, 20), (10, 15), (12, 20), (12, 15), (12, 10))
                    if math.pi * d ** 2 / 4 / 100 * 100 / s >= a), "a rever")
        retaining = {"H_m": round(Hs, 2), "k0": round(k0, 3), "phi": phi, "gamma": gam, "surcharge": 10.0,
                     "m_elu": round(m_e, 2), "v_elu": round(v_e, 2), "as_req": a, "vrdc": dv["shear"]["vrdc_kn"],
                     "face_terra": lab, "face_interior": "Ø8//0,20", "horizontais": "Ø8//0,20 (2 faces)", "t_m": 0.20}

    # 7) Escadas
    slab_h_max = max((s["h"] for s in slabs), default=0.20)
    stairs = design_stairs(g, slab_h_max)
    for s in stairs:
        if s.get("red_alerts"):
            warnings.append(f"Escada lanço {s['lanco']}: alertas {', '.join(s['red_alerts'])} — rever a caixa.")

    # 8) Cintas e pilaretes (confinamento; pormenorização mínima)
    perim = 2 * (L + W) + sum(W for _ in g["interior_walls_x"]) + sum(L for _ in g["interior_walls_y"])
    n_inter = 4 + 2 * len(g["interior_walls_x"]) + 2 * len(g["interior_walls_y"]) + len(g["interior_walls_x"]) * len(g["interior_walls_y"])
    ties = {"cinta": "0,20×0,20 — 4Ø10 + estribos Ø6//0,20", "pilarete": "0,20×0,20 — 4Ø12 + estribos Ø6//0,15",
            "cinta_ml_per_level": round(perim, 1), "pilaretes_count": n_inter,
            "note": "Alvenaria confinada: cinta em todos os pisos e pilaretes nos cantos, cruzamentos e de cada lado das aberturas > 1,5 m."} \
        if g["structure"] == "alvenaria" else None

    # 9) Medições
    q = quantities(g, slabs, descent, footings, lintels, retaining, stairs, ties, table)

    warnings.append("Ação sísmica (NP EN 1998-1) NÃO verificada — obrigatória em Portugal; verificação pelo projetista.")
    warnings.append("Pré-dimensionamento automático — a verificar e assinar por engenheiro civil antes da execução.")
    return {"version": VERSION, "geometry": g, "slabs": slabs, "descent": descent, "walls_check": walls_check,
            "footings": footings, "footing_table": table, "soil": soil, "lintels": lintels, "retaining": retaining,
            "stairs": stairs, "ties": ties, "quantities": q, "warnings": warnings,
            "materials": {"concrete": "C25/30 (XC1 interior; XC2 fundações)", "steel": "A500 NR",
                          "cover": "lajes 25 mm, vigas/lintéis 30 mm, fundações 50 mm", "alpha_cc": ALPHA_CC}}


def quantities(g, slabs, descent, footings, lintels, retaining, stairs, ties, table) -> dict:
    L, W, t = g["outer_L_m"], g["outer_W_m"], g["wall_thickness_m"]
    rows = []
    conc = steel = 0.0
    # lajes
    for s in slabs:
        area = sum(d["lx"] * d["ly"] for d in s["panels"])
        v = sum(d["lx"] * d["ly"] * d["h"] for d in s["panels"])
        kg = 0.0
        for d in s["panels"]:
            a = d["lx"] * d["ly"]
            kg += a * (_mesh_kg_m2(d["mesh_short"]) + _mesh_kg_m2(d["mesh_long"]))
            for side, sp in d["supports"].items():
                if sp["type"] == "continu" and sp["mesh"]:
                    edge_len = d["ly"] if side.startswith("x") else d["lx"]
                    kg += edge_len * (sp["len"] or 0.5) * _mesh_kg_m2(sp["mesh"])
                elif sp["type"] == "rive" and sp["mesh"]:
                    edge_len = d["ly"] if side.startswith("x") else d["lx"]
                    kg += edge_len * 0.6 * _mesh_kg_m2(sp["mesh"])
        kg *= 1.10                                   # sobreposições
        rows.append({"element": s["name"], "concrete_m3": round(v, 2), "steel_kg": round(kg, 0), "area_m2": round(area, 1)})
        conc += v; steel += kg
    # cintas e pilaretes
    if ties:
        n_lv = len(g["levels"])
        v = ties["cinta_ml_per_level"] * 0.04 * n_lv
        kg = ties["cinta_ml_per_level"] * n_lv * (4 * KG_M[10] * 1.1 + (0.72 / 0.20) * KG_M[6])
        rows.append({"element": "Cintas (todos os pisos)", "concrete_m3": round(v, 2), "steel_kg": round(kg, 0)})
        conc += v; steel += kg
        hh = sum(lv["storey_height_m"] for lv in g["levels"])
        v = ties["pilaretes_count"] * 0.04 * hh
        kg = ties["pilaretes_count"] * hh * (4 * KG_M[12] * 1.15 + (0.72 / 0.15) * KG_M[6])
        rows.append({"element": "Pilaretes de confinamento", "concrete_m3": round(v, 2), "steel_kg": round(kg, 0)})
        conc += v; steel += kg
    # lintéis
    v = kg = 0.0
    for li in lintels:
        if not li.get("ok"):
            continue
        Ld = li["L"] + 2 * 0.25
        v += li["b"] * li["h"] * Ld
        kg += Ld * (li["bot_n"] * KG_M[li["bot_d"]] + 2 * KG_M[10]) * 1.1
        kg += (Ld / (li["st_s"] / 100) + 1) * (2 * (li["b"] + li["h"]) - 0.08) * KG_M[6]
    if lintels:
        rows.append({"element": f"Lintéis ({len(lintels)})", "concrete_m3": round(v, 2), "steel_kg": round(kg, 0)})
        conc += v; steel += kg
    # fundações
    if footings:
        v = sum(f["b_m"] * f["h_m"] * f["length_m"] for f in footings.values())
        kg = 0.0
        for f in footings.values():
            dia = f.get("transv_dia", 10)
            kg += (f["length_m"] / 0.20 + 1) * (f["b_m"] - 0.10) * KG_M.get(dia, KG_M[10])
            kg += 4 * f["length_m"] * KG_M[10] * 1.1
        rows.append({"element": "Sapatas contínuas", "concrete_m3": round(v, 2), "steel_kg": round(kg, 0)})
        conc += v; steel += kg
    else:
        rows.append({"element": "Sapatas contínuas", "concrete_m3": None, "steel_kg": None,
                     "note": "não dimensionadas (sem estudo geotécnico)"})
    # muros de cave
    if retaining:
        per = 2 * (L + W)
        v = per * retaining["t_m"] * retaining["H_m"]
        kg = per * retaining["H_m"] * 0.20 * 2 / 0.20 * KG_M[10] * 4
        rows.append({"element": "Muros de cave", "concrete_m3": round(v, 2), "steel_kg": round(kg, 0)})
        conc += v; steel += kg
    # escadas
    if stairs:
        v = kg = 0.0
        for s in stairs:
            if s.get("error"):
                continue
            Ls = s["span_m"] / math.cos(math.radians(s["slope_deg"])) + 0.5
            wdt = g["stair"]["cage_width_m"]
            v += Ls * wdt * (s["t_m"] + s["riser_mm"] / 2000)
            n_main = math.ceil(wdt / (s["main"]["s"] / 100)) + 1
            kg += n_main * Ls * KG_M.get(s["main"]["dia"], KG_M[12]) + (Ls / 0.25 + 1) * wdt * KG_M[8] * 1.5
        rows.append({"element": "Escadas", "concrete_m3": round(v, 2), "steel_kg": round(kg, 0)})
        conc += v; steel += kg
    return {"rows": rows, "concrete_m3": round(conc, 2), "steel_kg": round(steel, 0),
            "ratio_kg_m3": round(steel / conc, 1) if conc else 0,
            "note": "Medição de pré-dimensionamento (comprimentos ao eixo, +10 % sobreposições). Exclui cofragem, desperdícios e armaduras construtivas de pormenor."}
