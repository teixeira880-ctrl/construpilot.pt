"""Contrôle des cotes : cote indiquée ↔ longueur mesurée sur le plan + chaînes de cotes.

Entrée : liste de cotes en pixels image {x1,y1,x2,y2,value_m,confidence,location,source}
(lues par l'IA — bbox_norm converti — ou extraites d'un DXF avec `measured_m` exact).
"""
from __future__ import annotations

import math

STATUS_ORDER = {"ko": 0, "warn": 1, "ok": 2}


def _length_px(d: dict) -> float:
    return math.hypot(d["x2"] - d["x1"], d["y2"] - d["y1"])


def _orientation(d: dict) -> str:
    dx, dy = abs(d["x2"] - d["x1"]), abs(d["y2"] - d["y1"])
    if dx >= 4 * dy:
        return "h"
    if dy >= 4 * dx:
        return "v"
    return "o"


def dims_from_ai(dimension_lines: list[dict], img_w: int, img_h: int) -> list[dict]:
    """Cotes IA (bbox_norm 0-1) → segments pixels."""
    out = []
    for d in dimension_lines or []:
        bbox = d.get("bbox_norm")
        try:
            value = float(d.get("value_m") or 0)
        except (TypeError, ValueError):
            continue
        if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4) or value <= 0:
            continue
        out.append({"x1": bbox[0] * img_w, "y1": bbox[1] * img_h,
                    "x2": bbox[2] * img_w, "y2": bbox[3] * img_h,
                    "value_m": value, "raw_text": d.get("raw_text"),
                    "confidence": float(d.get("confidence") or 0.5),
                    "location": d.get("location"), "source": "ai"})
    return out


EXACT_SOURCES = ("dxf", "pdf")


def dims_from_dxf(dxf_dimensions: list[dict]) -> list[dict]:
    return [{**d, "confidence": 1.0, "source": "dxf"} for d in dxf_dimensions or []
            if d.get("value_m") and d.get("measured_m")]


def dims_from_pdf_vectors(pdf_dimensions: list[dict]) -> list[dict]:
    """Cotes vectorielles PDF (mesure exacte en points PDF → m, positions px image)."""
    return [{**{k: v for k, v in d.items() if k != "orientation"}, "confidence": .5 if d.get("unverified") else .9, "source": "pdf"}
            for d in pdf_dimensions or [] if d.get("value_m") and d.get("measured_m")]


def check_elements(elements: list[dict]) -> list[dict]:
    """Semelles / poutres / murs étiquetés (« 60x30 ») : largeur dessinée vs largeur annoncée (seuils mm)."""
    out = []
    for i, e in enumerate(elements or []):
        mm = abs(float(e["delta_mm"]))
        out.append({**e, "index": i + 1, "status": "ok" if mm <= 10.5 else "warn" if mm <= 30.5 else "ko",
                    "niveau": _niveau_mm(mm)})
    return out


def facade_diagonals(facades: list[dict], items: list[dict]) -> None:
    """Pour chaque écart de façade : différence de diagonales et déviation d'angle si l'écart est un défaut d'équerrage
    (rectangle L×W dont un côté est décalé de δ : d1 − d2 ≈ 2·L·δ / √(L²+W²))."""
    for f in facades:
        other = [it["indicated_m"] for it in items if it["orientation"] != f["orientation"] and not it.get("unverified")]
        if not other or f["status"] == "ok":
            continue
        L = (f["a_m"] + f["b_m"]) / 2
        W = max(other)
        d = abs(f["delta_m"])
        d1, d2 = math.hypot(L + d / 2, W), math.hypot(L - d / 2, W)
        f["diag"] = {"L_m": round(L, 3), "W_m": round(W, 3), "d1_m": round(d1, 3), "d2_m": round(d2, 3),
                     "diff_cm": round((d1 - d2) * 100, 1), "angle_deg": round(math.degrees(math.atan2(d, W)), 2),
                     "offset_cm": round(d * 100, 1)}


def _mid(d: dict) -> tuple[float, float]:
    return (d["x1"] + d["x2"]) / 2, (d["y1"] + d["y2"]) / 2


