"""Iter175 — Growth + Trash review tests (backend focus)."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")

ADMIN = ("admin@construpilot.fr", "Construpilot2026!")
PRO = ("pro@construpilot.fr", "Pro2026!")


def _login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def pro_token():
    return _login(*PRO)


# --- Growth access & security ---

def test_growth_me_pro_forbidden(pro_token):
    r = requests.get(f"{BASE}/api/growth/me", headers={"Authorization": f"Bearer {pro_token}"}, timeout=30)
    assert r.status_code == 403
    assert "Growth" in r.text or "réservé" in r.text or "reserv" in r.text.lower()


def test_growth_me_admin_ok(admin_token):
    r = requests.get(f"{BASE}/api/growth/me", headers={"Authorization": f"Bearer {admin_token}"}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d.get("role") == "admin"
    projs = {p["key"]: p for p in d.get("projects", [])}
    assert "fr" in projs and "pt" in projs


def test_publish_inbox_requires_auth():
    r = requests.post(f"{BASE}/api/growth/publish-inbox", json={}, timeout=30)
    assert r.status_code == 401


# --- Growth data endpoints ---

def test_growth_costs(admin_token):
    r = requests.get(
        f"{BASE}/api/growth/projects/growth_fr/costs",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    d = r.json()
    assert "by_provider" in d
    providers = {row["provider"]: row for row in d["by_provider"]}
    assert "perplexity" in providers and providers["perplexity"]["estimated"] is False
    assert "openai" in providers and providers["openai"]["estimated"] is True
    assert d["budgets"]["daily_usd"] == 5
    assert d["budgets"]["monthly_usd"] == 60


def test_growth_campaigns_list_fr(admin_token):
    r = requests.get(
        f"{BASE}/api/growth/projects/growth_fr/campaigns",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r.status_code == 200
    items = r.json().get("campaigns", [])
    names = [c["name"] for c in items]
    assert "Pilote FR" in names
    pilote = next(c for c in items if c["name"] == "Pilote FR")
    assert pilote["status"] == "completed"


def test_growth_campaigns_compare_same_id(admin_token):
    # Get Pilote FR id
    r = requests.get(
        f"{BASE}/api/growth/projects/growth_fr/campaigns",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    cid = next(c["campaign_id"] for c in r.json()["campaigns"] if c["name"] == "Pilote FR")
    r2 = requests.get(
        f"{BASE}/api/growth/campaigns-compare",
        params={"a": cid, "b": cid},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=30,
    )
    assert r2.status_code == 200
    d = r2.json()
    assert "rows" in d and isinstance(d["rows"], list) and len(d["rows"]) >= 1
    assert d.get("changes") == []
