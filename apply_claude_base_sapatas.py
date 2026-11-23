"""Base das paredes/pilares do piso das fundações = topo das sapatas (As dominante dos rótulos), lida NA MESMA planta
(23/11/2026, planta FON do processo AES/TZ). Tudo-ou-nada; aceita as duas arquiteturas (pod lower_dxf_bytes / GitHub base_level)."""
import sys

P = "backend/engines/metre/volumes_tool.py"
s = open(P, encoding="utf-8").read()
if "dominante das sapatas desta planta" in s:
    print("já aplicado", P); sys.exit(0)
bloco = '''    if levels.get("niveau_base_murs_m") is None:
        # Planta de fundações: a base das paredes/pilares é o topo das sapatas (As dominante dos rótulos), lida nesta mesma planta.
        try:
            from engines.metre.fondations_dxf import fondations_takeoff
            _fon = fondations_takeoff(dxf_bytes)
            _as_sap = (_fon.get("totals") or {}).get("as_dominante_ngf")
        except Exception:  # noqa: BLE001
            _as_sap = None
        if _as_sap is not None:
            levels["niveau_base_murs_m"] = _as_sap
            levels["source"] = ((levels.get("source") or "") + f" ; base das paredes = As {_as_sap:.2f} NGF dominante das sapatas desta planta (topo das fundações)").strip(" ;")
'''
anc_pod = '''        else:
            out["findings"].append({"severity": "to_clarify", "subject": "Piso inferior sem AS de laje legível",'''
anc_fim = "    for k, v in (levels_override or {}).items():\n"
if s.count(anc_pod) == 1:
    i = s.index(anc_fim, s.index(anc_pod))
    s = s[:i] + bloco + s[i:]
elif s.count(anc_fim) == 1:
    s = s.replace(anc_fim, bloco + anc_fim, 1)
else:
    print(f"ERRO {P}: nenhuma âncora única (pod {s.count(anc_pod)}×, levels_override {s.count(anc_fim)}×)")
    for i, l in enumerate(s.splitlines(), 1):
        if "levels_override or {}" in l or "Piso inferior sem AS" in l:
            print(f"   linha {i}: {l.strip()[:150]}")
    sys.exit(1)
open(P, "w", encoding="utf-8").write(s)
print("OK", P)
