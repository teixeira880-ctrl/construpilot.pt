"""Iter 133 — Cotes multi-pages + /cotes/latest + PUT /auth/theme."""
import os
import io
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].splitlines()[0]).rstrip("/")
API = f"{BASE_URL}/api"
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"
MULTI_PLAN = "plan_3396f3ebea53"  # 2-page PDF
UA = "Mozilla/5.0 (X11; Linux) AppleWebKit/537.36"

HEADERS = {"User-Agent": UA, "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def pro_client():
    s = requests.Session()
    s.headers.update(HEADERS)
    r = s.post(f"{API}/auth/login", json={"email": PRO_EMAIL, "password": PRO_PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# --- Cotes multi-pages ---------------------------------------------------

def test_check_all_2_pages(pro_client):
    r = pro_client.post(f"{API}/takeoffs/{MULTI_PLAN}/cotes/check-all",
                        json={"tol_pct": 2, "tol_cm": 3}, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "pages" in d and "summary" in d and "tolerance" in d and "errors" in d
    assert len(d["pages"]) == 2, d
    for p in d["pages"]:
        assert "page_index" in p and "summary" in p
    s = d["summary"]
    for k in ("total", "ok", "warn", "ko", "chains_total", "chains_ko", "max_delta_cm", "pages", "verdict"):
        assert k in s, f"missing {k}"
    assert s["pages"] == 2
    assert d["tolerance"] == {"pct": 2.0, "cm": 3.0}


def test_report_all_pdf(pro_client):
    r = pro_client.get(f"{API}/takeoffs/{MULTI_PLAN}/cotes/report-all.pdf", timeout=60)
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type", "").startswith("application/pdf")
    body = r.content
    assert body[:4] == b"%PDF"
    # Count pages
    n_pages = body.count(b"/Type /Page\n") + body.count(b"/Type /Page ") + body.count(b"/Type/Page")
    # More reliable: count /Type /Page but not /Pages
    count = 0
    for line in body.split(b"\n"):
        if b"/Type /Page" in line and b"/Pages" not in line:
            count += 1
    # Fallback: use PyPDF2 if needed
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        count = len(reader.pages)
    except Exception:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(body))
            count = len(reader.pages)
        except Exception:
            pass
    assert count >= 5, f"Expected >=5 pages, got {count}"


def test_report_all_404_no_check(pro_client):
    # Register throwaway user with no plans → check-all/report-all on unknown plan → 404
    import uuid
    email = f"test_iter133_{uuid.uuid4().hex[:8]}@construpilot.fr"
    s2 = requests.Session()
    s2.headers.update(HEADERS)
    r = s2.post(f"{API}/auth/register", json={"name": "t", "email": email, "password": "abcdef1"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    s2.headers.update({"Authorization": f"Bearer {tok}"})
    # Any plan_id doesn't belong → 404
    r = s2.get(f"{API}/takeoffs/plan_doesnotexist/cotes/report-all.pdf")
    assert r.status_code == 404


# --- /cotes/latest --------------------------------------------------------

def test_cotes_latest_pro(pro_client):
    r = pro_client.get(f"{API}/cotes/latest")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "latest" in d and "plans_checked" in d
    assert d["plans_checked"] >= 1
    lat = d["latest"]
    assert lat is not None
    for k in ("plan_id", "filename", "page_index", "pages_checked", "checked_at", "summary", "verdict"):
        assert k in lat, f"missing {k}"


def test_cotes_latest_fresh_user():
    import uuid
    email = f"test_iter133_fresh_{uuid.uuid4().hex[:8]}@construpilot.fr"
    s = requests.Session()
    s.headers.update(HEADERS)
    r = s.post(f"{API}/auth/register", json={"name": "fresh", "email": email, "password": "abcdef1"})
    assert r.status_code == 200
    tok = r.json()["token"]
    s.headers.update({"Authorization": f"Bearer {tok}"})
    r = s.get(f"{API}/cotes/latest")
    assert r.status_code == 200
    d = r.json()
    assert d == {"latest": None, "plans_checked": 0}, d


# --- PUT /auth/theme ------------------------------------------------------

def test_theme_dark_then_light(pro_client):
    try:
        r = pro_client.put(f"{API}/auth/theme", json={"theme": "dark"})
        assert r.status_code == 200, r.text
        assert r.json() == {"theme": "dark"}

        r = pro_client.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json().get("theme") == "dark"

        r = pro_client.put(f"{API}/auth/theme", json={"theme": "blue"})
        assert r.status_code == 422, r.text
    finally:
        # Restore light
        r = pro_client.put(f"{API}/auth/theme", json={"theme": "light"})
        assert r.status_code == 200
        assert r.json() == {"theme": "light"}
