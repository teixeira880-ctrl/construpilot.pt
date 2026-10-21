"""Iter 172 — cotes dessinées obliques (auto-calibration du tirage), métré coffrage DXF par faces fermées, croisement nappes ↔ dalle."""
import io
import sys
from pathlib import Path

import ezdxf
import pymupdf
import pytest

sys.path.insert(0, "/app/backend")
from engines.metre.coffrage_dxf import coffrage_takeoff  # noqa: E402
from engines.metre.nappes_cross import cross_nappes  # noqa: E402
from engines.metre.oblique_dims import build_chains, match_labels  # noqa: E402
from engines.metre.rebar_schedule import extract_rebar_schedule  # noqa: E402

PLANS = Path("/app/tests/fixtures/eval/plans")
SUP, INF = PLANS / "GO-B3-R0-303_nappe_superieure.pdf", PLANS / "GO-B3-R0-302_nappe_inferieure.pdf"
PT_PER_M_50 = 72 / 0.0254 / 50
needs_plans = pytest.mark.skipif(not SUP.exists(), reason="plans d'évaluation absents")


def _tables(native):
    return [(b[0] - 6, b[1] - 4, b[2] + 6, b[3] + 4) for tbl in ("ha_bars", "mesh") for r in ((native.get(tbl) or {}).get("rows") or []) for b in [r["bbox_pt"]]]


@needs_plans
def test_oblique_dimensions_detect_fit_to_page_print_ratio_on_303():
    page = pymupdf.open(SUP)[0]
    res = match_labels(page, PT_PER_M_50, exclude_rects=_tables(extract_rebar_schedule(page)))
    cal = res["calibration"]
    assert cal["self_calibrated"] is True and abs(cal["print_ratio"] - 0.982) < 0.003 and cal["samples"] >= 40
    assert len(res["dimensions"]) >= 80
    assert all(abs(d["difference_mm"]) <= max(10, 4 * d["value_m"]) for d in res["dimensions"])
    assert all(d["state"] == "confirmed" and d["bounds_source"] in ("ticks", "chain") for d in res["dimensions"])
    assert all(u["state"] == "indeterminate" for u in res["unmatched"])


@needs_plans
def test_oblique_dimensions_302_not_rescaled():
    page = pymupdf.open(INF)[0]
    res = match_labels(page, PT_PER_M_50, exclude_rects=_tables(extract_rebar_schedule(page)))
    assert res["calibration"]["self_calibrated"] is False and len(res["dimensions"]) >= 90
    assert any(d["angle_deg"] not in (0.0, 90.0) for d in res["dimensions"])


def test_build_chains_merges_dashes_only_when_collinear():
    dashes = [(0, 0, 5, 0, 5), (8, 0, 13, 0, 5), (16, 0, 21, 0, 5), (0, 30, 5, 30, 5)]
    chains = build_chains(dashes)
    lengths = sorted(round(c[3] - c[2], 1) for c in chains)
    assert lengths == [5.0, 21.0]


def _synthetic_dxf() -> bytes:
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 6
    msp = doc.modelspace()
    for name in ("BEGT - Coffrage - Murs", "BEGT - Coffrage - Poteaux", "BEGT - Coffrage - Poutre", "BEGT - Coffrage - Dalle"):
        doc.layers.add(name)
    wall = [(0, 0), (10, 0), (10, 0.2), (0, 0.2)]
    for a, b in zip(wall, wall[1:] + wall[:1]):
        msp.add_line(a, b, dxfattribs={"layer": "BEGT - Coffrage - Murs"})
    h = msp.add_hatch(dxfattribs={"layer": "BEGT - Coffrage - Poteaux"})
    h.paths.add_polyline_path([(20, 0), (20.25, 0), (20.25, 0.5), (20, 0.5)], is_closed=True)
    beam = [(0, 5), (6, 5), (6, 5.4), (0, 5.4)]
    for a, b in zip(beam, beam[1:] + beam[:1]):
        msp.add_line(a, b, dxfattribs={"layer": "BEGT - Coffrage - Poutre"})
    slab = [(0, 10), (12, 10), (12, 18), (0, 18)]
    for a, b in zip(slab, slab[1:] + slab[:1]):
        msp.add_line(a, b, dxfattribs={"layer": "BEGT - Coffrage - Dalle"})
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_coffrage_takeoff_from_closed_faces_with_indeterminate_volumes():
    res = coffrage_takeoff(_synthetic_dxf())
    e = res["elements"]
    assert e["walls"]["count"] == 1 and e["walls"]["rows"][0]["length_m"] == 10.0 and e["walls"]["rows"][0]["thickness_m"] == 0.2
    assert e["walls"]["rows"][0]["formula"] == "10.00 m × 20 cm = 2.000 m²"
    assert e["columns"]["count"] == 1 and (e["columns"]["rows"][0]["w_cm"], e["columns"]["rows"][0]["h_cm"]) == (25.0, 50.0)
    assert e["beams"]["count"] == 1 and e["beams"]["rows"][0]["length_m"] == 6.0 and e["beams"]["rows"][0]["width_m"] == 0.4
    assert e["slab"]["net_area_m2"] == 96.0
    volumes = [l for l in res["lines"] if "volume" in l["element"]]
    assert volumes and all(l["state"] == "indeterminate" and l["net"] is None and l["missing"] for l in volumes)


def test_cross_nappes_lists_only_and_coverage():
    lower = {"mesh": {"count": 1, "rows": [{"mark": "T1", "panel": "TS25", "total_count": 2, "mass_kg": 80.0, "cuts": [{"count": 3, "width_cm": 240, "height_cm": 400}]}]},
             "mesh_recap": {"rows": [{"panel": "TS25", "count": 6, "width_cm": 600, "height_cm": 240}], "mass_laid_kg": 160.0}, "ha_bars": {"count": 2, "total_mass_kg": 10.0, "rows": [{"mark": "1", "diameter_mm": 12, "unit_length_cm": 200, "total_count": 4}]}, "partial": True}
    upper = {"mesh": {"count": 1, "rows": [{"mark": "T1", "panel": "TS35", "total_count": 1, "mass_kg": 50.0, "cuts": []}]}, "mesh_recap": None,
             "ha_bars": {"count": 1, "total_mass_kg": 5.0, "rows": [{"mark": "1", "diameter_mm": 12, "unit_length_cm": 200, "total_count": 4}]}, "partial": False}
    res = cross_nappes(lower, upper, slab_area_m2=100.0)
    assert res["layers"]["nappe inférieure"]["mesh_laid_area_m2_from_cuts"] == 57.6 and res["layers"]["nappe inférieure"]["mesh_ordered_area_m2_from_recap"] == 86.4
    assert res["duplicates"]["mesh"]["common_marks"] == 1 and len(res["duplicates"]["mesh"]["different"]) == 1
    assert res["duplicates"]["ha"]["identical"] == 1
    assert any(c["ratio"] == 0.576 for c in res["coverage"])
    assert any(f["subject"].startswith("Repères MESH") for f in res["findings"])
