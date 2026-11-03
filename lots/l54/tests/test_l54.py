"""Lot 54 — métré DXF de coffrage par éléments fermés sur les calques BET."""
import pathlib
import sys

import ezdxf

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.dxf_takeoff import extract_structural_metre  # noqa: E402


def _rect(msp, x, y, w, h, layer, **kw):
    msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": layer, **kw})


def _doc():
    doc = ezdxf.new()
    doc.header["$INSUNITS"] = 6
    if "HIDDEN" not in doc.linetypes:
        doc.linetypes.add("HIDDEN", pattern=[0.5, 0.25, -0.25])
    msp = doc.modelspace()
    _rect(msp, 0, 0, 10, 8, "A-FLOR")                       # dalle 80 m²
    _rect(msp, 0, 0, 5, 0.2, "A-WALL")                       # voile 5 m × 0,20
    _rect(msp, 0, 3, 4, 0.18, "A-WALL")                      # voile 4 m × 0,18
    _rect(msp, 0, 6, 6, 0.2, "A-WALL", linetype="HIDDEN")    # voile de l'étage au-dessus : exclu
    _rect(msp, 2, 2, 5, 0.2, "01-Murs_structure_Stylo_No__2")  # fond de plan architecte : exclu
    _rect(msp, 7, 1, 0.12, 0.24, "S-COLS")                   # poteau 12×24 …
    msp.add_line((7, 1), (7.12, 1.24), dxfattribs={"layer": "S-COLS"})  # … coupé par sa hachure
    _rect(msp, 1, 5, 3, 0.2, "S-BEAM")                       # poutre 3 m × 0,20
    return doc


def test_polygon_method_reads_bet_layers_only():
    m = extract_structural_metre(_doc(), 1.0)
    assert m["method"] == "polygones_calques_bet"
    assert m["slab_area_m2"] == 80.0
    assert abs(m["walls_ml"] - 9.0) < 0.05          # 5 + 4 ; caché et fond de plan exclus
    assert m["wall_area_m2"] == 1.72
    assert m["partitions_ml"] == 0.0
    assert m["columns_count"] == 1                  # poteau coupé en deux compté une fois
    assert abs(m["beams_ml"] - 3.0) < 0.05
    assert m["detected"]["wall_area_m2"] == 1.72


def test_plan_without_bet_layers_keeps_old_method():
    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_line((0, 0), (5, 0), dxfattribs={"layer": "MURS"})
    m = extract_structural_metre(doc, 1.0)
    assert m.get("method") != "polygones_calques_bet"
