"""
Iter 135 — Retest:
- Bug fix: relancer POST /cotes/check ne doit PLUS effacer geometry/narratif (préservés avec stale=True)
- Nouvelles pages de garde brandées (FR & PT) sur les 3 PDF (report.pdf, rapport.pdf, narratif.pdf)
"""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")

FR_EMAIL, FR_PASS = "pro@construpilot.fr", "Pro2026!"
PT_EMAIL, PT_PASS = "pro.pt@construpilot.pt", "ProPT2026!"
PLAN_FR = "plan_ee9385c91ee5"
PLAN_PT = "plan_e628b6d7479b"


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["token"]


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture(scope="module")
def tok_fr():
    return _login(FR_EMAIL, FR_PASS)


@pytest.fixture(scope="module")
def tok_pt():
    return _login(PT_EMAIL, PT_PASS)


def _open_pdf(content: bytes):
    import fitz
    return fitz.open(stream=content, filetype="pdf")


def _page1_text(content: bytes) -> str:
    doc = _open_pdf(content)
    try:
        return doc[0].get_text()
    finally:
        doc.close()


def _page1_images(content: bytes) -> int:
    doc = _open_pdf(content)
    try:
        return len(doc[0].get_images())
    finally:
        doc.close()


# --- (a) Bug critique : /cotes/check préserve geometry avec stale=True ---

def test_a_pre_check_geometry_present(tok_fr):
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes",
                     headers=_hdr(tok_fr), params={"page_index": 0}, timeout=60)
    assert r.status_code == 200, r.text[:400]
    rep = r.json()
    geo = rep.get("geometry") or {}
    assert geo, "geometry manquante avant le test — le prérequis 'analyse géométrique + narratif' doit exister sur plan_ee9385c91ee5 page 0"
    assert "niveau_global" in geo
    assert isinstance(geo.get("anomalies"), list)
    nar = geo.get("narratif") or {}
    sections = nar.get("sections") or []
    assert len(sections) >= 3, f"narratif.sections={len(sections)} (attendu ≥ 3)"


def test_b_check_background_preserves_geometry(tok_fr):
    r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes/check",
                      headers=_hdr(tok_fr), params={"background": 1},
                      json={"page_index": 0}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    job = r.json()
    job_id = job.get("job_id")
    assert job_id

    # Poll ≤ 120 s
    deadline = time.time() + 130
    status = None
    while time.time() < deadline:
        p = requests.get(f"{BASE_URL}/api/takeoffs/cotes-jobs/{job_id}",
                         headers=_hdr(tok_fr), timeout=15)
        assert p.status_code == 200
        j = p.json()
        status = j.get("status")
        if status == "done":
            break
        time.sleep(4)
    assert status == "done", f"job status={status}"

    # Re-GET /cotes → geometry toujours présente + stale True + narratif présent
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes",
                     headers=_hdr(tok_fr), params={"page_index": 0}, timeout=60)
    assert r.status_code == 200
    rep = r.json()
    geo = rep.get("geometry") or {}
    assert geo, "❌ REGRESSION: geometry effacée par /cotes/check"
    assert geo.get("stale") is True, f"geometry.stale attendu True, obtenu {geo.get('stale')}"
    nar = geo.get("narratif") or {}
    sections = nar.get("sections") or []
    assert len(sections) >= 3, f"narratif préservé ? sections={len(sections)}"


def test_c_narratif_pdf_still_available(tok_fr):
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes/narratif.pdf",
                     headers=_hdr(tok_fr), params={"page_index": 0}, timeout=60)
    assert r.status_code == 200
    assert "application/pdf" in r.headers.get("content-type", "")


# --- (b) Pages de garde brandées FR ---

FR_MENTIONS = [
    "CONTRÔLE DE COHÉRENCE DES COTATIONS",
    "RAPPORT DE CONTRÔLE",
    "Entreprise demandeuse",
    "Marc BTP",
    "ConstruPilot.fr",
    "Document examiné",
    "Portée de ce document",
    "bureau d'études techniques (BET)",
]


@pytest.mark.parametrize("path,extra", [
    ("rapport.pdf", {"court": 1}),
    ("narratif.pdf", {}),
    ("report.pdf", {}),
])
def test_fr_cover_pages(tok_fr, path, extra):
    params = {"page_index": 0, **extra}
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes/{path}",
                     headers=_hdr(tok_fr), params=params, timeout=90)
    assert r.status_code == 200, r.text[:200]
    txt = _page1_text(r.content)
    missing = [m for m in FR_MENTIONS if m not in txt]
    assert not missing, f"[{path}] mentions manquantes en page 1: {missing}\nExtrait: {txt[:600]}"
    imgs = _page1_images(r.content)
    assert imgs >= 1, f"[{path}] pas d'image (logo) sur page 1"


# --- (c) Pages de garde brandées PT ---

PT_MENTIONS = ["CONTROLO DE COERÊNCIA DAS COTAS", "Empresa requerente",
               "Marco Obras Lda", "Âmbito deste documento"]
PT_FORBIDDEN = ["Entreprise demandeuse", "Portée de ce document", "Portée"]


@pytest.mark.parametrize("path,extra", [
    ("rapport.pdf", {"court": 1}),
    ("narratif.pdf", {}),
    ("report.pdf", {}),
])
def test_pt_cover_pages(tok_pt, path, extra):
    params = {"page_index": 0, **extra}
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_PT}/cotes/{path}",
                     headers=_hdr(tok_pt), params=params, timeout=90)
    assert r.status_code == 200, r.text[:200]
    txt = _page1_text(r.content)
    missing = [m for m in PT_MENTIONS if m not in txt]
    assert not missing, f"[{path}] mentions PT manquantes en page 1: {missing}\nExtrait: {txt[:600]}"
    forbidden = [m for m in PT_FORBIDDEN if m in txt]
    assert not forbidden, f"[{path}] mentions FR interdites dans PDF PT: {forbidden}"
