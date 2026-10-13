"""Murs à deux faces, travées intérieures nu-à-nu et équations de fermeture — géométrie vectorielle PDF exacte.

Entrées : vecteurs PDF (points), cotes vectorielles rattachées (`extract_vector_dimensions`), échelle pt/m.
Sorties : murs {wall_id, orientation, face_1, face_2, axis, thickness_m…}, mesures {measurement_id INT-H-001…,
from_wall/face, to_wall/face, reference_type, written/geometric, status, confidence}, cotes classées par type de référence,
équations de fermeture par rangée, et contrôles de validation bloquants.

Un mur n'est jamais une ligne unique : deux traits longs parallèles distants de 5 à 60 cm qui se font face.
"""
from __future__ import annotations

import re
import math
from itertools import count

from engines.plan_vector_pdf import _segments

MIN_WALL_LEN_M = 0.40
MIN_T_M, MAX_T_M = 0.05, 0.61  # marge numérique autour de 60 cm ; aucune épaisseur imposée
FACE_TOL_M = 0.012       # rattachement d'une extrémité de cote à une face / un axe
CONFIRM_TOL_M = 0.010    # accord cote écrite / mesure géométrique
_SECTION_RE = re.compile(r"^\d{2,3}\s*[xX×]\s*\d{2,3}$")

INCOMPLETE_MSG = ("Analyse incomplète : les dimensions intérieures mur à mur n'ont pas toutes été établies. "
                  "Le rapport final ne peut pas encore être validé.")


def merged_lines(vectors: list[dict]) -> tuple[list[tuple], list[tuple]]:
    """Segments h/v colinéaires fusionnés → (hs [(y, xa, xb)], vs [(x, ya, yb)]) en points PDF."""
    # Les axes pointillés et les polygones de hachure ne sont pas des faces.
    # Conserver les contours re/qu, y compris les bandes pleines.
    def face_candidate(v):
        return (v.get("cad_role") != "dimension" and not v.get("curve_approximation") and not re.search(r"\[\s*\d", v.get("dashes") or "[] 0")
                and (v.get("paint_type") != "f" or v.get("type") in ("rect", "quad")))
    hs, vs, _ = _segments([v for v in vectors if face_candidate(v)])

    def merge(segs):
        segs = sorted(segs)
        out: list[list[float]] = []
        for pos, a, b in segs:
            if out and abs(out[-1][0] - pos) <= 0.4 and a <= out[-1][2] + 1.0:
                out[-1][2] = max(out[-1][2], b)
                out[-1][1] = min(out[-1][1], a)
            else:
                out.append([pos, a, b])
        return [tuple(o) for o in out]
    return merge(hs), merge(vs)


def _overlap(a1, b1, a2, b2) -> float:
    return max(0.0, min(b1, b2) - max(a1, a2))


def closed_bands(vectors: list[dict], ppm: float, bbox=None) -> list[dict]:
    """Bandes rectangulaires fermées réelles du PDF, avant l'appariement de traits.

    C'est une preuve de contour, pas une identification automatique de matériau
    ou de rôle porteur. Les quadrilatères obliques ne sont pas redressés.
    """
    out = []
    for v in vectors:
        if v.get("cad_role") == "dimension" or re.search(r"\[\s*\d", v.get("dashes") or "[] 0"):
            continue
        if v.get("type") == "rect":
            x, y, w, h = v["x"], v["y"], v["w"], v["h"]
        elif v.get("type") == "quad":
            pts = v["points"]
            if any(abs(a[0] - b[0]) > .1 and abs(a[1] - b[1]) > .1
                   for a, b in zip(pts, pts[1:] + pts[:1])):
                continue
            x, y = min(p[0] for p in pts), min(p[1] for p in pts)
            w, h = max(p[0] for p in pts) - x, max(p[1] for p in pts) - y
        else:
            continue
        if not MIN_T_M <= min(w, h) / ppm <= MAX_T_M or max(w, h) / ppm < 1.0:
            continue
        if bbox and not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
            continue
        vert = h > w
        lo, hi = (y, y + h) if vert else (x, x + w)
        p1, p2 = (x, x + w) if vert else (y, y + h)
        candidate = {"wall_id": None, "orientation": "vertical" if vert else "horizontal",
                     "pos_1": p1, "pos_2": p2, "lo": lo, "hi": hi,
                     "face_1_extent": [lo, hi], "face_2_extent": [lo, hi],
                     "axis_pos": (p1 + p2) / 2, "thickness_m": round((p2 - p1) / ppm, 4),
                     "source": "closed_contour", "confidence": .8, "ambiguous": False}
        # Fusion seulement si mêmes faces et emprises contiguës, sans combler une baie.
        previous = next((b for b in out if b["orientation"] == candidate["orientation"]
                         and abs(b["pos_1"] - p1) < .1 and abs(b["pos_2"] - p2) < .1
                         and min(b["hi"], hi) >= max(b["lo"], lo) - .1), None)
        if previous:
            previous["lo"], previous["hi"] = min(lo, previous["lo"]), max(hi, previous["hi"])
            previous["face_1_extent"] = previous["face_2_extent"] = [previous["lo"], previous["hi"]]
        else:
            out.append(candidate)
    return out


