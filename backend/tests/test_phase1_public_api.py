"""Phase 1 review — validate the two new backend routes via the official public URL.

Covers all backend items of the review request:
- POST /api/calculate/quarter-turn-top (straight and balanced auto)
- POST /api/calculate/half-turn (straight, balanced auto, num_winders out-of-range)
- CORS wildcard on /api/*
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://escalier-pro.preview.emergentagent.com").rstrip("/")
TIMEOUT = 20


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# Quarter-turn top
# ---------------------------------------------------------------------------

def test_qt_top_straight_is_buildable_16_steps(api):
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 5500,
        "available_width_mm": 2000,
        "stair_width_mm": 900,
        "balancing": "straight",
        "landing_length_mm": 1000,
        "landing_width_mm": 1000,
    }
    r = api.post(f"{BASE_URL}/api/calculate/quarter-turn-top", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_buildable"] is True
    assert data["num_steps"] == 16
    # sanity on geometry
    assert abs(data["riser_height_mm"] - 175) <= 1


def test_qt_top_balanced_auto_selects_winders(api):
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 4500,
        "available_width_mm": 2200,
        "stair_width_mm": 900,
        "balancing": "balanced",
    }
    r = api.post(f"{BASE_URL}/api/calculate/quarter-turn-top", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_buildable"] is True
    codes = {a["code"] for a in data["alerts"]}
    assert "AUTO_WINDERS_SELECTED" in codes


# ---------------------------------------------------------------------------
# Half turn
# ---------------------------------------------------------------------------

def test_half_turn_straight_is_buildable(api):
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 3000,
        "available_width_mm": 2200,
        "stair_width_mm": 900,
        "balancing": "straight",
    }
    r = api.post(f"{BASE_URL}/api/calculate/half-turn", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_buildable"] is True
    assert data["stair_type"].startswith("half_turn")


def test_half_turn_balanced_auto_finds_config(api):
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 2800,
        "available_width_mm": 2000,
        "stair_width_mm": 900,
        "balancing": "balanced",
        "num_winders": "auto",
    }
    r = api.post(f"{BASE_URL}/api/calculate/half-turn", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_buildable"] is True
    codes = {a["code"] for a in data["alerts"]}
    assert "AUTO_WINDERS_SELECTED" in codes


def test_half_turn_num_winders_2_rejected(api):
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 3000,
        "available_width_mm": 2200,
        "stair_width_mm": 900,
        "balancing": "balanced",
        "num_winders": 2,
    }
    r = api.post(f"{BASE_URL}/api/calculate/half-turn", json=payload, timeout=TIMEOUT)
    # Must be rejected by Pydantic validation (422) — 4..12 range
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# CORS wildcard
# ---------------------------------------------------------------------------

def test_cors_wildcard_on_calculate_route(api):
    r = api.options(
        f"{BASE_URL}/api/calculate/half-turn",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        timeout=TIMEOUT,
    )
    # Preflight should succeed
    assert r.status_code in (200, 204), (r.status_code, r.text)
    allow_origin = r.headers.get("access-control-allow-origin")
    assert allow_origin == "*", f"Expected wildcard, got {allow_origin!r}"
    # Wildcard MUST NOT be paired with credentials=true
    allow_creds = r.headers.get("access-control-allow-credentials")
    assert allow_creds in (None, "false"), f"credentials header must be false/absent, got {allow_creds!r}"


def test_cors_wildcard_on_norms_route(api):
    # NOTE: Cloudflare edge sometimes rewrites `*` -> echoed origin on connection reuse.
    # Both are valid CORS responses when allow_credentials=False (which we assert below).
    r = requests.get(
        f"{BASE_URL}/api/norms/fr",
        headers={"Origin": "https://example.com"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200
    acao = r.headers.get("access-control-allow-origin")
    assert acao in ("*", "https://example.com"), f"Unexpected ACAO: {acao!r}"
    # Credentials must remain false to keep wildcard/echo semantics safe
    assert r.headers.get("access-control-allow-credentials") in (None, "false")
