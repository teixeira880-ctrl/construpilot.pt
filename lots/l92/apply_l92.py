"""Lot 92 (FR + PT) — métré DWG : les m² de murs et de poutres ne sortaient pas (moins de la moitié).

Constat (fondateur, 04/11 22 h 56) : « les murs, même pas la moitié des m² ont été calculés ». Sur R+2.dwg, l'emprise
béton des voiles venait de hachures partielles (15 m²) → parement 192 m² au lieu de ≈ 2 450 m² mesurés à la main
(façade 993,6 + intérieurs 1 457,9). Les poutres : emprise 0,6 m² → 0,3 m³ de béton.
Correctif (sur le Lot 91) : emprise des voiles = Σ (recouvrement × écartement) des paires de traits, épaisseur moyenne
lue (0,19 m) → parement 2 560 m² (+4 %) ; poutres tracées en paires : axe 171 ml, emprise 52 m², largeur moyenne
lue 0,31 m (sections 20 à 40 cm du plan).
Usage : python3 lots/l92/apply_l92.py <racine /app>   (Lot 91 requis ; idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "dxf_takeoff.py"
s = f.read_text(encoding="utf-8")
if "Lot 92" in s:
    print("déjà appliqué"); print("L92 OK"); sys.exit(0)
if "Lot 91" not in s:
    print("Lot 91 absent — ARRÊT, rien écrit"); sys.exit(1)
R = [('''    if not lines:
        return 0.0
''', '''    if not lines:
        return 0.0, 0.0
'''),
     ('''    total = 0.0
    for i, a in enumerate(lines):''', '''    total = 0.0
    area = 0.0  # Lot 92 : emprise = Σ recouvrement × écartement
    for i, a in enumerate(lines):'''),
     ('''            if ov > 0:
                total += ov
    return total * unit_to_m
''', '''            if ov > 0:
                total += ov
                area += ov * d
    return total * unit_to_m, area * unit_to_m * unit_to_m
'''),
     ('''            axis = _l91_wall_axis_m(segs, unit_to_m)
            if axis > 0:
                res["walls_ml_raw"] = res.get("walls_ml")
                res["walls_ml"] = round(axis, 1)
''', '''            axis, area = _l91_wall_axis_m(segs, unit_to_m)
            if axis > 0:
                res["walls_ml_raw"] = res.get("walls_ml")
                res["walls_ml"] = round(axis, 1)
                # Lot 92 : emprise béton des voiles et épaisseur moyenne cohérentes avec l'axe
                res["wall_area_m2_raw"] = res.get("wall_area_m2")
                res["wall_area_m2"] = round(area, 2)
                det = dict(res.get("detected") or {})
                det["wall_area_m2"] = round(area, 2)
                det["wall_thickness_m"] = round(area / axis, 3)
                res["detected"] = det
'''),
     ('''        if res.get("slab_status") == "contours_ouverts":''', '''        # Lot 92 : poutres tracées en paires de traits (sans hachure exploitable) : axe + emprise
        beam_layers = [n for n in names if "poutre" in n.lower() or n.upper().endswith("BEAM")]
        bsegs = _l91_lines(doc, lambda lay: lay in beam_layers)
        if bsegs and float(res.get("beam_area_m2") or 0) < 1.0:
            baxis, barea = _l91_wall_axis_m(bsegs, unit_to_m, tmin=0.10, tmax=0.60)
            if baxis > 0:
                res["beams_ml_raw"] = res.get("beams_ml")
                res["beams_ml"] = round(baxis, 1)
                res["beam_area_m2"] = round(barea, 2)
                det = dict(res.get("detected") or {})
                det["beam_area_m2"] = round(barea, 2)
                det["beam_w_m"] = round(barea / baxis, 3)
                res["detected"] = det
                res["beams_method"] = "poutres_par_paires"
        if res.get("slab_status") == "contours_ouverts":''')]
for a, _ in R:
    if s.count(a) != 1:
        print("ANCRE introuvable — ARRÊT, rien écrit:", a.strip()[:70]); sys.exit(1)
for a, b in R:
    s = s.replace(a, b)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l92.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l92.py").read_bytes())
print("ok backend/engines/dxf_takeoff.py + backend/tests/test_l92.py")
print("L92 OK")
