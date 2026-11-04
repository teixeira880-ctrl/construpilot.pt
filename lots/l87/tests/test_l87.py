"""Lot 87 — DXF : miroir non signalé, diagnostics regroupés, poteaux hachurés comptés, dalle ouverte « à mesurer »."""
import ezdxf

from engines.cad_geometry import walk_entities
from engines.dxf_takeoff import extract_structural_metre


def _doc():
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = 5  # cm
    m = d.modelspace()
    for i in range(5):  # 5 poteaux 30×30 tracés en traits + hachure, sans bloc
        x = i * 500
        for a, b in (((x, 0), (x + 30, 0)), ((x + 30, 0), (x + 30, 30)), ((x + 30, 30), (x, 30)), ((x, 30), (x, 0))):
            m.add_line(a, b, dxfattribs={"layer": "BEGT - Coffrage - Poteaux"})
        h = m.add_hatch(dxfattribs={"layer": "BEGT - Coffrage - Poteaux"})
        h.paths.add_polyline_path([(x, 0), (x + 30, 0), (x + 30, 30), (x, 30)], is_closed=True)
    for i in range(30):  # dalle en lignes ouvertes
        m.add_line((i * 100, 1000), (i * 100 + 90, 1000), dxfattribs={"layer": "BEGT - Coffrage - Dalle"})
    tiny = m.add_hatch(dxfattribs={"layer": "BEGT - Coffrage - Dalle"})
    tiny.paths.add_polyline_path([(0, 0), (30, 0), (30, 30), (0, 30)], is_closed=True)  # 0,09 m²
    for i in range(40):  # cercles miroirs (extrusion 0,0,-1)
        m.add_circle((i * 10, 2000), 5, dxfattribs={"layer": "MURS", "extrusion": (0, 0, -1)})
    return d


def test_hatched_columns_counted_and_open_slab_to_measure():
    r = extract_structural_metre(_doc(), 0.01)
    assert r["columns_count"] == 5
    assert {"w_cm": 30, "h_cm": 30} in r["detected"]["col_sections"]
    assert r["slab_area_m2"] == 0.0 and r["slab_status"] == "contours_ouverts"


def test_mirrored_entities_not_reported_and_issues_grouped():
    d = _doc()
    issues = []
    list(walk_entities(d, diagnostics=issues))
    assert not [i for i in issues if i["code"] == "NON_PLANAR_GEOMETRY"]
    m = d.modelspace()
    for i in range(30):
        m.add_circle((i * 10, 3000), 5, dxfattribs={"extrusion": (0, 1, 0)})
    issues = []
    list(walk_entities(d, diagnostics=issues))
    np_ = [i for i in issues if i["code"] == "NON_PLANAR_GEOMETRY"]
    assert len(np_) == 1 and np_[0]["count"] == 30
