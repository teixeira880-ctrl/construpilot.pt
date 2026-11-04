"""Lot 69 — plans d'exécution élec/plomberie : le quantitatif sortait avec 42 lignes à prix « null ».

Test réel en prod .fr (04/11) : maison 91 m², 42 postes (prises, DCL, DDR, câbles, PER, PVC…), aucun prix
(« prix issus EXCLUSIVEMENT de la bibliothèque » → sans bibliothèque, 0 €). Règle du fondateur : un devis est
chiffré automatiquement.
Correctif (engines/mep/quantities.py, FR + PT) : la bibliothèque de l'entreprise reste prioritaire ; à défaut,
prix de référence ConstruPilot (fourniture + pose, HT, marché 2026) marqué « estimé, à vérifier » ; au Portugal
coefficient pays 0,68 (identique à l'estimation).
Usage : python3 lots/l69/apply_l69.py <racine /app> <fr|pt>   (idempotent ; ARRÊT si une ancre manque)
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
site = sys.argv[2]
assert site in ("fr", "pt")
f = root / "backend" / "engines" / "mep" / "quantities.py"
s = f.read_text(encoding="utf-8")
if "Lot 69" in s:
    print("déjà appliqué"); print(f"L69 {site.upper()} OK"); sys.exit(0)
if "def price(lines: list[dict], library: list[dict] | None) -> dict:" not in s:
    print("ANCRE price() introuvable — ARRÊT, rien écrit"); sys.exit(1)
COEF = 1.0 if site == "fr" else 0.68
LBL = {"fr": "Prix de référence ConstruPilot (fourniture + pose) — estimé, à vérifier",
       "pt": "Preço de referência ConstruPilot (fornecimento + montagem) — estimado, a verificar"}[site]
ADD = f'''

# --- Lot 69 : prix de référence quand la bibliothèque de l'entreprise ne couvre pas la ligne ---
_REF_PRICES = {{  # € HT fourniture + pose, marché France 2026 (indicatif)
    "EL-PRISE-SPE": 60.0, "EL-PRISE-PT": 50.0, "EL-PRISE": 45.0, "EL-SORTIE-32": 90.0, "EL-SORTIE-20": 70.0,
    "EL-DCL": 55.0, "EL-APPLIQUE-EXT": 85.0, "EL-INTER": 40.0, "EL-VV": 55.0, "EL-RJ45": 55.0, "EL-CAT6": 3.5,
    "EL-COFFRET": 250.0, "EL-TABLEAU": 320.0, "EL-DDR-A": 95.0, "EL-DDR-F": 130.0, "EL-DDR-AC": 70.0,
    "EL-DISJ": 25.0, "EL-CONTACTEUR": 70.0, "EL-CABLE": 4.5, "EL-DAAF": 45.0, "EL-LES": 60.0,
    "PL-NOURRICE": 180.0, "PL-TUBE": 14.0, "PL-PVC": 24.0, "PL-CHUTE": 45.0, "PL-SIPHON": 25.0,
    "PL-ROBINET": 120.0, "PL-GS-EVAC": 45.0, "PL-GS": 85.0, "PL-COLLIER": 6.0, "PL-COULISSANT": 12.0,
    "PL-APPAREIL": 150.0, "PL-REGARD": 180.0,
}}
_REF_COEF = {COEF!r}


def _ref_price(code):
    code = str(code or "")
    for key in sorted(_REF_PRICES, key=len, reverse=True):
        if code == key or code.startswith(key + "-"):
            base = _REF_PRICES[key]
            if key == "EL-CABLE":  # section : 1,5 / 2,5 / 6 mm²
                sec = code[len(key) + 1:].replace(",", ".")
                try:
                    s_mm2 = float(sec)
                    base = 4.0 if s_mm2 <= 1.5 else 5.0 if s_mm2 <= 2.5 else 6.5 if s_mm2 <= 4 else 9.0 if s_mm2 <= 6 else 12.0
                except ValueError:
                    pass
            return round(base * _REF_COEF, 2)
    return None


_price_lot69_base = price


def price(lines, library):
    out = _price_lot69_base(lines, library)
    est = 0
    for ln in lines:
        if ln.get("unit_price") is None:
            pu = _ref_price(ln.get("code"))
            if pu is not None:
                ln["unit_price"] = pu
                ln["total"] = round(pu * float(ln.get("qty") or 0), 2)
                ln["price_source"] = {{"reference": "construpilot", "estimated": True, "label": {LBL!r}}}
                est += 1
    priced = sum(1 for ln in lines if ln.get("unit_price") is not None)
    total = round(sum(float(ln.get("total") or 0) for ln in lines if ln.get("unit_price") is not None), 2)
    out.update(priced_lines=priced, unpriced_lines=len(lines) - priced, total_ht=total if priced else None,
               estimated_lines=est)
    return out
'''
f.write_text(s.rstrip("\n") + "\n" + ADD, encoding="utf-8")
t = root / "backend" / "tests" / "test_mep_engine.py"
if t.exists():
    ts = t.read_text(encoding="utf-8")
    ts2 = ts.replace('    assert res["unpriced_lines"] > 0          # le reste reste « à chiffrer »',
                     '    assert res["unpriced_lines"] == 0 and res["estimated_lines"] > 0  # Lot 69 : le reste est estimé (référence)')
    if ts2 != ts:
        t.write_text(ts2, encoding="utf-8"); print("ok tests/test_mep_engine.py (règle Lot 69)")
(root / "backend" / "tests" / "test_l69.py").write_bytes((pathlib.Path(__file__).resolve().parent / "tests" / "test_l69.py").read_bytes())
print("ok backend/engines/mep/quantities.py + backend/tests/test_l69.py")
print(f"L69 {site.upper()} OK")
