"""Liga a ferramenta de fundações ao Assistente (23/11/2026). Tudo-ou-nada, por âncoras estáveis:
1) escreve backend/engines/metre/fondations_dxf.py a partir de /tmp/fondations_dxf.github.py (git show prévio);
2) acrescenta a ferramenta «compute_foundations» à lista de ferramentas (antes de generate_conversation_report);
3) acrescenta o despacho em _exec_tool_inner (antes do bloco AUTODESK). Usa _dxf_bytes do pod quando existir."""
import sys

A = "backend/routes/assistant.py"
s = open(A, encoding="utf-8").read()
if '"compute_foundations"' in s:
    print("já aplicado", A); src_ok = True
else:
    anc1 = '    {"type": "function", "name": "generate_conversation_report", "strict": True,'
    anc2 = "    if name in AUTODESK_TOOL_NAMES:\n"
    for anc, label in ((anc1, "tool generate_conversation_report"), (anc2, "dispatch AUTODESK")):
        if s.count(anc) != 1:
            print(f"ERRO {A}: âncora «{label}» encontrada {s.count(anc)}× (esperado 1)")
            key = anc.strip()[:30]
            for i, l in enumerate(s.splitlines(), 1):
                if key.split('"')[0].strip() and ("generate_conversation_report" in l if label.startswith("tool") else "AUTODESK_TOOL_NAMES" in l):
                    print(f"   linha {i}: {l.strip()[:150]}")
            sys.exit(1)
    tool_def = '''    {"type": "function", "name": "compute_foundations", "strict": True,
     "description": "Fundações a partir do DWG/DXF de cofragem das fundações (camadas Fondations/Etiquettes de fondations ou AES-Semelle): reagrupa os rótulos impressos (S n A×B×ht, SF n L×ht, As: cota), fecha os contornos desenhados e devolve, sapata a sapata, o volume de betão (S = A×B×ht do rótulo; SF = área desenhada × ht), a cota As e o fundo (As − ht). Nada é estimado: rótulo ilegível ou contorno sem rótulo ficam explícitos. A escavação não é calculada (falta a cota do terreno).",
     "parameters": {"type": "object", "properties": {"plan_id": {"type": "string", "description": "planta DWG/DXF das fundações importada (um doc_… DWG de um processo também é aceite)"}},
                    "required": ["plan_id"], "additionalProperties": False}},
'''
    dispatch = '''    if name == "compute_foundations":
        from engines.metre.fondations_dxf import compact as _fon_compact, fondations_takeoff
        try:
            from engines.metre.volumes_run import _dxf_bytes as _fon_loader
        except ImportError:
            _fon_loader = None
        if _fon_loader is not None:
            raw = await _fon_loader(db, args["plan_id"], uid)
        else:
            from engines.plan_sources import load_cad_source as _fon_lcs
            src = await _fon_lcs(db, args["plan_id"], uid, "converted_dxf") or await _fon_lcs(db, args["plan_id"], uid, "original")
            raw = src if isinstance(src, (bytes, bytearray)) else (base64.b64decode(src["data_b64"]) if src else None)
        if not raw or raw[:4] == b"AC10":
            return {"ok": False, "error": "Nenhum DXF convertido para esta planta de fundações."}
        res = await asyncio.to_thread(fondations_takeoff, raw)
        return {"ok": True, **_fon_compact(res)}
'''
    s = s.replace(anc1, tool_def + anc1, 1).replace(anc2, dispatch + anc2, 1)
    open(A, "w", encoding="utf-8").write(s)
    print("OK", A)

E = "backend/engines/metre/fondations_dxf.py"
new = open("/tmp/fondations_dxf.github.py", encoding="utf-8").read()
if "fondations_takeoff" not in new:
    print("ERRO: /tmp/fondations_dxf.github.py inválido"); sys.exit(1)
open(E, "w", encoding="utf-8").write(new)
print("OK", E)
