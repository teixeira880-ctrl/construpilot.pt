"""Phase 4 P3 — Assistant IA via public URL (POST /api/assistant/chat).

Marked `slow` because it calls the real Anthropic API via EMERGENT_LLM_KEY.
Uses the same BASE_URL the mobile app uses.
"""
import os
import uuid

import pytest
import requests

pytestmark = pytest.mark.slow

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://escalier-pro.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")


@pytest.fixture
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestAssistantChatPublic:
    def test_simple_greeting_returns_reply(self, api):
        r = api.post(f"{BASE_URL}/api/assistant/chat", json={"message": "bonjour"}, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j.get("reply_text"), str) and len(j["reply_text"].strip()) > 0
        assert j.get("conversation_id")
        assert "claude-sonnet-4-5-20250929" in (j.get("metadata", {}).get("model") or "")

    def test_calculatory_request_triggers_engine(self, api):
        payload = {
            "message": (
                "Hauteur 2.85m, trémie 2.60x1.00, recul 3.20m, largeur dispo 1.5m, "
                "largeur souhaitée 900mm. Quel escalier me proposes-tu ?"
            )
        }
        r = api.post(f"{BASE_URL}/api/assistant/chat", json=payload, timeout=90)
        assert r.status_code == 200, r.text
        j = r.json()
        tools = [c["tool"] for c in j.get("referenced_engine_calls", [])]
        assert any(t in ("optimize_stair", "calculate_straight") for t in tools), \
            f"Aucun outil moteur appelé: {tools} | reply={j.get('reply_text')[:200]}"
        if "optimize_stair" in tools:
            assert len(j.get("computed_solutions", [])) >= 1

    def test_multi_turn_history_preserved(self, api):
        conv_id = str(uuid.uuid4())
        r1 = api.post(f"{BASE_URL}/api/assistant/chat", json={
            "message": "Je m'appelle Julien.", "conversation_id": conv_id
        }, timeout=60)
        assert r1.status_code == 200
        r2 = api.post(f"{BASE_URL}/api/assistant/chat", json={
            "message": "Comment je m'appelle ?", "conversation_id": conv_id
        }, timeout=60)
        assert r2.status_code == 200
        text = r2.json()["reply_text"].lower()
        assert "julien" in text, f"Contexte perdu: {r2.json()['reply_text']}"

    def test_conversation_history_endpoint(self, api):
        conv_id = str(uuid.uuid4())
        api.post(f"{BASE_URL}/api/assistant/chat", json={
            "message": "TEST_PING", "conversation_id": conv_id
        }, timeout=60)
        r = api.get(f"{BASE_URL}/api/assistant/conversations/{conv_id}", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["conversation_id"] == conv_id
        msgs = j.get("messages", [])
        roles = [m["role"] for m in msgs]
        assert "user" in roles and "assistant" in roles
        assert any(m["content"] == "TEST_PING" for m in msgs)


class TestNoRegression:
    def test_calculate_straight_ok(self, api):
        r = api.post(f"{BASE_URL}/api/calculate/straight", json={
            "floor_height_mm": 2800,
            "available_length_mm": 4500,
            "available_width_mm": 1500,
            "stair_width_mm": 900,
        }, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["num_steps"] > 0 and j["riser_height_mm"] > 0

    def test_optimize_ok(self, api):
        r = api.post(f"{BASE_URL}/api/optimize", json={
            "floor_height_mm": 2800,
            "available_length_mm": 4500,
            "available_width_mm": 1500,
        }, timeout=15)
        assert r.status_code == 200
        assert len(r.json().get("solutions", [])) >= 1

    def test_dossier_generate_ok(self, api):
        stair_input = {
            "floor_height_mm": 2800, "available_length_mm": 4500, "available_width_mm": 1500,
            "stair_width_mm": 900, "slab_thickness_mm": 200,
        }
        calc = api.post(f"{BASE_URL}/api/calculate/straight", json=stair_input, timeout=15)
        assert calc.status_code == 200
        r = api.post(f"{BASE_URL}/api/dossier/generate", json={
            "project_name": "TEST_regression",
            "stair_input": stair_input,
            "stair_result": calc.json(),
        }, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
