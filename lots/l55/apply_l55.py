"""Lot 55 — devis gros œuvre depuis un DWG : le coffrage des poteaux manquait (0 m², 0 €).

Test réel (plan AES coffrage PH R+1, 48 poteaux) : la ligne « Coffrage poteaux » n'existait pas dans
l'estimation ni dans le devis généré (« Métré → devis ») ; le total coffrage l'ignorait aussi.
Correctif (engines/dxf_takeoff.py, cost_structural) : coffrage poteaux = périmètre de chaque section
lue sur le plan (sinon section uniforme) × hauteur des éléments verticaux × niveaux ; prix 60 € HT/m² ;
ajouté au lot structure, au récapitulatif par catégorie et au total coffrage.

Usage : python3 lots/l55/apply_l55.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "backend" / "engines" / "dxf_takeoff.py"
s = f.read_text(encoding="utf-8")
if "Lot 55" in s:
    print("déjà appliqué"); print(f"L55 {site.upper()} OK"); sys.exit(0)

LABEL, DETAIL = {"fr": ("Coffrage poteaux", "périmètre des sections × {h}"),
                 "pt": ("Cofragem de pilares", "perímetro das secções × {h}")}[site]

EDITS = [
 ('    "acier_poteau":    1.6,\n',
  '    "acier_poteau":    1.6,\n    "coffrage_poteau": 60.0,  # m² (Lot 55) — 4 faces, par m² de paroi\n'),
 ('    col_ac = round(col_m3 * REBAR["poteau"], 0)\n',
  '    col_ac = round(col_m3 * REBAR["poteau"], 0)\n'
  '    # Lot 55 : coffrage poteaux = périmètre des sections lues (sinon section uniforme) × hauteur\n'
  '    _secs = [sc for sc in ((metre.get("detected") or {}).get("col_sections") or metre.get("col_sections") or [])\n'
  '             if isinstance(sc, dict) and sc.get("w_cm") and sc.get("h_cm")]\n'
  '    _n_cols = int(metre.get("columns_count", 0))\n'
  '    if _secs and _n_cols:\n'
  '        _per = sum(2 * (sc["w_cm"] + sc["h_cm"]) / 100.0 for sc in _secs) / len(_secs) * _n_cols\n'
  '    else:\n'
  '        _per = 2 * (cw + ch) * _n_cols\n'
  '    col_cof = round(_per * h_vert * nlv, 1)\n'
  '    P.setdefault("coffrage_poteau", 60.0)\n'),
 ('col_m3, 0.0, col_ac,', 'col_m3, col_cof, col_ac,'),
 ('col_m3 * P["beton_poteau"] + col_ac * P["acier_poteau"]))',
  'col_m3 * P["beton_poteau"] + col_cof * P["coffrage_poteau"] + col_ac * P["acier_poteau"]))'),
 ('        "coffrage_m2": round(wall_cof + beam_cof + slab_m2 + esc_cof, 1),\n',
  '        "coffrage_m2": round(wall_cof + beam_cof + col_cof + slab_m2 + esc_cof, 1),\n'),
]
for old, new in EDITS:
    c = s.count(old)
    if c != 1:
        print(f"ANCRE introuvable ({c}/1) : {old[:70]!r} — ARRÊT, rien écrit"); sys.exit(1)
    s = s.replace(old, new)
# ligne de devis : juste après la ligne « béton poteaux »
m = re.search(r'\n( +)_line\("[^"]*", col_detail, "m³", col_m3, P\["beton_poteau"\]\),\n', s)
if not m or len(re.findall(r'col_detail, "m³", col_m3, P\["beton_poteau"\]', s)) != 1:
    print("ANCRE ligne béton poteaux introuvable — ARRÊT, rien écrit"); sys.exit(1)
ins = (f'{m.group(1)}_line({LABEL!r}, f"{DETAIL.replace("{h}", "{h_label}")}", "m²", col_cof, '
       'P["coffrage_poteau"]),  # Lot 55\n')
s = s[:m.end()] + ins + s[m.end():]
f.write_text(s, encoding="utf-8")
t = pathlib.Path(__file__).resolve().parent / "tests" / "test_l55.py"
(root / "backend" / "tests" / "test_l55.py").write_bytes(t.read_bytes())
print("ok backend/engines/dxf_takeoff.py + backend/tests/test_l55.py")
print(f"L55 {site.upper()} OK")
