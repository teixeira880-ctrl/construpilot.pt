"""Iter 119 — Dépense chantier auto (e-invoicing) + Résumé mensuel surcoûts.

Vérifie :
- GET /api/einvoicing/projects (liste)
- POST /api/einvoicing/inbox/{inv_id}/decision accepted+project_id crée expense (budget spent +)
- POST /api/einvoicing/inbox/{inv_id}/expense sur facture acceptée OK, non acceptée 400, re-link idempotent
- POST .../expense/remove supprime expense
- POST /api/einvoicing/reports/monthly/preview renvoie champs attendus
- Particulier reçoit 403 sur ces endpoints (pro_required)
"""
import os
import pytest
import requests

def _load_frontend_env():
    p = "/app/frontend/.env"
    if os.path.exists(p):
        for line in open(p):
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    return os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

BASE_URL = _load_frontend_env()
PRO = ("pro@construpilot.fr", "Pro2026!")
CLIENT = ("client@construpilot.fr", "Client2026!")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def pro_headers():
    return {"Authorization": f"Bearer {_login(*PRO)}"}


@pytest.fixture(scope="module")
def client_headers():
    return {"Authorization": f"Bearer {_login(*CLIENT)}"}


@pytest.fixture(scope="module")
def ensure_connected(pro_headers):
    st = requests.get(f"{BASE_URL}/api/einvoicing/status", headers=pro_headers).json()
    if not st.get("connected"):
        r = requests.post(f"{BASE_URL}/api/einvoicing/connect",
                          json={"siret": "54210922700018", "platform": "Iopole"},
                          headers=pro_headers)
        assert r.status_code == 200, r.text
    return True


@pytest.fixture(scope="module")
def project_id(pro_headers):
    """Crée (ou réutilise) un projet pour rattacher les dépenses."""
    r = requests.get(f"{BASE_URL}/api/einvoicing/projects", headers=pro_headers)
    assert r.status_code == 200
    projs = r.json().get("projects") or []
    if projs:
        return projs[0]["project_id"]
    # sinon on en crée un via /api/projects
    body = {"name": "TEST_iter119 Chantier", "type": "renovation",
            "surface_m2": 50, "level": "standard"}
    r = requests.post(f"{BASE_URL}/api/projects", json=body, headers=pro_headers)
    assert r.status_code == 200, r.text
    return r.json()["project_id"]


@pytest.fixture(scope="module")
def fresh_invoice(pro_headers, ensure_connected):
    """Provoque la réception d'une facture 'received' pour tests d'acceptation."""
    r = requests.post(f"{BASE_URL}/api/einvoicing/inbox/simulate", headers=pro_headers)
    assert r.status_code == 200, r.text
    return r.json()["invoice"]


# ---------- Endpoints de base ----------

class TestProjectsList:
    def test_projects_endpoint_ok(self, pro_headers):
        r = requests.get(f"{BASE_URL}/api/einvoicing/projects", headers=pro_headers)
        assert r.status_code == 200
        data = r.json()
        assert "projects" in data
        assert isinstance(data["projects"], list)

    def test_projects_forbidden_for_client(self, client_headers):
        r = requests.get(f"{BASE_URL}/api/einvoicing/projects", headers=client_headers)
        assert r.status_code == 403


# ---------- Décision "accepted" avec project_id ----------

