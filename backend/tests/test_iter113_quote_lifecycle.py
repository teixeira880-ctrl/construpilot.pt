"""Backend tests for iter113 — quote lifecycle, deletions, import 2-step, campaigns, signature auto."""
import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASS = "Pro2026!"
ADMIN_EMAIL = "deboradsmelo@gmail.com"
ADMIN_PASS = "Miguel1156."


def _login(session: requests.Session, email: str, password: str) -> str:
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    tok = r.json().get("token")
    session.headers.update({"Authorization": f"Bearer {tok}"})
    return tok


@pytest.fixture(scope="module")
def pro():
    s = requests.Session()
    _login(s, PRO_EMAIL, PRO_PASS)
    return s


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    _login(s, ADMIN_EMAIL, ADMIN_PASS)
    return s


# ---------- helpers ----------
def _create_quote(session: requests.Session, number="TEST-Q1") -> str:
    body = {
        "doc_type": "quote",
        "number": number,
        "title": "TEST devis lifecycle",
        "client": {"company": "TEST Client SA", "email": "test-lifecycle@example.com"},
        "lines": [{"designation": "Ligne 1", "qty": 2, "pu": 100, "tva": 20}],
    }
    r = session.post(f"{BASE_URL}/api/documents", json=body, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["doc_id"]


def _delete_doc(session, doc_id):
    session.delete(f"{BASE_URL}/api/documents/{doc_id}", timeout=15)


def _delete_client(session, client_id):
    session.delete(f"{BASE_URL}/api/clients/{client_id}", timeout=15)


# ---------- 1) Quote lifecycle: status + invoice gate ----------
class TestQuoteLifecycle:
    def test_set_status_invalid_returns_400(self, pro):
        doc_id = _create_quote(pro, number="TEST-Q-STATUS-INV")
        try:
            r = pro.patch(f"{BASE_URL}/api/documents/{doc_id}/status", json={"status": "notreal"})
            assert r.status_code == 400
        finally:
            _delete_doc(pro, doc_id)

    def test_to_invoice_blocked_when_not_signed(self, pro):
        doc_id = _create_quote(pro, number="TEST-Q-INV-GATE")
        try:
            # status is 'draft' by default → invoicing must fail
            r = pro.post(f"{BASE_URL}/api/documents/{doc_id}/to-invoice", json={"mode": "total", "pct": 100})
            assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text}"
        finally:
            _delete_doc(pro, doc_id)

    def test_full_lifecycle_sign_then_invoice(self, pro):
        doc_id = _create_quote(pro, number="TEST-Q-FULL")
        inv_id = None
        try:
            for st in ("sent", "refused", "signed"):
                r = pro.patch(f"{BASE_URL}/api/documents/{doc_id}/status", json={"status": st})
                assert r.status_code == 200, r.text
                assert r.json().get("status") == st
            # signed=True flag verified via GET
            g = pro.get(f"{BASE_URL}/api/documents/{doc_id}").json()
            assert g["status"] == "signed"
            assert g.get("signed") is True
            # Now to-invoice succeeds
            r = pro.post(f"{BASE_URL}/api/documents/{doc_id}/to-invoice",
                         json={"mode": "total", "pct": 100})
            assert r.status_code == 200, r.text
            inv = r.json()
            inv_id = inv.get("doc_id")
            assert inv.get("doc_type") == "invoice"
            assert inv.get("parent_doc_id") == doc_id
        finally:
            if inv_id:
                _delete_doc(pro, inv_id)
            _delete_doc(pro, doc_id)

    def test_delete_document(self, pro):
        doc_id = _create_quote(pro, number="TEST-Q-DEL")
        r = pro.delete(f"{BASE_URL}/api/documents/{doc_id}")
        assert r.status_code == 200
        # verify gone
        g = pro.get(f"{BASE_URL}/api/documents/{doc_id}")
        assert g.status_code == 404


# ---------- 2) Client deletion guard ----------
class TestClientGuard:
    def test_delete_client_without_docs(self, pro):
        r = pro.post(f"{BASE_URL}/api/clients", json={
            "company": "TEST Cli Empty", "email": "test-empty@example.com"})
        assert r.status_code == 200, r.text
        cid = r.json()["client_id"]
        d = pro.delete(f"{BASE_URL}/api/clients/{cid}")
        assert d.status_code == 200

    def test_delete_client_with_docs_blocked(self, pro):
        r = pro.post(f"{BASE_URL}/api/clients", json={
            "company": "TEST Cli Linked", "email": "test-linked@example.com"})
        assert r.status_code == 200
        cid = r.json()["client_id"]
        # create doc linked to this client
        rq = pro.post(f"{BASE_URL}/api/documents", json={
            "doc_type": "quote", "number": "TEST-LNK", "title": "linked",
            "client_id": cid, "client": {"company": "TEST Cli Linked"},
            "lines": [{"designation": "x", "qty": 1, "pu": 10, "tva": 20}],
        })
        assert rq.status_code == 200
        doc_id = rq.json()["doc_id"]
        try:
            d = pro.delete(f"{BASE_URL}/api/clients/{cid}")
            assert d.status_code == 400
            assert "document" in d.text.lower() or "lié" in d.text.lower()
        finally:
            _delete_doc(pro, doc_id)
            _delete_client(pro, cid)


