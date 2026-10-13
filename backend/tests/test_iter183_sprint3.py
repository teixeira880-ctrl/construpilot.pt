"""Iteration 183 — Sprint 3 tests:
  (A) « Photos dans le compte rendu »: meeting-report PDF must append a
      pinned-photo annex page when open_points have before/after photos.
  (B) « Vignette Autodesk » (read-only): plans-pro job pplan_4e216317b5b949
      returns autodesk.thumbnail data URL + quantities Murs source=layers,
      vision.source == 'autodesk_thumbnail'. History projection excludes
      autodesk_thumbnail. Client cannot read pro job.

NO paid Autodesk conversion is triggered here (uses cached job).
Uses HttpOnly session cookies via requests.Session.
"""
import base64
import io
import os

import pytest
import requests
from PIL import Image, ImageDraw

def _read_env_url():
    v = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not v:
        try:
            for line in open("/app/frontend/.env"):
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass
    return v.rstrip("/")

BASE = _read_env_url()
assert BASE, "REACT_APP_BACKEND_URL required"
API = f"{BASE}/api"

PRO = ("pro@construpilot.fr", "Pro2026!")
CLIENT = ("client@construpilot.fr", "Client2026!")

KNOWN_JOB = "pplan_4e216317b5b949"


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


# --------------------------- (A) Meeting report + photo annex ---------------------------

