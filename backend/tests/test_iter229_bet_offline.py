"""Iteration 229 — tests for BET gating + dossier endpoints + project notes field.

Validates:
- POST /api/structuro/bet/studies requires pro level (FREE user → 403).
- PRO can list/create/get/delete BET dossiers.
- Projects PATCH accepts a `notes` field (offline chantier notes sync).

Does NOT upload documents (avoid spamming Gemini). Compare/report/inconsistencies
are exercised only on an empty dossier to confirm 404/422 short-circuits where
appropriate — the real AI flow is covered by UI testing.
"""
from __future__ import annotations

import os
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

PRO = ("pro@construpilot.fr", "Pro2026!")
FREE = ("client@construpilot.fr", "Client2026!")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def pro():
    return _login(*PRO)


@pytest.fixture(scope="module")
def free():
    return _login(*FREE)


class TestBetGating:
    def test_free_cannot_list_dossiers(self, free):
        r = free.get(f"{API}/structuro/bet/studies", timeout=20)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_free_cannot_create_dossier(self, free):
        r = free.post(f"{API}/structuro/bet/studies", json={"title": "TEST_free"}, timeout=20)
        assert r.status_code == 403

    def test_pro_can_list(self, pro):
        r = pro.get(f"{API}/structuro/bet/studies", timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert "studies" in data and isinstance(data["studies"], list)


class TestBetDossierCrud:
    def test_create_get_delete(self, pro):
        # Create
        r = pro.post(f"{API}/structuro/bet/studies", json={"title": "TEST_iter229"}, timeout=20)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["title"] == "TEST_iter229"
        assert d["dossier_id"].startswith("bet_")
        assert d["documents"] == []
        did = d["dossier_id"]

        # GET
        r2 = pro.get(f"{API}/structuro/bet/studies/{did}", timeout=20)
        assert r2.status_code == 200
        assert r2.json()["dossier_id"] == did

        # Compare on empty docs → 404 (no docs match)
        r3 = pro.post(f"{API}/structuro/bet/studies/{did}/compare",
                      json={"doc_a": "x", "doc_b": "y"}, timeout=20)
        assert r3.status_code == 404

        # Inconsistencies on empty dossier should still succeed (no docs)
        r4 = pro.post(f"{API}/structuro/bet/studies/{did}/inconsistencies", timeout=60)
        assert r4.status_code == 200, r4.text[:200]
        js = r4.json()
        assert js.get("inconsistencies") is not None

        # Report PDF on empty dossier should still render
        r5 = pro.get(f"{API}/structuro/bet/studies/{did}/report.pdf", timeout=60)
        assert r5.status_code == 200
        assert r5.headers.get("content-type", "").startswith("application/pdf")
        assert r5.content[:4] == b"%PDF"

        # Delete
        r6 = pro.delete(f"{API}/structuro/bet/studies/{did}", timeout=20)
        assert r6.status_code == 200
        # Confirm 404 after delete
        r7 = pro.get(f"{API}/structuro/bet/studies/{did}", timeout=20)
        assert r7.status_code == 404


class TestProjectsNotesField:
    """Projects endpoint should accept `notes` for offline chantier notes sync."""

    def test_patch_notes(self, pro):
        # Find any project of pro
        r = pro.get(f"{API}/projects", timeout=20)
        assert r.status_code == 200
        projects = r.json() if isinstance(r.json(), list) else r.json().get("projects", [])
        if not projects:
            pytest.skip("No project available for pro user")
        pid = projects[0].get("project_id") or projects[0].get("id")
        assert pid

        # PATCH notes
        new_note = "TEST_iter229 offline sync note"
        r2 = pro.patch(f"{API}/projects/{pid}", json={"notes": new_note}, timeout=20)
        assert r2.status_code in (200, 204), f"{r2.status_code} {r2.text[:200]}"

        # GET to verify persisted
        r3 = pro.get(f"{API}/projects/{pid}", timeout=20)
        assert r3.status_code == 200
        got = r3.json()
        assert got.get("notes") == new_note, f"notes not persisted: {got.get('notes')!r}"
