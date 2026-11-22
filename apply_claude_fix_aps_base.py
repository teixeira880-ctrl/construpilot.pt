"""Aplica no pod a correção de api_base() (Automation API: região/versão duplicadas → 404). Idempotente, por âncora."""
import sys
p = "backend/engines/autodesk_client.py"
s = open(p, encoding="utf-8").read()
if "if base.endswith('/v3'):" in s:
    print("já aplicado"); sys.exit(0)
old = """def api_base():
    return f"{config('APS_AUTOMATION_BASE_URL').rstrip('/')}/{config('APS_AUTOMATION_REGION')}/v3"
"""
new = """def api_base():
    # O painel Live tem APS_AUTOMATION_BASE_URL já com região e versão (…/da/us-east/v3): juntar outra vez «/us-east/v3»
    # dava …/da/us-east/v3/us-east/v3 e todas as chamadas Automation respondiam 404.
    base = config('APS_AUTOMATION_BASE_URL').rstrip('/')
    region = config('APS_AUTOMATION_REGION').strip('/')
    if base.endswith('/v3'):
        return base
    if region and base.endswith(f'/{region}'):
        return f"{base}/v3"
    return f"{base}/{region}/v3"
"""
if s.count(old) != 1:
    print(f"ERRO: âncora encontrada {s.count(old)}× (esperado 1)"); sys.exit(1)
open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
print("OK", p)