def _make_jpg_bytes(w=600, h=400, seed=0):
    img = Image.new("RGB", (w, h), (230, 230, 240))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 40, 260, 260], outline=(200, 40, 40), width=6)
    d.ellipse([300, 80, 520, 300], outline=(20, 90, 200), width=6)
    d.line([0, 0, w, h], fill=(0, 0, 0), width=3)
    d.text((60, 300), f"TEST photo CR {seed}", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _upload_photo(sess, seed=0):
    files = {"file": (f"TEST_photo_{seed}.jpg", _make_jpg_bytes(seed=seed), "image/jpeg")}
    r = sess.post(f"{API}/assistant/documents", params={"kind": "photo"}, files=files, timeout=60)
    assert r.status_code == 200, f"upload {r.status_code} {r.text[:300]}"
    j = r.json()
    assert j.get("mime", "").startswith("image/"), j
    return j["doc_id"]


def _create_conv(sess):
    r = sess.post(f"{API}/assistant/conversations", json={}, timeout=20)
    assert r.status_code == 200, r.text[:300]
    return r.json()["conversation_id"]


def _delete_conv(sess, cid):
    try:
        sess.delete(f"{API}/assistant/conversations/{cid}", timeout=20)
    except Exception:
        pass


def _delete_doc(sess, did):
    try:
        sess.delete(f"{API}/assistant/documents/{did}", timeout=20)
    except Exception:
        pass


def _create_open_point(sess, cid, statement):
    body = {
        "section": "open_points",
        "statement": statement,
        "source": "test",
        "status": "to_confirm",
        "kind": "action",
    }
    r = sess.put(f"{API}/assistant/conversations/{cid}/state", json=body, timeout=30)
    assert r.status_code == 200, f"state entry {r.status_code} {r.text[:300]}"
    j = r.json()
    # Find the newly created entry id in open_points
    st = j.get("state") or {}
    ops = st.get("open_points") or []
    assert ops, f"no open_points in state: {j}"
    # Statement may be normalised — take the entry with matching statement contained
    for e in ops:
        if statement.split(" — ")[0] in (e.get("statement") or ""):
            return e["entry_id"]
    return ops[-1]["entry_id"]


def _pin_photo(sess, cid, entry_id, doc_id, phase="before"):
    r = sess.post(
        f"{API}/assistant/conversations/{cid}/state/{entry_id}/photos",
        json={"doc_id": doc_id, "phase": phase},
        timeout=30,
    )
    assert r.status_code == 200, f"pin photo {r.status_code} {r.text[:300]}"
    return r.json()


def _meeting_report(sess, cid, items, meeting="Réunion test"):
    body = {
        "meeting": meeting,
        "attendees": "Test Pro",
        "remarks": "Compte rendu de test iteration 183.",
        "items": items,
    }
    r = sess.post(f"{API}/assistant/conversations/{cid}/meeting-report", json=body, timeout=90)
    assert r.status_code == 200, f"meeting-report {r.status_code} {r.text[:400]}"
    return r.json()


def _download_pdf(sess, artifact_id):
    r = sess.get(f"{API}/assistant/artifacts/{artifact_id}/content", timeout=60)
    assert r.status_code == 200, f"artifact {r.status_code} {r.text[:300]}"
    assert r.content.startswith(b"%PDF"), "not a PDF"
    return r.content


class TestMeetingReportPhotoAnnex:
    """(A) Photos dans le compte rendu."""

    def test_full_flow_with_photo_annex(self, pro_session):
        created_docs = []
        created_convs = []
        try:
            cid = _create_conv(pro_session)
            created_convs.append(cid)

            doc_id = _upload_photo(pro_session, seed=1)
            created_docs.append(doc_id)

            statement = "TEST photo CR — fissure façade"
            entry_id = _create_open_point(pro_session, cid, statement)
            _pin_photo(pro_session, cid, entry_id, doc_id, phase="before")

            res = _meeting_report(pro_session, cid, items=[{
                "entry_id": entry_id,
                "outcome": "decided",
                "decision_taken": "Reprise de l'enduit",
                "owner": "Entreprise X",
                "deadline": "2026-02-15",
            }])
            assert res.get("counts", {}).get("decided") == 1, res.get("counts")
            art_id = res["artifact"]["artifact_id"]

            pdf = _download_pdf(pro_session, art_id)

            import pymupdf
            with pymupdf.open(stream=pdf, filetype="pdf") as pdoc:
                assert pdoc.page_count >= 2, f"expected >=2 pages, got {pdoc.page_count}"
                # find any page containing the annex header + statement + embedded image
                found_header, found_stmt, found_img = False, False, False
                for i in range(pdoc.page_count):
                    p = pdoc.load_page(i)
                    txt = p.get_text() or ""
                    if "Annexe" in txt and "photos" in txt.lower():
                        found_header = True
                    if "TEST photo CR" in txt or "fissure fa" in txt:
                        found_stmt = True
                    if p.get_images():
                        found_img = True
                assert found_header, "annex header not found in PDF text"
                assert found_stmt, "entry statement not found in PDF text"
                assert found_img, "no embedded image found in PDF"
        finally:
            for d in created_docs: _delete_doc(pro_session, d)
            for c in created_convs: _delete_conv(pro_session, c)

    def test_control_no_photo_no_annex(self, pro_session):
        created_convs = []
        try:
            cid = _create_conv(pro_session)
            created_convs.append(cid)
            entry_id = _create_open_point(pro_session, cid, "TEST sans photo — contrôle CR")
            res = _meeting_report(pro_session, cid, items=[{
                "entry_id": entry_id,
                "outcome": "decided",
                "decision_taken": "OK",
                "owner": "-",
                "deadline": "2026-02-20",
            }], meeting="Réunion sans photo")
            art_id = res["artifact"]["artifact_id"]
            pdf = _download_pdf(pro_session, art_id)
            import pymupdf
            with pymupdf.open(stream=pdf, filetype="pdf") as pdoc:
                assert pdoc.page_count == 1, f"expected 1 page, got {pdoc.page_count}"
                txt = pdoc.load_page(0).get_text() or ""
                assert "Annexe" not in txt, "should not contain annex when no pinned photos"
        finally:
            for c in created_convs: _delete_conv(pro_session, c)


# --------------------------- (B) Plans Pro Autodesk thumbnail ---------------------------

class TestPlansProAutodeskThumbnail:
    """(B) Read-only: vignette + vision on cached job pplan_4e216317b5b949."""

    def test_job_result_has_thumbnail_and_vision(self, pro_session):
        r = pro_session.get(f"{API}/plans-pro/job/{KNOWN_JOB}/result", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        j = r.json()
        autodesk = j.get("autodesk") or {}
        thumb = autodesk.get("thumbnail")
        assert isinstance(thumb, str) and thumb.startswith("data:image/png;base64,"), f"bad thumbnail: {str(thumb)[:80]}"
        # decode PNG and check it's a valid image ~400px
        raw = base64.b64decode(thumb.split(",", 1)[1])
        img = Image.open(io.BytesIO(raw))
        img.verify()
        img2 = Image.open(io.BytesIO(raw))
        assert max(img2.size) >= 200, f"thumbnail too small: {img2.size}"

        quantities = autodesk.get("quantities") or {}
        murs = quantities.get("Murs")
        assert murs, f"no Murs in quantities: {list(quantities.keys())}"
        assert murs.get("source") == "layers", f"Murs.source != layers: {murs}"

        vision = j.get("vision") or {}
        assert vision.get("ok") is True, f"vision.ok not True: {vision}"
        assert vision.get("source") == "autodesk_thumbnail", f"vision.source={vision.get('source')}"
        assert vision.get("providers_used"), f"providers_used empty: {vision.get('providers_used')}"
        assert vision.get("elements"), "vision.elements empty"

    def test_history_excludes_thumbnail(self, pro_session):
        r = pro_session.get(f"{API}/plans-pro/history", params={"limit": 20}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("items", [])
        assert items, "empty history"
        for it in items:
            assert "autodesk_thumbnail" not in it, f"projection leaked autodesk_thumbnail in {it.get('job_id')}"

    def test_client_cannot_read_pro_job(self, client_session):
        r = client_session.get(f"{API}/plans-pro/job/{KNOWN_JOB}/result", timeout=30)
        assert r.status_code == 404, f"expected 404, got {r.status_code} {r.text[:200]}"
