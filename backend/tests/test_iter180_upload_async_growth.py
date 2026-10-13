"""
Iter180 — Tests for:
(A) Async plan upload: POST /api/takeoffs/upload → 202 + job polling; wait=true → 200
(B) POST /api/takeoffs/{plan_id}/detect-structure-all → 202 job
(C) Growth Results panel: GET /api/growth/projects/growth_fr/results
(D) Growth Marketing: ads connectors + publish 409 + oauth start
(E) Growth content push (admin, target_url = preview URL)
(F) Auth register with attribution field
"""
import io
import os
import time
import uuid

import pytest
import requests
from reportlab.pdfgen import canvas

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PW = "Construpilot2026!"
PRO_EMAIL = "pro@construpilot.fr"
PRO_PW = "Pro2026!"


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email} → {r.status_code} {r.text[:200]}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token for {email}: {data}"
    return tok


@pytest.fixture(scope="module")
def admin_tok():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def pro_tok():
    return _login(PRO_EMAIL, PRO_PW)


def _small_pdf_bytes():
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.setFont("Helvetica", 14)
    c.drawString(100, 750, "ConstruPilot Iter180 test plan")
    c.drawString(100, 720, "Simple 1-page plan for upload test")
    c.showPage()
    c.save()
    return buf.getvalue()


# ---------------- (A) Async plan upload ----------------
def test_a1_upload_async_returns_202_then_done(pro_tok):
    files = {"file": ("iter180_plan.pdf", _small_pdf_bytes(), "application/pdf")}
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/upload",
        headers={"Authorization": f"Bearer {pro_tok}", "X-Async-Upload": "1"},
        files=files,
        timeout=60,
    )
    assert r.status_code == 202, f"expected 202, got {r.status_code}: {r.text[:300]}"
    body = r.json()
    assert body.get("status") == "processing"
    job_id = body.get("job_id")
    assert job_id, f"missing job_id: {body}"

    # poll up to 90s
    plan = None
    t0 = time.time()
    while time.time() - t0 < 90:
        pr = requests.get(
            f"{BASE_URL}/api/takeoffs/upload-jobs/{job_id}",
            headers={"Authorization": f"Bearer {pro_tok}"},
            timeout=30,
        )
        assert pr.status_code == 200, f"poll status {pr.status_code}: {pr.text[:200]}"
        pb = pr.json()
        st = pb.get("status")
        if st == "done":
            plan = pb.get("plan")
            break
        if st == "error":
            pytest.fail(f"job errored: {pb}")
        time.sleep(2)
    assert plan, f"job did not finish in 90s (last status polled)"
    assert plan.get("plan_id"), f"missing plan_id: {plan}"
    assert plan.get("page_count") == 1, f"expected page_count=1, got {plan.get('page_count')}"


def test_a2_upload_wait_true_returns_plan_directly(pro_tok):
    files = {"file": ("iter180_plan_wait.pdf", _small_pdf_bytes(), "application/pdf")}
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/upload",
        headers={"Authorization": f"Bearer {pro_tok}"},
        files=files,
        data={"wait": "true"},
        timeout=180,
    )
    # NOTE: spec expects 200 for wait=true, but backend decorator forces status_code=202.
    # The body IS the full plan summary though, so functionally correct.
    body = r.json()
    assert body.get("plan_id"), f"missing plan_id: {body}"
    pytest.plan_id_for_detect = body["plan_id"]
    assert r.status_code == 200, f"WAIT_STATUS_MISMATCH: expected 200 with wait=true, got {r.status_code} (body has plan_id but status is wrong)"


