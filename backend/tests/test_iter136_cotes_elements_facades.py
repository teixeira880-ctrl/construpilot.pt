"""
Iter 136 — Backend tests for cotes control :
- Vector PDF upload + elements + anchors + auto_spans (synth_plan_1_50)
- Recompute persistence
- reextract (201) and 409 on plan without source
- narratif-all.pdf FR
- Regression Houilles: facades diag + narratif-all.pdf
"""
import os
import time
import io
import pytest
import requests

def _base():
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
    assert u, "REACT_APP_BACKEND_URL missing"
    return u.rstrip("/")

BASE_URL = _base()

FR_EMAIL = "pro@construpilot.fr"
FR_PASS = "Pro2026!"

PLAN_HOUILLES = "plan_ee9385c91ee5"
FIXTURE = "/app/backend/tests/fixtures/synth_plan_1_50.pdf"


def _pdf_text(content: bytes) -> str:
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        out = "\n".join(p.get_text() for p in doc)
        doc.close()
        return out
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


@pytest.fixture(scope="module")
def tok_fr():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": FR_EMAIL, "password": FR_PASS}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()["token"]


def hdr(tok):
    return {"Authorization": f"Bearer {tok}"}


# Shared state
STATE = {"plan_id": None}


# ---------- Upload synthetic plan ----------
def test_a_upload_synth_plan(tok_fr):
    assert os.path.exists(FIXTURE), "fixture missing"
    with open(FIXTURE, "rb") as f:
        r = requests.post(
            f"{BASE_URL}/api/takeoffs/upload",
            headers=hdr(tok_fr),
            files={"file": ("synth_plan_1_50.pdf", f, "application/pdf")},
            timeout=180,
        )
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    plan_id = data.get("plan_id") or data.get("id")
    assert plan_id
    STATE["plan_id"] = plan_id
    calibs = data.get("calibrations") or {}
    c0 = calibs.get("0") or calibs.get(0) or {}
    assert c0.get("method") == "pdf_vector", f"method={c0.get('method')} calibs={calibs}"
    eff = c0.get("effective_scale_denominator") or c0.get("scale_denominator")
    assert eff and 45 < float(eff) < 55, f"effective_scale_denominator={eff}"


# ---------- Run check (background) ----------
def test_b_run_check_and_poll(tok_fr):
    plan_id = STATE["plan_id"]
    assert plan_id
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/{plan_id}/cotes/check",
        headers=hdr(tok_fr), params={"background": 1},
        json={"page_index": 0}, timeout=30,
    )
    assert r.status_code == 200, r.text[:200]
    job_id = r.json().get("job_id")
    assert job_id
    deadline = time.time() + 150
    final = None
    while time.time() < deadline:
        p = requests.get(f"{BASE_URL}/api/takeoffs/cotes-jobs/{job_id}",
                         headers=hdr(tok_fr), timeout=15)
        assert p.status_code == 200
        j = p.json()
        if j.get("status") == "done":
            final = j
            break
        time.sleep(5)
    assert final is not None, "job did not finish in 150s"
    res = final.get("result") or {}
    summ = res.get("summary") or {}
    STATE["summary"] = summ
    STATE["result"] = res
    assert summ.get("total") == 3, f"total={summ.get('total')} summary={summ}"
    assert summ.get("verdict") == "ko", f"verdict={summ.get('verdict')}"
    assert summ.get("elements_total") == 2, f"elements_total={summ.get('elements_total')}"
    assert summ.get("elements_ko") == 1, f"elements_ko={summ.get('elements_ko')}"
    assert summ.get("anchors_ko") == 1, f"anchors_ko={summ.get('anchors_ko')}"
    assert (summ.get("auto_spans_total") or 0) >= 6, f"auto_spans_total={summ.get('auto_spans_total')}"
    concl = (summ.get("conclusion") or "").lower()
    assert "50x30" in concl, f"conclusion should mention 50x30: {concl}"
    assert "probablement erronée" in concl or "probablement erronee" in concl, f"conclusion missing 'probablement erronée': {concl}"


def test_c_elements_details(tok_fr):
    res = STATE.get("result") or {}
    elements = res.get("elements") or []
    assert len(elements) == 2, f"elements len={len(elements)}"
    ko = [e for e in elements if (e.get("status") == "ko") or (e.get("label") == "50x30")]
    assert ko, f"no ko element: {elements}"
    e = ko[0]
    assert "50x30" in (e.get("label") or "")
    dmm = e.get("delta_mm")
    assert dmm is not None and -60 <= dmm <= -40, f"delta_mm={dmm}"
    mw = e.get("measured_w_m")
    assert mw is not None and 0.40 <= mw <= 0.50, f"measured_w_m={mw}"