def detect_walls(hs: list[tuple], vs: list[tuple], ppm: float, thickness_cotes: list[dict] | None = None,
                 bbox: tuple | None = None) -> list[dict]:
    """Paires de traits longs parallèles voisins (5–60 cm) qui se font face → murs. `thickness_cotes` : cotes
    d'épaisseur écrites (orientation, p1, p2 en pt) qui confirment une paire (source explicit_dimension).
    Filtres anti-bruit : emprise `bbox` (zone cotée du dessin, exclut cartouche/détails), épaisseurs limitées aux
    plage d'épaisseurs admissibles, longueur ≥ 1 m pour une paire non confirmée.
    Les cotes d'épaisseur confirment seulement la paire à laquelle elles se rattachent."""
    walls: list[dict] = []
    ids = count(1)
    for orient, lines in (("vertical", vs), ("horizontal", hs)):
        longs = sorted(ln for ln in lines if ln[2] - ln[1] >= MIN_WALL_LEN_M * ppm)
        if bbox:
            (bx0, by0, bx1, by1) = bbox
            longs = [ln for ln in longs if ((bx0 <= ln[0] <= bx1 and ln[1] < by1 and ln[2] > by0) if orient == "vertical"
                                            else (by0 <= ln[0] <= by1 and ln[1] < bx1 and ln[2] > bx0))]
        # bandes hachurées : ≥ 4 traits parallèles longs au pas ≤ 12 mm → un remplissage dont les bords sont les deux faces
        groups: list[list[tuple]] = []
        for ln in longs:
            if groups and ln[0] - groups[-1][-1][0] <= 0.012 * ppm and _overlap(groups[-1][-1][1], groups[-1][-1][2], ln[1], ln[2]) >= 0.5 * (ln[2] - ln[1]):
                groups[-1].append(ln)
            else:
                groups.append([ln])
        longs = []
        for g in groups:
            if len(g) >= 4 and MIN_T_M * ppm <= g[-1][0] - g[0][0] <= MAX_T_M * ppm:
                lo, hi = min(x[1] for x in g), max(x[2] for x in g)
                walls.append({"wall_id": None, "orientation": orient, "pos_1": g[0][0], "pos_2": g[-1][0], "lo": lo, "hi": hi,
                              "face_1_extent": [lo, hi], "face_2_extent": [lo, hi], "axis_pos": (g[0][0] + g[-1][0]) / 2,
                              "thickness_m": round((g[-1][0] - g[0][0]) / ppm, 4), "source": "hatched_band", "confidence": 0.6,
                              "ambiguous": False, "_lines": (-1, -1)})
                longs += [g[0], g[-1]]
            else:
                longs += g
        used: dict[int, int] = {}
        for i, (p1, a1, b1) in enumerate(longs):
            for j in range(i + 1, len(longs)):
                p2, a2, b2 = longs[j]
                gap = p2 - p1
                if gap > MAX_T_M * ppm:
                    break
                if gap < MIN_T_M * ppm:
                    continue
                t_m = gap / ppm
                # Une épaisseur cotée est une preuve locale, jamais un filtre
                # global excluant les autres épaisseurs présentes sur le plan.
                ov = _overlap(a1, b1, a2, b2)
                if ov < MIN_WALL_LEN_M * ppm or ov < 0.5 * min(b1 - a1, b2 - a2):
                    continue
                # un trait intermédiaire long entre les deux → pas une paire de faces
                if any(p1 + 0.5 < q < p2 - 0.5 and _overlap(a1, b1, qa, qb) > 0.3 * ov for q, qa, qb in longs[i + 1:j]):
                    continue
                lo, hi = max(a1, a2), min(b1, b2)
                w = {"wall_id": None, "orientation": orient, "pos_1": p1, "pos_2": p2, "lo": lo, "hi": hi,
                     "face_1_extent": [a1, b1], "face_2_extent": [a2, b2],
                     "axis_pos": (p1 + p2) / 2, "thickness_m": round(gap / ppm, 4), "source": "vector_geometry",
                     "confidence": 0.7, "ambiguous": False}
                used[i] = used.get(i, 0) + 1
                used[j] = used.get(j, 0) + 1
                w["_lines"] = (i, j)
                walls.append(w)
        for w in [x for x in walls if x["orientation"] == orient and "_lines" in x]:
            i, j = w.pop("_lines")
            if i >= 0 and (used.get(i, 0) > 1 or used.get(j, 0) > 1):
                w["ambiguous"] = True
                w["confidence"] = 0.45
    for w in walls:
        for c in thickness_cotes or []:
            if c["orientation"] != ("h" if w["orientation"] == "vertical" else "v"):
                continue
            c1, c2 = sorted((c["p1"][0], c["p2"][0]) if c["orientation"] == "h" else (c["p1"][1], c["p2"][1]))
            perp = c["p1"][1] if c["orientation"] == "h" else c["p1"][0]
            if abs(c1 - w["pos_1"]) <= FACE_TOL_M * ppm and abs(c2 - w["pos_2"]) <= FACE_TOL_M * ppm \
                    and w["lo"] - 2.0 * ppm <= perp <= w["hi"] + 2.0 * ppm:
                w.update({"source": "explicit_dimension", "confidence": 0.95, "ambiguous": False, "thickness_cote_m": c["value_m"]})
                break
    walls = [w for w in walls if w["source"] == "explicit_dimension" or w["hi"] - w["lo"] >= 1.0 * ppm]
    # dédoublonnage : deux « murs » de même orientation dont les bandes se recouvrent = une seule paire de faces
    walls.sort(key=lambda w: (w["source"] != "explicit_dimension", -(w["hi"] - w["lo"])))
    kept: list[dict] = []
    for w in walls:
        dup = any(k["orientation"] == w["orientation"] and _overlap(k["pos_1"], k["pos_2"], w["pos_1"], w["pos_2"]) > 0.5 * (w["pos_2"] - w["pos_1"])
                  and _overlap(k["lo"], k["hi"], w["lo"], w["hi"]) > 0.5 * (w["hi"] - w["lo"]) for k in kept)
        if not dup:
            kept.append(w)
    walls = kept
    walls.sort(key=lambda w: (w["orientation"], w["pos_1"], w["lo"]))
    for w in walls:
        w["wall_id"] = f"M{next(ids):02d}"
    return walls


