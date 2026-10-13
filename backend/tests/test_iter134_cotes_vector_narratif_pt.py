"""
Iter 134 — Backend tests:
- Vector PDF extraction (calibration pdf_vector)
- Cotes report cross vector+ai
- Recompute stability
- PDFs: narratif, rapport, report (FR)
- Portuguese (PT) narratif + report + rapport
- Persistent cotes_jobs in Mongo (background=1)
- 404 narratif when absent
"""
import os
import time
import io
import pytest
import requests

def _base_url():
    u = os.environ.get("REACT_APP_BACKEND_URL")
    if not u:
        try:
            with open("/app/frontend/.env") as fh:
                for line in fh:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        u = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    assert u, "REACT_APP_BACKEND_URL not set"
    return u.rstrip("/")

BASE_URL = _base_url()

FR_EMAIL = "pro@construpilot.fr"
FR_PASS = "Pro2026!"
PT_EMAIL = "pro.pt@construpilot.pt"
PT_PASS = "ProPT2026!"

PLAN_FR = "plan_ee9385c91ee5"
PLAN_PT = "plan_e628b6d7479b"
PLAN_NO_NARR = "plan_3396f3ebea53"

HOUILLES = "/tmp/houilles.pdf"


def login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tok_fr():
    return login(FR_EMAIL, FR_PASS)


@pytest.fixture(scope="module")
def tok_pt():
    return login(PT_EMAIL, PT_PASS)


def _pdf_text(content: bytes) -> str:
    try:
        import fitz  # pymupdf
        doc = fitz.open(stream=content, filetype="pdf")
        out = []
        for p in doc:
            out.append(p.get_text())
        doc.close()
        return "\n".join(out)
    except Exception:
        try:
            from PyPDF2 import PdfReader
            r = PdfReader(io.BytesIO(content))
            return "\n".join((p.extract_text() or "") for p in r.pages)
        except Exception:
            return ""


def _pdf_pages(content: bytes) -> int:
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        from PyPDF2 import PdfReader
        return len(PdfReader(io.BytesIO(content)).pages)


# --- Upload vectoriel (optionnel) ---
def test_upload_vector_pdf(tok_fr):
    if not os.path.exists(HOUILLES):
        pytest.skip("houilles.pdf absent")
    with open(HOUILLES, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/takeoffs/upload",
            headers=hdr(tok_fr),
            files={"file": ("houilles.pdf", f, "application/pdf")},
            timeout=180,
        )
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    calibs = data.get("calibrations") or {}
    c0 = calibs.get("0") or calibs.get(0) or {}
    assert c0.get("method") == "pdf_vector", f"method={c0.get('method')} calibs={calibs}"
    eff = c0.get("effective_scale_denominator") or c0.get("scale_denominator")
    assert eff and 30 < float(eff) < 45, f"effective_scale_denominator={eff}"
    su = c0.get("samples_used")
    assert su == 51, f"samples_used={su}"


