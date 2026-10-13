"""Iter 132 — Contrôle des cotes: PATCH edit/ignore + POST recompute (no AI)."""
import os
import time
import pytest
import requests


def _read_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if v:
        return v.rstrip("/")
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                return ln.split("=", 1)[1].strip().rstrip("/")
    return ""


BASE_URL = _read_backend_url()
API = f"{BASE_URL}/api"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) tests/1.0"}

PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"
DXF_PLAN = "plan_383d0b5c291b"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update(UA)
    s.headers["Content-Type"] = "application/json"
    r = s.post(f"{API}/auth/login", json={"email": PRO_EMAIL, "password": PRO_PASSWORD})
    assert r.status_code == 200, r.text[:300]
    tok = r.json().get("token") or r.json().get("access_token")
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


@pytest.fixture(scope="module", autouse=True)
def ensure_report(session):
    """Make sure DXF plan has a report before edits, and restore item 3 after tests."""
    r = session.get(f"{API}/takeoffs/{DXF_PLAN}/cotes?page_index=0")
    if r.status_code == 404:
        r = session.post(f"{API}/takeoffs/{DXF_PLAN}/cotes/check",
                         json={"page_index": 0, "tol_pct": 2, "tol_cm": 3})
        assert r.status_code == 200, r.text
    yield
    # Restore state: item3 back to 5.5 (in case a test left it edited), item2 not ignored
    try:
        session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/3",
                      json={"page_index": 0, "indicated_m": 5.5})
        session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/2",
                      json={"page_index": 0, "ignored": False})
        # And ensure tolerance back to 2/3
        session.post(f"{API}/takeoffs/{DXF_PLAN}/cotes/recompute",
                     json={"page_index": 0, "tol_pct": 2, "tol_cm": 3})
    except Exception:
        pass


# ---------- PATCH edit: correct item 3 5.5 → 6.0 ----------

def test_patch_edit_item3_corrects_to_ok(session):
    t0 = time.time()
    r = session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/3",
                      json={"page_index": 0, "indicated_m": 6.0})
    dt = time.time() - t0
    assert r.status_code == 200, r.text
    assert dt < 5.0, f"took {dt:.1f}s (should be instant, no AI)"
    j = r.json()
    it3 = next((it for it in j["items"] if it["index"] == 3), None)
    assert it3 is not None
    assert it3["status"] == "ok", it3
    assert it3.get("edited") is True
    assert it3.get("original_m") == 5.5
    assert it3["indicated_m"] == 6.0
    # KO chain of 4+5.5 should now be ok (4+6=10)
    assert j["summary"]["verdict"] == "ok", j["summary"]
    ok_chains = [c for c in j.get("chains") or [] if c["status"] == "ok"]
    assert any(abs(c["sum_m"] - 10.0) < 0.01 for c in ok_chains), j["chains"]


def test_patch_edit_item3_restore(session):
    r = session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/3",
                      json={"page_index": 0, "indicated_m": 5.5})
    assert r.status_code == 200
    j = r.json()
    it3 = next((it for it in j["items"] if it["index"] == 3), None)
    assert it3["indicated_m"] == 5.5
    assert it3["status"] == "ko"
    assert j["summary"]["verdict"] == "ko"


# ---------- PATCH ignore ----------

def test_patch_ignore_item2(session):
    r = session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/2",
                      json={"page_index": 0, "ignored": True})
    assert r.status_code == 200, r.text
    j = r.json()
    it2 = next((it for it in j["items"] if it["index"] == 2), None)
    assert it2 is not None
    assert it2.get("ignored") is True
    assert it2.get("status") == "ignored", it2
    assert j["summary"]["total"] == 3
    assert j["summary"]["ignored"] == 1
    assert j.get("chains") == [] or len(j.get("chains") or []) == 0, j.get("chains")


def test_patch_unignore_item2(session):
    r = session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/2",
                      json={"page_index": 0, "ignored": False})
    assert r.status_code == 200
    j = r.json()
    assert j["summary"]["total"] == 4
    assert j["summary"].get("ignored", 0) == 0
    assert len(j.get("chains") or []) >= 1


# ---------- PATCH validation ----------

def test_patch_index_out_of_range(session):
    r = session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/99",
                      json={"page_index": 0, "indicated_m": 3.0})
    assert r.status_code == 404


def test_patch_invalid_indicated_zero(session):
    r = session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/3",
                      json={"page_index": 0, "indicated_m": 0})
    assert r.status_code == 422


def test_patch_invalid_indicated_negative(session):
    r = session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/3",
                      json={"page_index": 0, "indicated_m": -1.5})
    assert r.status_code == 422


# ---------- POST recompute (tolerance change, no AI) ----------

def test_recompute_tol10(session):
    t0 = time.time()
    r = session.post(f"{API}/takeoffs/{DXF_PLAN}/cotes/recompute",
                     json={"page_index": 0, "tol_pct": 10, "tol_cm": 3})
    dt = time.time() - t0
    assert r.status_code == 200, r.text
    assert dt < 5.0, f"took {dt:.1f}s (should be instant)"
    j = r.json()
    assert j["tolerance"]["pct"] == 10
    assert j["tolerance"]["cm"] == 3
    it3 = next((it for it in j["items"] if it["index"] == 3), None)
    assert it3 is not None
    # 50 cm delta on 5.5 m = 9.1% ≤ 10% but > 6% → warn
    assert it3["status"] == "warn", it3


def test_recompute_tol2_back_to_ko(session):
    r = session.post(f"{API}/takeoffs/{DXF_PLAN}/cotes/recompute",
                     json={"page_index": 0, "tol_pct": 2, "tol_cm": 3})
    assert r.status_code == 200
    j = r.json()
    it3 = next((it for it in j["items"] if it["index"] == 3), None)
    assert it3["status"] == "ko"


# ---------- Report PDF after edit still 200 ----------

def test_pdf_after_edit(session):
    # Apply an edit so PDF has an edited row
    r = session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/3",
                      json={"page_index": 0, "indicated_m": 6.0})
    assert r.status_code == 200
    r = session.get(f"{API}/takeoffs/{DXF_PLAN}/cotes/report.pdf?page_index=0",
                    headers=UA)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert r.content.startswith(b"%PDF")
    # Restore
    session.patch(f"{API}/takeoffs/{DXF_PLAN}/cotes/items/3",
                  json={"page_index": 0, "indicated_m": 5.5})
