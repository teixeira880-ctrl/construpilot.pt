"""Iter 74 — Page Mon compte : PUT /auth/profile + flag must_change_password."""
import os
import uuid
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
API = f"{BASE_URL}/api"

try:
    from tests.creds import DEMO_EMAIL, DEMO_PWD, PRO_EMAIL
except ImportError:
    from creds import DEMO_EMAIL, DEMO_PWD, PRO_EMAIL


def _login(email, pwd):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_profile_update_name_phone():
    h = _login(DEMO_EMAIL, DEMO_PWD)
    r = requests.put(f"{API}/auth/profile",
                     json={"name": "Client Démo", "phone": "+33 6 11 22 33 44"},
                     headers=h, timeout=15)
    assert r.status_code == 200, r.text
    u = r.json()["user"]
    assert u["name"] == "Client Démo"
    assert u["phone"] == "+33 6 11 22 33 44"


def test_profile_email_change_requires_password():
    h = _login(DEMO_EMAIL, DEMO_PWD)
    r = requests.put(f"{API}/auth/profile", json={"email": "x-nouveau@test.fr"},
                     headers=h, timeout=15)
    assert r.status_code == 401
    r = requests.put(f"{API}/auth/profile",
                     json={"email": "x-nouveau@test.fr", "current_password": "faux"},
                     headers=h, timeout=15)
    assert r.status_code == 401


def test_profile_email_change_rejects_taken_email():
    h = _login(DEMO_EMAIL, DEMO_PWD)
    r = requests.put(f"{API}/auth/profile",
                     json={"email": PRO_EMAIL, "current_password": DEMO_PWD},
                     headers=h, timeout=15)
    assert r.status_code == 400


def test_profile_email_change_ok_and_revert():
    h = _login(DEMO_EMAIL, DEMO_PWD)
    tmp = f"demo-tmp-{uuid.uuid4().hex[:6]}@construpilot.fr"
    r = requests.put(f"{API}/auth/profile",
                     json={"email": tmp, "current_password": DEMO_PWD},
                     headers=h, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == tmp
    r = requests.put(f"{API}/auth/profile",
                     json={"email": DEMO_EMAIL, "current_password": DEMO_PWD},
                     headers=h, timeout=15)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == DEMO_EMAIL


def test_profile_name_too_short_rejected():
    h = _login(DEMO_EMAIL, DEMO_PWD)
    r = requests.put(f"{API}/auth/profile", json={"name": "X"}, headers=h, timeout=15)
    assert r.status_code == 400


def test_change_password_clears_must_change_flag():
    email = f"jetable-{uuid.uuid4().hex[:8]}@test.fr"
    r = requests.post(f"{API}/auth/register",
                      json={"name": "Jetable Flag", "email": email, "password": "Jetable2026!"},
                      timeout=30)
    assert r.status_code == 200, r.text
    h = {"Authorization": f"Bearer {r.json()['token']}"}
    # Le flag n'est pas posé par register — on vérifie simplement que change-password
    # renvoie must_change_password=False côté /me après passage.
    r = requests.post(f"{API}/auth/change-password",
                      json={"current_password": "Jetable2026!", "new_password": "NouveauMdp2026!"},
                      headers=h, timeout=15)
    assert r.status_code == 200, r.text
    me = requests.get(f"{API}/auth/me", headers=h, timeout=15).json()
    assert me.get("must_change_password") == False


def test_me_exposes_profile_fields():
    h = _login(DEMO_EMAIL, DEMO_PWD)
    me = requests.get(f"{API}/auth/me", headers=h, timeout=15).json()
    for k in ("phone", "auth_provider", "must_change_password"):
        assert k in me, f"missing {k}"
