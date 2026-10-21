"""Iter162 backend regressions: assistant attachments, private previews, and validation guards."""

import io
import os
import sys
import uuid
from pathlib import Path

import pytest
import requests
from PIL import Image, ImageDraw
from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from engines.assistant_files import image_requested


BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
PRO_EMAIL = os.environ.get("TEST_PRO_EMAIL")
PRO_PASSWORD = os.environ.get("TEST_PRO_PASSWORD")
ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD")


def _require_env():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL missing")
    if not (PRO_EMAIL and PRO_PASSWORD and ADMIN_EMAIL and ADMIN_PASSWORD):
        pytest.skip("TEST_PRO/TEST_ADMIN credentials missing in environment")


def _login(email: str, password: str) -> dict:
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=40,
    )
    assert response.status_code == 200, response.text
    token = response.json().get("token")
    assert token and isinstance(token, str)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def sessions():
    _require_env()
    return {
        "pro": _login(PRO_EMAIL, PRO_PASSWORD),
        "admin": _login(ADMIN_EMAIL, ADMIN_PASSWORD),
    }


@pytest.fixture
def created_docs(sessions):
    docs = []
    yield docs
    for doc_id in docs:
        requests.delete(f"{BASE_URL}/api/assistant/documents/{doc_id}", headers=sessions["pro"], timeout=30)


def _synthetic_fixture_png() -> bytes:
    img = Image.new("RGB", (1200, 900), "#f5f5f5")
    draw = ImageDraw.Draw(img)
    draw.polygon([(120, 760), (530, 760), (530, 220), (180, 220)], fill="#8d3f2f")
    draw.polygon([(650, 760), (1080, 760), (1020, 220), (650, 220)], fill="#2f5f8d")
    draw.rectangle((540, 260, 640, 740), fill="#f5f5f5")
    draw.text((30, 24), "TEST_ITER162_VISUAL_CODE_A9K7", fill="#111111")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _upload_doc(headers: dict, filename: str, data: bytes, mime: str):
    response = requests.post(
        f"{BASE_URL}/api/assistant/documents",
        headers=headers,
        files={"file": (filename, data, mime)},
        timeout=60,
    )
    return response


def test_photo_upload_and_private_preview_jpeg_bytes(sessions, created_docs):
    upload = _upload_doc(sessions["pro"], "TEST_ITER162_fixture.png", _synthetic_fixture_png(), "image/png")
    assert upload.status_code == 200, upload.text
    payload = upload.json()
    assert payload["doc_id"].startswith("doc_")
    assert payload["mime"] == "image/jpeg"
    assert payload["kind"] == "photo"
    created_docs.append(payload["doc_id"])

    preview = requests.get(
        f"{BASE_URL}/api/assistant/documents/{payload['doc_id']}/preview",
        headers=sessions["pro"],
        timeout=40,
    )
    assert preview.status_code == 200, preview.text
    assert preview.headers.get("content-type", "").startswith("image/jpeg")
    assert preview.content[:3] == b"\xff\xd8\xff"


def test_other_user_cannot_access_private_preview(sessions, created_docs):
    upload = _upload_doc(sessions["pro"], "TEST_ITER162_private.png", _synthetic_fixture_png(), "image/png")
    assert upload.status_code == 200, upload.text
    doc_id = upload.json()["doc_id"]
    created_docs.append(doc_id)

    forbidden = requests.get(
        f"{BASE_URL}/api/assistant/documents/{doc_id}/preview",
        headers=sessions["admin"],
        timeout=40,
    )
    assert forbidden.status_code == 404


def test_blank_uniform_image_rejected(sessions):
    image = Image.new("RGB", (1024, 1024), "white")
    out = io.BytesIO()
    image.save(out, format="PNG")
    response = _upload_doc(sessions["pro"], "TEST_ITER162_blank.png", out.getvalue(), "image/png")
    assert response.status_code == 415
    assert "Image illisible" in response.json().get("detail", "")


def test_spoofed_jpg_content_rejected(sessions):
    response = _upload_doc(sessions["pro"], "TEST_ITER162_spoof.jpg", b"not-an-image", "image/jpeg")
    assert response.status_code == 415
    assert "Image illisible" in response.json().get("detail", "")


def test_too_many_pixels_rejected(sessions):
    # 48 MP > 40 MP guardrail
    image = Image.new("RGB", (8000, 6000), "#334455")
    out = io.BytesIO()
    image.save(out, format="PNG")
    response = _upload_doc(sessions["pro"], "TEST_ITER162_48mp.png", out.getvalue(), "image/png")
    assert response.status_code == 415
    assert "40 mégapixels" in response.json().get("detail", "")


def test_file_over_20mb_rejected_before_processing(sessions):
    huge = b"a" * (20 * 1024 * 1024 + 16)
    response = _upload_doc(sessions["pro"], "TEST_ITER162_large.pdf", huge, "application/pdf")
    assert response.status_code == 413
    assert "> 20 Mo" in response.json().get("detail", "")


def test_pdf_upload_and_preview_first_page(sessions, created_docs):
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_blank_page(width=595, height=842)
    out = io.BytesIO()
    writer.write(out)
    response = _upload_doc(sessions["pro"], "TEST_ITER162_pages.pdf", out.getvalue(), "application/pdf")
    assert response.status_code == 200, response.text
    payload = response.json()
    created_docs.append(payload["doc_id"])
    assert payload["mime"] == "application/pdf"
    assert payload["pages"] == 2

    preview = requests.get(
        f"{BASE_URL}/api/assistant/documents/{payload['doc_id']}/preview",
        headers=sessions["pro"],
        timeout=40,
    )
    assert preview.status_code == 200, preview.text
    assert preview.content[:3] == b"\xff\xd8\xff"


def test_image_requested_positive_and_negative_prompts():
    assert image_requested("Crée un JPG technique de cette solution") is True
    assert image_requested("please generate an image for this") is True
    assert image_requested("sans image, analyse seulement") is False
    assert image_requested("do not generate image; just analyse") is False


def test_jobs_submit_dedup_and_payload_conflict(sessions):
    conversation = requests.post(
        f"{BASE_URL}/api/assistant/conversations",
        headers=sessions["pro"],
        json={},
        timeout=30,
    )
    assert conversation.status_code == 200, conversation.text
    conv_id = conversation.json()["conversation_id"]

    request_id = "TEST_ITER162_REQ_DEDUP_" + uuid.uuid4().hex
    payload = {
        "conversation_id": conv_id,
        "request_id": request_id,
        "text": "Réponds en une phrase concise.",
        "response_mode": "fast",
        "web_enabled": False,
        "plan_ids": [],
        "doc_ids": [],
        "attachments": [],
    }
    first = requests.post(f"{BASE_URL}/api/assistant/jobs", headers=sessions["pro"], json=payload, timeout=40)
    assert first.status_code == 202, first.text
    first_job = first.json()
    assert first_job["job_id"].startswith("ajob_")
    assert first_job["request_id"] == request_id

    second = requests.post(f"{BASE_URL}/api/assistant/jobs", headers=sessions["pro"], json=payload, timeout=40)
    assert second.status_code == 202, second.text
    second_job = second.json()
    assert second_job["job_id"] == first_job["job_id"]

    changed_payload = {**payload, "text": "Cette charge utile diffère."}
    conflict = requests.post(f"{BASE_URL}/api/assistant/jobs", headers=sessions["pro"], json=changed_payload, timeout=40)
    assert conflict.status_code == 409

    requests.post(f"{BASE_URL}/api/assistant/jobs/{first_job['job_id']}/cancel", headers=sessions["pro"], timeout=30)
