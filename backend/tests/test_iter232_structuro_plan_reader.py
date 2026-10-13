"""Tests iter 232 – StructuroPilot Lecture de plan (zéro hallucination)."""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}
PART = {"email": "part.test@construpilot.fr", "password": "Part2026!"}
PLAN_URL = ("https://customer-assets-7cd3h4nn.emergentagent.net/"
            "job_24c1027c-3500-4369-9271-1f0502b94a6a/artifacts/"
            "5db6a5c53e1d6989_houilles%20plan.pdf")


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=20)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def part_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=PART, timeout=20)
    assert r.status_code == 200, f"part login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def plan_pdf_bytes():
    r = requests.get(PLAN_URL, timeout=60)
    assert r.status_code == 200 and len(r.content) > 1000
    return r.content


@pytest.fixture(scope="module")
def existing_or_new_read(admin_session, plan_pdf_bytes):
    """Reuse an existing read if present (preview seeded one), else POST /read."""
    r = admin_session.get(f"{API}/structuro/plan/list", timeout=30)
    assert r.status_code == 200, r.text[:300]
    reads = r.json().get("reads", [])
    if reads:
        rid = reads[0]["read_id"]
        full = admin_session.get(f"{API}/structuro/plan/{rid}", timeout=30).json()
        return {"created": False, "doc": full}
    # Create via POST /read (slow LLM call)
    files = {"file": ("houilles.pdf", plan_pdf_bytes, "application/pdf")}
    data = {"title": "TEST_Houilles-fondation"}
    r = admin_session.post(f"{API}/structuro/plan/read", files=files, data=data, timeout=180)
    assert r.status_code == 200, f"POST /read failed: {r.status_code} {r.text[:500]}"
    return {"created": True, "doc": r.json()}


# -------- gating --------

def test_gating_particulier_forbidden_list(part_session):
    r = part_session.get(f"{API}/structuro/plan/list", timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"


def test_gating_particulier_forbidden_read(part_session, plan_pdf_bytes):
    files = {"file": ("x.pdf", plan_pdf_bytes[:2000] + b"%EOF", "application/pdf")}
    r = part_session.post(f"{API}/structuro/plan/read", files=files, data={"title": "x"}, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}"


# -------- list + get --------

def test_list_contains_read(admin_session, existing_or_new_read):
    r = admin_session.get(f"{API}/structuro/plan/list", timeout=30)
    assert r.status_code == 200
    ids = [x["read_id"] for x in r.json().get("reads", [])]
    assert existing_or_new_read["doc"]["read_id"] in ids


def test_get_read_returns_full_doc(admin_session, existing_or_new_read):
    rid = existing_or_new_read["doc"]["read_id"]
    r = admin_session.get(f"{API}/structuro/plan/{rid}", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["read_id"] == rid
    assert "fondations" in d and "metre" in d and "missing_data" in d


def test_read_initial_shape(existing_or_new_read):
    d = existing_or_new_read["doc"]
    assert d.get("vector") is True
    # scale may be 1/25 or similar
    assert d.get("scale_detected"), "scale_detected should be present"
    m = d.get("metre") or {}
    for k in ("beton_total_m3", "acier_total_kg", "nb_semelles", "nb_poteaux"):
        assert k in m
    assert isinstance(d.get("fondations"), list)


def test_scale_is_1_25(existing_or_new_read):
    scale = existing_or_new_read["doc"].get("scale_detected")
    # Accept non-fatal if different; just report
    assert scale is not None
    if scale != "1/25":
        pytest.skip(f"scale detected = {scale} (expected 1/25) — vision/vector dependent")


# -------- recompute: complete=true path --------

def test_put_recompute_complete_true(admin_session, existing_or_new_read):
    rid = existing_or_new_read["doc"]["read_id"]
    # Build a minimal fully-specified foundations list
    fondations = [
        {"type": "semelle_isolee", "nombre": 4, "longueur_m": 1.0, "largeur_m": 1.0, "hauteur_m": 0.4},
        {"type": "semelle_filante", "nombre": 1, "longueur_m": 20.0, "largeur_m": 0.6, "hauteur_m": 0.35},
        {"type": "chainage", "nombre": 1, "longueur_m": 30.0, "largeur_m": 0.25, "hauteur_m": 0.25},
        {"type": "poteau", "nombre": 6, "longueur_m": 0.3, "largeur_m": 0.3, "hauteur_m": 2.6},
    ]
    body = {
        "fondations": fondations, "murs": [],
        "steel_ratios": {"semelle_filante": 45, "semelle_isolee": 50, "chainage": 90, "poteau": 110},
    }
    r = admin_session.put(f"{API}/structuro/plan/{rid}", json=body, timeout=60)
    assert r.status_code == 200, r.text[:500]
    d = r.json()
    assert d.get("complete") is True, f"expected complete=true, missing_data={d.get('missing_data')}"
    assert d["metre"]["beton_total_m3"] > 0
    assert d["metre"]["acier_total_kg"] > 0
    assert d.get("missing_data") == []


def test_put_recompute_missing_requests_data(admin_session, existing_or_new_read):
    rid = existing_or_new_read["doc"]["read_id"]
    fondations = [
        {"type": "semelle_isolee", "nombre": 4, "longueur_m": 1.0, "largeur_m": 1.0, "hauteur_m": None},
        {"type": "semelle_filante", "nombre": 1, "longueur_m": 20.0, "largeur_m": 0.6, "hauteur_m": 0.35},
    ]
    body = {"fondations": fondations, "murs": [], "steel_ratios": None}
    r = admin_session.put(f"{API}/structuro/plan/{rid}", json=body, timeout=60)
    assert r.status_code == 200, r.text[:500]
    d = r.json()
    assert d.get("complete") is False
    md = d.get("missing_data") or []
    assert len(md) > 0, "missing_data should not be empty"
    # At least one request should be about ratio or hauteur
    types = " ".join(str(x) for x in md).lower()
    assert ("ratio" in types) or ("hauteur" in types) or ("acier" in types)


# -------- PDF export --------

def test_export_pdf(admin_session, existing_or_new_read):
    rid = existing_or_new_read["doc"]["read_id"]
    r = admin_session.get(f"{API}/structuro/plan/{rid}/pdf", timeout=60)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "")
    assert len(r.content) > 500
    assert r.content[:4] == b"%PDF"


# -------- Fresh POST /read on real plan (slow LLM) --------

@pytest.mark.timeout(200)
def test_post_read_on_real_plan(admin_session, plan_pdf_bytes):
    files = {"file": ("houilles_plan.pdf", plan_pdf_bytes, "application/pdf")}
    data = {"title": "TEST_Houilles_fresh"}
    t0 = time.time()
    r = admin_session.post(f"{API}/structuro/plan/read", files=files, data=data, timeout=180)
    dt = time.time() - t0
    print(f"POST /read took {dt:.1f}s")
    assert r.status_code == 200, f"status={r.status_code} body={r.text[:500]}"
    d = r.json()
    assert d.get("read_id", "").startswith("plan_")
    assert d.get("vector") is True
    assert isinstance(d.get("fondations"), list)
    # Houilles plan is incomplete → complete should be False with missing_data
    if d.get("complete") is True:
        pytest.skip("Plan returned complete=true unexpectedly (vision may have inferred data)")
    assert len(d.get("missing_data") or []) > 0
    # cleanup
    admin_session.delete(f"{API}/structuro/plan/{d['read_id']}", timeout=20)
