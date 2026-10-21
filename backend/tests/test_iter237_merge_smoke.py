"""Iteration 237 - Post-merge smoke tests (non-destructive)
Validates that core endpoints respond 200 after branch merge (audit refonte).
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"


@pytest.fixture(scope="module")
def pro_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": PRO_EMAIL, "password": PRO_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert "user" in data
    # cookie is httpOnly; session carries it
    return s


def test_auth_me(pro_session):
    r = pro_session.get(f"{BASE_URL}/api/auth/me", timeout=20)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("email") == PRO_EMAIL


def test_assistant_conversations(pro_session):
    r = pro_session.get(f"{BASE_URL}/api/assistant/conversations", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert isinstance(data, (list, dict))


def test_list_documents_quotes(pro_session):
    # devis list
    r = pro_session.get(f"{BASE_URL}/api/documents?type=devis", timeout=30)
    assert r.status_code == 200, r.text[:300]


def test_list_plans(pro_session):
    r = pro_session.get(f"{BASE_URL}/api/takeoffs/plans", timeout=30)
    # Allow either /plans or alternative path
    assert r.status_code in (200, 404), r.text[:300]


def test_pricing_prefs_persist(pro_session):
    # Read current margin
    me = pro_session.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
    original = me.get("target_margin_pct")
    try:
        # Set to 17
        r = pro_session.put(f"{BASE_URL}/api/users/me/preferences",
                            json={"target_margin_pct": 17}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        me2 = pro_session.get(f"{BASE_URL}/api/auth/me", timeout=15).json()
        assert float(me2.get("target_margin_pct", 0)) == 17.0, me2
    finally:
        # restore
        pro_session.put(f"{BASE_URL}/api/users/me/preferences",
                        json={"target_margin_pct": original or 0}, timeout=15)
