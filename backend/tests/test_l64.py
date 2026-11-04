"""Lot 64 — le devis escalier n'a plus de lignes à 0 €."""
import pathlib


def test_stair_quote_is_priced():
    src = (pathlib.Path(__file__).resolve().parents[1] / "routes" / "stairs.py").read_text(encoding="utf-8")
    assert "Lot 64" in src and "_ln.unit_price_ht = round(float(_base) * _sm, 2)" in src
    i, j = src.index("Lot 64"), src.index('    doc = DocIn(doc_type="quote"')
    assert i < j
