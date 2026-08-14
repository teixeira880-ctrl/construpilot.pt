"""Iter 61 — Level-Aware Height + Compare on Room Estimate + PDF Icons + Sticky pill."""
import os
import pytest


# ============ FEATURE 1 — Level-Aware Height ============

def test_weighted_avg_height_empty_returns_default():
    from engines.estimation import _weighted_avg_height
    assert _weighted_avg_height(None, 2.5) == 2.5
    assert _weighted_avg_height([], 2.5) == 2.5


def test_weighted_avg_height_single_level():
    from engines.estimation import _weighted_avg_height
    levels = [{"label": "RDC", "surface_m2": 100, "ceiling_height_m": 2.70}]
    assert _weighted_avg_height(levels, 2.5) == 2.70


def test_weighted_avg_height_multi_levels():
    """Maison ancienne : RDC 100m² × 2.60m + R+1 80m² × 2.20m + combles 40m² × 1.80m.
    Pondération : (100×2.60 + 80×2.20 + 40×1.80) / 220 = (260+176+72)/220 = 508/220 = 2.309..."""
    from engines.estimation import _weighted_avg_height
    levels = [
        {"label": "RDC", "surface_m2": 100, "ceiling_height_m": 2.60},
        {"label": "R+1", "surface_m2": 80, "ceiling_height_m": 2.20},
        {"label": "combles", "surface_m2": 40, "ceiling_height_m": 1.80},
    ]
    h = _weighted_avg_height(levels, 2.5)
    assert abs(h - 2.309) < 0.001


def test_weighted_avg_height_zero_surfaces_falls_back():
    from engines.estimation import _weighted_avg_height
    levels = [{"label": "x", "surface_m2": 0, "ceiling_height_m": 2.5}]
    assert _weighted_avg_height(levels, 2.7) == 2.7


def test_weighted_avg_height_missing_fields_ignored():
    """Un item sans surface_m2 est ignoré, on retombe sur les autres."""
    from engines.estimation import _weighted_avg_height
    levels = [
        {"label": "RDC", "surface_m2": 100, "ceiling_height_m": 2.60},
        {"label": "invalid"},  # ignoré
    ]
    assert _weighted_avg_height(levels, 2.5) == 2.60


def test_estimate_with_levels_uses_weighted_height():
    """L'estimator utilise la hauteur pondérée pour les lots muraux."""
    from engines import estimation
    levels = [
        {"label": "RDC", "surface_m2": 100, "ceiling_height_m": 2.70},
        {"label": "combles", "surface_m2": 60, "ceiling_height_m": 1.80},
    ]
    # Pondération: (100*2.70 + 60*1.80) / 160 = (270+108)/160 = 378/160 = 2.3625
    est = estimation.estimate("renovation_complete", 160.0, levels=levels)
    assert abs(est["ceiling_height_m"] - 2.3625) < 0.001
    # Peinture doit être scalée par 2.3625/2.5 = 0.945
    expected_paint = round(160 * 2.9 * (2.3625 / 2.5), 2)
    paint_lot = next(l for l in est["lots"] if l["key"] == "peinture")
    assert abs(paint_lot["quantity"] - expected_paint) < 0.5  # marge d'arrondi


def test_estimate_response_exposes_levels():
    from engines import estimation
    levels = [{"label": "RDC", "surface_m2": 100, "ceiling_height_m": 2.5}]
    est = estimation.estimate("renovation_complete", 100.0, levels=levels)
    assert est["levels"] == levels


def test_estimate_response_empty_levels_when_absent():
    from engines import estimation
    est = estimation.estimate("renovation_complete", 100.0)
    assert est["levels"] == []


# ============ EstimateIn schema levels ============

def test_estimate_in_accepts_levels():
    from routes.estimation_routes import EstimateIn, LevelHeightSpec
    body = EstimateIn(
        surface=190,
        levels=[
            LevelHeightSpec(label="RDC", surface_m2=100, ceiling_height_m=2.70),
            LevelHeightSpec(label="R+1", surface_m2=90, ceiling_height_m=2.30),
        ]
    )
    assert len(body.levels) == 2
    assert body.levels[0].label == "RDC"
    assert body.levels[1].ceiling_height_m == 2.30


