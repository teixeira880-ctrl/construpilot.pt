"""Lot 69 — quantitatif élec/plomberie chiffré sans bibliothèque (prix de référence estimés)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.mep.quantities import _ref_price, price  # noqa: E402


def test_reference_prices_fill_every_known_code():
    lines = [{"code": "EL-PRISE", "designation": "Socle", "unit": "u", "qty": 10},
             {"code": "EL-DDR-A-40", "designation": "DDR", "unit": "u", "qty": 1},
             {"code": "EL-CABLE-6", "designation": "Câble", "unit": "m", "qty": 12},
             {"code": "PL-PVC-40", "designation": "PVC", "unit": "m", "qty": 3.7},
             {"code": "PL-GS-EVAC", "designation": "Entonnoir", "unit": "u", "qty": 1}]
    tot = price(lines, [])
    assert tot["unpriced_lines"] == 0 and tot["estimated_lines"] == 5 and tot["total_ht"] > 0
    assert _ref_price("PL-GS-EVAC") != _ref_price("PL-GS")
    assert _ref_price("EL-CABLE-6") > _ref_price("EL-CABLE-1,5")
