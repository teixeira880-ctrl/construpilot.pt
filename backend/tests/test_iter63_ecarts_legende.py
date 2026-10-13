"""Iter63 — Rapport PDF écarts + légende presets PDF + cotes cliquables (backend).

Couvre :
- GET /api/takeoffs/{id}/ecarts-pdf : 200 + application/pdf, matching live
- 400 si analyse IA absente, 400 si aucune pièce
- build_takeoff_pdf avec légende des catégories (non-régression rendu)
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


def _login(email, pwd):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


def _mongo():
    import pymongo
    env = {}
    with open("/app/backend/.env") as f:
        for ln in f:
            if "=" in ln:
                k, v = ln.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return pymongo.MongoClient(env["MONGO_URL"])[env["DB_NAME"]]


def _make_png(w=1200, h=900):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([100, 100, 700, 500], outline="black", width=6)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


FAKE_AI = {
    "plan_type": "residential", "page_index": 0, "confidence": 0.9,
    "dimension_lines": [
        {"value_m": 6.0, "bbox_norm": [100 / 1200, 80 / 900, 400 / 1200, 80 / 900],
         "confidence": 0.9},
        {"value_m": 4.0, "bbox_norm": [0.05, 0.2, 0.05, 0.2 + 200 / 900],
         "confidence": 0.8},
        {"value_m": 2.0, "bbox_norm": [0.5, 0.9, 0.5 + 100 / 1200, 0.9],
         "confidence": 0.9},
    ],
    "rooms": [
        {"name": "Séjour", "surface_written_m2": 121.0, "estimated_surface_m2": 120.0},
    ],
}


class TestIter63EcartsPdf:
    """Classe unique — loadscope pin sur un seul worker (état séquentiel partagé)."""

    @pytest.fixture(scope="class")
    def ctx(self):
        hdrs = {"Authorization": f"Bearer {_login(*ADMIN)}"}
        files = {"file": ("plan_iter63.png", _make_png(), "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files,
                          headers=hdrs, timeout=60)
        assert r.status_code == 200, r.text
        pid = r.json()["plan_id"]
        yield {"pid": pid, "hdrs": hdrs}
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=hdrs, timeout=15)

    def test_ecarts_pdf_requires_analysis(self, ctx):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/ecarts-pdf?page_index=0",
                         headers=ctx["hdrs"], timeout=30)
        assert r.status_code == 400
        assert "Analyse IA" in r.json()["detail"]

    def test_ecarts_pdf_requires_rooms(self, ctx):
        db = _mongo()
        assert db.plans_takeoff.update_one(
            {"plan_id": ctx["pid"]}, {"$set": {"ai_analysis": FAKE_AI}}).matched_count == 1
        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/ecarts-pdf?page_index=0",
                         headers=ctx["hdrs"], timeout=30)
        assert r.status_code == 400
        assert "pièce" in r.json()["detail"].lower()

    def test_ecarts_pdf_generated(self, ctx):
        # Calibration par cotes (50 px/m) puis pièce 500x500 px = 100 m²
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/calibrate/from-cotes",
                          json={"page_index": 0}, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/rooms", json={
            "page_index": 0, "name": "Séjour",
            "points": [[100, 100], [600, 100], [600, 600], [100, 600]],
            "ceiling_height_m": 2.5,
        }, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text

        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/ecarts-pdf?page_index=0",
                         headers=ctx["hdrs"], timeout=60)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 1500

class TestIter63CodeReviewFixes:
    """Régressions des 4 défauts confirmés par la revue de code (classe unique)."""

    @pytest.fixture(scope="class")
    def ctx(self):
        hdrs = {"Authorization": f"Bearer {_login(*ADMIN)}"}
        files = {"file": ("plan_iter63b.png", _make_png(), "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files,
                          headers=hdrs, timeout=60)
        assert r.status_code == 200, r.text
        pid = r.json()["plan_id"]
        db = _mongo()
        assert db.plans_takeoff.update_one(
            {"plan_id": pid}, {"$set": {"ai_analysis": FAKE_AI}}).matched_count == 1
        r = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/calibrate/from-cotes",
                          json={"page_index": 0}, headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        r = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/rooms", json={
            "page_index": 0, "name": "Séjour",
            "points": [[100, 100], [600, 100], [600, 600], [100, 600]],
            "ceiling_height_m": 2.5,
        }, headers=hdrs, timeout=15)
        assert r.status_code == 200, r.text
        yield {"pid": pid, "hdrs": hdrs, "room_id": r.json()["room_id"]}
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=hdrs, timeout=15)

    def test_walls_summary_ml_not_zero(self, ctx):
        # FIX HIGH : walls-summary lisait scale_m_per_px (clé inexistante) → ml=0
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/detect-walls?page_index=0",
                          headers=ctx["hdrs"], timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["segment_count"] > 0
        r = requests.get(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/walls-summary",
                         headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["scale_m_per_px"] is not None
        assert abs(d["scale_m_per_px"] - 0.02) < 0.001   # 1/50 px/m
        total_ml = sum(t["ml"] for t in d["totals"].values())
        assert total_ml > 0, d

    def test_patch_height_recomputes_walls(self, ctx):
        # FIX MEDIUM : PATCH height écrivait height_m sans recalcul
        r = requests.patch(
            f"{BASE_URL}/api/takeoffs/{ctx['pid']}/rooms/{ctx['room_id']}",
            json={"height_m": 3.0}, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        room = r.json()["room"]
        assert room["ceiling_height_m"] == 3.0
        # pièce 10x10 m → périmètre 40 m → murs bruts 40x3 = 120 m²
        assert abs(room["wall_area_gross_m2"] - 120.0) < 1.5, room
        assert abs(room["volume_m3"] - 300.0) < 4.0

    def test_estimate_uses_ceiling_height(self, ctx):
        # FIX MEDIUM : estimate lisait height_m (absent) → retombait sur 2.5
        r = requests.post(
            f"{BASE_URL}/api/takeoffs/{ctx['pid']}/rooms/{ctx['room_id']}/estimate",
            json={"trades": ["paint"]}, headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["room"]["height_m"] == 3.0

    def test_skirting_door_count(self, ctx):
        # FIX MEDIUM : décompte portes lisait o.type au lieu de o.kind
        r = requests.post(
            f"{BASE_URL}/api/takeoffs/{ctx['pid']}/rooms/{ctx['room_id']}/openings",
            json={"kind": "porte", "width_m": 0.9, "height_m": 2.1},
            headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        r = requests.post(f"{BASE_URL}/api/takeoffs/{ctx['pid']}/materials",
                          json={"room_ids": [ctx["room_id"]],
                                "include": {"skirting": True}},
                          headers=ctx["hdrs"], timeout=15)
        assert r.status_code == 200, r.text
        skirting = r.json()["skirting"]
        # périmètre 40 m − 0.9 m de porte déduite
        assert skirting["doors_deduction_m"] == 0.9, skirting
        assert skirting["net_m"] < 40.0, skirting

    def test_builders_render_legend_and_ecarts(self):
        # Rendu direct des builders (sans HTTP) — non-régression ReportLab
        import sys
        sys.path.insert(0, "/app/backend")
        from engines.pdf_takeoff import build_ecarts_pdf, build_takeoff_pdf

        pdf = build_ecarts_pdf(
            {"plan_id": "p1", "filename": "test.pdf"},
            {"method": "auto_cotes", "pixels_per_meter": 50.0,
             "samples_used": 3, "spread_pct": 1.2, "confidence": 0.85},
            [{"room_name": "Séjour", "measured_m2": 100.0, "written_m2": 121.0,
              "delta_pct": 21.0},
             {"room_name": "Cuisine", "measured_m2": 12.0, "written_m2": 12.3,
              "delta_pct": 2.5}],
            [{"name": "Couloir", "surface_m2": 6.5}],
            page_index=0)
        assert pdf[:5] == b"%PDF-"

        rooms = [{"name": "Séjour", "surface_m2": 100, "perimeter_m": 40,
                  "wall_area_gross_m2": 100, "wall_area_net_m2": 95,
                  "openings_area_m2": 5, "ceiling_area_m2": 100,
                  "preset_id": "pr1"}]
        presets = {"pr1": {"preset_id": "pr1", "name": "Carrelage 60x60",
                           "kind": "floor", "unit": "m²", "price_per_unit": 45.0,
                           "notes": "Grès cérame"}}
        pdf2 = build_takeoff_pdf(
            {"plan_id": "p1", "filename": "test.pdf", "page_count": 1},
            {"room_count": 1, "rooms": rooms, "levels": [], "totals":
             {"floor_m2": 100, "ceiling_m2": 100, "walls_gross_m2": 100,
              "walls_net_m2": 95, "perimeter_m": 40}},
            None, presets_by_id=presets)
        assert pdf2[:5] == b"%PDF-"
