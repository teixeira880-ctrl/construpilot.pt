"""Lote 65 PT — devis automatiques : le filet « catalogue ConstruPilot » appliquait les prix FRANÇAIS au Portugal.

Test réel en prod .pt (04/11) : « Demolição de azulejos » 31 €/m² et « Revestimento cerâmico » 80 €/m² = prix du
catalogue France (7 + 24 ; 38 + 42), alors que l'estimation PT applique un coefficient pays (0,68 par défaut ;
Porto 0,67, Lisboa 0,74, Braga 0,60…).
Correctif (engines/assistant_quote_pricing.py, PT seulement) : le prix catalogue est multiplié par le coefficient
régional portugais de l'estimation (region_coef), comme l'estimation.
Usage : python3 lots/l65/apply_l65.py <racine /app>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
f = root / "backend" / "engines" / "assistant_quote_pricing.py"
s = f.read_text(encoding="utf-8")
if "Lote 65" in s:
    print("déjà appliqué"); print("L65 PT OK"); sys.exit(0)
if "def catalog_price(designation, unit, lot=" not in s or "match = catalog_price(" not in s:
    print("ANCRE catalog_price (Lot 50) introuvable — ARRÊT, rien écrit"); sys.exit(1)
ADD = '''

# --- Lote 65 : coefficient pays/região sur le prix catalogue (catalogue = prix France) ---
_catalog_price_lot65_base = catalog_price


def catalog_price(designation, unit, lot=""):
    m = _catalog_price_lot65_base(designation, unit, lot)
    if not m:
        return m
    try:
        from engines.estimation import region_coef
        coef = float(region_coef("PT", None))
    except Exception:  # noqa: BLE001
        coef = 0.68
    if 0 < coef < 1.5:
        m = dict(m)
        m["unit_price_ht"] = round(float(m["unit_price_ht"]) * coef, 2)
        m["price_reference_label"] = (m.get("price_reference_label") or "") + f" · coeficiente Portugal {coef:g}"
    return m
'''
f.write_text(s.rstrip("\n") + "\n" + ADD, encoding="utf-8")
(root / "backend" / "tests" / "test_l65.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l65.py").read_bytes())
print("ok backend/engines/assistant_quote_pricing.py + backend/tests/test_l65.py")
print("L65 PT OK")
