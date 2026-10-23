"""Mapa de medições (elemento a elemento), orçamento estimativo por artigos e quadro de quantidades (paredes, sapatas, lajes, vãos).

Betão em volume teórico ; cofragem pela área de contacto ; aço por taxas médias de pré-dimensionamento por tipo de elemento
(kg/m³) — a substituir pelas listas de armaduras do projeto de execução. Restantes especialidades por rácios €/m² (± 20 %).
"""
from __future__ import annotations

import math

import numpy as np

from . import estrutura as ES
from . import grelha, perfis
from .modelo import Spec
from .textos import fmt as f

KG = {"sapata": 75, "ensoleiramento": 90, "sapata_corrida": 60, "lintel": 110, "muro": 95, "pilar": 170, "parede": 110, "nucleo": 120,
      "laje": 85, "laje_g": 90, "varanda": 95, "viga": 150, "escada": 100}


def _ba(S, vol, cof, aco):
    P = S.prices
    return vol * P["concrete"] + aco * P["steel"] + cof * P["formwork"]


def _footprint_overlap(S: Spec) -> float:
    """Área da cave fora da projeção do edifício (m²)."""
    if not S.basement or not S.bpoly:
        return 0.0
    xs = [p[0] for p in S.bpoly]
    ys = [p[1] for p in S.bpoly]
    st = 0.05
    X, Y = np.meshgrid(np.arange(min(xs) + st / 2, max(xs), st), np.arange(min(ys) + st / 2, max(ys), st), indexing="ij")
    inp = grelha._in_poly_grid(X, Y, S.bpoly)
    out = inp & ~((X >= 0) & (X <= S.L) & (Y >= 0) & (Y <= S.B))
    return float(out.sum()) * st * st


def slab_levels(S: Spec) -> list[int]:
    """Níveis com laje suspensa do edifício (inclui a cobertura = n)."""
    return list(range(0 if S.basement else 1, S.n + 1))


