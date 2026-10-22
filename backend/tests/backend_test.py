"""CMRENOV AI backend regression tests.

Covers auth, smart-project (AI), estimation, prices (mocked), projects CRUD,
calculators, leads and admin role protection.
"""
import os
import uuid
import pytest
import requests

# Suite e2e opcional: só corre quando REACT_APP_BACKEND_URL está exposto no
# ambiente (preview/CI). Em CI local do pod a var pode faltar — nesse caso
# saltamos tudo em vez de levantar KeyError na colecta do pytest.
_BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not _BACKEND_URL:
    pytest.skip(
        "REACT_APP_BACKEND_URL ausente — testes e2e `backend_test.py` saltados "
        "(suite só corre no preview/CI).",
        allow_module_level=True,
    )
BASE_URL = _BACKEND_URL.rstrip("/")
API = f"{BASE_URL}/api"

try:
    from tests.creds import ADMIN_EMAIL, ADMIN_PWD, DEMO_EMAIL, DEMO_PWD
except ImportError:
    from creds import ADMIN_EMAIL, ADMIN_PWD, DEMO_EMAIL, DEMO_PWD

ADMIN = {"email": ADMIN_EMAIL, "password": ADMIN_PWD}
DEMO = {"email": DEMO_EMAIL, "password": DEMO_PWD}


# ---------- fixtures ----------
def _fresh_session():
    """Fresh requests session with no cookies (avoid cookie leakage across tests)."""
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


@pytest.fixture()
def s():
    return _fresh_session()


def _login(creds):
    sess = _fresh_session()
    r = sess.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN)["token"]


@pytest.fixture(scope="session")
def demo_token():
    return _login(DEMO)["token"]


@pytest.fixture(scope="session")
def new_user():
    sess = _fresh_session()
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    r = sess.post(f"{API}/auth/register",
                  json={"name": "Testeur", "email": email, "password": "Passw0rd!"}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    return {"email": email, "token": data["token"], "user": data["user"]}


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- health ----------
def test_root(s):
    r = s.get(f"{API}/", timeout=15)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------- auth ----------
def test_register_and_login(s, new_user):
    # login with same creds
    r = s.post(f"{API}/auth/login",
               json={"email": new_user["email"], "password": "Passw0rd!"}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "token" in body and body["user"]["email"] == new_user["email"]


def test_login_admin_role(s, admin_token):
    r = s.get(f"{API}/auth/me", headers=_auth(admin_token), timeout=15)
    assert r.status_code == 200
    assert r.json().get("role") == "admin"


def test_login_demo_user(s, demo_token):
    r = s.get(f"{API}/auth/me", headers=_auth(demo_token), timeout=15)
    assert r.status_code == 200
    assert r.json().get("email") == DEMO["email"]
    assert r.json().get("role") == "user"


def test_login_bad_password(s):
    r = s.post(f"{API}/auth/login",
               json={"email": DEMO["email"], "password": "wrong"}, timeout=15)
    assert r.status_code == 401


# ---------- smart project IA ----------
def test_smart_project_analyse(s):
    payload = {"description": "Rénover salle de bain 8m2, refaire carrelage, plomberie, sanitaires"}
    r = s.post(f"{API}/estimation/analyse", json=payload, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "analysis" in data and "estimation" in data
    est = data["estimation"]
    assert est.get("total_avg", 0) > 0
    assert isinstance(est.get("lots"), list) and len(est["lots"]) > 0


# ---------- estimation compute ----------
def test_estimation_compute(s):
    payload = {"project_type": "renovation_complete", "surface": 80,
               "finish_level": "standard", "building_type": "maison", "condition": "bon"}
    r = s.post(f"{API}/estimation/compute", json=payload, timeout=30)
    assert r.status_code == 200
    data = r.json()
    assert data["total_avg"] > 0
    assert len(data["lots"]) > 0
    assert "planning" in data


def test_estimation_catalog(s):
    r = s.get(f"{API}/estimation/catalog", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "project_types" in body and "lots" in body


# ---------- prices (mocked) ----------
def test_prices_search(s):
    r = s.post(f"{API}/prices/search", json={"query": "carrelage", "limit": 5}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    # should return offers list or dict with offers
    assert isinstance(data, (list, dict))


def test_prices_suppliers(s):
    r = s.get(f"{API}/prices/suppliers", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------- projects CRUD ----------
@pytest.fixture(scope="session")
def created_project_id(demo_token):
    sess = _fresh_session()
    payload = {"name": "TEST_Projet Rénov", "description": "Salle de bain", "surface": 8,
               "project_type": "salle_de_bain", "finish_level": "standard"}
    r = sess.post(f"{API}/projects", json=payload, headers=_auth(demo_token), timeout=60)
    assert r.status_code == 200, r.text
    pid = r.json()["project_id"]
    yield pid
    sess.delete(f"{API}/projects/{pid}", headers=_auth(demo_token), timeout=15)


def test_project_list(s, demo_token, created_project_id):
    r = s.get(f"{API}/projects", headers=_auth(demo_token), timeout=15)
    assert r.status_code == 200
    assert any(p["project_id"] == created_project_id for p in r.json())


def test_project_detail(s, demo_token, created_project_id):
    r = s.get(f"{API}/projects/{created_project_id}", headers=_auth(demo_token), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == created_project_id
    assert body["estimation"]["total_avg"] > 0


def test_project_requires_auth(s):
    r = s.get(f"{API}/projects", timeout=15)
    assert r.status_code in (401, 403)


# ---------- calculators ----------
@pytest.mark.parametrize("key,params", [
    ("paint", {"length": 4, "width": 3, "height": 2.5}),
    ("tile", {"area": 20}),
    ("drywall", {"area": 15, "structure": "cloison"}),
    ("concrete", {"length": 5, "width": 4, "thickness": 0.1}),
    ("insulation", {"area": 30}),
])
def test_calculator(s, key, params):
    r = s.post(f"{API}/calculators/{key}", json={"params": params}, timeout=15)
    assert r.status_code == 200, f"{key}: {r.status_code} {r.text}"
    data = r.json()
    assert isinstance(data, dict)


def test_calculators_list(s):
    r = s.get(f"{API}/calculators", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list) and len(r.json()) > 0


# ---------- leads ----------
def test_create_lead(s):
    lead = {"name": "TEST Client", "email": "test_lead@example.com",
            "phone": "+33600000000", "description": "Rénovation appart 60m2"}
    r = s.post(f"{API}/leads", json=lead, timeout=15)
    assert r.status_code == 200
    assert r.json().get("lead_id", "").startswith("lead_")


def test_admin_leads_list(s, admin_token):
    r = s.get(f"{API}/admin/leads", headers=_auth(admin_token), timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_admin_forbidden_for_user(s, demo_token):
    r = s.get(f"{API}/admin/leads", headers=_auth(demo_token), timeout=15)
    assert r.status_code == 403


def test_admin_stats(s, admin_token):
    r = s.get(f"{API}/admin/stats", headers=_auth(admin_token), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "users" in body and "projects" in body


# ---------- AI chat (SSE) ----------
def test_ai_chat_stream(s):
    r = s.post(f"{API}/chat", json={"message": "Comment poser du carrelage ?"}, timeout=90, stream=True)
    assert r.status_code == 200
    # read a few chunks to verify SSE works
    got_any = False
    for i, line in enumerate(r.iter_lines()):
        if line and line.startswith(b"data:"):
            got_any = True
        if i > 10:
            break
    assert got_any
