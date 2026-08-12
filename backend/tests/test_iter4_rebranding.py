"""
Iter 4 — Rebranding tests: CMRENOV Travaux AI -> ConstruPilot.
Verifies:
- Brand endpoint
- New credentials work / old @cmrenov.fr removed
- Regression on major endpoints
- PDF contains 'ConstruPilot'
"""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://cmrenov-ai.preview.emergentagent.com').rstrip('/')
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PWD = "Construpilot2026!"
DEMO_EMAIL = "demo@construpilot.fr"
DEMO_PWD = "Demo2026!"


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PWD}, timeout=30)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert data.get("user", {}).get("role") == "admin", f"Expected admin role, got {data.get('user')}"
    return data["token"]


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PWD}, timeout=30)
    assert r.status_code == 200, f"Demo login failed: {r.status_code} {r.text}"
    return r.json()["token"]


# --- Brand endpoint ---
def test_root_brand():
    r = requests.get(f"{API}/", timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data.get("app") == "ConstruPilot"
    assert data.get("tagline") == "Estimez, Comparez, Construisez."
    assert data.get("status") == "ok"


# --- Auth: old creds removed ---
@pytest.mark.parametrize("email,pwd", [
    ("admin@cmrenov.fr", "Cmrenov2026!"),
    ("admin@cmrenov.fr", "Construpilot2026!"),
    ("demo@cmrenov.fr", "Demo2026!"),
])
def test_old_cmrenov_credentials_rejected(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code in (400, 401, 403, 404), f"Old cred {email} should be rejected, got {r.status_code}"


def test_admin_login(admin_token):
    assert admin_token and isinstance(admin_token, str)


def test_demo_login(demo_token):
    assert demo_token and isinstance(demo_token, str)


# --- PDF regression + brand ---
def _compute_payload():
    return {
        "project_type": "renovation_complete",
        "surface": 50,
        "finish_level": "standard",
        "building_type": "maison",
        "condition": "bon",
    }


def test_estimation_compute():
    r = requests.post(f"{API}/estimation/compute", json=_compute_payload(), timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("total_avg", 0) > 0
    assert isinstance(data.get("lots"), list) and len(data["lots"]) > 0


def test_estimation_pdf_contains_construpilot():
    # First compute
    comp = requests.post(f"{API}/estimation/compute", json=_compute_payload(), timeout=60)
    assert comp.status_code == 200, comp.text
    estimation = comp.json()
    pdf_payload = {
        "project": {"name": "TEST_iter4_rebrand"},
        "estimation": estimation,
        "advice": "",
    }
    r = requests.post(f"{API}/estimation/pdf", json=pdf_payload, timeout=90)
    assert r.status_code == 200, r.text
    content = r.content
    assert content[:4] == b"%PDF", "Response is not a PDF"
    lowered = content.lower()
    assert b"construpilot" in lowered, "PDF does not contain ConstruPilot brand string"
    assert b"cmrenov" not in lowered, "PDF still contains 'cmrenov' string"
    # filename header should also mention ConstruPilot
    cd = r.headers.get("Content-Disposition", "")
    assert "ConstruPilot" in cd, f"filename does not contain ConstruPilot: {cd}"


def test_estimation_pdf_email_subject_smoke():
    """Just check schema not broken (send to Resend sandbox address)."""
    comp = requests.post(f"{API}/estimation/compute", json=_compute_payload(), timeout=60)
    estimation = comp.json()
    payload = {
        "project": {"name": "TEST_iter4"},
        "estimation": estimation,
        "advice": "",
        "to": "delivered@resend.dev",
        "message": "",
    }
    r = requests.post(f"{API}/estimation/pdf/email", json=payload, timeout=90)
    # Accept 200 (sent) or 502 (mail provider blip). Do not accept 4xx (schema break).
    assert r.status_code in (200, 502), r.text


def test_prices_search():
    r = requests.post(f"{API}/prices/search", json={"query": "carrelage", "limit": 5}, timeout=30)
    assert r.status_code == 200, r.text


def test_ai_smart_project_available():
    """iter4 review calls it 'smart-project'; backend route is /estimation/analyse."""
    payload = {"description": "Refaire peinture salon 20m2"}
    r = requests.post(f"{API}/estimation/analyse", json=payload, timeout=180)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "analysis" in data and "estimation" in data


def test_prices_alerts_check_now(admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    r = requests.post(f"{API}/prices/alerts/check-now", headers=h, timeout=60)
    assert r.status_code in (200, 202), r.text


# --- No CMRENOV leaks in main JSON responses ---
def test_no_cmrenov_in_root():
    r = requests.get(f"{API}/", timeout=30)
    assert "cmrenov" not in r.text.lower()