# ---------- 3) Import PDF 2 steps: preview -> confirm ----------
def _make_pdf_bytes(number="PREV-42", company="Apercu Test", email="apercu-test@ex.fr"):
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 800, f"DEVIS N° {number}")
    c.drawString(100, 780, f"Client: {company}")
    c.drawString(100, 760, f"Email: {email}")
    c.drawString(100, 720, "Designation                       Qty   PU   Total")
    c.drawString(100, 700, "Prestation A                       2     150  300")
    c.drawString(100, 680, "Prestation B                       1     100  100")
    c.drawString(100, 640, "Total TTC: 480 EUR")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.read()


class TestImportPdfTwoStep:
    def test_preview_then_confirm(self, pro):
        pdf_bytes = _make_pdf_bytes()
        files = {"files": ("devis_prev42.pdf", pdf_bytes, "application/pdf")}
        data = {"doc_type": "quote", "status": "draft"}
        r = pro.post(f"{BASE_URL}/api/documents/import-pdf/preview", files=files, data=data, timeout=60)
        assert r.status_code == 200, r.text
        pv = r.json()
        items = pv.get("items") or []
        assert items, f"no items in preview {pv}"
        # Ensure a doc was NOT created yet: no doc_id at top-level
        item = items[0]
        assert "doc_id" not in item or not item.get("doc_id")
        # modify designation of first line and qty
        if item.get("lines"):
            item["lines"][0]["designation"] = "MODIF designation TEST"
            item["lines"][0]["qty"] = 9
        item["company"] = "Apercu Test MODIF"
        # confirm
        r2 = pro.post(f"{BASE_URL}/api/documents/import-pdf/confirm",
                      json={"items": items, "doc_type": "quote", "status": "draft"}, timeout=60)
        assert r2.status_code == 200, r2.text
        res = r2.json()
        assert res.get("imported", 0) >= 1, res
        created = res.get("results") or []
        assert len(created) >= 1
        doc_id = (created[0] or {}).get("doc_id")
        assert doc_id
        try:
            g = pro.get(f"{BASE_URL}/api/documents/{doc_id}").json()
            # Verify edit is reflected
            lines = g.get("lines") or []
            assert any((ln.get("designation") or "").startswith("MODIF") for ln in lines), lines
        finally:
            _delete_doc(pro, doc_id)


# ---------- 4) Admin campaigns ----------
class TestAdminCampaigns:
    def test_get_campaigns_ok(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/campaigns", timeout=15)
        assert r.status_code == 200, r.text
        assert "campaigns" in r.json()

    def test_bulk_email_single_recipient_records_campaign(self, admin):
        subject = f"TEST subject {int(time.time())}"
        r = admin.post(f"{BASE_URL}/api/admin/bulk-email", json={
            "recipients": [PRO_EMAIL],
            "subject": subject,
            "message": "Message de test automatisé (safe: 1 destinataire)."
        }, timeout=30)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("total") == 1
        # verify listed
        cs = admin.get(f"{BASE_URL}/api/admin/campaigns").json().get("campaigns") or []
        assert any(c.get("subject") == subject for c in cs), "campaign not listed"


# ---------- 5) Send + public sign → auto signed ----------
class TestSignatureAutoSigned:
    def test_send_then_public_sign_marks_signed(self, pro):
        doc_id = _create_quote(pro, number="TEST-Q-SIGN-AUTO")
        try:
            r = pro.post(f"{BASE_URL}/api/documents/{doc_id}/send",
                         json={"client_email": "test-sign@example.com",
                               "subject": "Test sign", "message": "hello"})
            assert r.status_code == 200, r.text
            log_id = r.json().get("log_id")
            assert log_id
            # Fetch token via direct mongo (localhost)
            from pymongo import MongoClient
            mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
            db = mc[os.environ.get("DB_NAME", "test_database")]
            row = db.quote_sends.find_one({"log_id": log_id})
            assert row and row.get("signature_token"), "no signature_token"
            token = row["signature_token"]
            sig = "data:image/png;base64," + ("A" * 200)
            sr = requests.post(f"{BASE_URL}/api/quotes/public/sign/{token}",
                               json={"signer_name": "Test Signer", "signature_b64": sig}, timeout=20)
            assert sr.status_code == 200, sr.text
            g = pro.get(f"{BASE_URL}/api/documents/{doc_id}").json()
            assert g.get("status") == "signed", g
        finally:
            _delete_doc(pro, doc_id)
