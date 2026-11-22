"""Aplica no pod a correção LEADER/extrusion (cad_geometry.walk_entities) por âncora de texto. Idempotente."""
import sys
p = "backend/engines/cad_geometry.py"
s = open(p, encoding="utf-8").read()
new = "if entity.dxf.is_supported('extrusion') else (0,0,1)"
if new in s:
    print("já aplicado"); sys.exit(0)
old = "ext=tuple(entity.dxf.get('extrusion',(0,0,1)))"
if s.count(old) != 1:
    print(f"ERRO: âncora encontrada {s.count(old)}× (esperado 1)"); sys.exit(1)
s = s.replace(old, old + " " + new, 1)
open(p, "w", encoding="utf-8").write(s)
print("OK", p)
