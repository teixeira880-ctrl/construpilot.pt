"""Backend tests for the Assistant BTP (routes/assistant.py)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback: read frontend .env
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip().rstrip("/")

PRO = ("pro@construpilot.fr", "Pro2026!")
PRO_PT = ("pro.pt@construpilot.pt", "ProPT2026!")
PLAN_PRO = "plan_c7f324ea7fe0"
PLAN_OTHER = "plan_e628b6d7479b"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers():
    return {"Authorization": f"Bearer {_login(*PRO)}"}


@pytest.fixture(scope="module")
def pt_headers():
    try:
        return {"Authorization": f"Bearer {_login(*PRO_PT)}"}
    except AssertionError:
        pytest.skip("pro.pt user not available")


@pytest.fixture(scope="module")
def conv_id(pro_headers):
    r = requests.post(f"{BASE_URL}/api/assistant/conversations", json={}, headers=pro_headers, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["title"] == "Nouvelle conversation"
    assert j["conversation_id"].startswith("conv_")
    return j["conversation_id"]


# ---- Conversations CRUD + isolation
class TestConversations:
    def test_list_contains_created(self, pro_headers, conv_id):
        r = requests.get(f"{BASE_URL}/api/assistant/conversations", headers=pro_headers, timeout=30)
        assert r.status_code == 200
        ids = [c["conversation_id"] for c in r.json()]
        assert conv_id in ids

    def test_get_conv_empty_messages(self, pro_headers, conv_id):
        r = requests.get(f"{BASE_URL}/api/assistant/conversations/{conv_id}", headers=pro_headers, timeout=30)
        assert r.status_code == 200
        assert r.json()["messages"] == []

    def test_conv_isolation(self, pt_headers, conv_id):
        r = requests.get(f"{BASE_URL}/api/assistant/conversations/{conv_id}", headers=pt_headers, timeout=30)
        assert r.status_code == 404


# ---- Message with plan (get_plan_results / generate_branded_pdf)
class TestMessagePlanResults:
    def test_message_plan_results(self, pro_headers, conv_id):
        payload = {
            "conversation_id": conv_id,
            "text": "Explique-moi les résultats du contrôle des cotes de ce plan et donne-moi le lien du rapport PDF de l analyse OpenAI",
            "plan_ids": [PLAN_PRO],
        }
        r = requests.post(f"{BASE_URL}/api/assistant/message", json=payload, headers=pro_headers, timeout=180)
        assert r.status_code == 200, r.text[:400]
        j = r.json()
        assert j["content"], "empty assistant content"
        tools = {a["tool"] for a in j.get("actions", [])}
        assert tools & {"get_plan_results", "generate_branded_pdf"}, f"no tool used, got {tools}"
        # If generate_branded_pdf present, check download url
        for a in j["actions"]:
            if a["tool"] == "generate_branded_pdf" and a["result"].get("download"):
                dl = a["result"]["download"]
                assert dl.startswith(f"/takeoffs/{PLAN_PRO}/")
                pdf_r = requests.get(f"{BASE_URL}/api{dl}", headers=pro_headers, timeout=60)
                assert pdf_r.status_code == 200
                assert pdf_r.headers.get("content-type", "").startswith("application/pdf")
                break
        # verify messages persisted
        r2 = requests.get(f"{BASE_URL}/api/assistant/conversations/{conv_id}", headers=pro_headers, timeout=30)
        msgs = r2.json()["messages"]
        assert len(msgs) >= 2
        assert msgs[0]["role"] == "user"
        assert any(m["role"] == "assistant" and m.get("actions") for m in msgs)

    def test_message_forbidden_plan(self, pro_headers, conv_id):
        payload = {"conversation_id": conv_id, "text": "test", "plan_ids": [PLAN_OTHER]}
        r = requests.post(f"{BASE_URL}/api/assistant/message", json=payload, headers=pro_headers, timeout=60)
        assert r.status_code == 403
        assert "inaccessible" in r.text.lower()


# ---- Quote draft
class TestQuoteDraft:
    def test_create_quote_draft(self, pro_headers, conv_id):
        payload = {
            "conversation_id": conv_id,
            "text": "Prépare un brouillon de devis pour le client Test : peinture 40 m2 à 20 euros HT le m2, TVA 20 %.",
        }
        r = requests.post(f"{BASE_URL}/api/assistant/message", json=payload, headers=pro_headers, timeout=180)
        assert r.status_code == 200, r.text[:400]
        j = r.json()
        quote = next((a for a in j.get("actions", []) if a["tool"] == "create_quote_draft"), None)
        assert quote, f"no create_quote_draft in actions: {[a['tool'] for a in j.get('actions', [])]}"
        res = quote["result"]
        assert res.get("ok") is True
        assert res.get("preview") is True
        d = res["draft"]
        assert d["status"] == "draft"
        assert d["total_ht"] == 800
        assert d["total_ttc"] == 960


# ---- Preferences (save + list + delete)
class TestPreferences:
    def test_save_pref_and_list_delete(self, pro_headers, conv_id):
        payload = {
            "conversation_id": conv_id,
            "text": "Enregistre pour mon compte la préférence : comptes rendus toujours en 3 parties (faits, décisions, actions). Oui je confirme.",
        }
        r = requests.post(f"{BASE_URL}/api/assistant/message", json=payload, headers=pro_headers, timeout=180)
        assert r.status_code == 200, r.text[:400]
        j = r.json()
        pref_action = next((a for a in j.get("actions", []) if a["tool"] == "save_user_preference"), None)
        assert pref_action, f"no save_user_preference: {[a['tool'] for a in j.get('actions', [])]}"
        assert pref_action["result"].get("ok") is True
        assert pref_action["args"].get("scope") == "user"

        lst = requests.get(f"{BASE_URL}/api/assistant/preferences", headers=pro_headers, timeout=30)
        assert lst.status_code == 200
        prefs = lst.json()
        assert prefs, "no prefs returned"
        p0 = prefs[-1]
        for k in ("category", "value", "scope", "active", "validated_by"):
            assert k in p0, f"missing {k} in pref: {p0.keys()}"
        pref_id = pref_action["result"]["preference"]["pref_id"]

        dr = requests.delete(f"{BASE_URL}/api/assistant/preferences/{pref_id}", headers=pro_headers, timeout=30)
        assert dr.status_code == 200
        assert dr.json() == {"deleted": 1}


# ---- Usage & Actions & Transcribe
class TestUsageActions:
    def test_usage(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/assistant/usage", headers=pro_headers, timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert "rows" in j and "actions" in j
        assert any(row.get("kind") == "assistant_chat" and row.get("model") == "gpt-5.6-terra" for row in j["rows"]), j["rows"]

    def test_actions_log(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/assistant/actions", headers=pro_headers, timeout=30)
        assert r.status_code == 200
        acts = r.json()
        assert isinstance(acts, list) and len(acts) > 0
        a = acts[0]
        for k in ("tool", "args", "ok", "created_at"):
            assert k in a

    def test_transcribe_no_file(self, pro_headers):
        r = requests.post(f"{BASE_URL}/api/assistant/transcribe", headers=pro_headers, timeout=30)
        assert r.status_code == 422
