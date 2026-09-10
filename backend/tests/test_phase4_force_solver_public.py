"""Phase 4 P3 — Solveur forcé (`force_stair_solution`) — tests via public URL.

Vérifie que le SYSTEM_PROMPT + tool-use Claude Sonnet 4.5 déclenchent bien
l'outil forcé quand l'espace est trop contraint OU quand l'utilisateur demande
explicitement un type absent des solutions optimisées.

Marqués `slow` : appels API Anthropic réels via EMERGENT_LLM_KEY.
"""
import os
import uuid

import pytest
import requests

pytestmark = pytest.mark.slow

BASE_URL = (os.environ.get("EXPO_PUBLIC_BACKEND_URL") or "https://escalier-pro.preview.emergentagent.com").rstrip("/")


@pytest.fixture
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------------------------------------------------------------------
# LLM-behavior tests
# ---------------------------------------------------------------------------
class TestForceSolverLLMBehavior:
    def test_cave_technique_triggers_force_solver(self, api):
        """Cas cave technique : H=3m, recul 1.5m, trémie 1.5x0.8 → force_stair_solution attendu."""
        payload = {
            "message": (
                "Je veux un escalier DROIT obligatoire. Hauteur 3m, recul 1.5m, "
                "trémie 1.5x0.8m. Accès cave technique. Pas d'hélicoïdal ni de quart tournant."
            ),
            "conversation_id": str(uuid.uuid4()),
        }
        r = api.post(f"{BASE_URL}/api/assistant/chat", json=payload, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        tools = [c["tool"] for c in j.get("referenced_engine_calls", [])]
        assert "force_stair_solution" in tools, \
            f"Le solveur forcé n'a pas été appelé. Tools: {tools} | reply={j.get('reply_text')[:300]}"
        text = (j.get("reply_text") or "").lower()
        assert any(kw in text for kw in ("hors norme", "hors-norme", "non conform", "non-conform", "compromis", "non_conforming", "dtu")), \
            f"L'assistant ne mentionne pas 'hors normes / compromis': {j.get('reply_text')}"
        # Ne doit pas refuser catégoriquement
        for refusal in ("aucune solution", "impossible de construire"):
            assert refusal not in text, f"Refus catégorique détecté ({refusal}): {j.get('reply_text')}"

    def test_standard_case_uses_optimize_only(self, api):
        """H=2.80m, recul 4.5m, largeur 1.2m → optimize_stair suffit, PAS de force."""
        payload = {
            "message": "Hauteur 2.80m, recul 4.5m, largeur 1.2m. Propose-moi le meilleur escalier.",
            "conversation_id": str(uuid.uuid4()),
        }
        r = api.post(f"{BASE_URL}/api/assistant/chat", json=payload, timeout=120)
        assert r.status_code == 200, r.text
        j = r.json()
        tools = [c["tool"] for c in j.get("referenced_engine_calls", [])]
        assert "optimize_stair" in tools, f"optimize_stair non appelé: {tools}"
        # Le comportement normal doit rester préservé
        assert len(j.get("computed_solutions", [])) >= 1, \
            f"Aucune solution computée: {j.get('computed_solutions')}"

    def test_theoretical_question_no_tool_call(self, api):
        """'C'est quoi Blondel ?' → aucun tool call."""
        payload = {
            "message": "C'est quoi la formule de Blondel exactement ?",
            "conversation_id": str(uuid.uuid4()),
        }
        r = api.post(f"{BASE_URL}/api/assistant/chat", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("referenced_engine_calls") == [], \
            f"Un outil a été appelé pour une question théorique: {j.get('referenced_engine_calls')}"
        text = (j.get("reply_text") or "").lower()
        assert ("blondel" in text) or ("2h" in text) or ("2 h" in text)


# ---------------------------------------------------------------------------
# Regression: no impact on existing endpoints
# ---------------------------------------------------------------------------
class TestNoRegressionForce:
    def test_optimize_still_returns_solutions(self, api):
        r = api.post(f"{BASE_URL}/api/optimize", json={
            "floor_height_mm": 2800,
            "available_length_mm": 4500,
            "available_width_mm": 1500,
        }, timeout=15)
        assert r.status_code == 200
        assert len(r.json().get("solutions", [])) >= 1

    def test_calculate_straight_still_ok(self, api):
        r = api.post(f"{BASE_URL}/api/calculate/straight", json={
            "floor_height_mm": 2800,
            "available_length_mm": 4500,
            "available_width_mm": 1500,
            "stair_width_mm": 900,
        }, timeout=15)
        assert r.status_code == 200
        assert r.json()["num_steps"] > 0

    def test_dossier_generate_still_returns_pdf(self, api):
        stair_input = {
            "floor_height_mm": 2800, "available_length_mm": 4500, "available_width_mm": 1500,
            "stair_width_mm": 900, "slab_thickness_mm": 200,
        }
        calc = api.post(f"{BASE_URL}/api/calculate/straight", json=stair_input, timeout=15)
        assert calc.status_code == 200
        r = api.post(f"{BASE_URL}/api/dossier/generate", json={
            "project_name": "TEST_regression_force",
            "stair_input": stair_input,
            "stair_result": calc.json(),
        }, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
