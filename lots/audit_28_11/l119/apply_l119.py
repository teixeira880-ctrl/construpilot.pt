"""Lot 119 (FR + PT) — Contrôle des cotes plantait (« Cannot read properties of undefined (reading '0') »).

Cause : un contrôle enregistré avec le verdict « nd » (non déterminé : cotes lues sans échelle fiable) n'existe
pas dans la table d'affichage (ok / warn / ko) → la page entière tombait dès que la liste des plans contenait
un tel plan. Ajout du verdict « Non déterminé » + repli pour tout verdict inconnu.

Usage : python3 lots/l119/apply_l119.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-11)
"""
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2] if len(sys.argv) > 2 else "fr"
MARK = "CP-AUDIT-NUIT-11"
p = root / "frontend/src/pages/CotesControl.jsx"
txt = p.read_text(encoding="utf-8")
if MARK in txt:
    print("DÉJÀ      contrôle des cotes : verdict « nd »")
    sys.exit(0)
m = re.search(r"const VERDICT = \{(.*?)\};", txt)
if not m:
    print("IGNORÉ    contrôle des cotes (table VERDICT absente)")
    sys.exit(1)
label = "Indeterminado" if site == "pt" and "Conforme\"" not in m.group(1) else "Non déterminé"
new_map = m.group(0)[:-2] + f', nd: ["{label}", "text-slate-500"] }};  // {MARK}'
if '"nd"' in m.group(0) or " nd:" in m.group(0):
    new_map = m.group(0) + f"  // {MARK}"
txt = txt.replace(m.group(0), new_map, 1)
n_before = len(re.findall(r"VERDICT\[([^\]]+?)\]\[", txt))
txt = re.sub(r"VERDICT\[([^\]]+?)\]\[", r"(VERDICT[\1] || VERDICT.nd)[", txt)
p.write_text(txt, encoding="utf-8")
print(f"OK        contrôle des cotes : verdict « nd » ajouté, {n_before} accès protégés")
