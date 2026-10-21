"""Iteration 128 regression tests: internal PDF, CCTP extract, newsletter, BLG webhook/sitemap, postal read-only."""
import io
import os
import random
import string
import time
import pytest
import requests

def _read_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL")
    if url:
        return url.rstrip("/")
    # fallback: read from frontend/.env
    for path in ("/app/frontend/.env", "frontend/.env"):
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not found")

BASE = _read_backend_url()
PRO = {"email": "pro@construpilot.fr", "password": "Pro2026!"}
ADMIN = {"email": "admin@construpilot.fr", "password": "Construpilot2026!"}
BLG_SECRET = "ZPBXSRe-uVlXunXsqyHNonuv0L_Hz4pv"


def _login(creds):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login {creds['email']} failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def pro_token():
    return _login(PRO)


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN)


@pytest.fixture(scope="session")
def pro_h(pro_token):
    return {"Authorization": f"Bearer {pro_token}"}


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


def _rand(n=8):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# ---------- (1) Internal PDF with costs & margins ----------
@pytest.fixture(scope="module")
def internal_doc_id(pro_h):
    payload = {
        "doc_type": "quote",
        "title": "TEST_iter128_internal",
        "lines": [
            {"designation": "Peinture murs", "quantity": 10, "unit": "m2",
             "unit_price_ht": 30, "cost_price_ht": 20, "vat_rate": 20, "category": "Peinture"},
            {"designation": "Carrelage sol", "quantity": 5, "unit": "m2",
             "unit_price_ht": 40, "cost_price_ht": 50, "vat_rate": 20, "category": "Carrelage"},
            {"designation": "Nettoyage final", "quantity": 1, "unit": "u",
             "unit_price_ht": 150, "vat_rate": 20, "category": "Finitions"},
        ],
    }
    r = requests.post(f"{BASE}/api/documents", json=payload, headers=pro_h, timeout=30)
    assert r.status_code in (200, 201), r.text[:200]
    return r.json()["doc_id"]


def test_pdf_internal_success(pro_h, internal_doc_id):
    r = requests.get(f"{BASE}/api/documents/{internal_doc_id}/pdf-internal",
                     headers=pro_h, timeout=60)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    disp = r.headers.get("content-disposition", "")
    assert "-INTERNE.pdf" in disp, disp
    # extract text
    from pypdf import PdfReader
    txt = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(r.content)).pages)
    for needle in ["VERSION INTERNE", "Marge", "Carrelage", "perte", "Synthèse"]:
        assert needle in txt, f"missing '{needle}' in internal PDF text: {txt[:500]}"


def test_pdf_internal_anonymous_401(internal_doc_id):
    r = requests.get(f"{BASE}/api/documents/{internal_doc_id}/pdf-internal", timeout=15)
    assert r.status_code == 401


def test_pdf_internal_other_user_404(internal_doc_id):
    # login as another user
    other = _login({"email": "collegue@construpilot.fr", "password": "Collegue2026!"})
    r = requests.get(f"{BASE}/api/documents/{internal_doc_id}/pdf-internal",
                     headers={"Authorization": f"Bearer {other}"}, timeout=15)
    assert r.status_code == 404, r.status_code


# ---------- (2) CCTP extract ----------
def _cctp_pdf() -> bytes:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    lines = [
        "CCTP - LOT 03 PLÂTRERIE",
        "",
        "LOT 03 PLÂTRERIE",
        "3.2.1 Doublage thermique BA13 + PSE 100 mm Placomur Ultra 32 ou équivalent,",
        "conforme DTU 25.41, Quantité : 62 m²",
        "Les matériaux Placomur Ultra 32 sont imposés au titre du présent marché.",
        "",
        "3.2.2 Cloisons Placostil 72/48, épaisseur 72 mm, hauteur 2,50 m,",
        "Quantité : 28 m²",
        "",
        "LOT 05 PEINTURE",
        "5.1 Peinture acrylique Tollens ou équivalent, deux couches sur murs",
        "et plafonds, teinte au choix du maître d'ouvrage,",
        "Quantité : 237 m²",
        "",
        "Prescriptions générales : respect des DTU applicables, garantie décennale.",
    ]
    for ln in lines:
        c.drawString(50, y, ln)
        y -= 18
    c.showPage()
    c.save()
    return buf.getvalue()


