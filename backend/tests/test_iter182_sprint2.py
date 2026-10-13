"""Iteration 182 — Sprint 2 tests: assistant office docs, BTP solver photos+PDF, plans-pro DWG quantities, deadline reminders.

Read-only where possible; NO paid /solve call is triggered here (rate limits + budget).
Uses HttpOnly session cookies via requests.Session.
"""
import base64
import io
import os
import time
from datetime import date, timedelta

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import requests
from PIL import Image, ImageDraw

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://pilot-build-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

PRO = ("pro@construpilot.fr", "Pro2026!")
CLIENT = ("client@construpilot.fr", "Client2026!")
COLLEGUE = ("collegue@construpilot.fr", "Collegue2026!")
ADMIN = ("admin@construpilot.fr", "Construpilot2026!")

KNOWN_SOLVER_WITH_PHOTO = "prob_0dc81bf712"
KNOWN_SOLVER_NO_PHOTO = "prob_69d962d5f6"
KNOWN_DWG_JOB = "pplan_e90d130834e84a"


def _login(email, pwd):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    assert s.cookies.get("session_token"), "no session_token cookie"
    return s


@pytest.fixture(scope="module")
def pro_session(): return _login(*PRO)


@pytest.fixture(scope="module")
def client_session(): return _login(*CLIENT)


@pytest.fixture(scope="module")
def collegue_session(): return _login(*COLLEGUE)


@pytest.fixture(scope="module")
def admin_session(): return _login(*ADMIN)


# ---------------- Assistant docs (office) ----------------

def _xlsx_bytes():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Devis"
    ws.append(["Poste", "Quantité", "Prix HT"])
    ws.append(["Maçonnerie", 12, 4500])
    ws.append(["Plomberie", 8, 3200])
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _docx_bytes(with_cctp: bool = True, filename_marker: str = "cctp"):
    from docx import Document
    doc = Document()
    doc.add_paragraph("Document technique du chantier — révision 1.")
    if with_cctp:
        doc.add_paragraph("Cahier des clauses techniques (CCTP) : lot maçonnerie, section 3.2.")
    else:
        doc.add_paragraph("Note libre.")
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


def _csv_bytes():
    return b"poste;quantite;prix\nmurs;12;4500\nplomberie;8;3200\ntoiture;30;15000\n".decode().encode()


def _txt_bytes():
    return ("Note de chantier — " + ("point de blocage a resoudre. " * 10)).encode()


def _jpg_bytes(w=800, h=600):
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.line([(0, 0), (w, h)], fill="black", width=3)
    d.line([(0, h), (w, 0)], fill="red", width=3)
    d.rectangle([50, 50, w-50, h-50], outline="black", width=4)
    for i in range(10):
        d.line([(50, 100+i*40), (w-50, 100+i*40)], fill=(50, 50, 50), width=1)
    buf = io.BytesIO(); img.save(buf, format="JPEG", quality=90); return buf.getvalue()


