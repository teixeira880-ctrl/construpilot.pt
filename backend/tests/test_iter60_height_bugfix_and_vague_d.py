"""Iter 60 — Bug fix Smart Project height + Vague D features (Preset Attach, Estimate→Quote, Live Total Bar, Video Teaser)."""
import math
import os
import pytest


# ============ BUG FIX 1 — ceiling_height_m scale wall lots ============

def test_reference_ceiling_constant():
    from engines.estimation import REFERENCE_CEILING_HEIGHT_M, DEFAULT_CEILING_HEIGHT_M
    assert REFERENCE_CEILING_HEIGHT_M == 2.5
    assert DEFAULT_CEILING_HEIGHT_M == 2.5


def test_wall_height_sensitive_lots():
    from engines.estimation import WALL_HEIGHT_SENSITIVE_LOTS
    assert "peinture" in WALL_HEIGHT_SENSITIVE_LOTS
    assert "placo" in WALL_HEIGHT_SENSITIVE_LOTS
    assert "isolation" in WALL_HEIGHT_SENSITIVE_LOTS
    assert "facade" in WALL_HEIGHT_SENSITIVE_LOTS
    # Non-wall lots doivent PAS être scalés
    assert "carrelage" not in WALL_HEIGHT_SENSITIVE_LOTS
    assert "parquet" not in WALL_HEIGHT_SENSITIVE_LOTS
    assert "menuiseries" not in WALL_HEIGHT_SENSITIVE_LOTS


def test_estimate_at_reference_height_unchanged():
    """À 2.5m (référence), les quantités doivent être identiques à l'ancien comportement."""
    from engines import estimation
    est = estimation.estimate("renovation_complete", 100.0, ceiling_height_m=2.5)
    lots = {l["key"]: l for l in est["lots"]}
    # Facteurs originaux du catalog : peinture=2.9, isolation=1.4, placo=1.8, facade non inclus
    assert lots["peinture"]["quantity"] == 290.0
    assert lots["isolation"]["quantity"] == 140.0
    assert lots["placo"]["quantity"] == 180.0


def test_estimate_at_270m_scales_wall_lots():
    """À 2.70m, les lots MURAUX doivent augmenter de 2.70/2.50 = 8%."""
    from engines import estimation
    est = estimation.estimate("renovation_complete", 100.0, ceiling_height_m=2.70)
    lots = {l["key"]: l for l in est["lots"]}
    # peinture 2.9 × 100 × 2.70/2.50 = 313.20
    assert abs(lots["peinture"]["quantity"] - 313.20) < 0.05
    # isolation 1.4 × 100 × 2.70/2.50 = 151.20
    assert abs(lots["isolation"]["quantity"] - 151.20) < 0.05
    # placo 1.8 × 100 × 2.70/2.50 = 194.40
    assert abs(lots["placo"]["quantity"] - 194.40) < 0.05
    # NON scalés
    assert lots["carrelage"]["quantity"] == 35.0
    assert lots["parquet"]["quantity"] == 50.0


def test_estimate_190m2_at_270m_matches_user_expectation():
    """Cas utilisateur : maison 190m² à 2.70m — vérif totaux cohérents."""
    from engines import estimation
    est = estimation.estimate("renovation_complete", 190.0, ceiling_height_m=2.70)
    lots = {l["key"]: l for l in est["lots"]}
    # Peinture doit être surface × 2.9 × (2.70/2.50) = 190 × 2.9 × 1.08 = 595.08
    expected_paint = round(190 * 2.9 * (2.70 / 2.50), 2)
    assert abs(lots["peinture"]["quantity"] - expected_paint) < 0.1
    # Le total doit être supérieur au total à 2.5m (car les murs sont plus grands)
    est_25 = estimation.estimate("renovation_complete", 190.0, ceiling_height_m=2.5)
    assert est["total_avg"] > est_25["total_avg"]


def test_estimate_response_includes_ceiling_height():
    """La réponse expose la hauteur utilisée pour transparence."""
    from engines import estimation
    est = estimation.estimate("renovation_complete", 100.0, ceiling_height_m=2.70)
    assert est["ceiling_height_m"] == 2.70


def test_pricing_request_dataclass_has_ceiling_height():
    from engines.estimation import PricingRequest, DEFAULT_CEILING_HEIGHT_M
    req = PricingRequest(project_type="renovation_complete", surface=100.0)
    assert req.ceiling_height_m == DEFAULT_CEILING_HEIGHT_M


# ============ AI detection of ceiling height ============

def test_ai_analyse_prompt_asks_for_ceiling_height():
    """Le prompt AI doit demander la hauteur sous plafond."""
    import inspect
    from engines import ai
    src = inspect.getsource(ai._analysis_prompt)
    assert "ceiling_height_m" in src
    assert "hauteur" in src.lower()


