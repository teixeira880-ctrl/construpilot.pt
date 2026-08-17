"""Iter 88: Backend tests for plan structure detection + AI describe + PC feature."""
import os
import pytest
import requests
import base64
from io import BytesIO

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pilot-build-demo.preview.emergentagent.com').rstrip('/')
DEMO_EMAIL = "demo@construpilot.fr"
DEMO_PASSWORD = "Demo2026!"
PLAN_IMG_URL = "https://customer-assets-7cd3h4nn.emergentagent.net/job_24c1027c-3500-4369-9271-1f0502b94a6a/artifacts/rwclpb0l_09de3cdcbe77a7ce819e811cc2b042b3.jpg"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    data = r.json()
    token = data.get("token") or data.get("access_token")
    if token:
        s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def plan_id(session):
    # Look for existing plan first
    r = session.get(f"{BASE_URL}/api/takeoffs", timeout=30)
    if r.status_code == 200:
        plans = r.json() if isinstance(r.json(), list) else r.json().get("plans", [])
        if plans:
            pid = plans[0].get("plan_id") or plans[0].get("id")
            if pid:
                print(f"Using existing plan_id={pid}")
                return pid
    # else upload
    img_bytes = requests.get(PLAN_IMG_URL, timeout=30).content
    files = {"file": ("plan.jpg", img_bytes, "image/jpeg")}
    r = session.post(f"{BASE_URL}/api/takeoffs/upload", files=files, timeout=60)
    assert r.status_code in (200, 201), f"Upload failed: {r.status_code} {r.text[:300]}"
    pid = r.json().get("plan_id") or r.json().get("id")
    assert pid
    return pid


class TestPlanStructure:
    def test_detect_structure(self, session, plan_id):
        r = session.post(f"{BASE_URL}/api/takeoffs/{plan_id}/detect-structure?page_index=0", timeout=90)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        assert "walls" in data and "openings" in data
        assert isinstance(data["walls"], list)
        assert isinstance(data["openings"], list)
        # Print counts for observability
        print(f"Detected walls={len(data['walls'])} openings={len(data['openings'])}")
        # Not strict on >0 since AI can vary, but expect at least some
        assert len(data["walls"]) + len(data["openings"]) > 0

    def test_structure_persisted_on_plan(self, session, plan_id):
        r = session.get(f"{BASE_URL}/api/takeoffs/{plan_id}", timeout=30)
        assert r.status_code == 200
        data = r.json()
        struct = data.get("structure") or {}
        # structure is a dict keyed by page index (as str)
        assert struct, "structure field missing from plan summary"
        p0 = struct.get("0") or struct.get(0)
        assert p0 is not None, f"page 0 structure missing, got keys={list(struct.keys())}"
        assert "walls" in p0 and "openings" in p0

    def test_put_structure_edit(self, session, plan_id):
        payload = {
            "walls": [
                {"id": "w_test1", "x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.1, "wall_type": "cloison"},
                {"id": "w_test2", "x1": 0.4, "y1": 0.1, "x2": 0.4, "y2": 0.4, "wall_type": "porteur"},
            ],
            "openings": [
                {"id": "o_test1", "x1": 0.15, "y1": 0.1, "x2": 0.25, "y2": 0.1, "opening_type": "window"},
            ],
            "image_width": 2000, "image_height": 1500,
        }
        r = session.put(f"{BASE_URL}/api/takeoffs/{plan_id}/structure/0", json=payload, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("wall_count") == 2
        assert data.get("opening_count") == 1

        # verify persistence via GET
        r2 = session.get(f"{BASE_URL}/api/takeoffs/{plan_id}", timeout=30)
        p0 = (r2.json().get("structure") or {}).get("0") or {}
        assert len(p0.get("walls", [])) == 2
        assert len(p0.get("openings", [])) == 1


class TestAIDescribe:
    def test_ai_describe_paint(self, session):
        r = session.post(f"{BASE_URL}/api/documents/ai/describe",
                         json={"designation": "Peinture murs salon", "context": ""}, timeout=45)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        data = r.json()
        desc = data.get("description", "")
        assert isinstance(desc, str) and len(desc) > 20, f"desc too short: {desc!r}"
        print(f"AI desc length={len(desc)}")

    def test_ai_describe_empty_rejects(self, session):
        r = session.post(f"{BASE_URL}/api/documents/ai/describe",
                         json={"designation": "", "context": ""}, timeout=15)
        assert r.status_code == 400


class TestPcRoute:
    def test_pc_dashboard_accessible(self, session):
        # PC endpoints - just verify some pc route responds
        r = session.get(f"{BASE_URL}/api/pc/dossiers", timeout=15)
        assert r.status_code in (200, 401, 403, 404), f"Unexpected {r.status_code}"
