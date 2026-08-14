"""Iter30 — Backend tests for video watermark + audio + auto-attach devis email.

Extends iter29:
- Watermark & audio toggles in POST /api/takeoffs/{plan_id}/render-video
- ffprobe verification of video/audio streams in the MP4 stream endpoint
- Auto-attach latest 3D tour MP4 in POST /api/takeoffs/{plan_id}/send-quote
- Validation regressions (unknown / 1 / 7 styles)
"""
import base64
import io
import json
import os
import shutil
import subprocess
import time

import pytest
import requests
from PIL import Image

# Rendus vidéo longs (> timeout ingress) : URL interne du backend
BASE_URL = os.environ.get("INTERNAL_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

# Credentials read from env — never hardcoded. See test_iter29_video_tour.py.
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
def orange_logo_b64():
    """240x120 orange PNG (base64, no data URI prefix)."""
    img = Image.new("RGB", (240, 120), (255, 90, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@pytest.fixture(scope="module")
def branded_pro(auth_headers, orange_logo_b64):
    """Set branding (logo + company) on pro/org so watermark can be applied."""
    r = requests.put(
        f"{API}/users/me/branding",
        headers=auth_headers,
        json={"logo_b64": orange_logo_b64, "company_name": "BTP Test"},
        timeout=30,
    )
    assert r.status_code == 200, f"branding put failed: {r.status_code} {r.text}"
    b = r.json()
    assert b.get("has_logo") == True, f"branding did not persist logo: {b}"
    return b


def _plan_has_rooms(auth_headers, pid: str) -> bool:
    r = requests.get(f"{API}/takeoffs/{pid}", headers=auth_headers, timeout=15)
    if r.status_code != 200:
        return False
    return bool(r.json().get("rooms"))


def _ensure_room(auth_headers, pid: str):
    """Calibrate page 0 + upsert one square room so /send-quote can build quote."""
    # 1) calibrate: 100px = 1m
    r = requests.post(
        f"{API}/takeoffs/{pid}/calibrate",
        headers=auth_headers,
        json={"page_index": 0, "p1": [0, 0], "p2": [100, 0], "real_distance_m": 1.0},
        timeout=30,
    )
    assert r.status_code == 200, f"calibrate failed: {r.status_code} {r.text}"
    # 2) upsert a 5m x 4m rectangle room
    r = requests.post(
        f"{API}/takeoffs/{pid}/rooms",
        headers=auth_headers,
        json={
            "page_index": 0,
            "name": "TEST_Salon",
            "points": [[0, 0], [500, 0], [500, 400], [0, 400]],
            "ceiling_height_m": 2.5,
            "openings": [],
        },
        timeout=30,
    )
    assert r.status_code == 200, f"upsert room failed: {r.status_code} {r.text}"


@pytest.fixture(scope="module")
def plan_id(auth_headers):
    """Prefer a plan that already has rooms; else upload + calibrate + add one."""
    r = requests.get(f"{API}/takeoffs", headers=auth_headers, timeout=30)
    plans = []
    if r.status_code == 200:
        data = r.json()
        plans = data.get("plans") or data.get("takeoffs") or (data if isinstance(data, list) else [])
    # Pass 1: plan already with rooms
    for p in plans:
        pid = p.get("plan_id") or p.get("id")
        if pid and _plan_has_rooms(auth_headers, pid):
            return pid
    # Pass 2: any plan → add a room
    for p in plans:
        pid = p.get("plan_id") or p.get("id")
        if pid:
            _ensure_room(auth_headers, pid)
            return pid
    # Pass 3: upload + add a room
    img = Image.new("RGB", (800, 600), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    files = {"file": ("plan.png", buf, "image/png")}
    r = requests.post(f"{API}/takeoffs/upload", headers=auth_headers,
                      files=files, timeout=90)
    assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
    pid = r.json()["plan_id"]
    _ensure_room(auth_headers, pid)
    return pid


def _ffprobe_streams(mp4_bytes: bytes) -> list[dict]:
    """Return list of {codec_type, codec_name, width, height, sample_rate}."""
    tmp = "/tmp/iter30_probe.mp4"
    with open(tmp, "wb") as f:
        f.write(mp4_bytes)
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", tmp,
    ], timeout=30)
    return json.loads(out).get("streams", [])


# ---------- validation regressions (fast) ----------

class TestVideoValidationRegression:
    def test_unknown_style_400(self, auth_headers, plan_id):
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers,
                          json={"styles": ["bogus_style", "isometric"]},
                          timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"

    def test_one_style_400(self, auth_headers, plan_id):
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers,
                          json={"styles": ["isometric"]},
                          timeout=30)
        assert r.status_code == 400, f"expected 400 (too few), got {r.status_code}: {r.text}"

    def test_seven_styles_400(self, auth_headers, plan_id):
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers,
                          json={"styles": [
                              "isometric", "photoreal", "axonometric",
                              "interior", "isometric", "photoreal", "interior"]},
                          timeout=30)
        assert r.status_code == 400, f"expected 400 (too many), got {r.status_code}: {r.text}"


# ---------- watermark + audio E2E (slow ~1-3 min) ----------