def test_estimate_in_levels_optional():
    from routes.estimation_routes import EstimateIn
    body = EstimateIn(surface=100)
    assert body.levels is None


# ============ AI prompt mentions levels ============

def test_ai_prompt_mentions_levels_per_storey():
    import inspect
    from engines import ai
    src = inspect.getsource(ai._analysis_prompt)
    assert '"levels"' in src
    assert "RDC" in src or "R+1" in src


def test_ai_cleans_invalid_levels():
    """`_clean_levels` rejette entrées sans surface ou hors bornes (1.5-5.0 m)."""
    from engines import ai
    cleaned = ai._clean_levels([
        {"label": "RDC", "surface_m2": 40, "ceiling_height_m": 2.6},
        {"label": "cave", "surface_m2": 0, "ceiling_height_m": 2.2},
        {"label": "grenier", "surface_m2": 10, "ceiling_height_m": 9.0},
        "junk",
    ])
    assert len(cleaned) == 1 and cleaned[0]["label"] == "RDC"


# ============ FEATURE 2 — Compare on Room Estimate ============

def test_live_total_bar_has_compare_prices_button():
    with open("/app/frontend/src/components/planTakeoff/LiveTotalBar.jsx") as f:
        src = f.read()
    assert "live-total-compare-prices" in src
    assert "compareBestPrices" in src
    assert "Voir vainqueur prix" in src


def test_live_total_bar_collects_materials_per_room():
    with open("/app/frontend/src/components/planTakeoff/LiveTotalBar.jsx") as f:
        src = f.read()
    assert "materialsByRoom" in src
    assert "setMaterialsByRoom" in src


# ============ FEATURE 3 — PDF Icons ============

def test_preset_kind_icons_mapping():
    from engines.pdf_takeoff import PRESET_KIND_ICONS
    # Doit couvrir les 10 kinds
    for k in ["wall", "opening", "floor", "ceiling", "paint",
              "insulation", "counter", "roof", "note", "other"]:
        assert k in PRESET_KIND_ICONS, f"Kind icon missing: {k}"
        entry = PRESET_KIND_ICONS[k]
        assert "color" in entry
        assert "letter" in entry
        assert "label" in entry


def test_preset_icon_drawing_returns_drawing():
    """Le helper génère un objet ReportLab Drawing sans exception."""
    from engines.pdf_takeoff import _preset_icon_drawing
    from reportlab.graphics.shapes import Drawing
    d = _preset_icon_drawing("wall")
    assert isinstance(d, Drawing)
    d_unknown = _preset_icon_drawing("unknown_kind")
    assert isinstance(d_unknown, Drawing)


def test_pdf_build_still_works_with_icons():
    """Le PDF se génère sans erreur et contient des bytes valides."""
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
    presets = {"tpr_test": {"name": "Isolant combles laine 200mm", "kind": "insulation",
                            "unit": "m²", "price_per_unit": 18.5, "notes": "R=5.0"}}
    pdf_bytes = build_takeoff_pdf(plan, takeoff, materials=None,
                                   branding=None, presets_by_id=presets)
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    # Icônes = Drawings, donc PDF doit être un peu plus gros que sans (au moins 1 KB overhead)
    assert len(pdf_bytes) > 2000


# ============ FEATURE 4 — Sticky on Scroll ============

def test_live_total_bar_has_pill_collapsed_mode():
    with open("/app/frontend/src/components/planTakeoff/LiveTotalBar.jsx") as f:
        src = f.read()
    assert "live-total-bar-pill" in src
    assert "live-total-pill-value" in src
    assert "collapsed" in src


def test_live_total_bar_listens_to_scroll():
    with open("/app/frontend/src/components/planTakeoff/LiveTotalBar.jsx") as f:
        src = f.read()
    # useEffect avec addEventListener("scroll", ...)
    assert 'addEventListener("scroll"' in src or "addEventListener('scroll'" in src


# ============ SmartProject UI shows levels ============

def test_smart_project_ui_shows_levels():
    with open("/app/frontend/src/pages/SmartProject.jsx") as f:
        src = f.read()
    assert "analysis-levels" in src
    assert "analysis-level-" in src
    assert "hauteur pondérée" in src or "pondérée" in src