def medir(S: Spec, R: dict) -> dict:
    L = []
    T = S.t

    def add(cap, art, el, dims, n, q, un, vol=0.0, cof=0.0, kg=0.0):
        L.append({"cap": cap, "art": art, "el": el, "dims": dims, "n": n, "q": round(q, 2), "un": un, "vol": round(vol, 3), "cof": round(cof, 2),
                  "aco": round(vol * kg, 1)})
    A_cave = S.basement_area()
    A_out = _footprint_overlap(S)
    bw = R["bwalls"]
    # 1. movimento de terras
    if S.basement:
        Lw = sum(w["L"] for w in bw) or 1.0
        depth = sum(w["L"] * w["ht"] for w in bw) / Lw + 0.30
        depth = max(depth, 1.0)
        add("1", "1.1", T("Escavação geral da cave", "Terrassement général du sous-sol"), f"{f(A_cave, 1)} m² × {f(depth)} m", 1, A_cave * depth, "m³")
        add("1", "1.2", T("Transporte a vazadouro (empolamento 25 %)", "Évacuation des terres (foisonnement 25 %)"), "1.1 × 1,25", 1, A_cave * depth * 1.25, "m³")
    afund = sum((x["x1"] - x["x0"]) * (x["y1"] - x["y0"]) for x in R["foots"]) + sum(x["L"] * x["B"] for x in R["fnd"]) + sum(w["L"] * 1.0 for w in bw)
    add("1", "1.3", T("Escavação para fundações", "Fouilles en rigole et en puits"), T("área × 1,00 m", "surface × 1,00 m"), 1, afund, "m³")
    # 2. fundações
    for x in R["foots"]:
        B_, L_, h = x["x1"] - x["x0"], x["y1"] - x["y0"], x["h"]
        v = B_ * L_ * h
        add("2", "2.1", T(f"Sapata S{x['id'].lstrip('P')} (pilar {x['id']})", f"Semelle S{x['id'].lstrip('P')} (poteau {x['id']})"),
            f"{f(B_)} × {f(L_)} × {f(h)}", 1, v, "m³", v, 2 * (B_ + L_) * h, KG["sapata"])
    for x in R["fnd"]:
        v = x["L"] * x["B"] * x["h"]
        add("2", "2.2", T(f"Ensoleiramento {x['id']} ({', '.join(x['members'])})", f"Radier {x['id']} ({', '.join(x['members'])})"),
            f"{f(x['L'])} × {f(x['B'])} × {f(x['h'])}", 1, v, "m³", v, 2 * (x["L"] + x["B"]) * x["h"], KG["ensoleiramento"])
    for w in bw:
        v = w["L"] * 1.0 * 0.40
        add("2", "2.3", T(f"Sapata contínua sob {w['name']}", f"Semelle filante sous {w['name']}"), f"{f(w['L'])} × 1,00 × 0,40", 1, v, "m³", v,
            2 * w["L"] * 0.40, KG["sapata_corrida"])
    add("2", "2.4", T("Betão de limpeza (e = 0,10)", "Béton de propreté (e = 0,10)"), T("área das fundações", "surface des fondations"), 1, afund, "m²")
    centers = [((x["x0"] + x["x1"]) / 2, (x["y0"] + x["y1"]) / 2) for x in R["foots"]] + [((x["x0"] + x["x1"]) / 2, (x["y0"] + x["y1"]) / 2) for x in R["fnd"]]
    lint = 0.0
    for i, c in enumerate(centers[:len(R["foots"])]):
        ds = [math.dist(c, o) for j, o in enumerate(centers) if j != i]
        if ds:
            lint += min(min(ds), 8.0)
    if lint:
        add("2", "2.5", T("Lintéis de travamento 0,30 × 0,50 entre sapatas", "Longrines 0,30 × 0,50 entre semelles"), f"{f(lint, 1)} m", 1,
            lint * 0.15, "m³", lint * 0.15, lint * 2 * 0.5, KG["lintel"])
    # 3. muros de cave
    for w in bw:
        v = w["L"] * w["t"] * S.H
        add("3", "3.1", T(f"Muro {w['name']}", f"Voile {w['name']}"), f"{f(w['L'])} × {f(S.H)} × {f(w['t'])}", 1, v, "m³", v, 2 * w["L"] * S.H, KG["muro"])
    # 4. pilares, paredes e núcleos
    st = ES.storeys(S)
    for c in R["cols"]:
        grp = c["groups"]
        for k, (tag, j0) in enumerate(grp):
            j1 = grp[k + 1][1] if k + 1 < len(grp) else (st[0] + 1 if c["garage"] else S.n)
            ns = j1 - j0
            s = c[tag]
            v = s["b"] * s["h"] * S.H * ns
            lv = f"{S.lname(j0)} → {S.lname(j1 - 1)}" if ns > 1 else S.lname(j0)
            add("4", "4.1", T(f"Pilar {c['id']} — {lv}", f"Poteau {c['id']} — {lv}"), f"{int(round(s['b'] * 100))}×{int(round(s['h'] * 100))} × {ns} × {f(S.H)}",
                ns, v, "m³", v, 2 * (s["b"] + s["h"]) * S.H * ns, KG["pilar"])
    ns = len(st)
    for w in S.walls:
        v = w["Lw"] * w["t"] * S.H * ns
        add("4", "4.2", T(f"Parede resistente {w['id']}", f"Voile de contreventement {w['id']}"), f"{f(w['Lw'])} × {f(w['t'])} × {ns} × {f(S.H)}",
            ns, v, "m³", v, 2 * w["Lw"] * S.H * ns, KG["parede"])
    for c in S.cores:
        cs = ES.core_section(c)
        v = cs["A"] * S.H * ns
        per = sum((p[2] - p[0]) + (p[3] - p[1]) for p in cs["parts"])
        nm = T("Núcleo de escada", "Noyau d'escalier") if c["kind"] == "stair" else T("Núcleo do elevador", "Noyau d'ascenseur")
        add("4", "4.3", f"{nm} {c['id']} (e = {f(c['t'])})", f"A = {f(cs['A'])} m² × {ns} × {f(S.H)}", ns, v, "m³", v, per * S.H * ns, KG["nucleo"])
    # 5. lajes, vigas, varandas, escadas
    holes = sum((c["box"][2] - c["box"][0]) * (c["box"][3] - c["box"][1]) for c in S.cores)
    a_slab = S.area_floor - holes
    for k in slab_levels(S):
        add("5", "5.1", T(f"Laje maciça h = {f(S.slab_h)} — {S.lname(k)}", f"Dalle pleine h = {f(S.slab_h)} — {S.lname(k)}"),
            f"{f(S.L)} × {f(S.B)} − {f(holes, 1)} m²", 1, a_slab, "m²", a_slab * S.slab_h, a_slab, KG["laje"])
    if A_out > 0.5:
        add("5", "5.2", T(f"Laje sobre a cave fora do edifício h = {f(S.slab_hg)}", f"Dalle sur sous-sol hors bâtiment h = {f(S.slab_hg)}"),
            f"{f(A_out, 1)} m²", 1, A_out, "m²", A_out * S.slab_hg, A_out, KG["laje_g"])
    ab = S.balcony_area()
    if ab:
        for k in range(1, S.n + 1):
            add("5", "5.3", T(f"Varandas em consola — {S.lname(k)}", f"Balcons en console — {S.lname(k)}"), f"{f(ab, 1)} m² × 0,175 ({T('méd.', 'moy.')})", 1, ab,
                "m²", ab * 0.175, ab * 1.15, KG["varanda"])
    nb = len(slab_levels(S))
    for b in R["beams"]:
        v = b["L"] * b["b_w"] * (b["h"] - S.slab_h) * nb
        add("5", "5.4", T(f"Viga {b['name']} ({int(b['b_w'] * 100)}×{int(b['h'] * 100)})", f"Poutre {b['name']} ({int(b['b_w'] * 100)}×{int(b['h'] * 100)})"),
            f"{f(b['L'])} × {f(b['b_w'])} × {f(b['h'] - S.slab_h)} × {nb}", nb, v, "m³", v, (b["b_w"] + 2 * (b["h"] - S.slab_h)) * b["L"] * nb, KG["viga"])
    n_st = sum(1 for c in S.cores if c["kind"] == "stair")
    if n_st:
        v = n_st * ns * 2 * 1.20 * (S.H * 1.2) * 0.18
        add("5", "5.5", T(f"Lanços de escada BA ({n_st * ns} lanços duplos, largura 1,20)", f"Volées d'escalier BA ({n_st * ns} volées doubles, largeur 1,20)"),
            f"{n_st * ns} × 2 × 1,20 × {f(S.H * 1.2)} × 0,18", n_st * ns * 2, v, "m³", v, v * 6, KG["escada"])
    A_gr = A_cave if S.basement else S.area_floor
    add("5", "5.6", T("Pavimento térreo e = 0,15 com malha, sobre tout-venant", "Dallage e = 0,15 armé sur grave compactée"), f"{f(A_gr, 1)} m²", 1, A_gr, "m²")
    # 6. impermeabilização e drenagem
    Lb = sum(w["L"] for w in bw if w["ht"] > 0)
    if Lb:
        add("6", "6.1", T("Impermeabilização dos muros enterrados + membrana drenante", "Étanchéité des voiles enterrés + nappe drainante"), f"{f(Lb, 1)} m", 1, Lb, "ml")
        add("6", "6.2", T("Dreno periférico Ø160 em vala drenante com geotêxtil", "Drain périphérique Ø160 en tranchée drainante avec géotextile"), f"{f(Lb, 1)} m", 1, Lb, "ml")
    if A_out > 0.5:
        add("6", "6.3", T("Impermeabilização da laje enterrada (terraços / jardins)", "Étanchéité de la dalle enterrée (terrasses / jardins)"), f"{f(A_out, 1)} m²", 1, A_out, "m²")
    areas = {"piso": S.area_floor, "acima_solo": S.n * S.area_floor, "cave": A_cave, "bruta": S.n * S.area_floor + A_cave,
             "varandas_piso": ab, "fora_edificio": A_out, "util": sum(sum(float(r.get("area") or 0) for r in u.get("rooms") or []) for u in S.units)}
    tot = {"betao": sum(x["vol"] for x in L), "aco": sum(x["aco"] for x in L), "cofragem": sum(x["cof"] for x in L)}
    return {"lines": L, "areas": areas, "totais": tot, "quant": quantidades(S, R, L)}


