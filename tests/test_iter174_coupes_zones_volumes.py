"""Iter 174 — têtes de coupe du plan de coffrage, recalage PDF ↔ DXF par les axes, murs complétés, volumes par zone de coupe."""
import json
import math
import sys
from pathlib import Path

import pymupdf
import pytest
from shapely.geometry import LineString, Polygon

sys.path.insert(0, "/app/backend")
from engines.metre.coupe_marks import locate_coupe_marks, pair_heads  # noqa: E402
from engines.metre.coupe_zones import assign_wall_zones, coupe_sheet_data  # noqa: E402
from engines.metre.grid_align import fit_similarity, register, to_model  # noqa: E402

EVAL = Path("/app/test_reports/eval")
COFFRAGE = Path("/tmp/coffrage.pdf")
needs_eval = pytest.mark.skipif(not (EVAL / "volumes_RDC_coupes.json").exists(), reason="rapport d'évaluation absent")
needs_pdf = pytest.mark.skipif(not COFFRAGE.exists(), reason="plan de coffrage local absent")


def test_pair_heads_requires_same_number_and_perpendicular_join():
    heads = [{"number": 4, "x": 0, "y": 0, "dir": [0, -1]}, {"number": 4, "x": 100, "y": 0, "dir": [0, -1]},
             {"number": 4, "x": 0, "y": 300, "dir": [0, -1]}, {"number": 7, "x": 50, "y": 0, "dir": [0, -1]}]
    res = pair_heads(heads)
    assert len(res["coupes"]) == 1 and res["coupes"][0]["name"] == "4-4" and res["coupes"][0]["length_pt"] == 100
    assert {h["number"] for h in res["unpaired_heads"]} == {4, 7}


def test_similarity_fit_recovers_scale_rotation_translation():
    src = [(0, 0), (100, 0), (100, 50)]
    dst = [(10, 20), (10, 20 + 176.4), (10 - 88.2, 20 + 176.4)]  # scale 1.764, rotation +90°
    T = fit_similarity(src, dst)
    assert abs(T["scale"] - 1.764) < 1e-6 and abs(T["rotation_deg"] - 90) < 1e-6 and T["residual"] < 1e-6
    reg = register({"A": {"point": (0, 0), "angle_deg": 0}, "B": {"point": (100, 0), "angle_deg": 90}, "C": {"point": (0, 50), "angle_deg": 0}},
                   {"A": {"point": (10, 20), "angle_deg": 90}, "B": {"point": (10, 20 + 176.4), "angle_deg": 0}, "C": {"point": (10 - 88.2, 20), "angle_deg": 90}},
                   declared_pt_per_m=1 / 1.764)
    assert reg["ok"] and reg["scale_state"] == "confirmed" and reg["residual_m"] < 1e-6
    x, y = to_model(reg, 100, 0)
    assert abs(x - 10) < 1e-6 and abs(y - (20 + 176.4)) < 1e-6


def test_register_refuses_single_intersection():
    reg = register({"A": {"point": (0, 0), "angle_deg": 0}, "B": {"point": (0, 0), "angle_deg": 90}},
                   {"A": {"point": (0, 0), "angle_deg": 0}, "B": {"point": (0, 0), "angle_deg": 90}}, declared_pt_per_m=None)
    assert not reg["ok"] and "deux intersections" in reg["error"]


def test_sheet_data_picks_proven_base_closest_to_dominant_and_zone_heights():
    coupes = {"summary": {"dominant": {"niveau_base_murs_m": 89.16}},
              "sheets": [{"page": 4, "coupes_checked": [{"name": "4-4", "as_plancher_haut_m": 93.37, "ai_plancher_haut_m": 93.17, "wall_thickness_cm": [16, 20], "slab_thickness_cm": [20],
                                                         "heights": [{"base_level_m": 88.54, "h_mur_m": 4.63, "chain_proof_cm": None}, {"base_level_m": 89.34, "h_mur_m": 3.83, "chain_proof_cm": [83, 15, 284]}]},
                                                        {"name": "8-8", "as_plancher_haut_m": 93.37, "ai_plancher_haut_m": 93.17, "wall_thickness_cm": [16], "slab_thickness_cm": [20],
                                                         "heights": [{"base_level_m": 89.16, "h_mur_m": 4.01, "chain_proof_cm": [400]}, {"base_level_m": 89.17, "h_mur_m": 4.0, "chain_proof_cm": [400]}]}]}]}
    sd = coupe_sheet_data(coupes)
    assert sd["4-4"]["base_used_m"] == 89.34 and sd["4-4"]["h_mur_m"] == 3.83 and not sd["4-4"]["single_base"]
    assert sd["8-8"]["single_base"] and sd["8-8"]["chain_proof"]
    walls = [Polygon([(0, 0), (5, 0), (5, 0.16), (0, 0.16)]), Polygon([(30, 0), (35, 0), (35, 0.2), (30, 0.2)]), Polygon([(100, 0), (104, 0), (104, 0.2), (100, 0.2)])]
    traces = [{"name": "8-8", "line": LineString([(2, -2), (2, 3)])}, {"name": "4-4", "line": LineString([(32, -2), (32, 3)])}]
    z = assign_wall_zones(walls, traces, sd, default_h_m=4.01, extent=None)
    by = {r["wall_index"]: r for r in z["rows"]}
    assert by[0]["coupe"] == "8-8" and by[0]["state"] == "confirmed" and math.isclose(by[0]["volume_m3"], 5 * 0.16 * 4.01, rel_tol=1e-3)
    assert by[1]["coupe"] == "4-4" and by[1]["state"] == "to_clarify" and by[1]["h_m"] == 3.83
    assert by[2]["coupe"] is None and by[2]["state"] == "to_clarify" and by[2]["h_m"] == 4.01
    assert z["volume_confirmed_m3"] > 0 and z["volume_to_clarify_m3"] > 0


@needs_pdf
def test_coffrage_pdf_all_sixteen_coupes_located_no_address_false_positive():
    page = pymupdf.open(COFFRAGE)[0]
    res = locate_coupe_marks(page, pt_per_m=72 / 0.0254 / 50)
    assert res["names"] == [f"{n}-{n}" for n in range(1, 17)] and len(res["coupes"]) == 23 and not res["unpaired_heads"]
    assert all(1.4 <= c["length_m"] <= 8.5 for c in res["coupes"])
    assert "1-15" not in res["names"] and "2-6" not in res["names"]


@needs_eval
def test_eval_volumes_registered_completed_walls_and_scope():
    full = json.loads((EVAL / "volumes_RDC_coupes.json").read_text())
    reg = full["registration"]
    assert reg["ok"] and set(reg["common_axes"]) == {"X1", "Y3", "Y4"} and reg["residual_m"] < 0.01 and reg["scale_state"] == "confirmed"
    walls = full["sources"]["dxf"]["walls"]
    assert walls["closed_faces_only"]["length_total_m"] < 200 and walls["length_total_m"] > 900
    assert walls["completion"]["thicknesses_used_cm"] == [15, 16, 18, 20, 23, 25, 28] and walls["completion"]["unpaired"]["length_m"] > 0
    assert full["scope"]["clipped_to_plan"] and len(full["coupes_located"]) == 23
    confirmed = [c for c in full["coupes_located"] if c["thickness_check"]["state"] == "confirmed"]
    assert len(confirmed) >= 18
    murs = next(l for l in full["lines"] if l["element"].startswith("Murs"))
    assert 200 < murs["net"] < 350 and murs["detail"]["by_coupe_m3"]
    assert full["total_m3"] and full["rule"]
