"""bet_geo (23/11/2026): a chamada de visão de read_levels não tinha limite de tempo próprio — uma ligação
pendurada ao fornecedor prendia o estudo 20-30 min no passo «A ler cotas e terras suportadas nos cortes»
(observado em preview, job bet_91a595a295). Limite de 240 s: ao estourar, o except existente devolve os
avisos por defeito e o estudo CONTINUA. Âncora verbatim da linha da chamada."""
import sys

P = "backend/engines/bet_geo/levels_ai.py"
s = open(P, encoding="utf-8").read()
if "wait_for(llm(" in s:
    print("já aplicado", P); sys.exit(0)
anc = "        txt = await llm(SYSTEM, PROMPT.format(n=len(edges(b))), images=images, max_tokens=1500)"
if s.count(anc) != 1:
    print(f"ERRO {P}: âncora da chamada llm encontrada {s.count(anc)}× (esperado 1)")
    for i, l in enumerate(s.splitlines(), 1):
        if "await llm(" in l:
            print(f"   linha {i}: {l.rstrip()[:160]}")
    sys.exit(1)
novo = ("        import asyncio as _aio\n"
        "        # 240 s de teto próprio: uma ligação pendurada ao fornecedor não pode prender o estudo (regra best-effort)\n"
        "        txt = await _aio.wait_for(llm(SYSTEM, PROMPT.format(n=len(edges(b))), images=images, max_tokens=1500), 240)\n")
s = s.replace(anc + "\n", novo, 1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P)
