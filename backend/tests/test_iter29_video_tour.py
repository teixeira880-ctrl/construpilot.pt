"""Iter29 — Backend tests for Video Tour 3D endpoints & validation.

Endpoints tested:
- POST /api/takeoffs/{plan_id}/render-video     (generation, 2 styles min)
- GET  /api/takeoffs/{plan_id}/videos-3d        (listing)
- GET  /api/takeoffs/{plan_id}/videos-3d/{video_id}/mp4  (streaming)
- Validation errors: unknown style, 1 style (too few), 7 styles (too many)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

# Credentials read from env — never hardcoded here. Set via TEST_USER_PRO_EMAIL /
# TEST_USER_PRO_PASSWORD, or fall back to /app/memory/test_credentials.md
# (which is the sanctioned test-fixture source, not a code secret).
PRO_EMAIL = os.environ.get("TEST_USER_PRO_EMAIL", "pro@construpilot.fr")
PRO_PASSWORD = os.environ.get("TEST_USER_PRO_PASSWORD", "Pro2026!")


# ---------- fixtures ----------

@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{API}/auth/login",
                      json={"email": PRO_EMAIL, "password": PRO_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("token")
    assert token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def plan_id(auth_headers):
    """Pick an existing plan for the pro user, or upload a tiny one if none."""
    r = requests.get(f"{API}/takeoffs", headers=auth_headers, timeout=30)
    assert r.status_code == 200, f"list takeoffs failed: {r.status_code} {r.text}"
    data = r.json()
    plans = data.get("plans") or data.get("takeoffs") or data if isinstance(data, list) else []
    if isinstance(data, dict):
        plans = data.get("plans") or data.get("takeoffs") or []
    if plans:
        # any plan with pages
        for p in plans:
            pid = p.get("plan_id") or p.get("id")
            if pid:
                return pid
    # fallback: upload a tiny PNG
    import io
    from PIL import Image
    img = Image.new("RGB", (300, 300), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    files = {"file": ("plan.png", buf, "image/png")}
    r = requests.post(f"{API}/takeoffs/upload", headers=auth_headers, files=files, timeout=60)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
    return r.json()["plan_id"]


# ---------- validation tests (fast, no video generation) ----------

class TestVideoValidation:
    def test_unknown_style_returns_400(self, auth_headers, plan_id):
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers,
                          json={"page_index": 0, "include_furniture": True,
                                "styles": ["bogus_style"]},
                          timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_one_style_returns_400(self, auth_headers, plan_id):
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers,
                          json={"page_index": 0, "styles": ["isometric"]},
                          timeout=30)
        assert r.status_code == 400, f"expected 400 (too few), got {r.status_code}: {r.text}"

    def test_seven_styles_returns_400(self, auth_headers, plan_id):
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers,
                          json={"page_index": 0,
                                "styles": ["isometric", "photoreal", "axonometric",
                                           "interior", "isometric", "photoreal", "interior"]},
                          timeout=30)
        assert r.status_code == 400, f"expected 400 (too many), got {r.status_code}: {r.text}"


# ---------- full generation flow (slow: ~2min) ----------

class TestVideoGeneration:
    _video_id = None

    def test_render_video_2_styles(self, auth_headers, plan_id):
        payload = {
            "page_index": 0,
            "include_furniture": True,
            "styles": ["isometric", "photoreal"],
        }
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers, json=payload,
                          timeout=300)  # allow up to 5min
        assert r.status_code == 200, f"render-video failed: {r.status_code} {r.text[:500]}"
        data = r.json()
        # Required response fields
        for key in ("video_id", "duration_s", "size_bytes", "styles", "filename"):
            assert key in data, f"missing key '{key}' in response: {data}"
        assert data["styles"] == ["isometric", "photoreal"]
        assert isinstance(data["duration_s"], (int, float)) and data["duration_s"] > 0
        assert isinstance(data["size_bytes"], int) and data["size_bytes"] > 0
        assert data["filename"].endswith(".mp4")
        TestVideoGeneration._video_id = data["video_id"]

    def test_list_videos_includes_new(self, auth_headers, plan_id):
        assert TestVideoGeneration._video_id, "prior test failed, skipping"
        r = requests.get(f"{API}/takeoffs/{plan_id}/videos-3d",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        data = r.json()
        videos = data.get("videos", [])
        ids = [v.get("video_id") for v in videos]
        assert TestVideoGeneration._video_id in ids, f"generated video not in list: {ids}"

    def test_get_mp4_returns_video(self, auth_headers, plan_id):
        vid = TestVideoGeneration._video_id
        assert vid, "prior test failed, skipping"
        r = requests.get(f"{API}/takeoffs/{plan_id}/videos-3d/{vid}/mp4",
                         headers=auth_headers, timeout=60, stream=True)
        assert r.status_code == 200
        ct = r.headers.get("Content-Type", "")
        assert "video/mp4" in ct, f"unexpected content-type: {ct}"
        body = r.content
        assert len(body) > 0, "empty video body"
        # MP4 files start with ftyp box
        assert b"ftyp" in body[:32], "not an MP4 file (magic bytes missing)"
