"""Poutres continues — équation des trois moments (Clapeyron) + alternance des charges variables.

Déterministe. Une « file » est une suite de travées alignées, monolithiques sur leurs appuis
intermédiaires (poutres d'un portique béton coulé en place). Appuis de rive : articulés
(moment nul) — l'encastrement partiel de rive est couvert par le minimum constructif
EN 1992-1-1 §9.2.1.2(1) (aciers supérieurs ≥ 0,15·As travée), appliqué par l'appelant.

Pour chaque combinaison (facteurs par action) :
- actions permanentes (kind G) : toutes les travées chargées ;
- actions variables (kind Q) : toutes les alternances de travées chargées/déchargées
  (2^n motifs jusqu'à 10 travées, sinon motifs normalisés : tout, pair, impair, paires adjacentes).

Sorties : enveloppe des moments en travée (positifs), aux appuis (négatifs), effort tranchant
et réactions d'appui. Analyse élastique linéaire, EI constant par travée, sans redistribution.
NON EXÉCUTOIRE — à valider par l'ingénieur.
"""
from __future__ import annotations

import itertools
import math

from engines.structuro_calc import trap_moment

VERSION = "continuous-3moments-0.1.0"
N_SAMPLES = 400          # pas d'intégration et d'échantillonnage par travée (pair pour Simpson)
MAX_ENUM_SPANS = 10


def _free_moment(L: float, loads: dict, x: float) -> float:
    """Moment isostatique (travée sur 2 appuis simples) d'un jeu de charges {udl, points, traps}."""
    w = loads.get("udl", 0.0)
    pts = loads.get("points", [])
    traps = loads.get("traps", [])
    ra = w * L / 2 + sum(p * (L - a) / L for p, a in pts)
    m = ra * x - w * x * x / 2 - sum(p * max(0.0, x - a) for p, a in pts)
    return m + sum(trap_moment(L, W, a, x) for W, a in traps)


def _free_reactions(L: float, loads: dict) -> tuple[float, float]:
    w = loads.get("udl", 0.0)
    pts = loads.get("points", [])
    traps = loads.get("traps", [])
    total = w * L + sum(p for p, _ in pts) + sum(W for W, _ in traps)
    ra = w * L / 2 + sum(p * (L - a) / L for p, a in pts) + sum(W for W, _ in traps) / 2
    return ra, total - ra


def _scale(loads: dict, f: float) -> dict:
    return {"udl": loads.get("udl", 0.0) * f,
            "points": [(p * f, a) for p, a in loads.get("points", [])],
            "traps": [(W * f, a) for W, a in loads.get("traps", [])]}


def _merge(a: dict, b: dict) -> dict:
    return {"udl": a.get("udl", 0.0) + b.get("udl", 0.0),
            "points": list(a.get("points", [])) + list(b.get("points", [])),
            "traps": list(a.get("traps", [])) + list(b.get("traps", []))}


def _load_terms(L: float, loads: dict) -> tuple[float, float]:
    """(6/L)∫M0·x dx et (6/L)∫M0·(L−x) dx — termes de charge de Clapeyron (Simpson)."""
    n = N_SAMPLES
    h = L / n
    s_left = s_right = 0.0
    for i in range(n + 1):
        x = i * h
        m0 = _free_moment(L, loads, x)
        c = 1 if i in (0, n) else (4 if i % 2 else 2)
        s_left += c * m0 * x
        s_right += c * m0 * (L - x)
    s_left *= h / 3
    s_right *= h / 3
    return 6 * s_left / L, 6 * s_right / L


