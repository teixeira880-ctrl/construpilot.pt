"""Iter13 — ConstruPilot PLAN (takeoff 2D)

Couvre :
- Geometry engine (unitaires)
- Upload PNG/PDF plans
- Calibration + check
- Measure distance/polygon
- Rooms upsert/delete
- Takeoff & Materials
- Twilio config (from_configured=False, twilio_enabled=False)
- Sanity: login, estimation ?surface prefill (backend), public estimation, revenue cockpit
"""
from __future__ import annotations

import io
import os
import sys

import pytest
import requests

def _get_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        # Read from frontend/.env
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass
    assert url, "REACT_APP_BACKEND_URL not set"
    return url.rstrip("/")

BASE_URL = _get_base_url()

ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PWD = "Construpilot2026!"
USER_EMAIL = "demo@construpilot.fr"
USER_PWD = "Demo2026!"

# Import backend modules for unit tests
sys.path.insert(0, "/app/backend")
from engines import geometry as G  # noqa: E402


# ============ HELPERS ============

def _login(email, pwd):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pwd}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def user_token():
    return _login(USER_EMAIL, USER_PWD)


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PWD)


@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}"}


# ============ GEOMETRY UNIT TESTS ============

class TestGeometry:
    def test_polygon_area_square(self):
        pts = [(0, 0), (400, 0), (400, 400), (0, 400)]
        assert G.polygon_area_m2(pts, 100.0) == pytest.approx(16.0, rel=1e-6)

    def test_polyline_length_345(self):
        assert G.polyline_length_m([(0, 0), (300, 0), (300, 400)], 100.0) == pytest.approx(7.0)

    def test_distance_pythagore(self):
        assert G.distance_m((0, 0), (300, 400), 100.0) == pytest.approx(5.0)

    def test_compute_calibration(self):
        c = G.compute_calibration((0, 0), (500, 0), 5.0)
        assert c["pixels_per_meter"] == 100.0

    def test_calibration_check_ok(self):
        r = G.calibration_check(3.18, 3.20)
        assert r["delta_pct"] == pytest.approx(0.63, abs=0.01)
        assert r["ok"] is True

    def test_paint_liters_100m2(self):
        r = G.paint_liters(100)
        assert r["liters_recommended"] == 23

    def test_placo_100m2(self):
        r = G.placo_quantity(100)
        assert r["plates"] == 35

    def test_floor_parquet_100m2(self):
        r = G.floor_quantity(100, "parquet")
        assert r["waste_pct"] == 7.0
        assert r["quantity_m2"] == pytest.approx(107.0, abs=0.5)

    def test_skirting_20m(self):
        r = G.skirting_length_m(20, 1.8)
        assert r["net_m"] == pytest.approx(18.2, abs=0.01)
        assert r["quantity_m"] == pytest.approx(20.02, abs=0.05)


# ============ UPLOAD (PNG) ============

