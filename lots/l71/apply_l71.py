"""Lot 71 — linteau (StructuroPilot) : calcul sur la portée UTILE, pas sur la portée libre.

Constat (test prod) : M_Ed / V_Ed et flèches étaient calculés sur la portée libre de l'ouverture (l_n),
alors que l'EN 1992-1-1 §5.3.2.2 impose l_eff = l_n + a1 + a2 (a_i = about/2 → l_eff = l_n + about).
Écart non sécuritaire ≈ 15-20 % sur le moment pour une baie de 2,40 m avec 0,20 m d'about.
Correctif (engines/structuro_lintel.py, FR + PT) : portée de calcul = l_n + about ; longueur posée
(acier et BA) = l_n + 2 abouts ; sortie « clear_span_m » inchangée (portée libre) + « effective_span_m ».
Usage : python3 lots/l71/apply_l71.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "backend" / "engines" / "structuro_lintel.py"
s = f.read_text(encoding="utf-8")
if "Lot 71" in s:
    print("déjà appliqué"); print(f"L71 {site.upper()} OK"); sys.exit(0)
NOTE = {"fr": "Portée de calcul = portée utile l_eff = l_n + about (EN 1992-1-1 §5.3.2.2) = ",
        "pt": "Vão de cálculo = vão efetivo l_eff = l_n + entrega (EN 1992-1-1 §5.3.2.2) = "}[site]
EDITS = [
    ('    L = float(opts["clear_span_m"])\n    t = float(opts.get("wall_thickness_m", 0.2))\n', 1,
     '    L_n = float(opts["clear_span_m"])\n'
     '    # Lot 71 : portée utile EN 1992-1-1 §5.3.2.2 (l_eff = l_n + a1 + a2, a_i = about/2)\n'
     '    L = L_n + max(float(opts.get("bearing_length_m", 0.2) or 0.0), 0.0)\n'
     '    t = float(opts.get("wall_thickness_m", 0.2))\n'),
    ('    comps, notes = [], []\n', 1,
     '    comps, notes = [], []\n'
     f'    notes.append({NOTE!r} + f"{{_r(L_n, 3)}} + {{_r(L - L_n, 3)}} = {{_r(L, 3)}} m.")  # Lot 71\n'),
    ('            mass = p["A"] * 1e-4 * STEEL_DENSITY * L * n            # kg\n', 1,
     '            mass = p["A"] * 1e-4 * STEEL_DENSITY * (L + max(float(opts.get("bearing_length_m", 0.2) or 0.0), 0.0)) * n  # kg — Lot 71 : l_n + 2 abouts\n'),
    ('(L + 2 * a_m)', 2, '(L + a_m)'),   # Lot 71 : L est déjà l_n + about → longueur posée l_n + 2 abouts
    ('"clear_span_m": _r(L, 3)', 2, '"clear_span_m": _r(L - max(a, 0.0), 3), "effective_span_m": _r(L, 3)'),
]
for old, n, new in EDITS:
    c = s.count(old)
    if c != n:
        print(f"ANCRE introuvable ({c}≠{n}) : {old[:60]!r} — ARRÊT, rien écrit"); sys.exit(1)
    s = s.replace(old, new)
# l'ancre de sortie suppose « a » défini avant geometry/return dans lintel_design
i_a = s.find('    a = float(opts.get("bearing_length_m", 0.2))\n')
i_g = s.find('"effective_span_m": _r(L, 3)')
if i_a == -1 or i_a > i_g:
    print("ordre about/sortie inattendu — ARRÊT, rien écrit"); sys.exit(1)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l71.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l71.py").read_bytes())
print("ok backend/engines/structuro_lintel.py + backend/tests/test_l71.py")
print(f"L71 {site.upper()} OK")
