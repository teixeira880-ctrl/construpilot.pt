"""Lot 64 — escalier → devis : le devis sortait avec toutes les lignes à 0 € (« prix à compléter »).

Règle du fondateur : « fais un devis » = devis chiffré automatiquement. Correctif (routes/stairs.py, FR + PT) :
béton, coffrage et aciers chiffrés avec les prix catalogue ConstruPilot des escaliers (mêmes prix que le métré
DWG : 320 €/m³, 90 €/m², 1,70 €/kg HT, marge par défaut intégrée), prix de revient renseigné (marge suivie),
lignes marquées « estimé, à vérifier ».
Usage : python3 lots/l64/apply_l64.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "backend" / "routes" / "stairs.py"
s = f.read_text(encoding="utf-8")
if "Lot 64" in s:
    print("déjà appliqué"); print(f"L64 {site.upper()} OK"); sys.exit(0)
A = '    doc = DocIn(doc_type="quote"'
if s.count(A) != 1:
    print("ANCRE DocIn introuvable dans stairs.py — ARRÊT, rien écrit"); sys.exit(1)
LBL = {"fr": "Prix catalogue ConstruPilot (escalier béton, fourniture + pose) — à vérifier",
       "pt": "Preço do catálogo ConstruPilot (escada em betão, fornecimento + aplicação) — a verificar"}[site]
ADD = ('    # Lot 64 : devis escalier chiffré automatiquement (prix catalogue escalier, marge par défaut intégrée)\n'
       '    from engines.dxf_takeoff import DEFAULTS as _SD, PRICES as _SP\n'
       '    _sm = 1 + float(_SD.get("margin_pct", 12.0)) / 100.0\n'
       '    for _ln in lines:\n'
       '        _u = (_ln.unit or "").lower().replace("³", "3").replace("²", "2")\n'
       '        _base = {"m3": _SP.get("beton_escalier", 0), "m2": _SP.get("coffrage_escalier", 0), "kg": _SP.get("acier_escalier", 0)}.get(_u, 0)\n'
       '        if _base and not _ln.unit_price_ht:\n'
       '            _ln.unit_price_ht = round(float(_base) * _sm, 2)\n'
       '            _ln.cost_price_ht = round(float(_base), 2)\n'
       '            _ln.price_missing = False\n'
       '            _ln.price_estimated = True\n'
       f'            _ln.price_reference_label = {LBL!r}\n')
f.write_text(s.replace(A, ADD + A), encoding="utf-8")
(root / "backend" / "tests" / "test_l64.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l64.py").read_bytes())
print("ok backend/routes/stairs.py + backend/tests/test_l64.py")
print(f"L64 {site.upper()} OK")
