"""Iter67 — Surfaces polygone persistées + modèles de message email.

Couvre :
- POST /measure kind=polygon (area_m2 + perimeter_m + label persistés)
- GET/POST/DELETE /api/emails/templates (CRUD user-scopé, cap 20)
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
    im = Image.new("RGB", (1200, 900), "white")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


class TestIter67SurfaceEtTemplates:
    """Classe unique — loadscope pin sur un seul worker (état séquentiel)."""

    @pytest.fixture(scope="class")
    def ctx(self):
        hdrs = _login()
        files = {"file": ("iter67.png", _make_png(), "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files,
                          headers=hdrs, timeout=60)
        assert r.status_code == 200, r.text
        pid = r.json()["plan_id"]
        r = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/calibrate", json={
            "page_index": 0, "p1": [100, 100], "p2": [600, 100],
            "real_distance_m": 10.0,
        }, headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        yield {"pid": pid, "hdrs": hdrs, "tids": []}
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=hdrs, timeout=15)

    def test_polygon_surface_persisted(self, ctx):
        # triangle rectangle 300x300 px @ 50 px/m = 6x6/2 = 18 m²
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measure", json={
            "page_index": 0, "kind": "polygon",
            "points": [[700, 600], [1000, 600], [1000, 900]],
            "label": "terrasse",
        }, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "polygon"
        assert abs(d["area_m2"] - 18.0) < 0.1
        assert d["perimeter_m"] > 0
        assert d["label"] == "terrasse"
        rp = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}", headers=ctx["hdrs"], timeout=15)
        m = rp.json()["measurements"][-1]
        assert m["kind"] == "polygon" and m["area_m2"] == d["area_m2"]

    def test_polygon_needs_3_points(self, ctx):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measure", json={
            "page_index": 0, "kind": "polygon", "points": [[0, 0], [10, 10]],
        }, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 422

    def test_template_create_and_list(self, ctx):
        r = requests.post(f"{BASE_URL}/api/emails/templates", json={
            "name": "Rapport standard", "body": "Bonjour,\nVoici le rapport.\nCordialement",
        }, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        tpl = r.json()["template"]
        assert tpl["template_id"].startswith("tpl_")
        ctx["tids"].append(tpl["template_id"])
        r = requests.get(f"{BASE_URL}/api/emails/templates", headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200
        ids = [t["template_id"] for t in r.json()["templates"]]
        assert tpl["template_id"] in ids

    def test_template_validation_422(self, ctx):
        r = requests.post(f"{BASE_URL}/api/emails/templates",
                          json={"name": "", "body": ""}, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 422

    def test_template_delete(self, ctx):
        tid = ctx["tids"][0]
        r = requests.delete(f"{BASE_URL}/api/emails/templates/{tid}",
                            headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200
        r = requests.delete(f"{BASE_URL}/api/emails/templates/{tid}",
                            headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 404

    def test_templates_require_auth(self, ctx):
        r = requests.get(f"{BASE_URL}/api/emails/templates", timeout=15)
        assert r.status_code in (401, 403)
