"""Lot 61 — calculateur d'isolation : le R visé était ignoré quand une épaisseur était saisie (test réel en prod .fr, 04/11).

Constat : R visé 5, laine de verre 50 mm → « R obtenu 1,56 » sans aucun avertissement.
Correctif : si l'épaisseur saisie ne permet pas d'atteindre le R visé, le résultat l'indique clairement et
donne l'épaisseur minimale nécessaire (arrondie au 10 mm supérieur).
Usage : python3 lots/l61/apply_l61.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
C = root / "backend" / "engines" / "calculators.py"
s = C.read_text(encoding="utf-8")
if "Lot 61" in s:
    print("déjà appliqué"); print(f"L61 {site.upper()} OK"); sys.exit(0)
for a in ("def insulation(", "CALCULATORS = {", '"insulation": {"key": "insulation"'):
    if a not in s:
        print(f"ANCRE {a!r} introuvable — ARRÊT, rien écrit"); sys.exit(1)
T = {"fr": ("⚠ R visé non atteint — épaisseur minimale nécessaire",
            "Avec {t} mm, R = {r} m².K/W, inférieur au R visé de {target} : prévoir au moins {need} mm."),
     "pt": ("⚠ R pretendido não atingido — espessura mínima necessária",
            "Com {t} mm, R = {r} m².K/W, inferior ao R pretendido de {target}: prever pelo menos {need} mm.")}[site]
ADD = f'''

# --- Lot 61 : le R visé n'est plus ignoré quand une épaisseur est saisie ---
_insulation_lot61_base = insulation


def insulation(area, material="laine_de_verre", thickness_mm=None, target_r=None, price_per_sqm=12.0):
    out = _insulation_lot61_base(area, material, thickness_mm, target_r, price_per_sqm)
    try:
        lam = LAMBDA.get(material, 0.035)
        t = float(out["inputs"]["thickness_mm"])
        r = round((t / 1000) / lam, 2)
        if target_r and r + 1e-9 < float(target_r):
            need = int(math.ceil(float(target_r) * lam * 1000 / 10.0) * 10)
            out["results"].insert(3, {{"label": {T[0]!r}, "value": need, "unit": "mm"}})
            out.setdefault("warnings", []).append({T[1]!r}.format(t=int(t), r=r, target=target_r, need=need))
    except (KeyError, TypeError, ValueError):
        pass
    return out


CALCULATORS["insulation"]["fn"] = insulation
'''
C.write_text(s.rstrip("\n") + "\n" + ADD, encoding="utf-8")
(root / "backend" / "tests" / "test_l61.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l61.py").read_bytes())
print("ok backend/engines/calculators.py + backend/tests/test_l61.py")
print(f"L61 {site.upper()} OK")
