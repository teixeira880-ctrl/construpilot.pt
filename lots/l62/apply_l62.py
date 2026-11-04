"""Lot 62 — chiffrage automatique : un prix de bibliothèque doit correspondre au même TYPE de travail (test réel en prod .pt, 04/11).

Constat : « Demolição de azulejos de parede » chiffrée 50,70 €/m² avec l'article « Azulejo de parede » (fourniture
et pose de faïence) — mots communs, action contraire. Et 167 des 322 articles de la bibliothèque partagée PT portent
le même libellé « Instalação e desmontagem de estaleiro » quelle que soit leur catégorie (import corrompu).
Correctif (engines/assistant_quote_pricing.py, FR + PT) : un prix trouvé n'est retenu que si la ligne et l'article
sont de la même famille de travail (démolition / installation de chantier / travaux) ; sinon la ligne passe au
filet suivant (catalogue ConstruPilot puis estimation marquée « à vérifier »).
Usage : python3 lots/l62/apply_l62.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "assistant_quote_pricing.py"
s = f.read_text(encoding="utf-8")
if "Lot 62" in s:
    print("déjà appliqué"); print("L62 OK"); sys.exit(0)
for a in ("def find_price(designation, unit, sources):", "async def build_lines(", "import unicodedata"):
    if a not in s:
        print(f"ANCRE {a!r} introuvable — ARRÊT, rien écrit"); sys.exit(1)
ADD = '''

# --- Lot 62 : même famille de travail entre la ligne et l'article de bibliothèque ---
_DEMOL_WORDS = ("demoli", "demol", "remoc", "remocao", "remover", "picagem", "levantamento de", "arranque",
                "depose", "arrachage", "enlevement", "curage", "decroutage")
_SITE_WORDS = ("estaleiro", "installation de chantier", "repli de chantier", "base vie", "base de vida")


def _work_family(text):
    t = " " + "".join(c for c in unicodedata.normalize("NFKD", str(text or "").lower())
                      if not unicodedata.combining(c)) + " "
    if any(w in t for w in _SITE_WORDS):
        return "site"
    if any(w in t for w in _DEMOL_WORDS):
        return "demolition"
    return "work"


_find_price_lot62_base = find_price


def find_price(designation, unit, sources):
    match = _find_price_lot62_base(designation, unit, sources)
    if match and _work_family(designation) != _work_family(match.get("price_reference_label")):
        return None
    return match
'''
f.write_text(s.rstrip("\n") + "\n" + ADD, encoding="utf-8")
(root / "backend" / "tests" / "test_l62.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l62.py").read_bytes())
print("ok backend/engines/assistant_quote_pricing.py + backend/tests/test_l62.py")
print("L62 OK")
