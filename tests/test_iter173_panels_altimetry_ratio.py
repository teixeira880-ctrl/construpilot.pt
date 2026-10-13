"""Iter 173 — étiquettes de panneaux treillis, altimétries DXF, ratio acier/béton Arche ↔ DXF."""
import json
import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, "/app/backend")
from engines.metre.altimetry_dxf import LEVEL, SIZE, altimetry_labels  # noqa: E402
from engines.metre.rebar_schedule import extract_rebar_schedule  # noqa: E402
from engines.metre.steel_ratio import pair_beams, ratio_lines  # noqa: E402
from engines.metre.treillis_labels import panel_labels  # noqa: E402

PLANS = Path("/app/tests/fixtures/eval/plans")
SUP = PLANS / "GO-B3-R0-303_nappe_superieure.pdf"
EVAL = Path("/app/test_reports/eval")
needs_plans = pytest.mark.skipif(not SUP.exists(), reason="plans d'évaluation absents")
needs_eval = pytest.mark.skipif(not (EVAL / "RDC.json").exists(), reason="rapports d'évaluation absents")


@needs_plans
def test_panel_labels_link_to_marks_and_schedule():
    page = pymupdf.open(SUP)[0]
    nat = extract_rebar_schedule(page)
    excl = [(b[0] - 6, b[1] - 4, b[2] + 6, b[3] + 4) for tbl in ("ha_bars", "mesh") for r in nat[tbl]["rows"] for b in [r["bbox_pt"]]]
    res = panel_labels(page, 72 / 0.0254 / 50, nat["mesh"]["rows"], excl)
    assert res["marks_in_drawing"] == nat["mesh"]["count"] == 71 and res["counts"]["marks_not_in_schedule"] == 0
    assert res["counts"]["confirmed_by_geometry"] >= 80 and res["counts"]["confirmed_by_schedule"] >= 150
    t99 = next(r for r in res["rows"] if r["mark"] == "T99")
    assert t99["panel"] == "FAP 10" and {l["text"] for l in t99["labels"]} >= {"240", "84"}
    assert all(l["state"] in ("confirmed_by_geometry", "confirmed_by_schedule", "to_clarify") for r in res["rows"] for l in r["labels"])


def test_altimetry_regexes_and_reservation_semantics():
    assert LEVEL.search("Ai: 92,970 m").group(2) == "92,970" and LEVEL.search("As=+93.55").group(1) == "As"
    assert SIZE.search("40x20ht").groups()[:2] == ("40", "20")
    assert LEVEL.search("HA12 e=25") is None


def test_pair_beams_by_section_and_length_only():
    vision = {"sheets": [
        {"page": 4, "page_kind": "element_sheet", "element": {"label": "T3.11", "width_cm": 40, "height_cm": 60, "span_cm": 305, "concrete_m3": 0.83, "steel_kg": 85.8, "ratio_kg_m3": 103.6}},
        {"page": 2, "page_kind": "element_sheet", "element": {"label": "T3.8", "width_cm": 50, "height_cm": 60, "span_cm": 425, "concrete_m3": 1.47, "steel_kg": 184.6, "ratio_kg_m3": 125.8}},
        {"page": 9, "page_kind": "schedule_sheet", "elements": [{"label": "BN3.2", "units": 1}]}]}
    beams = [{"ref": "PO01", "length_m": 3.05, "width_m": 0.4}, {"ref": "PO02", "length_m": 4.6, "width_m": 0.4}]
    res = pair_beams(vision, beams)
    t311 = next(r for r in res["rows"] if r["label"] == "T3.11")
    assert t311["state"] == "paired" and t311["dxf"]["ref"] == "PO01" and t311["dxf"]["volume_m3_with_arche_h"] == 0.732 and t311["dxf"]["difference_m3"] == -0.098
    assert t311["ratio_kg_m3_calc"] == 103.4 and t311["arche_length_m"] == 3.46
    assert res["unpaired_sheets"] == ["T3.8"] and res["unpaired_dxf_beams"] == 1
    assert res["aggregate"]["ratio_kg_m3"] == round((85.8 + 184.6) / (0.83 + 1.47), 1)
    lines = ratio_lines(res, 120.0)
    assert [l["state"] for l in lines if "ratio acier" in l["element"]] == ["confirmed", "confirmed"]
    assert lines[-1]["state"] == "indeterminate" and lines[-1]["missing"]


@needs_eval
def test_rdc_altimetry_only_reservations_no_element_heights():
    rep = json.loads((EVAL / "RDC.json").read_text())
    al = rep["altimetry"]
    assert al["ai_count"] == 48 and al["as_count"] == 0 and al["element_heights"] == []
    assert any(f["subject"] == "Altimétries limitées aux réservations" for f in al["findings"])
    pairing = json.loads((EVAL / "steel_ratio.json").read_text())
    assert pairing["paired"] == 10 and set(pairing["unpaired_sheets"]) == {"T3.30", "T3.8", "T3.9"}
    assert pairing["aggregate"]["ratio_kg_m3"] == 100.9