# --- GET cotes report ---
def test_get_cotes_report(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes",
        headers=hdr(tok_fr), params={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    rep = r.json()
    reading = rep.get("reading") or {}
    assert reading.get("source") == "pdf_vector+ai", f"source={reading.get('source')}"
    cross = reading.get("cross") or {}
    assert cross.get("vector") == 51, f"cross={cross}"
    assert isinstance(cross.get("divergences"), list)
    assert isinstance(cross.get("ai_only"), int)
    assert (cross.get("confirmed") or 0) > 0
    items = rep.get("items") or []
    pdf_items = [i for i in items if i.get("source") == "pdf"]
    assert len(pdf_items) >= 51, f"pdf items={len(pdf_items)}"
    assert all(i.get("measured_exact_m") is not None for i in pdf_items[:5])
    chains = rep.get("chains") or []
    assert len(chains) > 0, "chains empty"
    for c in chains:
        assert "niveau" in c and c.get("exact") is True
    calib = rep.get("calibration") or {}
    assert calib.get("method") == "pdf_vector"
    summ = rep.get("summary") or {}
    assert summ.get("ko", -1) == 0, f"summary={summ}"


# --- Recompute ---
def test_recompute(tok_fr):
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes/recompute",
        headers=hdr(tok_fr), json={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200, r.text[:400]
    rep = r.json()
    assert (rep.get("chains") or [])
    assert (rep.get("summary") or {}).get("total") is not None


# --- Narratif PDF FR ---
def test_narratif_pdf_fr(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes/narratif.pdf",
        headers=hdr(tok_fr), params={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200, r.text[:200]
    assert "application/pdf" in r.headers.get("content-type", "")
    assert _pdf_pages(r.content) >= 4
    txt = _pdf_text(r.content)
    assert "RAPPORT NARRATIF" in txt.upper() or "RAPPORT NARRATIF" in txt


def test_rapport_pdf_fr_court(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes/rapport.pdf",
        headers=hdr(tok_fr), params={"page_index": 0, "court": 1}, timeout=60,
    )
    assert r.status_code == 200, r.text[:200]
    assert "application/pdf" in r.headers.get("content-type", "")


def test_report_pdf_fr_mentions_vectorielles(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes/report.pdf",
        headers=hdr(tok_fr), params={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200
    txt = _pdf_text(r.content).lower()
    assert "vectoriel" in txt, "expected 'vectorielles' mention in report.pdf FR"


# --- PT ---
def test_narratif_pdf_pt(tok_pt):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_PT}/cotes/narratif.pdf",
        headers=hdr(tok_pt), params={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200, r.text[:200]
    txt = _pdf_text(r.content)
    up = txt.upper()
    assert "RELATÓRIO NARRATIVO" in up or "RELATORIO NARRATIVO" in up, f"PT narratif missing header. Sample: {txt[:300]}"
    assert "RAPPORT NARRATIF" not in up


def test_report_pdf_pt(tok_pt):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_PT}/cotes/report.pdf",
        headers=hdr(tok_pt), params={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200
    txt = _pdf_text(r.content)
    up = txt.upper()
    assert "CONTROLO DAS COTAS" in up, f"PT report missing. Sample: {txt[:300]}"
    assert "CONTRÔLE DES COTES" not in up and "CONTROLE DES COTES" not in up


def test_rapport_pdf_pt_court(tok_pt):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_PT}/cotes/rapport.pdf",
        headers=hdr(tok_pt), params={"page_index": 0, "court": 1}, timeout=60,
    )
    assert r.status_code == 200
    txt = _pdf_text(r.content).upper()
    assert "RELATÓRIO DE CONTROLO DA PLANTA" in txt or "RELATORIO DE CONTROLO DA PLANTA" in txt, f"missing PT rapport title. sample: {txt[:400]}"


def test_fr_cannot_access_pt_plan(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_PT}/cotes",
        headers=hdr(tok_fr), params={"page_index": 0}, timeout=30,
    )
    assert r.status_code == 404, f"expected 404, got {r.status_code}"


# --- Jobs persistés ---
def test_cotes_check_background_job(tok_fr, tok_pt):
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/{PLAN_FR}/cotes/check",
        headers=hdr(tok_fr), params={"background": 1}, json={"page_index": 0}, timeout=30,
    )
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    job_id = data.get("job_id")
    assert job_id, f"no job_id in {data}"
    assert data.get("status") in ("running", "queued")

    # Unknown job id
    r2 = requests.get(
        f"{BASE_URL}/api/takeoffs/cotes-jobs/unknown-xyz-{int(time.time())}",
        headers=hdr(tok_fr), timeout=15,
    )
    assert r2.status_code in (200, 404)
    if r2.status_code == 200:
        assert r2.json().get("status") == "running"

    # PT user shouldn't see result
    r3 = requests.get(
        f"{BASE_URL}/api/takeoffs/cotes-jobs/{job_id}",
        headers=hdr(tok_pt), timeout=15,
    )
    # either 404 or running w/o result
    if r3.status_code == 200:
        assert r3.json().get("status") == "running"

    # Poll up to 120s
    deadline = time.time() + 130
    final = None
    while time.time() < deadline:
        p = requests.get(
            f"{BASE_URL}/api/takeoffs/cotes-jobs/{job_id}",
            headers=hdr(tok_fr), timeout=15,
        )
        assert p.status_code == 200, p.text[:200]
        j = p.json()
        if j.get("status") == "done":
            final = j
            break
        time.sleep(5)
    assert final is not None, "job did not complete in 120s"
    assert (final.get("result") or {}).get("summary")


def test_narratif_404_when_absent(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_NO_NARR}/cotes/narratif.pdf",
        headers=hdr(tok_fr), params={"page_index": 0}, timeout=30,
    )
    assert r.status_code == 404
