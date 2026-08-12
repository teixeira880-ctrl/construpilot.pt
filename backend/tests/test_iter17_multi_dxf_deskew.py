"""Iter17 backend tests: DXF import, DWG rejection, level detection PDF, level PATCH,
takeoff by level, deskew photo + skip, non-regression."""
import io
import os
import base64
import pytest
import requests
import numpy as np

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return (url or "").rstrip("/")

BASE_URL = _load_backend_url()

# -------- Fixtures --------

@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "demo@construpilot.fr", "password": "Demo2026!"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@construpilot.fr", "password": "Construpilot2026!"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def auth_hdr(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


# -------- Helpers to build fixtures in-memory --------

def _make_dxf_bytes():
    import ezdxf
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    # rectangle 10x8
    msp.add_line((0, 0), (10, 0))
    msp.add_line((10, 0), (10, 8))
    msp.add_line((10, 8), (0, 8))
    msp.add_line((0, 8), (0, 0))
    msp.add_text("SALON", dxfattribs={"height": 0.5}).set_placement((3, 4))
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def _make_two_page_pdf():
    import pymupdf
    doc = pymupdf.open()
    for label in ("RDC", "R+1"):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 50), label, fontsize=24)
        page.draw_rect(pymupdf.Rect(100, 100, 400, 400))
    data = doc.tobytes()
    doc.close()
    return data


def _make_perspective_png():
    """Rectangle blanc légèrement en perspective sur fond noir."""
    import cv2
    h, w = 600, 800
    img = np.zeros((h, w, 3), dtype=np.uint8)
    quad = np.array([[120, 100], [700, 140], [680, 520], [140, 500]], np.int32)
    cv2.fillPoly(img, [quad], (255, 255, 255))
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return buf.tobytes()


# ---------- DXF IMPORT ----------

def test_dxf_upload(auth_hdr):
    data = _make_dxf_bytes()
    files = {"file": ("test.dxf", data, "application/dxf")}
    r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files, headers=auth_hdr)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["kind"] == "dxf"
    assert j["page_count"] == 1
    assert j["plan_id"].startswith("plan_")
    # page details returned in _plan_summary (pages minus image_png_b64)
    pages = j["pages"]
    assert len(pages) == 1
    pg0 = pages[0]
    lines = [v for v in pg0["vectors"] if v["type"] == "line"]
    assert len(lines) >= 4, f"expected 4 lines, got {len(lines)}"
    texts = [t["text"] for t in pg0["text_blocks"]]
    assert any("SALON" in t for t in texts), f"SALON not found in {texts}"

    # GET page returns image_png_b64
    plan_id = j["plan_id"]
    r2 = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}/page/0", headers=auth_hdr)
    assert r2.status_code == 200
    assert r2.json().get("image_png_b64")


# ---------- DWG REJECTION ----------

def test_dwg_rejection(auth_hdr):
    files = {"file": ("fake.dwg", b"fake dwg content", "application/acad")}
    r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files, headers=auth_hdr)
    assert r.status_code == 422, r.text
    detail = r.json().get("detail", "")
    assert "DWG" in detail or "dwg" in detail.lower()
    assert "convert" in detail.lower()
    assert "cloudconvert.com" in detail


# ---------- LEVEL DETECTION PDF ----------

@pytest.fixture(scope="module")
def two_page_plan(auth_hdr):
    data = _make_two_page_pdf()
    files = {"file": ("floors.pdf", data, "application/pdf")}
    r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files, headers=auth_hdr)
    assert r.status_code == 200, r.text
    return r.json()


def test_level_detection_auto(two_page_plan):
    pages = two_page_plan["pages"]
    assert len(pages) == 2
    assert pages[0]["level_index"] == 0
    assert pages[0]["level_label"] == "RDC"
    assert pages[1]["level_index"] == 1
    assert pages[1]["level_label"] == "R+1"


# ---------- LEVEL PATCH manual ----------

def test_level_patch_manual(two_page_plan, auth_hdr):
    plan_id = two_page_plan["plan_id"]
    # Set page 0 → RDC explicit
    r = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/pages/0/level",
                       json={"level_index": 0, "level_label": "RDC"}, headers=auth_hdr)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # GET plan confirms
    g = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=auth_hdr)
    assert g.status_code == 200
    assert g.json()["pages"][0]["level_label"] == "RDC"

    # Clear via nulls
    r2 = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/pages/0/level",
                        json={"level_index": None, "level_label": None}, headers=auth_hdr)
    assert r2.status_code == 200
    g2 = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=auth_hdr)
    assert g2.json()["pages"][0]["level_label"] is None

    # Reset for downstream
    requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/pages/0/level",
                   json={"level_index": 0, "level_label": "RDC"}, headers=auth_hdr)

    # Invalid page_index
    r3 = requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/pages/99/level",
                        json={"level_index": 0, "level_label": "RDC"}, headers=auth_hdr)
    assert r3.status_code == 404


