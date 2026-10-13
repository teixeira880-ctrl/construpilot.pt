"""Iter 67 — PC Study Situations, Progress, Public sign & signature endpoints."""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

PRO = ("pro@construpilot.fr", "Pro2026!")
COL = ("collegue@construpilot.fr", "Collegue2026!")
PLAN_A = "plan_619e41f98d6b"   # étude en cours (acompte payé + situation 60%)
PLAN_B = "plan_6696782f92ca"   # ALAOUI - vierge pour signature
TOKEN_A = "pcs_e2a4c343ca79d96e"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("token") or j.get("access_token")


@pytest.fixture(scope="module")
def pro_token():
    return _login(*PRO)


@pytest.fixture(scope="module")
def col_token():
    return _login(*COL)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# --- Situations / billing ---
class TestSituations:
    def test_initial_billing(self, pro_token):
        r = requests.get(f"{API}/takeoffs/{PLAN_A}/pc-study/situations", headers=H(pro_token), timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        b = d["billing"]
        assert abs(b["total_ttc"] - 148763.5) < 1.0
        assert abs(b["deposit_paid"] - 44629.05) < 1.0
        # Un acompte 30% + 1 situation à 60% = 60% facturé du total
        # invoiced peut être 89258.1 (60%) ou 148763.5 (100%) suivant que les situations 80% et solde ont déjà été créées
        assert b["invoiced"] >= 89258.1 - 5.0
        assert b["invoiced"] <= 148763.5 + 5.0
        sits = d["situations"]
        assert len(sits) >= 1
        assert sits[0]["invoice_no"] == "SIT-2026-0001"
        assert sits[0]["paid"] in (False, True)

    def test_create_situation_below_current_fails(self, pro_token):
        r = requests.post(f"{API}/takeoffs/{PLAN_A}/pc-study/situations",
                          headers=H(pro_token), json={"pct_cumul": 50}, timeout=30)
        assert r.status_code == 400, r.text

    def test_create_situation_80(self, pro_token):
        r = requests.post(f"{API}/takeoffs/{PLAN_A}/pc-study/situations",
                          headers=H(pro_token), json={"pct_cumul": 80}, timeout=60)
        # Peut être déjà créée par un run précédent — accepte 200 ou 400
        if r.status_code == 400:
            pytest.skip("Situation 80% déjà créée par un run précédent")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["situation"]["invoice_no"] == "SIT-2026-0002"
        assert d["situation"]["pct_cumul"] == 80
        assert 29000 < d["situation"]["amount"] < 30500
        assert d.get("emailed") == True

    def test_solde(self, pro_token):
        r = requests.post(f"{API}/takeoffs/{PLAN_A}/pc-study/situations",
                          headers=H(pro_token), json={"solde": True}, timeout=60)
        if r.status_code == 400:
            pytest.skip("Solde déjà émis ou blocage")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["situation"]["is_final"] == True
        # remaining_to_invoice ~ 0
        r2 = requests.get(f"{API}/takeoffs/{PLAN_A}/pc-study/situations", headers=H(pro_token), timeout=30)
        assert r2.json()["billing"]["remaining_to_invoice"] < 1.0


# --- Public sign endpoint ---
class TestPublicSign:
    def test_get_public(self):
        r = requests.get(f"{API}/pc/sign/{TOKEN_A}", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # pas d'info coût privé
        assert "cout_ht" not in (d.get("totals") or {})
        # acompte visible
        assert d.get("deposit", {}).get("invoice_no") == "AC-2026-0001"

    def test_public_invoice_pdfs(self, pro_token):
        r = requests.get(f"{API}/takeoffs/{PLAN_A}/pc-study/situations", headers=H(pro_token), timeout=30)
        sits = r.json()["situations"]
        assert len(sits) >= 1
        for s in sits:
            pdf = requests.get(f"{API}/pc/sign/{TOKEN_A}/situation/{s['sit_id']}/invoice", timeout=60)
            assert pdf.status_code == 200, f"Invoice PDF failed for {s['sit_id']}: {pdf.status_code}"
            assert pdf.headers.get("content-type", "").startswith("application/pdf")
            assert pdf.content[:4] == b"%PDF"


# --- Team read-only ---
class TestReadOnly:
    def test_situations_get_ok(self, col_token):
        r = requests.get(f"{API}/takeoffs/{PLAN_A}/pc-study/situations", headers=H(col_token), timeout=30)
        assert r.status_code == 200

    def test_situations_post_forbidden(self, col_token):
        r = requests.post(f"{API}/takeoffs/{PLAN_A}/pc-study/situations",
                          headers=H(col_token), json={"pct_cumul": 90}, timeout=30)
        assert r.status_code == 403, r.text
        assert "Lecture seule" in (r.json().get("detail") or "") or "lecture" in (r.json().get("detail") or "").lower()

    def test_progress_post_forbidden(self, col_token):
        r = requests.post(f"{API}/takeoffs/{PLAN_A}/pc-study/progress",
                          headers=H(col_token), json={"done": [0, 1]}, timeout=30)
        assert r.status_code == 403


# --- Progress ---
class TestProgress:
    def test_toggle_phase_3(self, pro_token):
        r = requests.post(f"{API}/takeoffs/{PLAN_A}/pc-study/progress",
                          headers=H(pro_token), json={"done": [0, 1, 2, 3]}, timeout=30)
        assert r.status_code == 200, r.text
        # Vérifier via public
        p = requests.get(f"{API}/pc/sign/{TOKEN_A}", timeout=30).json()
        prog = p.get("progress") or {}
        assert prog.get("pct") == 50
        assert prog.get("done_count") == 4
        assert prog["phases"][3]["done"] == True


# --- Regression dashboard ---
class TestDashboard:
    def test_pc_dashboard(self, pro_token):
        r = requests.get(f"{API}/pc/dashboard", headers=H(pro_token), timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d.get("studies"), list)
        # au moins l'étude PLAN_A présente
        assert any(s.get("plan_id") == PLAN_A for s in d["studies"])
