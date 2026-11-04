"""Lote 65 PT — le prix catalogue des orçamentos automatiques suit le coefficient Portugal."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import engines.assistant_quote_pricing as qp  # noqa: E402


def test_catalog_price_uses_portugal_coefficient():
    base = qp._catalog_price_lot65_base("Demolição de azulejos de parede", "m²", "Demolições")
    adj = qp.catalog_price("Demolição de azulejos de parede", "m²", "Demolições")
    assert base and adj
    assert adj["unit_price_ht"] < base["unit_price_ht"]
    assert abs(adj["unit_price_ht"] / base["unit_price_ht"] - 0.68) < 0.01
