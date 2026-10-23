"""Extraction structurée : schéma typé versionné + contrôles de cohérence (avant tout calcul).
Les deux cas de référence (La Courneuve FR, moradia PT) doivent passer schéma ET cohérence."""
import copy
import json
from pathlib import Path

import pytest

from engines.bet_core import checks, model, pipeline, schema

CASES = Path(__file__).parents[2] / "engines/bet_core/cases"


def _raw(name):
    return json.loads((CASES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", ["la_courneuve", "moradia_pt_demo"])
def test_reference_cases_pass_schema_and_coherence(name):
    raw = _raw(name)
    assert schema.validate(raw) == []
    m, anomalies = pipeline.validate(raw)
    assert m is not None
    assert [a for a in anomalies if a["level"] == checks.BLOCK] == []
    assert raw["schema_version"] == schema.SCHEMA_VERSION


def test_schema_version_is_stamped():
    assert schema.SCHEMA_VERSION == "1.0"
    js = schema.json_schema()
    assert js["type"] == "object" and "levels" in js["properties"]


def test_schema_rejects_missing_required_field():
    raw = _raw("la_courneuve")
    del raw["envelope"]["width_y"]
    errs = schema.validate(raw)
    assert errs and any("width_y" in e for e in errs)
    # la complétion BET déduit la largeur des pièces relevées, et le trace (jamais en silence)
    _, anomalies = pipeline.validate(raw)
    assert not any(a["code"] == "SCHEMA" for a in anomalies)
    assert any("width_y" in d for d in raw["_decisions"])
    # sans pièces ni largeur, le relevé reste bloqué
    raw2 = _raw("la_courneuve")
    del raw2["envelope"]["width_y"]
    raw2["rooms"] = {}
    _, anomalies = pipeline.validate(raw2)
    assert any(a["code"] == "SCHEMA" and a["level"] == checks.BLOCK for a in anomalies)


def test_schema_rejects_bad_type():
    raw = _raw("la_courneuve")
    raw["levels"][0]["floor_top"] = "pas un nombre"
    assert schema.validate(raw)


# ------------------------------------------------------------------ contrôles de cohérence (unitaires)
def _m(mutate=None):
    raw = _raw("la_courneuve")
    if mutate:
        mutate(raw)
    return model.from_dict(raw)


def _codes(m):
    return {a["code"] for a in checks.check_coherence(m)}


def test_coherence_clean_case_has_no_blocking():
    assert not any(a["level"] == checks.BLOCK for a in checks.check_coherence(_m()))


def test_coherence_levels_must_increase():
    def mut(r):
        r["levels"][2]["floor_top"] = r["levels"][1]["floor_top"] - 0.5
    assert "COH-01" in _codes(_m(mut))


def test_coherence_envelope_must_be_closed():
    assert "COH-02" in _codes(_m(lambda r: r["envelope"].update(length_x=0)))


def test_coherence_interior_wall_outside_envelope():
    def mut(r):
        r["interior_walls"]["RDC"] = [{"x0": 50.0, "y0": 0.0, "x1": 51.0, "y1": 2.0, "kind": "cloison 10"}]
    assert "COH-04" in _codes(_m(mut))


def test_coherence_opening_on_unknown_side():
    def mut(r):
        r["openings"][0]["side"] = "cote_inexistant"
    assert "COH-05" in _codes(_m(mut))


def test_coherence_hsp_out_of_band_is_warning():
    def mut(r):
        for lv in r["levels"]:
            if lv["use"].startswith("habitation"):
                lv["ceiling_height"] = 4.2
                break
    an = checks.check_coherence(_m(mut))
    assert any(a["code"] == "COH-06" and a["level"] == checks.WARN for a in an)


def test_coherence_room_surface_vs_sp():
    def bad(r):
        r["project"]["surface_plancher"] = 10.0        # très loin de la somme réelle
    assert any(a["code"] == "COH-07" for a in checks.check_coherence(_m(bad)))

    def good(r):
        tot = 0.0
        for rms in r["rooms"].values():
            for rm in rms:
                for part in [rm] + (rm.get("parts") or []):
                    tot += (part["x1"] - part["x0"]) * (part["y1"] - part["y0"])
        r["project"]["surface_plancher"] = round(tot, 1)
    assert not any(a["code"] == "COH-07" for a in checks.check_coherence(_m(good)))


# ------------------------------------------------------------------ source par valeur, affichée dans le dossier
def test_hypotheses_rows_carry_source_labels():
    raw = {"hypotheses": [
        {"field": "Surface de plancher", "value": 148.87, "source": "cote"},
        {"field": "HSP RDC", "value": 2.5, "source": "mesure"},
        {"field": "Escalier", "value": "quart tournant", "source": "hypothese"},
        {"field": "Zone sismique", "value": None, "source": "absent"}]}
    rows = schema.hypotheses_rows(raw)
    assert rows[0] == ("Surface de plancher", "148.87", "coté sur plan")
    assert rows[1][2] == "mesuré à l'échelle" and rows[2][2] == "hypothèse"
    assert rows[3] == ("Zone sismique", "—", "absent")


# ------------------------------------------------------------------ sismique Eurocode 8 (projets portugais)
def _mpt(mutate=None):
    raw = _raw("moradia_pt_demo")
    if mutate:
        mutate(raw)
    return model.from_dict(raw)


def _scodes(m):
    return {a["code"] for a in checks.check_seismic_pt(m)}


def test_seismic_check_skipped_for_fr():
    assert checks.check_seismic_pt(_m()) == []


def test_seismic_pt_reference_case_passes():
    assert not any(a["level"] == checks.BLOCK for a in checks.check_seismic_pt(_mpt()))


def test_seismic_pt_missing_data_blocks():
    an = checks.check_seismic_pt(_mpt(lambda r: r["project"].update(ground_type="a confirmar")))
    assert any(a["code"] == "SEIS-00" and a["level"] == checks.BLOCK for a in an)


def test_seismic_pt_invalid_values_block():
    assert "SEIS-01" in _scodes(_mpt(lambda r: r["project"].update(seismic_zone_type1="9.9")))
    assert "SEIS-02" in _scodes(_mpt(lambda r: r["project"].update(seismic_zone_type2="1.3")))
    assert "SEIS-03" in _scodes(_mpt(lambda r: r["project"].update(ground_type="Z")))
    assert "SEIS-04" in _scodes(_mpt(lambda r: r["project"].update(importance_class="V")))


def test_seismic_pt_q_out_of_band_warns():
    an = checks.check_seismic_pt(_mpt(lambda r: r["project"].update(behaviour_factor_q=7.0)))
    assert any(a["code"] == "SEIS-05" and a["level"] == checks.WARN for a in an)


# ------------------------------------------------------------------ télémétrie : taux de champs « absent »
def test_extraction_metrics_rate():
    raw = {"schema_version": "1.0", "hypotheses": [
        {"field": "SP", "value": 148.0, "source": "cote"},
        {"field": "HSP RDC", "value": 2.5, "source": "mesure"},
        {"field": "Zone sismique", "value": None, "source": "absent"},
        {"field": "q", "value": "", "source": "hypothese"}]}
    m = schema.extraction_metrics(raw)
    assert m["hyp_total"] == 4 and m["hyp_absent"] == 2 and m["absent_rate"] == 0.5
    assert set(m["absent_fields"]) == {"Zone sismique", "q"}


def test_extraction_metrics_empty_is_safe():
    m = schema.extraction_metrics({})
    assert m["hyp_total"] == 0 and m["absent_rate"] == 0.0 and m["absent_fields"] == []
