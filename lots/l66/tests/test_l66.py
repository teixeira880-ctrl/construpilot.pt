"""Lote 66 PT — plural correto de « preço médio »."""
import pathlib

F = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "components"


def test_plural():
    for p in (F / "assistant" / "QuoteDraftCard.jsx", F / "library" / "LearnedPricesPanel.jsx"):
        s = p.read_text(encoding="utf-8")
        assert 'preço médio{' not in s and '"preços médios"' in s
