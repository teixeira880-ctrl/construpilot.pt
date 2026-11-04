"""Lot 92 — emprise des voiles et des poutres mesurée par paires de traits."""
import ezdxf

from engines.dxf_takeoff import extract_structural_metre


def _pair(m, layer, x0, y0, length, th):
    m.add_line((x0, y0), (x0 + length, y0), dxfattribs={"layer": layer})
    m.add_line((x0, y0 + th), (x0 + length, y0 + th), dxfattribs={"layer": layer})


def test_wall_and_beam_areas_from_pairs():
    d = ezdxf.new("R2018"); d.header["$INSUNITS"] = 5
    for n in ("BEGT - Coffrage - Murs", "BEGT - Coffrage - Murs coupé", "BEGT - Coffrage - Poutre"):
        d.layers.add(n)
    m = d.modelspace()
    for k in range(5):
        _pair(m, "BEGT - Coffrage - Murs coupé", 0, k * 500, 1000, 20)
        _pair(m, "BEGT - Coffrage - Murs", 0, k * 500, 1000, 20)
    for k in range(3):
        _pair(m, "BEGT - Coffrage - Poutre", 0, 3000 + k * 500, 600, 30)
    r = extract_structural_metre(d, 0.01)
    assert abs(r["walls_ml"] - 50.0) < 0.6 and abs(r["wall_area_m2"] - 10.0) < 0.2
    assert abs(r["detected"]["wall_thickness_m"] - 0.20) < 0.005
    assert r["beams_method"] == "poutres_par_paires"
    assert abs(r["beams_ml"] - 18.0) < 0.3 and abs(r["detected"]["beam_w_m"] - 0.30) < 0.01
