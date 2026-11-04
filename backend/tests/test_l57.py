"""Lot 57 — l'erreur de validation interne du devis n'est pas affichée brute."""
import pathlib

CARD = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "assistant" / "ActionCard.jsx"


def test_internal_quote_error_is_masked():
    s = CARD.read_text(encoding="utf-8")
    assert "Lot 57" in s
    assert "{r.error && ` · ${r.error}`}" not in s
    assert "correction automatique en cours" in s or "correção automática em curso" in s
