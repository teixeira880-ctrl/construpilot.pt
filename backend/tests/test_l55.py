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
    from engines.dxf_takeoff import PRICES  # Lot 74 PT : preço de referência com coeficiente PT
    assert len(lines) == 1 and lines[0]["total"] == round(12.0 * PRICES["coffrage_poteau"], 2)
    base = cost_structural(_metre(columns_count=0, detected={}), {"storey_height_m": 2.5})
    assert est["totals"]["coffrage_m2"] == round(base["totals"]["coffrage_m2"] + 12.0, 1)


def test_column_formwork_uniform_section_and_levels():
    est = cost_structural(_metre(detected={}), {"storey_height_m": 3.0, "n_levels": 2,
                                                 "col_w_m": 0.25, "col_h_m": 0.25})
    cat = next(c for c in est["by_category"] if c["key"] == "poteaux")
    assert cat["coffrage_m2"] == 24.0          # 4 × 1,0 m × 3 m × 2 niveaux


def test_r12_polylines_use_bet_polygon_method():
    import ezdxf
    from engines.dxf_takeoff import extract_structural_metre
    doc = ezdxf.new("R12")
    msp = doc.modelspace()

    def r(x, y, w, h, layer):
        msp.add_polyline2d([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": layer})
    r(0, 0, 10, 8, "A-FLOR")
    r(0, 0, 5, 0.2, "A-WALL")
    r(1, 1, 5, 0.2, "01-Murs_Stylo_No__2")
    r(7, 1, 0.25, 0.25, "S-COLS")
    m = extract_structural_metre(doc, 1.0)
    assert m["method"] == "polygones_calques_bet"
    assert abs(m["walls_ml"] - 5.0) < 0.05 and m["columns_count"] == 1 and m["slab_area_m2"] == 80.0


def test_metre_to_quote_records_cost_price():
    src = (pathlib.Path(__file__).resolve().parents[1] / "routes" / "plans_crud.py").read_text(encoding="utf-8")
    assert '"cost_price_ht": round(float(ln.get("pu", 0)), 2)' in src
