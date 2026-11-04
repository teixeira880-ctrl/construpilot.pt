"""Lot 78 — estimation « construction maison » : le dallage / plancher bas béton manquait.

Constat (contrôle des ratios de l'estimateur, FR et PT) : « gros œuvre seul » = terrassement + fondations + VRD +
maçonnerie, SANS dallage sur terre-plein (≈ 100 m² × 60 €/m² pour une maison de 100 m²) → gros œuvre à 360 €/m²,
sous le marché. Correctif (engines/catalog.py, FR + PT) : nouveau poste « Dallage / plancher bas béton armé »
(m², 62 €/m² standard FR avant coefficient régional), placé après les fondations dans le planning, ajouté
(× 1,0 surface) aux 4 types « construction maison » (clé en main, hors d'eau/hors d'air, gros œuvre seul,
main d'œuvre seule). L'extension (prix global au m²) n'est pas modifiée.
Usage : python3 lots/l78/apply_l78.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "backend" / "engines" / "catalog.py"
s = f.read_text(encoding="utf-8")
if '"key": "dallage"' in s:
    print("déjà appliqué"); print(f"L78 {site.upper()} OK"); sys.exit(0)
FOND_TOOLS = {"fr": '     "tools": ["Mini-pelle", "Coffrage", "Aiguille vibrante"]},\n',
              "pt": '     "tools": ["Mini-escavadora", "Cofragem", "Agulha vibradora"]},\n'}[site]
NEW = {"fr": ('    # Lot 78 : dallage / plancher bas (manquait dans la construction maison)\n'
              '    {"key": "dallage", "name": "Dallage / plancher bas béton armé", "unit": "m²", "mat_eco": 24, "mat_std": 32,\n'
              '     "mat_premium": 45, "labour": 30, "hours": 0.6, "difficulty": "pro", "diy_possible": False,\n'
              '     "tools": ["Hérisson / polyane", "Treillis soudé", "Règle vibrante", "Toupie béton"]},\n'),
       "pt": ('    # Lot 78 : laje térrea / pavimento térreo (faltava na construção de moradia)\n'
              '    {"key": "dallage", "name": "Laje térrea / pavimento em betão armado", "unit": "m²", "mat_eco": 24, "mat_std": 32,\n'
              '     "mat_premium": 45, "labour": 30, "hours": 0.6, "difficulty": "pro", "diy_possible": False,\n'
              '     "tools": ["Enrocamento / tela", "Malha electrossoldada", "Régua vibratória", "Autobetoneira"]},\n')}[site]
EDITS = [
    (FOND_TOOLS, 1, FOND_TOOLS + NEW),
    ('"lots": {"terrassement": 1.0, "fondations": 0.30, "vrd": 0.40, "maconnerie": 1.10,', 4,
     '"lots": {"terrassement": 1.0, "fondations": 0.30, "dallage": 1.0, "vrd": 0.40, "maconnerie": 1.10,'),
    ('"terrassement", "fondations", "vrd",', 1, '"terrassement", "fondations", "dallage", "vrd",'),
]
for old, n, new in EDITS:
    c = s.count(old)
    if c != n:
        print(f"ANCRE introuvable ({c}≠{n}) : {old[:60]!r} — ARRÊT, rien écrit"); sys.exit(1)
    s = s.replace(old, new)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l78.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l78.py").read_bytes())
print("ok backend/engines/catalog.py + backend/tests/test_l78.py")
print(f"L78 {site.upper()} OK")