def test_cctp_extract_success(pro_h):
    pdf = _cctp_pdf()
    files = {"file": ("cctp.pdf", pdf, "application/pdf")}
    r = requests.post(f"{BASE}/api/documents/cctp/extract",
                      files=files, headers=pro_h, timeout=200)
    assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
    data = r.json()
    assert "title" in data
    lines = data.get("lines") or []
    assert len(lines) >= 3, f"expected >=3 lines, got {len(lines)}: {lines}"
    # each line: designation prefixed by article number; category (lot); unit; qty; description contains 'Imposé :'
    qtys_seen = set()
    imposed_desc = 0
    for ln in lines:
        desig = ln.get("designation", "")
        assert desig, f"empty designation in {ln}"
        assert ln.get("category"), f"missing category (lot) in {ln}"
        assert ln.get("unit"), f"missing unit in {ln}"
        qv = ln.get("qty", ln.get("quantity"))
        if qv in (62, 28, 237, 62.0, 28.0, 237.0):
            qtys_seen.add(int(qv))
        if "Imposé" in (ln.get("description") or ""):
            imposed_desc += 1
    assert qtys_seen & {62, 28, 237}, f"none of expected quantities found. lines={lines}"
    assert data.get("imposed_count", 0) >= 1
    assert "prescriptions" in data and isinstance(data["prescriptions"], list)
    assert "priced_lines" in data


def test_cctp_extract_too_short_422(pro_h):
    # PDF with < 200 chars
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 800, "tiny")
    c.showPage()
    c.save()
    files = {"file": ("tiny.pdf", buf.getvalue(), "application/pdf")}
    r = requests.post(f"{BASE}/api/documents/cctp/extract",
                      files=files, headers=pro_h, timeout=30)
    assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"


def test_cctp_extract_anonymous_401():
    pdf = _cctp_pdf()
    files = {"file": ("cctp.pdf", pdf, "application/pdf")}
    r = requests.post(f"{BASE}/api/documents/cctp/extract", files=files, timeout=30)
    assert r.status_code == 401


# ---------- (3) Newsletter ----------
NEWSLETTER_EMAIL = f"qa-newsletter-{_rand()}@construpilot-test.fr"


def test_newsletter_subscribe_first(admin_h):
    # clean up any prior rate limits for this test IP is not deterministic - just run
    r = requests.post(f"{BASE}/api/newsletter/subscribe",
                      json={"email": NEWSLETTER_EMAIL, "lang": "fr", "source": "qa"}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert not body.get("already")


def test_newsletter_subscribe_idempotent():
    r = requests.post(f"{BASE}/api/newsletter/subscribe",
                      json={"email": NEWSLETTER_EMAIL, "lang": "fr"}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("already") is True


def test_newsletter_subscribe_invalid_email():
    r = requests.post(f"{BASE}/api/newsletter/subscribe",
                      json={"email": "bad", "lang": "fr"}, timeout=15)
    assert r.status_code == 400


def test_newsletter_subscribe_example_domain():
    r = requests.post(f"{BASE}/api/newsletter/subscribe",
                      json={"email": f"foo-{_rand()}@example.com", "lang": "fr"}, timeout=15)
    assert r.status_code == 400


def test_newsletter_admin_stats_pro_forbidden(pro_h):
    r = requests.get(f"{BASE}/api/newsletter/admin/stats", headers=pro_h, timeout=15)
    assert r.status_code == 403


def test_newsletter_admin_stats_admin(admin_h):
    r = requests.get(f"{BASE}/api/newsletter/admin/stats", headers=admin_h, timeout=15)
    assert r.status_code == 200
    body = r.json()
    for k in ("active", "total", "recent_sends"):
        assert k in body


def test_newsletter_unsubscribe_valid_and_invalid():
    # fetch token from admin stats (subscribers list not directly exposed) → use API by re-subscribing with new email
    email = f"qa-unsub-{_rand()}@construpilot-test.fr"
    r = requests.post(f"{BASE}/api/newsletter/subscribe",
                      json={"email": email, "lang": "fr"}, timeout=30)
    if r.status_code == 429:
        pytest.skip("rate limited on newsletter subscribe (previous tests consumed slots)")
    assert r.status_code == 200
    # Fetch token from DB via a simple approach: hit unsubscribe with fake token first
    r_invalid = requests.get(f"{BASE}/api/newsletter/unsubscribe?token=nonexistent-{_rand(12)}",
                             timeout=15)
    assert r_invalid.status_code == 200
    assert "Lien invalide" in r_invalid.text
    # We can't easily obtain the token without DB access from here.
    # Attempt via pymongo directly
    try:
        from motor.motor_asyncio import AsyncIOMotorClient  # noqa: F401
        import pymongo
        cli = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "test_database")]
        sub = db.newsletter_subscribers.find_one({"email": email})
        assert sub and sub.get("token"), "subscriber not persisted"
        token = sub["token"]
        r_ok = requests.get(f"{BASE}/api/newsletter/unsubscribe?token={token}", timeout=15)
        assert r_ok.status_code == 200
        assert "désabonné" in r_ok.text
    except ImportError:
        pytest.skip("pymongo not available")