def merge_vector_and_ai(vdims: list[dict], adims: list[dict], img_w: int, img_h: int,
                        vector_complete: bool = False) -> tuple[list[dict], dict]:
    """Croisement lecture vectorielle ↔ lecture IA (mode hybride).

    - même valeur, même orientation, même zone → cote vectorielle CONFIRMÉE par l'IA ;
    - même zone mais valeur différente → DIVERGENCE de lecture (le texte vectoriel fait foi) ;
    - cote IA sans équivalent vectoriel → conservée comme non vérifiée (mesure pixel, jamais KO).
    """
    side = float(max(img_w, img_h))
    near, close = 0.04 * side, 0.025 * side
    merged = [dict(v) for v in vdims]
    stats = {"vector": len(vdims), "ai": len(adims), "confirmed": 0, "divergences": [], "ai_only": 0,
             "ai_only_dropped": 0, "vector_complete": vector_complete}
    for a in adims:
        if _length_px(a) < 0.002 * side:
            continue  # bbox IA dégénérée
        ao = _orientation(a)
        am = _mid(a)
        cands = []
        for v in merged:
            if _orientation(v) != ao:
                continue
            vm = _mid(v)
            dist = math.hypot(vm[0] - am[0], vm[1] - am[1])
            if dist <= near:
                cands.append((dist, v))
        cands.sort(key=lambda c: c[0])
        same = [c for c in cands if abs(c[1]["value_m"] - a["value_m"]) <= 0.006]
        if same:
            v = next((c[1] for c in same if not c[1].get("ai_confirmed")), same[0][1])
            if not v.get("ai_confirmed"):
                v["ai_confirmed"] = True
                stats["confirmed"] += 1
            continue
        if cands and cands[0][0] <= close:
            best = cands[0][1]
            stats["divergences"].append({"vector_text": best.get("raw_text"), "vector_m": best["value_m"],
                                         "ai_text": a.get("raw_text"), "ai_m": a["value_m"],
                                         "x": round(am[0], 1), "y": round(am[1], 1)})
            best["ai_divergent_m"] = a["value_m"]
            continue
        if vector_complete:  # tous les textes numériques du PDF ont un trait : une cote IA orpheline est un doublon mal placé
            stats["ai_only_dropped"] += 1
            continue
        stats["ai_only"] += 1
        merged.append({**a, "unverified": True})
    return merged, stats


def _status_exact(delta_m: float) -> str:
    """Mesure exacte (vecteurs PDF / DXF) : seuils mm ConstruPilot, la tolérance % (mesure pixel) ne s'applique pas."""
    mm = abs(delta_m) * 1000
    return "ok" if mm <= 10.5 else "warn" if mm <= 30.5 else "ko"


def _status(delta_m: float, tol_m: float) -> str:
    a = abs(delta_m)
    if a <= 0.6 * tol_m:
        return "ok"
    return "warn" if a <= tol_m else "ko"


def _niveau_mm(delta_mm: float) -> str:
    """Classification ConstruPilot : VERT ≤2 mm · BLEU ≤10 · JAUNE ≤30 · ORANGE ≤100 · ROUGE >100."""
    a = abs(delta_mm)
    return "VERT" if a <= 2 else "BLEU" if a <= 10 else "JAUNE" if a <= 30 else "ORANGE" if a <= 100 else "ROUGE"


def _tol_m(value_m: float, tol_pct: float, tol_cm: float) -> float:
    return max(value_m * tol_pct / 100.0, tol_cm / 100.0)


def _axis(d: dict, orient: str) -> tuple[float, float, float]:
    """(début, fin, position perpendiculaire) le long de l'axe de la cote."""
    if orient == "h":
        return min(d["x1"], d["x2"]), max(d["x1"], d["x2"]), (d["y1"] + d["y2"]) / 2
    return min(d["y1"], d["y2"]), max(d["y1"], d["y2"]), (d["x1"] + d["x2"]) / 2


