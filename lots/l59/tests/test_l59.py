"""Lot 59 — calculateurs : ouvertures > murs refusées ; unités PT."""
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.calculator_validation import run_validated  # noqa: E402


def test_openings_larger_than_walls_rejected():
    with pytest.raises(ValueError):
        run_validated("paint", {"length": 1, "width": 1, "height": 2.5, "doors": 5, "windows": 5,
                                "coats": 2, "include_ceiling": False})


def test_normal_paint_still_ok():
    r = run_validated("paint", {"length": 4, "width": 3, "height": 2.5, "doors": 1, "windows": 1,
                                "coats": 2, "include_ceiling": True})
    net = next(x for x in r["results"] if x["value"] == 43.5)
    assert net


def test_no_french_units_on_pt():
    src = (pathlib.Path(__file__).resolve().parents[1] / "engines" / "calculators.py").read_text(encoding="utf-8")
    if "Superfície" not in src:  # site FR : rien à vérifier
        return
    assert not re.findall(r'"unit": "(?:carton|bidon|plaque|rouleau|sac \d+ kg)"', src)