def snap_faces_to_cotes(walls: list[dict], dims: list[dict], ppm: float, tol_m: float = 0.03) -> None:
    """Faces par cotes : chaque face d'un mur (surtout les bandes hachurées dont les bords de hachure ≠ nus) est recalée
    sur l'extrémité de trait d'attache la plus proche (≤ 3 cm) d'une cote de même direction ; la face devient `cote`."""
    for w in walls:
        if w.get("is_post"):
            continue
        o = "h" if w["orientation"] == "vertical" else "v"
        along = 0 if o == "h" else 1
        ends = [(c["p1"][along], c) for c in dims if c["orientation"] == o] + [(c["p2"][along], c) for c in dims if c["orientation"] == o]
        for key in ("pos_1", "pos_2"):
            best = None
            other = w["pos_2"] if key == "pos_1" else w["pos_1"]
            for pos, c in ends:
                perp = c["p1"][1 - along]
                d = abs(pos - w[key])
                # la ligne de cote doit être proche de l'emprise du mur (≤ 2 m) ; l'épaisseur recalée reste plausible
                if d <= tol_m * ppm and (w["lo"] - 2.0 * ppm <= perp <= w["hi"] + 2.0 * ppm) \
                        and MIN_T_M * ppm <= abs(other - pos) <= MAX_T_M * ppm and (best is None or d < best[0]):
                    best = (d, pos)
            if best and best[0] > 0.3:
                w[key] = best[1]
                w.setdefault("faces_from_cotes", []).append(key)
        if w.get("faces_from_cotes"):
            w["axis_pos"] = (w["pos_1"] + w["pos_2"]) / 2
            w["thickness_m"] = round((w["pos_2"] - w["pos_1"]) / ppm, 4)
            if len(w["faces_from_cotes"]) == 2:
                w["source"] = "explicit_dimension" if w["source"] == "hatched_band" else w["source"]
                w["confidence"] = max(w["confidence"], 0.85)
                w["ambiguous"] = False


def detect_posts(hs: list[tuple], vs: list[tuple], ppm: float, text_blocks: list[dict], px_per_pt: float) -> list[dict]:
    """Poteaux (ex. 13x13) : petits rectangles fermés (4 traits courts) — chaque poteau produit deux « murs » courts
    (faces x → orientation vertical, faces y → horizontal) pour mesurer les travées entre nus de poteaux."""
    import re as _re
    sizes = set()
    for t in text_blocks or []:
        m = _re.match(r"^(\d{2})\s*[xX×]\s*(\d{2})$", (t.get("text") or "").strip())
        if m and m.group(1) == m.group(2) and 8 <= int(m.group(1)) <= 40:
            sizes.add(int(m.group(1)) / 100)
    if not sizes:
        return []
    tol = 0.02 * ppm
    shorts_v = [ln for ln in vs if 0.06 * ppm <= ln[2] - ln[1] <= 0.45 * ppm]
    shorts_h = [ln for ln in hs if 0.06 * ppm <= ln[2] - ln[1] <= 0.45 * ppm]
    posts = []
    for i, (x1, ya, yb) in enumerate(shorts_v):
        for x2, yc, yd in shorts_v[i + 1:]:
            gap = (x2 - x1) / ppm
            if gap <= 0.06:
                continue
            if gap > 0.45:
                break
            if not any(abs(gap - s) <= 0.02 for s in sizes) or abs(ya - yc) > tol or abs(yb - yd) > tol:
                continue
            top = any(abs(y - ya) <= tol and a <= x1 + tol and b >= x2 - tol for y, a, b in shorts_h)
            bot = any(abs(y - yb) <= tol and a <= x1 + tol and b >= x2 - tol for y, a, b in shorts_h)
            if top and bot:
                posts.append({"x1": x1, "x2": x2, "y1": ya, "y2": yb, "size_m": round(gap, 3)})
    walls = []
    for k, p in enumerate(posts, 1):
        base = {"source": "post_rectangle", "confidence": 0.9, "ambiguous": False, "is_post": True, "post_id": f"P{k:02d}",
                "ouvrage_class": "Poteau béton", "class_source": "rectangle fermé + repère de section (bibliothèque symboles)",
                "class_alternatives": ["Semelle isolée"], "labels": [f"{int(round(p['size_m'] * 100))}x{int(round(p['size_m'] * 100))}"]}
        walls.append({**base, "wall_id": None, "orientation": "vertical", "pos_1": p["x1"], "pos_2": p["x2"], "lo": p["y1"], "hi": p["y2"],
                      "face_1_extent": [p["y1"], p["y2"]], "face_2_extent": [p["y1"], p["y2"]], "axis_pos": (p["x1"] + p["x2"]) / 2,
                      "thickness_m": p["size_m"]})
        walls.append({**base, "wall_id": None, "orientation": "horizontal", "pos_1": p["y1"], "pos_2": p["y2"], "lo": p["x1"], "hi": p["x2"],
                      "face_1_extent": [p["x1"], p["x2"]], "face_2_extent": [p["x1"], p["x2"]], "axis_pos": (p["y1"] + p["y2"]) / 2,
                      "thickness_m": p["size_m"]})
    return walls