def test_heights_rule_as_murs_equals_ai_plancher():
    from engines.metre.heights import derive_heights, volumes_from_takeoff
    h = derive_heights({"as_plancher_haut_m": 93.55, "epaisseur_dalle_m": 0.20, "niveau_base_murs_m": 89.50})
    assert (h["ai_plancher_haut_m"], h["as_murs_m"], h["h_murs_m"], h["missing"]) == (93.35, 93.35, 3.85, [])
    tk = {"elements": {"walls": {"plan_area_m2": 35.28}, "columns": {"section_total_m2": 5.904}, "slab": {"net_area_m2": 2022.0}}}
    v = volumes_from_takeoff(tk, {"as_plancher_haut_m": 93.55, "epaisseur_dalle_m": 0.20, "niveau_base_murs_m": 89.50})
    assert [l["net"] for l in v["lines"]] == [135.83, 22.73, 404.4] and v["total_m3"] == 562.96
    empty = volumes_from_takeoff(tk, {})
    assert empty["total_m3"] is None and all(l["state"] == "indeterminate" for l in empty["lines"]) and len(empty["lines"]) == 3


def test_level_symbols_from_user_example():
    from engines.metre.level_symbols import levels_from_symbols, parse_level_symbols
    # circle « 60.55b / NGF / 18 / CS » and « 60.64b / NGF / 22 / CSP », plus opening labels — positions as in the user's screenshot
    words = [(140, 360, 175, 372, "60.55b"), (145, 373, 170, 383, "NGF"), (152, 384, 162, 394, "18"), (150, 396, 165, 406, "CS"),
             (455, 360, 490, 372, "60.64b"), (460, 373, 485, 383, "NGF"), (466, 384, 478, 394, "22"), (462, 396, 483, 406, "CSP"),
             (300, 150, 380, 160, "LT(Ai: 59.95)"), (330, 690, 420, 700, "Allège(As:60.92)"), (60, 300, 130, 310, "GT - 01a (60x190 ht)"), (900, 900, 920, 910, "NGF")]
    p = parse_level_symbols(words)
    assert len(p["symbols"]) == 2
    s0 = p["symbols"][0]
    assert (s0["as_plancher_m"], s0["finish"], s0["epaisseur_cm"], s0["kind"], s0["ai_plancher_m"]) == (60.55, "brut", 18, "CS", 60.37)
    assert p["symbols"][1]["epaisseur_cm"] == 22 and p["symbols"][1]["kind"] == "CSP" and p["symbols"][1]["ai_plancher_m"] == 60.42
    assert p["openings"][0] == {"element": "LT", "kind": "AI", "level_m": 59.95, "raw": "LT(Ai: 59.95)"} and p["openings"][1]["kind"] == "AS"
    assert p["sizes"] == [{"type": "GT", "ref": "01a", "w_cm": 60, "h_cm": 190, "raw": "GT - 01a (60x190 ht)"}]
    lv = levels_from_symbols(p, base_level_m=57.20, source="test")
    assert lv["as_plancher_haut_m"] in (60.55, 60.64) and lv["niveau_base_murs_m"] == 57.2 and len(lv["exceptions"]) == 1


def test_level_symbols_ignore_opening_labels_and_read_rotated_symbol():
    from engines.metre.level_symbols import parse_level_symbols
    words = [(1689, 2100, 1700, 2110, "Ai:"), (1670, 2100, 1690, 2110, "92,77"), (1653, 2100, 1668, 2110, "NGF"), (1660, 2090, 1700, 2098, "40x60ht"),
             (905, 1684, 912, 1692, "B"), (915, 1686, 925, 1710, "93,37"), (915, 1672, 925, 1684, "NGF"), (930, 1681, 938, 1690, "20"), (889, 1682, 899, 1708, "93.44"), (889, 1668, 899, 1680, "fini")]
    p = parse_level_symbols(words)
    assert len(p["symbols"]) == 1
    s0 = p["symbols"][0]
    assert (s0["as_plancher_m"], s0["as_fini_m"], s0["epaisseur_cm"], s0["ai_plancher_m"]) == (93.37, 93.44, 20, 93.17)


def test_coupe_checks_use_plan_top_level_and_printed_chains():
    from engines.metre.coupes_vision import check_coupe, summarize
    coupe = {"name": "5-5", "levels": [{"level_m": 93.44, "finish": "F"}, {"level_m": 93.37, "finish": "B"}, {"level_m": 93.78, "finish": "B"}, {"level_m": 92.34, "finish": None},
                                       {"level_m": 89.04, "finish": "B"}, {"level_m": 89.2, "finish": "F"}],
             "vertical_dims_cm": [{"value_cm": 403, "description": "voile"}, {"value_cm": 30, "description": "dalle+"}, {"value_cm": 20, "description": "dalle"}, {"value_cm": 7, "description": ""}],
             "slab_thickness_cm": [20], "wall_thickness_cm": [25]}
    c = check_coupe(coupe, expected_top_m=93.37)
    assert c["as_plancher_haut_m"] == 93.37 and c["ai_plancher_haut_m"] == 93.17 and c["above_slab_levels_m"] == [93.78] and c["intermediate_levels_m"] == [92.34]
    assert c["base_levels_m"] == [89.04] and c["heights"][0]["h_mur_m"] == 4.13 and c["heights"][0]["chain_proof_cm"] is None  # 413 cm not printed as such
    gap = next(k for k in c["checks"] if k["check"].startswith("93.37 B − 89.04 B"))
    assert gap["state"] == "confirmed" and sorted(gap["printed_chain_cm"]) == [30, 403]
    s = summarize([{"page": 1, "page_kind": "coupes", "coupes_checked": [c], "title_block": {"document_code": "GO - B3 - R0 - 200"}}])
    assert s["dominant"] == {"as_plancher_haut_m": 93.37, "epaisseur_dalle_cm": 20, "niveau_base_murs_m": 89.04} and s["confirmed_level_gaps"] == 1
