"""Iter 171 — nomenclatures d'aciers : lecture native déterministe, contrôles arithmétiques, identité étendue, scoring d'évaluation."""
import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, "/app/backend")
from engines.eval_harness import score_rebar  # noqa: E402
from engines.metre.rebar_schedule import check_ha_rows, check_mesh, extract_rebar_schedule, _parse_cuts  # noqa: E402
from engines.metre.rebar_vision import SHEET_SCHEMA, check_sheet, summarize  # noqa: E402
from engines.plan_identity import identify_document, row_text  # noqa: E402

PLANS = Path("/app/tests/fixtures/eval/plans")
SUP = PLANS / "GO-B3-R0-303_nappe_superieure.pdf"
INF = PLANS / "GO-B3-R0-302_nappe_inferieure.pdf"
POUTRE = PLANS / "GO-B3-R0-301_poutre_BN_PV.pdf"
needs_plans = pytest.mark.skipif(not SUP.exists(), reason="plans d'évaluation absents")


@pytest.fixture(scope="module")
def sup():
    return extract_rebar_schedule(pymupdf.open(SUP)[0])


@pytest.fixture(scope="module")
def inf():
    return extract_rebar_schedule(pymupdf.open(INF)[0])


@needs_plans
def test_ha_schedule_reconciles_with_printed_recap(sup, inf):
    for r, expected_rows, recap_kg in ((sup, 63, 461.0), (inf, 71, 350.0)):
        ha = r["ha_bars"]
        assert ha["count"] == expected_rows
        assert ha["inconsistencies"] == []
        assert abs(ha["total_mass_kg"] - recap_kg) <= 0.5
        assert ha["comparison"]["b_kg"] == recap_kg
        assert all(row["origin"] == "native_text" and len(row["bbox_pt"]) == 4 for row in ha["rows"])


@needs_plans
def test_ha_row_values_are_printed_values(sup):
    row = next(r for r in sup["ha_bars"]["rows"] if r["mark"] == "2")
    assert (row["diameter_mm"], row["per_element"], row["elements"], row["total_count"]) == (12, 14, 1, 14)
    assert (row["spacing_cm"], row["unit_length_cm"], row["total_length_cm"]) == (25, 220, 3080)
    assert row["mass_kg"] == round(30.80 * 0.888, 2)


@needs_plans
def test_mesh_schedule_and_recap(sup, inf):
    assert sup["mesh"]["count"] == 71 and abs(sup["mesh"]["rows_mass_kg"] - 2476) < 3
    assert sup["mesh_recap"]["mass_laid_kg"] == 2476 and abs(sup["mesh_recap"]["sum_mass_kg"] - 3134) < 1
    assert inf["mesh"]["count"] == 49 and abs(inf["mesh"]["rows_mass_kg"] - 3464) < 1
    assert inf["mesh_recap"]["mass_total_kg"] == 4554 and abs(inf["mesh_recap"]["sum_mass_kg"] - 4554) < 1
    assert inf["steel_recap"] == {"ha_shaped_kg": 181.0, "ha_shaped_label": "HA façonnés", "ha_straight_kg": 169.0, "ha_straight_label": "HA non façonnés"}
    t48 = next(r for r in sup["mesh"]["rows"] if r["mark"] == "T48")
    assert t48["panel"] == "TS25C ECO" and t48["mass_kg"] == 35.3 and {"count": 2, "width_cm": 240, "height_cm": 200} in t48["cuts"]
    assert sup["partial"] is True and any(f["subject"] == "Nomenclature partielle" for f in sup["findings"])


@needs_plans
def test_vectorised_text_page_reports_no_native_table():
    r = extract_rebar_schedule(pymupdf.open(POUTRE)[0])
    assert r["ha_bars"] is None and r["mesh"] is None
    assert any(f["subject"] == "Aucune nomenclature native" for f in r["findings"])


def test_check_ha_rows_flags_arithmetic_without_correcting():
    rows = [{"mark": "1", "diameter_mm": 12, "per_element": 2, "elements": 3, "total_count": 6, "unit_length_cm": 100, "total_length_cm": 600},
            {"mark": "2", "diameter_mm": 8, "per_element": 2, "elements": 3, "total_count": 5, "unit_length_cm": 100, "total_length_cm": 600}]
    out = check_ha_rows(rows)
    assert [c["state"] for c in out["checks"]] == ["confirmed", "confirmed", "to_clarify", "to_clarify"]
    assert rows[1]["total_count"] == 5 and rows[1]["total_length_cm"] == 600
    assert out["by_diameter"]["HA12"]["mass_kg"] == round(6 * 0.888, 2)
    assert out["total_mass_kg"] == round(6 * 0.888 + 6 * 0.395, 1)