# ---------------- (B) detect-structure-all async ----------------
def test_b_detect_structure_all_async(pro_tok):
    plan_id = getattr(pytest, "plan_id_for_detect", None)
    if not plan_id:
        # fallback: upload synchronously
        files = {"file": ("iter180_detect.pdf", _small_pdf_bytes(), "application/pdf")}
        rr = requests.post(
            f"{BASE_URL}/api/takeoffs/upload",
            headers={"Authorization": f"Bearer {pro_tok}"},
            files=files,
            data={"wait": "true"},
            timeout=180,
        )
        assert rr.status_code in (200, 202), rr.text[:200]
        plan_id = rr.json()["plan_id"]

    r = requests.post(
        f"{BASE_URL}/api/takeoffs/{plan_id}/detect-structure-all",
        headers={"Authorization": f"Bearer {pro_tok}"},
        timeout=60,
    )
    assert r.status_code == 202, f"expected 202, got {r.status_code}: {r.text[:300]}"
    job_id = r.json().get("job_id")
    assert job_id, f"missing job_id: {r.json()}"

    t0 = time.time()
    result = None
    while time.time() - t0 < 120:
        pr = requests.get(
            f"{BASE_URL}/api/takeoffs/upload-jobs/{job_id}",
            headers={"Authorization": f"Bearer {pro_tok}"},
            timeout=30,
        )
        assert pr.status_code == 200, pr.text[:200]
        pb = pr.json()
        st = pb.get("status")
        if st == "done":
            result = pb.get("result") or {}
            break
        if st == "error":
            pytest.fail(f"detect job errored: {pb}")
        time.sleep(3)
    assert result is not None, "detect-structure-all did not finish in 120s"
    # accept either 'page_count' or 'pages' list length
    pc = result.get("page_count")
    if pc is None and isinstance(result.get("pages"), list):
        pc = len(result["pages"])
    assert pc == 1, f"expected 1 page, got {pc} (result={str(result)[:300]})"


# ---------------- (C) Growth results ----------------
def test_c_growth_results(admin_tok):
    r = requests.get(
        f"{BASE_URL}/api/growth/projects/growth_fr/results",
        headers={"Authorization": f"Bearer {admin_tok}"},
        timeout=30,
    )
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    body = r.json()
    rows = body.get("rows") or []
    assert len(rows) >= 4, f"expected ≥4 rows, got {len(rows)}"
    for row in rows[:4]:
        assert "path" in row, row
        assert "clicks" in row, row
        assert "signups_organic" in row, row
        assert "gsc_available" in row, row
    assert "totals" in body


# ---------------- (D) Ads connectors + publish 409 + oauth start ----------------
def test_d1_ads_connectors(admin_tok):
    r = requests.get(
        f"{BASE_URL}/api/growth/projects/growth_fr/ads/connectors",
        headers={"Authorization": f"Bearer {admin_tok}"},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("google", {}).get("configured") is False
    assert isinstance(body["google"].get("missing"), list) and body["google"]["missing"]
    assert body.get("meta", {}).get("configured") is False
    assert isinstance(body["meta"].get("missing"), list)


def test_d2_publish_409_not_configured(admin_tok):
    r = requests.post(
        f"{BASE_URL}/api/growth/ads/ad_78ba506ddd11/publish",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"platform": "google", "daily_budget_eur": 10},
        timeout=30,
    )
    assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text[:300]}"


def test_d3_google_oauth_start(admin_tok):
    r = requests.post(
        f"{BASE_URL}/api/growth/integrations/google/start",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"project_id": "growth_fr", "provider": "google_ads"},
        timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    url = r.json().get("url", "")
    assert "adwords" in url.lower(), f"scope adwords not in url: {url[:200]}"


# ---------------- (E) content push admin ----------------
def test_e_content_push(admin_tok):
    r = requests.post(
        f"{BASE_URL}/api/growth/contents/cnt_ce2472d534bd/push",
        headers={"Authorization": f"Bearer {admin_tok}"},
        json={"target_url": BASE_URL},
        timeout=60,
    )
    # Cibles restreintes (liste blanche GROWTH_PUSH_TARGETS) : l'aperçu n'en fait pas partie → 422 attendu ; 200 si autorisé.
    assert r.status_code in (200, 422), f"{r.status_code}: {r.text[:300]}"
    if r.status_code == 200:
        assert r.json().get("url"), r.json()


# ---------------- (F) Register with attribution ----------------
def test_f_register_with_attribution(admin_tok):
    unique = uuid.uuid4().hex[:10]
    email = f"test.iter180.{unique}@example.com"
    payload = {
        "email": email,
        "password": "TestIter180!",
        "name": "Iter180 Test",
        "attribution": {
            "landing_path": "/blog/test",
            "utm_source": "ads",
            "utm_medium": "cpc",
            "utm_campaign": "test-camp",
        },
    }
    r = requests.post(f"{BASE_URL}/api/auth/register", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"register {r.status_code}: {r.text[:300]}"

    # admin can still GET results
    rr = requests.get(
        f"{BASE_URL}/api/growth/projects/growth_fr/results",
        headers={"Authorization": f"Bearer {admin_tok}"},
        timeout=30,
    )
    assert rr.status_code == 200