def _wall_json(w: dict, ppm: float, px: float) -> dict:
    vert = w["orientation"] == "vertical"

    def face(pos, ext):
        return ({"x1": pos, "y1": ext[0], "x2": pos, "y2": ext[1]} if vert else {"x1": ext[0], "y1": pos, "x2": ext[1], "y2": pos})
    f1, f2 = face(w["pos_1"], w["face_1_extent"]), face(w["pos_2"], w["face_2_extent"])
    ax = face(w["axis_pos"], [w["lo"], w["hi"]])
    scale = lambda d: {k: round(v * px, 2) for k, v in d.items()}  # noqa: E731
    return {"wall_id": w["wall_id"], "orientation": w["orientation"], "face_1": scale(f1), "face_2": scale(f2), "axis": scale(ax),
            "thickness_m": w["thickness_m"], "length_m": round((w["hi"] - w["lo"]) / ppm, 3), "source": w["source"],
            "confidence": w["confidence"], "ambiguous": w["ambiguous"], "thickness_cote_m": w.get("thickness_cote_m"),
            "intersections": w.get("intersections", []), "labels": w.get("labels", []), "ouvrage_class": w.get("ouvrage_class"),
            "class_source": w.get("class_source"), "class_alternatives": w.get("class_alternatives", []),
            "faces_from_cotes": w.get("faces_from_cotes", []), "is_post": bool(w.get("is_post")), "post_id": w.get("post_id")}


def _intersections(walls: list[dict], ppm: float) -> None:
    tol = 0.02 * ppm
    for w in walls:
        w["intersections"] = []
    for a in walls:
        for b in walls:
            if a is b or a["orientation"] == b["orientation"]:
                continue
            # b (perpendiculaire) croise ou bute sur a ?
            if a["pos_1"] - tol <= b["axis_pos"] <= a["pos_2"] + tol or a["lo"] - tol <= b["axis_pos"] <= a["hi"] + tol:
                if b["lo"] - tol <= a["axis_pos"] <= b["hi"] + tol and a["lo"] - tol <= b["axis_pos"] <= a["hi"] + tol:
                    a["intersections"].append(b["wall_id"])


def _dims_pt(dims_px: list[dict], px: float) -> list[dict]:
    out = []
    for d in dims_px or []:
        o = d.get("orientation")
        p1, p2 = (d["x1"] / px, d["y1"] / px), (d["x2"] / px, d["y2"] / px)
        if (o == "h" and p1[0] > p2[0]) or (o == "v" and p1[1] > p2[1]):
            p1, p2 = p2, p1
        out.append({"orientation": o, "p1": p1, "p2": p2, "value_m": d.get("value_m"), "raw_text": d.get("raw_text"),
                    "index": d.get("index"), "px": d})
    return out


def _hit(pos: float, walls: list[dict], ppm: float, orient_wall: str):
    """Extrémité de cote → (wall, 'face_1'|'face_2'|'axis') le plus proche (≤ FACE_TOL) parmi les murs d'orientation donnée."""
    best = None
    for w in walls:
        if w["orientation"] != orient_wall:
            continue
        for kind, p in (("face_1", w["pos_1"]), ("face_2", w["pos_2"]), ("axis", w["axis_pos"])):
            gap = abs(pos - p)
            if gap <= FACE_TOL_M * ppm and (best is None or gap < best[2]):
                best = (w, kind, gap)
    return best