def test_check_mesh_compares_without_tolerance_claims():
    out = check_mesh([{"panel": "TS25", "total_count": 2, "mass_kg": 10.0}], {"sum_mass_kg": 12.0, "mass_total_kg": 12.0, "mass_laid_kg": 10.0})
    assert out["rows_mass_kg"] == 10.0
    assert [(c["difference_kg"], c["expect_equal"]) for c in out["comparisons"]] == [(0.0, True), (0.0, True), (2.0, False)]
    assert _parse_cuts(["2", "x", "240x200", "1 x 180x250"]) == [{"count": 2, "width_cm": 240, "height_cm": 200}, {"count": 1, "width_cm": 180, "height_cm": 250}]


def test_vision_sheet_checks_lg_poids():
    sheet = {"page_kind": "element_sheet", "element": {"label": "T3.11", "steel_kg": 85.8, "concrete_m3": 0.83, "ratio_kg_m3": 103.6},
             "bars": [{"mark": 1, "count": 4, "diameter_mm": 20, "length_cm": 305, "shape": None}, {"mark": 9, "count": 26, "diameter_mm": 8, "length_cm": 130, "shape": None}],
             "by_diameter": [{"diameter_mm": 20, "length_m": 12.2, "mass_kg": 30.1}, {"diameter_mm": 8, "length_m": 33.8, "mass_kg": 13.4}, {"diameter_mm": 12, "length_m": 5.0, "mass_kg": 4.4}]}
    chk = check_sheet(sheet)
    states = {(c.get("diameter_mm"), c["check"]): c["state"] for c in chk["checks"]}
    assert states[(20, "Σ count × Lg = Lg totale")] == "confirmed" and states[(8, "Σ count × Lg = Lg totale")] == "confirmed"
    assert states[(12, "Lg/Poids sans barre correspondante dans le tableau")] == "to_clarify"
    assert states[(None, "Acier / Béton = d")] == "confirmed"
    assert chk["by_diameter_calc"]["HA20"]["length_m"] == 12.2


def test_vision_schedule_sheet_uses_native_checks_and_summary():
    sheet = {"page": 17, "page_kind": "schedule_sheet", "elements": [{"label": "BN3.2", "units": 1}], "schedule_partial": True,
             "schedule_rows": [{"mark": 9, "diameter_mm": 12, "per_element": 2, "elements": 1, "total_count": 2, "spacing_cm": None, "unit_length_cm": 202, "mandrel_cm": 10, "total_length_cm": 404}]}
    chk = check_sheet(sheet)
    assert chk["inconsistencies"] == [] and chk["calc_mass_kg"] == round(4.04 * 0.888, 1)
    s = summarize([{**sheet, "checks": chk}, {"page": 0, "page_kind": "cover", "recap": {"ha_shaped_kg": 100, "ha_straight_kg": None}}])
    assert s["schedule_sheets"] == 1 and s["schedule_elements"] == ["BN3.2"] and s["comparison"]["a_kg"] == chk["calc_mass_kg"]
    assert SHEET_SCHEMA["required"] == list(SHEET_SCHEMA["properties"])


@needs_plans
def test_identity_reads_lot_code_numeric_index_from_title_block():
    page = pymupdf.open(SUP)[0]
    ident = identify_document(page.get_text(), page.get_text("words"))
    assert ident["document_code"] == "GO-B3-R0-303" and ident["discipline"] == "Gros œuvre"
    assert (ident["revision_index"], ident["revision_date"], ident["revision_label"]) == ("0", "09/06/2023", "1ère Diffusion")
    assert ident["declared_scale"] == "1/50" and ident["level"] == "RDC" and ident["revision_index_is_numeric"] is True
    assert "GO - B3 - R0 - 303" in row_text(page.get_text("words"))


def test_identity_legacy_pattern_unchanged():
    ident = identify_document("Plan coffrage COF 1203 R+1  B 12/03/2024 Mise à jour trémies  Ech 1/50")
    assert ident["document_code"] == "COF 1203 R+1" and ident["revision_index"] == "B" and ident["declared_scale"] == "1/50"
    assert identify_document("Poutres PH RDC Echelle : sans")["declared_scale"] == "sans échelle"


def test_score_rebar_against_truth():
    native = {"ha_bars": {"count": 63, "total_mass_kg": 461.4, "rows": [{"mark": "2", "total_count": 14, "unit_length_cm": 220}], "inconsistencies": []},
              "mesh": {"count": 71, "rows_mass_kg": 2473.4}, "mesh_recap": {"mass_laid_kg": 2476}}
    sc = score_rebar(native, {"ha_rows": 63, "ha_mass_kg": 461, "mesh_rows": 70, "mass_laid_kg": 2476, "rows": {"2": {"total_count": 14, "unit_length_cm": 225}}})
    assert sc["fields"]["ha_rows"]["ok"] and sc["fields"]["ha_mass_kg"]["ok"] and not sc["fields"]["mesh_rows"]["ok"]
    assert sc["rows"]["2"]["total_count"]["ok"] and not sc["rows"]["2"]["unit_length_cm"]["ok"]
    assert (sc["correct"], sc["total"]) == (4, 6) and sc["duplicate_marks"] == []