def _make_png_bytes(w=800, h=600):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([100, 100, 700, 500], outline="black", width=3)
    d.text((200, 200), "Salon", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestPlanFlow:
    plan_id = None

    def test_01_upload_png(self, user_headers):
        png = _make_png_bytes()
        files = {"file": ("test_plan.png", png, "image/png")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload",
                          files=files, headers=user_headers, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "image"
        assert d["page_count"] == 1
        assert "plan_id" in d
        assert len(d["pages"]) == 1
        TestPlanFlow.plan_id = d["plan_id"]

    def test_02_list_takeoffs(self, user_headers):
        # New endpoint /api/takeoffs — must return user's takeoff plans.
        r = requests.get(f"{BASE_URL}/api/takeoffs", headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "plans" in body
        plans = body["plans"]
        assert isinstance(plans, list)
        # Must NOT contain billing 'code' key (Free/Pro/Business).
        assert not any(p.get("code") in ("free", "pro", "business") for p in plans), \
            "takeoff list must not shadow billing plans"
        # Our uploaded plan_id must be present.
        found = any(p.get("plan_id") == TestPlanFlow.plan_id for p in plans)
        assert found, f"uploaded plan {TestPlanFlow.plan_id} not found in {plans}"

    def test_02b_billing_plans_still_ok(self, user_headers):
        # Billing endpoint must still return subscription plans catalog.
        r = requests.get(f"{BASE_URL}/api/plans", headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "plans" in body
        plans = body["plans"]
        codes = {(p.get("code") or "").lower() for p in plans}
        # Expect at least the classic subscription tier "free".
        assert "free" in codes, f"billing /api/plans doesn't return subscription catalog: {codes}"
        # Should have 'features'/'tagline' typical of billing plans.
        assert any("features" in p or "tagline" in p for p in plans)

    def test_03_get_page_image(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/page/0",
                         headers=user_headers, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d.get("image_png_b64")
        assert len(d["image_png_b64"]) > 100

    def test_04_calibrate_invalid_distance(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/calibrate",
                          json={"page_index": 0, "p1": [100, 100], "p2": [700, 100],
                                "real_distance_m": 0},
                          headers=user_headers, timeout=15)
        assert r.status_code == 422

    def test_05_calibrate_404(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/plan_deadbeef/calibrate",
                          json={"page_index": 0, "p1": [0, 0], "p2": [100, 0],
                                "real_distance_m": 1.0},
                          headers=user_headers, timeout=15)
        assert r.status_code == 404

    def test_06_calibrate_ok(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/calibrate",
                          json={"page_index": 0, "p1": [100, 100], "p2": [700, 100],
                                "real_distance_m": 6.0},
                          headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["calibration"]["pixels_per_meter"] == 100.0

    def test_07_plan_calibrations_persisted(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}",
                         headers=user_headers, timeout=15)
        assert r.status_code == 200
        c = r.json()["calibrations"]["0"]
        assert c["pixels_per_meter"] == 100.0
        assert c["method"] == "two_points"

    def test_08_calibrate_check(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/calibrate/check",
                          json={"page_index": 0, "p1": [100, 100], "p2": [400, 100],
                                "expected_m": 3.0},
                          headers=user_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "delta_pct" in d
        assert d["ok"] is True

    def test_09_measure_distance(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/measure",
                          json={"page_index": 0, "kind": "distance",
                                "points": [[0, 0], [300, 400]]},
                          headers=user_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["value_m"] == pytest.approx(5.0)

    def test_10_measure_polygon(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/measure",
                          json={"page_index": 0, "kind": "polygon",
                                "points": [[100, 100], [700, 100], [700, 500], [100, 500]]},
                          headers=user_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["area_m2"] == pytest.approx(24.0)
        assert d["perimeter_m"] == pytest.approx(20.0)

    def test_11_room_upsert(self, user_headers):
        # Salon 6×4m at 100 ppm → 600×400 px
        pts = [[100, 100], [700, 100], [700, 500], [100, 500]]
        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/rooms",
                          json={"page_index": 0, "name": "Salon", "points": pts,
                                "ceiling_height_m": 2.5,
                                "openings": [
                                    {"type": "porte", "width_m": 0.9, "height_m": 2.1},
                                    {"type": "fenetre", "width_m": 1.2, "height_m": 1.35},
                                ]},
                          headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["surface_m2"] == pytest.approx(24.0)
        assert d["wall_area_gross_m2"] == pytest.approx(50.0)
        assert d["wall_area_net_m2"] == pytest.approx(46.49, abs=0.02)
        TestPlanFlow.room_id = d["room_id"]

    def test_12_room_update_no_dup(self, user_headers):
        pts = [[100, 100], [700, 100], [700, 500], [100, 500]]
        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/rooms",
                          json={"page_index": 0, "name": "Salon MAJ", "points": pts,
                                "ceiling_height_m": 2.5, "openings": [],
                                "room_id": TestPlanFlow.room_id},
                          headers=user_headers, timeout=15)
        assert r.status_code == 200
        # Verify not duplicated
        r2 = requests.get(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}",
                          headers=user_headers, timeout=15)
        rooms = r2.json()["rooms"]
        assert len(rooms) == 1
        assert rooms[0]["name"] == "Salon MAJ"

    def test_13_takeoff(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/takeoff",
                         headers=user_headers, timeout=15)
        assert r.status_code == 200
        t = r.json()["totals"]
        assert t["floor_m2"] == pytest.approx(24.0)
        # After update (openings removed), walls_net == walls_gross == 50
        assert t["walls_net_m2"] == pytest.approx(50.0)

    def test_14_materials_parquet(self, user_headers):
        # Restore the room with openings
        pts = [[100, 100], [700, 100], [700, 500], [100, 500]]
        requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/rooms",
                      json={"page_index": 0, "name": "Salon", "points": pts,
                            "ceiling_height_m": 2.5,
                            "openings": [
                                {"type": "porte", "width_m": 0.9, "height_m": 2.1},
                                {"type": "fenetre", "width_m": 1.2, "height_m": 1.35},
                            ],
                            "room_id": TestPlanFlow.room_id},
                      headers=user_headers, timeout=15)

        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/materials",
                          json={}, headers=user_headers, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "floor" in d and "paint" in d and "placo" in d and "skirting" in d
        assert d["floor"]["material"] == "parquet"
        assert d["floor"]["quantity_m2"] == pytest.approx(25.68, abs=0.05)
        assert d["paint"]["liters_recommended"] > 0
        assert d["placo"]["plates"] > 0
        assert d["skirting"]["quantity_m"] > 0

    def test_15_materials_carrelage(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/materials",
                          json={"floor_material": "carrelage"},
                          headers=user_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["floor"]["waste_pct"] == 10.0
        assert d["floor"]["quantity_m2"] == pytest.approx(26.4, abs=0.05)

    def test_16_measure_no_calib(self, user_headers):
        # Upload another plan without calibration
        png = _make_png_bytes()
        up = requests.post(f"{BASE_URL}/api/takeoffs/upload",
                           files={"file": ("nocalib.png", png, "image/png")},
                           headers=user_headers, timeout=30)
        pid = up.json()["plan_id"]
        r = requests.post(f"{BASE_URL}/api/takeoffs/{pid}/measure",
                          json={"page_index": 0, "kind": "distance",
                                "points": [[0, 0], [10, 0]]},
                          headers=user_headers, timeout=15)
        assert r.status_code == 400
        assert "calibr" in r.text.lower()
        # cleanup
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=user_headers, timeout=10)

    def test_17_delete_room(self, user_headers):
        r = requests.delete(
            f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}/rooms/{TestPlanFlow.room_id}",
            headers=user_headers, timeout=15)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_99_cleanup(self, user_headers):
        r = requests.delete(f"{BASE_URL}/api/takeoffs/{TestPlanFlow.plan_id}",
                            headers=user_headers, timeout=15)
        assert r.status_code == 200


# ============ UPLOAD PDF ============

class TestPdfUpload:
    def test_pdf_upload(self, user_headers):
        try:
            import pymupdf as fitz
        except ImportError:
            import fitz
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "Test plan PDF - Salon 4m x 3m")
        pdf_bytes = doc.write()
        doc.close()

        files = {"file": ("plan.pdf", pdf_bytes, "application/pdf")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload",
                          files=files, headers=user_headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["kind"] == "pdf"
        assert d["page_count"] == 1
        pid = d["plan_id"]
        # cleanup
        requests.delete(f"{BASE_URL}/api/takeoffs/{pid}", headers=user_headers, timeout=10)


# ============ TWILIO ============

class TestTwilio:
    def test_sms_config(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/share/sms/config",
                         headers=user_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["sid_configured"] is True
        assert d["token_configured"] is True
        assert d["from_configured"] is False
        assert d["twilio_enabled"] is False

    def test_sms_send_503(self, user_headers):
        # Need real project - use bogus id, expect 404 (project missing) OR 503 (twilio disabled).
        r = requests.post(f"{BASE_URL}/api/projects/bogus_project/share/sms",
                          json={"to": "+33612345678", "message": "test"},
                          headers=user_headers, timeout=10)
        assert r.status_code in (404, 503), f"got {r.status_code}: {r.text}"


# ============ SANITY ============

class TestSanity:
    def test_login_admin(self):
        _login(ADMIN_EMAIL, ADMIN_PWD)

    def test_dashboard(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/auth/me", headers=user_headers, timeout=10)
        assert r.status_code == 200

    def test_estimation_compute(self, user_headers):
        r = requests.post(f"{BASE_URL}/api/estimation/compute",
                          json={"surface_m2": 80, "quality": "standard",
                                "trades": ["peinture"], "region": "idf"},
                          headers=user_headers, timeout=20)
        assert r.status_code in (200, 201), r.text

    def test_revenue_cockpit(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/admin/revenue/kpis",
                         headers={"Authorization": f"Bearer {admin_token}"}, timeout=15)
        assert r.status_code == 200

    def test_plans_list_empty_ok(self, user_headers):
        # Billing subscription catalog.
        r = requests.get(f"{BASE_URL}/api/plans", headers=user_headers, timeout=10)
        assert r.status_code == 200
        assert "plans" in r.json()

    def test_takeoffs_list_ok(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/takeoffs", headers=user_headers, timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "plans" in body
        # takeoff list must not contain billing 'code' key
        assert not any(p.get("code") in ("free", "pro", "business") for p in body["plans"])

    def test_push_public_key(self, user_headers):
        r = requests.get(f"{BASE_URL}/api/push/public-key", headers=user_headers, timeout=10)
        assert r.status_code == 200

    def test_project_share(self, user_headers):
        # bogus project_id — expect 404
        r = requests.get(f"{BASE_URL}/api/projects/bogus_project/share",
                         headers=user_headers, timeout=10)
        assert r.status_code in (404, 405, 200)