def _find_chains(items: list[dict], tol_pct: float, tol_cm: float, img_side: float) -> list[dict]:
    """Une cote 'totale' doit être égale à la somme des cotes partielles contiguës qu'elle couvre."""
    exact = bool(items) and all(it.get("source") in EXACT_SOURCES for it in items)
    # positions exactes (DXF / vecteurs PDF) → tolérances serrées pour ne pas mélanger deux lignes de cotes voisines
    tol_px = max(2.0, img_side * 0.0015) if exact else max(6.0, img_side * 0.015)
    band_px = max(3.0, img_side * 0.003) if exact else max(10.0, img_side * 0.02)
    chains = []
    for total in items:
        o = total["orientation"]
        if o == "o" or total["indicated_m"] < 1.0:
            continue
        a1, a2, _ = _axis(total, o)
        cands = [it for it in items if it is not total and it["orientation"] == o]
        cands = [it for it in cands
                 if _axis(it, o)[0] >= a1 - tol_px and _axis(it, o)[1] <= a2 + tol_px
                 and _axis(it, o)[1] - _axis(it, o)[0] < (a2 - a1) - tol_px
                 and it["indicated_m"] < 0.9 * total["indicated_m"]]
        if len(cands) < 2:
            continue
        bands: dict[int, list[dict]] = {}
        for it in cands:
            bands.setdefault(int(round(_axis(it, o)[2] / band_px)), []).append(it)
        best = None
        for group in bands.values():
            group.sort(key=lambda it: _axis(it, o)[0])
            if len(group) < 2 or abs(_axis(group[0], o)[0] - a1) > tol_px:
                continue
            cursor, ok = a1, True
            for it in group:
                s, e, _ = _axis(it, o)
                if abs(s - cursor) > tol_px:
                    ok = False
                    break
                cursor = e
            if ok and abs(cursor - a2) <= tol_px and (best is None or len(group) > len(best)):
                best = group
        if not best:
            continue
        sum_m = sum(it["indicated_m"] for it in best)
        delta = sum_m - total["indicated_m"]
        if exact:  # arithmétique pure sur des valeurs inscrites : seuils mm ConstruPilot (BLEU ok / JAUNE warn / au-delà ko)
            status = "ok" if abs(delta) <= 0.0105 else "warn" if abs(delta) <= 0.0305 else "ko"
        else:
            status = _status(delta, _tol_m(total["indicated_m"], tol_pct, tol_cm))
        chains.append({"total_index": total["index"], "total_m": total["indicated_m"],
                       "part_indexes": [it["index"] for it in best],
                       "parts_m": [it["indicated_m"] for it in best],
                       "sum_m": round(sum_m, 3), "delta_m": round(delta, 3),
                       "delta_cm": round(delta * 100, 1), "status": status,
                       "niveau": _niveau_mm(delta * 1000), "exact": exact})
    return chains


def snap_dims_to_image(image_b64: str, dims: list[dict], max_shift_frac: float = 0.03) -> int:
    """Recale les extrémités des cotes IA sur les traits d'attache réellement dessinés.

    Pour une cote horizontale, on cherche dans une bande autour de y la colonne sombre
    (trait vertical traversant la bande) la plus proche de chaque extrémité ; idem en vertical.
    Renvoie le nombre d'extrémités recalées.
    """
    import base64
    import io

    import numpy as np
    from PIL import Image

    img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("L")
    dark = np.asarray(img) < 140
    H, W = dark.shape
    moved = 0

    def _snap(profile: np.ndarray, pos: float, window: float) -> float | None:
        lo, hi = int(max(0, pos - window)), int(min(len(profile) - 1, pos + window))
        if hi <= lo:
            return None
        idx = np.nonzero(profile[lo:hi + 1] >= 0.6)[0]
        if idx.size == 0:
            return None
        cols = idx + lo
        return float(cols[np.argmin(np.abs(cols - pos))])

    for d in dims:
        if d.get("source") != "ai":
            continue
        o = _orientation(d)
        if o == "h":
            y = (d["y1"] + d["y2"]) / 2
            bh = max(4, int(0.012 * H))
            band = dark[max(0, int(y) - bh):min(H, int(y) + bh), :]
            prof = band.mean(axis=0) if band.size else None
            if prof is None:
                continue
            for k in ("x1", "x2"):
                nx = _snap(prof, d[k], max(6.0, max_shift_frac * W))
                if nx is not None and abs(nx - d[k]) > 1:
                    d[k] = nx
                    moved += 1
            d["y1"] = d["y2"] = y
        elif o == "v":
            x = (d["x1"] + d["x2"]) / 2
            bw = max(4, int(0.012 * W))
            band = dark[:, max(0, int(x) - bw):min(W, int(x) + bw)]
            prof = band.mean(axis=1) if band.size else None
            if prof is None:
                continue
            for k in ("y1", "y2"):
                ny = _snap(prof, d[k], max(6.0, max_shift_frac * H))
                if ny is not None and abs(ny - d[k]) > 1:
                    d[k] = ny
                    moved += 1
            d["x1"] = d["x2"] = x
        if moved:
            d["snapped"] = True
    return moved


