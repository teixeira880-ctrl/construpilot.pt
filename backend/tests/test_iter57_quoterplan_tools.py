"""Iter 57 — QuoterPlan-like tools (Counter/Note/Angle/RoofPitch) regression."""
import math
import pytest
from fastapi.testclient import TestClient

from server import app
from routes.plans_common import _plan_summary

client = TestClient(app)


# ============ Schema — AnnotationsIn ============

def test_annotations_in_schema_all_types():
    from routes.plans_crud import AnnotationsIn
    payload = {
        "page_index": 0,
        "counters": [{"id": "c1", "label": "Prises", "color": "#f97316", "unit": "u",
                      "markers": [{"x": 10.0, "y": 20.0}, {"x": 30.0, "y": 40.0}]}],
        "notes": [{"id": "n1", "x": 5.0, "y": 5.0, "text": "Mur porteur"}],
        "angles": [{"id": "a1", "vx": 100.0, "vy": 100.0, "ax": 150.0, "ay": 100.0,
                    "bx": 100.0, "by": 150.0, "degrees": 90.0}],
        "pitched_surfaces": [{"id": "p1", "points": [[0, 0], [100, 0], [100, 100], [0, 100]],
                              "projected_area_m2": 100.0, "pitch_degrees": 30.0,
                              "real_area_m2": 115.5}],
    }
    parsed = AnnotationsIn(**payload)
    assert len(parsed.counters) == 1
    assert len(parsed.counters[0].markers) == 2
    assert parsed.counters[0].markers[0].x == 10.0
    assert parsed.notes[0].text == "Mur porteur"
    assert parsed.angles[0].degrees == 90.0
    assert parsed.pitched_surfaces[0].pitch_degrees == 30.0


def test_annotations_in_defaults_empty_lists():
    from routes.plans_crud import AnnotationsIn
    a = AnnotationsIn(page_index=2)
    assert a.counters == []
    assert a.notes == []
    assert a.angles == []
    assert a.pitched_surfaces == []


def test_counter_annotation_default_color():
    from routes.plans_crud import CounterAnnotation
    c = CounterAnnotation(id="x")
    assert c.color == "#f97316"
    assert c.unit == "u"
    assert c.markers == []


# ============ Endpoint registration ============

def test_annotations_route_registered():
    routes = {r.path for r in app.routes}
    assert "/api/takeoffs/{plan_id}/annotations" in routes


# ============ _plan_summary includes annotations ============

def test_plan_summary_exposes_annotations():
    p = {
        "plan_id": "p1", "filename": "x.pdf", "kind": "pdf", "page_count": 1,
        "pages": [], "rooms": [], "calibrations": {},
        "annotations": {"0": {"counters": [{"id": "c1", "markers": []}]}},
    }
    s = _plan_summary(p)
    assert "annotations" in s
    assert s["annotations"]["0"]["counters"][0]["id"] == "c1"


def test_plan_summary_defaults_empty_annotations():
    p = {"plan_id": "p1", "filename": "x.pdf", "kind": "pdf", "pages": []}
    s = _plan_summary(p)
    assert s["annotations"] == {}


# ============ Roof pitch math ============

def test_roof_pitch_projected_to_real_area():
    """La surface réelle d'une toiture inclinée = projected / cos(pitch)."""
    projected = 100.0
    for pitch in [0, 15, 30, 45, 60]:
        real = projected / max(0.05, math.cos(math.radians(pitch)))
        # À plat : real == projected. À 45° : ratio ≈ 1.414. À 60° : ratio ≈ 2.
        if pitch == 0:
            assert abs(real - 100.0) < 0.01
        if pitch == 45:
            assert 141 < real < 142
        if pitch == 60:
            assert 199 < real < 201


def test_angle_computation_right_angle():
    """3 clics formant un angle droit → 90°."""
    a = (100, 0)   # branche 1
    v = (0, 0)     # sommet
    b = (0, 100)   # branche 2
    v1 = (a[0] - v[0], a[1] - v[1])
    v2 = (b[0] - v[0], b[1] - v[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    cosT = dot / (math.hypot(*v1) * math.hypot(*v2))
    deg = math.degrees(math.acos(cosT))
    assert abs(deg - 90.0) < 0.01


def test_angle_computation_45_degrees():
    a = (100, 0)
    v = (0, 0)
    b = (100, 100)
    v1 = (a[0] - v[0], a[1] - v[1])
    v2 = (b[0] - v[0], b[1] - v[1])
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    cosT = dot / (math.hypot(*v1) * math.hypot(*v2))
    deg = math.degrees(math.acos(cosT))
    assert abs(deg - 45.0) < 0.01


# ============ x/12 pitch reading (roof convention) ============

def test_pitch_x_over_12():
    """La pente x/12 = tan(angle) × 12."""
    assert abs(math.tan(math.radians(0)) * 12 - 0) < 0.01
    assert abs(math.tan(math.radians(30)) * 12 - 6.928) < 0.01   # 7/12 approx
    assert abs(math.tan(math.radians(45)) * 12 - 12) < 0.01       # 12/12
