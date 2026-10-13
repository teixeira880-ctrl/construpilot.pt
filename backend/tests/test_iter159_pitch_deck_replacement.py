"""Iter159 — investor pitch deck replacement regression (public API + lead logging)."""

from __future__ import annotations

import hashlib
import io
import os
import re
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
import requests
from PIL import Image, ImageStat
from pypdf import PdfReader


def _base_url() -> str:
    env = os.environ.get("REACT_APP_BACKEND_URL")
    if env:
        return env.rstrip("/")
    frontend_env = Path("/app/frontend/.env")
    if frontend_env.exists():
        for line in frontend_env.read_text(encoding="utf-8").splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                value = line.split("=", 1)[1].strip()
                if value:
                    return value.rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL missing")


BASE_URL = _base_url()
EXPECTED_PPTX_SHA = "81274306e33f55fa7e3577b71eabcbac66290de648577cda4171b4c9cc60f7c9"


def _admin_creds() -> tuple[str, str]:
    from dotenv import dotenv_values

    env = {**dotenv_values("/app/backend/.env"), **os.environ}
    return env["TEST_ADMIN_EMAIL"], env["TEST_ADMIN_PASSWORD"]


def _login_admin_token() -> str:
    email, pwd = _admin_creds()
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": pwd},
        timeout=30,
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login unavailable ({response.status_code})")
    token = response.json().get("token") or response.json().get("access_token")
    if not token:
        pytest.skip("Admin token missing")
    return token


@pytest.fixture(scope="module")
def created_test_tag() -> str:
    return f"TEST_ITER159_{uuid4().hex[:8]}"


@pytest.fixture(scope="module", autouse=True)
def cleanup_iter159_deck_leads(created_test_tag):
    # deck_downloads cleanup for TEST_ITER159-only records created by this suite
    yield
    from dotenv import dotenv_values
    from pymongo import MongoClient

    env = dotenv_values("/app/backend/.env")
    with MongoClient(env["MONGO_URL"]) as client:
        client[env["DB_NAME"]].deck_downloads.delete_many(
            {
                "$or": [
                    {"name": {"$regex": f"^{re.escape(created_test_tag)}"}},
                    {"fund": {"$regex": f"^{re.escape(created_test_tag)}"}},
                    {"email": {"$regex": f"^{re.escape(created_test_tag.lower())}"}},
                ]
            }
        )


# metadata/public contract
def test_pitch_deck_metadata_contract_no_internal_paths():
    response = requests.get(f"{BASE_URL}/api/investors/pitch-deck", timeout=30)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["source_filename"] == "ConstruPilot_PitchDeck.pptx"
    assert data["source_sha256"] == EXPECTED_PPTX_SHA
    assert data["page_count"] == 19
    assert data["width"] == 1920
    assert data["height"] == 1080
    assert "path" not in str(data).lower()
    assert "assets/investors" not in str(data).lower()


# binary package checks (PPTX/PDF)
def test_pitch_deck_pptx_get_integrity_and_slide_count():
    response = requests.get(f"{BASE_URL}/api/investors/pitch-deck.pptx", timeout=40)
    assert response.status_code == 200, response.text
    assert response.headers.get("content-type", "").startswith(
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
    assert response.headers.get("etag") == f'"{EXPECTED_PPTX_SHA}"'
    assert len(response.content) == 181220

    sha = hashlib.sha256(response.content).hexdigest()
    assert sha == EXPECTED_PPTX_SHA

    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        names = zf.namelist()
        slide_xml = [name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml")]
        assert len(slide_xml) == 19


def test_pitch_deck_pdf_head_get_and_text_markers():
    head = requests.head(f"{BASE_URL}/api/investors/pitch-deck.pdf", timeout=30)
    assert head.status_code == 200
    assert head.headers.get("content-type", "").startswith("application/pdf")
    assert "etag" in head.headers

    response = requests.get(f"{BASE_URL}/api/investors/pitch-deck.pdf", timeout=40)
    assert response.status_code == 200
    assert len(response.content) == 306489
    disposition = response.headers.get("content-disposition", "").lower()
    assert "construpilot_pitchdeck.pdf" in disposition

    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 19
    joined = "\n".join((page.extract_text() or "") for page in reader.pages)
    assert "149" in joined
    assert "249" in joined


# slide rendering API checks
@pytest.mark.parametrize("page", list(range(1, 20)))
def test_pitch_deck_slide_routes_all_pages_ok(page: int):
    response = requests.get(f"{BASE_URL}/api/investors/pitch-deck/slides/{page}.webp", timeout=30)
    assert response.status_code == 200, f"slide {page}: {response.status_code}"
    assert response.headers.get("content-type", "").startswith("image/webp")
    assert "etag" in response.headers
    assert len(response.content) > 2000


@pytest.mark.parametrize("path", ["0", "20", "-1", "abc"])
def test_pitch_deck_slide_invalid_paths_rejected(path: str):
    response = requests.get(f"{BASE_URL}/api/investors/pitch-deck/slides/{path}.webp", timeout=30)
    assert response.status_code == 422


def test_pitch_deck_all_slide_dimensions_nonblank():
    for page in range(1, 20):
        response = requests.get(f"{BASE_URL}/api/investors/pitch-deck/slides/{page}.webp", timeout=30)
        assert response.status_code == 200
        img = Image.open(io.BytesIO(response.content)).convert("RGB")
        assert img.size == (1920, 1080), f"slide {page} unexpected size {img.size}"
        stat = ImageStat.Stat(img)
        assert max(stat.stddev) > 2.0
        assert response.headers["etag"] == f'"{hashlib.sha256(response.content).hexdigest()}"'


# lead logging + admin CSV contract
def test_deck_request_logs_once_and_csv_reflects_trim_and_lowercase(created_test_tag):
    payload = {
        "name": f"  {created_test_tag} Name  ",
        "email": f"  {created_test_tag}@Example.COM  ",
        "fund": f"  {created_test_tag} FUND  ",
        "note": "iter159 investor flow",
    }
    response = requests.post(f"{BASE_URL}/api/investors/deck-request", json=payload, timeout=30)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True
    assert body["download_url"] == "/api/investors/pitch-deck.pdf"
    assert body["powerpoint_url"] == "/api/investors/pitch-deck.pptx"

    token = _login_admin_token()
    csv_response = requests.get(
        f"{BASE_URL}/api/investors/deck-requests.csv",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    assert csv_response.status_code == 200, csv_response.text
    assert csv_response.headers.get("content-type", "").startswith("text/csv")

    csv_text = csv_response.content.decode("utf-8-sig", errors="replace")
    needle = f"{created_test_tag} Name"
    rows = [line for line in csv_text.splitlines() if needle in line]
    assert len(rows) == 1
    row = rows[0]
    assert f"{created_test_tag.lower()}@example.com" in row
    assert f"{created_test_tag} FUND" in row


def test_deck_requests_csv_requires_admin_auth():
    response = requests.get(f"{BASE_URL}/api/investors/deck-requests.csv", timeout=30)
    assert response.status_code in (401, 403)
