"""Integration tests for STAIRPILOT Phase 0 backend routes via public preview URL.

Tests the deployed endpoints on the public preview URL specified in the
review request (iteration 2 fixes):
    - GET /api/norms/fr
    - GET /api/openapi.json
    - POST /api/calculate/straight
    - POST /api/calculate/quarter-turn-bottom (auto num_winders)
    - All alerts populate 'message' field (FR)
    - Blondel / STAIR_RUN_TOO_LONG validation
    - Non-blocker DTU deviation (BALANCING_WALKLINE_TOO_SMALL)
"""
from __future__ import annotations

import pytest
import requests

# Public preview URL from the review request (iteration 3: official custom subdomain).
BASE_URL = "https://escalier-pro.preview.emergentagent.com"
TIMEOUT = 30


@pytest.fixture(scope="module")
def api_client() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --------------------------------------------------------------------------- #
# 1) GET /api/norms/fr — seuils DTU 36.3
# --------------------------------------------------------------------------- #
def test_norms_fr_returns_dtu_thresholds(api_client: requests.Session) -> None:
    r = api_client.get(f"{BASE_URL}/api/norms/fr", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["headroom_min_mm"] == 1900
    assert data["blondel_optimal_min_mm"] == 600
    # sanity check other keys exist
    assert "riser_height_max_mm" in data
    assert "tread_depth_optimal_min_mm" in data


# --------------------------------------------------------------------------- #
# 2) GET /api/openapi.json
# --------------------------------------------------------------------------- #
def test_openapi_alias_accessible(api_client: requests.Session) -> None:
    r = api_client.get(f"{BASE_URL}/api/openapi.json", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "paths" in data
    assert "/api/calculate/straight" in data["paths"]
    assert "/api/calculate/quarter-turn-bottom" in data["paths"]


# --------------------------------------------------------------------------- #
# 3) POST /api/calculate/straight — cas nominal H=2800, L=4500
# --------------------------------------------------------------------------- #
def test_calculate_straight_nominal(api_client: requests.Session) -> None:
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 4500,
        "available_width_mm": 1500,
        "stair_width_mm": 900,
        "stairwell_length_mm": 3200,
        "stairwell_width_mm": 1000,
        "ceiling_height_mm": 2800,
    }
    r = api_client.post(f"{BASE_URL}/api/calculate/straight", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["num_steps"] == 16
    assert abs(data["riser_height_mm"] - 175) < 1
    assert abs(data["tread_depth_mm"] - 280) < 1
    assert abs(data["blondel_value_mm"] - 630) < 1
    assert data["is_buildable"] is True


# --------------------------------------------------------------------------- #
# 4) POST /api/calculate/quarter-turn-bottom — mode auto
# --------------------------------------------------------------------------- #
def test_quarter_turn_bottom_auto_winders(api_client: requests.Session) -> None:
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 3000,
        "available_width_mm": 2200,
        "stair_width_mm": 900,
        "stairwell_length_mm": 2800,
        "stairwell_width_mm": 1000,
        "ceiling_height_mm": 2800,
        "balancing": "balanced",
        # num_winders omitted -> auto
    }
    r = api_client.post(
        f"{BASE_URL}/api/calculate/quarter-turn-bottom", json=payload, timeout=TIMEOUT
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_buildable"] is True, f"alerts={data['alerts']}"

    auto_alerts = [a for a in data["alerts"] if a["code"] == "AUTO_WINDERS_SELECTED"]
    assert len(auto_alerts) == 1, f"AUTO_WINDERS_SELECTED absent: {data['alerts']}"
    auto = auto_alerts[0]
    # tread_index is used to convey the chosen number of winders
    chosen = auto.get("tread_index") or auto.get("value")
    assert chosen is not None
    assert 3 <= int(chosen) <= 9, f"chosen={chosen}"


# --------------------------------------------------------------------------- #
# 5) TOUS les alertes doivent avoir un 'message' non-vide
# --------------------------------------------------------------------------- #
def _all_alerts_have_message(alerts: list) -> None:
    for a in alerts:
        assert "message" in a, f"missing 'message' key: {a}"
        assert a["message"] is not None and a["message"].strip() != "", (
            f"empty message: {a}"
        )
        # Should equal message_fr (auto-filled)
        assert a["message"] == a["message_fr"], (
            f"message != message_fr: {a}"
        )


def test_all_alerts_have_message_field(api_client: requests.Session) -> None:
    # Trigger from straight nominal + QT auto
    r1 = api_client.post(
        f"{BASE_URL}/api/calculate/straight",
        json={
            "floor_height_mm": 2800,
            "available_length_mm": 4500,
            "available_width_mm": 1500,
            "stair_width_mm": 900,
            "stairwell_length_mm": 3200,
            "stairwell_width_mm": 1000,
            "ceiling_height_mm": 2800,
        },
        timeout=TIMEOUT,
    )
    assert r1.status_code == 200
    _all_alerts_have_message(r1.json()["alerts"])

    r2 = api_client.post(
        f"{BASE_URL}/api/calculate/quarter-turn-bottom",
        json={
            "floor_height_mm": 2800,
            "available_length_mm": 3000,
            "available_width_mm": 2200,
            "stair_width_mm": 900,
            "stairwell_length_mm": 2800,
            "stairwell_width_mm": 1000,
            "ceiling_height_mm": 2800,
            "balancing": "balanced",
        },
        timeout=TIMEOUT,
    )
    assert r2.status_code == 200
    _all_alerts_have_message(r2.json()["alerts"])


# --------------------------------------------------------------------------- #
# 6) Blondel / STAIR_RUN_TOO_LONG — bloquant
# --------------------------------------------------------------------------- #
def test_stair_run_too_long_is_blocking(api_client: requests.Session) -> None:
    """H=2800, L=3200 : l'escalier ne rentre pas -> alerte rouge blocker."""
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 3200,
        "available_width_mm": 1500,
        "stair_width_mm": 900,
        "stairwell_length_mm": 3200,
        "stairwell_width_mm": 1000,
        "ceiling_height_mm": 2800,
    }
    r = api_client.post(f"{BASE_URL}/api/calculate/straight", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    codes = [a["code"] for a in data["alerts"]]
    assert "STAIR_RUN_TOO_LONG" in codes, f"codes={codes}"
    stair_run_alert = next(a for a in data["alerts"] if a["code"] == "STAIR_RUN_TOO_LONG")
    assert stair_run_alert["level"] == "red"
    assert data["is_buildable"] is False
    _all_alerts_have_message(data["alerts"])


# --------------------------------------------------------------------------- #
# 7) Non-conformité DTU non-blocker — BALANCING_WALKLINE_TOO_SMALL
# --------------------------------------------------------------------------- #
def test_qt_bottom_manual_winders_5_walkline_too_small(api_client: requests.Session) -> None:
    """5 winders -> walkline < 240mm ; DTU alert rouge mais is_buildable=True si run rentre."""
    # available_length_mm augmenté à 3800 pour que le run rentre malgré 5 winders
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 3800,
        "available_width_mm": 2200,
        "stair_width_mm": 900,
        "stairwell_length_mm": 3800,
        "stairwell_width_mm": 1000,
        "ceiling_height_mm": 2800,
        "balancing": "balanced",
        "num_winders": 5,
    }
    r = api_client.post(
        f"{BASE_URL}/api/calculate/quarter-turn-bottom", json=payload, timeout=TIMEOUT
    )
    assert r.status_code == 200, r.text
    data = r.json()
    codes = [a["code"] for a in data["alerts"]]
    assert "BALANCING_WALKLINE_TOO_SMALL" in codes, f"codes={codes}"
    walk_alert = next(a for a in data["alerts"] if a["code"] == "BALANCING_WALKLINE_TOO_SMALL")
    assert walk_alert["level"] == "red"
    # DTU deviation only -> not blocker as long as physical run fits
    assert data["is_buildable"] is True, (
        f"BALANCING_WALKLINE_TOO_SMALL doit rester non-blocker. alerts={data['alerts']}"
    )
    _all_alerts_have_message(data["alerts"])


# --------------------------------------------------------------------------- #
# 8) Iteration-3 : auto vs explicit avec le MEME num_winders -> même géométrie
# --------------------------------------------------------------------------- #
def test_auto_and_explicit_same_winders_same_geometry(api_client: requests.Session) -> None:
    base = {
        "floor_height_mm": 2800,
        "available_length_mm": 3000,
        "available_width_mm": 2200,
        "stair_width_mm": 900,
        "stairwell_length_mm": 2800,
        "stairwell_width_mm": 1000,
        "ceiling_height_mm": 2800,
        "balancing": "balanced",
    }
    r_auto = api_client.post(
        f"{BASE_URL}/api/calculate/quarter-turn-bottom", json=base, timeout=TIMEOUT
    )
    assert r_auto.status_code == 200, r_auto.text
    auto = r_auto.json()
    auto_alert = next((a for a in auto["alerts"] if a["code"] == "AUTO_WINDERS_SELECTED"), None)
    assert auto_alert is not None
    n_auto = int(auto_alert.get("tread_index") or auto_alert.get("value"))

    r_expl = api_client.post(
        f"{BASE_URL}/api/calculate/quarter-turn-bottom",
        json={**base, "num_winders": n_auto},
        timeout=TIMEOUT,
    )
    assert r_expl.status_code == 200, r_expl.text
    expl = r_expl.json()

    assert auto["is_buildable"] == expl["is_buildable"]
    assert auto["num_treads"] == expl["num_treads"]
    assert auto["stair_run_mm"] == expl["stair_run_mm"]
    assert auto["riser_height_mm"] == expl["riser_height_mm"]

    codes_auto = {a["code"] for a in auto["alerts"] if a["code"] != "AUTO_WINDERS_SELECTED"}
    codes_expl = {a["code"] for a in expl["alerts"]}
    assert codes_auto == codes_expl
    assert "AUTO_WINDERS_SELECTED" not in codes_expl


# --------------------------------------------------------------------------- #
# 9) Iteration-3 : physiquement impossible -> is_buildable=false + blocker
# --------------------------------------------------------------------------- #
def test_physically_impossible_straight_is_not_buildable(api_client: requests.Session) -> None:
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 500,
        "available_width_mm": 1500,
        "stair_width_mm": 900,
    }
    r = api_client.post(f"{BASE_URL}/api/calculate/straight", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_buildable"] is False
    blockers = {"STAIR_RUN_TOO_LONG", "STAIR_WIDTH_INSUFFICIENT", "HEADROOM_INSUFFICIENT",
                "STAIRWELL_TOO_SMALL", "GEOMETRY_INVALID", "BALANCING_IMPOSSIBLE",
                "AUTO_WINDERS_NO_SOLUTION"}
    red_codes = {a["code"] for a in data["alerts"] if a["level"] == "red"}
    assert red_codes & blockers, f"aucun blocker parmi red={red_codes}"


# --------------------------------------------------------------------------- #
# 10) Iteration-3 : DTU non-conforme mais physiquement OK -> is_buildable=true
# --------------------------------------------------------------------------- #
def test_dtu_nonconform_but_physically_ok_is_buildable(api_client: requests.Session) -> None:
    payload = {
        "floor_height_mm": 2800,
        "available_length_mm": 3000,
        "available_width_mm": 2200,
        "stair_width_mm": 900,
        "balancing": "balanced",
    }
    r = api_client.post(
        f"{BASE_URL}/api/calculate/quarter-turn-bottom", json=payload, timeout=TIMEOUT
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_buildable"] is True
    red_codes = {a["code"] for a in data["alerts"] if a["level"] == "red"}
    blockers = {"STAIR_RUN_TOO_LONG", "STAIR_WIDTH_INSUFFICIENT", "HEADROOM_INSUFFICIENT",
                "STAIRWELL_TOO_SMALL", "GEOMETRY_INVALID", "BALANCING_IMPOSSIBLE",
                "AUTO_WINDERS_NO_SOLUTION"}
    # Il DOIT y avoir des red DTU non-blocker
    assert red_codes and (red_codes - blockers), (
        f"attendu au moins une red DTU non-blocker, red={red_codes}"
    )
    # STAIR_RUN_TOO_LONG absent
    assert "STAIR_RUN_TOO_LONG" not in red_codes
