"""Iter178 backend tests — Growth SEO overrides, autopilot, ads, newsletters, admin OpenAI key.

Endpoints scope:
- Public: GET /api/growth/seo-overrides
- Admin: growth autopilot (settings/budget/runs), seo-overrides list & PUT approve/proposed,
  ads (list, csv google/meta, PUT approve, publish 409),
  newsletters (list, preview HTML, PUT subject),
  admin/ai-openai-key GET + reactivate 409,
  documents/from-text POST (pro).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@construpilot.fr"
ADMIN_PASSWORD = "Construpilot2026!"
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"

PROJECT = "growth_fr"
AD_ID = "ad_78ba506ddd11"
NL_ID = "nl_3c74aaa7a146"


def _login(email, password):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:200]}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token: {data}"
    return tok


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {_login(ADMIN_EMAIL, ADMIN_PASSWORD)}"}


@pytest.fixture(scope="module")
def pro_headers():
    return {"Authorization": f"Bearer {_login(PRO_EMAIL, PRO_PASSWORD)}"}


# --- Public SEO overrides ---
def test_public_seo_overrides_no_auth():
    r = requests.get(f"{API}/growth/seo-overrides", timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert "overrides" in data and isinstance(data["overrides"], dict)


# --- Autopilot state ---
def test_autopilot_state(admin_headers):
    r = requests.get(f"{API}/growth/projects/{PROJECT}/autopilot", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    for k in ("settings", "budget", "runs"):
        assert k in data, f"missing {k} in {list(data.keys())}"


# --- SEO overrides list + approve/reset ---
def test_seo_overrides_approve_then_reset(admin_headers):
    lst = requests.get(f"{API}/growth/projects/{PROJECT}/seo-overrides", headers=admin_headers, timeout=30)
    assert lst.status_code == 200, lst.text[:300]
    items = lst.json().get("items") or lst.json().get("overrides") or lst.json()
    if isinstance(items, dict):
        items = items.get("items", [])
    assert isinstance(items, list) and len(items) >= 1, f"no override proposals: {str(lst.json())[:300]}"
    # pick a proposed one
    proposed = [it for it in items if it.get("status") == "proposed"]
    target = proposed[0] if proposed else items[0]
    oid = target.get("override_id") or target.get("id") or target.get("_id")
    assert oid, f"no id in {target}"
    original_status = target.get("status", "proposed")
    original_title = target.get("title") or target.get("suggested_title") or "Test title"
    original_desc = target.get("description") or target.get("suggested_description") or "Test description"

    # Approve
    put = requests.put(
        f"{API}/growth/seo-overrides/{oid}",
        headers=admin_headers,
        json={"status": "approved", "title": original_title, "description": original_desc},
        timeout=30,
    )
    assert put.status_code == 200, f"approve failed {put.status_code}: {put.text[:300]}"
    result = put.json()
    assert (result.get("status") == "approved") or result.get("ok") is True, f"unexpected: {result}"

    # Public list should contain the path
    pub = requests.get(f"{API}/growth/seo-overrides", timeout=30).json().get("overrides", {})
    path = target.get("path") or target.get("url_path")
    if path:
        # loose match
        assert any(path in k or k in path for k in pub.keys()) or path in pub, (
            f"path {path} not in public overrides {list(pub.keys())[:10]}"
        )

    # Reset to proposed (if originally proposed) to avoid consuming
    if original_status == "proposed":
        r2 = requests.put(
            f"{API}/growth/seo-overrides/{oid}",
            headers=admin_headers,
            json={"status": "proposed"},
            timeout=30,
        )
        assert r2.status_code == 200, r2.text[:300]


# --- Ads listing + CSV + approve + publish 409 ---
def test_ads_list_and_connectors(admin_headers):
    r = requests.get(f"{API}/growth/projects/{PROJECT}/ads", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    ads = data.get("ads") or data.get("items") or []
    assert len(ads) >= 1
    ids = [a.get("ad_id") or a.get("id") for a in ads]
    assert AD_ID in ids, f"{AD_ID} not in {ids}"
    connectors = data.get("connectors", {})
    for platform in ("google", "meta"):
        c = connectors.get(platform, {})
        assert c.get("configured") is False, f"{platform} connector should be non configured: {c}"


def test_ads_csv_google(admin_headers):
    r = requests.get(f"{API}/growth/ads/{AD_ID}/export.csv", params={"platform": "google"}, headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    ct = r.headers.get("content-type", "")
    assert "text/csv" in ct, ct
    body = r.text
    assert "Campaign" in body and "Headline 1" in body and "Headline 15" in body
    assert "Description 1" in body and "Description 4" in body


def test_ads_csv_meta(admin_headers):
    r = requests.get(f"{API}/growth/ads/{AD_ID}/export.csv", params={"platform": "meta"}, headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert "text/csv" in r.headers.get("content-type", "")


def test_ads_approve_and_publish_409(admin_headers):
    r = requests.put(f"{API}/growth/ads/{AD_ID}", headers=admin_headers, json={"status": "approved"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    pub = requests.post(f"{API}/growth/ads/{AD_ID}/publish", headers=admin_headers, json={"platform": "google"}, timeout=30)
    assert pub.status_code == 409, f"expected 409 got {pub.status_code}: {pub.text[:200]}"


# --- Newsletters ---
def test_newsletters_list_preview_update(admin_headers):
    r = requests.get(f"{API}/growth/projects/{PROJECT}/newsletters", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data.get("newsletters") or data.get("items") or []
    assert len(items) >= 1
    assert any((n.get("newsletter_id") or n.get("id")) == NL_ID for n in items)
    # Preview
    prev = requests.get(f"{API}/growth/newsletters/{NL_ID}/preview", headers=admin_headers, timeout=30)
    assert prev.status_code == 200, prev.text[:300]
    txt = prev.text
    assert "<" in txt and (">" in txt), "preview should be HTML"
    # Update subject (safe)
    put = requests.put(f"{API}/growth/newsletters/{NL_ID}", headers=admin_headers, json={"subject": "Test objet"}, timeout=30)
    assert put.status_code == 200, put.text[:300]


# --- Admin OpenAI key ---
def test_admin_openai_key_state_and_reactivate(admin_headers):
    r = requests.get(f"{API}/admin/ai-openai-key", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    assert data.get("configured") is True
    assert data.get("active") is False
    assert data.get("disabled") is True
    rea = requests.post(f"{API}/admin/ai-openai-key/reactivate", headers=admin_headers, timeout=60)
    assert rea.status_code == 409, f"expected 409 got {rea.status_code}: {rea.text[:200]}"
    body = rea.text.lower()
    assert "openai" in body


# --- Autopilot run 409 or resume_only ---
def test_autopilot_run_resume_only(admin_headers):
    # Fetch current state to check if a run is already running
    st = requests.get(f"{API}/growth/projects/{PROJECT}/autopilot", headers=admin_headers, timeout=30).json()
    runs = st.get("runs") or []
    running = any(r.get("status") == "running" for r in runs)
    r = requests.post(
        f"{API}/growth/projects/{PROJECT}/autopilot/run",
        headers=admin_headers,
        json={"resume_only": True},
        timeout=60,
    )
    if running:
        assert r.status_code == 409, f"expected 409 while running, got {r.status_code}: {r.text[:200]}"
    else:
        assert r.status_code in (200, 202), r.text[:300]
        j = r.json()
        assert j.get("started") is True or j.get("ok") is True


# --- documents/from-text (pro) — costly, keep last ---
@pytest.mark.slow
def test_documents_from_text_pro(pro_headers):
    payload = {"text": "Créer un devis peinture 40 m² deux couches", "images": []}
    r = requests.post(f"{API}/documents/from-text", headers=pro_headers, json=payload, timeout=120)
    assert r.status_code == 200, r.text[:400]
    data = r.json()
    assert data.get("doc_id"), f"no doc_id: {data}"
    assert isinstance(data.get("lines"), list) and len(data["lines"]) >= 1
