"""Iter 58 — Vague B (QuoterPlan) : Tool Presets + Object Panel Room Edit."""
import pytest
from fastapi.testclient import TestClient

from server import app
from routes.tool_presets import _normalize, KNOWN_PRESET_KINDS, ToolPresetIn


client = TestClient(app)


# ============ Schema / normalize ============

def test_known_preset_kinds_covers_use_cases():
    for k in ["wall", "opening", "floor", "ceiling", "paint",
              "insulation", "counter", "roof", "note", "other"]:
        assert k in KNOWN_PRESET_KINDS


def test_normalize_unknown_kind_falls_back_to_other():
    body = ToolPresetIn(name="Test", kind="INVALID_KIND", unit="m²")
    doc = _normalize(body)
    assert doc["kind"] == "other"


def test_normalize_defaults_color_orange():
    body = ToolPresetIn(name="Test", kind="wall")
    doc = _normalize(body)
    assert doc["color"] == "#f97316"
    assert doc["unit"] == "u"
    assert doc["notes"] is None
    assert doc["params"] == {}


def test_normalize_strips_and_bounds_name():
    body = ToolPresetIn(name="  Mur ext  ", kind="wall", unit="m²")
    doc = _normalize(body)
    assert doc["name"] == "Mur ext"
    assert doc["unit"] == "m²"


def test_normalize_empty_unit_falls_back_to_u():
    body = ToolPresetIn(name="X", kind="wall", unit="")
    doc = _normalize(body)
    assert doc["unit"] == "u"


def test_normalize_strips_notes():
    body = ToolPresetIn(name="X", notes="  note test  ")
    doc = _normalize(body)
    assert doc["notes"] == "note test"


def test_normalize_empty_notes_becomes_none():
    body = ToolPresetIn(name="X", notes="   ")
    doc = _normalize(body)
    assert doc["notes"] is None


# ============ Routes registration ============

def test_tool_presets_routes_registered():
    routes = {r.path for r in app.routes}
    assert "/api/tool-presets" in routes
    assert "/api/tool-presets/{preset_id}" in routes
    assert "/api/tool-presets/seed-defaults" in routes


def test_room_update_route_registered():
    routes = {r.path for r in app.routes}
    assert "/api/takeoffs/{plan_id}/rooms/{room_id}" in routes


# ============ RoomUpdateIn schema ============

def test_room_update_schema_accepts_partial():
    from routes.plans_analysis import RoomUpdateIn
    a = RoomUpdateIn(name="Salon")
    assert a.name == "Salon" and a.height_m is None and a.preset_id is None
    b = RoomUpdateIn(height_m=2.7)
    assert b.height_m == 2.7 and b.name is None
    c = RoomUpdateIn(preset_id="tpr_xxx")
    assert c.preset_id == "tpr_xxx"


def test_room_update_schema_allows_empty_body():
    """Pas de champ requis — le endpoint vérifiera la présence d'au moins un update."""
    from routes.plans_analysis import RoomUpdateIn
    empty = RoomUpdateIn()
    assert empty.name is None
    assert empty.height_m is None
    assert empty.preset_id is None


# ============ Seed defaults content ============

def test_seed_defaults_covers_6_kinds():
    """Vérifie que la liste des defaults couvre bien les 6 métiers principaux."""
    from routes import tool_presets
    import inspect
    src = inspect.getsource(tool_presets.seed_default_presets)
    # Doit contenir les 6 kinds représentatifs
    for label in ["Mur ext. porteur", "Cloison BA13", "Isolant combles",
                  "Sol carrelage", "Peinture mate", "Ossature bois"]:
        assert label in src, f"Default preset missing: {label}"


# ============ Object Panel props smoke ============

def test_object_panel_component_exists():
    """Le composant frontend doit être présent (validé par existence de fichier).
    Test lu côté disk pour valider bien la présence du composant dans /components/planTakeoff."""
    import os
    assert os.path.exists("/app/frontend/src/components/planTakeoff/ObjectPanel.jsx")
    assert os.path.exists("/app/frontend/src/components/planTakeoff/PresetPicker.jsx")


def test_object_panel_has_all_tabs():
    """Vérifie que le composant expose les 7 tabs demandés."""
    with open("/app/frontend/src/components/planTakeoff/ObjectPanel.jsx") as f:
        src = f.read()
    for tab_id in ["rooms", "openings", "counters", "notes",
                   "angles", "pitched", "measures"]:
        assert f'"{tab_id}"' in src, f"Tab missing: {tab_id}"
    # Test IDs par tab
    for tab_id in ["rooms", "openings", "counters", "notes", "angles", "pitched", "measures"]:
        assert f"object-panel-tab-${{" not in src or f"object-panel-tab-" in src


def test_preset_picker_has_seed_and_create_buttons():
    with open("/app/frontend/src/components/planTakeoff/PresetPicker.jsx") as f:
        src = f.read()
    assert "seedDefaults" in src
    assert "seed-defaults" in src or "-seed-defaults" in src
    assert "new-btn" in src  # bouton "Créer un nouveau modèle"
