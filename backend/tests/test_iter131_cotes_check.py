"""Iter 131 — Contrôle des cotes (backend)."""
import io
import os
import time

import ezdxf
import pytest
import requests

def _read_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for ln in f:
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    return ln.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return ""


BASE_URL = _read_backend_url()
API = f"{BASE_URL}/api"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) tests/1.0"}

PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"
IMG_PLAN = "plan_f6d3ae6fb2f2"
DXF_PLAN = "plan_383d0b5c291b"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update(UA)
    s.headers["Content-Type"] = "application/json"
    r = s.post(f"{API}/auth/login", json={"email": PRO_EMAIL, "password": PRO_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.text
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


# ---------- Validation ----------

def test_validation_tol_pct(session):
    r = session.post(f"{API}/takeoffs/{IMG_PLAN}/cotes/check",
                     json={"page_index": 0, "tol_pct": 0.01, "tol_cm": 3})
    assert r.status_code == 422, r.text
    r = session.post(f"{API}/takeoffs/{IMG_PLAN}/cotes/check",
                     json={"page_index": 0, "tol_pct": 25, "tol_cm": 3})
    assert r.status_code == 422, r.text


def test_unknown_plan_404(session):
    r = session.post(f"{API}/takeoffs/plan_does_not_exist/cotes/check",
                     json={"page_index": 0, "tol_pct": 2, "tol_cm": 3})
    assert r.status_code == 404, r.text


def test_get_cotes_unknown_plan(session):
    r = session.get(f"{API}/takeoffs/plan_does_not_exist/cotes?page_index=0")
    assert r.status_code == 404


# ---------- GET last report (image plan already has one per problem statement) ----------

def test_get_last_report_image_plan(session):
    r = session.get(f"{API}/takeoffs/{IMG_PLAN}/cotes?page_index=0")
    # Should be 200 if a previous check was run, else 404. Both acceptable pre-run.
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        j = r.json()
        for k in ("items", "chains", "summary", "tolerance", "calibration",
                  "reading", "page_index", "created_at"):
            assert k in j, f"missing key {k}"


# ---------- DXF exact path ----------

def test_dxf_cotes_check(session):
    r = session.post(f"{API}/takeoffs/{DXF_PLAN}/cotes/check",
                     json={"page_index": 0, "tol_pct": 2, "tol_cm": 3})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["reading"]["source"] == "dxf"
    assert len(j["items"]) == 4, f"expected 4 items got {len(j['items'])}"
    # item 3 override, indicated 5.5 measured 6.0 ko
    it3 = next((it for it in j["items"] if it["index"] == 3), None)
    assert it3, j["items"]
    assert it3["indicated_m"] == 5.5, it3
    assert it3["measured_m"] == 6.0, it3
    assert it3["status"] == "ko", it3
    assert it3["override"] is True
    # chains: at least one chain with parts sum 9.5 status ko
    assert len(j["chains"]) >= 1
    ko_chain = next((c for c in j["chains"] if c["status"] == "ko"), None)
    assert ko_chain, j["chains"]
    assert ko_chain["sum_m"] == 9.5
    # summary verdict
    assert j["summary"]["verdict"] == "ko"
    # required summary keys
    for k in ("total", "ok", "warn", "ko", "chains_total", "chains_ko",
              "max_delta_cm", "verdict"):
        assert k in j["summary"]


def test_get_dxf_last_report(session):
    r = session.get(f"{API}/takeoffs/{DXF_PLAN}/cotes?page_index=0")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["summary"]["verdict"] == "ko"


def test_dxf_overlay_png(session):
    r = session.get(f"{API}/takeoffs/{DXF_PLAN}/cotes/overlay.png?page_index=0",
                    headers=UA)
    assert r.status_code == 200, r.text[:300]
    assert r.headers.get("content-type", "").startswith("image/png")
    assert len(r.content) > 500


def test_dxf_report_pdf(session):
    r = session.get(f"{API}/takeoffs/{DXF_PLAN}/cotes/report.pdf?page_index=0",
                    headers=UA)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    body = r.content
    assert body.startswith(b"%PDF")
    # count PDF pages
    n_pages = body.count(b"/Type /Page") + body.count(b"/Type/Page")
    assert n_pages >= 2, f"expected >=2 pages, got {n_pages}"


# ---------- Plan detail returns cotes_checks ----------

def test_plan_detail_contains_cotes_checks(session):
    r = session.get(f"{API}/takeoffs/{DXF_PLAN}")
    assert r.status_code == 200
    j = r.json()
    assert "cotes_checks" in j, list(j.keys())
    assert "0" in j["cotes_checks"]


# ---------- Status logic sanity via a manually built DXF (exact) ----------

def _make_dxf_bytes():
    """Build a DXF with known dims for status logic test.

    - total 10 m (indicated & measured)
    - partial 4 m OK
    - partial faked '5.50' text over real 6 m → KO
    - vertical 6 m OK
    """
    doc = ezdxf.new(setup=True)
    doc.header["$INSUNITS"] = 6  # meters
    msp = doc.modelspace()
    # geometry
    msp.add_line((0, 0), (10, 0))     # bottom edge 10 m
    msp.add_line((0, 0), (0, 6))      # left edge 6 m
    msp.add_line((0, 6), (10, 6))
    msp.add_line((10, 0), (10, 6))
    # DIMENSIONS
    d1 = msp.add_linear_dim(base=(0, -1.0), p1=(0, 0), p2=(10, 0))  # total 10 m
    d1.render()
    d2 = msp.add_linear_dim(base=(0, -2.0), p1=(0, 0), p2=(4, 0))   # partial 4 m
    d2.render()
    d3 = msp.add_linear_dim(base=(0, -2.0), p1=(4, 0), p2=(10, 0),
                            text="5.50")               # partial fake '5.50'
    d3.render()
    d4 = msp.add_linear_dim(base=(-1.0, 0), p1=(0, 0), p2=(0, 6), angle=90)  # vertical 6 m
    d4.render()
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def test_status_logic_via_uploaded_dxf(session):
    files = {"file": ("iter131_test.dxf", _make_dxf_bytes(), "application/dxf")}
    hdr = {"Authorization": session.headers["Authorization"], **UA}
    r = requests.post(f"{API}/takeoffs/upload", headers=hdr, files=files)
    assert r.status_code == 200, r.text[:400]
    plan_id = r.json().get("plan_id") or r.json().get("id")
    assert plan_id
    try:
        r = session.post(f"{API}/takeoffs/{plan_id}/cotes/check",
                         json={"page_index": 0, "tol_pct": 2, "tol_cm": 3})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["reading"]["source"] == "dxf"
        # find fake 5.50 dim (measured != indicated)
        ko_items = [it for it in j["items"] if it["status"] == "ko"]
        assert any(abs(it["indicated_m"] - 5.5) < 0.01 and abs(it["measured_m"] - 6.0) < 0.01
                   for it in ko_items), j["items"]
        # ok items have delta ~ 0
        ok_items = [it for it in j["items"] if it["status"] == "ok"]
        assert any(abs(it["indicated_m"] - 10.0) < 0.01 for it in ok_items)
    finally:
        session.delete(f"{API}/takeoffs/{plan_id}")


# ---------- AI path on image plan (slow) ----------

def test_ai_cotes_check_image_plan(session):
    """Runs the AI-driven check exactly once (slow ~30 s)."""
    t0 = time.time()
    r = session.post(f"{API}/takeoffs/{IMG_PLAN}/cotes/check",
                     json={"page_index": 0, "tol_pct": 2, "tol_cm": 3},
                     timeout=120)
    dt = time.time() - t0
    assert r.status_code == 200, f"({dt:.1f}s) {r.status_code} {r.text[:400]}"
    j = r.json()
    assert j["reading"]["source"] == "ai"
    assert "snapped_endpoints" in j["reading"]
    assert isinstance(j["items"], list) and len(j["items"]) >= 1
    for it in j["items"]:
        for k in ("index", "x1", "y1", "x2", "y2", "orientation",
                  "indicated_m", "measured_m", "delta_cm", "delta_pct",
                  "tolerance_cm", "status"):
            assert k in it, f"missing {k}: {it}"
        assert it["orientation"] in ("h", "v", "o")
        assert it["status"] in ("ok", "warn", "ko")
    # overlay + PDF should work now
    r2 = session.get(f"{API}/takeoffs/{IMG_PLAN}/cotes/overlay.png?page_index=0", headers=UA)
    assert r2.status_code == 200
    assert r2.headers.get("content-type", "").startswith("image/png")
    r3 = session.get(f"{API}/takeoffs/{IMG_PLAN}/cotes/report.pdf?page_index=0", headers=UA)
    assert r3.status_code == 200
    assert r3.content.startswith(b"%PDF")
