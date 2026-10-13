"""Chaînes de cotes périphériques (haut / bas / gauche / droite) : somme des partielles vs total, et comparaison
membre à membre des chaînes opposées → incohérences chiffrées (mm). Travaille sur les cotes vectorielles en points PDF."""
from __future__ import annotations

LINE_TOL_M = 0.004   # même ligne de cote
JOIN_TOL_M = 0.012   # extrémités jointives
OK_MM, WARN_MM = 10.5, 20.5


def _status(mm: float) -> str:
    return "ok" if mm <= OK_MM else "warn" if mm <= WARN_MM else "ko"


def _lines(cotes: list[dict], orient: str, ppm: float) -> list[dict]:
    """Regroupe les cotes d'une orientation par ligne de cote (position perpendiculaire)."""
    along, perp = (0, 1) if orient == "h" else (1, 0)
    cs = sorted((c for c in cotes if c["orientation"] == orient and c.get("value_m") is not None), key=lambda c: c["p1"][perp])
    groups: list[dict] = []
    for c in cs:
        pos = c["p1"][perp]
        if groups and abs(pos - groups[-1]["pos"]) <= LINE_TOL_M * ppm:
            groups[-1]["cotes"].append(c)
        else:
            groups.append({"pos": pos, "cotes": [c]})
    out = []
    for g in groups:
        items = sorted(g["cotes"], key=lambda c: c["p1"][along])
        a, b = min(c["p1"][along] for c in items), max(c["p2"][along] for c in items)
        out.append({"pos": g["pos"], "a": a, "b": b, "cotes": items, "along": along})
    return out


def _chain_of(line: dict, ppm: float, all_cotes: list[dict], orient: str) -> dict | None:
    """Une ligne = chaîne si ses cotes sont jointives (≥ 2 partielles). Le total est la cote de même orientation (sur cette
    ligne ou une ligne voisine ≤ 2 m) dont les deux extrémités coïncident avec celles de la chaîne (± 12 mm) ; à défaut,
    une cote englobante est signalée comme « référence non couverte » (chaîne partielle, ex. chaîne d'axes)."""
    along, perp = line["along"], 1 - line["along"]
    items = line["cotes"]
    span = line["b"] - line["a"]
    totals = [c for c in items if c["p2"][along] - c["p1"][along] >= 0.9 * span and len(items) > 1]
    partials = [c for c in items if c not in totals]
    partials.sort(key=lambda c: c["p1"][along])
    if len(partials) < 2:
        return None
    joined = all(abs(n["p1"][along] - p["p2"][along]) <= JOIN_TOL_M * ppm for p, n in zip(partials, partials[1:]))
    if not joined:
        return None
    a, b = partials[0]["p1"][along], partials[-1]["p2"][along]
    exact, enclosing = None, None
    for c in all_cotes:
        if c["orientation"] != orient or c.get("value_m") is None or c in partials or abs(c["p1"][perp] - line["pos"]) > 2.0 * ppm:
            continue
        if abs(c["p1"][along] - a) <= JOIN_TOL_M * ppm and abs(c["p2"][along] - b) <= JOIN_TOL_M * ppm:
            if exact is None or abs(c["p1"][perp] - line["pos"]) < abs(exact["p1"][perp] - line["pos"]):
                exact = c
        elif c["p1"][along] <= a + JOIN_TOL_M * ppm and c["p2"][along] >= b - JOIN_TOL_M * ppm and c["p2"][along] - c["p1"][along] < 1.3 * (b - a):
            if enclosing is None or abs(c["p1"][perp] - line["pos"]) < abs(enclosing["p1"][perp] - line["pos"]):
                enclosing = c
    return {"partials": partials, "total": exact, "reference": enclosing if exact is None else None,
            "uncovered_m": round(((enclosing["p2"][along] - enclosing["p1"][along]) - (b - a)) / ppm, 3) if enclosing and exact is None else None}


def _shift_candidates(partials: list[dict], k: int) -> list[float]:
    """Sommes d'épaisseurs voisines (≤ 0,35 m, jusqu'à 2 de chaque côté) et demi-épaisseurs : un écart égal à l'une d'elles
    entre deux chaînes opposées traduit une différence de référence (nu/nu vs axe/axe), pas une incohérence."""
    small = lambda c: c["value_m"] <= 0.35  # noqa: E731
    left = [c["value_m"] for c in reversed(partials[max(0, k - 2):k]) if small(c)]
    right = [c["value_m"] for c in partials[k + 1:k + 3] if small(c)]
    cands = set()
    for i in range(len(left) + 1):
        for j in range(len(right) + 1):
            base = sum(left[:i]) + sum(right[:j])
            if i or j:
                cands.add(base)
            for h in (left[i - 1] / 2 if i else None, right[j - 1] / 2 if j else None):
                if h is not None:
                    cands.add(base - h)
    return sorted(c for c in cands if c > 0)


