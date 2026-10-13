"""Tests for the Site Tracking module (pack Business)."""
import os
import base64
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://pilot-build-demo.preview.emergentagent.com"
ADMIN = ("admin@construpilot.fr", "Construpilot2026!")
CLIENT = ("client@construpilot.fr", "Client2026!")

# 1x1 transparent PNG
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
PNG_DATA_URL = "data:image/png;base64," + PNG_B64


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data, f"no token in login response: {data}"
    return data["token"]


@pytest.fixture(scope="module")
def admin_headers():
    tok = _login(*ADMIN)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def client_headers():
    tok = _login(*CLIENT)
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def project_name():
    return "TEST_Villa_SiteTracking"


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin_headers, project_name):
    yield
    # Best-effort cleanup
    for path in ("reports", "reserves", "checklist"):
        try:
            r = requests.get(f"{BASE}/api/site/{path}", headers=admin_headers, params={"project": project_name}, timeout=30)
            if r.status_code == 200:
                for item in r.json():
                    key = item.get("report_id") or item.get("reserve_id") or item.get("item_id")
                    if key:
                        requests.delete(f"{BASE}/api/site/{path}/{key}", headers=admin_headers, timeout=30)
        except Exception:
            pass


# ── Billing gating (module-level, no auth requirement for user's own tier)
def test_billing_me_admin(admin_headers):
    r = requests.get(f"{BASE}/api/billing/me", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    # admin bypasses via role check in frontend BillingContext; the backend just returns their real tier


def test_billing_me_client(client_headers):
    r = requests.get(f"{BASE}/api/billing/me", headers=client_headers, timeout=30)
    assert r.status_code == 200
    tier = r.json().get("tier", "free")
    assert tier != "pro_business", f"client should not be pro_business, got {tier}"


# ── Reports CRUD
def test_create_report(admin_headers, project_name):
    payload = {"project": project_name, "title": "TEST_Visite 1", "notes": "Chape coulée OK", "photos": [PNG_DATA_URL]}
    r = requests.post(f"{BASE}/api/site/reports", headers=admin_headers, json=payload, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["title"] == "TEST_Visite 1"
    assert data["project"] == project_name
    assert "report_id" in data
    assert isinstance(data.get("photos"), list) and len(data["photos"]) == 1
    assert "_id" not in data
    # GET file to confirm upload
    fr = requests.get(f"{BASE}/api/site/file", params={"path": data["photos"][0]}, timeout=30)
    assert fr.status_code == 200, fr.text
    assert fr.headers.get("content-type", "").startswith("image/")
    pytest.report_id = data["report_id"]


def test_list_reports_contains_created(admin_headers, project_name):
    r = requests.get(f"{BASE}/api/site/reports", headers=admin_headers, params={"project": project_name}, timeout=30)
    assert r.status_code == 200
    ids = [x["report_id"] for x in r.json()]
    assert pytest.report_id in ids


# ── Reserves CRUD + toggle
def test_create_reserve(admin_headers, project_name):
    payload = {
        "project": project_name,
        "lot": "TEST_Plomberie",
        "description": "TEST_Fuite sous évier",
        "company": "TEST_Plombco",
        "company_email": "contact-test@example.com",
        "photos": [PNG_DATA_URL],
    }
    r = requests.post(f"{BASE}/api/site/reserves", headers=admin_headers, json=payload, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "open"
    assert data["description"] == "TEST_Fuite sous évier"
    assert len(data.get("photos", [])) == 1
    pytest.reserve_id = data["reserve_id"]


def test_toggle_reserve(admin_headers):
    r = requests.patch(f"{BASE}/api/site/reserves/{pytest.reserve_id}", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    assert r.json().get("status") == "lifted"
    # toggle back to open
    r2 = requests.patch(f"{BASE}/api/site/reserves/{pytest.reserve_id}", headers=admin_headers, timeout=30)
    assert r2.json().get("status") == "open"


# ── Checklist
def test_create_checklist(admin_headers, project_name):
    payload = {"project": project_name, "lot": "TEST_Gros oeuvre", "label": "TEST_Couler dalle"}
    r = requests.post(f"{BASE}/api/site/checklist", headers=admin_headers, json=payload, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["label"] == "TEST_Couler dalle"
    assert data["done"] is False
    pytest.ck_id = data["item_id"]


def test_toggle_checklist(admin_headers):
    r = requests.patch(f"{BASE}/api/site/checklist/{pytest.ck_id}", headers=admin_headers, timeout=30)
    assert r.status_code == 200
    assert r.json().get("done") is True


# ── PDF export
def test_report_pdf(admin_headers, project_name):
    r = requests.get(f"{BASE}/api/site/report-pdf", headers=admin_headers, params={"project": project_name}, timeout=60)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content[:4] == b"%PDF"


# ── Reminder
def test_remind_companies(admin_headers, project_name):
    r = requests.post(f"{BASE}/api/site/reserves/remind", headers=admin_headers, params={"project": project_name}, timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "emails_sent" in data
    assert "companies" in data
    assert "reserves_without_email" in data
    assert isinstance(data["emails_sent"], int)


# ── Deletion
def test_delete_all(admin_headers):
    r1 = requests.delete(f"{BASE}/api/site/reports/{pytest.report_id}", headers=admin_headers, timeout=30)
    assert r1.status_code == 200
    r2 = requests.delete(f"{BASE}/api/site/reserves/{pytest.reserve_id}", headers=admin_headers, timeout=30)
    assert r2.status_code == 200
    r3 = requests.delete(f"{BASE}/api/site/checklist/{pytest.ck_id}", headers=admin_headers, timeout=30)
    assert r3.status_code == 200


# ── Auth required
def test_reports_requires_auth():
    r = requests.get(f"{BASE}/api/site/reports", timeout=30)
    assert r.status_code in (401, 403)
