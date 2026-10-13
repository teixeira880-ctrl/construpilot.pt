"""Completion of wall bodies that do not close in the DXF: two parallel native lines of the wall layer, at a distance equal to one of the
wall thicknesses READ on the sections (± 1 cm), with overlapping extents, bound one wall body. Bodies are unioned with the closed faces
so nothing is counted twice; lines without a parallel partner are listed, never summed."""
import math
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union
from shapely.strtree import STRtree

from engines.metre.coffrage_dxf import _lines

ANGLE_TOL_DEG = 1.0
THICK_TOL_M = 0.012
MIN_OVERLAP_M = 0.30


def _segments(lines: list[LineString]) -> list[tuple]:
    segs = []
    for ls in lines:
        c = list(ls.coords)
        for a, b in zip(c, c[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            if L >= 0.05:
                segs.append((a, b, L))
    return segs


def _pair_rect(s1, s2, thicknesses):
    (a1, b1, L1), (a2, b2, L2) = s1, s2
    ux, uy = (b1[0] - a1[0]) / L1, (b1[1] - a1[1]) / L1
    vx, vy = (b2[0] - a2[0]) / L2, (b2[1] - a2[1]) / L2
    if abs(ux * vx + uy * vy) < math.cos(math.radians(ANGLE_TOL_DEG)):
        return None
    d = abs((a2[0] - a1[0]) * uy - (a2[1] - a1[1]) * ux)
    t = next((th for th in thicknesses if abs(d - th) <= THICK_TOL_M), None)
    if t is None:
        return None
    p1 = sorted((0.0, L1))
    p2 = sorted(((a2[0] - a1[0]) * ux + (a2[1] - a1[1]) * uy, (b2[0] - a1[0]) * ux + (b2[1] - a1[1]) * uy))
    lo, hi = max(p1[0], p2[0]), min(p1[1], p2[1])
    if hi - lo < MIN_OVERLAP_M:
        return None
    nx, ny = -uy, ux
    side = 1 if (a2[0] - a1[0]) * nx + (a2[1] - a1[1]) * ny > 0 else -1
    pts = [(a1[0] + lo * ux, a1[1] + lo * uy), (a1[0] + hi * ux, a1[1] + hi * uy)]
    pts += [(pts[1][0] + side * d * nx, pts[1][1] + side * d * ny), (pts[0][0] + side * d * nx, pts[0][1] + side * d * ny)]
    return {"poly": Polygon(pts), "length_m": hi - lo, "thickness_m": d, "class_m": t}


def complete_walls(msp, wall_layers: set[str], unit_to_m: float, thicknesses_cm: list[float], closed_faces: list[Polygon]) -> dict:
    thicknesses = sorted({round(t / 100, 3) for t in thicknesses_cm if t})
    segs = _segments(_lines(msp, wall_layers, unit_to_m))
    geoms = [LineString([a, b]) for a, b, _ in segs]
    tree = STRtree(geoms)
    rects, paired = [], set()
    reach = (max(thicknesses) if thicknesses else 0) + THICK_TOL_M
    for i, s in enumerate(segs):
        for j in tree.query(geoms[i].buffer(reach)):
            j = int(j)
            if j <= i:
                continue
            r = _pair_rect(s, segs[j], thicknesses)
            if r:
                rects.append(r); paired.update((i, j))
    closed_union = unary_union(closed_faces) if closed_faces else Polygon()
    bodies, added = list(closed_faces), {}
    body_tree = [closed_union] if closed_faces else []
    for r in sorted(rects, key=lambda r: -r["length_m"]):
        overlap = [g for g in body_tree if g.intersects(r["poly"])]
        new = r["poly"].difference(unary_union(overlap)) if overlap else r["poly"]
        if new.area < 0.005:
            continue
        for piece in (new.geoms if hasattr(new, "geoms") else [new]):
            if piece.area >= 0.005:
                bodies.append(piece)
        body_tree.append(r["poly"])
        k = f"{round(r['class_m'] * 100)} cm"
        a = added.setdefault(k, {"length_m": 0.0, "plan_area_m2": 0.0, "bodies": 0})
        a["length_m"] += new.area / r["class_m"]; a["plan_area_m2"] += new.area; a["bodies"] += 1
    added = {k: {"length_m": round(v["length_m"], 2), "plan_area_m2": round(v["plan_area_m2"], 3), "bodies": v["bodies"]} for k, v in added.items()}
    acc_area = sum(b.area for b in bodies)
    unpaired = [segs[i] for i in range(len(segs)) if i not in paired]
    unpaired_len = sum(s[2] for s in unpaired)
    return {"thicknesses_used_cm": [round(t * 100) for t in thicknesses], "segments_total": len(segs), "segments_paired": len(paired),
            "added_by_thickness": added, "added_length_m": round(sum(v["length_m"] for v in added.values()), 2),
            "added_plan_area_m2": round(acc_area - closed_union.area, 3), "union_plan_area_m2": round(acc_area, 3), "bodies": bodies,
            "unpaired": {"count": len(unpaired), "length_m": round(unpaired_len, 2),
                         "note": "lignes du calque murs sans parallèle à une épaisseur lue sur les coupes : non comptées (bords de trémies, tracés, murs d'une épaisseur non lue ?)"},
            "note": "Corps de murs = deux lignes natives parallèles à une épaisseur lue sur les coupes (±1 cm), union avec les faces fermées ; aucun trait isolé n'est compté."}
