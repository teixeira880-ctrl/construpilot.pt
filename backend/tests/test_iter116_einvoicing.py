"""Tests for e-invoicing (facturation électronique) endpoints — MOCKED PDP."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PRO = {"email": "pro@construpilot.fr", "password": "Pro2026!"}
PART = {"email": "client@construpilot.fr", "password": "Client2026!"}


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def pro_headers():
    return {"Authorization": f"Bearer {_login(PRO)}"}


@pytest.fixture(scope="module")
def part_headers():
    return {"Authorization": f"Bearer {_login(PART)}"}


# --- pro_required gating ---
class TestGating:
    def test_particulier_forbidden_status(self, part_headers):
        r = requests.get(f"{API}/einvoicing/status", headers=part_headers, timeout=20)
        assert r.status_code == 403

    def test_particulier_forbidden_inbox(self, part_headers):
        r = requests.get(f"{API}/einvoicing/inbox", headers=part_headers, timeout=20)
        assert r.status_code == 403

    def test_particulier_forbidden_connect(self, part_headers):
        r = requests.post(f"{API}/einvoicing/connect", headers=part_headers,
                          json={"siret": "54210922700018"}, timeout=20)
        assert r.status_code == 403


# --- connect / status / inbox flow ---
class TestFlow:
    def test_status_shape(self, pro_headers):
        r = requests.get(f"{API}/einvoicing/status", headers=pro_headers, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert data.get("mocked") is True
        assert "connected" in data

    def test_connect_invalid_siret(self, pro_headers):
        r = requests.post(f"{API}/einvoicing/connect", headers=pro_headers,
                          json={"siret": "123"}, timeout=20)
        assert r.status_code == 400

    def test_connect_valid_and_status_connected(self, pro_headers):
        # ensure connected
        r = requests.post(f"{API}/einvoicing/connect", headers=pro_headers,
                          json={"siret": "54210922700018", "platform": "Iopole"}, timeout=20)
        assert r.status_code == 200
        assert r.json().get("connected") is True
        # verify status
        r2 = requests.get(f"{API}/einvoicing/status", headers=pro_headers, timeout=20)
        assert r2.status_code == 200
        d = r2.json()
        assert d["connected"] is True
        assert d["siret"] == "54210922700018"
        assert d["platform"] == "Iopole"

    def test_inbox_has_seeded(self, pro_headers):
        r = requests.get(f"{API}/einvoicing/inbox", headers=pro_headers, timeout=20)
        assert r.status_code == 200
        invs = r.json().get("invoices", [])
        assert len(invs) >= 2
        # ensure no _id leaked
        for i in invs:
            assert "_id" not in i

    def test_simulate_reception(self, pro_headers):
        before = len(requests.get(f"{API}/einvoicing/inbox", headers=pro_headers).json()["invoices"])
        r = requests.post(f"{API}/einvoicing/inbox/simulate", headers=pro_headers, timeout=20)
        assert r.status_code == 200
        inv = r.json()["invoice"]
        assert inv["status"] == "received"
        after = len(requests.get(f"{API}/einvoicing/inbox", headers=pro_headers).json()["invoices"])
        assert after == before + 1

    def test_decision_accept(self, pro_headers):
        # get an invoice with status 'received'
        invs = requests.get(f"{API}/einvoicing/inbox", headers=pro_headers).json()["invoices"]
        target = next((i for i in invs if i["status"] == "received"), None)
        assert target
        r = requests.post(f"{API}/einvoicing/inbox/{target['inv_id']}/decision",
                          headers=pro_headers, json={"decision": "accepted"}, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "accepted"
        assert body["admin_status"] == "transmis (simulé)"

    def test_decision_refuse(self, pro_headers):
        # ensure at least one received
        requests.post(f"{API}/einvoicing/inbox/simulate", headers=pro_headers, timeout=20)
        invs = requests.get(f"{API}/einvoicing/inbox", headers=pro_headers).json()["invoices"]
        target = next((i for i in invs if i["status"] == "received"), None)
        assert target
        r = requests.post(f"{API}/einvoicing/inbox/{target['inv_id']}/decision",
                          headers=pro_headers,
                          json={"decision": "refused", "reason": "test motif"}, timeout=20)
        assert r.status_code == 200
        assert r.json()["status"] == "refused"

    def test_decision_invalid(self, pro_headers):
        invs = requests.get(f"{API}/einvoicing/inbox", headers=pro_headers).json()["invoices"]
        target = invs[0]
        r = requests.post(f"{API}/einvoicing/inbox/{target['inv_id']}/decision",
                          headers=pro_headers, json={"decision": "maybe"}, timeout=20)
        assert r.status_code == 400

    def test_decision_not_found(self, pro_headers):
        r = requests.post(f"{API}/einvoicing/inbox/does_not_exist/decision",
                          headers=pro_headers, json={"decision": "accepted"}, timeout=20)
        assert r.status_code == 404

    def test_disconnect_then_simulate_forbidden(self, pro_headers):
        r = requests.post(f"{API}/einvoicing/disconnect", headers=pro_headers, timeout=20)
        assert r.status_code == 200
        r2 = requests.post(f"{API}/einvoicing/inbox/simulate", headers=pro_headers, timeout=20)
        assert r2.status_code == 400
        # reconnect for cleanup / next flows
        requests.post(f"{API}/einvoicing/connect", headers=pro_headers,
                      json={"siret": "54210922700018"}, timeout=20)
