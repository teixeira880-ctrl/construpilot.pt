"""Iter 191 — Voix managée Emergent (STT Whisper / TTS) + paliers Gemini dans Admin → IA."""
import os

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def pro():
    return _login("pro@construpilot.fr", "Pro2026!")


@pytest.fixture(scope="module")
def admin():
    return _login("admin@construpilot.fr", "Construpilot2026!")


class TestSpeech:
    def test_tts_then_stt_roundtrip(self, pro):
        r = pro.post(f"{BASE_URL}/api/speech/tts", json={"text": "Bonjour, la démolition est terminée."}, timeout=90)
        assert r.status_code == 200 and r.headers["content-type"].startswith("audio/mpeg") and len(r.content) > 5000
        t = pro.post(f"{BASE_URL}/api/speech/transcribe", files={"file": ("test.mp3", r.content, "audio/mpeg")}, timeout=90)
        assert t.status_code == 200, t.text
        assert "démolition" in t.json()["text"].lower() and t.json()["engine"] == "emergent-whisper"
        a = pro.post(f"{BASE_URL}/api/assistant/transcribe", files={"file": ("test.mp3", r.content, "audio/mpeg")}, timeout=90)
        assert a.status_code == 200 and "démolition" in a.json()["text"].lower()

    def test_validation_and_auth(self, pro):
        assert pro.post(f"{BASE_URL}/api/speech/tts", json={"text": ""}).status_code == 422
        assert pro.post(f"{BASE_URL}/api/speech/tts", json={"text": "x", "voice": "robot"}).status_code == 422
        assert pro.post(f"{BASE_URL}/api/speech/transcribe", files={"file": ("e.webm", b"", "audio/webm")}).status_code == 422
        assert requests.post(f"{BASE_URL}/api/speech/tts", json={"text": "x"}, timeout=30).status_code == 401
        assert requests.post(f"{BASE_URL}/api/speech/portal/tts", json={"text": "x"}, timeout=30).status_code == 401


class TestGeminiTiers:
    def test_options_include_gemini(self, admin):
        d = admin.get(f"{BASE_URL}/api/admin/ai-model").json()
        tiers = {o["tier"]: o for o in d["options"]}
        assert "gemini_pro" in tiers and "gemini_flash" in tiers
        assert tiers["gemini_pro"]["model"] == "gemini-3.1-pro-preview" if "model" in tiers["gemini_pro"] else True

    def test_switch_and_restore(self, admin):
        cur = admin.get(f"{BASE_URL}/api/admin/ai-model").json()["current"]
        r = admin.put(f"{BASE_URL}/api/admin/ai-model", json={"tier": "gemini_flash"})
        assert r.status_code == 200 and r.json()["current"] == "gemini_flash"
        admin.put(f"{BASE_URL}/api/admin/ai-model", json={"tier": cur})
        assert admin.get(f"{BASE_URL}/api/admin/ai-model").json()["current"] == cur
