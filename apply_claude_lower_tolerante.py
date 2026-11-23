"""Piso inferior tolerante (23/11/2026): um lower_dxf_plan_id inexistente nesta conta deixa de fazer falhar
compute_concrete_volumes em ciclo («Recurso inacessível» ×3). Passa a ser ignorado com um finding explícito,
e o cálculo continua com as cotas impressas (sapatas/etiquetas). Tudo-ou-nada, âncoras verbatim do pod."""
import sys

P = "backend/engines/metre/volumes_run.py"
s = open(P, encoding="utf-8").read()
if "Piso inferior ignorado" in s:
    print("já aplicado", P); sys.exit(0)

anc1 = '''    lower = None
    if lower_dxf_plan_id:
        try:
            lower = await _dxf_bytes(db, lower_dxf_plan_id, user_id)
        except RuntimeError as exc:
            return {"ok": False, "error": f"DWG do piso inferior não convertido em DXF: {exc}"}
'''
new1 = '''    lower = None
    lower_note = None
    if lower_dxf_plan_id:
        try:
            lower = await _dxf_bytes(db, lower_dxf_plan_id, user_id)
        except RuntimeError as exc:
            return {"ok": False, "error": f"DWG do piso inferior não convertido em DXF: {exc}"}
        except Exception:  # noqa: BLE001 — planta inexistente/inacessível: ignorar, nunca falhar o cálculo inteiro em ciclo
            lower, lower_note = None, (f"Planta do piso inferior «{lower_dxf_plan_id}» não encontrada nesta conta: ignorada. "
                                       "A base das paredes vem só das cotas impressas (sapatas/etiquetas desta planta). Não inventes outro identificador.")
'''
anc2 = "    res = await asyncio.to_thread(compute_volumes, raw, formwork, coupes, levels, None, lower)\n"
new2 = anc2 + '''    if lower_note:
        res.setdefault("findings", []).append({"severity": "to_clarify", "subject": "Piso inferior ignorado", "explanation": lower_note})
'''
for anc, new, label in ((anc1, new1, "bloco lower"), (anc2, new2, "res = compute_volumes")):
    if s.count(anc) != 1:
        print(f"ERRO {P}: âncora «{label}» encontrada {s.count(anc)}× (esperado 1)")
        for i, l in enumerate(s.splitlines(), 1):
            if "lower_dxf_plan_id" in l or "asyncio.to_thread(compute_volumes" in l:
                print(f"   linha {i}: {l.strip()[:150]}")
        sys.exit(1)
    s = s.replace(anc, new, 1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P)
