"""
Iteration 140 backend tests:
 - /api/takeoffs/{plan}/cotes/issues (report + resolve)
 - /api/takeoffs/{plan}/cotes/versions
 - Houilles peripheral chains + inconsistencies + wall ouvrage_class + legend
 - PDF report contains new sections
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
PRO = ("pro@construpilot.fr", "Pro2026!")
CLIENT = ("client@construpilot.fr", "Client2026!")

with open("/app/memory/houilles_pid.txt") as f:
    PLAN_ID = f.read().strip()


def _login(creds):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_headers():
    return {"Authorization": f"Bearer {_login(PRO)}"}


@pytest.fixture(scope="module")
def client_headers():
    return {"Authorization": f"Bearer {_login(CLIENT)}"}


# ---------- Issues + versions ----------

def test_report_issue_and_version(pro_headers):
    payload = {
        "page_index": 0,
        "target": "INT-H-003",
        "element": "Travée M18 → M19",
        "description": "Test QA : la mesure devrait être 4,10 nu/nu",
        "expected_value": "4.10",
    }
    r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes/issues", json=payload, headers=pro_headers, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "issue_id" in data
    assert data.get("status") == "open"
    issue_id = data["issue_id"]

    # versions listing
    rv = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes/versions?page_index=0", headers=pro_headers, timeout=30)
    assert rv.status_code == 200, rv.text
    vdata = rv.json()
    assert isinstance(vdata.get("versions"), list) and len(vdata["versions"]) >= 1
    assert vdata["versions"][-1].get("trigger") == "issue_reported"
    assert vdata["versions"][-1].get("open_issues", 0) >= 1
    ids = [i.get("issue_id") for i in vdata.get("issues", [])]
    assert issue_id in ids

    # cotes report should mark under_review
    rc = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes?page_index=0", headers=pro_headers, timeout=30)
    assert rc.status_code == 200
    cdata = rc.json()
    assert cdata.get("under_review") is True
    assert cdata.get("open_issues", 0) >= 1

    # resolve
    rr = requests.patch(
        f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes/issues/{issue_id}",
        json={"resolution": "corrigé QA"},
        headers=pro_headers,
        timeout=30,
    )
    assert rr.status_code == 200, rr.text
    assert rr.json().get("status") == "resolved"


def test_report_issue_validation(pro_headers):
    payload = {"page_index": 0, "target": "INT-H-003", "element": "x", "description": "abc"}
    r = requests.post(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes/issues", json=payload, headers=pro_headers, timeout=20)
    assert r.status_code == 422


def test_unknown_plan(pro_headers):
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/plan_zzz_unknown/cotes/issues",
        json={"page_index": 0, "target": "X", "element": "El", "description": "descr long enough"},
        headers=pro_headers,
        timeout=20,
    )
    assert r.status_code == 404, r.text


def test_client_forbidden(client_headers):
    r = requests.post(
        f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes/issues",
        json={"page_index": 0, "target": "X", "element": "El", "description": "descr long enough"},
        headers=client_headers,
        timeout=20,
    )
    assert r.status_code in (403, 404), r.text


# ---------- Houilles peripheral + interior ----------

def test_houilles_report(pro_headers):
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes?page_index=0", headers=pro_headers, timeout=30)
    assert r.status_code == 200
    d = r.json()
    interior = d.get("interior") or {}
    peri = interior.get("peripheral") or {}
    summary = peri.get("summary") or {}
    assert summary.get("inconsistencies") == 3, summary
    incs = peri.get("inconsistencies") or []
    deltas = sorted([int(round(i.get("delta_mm"))) for i in incs])
    assert deltas == sorted([-130, 40, -30]), deltas
    for i in incs:
        assert i.get("a_item_index") is not None
        assert i.get("b_item_index") is not None
    sides = {c.get("side") for c in peri.get("chains", [])}
    assert {"haut", "bas", "gauche", "droite"}.issubset(sides), sides

    val = interior.get("validation") or {}
    assert val.get("complete") is False
    assert "incompl" in (val.get("message") or "").lower()

    walls = interior.get("walls") or []
    classes = {w.get("ouvrage_class") for w in walls}
    assert classes & {"Poutre", "Semelle filante", "Poteau béton"}, classes


def test_houilles_legend(pro_headers):
    """Regression: interior.legend.document_kind should be 'plan de fondations'"""
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes?page_index=0", headers=pro_headers, timeout=30)
    d = r.json()
    interior = d.get("interior") or {}
    legend = interior.get("legend")
    assert legend is not None, "interior.legend est None (extract_legend non alimenté pour ce plan)"
    assert legend.get("document_kind") == "plan de fondations", legend


def test_houilles_pdf(pro_headers):
    r = requests.get(f"{BASE_URL}/api/takeoffs/{PLAN_ID}/cotes/report.pdf?page_index=0", headers=pro_headers, timeout=60)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    try:
        from pypdf import PdfReader
    except Exception:
        from PyPDF2 import PdfReader  # type: ignore
    reader = PdfReader(io.BytesIO(r.content))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    tnorm = text.lower()
    assert "chaînes de cotes périphériques" in tnorm or "chaines de cotes" in tnorm, text[:2000]
    assert ("incohérence" in tnorm) or ("incoherence" in tnorm), text[:2000]
