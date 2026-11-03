"""Lot 57 — l'assistant n'affiche plus à l'utilisateur ses erreurs internes d'outil (test réel en prod, 03/11).

Constat : devis gros œuvre demandé à l'assistant → la carte affichait au client
« Brouillon mis à jour · Arguments du devis invalides (lines → 1) : Value error, price_origin=… Corrige et
rappelle l'outil. » pendant que l'assistant se corrigeait tout seul (le devis final était juste).
Correctif (frontend ActionCard) : une erreur de validation destinée au modèle (devis) est affichée
« correction automatique en cours » ; les autres erreurs restent affichées telles quelles.

Usage : python3 lots/l57/apply_l57.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si l'ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "frontend" / "src" / "components" / "assistant" / "ActionCard.jsx"
s = f.read_text(encoding="utf-8")
if "Lot 57" in s:
    print("déjà appliqué"); print(f"L57 {site.upper()} OK"); sys.exit(0)
OLD = '{r.error && ` · ${r.error}`}'
LBL = {"fr": "correction automatique en cours", "pt": "correção automática em curso"}[site]
NEW = ('{r.error && ` · ${isQuote && /rappelle l.outil|volta a chamar a ferramenta|Arguments du devis invalides|Argumentos do or[çc]amento inv[áa]lidos/i.test(String(r.error))'
       f' ? "{LBL}" : r.error}}`}}{{/* Lot 57 : erreur interne destinée au modèle, jamais montrée brute */}}')
if s.count(OLD) != 1:
    print(f"ANCRE introuvable ({s.count(OLD)}/1) dans ActionCard.jsx — ARRÊT, rien écrit"); sys.exit(1)
if "const isQuote" not in s and "isQuote =" not in s:
    print("isQuote absent — ARRÊT, rien écrit"); sys.exit(1)
f.write_text(s.replace(OLD, NEW), encoding="utf-8")
t = pathlib.Path(__file__).resolve().parent / "tests" / "test_l57.py"
(root / "backend" / "tests" / "test_l57.py").write_bytes(t.read_bytes())
print("ok frontend/src/components/assistant/ActionCard.jsx + backend/tests/test_l57.py")
print(f"L57 {site.upper()} OK")
