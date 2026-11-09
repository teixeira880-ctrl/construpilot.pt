"""Calcul complet d'un bâtiment bois massif sur trame (CLT + lamellé-collé), déterministe.

Système « poteaux-poutres » (par défaut, type Structurlam / Borregas) : poteaux GL à chaque nœud de trame, poutres GL sur
les files perpendiculaires à la portée des panneaux, pannes intermédiaires + sommiers si la portée CLT l'exige, planchers CLT
continus sur au moins deux appuis. Système « murs CLT » (maison, petit collectif) : les files d'appui deviennent des murs CLT
porteurs, plus les murs de façade.

Chaîne : charges (pays) → choix du schéma porteur (orientation + nombre de pannes, coût mini parmi les variantes qui
vérifient) → CLT par plancher → poutres / pannes / sommiers → descente de charges et poteaux (ou murs) étage par étage →
assemblages (étriers, pieds de poteaux, éclissages CLT, fixations CLT/poutre) → stabilité (vent, séisme, diaphragme) →
gros œuvre (semelles BA, dallage, soubassement) → quantités. Aucune valeur n'est produite par une IA.
"""
from __future__ import annotations

import math

from engines.bet_frame.model import BLOCK, WARN, Frame, use_key

from . import norms, timber
from .lang import num, t
from .mat import CLT, GL_COLS, LAYUPS, PANEL_MAX_L, PANEL_MAX_W, WALL_LAYUPS, beam_sizes, layup

SIZES = beam_sizes()


def system(m: Frame) -> str:
    s = str((m.st.get("system") or "")).lower()
    if s in ("walls", "clt_walls", "murs"):
        return "walls"
    if s in ("post_beam", "poteaux_poutres", "frame"):
        return "post_beam"
    return "walls" if str(m.raw.get("building_type", "")).lower() in ("maison", "moradia", "house") else "post_beam"


def _loads_for(m: Frame, use: str, roof: bool, snow: dict) -> dict:
    ld = m.raw.get("loads") or {}
    c = m.country if m.country in norms.Q_USE else "FR"
    if roof:
        g = float(ld.get("roof_finishes", 1.5))
        qh = norms.q_use(c, "toiture" if use == "toiture" else use)
        if use == "toiture":
            q, dur, psi = max(qh, snow["s"]), "short", norms.PSI["snow"] if snow["s"] >= qh else norms.PSI["toiture"]
        else:
            q, dur, psi = qh, "medium", norms.PSI.get(use, norms.PSI["habitation"])
            if snow["s"] > 0:
                q, dur = max(qh, snow["s"]), "short" if snow["s"] > qh else "medium"
        return {"g": g, "q": q, "dur": dur, "psi1": psi[1], "psi2": psi[2], "use": use, "fin": g, "part": 0.0}
    fin = float(ld.get("finishes", 2.0))                     # chape + résilient + plafond (exigences acoustiques)
    part = 0.0 if use in ("stationnement", "technique") else float(ld.get("partitions", 0.8))
    q = norms.q_use(c, use)
    psi = norms.PSI.get(use, norms.PSI["habitation"])
    return {"g": fin + part, "q": q, "dur": "medium", "psi1": psi[1], "psi2": psi[2], "use": use, "fin": fin, "part": part}


# ============================================================ schéma porteur
def _bays(m: Frame, o: str) -> list[float]:
    g = m.gx if o == "x" else m.gy
    return [round(g[k + 1] - g[k], 4) for k in range(len(g) - 1)]


def _scheme_cost(m: Frame, o: str, n: int, ld: dict, R: int, defl, prices) -> dict | None:
    """Coût (€/m² de plancher) d'un schéma : CLT d'épaisseur requise + poutres (+ pannes et sommiers)."""
    span_b = max(_bays(m, o))
    perp = max(_bays(m, "y" if o == "x" else "x"))
    s = span_b / n
    if s > PANEL_MAX_L:
        return None
    c = timber.design_clt(s, ld["g"], ld["q"], ld["psi1"], ld["psi2"], R, q_dur=ld["dur"], defl=defl, a_vib=_avib(m, ld))
    if not c["ok"]:
        return None
    G, q = c["G"], ld["q"]
    k = 1.25
    bm = timber.design_gl_beam(perp, G * s * k, q * s * k, [], [], SIZES, psi1=ld["psi1"], psi2=ld["psi2"], q_dur=ld["dur"], R=R, defl=defl)
    vol = c["h"] / 1000 * span_b * perp + bm["b"] * bm["h"] / 1e6 * perp * n
    if n > 1:
        Pg = [(s * k_, 2 * bm["R_g"][0]) for k_ in range(1, n)]
        Pq = [(s * k_, 2 * bm["R_q"][0]) for k_ in range(1, n)]
        gd = timber.design_gl_beam(span_b, 0.0, 0.0, Pg, Pq, SIZES, psi1=ld["psi1"], psi2=ld["psi2"], q_dur=ld["dur"], R=R, defl=defl)
        vol += gd["b"] * gd["h"] / 1e6 * span_b
        if not gd["ok"]:
            return None
    if not bm["ok"]:
        return None
    vol_gl = vol - c["h"] / 1000 * span_b * perp
    n_hang = 2 * n + (2 if n > 1 else 0)                    # étriers par travée : porteuses + pannes (+ sommier)
    cost = (c["h"] / 1000 * span_b * perp * (prices["clt_m3"] + prices["clt_pose_m2"] * 1000 / c["h"])
            + vol_gl * (prices["gl_m3"] + prices["gl_pose_m3"]) + n_hang * (prices["hanger"] + 16 * prices["screw"])) / (span_b * perp)
    return {"o": o, "n": n, "s": s, "clt": c["name"], "h": c["h"], "beam": f"{bm['b']}×{bm['h']}", "cost_m2": round(cost, 1),
            "vol_m3_m2": round(vol / (span_b * perp), 4)}


def _avib(m: Frame, ld: dict) -> float | None:
    """Critère de vibration (§7.3.3) pour les planchers occupés ; pas pour la toiture ni le stationnement."""
    if ld["use"] in ("toiture", "stationnement", "technique"):
        return None
    return float((m.raw.get("criteria") or {}).get("a_vib", 1.5))


def choose_scheme(m: Frame, ld: dict, R: int, defl, prices, decisions: list) -> dict:
    forced = m.st.get("clt_span_dir")
    cands = []
    for o in (("x", "y") if forced not in ("x", "y") else (forced,)):
        for n in (1, 2, 3, 4):
            r = _scheme_cost(m, o, n, ld, R, defl, prices)
            if r:
                cands.append(r)
    if not cands:
        o = "y" if max(_bays(m, "y")) <= max(_bays(m, "x")) else "x"
        n = max(1, math.ceil(max(_bays(m, o)) / 6.0))
        return {"o": o, "n": n, "s": max(_bays(m, o)) / n, "cands": [], "forced": True}
    best = min(cands, key=lambda r: r["cost_m2"])
    decisions.append(t(
        f"Schéma porteur retenu : CLT {best['clt']} portant selon {best['o'].upper()} sur {num(best['s'])} m"
        + (f" ({best['n'] - 1} panne(s) intermédiaire(s) par travée)" if best["n"] > 1 else "") + f", le moins coûteux des {len(cands)} schémas qui vérifient.",
        f"Esquema estrutural adotado: CLT {best['clt']} a vencer segundo {best['o'].upper()} {num(best['s'])} m"
        + (f" ({best['n'] - 1} madre(s) intermédia(s) por vão)" if best["n"] > 1 else "") + f", o mais económico dos {len(cands)} esquemas que verificam.",
        f"Structural scheme: CLT {best['clt']} spanning {best['o'].upper()} over {num(best['s'])} m"
        + (f" ({best['n'] - 1} intermediate purlin(s) per bay)" if best["n"] > 1 else "") + f", the cheapest of {len(cands)} compliant schemes.",
        f"Прийнята схема: CLT {best['clt']} з прольотом за {best['o'].upper()} {num(best['s'])} м"
        + (f" ({best['n'] - 1} проміжних прогонів у прольоті)" if best["n"] > 1 else "") + f", найдешевша з {len(cands)} схем, що задовольняють перевірки."))
    return dict(best, cands=sorted(cands, key=lambda r: r["cost_m2"]))