CAPS = {"1": ("Movimento de terras", "Terrassements"), "2": ("Fundações", "Fondations"), "3": ("Muros de cave", "Voiles enterrés"),
        "4": ("Pilares, paredes e núcleos", "Poteaux, voiles et noyaux"), "5": ("Lajes, vigas, varandas e escadas", "Dalles, poutres, balcons et escaliers"),
        "6": ("Impermeabilização e drenagem", "Étanchéité et drainage")}
ART = {   # art : (designação PT, designação FR, unidade, chave de preço unitário ou None = betão armado composto)
    "1.1": ("Escavação geral em terreno de qualquer natureza, incluindo entivação corrente", "Terrassement en pleine masse, tous terrains, blindage courant", "m³", "excavation"),
    "1.2": ("Carga, transporte e deposição a vazadouro licenciado", "Chargement, transport et mise en décharge agréée", "m³", "transport"),
    "1.3": ("Escavação localizada para fundações, regularização e compactação do fundo", "Fouilles pour fondations, réglage et compactage du fond", "m³", "excavation_fnd"),
    "2.1": ("Sapatas isoladas em betão armado, incluindo cofragem", "Semelles isolées en béton armé, coffrage compris", "m³", None),
    "2.2": ("Ensoleiramentos sob núcleos e paredes em betão armado", "Radiers sous noyaux et voiles en béton armé", "m³", None),
    "2.3": ("Sapatas contínuas sob muros de cave em betão armado", "Semelles filantes sous voiles enterrés en béton armé", "m³", None),
    "2.4": ("Betão de limpeza com 0,10 m de espessura", "Béton de propreté de 0,10 m", "m²", "blinding"),
    "2.5": ("Lintéis de travamento de fundações em betão armado", "Longrines de liaison en béton armé", "m³", None),
    "3.1": ("Muros de cave em betão armado, cofragem nas duas faces", "Voiles enterrés en béton armé, coffrage deux faces", "m³", None),
    "4.1": ("Pilares em betão armado, cofragem lisa", "Poteaux en béton armé, coffrage lisse", "m³", None),
    "4.2": ("Paredes resistentes em betão armado (ductilidade)", "Voiles de contreventement en béton armé", "m³", None),
    "4.3": ("Paredes dos núcleos de escada e elevador em betão armado", "Voiles des noyaux d'escalier et d'ascenseur en béton armé", "m³", None),
    "5.1": ("Lajes maciças em betão armado, cofragem e escoramento", "Dalles pleines en béton armé, coffrage et étaiement", "m²", None),
    "5.2": ("Laje sobre a cave exterior em betão armado", "Dalle sur sous-sol extérieur en béton armé", "m²", None),
    "5.3": ("Varandas em consola em betão armado, rotura térmica", "Balcons en console en béton armé, rupteurs thermiques", "m²", None),
    "5.4": ("Vigas em betão armado (abaixo da laje), cofragem e escoramento", "Poutres en béton armé (retombées), coffrage et étaiement", "m³", None),
    "5.5": ("Lanços e patamares de escada em betão armado", "Volées et paliers d'escalier en béton armé", "m³", None),
    "5.6": ("Pavimento térreo com malha electrossoldada sobre tout-venant", "Dallage armé sur grave compactée", "m²", "ground_slab_m2"),
    "6.1": ("Impermeabilização de muros enterrados com membrana drenante", "Étanchéité de voiles enterrés avec nappe drainante", "ml", "waterproof_wall"),
    "6.2": ("Dreno perimetral Ø160 com brita e geotêxtil, ligado à rede pluvial", "Drain périphérique Ø160 avec graviers et géotextile", "ml", "drain"),
    "6.3": ("Impermeabilização de laje enterrada com proteção mecânica", "Étanchéité de dalle enterrée avec protection lourde", "m²", "waterproof_slab"),
}


