"""Lot 63 — une emprise en L ne rend pas un plan juste « KO »."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import engines.plan_cotes as C  # noqa: E402


def _it(i, orient, val, x1, y1, x2, y2):
    return {"index": i, "orientation": orient, "indicated_m": val, "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def test_l_shape_is_not_an_error():
    items = [_it(1, "v", 9.89, 50, 100, 50, 1089), _it(2, "v", 6.74, 950, 100, 950, 1089)]
    fac = C._find_facades(items, 1000, 1200)
    assert fac and fac[0]["status"] == "nd"


def test_small_gap_on_rectangle_stays_ko():
    items = [_it(1, "v", 9.00, 50, 100, 50, 1000), _it(2, "v", 9.05, 950, 100, 950, 1005)]
    fac = C._find_facades(items, 1000, 1200)
    assert fac and fac[0]["status"] == "ko"


def test_conclusion_does_not_claim_equal_dimensions():
    rep = {"summary": {"ko": 0, "warn": 0}, "items": [], "chains": [], "elements": [],
           "facades": [{"status": "nd", "a_m": 9.89, "b_m": 6.74, "a_side": "gauche", "b_side": "droite", "delta_cm": -315}]}
    txt = C.quick_conclusion(rep)
    assert "9.89" in txt and ("rectangul" in txt or "retangular" in txt)
    assert "opposées sont égales" not in txt and "opostas são iguais" not in txt
