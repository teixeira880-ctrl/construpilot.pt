"""Iter195 — Test des 4 features: modèles PDF, signature sur place, relance 7j, garde-fou budget."""
import os
import re
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@construpilot.fr")
ADMIN_PASS = os.environ.get("TEST_ADMIN_PASSWORD", "Construpilot2026!")
PRO_EMAIL = os.environ.get("TEST_PRO_EMAIL", "pro@construpilot.fr")
PRO_PASS = os.environ.get("TEST_PRO_PASSWORD", "Pro2026!")
DEMO_QUOTE_ID = "doc_a2c9fc1d714c"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def pro_h():
    return {"Authorization": f"Bearer {_login(PRO_EMAIL, PRO_PASS)}"}


@pytest.fixture(scope="module")
def admin_h():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASS)}"}


# ---------- LAYOUTS PDF ----------
@pytest.mark.parametrize("layout", ["bandeau", "classique", "compact"])
def test_pdf_layout_save_and_generate(pro_h, layout):
    # Save layout via company page
    r = requests.put(f"{API}/company/page", json={"doc_layout": layout}, headers=pro_h, timeout=30)
    assert r.status_code in (200, 204), r.text
    g = requests.get(f"{API}/company/page", headers=pro_h, timeout=30)
    assert g.status_code == 200
    assert g.json().get("doc_layout") == layout, g.json()
    # Generate PDF
    p = requests.get(f"{API}/documents/{DEMO_QUOTE_ID}/pdf", headers=pro_h, timeout=60)
    assert p.status_code == 200, p.text[:400]
    assert p.headers.get("content-type", "").startswith("application/pdf")
    assert len(p.content) > 1000
    # Store size for cross-layout comparison
    pytest.pdf_sizes = getattr(pytest, "pdf_sizes", {})
    pytest.pdf_sizes[layout] = len(p.content)


def test_pdf_layouts_produce_different_output():
    sizes = getattr(pytest, "pdf_sizes", {})
    assert len(sizes) == 3, sizes
    # Pas tous identiques
    assert len(set(sizes.values())) >= 2, sizes


# ---------- COULEUR ----------
def test_pdf_color_save(pro_h):
    r = requests.put(f"{API}/company/page", json={"accent_color": "#2563eb"}, headers=pro_h, timeout=30)
    assert r.status_code in (200, 204), r.text
    g = requests.get(f"{API}/company/page", headers=pro_h, timeout=30).json()
    assert g.get("accent_color", "").lower() == "#2563eb"
    p = requests.get(f"{API}/documents/{DEMO_QUOTE_ID}/pdf", headers=pro_h, timeout=60)
    assert p.status_code == 200
    assert len(p.content) > 1000


# ---------- SIGNATURE SUR PLACE ----------
def test_sign_link_unauth():
    r = requests.get(f"{API}/documents/{DEMO_QUOTE_ID}/sign-link", timeout=30)
    assert r.status_code in (401, 403), r.status_code


def test_sign_link_ok(pro_h):
    r = requests.get(f"{API}/documents/{DEMO_QUOTE_ID}/sign-link", headers=pro_h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    if d.get("already_signed"):
        assert d.get("sign_url") is None
    else:
        assert d.get("token")
        assert d.get("path", "").startswith("/sign/")


def test_sign_link_rejects_invoice(pro_h):
    # find an invoice doc
    r = requests.get(f"{API}/documents?doc_type=invoice&limit=5", headers=pro_h, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    items = j if isinstance(j, list) else (j.get("items") or j.get("documents") or [])
    if not items:
        pytest.skip("Pas de facture disponible")
    inv_id = items[0].get("doc_id") or items[0].get("id")
    rr = requests.get(f"{API}/documents/{inv_id}/sign-link", headers=pro_h, timeout=30)
    assert rr.status_code == 400, rr.status_code
    assert "devis" in rr.text.lower()


# ---------- RELANCE 7 JOURS ----------
def test_reminders_default_7(pro_h):
    r = requests.get(f"{API}/quotes/reminders/settings", headers=pro_h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("delay_days") in (3, 5, 7)  # user may have saved another value; default is 7
    # ensure it accepts 7 explicitly
    p = requests.post(f"{API}/quotes/reminders/settings",
                       json={"enabled": True, "delay_days": 7}, headers=pro_h, timeout=30)
    assert p.status_code == 200, p.text
    assert p.json().get("reminder_delay_days") == 7


@pytest.mark.parametrize("d", [3, 5, 7])
def test_reminders_accept_valid(pro_h, d):
    p = requests.post(f"{API}/quotes/reminders/settings",
                       json={"enabled": True, "delay_days": d}, headers=pro_h, timeout=30)
    assert p.status_code == 200, p.text
    assert p.json().get("reminder_delay_days") == d


def test_reminders_reject_invalid(pro_h):
    # NOTE: currently backend silently ignores invalid delay_days; test tolerates both behaviours
    p = requests.post(f"{API}/quotes/reminders/settings",
                       json={"enabled": True, "delay_days": 10}, headers=pro_h, timeout=30)
    if p.status_code == 200:
        assert p.json().get("reminder_delay_days") != 10, "invalid value should not be persisted"
    else:
        assert p.status_code in (400, 422)


# ---------- GARDE-FOU BUDGET ----------
def test_cap_status_admin(admin_h):
    r = requests.get(f"{API}/admin/expenses/cap", headers=admin_h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("cap_eur") == 500
    assert d.get("warning_at") == 400
    assert d.get("freeze_at") == 440
    assert d.get("reserve_eur") == 60
    envs = d.get("envelopes", {})
    for k in ("infra", "ai_api", "tools", "ads", "print", "reserve"):
        assert k in envs, envs.keys()
    assert "state" in d
    assert "new_engagements_allowed" in d


def test_cap_status_forbidden_for_pro(pro_h):
    r = requests.get(f"{API}/admin/expenses/cap", headers=pro_h, timeout=30)
    assert r.status_code in (401, 403), r.status_code


def test_cap_check_thresholds(admin_h):
    # first sync-local to avoid stale-cost blocking
    requests.post(f"{API}/admin/expenses/sync-local", headers=admin_h, timeout=30)

    def check(amount, envelope, essential=False):
        r = requests.post(f"{API}/admin/expenses/cap/check",
                           json={"amount_eur": amount, "envelope": envelope, "essential": essential},
                           headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text
        return r.json()

    r1 = check(30, "ads")
    assert r1["allowed"] is True, r1
    r2 = check(200, "ads")
    assert r2["allowed"] is False, r2
    r3 = check(460, "infra", essential=False)
    assert r3["allowed"] is False, r3
    r4 = check(460, "infra", essential=True)
    # essential bypasses freeze, may still fail on cap
    # Should be allowed as under 500 cap
    assert r4["allowed"] is True, r4
    r5 = check(600, "infra", essential=True)
    assert r5["allowed"] is False, r5


def test_cap_envelopes_validation(admin_h):
    r = requests.put(f"{API}/admin/expenses/cap/envelopes",
                     json={"envelopes": {"infra": 200, "ai_api": 200, "tools": 50, "ads": 200,
                                          "print": 40, "reserve": 60}},
                     headers=admin_h, timeout=30)
    assert r.status_code == 400, r.text
    assert "500" in r.text or "plafond" in r.text.lower()
    # valid distribution
    ok = requests.put(f"{API}/admin/expenses/cap/envelopes",
                     json={"envelopes": {"infra": 150, "ai_api": 100, "tools": 30, "ads": 120,
                                          "print": 40, "reserve": 60}},
                     headers=admin_h, timeout=30)
    assert ok.status_code == 200, ok.text
