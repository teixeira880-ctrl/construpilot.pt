"""Lot 75 — import DPGF/devis Excel : titres de lot avec parenthèse + lignes « ratios » après le total.

Constat (fichier réel du fondateur « Metre_devis_PH_R1.xlsx ») :
1) « POUTRES BA (consoles de balcons/coursives et poutres) » n'était pas reconnu comme titre de lot (la
   parenthèse en minuscules faisait baisser la part de majuscules) → les poutres étaient rangées dans le lot
   « LINTEAUX ».
2) Les lignes « Ratios de contrôle » placées APRÈS « Total TTC » (Béton total 418 m³, Acier total 32 486 kg,
   Coût HT/m²…) étaient importées comme 6 ouvrages à chiffrer (unité « u ») → chiffrage IA de lignes fictives.
Correctif (engines/dpgf_engine.py, FR + PT) : majuscules évaluées hors parenthèses ; la lecture d'un onglet
s'arrête après la ligne « Total TTC » / « Total général » (FR) ou « Total com IVA » / « Total geral » (PT).
Usage : python3 lots/l75/apply_l75.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "dpgf_engine.py"
s = f.read_text(encoding="utf-8")
if "Lot 75" in s:
    print("déjà appliqué"); print("L75 OK"); sys.exit(0)
EDITS = [
    ('    letters = [c for c in t if c.isalpha()]\n',
     '    # Lot 75 : « POUTRES BA (consoles de balcons…) » — la parenthèse ne compte pas dans la part de majuscules\n'
     '    letters = [c for c in (re.sub(r"\\([^)]*\\)", "", t) or t) if c.isalpha()]\n'),
    ('            des = ws.cell(row=r, column=c_des).value if c_des else None\n',
     '            # Lot 75 : fin du devis (Total TTC / général) → les « ratios de contrôle » qui suivent ne sont pas des ouvrages\n'
     '            _cells75 = " ".join(fold(str(ws.cell(row=r, column=_c).value or "")) for _c in range(1, min(ws.max_column, 30) + 1))\n'
     '            if re.search(r"\\btotal\\s+(?:ttc|general|geral|com\\s+iva)\\b", _cells75):\n'
     '                break\n'
     '            des = ws.cell(row=r, column=c_des).value if c_des else None\n'),
]
for old, new in EDITS:
    c = s.count(old)
    if c != 1:
        print(f"ANCRE introuvable ({c}) : {old[:60]!r} — ARRÊT, rien écrit"); sys.exit(1)
    s = s.replace(old, new)
if "\nimport re\n" not in s and not s.startswith("import re\n"):
    print("module re non importé dans dpgf_engine.py — ARRÊT, rien écrit"); sys.exit(1)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l75.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l75.py").read_bytes())
print("ok backend/engines/dpgf_engine.py + backend/tests/test_l75.py")
print("L75 OK")
