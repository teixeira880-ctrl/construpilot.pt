"""Aplica no pod: APS_DWG_PREFERRED=true → conversão DWG pelo AutoCAD da Autodesk PRIMEIRO; se falhar, LibreDWG como antes.
Sem a variável, nada muda. Idempotente, por âncora."""
import sys
p = "backend/engines/dwg_convert.py"
s = open(p, encoding="utf-8").read()
if "APS_DWG_PREFERRED" in s:
    print("já aplicado"); sys.exit(0)
anchor = "    from engines import dwg_local\n    if dwg_local.available():"
if s.count(anchor) != 1:
    print(f"ERRO: âncora encontrada {s.count(anchor)}× (esperado 1)"); sys.exit(1)
block = '''    aps_tried = False
    if os.environ.get("APS_DWG_PREFERRED") == "true" and os.environ.get("APS_DWG_ENABLED") == "true":
        # AutoCAD na nuvem Autodesk primeiro (leitura fiel do DWG); qualquer falha → conversor local, como antes.
        from engines.autodesk_dwg import convert
        aps_tried = True
        try:
            output, metadata = await convert(dwg_bytes, user_id=user_id)
            _validate_dxf(output)
            if provenance is not None: provenance.update(metadata)
            return output
        except Exception as exc:  # noqa: BLE001 — o conversor local continua a ser a rede de segurança
            logger.warning("Autodesk (preferido) falhou, a usar o conversor local: %s", type(exc).__name__)
            if provenance is not None: provenance.update(fallback_reason=f"aps_preferred_failed:{type(exc).__name__}")
'''
s = s.replace(anchor, block + anchor, 1)
old2 = '    if os.environ.get("APS_DWG_ENABLED") == "true":\n        from engines.autodesk_client import AutodeskError'
if s.count(old2) != 1:
    print(f"ERRO: segunda âncora encontrada {s.count(old2)}× (esperado 1)"); sys.exit(1)
s = s.replace(old2, '    if os.environ.get("APS_DWG_ENABLED") == "true" and not aps_tried:\n        from engines.autodesk_client import AutodeskError', 1)
open(p, "w", encoding="utf-8").write(s)
print("OK", p)
