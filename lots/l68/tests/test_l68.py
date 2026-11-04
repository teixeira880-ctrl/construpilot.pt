"""Lot 68 — une vue 3D éloignée sur les mêmes calques n'est pas métrée."""
import pathlib
import sys

import ezdxf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.dxf_takeoff import extract_structural_metre  # noqa: E402


def _rect(msp, x, y, w, h, layer):
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": layer})


def test_far_view_on_same_layers_is_ignored():
    doc = ezdxf.new()
    msp = doc.modelspace()
    _rect(msp, 0, 0, 10, 8, "A-FLOR")
    _rect(msp, 0, 0, 5, 0.2, "A-WALL")
    _rect(msp, 2, 4, 3, 0.2, "S-BEAM")
    _rect(msp, 400, 400, 6, 0.2, "A-WALL")   # vue 3D lointaine
    _rect(msp, 400, 410, 4, 0.2, "S-BEAM")
    m = extract_structural_metre(doc, 1.0)
    assert m["method"] == "polygones_calques_bet"
    assert abs(m["walls_ml"] - 5.0) < 0.05
    assert abs(m["beams_ml"] - 3.0) < 0.05