# ---------- TAKEOFF by level ----------

def test_takeoff_by_level(two_page_plan, auth_hdr):
    plan_id = two_page_plan["plan_id"]
    # PATCH both pages
    requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/pages/0/level",
                   json={"level_index": 0, "level_label": "RDC"}, headers=auth_hdr)
    requests.patch(f"{BASE_URL}/api/takeoffs/{plan_id}/pages/1/level",
                   json={"level_index": 1, "level_label": "R+1"}, headers=auth_hdr)
    # Calibrate both pages
    for idx in (0, 1):
        r = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/calibrate",
                          json={"page_index": idx, "p1": [0, 0], "p2": [100, 0],
                                "real_distance_m": 1.0}, headers=auth_hdr)
        assert r.status_code == 200, r.text

    # Add 1 room per page
    room1 = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/rooms",
                          json={"page_index": 0, "name": "Salon",
                                "points": [[0, 0], [400, 0], [400, 300], [0, 300]],
                                "ceiling_height_m": 2.5}, headers=auth_hdr)
    assert room1.status_code == 200, room1.text
    room2 = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/rooms",
                          json={"page_index": 1, "name": "Chambre",
                                "points": [[0, 0], [300, 0], [300, 200], [0, 200]],
                                "ceiling_height_m": 2.5}, headers=auth_hdr)
    assert room2.status_code == 200, room2.text

    # GET takeoff
    t = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}/takeoff", headers=auth_hdr)
    assert t.status_code == 200
    tj = t.json()
    assert "levels" in tj
    lvl_indices = [l["level_index"] for l in tj["levels"]]
    assert 0 in lvl_indices and 1 in lvl_indices
    # sorted ascending
    filtered = [i for i in lvl_indices if i is not None]
    assert filtered == sorted(filtered)
    # labels
    labels = {l["level_index"]: l["level_label"] for l in tj["levels"]}
    assert labels.get(0) == "RDC"
    assert labels.get(1) == "R+1"
    # totals = sum of levels
    total_floor = tj["totals"]["floor_m2"]
    sum_lvl = sum(l["totals"]["floor_m2"] for l in tj["levels"])
    assert abs(total_floor - sum_lvl) < 0.05


# ---------- DESKEW PHOTO ----------

def test_deskew_upload_with_flag(auth_hdr):
    png = _make_perspective_png()
    files = {"file": ("perspective.png", png, "image/png")}
    r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files,
                      data={"deskew": "true"}, headers=auth_hdr)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["kind"] == "image"
    assert j["page_count"] == 1


def test_deskew_skip(auth_hdr):
    png = _make_perspective_png()
    files = {"file": ("perspective.png", png, "image/png")}
    r = requests.post(f"{BASE_URL}/api/takeoffs/upload", files=files,
                      data={"deskew": "false"}, headers=auth_hdr)
    assert r.status_code == 200
    j = r.json()
    assert j["kind"] == "image"


# ---------- NON-REGRESSION ----------

def test_login_admin(admin_token):
    assert admin_token

def test_login_demo(demo_token):
    assert demo_token

def test_estimation_compute(auth_hdr):
    payload = {"surface_m2": 100, "project_type": "renovation_complete",
               "quality": "standard", "region": "idf"}
    r = requests.post(f"{BASE_URL}/api/estimation/compute", json=payload, headers=auth_hdr)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "lots" in j or "total_ttc" in j or "totals" in j


def test_prices_optimize(auth_hdr):
    payload = {"items": [{"query": "membrane pare-vapeur", "quantity": 1}]}
    r = requests.post(f"{BASE_URL}/api/prices/optimize", json=payload, headers=auth_hdr)
    assert r.status_code == 200, r.text
    j = r.json()
    # Ensure quantity preserved
    lines = j.get("multi", {}).get("lines") or j.get("lines") or []
    if lines:
        assert lines[0]["quantity"] == 1


def test_plans_billing(auth_hdr):
    r = requests.get(f"{BASE_URL}/api/plans", headers=auth_hdr)
    assert r.status_code == 200


def test_takeoffs_list(auth_hdr):
    r = requests.get(f"{BASE_URL}/api/takeoffs", headers=auth_hdr)
    assert r.status_code == 200


def test_admin_revenue(admin_token):
    r = requests.get(f"{BASE_URL}/api/admin/revenue/kpis",
                     headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200


def test_share_sms_config(auth_hdr):
    r = requests.get(f"{BASE_URL}/api/share/sms/config", headers=auth_hdr)
    assert r.status_code == 200
    assert r.json().get("twilio_enabled") is True


def test_push_public_key():
    r = requests.get(f"{BASE_URL}/api/push/public-key")
    assert r.status_code == 200