def items_to_dims(items: list[dict]) -> list[dict]:
    """Rapport stocké → cotes réutilisables pour un recalcul sans relire le plan."""
    return [{"x1": it["x1"], "y1": it["y1"], "x2": it["x2"], "y2": it["y2"],
             "value_m": it["indicated_m"], "measured_m": it.get("measured_exact_m"),
             "source": it.get("source", "ai"), "confidence": it.get("confidence", 0.5),
             "location": it.get("location"), "raw_text": it.get("raw_text"),
             "override": it.get("override"), "ignored": it.get("ignored", False),
             "edited": it.get("edited", False), "original_m": it.get("original_m"),
             "unverified": it.get("unverified", False), "ai_confirmed": it.get("ai_confirmed", False),
             "ai_divergent_m": it.get("ai_divergent_m"), "anchor_mm": it.get("anchor_mm")}
            for it in items]


def _find_facades(items: list[dict], img_w: int, img_h: int) -> list[dict]:
    """Cotes générales opposées (même orientation, même emprise, aux deux bords du dessin) : elles doivent être
    égales sur une emprise rectangulaire. Écart > 20 mm → incohérence (3-4 cm = implantation ambiguë)."""
    side = float(max(img_w, img_h))
    out = []
    for orient in ("h", "v"):
        tot = [it for it in items if it["orientation"] == orient and not it.get("unverified") and not it.get("ignored")]
        if len(tot) < 2:
            continue
        vmax = max(it["indicated_m"] for it in tot)
        tot = [it for it in tot if it["indicated_m"] >= max(3.0, 0.6 * vmax)]
        seen = set()
        for i, a in enumerate(tot):
            for b in tot[i + 1:]:
                if orient == "h":
                    a1, a2, ap = min(a["x1"], a["x2"]), max(a["x1"], a["x2"]), (a["y1"] + a["y2"]) / 2
                    b1, b2, bp = min(b["x1"], b["x2"]), max(b["x1"], b["x2"]), (b["y1"] + b["y2"]) / 2
                else:
                    a1, a2, ap = min(a["y1"], a["y2"]), max(a["y1"], a["y2"]), (a["x1"] + a["x2"]) / 2
                    b1, b2, bp = min(b["y1"], b["y2"]), max(b["y1"], b["y2"]), (b["x1"] + b["x2"]) / 2
                overlap = max(0.0, min(a2, b2) - max(a1, b1)) / max(1e-6, min(a2 - a1, b2 - b1))
                if overlap < 0.7 or abs(ap - bp) < 0.25 * side:
                    continue
                key = tuple(sorted((a["index"], b["index"])))
                if key in seen:
                    continue
                seen.add(key)
                delta = b["indicated_m"] - a["indicated_m"]
                mm = abs(delta) * 1000
                status = "ok" if mm <= 10.5 else "warn" if mm <= 20.5 else "ko"
                out.append({"orientation": orient, "a_index": a["index"], "a_m": a["indicated_m"],
                            "b_index": b["index"], "b_m": b["indicated_m"], "delta_m": round(delta, 3),
                            "delta_cm": round(delta * 100, 1), "niveau": _niveau_mm(mm), "status": status,
                            "a_side": ("haut" if orient == "h" else "gauche") if ap < bp else ("bas" if orient == "h" else "droite"),
                            "b_side": ("bas" if orient == "h" else "droite") if ap < bp else ("haut" if orient == "h" else "gauche")})
    out.sort(key=lambda f: -abs(f["delta_m"]))
    return out


