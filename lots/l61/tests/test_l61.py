"""Lot 61 — isolation : R visé non atteint signalé avec l'épaisseur minimale."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.calculator_validation import run_validated  # noqa: E402
from engines.calculators import CALCULATORS  # noqa: E402

MAT = next(o for o in next(f for f in CALCULATORS["insulation"]["fields"] if f["name"] == "material")["options"]
           if "verre" in o or "vidro" in o or o == "laine_de_verre")


def test_target_r_not_reached_is_flagged():
    r = run_validated("insulation", {"area": 50, "material": MAT, "thickness_mm": 50, "target_r": 5})
    assert r.get("warnings")
    need = [x for x in r["results"] if x["unit"] == "mm" and x["value"] >= 150]
    assert need and need[0]["value"] % 10 == 0


def test_target_reached_no_warning():
    r = run_validated("insulation", {"area": 50, "material": MAT, "thickness_mm": 200, "target_r": 5})
    assert not r.get("warnings")
