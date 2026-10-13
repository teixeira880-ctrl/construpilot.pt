"""Iter169 backend integration tests: calculations, corrections, crop, unified PDF report.

Uses live pro account credentials. Reads conv id from /app/memory/.conv_calc and plan_3e4bb8efb992.
"""
import os
import pathlib
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"
OTHER_EMAIL = "demo@construpilot.fr"
OTHER_PASSWORD = "Demo2026!"
PLAN_ID = "plan_3e4bb8efb992"

CONV_ID = pathlib.Path("/app/memory/.conv_calc").read_text().strip().splitlines()[0].strip()


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def pro():
    return _login(PRO_EMAIL, PRO_PASSWORD)


@pytest.fixture(scope="module")
def other():
    return _login(OTHER_EMAIL, OTHER_PASSWORD)


# --- calculations listing ---
def test_list_calculations(pro):
    r = pro.get(f"{BASE_URL}/api/assistant/conversations/{CONV_ID}/calculations", timeout=30)
    assert r.status_code == 200, r.text[:300]
    calcs = r.json()["calculations"]
    assert isinstance(calcs, list)
    assert len(calcs) >= 2, f"expected >=2 records, got {len(calcs)}"
    # Ensure required fields
    for c in calcs:
        for f in ("calc_ref", "tool", "args", "result"):
            assert f in c, f"missing {f} in {c.keys()}"
    # At least one superseded record + a correction record
    has_correction = any(c.get("correction") and c.get("supersedes") for c in calcs)
    has_superseded = any(c.get("superseded_by") for c in calcs)
    assert has_correction, "no record has correction+supersedes"
    assert has_superseded, "no record marked superseded_by"


def test_list_calculations_other_user_404(other):
    r = other.get(f"{BASE_URL}/api/assistant/conversations/{CONV_ID}/calculations", timeout=30)
    assert r.status_code == 404


# --- correction endpoint ---
def _find_live_chain(pro):
    calcs = pro.get(f"{BASE_URL}/api/assistant/conversations/{CONV_ID}/calculations", timeout=30).json()["calculations"]
    for c in calcs:
        if c["tool"] == "check_dimension_chain" and not c.get("superseded_by"):
            return c
    return None


def test_correct_calculation_success(pro):
    live = _find_live_chain(pro)
    assert live, "no live check_dimension_chain record to correct"
    # find a valid label from args (spans/thicknesses etc.)
    def find_label(node):
        if isinstance(node, dict):
            if node.get("label") and "candidates_m" in node:
                return node["label"]
            for v in node.values():
                r = find_label(v)
                if r:
                    return r
        elif isinstance(node, list):
            for v in node:
                r = find_label(v)
                if r:
                    return r
        return None

    label = find_label(live["args"])
    assert label, "no correctable label found"
    r = pro.post(f"{BASE_URL}/api/assistant/calculations/{live['calc_ref']}/correct",
                 json={"label": label, "value_m": 4.1}, timeout=30)
    assert r.status_code == 200, r.text[:400]
    j = r.json()
    assert j["ok"] is True
    assert j["calc_ref"] != live["calc_ref"]
    assert j["supersedes"] == live["calc_ref"]
    assert (j["result"].get("calculation") or {}).get("formula")

    # verify user message with kind 'correction' present
    conv = pro.get(f"{BASE_URL}/api/assistant/conversations/{CONV_ID}", timeout=30).json()
    msgs = conv.get("messages") or conv.get("msgs") or []
    kinds = [m.get("kind") for m in msgs]
    assert "correction" in kinds, f"no correction message; kinds={kinds[-6:]}"


def test_correct_unknown_label_404(pro):
    live = _find_live_chain(pro)
    if not live:
        pytest.skip("no live record")
    r = pro.post(f"{BASE_URL}/api/assistant/calculations/{live['calc_ref']}/correct",
                 json={"label": "___nope___", "value_m": 1.0}, timeout=30)
    assert r.status_code == 404


def test_correct_other_user_404(other, pro):
    calcs = pro.get(f"{BASE_URL}/api/assistant/conversations/{CONV_ID}/calculations", timeout=30).json()["calculations"]
    ref = calcs[0]["calc_ref"]
    r = other.post(f"{BASE_URL}/api/assistant/calculations/{ref}/correct",
                   json={"label": "x", "value_m": 1.0}, timeout=30)
    assert r.status_code == 404


# --- crop endpoint ---
def test_crop_ok(pro):
    r = pro.get(f"{BASE_URL}/api/assistant/plans/{PLAN_ID}/crop",
                params={"page": 0, "box": "0.80,0.90,0.99,0.99"}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 100


def test_crop_bad_box_400(pro):
    r = pro.get(f"{BASE_URL}/api/assistant/plans/{PLAN_ID}/crop",
                params={"page": 0, "box": "not-a-box"}, timeout=30)
    assert r.status_code == 400


def test_crop_unknown_plan_404(pro):
    r = pro.get(f"{BASE_URL}/api/assistant/plans/plan_nonexistent/crop",
                params={"page": 0, "box": "0.1,0.1,0.5,0.5"}, timeout=30)
    assert r.status_code == 404


def test_crop_other_user_404(other):
    r = other.get(f"{BASE_URL}/api/assistant/plans/{PLAN_ID}/crop",
                  params={"page": 0, "box": "0.1,0.1,0.5,0.5"}, timeout=30)
    assert r.status_code == 404


# --- unified PDF report ---
def test_report_pdf_ok(pro):
    r = pro.get(f"{BASE_URL}/api/assistant/conversations/{CONV_ID}/report.pdf", timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 500
    # Try to extract text for content assertions
    try:
        from pypdf import PdfReader
        from io import BytesIO
        reader = PdfReader(BytesIO(r.content))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        text = ""
    if text:
        assert "Rapport de contrôle" in text or "controle" in text.lower() or "ConstruPilot" in text
        # signature line
        assert "ConstruPilot" in text


def test_report_pdf_other_user_404(other):
    r = other.get(f"{BASE_URL}/api/assistant/conversations/{CONV_ID}/report.pdf", timeout=30)
    assert r.status_code == 404
