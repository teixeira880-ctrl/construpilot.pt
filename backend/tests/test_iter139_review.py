"""Iteration 139 review: assistant documents, public shared estimation, interior walls / cotes"""
import os
import io
import time
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = BASE + "/api"

PRO = {"email": "pro@construpilot.fr", "password": "Pro2026!"}
CLIENT = {"email": "client@construpilot.fr", "password": "Client2026!"}

DEVIS_A = "/tmp/cmp/devis_A.pdf"
SYNTH_PDF = "/app/backend/tests/fixtures/synth_walls_1_50.pdf"

with open("/tmp/synthpid") as f:
    PLAN_ID = f.read().strip()

SHARED_TOKEN = "tok_test_share_0001"


def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="module")
def pro_token():
    return _login(PRO)


@pytest.fixture(scope="module")
def client_token():
    return _login(CLIENT)


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


# ============ Assistant documents ============
class TestAssistantDocuments:
    doc_id = None

    def test_upload_pdf(self, client_token):
        with open(DEVIS_A, "rb") as f:
            r = requests.post(
                f"{API}/assistant/documents",
                headers=h(client_token),
                files={"file": ("devis_A.pdf", f, "application/pdf")},
                timeout=60,
            )
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("mime") == "application/pdf"
        assert j.get("has_text") is True
        assert j.get("kind") == "quote"
        assert j.get("filename")
        assert j.get("pages", 0) >= 1
        assert j.get("doc_id")
        TestAssistantDocuments.doc_id = j["doc_id"]

    def test_list_documents(self, client_token):
        r = requests.get(f"{API}/assistant/documents", headers=h(client_token), timeout=30)
        assert r.status_code == 200
        arr = r.json()
        assert isinstance(arr, list)
        found = [d for d in arr if d.get("doc_id") == TestAssistantDocuments.doc_id]
        assert found, "uploaded doc missing from list"
        d = found[0]
        assert "data_b64" not in d
        assert "text" not in d

    def test_upload_txt_rejected(self, client_token):
        r = requests.post(
            f"{API}/assistant/documents",
            headers=h(client_token),
            files={"file": ("hello.txt", io.BytesIO(b"hello world"), "text/plain")},
            timeout=30,
        )
        assert r.status_code == 415, f"expected 415 got {r.status_code}: {r.text}"

    def test_pro_cannot_delete_client_doc(self, pro_token):
        r = requests.delete(
            f"{API}/assistant/documents/{TestAssistantDocuments.doc_id}",
            headers=h(pro_token),
            timeout=30,
        )
        assert r.status_code == 404

    def test_stream_forbidden_with_unknown_docids(self, client_token):
        # need a conversation_id
        rc = requests.post(f"{API}/assistant/conversations", headers=h(client_token), json={"title": "t"}, timeout=30)
        conv_id = None
        if rc.status_code == 200:
            conv_id = (rc.json() or {}).get("id") or (rc.json() or {}).get("conversation_id")
        if not conv_id:
            rl = requests.get(f"{API}/assistant/conversations", headers=h(client_token), timeout=30)
            arr = rl.json() if rl.status_code == 200 else []
            if arr:
                conv_id = (arr[0] or {}).get("id") or (arr[0] or {}).get("conversation_id")
        assert conv_id, "no conversation to use"
        r = requests.post(
            f"{API}/assistant/message/stream",
            headers=h(client_token),
            json={"conversation_id": conv_id, "text": "test", "doc_ids": ["doc_inexistant"]},
            timeout=30,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"

    def test_delete_nonexistent(self, client_token):
        r = requests.delete(f"{API}/assistant/documents/doc_notthere", headers=h(client_token), timeout=30)
        assert r.status_code == 404

    def test_delete_own_doc(self, client_token):
        r = requests.delete(
            f"{API}/assistant/documents/{TestAssistantDocuments.doc_id}",
            headers=h(client_token),
            timeout=30,
        )
        assert r.status_code == 200
        assert r.json().get("deleted") == 1


# ============ Public shared estimation ============
class TestPublicSharedEstimate:
    def test_public_get(self):
        r = requests.get(f"{API}/public/estimations/{SHARED_TOKEN}", timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ref")
        assert j.get("created_at")
        est = j.get("estimate") or {}
        assert est.get("low_estimate", 0) < est.get("high_estimate", 0)
        assert est.get("mandatory_notice")
        assert est.get("project") == "Rénovation salle de bain 6 m²"

    def test_public_pdf(self):
        r = requests.get(f"{API}/public/estimations/{SHARED_TOKEN}/pdf", timeout=30)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content.startswith(b"%PDF")

    def test_public_pdf_pt(self):
        r = requests.get(f"{API}/public/estimations/{SHARED_TOKEN}/pdf?lang=pt", timeout=30)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")

    def test_unknown_token(self):
        r = requests.get(f"{API}/public/estimations/tok_definitely_not_a_thing", timeout=30)
        assert r.status_code == 404

    def test_estimate_pdf_as_owner(self, client_token):
        r = requests.get(
            f"{API}/assistant/estimates/est_test000001/pdf",
            headers=h(client_token),
            timeout=30,
        )
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")

    def test_estimate_pdf_as_pro_forbidden(self, pro_token):
        r = requests.get(
            f"{API}/assistant/estimates/est_test000001/pdf",
            headers=h(pro_token),
            timeout=30,
        )
        assert r.status_code == 404


# ============ Interior walls / cotes ============
class TestInterior:
    def test_cotes_interior_report(self, pro_token):
        r = requests.get(
            f"{API}/takeoffs/{PLAN_ID}/cotes?page_index=0",
            headers=h(pro_token),
            timeout=60,
        )
        assert r.status_code == 200, r.text
        j = r.json()
        interior = (j.get("report") or {}).get("interior") or j.get("interior")
        assert interior, f"no interior report: keys={list(j.keys())}"
        walls = interior.get("walls") or []
        assert len(walls) == 7, f"expected 7 walls got {len(walls)}"
        for w in walls:
            assert abs(w.get("thickness_m", 0) - 0.20) < 1e-6
            assert w.get("face_1") != w.get("face_2")
            assert w.get("source") == "explicit_dimension"

        ims = interior.get("interior_measurements") or []
        assert len(ims) == 12
        allowed = {3.0, 3.6, 4.0, 4.4}
        for m in ims:
            assert m.get("status") == "confirmed"
            assert m.get("reference_type") == "inside_face_to_inside_face"
            assert m.get("geometric_dimension_m") in allowed
            assert m.get("item_index") is not None

        eqs = interior.get("closure_equations") or []
        assert len(eqs) == 5
        for e in eqs:
            assert e.get("status") == "closed"
            assert e.get("written_exterior_m") in (12.0, 8.0)

        assert (interior.get("validation") or {}).get("complete") is True
        assert set(interior.get("sections_ignored") or []) >= {"50x30", "60x30"}

    def test_interior_overlay_png(self, pro_token):
        r = requests.get(
            f"{API}/takeoffs/{PLAN_ID}/cotes/interior-overlay.png?page_index=0&highlight=INT-H-003",
            headers=h(pro_token),
            timeout=60,
        )
        assert r.status_code == 200
        assert "image/png" in r.headers.get("content-type", "")
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"

    def test_report_pdf_contains_interior(self, pro_token):
        r = requests.get(
            f"{API}/takeoffs/{PLAN_ID}/cotes/report.pdf?page_index=0",
            headers=h(pro_token),
            timeout=60,
        )
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        # Decompress PDF streams to find text markers
        from pypdf import PdfReader
        import io as _io
        rdr = PdfReader(_io.BytesIO(r.content))
        text = "\n".join((p.extract_text() or "") for p in rdr.pages)
        assert "Dimensions int" in text, "'Dimensions intérieures' not found"
        assert "INT-H-001" in text, "'INT-H-001' not found"

    def test_studies_verified(self, pro_token):
        r = requests.get(
            f"{API}/takeoffs/{PLAN_ID}/studies?page_index=0",
            headers=h(pro_token),
            timeout=60,
        )
        assert r.status_code == 200
        study = (r.json().get("study") or r.json())
        assert study.get("verified") is True
        assert ((study.get("interior") or {}).get("complete")) is True


# ============ Import flow (upload + cotes check job) ============
class TestImportFlow:
    new_plan_id = None
    job_id = None

    def test_upload_plan(self, pro_token):
        with open(SYNTH_PDF, "rb") as f:
            r = requests.post(
                f"{API}/takeoffs/upload",
                headers=h(pro_token),
                files={"file": ("synth_walls_1_50.pdf", f, "application/pdf")},
                timeout=90,
            )
        assert r.status_code == 200, r.text
        j = r.json()
        pid = j.get("plan_id") or j.get("id") or (j.get("plan") or {}).get("id")
        assert pid, f"no plan id in response: {j}"
        TestImportFlow.new_plan_id = pid

    def test_start_cotes_check_and_poll(self, pro_token):
        pid = TestImportFlow.new_plan_id
        assert pid
        r = requests.post(
            f"{API}/takeoffs/{pid}/cotes/check?background=1",
            headers=h(pro_token),
            json={"page_index": 0},
            timeout=30,
        )
        assert r.status_code in (200, 202), r.text
        j = r.json()
        job_id = j.get("job_id") or j.get("id")
        assert job_id
        TestImportFlow.job_id = job_id

        deadline = time.time() + 150
        status = None
        while time.time() < deadline:
            rj = requests.get(f"{API}/takeoffs/cotes-jobs/{job_id}", headers=h(pro_token), timeout=30)
            assert rj.status_code == 200
            jj = rj.json()
            status = jj.get("status") or jj.get("state")
            if status in ("done", "completed", "success", "finished"):
                break
            if status in ("error", "failed"):
                pytest.fail(f"job failed: {jj}")
            time.sleep(3)
        assert status in ("done", "completed", "success", "finished"), f"job did not finish: {status}"

    def test_new_plan_interior_complete(self, pro_token):
        pid = TestImportFlow.new_plan_id
        r = requests.get(
            f"{API}/takeoffs/{pid}/cotes?page_index=0",
            headers=h(pro_token),
            timeout=60,
        )
        assert r.status_code == 200
        j = r.json()
        interior = (j.get("report") or {}).get("interior") or j.get("interior")
        assert interior
        assert (interior.get("validation") or {}).get("complete") is True

    def test_cleanup_delete(self, pro_token):
        pid = TestImportFlow.new_plan_id
        if not pid:
            return
        r = requests.delete(f"{API}/takeoffs/{pid}", headers=h(pro_token), timeout=30)
        # Route may not exist – don't fail
        assert r.status_code in (200, 204, 404, 405)
