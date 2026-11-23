"""O ficheiro DWG anexado como piso inferior (lower_dxf_plan_id) também é promovido doc_… → plan_… (23/11/2026:
Martinho anexou o sous-sol como piso inferior e recebeu «Recurso inacessível» — a ponte não cobria este argumento)."""
import sys

P = "backend/routes/assistant.py"
s = open(P, encoding="utf-8").read()
if '"lower_dxf_plan_id")' in s.split("PLAN_ARG_KEYS", 1)[1][:400]:
    print("já aplicado", P); sys.exit(0)
anc = '"coupes_plan_id", "base_plan_id")'
if s.count(anc) != 1:
    print(f"ERRO {P}: âncora PLAN_ARG_KEYS encontrada {s.count(anc)}× (esperado 1)")
    for i, l in enumerate(s.splitlines(), 1):
        if "PLAN_ARG_KEYS" in l:
            print(f"   linha {i}: {l.strip()[:160]}")
    sys.exit(1)
s = s.replace(anc, '"coupes_plan_id", "base_plan_id", "lower_dxf_plan_id")', 1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P)
