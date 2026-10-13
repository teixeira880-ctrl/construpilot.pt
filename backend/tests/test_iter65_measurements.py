"""Iter65 — Persistance des mesures ad-hoc + historique des envois de rapports.

Couvre :
- POST /measure persiste (measurement_id, cap 50) et renvoie value_m/length_m
- GET plan renvoie measurements + sent_reports
- DELETE /measurements/{id} et DELETE /measurements?page_index (clear page)
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


class TestIter65Measurements:
    """Classe unique — loadscope pin sur un seul worker (état séquentiel)."""

    @pytest.fixture(scope="class")
    def ctx(self):
        hdrs = _login()
        files = {"file": ("iter65.png", _make_png(), "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files,
                          headers=hdrs, timeout=60)
        assert r.status_code == 200, r.text
        pid = r.json()["plan_id"]
        # calibration 2 points : 500 px = 10 m → 50 px/m
        r = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/calibrate", json={
            "page_index": 0, "p1": [100, 100], "p2": [600, 100],
            "real_distance_m": 10.0,
        }, headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        yield {"pid": pid, "hdrs": hdrs, "mids": []}
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=hdrs, timeout=15)

    def test_measure_distance_persisted(self, ctx):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measure", json={
            "page_index": 0, "kind": "distance", "points": [[100, 200], [600, 200]],
        }, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["measurement_id"].startswith("mes_")
        assert d["value_m"] == 10.0
        assert d["length_m"] == 10.0          # champ affiché par le volet Objets
        ctx["mids"].append(d["measurement_id"])

    def test_measure_polyline_persisted(self, ctx):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measure", json={
            "page_index": 0, "kind": "polyline",
            "points": [[100, 300], [350, 300], [350, 400]],
        }, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["length_m"] == 7.0    # 250px + 100px = 350px / 50
        ctx["mids"].append(r.json()["measurement_id"])

    def test_plan_returns_measurements_and_sent_reports(self, ctx):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}", headers=ctx["hdrs"], timeout=15)
        p = r.json()
        assert len(p["measurements"]) == 2
        assert "sent_reports" in p            # historique envois exposé sur la fiche
        assert p["measurements"][0]["created_at"]

    def test_delete_single_measurement(self, ctx):
        r = requests.delete(
            f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measurements/{ctx['mids'][0]}",
            headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200
        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}", headers=ctx["hdrs"], timeout=15)
        assert len(r.json()["measurements"]) == 1

    def test_clear_page_measurements(self, ctx):
        r = requests.delete(
            f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measurements?page_index=0",
            headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200
        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}", headers=ctx["hdrs"], timeout=15)
        assert r.json()["measurements"] == []

    def test_delete_unknown_plan_404(self, ctx):
        r = requests.delete(f"{BASE_URL}/api/takeoffs/plan_inconnu/measurements/mes_x",
                            headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 404


class TestIter66MeasureLabels:
    """Iter66 — libellés modifiables sur les mesures + PDF avec mesures."""

    @pytest.fixture(scope="class")
    def ctx(self):
        hdrs = _login()
        files = {"file": ("iter66.png", _make_png(), "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files,
                          headers=hdrs, timeout=60)
        assert r.status_code == 200, r.text
        pid = r.json()["plan_id"]
        r = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/calibrate", json={
            "page_index": 0, "p1": [100, 100], "p2": [600, 100],
            "real_distance_m": 10.0,
        }, headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        yield {"pid": pid, "hdrs": hdrs}
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=hdrs, timeout=15)

    def test_measure_with_label(self, ctx):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measure", json={
            "page_index": 0, "kind": "distance",
            "points": [[100, 200], [600, 200]], "label": "murs parpaing",
        }, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["label"] == "murs parpaing"
        ctx["mid"] = r.json()["measurement_id"]

    def test_rename_measurement(self, ctx):
        r = requests.patch(
            f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measurements/{ctx['mid']}",
            json={"label": "murs en brique"}, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["label"] == "murs en brique"
        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}", headers=ctx["hdrs"], timeout=15)
        assert r.json()["measurements"][0]["label"] == "murs en brique"

    def test_rename_unknown_404(self, ctx):
        r = requests.patch(
            f"{BASE_URL}/api/takeoffs/{ctx['pid']}/measurements/mes_inconnu",
            json={"label": "x"}, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 404

    def test_takeoff_pdf_includes_measurements(self, ctx):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/pdf",
                         headers=ctx["hdrs"], timeout=60)
        assert r.status_code == 200, r.text
        assert r.content[:5] == b"%PDF-"

    def test_builder_measurements_section(self):
        import sys
        sys.path.insert(0, "/app/backend")
        from engines.pdf_takeoff import build_takeoff_pdf
        pdf = build_takeoff_pdf(
            {"plan_id": "p1", "filename": "t.pdf", "page_count": 1},
            {"room_count": 0, "rooms": [], "levels": [], "totals":
             {"floor_m2": 0, "ceiling_m2": 0, "walls_gross_m2": 0,
              "walls_net_m2": 0, "perimeter_m": 0}},
            None,
            measurements=[{"kind": "distance", "value_m": 10.0, "page_index": 0,
                           "label": "murs parpaing", "created_at": "2026-06-14T10:00:00"},
                          {"kind": "polyline", "length_m": 7.0, "page_index": 0,
                           "label": None, "created_at": "2026-06-14T10:05:00"}])
        assert pdf[:5] == b"%PDF-"