def test_newsletter_rate_limit_429():
    # Same IP, 6 requests. Each with different (valid) email so first would be 200,
    # but the 6th should hit 429 regardless.
    codes = []
    for i in range(7):
        e = f"qa-rate-{_rand()}@construpilot-test.fr"
        r = requests.post(f"{BASE}/api/newsletter/subscribe",
                          json={"email": e, "lang": "fr"}, timeout=15)
        codes.append(r.status_code)
    # At least one 429 in the last few
    assert 429 in codes, f"no 429 seen, codes={codes}"


# ---------- (4) BabyLoveGrowth webhook + sitemap ----------
BLG_SLUG_1 = f"qa-blg-article-{_rand(6)}-1"
BLG_SLUG_2 = f"qa-blg-article-{_rand(6)}-2"
BLG_ID_1 = random.randint(900000, 999999)
BLG_ID_2 = random.randint(900000, 999999)


def _blg_payload(art_id, slug, title):
    return {
        "id": art_id,
        "title": title,
        "slug": slug,
        "content_html": "<h2>Intro</h2><p>" + ("Contenu " * 200) + "</p>",
        "meta_description": "Guide d'isolation thermique.",
        "languageCode": "fr",
        "seedKeyword": "isolation",
        "keywords": ["isolation", "thermique"],
        "faqJsonLd": {"mainEntity": [
            {"name": "Q?", "acceptedAnswer": {"text": "R."}},
        ]},
        "created_at": "2026-01-15T10:00:00Z",
    }


def test_blg_webhook_no_auth():
    r = requests.post(f"{BASE}/api/webhooks/babylovegrowth",
                      json=_blg_payload(BLG_ID_1, BLG_SLUG_1, "QA BLG 1"), timeout=15)
    assert r.status_code == 401


def test_blg_webhook_success():
    r = requests.post(f"{BASE}/api/webhooks/babylovegrowth",
                      headers={"Authorization": f"Bearer {BLG_SECRET}"},
                      json=_blg_payload(BLG_ID_1, BLG_SLUG_1, "QA BLG Article 1"),
                      timeout=30)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("ok") is True
    assert BLG_SLUG_1 in (body.get("url") or "")
    # article 2 for related-articles test
    r2 = requests.post(f"{BASE}/api/webhooks/babylovegrowth",
                       headers={"Authorization": f"Bearer {BLG_SECRET}"},
                       json=_blg_payload(BLG_ID_2, BLG_SLUG_2, "QA BLG Article 2"),
                       timeout=30)
    assert r2.status_code == 200


