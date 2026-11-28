"""Lot 116 (FR + PT) — liste des plans encore allégée.

Après le lot 109, GET /api/takeoffs pesait encore 9,8 Mo (3 s) : `pages[].walls_analysis` (9 Mo) et
`pages[].dxf_dimensions` (0,2 Mo) partent dans la liste alors que l'écran de liste ne s'en sert pas
(le plan complet reste chargé par GET /api/takeoffs/{id}).
Sécurité : un champ n'est exclu que si AUCUN fichier du frontend ne le lit.

Usage : python3 lots/l116/apply_l116.py <racine /app> <fr|pt>   (idempotent, marqueur CP-AUDIT-NUIT-8)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
MARK = "CP-AUDIT-NUIT-8"
rel = "backend/routes/plans_crud.py"
p = root / rel
txt = p.read_text(encoding="utf-8")
if MARK in txt:
    print("DÉJÀ      liste des plans allégée (2)")
    sys.exit(0)
anchor = '"pages.pdf_elements": 0, "pages.pdf_auto_spans": 0}'
if txt.count(anchor) != 1:
    print("IGNORÉ    liste des plans allégée (2) — lot 109 non posé ?")
    sys.exit(1)
front = "\n".join(f.read_text(encoding="utf-8", errors="ignore")
                  for f in (root / "frontend/src").rglob("*.js*") if "__tests__" not in f.parts)
champs = [c for c in ("walls_analysis", "dxf_dimensions") if c not in front]
if not champs:
    print("IGNORÉ    liste des plans allégée (2) — champs lus par le frontend, rien changé")
    sys.exit(0)
extra = "".join(f', "pages.{c}": 0' for c in champs)
txt = txt.replace(anchor, anchor[:-1] + extra + "}  # " + MARK, 1)
p.write_text(txt, encoding="utf-8")
print(f"OK        liste des plans allégée (2) : exclus {', '.join(champs)}")
