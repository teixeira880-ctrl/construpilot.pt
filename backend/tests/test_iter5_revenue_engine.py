"""Backend tests for Iter 5 — Revenue Engine (Stripe + PDF quote support).

Covers:
- POST /api/quotes/analyse with pdf_base64 (text + scan fallback)
- GET /api/plans (+ audience filter, flags)
- POST /api/billing/checkout (auth + errors)
- GET /api/billing/status/{session_id}
- GET /api/billing/me (auth)
- GET /api/billing/flags (public)
- Admin plans / feature-flags / sync-stripe / revenue + RBAC 403 for non-admin
"""
import base64
import io
import os

import pytest
import requests
from pypdf import PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")

ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}
DEMO = {"email": "demo@construpilot.fr", "password": "Demo2026!"}


# ---------- Fixtures ----------

@pytest.fixture(scope="module")
def s():
    return requests.Session()


@pytest.fixture(scope="module")
def admin_headers(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def user_headers(s):
    r = s.post(f"{BASE_URL}/api/auth/login", json=DEMO, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _make_pdf_with_text(text: str) -> str:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.split("\n"):
        c.drawString(50, y, line)
        y -= 15
    c.save()
    return base64.b64encode(buf.getvalue()).decode()


def _make_empty_pdf() -> str:
    w = PdfWriter()
    w.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    w.write(buf)
    return base64.b64encode(buf.getvalue()).decode()


# ---------- PDF Quotes ----------

class TestPdfQuote:
    def test_pdf_with_text_ok(self, s):
        txt = ("Entreprise Dupont BTP\nDevis N° 2026-042\n"
               "Renovation salle de bain - 5 m2\n"
               "Ligne 1: Depose carrelage 300 EUR\n"
               "Ligne 2: Pose faience 950 EUR\n"
               "Ligne 3: Plomberie 1200 EUR\n"
               "Ligne 4: Electricite 450 EUR\n"
               "Total HT: 2900 EUR\nTVA 10 pourcent: 290 EUR\n"
               "Total TTC: 3190 EUR\nGarantie decennale incluse.")
        pdf = _make_pdf_with_text(txt)
        r = s.post(f"{BASE_URL}/api/quotes/analyse",
                   json={"pdf_base64": pdf, "company": "Dupont BTP"}, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "quote_id" in data
        analysis = data["analysis"]
        assert len(analysis.get("lines", [])) >= 1
        assert analysis.get("total_ttc") or analysis.get("total_ht")
        assert "verdict" in analysis

    def test_pdf_empty_returns_422(self, s):
        pdf = _make_empty_pdf()
        r = s.post(f"{BASE_URL}/api/quotes/analyse",
                   json={"pdf_base64": pdf}, timeout=30)
        assert r.status_code == 422, r.text
        detail = r.json().get("detail", "")
        # message en français
        assert any(w in detail.lower() for w in ["pdf", "scan", "texte"])


# ---------- Plans ----------

class TestPlans:
    def test_list_all(self, s):
        r = s.get(f"{BASE_URL}/api/plans", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d["plans"]) == 8
        # tri par sort_order
        so = [p["sort_order"] for p in d["plans"]]
        assert so == sorted(so)
        flags = d["flags"]
        assert flags["trial_enabled"] is True
        assert flags["trial_days"] == 7
        assert flags["paywall_mode"] == "soft"

    def test_pro_audience(self, s):
        r = s.get(f"{BASE_URL}/api/plans?audience=pro", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d["plans"]) == 4
        assert all(p["audience"] == "pro" for p in d["plans"])

    def test_particulier_audience(self, s):
        r = s.get(f"{BASE_URL}/api/plans?audience=particulier", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert len(d["plans"]) == 4
        assert all(p["audience"] == "particulier" for p in d["plans"])

    def test_stripe_ids_populated(self, s):
        r = s.get(f"{BASE_URL}/api/plans", timeout=15).json()
        paid = [p for p in r["plans"] if p["kind"] != "free"]
        assert len(paid) == 7
        for p in paid:
            assert p.get("stripe_product_id"), f"{p['plan_id']} missing product id"
            assert p.get("stripe_price_id"), f"{p['plan_id']} missing price id"


# ---------- Checkout ----------

class TestCheckout:
    def test_checkout_project_pass(self, s, user_headers):
        r = s.post(f"{BASE_URL}/api/billing/checkout",
                   headers=user_headers,
                   json={"plan_id": "project_pass",
                         "origin_url": "https://example.com"}, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["url"].startswith("https://checkout.stripe.com")
        assert d["session_id"]
        # verify status endpoint
        st = s.get(f"{BASE_URL}/api/billing/status/{d['session_id']}", timeout=15)
        assert st.status_code == 200
        assert st.json()["payment_status"] == "pending"

    def test_checkout_premium_subscription(self, s, user_headers):
        r = s.post(f"{BASE_URL}/api/billing/checkout",
                   headers=user_headers,
                   json={"plan_id": "premium_monthly",
                         "origin_url": "https://example.com"}, timeout=45)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["url"].startswith("https://checkout.stripe.com")
        st = s.get(f"{BASE_URL}/api/billing/status/{d['session_id']}", timeout=15).json()
        assert st["mode"] == "subscription"

    def test_checkout_unknown_plan(self, s, user_headers):
        r = s.post(f"{BASE_URL}/api/billing/checkout",
                   headers=user_headers,
                   json={"plan_id": "nope", "origin_url": "https://example.com"}, timeout=15)
        assert r.status_code == 404

    def test_checkout_free_rejected(self, s, user_headers):
        r = s.post(f"{BASE_URL}/api/billing/checkout",
                   headers=user_headers,
                   json={"plan_id": "free", "origin_url": "https://example.com"}, timeout=15)
        assert r.status_code == 400

    def test_status_unknown_session(self, s):
        r = s.get(f"{BASE_URL}/api/billing/status/cs_test_unknown_xxx", timeout=15)
        assert r.status_code == 404


# ---------- Billing self ----------

class TestBillingMe:
    def test_me_requires_auth(self):
        # fresh session to avoid session cookies from other tests
        r = requests.get(f"{BASE_URL}/api/billing/me", timeout=15)
        assert r.status_code in (401, 403)

    def test_me_free_user(self, s, user_headers):
        r = s.get(f"{BASE_URL}/api/billing/me", headers=user_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["tier"] == "free"
        assert d["active"] is None
        assert isinstance(d["history"], list)

    def test_flags_public(self, s):
        r = s.get(f"{BASE_URL}/api/billing/flags", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["trial_enabled"] is True
        assert d["trial_days"] == 7
        assert d["paywall_mode"] == "soft"


# ---------- Admin ----------

class TestAdmin:
    def test_admin_plans_list(self, s, admin_headers):
        r = s.get(f"{BASE_URL}/api/admin/plans", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        assert len(r.json()) == 8

    def test_admin_upsert_plan(self, s, admin_headers):
        # Get free plan and re-upsert (idempotent)
        plans = s.get(f"{BASE_URL}/api/admin/plans", headers=admin_headers).json()
        free = next(p for p in plans if p["plan_id"] == "free")
        # only pass fields present in PlanIn
        allowed = {"plan_id", "code", "name", "tagline", "description", "audience", "kind",
                   "amount_cents", "currency", "interval", "lookup_key", "trial_days",
                   "features", "quotas", "sort_order", "active", "highlight", "badge"}
        payload = {k: v for k, v in free.items() if k in allowed}
        payload["tagline"] = "Découvrez ConstruPilot (test)"
        r = s.post(f"{BASE_URL}/api/admin/plans", headers=admin_headers, json=payload, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["tagline"] == "Découvrez ConstruPilot (test)"

    def test_admin_feature_flags(self, s, admin_headers):
        r = s.get(f"{BASE_URL}/api/admin/feature-flags", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        flags = r.json()
        assert flags.get("paywall_mode") == "soft"
        # PUT (identity)
        r2 = s.put(f"{BASE_URL}/api/admin/feature-flags",
                   headers=admin_headers, json=flags, timeout=15)
        assert r2.status_code == 200

    def test_admin_sync_stripe(self, s, admin_headers):
        r = s.post(f"{BASE_URL}/api/admin/plans/sync-stripe",
                   headers=admin_headers, timeout=120)
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_admin_revenue(self, s, admin_headers):
        r = s.get(f"{BASE_URL}/api/admin/revenue", headers=admin_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "total_revenue_cents" in d
        assert d["total_revenue_cents"] == 0

    def test_non_admin_403(self, s, user_headers):
        for path in ["/api/admin/plans", "/api/admin/feature-flags", "/api/admin/revenue"]:
            r = s.get(f"{BASE_URL}{path}", headers=user_headers, timeout=15)
            assert r.status_code == 403, f"{path} → {r.status_code}"