def classify_cotes(dims: list[dict], walls: list[dict], ppm: float) -> list[dict]:
    """Type de référence de chaque cote écrite : nu/nu intérieur, nu/nu extérieur, axe/axe, axe/nu, épaisseur, cumulée…"""
    out = []
    for d in dims:
        along = 0 if d["orientation"] == "h" else 1
        wall_o = "vertical" if d["orientation"] == "h" else "horizontal"
        a, b = _hit(d["p1"][along], walls, ppm, wall_o), _hit(d["p2"][along], walls, ppm, wall_o)
        ref, wa, wb = "unresolved", None, None
        if a and b:
            wa, wb = a[0], b[0]
            crossed = [w for w in walls if w is not wa and w is not wb and w["orientation"] == wall_o
                       and d["p1"][along] + 1 < w["axis_pos"] < d["p2"][along] - 1
                       and _overlap(max(wa["lo"], wb["lo"]), min(wa["hi"], wb["hi"]), w["lo"], w["hi"]) > 0]
            if wa is wb:
                ref = "wall_thickness" if {a[1], b[1]} == {"face_1", "face_2"} else "axis_to_face"
            elif a[1] == "axis" and b[1] == "axis":
                ref = "axis_to_axis"
            elif "axis" in (a[1], b[1]):
                ref = "axis_to_face"
            elif crossed:
                ref = "outside_face_to_outside_face" if (a[1], b[1]) == ("face_1", "face_2") else "cumulative"
            elif a[1] == "face_2" and b[1] == "face_1":
                ref = "inside_face_to_inside_face"
            elif a[1] == "face_1" and b[1] == "face_2":
                ref = "outside_face_to_outside_face"
            else:
                ref = "face_to_face"
            if ref in ("inside_face_to_inside_face", "axis_to_axis", "face_to_face") and crossed:
                ref = "cumulative"
        elif a or b:
            ref = "partial_anchor"
        val = d.get("value_m")
        out.append({"index": d.get("index"), "raw_text": d.get("raw_text"), "orientation": d["orientation"], "value_m": val,
                    "geometric_m": round((d["p2"][along] - d["p1"][along]) / ppm, 4), "reference_type": ref,
                    "from_wall": wa["wall_id"] if wa else None, "from_ref": a[1] if a else None,
                    "to_wall": wb["wall_id"] if wb else None, "to_ref": b[1] if b else None,
                    "p1": d["p1"], "p2": d["p2"]})
    return out


def _bands(walls: list[dict], orient: str, ppm: float) -> list[dict]:
    """Bandes libres entre deux murs parallèles voisins qui se font face (espace entre nus intérieurs)."""
    par = sorted((w for w in walls if w["orientation"] == orient and not w.get("is_post")), key=lambda w: w["pos_1"])
    out = []
    for i, a in enumerate(par):
        for b in par[i + 1:]:
            if b["pos_1"] <= a["pos_2"] + 0.5:
                continue
            ov_lo, ov_hi = max(a["lo"], b["lo"]), min(a["hi"], b["hi"])
            min_ov = 0.06 * ppm if (a.get("is_post") or b.get("is_post")) else MIN_WALL_LEN_M * ppm
            if ov_hi - ov_lo < min_ov:
                continue
            # un mur parallèle intermédiaire couvrant la même emprise → pas voisins (poteaux : seuls d'autres poteaux comptent)
            both_posts = bool(a.get("is_post") and b.get("is_post"))
            if both_posts and abs(a["lo"] - b["lo"]) > 0.03 * ppm:
                continue  # poteaux d'une même file uniquement
            free = [(ov_lo, ov_hi)]
            for obstacle in par:
                if obstacle is a or obstacle is b or not a["pos_2"] < obstacle["axis_pos"] < b["pos_1"]:
                    continue
                remaining = []
                for low, high in free:
                    if _overlap(low, high, obstacle["lo"], obstacle["hi"]) <= 0:
                        remaining.append((low, high))
                    else:
                        if low < obstacle["lo"]: remaining.append((low, obstacle["lo"]))
                        if high > obstacle["hi"]: remaining.append((obstacle["hi"], high))
                free = remaining
            out.extend({"from": a, "to": b, "lo": low, "hi": high}
                       for low, high in free if high - low >= min_ov)
    return out


