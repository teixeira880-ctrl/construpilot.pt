"""Iteration 11 — Phase 7 finalization tests.

Covers:
- PRICING PRO updated to 99€/199€ (yearly 990€/1990€)
- PUSH endpoints (public-key, subscribe, unsubscribe, test)
- RETENTION admin trigger and user preferences
- SANITY: /api/, estimation/analyse, prices/search, /sw.js
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

USER = {"email": "demo@construpilot.fr", "password": "Demo2026!"}
ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    return _login(USER)


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


# --------- PRICING PRO ---------
class TestPricingPro:
    def test_plans_pro_amounts(self):
        r = requests.get(f"{BASE_URL}/api/plans", params={"audience": "pro"}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        plans = data if isinstance(data, list) else data.get("plans", data.get("items", []))
        assert plans, f"no plans in response {data}"
        amounts = sorted([p.get("amount_cents") for p in plans if p.get("amount_cents") is not None])
        expected = sorted([9900, 99000, 19900, 199000])
        # Ensure the 4 expected amounts are present (may include other plans; assert subset)
        for e in expected:
            assert e in amounts, f"missing amount {e} in {amounts}"


# --------- PUSH NOTIFICATIONS ---------
class TestPush:
    def test_public_key(self):
        r = requests.get(f"{BASE_URL}/api/push/public-key", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("public_key"), f"empty public key: {data}"
        assert isinstance(data["public_key"], str) and len(data["public_key"]) > 10

    def test_subscribe_unsubscribe_test(self, user_token):
        headers = {"Authorization": f"Bearer {user_token}"}
        body = {"endpoint": "https://example.com/test-iter11", "keys": {"p256dh": "x", "auth": "y"}}
        r = requests.post(f"{BASE_URL}/api/push/subscribe", json=body, headers=headers, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # test broadcast
        rt = requests.post(f"{BASE_URL}/api/push/test", headers=headers, timeout=30)
        assert rt.status_code == 200, rt.text
        j = rt.json()
        assert j.get("ok") is True
        assert "sent" in j and isinstance(j["sent"], int)

        # unsubscribe cleanup
        ru = requests.post(
            f"{BASE_URL}/api/push/unsubscribe",
            json=body,
            headers=headers,
            timeout=30,
        )
        assert ru.status_code == 200, ru.text


# --------- RETENTION EMAIL ---------
class TestRetention:
    def test_admin_send_digests(self, admin_token):
        headers = {"Authorization": f"Bearer {admin_token}"}
        r = requests.post(f"{BASE_URL}/api/admin/retention/send-digests", headers=headers, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert "sent" in j

    def test_user_preferences_update(self, user_token):
        headers = {"Authorization": f"Bearer {user_token}"}
        r = requests.put(
            f"{BASE_URL}/api/users/me/preferences",
            json={"weekly_digest": False},
            headers=headers,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        prefs = r.json()
        # Should reflect the update
        assert prefs.get("weekly_digest") is False or prefs.get("preferences", {}).get("weekly_digest") is False
        # Restore true
        requests.put(
            f"{BASE_URL}/api/users/me/preferences",
            json={"weekly_digest": True},
            headers=headers,
            timeout=30,
        )


# --------- SANITY ---------
class TestSanity:
    def test_api_root(self):
        r = requests.get(f"{BASE_URL}/api/", timeout=30)
        assert r.status_code == 200

    def test_estimation_analyse(self, user_token):
        headers = {"Authorization": f"Bearer {user_token}"}
        r = requests.post(
            f"{BASE_URL}/api/estimation/analyse",
            json={"description": "Rénovation salle de bain 5m2 avec carrelage et douche italienne"},
            headers=headers,
            timeout=90,
        )
        assert r.status_code in (200, 201), r.text[:200]

    def test_prices_search(self):
        r = requests.post(f"{BASE_URL}/api/prices/search", json={"query": "carrelage", "limit": 3}, timeout=60)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        # Just ensure structure ok
        assert isinstance(data, (list, dict))

    def test_sw_served(self):
        # SW is a frontend asset, hit REACT_APP_BACKEND_URL/sw.js (no /api prefix)
        r = requests.get(f"{BASE_URL}/sw.js", timeout=30)
        assert r.status_code == 200, f"sw.js status {r.status_code}"
        assert "service" in r.text.lower() or "self" in r.text.lower() or len(r.text) > 20
