"""Lote 66 PT — erro de português visível no Assistente: « 4 preço médios de mercado aprendidos ».

Correção : « 1 preço médio de mercado aprendido » / « 4 preços médios de mercado aprendidos » (QuoteDraftCard e
LearnedPricesPanel).
Usage : python3 lots/l66/apply_l66.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
F = root / "frontend" / "src" / "components"
EDITS = {
 F / "assistant" / "QuoteDraftCard.jsx": ('{d.estimated_lines} preço médio{d.estimated_lines > 1 ? "s" : ""} de mercado aprendidos',
   '{d.estimated_lines} {d.estimated_lines > 1 ? "preços médios" : "preço médio"} de mercado {d.estimated_lines > 1 ? "aprendidos" : "aprendido"}'),
 F / "library" / "LearnedPricesPanel.jsx": ('{items.length} preço médio{items.length > 1 ? "s" : ""} de mercado aprendidos',
   '{items.length} {items.length > 1 ? "preços médios" : "preço médio"} de mercado {items.length > 1 ? "aprendidos" : "aprendido"}'),
}
out = {}
for f, (old, new) in EDITS.items():
    s = f.read_text(encoding="utf-8")
    if new in s:
        print(f"déjà appliqué : {f.name}"); continue
    if s.count(old) != 1:
        print(f"ANCRE introuvable dans {f.name} — ARRÊT, rien écrit"); sys.exit(1)
    out[f] = s.replace(old, new)
for f, s in out.items():
    f.write_text(s, encoding="utf-8"); print(f"ok {f.name}")
(root / "backend" / "tests" / "test_l66.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l66.py").read_bytes())
print("L66 PT OK")
