"""IA BTP — deterministic metre rules: provenance, no silent defaults, assumptions visible, deductions counted once."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from btp_ai.metre import build_elements, compute_quantities  # noqa: E402

PLAN = {"plan_id": "plan_t", "updated_at": "x", "calibrations": {"0": {"pixels_per_meter": 100.0, "method": "two_points", "confidence": 0.9}},
        "rooms": [{"room_id": "r1", "page_index": 0, "name": "Salon", "points": [[0, 0], [600, 0], [600, 400], [0, 400]], "ceiling_height_m": 2.5,
                   "openings": [{"type": "porte", "width_m": 0.9, "height_m": 2.1}, {"type": "fenetre", "width_m": 1.2, "height_m": 1.35}]},
                  {"room_id": "r2", "page_index": 1, "name": "Cave", "points": [[0, 0], [100, 0], [100, 100]], "openings": []}]}


def test_lengths_are_measured_and_missing_is_reported_not_defaulted():
    els, missing = build_elements(PLAN)
    murs = next(e for e in els if e["type"] == "mur" and e["room_id"] == "r1")
    assert murs["dimensions"]["perimetre_m"]["value"] == 20.0 and murs["dimensions"]["perimetre_m"]["source"] == "mesuré"
    assert murs["dimensions"]["epaisseur_m"]["value"] is None and murs["dimensions"]["epaisseur_m"]["source"] == "manquant"
    assert any(m["kind"] == "calibration" and m["room_id"] == "r2" for m in missing)
    assert any(m["kind"] == "thickness" for m in missing)


def test_quantities_formula_deductions_and_undetermined():
    els, _ = build_elements(PLAN)
    q = {x["rule"]: x for x in compute_quantities(els, {})}
    assert q["dalle_surface"]["quantity_net"] == 24.0
    assert q["mur_surface_nette"]["quantity_net"] == round(20 * 2.5 - (0.9 * 2.1 + 1.2 * 1.35), 3)
    assert len(q["mur_surface_nette"]["deductions"]) == 2
    assert q["mur_volume"]["quantity_net"] is None and q["mur_volume"]["status"] == "undetermined"
    assert q["ouverture_unite"]["quantity_net"] == 1


def test_explicit_assumption_marks_lines_provisional():
    els, _ = build_elements(PLAN)
    murs = next(e for e in els if e["type"] == "mur")
    q = {x["rule"]: x for x in compute_quantities(els, {murs["element_id"]: {"epaisseur_m": 0.2, "reason": "bloc 20", "by": "t"}})}
    assert q["mur_volume"]["status"] == "provisional" and q["mur_volume"]["assumptions"][0]["name"] == "épaisseur"
    assert q["mur_volume"]["quantity_net"] == round(q["mur_surface_nette"]["quantity_net"] * 0.2, 3)
