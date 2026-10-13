"""Iter 59 — Vague C (QuoterPlan): Room estimator + Preset in PDF + Focus zoom."""
import pytest
from fastapi.testclient import TestClient

from server import app


client = TestClient(app)


# ============ Room estimator endpoint ============

def test_room_estimate_route_registered():
    routes = {r.path for r in app.routes}
    assert "/api/takeoffs/{plan_id}/rooms/{room_id}/estimate" in routes


def test_room_estimate_in_schema_defaults():
    from routes.plans_analysis import RoomEstimateIn
    body = RoomEstimateIn()
    assert body.trades is None
    assert body.override_height_m is None
    assert body.doors == 1
    assert body.windows == 1


def test_room_estimate_in_accepts_selected_trades():
    from routes.plans_analysis import RoomEstimateIn
    body = RoomEstimateIn(trades=["paint", "plinths"], doors=2, windows=3, override_height_m=2.7)
    assert body.trades == ["paint", "plinths"]
    assert body.doors == 2
    assert body.override_height_m == 2.7


# ============ Room dimensions derivation ============

def test_room_dimensions_from_surface_and_perimeter():
    from routes.plans_analysis import _room_dimensions_for_estimator
    # Surface 24 m² + périmètre 20 m → L=6, W=4 (résolution système)
    room = {"surface_m2": 24.0, "perimeter_m": 20.0, "height_m": 2.5}
    L, W, H = _room_dimensions_for_estimator(room, None)
    assert abs(L - 6.0) < 0.1
    assert abs(W - 4.0) < 0.1
    assert H == 2.5


def test_room_dimensions_falls_back_to_square():
    """Sans périmètre, pièce ≈ carré côté √surface."""
    from routes.plans_analysis import _room_dimensions_for_estimator
    room = {"surface_m2": 25.0, "height_m": 2.5}
    L, W, H = _room_dimensions_for_estimator(room, None)
    assert abs(L - 5.0) < 0.01
    assert abs(W - 5.0) < 0.01


def test_room_dimensions_default_when_no_surface():
    from routes.plans_analysis import _room_dimensions_for_estimator
    room = {}
    L, W, H = _room_dimensions_for_estimator(room, None)
    assert L == 4.0 and W == 4.0
    assert H == 2.5  # défaut


def test_room_dimensions_override_height():
    from routes.plans_analysis import _room_dimensions_for_estimator
    room = {"surface_m2": 20.0}
    _, _, H = _room_dimensions_for_estimator(room, 2.7)
    assert H == 2.7


# ============ PDF preset section ============

def test_build_takeoff_pdf_accepts_presets_by_id():
    """La signature doit accepter le paramètre optionnel presets_by_id."""
    from engines.pdf_takeoff import build_takeoff_pdf
    import inspect
    sig = inspect.signature(build_takeoff_pdf)
    assert "presets_by_id" in sig.parameters
    # Par défaut None (optionnel — pas de régression)
    assert sig.parameters["presets_by_id"].default is None


def test_story_room_presets_skips_when_no_preset():
    """Si aucune pièce n'a de preset_id, la section n'est pas rendue (aucun ajout à story)."""
    from engines.pdf_takeoff import _story_room_presets, _styles
    S = _styles()
    story = []
    rooms = [{"name": "Salon"}, {"name": "Cuisine"}]
    _story_room_presets(story, rooms, {}, S)
    assert len(story) == 0


def test_story_room_presets_renders_when_preset_attached():
    """Si une pièce a un preset_id référencé, la section est ajoutée."""
    from engines.pdf_takeoff import _story_room_presets, _styles
    S = _styles()
    story = []
    rooms = [{"name": "Salon", "preset_id": "tpr_test"}]
    presets = {"tpr_test": {"name": "Mur ext porteur 20 cm", "kind": "wall",
                             "unit": "m²", "price_per_unit": 85.0, "notes": None}}
    _story_room_presets(story, rooms, presets, S)
    # Un Paragraph + une Table = 2 éléments au moins
    assert len(story) >= 2


def test_pdf_build_end_to_end_with_presets():
    """Vérifie que le PDF se génère sans erreur avec des presets attachés."""
    from engines.pdf_takeoff import build_takeoff_pdf
    plan = {"plan_id": "p_test", "filename": "test.pdf", "page_count": 1}
    takeoff = {
        "room_count": 1,
        "rooms": [{
            "name": "Salon", "surface_m2": 24, "perimeter_m": 20, "height_m": 2.5,
            "wall_area_gross_m2": 50, "openings_area_m2": 4, "wall_area_net_m2": 46,
            "preset_id": "tpr_test",
        }],
        "levels": [],
        "totals": {"floor_m2": 24, "walls_gross_m2": 50, "walls_net_m2": 46, "perimeter_m": 20},
    }
    presets = {"tpr_test": {"name": "Sol carrelage 60x60", "kind": "floor",
                            "unit": "m²", "price_per_unit": 55.0, "notes": "Antidérapant R11"}}
    pdf_bytes = build_takeoff_pdf(plan, takeoff, materials=None,
                                   branding=None, presets_by_id=presets)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 1000


def test_pdf_build_backward_compat_without_presets():
    """Le paramètre presets_by_id est bien optionnel — les anciens appels marchent."""
    from engines.pdf_takeoff import build_takeoff_pdf
    plan = {"plan_id": "p", "filename": "x.pdf", "page_count": 1}
    takeoff = {"room_count": 0, "rooms": [], "levels": [], "totals": {}}
    pdf_bytes = build_takeoff_pdf(plan, takeoff)  # signature legacy
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


# ============ Frontend RoomEstimateDialog exists ============

def test_room_estimate_dialog_component_exists():
    import os
    assert os.path.exists("/app/frontend/src/components/planTakeoff/RoomEstimateDialog.jsx")


def test_room_estimate_dialog_has_5_trades_and_total_test_id():
    """Le dialog doit exposer un test-id pour le total + un par métier."""
    with open("/app/frontend/src/components/planTakeoff/RoomEstimateDialog.jsx") as f:
        src = f.read()
    assert "room-estimate-dialog" in src
    assert "room-estimate-close" in src
    assert "room-estimate-total" in src
    for trade in ["paint", "floor_tile", "drywall", "insulation", "plinths"]:
        assert trade in src, f"Trade missing: {trade}"
