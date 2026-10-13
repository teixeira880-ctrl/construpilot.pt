"""Iteration 2 — Tests for the 3 new features:
1. Tavily real-price search (mode=='web')
2. Public /api/estimation/pdf (no-auth PDF generation)
3. Photos before/after (upload, list, download, delete, RBAC, validation)
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

try:
    from tests.creds import DEMO_EMAIL, DEMO_PWD
except ImportError:
    from creds import DEMO_EMAIL, DEMO_PWD

DEMO = {"email": DEMO_EMAIL, "password": DEMO_PWD}


def _sess():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(creds):
    s = _sess()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO)


@pytest.fixture(scope="module")
def other_token():
    s = _sess()
    email = f"other_{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register",
               json={"name": "Autre User", "email": email, "password": "Passw0rd!"},
               timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def project_id(demo_token):
    s = _sess()
    payload = {"name": "TEST_Photos Iter2", "description": "Projet test photos",
               "surface": 20, "project_type": "salle_de_bain", "finish_level": "standard"}
    r = s.post(f"{API}/projects", json=payload, headers=_auth(demo_token), timeout=60)
    assert r.status_code == 200, r.text
    pid = r.json()["project_id"]
    yield pid
    s.delete(f"{API}/projects/{pid}", headers=_auth(demo_token), timeout=15)


# ---------- Tavily prices ----------
class TestTavilyPrices:
    def test_search_mode_web_with_real_suppliers(self):
        s = _sess()
        r = s.post(f"{API}/prices/search",
                   json={"query": "carrelage 60x60", "limit": 10}, timeout=45)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("mode") == "web", f"Expected mode=web, got {data.get('mode')}. Full: {data}"
        results = data.get("results", [])
        # Au moins 1 résultat avec prix > 0 (le web vivant varie d'un jour à l'autre)
        priced = [r for r in results if r.get("price") and r["price"] > 0]
        assert len(priced) >= 1, f"Expected >=1 priced results, got {len(priced)}: {results}"
        # Real French suppliers
        known = {"Leroy Merlin", "Bricoman", "Castorama", "ManoMano", "Brico Dépôt",
                 "Point.P", "Gedimat", "BigMat", "Lapeyre", "Amazon"}
        suppliers = {r.get("supplier") for r in results}
        assert suppliers & known, f"No known supplier found in: {suppliers}"


# ---------- Public estimation PDF ----------
class TestEstimationPdf:
    def test_estimation_pdf_public(self):
        s = _sess()
        # First compute an estimation
        r = s.post(f"{API}/estimation/compute",
                   json={"project_type": "renovation_complete", "surface": 100,
                         "finish_level": "standard", "building_type": "maison",
                         "condition": "bon"}, timeout=30)
        assert r.status_code == 200, r.text
        est = r.json()
        # No auth header — must be public
        pdf_sess = _sess()
        r = pdf_sess.post(f"{API}/estimation/pdf",
                          json={"project": {"name": "Test Devis", "city": "Paris"},
                                "estimation": est, "advice": "Conseil test"},
                          timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers.get("Content-Type", "").startswith("application/pdf")
        assert r.content[:4] == b"%PDF", f"Not a PDF file, starts with: {r.content[:20]}"
        assert len(r.content) > 500

    def test_estimation_pdf_empty_returns_400(self):
        s = _sess()
        r = s.post(f"{API}/estimation/pdf",
                   json={"project": {"name": "X"}, "estimation": {}},
                   timeout=20)
        assert r.status_code == 400


# ---------- Photos ----------
def _fake_jpeg(size_bytes: int = 200) -> bytes:
    """Minimal JPEG-like payload (starts with JPEG magic bytes)."""
    # Real JPEG start marker + padding + end marker
    header = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    footer = b"\xff\xd9"
    pad = b"\x00" * max(0, size_bytes - len(header) - len(footer))
    return header + pad + footer


class TestPhotos:
    photo_ids = {}

    def test_upload_before(self, demo_token, project_id):
        s = requests.Session()
        files = {"file": ("before.jpg", _fake_jpeg(500), "image/jpeg")}
        data = {"kind": "before", "lot": "Salle de bain", "caption": "Avant travaux"}
        r = s.post(f"{API}/projects/{project_id}/photos",
                   files=files, data=data, headers=_auth(demo_token), timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("photo_id", "").startswith("ph_")
        assert body.get("kind") == "before"
        assert body.get("lot") == "Salle de bain"
        assert body.get("size") > 0
        assert body.get("storage_path")
        TestPhotos.photo_ids["before"] = body["photo_id"]

    def test_upload_after(self, demo_token, project_id):
        s = requests.Session()
        files = {"file": ("after.jpg", _fake_jpeg(500), "image/jpeg")}
        data = {"kind": "after", "lot": "Salle de bain", "caption": "Après"}
        r = s.post(f"{API}/projects/{project_id}/photos",
                   files=files, data=data, headers=_auth(demo_token), timeout=60)
        assert r.status_code == 200, r.text
        TestPhotos.photo_ids["after"] = r.json()["photo_id"]

    def test_list_photos(self, demo_token, project_id):
        s = _sess()
        r = s.get(f"{API}/projects/{project_id}/photos",
                  headers=_auth(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        photos = r.json().get("photos", [])
        assert len(photos) >= 2
        kinds = {p["kind"] for p in photos}
        assert "before" in kinds and "after" in kinds

    def test_download_photo(self, demo_token, project_id):
        s = requests.Session()
        pid = TestPhotos.photo_ids.get("before")
        assert pid, "before photo not uploaded"
        r = s.get(f"{API}/projects/{project_id}/photos/{pid}/download",
                  headers=_auth(demo_token), timeout=30)
        assert r.status_code == 200, r.text
        assert r.headers.get("Content-Type", "").startswith("image/")
        assert len(r.content) > 0

    def test_rbac_other_user_cannot_access(self, other_token, project_id):
        s = _sess()
        r = s.get(f"{API}/projects/{project_id}/photos",
                  headers=_auth(other_token), timeout=15)
        assert r.status_code == 404

    def test_invalid_kind(self, demo_token, project_id):
        s = requests.Session()
        files = {"file": ("x.jpg", _fake_jpeg(300), "image/jpeg")}
        data = {"kind": "invalid", "lot": "", "caption": ""}
        r = s.post(f"{API}/projects/{project_id}/photos",
                   files=files, data=data, headers=_auth(demo_token), timeout=30)
        assert r.status_code == 400

    def test_empty_file(self, demo_token, project_id):
        s = requests.Session()
        files = {"file": ("empty.jpg", b"", "image/jpeg")}
        data = {"kind": "before"}
        r = s.post(f"{API}/projects/{project_id}/photos",
                   files=files, data=data, headers=_auth(demo_token), timeout=30)
        assert r.status_code == 400

    def test_file_too_large(self, demo_token, project_id):
        s = requests.Session()
        big = _fake_jpeg(11 * 1024 * 1024)  # 11 MB
        files = {"file": ("big.jpg", big, "image/jpeg")}
        data = {"kind": "before"}
        r = s.post(f"{API}/projects/{project_id}/photos",
                   files=files, data=data, headers=_auth(demo_token), timeout=120)
        assert r.status_code == 413

    def test_delete_photo(self, demo_token, project_id):
        s = _sess()
        pid = TestPhotos.photo_ids.get("after")
        assert pid
        r = s.delete(f"{API}/projects/{project_id}/photos/{pid}",
                     headers=_auth(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        # verify absent
        r = s.get(f"{API}/projects/{project_id}/photos",
                  headers=_auth(demo_token), timeout=15)
        photos = r.json().get("photos", [])
        assert not any(p["photo_id"] == pid for p in photos)