def peripheral_chains(cotes: list[dict], ppm: float) -> dict:
    """→ {chains: [...], comparisons: [...], inconsistencies: [...]}. Les chaînes périphériques = les deux chaînes
    jointives les plus éloignées l'une de l'autre dans chaque orientation (haut/bas, gauche/droite) ; les chaînes
    intermédiaires (axes) sont conservées comme « intérieures »."""
    chains, comparisons, incons = [], [], []
    for orient, sides in (("h", ("haut", "bas")), ("v", ("gauche", "droite"))):
        found = []
        for ln in _lines(cotes, orient, ppm):
            ch = _chain_of(ln, ppm, cotes, orient)
            if ch:
                found.append((ln, ch))
        if not found:
            continue
        found.sort(key=lambda x: x[0]["pos"])
        along = found[0][0]["along"]
        for k, (ln, ch) in enumerate(found):
            side = sides[0] if k == 0 else sides[1] if k == len(found) - 1 and len(found) > 1 else "intérieure"
            s = sum(c["value_m"] for c in ch["partials"])
            tot = ch["total"]["value_m"] if ch["total"] else None
            diff_mm = round((s - tot) * 1000, 1) if tot is not None else None
            cid = f"CH-{orient.upper()}-{k + 1:02d}"
            ref = ch.get("reference")
            chains.append({"chain_id": cid, "orientation": "horizontal" if orient == "h" else "vertical", "side": side,
                           "reference_total_m": ref["value_m"] if ref else None, "reference_index": ref.get("index") if ref else None,
                           "uncovered_m": ch.get("uncovered_m"),
                           "partials": [{"index": c.get("index"), "value_m": c["value_m"], "from_m": round((c["p1"][along] - ln["a"]) / ppm, 3),
                                         "to_m": round((c["p2"][along] - ln["a"]) / ppm, 3)} for c in ch["partials"]],
                           "sum_m": round(s, 3), "total_m": tot, "total_index": ch["total"].get("index") if ch["total"] else None,
                           "difference_mm": diff_mm, "status": _status(abs(diff_mm)) if diff_mm is not None else "no_total"})
            if diff_mm is not None and abs(diff_mm) > OK_MM:
                incons.append({"kind": "chain_sum", "chain_id": cid, "side": side, "detail": f"Σ partielles {s:.2f} m ≠ total {tot:.2f} m ({diff_mm:+.0f} mm)",
                               "delta_mm": diff_mm, "status": _status(abs(diff_mm))})
        if len(found) >= 2:
            (_la, ca), (_lb, cb) = found[0], found[-1]
            sa, sb = sides
            # totaux opposés
            ta, tb_ = ca["total"] or ca.get("reference"), cb["total"] or cb.get("reference")
            if ta and tb_ and ta is not tb_:
                d = round((tb_["value_m"] - ta["value_m"]) * 1000, 1)
                comparisons.append({"kind": "total", "side_a": sa, "side_b": sb, "a_index": ta.get("index"), "a_value_m": ta["value_m"],
                                    "b_index": tb_.get("index"), "b_value_m": tb_["value_m"], "delta_mm": d, "status": _status(abs(d))})
                if abs(d) > OK_MM:
                    incons.append({"kind": "opposite_totals", "side": f"{sa}/{sb}", "detail": f"Dimension générale {sa} {ta['value_m']:.2f} m ≠ {sb} {tb_['value_m']:.2f} m ({d:+.0f} mm)",
                                   "delta_mm": d, "status": _status(abs(d)), "a_index": ta.get("index"), "b_index": tb_.get("index")})
            # partielles opposées alignées (même emprise le long de la chaîne, référence commune = début de ligne)
            used = set()
            for k, pa in enumerate(ca["partials"]):
                a1, a2 = pa["p1"][along], pa["p2"][along]
                best = None
                for j, pb in enumerate(cb["partials"]):
                    if j in used:
                        continue
                    b1, b2 = pb["p1"][along], pb["p2"][along]
                    ov = min(a2, b2) - max(a1, b1)
                    if ov >= 0.7 * max(a2 - a1, b2 - b1) and (best is None or ov > best[0]):
                        best = (ov, j, pb)
                if not best:
                    if pa["value_m"] >= 0.5:
                        incons.append({"kind": "missing_opposite", "side": sb, "detail": f"Cote {pa['value_m']:.2f} m ({sa}) sans cote de même emprise en face ({sb}) — références différentes (nu/axe) ou cote manquante",
                                       "delta_mm": None, "status": "warn", "a_index": pa.get("index")})
                    continue
                used.add(best[1])
                pb = best[2]
                d = round((pb["value_m"] - pa["value_m"]) * 1000, 1)
                shift = next((c for c in _shift_candidates(ca["partials"], k) + _shift_candidates(cb["partials"], best[1])
                              if abs(abs(d) / 1000 - c) <= OK_MM / 1000), None)
                st = "reference_shift" if (shift is not None and abs(d) > OK_MM) else _status(abs(d))
                comparisons.append({"kind": "partial", "side_a": sa, "side_b": sb, "a_index": pa.get("index"), "a_value_m": pa["value_m"],
                                    "b_index": pb.get("index"), "b_value_m": pb["value_m"], "delta_mm": d, "status": st,
                                    "explanation": f"écart = épaisseur(s) voisine(s) {shift:.2f} m : références différentes (nu/nu vs axe/axe), cohérent" if st == "reference_shift" else None})
                if st != "reference_shift" and abs(d) > OK_MM:
                    incons.append({"kind": "opposite_partials", "side": f"{sa}/{sb}", "detail": f"{pa['value_m']:.2f} m ({sa}) ≠ {pb['value_m']:.2f} m ({sb}) : {d:+.0f} mm",
                                   "delta_mm": d, "status": _status(abs(d)), "a_index": pa.get("index"), "b_index": pb.get("index")})
    incons.sort(key=lambda x: -(abs(x["delta_mm"]) if x["delta_mm"] is not None else 0))
    return {"chains": chains, "comparisons": comparisons, "inconsistencies": incons,
            "summary": {"chains": len(chains), "comparisons": len(comparisons), "inconsistencies": len(incons),
                        "ko": sum(1 for x in incons if x["status"] == "ko"), "warn": sum(1 for x in incons if x["status"] == "warn")}}
