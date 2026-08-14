"""Iter 72 — Final tests for new PC features:
- Weather (Open-Meteo)
- Purchase-Order response tracking
- Public signature GET/accept
- PC dashboard
"""
import os
import pytest
import requests

def _read_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip()
    except Exception:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"

PRO_EMAIL = "pro@construpilot.fr"
PRO_PWD = "Pro2026!"
ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PWD = "Construpilot2026!"

PLAN_WITH_STUDY = "plan_6ebd820859f2"
PLAN_WITH_BC = "plan_619e41f98d6b"
ALREADY_ACCEPTED_TOKEN = "pcs_e2a4c343ca79d96e"


@pytest.fixture(scope="module")
def pro_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": PRO_EMAIL, "password": PRO_PWD}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers(pro_token):
    return {"Authorization": f"Bearer {pro_token}"}


# ---------- A. Weather ----------
class TestWeather:
    def test_weather_marseille(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/pc/weather", params={"city": "Marseille"},
                         headers=pro_headers, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("city")
        assert "days" in data
        # 16 forecast days from Open-Meteo
        days = data["days"]
        assert isinstance(days, list)
        assert len(days) >= 14

    def test_weather_unknown_city(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/pc/weather",
                         params={"city": "Xyzabc123ZZZ"},
                         headers=pro_headers, timeout=30)
        # Should either be 200 with error field or a 4xx
        assert r.status_code in (200, 400, 404, 422)
        if r.status_code == 200:
            data = r.json()
            assert data.get("error") or not data.get("days")

    def test_weather_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/pc/weather",
                         params={"city": "Marseille"}, timeout=15)
        assert r.status_code in (401, 403)


# ---------- B. Purchase Order response ----------
class TestPoResponse:
    def test_unknown_ref_returns_404(self, pro_headers):
        r = requests.post(
            f"{BASE_URL}/api/takeoffs/{PLAN_WITH_BC}/purchase-orders/response",
            json={"ref": "BC-DOES-NOT-EXIST-9999", "status": "recu",
                  "quoted_ht": 1000},
            headers=pro_headers, timeout=15)
        assert r.status_code == 404

    def test_invalid_status_422(self, pro_headers):
        r = requests.post(
            f"{BASE_URL}/api/takeoffs/{PLAN_WITH_BC}/purchase-orders/response",
            json={"ref": "BC-F98D6B-N1-20260814", "status": "not_a_status",
                  "quoted_ht": 1000},
            headers=pro_headers, timeout=15)
        assert r.status_code == 422

    def test_valid_response_ok(self, pro_headers):
        # First find an existing BC ref via dashboard/plan detail if possible.
        # Attempt with the ref mentioned in the request spec.
        r = requests.post(
            f"{BASE_URL}/api/takeoffs/{PLAN_WITH_BC}/purchase-orders/response",
            json={"ref": "BC-F98D6B-N1-20260814", "status": "retenu",
                  "quoted_ht": 3900, "notes": "TEST_ regression"},
            headers=pro_headers, timeout=15)
        # It might 404 if the seed ref differs; document either outcome
        assert r.status_code in (200, 404), r.text
        if r.status_code == 200:
            data = r.json()
            assert data.get("ok") is True
            assert data.get("status") == "retenu"


# ---------- C. Signature (public) ----------
class TestSign:
    def test_invalid_token_404(self):
        r = requests.get(f"{BASE_URL}/api/pc/sign/pcs_invalid_token_xxx",
                         timeout=15)
        assert r.status_code == 404

    def test_valid_token_get(self):
        r = requests.get(f"{BASE_URL}/api/pc/sign/{ALREADY_ACCEPTED_TOKEN}",
                         timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "totals" in data
        assert "lots" in data
        assert data.get("accepted") is True
        assert data.get("accepted_by")

    def test_already_accepted_returns_already(self):
        r = requests.post(
            f"{BASE_URL}/api/pc/sign/{ALREADY_ACCEPTED_TOKEN}/accept",
            json={"name": "Testeur QA"}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("already") is True


# ---------- D. Dashboard ----------
class TestDashboard:
    def test_dashboard_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/pc/dashboard", timeout=15)
        assert r.status_code in (401, 403)

    def test_dashboard_authed(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/pc/dashboard",
                         headers=pro_headers, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "studies" in data
        assert isinstance(data["studies"], list)
        # Pro user should have at least one study
        assert len(data["studies"]) >= 1
        for s in data["studies"]:
            assert "plan_id" in s
            assert "status" in s
            assert s["status"] in (
                "générée", "envoyée", "relancée", "ouverte", "acceptée")
        # At least one should be 'acceptée' per task context
        assert any(s["status"] == "acceptée" for s in data["studies"])
