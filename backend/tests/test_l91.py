"""Lot 91 — murs « coupés » mesurés par paires (doublons exclus) ; dalle ouverte refermée."""
import ezdxf

from engines.dxf_takeoff import extract_structural_metre


def _wall(m, layer, x0, y0, length, th=20):
    m.add_line((x0, y0), (x0 + length, y0), dxfattribs={"layer": layer})
    m.add_line((x0, y0 + th), (x0 + length, y0 + th), dxfattribs={"layer": layer})


def test_cut_walls_measured_once_at_axis():
    d = ezdxf.new("R2018"); d.header["$INSUNITS"] = 5
    for n in ("BEGT - Coffrage - Murs", "BEGT - Coffrage - Murs coupé"):
        d.layers.add(n)
    m = d.modelspace()
    for k in range(5):                      # 5 murs de 10 m, tracés sur les DEUX calques (doublon) + trait répété
        _wall(m, "BEGT - Coffrage - Murs coupé", 0, k * 500, 1000)
        _wall(m, "BEGT - Coffrage - Murs", 0, k * 500, 1000)
        _wall(m, "BEGT - Coffrage - Murs coupé", 0, k * 500, 1000)
    r = extract_structural_metre(d, 0.01)
    assert r["walls_method"] == "murs_coupes_par_paires"
    assert abs(r["walls_ml"] - 50.0) < 0.6


def test_open_slab_lines_rebuilt():
    d = ezdxf.new("R2018"); d.header["$INSUNITS"] = 5
    m = d.modelspace()
    # deux panneaux 10 × 10 m tracés en segments (avec micro-jours de 2 cm)
    for x0 in (0, 1020):
        pts = [(x0, 0), (x0 + 1000, 0), (x0 + 1000, 1000), (x0, 1000)]
        for i in range(4):
            a, b = pts[i], pts[(i + 1) % 4]
            for t in range(5):
                sa = (a[0] + (b[0] - a[0]) * t / 5, a[1] + (b[1] - a[1]) * t / 5)
                sb = (a[0] + (b[0] - a[0]) * (t + 1) / 5 - (2 if t == 4 else 0) * (1 if b[0] > a[0] else -1 if b[0] < a[0] else 0),
                      a[1] + (b[1] - a[1]) * (t + 1) / 5)
                m.add_line(sa, sb, dxfattribs={"layer": "BEGT - Coffrage - Dalle"})
    r = extract_structural_metre(d, 0.01)
    assert r["slab_status"] == "contours_reconstitues"
    assert 190 <= r["slab_area_m2"] <= 202
