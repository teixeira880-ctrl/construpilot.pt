"""Lote 80 PT — SEO: a página inicial de construpilot.pt mostrava um título FRANCÊS.

Constatação (teste em produção, 04/11): o separador do browser em https://construpilot.pt/ mostrava
« Bureau d’études BTP en ligne avec IA · ConstruPilot » (e descrição francesa). Causa: growth/routes.py
(código copiado do .fr) escolhia de propósito a variante NÃO portuguesa das substituições SEO aprovadas.
Correção (só PT): prefere a variante portuguesa ; uma variante com ar francês nunca é servida no .pt
(fica o título da própria página).
Uso : python3 lots/l80/apply_l80.py <raiz /app>   (idempotente ; ARRÊT se faltar a âncora)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "growth" / "routes.py"
s = f.read_text(encoding="utf-8")
if "Lote 80" in s:
    print("déjà appliqué"); print("L80 PT OK"); sys.exit(0)
A = ('        chosen = next((v for v in variants if v[0] and not _looks_portuguese(v[0])), variants[0])\n'
     '        out.setdefault(path, {}).update({"title": chosen[0], "description": chosen[1]})\n')
if s.count(A) != 1:
    print("ANCRE seo-overrides introuvable dans growth/routes.py — ARRÊT, rien écrit"); sys.exit(1)
B = ('        # Lote 80 PT : construpilot.pt é PT → variante portuguesa primeiro ; nunca servir um título francês\n'
     '        chosen = (next((v for v in variants if v[0] and _looks_portuguese(v[0])), None)\n'
     '                  or next((v for v in variants if v[0] and not _looks_french80(v[0])), None))\n'
     '        if chosen:\n'
     '            out.setdefault(path, {}).update({"title": chosen[0], "description": chosen[1]})\n')
s = s.replace(A, B)
A2 = '@router.get("/seo-overrides")\n'
B2 = ('_FR_MARKERS80 = ("bureau d", "en ligne", "devis", "travaux", "déposez", "maison", "chantier", "études",\n'
      '                 "coût", "prix au m", "estimez", "rénovation")\n\n\n'
      'def _looks_french80(title: str) -> bool:\n'
      '    """Lote 80 PT : título com ar francês (não deve aparecer no .pt)."""\n'
      '    s = (title or "").lower()\n'
      '    return any(m in s for m in _FR_MARKERS80) and not _looks_portuguese(title)\n\n\n'
      + A2)
if s.count(A2) != 1:
    print("ANCRE route seo-overrides introuvable — ARRÊT, rien écrit"); sys.exit(1)
s = s.replace(A2, B2)
f.write_text(s, encoding="utf-8")
(root / "backend" / "tests" / "test_l80.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l80.py").read_bytes())
print("ok backend/growth/routes.py + backend/tests/test_l80.py")
print("L80 PT OK")
