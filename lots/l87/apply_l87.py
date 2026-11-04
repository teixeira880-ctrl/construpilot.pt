"""Lot 87 (FR + PT) — import DWG réel (coffrage R+2, 95 × 66 m) : lecture « partielle » trompeuse et métré faux.

Constat (production .fr, 04/11, import réel R+2.dwg → DXF AutoCAD) :
1. Le panneau « Lecture CAO » listait des centaines de lignes « NON_PLANAR_GEOMETRY » identiques et classait l'import
   « lecture partielle » : une entité miroir (extrusion 0,0,-1) est plane ; seules les extrusions hors axe Z sont
   non planes. → diagnostic regroupé (un seul avec compteur), miroirs ignorés.
2. Poteaux : 2 comptés alors que le plan en a 13 (dessinés en traits + hachure, sans bloc). → chaque boucle de hachure
   d'un calque poteau compte comme un poteau, avec sa section ; on garde le plus grand des deux comptages.
3. Dalles : 0,1 m² (une micro-hachure) alors que la dalle est tracée en lignes ouvertes ; ce 0,1 m² empêchait même le
   repli sur l'emprise. → une surface < 1 m² avec un calque dalle tracé (≥ 20 lignes) est traitée comme « à mesurer »
   (0) et le repli emprise existant s'applique.
Mêmes chiffres reproduits en local sur R+1, R+2, R+3 (DXF convertis).
Usage : python3 lots/l87/apply_l87.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
fg = root / "backend" / "engines" / "cad_geometry.py"
ft = root / "backend" / "engines" / "dxf_takeoff.py"
g = fg.read_text(encoding="utf-8")
t = ft.read_text(encoding="utf-8")
if "Lot 87" in g and "Lot 87" in t:
    print("déjà appliqué"); print("L87 OK"); sys.exit(0)

G = [("            if tuple(entity.dxf.get('extrusion',(0,0,1))) != (0,0,1) or (kind=='POLYLINE' and entity.is_3d_polyline):\n"
      "                issues.append({'code':'NON_PLANAR_GEOMETRY','entity':kind})\n",
      "            ext=tuple(entity.dxf.get('extrusion',(0,0,1)))\n"
      "            # Lot 87 : (0,0,-1) = entité miroir, plane ; un seul diagnostic par type avec compteur\n"
      "            if abs(ext[0])>1e-9 or abs(ext[1])>1e-9 or (kind=='POLYLINE' and entity.is_3d_polyline):\n"
      "                np87=next((i for i in issues if i.get('code')=='NON_PLANAR_GEOMETRY' and i.get('entity')==kind),None)\n"
      "                if np87 is None: issues.append({'code':'NON_PLANAR_GEOMETRY','entity':kind,'count':1})\n"
      "                else: np87['count']=np87.get('count',1)+1\n")]
T = [("    col_sections_units: list = []  # (w, h) en unités dessin, par poteau\n",
      "    col_sections_units: list = []  # (w, h) en unités dessin, par poteau\n"
      "    col_hatch_sections: list = []  # Lot 87 : poteaux tracés en traits + hachure (une boucle = un poteau)\n"
      "    slab_lines87 = 0\n"),
     ('        elif t == "HATCH":\n'
      '            # Emprise béton lue par élément (voiles/poutres) — remplissage plein\n',
      '        elif t == "HATCH":\n'
      '            if _match(L, _COL):  # Lot 87\n'
      '                col_hatch_sections.extend(_hatch_loops_wh87(e))\n'
      '            # Emprise béton lue par élément (voiles/poutres) — remplissage plein\n'),
     ('            elif _match(L, _LINTEL): lintel_len += ln\n',
      '            elif _match(L, _LINTEL): lintel_len += ln\n'
      '            if _match(L, _SLAB): slab_lines87 += 1  # Lot 87\n'),
     ("    columns_count = col_inserts\n",
      "    columns_count = col_inserts\n"
      "    if len(col_hatch_sections) > col_inserts:  # Lot 87 : poteaux sans bloc, comptés par hachure\n"
      "        columns_count = len(col_hatch_sections)\n"
      "        col_sections_units = list(col_hatch_sections)\n"),
     ("    slab_area_m2 = round(slab_area_units * U * U, 1)\n",
      "    slab_area_m2 = round(slab_area_units * U * U, 1)\n"
      "    slab_status = \"mesuree\" if slab_area_m2 > 0 else \"absente\"\n"
      "    if slab_area_m2 < 1.0 and slab_lines87 >= 20:  # Lot 87 : dalle tracée en lignes ouvertes → à mesurer\n"
      "        slab_area_m2, slab_status = 0.0, \"contours_ouverts\"\n"),
     ('        "slab_area_m2": slab_area_m2,\n',
      '        "slab_area_m2": slab_area_m2,\n'
      '        "slab_status": slab_status,\n'),
     ("def extract_structural_metre(doc, unit_to_m: float) -> dict:\n",
      "def _hatch_loops_wh87(e):\n"
      "    \"\"\"Lot 87 : (largeur, hauteur) de chaque boucle extérieure d'une hachure, en unités dessin.\"\"\"\n"
      "    out = []\n"
      "    try:\n"
      "        from ezdxf.path import from_hatch\n"
      "        for p in from_hatch(e):\n"
      "            pts = list(p.flattening(distance=1.0, segments=8))\n"
      "            if len(pts) < 3:\n"
      "                continue\n"
      "            xs = [q.x for q in pts]; ys = [q.y for q in pts]\n"
      "            w, h = max(xs) - min(xs), max(ys) - min(ys)\n"
      "            if w > 0 and h > 0:\n"
      "                out.append((w, h))\n"
      "    except Exception:  # noqa: BLE001 — hachure illisible : ignorée, jamais bloquante\n"
      "        return []\n"
      "    return out\n\n\n"
      "def extract_structural_metre(doc, unit_to_m: float) -> dict:\n")]
for s, reps, name in ((g, G, "cad_geometry"), (t, T, "dxf_takeoff")):
    for a, _ in reps:
        if s.count(a) != 1:
            print(f"ANCRE {name} introuvable — ARRÊT, rien écrit:", a.strip()[:70]); sys.exit(1)
for a, b in G:
    g = g.replace(a, b)
for a, b in T:
    t = t.replace(a, b)
fg.write_text(g, encoding="utf-8")
ft.write_text(t, encoding="utf-8")
(root / "backend" / "tests" / "test_l87.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l87.py").read_bytes())
print("ok backend/engines/cad_geometry.py + dxf_takeoff.py + backend/tests/test_l87.py")
print("L87 OK")
