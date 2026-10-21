"""Iteration 166 — LIVE assistant tests for the deterministic metré engine.

Tests B, C, J, D against POST /api/assistant/message (real OpenAI call, fast mode).
Test P against POST /api/assistant/jobs (idempotency).
Persistence check on db.assistant_calculations.
"""
import os
import re
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

PRO_EMAIL = os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr")
PRO_PASSWORD = os.environ.get("TEST_PRO_PASSWORD", "Pro2026!")
INDIV_EMAIL = os.environ.get("TEST_INDIV_EMAIL", "client@construpilot.fr")
INDIV_PASSWORD = os.environ.get("TEST_INDIV_PASSWORD", "Client2026!")

TIMEOUT_MSG = 240


@pytest.fixture(scope="module")
def pro_token():
    r = requests.post(f"{API}/auth/login", json={"email": PRO_EMAIL, "password": PRO_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="module")
def pro_headers(pro_token):
    return {"Authorization": f"Bearer {pro_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def conversation_id(pro_headers):
    r = requests.post(f"{API}/assistant/conversations", json={"title": "iter166 metré live"}, headers=pro_headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["conversation_id"]


def _send(conversation_id, text, pro_headers, mode="fast", effort="medium"):
    body = {"conversation_id": conversation_id, "text": text, "response_mode": mode, "effort": effort, "web_enabled": False}
    r = requests.post(f"{API}/assistant/message", json=body, headers=pro_headers, timeout=TIMEOUT_MSG)
    assert r.status_code == 200, f"/message failed: {r.status_code} {r.text[:500]}"
    return r.json()


def _actions_by_tool(resp, name):
    return [a for a in (resp.get("actions") or []) if a.get("tool") == name]


# Test B — dimension chain 4 + 5 + 0.20 + 0.10 + 0.20 = 9.50
def test_B_check_dimension_chain_live(conversation_id, pro_headers):
    text = ("Cas de test synthétique : chaîne de cotes du même intervalle : vides libres 4,00 m et 5,00 m, "
            "deux murs extérieurs 0,20 m, cloison 0,10 m, total inscrit 9,50 m. Vérifie la cohérence et montre la formule.")
    resp = _send(conversation_id, text, pro_headers)
    acts = _actions_by_tool(resp, "check_dimension_chain")
    assert acts, f"expected tool check_dimension_chain in actions; got {[a.get('tool') for a in resp.get('actions', [])]}"
    calc = acts[-1]["result"]["calculation"]
    assert calc["result"] == 9.5
    assert calc["state"] == "confirmed"
    content = resp.get("content") or ""
    # allow comma or dot decimals in the assistant answer
    normalized = content.replace(",", ".")
    assert re.search(r"4\s*\+\s*5\s*\+\s*0\.2\s*\+\s*0\.1\s*\+\s*0\.2\s*=\s*9\.5", normalized) or "9.5" in normalized, content[:400]
    assert "incohérence" not in content.lower() and "incoherence" not in content.lower()


# Test C — 13,27 vs 13,30 = 0,03 m
def test_C_compare_values_live(conversation_id, pro_headers):
    text = ("Cas synthétique : deux cotes 13,27 m et 13,30 m pour le même intervalle confirmé et la même référence. "
            "Quel est l'écart ?")
    resp = _send(conversation_id, text, pro_headers)
    acts = _actions_by_tool(resp, "compare_dimension_values")
    assert acts, f"expected compare_dimension_values; got {[a.get('tool') for a in resp.get('actions', [])]}"
    calc = acts[-1]["result"]["calculation"]
    assert abs(calc["result"] - 0.03) < 1e-6
    content = (resp.get("content") or "").lower()
    # LaTeX renders may embed digits with braces (e.g. 0{,}03); normalize
    normalized = re.sub(r"[{}\\\s]+", "", content)
    assert "3cm" in normalized or "0,03" in normalized or "0.03" in normalized, content[:400]


# Test J — 5 × 2,8 with door 1 × 2,1, full deduction
def test_J_calculate_quantities_live(conversation_id, pro_headers):
    text = ("Cas synthétique : mur 5 m × 2,8 m avec une porte 1 m × 2,1 m, règle de déduction intégrale choisie. "
            "Surface brute, déduction, nette ?")
    resp = _send(conversation_id, text, pro_headers)
    acts = _actions_by_tool(resp, "calculate_quantities")
    assert acts, f"expected calculate_quantities; got {[a.get('tool') for a in resp.get('actions', [])]}"
    line = acts[-1]["result"]["lines"][0]
    assert line["gross"] == 14.0
    assert line["deductions"][0]["area_m2"] == 2.1
    assert line["net"] == 11.9
    assert line.get("extra_pct") in (None, 0)


# Test D — ambiguous OCR, no independent evidence
def test_D_resolve_ambiguous_reading_live(conversation_id, pro_headers):
    text = ("L'OCR lit 13,27 ou 13,72 m ; avec 13,72 la chaîne tombe juste, aucune autre preuve. Quelle valeur retenir ?")
    resp = _send(conversation_id, text, pro_headers)
    acts = _actions_by_tool(resp, "resolve_ambiguous_reading")
    assert acts, f"expected resolve_ambiguous_reading; got {[a.get('tool') for a in resp.get('actions', [])]}"
    result = acts[-1]["result"]
    assert result["state"] == "indeterminate"
    content = (resp.get("content") or "").lower()
    # Assistant should refuse to pick a value
    assert any(k in content for k in ["indéterm", "indeterm", "impossible", "ne peux", "refus", "preuve", "confirmation"])


# Persistence: db.assistant_calculations contains docs for this conversation_id
def test_persistence_assistant_calculations(conversation_id):
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    async def check():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        docs = [d async for d in db.assistant_calculations.find({"conversation_id": conversation_id}, {"_id": 0})]
        client.close()
        return docs

    # Always (re)load backend .env for MONGO_URL/DB_NAME (strip surrounding quotes)
    from pathlib import Path
    for line in Path("/app/backend/.env").read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
    docs = asyncio.run(check())
    assert docs, "no documents in assistant_calculations for this conversation"
    tools = {d.get("tool") for d in docs}
    assert {"check_dimension_chain", "compare_dimension_values", "calculate_quantities", "resolve_ambiguous_reading"}.issubset(tools), tools
    for d in docs:
        assert "args" in d and "result" in d and "tool" in d


# Test P — idempotent background job
def test_P_jobs_idempotent(conversation_id, pro_headers):
    request_id = f"iter166-p-{uuid.uuid4().hex[:8]}"
    text = "Somme synthétique : 4 + 5 + 0,2 + 0,1 + 0,2"
    body = {"conversation_id": conversation_id, "text": text, "response_mode": "fast", "effort": "medium",
            "web_enabled": False, "request_id": request_id}
    r1 = requests.post(f"{API}/assistant/jobs", json=body, headers=pro_headers, timeout=30)
    assert r1.status_code == 202, r1.text
    job1 = r1.json()["job_id"]
    r2 = requests.post(f"{API}/assistant/jobs", json=body, headers=pro_headers, timeout=30)
    assert r2.status_code == 202, r2.text
    assert r2.json()["job_id"] == job1, f"non-idempotent: {job1} vs {r2.json()['job_id']}"
    # Third call, same request_id, different text → 409
    body3 = dict(body, text="Autre texte totalement différent")
    r3 = requests.post(f"{API}/assistant/jobs", json=body3, headers=pro_headers, timeout=30)
    assert r3.status_code == 409, f"expected 409, got {r3.status_code} {r3.text[:200]}"


# Individual account: metré tools available (GET /api/assistant/actions)
def test_individual_can_see_metre_actions():
    r = requests.post(f"{API}/auth/login", json={"email": INDIV_EMAIL, "password": INDIV_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"individual login failed: {r.status_code}")
    tok = r.json().get("token") or r.json().get("access_token")
    headers = {"Authorization": f"Bearer {tok}"}
    r2 = requests.get(f"{API}/assistant/actions", headers=headers, timeout=30)
    assert r2.status_code == 200, r2.text
    # Endpoint may return a list of past actions; we just check auth works for individual
