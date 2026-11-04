"""Lot 72 — lecture des niveaux sur plans réels (dossier Saint-Denis, 29 pages).

Constats (test sur plans réels du fondateur) :
1) Une cote altimétrique « +3.10  Étage » devenait le niveau « R+10 » (le « 10 » après le point était lu
   comme « 10e étage »). Même risque côté PT (« 3.1º andar »). → un nombre précédé d'un point ou d'une
   virgule (cote décimale) n'est plus un numéro d'étage.
2) Titre « Plan d'exécution gros œuvre — Étage » sans numéro : niveau non affecté. → dans un TITRE,
   « Étage » seul vaut R+1 quand le document ne cite aucun étage au-delà de R+1 (maison R+1).
Usage : python3 lots/l72/apply_l72.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "plan_page_context.py"
s = f.read_text(encoding="utf-8")
if "Lot 72" in s:
    print("déjà appliqué"); print("L72 OK"); sys.exit(0)
EDITS = [
    ('    for match in re.finditer(r"(?<![:/\\d])(?<![:/][ \\t])\\b(\\d{1,2})(?:e|er|eme|ème)?[ \\t]*[eé]tage\\b", text, re.I):\n',
     '    # Lot 72 : « +3.10  Étage » est une cote, pas le 10e étage\n'
     '    for match in re.finditer(r"(?<![:/\\d.,])(?<![:/.,][ \\t])\\b(\\d{1,2})(?:e|er|eme|ème)?[ \\t]*[eé]tage\\b", text, re.I):\n'),
    ('    lines = [ln for ln in (text or "").splitlines() if re.match(r"\\s*(?:plans?|plantas?)\\b", ln, re.I)]\n'
     '    found = {}\n'
     '    for ln in lines:\n'
     '        for lv in level_candidates(ln):\n'
     '            found[lv["level_index"]] = lv\n',
     '    lines = [ln for ln in (text or "").splitlines() if re.match(r"\\s*(?:plans?|plantas?)\\b", ln, re.I)]\n'
     '    found = {}\n'
     '    _doc_floors = {lv["level_index"] for lv in level_candidates(text) if 0 < lv["level_index"] < 99}\n'
     '    for ln in lines:\n'
     '        for lv in level_candidates(ln):\n'
     '            found[lv["level_index"]] = lv\n'
     '        # Lot 72 : « … — Étage » seul dans un titre = R+1 si le document ne cite pas d\'étage au-delà de R+1\n'
     '        if (not level_candidates(ln) and re.search(r"(?:^|[\\s—–\\-:])[eé]tage\\s*$", ln, re.I)\n'
     '                and _doc_floors <= {1}):\n'
     '            found[1] = {"level_index": 1, "level_label": "R+1"}\n'),
]
for old, new in EDITS:
    c = s.count(old)
    if c != 1:
        print(f"ANCRE introuvable ({c}) : {old[:70]!r} — ARRÊT, rien écrit"); sys.exit(1)
    s = s.replace(old, new)
A3 = '    for match in re.finditer(r"(?<![:/\\d])\\b(\\d{1,2})[ \\t]*\\.?[ \\t]*[ºo°][ \\t]*andar\\b", text, re.I):\n'
if s.count(A3) == 1:
    s = s.replace(A3, '    for match in re.finditer(r"(?<![:/\\d.,])\\b(\\d{1,2})[ \\t]*\\.?[ \\t]*[ºo°][ \\t]*andar\\b", text, re.I):  # Lot 72\n')
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l72.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l72.py").read_bytes())
print("ok backend/engines/plan_page_context.py + backend/tests/test_l72.py")
print("L72 OK")
