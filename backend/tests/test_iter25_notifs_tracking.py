"""Iter25 tests: Notifications read-all + Quote Sends aggregated (Suivi Devis)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or "http://localhost:3000"
if not BASE_URL:
    BASE_URL = "http://localhost:3000"

# Frontend .env has the public URL
def _read_public_url():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        return None
    return None

PUBLIC_URL = _read_public_url() or BASE_URL


@pytest.fixture(scope="module")
def pro_token():
    r = requests.post(f"{PUBLIC_URL}/api/auth/login",
                      json={"email": "pro@construpilot.fr", "password": "Pro2026!"},
                      timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers(pro_token):
    return {"Authorization": f"Bearer {pro_token}"}


# ---------- Notifications ----------

class TestNotifications:
    def test_list_notifications(self, pro_headers):
        r = requests.get(f"{PUBLIC_URL}/api/quotes/notifications/me",
                         headers=pro_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "unread" in data and "notifications" in data
        assert isinstance(data["notifications"], list)
        assert isinstance(data["unread"], int)

    def test_read_all_notifications(self, pro_headers):
        r = requests.post(f"{PUBLIC_URL}/api/quotes/notifications/read-all",
                          headers=pro_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") == True
        assert "marked" in data and isinstance(data["marked"], int)

        # Verify unread now = 0
        r2 = requests.get(f"{PUBLIC_URL}/api/quotes/notifications/me",
                          headers=pro_headers, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["unread"] == 0


# ---------- Suivi Devis ----------

class TestQuoteSendsAll:
    def test_sends_all_shape(self, pro_headers):
        r = requests.get(f"{PUBLIC_URL}/api/quotes/sends/all",
                         headers=pro_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "sends" in data and "stats" in data
        assert isinstance(data["sends"], list)

        stats = data["stats"]
        for k in ("sent", "opened", "signed", "not_opened",
                  "total_ttc_signed", "total_ttc_pipeline"):
            assert k in stats, f"missing stat key: {k}"

        # Each send: no _id, no signature_b64, has plan_filename key
        for s in data["sends"]:
            assert "_id" not in s
            assert "signature_b64" not in s
            assert "plan_filename" in s  # key present (value may be None)
            assert "log_id" in s
            assert "plan_id" in s

    def test_sends_all_requires_auth(self):
        r = requests.get(f"{PUBLIC_URL}/api/quotes/sends/all", timeout=10)
        assert r.status_code in (401, 403)

    def test_signature_link_creation(self, pro_headers):
        # Get an unsigned send
        r = requests.get(f"{PUBLIC_URL}/api/quotes/sends/all",
                         headers=pro_headers, timeout=15)
        sends = r.json()["sends"]
        target = next((s for s in sends if not s.get("signed")), None)
        if not target:
            pytest.skip("No unsigned send available")
        r2 = requests.post(
            f"{PUBLIC_URL}/api/takeoffs/{target['plan_id']}/quote-sends/{target['log_id']}/signature-link",
            headers=pro_headers, timeout=15
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data.get("ok") == True
        assert "token" in data and "url" in data
        assert "/sign/" in data["url"]