def test_ai_analyse_result_bounds_ceiling_height():
    """La hauteur détectée par l'IA est cappée à [2.0, 5.0]."""
    import inspect
    from engines import ai
    src = inspect.getsource(ai._normalize_analysis)
    assert "max(2.0" in src and "min(5.0" in src


# ============ EstimateIn / DescribeIn accept ceiling_height ============

def test_estimate_in_schema_has_ceiling_height():
    from routes.estimation_routes import EstimateIn
    body = EstimateIn()
    assert body.ceiling_height_m == 2.5
    body2 = EstimateIn(ceiling_height_m=2.7)
    assert body2.ceiling_height_m == 2.7


def test_describe_in_schema_has_optional_ceiling_height():
    from routes.estimation_routes import DescribeIn
    body = DescribeIn(description="Rénovation maison 190m²")
    assert body.ceiling_height_m is None  # optionnel
    body2 = DescribeIn(description="X", ceiling_height_m=2.7)
    assert body2.ceiling_height_m == 2.7


# ============ FEATURE 2 — Estimate to Quote ============

def test_room_estimate_dialog_has_add_to_quote_prop():
    with open("/app/frontend/src/components/planTakeoff/RoomEstimateDialog.jsx") as f:
        src = f.read()
    assert "onAddToQuote" in src
    assert "room-estimate-add-to-quote" in src
    assert "Ajouter au devis" in src


def test_smart_project_batch_key_in_price_search():
    """PriceSearch lit sessionStorage 'construpilot_price_search_batch'."""
    with open("/app/frontend/src/pages/PriceSearch.jsx") as f:
        src = f.read()
    assert "construpilot_price_search_batch" in src
    assert "estimation-batch-panel" in src
    assert "estimationBatch" in src


def test_smart_project_writes_batch_on_prices_button():
    """Le bouton 'Comparer prix' de SmartProject écrit le batch."""
    with open("/app/frontend/src/pages/SmartProject.jsx") as f:
        src = f.read()
    assert "construpilot_price_search_batch" in src
    assert "/estimation/materials" in src
    assert "goto-prices-btn" in src


# ============ FEATURE 3 — Preset Attach in Object Panel ============

def test_object_panel_has_preset_attach_hooks():
    with open("/app/frontend/src/components/planTakeoff/ObjectPanel.jsx") as f:
        src = f.read()
    assert "onAttachPreset" in src
    assert "room-preset-toggle-" in src
    assert "room-preset-attach-" in src
    assert "room-preset-option-" in src


def test_object_panel_loads_presets_when_open():
    """L'ObjectPanel doit faire GET /tool-presets à l'ouverture."""
    with open("/app/frontend/src/components/planTakeoff/ObjectPanel.jsx") as f:
        src = f.read()
    assert '"/tool-presets"' in src or "'/tool-presets'" in src


def test_plan_takeoff_calls_attach_preset():
    """PlanTakeoff.jsx doit avoir attachPresetToRoom + le passer à ObjectPanel."""
    with open("/app/frontend/src/pages/PlanTakeoff.jsx") as f:
        src = f.read()
    assert "attachPresetToRoom" in src
    assert "onAttachPreset={attachPresetToRoom}" in src


# ============ FEATURE 4 — Live Total Bar ============

def test_live_total_bar_component_exists():
    assert os.path.exists("/app/frontend/src/components/planTakeoff/LiveTotalBar.jsx")


def test_live_total_bar_has_test_ids():
    with open("/app/frontend/src/components/planTakeoff/LiveTotalBar.jsx") as f:
        src = f.read()
    for tid in ["live-total-bar", "live-total-value", "live-total-compute-btn"]:
        assert tid in src, f"Missing testid: {tid}"


def test_live_total_bar_wired_in_plan_takeoff():
    with open("/app/frontend/src/pages/PlanTakeoff.jsx") as f:
        src = f.read()
    assert "LiveTotalBar" in src
    assert "planId={plan?.plan_id}" in src


# ============ FEATURE 5 — Marketing teaser video uploaded ============

def test_marketing_teaser_video_uploaded():
    path = "/app/frontend/public/marketing-teaser.mp4"
    assert os.path.exists(path)
    size = os.path.getsize(path)
    # Video should be at least 500KB (real video, not placeholder)
    assert size > 500 * 1024, f"Video too small: {size} bytes"
    with open(path, "rb") as f:
        header = f.read(8)
    # Valid MP4 files start with ftyp box at offset 4
    assert b"ftyp" in header, f"Not a valid MP4 header: {header}"
