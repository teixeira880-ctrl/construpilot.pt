"""Wave C3 PT-PT localization tests.
Checks: backend imports OK, auth admin PT config, catalog PT labels, DIY PT content."""
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://construpilot-recon.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@construpilot.io"
ADMIN_PASSWORD = "VJAiUOI90Ss2brVH"
ADMIN_PT_EMAIL = "info@construpilot.pt"
ADMIN_PT_PASSWORD = "Ruquinha2020."

FRENCH_WORDS = re.compile(
    r"\b(Bonjour|Bienvenue|Devis|Enregistrer|Annuler|Supprimer|Modifier|Ajouter|Utilisateur|"
    r"Paramètres|Fournisseur|Chantier|Facture|Éditeur|Nouveau|Modèle|Aperçu|Envoyer|"
    r"Télécharger|Rechercher|Suivant|Précédent|Fermer|Confirmer)\b",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 10
    return data["token"]


@pytest.fixture(scope="module")
def pt_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_PT_EMAIL, "password": ADMIN_PT_PASSWORD}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"PT admin login failed: {r.status_code}")
    return r.json()["token"]


def test_health_or_root_ok():
    # backend up
    r = requests.get(f"{BASE_URL}/api/", timeout=15)
    assert r.status_code in (200, 404, 405)


def test_login_admin_ok(token):
    assert token


def test_login_invalid():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "no@no.no", "password": "xx"}, timeout=15)
    assert r.status_code in (400, 401, 403, 422)


def test_auth_me_admin(token):
    r = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {token}"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    # country/language/timezone might be present
    assert "email" in data
    assert data["email"] == ADMIN_EMAIL


def test_auth_me_pt_admin(pt_token):
    r = requests.get(f"{BASE_URL}/api/auth/me",
                     headers={"Authorization": f"Bearer {pt_token}"}, timeout=15)
    assert r.status_code == 200
    data = r.json()
    # PT admin should have country/language pt
    if "country" in data:
        assert data["country"] in ("PT", "pt")
    if "language" in data:
        assert data["language"].lower().startswith("pt")


def test_catalog_lots_pt(token):
    r = requests.get(f"{BASE_URL}/api/estimation/catalog",
                     headers={"Authorization": f"Bearer {token}"}, timeout=15)
    assert r.status_code == 200, r.text
    catalog = r.json()
    lots = catalog["lots"] if isinstance(catalog, dict) else catalog
    assert isinstance(lots, list) and len(lots) > 0
    # scan labels for stray french words
    combined = " ".join(str(l.get("label", "") or l.get("name", "")) for l in lots)
    fr = FRENCH_WORDS.findall(combined)
    assert not fr, f"French words found in catalog lots: {fr[:5]} :: {combined[:400]}"


def test_diy_tasks_pt():
    r = requests.get(f"{BASE_URL}/api/diy/tasks", timeout=15)
    assert r.status_code == 200, r.text
    tasks = r.json()
    assert isinstance(tasks, list) and len(tasks) > 0
    names = " | ".join(t.get("name", "") + " " + (t.get("difficulty_label", "") or "") for t in tasks)
    fr = FRENCH_WORDS.findall(names)
    assert not fr, f"French words in DIY task names/difficulty: {fr[:5]} :: {names[:500]}"


def test_diy_guide_plafond_placo():
    payload = {"params": {"area_m2": 10}}
    r = requests.post(f"{BASE_URL}/api/diy/guide/plafond_placo", json=payload, timeout=20)
    if r.status_code == 404:
        # try any first task
        tasks = requests.get(f"{BASE_URL}/api/diy/tasks", timeout=15).json()
        assert tasks, "no diy tasks available"
        key = tasks[0]["key"]
        r = requests.post(f"{BASE_URL}/api/diy/guide/{key}", json=payload, timeout=20)
    assert r.status_code == 200, r.text
    body = r.text
    fr = FRENCH_WORDS.findall(body)
    # Allow occasional overlap words but should be zero
    assert len(fr) == 0, f"French words in DIY guide: set={set(fr)} sample={body[:600]}"


def test_backend_import_no_error():
    # If backend serves /api/auth/me, imports are OK.
    # Additionally attempt to hit a few refactored routes to ensure no 500 startup issue.
    for path in ["/api/catalog/lots", "/api/diy/tasks"]:
        r = requests.get(f"{BASE_URL}{path}", timeout=15)
        assert r.status_code < 500, f"{path} -> {r.status_code}: {r.text[:200]}"
