"""Tests for iter 83: multilingual emails, AI cost counter, CRM multilingual.

Covers:
- PUT /api/auth/language (persistence + invalid normalization to 'fr')
- Register accepts optional lang
- GET/PUT /api/admin/ai-model with quality/speed/cost
- GET /api/admin/ai-usage shape + increment after real AI call
- GET /api/documents/{id}/pdf returns 200 application/pdf
"""
import os
import time
import uuid
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        env_path = "/app/frontend/.env"
        if os.path.exists(env_path):
            for line in open(env_path):
                if line.startswith("REACT_APP_BACKEND_URL"):
                    v = line.split("=", 1)[1].strip()
                    break
    return v.rstrip("/")

BASE_URL = _load_backend_url()
ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PASS = "Construpilot2026!"
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASS = "Pro2026!"


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    j = r.json()
    assert "token" in j, j
    return j["token"], j["user"]


@pytest.fixture(scope="module")
def admin_auth():
    tok, user = _login(ADMIN_EMAIL, ADMIN_PASS)
    return {"token": tok, "user": user, "headers": {"Authorization": f"Bearer {tok}"}}


@pytest.fixture(scope="module")
def pro_auth():
    tok, user = _login(PRO_EMAIL, PRO_PASS)
    return {"token": tok, "user": user, "headers": {"Authorization": f"Bearer {tok}"}}


# ---------- Language persistence ----------

class TestLanguage:
    def test_set_language_es_persists(self, pro_auth):
        r = requests.put(f"{BASE_URL}/api/auth/language", json={"lang": "es"}, headers=pro_auth["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["lang"] == "es"

        # Verify via /auth/me
        m = requests.get(f"{BASE_URL}/api/auth/me", headers=pro_auth["headers"])
        assert m.status_code == 200
        assert m.json().get("lang") == "es"

    def test_invalid_lang_normalizes_to_fr(self, pro_auth):
        r = requests.put(f"{BASE_URL}/api/auth/language", json={"lang": "zz"}, headers=pro_auth["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["lang"] == "fr"
        # cleanup: reset to fr
        m = requests.get(f"{BASE_URL}/api/auth/me", headers=pro_auth["headers"])
        assert m.json().get("lang") == "fr"

    def test_register_with_lang(self):
        email = f"test_lang_{uuid.uuid4().hex[:8]}@example.com"
        r = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": "TestPass123!", "name": "Test Lang", "lang": "de"
        })
        assert r.status_code in (200, 201), r.text
        user = r.json().get("user", {})
        assert user.get("lang") == "de", f"expected lang=de got {user}"


# ---------- AI model selector ----------

class TestAIModel:
    def test_get_ai_model_shape(self, admin_auth):
        r = requests.get(f"{BASE_URL}/api/admin/ai-model", headers=admin_auth["headers"])
        assert r.status_code == 200, r.text
        j = r.json()
        assert "current" in j and "options" in j
        assert len(j["options"]) >= 3
        for opt in j["options"]:
            assert opt.get("quality") is not None
            assert opt.get("speed") is not None
            assert opt.get("cost") is not None
            assert isinstance(opt["quality"], int)

    def test_put_ai_model_persists(self, admin_auth):
        # set to haiku
        r = requests.put(f"{BASE_URL}/api/admin/ai-model", json={"tier": "haiku"}, headers=admin_auth["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["current"] == "haiku"
        # verify persisted
        g = requests.get(f"{BASE_URL}/api/admin/ai-model", headers=admin_auth["headers"])
        assert g.json()["current"] == "haiku"
        # reset to sonnet
        r2 = requests.put(f"{BASE_URL}/api/admin/ai-model", json={"tier": "sonnet"}, headers=admin_auth["headers"])
        assert r2.status_code == 200
        assert r2.json()["current"] == "sonnet"

    def test_put_ai_model_invalid_400(self, admin_auth):
        r = requests.put(f"{BASE_URL}/api/admin/ai-model", json={"tier": "bogus"}, headers=admin_auth["headers"])
        assert r.status_code == 400


# ---------- AI usage counter ----------

class TestAIUsage:
    def test_get_ai_usage_shape(self, admin_auth):
        r = requests.get(f"{BASE_URL}/api/admin/ai-usage", headers=admin_auth["headers"])
        assert r.status_code == 200, r.text
        j = r.json()
        assert "total_calls" in j
        assert "by_feature" in j and isinstance(j["by_feature"], list)
        assert "by_model" in j and isinstance(j["by_model"], list)
        assert "detail" in j and isinstance(j["detail"], list)

    def test_ai_call_increments_counter(self, admin_auth, pro_auth):
        before = requests.get(f"{BASE_URL}/api/admin/ai-usage", headers=admin_auth["headers"]).json()
        before_total = before["total_calls"]
        before_smart = sum(x["calls"] for x in before["by_feature"] if x["feature"] == "smart_project")

        # trigger real AI call
        r = requests.post(
            f"{BASE_URL}/api/estimation/analyse",
            json={"description": "Rénovation salle de bain 8m2 haut de gamme"},
            headers=pro_auth["headers"],
            timeout=60,
        )
        assert r.status_code == 200, f"AI analyze failed: {r.status_code} {r.text[:300]}"
        # small settle
        time.sleep(1)
        after = requests.get(f"{BASE_URL}/api/admin/ai-usage", headers=admin_auth["headers"]).json()
        after_total = after["total_calls"]
        after_smart = sum(x["calls"] for x in after["by_feature"] if x["feature"] == "smart_project")

        assert after_total > before_total, f"total_calls did not increment: {before_total}->{after_total}"
        assert after_smart > before_smart, (
            f"smart_project counter did not increment: {before_smart}->{after_smart}. "
            f"by_feature={after['by_feature']}"
        )


# ---------- Document PDF localization ----------

class TestDocumentPDF:
    def test_pdf_returns_200(self, admin_auth, pro_auth):
        # Try both admin and pro
        for who, auth in [("pro", pro_auth), ("admin", admin_auth)]:
            r = requests.get(f"{BASE_URL}/api/documents", headers=auth["headers"])
            if r.status_code != 200:
                continue
            docs = r.json()
            if isinstance(docs, dict):
                docs = docs.get("documents") or docs.get("items") or []
            if not docs:
                continue
            doc_id = docs[0].get("id") or docs[0].get("doc_id") or docs[0].get("_id")
            if not doc_id:
                continue
            p = requests.get(f"{BASE_URL}/api/documents/{doc_id}/pdf", headers=auth["headers"])
            assert p.status_code == 200, f"pdf ({who}): {p.status_code} {p.text[:200]}"
            assert "pdf" in p.headers.get("content-type", "").lower(), p.headers
            assert len(p.content) > 500, "PDF empty"
            return
        pytest.skip("no documents available for either admin or pro")