def test_blg_article_listed_in_autoseo():
    r = requests.get(f"{BASE}/api/blog/autoseo?lang=fr", timeout=15)
    assert r.status_code == 200
    arts = r.json().get("articles", [])
    slugs = [a.get("slug") for a in arts]
    assert BLG_SLUG_1 in slugs, f"{BLG_SLUG_1} not in {slugs[:20]}"
    a = next(x for x in arts if x["slug"] == BLG_SLUG_1)
    assert a.get("source") == "babylovegrowth"
    assert a.get("reading_minutes")


def test_blg_article_detail_faq_and_id():
    r = requests.get(f"{BASE}/api/blog/autoseo/{BLG_SLUG_1}", timeout=15)
    assert r.status_code == 200
    a = r.json()
    assert a.get("autoseo_id") == f"blg-{BLG_ID_1}"
    faq = a.get("faq_schema") or []
    assert len(faq) >= 1
    assert "question" in faq[0] and "answer" in faq[0]


def test_blog_sitemap_xml():
    r = requests.get(f"{BASE}/api/blog/sitemap.xml", timeout=15)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/xml")
    assert f"<loc>https://construpilot.fr/blog/{BLG_SLUG_1}</loc>" in r.text


def test_frontend_sitemap_index():
    r = requests.get(f"{BASE}/sitemap.xml", timeout=15)
    assert r.status_code == 200
    assert "sitemapindex" in r.text
    assert "/sitemap-pages.xml" in r.text
    assert "/api/blog/sitemap.xml" in r.text
    # both referenced sitemaps 200
    r1 = requests.get(f"{BASE}/sitemap-pages.xml", timeout=15)
    assert r1.status_code == 200
    r2 = requests.get(f"{BASE}/api/blog/sitemap.xml", timeout=15)
    assert r2.status_code == 200


def test_blg_admin_status(admin_h):
    r = requests.get(f"{BASE}/api/admin/babylovegrowth/status", headers=admin_h, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("configured") is True
    assert body.get("count", 0) >= 1
    recent_slugs = [a.get("slug") for a in body.get("recent", [])]
    assert BLG_SLUG_1 in recent_slugs


def test_blg_admin_sync(admin_h):
    r = requests.post(f"{BASE}/api/admin/babylovegrowth/sync", headers=admin_h, timeout=180)
    # Allow 502 if remote BLG API refuses (network); accept 200 with expected keys
    assert r.status_code in (200, 502), r.text[:300]
    if r.status_code == 200:
        body = r.json()
        for k in ("created", "skipped", "errors"):
            assert k in body


def test_blg_cleanup(admin_h):
    r1 = requests.delete(f"{BASE}/api/admin/babylovegrowth/articles/{BLG_SLUG_1}",
                         headers=admin_h, timeout=15)
    assert r1.status_code == 200
    assert r1.json().get("deleted") == 1
    r2 = requests.delete(f"{BASE}/api/admin/babylovegrowth/articles/{BLG_SLUG_2}",
                         headers=admin_h, timeout=15)
    assert r2.status_code == 200
    assert r2.json().get("deleted") == 1


# ---------- (5) Postal READ-ONLY ----------
def test_postal_status(pro_h):
    r = requests.get(f"{BASE}/api/radar/postal/status", headers=pro_h, timeout=15)
    assert r.status_code == 200
    assert r.json().get("configured") is True


def test_postal_price_suivi(pro_h):
    r = requests.get(f"{BASE}/api/radar/postal/price?mode=suivi", headers=pro_h, timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert (body.get("total_ttc") or 0) > 0


# ---------- Cleanup: newsletter subscribers ----------
def test_cleanup_newsletter_subscribers():
    try:
        import pymongo
        cli = pymongo.MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = cli[os.environ.get("DB_NAME", "test_database")]
        r = db.newsletter_subscribers.delete_many({"email": {"$regex": "^qa-"}})
        assert r.deleted_count >= 1
    except ImportError:
        pytest.skip("pymongo not available")
