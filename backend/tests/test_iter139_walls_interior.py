"""Moteur murs à deux faces / dimensions intérieures nu-à-nu / fermetures (plan synthétique 1/50) + validation bloquante."""
import os
import sys

import pymupdf

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engines.plan_vector_pdf import extract_vector_dimensions, pdf_lines  # noqa: E402
from engines.plan_walls import INCOMPLETE_MSG, analyze_walls, validate  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "synth_walls_1_50.pdf")


def _analyze():
    doc = pymupdf.open(FIXTURE)
    page = doc[0]
    vec = pdf_lines(page)
    tb = [{"text": sp["text"].strip(), "x": sp["bbox"][0], "y": sp["bbox"][1], "w": sp["bbox"][2] - sp["bbox"][0], "h": sp["bbox"][3] - sp["bbox"][1]}
          for b in page.get_text("dict")["blocks"] if b["type"] == 0 for ln in b["lines"] for sp in ln["spans"] if sp["text"].strip()]
    px = 200 / 72
    dims = extract_vector_dimensions(vec, tb, px)
    return analyze_walls(vec, [{**d, "index": i + 1} for i, d in enumerate(dims["dimensions"])], tb, dims["pt_per_m"], px)


def test_walls_two_faces_and_thickness():
    r = _analyze()
    assert r["stats"]["walls"] == 7
    for w in r["walls"]:
        assert abs(w["thickness_m"] - 0.20) < 0.005
        assert w["source"] == "explicit_dimension" and not w["ambiguous"]
        assert w["face_1"] != w["face_2"] and w["axis"]
    assert all(len(w["intersections"]) >= 3 for w in r["walls"])


def test_interior_spans_not_exterior_minus_walls():
    r = _analyze()
    geo = sorted({round(m["geometric_dimension_m"], 2) for m in r["interior_measurements"]})
    assert geo == [3.0, 3.6, 4.0, 4.4]
    assert all(m["reference_type"] == "inside_face_to_inside_face" for m in r["interior_measurements"])
    assert all(m["status"] == "confirmed" for m in r["interior_measurements"])
    assert 11.6 not in geo and 12.0 not in geo  # jamais « extérieur − 2 murs »


def test_reference_types_and_sections():
    r = _analyze()
    types = {c["raw_text"]: c["reference_type"] for c in r["cotes"]}
    assert types["12.00"] == "outside_face_to_outside_face"
    assert types["4.20"] == "axis_to_axis"
    assert types["4.00"] == "inside_face_to_inside_face"
    assert all(t == "wall_thickness" for k, t in types.items() if k == "0.20")
    assert r["sections_ignored"] == ["50x30", "60x30"]
    assert not any(m["geometric_dimension_m"] in (0.5, 0.6, 0.3) for m in r["interior_measurements"])


def test_closure_rows():
    r = _analyze()
    rows = r["closure_equations"]
    assert rows and all(x["status"] == "closed" for x in rows)
    h = [x for x in rows if x["direction"] == "horizontal"][0]
    assert [t["value_m"] for t in h["terms"]] == [0.2, 4.0, 0.2, 3.6, 0.2, 3.6, 0.2]
    assert h["written_exterior_m"] == 12.0 and h["walls_count"] == 4 and h["spans_count"] == 3


def test_validation_complete_and_blocking():
    r = _analyze()
    assert r["validation"]["complete"] is True
    broken = {**r, "closure_equations": [{**x, "status": "open"} for x in r["closure_equations"]]}
    v = validate(broken)
    assert v["complete"] is False and v["message"] == INCOMPLETE_MSG
    assert any("chaînes horizontales" in f for f in v["failed_checks"])
    empty = validate({"walls": [], "interior_measurements": [], "closure_equations": [], "cotes": []})
    assert "nombre de murs détectés non établi" in empty["failed_checks"]


def test_houilles_peripheral_chains_inconsistencies():
    """Plan réel (fondations Houilles) : chaînes périphériques comparées, écarts de référence nu/axe tolérés."""
    from engines.plan_chains import peripheral_chains
    from engines.plan_walls import _dims_pt
    doc = pymupdf.open(os.path.join(os.path.dirname(__file__), "fixtures", "houilles_plan.pdf"))
    page = doc[0]
    vec = pdf_lines(page)
    tb = [{"text": sp["text"].strip(), "x": sp["bbox"][0], "y": sp["bbox"][1], "w": sp["bbox"][2] - sp["bbox"][0], "h": sp["bbox"][3] - sp["bbox"][1]}
          for b in page.get_text("dict")["blocks"] if b["type"] == 0 for ln in b["lines"] for sp in ln["spans"] if sp["text"].strip()]
    px = 200 / 72
    dims = extract_vector_dimensions(vec, tb, px)
    r = peripheral_chains(_dims_pt([{**d, "index": i + 1} for i, d in enumerate(dims["dimensions"])], px), dims["pt_per_m"])
    sides = {c["side"] for c in r["chains"]}
    assert {"haut", "bas", "gauche", "droite"} <= sides
    deltas = sorted(round(x["delta_mm"]) for x in r["inconsistencies"])
    assert deltas == [-130, -30, 40]
    shifts = [c for c in r["comparisons"] if c["status"] == "reference_shift"]
    assert {(c["a_value_m"], c["b_value_m"]) for c in shifts} == {(5.07, 5.2), (4.1, 4.7), (4.57, 4.7)}
