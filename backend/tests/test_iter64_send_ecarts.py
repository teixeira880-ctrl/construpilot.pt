"""Iter64 — Envoi email rapport écarts : chemins d'erreur (sans envoi réel).

Le happy path (200 + envoi Resend réel vers delivered@resend.dev) a été validé
manuellement — non répété ici pour préserver le quota Resend.
"""
from __future__ import annotations

import io
import os

import pytest
import requests


def _base():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    url = ln.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    return url.rstrip("/")


BASE_URL = _base()
ADMIN = ("admin@construpilot.fr", os.environ.get("TEST_ADMIN_PASSWORD", "Construpilot2026!"))


def _login():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN[0], "password": ADMIN[1]}, timeout=15)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _make_png():
    from PIL import Image
    im = Image.new("RGB", (400, 300), "white")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class TestIter64SendEcarts:
    """Classe unique — loadscope pin sur un seul worker."""

    @pytest.fixture(scope="class")
    def ctx(self):
        hdrs = _login()
        files = {"file": ("iter64.png", _make_png(), "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files,
                          headers=hdrs, timeout=60)
        assert r.status_code == 200, r.text
        pid = r.json()["plan_id"]
        yield {"pid": pid, "hdrs": hdrs}
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=hdrs, timeout=15)

    def test_send_invalid_email_422(self, ctx):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/ecarts-pdf/send",
                          json={"page_index": 0, "to_email": "pas-un-email"},
                          headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 422

    def test_send_without_analysis_400(self, ctx):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/ecarts-pdf/send",
                          json={"page_index": 0, "to_email": "client@exemple.fr"},
                          headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 400
        assert "Analyse IA" in r.json()["detail"]

    def test_send_unknown_plan_404(self, ctx):
        r = requests.post(f"{BASE_URL}/api/takeoffs/plan_inexistant/ecarts-pdf/send",
                          json={"page_index": 0, "to_email": "client@exemple.fr"},
                          headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 404

    def test_send_requires_auth(self, ctx):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/ecarts-pdf/send",
                          json={"page_index": 0, "to_email": "client@exemple.fr"},
                          timeout=15)
        assert r.status_code in (401, 403)
