"""Lot 59 — calculateurs (tests réels en prod .pt, 04/11).

1. FR + PT : peinture — des ouvertures plus grandes que les murs (5 portes + 5 fenêtres = 17,5 m² sur 10 m² de
   murs) donnaient « 0 m² à peindre » sans avertissement → refus clair (422).
2. PT seulement : unités en français affichées sur le site portugais (« carton », « sac 25 kg », « bidon »,
   « plaque », « rouleau ») → « caixa », « saco 25 kg », « bidão », « placa », « rolo » ; recherche produit
   « plaque platre » → « placa gesso cartonado ».
Usage : python3 lots/l59/apply_l59.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
V = root / "backend" / "engines" / "calculator_validation.py"
C = root / "backend" / "engines" / "calculators.py"
MSG = {"fr": "La surface des portes et fenêtres dépasse celle des murs ; vérifiez les dimensions et le nombre d'ouvertures",
       "pt": "A área das portas e janelas ultrapassa a das paredes; verifique as dimensões e o número de vãos"}[site]
ANCHOR = '    if key == "roof_facade" and args.get("openings_m2", 0) > args.get("wall_perimeter_m", 0) * args.get("wall_height_m", 0):\n'
vs = V.read_text(encoding="utf-8")
out = {}
if "Lot 59" not in vs:
    if vs.count(ANCHOR) != 1:
        print("ANCRE roof_facade introuvable dans calculator_validation.py — ARRÊT, rien écrit"); sys.exit(1)
    add = ('    if key == "paint":  # Lot 59 : ouvertures > murs → « 0 m² » silencieux\n'
           '        _walls = 2 * (args.get("length", 0) + args.get("width", 0)) * args.get("height", 0)\n'
           '        if args.get("doors", 0) * 2.0 + args.get("windows", 0) * 1.5 > _walls:\n'
           f'            raise ValueError({MSG!r})\n')
    out[V] = vs.replace(ANCHOR, add + ANCHOR)
if site == "pt":
    cs = C.read_text(encoding="utf-8")
    if "Lot 59" not in cs:
        n0 = len(re.findall(r'"unit": "(?:carton|bidon|plaque|rouleau|sac \d+ kg)"', cs))
        if n0 == 0:
            print("aucune unité française trouvée dans calculators.py — ARRÊT, rien écrit"); sys.exit(1)
        cs = re.sub(r'"unit": "sac (\d+) kg"', r'"unit": "saco \1 kg"', cs)
        for a, b in (("carton", "caixa"), ("bidon", "bidão"), ("plaque", "placa"), ("rouleau", "rolo")):
            cs = cs.replace(f'"unit": "{a}"', f'"unit": "{b}"')
        cs = cs.replace('f"plaque platre {plate_type}', 'f"placa gesso cartonado {plate_type}')
        cs = cs.rstrip("\n") + "\n\n# Lot 59 : unités traduites en portugais (%d)\n" % n0
        out[C] = cs
        t16 = root / "backend" / "tests" / "test_iter16_quantity_fixes.py"
        if t16.exists():
            ts = t16.read_text(encoding="utf-8")
            ts2 = ts.replace('membrane["unit"] == "rouleau"', 'membrane["unit"] == "rolo"').replace('adhesif["unit"] == "rouleau"', 'adhesif["unit"] == "rolo"')
            if ts2 != ts:
                out[t16] = ts2
for f, s in out.items():
    f.write_text(s, encoding="utf-8"); print(f"ok {f.relative_to(root)}")
(root / "backend" / "tests" / "test_l59.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l59.py").read_bytes())
print(f"L59 {site.upper()} OK")
