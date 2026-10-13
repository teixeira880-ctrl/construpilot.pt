"""Auto-pilote BET — tests déterministes du pont import→modèle→descente→semelles."""
import math

import pytest

from engines import structuro_autopilot as ap
from engines.structuro_calc import Model, calculate


def _inp(levels=2, bx=(4.0, 4.0), by=(5.0,), q_els=200, q_elu=300, dest="habitation"):
    return {"building": {"destination": dest, "levels": levels, "storey_height_m": 2.8, "ground_height_m": 3.0},
            "grid": {"bays_x_m": list(bx), "bays_y_m": list(by)},
            "soil": {"q_els_kpa": q_els, "q_elu_kpa": q_elu, "q_confirmed": True}}


def test_build_model_is_valid_and_balanced():
    model = ap.build_model(_inp())
    assert isinstance(model, Model)
    res = calculate(model)
    assert res["status"] == "mechanical_only"
    assert res["issues"] == []
    for case in res["cases"]:
        assert abs(case["balance_error_kn"]) < 1e-6  # chemin de charges équilibré


def test_combinations_generated_uls_sls():
    model = ap.build_model(_inp())
    ids = [c.id for c in model.combinations]
    assert any(i.startswith("ELU") for i in ids)
    assert any(i.startswith("ELScar") for i in ids)


def test_footing_sizing_from_allowable_stress():
    out = ap.build_and_compute(_inp())
    sizes = out["footing_sizes"]
    assert sizes
    # chaque semelle : aire adoptée (côté²) >= aire requise, côté arrondi 5 cm, >= 0.6 m
    for s in sizes.values():
        assert s["side_m"] >= 0.6
        assert round(s["side_m"] % 0.05, 6) in (0.0, 0.05)
        assert s["side_m"] ** 2 + 1e-6 >= s["area_req_m2"]


def test_central_footing_larger_than_corner():
    out = ap.build_and_compute(_inp(levels=2, bx=(5.0, 5.0), by=(6.0,)))
    sizes = out["footing_sizes"]
    center = sizes.get("F_1_0", {}).get("side_m", 0)   # file centrale (2 travées)
    corner = sizes.get("F_0_0", {}).get("side_m", 0)   # angle (1 demi-travée)
    assert center > corner


def test_lower_allowable_stress_gives_bigger_footings():
    strong = ap.build_and_compute(_inp(q_els=300, q_elu=450))
    weak = ap.build_and_compute(_inp(q_els=100, q_elu=150))
    assert weak["footing_sizes"]["F_1_0"]["side_m"] > strong["footing_sizes"]["F_1_0"]["side_m"]


def test_destination_sets_imposed_load():
    office = ap.build_and_compute(_inp(dest="bureau"))
    home = ap.build_and_compute(_inp(dest="habitation"))
    # bureau (2.5) > habitation (1.5) → réaction au sol plus élevée
    assert office["summary"]["ground_reaction_elu_kn"] > home["summary"]["ground_reaction_elu_kn"]


def test_element_cap_raises():
    with pytest.raises(ValueError):
        ap.build_model(_inp(levels=8, bx=tuple([4.0] * 8), by=tuple([4.0] * 6)))


def test_normalize_defaults_are_safe():
    d = ap.normalize_inputs({})
    assert d["building"]["destination"] in ap.IMPOSED
    # Aucune contrainte de sol inventée : absente tant que la G2 n'est pas lue ou saisie.
    assert d["soil"]["q_els_kpa"] is None and d["soil"]["q_elu_kpa"] is None
    assert d["soil"]["q_confirmed"] is False
    assert len(d["grid"]["bays_x_m"]) >= 1
    assert d["system"]["structure"] == "portique"


def _voiles(**kw):
    i = _inp(**kw)
    i["system"] = {"structure": "voiles", "wall_thickness_m": 0.2}
    return i


def test_walls_mode_valid_balanced_and_strip_footings():
    out = ap.build_and_compute(_voiles())
    assert out["result"]["status"] == "mechanical_only"
    assert out["result"]["issues"] == []
    for case in out["result"]["cases"]:
        assert abs(case["balance_error_kn"]) < 1e-6
    assert out["summary"]["footing_type"] == "filante"
    # semelle filante : largeur et charge linéique présentes
    f = next(iter(out["footing_sizes"].values()))
    assert f["type"] == "filante" and f["width_m"] >= 0.4 and "line_load_elu_kn_m" in f
    counts = out["summary"]["elements_count"]
    assert counts.get("wall") and not counts.get("column")