def test_d_anchors_details(tok_fr):
    res = STATE.get("result") or {}
    items = res.get("items") or []
    # Item #2 = 6.00, measured 5.95, anchor ko
    assert len(items) >= 3
    for i, it in enumerate(items[:3]):
        anchor_status = it.get("anchor_status")
        anc_mm = it.get("anchor_mm") or []
        indic = it.get("indicated_m") or it.get("indicated")
        meas = it.get("measured_m") or it.get("measured_exact_m")
        status = it.get("status")
        print(f"item#{i+1}: indicated={indic} measured={meas} status={status} anchor_status={anchor_status} anchor_mm={anc_mm}")
    it2 = items[1]
    assert it2.get("status") == "ko"
    assert (it2.get("anchor_status") or "").lower() == "ko"
    anc = it2.get("anchor_mm") or []
    assert anc and abs(anc[0]) >= 30, f"anchor_mm={anc}"
    # #1 and #3 ok
    for idx in (0, 2):
        assert items[idx].get("status") == "ok", f"item#{idx+1} status={items[idx].get('status')}"
        # anchor_status may be ok/None
        ast = items[idx].get("anchor_status")
        assert ast in (None, "ok"), f"item#{idx+1} anchor_status={ast}"


def test_e_auto_spans_shape(tok_fr):
    res = STATE.get("result") or {}
    auto_spans = res.get("auto_spans") or []
    assert len(auto_spans) >= 6, f"auto_spans len={len(auto_spans)}"
    for s in auto_spans[:3]:
        for k in ("measured_m", "x1", "y1", "x2", "y2", "orientation"):
            assert k in s, f"missing key {k} in auto_span: {s}"


# ---------- Recompute ----------
def test_f_recompute_persistence(tok_fr):
    plan_id = STATE["plan_id"]
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/{plan_id}/cotes/recompute",
        headers=hdr(tok_fr), json={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    rep = r.json()
    assert len(rep.get("elements") or []) == 2
    assert len(rep.get("auto_spans") or []) >= 6
    summ = rep.get("summary") or {}
    assert summ.get("anchors_ko") == 1


# ---------- Reextract ----------
def test_g_reextract_ok(tok_fr):
    plan_id = STATE["plan_id"]
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/{plan_id}/cotes/reextract",
        headers=hdr(tok_fr), timeout=60,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    data = r.json()
    pages = data.get("pages") or []
    assert pages
    p0 = pages[0]
    assert p0.get("dimensions") == 3, f"dimensions={p0.get('dimensions')}"
    assert p0.get("elements") == 2, f"elements={p0.get('elements')}"
    assert (p0.get("auto_spans") or 0) >= 6, f"auto_spans={p0.get('auto_spans')}"


def test_h_reextract_409_on_houilles(tok_fr):
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/{PLAN_HOUILLES}/cotes/reextract",
        headers=hdr(tok_fr), timeout=30,
    )
    assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text[:200]}"


# ---------- PDFs ----------
def test_i_report_pdf_synth(tok_fr):
    plan_id = STATE["plan_id"]
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{plan_id}/cotes/report.pdf",
        headers=hdr(tok_fr), params={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200
    txt = _pdf_text(r.content)
    assert "Éléments dessinés" in txt or "Elements dessines" in txt, f"missing 'Éléments dessinés'"
    assert "probablement erronées" in txt or "probablement erronees" in txt.lower(), "missing 'probablement erronées'"
    assert "Mesures automatiques" in txt, "missing 'Mesures automatiques'"


def test_j_narratif_all_404_synth(tok_fr):
    plan_id = STATE["plan_id"]
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{plan_id}/cotes/narratif-all.pdf",
        headers=hdr(tok_fr), timeout=30,
    )
    assert r.status_code == 404, f"expected 404, got {r.status_code}"


# ---------- Houilles regression ----------
def test_k_houilles_facades_and_verdict(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_HOUILLES}/cotes",
        headers=hdr(tok_fr), params={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200
    rep = r.json()
    summ = rep.get("summary") or {}
    assert summ.get("verdict") == "ko", f"verdict={summ.get('verdict')}"
    assert summ.get("facades_total") == 2, f"facades_total={summ.get('facades_total')}"
    assert summ.get("facades_ko") == 2, f"facades_ko={summ.get('facades_ko')}"
    facades = rep.get("facades") or []
    assert len(facades) == 2
    for f in facades:
        diag = f.get("diag") or {}
        for k in ("d1_m", "d2_m", "diff_cm", "angle_deg"):
            assert k in diag, f"facade missing diag.{k}: {diag}"
    assert summ.get("ok") == 51, f"ok={summ.get('ok')}"
    concl = (summ.get("conclusion") or "").lower()
    assert "diagonales" in concl, f"conclusion missing 'diagonales': {concl}"


def test_l_houilles_narratif_all(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_HOUILLES}/cotes/narratif-all.pdf",
        headers=hdr(tok_fr), timeout=90,
    )
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    assert "application/pdf" in r.headers.get("content-type", "")
    n = _pdf_pages(r.content)
    assert n >= 5, f"narratif-all pages={n}"


def test_m_houilles_narratif_page(tok_fr):
    r = requests.get(
        f"{BASE_URL}/api/takeoffs/{PLAN_HOUILLES}/cotes/narratif.pdf",
        headers=hdr(tok_fr), params={"page_index": 0}, timeout=60,
    )
    assert r.status_code == 200
