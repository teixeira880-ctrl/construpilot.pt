"""Iteration 141 review — Compare PDF, Inconsistencies PDF, Guided correction, Posts detection."""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

with open("/app/memory/houilles_pid.txt") as f:
    PLAN_ID = f.read().strip()

PRO = ("pro@construpilot.fr", "Pro2026!")
CLIENT = ("client@construpilot.fr", "Client2026!")


def _login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_token():
    return _login(PRO)


@pytest.fixture(scope="module")
def client_token():
    return _login(CLIENT)


# -------- 1) Comparison PDF (particulier) --------
@pytest.fixture(scope="module")
def comparison_id(client_token):
    h = {"Authorization": f"Bearer {client_token}"}
    r = requests.get(f"{API}/assistant/conversations", headers=h, timeout=30)
    assert r.status_code == 200, r.text
    convs = r.json()
    # Find one titled starting with "Compare les deux devis"
    target = None
    for c in convs if isinstance(convs, list) else convs.get("conversations", []):
        title = c.get("title", "") or ""
        if title.lower().startswith("compare les deux devis"):
            target = c
            break
    assert target, f"No 'Compare les deux devis' conversation found. Titles: {[c.get('title') for c in (convs if isinstance(convs,list) else convs.get('conversations',[]))][:10]}"
    cid = target.get("conversation_id") or target.get("id") or target.get("_id")
    r2 = requests.get(f"{API}/assistant/conversations/{cid}", headers=h, timeout=30)
    assert r2.status_code == 200, r2.text
    conv = r2.json()
    msgs = conv.get("messages", [])
    for m in msgs:
        for a in (m.get("actions") or []):
            if a.get("tool") == "compare_documents":
                res = a.get("result") or {}
                cmp_id = res.get("comparison_id")
                if cmp_id:
                    return cmp_id
    pytest.fail("comparison_id not found in conversation messages")


def test_comparison_pdf_ok_particulier(client_token, comparison_id):
    h = {"Authorization": f"Bearer {client_token}"}
    r = requests.get(f"{API}/assistant/comparisons/{comparison_id}/pdf", headers=h, timeout=60)
    assert r.status_code == 200, r.text[:400]
    assert "application/pdf" in r.headers.get("content-type", "")
    # Extract text
    from pypdf import PdfReader
    from io import BytesIO
    reader = PdfReader(BytesIO(r.content))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    assert "COMPARAISON DE DOCUMENTS" in text.upper() or "COMPARAISON" in text.upper(), text[:500]
    assert "Document informatif" in text or "informatif" in text.lower(), text[:500]


def test_comparison_pdf_forbidden_other_user(pro_token, comparison_id):
    h = {"Authorization": f"Bearer {pro_token}"}
    r = requests.get(f"{API}/assistant/comparisons/{comparison_id}/pdf", headers=h, timeout=30)
    assert r.status_code == 404, r.status_code


def test_comparison_pdf_unknown_id(client_token):
    h = {"Authorization": f"Bearer {client_token}"}
    r = requests.get(f"{API}/assistant/comparisons/does-not-exist-xyz/pdf", headers=h, timeout=30)
    assert r.status_code == 404


# -------- 2) Inconsistencies PDF --------
def test_inconsistencies_pdf_pro(pro_token):
    h = {"Authorization": f"Bearer {pro_token}"}
    r = requests.get(f"{API}/takeoffs/{PLAN_ID}/cotes/inconsistencies.pdf?page_index=0", headers=h, timeout=60)
    assert r.status_code == 200, r.text[:400]
    assert "application/pdf" in r.headers.get("content-type", "")
    from pypdf import PdfReader
    from io import BytesIO
    reader = PdfReader(BytesIO(r.content))
    assert len(reader.pages) == 1
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    up = text.upper()
    assert "INCOHÉRENCES DE COTATION" in up or "INCOHERENCES DE COTATION" in up, text[:500]
    assert "5.33" in text, text[:500]
    assert "-130" in text or "−130" in text, text[:500]
    assert "CH-H-01" in text, text[:500]


def test_inconsistencies_pdf_forbidden_particulier(client_token):
    h = {"Authorization": f"Bearer {client_token}"}
    r = requests.get(f"{API}/takeoffs/{PLAN_ID}/cotes/inconsistencies.pdf?page_index=0", headers=h, timeout=30)
    assert r.status_code in (403, 404), r.status_code


