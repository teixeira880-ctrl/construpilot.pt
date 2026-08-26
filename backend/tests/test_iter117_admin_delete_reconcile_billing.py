"""Iter 117 — Admin suppression, mark-viewed leads, reconcile e-invoices, billing checkout."""
import os
import uuid
import pytest
import requests

from dotenv import load_dotenv
load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PWD = "Construpilot2026!"
PRO_EMAIL = "pro@construpilot.fr"
PRO_PWD = "Pro2026!"
CLIENT_EMAIL = "client@construpilot.fr"
CLIENT_PWD = "Client2026!"


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture(scope="module")
def pro_token():
    return _login(PRO_EMAIL, PRO_PWD)


@pytest.fixture(scope="module")
def client_token():
    return _login(CLIENT_EMAIL, CLIENT_PWD)


# ============ Admin suppression ============

class TestAdminDelete:
    def test_register_then_delete_and_purge(self, admin_token):
        # Create a disposable particulier
        suffix = uuid.uuid4().hex[:8]
        email = f"TEST_del_{suffix}@construpilot.fr"
        r = requests.post(f"{API}/auth/register", json={
            "email": email, "password": "TempPwd2026!", "name": "Test Delete",
            "account_type": "particulier"
        }, timeout=15)
        assert r.status_code in (200, 201), r.text
        data = r.json()
        uid = (data.get("user") or {}).get("user_id") or (data.get("user") or {}).get("id")
        if not uid:
            r2 = requests.get(f"{API}/admin/users", headers=_h(admin_token), timeout=15)
            assert r2.status_code == 200
            users = r2.json()
            target = next((u for u in users if (u.get("email") or "").lower() == email.lower()), None)
            assert target, "created user not found in admin list"
            uid = target["user_id"]
        # sanity: not admin
        r_list = requests.get(f"{API}/admin/users", headers=_h(admin_token), timeout=15)
        target = next((u for u in r_list.json() if u.get("user_id") == uid), None)
        assert target and target.get("role") != "admin"

        # DELETE
        r3 = requests.delete(f"{API}/admin/users/{uid}", headers=_h(admin_token), timeout=30)
        assert r3.status_code == 200, r3.text
        body = r3.json()
        assert body.get("ok") is True
        assert body.get("deleted_user") == uid
        assert "purged" in body and "purged_total" in body

        # Verify no longer in list
        r4 = requests.get(f"{API}/admin/users", headers=_h(admin_token), timeout=15)
        assert not any(u.get("user_id") == uid for u in r4.json())

    def test_delete_admin_forbidden(self, admin_token):
        r = requests.get(f"{API}/admin/users", headers=_h(admin_token), timeout=15)
        admin_target = next((u for u in r.json()
                             if u.get("role") == "admin" and u.get("email") != ADMIN_EMAIL), None)
        if not admin_target:
            pytest.skip("no other admin to test against")
        r2 = requests.delete(f"{API}/admin/users/{admin_target['user_id']}",
                             headers=_h(admin_token), timeout=15)
        assert r2.status_code == 403

    def test_delete_self_forbidden(self, admin_token):
        me = requests.get(f"{API}/auth/me", headers=_h(admin_token), timeout=15).json()
        uid = me.get("user_id") or me.get("id")
        r = requests.delete(f"{API}/admin/users/{uid}", headers=_h(admin_token), timeout=15)
        assert r.status_code == 403

    def test_delete_requires_admin(self, client_token):
        # Find any user id — use own
        me = requests.get(f"{API}/auth/me", headers=_h(client_token), timeout=15).json()
        uid = me.get("user_id") or me.get("id")
        r = requests.delete(f"{API}/admin/users/{uid}", headers=_h(client_token), timeout=15)
        assert r.status_code == 403


# ============ Leads mark-viewed ============