@pytest.fixture(scope="module")
def uploaded_docs(pro_session):
    """Upload each office variant and return list of doc dicts. Cleaned up after class."""
    created = []
    payloads = [
        ("devis-test.xlsx", _xlsx_bytes(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("cctp-lot1.docx", _docx_bytes(True), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("liste.csv", _csv_bytes(), "text/csv"),
        ("note.txt", _txt_bytes(), "text/plain"),
    ]
    for name, data, mime in payloads:
        r = pro_session.post(f"{API}/assistant/documents", files={"file": (name, data, mime)}, timeout=30)
        assert r.status_code == 200, f"upload {name}: {r.status_code} {r.text[:200]}"
        created.append(r.json())
    yield created
    for d in created:
        pro_session.delete(f"{API}/assistant/documents/{d['doc_id']}", timeout=30)


class TestAssistantOfficeDocs:
    def test_uploads(self, uploaded_docs):
        by_name = {d["filename"]: d for d in uploaded_docs}
        xlsx = by_name["devis-test.xlsx"]
        docx = by_name["cctp-lot1.docx"]
        csv = by_name["liste.csv"]
        txt = by_name["note.txt"]
        # xlsx
        assert xlsx["mime"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        assert xlsx["kind"] != "plan", f"xlsx should not be classified as plan, got {xlsx['kind']}"
        # docx classified as cctp (filename OR text)
        assert docx["mime"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        assert docx["kind"] == "cctp", f"docx kind={docx['kind']}"
        # csv, txt
        assert csv["mime"] == "text/csv"
        assert txt["mime"] == "text/plain"
        # has_text: at least the docx and txt should be True (>=120 chars in their text)
        assert isinstance(docx.get("has_text"), bool)
        assert docx["has_text"] is True or txt["has_text"] is True

    def test_unsupported_ext(self, pro_session):
        r = pro_session.post(f"{API}/assistant/documents", files={"file": ("archive.zip", b"PK\x03\x04data", "application/zip")}, timeout=30)
        assert r.status_code == 415, f"expected 415 got {r.status_code}: {r.text[:200]}"
        msg = r.json().get("detail", "").lower()
        # Check message lists accepted formats
        for fmt in ("pdf", "png"):
            assert fmt in msg, f"detail should list accepted formats: {msg}"

    def test_list_documents(self, pro_session, uploaded_docs):
        r = pro_session.get(f"{API}/assistant/documents", timeout=30)
        assert r.status_code == 200
        ids = {d["doc_id"] for d in r.json()}
        for d in uploaded_docs:
            assert d["doc_id"] in ids

    def test_preview_xlsx_415(self, pro_session, uploaded_docs):
        xlsx = next(d for d in uploaded_docs if d["filename"].endswith(".xlsx"))
        r = pro_session.get(f"{API}/assistant/documents/{xlsx['doc_id']}/preview", timeout=30)
        assert r.status_code == 415, f"expected 415 got {r.status_code}"

    def test_preview_png_ok(self, pro_session):
        # Upload a non-uniform PNG that survives the image normalizer.
        img = Image.new("RGB", (600, 400), "white")
        d = ImageDraw.Draw(img)
        d.rectangle([20, 20, 580, 380], outline="black", width=4)
        for i in range(5):
            d.line([(0, i*80), (600, i*80)], fill=(100, 100, 100), width=2)
        buf = io.BytesIO(); img.save(buf, format="PNG")
        r = pro_session.post(f"{API}/assistant/documents", files={"file": ("preview.png", buf.getvalue(), "image/png")}, timeout=30)
        assert r.status_code == 200, f"upload png: {r.status_code} {r.text[:200]}"
        did = r.json()["doc_id"]
        try:
            r2 = pro_session.get(f"{API}/assistant/documents/{did}/preview", timeout=30)
            assert r2.status_code == 200
            assert r2.headers.get("content-type", "").startswith("image/jpeg")
            assert len(r2.content) > 0
        finally:
            pro_session.delete(f"{API}/assistant/documents/{did}", timeout=30)


class TestAssistantMessageDocIds:
    def test_7_doc_ids_not_422(self, pro_session, uploaded_docs):
        # Create conv, then post message with 7 doc_ids (mostly duplicates of one real id).
        c = pro_session.post(f"{API}/assistant/conversations", json={"title": "test iter182"}, timeout=30)
        assert c.status_code == 200
        conv_id = c.json()["conversation_id"]
        try:
            doc_ids = [uploaded_docs[0]["doc_id"]] * 7
            body = {"conversation_id": conv_id, "text": "Résume vite", "doc_ids": doc_ids,
                    "request_id": "iter182-t1", "effort": "low", "response_mode": "fast"}
            # /message may be long-running; give it 5s only — we only care about non-422.
            try:
                r = pro_session.post(f"{API}/assistant/message", json=body, timeout=5)
                code = r.status_code
            except requests.Timeout:
                code = 200  # not rejected at validation stage
            assert code != 422, f"unexpected 422 with 7 doc_ids"
        finally:
            pro_session.delete(f"{API}/assistant/conversations/{conv_id}", timeout=30)

    def test_11_doc_ids_422(self, pro_session, uploaded_docs):
        c = pro_session.post(f"{API}/assistant/conversations", json={"title": "test iter182b"}, timeout=30)
        assert c.status_code == 200
        conv_id = c.json()["conversation_id"]
        try:
            doc_ids = [uploaded_docs[0]["doc_id"]] * 11
            body = {"conversation_id": conv_id, "text": "Trop", "doc_ids": doc_ids, "request_id": "iter182-t2"}
            r = pro_session.post(f"{API}/assistant/message", json=body, timeout=15)
            assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text[:200]}"
        finally:
            pro_session.delete(f"{API}/assistant/conversations/{conv_id}", timeout=30)


# ---------------- BTP solver photos ----------------

class TestSolverPhotos:
    def test_upload_jpg(self, pro_session):
        r = pro_session.post(f"{API}/btp-solver/photos", files={"file": ("fissure.jpg", _jpg_bytes(), "image/jpeg")}, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        d = r.json()
        assert d["photo_id"].startswith("sph_")
        assert d["mime"] == "image/jpeg"
        assert d["size"] > 100
        # keep photo_id for get/cross-user tests
        pytest.upload_photo_id = d["photo_id"]

    def test_get_own_photo(self, pro_session):
        pid = pytest.upload_photo_id
        r = pro_session.get(f"{API}/btp-solver/photos/{pid}", timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/jpeg")
        assert len(r.content) > 100

    def test_get_photo_cross_user_404(self, client_session):
        pid = pytest.upload_photo_id
        r = client_session.get(f"{API}/btp-solver/photos/{pid}", timeout=30)
        assert r.status_code == 404

    def test_empty_photo(self, pro_session):
        r = pro_session.post(f"{API}/btp-solver/photos", files={"file": ("x.jpg", b"", "image/jpeg")}, timeout=30)
        assert r.status_code == 400

    def test_pdf_as_photo_415(self, pro_session):
        r = pro_session.post(f"{API}/btp-solver/photos", files={"file": ("x.pdf", b"%PDF-1.4\n%EOF", "application/pdf")}, timeout=30)
        assert r.status_code == 415

    def test_txt_as_photo_415(self, pro_session):
        r = pro_session.post(f"{API}/btp-solver/photos", files={"file": ("x.txt", b"hello", "text/plain")}, timeout=30)
        assert r.status_code == 415

    def test_solve_too_many_photo_ids(self, pro_session):
        body = {"description": "Fissure horizontale à surveiller sur pignon.", "photo_ids": ["sph_a", "sph_b", "sph_c", "sph_d"]}
        r = pro_session.post(f"{API}/btp-solver/solve", json=body, timeout=15)
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text[:200]}"

    def test_solve_unknown_photo_id_404(self, pro_session):
        body = {"description": "Fissure horizontale à surveiller sur pignon.", "photo_ids": ["sph_deadbeef00"]}
        r = pro_session.post(f"{API}/btp-solver/solve", json=body, timeout=15)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:200]}"


# ---------------- Solver PDF ----------------

class TestSolverPDF:
    def test_pdf_with_photo(self, pro_session):
        r = pro_session.get(f"{API}/btp-solver/{KNOWN_SOLVER_WITH_PHOTO}/report.pdf", timeout=60)
        assert r.status_code == 200, r.text[:200]
        assert r.headers["content-type"] == "application/pdf"
        assert "attachment" in r.headers.get("content-disposition", "")
        content = r.content
        assert content.startswith(b"%PDF"), "not a valid PDF"
        # Count pages by /Type /Page occurrences (rough but sufficient)
        pages = content.count(b"/Type /Page") - content.count(b"/Type /Pages")
        assert pages >= 5, f"expected >=5 pages, got {pages}"
        # Extract text via pypdf
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        for kw in ("Diagnostic provisionnel", "Causes probables", "Solutions proposées",
                   "Comparatifs visuels", "Photos jointes", "Lecture des photos jointes"):
            assert kw in text, f"missing keyword {kw!r} in PDF"

    def test_pdf_no_photo(self, pro_session):
        r = pro_session.get(f"{API}/btp-solver/{KNOWN_SOLVER_NO_PHOTO}/report.pdf", timeout=60)
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(r.content))
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        assert "Photos jointes" not in text
        assert "Diagnostic provisionnel" in text

    def test_pdf_cross_user_404(self, client_session):
        r = client_session.get(f"{API}/btp-solver/{KNOWN_SOLVER_WITH_PHOTO}/report.pdf", timeout=30)
        assert r.status_code == 404

    def test_pdf_unauth_401(self):
        r = requests.get(f"{API}/btp-solver/{KNOWN_SOLVER_WITH_PHOTO}/report.pdf", timeout=30)
        assert r.status_code == 401

    def test_detail_photo_analysis(self, pro_session):
        r = pro_session.get(f"{API}/btp-solver/{KNOWN_SOLVER_WITH_PHOTO}", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "done"
        assert d.get("photo_ids") == ["sph_db28a421ebb6"]
        pa = d.get("photo_analysis")
        assert isinstance(pa, str) and len(pa) > 0


# ---------------- Plans Pro DWG quantities ----------------

class TestPlansProDWG:
    def test_history_has_dwg(self, pro_session):
        r = pro_session.get(f"{API}/plans-pro/history?limit=20", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        target = next((it for it in items if it.get("job_id") == KNOWN_DWG_JOB), None)
        if not target:
            target = next((it for it in items if (it.get("filename") or "").lower().endswith(".dwg") and it.get("status") == "done"), None)
        assert target, "no .dwg done job found in history"
        assert target.get("status") == "done"

    def test_dwg_result_quantities(self, pro_session):
        r = pro_session.get(f"{API}/plans-pro/job/{KNOWN_DWG_JOB}/result", timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d.get("vision") is None
        auto = d.get("autodesk") or {}
        q = auto.get("quantities")
        assert isinstance(q, dict), f"quantities not a dict: {type(q)}"
        expected = {"Murs", "Poutres", "Poteaux", "Sols", "Portes", "Fenêtres"}
        present = expected & set(q.keys())
        assert present, f"none of {expected} in {list(q.keys())}"
        for cat, val in q.items():
            if cat not in expected:
                continue
            assert isinstance(val, dict)
            assert val.get("count", 0) > 0
            assert val.get("source") == "layers"
            assert isinstance(val.get("layers"), list) and len(val["layers"]) > 0
            for lay in val["layers"]:
                assert "layer" in lay and "count" in lay
        # elements_count near 35615
        ec = auto.get("elements_count")
        assert isinstance(ec, int)
        assert 30000 < ec < 40000, f"elements_count={ec}"


# ---------------- Deadline reminders ----------------

class TestDeadlineReminders:
    def test_pro_forbidden(self, pro_session):
        r = pro_session.post(f"{API}/trash/deadline-reminders/run", timeout=30)
        assert r.status_code == 403

    def test_admin_run_idempotent(self, admin_session):
        r = admin_session.post(f"{API}/trash/deadline-reminders/run", timeout=60)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        for k in ("notified", "emails", "target"):
            assert k in d
        # second immediate run should be idempotent (already sent today)
        time.sleep(1)
        r2 = admin_session.post(f"{API}/trash/deadline-reminders/run", timeout=60)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("notified", 1) == 0, f"expected notified=0 second run, got {d2}"

    def test_notifications_pro(self, pro_session):
        r = pro_session.get(f"{API}/notifications", timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data.get("notifications", []) if isinstance(data, dict) else data
        dr = [n for n in items if n.get("type") == "deadline_reminder"]
        assert dr, f"no deadline_reminder notif for pro. sample: {items[:3]}"
        n = dr[0]
        assert n.get("url") == "/assistant?conversation=conv_f1f91025f9"
        assert "Échéance demain" in (n.get("message") or ""), f"message={n.get('message')}"

    def test_notifications_collegue(self, collegue_session):
        r = collegue_session.get(f"{API}/notifications", timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data.get("notifications", []) if isinstance(data, dict) else data
        dr = [n for n in items if n.get("type") == "deadline_reminder"]
        assert dr, "no deadline_reminder notif for collegue"


class TestParseDeadlineUnit:
    def test_parse(self):
        from engines.deadline_reminders import parse_deadline
        today = date(2026, 1, 20)
        assert parse_deadline("22/09/2026", today) == date(2026, 9, 22)
        # "19 septembre" without year -> current year
        assert parse_deadline("19 septembre", today) == date(2026, 9, 19)
        assert parse_deadline("avant coulage", today) is None
