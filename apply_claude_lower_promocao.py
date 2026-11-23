"""lower_dxf_plan_id entra em PLAN_ARG_KEYS: o DWG anexado e passado explicitamente como piso inferior é promovido
doc_→plan_ em vez de «Recurso inacessível»/ignorado. v2 (23/11/2026): âncora dupla — o pod não tem base_plan_id."""
import re
import sys

P = "backend/routes/assistant.py"
s = open(P, encoding="utf-8").read()
m = re.search(r'PLAN_ARG_KEYS = \([^)]*\)', s)
if not m:
    print(f"ERRO {P}: linha PLAN_ARG_KEYS não encontrada"); sys.exit(1)
linha = m.group(0)
if '"lower_dxf_plan_id"' in linha:
    print("já aplicado", P); sys.exit(0)
nova = linha[:-1].rstrip() + ' "lower_dxf_plan_id",)' if linha.rstrip().endswith(',)') else linha[:-1] + ', "lower_dxf_plan_id")'
s = s.replace(linha, nova, 1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P, "→", nova)