class TestDecisionCreatesExpense:
    def test_accept_with_project_creates_expense(self, pro_headers, project_id, fresh_invoice):
        inv_id = fresh_invoice["inv_id"]
        amount_ht = float(fresh_invoice["amount_ht"])

        # baseline spent
        b0 = requests.get(f"{BASE_URL}/api/projects/{project_id}/budget",
                          headers=pro_headers).json()
        spent0 = float(b0.get("spent") or 0)

        r = requests.post(f"{BASE_URL}/api/einvoicing/inbox/{inv_id}/decision",
                          json={"decision": "accepted", "project_id": project_id},
                          headers=pro_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "accepted"
        assert data.get("expense") is not None
        assert data["expense"]["project_id"] == project_id
        assert abs(float(data["expense"]["amount"]) - round(amount_ht, 2)) < 0.01

        # vérifier budget
        b1 = requests.get(f"{BASE_URL}/api/projects/{project_id}/budget",
                          headers=pro_headers).json()
        assert round(float(b1["spent"]) - spent0, 2) == round(amount_ht, 2)
        # vérifier expense source='einvoice'
        exp_found = [e for e in b1["expenses"] if e.get("source") == "einvoice"
                     and e.get("einvoice_id") == inv_id]
        assert len(exp_found) == 1


# ---------- Endpoint /expense standalone ----------

class TestStandaloneExpenseLink:
    def test_link_expense_on_non_accepted_returns_400(self, pro_headers, project_id):
        # utilise une facture fraîchement reçue (statut received)
        inv = requests.post(f"{BASE_URL}/api/einvoicing/inbox/simulate",
                            headers=pro_headers).json()["invoice"]
        r = requests.post(
            f"{BASE_URL}/api/einvoicing/inbox/{inv['inv_id']}/expense",
            json={"project_id": project_id}, headers=pro_headers)
        assert r.status_code == 400

    def test_link_and_relink_idempotent(self, pro_headers, project_id):
        # simulate + accept (sans project_id) pour obtenir une facture 'accepted' sans expense
        inv = requests.post(f"{BASE_URL}/api/einvoicing/inbox/simulate",
                            headers=pro_headers).json()["invoice"]
        inv_id = inv["inv_id"]
        amount_ht = float(inv["amount_ht"])
        r = requests.post(f"{BASE_URL}/api/einvoicing/inbox/{inv_id}/decision",
                          json={"decision": "accepted"}, headers=pro_headers)
        assert r.status_code == 200
        assert r.json().get("expense") is None

        # baseline
        b0 = requests.get(f"{BASE_URL}/api/projects/{project_id}/budget",
                          headers=pro_headers).json()
        spent0 = float(b0.get("spent") or 0)

        # premier lien
        r1 = requests.post(f"{BASE_URL}/api/einvoicing/inbox/{inv_id}/expense",
                           json={"project_id": project_id}, headers=pro_headers)
        assert r1.status_code == 200
        assert r1.json()["expense"]["project_id"] == project_id

        # re-lien (doit remplacer et non doubler)
        r2 = requests.post(f"{BASE_URL}/api/einvoicing/inbox/{inv_id}/expense",
                           json={"project_id": project_id}, headers=pro_headers)
        assert r2.status_code == 200

        b1 = requests.get(f"{BASE_URL}/api/projects/{project_id}/budget",
                          headers=pro_headers).json()
        # spent doit avoir augmenté exactement d'un montant HT (pas double)
        assert round(float(b1["spent"]) - spent0, 2) == round(amount_ht, 2)
        # une seule expense pour ce einvoice_id
        matches = [e for e in b1["expenses"] if e.get("einvoice_id") == inv_id]
        assert len(matches) == 1

        # unlink retire la dépense
        r3 = requests.post(
            f"{BASE_URL}/api/einvoicing/inbox/{inv_id}/expense/remove",
            headers=pro_headers)
        assert r3.status_code == 200
        b2 = requests.get(f"{BASE_URL}/api/projects/{project_id}/budget",
                          headers=pro_headers).json()
        matches2 = [e for e in b2["expenses"] if e.get("einvoice_id") == inv_id]
        assert len(matches2) == 0
        assert round(float(b2["spent"]), 2) == round(spent0, 2)

    def test_expense_forbidden_for_client(self, client_headers):
        r = requests.post(f"{BASE_URL}/api/einvoicing/inbox/xxx/expense",
                          json={"project_id": "p"}, headers=client_headers)
        assert r.status_code == 403


# ---------- Résumé mensuel ----------

class TestMonthlyPreview:
    def test_preview_returns_expected_fields(self, pro_headers):
        r = requests.post(
            f"{BASE_URL}/api/einvoicing/reports/monthly/preview",
            headers=pro_headers)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("month", "overspend_total", "savings_total",
                  "over_count", "under_count", "over_items"):
            assert k in data, f"missing key {k}"
        assert isinstance(data["over_items"], list)
        assert isinstance(data["overspend_total"], (int, float))

    def test_preview_forbidden_for_client(self, client_headers):
        r = requests.post(
            f"{BASE_URL}/api/einvoicing/reports/monthly/preview",
            headers=client_headers)
        assert r.status_code == 403
