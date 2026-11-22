"""Aplica no pod (por âncoras, idempotente):
1) «Recurso inacessível» passa a listar os identificadores REAIS (plantas plan_… e ficheiros CAD doc_… desta conta) para o modelo
   corrigir em vez de inventar outro id em ciclo;
2) anti-ciclo por ferramenta: 3 falhas da mesma ferramenta no mesmo pedido → as chamadas seguintes dessa ferramenta já não são
   executadas (respondem logo stop_retrying), mesmo quando o modelo as lança em paralelo com ids diferentes."""
import sys
p = "backend/routes/assistant.py"
s = open(p, encoding="utf-8").read()
if "_available_ids_hint" in s:
    print("já aplicado"); sys.exit(0)

def rep(old, new, label):
    global s
    if s.count(old) != 1:
        print(f"ERRO: âncora «{label}» encontrada {s.count(old)}× (esperado 1)"); sys.exit(1)
    s = s.replace(old, new, 1)

rep("async def _allowed_plan(plan_id: str, user_id: str) -> dict:\n",
    '''async def _available_ids_hint(user_id: str) -> str:
    """Identificadores reais que o modelo pode usar (plantas importadas + ficheiros CAD dos processos), mais recentes primeiro."""
    try:
        plans = [p async for p in db.plans_takeoff.find({"user_id": user_id}, {"_id": 0, "plan_id": 1, "filename": 1}).sort("created_at", -1).limit(15)]
        cads = [d async for d in db.assistant_docs.find({"user_id": user_id, "filename": {"$regex": r"\\.(dwg|dxf)$", "$options": "i"}},
                                                        {"_id": 0, "doc_id": 1, "filename": 1}).sort("created_at", -1).limit(25)]
    except Exception:  # noqa: BLE001
        return ""
    parts = [f"{p['plan_id']} ({p.get('filename') or ''})" for p in plans] + [f"{d['doc_id']} ({d.get('filename') or ''})" for d in cads]
    return ("Identificadores válidos nesta conta (copiar exatamente; um doc_… DWG/DXF é aceite como plan_id): " + "; ".join(parts)) if parts \\
        else "Nenhuma planta nem ficheiro DWG/DXF encontrado nesta conta: pede ao utilizador para anexar o ficheiro."


async def _allowed_plan(plan_id: str, user_id: str) -> dict:
''', "_allowed_plan")

rep('''    except PermissionError:
        result = {"ok": False, "error": "Recurso inacessível: o documento referido não pertence a esta conta ou já não existe. Pede ao utilizador para (re)anexar o ficheiro à mensagem (não é um problema de assinatura)."}
''', '''    except PermissionError:
        result = {"ok": False, "error": "Recurso inacessível: o identificador dado não corresponde a nenhum documento desta conta. Não inventes outro identificador.",
                  "available": await _available_ids_hint(user["user_id"])}
''', "except PermissionError (tool_turn)")

rep('''        fails = cache.setdefault("__fails__", {})
        fkey = f"{name}|{str(result.get('error'))[:160]}"
        fails[fkey] = fails.get(fkey, 0) + 1
''', '''        fails = cache.setdefault("__fails__", {})
        fkey = f"{name}|{str(result.get('error'))[:160]}"
        fails[fkey] = fails.get(fkey, 0) + 1
        per_tool = cache.setdefault("__fails_tool__", {})
        per_tool[name] = per_tool.get(name, 0) + 1
        if per_tool[name] >= 3:
            cache.setdefault("__blocked__", set()).add(name)
''', "anti-ciclo")

rep('''        if not read_tool and key in cache:
            result, attachments = cache[key]
''', '''        if name in cache.get("__blocked__", ()):
            result = {"ok": False, "stop_retrying": True,
                      "error": f"{name} já falhou 3 vezes neste pedido: não foi executada outra vez. Continua com as outras ferramentas e diz ao utilizador, uma só vez, o que não foi possível ler."}
        elif not read_tool and key in cache:
            result, attachments = cache[key]
''', "cache lookup")
open(p, "w", encoding="utf-8").write(s)
print("OK", p)