def quick_conclusion(report: dict) -> str:
    """« Conclusion rapide » déterministe (FR ; traduite via plan_pdf_i18n.tr en PT)."""
    sm, fac, chains = report["summary"], report.get("facades") or [], report.get("chains") or []
    bad_f = [f for f in fac if f["status"] != "ok"]
    bad_c = [c for c in chains if c["status"] != "ok"]
    parts = []
    if bad_f:
        parts.append("As dimensões gerais opostas apresentam diferenças de "
                     + " et ".join(f"{abs(f['delta_cm']):g} cm ({f['a_m']:.2f} m {f['a_side']} / {f['b_m']:.2f} m {f['b_side']})" for f in bad_f)
                     + " : a implantação não está confirmada como retangular sem cota única, diagonal ou planta de eixos.")
    if bad_c:
        parts.append("Cadeia(s) de cotas que não fecham: "
                     + " ; ".join(f"{c['total_m']:.2f} m contra {c['sum_m']:.2f} m en cotes partielles ({c['delta_cm']:+g} cm)" for c in bad_c) + ".")
    for f in bad_f:
        if f.get("diag"):
            parts.append(f"Se a diferença de {f['diag']['offset_cm']:g} cm for um defeito de esquadria, as diagonais diferem cerca de {abs(f['diag']['diff_cm']):g} cm ({f['diag']['d1_m']:.2f} m / {f['diag']['d2_m']:.2f} m), ou seja, um desvio angular de {f['diag']['angle_deg']:g}°.")
    bad_e = [e for e in report.get("elements") or [] if e["status"] != "ok"]
    if bad_e:
        parts.append("Elementos desenhados cuja largura não corresponde à etiqueta: "
                     + " ; ".join(f"{e['label']} dessiné {e['measured_w_m'] * 100:.0f} cm ({e['delta_mm']:+.0f} mm)" for e in bad_e[:6])
                     + (f" et {len(bad_e) - 6} autre(s)" if len(bad_e) > 6 else "") + ".")
    floating = [it for it in report.get("items") or [] if it.get("anchor_status") in ("warn", "ko") and not it.get("ignored")]
    if floating:
        parts.append(f'{len(floating)} cota(s) provavelmente errada(s): as suas extremidades não estão alinhadas com nenhuma face nem eixo de parede desenhado (diferença > 10 mm em projeção perpendicular) — '
                     + ", ".join(f"#{it['index']} {it['indicated_m']:.2f} m ({max(a for a in it['anchor_mm'] if a is not None):.0f} mm)" for it in floating[:6]) + ".")
    if sm.get("ko") or sm.get("warn"):
        parts.append(f"{sm.get('ko', 0)} cota(s) incoerente(s) e {sm.get('warn', 0)} a verificar entre o valor inscrito e a medição.")
    if not parts:
        return ("Todas as cotas inscritas correspondem à medição, as cadeias fecham, as dimensões gerais opostas são iguais, as cotas estão associadas ao desenho e os elementos etiquetados têm a largura anunciada: nenhuma incoerência registada nesta página.")
    parts.append("Estes pontos devem ser esclarecidos numa planta corrigida antes da implantação.")
    return " ".join(parts)