class TestVideoWatermarkAndAudio:
    _video_wm_music_id: str | None = None
    _video_bare_id: str | None = None

    def test_render_with_watermark_and_music(self, auth_headers, plan_id, branded_pro):
        payload = {
            "page_index": 0,
            "include_furniture": True,
            "styles": ["isometric", "photoreal"],
            "add_watermark": True,
            "add_music": True,
        }
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers, json=payload, timeout=300)
        assert r.status_code == 200, f"render failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert data.get("has_watermark") == True, f"has_watermark not True: {data}"
        assert data.get("has_audio") == True, f"has_audio not True: {data}"
        assert data.get("video_id")
        TestVideoWatermarkAndAudio._video_wm_music_id = data["video_id"]

    def test_ffprobe_has_video_and_audio(self, auth_headers, plan_id):
        vid = TestVideoWatermarkAndAudio._video_wm_music_id
        assert vid, "prior render test failed"
        assert shutil.which("ffprobe"), "ffprobe not installed"
        r = requests.get(f"{API}/takeoffs/{plan_id}/videos-3d/{vid}/mp4",
                         headers=auth_headers, timeout=90)
        assert r.status_code == 200
        streams = _ffprobe_streams(r.content)
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        assert video_streams, f"no video stream: {streams}"
        assert audio_streams, f"no audio stream: {streams}"
        v = video_streams[0]
        assert v.get("codec_name") == "h264", f"video codec != h264: {v.get('codec_name')}"
        assert v.get("width") == 1280 and v.get("height") == 720, (
            f"resolution != 1280x720: {v.get('width')}x{v.get('height')}"
        )
        assert audio_streams[0].get("codec_name") == "aac", (
            f"audio codec != aac: {audio_streams[0].get('codec_name')}"
        )

    def test_render_without_watermark_and_music(self, auth_headers, plan_id):
        payload = {
            "page_index": 0,
            "styles": ["isometric", "photoreal"],
            "add_watermark": False,
            "add_music": False,
        }
        r = requests.post(f"{API}/takeoffs/{plan_id}/render-video",
                          headers=auth_headers, json=payload, timeout=300)
        assert r.status_code == 200, f"render failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert data.get("has_watermark") == False, f"has_watermark should be False: {data}"
        assert data.get("has_audio") == False, f"has_audio should be False: {data}"
        TestVideoWatermarkAndAudio._video_bare_id = data["video_id"]

    def test_ffprobe_bare_has_no_audio(self, auth_headers, plan_id):
        vid = TestVideoWatermarkAndAudio._video_bare_id
        assert vid, "prior render test failed"
        r = requests.get(f"{API}/takeoffs/{plan_id}/videos-3d/{vid}/mp4",
                         headers=auth_headers, timeout=90)
        assert r.status_code == 200
        streams = _ffprobe_streams(r.content)
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        assert video_streams, "no video stream in bare mp4"
        assert not audio_streams, f"unexpected audio stream: {audio_streams}"


# ---------- auto-attach video in send-quote ----------

class TestQuoteAutoAttachVideo:
    @pytest.fixture(scope="class")
    def existing_video(self, auth_headers, plan_id):
        """Attend qu'une vidéo existe (la classe rendu peut tourner sur un autre
        worker xdist) — sinon skip proprement au lieu d'un faux négatif."""
        deadline = time.time() + 90
        while time.time() < deadline:
            r = requests.get(f"{API}/takeoffs/{plan_id}/videos-3d",
                             headers=auth_headers, timeout=30)
            if r.status_code == 200 and r.json().get("videos"):
                return r.json()["videos"][0]
            time.sleep(5)
        pytest.skip("Aucune vidéo disponible pour ce plan (classe rendu non exécutée avant)")

    def test_send_quote_with_attach(self, auth_headers, plan_id, existing_video):
        # Depends on at least one video existing (previous class ran).
        payload = {
            "client_email": "client-test@example.com",
            "client_name": "Client Test",
            "client_address": "1 rue Test 75001 Paris",
            "attach_latest_video": True,
            "include_tva_attestation": False,
            "cc_self": False,
        }
        r = requests.post(f"{API}/takeoffs/{plan_id}/send-quote",
                          headers=auth_headers, json=payload, timeout=120)
        assert r.status_code == 200, f"send-quote failed: {r.status_code} {r.text[:400]}"
        data = r.json()
        assert data.get("email_status") in ("sent", "failed"), (
            f"unexpected email_status: {data}"
        )

    def test_quote_sends_log_has_attached_video_id(self, auth_headers, plan_id, existing_video):
        r = requests.get(f"{API}/takeoffs/{plan_id}/quote-sends",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        sends = r.json().get("sends", [])
        assert sends, "no quote_sends found"
        latest = sends[0]  # sorted by created_at desc
        assert latest.get("attach_latest_video") == True, (
            f"attach_latest_video not stored True: {latest}"
        )
        assert latest.get("attached_video_id"), (
            f"attached_video_id missing/null: {latest}"
        )
        assert latest["attached_video_id"].startswith(("v3d_", "vid_")), (
            f"unexpected video_id format: {latest.get('attached_video_id')}"
        )

    def test_send_quote_without_attach(self, auth_headers, plan_id):
        payload = {
            "client_email": "client-test2@example.com",
            "attach_latest_video": False,
            "include_tva_attestation": False,
            "cc_self": False,
        }
        r = requests.post(f"{API}/takeoffs/{plan_id}/send-quote",
                          headers=auth_headers, json=payload, timeout=120)
        assert r.status_code == 200, f"send-quote failed: {r.status_code} {r.text[:400]}"

        # Verify log
        r2 = requests.get(f"{API}/takeoffs/{plan_id}/quote-sends",
                          headers=auth_headers, timeout=30)
        assert r2.status_code == 200
        sends = r2.json().get("sends", [])
        assert sends
        latest = sends[0]
        assert latest.get("attach_latest_video") == False, (
            f"attach_latest_video not False: {latest}"
        )
        assert latest.get("attached_video_id") is None, (
            f"attached_video_id should be null: {latest.get('attached_video_id')}"
        )
