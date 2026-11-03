"""Lot 54 — métré DWG/DXF de coffrage : quantités réelles par éléments fermés (calques BET).

Test réel (plan AES « coffrage PH R+1 », comparé au métré de référence du fondateur) :
                     avant      après (ce lot)   référence
  dalles (m²)        1 077      1 129            1 129
  voiles (ml)        1 650      ~290             279
  poutres (ml)       1 039      ~310             227
  poteaux (u)        74         48               48
Causes : (1) le fond de plan de l'architecte (calques ArchiCAD « 01-Murs… _Stylo_No_ ») compté en
plus des calques BET ; (2) les traits « cachés » (murs de l'étage du dessus) comptés ; (3) longueur
« traits / 2 » au lieu des éléments fermés ; (4) poteaux coupés en deux par leur hachure comptés 2 fois.

Méthode ajoutée : si le plan a des calques BET normalisés (A-WALL, A-FLOR, S-BEAM, S-COLS…), chaque
élément est reconstruit en polygone fermé (traits continus seulement) ; voile/poutre = surface ÷ épaisseur
mesurée ; poteau = section fermée ≥ 10 cm ; dalle = panneau fermé. Sinon l'ancienne méthode est gardée.

Usage : python3 lots/l54/apply_l54.py <racine /app>   (idempotent)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "dxf_takeoff.py"
s = f.read_text(encoding="utf-8")
if "Lot 54" in s:
    print("déjà appliqué"); print("L54 OK"); sys.exit(0)
if "def extract_structural_metre(doc, unit_to_m: float) -> dict:" not in s:
    print("ANCRE extract_structural_metre introuvable — ARRÊT, rien écrit"); sys.exit(1)

ADD = r'''


# --- Lot 54 : métré par éléments fermés sur les calques BET normalisés ---------------------------
_BET_LAYERS = {
    "wall": ("a-wall", "s-wall", "s-cwal"),
    "slab": ("a-flor", "s-flor", "s-slab"),
    "beam": ("s-beam",),
    "col": ("s-cols", "s-col"),
}
_HIDDEN_LT = ("cach", "hidden", "dash", "tiret", "pointill", "axe", "center")


def _bet_kind(layer: str):
    low = (layer or "").strip().lower()
    for kind, names in _BET_LAYERS.items():
        if low in names:
            return kind
    return None


def _bet_polygon_metre(doc, unit_to_m: float):
    """Quantités par polygones fermés sur les calques BET (traits continus uniquement)."""
    import statistics
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    from engines.cad_geometry import walk_entities
    U = unit_to_m
    segs = {k: [] for k in _BET_LAYERS}

    def add(kind, pts):
        for a, b in zip(pts, pts[1:]):
            a2 = (round(a[0] * U, 3), round(a[1] * U, 3))
            b2 = (round(b[0] * U, 3), round(b[1] * U, 3))
            if a2 != b2:
                segs[kind].append(LineString([a2, b2]))

    for e in walk_entities(doc, doc.modelspace(), explode_dimensions=False, preserve_blocks=lambda i, l: False):
        kind = _bet_kind(getattr(e.dxf, "layer", ""))
        if not kind:
            continue
        lt = (e.dxf.get("linetype", "") or "").lower()
        if any(h in lt for h in _HIDDEN_LT):
            continue  # traits cachés / axes : éléments d'un autre niveau, non métrés
        t = e.dxftype()
        if t == "LINE":
            add(kind, [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)])
        elif t == "LWPOLYLINE":
            pts = [(p[0], p[1]) for p in e.get_points("xy")]
            if e.closed and pts:
                pts.append(pts[0])
            add(kind, pts)
    if not segs["wall"] and not segs["slab"]:
        return None

    def polys(kind):
        if not segs[kind]:
            return []
        return [p for p in polygonize(unary_union(segs[kind])) if p.area > 1e-4]

    def dims(p):
        r = p.minimum_rotated_rectangle
        c = list(r.exterior.coords)
        import math
        a, b = math.dist(c[0], c[1]), math.dist(c[1], c[2])
        return min(a, b), max(a, b)

    out = {}
    walls = []
    for p in polys("wall"):
        t, l = dims(p)
        if 0.15 <= t <= 0.40 and l >= 0.30:
            walls.append((p.area / t, t, p.area))
    slabs = [p.area for p in polys("slab") if p.area >= 1.0]
    beams = []
    for p in polys("beam"):
        t, l = dims(p)
        if 0.10 <= t <= 0.70 and l >= 0.50:
            beams.append((p.area / t, t, p.area))
    cols = []
    merged = unary_union(polys("col")) if segs["col"] else None  # poteau coupé par sa hachure → une seule section
    col_polys = [] if merged is None or merged.is_empty else list(getattr(merged, "geoms", [merged]))
    for p in col_polys:
        t, l = dims(p)
        if 0.10 <= t <= 2.0 and l <= 2.0:
            cols.append((t, l, p.area))
    if walls:
        out.update(walls_ml=round(sum(w[0] for w in walls), 1), wall_area_m2=round(sum(w[2] for w in walls), 2),
                   partitions_ml=0.0, partition_area_m2=0.0, wall_source="polygones_bet",
                   wall_elements=len(walls), wall_thickness_m=round(statistics.median(w[1] for w in walls), 3))
    if slabs:
        out.update(slab_area_m2=round(sum(slabs), 1), slab_panels=len(slabs))
    if beams:
        out.update(beams_ml=round(sum(b[0] for b in beams), 1), beam_area_m2=round(sum(b[2] for b in beams), 2),
                   beam_elements=len(beams), beam_w_m=round(statistics.median(b[1] for b in beams), 3))
    if cols:
        out.update(columns_count=len(cols), col_area_m2=round(sum(c[2] for c in cols), 3),
                   col_sections=[{"w_cm": round(c[0] * 100), "h_cm": round(c[1] * 100)} for c in cols[:400]])
    return out or None


_extract_structural_metre_lot54_base = extract_structural_metre


def extract_structural_metre(doc, unit_to_m: float) -> dict:
    res = _extract_structural_metre_lot54_base(doc, unit_to_m)
    try:
        poly = _bet_polygon_metre(doc, unit_to_m)
    except Exception:  # noqa: BLE001 — la méthode historique reste disponible
        poly = None
    if not poly:
        return res
    det = dict(res.get("detected") or {})
    for k_src, k_det in (("wall_area_m2", "wall_area_m2"), ("beam_area_m2", "beam_area_m2"), ("col_area_m2", "col_area_m2"),
                         ("wall_thickness_m", "wall_thickness_m"), ("beam_w_m", "beam_w_m"), ("col_sections", "col_sections")):
        if k_src in poly:
            det[k_det] = poly[k_src]
    if "partition_area_m2" in poly:
        det["partition_area_m2"] = 0.0
    keep = {k: v for k, v in poly.items() if k not in ("col_sections", "wall_thickness_m", "beam_w_m")}
    res.update(keep)
    res["detected"] = det
    res["method"] = "polygones_calques_bet"
    res["method_note"] = ("Quantités lues par éléments fermés sur les calques BET (traits continus) ; "
                          "fond de plan architecte et traits cachés exclus.")
    return res
'''
f.write_text(s.rstrip("\n") + "\n" + ADD, encoding="utf-8")
t = pathlib.Path(__file__).resolve().parent / "tests" / "test_l54.py"
(root / "backend" / "tests" / "test_l54.py").write_bytes(t.read_bytes())
print("ok backend/engines/dxf_takeoff.py + backend/tests/test_l54.py")
print("L54 OK")