# -------- 3) Guided correction --------
def test_guided_correction_flow(pro_token):
    h = {"Authorization": f"Bearer {pro_token}", "Content-Type": "application/json"}
    # Create issue
    payload = {
        "page_index": 0,
        "target": "INT-H-006",
        "element": "Travée QA",
        "description": "Test QA correction guidée",
        "expected_value": "4.57",
    }
    r = requests.post(f"{API}/takeoffs/{PLAN_ID}/cotes/issues", headers=h, json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text[:400]
    issue = r.json()
    issue_id = issue.get("issue_id") or issue.get("id") or issue.get("_id")
    assert issue_id, issue

    # Reanalyze
    r2 = requests.post(f"{API}/takeoffs/{PLAN_ID}/cotes/issues/{issue_id}/reanalyze", headers=h, timeout=30)
    assert r2.status_code == 200, r2.text[:400]
    job_id = r2.json().get("job_id")
    assert job_id

    # Poll job
    deadline = time.time() + 240
    result = None
    while time.time() < deadline:
        rj = requests.get(f"{API}/takeoffs/cotes-jobs/{job_id}", headers=h, timeout=15)
        assert rj.status_code == 200
        data = rj.json()
        st = data.get("status") or data.get("state")
        if st in ("done", "success", "completed", "finished"):
            result = data.get("result") or data
            break
        if st in ("error", "failed"):
            pytest.fail(f"job failed: {data}")
        time.sleep(3)
    assert result, "job did not finish in 240s"

    assert isinstance(result.get("changed"), bool), result
    tb = result.get("target_before") or {}
    ta = result.get("target_after") or {}
    assert tb.get("kind") == "measurement", tb
    assert tb.get("id") == "INT-H-006", tb
    assert ta.get("kind") == "measurement", ta
    assert ta.get("id") == "INT-H-006", ta
    assert isinstance(result.get("version"), int), result

    # Versions listing
    rv = requests.get(f"{API}/takeoffs/{PLAN_ID}/cotes/versions?page_index=0", headers=h, timeout=30)
    assert rv.status_code == 200, rv.text[:400]
    versions = rv.json()
    vlist = versions if isinstance(versions, list) else versions.get("versions", [])
    assert vlist, "versions empty"
    last = vlist[-1] if vlist[-1].get("version", 0) >= vlist[0].get("version", 0) else vlist[0]
    # Try last by max version number
    last = max(vlist, key=lambda v: v.get("version", 0))
    assert last.get("trigger") == "guided_correction", last
    assert last.get("target_before"), last
    assert last.get("target_after"), last
    assert "changed" in last, last

    # Check issue has resolution via versions endpoint (returns {versions, issues})
    ri = requests.get(f"{API}/takeoffs/{PLAN_ID}/cotes/versions?page_index=0", headers=h, timeout=30)
    assert ri.status_code == 200
    issues = ri.json().get("issues", [])
    match = [i for i in issues if i.get("issue_id") == issue_id]
    assert match, f"issue {issue_id} not found. issues={[i.get('issue_id') for i in issues][:10]}"
    it = match[0]
    assert it.get("resolution"), it
    expected_status = "resolved" if result["changed"] else "open"
    assert it.get("status") == expected_status, it


def test_guided_correction_unknown_issue(pro_token):
    h = {"Authorization": f"Bearer {pro_token}"}
    r = requests.post(f"{API}/takeoffs/{PLAN_ID}/cotes/issues/unknown-xyz/reanalyze", headers=h, timeout=15)
    assert r.status_code == 404, r.status_code


# -------- 4) Posts detection --------
def test_posts_detected(pro_token):
    h = {"Authorization": f"Bearer {pro_token}"}
    r = requests.get(f"{API}/takeoffs/{PLAN_ID}/cotes?page_index=0", headers=h, timeout=60)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    interior = data.get("report", {}).get("interior", {}) or data.get("interior", {})
    walls = interior.get("walls", [])
    posts = [w for w in walls if w.get("is_post")]
    assert len(posts) >= 10, f"expected >=10 posts, got {len(posts)}"
    for p in posts[:3]:
        assert (p.get("post_id") or "").startswith("P"), p
        t = p.get("thickness_m")
        assert t is not None and abs(t - 0.13) < 0.02, p
        assert p.get("ouvrage_class") == "Poteau béton", p
        assert p.get("source") == "post_rectangle", p

    # closure_equations no span < 0.05
    eqs = interior.get("closure_equations") or data.get("report", {}).get("closure_equations") or []
    for row in eqs:
        terms = row.get("terms") or []
        for t in terms:
            span = t.get("span") if isinstance(t, dict) else None
            if span is not None:
                assert span >= 0.05, f"span<0.05 in {row}"