def test_superstructure_beams_and_columns_frame():
    out = ap.build_and_compute(_inp(levels=2))
    ss = out["superstructure"]
    assert ss["beams"] and ss["columns"]
    for c in ss["columns"]:
        assert c["long_bars"].endswith(tuple("0123456789")) or "Ø" in c["long_bars"]
        assert c["as_prov_cm2"] >= c["as_min_cm2"] - 1e-6
    # ground storey column more loaded than roof storey column
    by_lvl = {c["level"]: c["n_ed_kn"] for c in ss["columns"]}
    assert by_lvl.get("RDC", 0) >= by_lvl.get("Toiture", 0)


def test_superstructure_walls_in_voiles_mode():
    out = ap.build_and_compute(_voiles(levels=2))
    ss = out["superstructure"]
    assert ss["walls"] and not ss["columns"]
    for w in ss["walls"]:
        assert w["as_vert_cm2"] > 0


def test_column_rebar_min_reinforcement_rule():
    r = ap.column_rebar(500.0, 0.3, 0.3)
    assert r["as_min_cm2"] > 0 and r["as_prov_cm2"] >= r["as_min_cm2"] - 1e-6
    assert r["long_bars"].startswith(("4", "6", "8"))


def test_coffrage_pdf_builds_both_systems():
    from engines.structuro_coffrage import build_coffrage_pdf
    for cfg in (_inp(), _voiles()):
        out = ap.build_and_compute(cfg)
        pdf = build_coffrage_pdf(out["model"], 1, out["model"]["title"], out["summary"]["superstructure"],
                                 out["metre"], out["marks"])
        assert pdf[:5] == b"%PDF-" and len(pdf) > 1500


def _two_way(**kw):
    i = _inp(**kw)
    i["system"] = {"structure": "portique", "two_way_slab": True}
    return i


def test_two_way_slab_valid_balanced_adds_y_beams():
    out = ap.build_and_compute(_two_way(bx=(5.0, 5.0), by=(6.0,)))
    assert out["result"]["status"] == "mechanical_only"
    assert out["result"]["issues"] == []
    for case in out["result"]["cases"]:
        assert abs(case["balance_error_kn"]) < 1e-6
    one = ap.build_and_compute(_inp(bx=(5.0, 5.0), by=(6.0,)))
    assert out["summary"]["elements_count"]["beam"] > one["summary"]["elements_count"]["beam"]


def test_two_way_slab_fractions_sum_to_one():
    model = ap.build_model(_two_way()).model_dump()
    for e in model["elements"]:
        if e["kind"] == "slab":
            assert len(e["supports"]) == 4
            assert abs(sum(s["fraction"] for s in e["supports"]) - 1.0) < 1e-6


def test_metre_concrete_steel_and_cost():
    out = ap.build_and_compute(_inp(levels=2))
    m = out["metre"]
    assert m["concrete"]["total_m3"] > 0
    assert abs(sum(m["concrete"]["by_type_m3"].values()) - m["concrete"]["total_m3"]) < 1e-2
    assert m["steel"]["total_kg"] > 0 and m["steel"]["schedule"]
    # coût = béton×prix + acier×prix
    c = m["cost"]
    assert abs(c["concrete_eur"] - m["concrete"]["total_m3"] * c["concrete_eur_m3"]) < 1.0
    assert abs(c["total_eur"] - (c["concrete_eur"] + c["steel_eur"])) < 1.0


def test_metre_steel_scales_with_price():
    base = ap.normalize_inputs(_inp(levels=2))
    base["prices"] = {"concrete_eur_m3": 150, "steel_eur_kg": 4.0, "formwork_eur_m2": 45}
    hi = ap.build_and_compute(base)
    base2 = ap.normalize_inputs(_inp(levels=2))
    base2["prices"] = {"concrete_eur_m3": 150, "steel_eur_kg": 1.0, "formwork_eur_m2": 45}
    lo = ap.build_and_compute(base2)
    assert hi["metre"]["cost"]["steel_eur"] > lo["metre"]["cost"]["steel_eur"]


def test_element_marks_cover_all_elements():
    out = ap.build_and_compute(_inp())
    marks = out["marks"]
    model = out["model"]
    assert all(e["id"] in marks for e in model["elements"])
    assert any(v.startswith("POT") for v in marks.values())
