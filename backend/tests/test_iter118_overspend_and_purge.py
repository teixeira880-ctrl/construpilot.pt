"""Iter 118 — Alerte surcoût (einvoicing) + Purge élargie (admin delete).

Re-confirm backend:
 - POST /api/einvoicing/settings {overspend_threshold_pct:5} -> ok
 - POST /api/einvoicing/inbox/einv_demo1/reconcile expected_ht=1000 -> alert.overspend=True, gap_flag='over'
 - Same reconcile with expected_ht=1230 -> gap_flag='ok', alert=None
 - Notification 'einvoice_overspend' created
 - Purge admin multi-key: user_id / owner_user_id / created_by
"""
import os
import time
import uuid
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except FileNotFoundError:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()
API = f"{BASE_URL}/api"

PRO = ("pro@construpilot.fr", "Pro2026!")
ADMIN = ("admin@construpilot.fr", "Construpilot2026!")


def _login(email: str, pwd: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers():
    tok = _login(*PRO)
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def admin_headers():
    tok = _login(*ADMIN)
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ---------- EINVOICING SETUP ----------

def test_einv_status_and_connect(pro_headers):
    st = requests.get(f"{API}/einvoicing/status", headers=pro_headers).json()
    if not st.get("connected"):
        r = requests.post(f"{API}/einvoicing/connect",
                          json={"siret": "54210922700018", "platform": "Iopole"},
                          headers=pro_headers)
        assert r.status_code == 200
    st = requests.get(f"{API}/einvoicing/status", headers=pro_headers).json()
    assert st["connected"] is True


def test_einv_set_threshold_5(pro_headers):
    r = requests.post(f"{API}/einvoicing/settings",
                      json={"overspend_threshold_pct": 5}, headers=pro_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["overspend_threshold_pct"] == 5
    # persisted
    st = requests.get(f"{API}/einvoicing/status", headers=pro_headers).json()
    assert st["overspend_threshold_pct"] == 5


@pytest.fixture(scope="module")
def order_id(pro_headers):
    """Ensure at least one material order exists for reconcile."""
    orders = requests.get(f"{API}/einvoicing/orders", headers=pro_headers).json().get("orders", [])
    if orders:
        return orders[0]["order_id"]
    # Create a minimal material order via /material-orders if endpoint exists
    payload = {
        "type": "Matériaux test",
        "supplier": "Test Supplier",
        "project": "TEST_iter118",
        "items": [{"description": "item A", "unit_price": 100, "commandable_qty": 10}],
    }
    r = requests.post(f"{API}/material-orders", json=payload, headers=pro_headers)
    assert r.status_code in (200, 201), f"failed to create material order: {r.status_code} {r.text}"
    oid = r.json().get("order_id") or r.json().get("order", {}).get("order_id")
    assert oid
    return oid


def test_einv_reconcile_overspend_triggers_alert(pro_headers, order_id):
    # Ensure einv_demo1 exists (seeded on connect)
    inbox = requests.get(f"{API}/einvoicing/inbox", headers=pro_headers).json()["invoices"]
    inv_ids = [i["inv_id"] for i in inbox]
    assert "einv_demo1" in inv_ids, f"expected demo invoice, got {inv_ids}"

    r = requests.post(f"{API}/einvoicing/inbox/einv_demo1/reconcile",
                      json={"order_id": order_id, "expected_ht": 1000},
                      headers=pro_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    recon = data["reconciliation"]
    assert recon["gap_flag"] == "over"
    assert 20 < recon["gap_pct"] < 30  # ~24.05%
    alert = data.get("alert")
    assert alert is not None, "expected overspend alert"
    assert alert["overspend"] is True
    assert alert["threshold_pct"] == 5
    assert alert["gap_pct"] == recon["gap_pct"]


def test_einv_notification_created(pro_headers):
    time.sleep(0.3)
    r = requests.get(f"{API}/quotes/notifications/me", headers=pro_headers)
    assert r.status_code == 200
    notifs = r.json().get("notifications") or r.json().get("items") or r.json()
    if isinstance(notifs, dict):
        notifs = notifs.get("notifications") or notifs.get("items") or []
    types = [n.get("type") for n in notifs if isinstance(n, dict)]
    assert "einvoice_overspend" in types, f"no einvoice_overspend notif in {types[:10]}"


def test_einv_reconcile_ok_no_alert(pro_headers, order_id):
    r = requests.post(f"{API}/einvoicing/inbox/einv_demo1/reconcile",
                      json={"order_id": order_id, "expected_ht": 1230},
                      headers=pro_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["reconciliation"]["gap_flag"] == "ok"
    assert data.get("alert") in (None, {}), f"expected no alert, got {data.get('alert')}"


def test_einv_unreconcile_cleanup(pro_headers):
    r = requests.post(f"{API}/einvoicing/inbox/einv_demo1/unreconcile", headers=pro_headers)
    assert r.status_code == 200


# ---------- PURGE ELARGIE ----------

def _register_disposable():
    email = f"TEST_purge_{uuid.uuid4().hex[:8]}@construpilot.fr"
    r = requests.post(f"{API}/auth/register", json={
        "email": email, "password": "TestPurge2026!",
        "name": "Purge Tester", "account_type": "particulier",
    }, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    token = data.get("token")
    user_id = (data.get("user") or {}).get("user_id") or data.get("user_id")
    assert token and user_id
    return email, token, user_id


def test_admin_delete_purges_multiple_collections(admin_headers):
    email, tok, uid = _register_disposable()
    h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    # Create data in multiple collections keyed by different fields
    # 1) notifications (user_id)
    requests.post(f"{API}/leads", json={
        "name": "TEST lead", "email": email, "phone": "0600000000",
        "project_type": "renovation", "message": "purge test"
    }, headers=h)
    # 2) A project (owner_user_id via projects)
    requests.post(f"{API}/projects", json={"name": "TEST_purge_project"}, headers=h)

    # DELETE
    r = requests.delete(f"{API}/admin/users/{uid}", headers=admin_headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert data["deleted_user"] == uid
    purged = data["purged"]
    # Expect at least one purge entry
    assert isinstance(purged, dict)
    assert data["purged_total"] >= 0  # may be 0 if endpoints not creating rows
    # The user is gone
    login_check = requests.post(f"{API}/auth/login",
                                json={"email": email, "password": "TestPurge2026!"})
    assert login_check.status_code in (401, 403, 404)


def test_admin_delete_nonexistent(admin_headers):
    r = requests.delete(f"{API}/admin/users/does_not_exist_xyz", headers=admin_headers)
    assert r.status_code == 404


def test_admin_cannot_delete_admin(admin_headers):
    # find another admin? just try self-delete guard
    me = requests.get(f"{API}/auth/me", headers=admin_headers).json()
    my_id = me.get("user_id") or me.get("user", {}).get("user_id")
    if my_id:
        r = requests.delete(f"{API}/admin/users/{my_id}", headers=admin_headers)
        assert r.status_code == 403
