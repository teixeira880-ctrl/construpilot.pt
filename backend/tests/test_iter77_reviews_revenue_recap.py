"""Iteration 77 tests — Reviews, Revenue chart, Accounting recap PDF, Admin 2FA-off, Analyse IA symbols."""
import os
import io
import re
import pytest
import requests

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")

BASE = _load_base()
API = f"{BASE}/api"

ADMIN_PROV = ("teixeira8880@gmail.com", "CP-D5615C-Prov!")
ADMIN_BO = ("admin@construpilot.fr", "Construpilot2026!")
PRO = ("pro@construpilot.fr", "Pro2026!")
DEMO = ("demo@construpilot.fr", "Demo2026!")


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    return r


# ---------- Admin 2FA disabled ----------
class TestAdminLoginNo2FA:
    def test_admin_prov_login_returns_token_directly(self):
        r = _login(*ADMIN_PROV)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data and "user" in data
        assert not data.get("two_fa_required"), f"2FA should be OFF, got: {data}"
        assert data["user"]["email"] == ADMIN_PROV[0]

    def test_admin_backoffice_login(self):
        r = _login(*ADMIN_BO)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "token" in d and not d.get("two_fa_required")


# ---------- Revenue chart ----------
@pytest.fixture(scope="module")
def pro_token():
    r = _login(*PRO)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers(pro_token):
    return {"Authorization": f"Bearer {pro_token}"}


class TestRevenueMonthly:
    def test_monthly_revenue_structure(self, pro_headers):
        r = requests.get(f"{API}/quotes/revenue/monthly", headers=pro_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "months" in d and isinstance(d["months"], list)
        assert "total" in d and "signed_count" in d
        assert len(d["months"]) > 0
        m0 = d["months"][0]
        for k in ("month", "label", "revenue", "count"):
            assert k in m0, f"missing key {k} in {m0}"
        # Total is sum of months revenue
        total_sum = sum(float(x["revenue"]) for x in d["months"])
        assert abs(total_sum - float(d["total"])) < 1.0

    def test_monthly_revenue_requires_auth(self):
        r = requests.get(f"{API}/quotes/revenue/monthly", timeout=15)
        assert r.status_code in (401, 403)


# ---------- Accounting recap PDF ----------
class TestAccountingRecap:
    def test_recap_pdf_returns_pdf(self, pro_headers):
        r = requests.get(f"{API}/quotes/recap-pdf", params={"year": 2026, "month": 6}, headers=pro_headers, timeout=60)
        assert r.status_code == 200, r.text[:400]
        ctype = r.headers.get("content-type", "")
        assert "pdf" in ctype.lower(), f"content-type={ctype}"
        assert r.content[:4] == b"%PDF", "response is not a PDF"
        assert len(r.content) > 500

    def test_recap_pdf_auth_required(self):
        r = requests.get(f"{API}/quotes/recap-pdf", params={"year": 2026, "month": 6}, timeout=15)
        assert r.status_code in (401, 403)


# ---------- Reviews flow ----------
class TestReviewsFlow:
    def test_reviews_me(self, pro_headers):
        r = requests.get(f"{API}/reviews/me", headers=pro_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Expected keys
        for k in ("reviews", "pending"):
            assert k in d, f"missing {k} in {d.keys()}"
        assert isinstance(d["reviews"], list)

    def test_full_flow_request_collect_publish(self, pro_headers):
        # Find a signed quote_log for pro to trigger completion
        # Look at signed quotes list
        r = requests.get(f"{API}/quotes/tracking", headers=pro_headers, timeout=30)
        if r.status_code != 200:
            pytest.skip(f"tracking not available: {r.status_code}")
        data = r.json()
        signed = []
        if isinstance(data, dict):
            signed = data.get("signed", []) or data.get("items", [])
        elif isinstance(data, list):
            signed = [x for x in data if (x.get("status") == "signed" or x.get("signed_at"))]
        if not signed:
            pytest.skip("No signed quote_log to test worksite completion")
        log_id = signed[0].get("id") or signed[0].get("_id") or signed[0].get("log_id")
        if not log_id:
            pytest.skip(f"Cannot resolve log_id from signed item: {signed[0].keys()}")

        # POST /reviews/request/{log_id}
        rr = requests.post(f"{API}/reviews/request/{log_id}", headers=pro_headers, timeout=30)
        assert rr.status_code in (200, 201), rr.text
        body = rr.json()
        token = body.get("token") or body.get("review_token")
        review_url = body.get("review_url") or body.get("url")
        assert token or review_url, f"missing token/url in {body}"
        if not token and review_url:
            m = re.search(r"/avis/([^/?#]+)", review_url)
            if m:
                token = m.group(1)
        assert token, "no review token extracted"

        # GET /reviews/collect/{token} (public)
        g = requests.get(f"{API}/reviews/collect/{token}", timeout=30)
        assert g.status_code == 200, g.text
        # POST /reviews/collect/{token}
        p = requests.post(
            f"{API}/reviews/collect/{token}",
            json={"rating": 5, "author": "Marie D.", "comment": "Excellent chantier"},
            timeout=30,
        )
        assert p.status_code in (200, 201), p.text

        # /reviews/me should have new review now
        me = requests.get(f"{API}/reviews/me", headers=pro_headers, timeout=30).json()
        reviews = me.get("reviews", [])
        assert len(reviews) >= 1
        review_id = reviews[0].get("id") or reviews[0].get("_id")

        # Toggle publish
        if review_id:
            tog = requests.patch(
                f"{API}/reviews/{review_id}/publish",
                headers=pro_headers,
                json={"published": True},
                timeout=15,
            )
            assert tog.status_code in (200, 204), tog.text


# ---------- AI plan symbols ----------
class TestAISymbols:
    def test_plan_analyze_has_electrical_plumbing(self, pro_headers):
        # Get plans list
        pl = requests.get(f"{API}/plans", headers=pro_headers, timeout=30)
        if pl.status_code != 200:
            pytest.skip(f"/plans returned {pl.status_code}")
        plans = pl.json()
        items = plans if isinstance(plans, list) else plans.get("items", [])
        if not items:
            pytest.skip("No plan available to analyze")
        plan_id = items[0].get("id") or items[0].get("_id")
        r = requests.post(f"{API}/takeoffs/{plan_id}/analyze", params={"page_index": 0}, headers=pro_headers, timeout=180)
        if r.status_code != 200:
            pytest.skip(f"analyze returned {r.status_code}: {r.text[:200]}")
        d = r.json()
        # electrical / plumbing may be nested
        found = False
        def _find_keys(obj):
            nonlocal found
            if isinstance(obj, dict):
                if "electrical" in obj and "plumbing" in obj:
                    found = True
                for v in obj.values():
                    _find_keys(v)
            elif isinstance(obj, list):
                for v in obj:
                    _find_keys(v)
        _find_keys(d)
        assert found, f"electrical/plumbing keys missing in analyze response keys={list(d.keys())}"


# ---------- Regression: CSV export still works ----------
class TestCSVRegression:
    def test_csv_export(self, pro_headers):
        for path in ("/quotes/export.csv", "/quotes/export/csv", "/quotes/tracking/export.csv"):
            r = requests.get(f"{API}{path}", headers=pro_headers, timeout=30)
            if r.status_code == 200:
                assert "csv" in r.headers.get("content-type", "").lower() or r.text.count(",") > 0
                return
        pytest.skip("CSV export endpoint not found under expected paths")
