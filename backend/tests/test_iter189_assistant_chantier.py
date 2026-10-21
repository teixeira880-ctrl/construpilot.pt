"""Iter 189 — Assistant contextuel chantier : conversation rattachée, dossier injecté, devis rattaché au dossier et au client."""
import os
import uuid

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
def collegue():
    return _login("collegue@construpilot.fr", "Collegue2026!")


@pytest.fixture(scope="module")
def dossier(pro):
    c = pro.post(f"{BASE_URL}/api/clients", json={"first_name": "Amélie", "last_name": "Iter189", "email": f"iter189-{uuid.uuid4().hex[:6]}@test.fr", "city": "Lyon", "postal_code": "69003"}).json()
    ch = pro.post(f"{BASE_URL}/api/chantiers", json={"name": "Iter189 Loft Lyon", "client_id": c["client_id"], "notes": "Accès par la cour, 3e étage sans ascenseur"}).json()
    q = pro.post(f"{BASE_URL}/api/documents", json={"doc_type": "quote", "title": "Devis démolition cloisons", "client_id": c["client_id"], "chantier_id": ch["chantier_id"],
                                                     "lines": [{"designation": "Démolition cloison", "qty": 12, "unit": "m²", "unit_price_ht": 45, "vat_rate": 10}]}).json()
    yield {"client": c, "chantier": ch, "quote": q}
    for d in pro.get(f"{BASE_URL}/api/chantiers/{ch['chantier_id']}").json().get("documents", []):
        pro.delete(f"{BASE_URL}/api/documents/{d['doc_id']}")
    pro.delete(f"{BASE_URL}/api/chantiers/{ch['chantier_id']}")
    pro.delete(f"{BASE_URL}/api/clients/{c['client_id']}")


class TestAssistantChantier:
    def test_conversation_linked_and_titled(self, pro, dossier):
        r = pro.post(f"{BASE_URL}/api/assistant/conversations", json={"chantier_id": dossier["chantier"]["chantier_id"]})
        assert r.status_code == 200, r.text
        conv = r.json()
        assert conv["chantier_id"] == dossier["chantier"]["chantier_id"]
        assert conv["title"] == "Chantier Iter189 Loft Lyon"
        listed = pro.get(f"{BASE_URL}/api/assistant/conversations").json()
        assert any(c["conversation_id"] == conv["conversation_id"] and c.get("chantier_id") == conv["chantier_id"] for c in listed)
        pro.delete(f"{BASE_URL}/api/assistant/conversations/{conv['conversation_id']}")

    def test_foreign_chantier_rejected(self, collegue, dossier):
        r = collegue.post(f"{BASE_URL}/api/assistant/conversations", json={"chantier_id": dossier["chantier"]["chantier_id"]})
        assert r.status_code == 404

    def test_assistant_summary_contains_known_facts(self, dossier):
        from routes.chantiers import assistant_summary
        d = {**dossier["chantier"], "client": dossier["client"], "documents": [dossier["quote"]], "plans": [], "plans_pro": [], "diagnostics": [], "reports": [],
             "reserves": [{"status": "ouverte", "lot": "Plomberie", "description": "Fuite"}], "kpis": {"quotes": 1}}
        s = assistant_summary(d)
        assert s["client"]["nom"] == "Amélie Iter189" and s["client"]["client_id"] == dossier["client"]["client_id"]
        assert s["devis_factures"][0]["total_ttc"] == dossier["quote"]["totals"]["ttc"]
        assert s["notes"].startswith("Accès par la cour")
        assert len(s["reserves_ouvertes"]) == 1

    def test_message_uses_dossier_and_quote_attached(self, pro, dossier):
        """Vrai tour LLM : la réponse cite le client / devis du dossier ; un devis créé est rattaché au chantier et au client CRM."""
        conv = pro.post(f"{BASE_URL}/api/assistant/conversations", json={"chantier_id": dossier["chantier"]["chantier_id"]}).json()
        req = uuid.uuid4().hex
        body = {"conversation_id": conv["conversation_id"], "request_id": req, "response_mode": "fast", "web_enabled": False,
                "text": "Quel est le nom du client de ce chantier et le montant TTC du devis déjà existant ? Réponds en une phrase, sans outil."}
        r = pro.post(f"{BASE_URL}/api/assistant/jobs", json=body, timeout=60)
        assert r.status_code in (200, 202), r.text
        import time
        answer = ""
        for _ in range(60):
            time.sleep(3)
            msgs = pro.get(f"{BASE_URL}/api/assistant/conversations/{conv['conversation_id']}").json().get("messages", [])
            done = [m for m in msgs if m.get("role") == "assistant" and m.get("request_id") == req and m.get("content")]
            job = pro.get(f"{BASE_URL}/api/assistant/jobs/{r.json()['job_id']}").json() if r.json().get("job_id") else {}
            if done and job.get("status") not in ("queued", "running"):
                answer = done[-1]["content"]
                break
        assert answer, "pas de réponse de l'assistant"
        assert "Iter189" in answer or "Amélie" in answer, answer
        pro.delete(f"{BASE_URL}/api/assistant/conversations/{conv['conversation_id']}")
