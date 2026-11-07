"""Auditoria V2 (07/11/2026) — verificador estático de isolamento entre contas.

Para cada rota autenticada com um identificador no caminho, exige uma prova de
verificação de dono (filtro user_id/company_id ou helper de posse conhecido).
Uso : python scripts/audit_tenant_scope.py  → código 1 se surgir uma rota nova
sem verificação. Não substitui um teste com duas organizações reais.
"""
import ast
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(__file__), "..", "routes")
OWNER = re.compile(r"(user_id|company_id|_scope|_owned|owned|_get\(|_check|_assert|ensure|can_|_require|"
                   r"_load_plan|_get_plan|_plan_or_404|_plan_page|_plan_and_study|_pc_owner_id|_project_quote|"
                   r"editable_permit|build_deposit_invoice|enqueue_study|_owner|has_access|_member)")
# Rotas sem recurso de outro utilizador (o identificador do caminho não é um dado de cliente).
ALLOW = {"prompt_fill.py:preencher"}


def scan() -> list[str]:
    bad = []
    for fn in sorted(os.listdir(ROOT)):
        if not fn.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(ROOT, fn), encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            route = [ast.unparse(d) for d in node.decorator_list if "router." in ast.unparse(d)]
            if not route or not re.search(r"\{\w+\}", route[0]):
                continue
            args = ast.unparse(node.args)
            if "current_user" not in args or "admin" in args.lower():
                continue
            if f"{fn}:{node.name}" in ALLOW:
                continue
            if not OWNER.search(ast.unparse(node)):
                bad.append(f"{fn}:{node.lineno} {node.name} {route[0][:80]}")
    return bad


if __name__ == "__main__":
    found = scan()
    for b in found:
        print("SEM VERIFICAÇÃO DE DONO:", b)
    print(f"{len(found)} rota(s) a verificar")
    sys.exit(1 if found else 0)
