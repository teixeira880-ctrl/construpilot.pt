"""Lot 124pt (construpilot.pt) — Estúdio do Ateliê : botão « Repor » rebentava com
ReferenceError `textoRepor is not defined` (EstudioAtelier.jsx:575, desde efb4708e).
Correção : usa diretamente o texto de confirmação. Diagnóstico SavingsCard para a próxima ronda.
Usage : python3 lots/audit_28_11/l124pt/apply_l124pt.py /app pt — idempotente."""
import pathlib, sys
root = pathlib.Path(sys.argv[1])
f = root / "frontend/src/components/atelier/EstudioAtelier.jsx"
OLD = 'window.confirm(textoRepor || "Repor o modelo'
NEW = 'window.confirm("Repor o modelo'
if not f.exists():
    print("ABSENT    EstudioAtelier.jsx")
else:
    t = f.read_text(encoding="utf-8")
    if "textoRepor" not in t:
        print("DÉJÀ      EstudioAtelier.jsx : textoRepor já não existe")
    elif t.count(OLD) == 1:
        f.write_text(t.replace(OLD, NEW, 1), encoding="utf-8"); print("OK        EstudioAtelier.jsx : textoRepor removido")
    else:
        print("IGNORÉ    EstudioAtelier.jsx — âncora diferente")
s = root / "frontend/src/components/SavingsCard.jsx"
if s.exists():
    L = s.read_text(encoding="utf-8").split("\n")
    print("--- DIAGNÓSTICO SavingsCard.jsx (linhas com montantes/€) :")
    for i, l in enumerate(L):
        if "€" in l or "toFixed" in l or "toLocaleString" in l or "Math.round" in l:
            print(f"{i+1:5d}| {l[:220]}")
