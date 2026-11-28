"""Lot 123pt (construpilot.pt) — mesmas 16 correções do l122pt, mas aplicadas FICHEIRO A FICHEIRO :
um ficheiro cuja âncora não existe no servidor é IGNORADO sem bloquear os outros.
Fallbacks robustos : `import traceback` (assistant_tool) e `prev_z = z0` (especialidades) são inseridos
mesmo que o texto à volta seja diferente do GitHub.
Diagnóstico : mostra as linhas à volta de `textoRepor` em EstudioAtelier.jsx (erro « not defined »).
Usage : python3 lots/audit_28_11/l123pt/apply_l123pt.py /app pt
Idempotente."""
import json, pathlib, re, sys
root = pathlib.Path(sys.argv[1]); here = pathlib.Path(__file__).resolve().parent
data = json.loads((here / "patches.json").read_text(encoding="utf-8"))
groups = {}
for p in data["patches"]:
    groups.setdefault(p["file"], []).append(p)

def fallback(fn, t):
    if fn.endswith("bet_core/assistant_tool.py") and not re.search(r"^import traceback", t, re.M):
        m = re.search(r"^(import [^\n]+\n)", t, re.M)
        if m:
            return t[:m.end()] + "import traceback  # CP-AUDIT-PT\n" + t[m.end():], "fallback import traceback"
    if fn.endswith("calc_lots/especialidades.py") and "prev_z = z0" not in t:
        m = re.search(r"^(\s*)prev, prev_q = [^\n]+\n", t, re.M)
        if m and "z0" in t[:m.start()]:
            return t[:m.end()] + m.group(1) + "prev_z = z0  # CP-AUDIT-PT\n" + t[m.end():], "fallback prev_z"
    return None, None

for fn, ps in groups.items():
    f = root / fn
    if not f.exists():
        print(f"ABSENT    {fn}"); continue
    t = f.read_text(encoding="utf-8"); todo = []; done = 0; ok = True
    for p in ps:
        if p["new"] in t: done += 1
        elif t.count(p["old"]) == 1: todo.append(p)
        else: ok = False
    if not ok:
        nt, why = fallback(fn, t)
        if nt:
            f.write_text(nt, encoding="utf-8"); print(f"OK        {fn} ({why})")
        else:
            print(f"IGNORÉ    {fn} — âncora diferente no servidor (nada alterado neste ficheiro)")
        continue
    for p in todo:
        t = t.replace(p["old"], p["new"], 1)
    if todo: f.write_text(t, encoding="utf-8")
    print(("OK        " if todo else "DÉJÀ      ") + f"{fn} : {len(todo)} aplicada(s), {done} já presente(s)")

ea = root / "frontend/src/components/atelier/EstudioAtelier.jsx"
if ea.exists():
    L = ea.read_text(encoding="utf-8").split("\n")
    hits = [i for i, l in enumerate(L) if "textoRepor" in l or "setTextoRepor" in l]
    print("--- DIAGNÓSTICO textoRepor : ocorrências nas linhas", [h + 1 for h in hits])
    for h in hits[:3]:
        for j in range(max(0, h - 12), min(len(L), h + 8)):
            print(f"{j+1:5d}| {L[j]}")
        print("-----")
    for i, l in enumerate(L[:400]):
        if "useState" in l and ("texto" in l.lower() or "repor" in l.lower()):
            print(f"{i+1:5d}| {l}")
