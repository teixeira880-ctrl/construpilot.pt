"""Iter 186 — Company page, PDF customization, generated VAT, today block."""
import io
import os

import pytest
import requests

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PRO_EMAIL, PRO_PWD = "pro@construpilot.fr", "Pro2026!"
COL_EMAIL, COL_PWD = "collegue@construpilot.fr", "Collegue2026!"
CLI_EMAIL, CLI_PWD = "client@construpilot.fr", "Client2026!"
DOC_REVISION = "doc_e678adc22636"


def _login(email: str, pwd: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def pro():
    return _login(PRO_EMAIL, PRO_PWD)


@pytest.fixture(scope="module")
def collegue():
    return _login(COL_EMAIL, COL_PWD)


@pytest.fixture(scope="module")
def client():
    return _login(CLI_EMAIL, CLI_PWD)


def _make_jpg(w=800, h=500) -> bytes:
    if Image is None:
        pytest.skip("Pillow not installed")
    img = Image.new("RGB", (w, h), (200, 220, 255))
    d = ImageDraw.Draw(img)
    d.rectangle([50, 50, w - 50, h - 50], outline=(30, 60, 120), width=8)
    d.ellipse([200, 100, 600, 400], fill=(255, 180, 90))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    return buf.getvalue()


# ---------------- Company page (GET / PUT / slug conflict / 403) ---------------- #
class TestCompanyPage:
    def test_get_page_pro(self, pro):
        r = pro.get(f"{BASE_URL}/api/company/page")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["slug"] == "marc-btp-pro"
        assert "published" in d and isinstance(d["published"], bool)
        assert d["public_url"] == "/entreprise/marc-btp-pro"
        assert "user_id" in d and d["user_id"]
        assert "accent_color" in d
        assert isinstance(d.get("photos"), list)

    def test_put_page_valid(self, pro):
        payload = {"header_text": "Maçonnerie générale — Qualibat 2111",
                   "footer_text": "SARL BTP Demo — RCS Paris 123 456 789 — Décennale AXA n° 4567",
                   "accent_color": "#0f766e", "tagline": "Artisan maçon depuis 2005",
                   "description": "Rénovation, extension, gros œuvre à Paris et proche banlieue.",
                   "published": True, "contact_phone": "+33 6 12 34 56 78",
                   "website": "https://marc-btp.fr", "show_reviews": True}
        r = pro.put(f"{BASE_URL}/api/company/page", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["accent_color"] == "#0f766e"
        assert d["tagline"] == payload["tagline"]
        assert d["header_text"] == payload["header_text"]
        assert d["published"] is True
        assert d["phone"] == payload["contact_phone"]

    def test_put_page_invalid_color(self, pro):
        r = pro.put(f"{BASE_URL}/api/company/page", json={"accent_color": "red"})
        assert r.status_code == 422

    def test_put_own_slug_ok(self, pro):
        r = pro.put(f"{BASE_URL}/api/company/page", json={"slug": "marc-btp-pro"})
        assert r.status_code == 200

    def test_put_taken_slug_conflict(self, collegue):
        r = collegue.put(f"{BASE_URL}/api/company/page", json={"slug": "marc-btp-pro"})
        assert r.status_code == 409, r.text

    def test_client_page_forbidden(self, client):
        r = client.get(f"{BASE_URL}/api/company/page")
        assert r.status_code == 403


# ---------------- Showcase gallery ---------------- #
class TestShowcase:
    photo_id = None

    def test_add_photo(self, pro):
        jpg = _make_jpg()
        r = pro.post(f"{BASE_URL}/api/company/page/photos",
                     files={"file": ("test186.jpg", jpg, "image/jpeg")},
                     data={"title": "Test iter186", "description": "desc"})
        if r.status_code == 503:
            pytest.skip("Emergent object storage unavailable (503)")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["photo_id"].startswith("shw_")
        assert d["title"] == "Test iter186"
        assert d["description"] == "desc"
        TestShowcase.photo_id = d["photo_id"]

    def test_patch_photo(self, pro):
        assert TestShowcase.photo_id
        r = pro.patch(f"{BASE_URL}/api/company/page/photos/{TestShowcase.photo_id}", json={"title": "Renommé"})
        assert r.status_code == 200
        page = pro.get(f"{BASE_URL}/api/company/page").json()
        photo = next(p for p in page["photos"] if p["photo_id"] == TestShowcase.photo_id)
        assert photo["title"] == "Renommé"
        # no 'path' leak in listing
        assert "path" not in photo

    def test_own_photo_binary(self, pro):
        r = pro.get(f"{BASE_URL}/api/company/page/photo/{TestShowcase.photo_id}")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/jpeg")
        assert len(r.content) > 500

    def test_public_page_ok(self):
        r = requests.get(f"{BASE_URL}/api/public/company/marc-btp-pro", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["company_name"]
        assert "accent_color" in d
        assert "tagline" in d
        assert "brand_logo_b64" not in d
        assert any(p["photo_id"] == TestShowcase.photo_id for p in d["photos"])
        for p in d["photos"]:
            assert "path" not in p

    def test_public_photo_no_auth(self):
        r = requests.get(f"{BASE_URL}/api/public/company/marc-btp-pro/photo/{TestShowcase.photo_id}", timeout=30)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")

    def test_unpublish_hides_public(self, pro):
        pro.put(f"{BASE_URL}/api/company/page", json={"published": False})
        try:
            r = requests.get(f"{BASE_URL}/api/public/company/marc-btp-pro", timeout=30)
            assert r.status_code == 404
        finally:
            pro.put(f"{BASE_URL}/api/company/page", json={"published": True})

    def test_empty_file_400(self, pro):
        r = pro.post(f"{BASE_URL}/api/company/page/photos",
                     files={"file": ("empty.jpg", b"", "image/jpeg")},
                     data={"title": "x"})
        assert r.status_code == 400

    def test_txt_file_415(self, pro):
        r = pro.post(f"{BASE_URL}/api/company/page/photos",
                     files={"file": ("note.txt", b"hello world", "text/plain")},
                     data={"title": "x"})
        assert r.status_code == 415

    def test_delete_photo(self, pro):
        r = pro.delete(f"{BASE_URL}/api/company/page/photos/{TestShowcase.photo_id}")
        assert r.status_code == 200
        r2 = pro.delete(f"{BASE_URL}/api/company/page/photos/shw_doesnotexist")
        assert r2.status_code == 404

    def test_unknown_slug_404(self):
        r = requests.get(f"{BASE_URL}/api/public/company/does-not-exist-xyz", timeout=30)
        assert r.status_code == 404


# ---------------- PDF customization ---------------- #
class TestPDFCustomization:
    def test_pdf_contains_header_footer(self, pro):
        try:
            import pymupdf  # type: ignore
        except ImportError:
            try:
                import fitz as pymupdf  # type: ignore
            except ImportError:
                pytest.skip("pymupdf not installed")
        # Set custom header/footer
        r = pro.put(f"{BASE_URL}/api/company/page",
                    json={"header_text": "HEADERTEST-186", "footer_text": "FOOTERTEST-186"})
        assert r.status_code == 200
        try:
            r = pro.get(f"{BASE_URL}/api/documents/{DOC_REVISION}/pdf")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("application/pdf")
            doc = pymupdf.open(stream=r.content, filetype="pdf")
            text = "".join(p.get_text() for p in doc)
            doc.close()
            assert "HEADERTEST-186" in text, text[:500]
            assert "FOOTERTEST-186" in text, text[:500]
        finally:
            # reset to neutral
            pro.put(f"{BASE_URL}/api/company/page",
                    json={"header_text": "Maçonnerie générale — Qualibat 2111",
                          "footer_text": "SARL BTP Demo — RCS Paris 123 456 789 — Décennale AXA n° 4567"})


# ---------------- Generated VAT normalisation ---------------- #
class TestGeneratedVAT:
    def test_create_and_update_vat_normalisation(self, pro):
        payload = {"doc_type": "quote", "title": "TEST_iter186_vat",
                   "lines": [
                       {"designation": "IA", "qty": 1, "unit_price_ht": 100, "vat_rate": 10, "price_source": "plan_ai"},
                       {"designation": "Manuelle", "qty": 1, "unit_price_ht": 100, "vat_rate": 10},
                       {"designation": "IA confirmée", "qty": 1, "unit_price_ht": 100, "vat_rate": 10,
                        "price_source": "cctp_ai", "vat_confirmed": True},
                       {"designation": "IA sans TVA", "qty": 1, "unit_price_ht": 100, "price_source": "photo_ai"},
                   ]}
        r = pro.post(f"{BASE_URL}/api/documents", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        try:
            lines = d["lines"]
            assert lines[0]["vat_rate"] == 20 and lines[0]["vat_assumed"] is True
            assert lines[1]["vat_rate"] == 10 and lines[1]["vat_assumed"] is False
            assert lines[2]["vat_rate"] == 10 and lines[2]["vat_assumed"] is False
            assert lines[3]["vat_rate"] == 20 and lines[3]["vat_assumed"] is True
            assert d["totals"]["vat_assumed_lines"] == 2

            # PUT same payload -> re-normalises
            r2 = pro.put(f"{BASE_URL}/api/documents/{d['doc_id']}", json=payload)
            assert r2.status_code == 200, r2.text
            d2 = r2.json()
            l2 = d2["lines"]
            assert l2[0]["vat_rate"] == 20 and l2[0]["vat_assumed"] is True
            assert l2[1]["vat_rate"] == 10 and l2[1]["vat_assumed"] is False
            assert l2[3]["vat_rate"] == 20 and l2[3]["vat_assumed"] is True
            assert d2["totals"]["vat_assumed_lines"] == 2
        finally:
            pro.delete(f"{BASE_URL}/api/documents/{d['doc_id']}")


# ---------------- Today block ---------------- #
class TestToday:
    def test_pro_today(self, pro):
        r = pro.get(f"{BASE_URL}/api/dashboard/today")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "date" in d
        na = d["next_action"]
        assert {"kind", "label", "url"} <= set(na)
        assert isinstance(d["items"], list)
        allowed = {"invoice_overdue", "quote_followup", "plan_review", "deadline", "vat_to_confirm"}
        for it in d["items"]:
            assert it["kind"] in allowed
        assert isinstance(d["running_analyses"], int)
        counts = d["counts"]
        for k in ("quotes", "clients", "projects", "plans"):
            assert k in counts and isinstance(counts[k], int)
        assert d["empty_account"] is False
        # If any invoice_overdue present, it should come first
        kinds = [i["kind"] for i in d["items"]]
        if "invoice_overdue" in kinds:
            assert kinds[0] == "invoice_overdue"

    def test_client_today(self, client):
        r = client.get(f"{BASE_URL}/api/dashboard/today")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["next_action"]["kind"] in ("setup", "clear")
        pro_kinds = {"invoice_overdue", "quote_followup", "plan_review", "vat_to_confirm"}
        for it in d["items"]:
            assert it["kind"] not in pro_kinds

    def test_unauth(self):
        r = requests.get(f"{BASE_URL}/api/dashboard/today", timeout=15)
        assert r.status_code == 401