# ============================================================ planchers
def _cells(m: Frame, sid: str) -> set:
    with m.at_slab(sid):
        cells = {(i, j) for i in range(len(m.gx) - 1) for j in range(len(m.gy) - 1) if m.cell_in(i, j)}
    for c in m.cores:
        for (i, j) in list(cells):
            cx, cy = (m.gx[i] + m.gx[i + 1]) / 2, (m.gy[j] + m.gy[j + 1]) / 2
            if c["x0"] < cx < c["x1"] and c["y0"] < cy < c["y1"]:
                cells.discard((i, j))
    return cells


def panels_layout(m: Frame, cells: set, o: str, n: int, prefix: str, layup: str) -> list[dict]:
    """Calepinage : panneaux de largeur ≤ 2,95 m alignés sur la trame (chaque travée perpendiculaire divisée en parts égales),
    longueur = travées consécutives pleines jusqu'à 13,5 m, extrémités toujours sur une file porteuse."""
    gs = m.gx if o == "x" else m.gy               # direction de portée
    gp = m.gy if o == "x" else m.gx               # direction perpendiculaire
    out = []
    k = 0
    for jp in range(len(gp) - 1):
        wbay = gp[jp + 1] - gp[jp]
        nw = math.ceil(wbay / PANEL_MAX_W - 1e-9)
        w = wbay / nw
        run = []
        runs = []
        for js in range(len(gs) - 1):
            cell = (js, jp) if o == "x" else (jp, js)
            if cell in cells:
                run.append(js)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        for run in runs:
            # découpe en panneaux de longueur ≤ PANEL_MAX_L (sur files porteuses ou pannes)
            pieces, cur = [], [run[0]]
            for js in run[1:]:
                if gs[js + 1] - gs[cur[0]] <= PANEL_MAX_L + 1e-6:
                    cur.append(js)
                else:
                    pieces.append(cur)
                    cur = [js]
            pieces.append(cur)
            for pc in pieces:
                a0, a1 = gs[pc[0]], gs[pc[-1] + 1]
                segs = [(a0, a1)]
                if a1 - a0 > PANEL_MAX_L + 1e-6:              # une seule travée plus longue que 13,5 m : coupe sur pannes
                    step = (a1 - a0) / n
                    per = max(1, int(PANEL_MAX_L // step))
                    segs = [(a0 + step * i, min(a1, a0 + step * (i + per))) for i in range(0, n, per)]
                for (s0, s1) in segs:
                    for kw in range(nw):
                        k += 1
                        p0, p1 = gp[jp] + kw * w, gp[jp] + (kw + 1) * w
                        x0, x1, y0, y1 = (s0, s1, p0, p1) if o == "x" else (p0, p1, s0, s1)
                        nsup = round((s1 - s0) / ((gs[pc[0] + 1] - gs[pc[0]]) / n)) + 1
                        out.append({"id": f"{prefix}-{k}", "x0": round(x0, 4), "x1": round(x1, 4), "y0": round(y0, 4), "y1": round(y1, 4),
                                    "L": round(s1 - s0, 3), "w": round(w, 3), "layup": layup, "supports": nsup, "dir": o})
    return out


def _panel_types(panels: list[dict]) -> list[dict]:
    types = {}
    for p in panels:
        key = (p["layup"], round(p["L"], 2), round(p["w"], 2))
        types.setdefault(key, []).append(p["id"])
    out = []
    for k_, (key, ids) in enumerate(sorted(types.items(), key=lambda kv: (-len(kv[1]), kv[0])), 1):
        out.append({"type": f"T{k_}", "layup": key[0], "L": key[1], "w": key[2], "n": len(ids), "ids": ids,
                    "area": round(key[1] * key[2] * len(ids), 2), "vol": round(key[1] * key[2] * int(key[0].split()[0]) / 1000 * len(ids), 3)})
    for p in panels:
        p["type"] = next(tp["type"] for tp in out if p["id"] in tp["ids"])
    return out


def beams_for_slab(m: Frame, cells: set, o: str, n: int, lvl: str, ld: dict, clt: dict, R: int, defl, facade: float, roof: bool,
                   issues: list) -> list[dict]:
    """Poutres GL du plancher : porteuses (files ⟂ portée), pannes intermédiaires, sommiers (files ∥ portée, si pannes),
    rives de façade. Toutes isostatiques entre nœuds (étriers)."""
    gs = m.gx if o == "x" else m.gy
    gp = m.gy if o == "x" else m.gx
    G, q = clt["G"], ld["q"]
    cols = set(m.columns)

    def cell(js, jp):
        return ((js, jp) if o == "x" else (jp, js)) in cells

    def node(js, jp):
        return (js, jp) if o == "x" else (jp, js)
    beams = []
    kb = kp = 0
    out_edges = lambda js, jp: (not cell(js - 1, jp)) or (not cell(js, jp))       # file porteuse en rive
    # ---- poutres porteuses sur les files ⟂ portée (positions gs[js]) et pannes (positions intermédiaires)
    for js in range(len(gs)):
        for jp in range(len(gp) - 1):
            left, right = cell(js - 1, jp), cell(js, jp)
            if not (left or right):
                continue
            sl = (gs[js] - gs[js - 1]) / n if left and js > 0 else 0.0
            sr = (gs[js + 1] - gs[js]) / n if right and js < len(gs) - 1 else 0.0
            k = 1.25 if (left and right) or n > 1 else 1.0
            trib = (sl + sr) / 2 * k
            fac = facade if not (left and right) else 0.0
            L = gp[jp + 1] - gp[jp]
            kb += 1
            beams.append({"id": f"B{lvl}-{kb}", "role": "main", "o": "p", "L": round(L, 3), "trib": round(trib, 3),
                          "wg": G * trib + fac, "wq": q * trib, "Pg": [], "Pq": [], "line": ("s", js), "a0": gp[jp], "a1": gp[jp + 1],
                          "n0": node(js, jp), "n1": node(js, jp + 1)})
        if js < len(gs) - 1 and n > 1:
            for jp in range(len(gp) - 1):
                if not cell(js, jp):
                    continue
                s = (gs[js + 1] - gs[js]) / n
                for kk in range(1, n):
                    kp += 1
                    L = gp[jp + 1] - gp[jp]
                    beams.append({"id": f"P{lvl}-{kp}", "role": "purlin", "o": "p", "L": round(L, 3), "trib": round(s * 1.25, 3),
                                  "wg": G * s * 1.25, "wq": q * s * 1.25, "Pg": [], "Pq": [], "line": ("s", js + kk / n),
                                  "pos": gs[js] + kk * s, "a0": gp[jp], "a1": gp[jp + 1], "n0": None, "n1": None, "cell": (js, jp)})
    # ---- sommiers (files ∥ portée) : si pannes, ou en rive de façade
    for jp in range(len(gp)):
        for js in range(len(gs) - 1):
            below, above = cell(js, jp - 1), cell(js, jp)
            if not (below or above):
                continue
            edge = not (below and above)
            if n == 1 and not edge:
                continue
            L = gs[js + 1] - gs[js]
            Pg, Pq = [], []
            if n > 1:
                for side_ok, jpp in ((below, jp - 1), (above, jp)):
                    if not side_ok:
                        continue
                    span_p = gp[jpp + 1] - gp[jpp]
                    s = L / n
                    for kk in range(1, n):
                        Pg.append((s * kk, (G * s * 1.25 + 0.0) * span_p / 2))
                        Pq.append((s * kk, q * s * 1.25 * span_p / 2))
            kb += 1
            beams.append({"id": f"B{lvl}-{kb}", "role": "girder" if n > 1 else "edge", "o": "s", "L": round(L, 3), "trib": 0.0,
                          "wg": facade if edge else 0.0, "wq": 0.0, "Pg": Pg, "Pq": Pq, "line": ("p", jp), "a0": gs[js], "a1": gs[js + 1],
                          "n0": node(js, jp), "n1": node(js + 1, jp)})
    # ---- dimensionnement (sections homogénéisées par rôle et portée, comme en atelier)
    for bm in beams:
        sw_p = 0.0
        if bm["role"] == "girder":                       # poids propre des pannes ajouté aux charges ponctuelles
            sw_p = 0.0
        r = timber.design_gl_beam(bm["L"], bm["wg"], bm["wq"], bm["Pg"], bm["Pq"], SIZES, psi1=ld["psi1"], psi2=ld["psi2"],
                                  q_dur=ld["dur"], R=R, defl=defl)
        bm.update(sec=r, b=r["b"], h=r["h"], grade=r["grade"])
        if not r["ok"]:
            issues.append({"code": "GL-NOK", "level": BLOCK, "message": t(
                f"Poutre {bm['id']} : aucune section GL jusqu'à {r['b']}×{r['h']} ne vérifie (taux {num(r['u_max'])}).",
                f"Viga {bm['id']}: nenhuma secção GL até {r['b']}×{r['h']} verifica (taxa {num(r['u_max'])}).",
                f"Beam {bm['id']}: no GL section up to {r['b']}×{r['h']} works (ratio {num(r['u_max'])}).",
                f"Балка {bm['id']}: жоден переріз GL до {r['b']}×{r['h']} не проходить (коеф. {num(r['u_max'])}).")})
    # ---- appuis : réaction aux nœuds (poteaux) ou aux sommiers / noyaux
    for bm in beams:
        sec = bm["sec"]
        bm["R0"] = {"g": sec["R_g"][0], "q": sec["R_q"][0]}
        bm["R1"] = {"g": sec["R_g"][1], "q": sec["R_q"][1]}
        for key in ("n0", "n1"):
            nd = bm.get(key)
            if nd is not None and nd not in cols and not m.in_core(m.gx[nd[0]], m.gy[nd[1]], strict=False):
                issues.append({"code": "GL-SUP", "level": WARN, "message": t(
                    f"Poutre {bm['id']} : pas de poteau au nœud {m.node_name(*nd)} — appui sur poutre de reprise à prévoir.",
                    f"Viga {bm['id']}: sem pilar no nó {m.node_name(*nd)} — prever viga de transição.",
                    f"Beam {bm['id']}: no column at node {m.node_name(*nd)} — a transfer beam is required.",
                    f"Балка {bm['id']}: немає колони у вузлі {m.node_name(*nd)} — потрібна передатна балка.")})
    return beams


# ============================================================ assemblages
def hanger(bm: dict, R_uls: float, kmod: float) -> dict:
    """Étrier caché (plaque âme + vis inclinées 45° entièrement filetées Ø8) : nombre de vis côté poutre portée.
    Chaque vis inclinée reprend V·/(n·cos45°) en traction ; résistance = min(arrachement, traction acier)."""
    h = bm["h"]
    lef = min(160.0, 0.5 * h)
    sc = timber.screw_axial(8, lef, 385, 45.0, kmod)
    per = sc["R_d"] * math.cos(math.radians(45)) / 1000          # kN de tranchant par vis
    nv = max(4, math.ceil(R_uls / per / 2) * 2)
    plate_h = min(h - 60, max(120, nv // 2 * 50 + 40))
    return {"type": "H", "screws": nv, "d": 8, "L": int(round(lef * 1.414 / 20) * 20 + 40), "V_Ed": round(R_uls, 1), "per_screw": round(per, 2),
            "V_Rd": round(per * nv, 1), "u": round(R_uls / (per * nv), 3), "plate": f"{plate_h}×{max(8, 10 if R_uls > 120 else 8)}"}


def base_plate(b: int, h: int, NEd: float, fck: float, V: float = 0.0) -> dict:
    """Pied de poteau : platine S355 sur mortier de calage, EN 1993-1-8 §6.2.5 (f_jd = β_j·α·f_cd, β_j = 2/3, α = 1,5),
    largeur d'appui additionnelle c = t·√(f_y/(3 f_jd γ_M0)) ; 4 tiges M16 ou M20 (reprise du tranchant)."""
    fcd = fck / 1.5
    fjd = 2 / 3 * 1.5 * fcd
    Areq = NEd * 1000 / fjd                          # mm²
    t = 15
    while True:
        c = t * math.sqrt(355 / (3 * fjd * 1.0))
        Aeff = (b + 2 * c) * (h + 2 * c)
        if Aeff >= Areq or t >= 50:
            break
        t += 5
    B = int(math.ceil((max(b, h) + 2 * max(c, 50)) / 10) * 10)
    rod = "M20" if V > 40 or NEd > 1500 else "M16"
    return {"t": t, "B": B, "rod": rod, "n_rod": 4, "f_jd": round(fjd, 2), "A_req": round(Areq), "u": round(Areq / Aeff, 3) if Aeff else 9.9,
            "dowels": "4 tiges collées Ø16 × 400" if NEd > 800 else "vis Ø10 × 200 (8)"}


def clt_on_beam(G: float, q: float, s: float, kmod: float) -> dict:
    """Fixation CLT / poutre : vis Ø8 entièrement filetées à 90°, ancrage ≥ 100 mm dans la poutre ; espacement courant 300 mm
    (diaphragme) et résistance à l'arrachement en dépression de toiture vérifiée séparément."""
    sc = timber.screw_axial(8, 100, 385, 90, kmod)
    return {"d": 8, "spacing": 300, "R_d": round(sc["R_d"] / 1000, 2)}


# ============================================================ calcul général
def compute(m: Frame) -> dict:
    warns: list = []
    issues: list = []
    decisions: list = []
    c = m.country if m.country in ("FR", "PT", "UA") else "FR"
    syst = system(m)
    H = m.height_total
    snow = norms.snow(m.raw, c, warns)
    wind = norms.wind(m.raw, c, H, warns)
    seis = norms.seismic(m.raw, c, warns)
    occ = [l for l in m.levels]
    h_last = max(0.0, m.levels[-1].z - m.levels[0].z)
    main_use = next((l.use for l in m.levels if not l.on_grade), m.levels[-1].use)
    R, R_src = norms.fire_rating(m.raw, c, h_last, len(m.levels), main_use)
    defl = norms.DEFL.get(c, (300, 250))
    from .devis import prices as _prices
    prices = _prices(c)
    slabs = m.slabs
    timber_slabs = [s for s in slabs if not any(l.id == s.id and l.on_grade for l in m.levels)]
    facade = float((m.raw.get("facade") or {}).get("weight", 0.8))
    # schéma porteur : choisi sur le plancher courant le plus chargé
    ref = None
    for s in timber_slabs:
        ld = _loads_for(m, s.use, s.id == "COB", snow)
        if ref is None or ld["g"] + ld["q"] > ref["g"] + ref["q"]:
            ref = ld
    ref = ref or _loads_for(m, "habitation", False, snow)
    if syst == "walls":
        o = "y" if max(_bays(m, "y")) <= max(_bays(m, "x")) else "x"
        sch = {"o": m.st.get("clt_span_dir") if m.st.get("clt_span_dir") in ("x", "y") else o, "n": 1, "cands": []}
        sch["s"] = max(_bays(m, sch["o"]))
        decisions.append(t(f"Murs CLT porteurs sur les files ⟂ {sch['o'].upper()} ; planchers CLT portant selon {sch['o'].upper()}.",
                           f"Paredes CLT resistentes nos alinhamentos ⟂ {sch['o'].upper()}; lajes CLT a vencer segundo {sch['o'].upper()}.",
                           f"Load-bearing CLT walls on the grid lines ⟂ {sch['o'].upper()}; CLT floors spanning {sch['o'].upper()}.",
                           f"Несучі стіни CLT по осях ⟂ {sch['o'].upper()}; перекриття CLT з прольотом за {sch['o'].upper()}."))
    else:
        sch = choose_scheme(m, ref, R, defl, prices, decisions)
    o, n = sch["o"], sch["n"]
    floors = []
    for s in timber_slabs:
        roof = s.id == "COB"
        sname = t("Toiture", "Cobertura", "Roof", "Покрівля") if roof else s.name
        ld = _loads_for(m, s.use, roof, snow)
        cells = _cells(m, s.id)
        if not cells:
            continue
        gs = m.gx if o == "x" else m.gy
        spans = sorted({round((gs[k + 1] - gs[k]) / n, 3) for k in range(len(gs) - 1)})
        imposed = layup(m.st.get("clt_roof_layup" if roof else "clt_floor_layup"))
        if imposed:                                   # composition imposée par le plan de l'architecte / du fabricant : on la VÉRIFIE
            clt = timber.design_clt(max(spans), ld["g"], ld["q"], ld["psi1"], ld["psi2"], R, q_dur=ld["dur"], defl=defl, a_vib=_avib(m, ld),
                                    layups=[imposed])
            mini = timber.design_clt(max(spans), ld["g"], ld["q"], ld["psi1"], ld["psi2"], R, q_dur=ld["dur"], defl=defl, a_vib=_avib(m, ld))
            decisions.append(t(f"{sname} : CLT {imposed[0]} imposé par le plan, vérifié (taux {num(clt['u_max'])}, {clt['governing']}) — minimum de calcul : {mini['name']}.",
                               f"{sname}: CLT {imposed[0]} imposto pela planta, verificado (taxa {num(clt['u_max'])}, {clt['governing']}) — mínimo de cálculo: {mini['name']}.",
                               f"{sname}: CLT {imposed[0]} specified on the drawings, checked (ratio {num(clt['u_max'])}, {clt['governing']}) — calculated minimum: {mini['name']}.",
                               f"{sname}: CLT {imposed[0]} задано кресленнями, перевірено (коеф. {num(clt['u_max'])}, {clt['governing']}) — розрахунковий мінімум: {mini['name']}."))
            if len(spans) > 1:                        # taux par portée : localise les travées à reprendre (sens de pose, épaisseur, poutre)
                det = []
                for sp in spans:
                    ck = timber.design_clt(sp, ld["g"], ld["q"], ld["psi1"], ld["psi2"], R, q_dur=ld["dur"], defl=defl, a_vib=_avib(m, ld), layups=[imposed])
                    det.append(f"{num(sp)} m → {num(ck['u_max'])}{'' if ck['u_max'] <= 1 else ' ✗'}")
                decisions.append(t(f"{sname} : CLT {imposed[0]} par portée : " + " ; ".join(det) + ".",
                                   f"{sname}: CLT {imposed[0]} por vão: " + "; ".join(det) + ".",
                                   f"{sname}: CLT {imposed[0]} per span: " + "; ".join(det) + ".",
                                   f"{sname}: CLT {imposed[0]} за прольотами: " + "; ".join(det) + "."))
        else:
            clt = timber.design_clt(max(spans), ld["g"], ld["q"], ld["psi1"], ld["psi2"], R, q_dur=ld["dur"], defl=defl, a_vib=_avib(m, ld))
        if not clt["ok"]:
            issues.append({"code": "CLT-NOK", "level": BLOCK, "message": t(
                f"Plancher {sname} : portée {num(max(spans))} m trop grande pour le CLT 280 mm (taux {num(clt['u_max'])}, {clt['governing']}).",
                f"Laje {sname}: vão {num(max(spans))} m demasiado grande para CLT 280 mm (taxa {num(clt['u_max'])}).",
                f"Floor {sname}: span {num(max(spans))} m too long for 280 mm CLT (ratio {num(clt['u_max'])}).",
                f"Перекриття {sname}: проліт {num(max(spans))} м завеликий для CLT 280 мм (коеф. {num(clt['u_max'])})."),
                "fix": t("Ajouter des pannes ou réduire la trame.", "Acrescentar madres ou reduzir a trama.", "Add purlins or reduce the grid.",
                         "Додати прогони або зменшити сітку.")})
        lvl_no = "R" if roof else str(next((k + 1 for k, l in enumerate(m.levels) if l.id == s.id), len(floors) + 1))
        panels = panels_layout(m, cells, o, n, f"FP{lvl_no}", clt["name"])
        ptypes = _panel_types(panels)
        beams = [] if syst == "walls" else beams_for_slab(m, cells, o, n, lvl_no, ld, clt, R, defl, facade * (1.0 if roof else _storey_h(m, s)), roof, issues)
        area = sum((m.gx[i + 1] - m.gx[i]) * (m.gy[j + 1] - m.gy[j]) for (i, j) in cells)
        floors.append({"id": s.id, "name": sname, "z": s.z, "roof": roof, "loads": ld, "clt": clt, "panels": panels, "ptypes": ptypes,
                       "beams": beams, "area": round(area, 2), "cells": sorted(cells), "tag": lvl_no, "level_below": s.level_below,
                       "spans": spans})
    # ---- descente de charges : poteaux (ou murs)
    cols, walls = ([], _walls(m, floors, o, R, snow, wind, issues, decisions)) if syst == "walls" else (_columns(m, floors, R, issues), [])
    fnd = _foundations(m, cols, walls, issues)
    lat = _lateral(m, floors, syst, wind, seis, walls, issues)
    conns = _connections(m, floors, cols, issues)
    q = quantities(m, floors, cols, walls, fnd, conns, lat)
    for code, msg in warns:
        issues.append({"code": code, "level": WARN, "message": msg})
    review = _review(m, floors, cols, walls, fnd, lat, R)
    return {"system": syst, "country": c, "scheme": sch, "R": R, "R_src": R_src, "snow": snow, "wind": wind, "seismic": seis,
            "defl": defl, "floors": floors, "columns": cols, "walls": walls, "foundations": fnd, "lateral": lat, "connections": conns,
            "quantities": q, "issues": issues, "decisions": decisions, "review": review, "H": H, "facade": facade}


def _storey_h(m: Frame, s) -> float:
    lv = next((l for l in m.levels if l.id == s.level_below), None)
    return lv.height if lv else 3.0


# ============================================================ poteaux
def _columns(m: Frame, floors: list, R: int, issues: list) -> list[dict]:
    """Poteaux GL par étage (aboutés plancher par plancher sur platines acier, CLT découpé autour du poteau)."""
    nodes = m.columns
    lv_ids = [l.id for l in m.levels]
    by_slab = {f["id"]: f for f in floors}
    out = []
    for (i, j) in nodes:
        name = m.node_name(i, j)
        Ng = Nq = 0.0
        segs = []
        sec_prev = None
        top_down = []
        # étages du haut vers le bas : chaque étage porte le plancher situé au-dessus de lui
        for k in range(len(m.levels) - 1, -1, -1):
            lv = m.levels[k]
            if lv.on_grade and k == 0 and False:
                pass
            slab_above = "COB" if k == len(m.levels) - 1 else m.levels[k + 1].id
            f = by_slab.get(slab_above)
            dG = dQ = 0.0
            Mg = Mq = 0.0
            if f:
                left = {"g": 0.0, "q": 0.0}
                right = {"g": 0.0, "q": 0.0}
                for bm in f["beams"]:
                    for key, rk in (("n0", "R0"), ("n1", "R1")):
                        if bm.get(key) == (i, j):
                            dG += bm[rk]["g"]
                            dQ += bm[rk]["q"]
                            side = left if (bm["o"] == "p") == (key == "n0") else right
                            side["g"] += bm[rk]["g"]
                            side["q"] += bm[rk]["q"]
                ecc = 0.15
                Mg = abs(left["g"] - right["g"]) * ecc
                Mq = max(left["q"], right["q"]) * ecc
            if lv.on_grade and k == 0:
                # étage sur dallage : le poteau du RDC descend sur sa semelle
                pass
            top_down.append((lv, dG, dQ, Mg, Mq, f is not None))
        cum_g = cum_q = 0.0
        for (lv, dG, dQ, Mg, Mq, has) in top_down:
            cum_g += dG
            cum_q += dQ
            if cum_g + cum_q <= 0:
                continue
            Lc = lv.height - 0.3
            topmost = not segs
            best = None
            for (b, h) in GL_COLS:
                if sec_prev and b < sec_prev[0]:
                    continue
                for grade in ("GL24h", "GL28h"):
                    sw = 4.6 * b * h / 1e6 * lv.height
                    r = timber.check_gl_column(b, h, grade, Lc, cum_g + sw, cum_q, Mg, Mq, q_dur="medium", R=R, top=topmost)
                    if r["ok"]:
                        best = r
                        break
                if best:
                    break
            if best is None:
                b, h = GL_COLS[-1]
                best = timber.check_gl_column(b, h, "GL28h", Lc, cum_g, cum_q, Mg, Mq, R=R, top=topmost)
                issues.append({"code": "COL-NOK", "level": BLOCK, "message": t(
                    f"Poteau {name} ({lv.name}) : section 600×600 insuffisante (taux {num(best['u_max'])}).",
                    f"Pilar {name} ({lv.name}): secção 600×600 insuficiente (taxa {num(best['u_max'])}).",
                    f"Column {name} ({lv.name}): 600×600 section insufficient (ratio {num(best['u_max'])}).",
                    f"Колона {name} ({lv.name}): переріз 600×600 недостатній (коеф. {num(best['u_max'])}).")})
            cum_g += 4.6 * best["b"] * best["h"] / 1e6 * lv.height
            sec_prev = (best["b"], best["h"])
            segs.append({"level": lv.id, "level_name": lv.name, "b": best["b"], "h": best["h"], "grade": best["grade"], "Lc": round(Lc, 2),
                         "Ng": round(cum_g, 1), "Nq": round(cum_q, 1), "NEd": round(1.35 * cum_g + 1.5 * cum_q, 1), "Nser": round(cum_g + cum_q, 1),
                         "chk": best})
        if not segs:
            continue
        segs.reverse()                        # du bas vers le haut
        out.append({"name": name, "node": (i, j), "x": m.gx[i], "y": m.gy[j], "b": segs[0]["b"] / 1000, "h": segs[0]["h"] / 1000,
                    "segs": segs})
    for k, c in enumerate(out, 1):
        c["id"] = f"C-{k}"
    return out


# ============================================================ murs CLT (système murs)
def _walls(m: Frame, floors: list, o: str, R: int, snow: dict, wind: dict, issues: list, decisions: list) -> list[dict]:
    """Murs porteurs CLT sur chaque file ⟂ portée (et murs de façade ∥ portée) ; bande de 1 m, flambement + vent latéral."""
    gs = m.gx if o == "x" else m.gy
    gp = m.gy if o == "x" else m.gx
    out = []
    by_slab = {f["id"]: f for f in floors}
    for js in range(len(gs)):
        # charge linéique cumulée, du haut vers le bas
        ng = nq = 0.0
        segs = []
        for k in range(len(m.levels) - 1, -1, -1):
            lv = m.levels[k]
            sid = "COB" if k == len(m.levels) - 1 else m.levels[k + 1].id
            f = by_slab.get(sid)
            if f:
                cells = set(map(tuple, f["cells"]))
                left = any(((js - 1, jp) if o == "x" else (jp, js - 1)) in cells for jp in range(len(gp) - 1))
                right = any(((js, jp) if o == "x" else (jp, js)) in cells for jp in range(len(gp) - 1))
                sl = gs[js] - gs[js - 1] if left and js > 0 else 0
                sr = gs[js + 1] - gs[js] if right and js < len(gs) - 1 else 0
                kk = 1.25 if left and right else 1.0
                ng += f["clt"]["G"] * (sl + sr) / 2 * kk
                nq += f["loads"]["q"] * (sl + sr) / 2 * kk
            run = _run(m, o, js, lv.id, bearing=True)
            if ng + nq <= 0 or not run:
                continue
            ext = js in (0, len(gs) - 1) or _run(m, o, js, lv.id, bearing=False) is not None
            seg = _wall_check(lv.height, ng, nq, R, wind["qp"] * 1.1 if ext else 0.0, _wall_lays(m))
            ng += seg["sw"]
            segs.append(dict(seg, level=lv.id, level_name=lv.name, ng=round(ng, 1), nq=round(nq, 1), leaves=1, **run))
        if segs:
            segs.reverse()
            out.append({"id": f"W{js + 1}", "axis": o, "pos": gs[js], "a": segs[0]["a"], "b": segs[0]["b"], "L": segs[0]["L"],
                        "bearing": True, "segs": segs, "n_ser": segs[0]["ng"] + segs[0]["nq"],
                        "n_uls": round(1.35 * segs[0]["ng"] + 1.5 * segs[0]["nq"], 1)})
    # façades parallèles à la portée (non porteuses verticalement, contreventement + vent), y compris les façades en retrait
    # d'un étage (emprise en L) : longueur réelle par étage
    for jp in range(len(gp)):
        segs = []
        ng = 0.0
        for k in range(len(m.levels) - 1, -1, -1):
            lv = m.levels[k]
            run = _run(m, o, jp, lv.id, bearing=False)
            if not run:
                continue
            pw = _party(m, o, jp) if jp in (0, len(gp) - 1) else (_wall_lays(m), 1)
            seg = _wall_check(lv.height, (ng + 2.0) / pw[1], 0.0, R, wind["qp"] * 1.1 / pw[1], pw[0])
            ng += seg["sw"]
            segs.append(dict(seg, level=lv.id, level_name=lv.name, ng=round(ng + 2.0, 1), nq=0.0, leaves=pw[1], **run))
        if not segs:
            continue
        segs.reverse()
        wid = "WS" if jp == 0 else "WN" if jp == len(gp) - 1 else f"WF{jp}"
        out.append({"id": wid, "axis": "y" if o == "x" else "x", "pos": gp[jp], "a": segs[0]["a"], "b": segs[0]["b"],
                    "L": segs[0]["L"], "bearing": False, "segs": segs, "n_ser": segs[0]["ng"], "n_uls": round(1.35 * segs[0]["ng"], 1)})
    for w in out:
        if any(not s["ok"] for s in w["segs"]):
            ly = next(s_["layup"] for s_ in w["segs"] if not s_["ok"])
            issues.append({"code": "WALL-NOK", "level": BLOCK, "message": t(f"Mur {w['id']} : CLT {ly} insuffisant.", f"Parede {w['id']}: CLT {ly} insuficiente.",
                                                                            f"Wall {w['id']}: CLT {ly} insufficient.", f"Стіна {w['id']}: CLT {ly} недостатньо.")})
    return out


def _run(m: Frame, o: str, line: int, lid: str, bearing: bool) -> dict | None:
    """Étendue réelle d'un mur sur une file à un étage (emprise propre à l'étage : retraits, L, U).
    bearing : file `line` de la trame de portée gs, mur présent là où une case de l'étage la borde ;
    sinon façade sur la file `line` de gp, présente là où UNE seule des deux cases adjacentes existe (contour)."""
    gs = m.gx if o == "x" else m.gy
    gp = m.gy if o == "x" else m.gx
    with m.at_storey(lid):
        def cell(a_, b_):                    # a_ le long de gs, b_ le long de gp
            return m.cell_in(a_, b_) if o == "x" else m.cell_in(b_, a_)
        iv = []
        if bearing:
            for k in range(len(gp) - 1):
                if cell(line - 1, k) or cell(line, k):
                    iv.append((gp[k], gp[k + 1]))
        else:
            for k in range(len(gs) - 1):
                if cell(k, line - 1) != cell(k, line):
                    iv.append((gs[k], gs[k + 1]))
    if not iv:
        return None
    return {"a": iv[0][0], "b": iv[-1][1], "L": round(sum(b_ - a_ for a_, b_ in iv), 2)}


def _wall_lays(m: Frame) -> list:
    lay = layup(m.st.get("wall_layup"))
    return [lay] if lay else WALL_LAYUPS


def _party(m: Frame, o: str, jp: int) -> tuple[list, int]:
    """Mur mitoyen double (ex. 2 × CLT 80 L3s + isolant acoustique) sur la façade parallèle à la portée : chaque voile reprend la
    moitié du vent et de son poids ; il est vérifié seul. structure.party_wall = {side: x0|x1|y0|y1, layup, leaves}."""
    pw = m.st.get("party_wall") or {}
    side = ("y0" if jp == 0 else "y1") if o == "x" else ("x0" if jp == 0 else "x1")
    lay = layup(pw.get("layup"))
    if lay and str(pw.get("side", "")).lower() == side:
        return [lay], max(1, int(pw.get("leaves") or 1))
    return _wall_lays(m), 1


def _wall_check(Hs: float, ng: float, nq: float, R: int, wlat: float, lays: list | None = None) -> dict:
    """Mur CLT (bande 1 m, plis longitudinaux verticaux) : flambement §6.3.2 sur la section efficace (méthode γ), vent latéral
    (M = w·h²/8), compression ⟂ du plancher sous le mur (plate-forme, k_c,90 = 1,0)."""
    lays = lays or WALL_LAYUPS
    for name, lay in lays:
        p = timber.clt_props(lay, Hs * 1000)
        A = 1000 * sum(t_ for k, t_ in enumerate(lay) if k % 2 == 0)
        I_ef = p["EI"] / CLT["E0"]
        i = math.sqrt(I_ef / A)
        lr = Hs * 1000 / i / math.pi * math.sqrt(CLT["fc0"] / CLT["E05"])
        kk = 0.5 * (1 + 0.1 * (lr - 0.3) + lr * lr)
        kc = 1.0 if lr <= 0.3 else 1 / (kk + math.sqrt(kk * kk - lr * lr))
        sw = 5.0 * sum(lay) / 1000 * Hs
        N = (1.35 * (ng + sw) + 1.5 * nq) * 1000
        M = 1.5 * wlat * Hs ** 2 / 8 * 1e6 * 0.6 if wlat else 0.0           # vent en accompagnement (ψ0 = 0,6)
        fc = 0.8 * CLT["fc0"] / 1.25
        fm = 0.9 * CLT["fm"] / 1.25
        u = N / A / (kc * fc) + (M * p["s_fac"] / fm if M else 0.0)
        sc90 = N / (sum(lay) * 1000)
        u90 = sc90 / (0.8 * CLT["fc90"] / 1.25)
        fire = None
        if R:
            dch = timber.char_depth(R, lay) + 7
            pf = timber.clt_props(lay, Hs * 1000, remove_bottom=dch)
            if pf["ok"]:
                secf = timber._clt_section(lay, dch)
                Af = 1000 * sum(t_ for t_, z, lg in secf if lg)
                If = pf["EI"] / CLT["E0"]
                lrf = Hs * 1000 / math.sqrt(If / Af) / math.pi * math.sqrt(CLT["fc0"] / CLT["E05"])
                kf = 0.5 * (1 + 0.1 * (lrf - 0.3) + lrf * lrf)
                kcf = 1.0 if lrf <= 0.3 else 1 / (kf + math.sqrt(kf * kf - lrf * lrf))
                Nfi = (ng + sw + 0.5 * nq) * 1000
                fire = {"R": R, "u": round(Nfi / Af / (kcf * 1.15 * CLT["fc0"]), 3)}
            else:
                fire = {"R": R, "u": 9.9}
        ok = u <= 1 and u90 <= 1 and (fire is None or fire["u"] <= 1)
        if ok or name == lays[-1][0]:
            return {"ok": ok, "layup": name, "t": sum(lay), "kc": round(kc, 3), "u": round(u, 3), "u_c90": round(u90, 3), "sw": round(sw, 2),
                    "N_Ed": round(N / 1000, 1), "fire": fire}


# ============================================================ fondations (gros œuvre)
def _foundations(m: Frame, cols: list, walls: list, issues: list) -> dict:
    from engines.bet_frame import calc as fc
    mt = fc.mat(m)
    out = {"pads": [], "strips": [], "kind": "isolees"}
    if cols:
        r = fc.foundations(m, [dict(c, b=c["segs"][0]["b"] / 1000, h=c["segs"][0]["h"] / 1000) for c in cols], mt, issues)
        out = r
    if walls:
        geo = m.geo
        sigma = float(geo.get("sigma_adm_mpa") or 0.20) * 1000
        if not geo.get("sigma_adm_mpa"):
            issues.append({"code": "GEO-HYP", "level": WARN, "message": t(
                "Pas d'étude de sol : contrainte admissible 0,20 MPa et assise à 1,00 m retenues par défaut.",
                "Sem estudo geotécnico: tensão admissível 0,20 MPa e cota de fundação 1,00 m admitidas.",
                "No soil report: allowable bearing 0.20 MPa and 1.00 m founding depth assumed.",
                "Немає геології: прийнято допустимий тиск 0,20 МПа та глибину закладання 1,00 м.")})
        strips = []
        for w in walls:
            n = w["n_ser"] + 0.5 * 25 * 1.0           # + longrine / soubassement BA
            B = max(0.40, fc.ceil_to(n * 1.1 / sigma, 0.05))
            hf = max(0.30, fc.ceil_to((B - 0.2) / 4 + 0.05, 0.05))
            As = (1.35 * n + 0) * (B - 0.2) / (8 * (hf - 0.06) * mt["fyd"] * 1000)
            strips.append({"id": "SF-" + w["id"], "wall": w["id"], "B": B, "h": hf, "n": round(n, 1), "sigma": round(n * 1.1 / B, 1),
                           "As_cm2_m": round(max(As, 0.001 * hf) * 1e4, 2), "mesh": fc.pick_mesh(max(As, 0.001 * hf), hf, False),
                           "axis": w["axis"], "pos": w["pos"], "a": w["a"], "b": w["b"], "L": w["L"]})
        out = dict(out, wall_strips=strips, sigma_kpa=sigma, depth=float(geo.get("depth", 1.0) or 1.0), assumed=not geo.get("sigma_adm_mpa"))
    out["mt"] = {"concrete": mt["concrete"], "steel": mt["steel"]}
    base = m.levels[0]
    out["ground_slab"] = {"on_grade": base.on_grade, "h": 0.16 if base.use not in ("stationnement", "technique", "commerce") else 0.20,
                          "area": round(m.footprint, 1), "mesh": "ST 25 C" if m.country == "FR" else "AR 50 (#Ø8//0,15)" if m.country == "PT" else "Ø8 A500 / 150×150"}
    perim = sum(math.dist(a, b) for a, b in m.boundary_edges())
    out["plinth"] = {"h": 0.30, "t": 0.20, "L": round(perim, 1)}
    return out


# ============================================================ stabilité horizontale
def _lateral(m: Frame, floors: list, syst: str, wind: dict, seis: dict, walls: list, issues: list) -> dict:
    H = m.height_total
    Lx, Ly = m.L, m.W
    cf = 1.3
    Vw = {"x": round(cf * wind["qp"] * Ly * H, 1), "y": round(cf * wind["qp"] * Lx * H, 1)}     # vent agissant selon x / y (kN)
    mass = 0.0
    for f in floors:
        psi2 = 0.0 if f["roof"] else f["loads"]["psi2"]
        mass += (f["clt"]["G"] + psi2 * f["loads"]["q"]) * f["area"] + sum(b["sec"]["sw"] * b["L"] for b in f["beams"])
    T1 = 0.05 * H ** 0.75
    # séisme non requis : FR zones 1–2 pour les bâtiments de catégorie d'importance II (arrêté du 22/10/2010) ;
    # UA intensité ≤ 6 (ДБН В.1.1-12) ; sinon méthode des forces latérales (EN 1998-1 §4.3.3.2)
    zone_fr = int((m.raw.get("seismic") or {}).get("zone") or (m.raw.get("project") or {}).get("seismic_zone") or 2)
    seis_req = not ((m.country == "FR" and zone_fr <= 2 and seis["gamma_i"] <= 1.0) or (m.country == "UA" and seis["agr"] <= 0.5))
    Tc = 0.5 if m.country == "PT" else 0.4
    ag = seis["agr"] * seis["gamma_i"]
    Sd = ag * seis["S"] * 2.5 / seis["q"] if T1 <= Tc else ag * seis["S"] * 2.5 / seis["q"] * Tc / T1
    lam = 0.85 if (T1 <= 2 * Tc and len(m.levels) > 2) else 1.0
    Vs = round(Sd / 9.81 * mass * lam, 1) if seis_req else 0.0
    Vd = {d: max(1.5 * Vw[d], Vs) for d in ("x", "y")}
    gov = {d: ("vent" if 1.5 * Vw[d] >= Vs else "séisme") for d in ("x", "y")}
    res = {"Vw": Vw, "Vs": Vs, "seis_req": seis_req, "T1": round(T1, 3), "Sd": round(Sd, 3), "mass_kN": round(mass, 1), "V_d": {k: round(v, 1) for k, v in Vd.items()},
           "gov": gov, "cf": cf}
    # diaphragme CLT : effort de cisaillement le long des joints de panneaux (vis Ø6 en éclissage, R_d ≈ 1,9 kN par vis)
    nfl = max(1, len(floors))
    vmax = max(Vd["x"] / Ly, Vd["y"] / Lx) / nfl * 1.5                    # kN/m (répartition parabolique ≈ 1,5 × moyenne)
    sc = timber.screw_shear_steel(6, 27, 350)
    rs = max(1.2, sc["R_d"] / 1000 * 0.75)
    sp = max(75, min(300, int(1000 / math.ceil(vmax / rs) // 25 * 25))) if vmax > 0 else 300
    res["diaphragm"] = {"v_kNm": round(vmax, 2), "spline": "LVL 27 × 100", "screw": "Ø6 × 60", "spacing": sp, "R_screw": round(rs, 2)}
    if syst == "walls":
        F_br, F_hd = 30.0, 60.0
        res["walls"] = {}
        for d in ("x", "y"):
            lw = sum(w["L"] for w in walls if w["axis"] != d) or 1.0
            lw = sum(w["L"] for w in walls if (w["axis"] == ("y" if d == "x" else "x"))) or lw
            v = Vd[d] / lw
            nb = math.ceil(Vd[d] / F_br)
            T = Vd[d] * H / 2 / max(lw / 2, 1.0)
            res["walls"][d] = {"v_kNm": round(v, 2), "brackets": nb, "F_br": F_br, "T_holddown": round(T, 1), "F_hd": F_hd,
                               "holddowns": 2 * math.ceil(T / F_hd)}
    elif m.cores:
        res["bracing"] = "cores"
        issues.append({"code": "LAT-CORE", "level": WARN, "message": t(
            f"Contreventement par les noyaux BA : effort horizontal de calcul {num(Vd['x'], 0)} kN (X) / {num(Vd['y'], 0)} kN (Y) à reprendre par les voiles (étude BA du noyau à faire).",
            f"Contraventamento pelos núcleos BA: esforço horizontal {num(Vd['x'], 0)} kN (X) / {num(Vd['y'], 0)} kN (Y) a resistir pelas paredes (estudo BA do núcleo a fazer).",
            f"Bracing by RC cores: design lateral force {num(Vd['x'], 0)} kN (X) / {num(Vd['y'], 0)} kN (Y) to be resisted by the core walls (core design to be done).",
            f"Стійкість забезпечують з/б ядра: розрахункове горизонтальне зусилля {num(Vd['x'], 0)} кН (X) / {num(Vd['y'], 0)} кН (Y) (розрахунок ядра виконати окремо)."),
            "fix": ""})
    else:
        # palées en croix de Saint-André (tirants acier S355, tension seule), 2 par façade et par direction, à chaque étage
        brs = {}
        for d, Lb in (("x", m.gx), ("y", m.gy)):
            bay = max(Lb[k + 1] - Lb[k] for k in range(len(Lb) - 1))
            hs = max(l.height for l in m.levels)
            th = math.atan2(hs, bay)
            N = Vd[d] / 4 / math.cos(th)
            dia = math.sqrt(4 * N * 1000 / (math.pi * 355 / 1.0 * 0.9)) / 0.85
            dmm = next((x for x in (16, 20, 24, 27, 30, 36, 42, 48, 56) if x >= dia), 64)
            brs[d] = {"N": round(N, 1), "rod": f"M{dmm}", "n": 4, "angle": round(math.degrees(th), 1)}
        res["bracing"] = "steel_x"
        res["braces"] = brs
    return res


# ============================================================ assemblages
def _connections(m: Frame, floors: list, cols: list, issues: list) -> dict:
    hangers = []
    for f in floors:
        for bm in f["beams"]:
            for key in ("R0", "R1"):
                Ru = 1.35 * bm[key]["g"] + 1.5 * bm[key]["q"]
                hg = hanger(bm, Ru, 0.8)
                hangers.append(dict(hg, beam=bm["id"], end=key, level=f["tag"]))
    # regroupement en types (H1, H2…) par nombre de vis
    types = {}
    for h in hangers:
        types.setdefault((h["screws"], h["plate"]), []).append(h)
    htypes = []
    for k, ((ns, pl), lst) in enumerate(sorted(types.items()), 1):
        htypes.append({"type": f"H{k}", "screws": ns, "plate": pl, "n": len(lst), "V_max": max(x["V_Ed"] for x in lst),
                       "V_Rd": min(x["V_Rd"] for x in lst), "L": lst[0]["L"]})
        for x in lst:
            x["type"] = f"H{k}"
    bases = []
    for c in cols:
        s0 = c["segs"][0]
        bp = base_plate(s0["b"], s0["h"], s0["NEd"], m.fck)
        bases.append(dict(bp, col=c["name"], NEd=s0["NEd"], b=s0["b"], h=s0["h"]))
    splices = []
    for c in cols:
        for lo, hi in zip(c["segs"], c["segs"][1:]):
            splices.append({"col": c["name"], "level": hi["level"], "N": hi["NEd"], "plate": f"{lo['b']}×{lo['b']}×15 S355",
                            "note": "CLT découpé autour du poteau — appui bois debout / bois debout"})
    fx = []
    for f in floors:
        r = clt_on_beam(f["clt"]["G"], f["loads"]["q"], f["spans"][-1], 0.8)
        fx.append(dict(r, floor=f["tag"]))
    return {"hangers": hangers, "hanger_types": htypes, "bases": bases, "splices": splices, "clt_fix": fx}


# ============================================================ quantités
def quantities(m: Frame, floors, cols, walls, fnd, conns, lat) -> dict:
    clt_m3 = sum(tp["vol"] for f in floors for tp in f["ptypes"])
    clt_m2 = sum(tp["area"] for f in floors for tp in f["ptypes"])
    gl_beams = sum(b["b"] * b["h"] / 1e6 * b["L"] for f in floors for b in f["beams"])
    gl_cols = sum(s["b"] * s["h"] / 1e6 * next(l.height for l in m.levels if l.id == s["level"]) for c in cols for s in c["segs"])
    wall_m2 = sum(s.get("L", w["L"]) * s.get("leaves", 1) * next(l.height for l in m.levels if l.id == s["level"]) for w in walls for s in w["segs"])
    wall_m3 = sum(s.get("L", w["L"]) * s.get("leaves", 1) * next(l.height for l in m.levels if l.id == s["level"]) * s["t"] / 1000
                  for w in walls for s in w["segs"])
    conc = sum(p["B"] ** 2 * p["h"] for p in fnd.get("pads", []))
    conc += sum(s["B"] * s["h"] * s["L"] for s in fnd.get("wall_strips", []))
    gs = fnd["ground_slab"]
    slab_c = gs["area"] * gs["h"] if gs["on_grade"] else 0.0
    pl = fnd["plinth"]
    plinth_c = pl["h"] * pl["t"] * pl["L"]
    exc = sum((p["B"] + 0.4) ** 2 * (fnd.get("depth", 1.0)) for p in fnd.get("pads", [])) + \
          sum((s["B"] + 0.4) * s["L"] * fnd.get("depth", 1.0) for s in fnd.get("wall_strips", []))
    steel_kg = sum(b["t"] * b["B"] * b["B"] * 7.85e-6 for b in conns["bases"]) + len(conns["splices"]) * 25
    n_hang = len(conns["hangers"])
    screws = sum(h["screws"] for h in conns["hangers"])
    spline_m = sum(sum((p["y1"] - p["y0"]) if p["dir"] == "x" else (p["x1"] - p["x0"]) for p in f["panels"]) for f in floors)
    spline_m = sum(sum(p["L"] for p in f["panels"]) for f in floors)
    rebar = conc * 50 + slab_c * 25 + plinth_c * 60
    return {"clt_m3": round(clt_m3, 2), "clt_m2": round(clt_m2, 1), "gl_beams_m3": round(gl_beams, 2), "gl_cols_m3": round(gl_cols, 2),
            "wall_m2": round(wall_m2, 1), "wall_m3": round(wall_m3, 2), "conc_fnd_m3": round(conc, 2), "conc_slab_m3": round(slab_c, 2),
            "conc_plinth_m3": round(plinth_c, 2), "excav_m3": round(exc, 1), "rebar_kg": round(rebar), "steel_kg": round(steel_kg),
            "hangers": n_hang, "hanger_screws": screws, "bases": len(conns["bases"]), "splices": len(conns["splices"]),
            "spline_m": round(spline_m, 1), "slab_area": round(gs["area"], 1),
            "braces": sum(4 * len(m.levels) for _ in (lat.get("braces") or {})), "panels": sum(len(f["panels"]) for f in floors)}


# ============================================================ synthèse des vérifications
def _review(m: Frame, floors, cols, walls, fnd, lat, R) -> list[dict]:
    out = []

    def add(code, ok, txt, u=None):
        out.append({"code": code, "level": "OK" if ok else "NOK", "message": txt, "u": u})
    for f in floors:
        c = f["clt"]
        add("CLT", c["ok"], t(f"Plancher {f['name']} : CLT {c['name']}, taux max {num(c['u_max'])} ({c['governing']})",
                             f"Laje {f['name']}: CLT {c['name']}, taxa máx. {num(c['u_max'])} ({c['governing']})",
                             f"Floor {f['name']}: CLT {c['name']}, max ratio {num(c['u_max'])} ({c['governing']})",
                             f"Перекриття {f['name']}: CLT {c['name']}, макс. коеф. {num(c['u_max'])} ({c['governing']})"), c["u_max"])
        if f["beams"]:
            worst = max(f["beams"], key=lambda b: b["sec"]["u_max"])
            add("GL", all(b["sec"]["ok"] for b in f["beams"]), t(
                f"Poutres {f['name']} : {len(f['beams'])} pièces, taux max {num(worst['sec']['u_max'])} ({worst['id']})",
                f"Vigas {f['name']}: {len(f['beams'])} peças, taxa máx. {num(worst['sec']['u_max'])} ({worst['id']})",
                f"Beams {f['name']}: {len(f['beams'])} members, max ratio {num(worst['sec']['u_max'])} ({worst['id']})",
                f"Балки {f['name']}: {len(f['beams'])} шт., макс. коеф. {num(worst['sec']['u_max'])} ({worst['id']})"), worst["sec"]["u_max"])
    if cols:
        worst = max((s for c in cols for s in c["segs"]), key=lambda s: s["chk"]["u_max"])
        add("COL", all(s["chk"]["ok"] for c in cols for s in c["segs"]), t(
            f"Poteaux : {len(cols)} files, taux max {num(worst['chk']['u_max'])}", f"Pilares: {len(cols)} alinhamentos, taxa máx. {num(worst['chk']['u_max'])}",
            f"Columns: {len(cols)} stacks, max ratio {num(worst['chk']['u_max'])}", f"Колони: {len(cols)} шт., макс. коеф. {num(worst['chk']['u_max'])}"), worst["chk"]["u_max"])
    for w in walls:
        u = max(max(s["u"], s["u_c90"], s["fire"]["u"] if s["fire"] else 0) for s in w["segs"])
        add("WALL", all(s["ok"] for s in w["segs"]), t(f"Mur {w['id']} : taux max {num(u)}", f"Parede {w['id']}: taxa máx. {num(u)}",
                                                      f"Wall {w['id']}: max ratio {num(u)}", f"Стіна {w['id']}: макс. коеф. {num(u)}"), u)
    pads = fnd.get("pads", [])
    if pads:
        add("FND", True, t(f"Semelles : {len(pads)} u, σ ≤ {num(fnd['sigma_kpa'], 0)} kPa", f"Sapatas: {len(pads)} un., σ ≤ {num(fnd['sigma_kpa'], 0)} kPa",
                           f"Pad footings: {len(pads)} no., σ ≤ {num(fnd['sigma_kpa'], 0)} kPa", f"Фундаменти: {len(pads)} шт., σ ≤ {num(fnd['sigma_kpa'], 0)} кПа"))
    add("FIRE", True, t(f"Stabilité au feu R{R} vérifiée élément par élément (EN 1995-1-2)", f"Resistência ao fogo R{R} verificada elemento a elemento (EN 1995-1-2)",
                        f"Fire resistance R{R} checked member by member (EN 1995-1-2)", f"Вогнестійкість R{R} перевірена для кожного елемента (EN 1995-1-2)"))
    return out
