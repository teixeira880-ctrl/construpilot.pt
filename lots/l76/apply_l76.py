"""Lot 76 — symboles de niveau NGF des plans de coffrage : niveau « fini » plausible uniquement.

Constat (plan réel AES R+4, PH 68,72 b) : le niveau « fini » d'un symbole était pris sur le niveau du symbole
voisin (68,09 ; 68,32 ; et même 110,48 NGF) → « fini » 42 m au-dessus du brut ou sous le brut.
Correctif (engines/metre/level_symbols.py, FR + PT) : un niveau fini n'est retenu que s'il est au-dessus du brut
d'au plus 0,30 m (chape / revêtement) ; sinon « non lu ».
Usage : python3 lots/l76/apply_l76.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "metre" / "level_symbols.py"
s = f.read_text(encoding="utf-8")
if "Lot 76" in s:
    print("déjà appliqué"); print("L76 OK"); sys.exit(0)
A = ('        fini = next((w for w in lv if w is not brut and (m.group(2) or "").lower() != "f" and '
     '(fini_w is None or _dist(w, fini_w) < _dist(brut, fini_w))), None)\n')
if s.count(A) != 1:
    print("ANCRE fini introuvable dans level_symbols.py — ARRÊT, rien écrit"); sys.exit(1)
B = ('        # Lot 76 : un « fini » est au-dessus du brut de 0 à 0,30 m (chape/revêtement), jamais le niveau d\'un symbole voisin\n'
     '        fini = next((w for w in lv if w is not brut and (m.group(2) or "").lower() != "f" and '
     '(fini_w is None or _dist(w, fini_w) < _dist(brut, fini_w))\n'
     '                     and 0.0 < _f(NGF_LEVEL.match(w[4].strip()).group(1)) - _f(m.group(1)) <= 0.30), None)\n')
f.write_text(s.replace(A, B), encoding="utf-8")
(root / "backend" / "tests" / "test_l76.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l76.py").read_bytes())
print("ok backend/engines/metre/level_symbols.py + backend/tests/test_l76.py")
print("L76 OK")