class TestLeadsMarkViewed:
    def test_mark_viewed(self, client_token):
        r = requests.post(f"{API}/leads/mine/mark-viewed",
                          headers=_h(client_token), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert "marked" in body

        # GET /leads/mine should return leads (possibly empty) with viewed field on any existing
        r2 = requests.get(f"{API}/leads/mine", headers=_h(client_token), timeout=15)
        assert r2.status_code == 200
        leads = r2.json()
        assert isinstance(leads, list)
        for lead in leads:
            assert lead.get("viewed") is True

    def test_mark_viewed_requires_auth(self):
        r = requests.post(f"{API}/leads/mine/mark-viewed", timeout=15)
        assert r.status_code in (401, 403)


# ============ E-invoicing reconcile ============

class TestReconcile:
    def test_orders_pro(self, pro_token):
        r = requests.get(f"{API}/einvoicing/orders", headers=_h(pro_token), timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "orders" in data
        assert isinstance(data["orders"], list)
        for o in data["orders"]:
            assert "order_id" in o
            assert "est_ht" in o

    def test_orders_particulier_forbidden(self, client_token):
        r = requests.get(f"{API}/einvoicing/orders", headers=_h(client_token), timeout=15)
        assert r.status_code == 403

    def test_reconcile_flow(self, pro_token):
        # Get inbox
        r_inbox = requests.get(f"{API}/einvoicing/inbox", headers=_h(pro_token), timeout=15)
        assert r_inbox.status_code == 200
        invoices = r_inbox.json().get("invoices", [])
        if not invoices:
            pytest.skip("no invoices in inbox")
        inv = invoices[0]
        inv_id = inv["inv_id"]

        # Get orders
        r_orders = requests.get(f"{API}/einvoicing/orders", headers=_h(pro_token), timeout=15)
        orders = r_orders.json()["orders"]
        if not orders:
            # Create a material order for reconcile
            order_body = {
                "type": "materiaux",
                "supplier": "TEST_Fournisseur",
                "project": "TEST_Chantier",
                "items": [{"label": "Ciment", "qty": 10, "unit_price": 15.0, "unit": "sac"}]
            }
            r_new = requests.post(f"{API}/appro/orders",
                                  headers=_h(pro_token), json=order_body, timeout=15)
            if r_new.status_code not in (200, 201):
                pytest.skip(f"cannot create order: {r_new.status_code} {r_new.text}")
            r_orders = requests.get(f"{API}/einvoicing/orders",
                                    headers=_h(pro_token), timeout=15)
            orders = r_orders.json()["orders"]
        assert orders, "still no orders after creation"
        order_id = orders[0]["order_id"]

        # Reconcile with an expected_ht that differs to test gap
        invoice_ht = float(inv.get("amount_ht") or 100.0)
        expected_ht = invoice_ht * 0.9  # 10% under -> flag "over"
        r_rec = requests.post(
            f"{API}/einvoicing/inbox/{inv_id}/reconcile",
            headers=_h(pro_token),
            json={"order_id": order_id, "expected_ht": expected_ht},
            timeout=15)
        assert r_rec.status_code == 200, r_rec.text
        recon = r_rec.json()["reconciliation"]
        assert recon["order_id"] == order_id
        assert "gap_ht" in recon
        assert "gap_pct" in recon
        assert recon["gap_flag"] in ("ok", "over", "under")
        # invoice_ht > expected -> "over" (if gap > 2%)
        if abs((invoice_ht - expected_ht) / expected_ht * 100) > 2:
            assert recon["gap_flag"] == "over"

        # Verify persisted
        r_inbox2 = requests.get(f"{API}/einvoicing/inbox", headers=_h(pro_token), timeout=15)
        inv2 = next(i for i in r_inbox2.json()["invoices"] if i["inv_id"] == inv_id)
        assert inv2.get("reconciliation", {}).get("order_id") == order_id

        # Unreconcile
        r_un = requests.post(f"{API}/einvoicing/inbox/{inv_id}/unreconcile",
                             headers=_h(pro_token), timeout=15)
        assert r_un.status_code == 200
        assert r_un.json().get("ok") is True

        # Verify removed
        r_inbox3 = requests.get(f"{API}/einvoicing/inbox", headers=_h(pro_token), timeout=15)
        inv3 = next(i for i in r_inbox3.json()["invoices"] if i["inv_id"] == inv_id)
        assert not inv3.get("reconciliation")

    def test_reconcile_particulier_forbidden(self, client_token):
        r = requests.post(f"{API}/einvoicing/inbox/fake_id/reconcile",
                          headers=_h(client_token),
                          json={"order_id": "x"}, timeout=15)
        assert r.status_code == 403

    def test_unreconcile_particulier_forbidden(self, client_token):
        r = requests.post(f"{API}/einvoicing/inbox/fake_id/unreconcile",
                          headers=_h(client_token), timeout=15)
        assert r.status_code == 403


# ============ Billing checkout ============

class TestBilling:
    def test_plans_public(self):
        r = requests.get(f"{API}/plans", timeout=15)
        assert r.status_code == 200
        plans = r.json()["plans"]
        assert isinstance(plans, list) and len(plans) > 0

    def test_checkout_pro_particulier(self, client_token):
        # Get a pro plan
        r = requests.get(f"{API}/plans", timeout=15)
        plans = r.json()["plans"]
        pro_plan = next((p for p in plans if p.get("kind") != "free"
                         and "pro" in (p.get("plan_id") or "").lower()), None)
        if not pro_plan:
            pro_plan = next((p for p in plans if p.get("kind") != "free"), None)
        if not pro_plan:
            pytest.skip("no paid plan available")
        r2 = requests.post(f"{API}/billing/checkout",
                           headers=_h(client_token),
                           json={"plan_id": pro_plan["plan_id"],
                                 "origin_url": BASE_URL},
                           timeout=30)
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert "url" in body
        assert body["url"].startswith("http")

    def test_checkout_premium_particulier(self, client_token):
        r = requests.get(f"{API}/plans", timeout=15)
        plans = r.json()["plans"]
        prem = next((p for p in plans if "premium" in (p.get("plan_id") or "").lower()
                     and p.get("kind") != "free"), None)
        if not prem:
            pytest.skip("no premium plan available")
        r2 = requests.post(f"{API}/billing/checkout",
                           headers=_h(client_token),
                           json={"plan_id": prem["plan_id"],
                                 "origin_url": BASE_URL},
                           timeout=30)
        assert r2.status_code == 200, r2.text
        assert "url" in r2.json()
