"""Iteration 170 — native CAD dimension chains: collinear DXF dimensions → chain check against the overall dimension; forced text kept as evidence."""
import sys

sys.path.append("/app/backend")

import ezdxf

from engines.native_chains import build_chains, native_chains_for_page
from engines.plan_dxf import process_dxf


def _dim(x1, x2, y, value, override=None, measured=None):
    return {"x1": x1, "y1": y, "x2": x2, "y2": y, "measured_m": measured if measured is not None else value, "value_m": value,
            "raw_text": override, "override": override is not None, "location": "calque COTES"}


def test_chain_of_native_dimensions_matches_overall_and_flags_forced_text():
    px = 100.0  # 100 px per metre
    dims = [_dim(0, 400, 50, 4.0), _dim(400, 420, 50, 0.20), _dim(420, 920, 50, 5.0), _dim(920, 930, 50, 0.10),  # chain incl. thicknesses
            _dim(0, 930, 20, 9.30),  # overall on a parallel line, same interval
            _dim(0, 400, 300, 4.05, override="4.05", measured=4.0),  # forced text ≠ geometry
            _dim(100, 100, 600, 3.0)]  # degenerate, ignored by direction bucketing (zero length → still a line)
    dims[-1]["y2"] = 900
    res = build_chains(dims, px_per_m=px, plan_id="p1", page=0, size=(1000, 1000))
    chain = res["chains"][0]
    assert [s["value_m"] for s in chain["segments"]] == [4.0, 0.2, 5.0, 0.1]
    assert chain["declared_total"]["value_m"] == 9.3 and chain["calculation"]["result"] == 9.3 and chain["findings"] == []
    assert chain["calculation"]["formula"] == "4 + 0.2 + 5 + 0.1 = 9.3 m" and chain["segments"][0]["box"] == [0.0, 0.05, 0.4, 0.05]
    assert chain["segments"][0]["origin"] == "native_text"
    assert res["overrides"] == [{"label": "D6", "text": "4.05", "value_m": 4.05, "measured_m": 4.0, "difference_m": 0.05}]
    # a mismatching overall dimension produces a demonstrated 3 cm difference, never an auto-correction
    dims[4]["value_m"] = dims[4]["measured_m"] = 9.33
    res2 = build_chains(dims, px_per_m=px, plan_id="p1", page=0, size=(1000, 1000))
    f = res2["chains"][0]["findings"]
    assert len(f) == 1 and "3 cm" in f[0]["explanation"] and f[0]["severity"] == "demonstrated"


def test_real_dxf_roundtrip_through_plan_processor(tmp_path):
    """Synthetic DXF in metres: 3 consecutive dimensions + overall; the plan pipeline extracts them and the chain closes."""
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for x1, x2 in ((0, 4), (4, 4.2), (4.2, 9.2)):
        msp.add_linear_dim(base=(0, -1), p1=(x1, 0), p2=(x2, 0), dimstyle="EZDXF").render()
        msp.add_line((x1, 0), (x2, 0))
    msp.add_linear_dim(base=(0, -2), p1=(0, 0), p2=(9.2, 0), dimstyle="EZDXF").render()
    msp.add_line((0, 0), (0, 3))
    path = tmp_path / "chain.dxf"
    doc.saveas(path)
    parsed = process_dxf(path.read_bytes(), "chain.dxf")
    page = parsed["pages"][0]
    assert len(page["dxf_dimensions"]) == 4
    res = native_chains_for_page(page, plan_id="plan_test", page_index=0)
    assert res["px_per_m"] > 0 and res["chains"], res
    chain = res["chains"][0]
    assert [round(s["value_m"], 2) for s in chain["segments"]] == [4.0, 0.2, 5.0]
    assert chain["declared_total"] and round(chain["declared_total"]["value_m"], 2) == 9.2 and chain["findings"] == []
    assert all(0 <= v <= 1 for s in chain["segments"] for v in s["box"])
