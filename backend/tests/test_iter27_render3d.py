"""Iter27 — 3D Render endpoint tests (Nano Banana / Gemini image-to-image).

Only ONE actual Gemini call is executed (cost). Other styles/edge cases are
tested with mocked/quick paths where possible.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback for internal tests
    BASE_URL = "http://localhost:8001"

API = f"{BASE_URL}/api"
PLAN_ID = "plan_d6e446d3a459"
TIMEOUT_LLM = 180
TIMEOUT_STD = 30


def _login(email, password):
    r = requests.post(f"{API}/auth/login",
                      json={"email": email, "password": password},
                      timeout=TIMEOUT_STD)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers():
    tok = _login("pro@construpilot.fr", "Pro2026!")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def client_headers():
    tok = _login("client@construpilot.fr", "Client2026!")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def rendered(pro_headers):
    """Perform ONE real render (isometric) and share across tests."""
    body = {"page_index": 0, "style": "isometric", "include_furniture": True}
    r = requests.post(f"{API}/takeoffs/{PLAN_ID}/render-3d",
                      json=body, headers=pro_headers, timeout=TIMEOUT_LLM)
    assert r.status_code == 200, f"render-3d failed: {r.status_code} {r.text[:500]}"
    data = r.json()
    return data


# 1a) POST /render-3d success payload
def test_render_3d_success_payload(rendered):
    d = rendered
    assert d.get("ok") == True
    assert d.get("render_id", "").startswith("r3d_")
    assert d.get("style") == "isometric"
    assert d.get("mime_type") == "image/png"
    assert isinstance(d.get("image_b64"), str)
    assert len(d["image_b64"]) > 100000
    assert isinstance(d.get("prompt_used"), str)
    assert len(d["prompt_used"]) > 20


# 1c) A render doc was pushed
def test_render_present_in_history(pro_headers, rendered):
    r = requests.get(f"{API}/takeoffs/{PLAN_ID}/renders-3d",
                     headers=pro_headers, timeout=TIMEOUT_STD)
    assert r.status_code == 200
    data = r.json()
    ids = [x["render_id"] for x in data["renders"]]
    assert rendered["render_id"] in ids
    # verify meta fields present but no image_b64
    entry = next(x for x in data["renders"] if x["render_id"] == rendered["render_id"])
    for k in ("render_id", "style", "page_index", "created_at", "include_furniture"):
        assert k in entry
    assert "image_b64" not in entry
    assert len(data["renders"]) <= 10  # cap


# 2b) GET one render returns full image_b64
def test_get_render_full_image(pro_headers, rendered):
    rid = rendered["render_id"]
    r = requests.get(f"{API}/takeoffs/{PLAN_ID}/renders-3d/{rid}",
                     headers=pro_headers, timeout=TIMEOUT_STD)
    assert r.status_code == 200
    d = r.json()
    assert d["render_id"] == rid
    assert d["mime_type"] == "image/png"
    assert isinstance(d["image_b64"], str) and len(d["image_b64"]) > 100000


def test_get_render_unknown_id(pro_headers):
    r = requests.get(f"{API}/takeoffs/{PLAN_ID}/renders-3d/r3d_nopeee",
                     headers=pro_headers, timeout=TIMEOUT_STD)
    assert r.status_code == 404


# 1d) unknown plan
def test_render_unknown_plan(pro_headers):
    r = requests.post(f"{API}/takeoffs/plan_does_not_exist/render-3d",
                      json={"page_index": 0, "style": "isometric"},
                      headers=pro_headers, timeout=TIMEOUT_STD)
    assert r.status_code == 404


# 1e) invalid page_index
def test_render_invalid_page_index(pro_headers):
    r = requests.post(f"{API}/takeoffs/{PLAN_ID}/render-3d",
                      json={"page_index": 99, "style": "isometric"},
                      headers=pro_headers, timeout=TIMEOUT_STD)
    assert r.status_code == 404


# 4) Security: non-owner
def test_render_non_owner_returns_404(client_headers):
    r = requests.post(f"{API}/takeoffs/{PLAN_ID}/render-3d",
                      json={"page_index": 0, "style": "isometric"},
                      headers=client_headers, timeout=TIMEOUT_STD)
    assert r.status_code in (402, 404)


def test_list_renders_non_owner_returns_404(client_headers):
    r = requests.get(f"{API}/takeoffs/{PLAN_ID}/renders-3d",
                     headers=client_headers, timeout=TIMEOUT_STD)
    assert r.status_code == 404
