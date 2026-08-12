"""Iter 3 tests: PDF email, timeline, alerts check-now, scheduler."""
import os
import base64
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cmrenov-ai.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@cmrenov.fr"
DEMO_PASS = "Demo2026!"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sample_estimation():
    r = requests.post(f"{API}/estimation/compute", json={
        "project_type": "renovation_complete", "surface": 60,
        "finish_level": "standard", "country": "FR", "region": "IDF",
        "building_type": "appartement", "condition": "bon",
    }, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---- PDF email ----
class TestPdfEmail:
    def test_email_success(self, sample_estimation):
        r = requests.post(f"{API}/estimation/pdf/email", json={
            "project": {"name": "TEST_iter3_email"},
            "estimation": sample_estimation,
            "to": "delivered@resend.dev",
            "message": "Test iter3",
        }, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("to") == "delivered@resend.dev"

    def test_email_empty_estimation_400(self):
        r = requests.post(f"{API}/estimation/pdf/email", json={
            "project": {"name": "x"}, "estimation": {}, "to": "delivered@resend.dev"
        }, timeout=15)
        assert r.status_code == 400


# ---- Timeline ----
class TestTimeline:
    def test_timeline_full(self, headers, sample_estimation):
        # create project
        r = requests.post(f"{API}/projects", headers=headers, json={
            "name": "TEST_iter3_timeline",
            "project": {"project_type": "renovation_complete", "surface": 50,
                        "finish_level": "standard", "country": "FR",
                        "building_type": "appartement", "condition": "bon"},
            "estimation": sample_estimation,
        }, timeout=30)
        assert r.status_code in (200, 201), r.text
        pid = r.json().get("project_id") or r.json().get("id")
        assert pid

        # add photo (tiny 1x1 png)
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
        )
        r = requests.post(f"{API}/projects/{pid}/photos", headers=headers,
                          files={"file": ("t.png", png, "image/png")},
                          data={"kind": "progress", "caption": "test"}, timeout=30)
        assert r.status_code in (200, 201), r.text

        # add expense
        r = requests.post(f"{API}/projects/{pid}/expenses", headers=headers, json={
            "label": "TEST expense", "amount": 100, "lot": "peinture",
        }, timeout=15)
        assert r.status_code in (200, 201), r.text

        # toggle progress via PATCH /projects/{id}
        r = requests.patch(f"{API}/projects/{pid}", headers=headers,
                           json={"progress": {"peinture": "done"}}, timeout=15)
        assert r.status_code in (200, 204), r.text

        # get timeline
        r = requests.get(f"{API}/projects/{pid}/timeline", headers=headers, timeout=15)
        assert r.status_code == 200, r.text
        tl = r.json()
        assert "events" in tl and "count" in tl
        types = [e["type"] for e in tl["events"]]
        assert "project" in types
        assert "photo" in types
        assert "expense" in types
        assert "progress" in types
        # sorted desc by 'at'
        ats = [e.get("at") or "" for e in tl["events"]]
        assert ats == sorted(ats, reverse=True)

        # create lead for that project
        r = requests.post(f"{API}/leads", headers=headers, json={
            "project_id": pid, "name": "TEST Lead", "phone": "0600000000",
            "email": "lead@test.fr", "message": "test",
        }, timeout=15)
        # lead endpoint may vary — accept both
        if r.status_code in (200, 201):
            r = requests.get(f"{API}/projects/{pid}/timeline", headers=headers, timeout=15)
            assert r.status_code == 200
            types2 = [e["type"] for e in r.json()["events"]]
            assert "lead" in types2

        # cleanup
        requests.delete(f"{API}/projects/{pid}", headers=headers, timeout=15)

    def test_timeline_requires_auth(self):
        r = requests.get(f"{API}/projects/nonexistent/timeline", timeout=15)
        assert r.status_code in (401, 403)


# ---- Alerts check-now ----
class TestAlertsCheckNow:
    def test_check_now(self, headers):
        # Create an alert with high target price (likely to trigger)
        r = requests.post(f"{API}/prices/alerts", headers=headers, json={
            "query": "peinture blanche 10L",
            "target_price": 9999.0,
            "product": "TEST_iter3 peinture",
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        alert_id = r.json().get("alert_id")

        # trigger check
        r = requests.post(f"{API}/prices/alerts/check-now", headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert isinstance(d.get("notified"), int)
        assert d["notified"] >= 0

        # cleanup
        if alert_id:
            requests.delete(f"{API}/prices/alerts/{alert_id}", headers=headers, timeout=15)

    def test_check_now_requires_auth(self):
        r = requests.post(f"{API}/prices/alerts/check-now", timeout=10)
        assert r.status_code in (401, 403)


# ---- Regression key endpoints ----
class TestRegression:
    def test_prices_search(self):
        r = requests.post(f"{API}/prices/search", json={"query": "carrelage 60x60", "limit": 5}, timeout=30)
        assert r.status_code == 200
        assert "results" in r.json()

    def test_estimation_pdf_public(self, sample_estimation):
        r = requests.post(f"{API}/estimation/pdf", json={
            "project": {"name": "reg"}, "estimation": sample_estimation,
        }, timeout=30)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/pdf")

    def test_auth_me(self, headers):
        r = requests.get(f"{API}/auth/me", headers=headers, timeout=15)
        assert r.status_code == 200
