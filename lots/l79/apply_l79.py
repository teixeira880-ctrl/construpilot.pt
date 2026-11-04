"""Lot 79 — escalier droit : alertes contradictoires et largeur non contrôlée.

Constats (tests en production construpilot.fr) :
1) Escalier qui NE RENTRE PAS (alerte rouge « reculement 4 388 mm > 2 000 mm ») affiché en même temps que
   « Configuration optimale » (vert) → message contradictoire.
2) Escalier droit de 900 mm dans une largeur disponible de 600 mm → « Géométrie conforme » : la largeur
   disponible n'était pas comparée (elle l'est déjà pour le quart et le demi-tournant).
Correctif (stair_engine, FR + PT) : alerte rouge bloquante STAIR_WIDTH_INSUFFICIENT pour l'escalier droit ;
« Configuration optimale » retirée dès qu'une alerte rouge existe.
Usage : python3 lots/l79/apply_l79.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
fa = root / "backend" / "stair_engine" / "alerts.py"
fs = root / "backend" / "stair_engine" / "straight.py"
a, st = fa.read_text(encoding="utf-8"), fs.read_text(encoding="utf-8")
if "Lot 79" in a and "Lot 79" in st:
    print("déjà appliqué"); print(f"L79 {site.upper()} OK"); sys.exit(0)
A1 = '    non_green = [a for a in alerts if a.level != "green"]\n'
B1 = ('    # Lot 79 : pas de « configuration optimale » quand une alerte rouge existe (message contradictoire)\n'
      '    if any(a.level == "red" for a in alerts):\n'
      '        alerts = [a for a in alerts if a.code != "OPTIMAL_CONFIG"]\n'
      + A1)
A2 = '    # 6. is_buildable\n'
MSG = {"fr": 'f"Largeur d\'escalier {inp.stair_width_mm:.0f} mm > largeur disponible {inp.available_width_mm:.0f} mm. L\'escalier ne rentre pas."',
       "pt": 'f"Largura da escada {inp.stair_width_mm:.0f} mm > largura disponível {inp.available_width_mm:.0f} mm. A escada não cabe."'}[site]
B2 = ('    # Lot 79 : largeur de l\'escalier droit comparée à la largeur disponible\n'
      '    if inp.available_width_mm and inp.stair_width_mm > inp.available_width_mm:\n'
      '        alerts_all.append(Alert(level="red", code="STAIR_WIDTH_INSUFFICIENT",\n'
      f'                                message_fr={MSG},\n'
      '                                metric="available_width_mm", value=inp.stair_width_mm,\n'
      '                                threshold=inp.available_width_mm))\n'
      + A2)
if "Lot 79" not in a:
    if a.count(A1) != 1:
        print("ANCRE summarize introuvable dans alerts.py — ARRÊT, rien écrit"); sys.exit(1)
    a = a.replace(A1, B1)
if "Lot 79" not in st:
    if st.count(A2) != 1:
        print("ANCRE « # 6. is_buildable » introuvable dans straight.py — ARRÊT, rien écrit"); sys.exit(1)
    if "Alert(" not in st:
        print("Alert non importé dans straight.py — ARRÊT, rien écrit"); sys.exit(1)
    st = st.replace(A2, B2)
fa.write_text(a, encoding="utf-8")
fs.write_text(st, encoding="utf-8")
(root / "backend" / "tests" / "test_l79.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l79.py").read_bytes())
print("ok backend/stair_engine/alerts.py + straight.py + backend/tests/test_l79.py")
print(f"L79 {site.upper()} OK")