def orcamento(S: Spec, R: dict, Q: dict) -> dict:
    P = dict(S.prices, ground_slab_m2=S.prices["ground_slab"] * 0.15)
    arts = {}
    for l_ in Q["lines"]:
        a = arts.setdefault(l_["art"], {"cap": l_["cap"], "q": 0.0, "vol": 0.0, "cof": 0.0, "aco": 0.0})
        for k in ("q", "vol", "cof", "aco"):
            a[k] += l_[k]
    out = []
    for k, a in arts.items():
        pt, fr, un, key = ART[k]
        total = _ba(S, a["vol"], a["cof"], a["aco"]) if key is None else a["q"] * P[key]
        out.append({"art": k, "cap": a["cap"], "desc": S.t(pt, fr), "un": un, "q": round(a["q"], 2), "pu": round(total / a["q"], 2) if a["q"] else 0.0,
                    "total": round(total, 0), "vol": round(a["vol"], 1), "aco": round(a["aco"], 0), "cof": round(a["cof"], 0)})
    lift = sum(1 for c in S.cores if c["kind"] == "lift")
    roof = S.area_floor + S.balcony_area()
    par = []
    for cap, pt, fr, ppt, pfr, base in perfis.PARAM:
        pu = pfr if S.country == "FR" else ppt
        q, un = {"a": (Q["areas"]["acima_solo"], "m²"), "roof": (roof, "m²"), "u": (1, "vg"), "lift": (lift, "un"),
                 "cave": (Q["areas"]["cave"], "m²")}[base]
        if q <= 0:
            continue
        par.append({"cap": cap, "desc": S.t(pt, fr), "un": un, "q": round(q, 1), "pu": pu, "total": round(q * pu, 0)})
    tot_s = sum(a["total"] for a in out)
    tot_p = sum(p["total"] for p in par)
    est = round(0.03 * (tot_s + tot_p), 0)
    sub = tot_s + tot_p + est
    vat = round(sub * S.prof["vat"], 0)
    return {"arts": out, "par": par, "tot_s": tot_s, "tot_p": tot_p, "estaleiro": est, "sub": sub, "vat": vat,
            "m2": sub / max(Q["areas"]["bruta"], 1.0), "per_unit": sub / max(len(S.units), 1)}


