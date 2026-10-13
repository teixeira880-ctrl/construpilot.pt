"""Flèches SLS EN 1990 — tests déterministes (auto portée du plan / override manuel)."""
from engines import structuro_sls as sls

RESULT = {"cases": [
    {"id": "ELScar1", "label": "ELS caractéristique", "elements": [{"id": "B1", "kind": "beam", "deflection_sampled_mm": 18.0}]},
    {"id": "ELSqp", "label": "ELS quasi-permanente", "elements": [{"id": "B1", "kind": "beam", "deflection_sampled_mm": 12.0}]},
]}


def test_span_auto_from_plan():
    model = {"elements": [{"id": "B1", "kind": "beam", "length_m": 5.0}]}
    out = sls.deflection_study(model, RESULT, {"ratio_char": 250, "ratio_qp": 300})
    row = out["elements"][0]
    assert row["status"] == "ok" and row["span_source"] == "plan (auto)" and row["span_m"] == 5.0
    assert row["char"]["limit_mm"] == 20.0 and row["char"]["utilisation"]["ratio"] == 0.9
    assert row["qp"]["w_mm"] == 12.0 and row["qp"]["ratio_label"] == "L/300"
    assert out["execution_ready"] is False


def test_plan_span_wins_over_manual_override():
    # La portée du plan est TOUJOURS automatique pour les flèches (sans toucher au carton manuel)
    model = {"elements": [{"id": "B1", "kind": "beam", "length_m": 5.0}]}
    out = sls.deflection_study(model, RESULT, {"spans": {"B1": 8.0}})
    row = out["elements"][0]
    assert row["span_source"] == "plan (auto)" and row["span_m"] == 5.0


def test_span_manual_override_when_plan_missing():
    model = {"elements": [{"id": "B1", "kind": "beam"}]}
    out = sls.deflection_study(model, RESULT, {"spans": {"B1": 4.0}})
    row = out["elements"][0]
    assert row["span_source"] == "manuel" and row["span_m"] == 4.0 and row["status"] == "ok"


def test_need_span_when_missing_everywhere():
    out = sls.deflection_study({"elements": [{"id": "B1", "kind": "beam"}]}, RESULT, {})
    assert out["elements"][0]["status"] == "need_span"


def test_no_deflection_when_no_ei():
    out = sls.deflection_study({"elements": [{"id": "B1", "kind": "beam", "length_m": 5.0}]}, {"cases": []}, {})
    assert out["elements"][0]["status"] == "no_deflection"