def interior_measurements(walls: list[dict], cotes: list[dict], ppm: float, px: float) -> list[dict]:
    """Pour chaque espace entre deux murs parallèles voisins : distance nu intérieur → nu intérieur, coordonnées exactes,
    cote écrite correspondante (même référence) et statut."""
    out = []
    for orient, direction, tag in (("vertical", "horizontal", "H"), ("horizontal", "vertical", "V")):
        n = count(1)
        # bandes perpendiculaires : chaque espace est découpé par les murs perpendiculaires (cellules)
        perp_bands = _bands(walls, "horizontal" if orient == "vertical" else "vertical", ppm) or [None]
        for band in _bands(walls, orient, ppm):
            a, b = band["from"], band["to"]
            f1, f2 = a["pos_2"], b["pos_1"]
            span_m = (f2 - f1) / ppm
            if span_m < 0.30:  # pas un espace : double trait, semelle, épaisseur
                continue
            cells = [pb for pb in perp_bands if pb and _overlap(pb["from"]["pos_2"], pb["to"]["pos_1"], band["lo"], band["hi"]) > 0.3 * ppm
                     and pb["lo"] <= f1 + 1 and pb["hi"] >= f2 - 1] or [None]
            for cell in cells:
                c_lo, c_hi = (cell["from"]["pos_2"], cell["to"]["pos_1"]) if cell else (band["lo"], band["hi"])
                c_lo, c_hi = max(c_lo, band["lo"]), min(c_hi, band["hi"])
                if c_hi - c_lo < 0.2 * ppm:
                    continue
                mid = (c_lo + c_hi) / 2
                written = None
                for c in cotes:
                    if c["orientation"] != ("h" if direction == "horizontal" else "v"):
                        continue
                    if c["reference_type"] != "inside_face_to_inside_face" or c["from_wall"] != a["wall_id"] or c["to_wall"] != b["wall_id"]:
                        continue
                    along = 0 if direction == "horizontal" else 1
                    if abs(c["p1"][along] - f1) <= FACE_TOL_M * ppm and abs(c["p2"][along] - f2) <= FACE_TOL_M * ppm:
                        perp = c["p1"][1 - along]
                        d = 0 if c_lo <= perp <= c_hi else min(abs(perp - c_lo), abs(perp - c_hi))
                        if written is None or d < written[1]:
                            written = (c, d)
                axis_cote = next((c for c in cotes if c["reference_type"] == "axis_to_axis" and c["from_wall"] == a["wall_id"]
                                  and c["to_wall"] == b["wall_id"]), None)
                conf = min(a["confidence"], b["confidence"])
                w_m = written[0]["value_m"] if written else None
                diff = round(w_m - span_m, 4) if w_m is not None else None
                if a["ambiguous"] or b["ambiguous"]:
                    status = "to_confirm"
                elif w_m is not None:
                    status = "confirmed" if abs(diff) <= CONFIRM_TOL_M else "to_confirm"
                    conf = min(0.98, conf + 0.2) if status == "confirmed" else conf * 0.7
                else:
                    status = "probable"
                seg = ((f1, mid), (f2, mid)) if direction == "horizontal" else ((mid, f1), (mid, f2))
                out.append({"measurement_id": f"INT-{tag}-{next(n):03d}", "direction": direction,
                            "from_wall": a["wall_id"], "from_face": "interior_right" if direction == "horizontal" else "interior_bottom",
                            "to_wall": b["wall_id"], "to_face": "interior_left" if direction == "horizontal" else "interior_top",
                            "reference_type": "inside_face_to_inside_face", "written_dimension_m": w_m,
                            "written_cote_index": written[0]["index"] if written else None,
                            "axis_cote_m": axis_cote["value_m"] if axis_cote else None,
                            "geometric_dimension_m": round(span_m, 4), "difference_m": diff,
                            "coordinates": {"x1": round(seg[0][0] * px, 2), "y1": round(seg[0][1] * px, 2),
                                            "x2": round(seg[1][0] * px, 2), "y2": round(seg[1][1] * px, 2)},
                            "zone": {"lo": round(c_lo * px, 1), "hi": round(c_hi * px, 1)},
                            "cell_bounds_px": ([round(v * px, 1) for v in
                                                ((f1, c_lo, f2, c_hi) if direction == "horizontal" else (c_lo, f1, c_hi, f2))]
                                               if cell else None),
                            "status": status, "confidence": round(conf, 2)})
    return out


def cell_coverage(measurements: list[dict]) -> dict:
    cells = {}
    for m in measurements:
        if not m.get("cell_bounds_px"):
            continue
        key = tuple(m["cell_bounds_px"])
        cells.setdefault(key, []).append(m)
    rows = []
    for i, (bounds, ms) in enumerate(sorted(cells.items()), 1):
        directions = {m["direction"] for m in ms}
        rows.append({"cell_id": f"CELL-{i:03d}", "bounds_px": list(bounds),
                     "measurement_ids": [m["measurement_id"] for m in ms],
                     "both_directions": directions == {"horizontal", "vertical"},
                     "confirmed": directions == {"horizontal", "vertical"} and all(m["status"] == "confirmed" for m in ms)})
    return {"scope": "detected_rectangular_cells", "cells": rows, "detected": len(rows),
            "with_both_directions": sum(c["both_directions"] for c in rows),
            "confirmed": sum(c["confirmed"] for c in rows)}


