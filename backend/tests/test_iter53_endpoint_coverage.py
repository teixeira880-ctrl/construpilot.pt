"""Iter53 endpoint HTTP-level coverage.

Complements test_iter53_refactor_regression.py by hitting HTTP endpoints
requested by the review to confirm no 500 regression after the split of
routes/plans.py into 5 sub-modules.
"""
import io
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
if not BASE.endswith("/api"):
    BASE = BASE + "/api"

ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}
PRO = {"email": "pro@construpilot.fr", "password": "Pro2026!"}


def _login(creds):
    r = requests.post(f"{BASE}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def pro_token():
    return _login(PRO)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ============ plans_crud ============

class TestPlansCrud:
    def test_list_takeoffs_200(self, admin_headers):
        r = requests.get(f"{BASE}/takeoffs", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "plans" in data
        assert isinstance(data["plans"], list)

    def test_upload_bad_file_no_500(self, admin_headers):
        # Un simple PNG factice — peut retourner 200 ou 4xx mais surtout pas 500
        fake_png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        files = {"file": ("test.png", io.BytesIO(fake_png), "image/png")}
        r = requests.post(f"{BASE}/takeoffs/upload",
                          headers=admin_headers, files=files, timeout=30)
        assert r.status_code < 500, f"upload crashed: {r.status_code} {r.text[:300]}"


# ============ plans_analysis ============

class TestPlansAnalysis:
    def test_measure_unknown_plan_404(self, admin_headers):
        r = requests.post(f"{BASE}/takeoffs/does-not-exist-xyz/measure",
                          headers=admin_headers,
                          json={"page_index": 0, "kind": "distance",
                                "points": [[0, 0], [10, 0]]}, timeout=15)
        assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text[:200]}"

    def test_compare_same_ids_400(self, admin_headers):
        r = requests.post(f"{BASE}/takeoffs/compare",
                          headers=admin_headers,
                          json={"before_plan_id": "same-id",
                                "after_plan_id": "same-id"},
                          timeout=15)
        # Selon l'ordre des checks, l'endpoint peut renvoyer 400 (validation
        # IDs identiques) ou 404 (plans introuvables). Le point clé : pas 500.
        assert r.status_code in (400, 404), \
            f"expected 400/404, got {r.status_code} {r.text[:200]}"


# ============ plans_render ============

class TestPlansRender:
    def test_render3d_admin_unknown_plan_404(self, admin_headers):
        r = requests.post(f"{BASE}/takeoffs/nonexistent-plan-id/render-3d",
                          headers=admin_headers, json={}, timeout=15)
        # Admin bypasse le gate pro_business → doit être 404 (plan introuvable)
        assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text[:200]}"


# ============ plans_export ============

class TestPlansExport:
    def test_pdf_unknown_plan_404(self, admin_headers):
        r = requests.get(f"{BASE}/takeoffs/nonexistent-xyz/pdf",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 404

    def test_quote_pdf_unknown_plan_404(self, admin_headers):
        r = requests.get(f"{BASE}/takeoffs/nonexistent-xyz/quote-pdf",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 404

    def test_send_quote_invalid_email(self, admin_headers):
        r = requests.post(f"{BASE}/takeoffs/nonexistent-xyz/send-quote",
                          headers=admin_headers,
                          json={"to_email": "not-an-email"}, timeout=15)
        # Doit renvoyer 400 (email invalide) ou 404 (plan inconnu) — jamais 500
        assert r.status_code in (400, 404, 422), \
            f"unexpected {r.status_code}: {r.text[:200]}"


# ============ quote_router ============

class TestQuoteRouter:
    def test_templates_200(self, admin_headers):
        r = requests.get(f"{BASE}/quotes/templates",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "templates" in data
        assert isinstance(data["templates"], list)

    def test_notifications_me_200(self, admin_headers):
        r = requests.get(f"{BASE}/quotes/notifications/me",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "unread" in data
        assert "notifications" in data

    def test_sends_all_200(self, admin_headers):
        r = requests.get(f"{BASE}/quotes/sends/all",
                         headers=admin_headers, timeout=15)
        assert r.status_code == 200


# ============ Public portals ============

class TestPublicPortals:
    def test_client_portal_bad_token_400(self):
        r = requests.get(f"{BASE}/quotes/client-portal/BADTOKEN", timeout=15)
        assert r.status_code == 400, f"expected 400 got {r.status_code}"

    def test_public_sign_nonexistent_404(self):
        r = requests.get(f"{BASE}/quotes/public/sign/nonexistent-token",
                         timeout=15)
        assert r.status_code == 404


# ============ monetization / billing ============

class TestBilling:
    def test_billing_checkout_valid_plan_no_500(self, admin_headers):
        # On récupère un plan payant depuis le catalogue si dispo
        r = requests.post(f"{BASE}/billing/checkout",
                          headers=admin_headers,
                          json={"plan_id": "pro_monthly",
                                "origin_url": "https://example.com"},
                          timeout=20)
        # 200 (checkout OK), 400 (plan free), 404 (plan introuvable), 502 (stripe indispo)
        # Le point clé : PAS 500 (crash de code)
        assert r.status_code != 500, f"checkout crashed: {r.text[:300]}"
        assert r.status_code in (200, 400, 404, 502), \
            f"unexpected status: {r.status_code} {r.text[:200]}"


# ============ calculators ============

class TestCalculators:
    def test_paint_calculator(self):
        r = requests.post(f"{BASE}/calculators/paint",
                          json={"params": {"length": 4, "width": 3,
                                            "height": 2.5, "doors": 1,
                                            "windows": 1, "coats": 2}},
                          timeout=15)
        assert r.status_code == 200, f"paint calc failed: {r.text[:200]}"
        data = r.json()
        assert "materials" in data or "inputs" in data

    def test_roof_facade_calculator(self):
        r = requests.post(f"{BASE}/calculators/roof_facade",
                          json={"params": {"projected_m2": 100,
                                            "pitch_deg": 30,
                                            "wall_perimeter_m": 40,
                                            "wall_height_m": 5.5,
                                            "openings_m2": 15,
                                            "ite_thickness_mm": 140}},
                          timeout=15)
        assert r.status_code == 200, f"roof_facade calc failed: {r.text[:200]}"
        data = r.json()
        assert "materials" in data


# ============ Regression iter52 critical endpoints ============

class TestIter52CriticalRegression:
    def test_landing_root(self):
        # frontend root via preview URL uniquement — sinon skip
        preview = os.environ.get("REACT_APP_BACKEND_URL", "")
        if not preview.startswith("http") or "localhost" in preview:
            pytest.skip("No preview URL configured")
        r = requests.get(preview.rstrip("/") + "/", timeout=15)
        assert r.status_code == 200

    def test_client_log(self):
        r = requests.post(f"{BASE}/errors/client-log",
                         json={"message": "TEST log", "url": "/test",
                               "user_agent": "pytest"}, timeout=10)
        assert r.status_code in (200, 204)

    def test_unsubscribe_bad_token(self):
        r = requests.get(f"{BASE}/emails/unsubscribe?token=BAD", timeout=10)
        assert r.status_code in (400, 404)

    def test_admin_leads(self, admin_headers):
        # Route possible : /admin/leads ou /admin/inbox
        r = requests.get(f"{BASE}/admin/leads", headers=admin_headers, timeout=15)
        if r.status_code == 404:
            r = requests.get(f"{BASE}/admin/inbox", headers=admin_headers, timeout=15)
        assert r.status_code == 200, f"admin leads/inbox failed: {r.status_code}"
