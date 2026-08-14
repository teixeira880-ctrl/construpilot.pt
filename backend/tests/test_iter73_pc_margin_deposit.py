"""Iter 73 — Test 4 new PC features: Margin 30% pro, Stripe deposit, team share, weekly report."""
import os
import time
import pytest
import requests

def _fe_env():
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip()
    except Exception:
        return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe_env() or "").rstrip("/")
assert BASE_URL

try:
    from tests.creds import ADMIN, CLIENT, COLLEGUE, PRO
except ImportError:
    from creds import ADMIN, CLIENT, COLLEGUE, PRO

PLAN_ID = "plan_6696782f92ca"
TOKEN = "pcs_e2a4c343ca79d96e"


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": creds[0], "password": creds[1]}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    tok = j.get("access_token") or j.get("token")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def pro_h():
    return _login(PRO)


@pytest.fixture(scope="module")
def col_h():
    return _login(COLLEGUE)


@pytest.fixture(scope="module")
def cli_h():
    return _login(CLIENT)


@pytest.fixture(scope="module")
def adm_h():
    return _login(ADMIN)


# --- 1) GET /api/pc/settings defaults --------------------------------------

def test_pc_settings_defaults(pro_h):
    r = requests.get(f"{BASE_URL}/api/pc/settings", headers=pro_h, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()["defaults"]
    assert d["margin_pct"] == 30
    assert d["deposit_pct"] == 30
    assert d["weekly_report"] == True
    assert d["team_share"] == True
    assert d["hourly_rate_eur"] == 35
    assert len(d["unit_prices"]) == 21


# --- 2) PUT settings margin 40 -> recompute -> restore ---------------------

def test_margin_change_and_restore(pro_h):
    # Set to 40
    r = requests.put(f"{BASE_URL}/api/pc/settings", headers=pro_h,
                     json={"margin_pct": 40}, timeout=30)
    assert r.status_code == 200, r.text
    # Recompute
    r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/recompute",
                      headers=pro_h, timeout=60)
    assert r.status_code == 200, r.text
    totals = (r.json().get("study") or r.json())["totals"]
    assert abs(totals["marge_pct"] - 40) < 0.5, totals
    cout_ht = totals.get("cout_ht") or totals.get("cost_ht")
    assert cout_ht and abs(totals["ht"] - cout_ht * 1.4) / totals["ht"] < 0.01, totals
    assert totals.get("marge_eur", 0) > 0

    # Restore 30
    r = requests.put(f"{BASE_URL}/api/pc/settings", headers=pro_h,
                     json={"margin_pct": 30, "deposit_pct": 30}, timeout=30)
    assert r.status_code == 200
    r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/recompute",
                      headers=pro_h, timeout=60)
    assert r.status_code == 200
    t2 = (r.json().get("study") or r.json())["totals"]
    assert abs(t2["marge_pct"] - 30) < 0.5


# --- 3) Public sign GET hides cost/margin ---------------------------------

def test_public_sign_hides_cost():
    r = requests.get(f"{BASE_URL}/api/pc/sign/{TOKEN}", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    totals = body.get("totals") or body.get("study", {}).get("totals") or {}
    # It must contain public keys
    for k in ("ht", "tva", "ttc"):
        assert k in totals, (k, list(totals.keys()))
    # And must NOT contain private ones
    for forbidden in ("cout_ht", "marge_eur", "marge_pct", "cost_ht"):
        assert forbidden not in totals, f"leak: {forbidden}"
    dep = body.get("deposit") or {}
    assert dep.get("pct") == 30
    assert (dep.get("amount") or 0) > 0
    # paid may be True from previous E2E — accept both
    assert "paid" in dep


# --- 4) Stripe deposit checkout & status ----------------------------------

def test_deposit_checkout_and_status():
    # First check if already paid
    r0 = requests.get(f"{BASE_URL}/api/pc/sign/{TOKEN}", timeout=30)
    already_paid = (r0.json().get("deposit") or {}).get("paid")
    if already_paid:
        pytest.skip("deposit already paid on this token — skipping new checkout")

    r = requests.post(f"{BASE_URL}/api/pc/sign/{TOKEN}/deposit/checkout",
                      json={"origin_url": BASE_URL}, timeout=45)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "checkout.stripe.com" in j.get("url", "")
    assert j.get("session_id", "").startswith("cs_")
    assert (j.get("amount") or 0) > 0

    r2 = requests.get(f"{BASE_URL}/api/pc/deposit/status/{j['session_id']}",
                      timeout=30)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("payment_status") in ("pending", "unpaid", "paid")


# --- 6) Team share -------------------------------------------------------

def test_team_share_collegue_sees_pro_studies(col_h):
    r = requests.get(f"{BASE_URL}/api/pc/dashboard", headers=col_h, timeout=30)
    assert r.status_code == 200, r.text
    rows = r.json().get("rows") or r.json().get("studies") or []
    assert len(rows) >= 1
    marc = [x for x in rows if (x.get("owner_name") or "").startswith("Marc")]
    assert len(marc) >= 1, [r.get("owner_name") for r in rows]
    for r_ in marc:
        assert r_.get("is_own") == False


def test_team_share_collegue_access_study(col_h):
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study",
                     headers=col_h, timeout=30)
    assert r.status_code == 200, r.text


def test_client_outside_org_cannot_access(cli_h):
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study",
                     headers=cli_h, timeout=30)
    assert r.status_code == 404


# --- 7) Weekly report ----------------------------------------------------

def test_weekly_report_send_me(pro_h):
    r = requests.post(f"{BASE_URL}/api/pc/weekly-report/send-me",
                      headers=pro_h, timeout=60)
    # 503 (Resend sandbox) acceptable
    if r.status_code == 503:
        pytest.skip("Resend sandbox 503 — non blocking")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("ok") == True
    assert (j.get("studies") or 0) >= 1


def test_weekly_report_admin_run(adm_h):
    r = requests.post(f"{BASE_URL}/api/pc/weekly-report/run",
                      headers=adm_h, timeout=90)
    if r.status_code == 503:
        pytest.skip("Resend sandbox 503")
    assert r.status_code == 200, r.text
    assert (r.json().get("sent") or 0) >= 1


# --- Regression exports ---------------------------------------------------

def test_export_pdf(pro_h):
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/pdf",
                     headers=pro_h, timeout=60)
    assert r.status_code == 200
    assert len(r.content) > 500


def test_export_docx(pro_h):
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/docx",
                     headers=pro_h, timeout=60)
    assert r.status_code == 200
    assert len(r.content) > 500


def test_purchase_order_pdf(pro_h):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_ID}/pc-study/purchase-order?level=1",
        headers=pro_h, timeout=60)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"