def closure_equations(walls: list[dict], cotes: list[dict], ppm: float) -> list[dict]:
    """Par rangée : mur ext. + travée + refend + … + mur ext. = cote extérieure écrite correspondante."""
    out = []
    for orient, direction in (("vertical", "horizontal"), ("horizontal", "vertical")):
        par = sorted((w for w in walls if w["orientation"] == orient), key=lambda w: w["pos_1"])
        if len(par) < 2:
            continue
        # rangées = bandes perpendiculaires (entre murs perpendiculaires voisins) ; sinon une seule rangée
        rows = _bands(walls, "horizontal" if orient == "vertical" else "vertical", ppm) or [None]
        for r_i, row in enumerate(rows, 1):
            lo, hi = (row["from"]["pos_2"], row["to"]["pos_1"]) if row else (min(w["lo"] for w in par), max(w["hi"] for w in par))
            seq = [w for w in par if _overlap(w["lo"], w["hi"], lo, hi) >= 0.5 * (hi - lo)]
            if len(seq) < 2:
                continue
            terms, total = [], 0.0
            for i, w in enumerate(seq):
                terms.append({"kind": "wall", "wall_id": w["wall_id"], "value_m": w["thickness_m"]})
                total += w["thickness_m"]
                if i + 1 < len(seq):
                    span = (seq[i + 1]["pos_1"] - w["pos_2"]) / ppm
                    terms.append({"kind": "span", "from_wall": w["wall_id"], "to_wall": seq[i + 1]["wall_id"], "value_m": round(span, 4)})
                    total += span
            if any(t["kind"] == "span" and t["value_m"] < 0.05 for t in terms):
                continue  # murs qui se chevauchent / doubles traits : pas une rangée exploitable
            ext_a, ext_b = seq[0]["pos_1"], seq[-1]["pos_2"]
            along = 0 if direction == "horizontal" else 1
            ext = [c for c in cotes if c["orientation"] == ("h" if direction == "horizontal" else "v")
                   and abs(c["p1"][along] - ext_a) <= FACE_TOL_M * ppm and abs(c["p2"][along] - ext_b) <= FACE_TOL_M * ppm]
            ext_val = ext[0]["value_m"] if ext else None
            geo_total = (ext_b - ext_a) / ppm
            diff = round(ext_val - total, 4) if ext_val is not None else None
            out.append({"row_id": f"ROW-{'H' if direction == 'horizontal' else 'V'}-{r_i:02d}", "direction": direction,
                        "walls_count": len(seq), "spans_count": len(seq) - 1, "terms": terms, "sum_m": round(total, 4),
                        "geometric_exterior_m": round(geo_total, 4), "written_exterior_m": ext_val,
                        "written_cote_index": ext[0]["index"] if ext else None, "difference_m": diff,
                        "status": "not_compared" if ext_val is None else ("closed" if abs(diff) <= CONFIRM_TOL_M else "open")})
    return out


def validate(result: dict) -> dict:
    """Conditions bloquantes : l'analyse ne peut être « terminée » que si tout est établi."""
    walls, meas, rows, cotes = result["walls"], result["interior_measurements"], result["closure_equations"], result["cotes"]
    fails = []
    if not walls:
        fails.append("nombre de murs détectés non établi")
    if walls and not any(w["ambiguous"] is False for w in walls):
        fails.append("faces des murs intérieurs non détectées")
    if not meas:
        fails.append("aucune dimension intérieure mur à mur produite")
    for d, lbl in (("horizontal", "chaînes horizontales incomplètes"), ("vertical", "chaînes verticales incomplètes")):
        rs = [r for r in rows if r["direction"] == d]
        if not rs or any(r["status"] == "open" for r in rs):
            fails.append(lbl)
    ambiguous = [c for c in cotes if c["reference_type"] in ("unresolved", "partial_anchor")]
    if len(ambiguous) >= 4 or (cotes and len(ambiguous) > 0.5 * len(cotes)):
        fails.append(f"association ambiguë entre texte et segment ({len(ambiguous)} cote(s))")
    bad = [c for c in cotes if c["value_m"] is not None and c["reference_type"] not in ("unresolved", "partial_anchor")
           and abs(c["value_m"] - c["geometric_m"]) > 0.03]
    if len(bad) >= 4:
        fails.append(f"quatre mauvaises associations ou plus ({len(bad)})")
    if any(r["status"] == "not_compared" for r in rows):
        fails.append("somme des travées et murs non comparée à la cote extérieure")
    if meas and all(m["status"] != "confirmed" for m in meas):
        fails.append("aucune dimension intérieure confirmée par une cote écrite")
    pending = [m for m in meas if m.get("status") != "confirmed"]
    if pending:
        fails.append(f"dimensions intérieures non confirmées ({len(pending)})")
    for direction in ("horizontal", "vertical"):
        if not any(m.get("direction") == direction for m in meas):
            fails.append(f"aucune mesure intérieure {direction}e")
    coverage = result.get("coverage") or cell_coverage(meas)
    if not coverage["detected"] or coverage["with_both_directions"] != coverage["detected"]:
        fails.append("couverture des cellules détectées non établie dans les deux directions")
    if any(w.get("ambiguous") for w in walls):
        fails.append("paires de faces ambiguës à confirmer")
    if any(w.get("ouvrage_class") in ("Poutre", "Semelle filante", "Longrine", "Poteau béton") for w in walls):
        fails.append("des contours d'ouvrages structurels demandent confirmation avant identification comme murs")
    return {"complete": not fails, "failed_checks": fails, "message": None if not fails else INCOMPLETE_MSG}