# ------------------------------------------------------------------ quadro de quantidades (paredes, vãos)
def quantidades(S: Spec, R: dict, lines: list[dict]) -> dict:
    per = 2 * (S.L + S.B)
    conc_fac = 0.0
    for w in S.walls:
        on = (w["axis"] == "Y" and (abs(w["x0"]) < 0.05 or abs(w["x0"] - S.L) < 0.05)) or \
             (w["axis"] == "X" and (abs(w["y0"]) < 0.05 or abs(w["y0"] - S.B) < 0.05))
        if on:
            conc_fac += w["Lw"]
    ot = S.opening_types
    vaos = {}
    rows = []
    for k in range(S.n):
        a_v = 0.0
        n_v = 0
        for u in [u for u in S.units if int(u.get("level", -1)) == k]:
            for o in u.get("openings") or []:
                d = ot.get(o["type"]) or {}
                n = int(o.get("count") or 1)
                a_v += n * float(d.get("width") or 0) * float(d.get("height") or 0)
                n_v += n
                v = vaos.setdefault(o["type"], {"n": 0, "by_level": {}, "by_facade": {}})
                v["n"] += n
                v["by_level"][k] = v["by_level"].get(k, 0) + n
                v["by_facade"][o.get("facade")] = v["by_facade"].get(o.get("facade"), 0) + n
        for o in S.raw.get("common_openings") or []:
            if int(o.get("level", -1)) == k:
                d = ot.get(o["type"]) or {}
                n = int(o.get("count") or 1)
                a_v += n * float(d.get("width") or 0) * float(d.get("height") or 0)
                n_v += n
                v = vaos.setdefault(o["type"], {"n": 0, "by_level": {}, "by_facade": {}})
                v["n"] += n
                v["by_level"][k] = v["by_level"].get(k, 0) + n
                v["by_facade"][o.get("facade")] = v["by_facade"].get(o.get("facade"), 0) + n
        iw = S.interior

        def lv(key, default):
            v = iw.get(key)
            if isinstance(v, list):
                return float(v[k]) if k < len(v) else float(v[-1])
            return float(v) if v is not None else default
        a_units = sum(sum(float(r.get("area") or 0) for r in u.get("rooms") or []) for u in S.units if int(u.get("level", -1)) == k)
        n_units = sum(1 for u in S.units if int(u.get("level", -1)) == k)
        core_per = sum(2 * ((c["box"][2] - c["box"][0]) + (c["box"][3] - c["box"][1])) for c in S.cores)
        rows.append({"k": k, "piso": S.lname(k), "L_fach": per, "h": S.H, "a_vaos": a_v, "n_vaos": n_v, "L_bet": conc_fac,
                     "div": lv("partitions", round(0.34 * a_units, 1)), "sep": lv("separating", round(max(n_units - 1, 0) * 6.5, 1)),
                     "enu": lv("common", round(core_per * 0.75 + max(n_units, 1) * 1.5, 1))})
    return {"paredes": rows, "vaos": vaos, "clear_h": S.clear_h,
            "estimado": not S.interior}
