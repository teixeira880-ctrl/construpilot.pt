import pytest
from engines.eval_harness import score_quantities, summary
from engines.revision_impact import revision_delta


def item(value=10, **kw):
    return {"quantity_id": "wall", "page_index": 0, "unit": "m2", "value": value, **kw}


def truth(*rows):
    return {"verified": True, "exhaustive": True, "quantities": list(rows or [item()])}


def test_two_percent_is_error_tolerance_not_global_accuracy():
    out = score_quantities([item(10.2)], truth())
    assert out["agreement"] == 1 and out["rows"][0]["absolute_error"] == pytest.approx(.2)
    assert score_quantities([item(10.21)], truth())["agreement"] == 0


def test_missing_extra_duplicate_units_do_not_inflate_score():
    assert score_quantities([], truth())["agreement"] == 0
    assert score_quantities([item(), item()], truth())["agreement"] == 0
    out = score_quantities([item(), item(quantity_id="falsepositive")], truth())
    assert out["agreement"] == 1 and out["precision"] == .5
    assert score_quantities([item(unit="m3")], truth())["agreement"] == 0
    assert score_quantities([item(page_index=1)], truth())["agreement"] == 0
    assert score_quantities([item(value=float("nan"))], truth())["agreement"] == 0


def test_count_is_exact_and_zero_has_no_relative_error():
    assert score_quantities([item(100.5, unit="u")], truth(item(100, unit="u")))["agreement"] == 0
    out = score_quantities([item(0)], truth(item(0)))
    assert out["agreement"] == 1 and out["rows"][0]["relative_error"] is None


def test_unverified_reference_and_duplicate_truth_rejected():
    with pytest.raises(ValueError):
        score_quantities([item()], {**truth(), "verified": False})
    with pytest.raises(ValueError):
        score_quantities([item()], truth(item(), item()))
    assert score_quantities([item()], {**truth(), "exhaustive": False})["precision"] is None


def test_empty_dimension_truth_excluded_from_average():
    base = {"identity": {"correct": 0, "total": 0}}
    out = summary({"a": {**base, "dimensions": {"recall": None, "duplicate_readings": 0}}, "b": {**base, "dimensions": {"recall": .8, "duplicate_readings": 0}}})
    assert out["dimension_recall_mean"] == .8


def qty(net, order, unit="m2"):
    return {"quantity_net": net, "quantity_to_order": order, "unit": unit}


def test_revision_uses_order_quantity_for_quote_impact():
    out = revision_delta(qty(10, 11), qty(12, 13.2), {"unit": "m2", "quantity": 11, "unit_price_ht": 20})
    assert out["delta"] == 2 and out["delta_to_order"] == 2.2 and out["impact_ht"] == 44


def test_added_removed_and_unknown_revision_quantities():
    price = {"unit": "m2", "quantity": 11, "unit_price_ht": 20}
    assert revision_delta(qty(10, 11), None, price)["impact_ht"] == -220
    assert revision_delta(None, qty(10, 11), price)["impact_ht"] == 220
    for changed in (qty(None, None), qty(10, 11, "m3")):
        assert revision_delta(qty(10, 11), changed, price)["impact_ht"] is None
    assert revision_delta(qty(10, 11), qty(12, 13.2), {**price, "ambiguous": True})["impact_ht"] is None
    assert revision_delta(qty(10, 11), qty(12, 13.2), {**price, "quantity": 20})["impact_ht"] is None