def analyze_walls(vectors: list[dict], dims_px: list[dict], text_blocks: list[dict], ppm: float, px_per_pt: float,
                  segments: dict | None = None, page_size_px: tuple | None = None) -> dict:
    """Pipeline complet géométrie → cotations → rapprochement (sans IA). `segments` = {hs, vs} déjà fusionnés (réanalyse)."""
    if not ppm or not math.isfinite(ppm) or ppm <= 0 or not px_per_pt or not math.isfinite(px_per_pt) or px_per_pt <= 0:
        return {"walls": [], "interior_measurements": [], "closure_equations": [], "cotes": [], "sections_ignored": [],
                "engine_version": 2, "posts": [], "coverage": cell_coverage([]),
                "stats": {"walls": 0, "walls_ambiguous": 0, "measurements": 0, "confirmed": 0, "to_confirm": 0, "rows": 0, "rows_closed": 0},
                "validation": {"complete": False, "failed_checks": ["échelle inconnue"], "message": INCOMPLETE_MSG}}
    hs, vs = (segments["hs"], segments["vs"]) if segments else merged_lines(vectors)
    hs, vs = [tuple(x) for x in hs], [tuple(x) for x in vs]
    source_hs, source_vs = hs, vs
    dims = _dims_pt(dims_px, px_per_pt)
    def object_lines(lines, orientation):
        along = 0 if orientation == "h" else 1
        cote_lines = [(d["p1"][1-along], d["p1"][along], d["p2"][along]) for d in dims if d["orientation"] == orientation]
        return [ln for ln in lines if not any(abs(ln[0] - p) < .2 and _overlap(ln[1], ln[2], lo, hi) > .5 * min(ln[2]-ln[1], hi-lo)
                                             for p, lo, hi in cote_lines)]
    # Les longues lignes de cotation périphériques ne sont pas des ouvrages.
    hs, vs = object_lines(hs, "h"), object_lines(vs, "v")
    thick = [d for d in dims if d.get("value_m") and MIN_T_M <= d["value_m"] <= MAX_T_M]
    bbox = None
    if dims:
        xs = [p[0] for d in dims for p in (d["p1"], d["p2"])]
        ys = [p[1] for d in dims for p in (d["p1"], d["p2"])]
        m = 0.5 * ppm
        bbox = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)
    walls = detect_walls(hs, vs, ppm, thick, bbox)
    contour_vectors = segments.get("contour_vectors", []) if segments else [v for v in vectors if v.get("type") in ("rect", "quad")]
    contours = closed_bands(contour_vectors, ppm, bbox)
    # Un axe intérieur ne doit pas découper un contour fermé en faux demi-murs.
    walls = contours + [w for w in walls if not any(c["orientation"] == w["orientation"]
                       and _overlap(c["pos_1"], c["pos_2"], w["pos_1"], w["pos_2"]) > .5 * min(c["pos_2"] - c["pos_1"], w["pos_2"] - w["pos_1"])
                       and _overlap(c["lo"], c["hi"], w["lo"], w["hi"]) > .5 * min(c["hi"] - c["lo"], w["hi"] - w["lo"])
                       for c in contours)]
    walls.sort(key=lambda w: (w["orientation"], w["pos_1"], w["lo"]))
    for idx, w in enumerate(walls, 1): w["wall_id"] = f"M{idx:02d}"
    posts = detect_posts(hs, vs, ppm, text_blocks or [], px_per_pt)
    nxt = len(walls) + 1
    for w in posts:
        w["wall_id"] = f"M{nxt:02d}"
        nxt += 1
    # Les faces de poteaux restent des appuis, pas des refends de locaux.
    # Garder les faces mesurées : les déplacer vers les cotes à vérifier
    # effaçait artificiellement les écarts allant jusqu'à 3 cm.
    _intersections(walls, ppm)
    from engines.plan_symbols import extract_legend, label_walls
    label_walls([w for w in walls if not w.get("is_post")], text_blocks or [], px_per_pt, ppm)
    W = (page_size_px[0] / px_per_pt, page_size_px[1] / px_per_pt) if page_size_px else (
        max([t["x"] + t.get("w", 0) for t in text_blocks or []] or [1]),
        max([t["y"] + t.get("h", 0) for t in text_blocks or []] or [1]))
    legend = extract_legend(text_blocks or [], *W)
    cotes = classify_cotes(dims, walls, ppm)
    meas = interior_measurements(walls, cotes, ppm, px_per_pt)
    rows = closure_equations(walls, cotes, ppm)
    sections = [t["text"] for t in text_blocks or [] if _SECTION_RE.match((t.get("text") or "").strip())]
    from engines.plan_chains import peripheral_chains
    peripheral = peripheral_chains(dims, ppm)
    result = {"walls": [_wall_json(w, ppm, px_per_pt) for w in walls], "interior_measurements": meas, "closure_equations": rows,
              "cotes": [{k: v for k, v in c.items() if k not in ("p1", "p2")} for c in cotes],
              "sections_ignored": sorted(set(sections)), "pt_per_m": round(ppm, 4), "px_per_pt": round(px_per_pt, 5),
              "posts": [_wall_json(w, ppm, px_per_pt) for w in posts], "engine_version": 2,
              "peripheral": peripheral, "legend": legend,
              "stats": {"walls": len(walls), "walls_ambiguous": sum(1 for w in walls if w["ambiguous"]), "measurements": len(meas),
                        "confirmed": sum(1 for m in meas if m["status"] == "confirmed"),
                        "to_confirm": sum(1 for m in meas if m["status"] == "to_confirm"), "rows": len(rows),
                        "rows_closed": sum(1 for r in rows if r["status"] == "closed")}}
    # Garder les sources en points, avant filtrage par cotes ou calibration :
    # un recalcul doit pouvoir reproduire une extraction fraîche.
    result["segments"] = {"contour_vectors": contour_vectors,
                          "hs": [list(x) for x in source_hs], "vs": [list(x) for x in source_vs]}
    result["coverage"] = cell_coverage(meas)
    result["validation"] = validate(result)
    return result
