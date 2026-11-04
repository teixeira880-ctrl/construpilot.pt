"""Lot 60 PT — devis de structure généré depuis un DWG : restes de français sur construpilot.pt (test réel en prod, 04/11).

Constat : « emprise 8.2 m² (espess. lidas) », « (larg. lues) », « 108.0 m² (contour) × ép. 0.2 m »,
« ép. éq. », et l'unité « forfait » sur les lignes d'estaleiro du devis portugais.
Correctif : textes en portugais européen (implantação, larguras lidas, contorno, esp., vg) dans
engines/dxf_takeoff.py et unité « vg » dans l'écran des preços (PcSettingsDialog).
Usage : python3 lots/l60/apply_l60.py <racine /app>   (PT uniquement ; idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
D = root / "backend" / "engines" / "dxf_takeoff.py"
F = root / "frontend" / "src" / "components" / "planTakeoff" / "PcSettingsDialog.jsx"
ds = D.read_text(encoding="utf-8")
if "Lot 60" in ds:
    print("déjà appliqué"); print("L60 PT OK"); sys.exit(0)
EDITS = [
 ("f'emprise {round(wall_area, 1)} m² (espess. lidas) × {h_label}'", "f'implantação {round(wall_area, 1)} m² (espessuras lidas) × {h_label}'", 1),
 ('f"{walls_ml} ml × {h_label} × ép. {tw} m"', 'f"{walls_ml} ml × {h_label} × esp. {tw} m"', 1),
 ('f"emprise {round(beam_area, 1)} m² (larg. lues) × h {bh} m"', 'f"implantação {round(beam_area, 1)} m² (larguras lidas) × h {bh} m"', 1),
 ('f"{slab_m2} m² ({slab_source}) × ép. {ts} m"',
  'f"{slab_m2} m² ({_SLAB_SRC_PT.get(slab_source, slab_source)}) × esp. {ts} m"', 1),
 ("× ép. éq. {esc_eq_thk} m", "× esp. eq. {esc_eq_thk} m", 1),
 ('"forfait", "forfait", 1,', '"global", "vg", 1,', 3),
]
for old, new, n in EDITS:
    c = ds.count(old)
    if c != n:
        print(f"ANCRE introuvable ({c}/{n}) : {old[:70]!r} — ARRÊT, rien écrit"); sys.exit(1)
    ds = ds.replace(old, new)
ds = ds.replace("def cost_structural(", '_SLAB_SRC_PT = {"saisie": "indicada", "contour": "contorno", "emprise_auto": "implantação automática"}  # Lot 60\n\n\ndef cost_structural(', 1)
fs = F.read_text(encoding="utf-8")
fs2 = fs.replace('"forfait"]', '"vg"]').replace('"forfait/niv."]', '"vg/piso"]')
if fs2 == fs and "Lot 60" not in fs:
    print("aucune unité « forfait » dans PcSettingsDialog.jsx — ARRÊT, rien écrit"); sys.exit(1)
fs2 = fs2.replace("const PRICE_LABELS = {", "// Lot 60 : unité « vg » (valor global) au lieu de « forfait »\nconst PRICE_LABELS = {", 1)
D.write_text(ds, encoding="utf-8")
F.write_text(fs2, encoding="utf-8")
(root / "backend" / "tests" / "test_l60.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l60.py").read_bytes())
print("ok backend/engines/dxf_takeoff.py + frontend/.../PcSettingsDialog.jsx + backend/tests/test_l60.py")
print("L60 PT OK")
