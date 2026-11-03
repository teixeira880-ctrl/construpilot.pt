"""Lot 55 — le devis structure DWG inclut le coffrage des poteaux."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.dxf_takeoff import cost_structural  # noqa: E402


def _metre(**kw):
    m = {"walls_ml": 10.0, "columns_count": 4, "slab_area_m2": 50.0, "beams_ml": 0.0,
         "detected": {"col_sections": [{"w_cm": 20, "h_cm": 40}] * 4}}
    m.update(kw)
    return m


def _col_line(est):
    return [ln for lot in est["lots"] for ln in lot["lines"] if ln["unit"] == "m²" and "col_cof" not in ln
            and ln["total"] and ("oteaux" in str(ln) or "ilares" in str(ln))]


def test_column_formwork_from_sections():
    est = cost_structural(_metre(), {"storey_height_m": 2.5})
    cat = next(c for c in est["by_category"] if c["key"] == "poteaux")
    assert cat["coffrage_m2"] == 12.0          # 4 × 2×(0,20+0,40) × 2,5
    lines = _col_line(est)
    assert len(lines) == 1 and lines[0]["total"] == 720.0
    base = cost_structural(_metre(columns_count=0, detected={}), {"storey_height_m": 2.5})
    assert est["totals"]["coffrage_m2"] == round(base["totals"]["coffrage_m2"] + 12.0, 1)


def test_column_formwork_uniform_section_and_levels():
    est = cost_structural(_metre(detected={}), {"storey_height_m": 3.0, "n_levels": 2,
                                                 "col_w_m": 0.25, "col_h_m": 0.25})
    cat = next(c for c in est["by_category"] if c["key"] == "poteaux")
    assert cat["coffrage_m2"] == 24.0          # 4 × 1,0 m × 3 m × 2 niveaux
