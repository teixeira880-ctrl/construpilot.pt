"""Lot 67 — pas d'alerte de marge « 0 ligne » sur un devis vide."""
import pathlib


def test_guard_present():
    s = (pathlib.Path(__file__).resolve().parents[1] / "engines" / "quote_check.py").read_text(encoding="utf-8")
    assert 'cov.get("missing_lines", 0) > 0:  # Lot 67' in s
