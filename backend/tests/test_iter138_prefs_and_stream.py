"""Iteration 138 — Assistant BTP: preferences CRUD, isolation, SSE streaming, particulier estimate."""
import json
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")

PRO = ("pro@construpilot.fr", "Pro2026!")
CLIENT = ("client@construpilot.fr", "Client2026!")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:300]}"
    return r.json()


@pytest.fixture(scope="module")
def pro_h():
    return {"Authorization": f"Bearer {_login(*PRO)['token']}"}


@pytest.fixture(scope="module")
def client_h():
    return {"Authorization": f"Bearer {_login(*CLIENT)['token']}"}


# ------------- Préférences (pro) : CRUD complet -------------
class TestPreferencesPro:
    _created_ids: list[str] = []

    def test_create_user_scope(self, pro_h):
        cat = f"TEST_QA_{uuid.uuid4().hex[:6]}"
        r = requests.post(f"{BASE_URL}/api/assistant/preferences",
                          json={"category": cat, "value": "Règle QA v1", "scope": "user"}, headers=pro_h, timeout=30)
        assert r.status_code == 200, r.text
        p = r.json()
        assert p["pref_id"].startswith("pref_")
        assert p["category"] == cat and p["value"] == "Règle QA v1"
        assert p["scope"] == "user" and p["active"] is True and p["source"] == "manual"
        TestPreferencesPro._created_ids.append(p["pref_id"])

    def test_list_contains_created(self, pro_h):
        r = requests.get(f"{BASE_URL}/api/assistant/preferences", headers=pro_h, timeout=30)
        assert r.status_code == 200
        ids = {p["pref_id"] for p in r.json()}
        assert TestPreferencesPro._created_ids[0] in ids

    def test_patch_deactivate(self, pro_h):
        pid = TestPreferencesPro._created_ids[0]
        r = requests.patch(f"{BASE_URL}/api/assistant/preferences/{pid}", json={"active": False},
                           headers=pro_h, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["active"] is False

    def test_patch_update_value(self, pro_h):
        pid = TestPreferencesPro._created_ids[0]
        r = requests.patch(f"{BASE_URL}/api/assistant/preferences/{pid}",
                           json={"value": "Règle QA v2"}, headers=pro_h, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["value"] == "Règle QA v2"
        # verify persisted
        lst = requests.get(f"{BASE_URL}/api/assistant/preferences", headers=pro_h, timeout=30).json()
        matched = next(p for p in lst if p["pref_id"] == pid)
        assert matched["value"] == "Règle QA v2"

    def test_export_prefs(self, pro_h):
        r = requests.get(f"{BASE_URL}/api/assistant/preferences/export", headers=pro_h, timeout=30)
        assert r.status_code == 200
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        assert "application/json" in r.headers.get("content-type", "")
        j = r.json()
        assert "preferences" in j and isinstance(j["preferences"], list)
        assert any(p["pref_id"] == TestPreferencesPro._created_ids[0] for p in j["preferences"])

    def test_pro_role_user_cannot_company_scope(self, pro_h):
        # pro user role (not owner/admin/manager) → 403 on scope=company
        r = requests.post(f"{BASE_URL}/api/assistant/preferences",
                          json={"category": "TEST_QA_company", "value": "x", "scope": "company"},
                          headers=pro_h, timeout=30)
        assert r.status_code == 403, r.text
        assert "administrateur" in r.text.lower() or "réservée" in r.text.lower()

    def test_delete_unknown(self, pro_h):
        r = requests.delete(f"{BASE_URL}/api/assistant/preferences/pref_notfound_xyz",
                            headers=pro_h, timeout=30)
        assert r.status_code == 404

    def test_delete_created(self, pro_h):
        pid = TestPreferencesPro._created_ids[0]
        r = requests.delete(f"{BASE_URL}/api/assistant/preferences/{pid}", headers=pro_h, timeout=30)
        assert r.status_code == 200
        assert r.json()["deleted"] == 1
        # verify gone
        lst = requests.get(f"{BASE_URL}/api/assistant/preferences", headers=pro_h, timeout=30).json()
        assert all(p["pref_id"] != pid for p in lst)


# ------------- Isolation particulier -------------
class TestPreferencesIsolation:
    def test_individual_scope_company_forbidden(self, client_h):
        r = requests.post(f"{BASE_URL}/api/assistant/preferences",
                          json={"category": "TEST_QA_client", "value": "x", "scope": "company"},
                          headers=client_h, timeout=30)
        assert r.status_code == 403
        assert "particulier" in r.text.lower() or "indisponible" in r.text.lower()

    def test_individual_cannot_touch_pro_pref(self, pro_h, client_h):
        # pro creates a pref
        r = requests.post(f"{BASE_URL}/api/assistant/preferences",
                          json={"category": "TEST_QA_iso", "value": "v", "scope": "user"},
                          headers=pro_h, timeout=30)
        assert r.status_code == 200
        pid = r.json()["pref_id"]
        try:
            # client PATCH → 404
            p = requests.patch(f"{BASE_URL}/api/assistant/preferences/{pid}", json={"value": "hack"},
                               headers=client_h, timeout=30)
            assert p.status_code == 404, p.text
            # client DELETE → 404
            d = requests.delete(f"{BASE_URL}/api/assistant/preferences/{pid}", headers=client_h, timeout=30)
            assert d.status_code == 404, d.text
        finally:
            requests.delete(f"{BASE_URL}/api/assistant/preferences/{pid}", headers=pro_h, timeout=30)


# ------------- SSE streaming (pro) -------------
class TestStreamingPro:
    def test_stream_delta_then_done(self, pro_h):
        conv = requests.post(f"{BASE_URL}/api/assistant/conversations", json={}, headers=pro_h, timeout=30).json()
        cid = conv["conversation_id"]
        with requests.post(f"{BASE_URL}/api/assistant/message/stream",
                           json={"conversation_id": cid, "text": "Bonjour, présente-toi en une phrase.",
                                 "effort": "low"},
                           headers={**pro_h, "Accept": "text/event-stream"}, stream=True, timeout=120) as r:
            assert r.status_code == 200, r.text
            assert "text/event-stream" in r.headers.get("content-type", "")
            events = []
            for raw in r.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                ev = json.loads(raw[5:].strip())
                events.append(ev)
                if ev.get("type") in ("done", "error"):
                    break
        types = [e["type"] for e in events]
        assert "delta" in types, f"no delta events: {types}"
        assert types[-1] == "done", f"last event not done: {types}"
        final = events[-1]["message"]
        assert final["role"] == "assistant"
        assert final["content"] and len(final["content"]) > 5

        # Verify persistence
        conv_full = requests.get(f"{BASE_URL}/api/assistant/conversations/{cid}",
                                 headers=pro_h, timeout=30).json()
        roles = [m["role"] for m in conv_full["messages"]]
        assert "user" in roles and "assistant" in roles


# ------------- attachments errors -------------
class TestAttachmentsErrors:
    def test_unknown_plan_403(self, pro_h):
        conv = requests.post(f"{BASE_URL}/api/assistant/conversations", json={}, headers=pro_h, timeout=30).json()
        cid = conv["conversation_id"]
        r = requests.post(f"{BASE_URL}/api/assistant/message/stream",
                          json={"conversation_id": cid, "text": "Analyse ce plan",
                                "plan_ids": ["plan_inexistant"], "attachments": ["plan_inexistant"],
                                "effort": "low"},
                          headers=pro_h, timeout=60)
        assert r.status_code == 403, r.text
        assert "inaccessible" in r.text.lower() or "document" in r.text.lower()

    def test_unknown_conversation_404(self, pro_h):
        r = requests.post(f"{BASE_URL}/api/assistant/message/stream",
                          json={"conversation_id": "conv_nope_xxx", "text": "hi", "effort": "low"},
                          headers=pro_h, timeout=30)
        assert r.status_code == 404, r.text


# ------------- Particulier: estimate_budget_range (one call to keep costs low) -------------
class TestIndividualEstimate:
    def test_estimate_range(self, client_h):
        conv = requests.post(f"{BASE_URL}/api/assistant/conversations", json={}, headers=client_h, timeout=30).json()
        cid = conv["conversation_id"]
        r = requests.post(f"{BASE_URL}/api/assistant/message",
                          json={"conversation_id": cid,
                                "text": "Combien coûte environ la rénovation complète d'une salle de bain de 6 m² en Île-de-France ? Donne une fourchette.",
                                "effort": "low"},
                          headers=client_h, timeout=150)
        assert r.status_code == 200, r.text[:500]
        msg = r.json()
        assert msg["role"] == "assistant"
        assert msg.get("account_type") == "individual"
        acts = msg.get("actions") or []
        est = next((a for a in acts if a["tool"] == "estimate_budget_range"), None)
        assert est is not None, f"no estimate_budget_range in actions: {[a['tool'] for a in acts]}"
        assert est["result"].get("ok") is True, est["result"]
        e = est["result"]["estimate"]
        low, high = float(e["low_estimate"]), float(e["high_estimate"])
        assert low < high, (low, high)
        assert (high - low) / low >= 0.30, (low, high)
        assert e.get("mandatory_notice") and isinstance(e["mandatory_notice"], str)
