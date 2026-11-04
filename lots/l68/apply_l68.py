"""Lot 68 — métré DWG de coffrage : la vue 3D (et les autres vues hors plan) n'est plus comptée.

Test réel (plan AES « coffrage PH R+1 ») : le DXF contient le plan ET une vue 3D isométrique à ~400 m, dessinée
sur les mêmes calques BET (S-BEAM, A-WALL, S-COLS). Elle ajoutait 16 poutres / 28,7 ml et 21 voiles / 15,5 ml.
Correctif (engines/dxf_takeoff.py, méthode polygones BET du Lot 54) : seuls les éléments situés dans le dessin
principal (groupe des dalles A-FLOR le plus étendu, marge 8 m) sont métrés. Voiles 292 → 276,6 ml
(référence 278,6) ; dalles 1 129,3 m² et poteaux 48 inchangés.
Usage : python3 lots/l68/apply_l68.py <racine /app>   (FR + PT ; idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "dxf_takeoff.py"
s = f.read_text(encoding="utf-8")
if "Lot 68" in s:
    print("déjà appliqué"); print("L68 OK"); sys.exit(0)
OLD = ('    def polys(kind):\n'
       '        if not segs[kind]:\n'
       '            return []\n'
       '        return [p for p in polygonize(unary_union(segs[kind])) if p.area > 1e-4]\n')
NEW = ('    _zone_cache = {}\n'
       '\n'
       '    def _raw(kind):\n'
       '        if not segs[kind]:\n'
       '            return []\n'
       '        return [p for p in polygonize(unary_union(segs[kind])) if p.area > 1e-4]\n'
       '\n'
       '    def polys(kind):  # Lot 68 : uniquement le dessin principal (pas la vue 3D / les autres vues)\n'
       '        if "z" not in _zone_cache:\n'
       '            _zone_cache["z"] = _bet_main_zone([p for p in _raw("slab") if p.area >= 1.0])\n'
       '        z = _zone_cache["z"]\n'
       '        return [p for p in _raw(kind) if z is None or z.contains(p.centroid)]\n')
if s.count(OLD) != 1:
    print("ANCRE polys(kind) (Lot 54) introuvable — ARRÊT, rien écrit"); sys.exit(1)
s = s.replace(OLD, NEW)
s = s.replace("def _bet_polygon_metre(doc, unit_to_m: float):", '''def _bet_main_zone(slabs, margin=8.0, link=25.0):
    """Lot 68 : emprise du dessin principal = groupe de dalles le plus étendu (les vues 3D/détails sont ailleurs)."""
    from shapely.geometry import box
    from shapely.ops import unary_union
    if not slabs:
        return None
    boxes = [box(*p.bounds) for p in slabs]
    parent = list(range(len(boxes)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i].distance(boxes[j]) <= link:
                parent[find(i)] = find(j)
    groups = {}
    for i in range(len(boxes)):
        groups.setdefault(find(i), []).append(i)
    best = max(groups.values(), key=lambda g: sum(slabs[i].area for i in g))
    return box(*unary_union([boxes[i] for i in best]).bounds).buffer(margin)


def _bet_polygon_metre(doc, unit_to_m: float):''', 1)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l68.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l68.py").read_bytes())
print("ok backend/engines/dxf_takeoff.py + backend/tests/test_l68.py")
print("L68 OK")
