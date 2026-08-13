"""Iter 56 — AI Plan enriched schema regression tests.

Vérifie que le prompt et le normalizer supportent :
- `dimension_lines` (traits de cote — distingués des murs)
- `wall_types` (classification visuelle porteur/cloison/doublage)
- `materials_notes` (textes et symboles inscrits sur le plan)
- `openings.reservations_visible` (trémies, gaines techniques)
- `rooms[i].floor_material` / `floor_note_text` (revêtement inscrit)
"""
from engines.plan_ai import PROMPT, _normalize_analysis


def test_prompt_mentions_dimension_line_distinction():
    """Le prompt doit demander à l'IA de distinguer traits de cotes ≠ murs."""
    assert "traits de cote" in PROMPT.lower() or "dimension_lines" in PROMPT
    assert "NE JAMAIS confondre" in PROMPT or "distingue" in PROMPT.lower()


def test_prompt_mentions_wall_type_distinction():
    assert "porteur" in PROMPT
    assert "cloison" in PROMPT
    assert "doublage" in PROMPT
    assert "hachures" in PROMPT.lower() or "trait épais" in PROMPT.lower()


def test_prompt_mentions_openings_reservations():
    assert "reservation" in PROMPT.lower() or "réservation" in PROMPT.lower()
    assert "trémie" in PROMPT.lower()


def test_prompt_mentions_materials_notes():
    assert "materials_notes" in PROMPT
    assert "text_verbatim" in PROMPT
    assert "revêtement" in PROMPT.lower() or "isolation" in PROMPT.lower()


def test_normalize_adds_new_fields_when_missing():
    result = _normalize_analysis({})
    assert result["dimension_lines"] == []
    assert result["wall_types"] == {}
    assert result["materials_notes"] == []
    # Existing fields still there
    assert result["rooms"] == []
    assert result["openings"] == {"details": [], "reservations_visible": 0}


def test_normalize_preserves_existing_data():
    payload = {
        "dimension_lines": [{"value_m": 3.42, "location": "façade sud"}],
        "wall_types": {"load_bearing_visible": True},
        "materials_notes": [{"text_verbatim": "Carrelage 60x60", "category": "revêtement_sol"}],
        "openings": {"reservations_visible": 2, "details": [{"kind": "porte"}]},
    }
    result = _normalize_analysis(payload)
    assert result["dimension_lines"][0]["value_m"] == 3.42
    assert result["wall_types"]["load_bearing_visible"] is True
    assert result["materials_notes"][0]["category"] == "revêtement_sol"
    assert result["openings"]["reservations_visible"] == 2
    assert result["openings"]["details"][0]["kind"] == "porte"


def test_normalize_openings_reservations_default_zero():
    """Even if openings dict was already provided, reservations_visible should default."""
    result = _normalize_analysis({"openings": {"doors_visible": 5}})
    assert result["openings"]["reservations_visible"] == 0
    assert result["openings"]["doors_visible"] == 5
    assert result["openings"]["details"] == []
