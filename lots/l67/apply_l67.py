"""Lot 67 — contrôle de devis : plus d'alerte « 0 ligne(s) sans coût de revient » (devis vide ou lignes non chiffrées).

Usage : python3 lots/l67/apply_l67.py <racine /app>   (FR + PT ; idempotent ; ARRÊT si l'ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "quote_check.py"
s = f.read_text(encoding="utf-8")
if "Lot 67" in s:
    print("déjà appliqué"); print("L67 OK"); sys.exit(0)
A = '    if not cov.get("complete"):\n'
if s.count(A) != 1:
    print("ANCRE cost_coverage introuvable — ARRÊT, rien écrit"); sys.exit(1)
s = s.replace(A, '    if not cov.get("complete") and cov.get("missing_lines", 0) > 0:  # Lot 67\n')
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l67.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l67.py").read_bytes())
print("ok backend/engines/quote_check.py + backend/tests/test_l67.py")
print("L67 OK")
