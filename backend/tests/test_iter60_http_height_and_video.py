"""Iter60 HTTP E2E — /estimation/analyse + /compute height scaling + video file served."""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@construpilot.fr", "password": "Construpilot2026!"
    }, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ============ /api/estimation/compute — scaling backward compat + at 2.70 ============

def test_compute_default_height_backward_compat(auth_headers):
    """Sans ceiling_height_m, doit conserver quantités iter59 (peinture=290 pour 100m²)."""
    r = requests.post(f"{BASE_URL}/api/estimation/compute", json={
        "project_type": "renovation_complete", "surface": 100.0
    }, headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    lots = {l["key"]: l for l in data["lots"]}
    assert lots["peinture"]["quantity"] == 290.0
    assert data.get("ceiling_height_m") == 2.5


def test_compute_at_270_scales_wall_lots(auth_headers):
    r = requests.post(f"{BASE_URL}/api/estimation/compute", json={
        "project_type": "renovation_complete", "surface": 100.0, "ceiling_height_m": 2.70
    }, headers=auth_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    lots = {l["key"]: l for l in data["lots"]}
    # 2.9 * 100 * 2.70/2.50 = 313.2
    assert abs(lots["peinture"]["quantity"] - 313.20) < 0.05
    # non-wall lot untouched
    assert lots["carrelage"]["quantity"] == 35.0
    assert data["ceiling_height_m"] == 2.70


def test_compute_at_270_total_greater_than_at_250(auth_headers):
    r25 = requests.post(f"{BASE_URL}/api/estimation/compute", json={
        "project_type": "renovation_complete", "surface": 190.0, "ceiling_height_m": 2.5
    }, headers=auth_headers, timeout=30).json()
    r27 = requests.post(f"{BASE_URL}/api/estimation/compute", json={
        "project_type": "renovation_complete", "surface": 190.0, "ceiling_height_m": 2.70
    }, headers=auth_headers, timeout=30).json()
    assert r27["total_avg"] > r25["total_avg"]


# ============ /api/estimation/analyse — override + AI detect ============

def test_analyse_with_override_forces_height(auth_headers):
    """Override utilisateur force la hauteur même si l'IA détecte autre."""
    r = requests.post(f"{BASE_URL}/api/estimation/analyse", json={
        "description": "Rénovation maison 190m²",
        "ceiling_height_m": 2.70
    }, headers=auth_headers, timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    # Endpoint returns {analysis, estimation}
    est = data.get("estimation") or data
    assert est.get("ceiling_height_m") == 2.70
    lots = {l["key"]: l for l in est["lots"]}
    # Wall lots should be scaled
    # peinture surface * 2.9 * 2.70/2.50
    surface = est.get("surface", 190.0)
    expected = round(surface * 2.9 * 2.70 / 2.50, 2)
    assert abs(lots["peinture"]["quantity"] - expected) < 0.5


# ============ Marketing teaser video accessible via public URL ============

def test_marketing_teaser_video_accessible():
    """La vidéo MP4 doit être servie par le frontend en HTTPS."""
    r = requests.head(f"{BASE_URL}/marketing-teaser.mp4", timeout=30, allow_redirects=True)
    # Frontend may serve or not depending on ingress routing; accept 200 or check via GET range
    if r.status_code != 200:
        # Try GET with range
        r = requests.get(f"{BASE_URL}/marketing-teaser.mp4",
                         headers={"Range": "bytes=0-15"}, timeout=30)
        assert r.status_code in (200, 206), f"Video not served: {r.status_code}"
        assert b"ftyp" in r.content, f"Not a valid MP4: {r.content[:20]}"
    else:
        ct = r.headers.get("Content-Type", "")
        assert "video" in ct or "mp4" in ct or ct == "application/octet-stream", \
            f"Unexpected content-type: {ct}"