def _solve_tridiagonal(a: list[float], b: list[float], c: list[float], d: list[float]) -> list[float]:
    n = len(d)
    if n == 0:
        return []
    cp, dp = [0.0] * n, [0.0] * n
    cp[0], dp[0] = c[0] / b[0], d[0] / b[0]
    for i in range(1, n):
        den = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / den if i < n - 1 else 0.0
        dp[i] = (d[i] - a[i] * dp[i - 1]) / den
    x = [0.0] * n
    x[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x


def solve(spans: list[dict]) -> dict:
    """Une file sous UN chargement. spans : [{L, EI (optionnel), loads:{udl,points,traps}}].

    Renvoie les moments d'appuis (négatifs = chapeaux), le moment max positif par travée,
    l'effort tranchant max par travée et les réactions d'appui.
    """
    n = len(spans)
    if n == 0:
        raise ValueError("File vide")
    Ls = [float(s["L"]) for s in spans]
    if any(not math.isfinite(L) or L <= 0 for L in Ls):
        raise ValueError("Portée invalide")
    eis = [float(s.get("EI") or 1.0) for s in spans]
    flex = [L / ei for L, ei in zip(Ls, eis)]               # L/EI
    terms = [_load_terms(L, s["loads"]) for L, s in zip(Ls, spans)]
    # Inconnues : moments des appuis intérieurs 1..n-1 (appuis 0 et n articulés).
    a, b, c, d = [], [], [], []
    for i in range(1, n):
        a.append(flex[i - 1])
        b.append(2 * (flex[i - 1] + flex[i]))
        c.append(flex[i])
        d.append(-(terms[i - 1][0] / eis[i - 1] + terms[i][1] / eis[i]))
    inner = _solve_tridiagonal(a, b, c, d) if n > 1 else []
    M = [0.0] + inner + [0.0]
    span_out, reactions = [], [0.0] * (n + 1)
    for i, (L, s) in enumerate(zip(Ls, spans)):
        ml, mr = M[i], M[i + 1]
        best_pos, best_x = 0.0, 0.0
        for k in range(N_SAMPLES + 1):
            x = L * k / N_SAMPLES
            m = _free_moment(L, s["loads"], x) + ml * (1 - x / L) + mr * x / L
            if m > best_pos:
                best_pos, best_x = m, x
        ra0, rb0 = _free_reactions(L, s["loads"])
        dv = (mr - ml) / L
        v_left, v_right = ra0 + dv, rb0 - dv               # réactions de la travée sur ses appuis
        reactions[i] += v_left
        reactions[i + 1] += v_right
        span_out.append({"m_span_max_knm": best_pos, "x_m": best_x,
                         "v_max_kn": max(abs(v_left), abs(v_right)),
                         "r_left_kn": v_left, "r_right_kn": v_right})
    return {"support_moments_knm": M, "spans": span_out, "reactions_kn": reactions}


def _patterns(n: int) -> list[tuple[bool, ...]]:
    if n <= MAX_ENUM_SPANS:
        return list(itertools.product((True, False), repeat=n))
    pats = {tuple([True] * n), tuple(i % 2 == 0 for i in range(n)), tuple(i % 2 == 1 for i in range(n))}
    for j in range(n - 1):   # deux travées adjacentes chargées puis une sur deux de part et d'autre
        pats.add(tuple((i in (j, j + 1)) or (i > j + 1 and (i - j) % 2 == 1) or (i < j and (j - i) % 2 == 0)
                       for i in range(n)))
    return sorted(pats)


def _span_tables(L: float, loads: dict) -> dict:
    """Pré-calculs linéaires d'une travée pour un jeu de charges : M0(x), termes de Clapeyron, réactions."""
    xs = [L * k / N_SAMPLES for k in range(N_SAMPLES + 1)]
    return {"m0": [_free_moment(L, loads, x) for x in xs], "terms": _load_terms(L, loads),
            "react": _free_reactions(L, loads)}


def envelope(spans: list[dict], combos: list[dict], action_kinds: dict[str, str]) -> dict:
    """Enveloppe sur des combinaisons et l'alternance des actions variables.

    spans : [{id, L, EI, actions: {action_id: {udl, points, traps}}}]
    combos : [{id, label, factors: {action_id: facteur}}]
    action_kinds : {action_id: "G"|"Q"}
    Tout est linéaire : M0, termes de charge et réactions sont pré-calculés par travée et
    par famille (G, Q), puis combinés par motif — 2^n motifs restent rapides.
    """
    n = len(spans)
    Ls = [float(s["L"]) for s in spans]
    eis = [float(s.get("EI") or 1.0) for s in spans]
    flex = [L / ei for L, ei in zip(Ls, eis)]
    out_spans = [{"id": s.get("id"), "L_m": s["L"], "m_pos_knm": 0.0, "m_pos_case": None,
                  "v_max_kn": 0.0, "v_case": None} for s in spans]
    out_sup = [{"m_neg_knm": 0.0, "m_neg_case": None, "r_max_kn": 0.0, "r_case": None,
                "r_iso_kn": 0.0} for _ in range(n + 1)]
    xs = [[L * k / N_SAMPLES for k in range(N_SAMPLES + 1)] for L in Ls]
    for combo in combos:
        factors = combo["factors"]
        label = combo.get("label", combo["id"])
        perm = {a: f for a, f in factors.items() if action_kinds.get(a) == "G" and f}
        var = {a: f for a, f in factors.items() if action_kinds.get(a) != "G" and f}
        tg, tq = [], []
        for i, s in enumerate(spans):
            g = {"udl": 0.0, "points": [], "traps": []}
            for a, f in perm.items():
                g = _merge(g, _scale(s["actions"].get(a, {}), f))
            q = {"udl": 0.0, "points": [], "traps": []}
            for a, f in var.items():
                q = _merge(q, _scale(s["actions"].get(a, {}), f))
            tg.append(_span_tables(Ls[i], g))
            tq.append(_span_tables(Ls[i], q))
        # Réactions isostatiques toutes travées chargées (référence de la descente de charges).
        iso = [0.0] * (n + 1)
        for i in range(n):
            iso[i] += tg[i]["react"][0] + tq[i]["react"][0]
            iso[i + 1] += tg[i]["react"][1] + tq[i]["react"][1]
        for k in range(n + 1):
            out_sup[k]["r_iso_kn"] = max(out_sup[k]["r_iso_kn"], iso[k])
        pats = _patterns(n) if var else [tuple([False] * n)]
        for pat in pats:
            on = [1.0 if pat[i] else 0.0 for i in range(n)]
            a_, b_, c_, d_ = [], [], [], []
            for i in range(1, n):
                tl = tg[i - 1]["terms"][0] + on[i - 1] * tq[i - 1]["terms"][0]
                tr = tg[i]["terms"][1] + on[i] * tq[i]["terms"][1]
                a_.append(flex[i - 1])
                b_.append(2 * (flex[i - 1] + flex[i]))
                c_.append(flex[i])
                d_.append(-(tl / eis[i - 1] + tr / eis[i]))
            M = [0.0] + (_solve_tridiagonal(a_, b_, c_, d_) if n > 1 else []) + [0.0]
            reactions = [0.0] * (n + 1)
            for i in range(n):
                L, ml, mr = Ls[i], M[i], M[i + 1]
                m0g, m0q, f = tg[i]["m0"], tq[i]["m0"], on[i]
                best = 0.0
                for k, x in enumerate(xs[i]):
                    m = m0g[k] + f * m0q[k] + ml * (1 - x / L) + mr * x / L
                    if m > best:
                        best = m
                dv = (mr - ml) / L
                v_left = tg[i]["react"][0] + f * tq[i]["react"][0] + dv
                v_right = tg[i]["react"][1] + f * tq[i]["react"][1] - dv
                reactions[i] += v_left
                reactions[i + 1] += v_right
                if best > out_spans[i]["m_pos_knm"]:
                    out_spans[i]["m_pos_knm"], out_spans[i]["m_pos_case"] = best, label
                v = max(abs(v_left), abs(v_right))
                if v > out_spans[i]["v_max_kn"]:
                    out_spans[i]["v_max_kn"], out_spans[i]["v_case"] = v, label
            for k, m in enumerate(M):
                if m < out_sup[k]["m_neg_knm"]:
                    out_sup[k]["m_neg_knm"], out_sup[k]["m_neg_case"] = m, label
            for k, r in enumerate(reactions):
                if r > out_sup[k]["r_max_kn"]:
                    out_sup[k]["r_max_kn"], out_sup[k]["r_case"] = r, label
    for k in range(n + 1):
        # Majoration de descente de charges due à la continuité (jamais une minoration).
        out_sup[k]["continuity_delta_kn"] = max(0.0, out_sup[k]["r_max_kn"] - out_sup[k]["r_iso_kn"])
    return {"version": VERSION, "spans": out_spans, "supports": out_sup,
            "method": "Équation des trois moments (Clapeyron), EI par travée, appuis de rive articulés ; "
                      "actions G sur toutes les travées, actions Q alternées (enveloppe).",
            "execution_ready": False}


def combined_loads(span: dict, factors: dict) -> dict:
    """Charges d'une travée sous une combinaison (toutes actions, sans alternance)."""
    out = {"udl": 0.0, "points": [], "traps": []}
    for a, f in factors.items():
        if f:
            out = _merge(out, _scale(span["actions"].get(a, {}), f))
    return out


def beam_actions(model: dict, result: dict, beam_id: str) -> dict:
    """Charges reçues par une poutre, par action, reconstruites depuis les cas unitaires du moteur
    gravitaire (cas = une action à facteur 1) : poids propre, charges propres et transferts reçus."""
    el = next(e for e in model["elements"] if e["id"] == beam_id)
    L = float(el["length_m"])
    out: dict[str, dict] = {}
    action_ids = [a["id"] for a in model.get("actions", [])]
    sw = model.get("self_weight_action")
    for a in action_ids:
        loads = {"udl": 0.0, "points": [], "traps": []}
        if a == sw:
            loads["udl"] += el["length_m"] * el["width_m"] * el["height_m"] * el["density_kn_m3"] / L
        for ld in el.get("loads", []):
            if ld["action"] != a:
                continue
            if ld["mode"] == "point":
                loads["points"].append((ld["value"], ld["position_m"]))
            elif ld["mode"] == "line":
                loads["udl"] += ld["value"]
        case = next((c for c in result.get("cases", []) if c["id"] == a), None)
        for t in (case or {}).get("transfers", []):
            if t["to"] != beam_id:
                continue
            if t.get("shape"):
                loads["traps"].append((t["force_kn"], t["ramp_m"]))
            elif t["receiving"] == "point":
                loads["points"].append((t["force_kn"], t["position_m"]))
            else:
                loads["udl"] += t["force_kn"] / L
        out[a] = loads
    return out
