"""Lot 1 — tests déterministes des combinaisons EN 1990 et de l'enveloppe."""
from engines.structuro_calc import Action, Model, calculate
from engines import structuro_eurocode as ec


def _actions(*specs):
    return [Action(id=i, kind=k, label=l) for i, k, l in specs]


def test_catalog_has_categories_and_gamma():
    cat = ec.catalog()
    assert cat["gamma"]["G_sup"] == 1.35 and cat["gamma"]["Q"] == 1.5
    keys = {c["key"] for c in cat["categories"]}
    assert {"A", "B", "C", "E", "neige_bas", "vent"} <= keys


def test_single_q_category_A():
    acts = _actions(("G", "G", "Permanentes"), ("Q", "Q", "Exploitation"))
    combos = ec.generate(acts, {"Q": "A"}, {"uls": True, "sls_char": True, "sls_freq": True, "sls_qp": True})
    by = {c.id: c for c in combos}
    assert by["ELU1"].factors == {"G": 1.35, "Q": 1.5}
    assert by["ELScar1"].factors == {"G": 1.0, "Q": 1.0}
    assert by["ELSfreq1"].factors == {"G": 1.0, "Q": 0.5}   # ψ1 = 0.5
    assert by["ELSqp"].factors == {"G": 1.0, "Q": 0.3}      # ψ2 = 0.3
    for c in combos:
        assert c.source.document and c.source.note


def test_two_q_accompanying_uses_psi0():
    acts = _actions(("G", "G", "Perm"), ("Qh", "Q", "Habitation"), ("Qs", "Q", "Neige"))
    combos = ec.generate(acts, {"Qh": "A", "Qs": "neige_bas"}, {"uls": True, "sls_char": False, "sls_freq": False, "sls_qp": False})
    by = {c.id: c for c in combos}
    # Qh dominante : Qh=1.5, Qs accompagnante = 1.5*ψ0(neige_bas=0.5)=0.75
    assert by["ELU1"].factors == {"G": 1.35, "Qh": 1.5, "Qs": 0.75}
    # Qs dominante : Qs=1.5, Qh accompagnante = 1.5*ψ0(A=0.7)=1.05
    assert by["ELU2"].factors == {"G": 1.35, "Qh": 1.05, "Qs": 1.5}


def test_generated_combos_validate_in_model_and_compute():
    base = Model(
        title="t", actions=_actions(("G", "G", "Perm"), ("Q", "Q", "Exploit")),
        self_weight_action="G",
    )
    combos = ec.generate(base.actions, {"Q": "A"})
    base.combinations = combos
    model = Model.model_validate(base.model_dump())  # must not raise (set(factors)==set(actions))
    assert all(set(c.factors) == {"G", "Q"} for c in model.combinations)
    result = calculate(model)  # no elements -> blocked, but structure valid
    assert result["engine_version"]


def test_no_q_fallback():
    combos = ec.generate(_actions(("G", "G", "Perm")), {})
    ids = {c.id for c in combos}
    assert "ELU" in ids and "ELScar" in ids


def test_psi_override_respected():
    acts = _actions(("G", "G", "Perm"), ("Q", "Q", "Spécial"))
    combos = ec.generate(acts, {"Q": "A"}, {"uls": True, "sls_char": False, "sls_qp": True},
                         psi_overrides={"Q": {"psi0": 0.9, "psi1": 0.8, "psi2": 0.7}})
    by = {c.id: c for c in combos}
    assert by["ELSqp"].factors["Q"] == 0.7


def test_design_envelope_picks_max_uls():
    result = {"cases": [
        {"id": "ELU1", "label": "ELU1", "elements": [
            {"id": "B1", "kind": "beam", "moment_max_knm": 10.0, "shear_max_kn": 5.0}]},
        {"id": "ELU2", "label": "ELU2", "elements": [
            {"id": "B1", "kind": "beam", "moment_max_knm": 18.0, "shear_max_kn": 4.0}]},
        {"id": "ELScar1", "label": "ELScar1", "elements": [
            {"id": "B1", "kind": "beam", "deflection_sampled_mm": 7.2}]},
        {"id": "G", "label": "G", "elements": [
            {"id": "B1", "kind": "beam", "moment_max_knm": 99.0}]},  # raw action ignored
    ]}
    env = ec.design_envelope(result)
    b1 = next(e for e in env["elements"] if e["id"] == "B1")
    assert b1["uls"]["moment_knm"]["case"] == "ELU2" and b1["uls"]["moment_knm"]["value"] == 18.0
    assert b1["uls"]["shear_kn"]["case"] == "ELU1"
    assert b1["sls"]["deflection_mm"]["value"] == 7.2
    assert env["uls_count"] == 2 and env["sls_count"] == 1
