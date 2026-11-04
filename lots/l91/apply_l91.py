"""Lot 91 (FR + PT) — métré DWG : murs comptés ×2,4 ; dalle à contours ouverts non mesurée.

Constat : mesure manuelle réelle du fondateur sur R+2.dwg (coffrage, < 2 % d'erreur) : murs façade 397,44 + intérieurs
583,15 = 980,6 ml ; dalle 2 348,8 m² (périmètre 390,5 m). La plateforme donnait 2 360,8 ml (+141 %) et une dalle
« à mesurer ». Cause : chaque mur est tracé sur deux calques (« Murs » et « Murs coupé ») avec des traits répétés ;
la somme brute ÷ 2 comptait tout deux à quatre fois.
Correctif (après le calcul existant, ne s'active que si les calques le permettent) :
1. Murs : quand un calque mur « coupé » coexiste avec son jumeau non coupé, seuls les murs COUPÉS (ceux du niveau)
   sont comptés, et la longueur d'axe est mesurée par paires de traits parallèles écartés d'une épaisseur de mur
   (8 à 45 cm), recouvrement compté une fois → 954,7 ml (−2,6 %).
2. Dalle tracée en lignes ouvertes : contours refermés (tolérance 5 cm), somme des panneaux fermés de taille
   significative (≥ 2 % de l'emprise) → 2 418,9 m² (+3,0 %), statut « contours_reconstitues » (estimation).
Usage : python3 lots/l91/apply_l91.py <racine /app>   (idempotent ; requiert Lot 87 ; ARRÊT sinon)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "dxf_takeoff.py"
s = f.read_text(encoding="utf-8")
if "Lot 91" in s:
    print("déjà appliqué"); print("L91 OK"); sys.exit(0)
if "Lot 87" not in s or "def extract_structural_metre(doc, unit_to_m: float) -> dict:" not in s:
    print("Lot 87 absent — ARRÊT, rien écrit"); sys.exit(1)
ADD = r'''


# ── Lot 91 : murs « coupés » mesurés par paires de traits ; dalle ouverte refermée ─────────────────────────────
def _l91_lines(doc, pred):
    out = []
    for e in doc.modelspace():
        try:
            lay = (e.dxf.layer or "")
            if not pred(lay):
                continue
            t = e.dxftype()
            if t == "LINE":
                out.append(((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)))
            elif t == "LWPOLYLINE":
                pts = [(p[0], p[1]) for p in e.get_points()]
                if e.closed and pts:
                    pts.append(pts[0])
                out.extend(zip(pts, pts[1:]))
        except Exception:  # noqa: BLE001 — entité illisible ignorée
            continue
    return [s for s in out if s[0] != s[1]]


def _l91_wall_axis_m(segs, unit_to_m, tmin=0.08, tmax=0.45, ang_tol_deg=3.0):
    import math
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    u = unary_union([LineString(x) for x in segs])
    lines = [g for g in (u.geoms if hasattr(u, "geoms") else [u]) if g.length > 0]
    if not lines:
        return 0.0
    tree = STRtree(lines)
    lo, hi = tmin / unit_to_m, tmax / unit_to_m
    sin_tol = math.sin(math.radians(ang_tol_deg))
    total = 0.0
    for i, a in enumerate(lines):
        (x1, y1), (x2, y2) = a.coords[0], a.coords[-1]
        la = a.length
        ux, uy = (x2 - x1) / la, (y2 - y1) / la
        for j in tree.query(a.buffer(hi)):
            j = int(j)
            if j <= i:
                continue
            b = lines[j]
            (p1, q1), (p2, q2) = b.coords[0], b.coords[-1]
            lb = b.length
            vx, vy = (p2 - p1) / lb, (q2 - q1) / lb
            if abs(ux * vy - uy * vx) > sin_tol:
                continue
            d = abs((p1 - x1) * uy - (q1 - y1) * ux)
            if not lo <= d <= hi:
                continue
            t1 = (p1 - x1) * ux + (q1 - y1) * uy
            t2 = (p2 - x1) * ux + (q2 - y1) * uy
            ov = min(la, max(t1, t2)) - max(0.0, min(t1, t2))
            if ov > 0:
                total += ov
    return total * unit_to_m


def _l91_slab_from_lines(segs, unit_to_m, tol_m=0.05, min_share=0.02):
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    if len(segs) < 20:
        return None
    b = tol_m / unit_to_m
    u = unary_union([LineString(x).buffer(b) for x in segs])
    polys = list(u.geoms) if hasattr(u, "geoms") else [u]
    if not polys:
        return None
    ext = sum(Polygon(p.exterior).area for p in polys)
    panels = [Polygon(r).area for p in polys for r in p.interiors if Polygon(r).area >= min_share * ext]
    if not panels:
        return None
    k = unit_to_m * unit_to_m
    main = max(polys, key=lambda p: Polygon(p.exterior).area)
    return {"slab_area_m2": round(sum(panels) * k, 1), "panels": len(panels),
            "outline_perimeter_m": round(main.exterior.length * unit_to_m, 1)}


_extract_structural_metre_l91_base = extract_structural_metre


def extract_structural_metre(doc, unit_to_m: float) -> dict:
    res = _extract_structural_metre_l91_base(doc, unit_to_m)
    try:
        names = {(L.dxf.name or "") for L in doc.layers}
        low = {n.lower(): n for n in names}
        cut = [n for n in names if "mur" in n.lower() and "coup" in n.lower()]
        twins = [c for c in cut if any(k != c.lower() and k.replace(" ", "") == c.lower().replace("coupé", "").replace("coupe", "").replace(" ", "").rstrip("-_")
                                       for k in low)]
        if twins:
            segs = _l91_lines(doc, lambda lay: lay in twins)
            axis = _l91_wall_axis_m(segs, unit_to_m)
            if axis > 0:
                res["walls_ml_raw"] = res.get("walls_ml")
                res["walls_ml"] = round(axis, 1)
                res["walls_method"] = "murs_coupes_par_paires"
                res["walls_note"] = ("Murs du niveau (calques « coupé ») mesurés à l'axe entre leurs deux traits ; "
                                     "les murs vus / doublons sont exclus.")
        if res.get("slab_status") == "contours_ouverts":
            slab = _l91_slab_from_lines(_l91_lines(doc, lambda lay: "dalle" in lay.lower() or "slab" in lay.lower()), unit_to_m)
            if slab:
                res["slab_area_m2"] = slab["slab_area_m2"]
                res["slab_status"] = "contours_reconstitues"
                res["slab_outline_perimeter_m"] = slab["outline_perimeter_m"]
                res["slab_note"] = ("Dalle tracée en lignes ouvertes : contours refermés (tolérance 5 cm), "
                                    f"{slab['panels']} panneau(x) — estimation à vérifier.")
    except Exception:  # noqa: BLE001 — en cas d'échec, le métré historique reste valable
        pass
    return res
'''
f.write_text(s.rstrip("\n") + "\n" + ADD.replace("Lot 91 :", "Lot 91 :"), encoding="utf-8")
(root / "backend" / "tests" / "test_l91.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l91.py").read_bytes())
print("ok backend/engines/dxf_takeoff.py + backend/tests/test_l91.py")
print("L91 OK")
