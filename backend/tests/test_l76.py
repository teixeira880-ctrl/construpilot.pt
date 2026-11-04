"""Lot 76 — niveau fini plausible dans les symboles NGF."""
from engines.metre.level_symbols import parse_level_symbols


def _w(x, y, t):
    return (x, y, x + 10, y + 4, t)


def test_fini_kept_when_plausible():
    out = parse_level_symbols([_w(100, 96, "93,37b"), _w(100, 100, "NGF"), _w(100, 104, "93.44"), _w(100, 108, "20")])
    s = out["symbols"][0]
    assert s["as_plancher_m"] == 93.37 and s["as_fini_m"] == 93.44 and s["epaisseur_cm"] == 20


def test_neighbour_level_not_taken_as_fini():
    for other in ("110.48", "68.09"):
        out = parse_level_symbols([_w(100, 96, "68.72b"), _w(100, 100, "NGF"), _w(104, 104, other), _w(100, 108, "20")])
        assert out["symbols"][0]["as_fini_m"] is None
