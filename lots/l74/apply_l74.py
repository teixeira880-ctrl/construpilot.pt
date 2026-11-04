"""Lot 74 PT — preços de referência da estrutura (DWG → orçamento, escadas) com o coeficiente de Portugal.

Constatação (teste em produção construpilot.pt) : o orçamento de escada e o orçamento de estrutura DWG usavam os
preços de referência franceses (betão escada 320 €/m³ + margem = 358,40 €/m³), enquanto a estimativa e o catálogo
já aplicam o coeficiente regional de Portugal (0,68, Lote 65). Correção (engines/dxf_takeoff.py, só PT) : a
tabela PRICES de referência é multiplicada pelo coeficiente regional PT ; os preços próprios do utilizador
(params["prices"]) continuam prioritários e não são alterados.
Uso : python3 lots/l74/apply_l74.py <raiz /app>   (idempotente ; ARRÊT se faltar uma âncora)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "dxf_takeoff.py"
s = f.read_text(encoding="utf-8")
if "Lot 74" in s:
    print("déjà appliqué"); print("L74 PT OK"); sys.exit(0)
A = ('    "protection_securite":  6000.0,\n}\n# Ratios aciers kg/m³\n')
if s.count(A) != 1:
    print("ANCRE PRICES introuvable dans dxf_takeoff.py — ARRÊT, rien écrit"); sys.exit(1)
B = ('    "protection_securite":  6000.0,\n}\n'
     '# Lot 74 PT : preços de referência ajustados ao mercado português (mesmo coeficiente regional da estimativa)\n'
     'try:\n'
     '    from engines.estimation import region_coef as _rc74\n'
     '    _COEF_PT74 = float(_rc74("PT", None))\n'
     'except Exception:  # pragma: no cover\n'
     '    _COEF_PT74 = 0.68\n'
     'PRICES = {k: (round(v * _COEF_PT74, 2) if isinstance(v, (int, float)) else v) for k, v in PRICES.items()}\n'
     '# Ratios aciers kg/m³\n')
s = s.replace(A, B)
f.write_text(s, encoding="utf-8")
t55 = root / "backend" / "tests" / "test_l55.py"
if t55.exists():
    q = t55.read_text(encoding="utf-8")
    A2 = '    assert len(lines) == 1 and lines[0]["total"] == 720.0\n'
    B2 = ('    from engines.dxf_takeoff import PRICES  # Lot 74 PT : preço de referência com coeficiente PT\n'
          '    assert len(lines) == 1 and lines[0]["total"] == round(12.0 * PRICES["coffrage_poteau"], 2)\n')
    if q.count(A2) == 1:
        t55.write_text(q.replace(A2, B2), encoding="utf-8"); print("ok tests/test_l55.py (preço PT)")
(root / "backend" / "tests" / "test_l74.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l74.py").read_bytes())
print("ok backend/engines/dxf_takeoff.py + backend/tests/test_l74.py")
print("L74 PT OK")