def check_dimensions(dims: list[dict], ppm: float, tol_pct: float, tol_cm: float,
                     img_w: int, img_h: int, elements: list[dict] | None = None,
                     auto_spans: list[dict] | None = None) -> dict:
    items = []
    for i, d in enumerate(dims):
        px = _length_px(d)
        exact = d.get("measured_m") if d.get("source") in EXACT_SOURCES else None
        measured = exact if exact is not None else px / ppm
        indicated = float(d["value_m"])
        delta = measured - indicated
        tol = _tol_m(indicated, tol_pct, tol_cm)
        items.append({
            "index": i + 1, "x1": round(d["x1"], 1), "y1": round(d["y1"], 1),
            "x2": round(d["x2"], 1), "y2": round(d["y2"], 1),
            "orientation": _orientation(d), "location": d.get("location"),
            "raw_text": d.get("raw_text"), "source": d.get("source", "ai"),
            "confidence": round(float(d.get("confidence") or 0.5), 2),
            "indicated_m": round(indicated, 3), "measured_m": round(measured, 3),
            "measured_exact_m": exact, "pixel_length": round(px, 1),
            "delta_m": round(delta, 3), "delta_cm": round(delta * 100, 1),
            "delta_pct": round(delta / indicated * 100, 2) if indicated else None,
            "tolerance_cm": round(tol * 100, 1),
            "status": ("ignored" if d.get("ignored") else _status_exact(delta) if exact is not None else _status(delta, tol)),
            "niveau": _niveau_mm(delta * 1000),
            "override": bool(d.get("override")), "ignored": bool(d.get("ignored")),
            "edited": bool(d.get("edited")), "original_m": d.get("original_m"),
            "unverified": bool(d.get("unverified")), "ai_confirmed": bool(d.get("ai_confirmed")),
            "ai_divergent_m": d.get("ai_divergent_m"), "anchor_mm": d.get("anchor_mm"),
        })
        anc = [a for a in (d.get("anchor_mm") or []) if a is not None]
        worst_anchor = max(anc) if anc else None
        # rattachement au dessin : une extrémité de cote à > 10 mm de tout trait long (face/axe) = cote « flottante »
        items[-1]["anchor_status"] = (None if worst_anchor is None else
                                      "ok" if worst_anchor <= 10.5 else "warn" if worst_anchor <= 30.5 else "ko")
        if items[-1]["unverified"] and not items[-1]["ignored"]:
            items[-1]["status"] = "nd"  # rattachement non vérifié : ni conformité ni erreur démontrée
    active = [it for it in items if not it["ignored"]]
    # Abstention (règle ConstruPilot : un faux positif est plus dangereux qu'une donnée non déterminée) :
    # si les ratios mesure/cote sont trop dispersés, l'échelle ou le placement des traits n'est pas fiable →
    # les statuts issus de la MESURE passent en « nd » ; seuls les contrôles arithmétiques (chaînes) restent.
    measure_reliable = True
    ratios = sorted(it["measured_m"] / it["indicated_m"] for it in active
                    if it["indicated_m"] >= 1.0 and it.get("source") not in EXACT_SOURCES)
    if len(ratios) >= 4:
        med = ratios[len(ratios) // 2]
        spread = sorted(abs(r - med) for r in ratios)[len(ratios) // 2] / med if med else 1
        if spread > 0.08 or abs(1 - med) > 0.12:
            measure_reliable = False
            for it in active:
                if it["source"] not in EXACT_SOURCES and it["status"] in ("warn", "ko"):
                    it["status"] = "nd"
    # Les chaînes reposent sur la position des traits : sans mesure fiable, on s'abstient aussi (l'analyse
    # géométrique IA, qui raisonne sur les valeurs inscrites, prend le relais pour les fermetures).
    chain_items = [it for it in active if not it["unverified"]]
    chains = _find_chains(chain_items, tol_pct, tol_cm, float(max(img_w, img_h))) if measure_reliable else []
    for it in items:
        it["chain_status"] = None
    for c in chains:
        if c["status"] != "ok":
            for idx in [c["total_index"], *c["part_indexes"]]:
                items[idx - 1]["chain_status"] = c["status"]
    facades = _find_facades(active, img_w, img_h) if measure_reliable else []
    facade_diagonals(facades, active)
    elems = check_elements(elements)
    el_counts = {s: sum(1 for e in elems if e["status"] == s) for s in ("ok", "warn", "ko")}
    anchor_counts = {s: sum(1 for it in active if it.get("anchor_status") == s) for s in ("ok", "warn", "ko")}
    for f in facades:
        if f["status"] != "ok":
            for idx in (f["a_index"], f["b_index"]):
                items[idx - 1]["facade_status"] = f["status"]
    counts = {s: sum(1 for it in active if it["status"] == s) for s in ("ok", "warn", "ko", "nd")}
    chain_counts = {s: sum(1 for c in chains if c["status"] == s) for s in ("ok", "warn", "ko")}
    fac_counts = {s: sum(1 for f in facades if f["status"] == s) for s in ("ok", "warn", "ko")}
    worst = max((abs(it["delta_cm"]) for it in active if it["status"] != "nd"), default=0.0)
    result = {
        "items": items, "chains": chains, "facades": facades, "elements": elems,
        "auto_spans": [{**sp, "index": i + 1} for i, sp in enumerate(auto_spans or [])],
        "measure_reliable": measure_reliable,
        "abstention": None if measure_reliable else (
            "Medição à escala não fiável nesta página (dispersão das razões medição/cota): as diferenças medidas não são assinaladas como incoerências. Só os controlos aritméticos (cadeias, fechos) fazem fé. Calibre a escala manualmente para reativar a medição."),
        "summary": {"total": len(active), "ignored": len(items) - len(active), **counts,
                    "chains_total": len(chains),
                    "chains_ko": chain_counts["ko"], "chains_warn": chain_counts["warn"],
                    "facades_total": len(facades), "facades_ko": fac_counts["ko"], "facades_warn": fac_counts["warn"],
                    "elements_total": len(elems), "elements_ko": el_counts["ko"], "elements_warn": el_counts["warn"],
                    "auto_spans_total": len(auto_spans or []),
                    "anchors_ko": anchor_counts["ko"], "anchors_warn": anchor_counts["warn"],
                    "max_delta_cm": round(worst, 1),
                    "verdict": ("ko" if counts["ko"] or chain_counts["ko"] or fac_counts["ko"] or el_counts["ko"] or anchor_counts["ko"]
                                else "warn" if counts["warn"] or chain_counts["warn"] or fac_counts["warn"] or el_counts["warn"] or anchor_counts["warn"]
                                else "ok")},
        "tolerance": {"pct": tol_pct, "cm": tol_cm},
    }
    result["summary"]["conclusion"] = quick_conclusion(result)
    return result
