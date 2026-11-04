"""Lot 60 PT — le devis structure DWG est entièrement en portugais."""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.dxf_takeoff import cost_structural  # noqa: E402


def test_no_french_left_in_structural_quote():
    m = {"walls_ml": 41.2, "wall_area_m2": 8.24, "beam_area_m2": 0.8, "beams_ml": 4, "columns_count": 2,
         "slab_area_m2": 108, "escaliers_area_m2": 5, "escaliers_count": 1,
         "detected": {"col_sections": [{"w_cm": 25, "h_cm": 25}] * 2}}
    txt = json.dumps(cost_structural(m, {"storey_height_m": 2.7})["lots"], ensure_ascii=False)
    for fr in ("emprise", "lues", "(contour)", "ép.", "forfait"):
        assert fr not in txt, fr
    assert "contorno" in txt and '"vg"' in txt
