"""Iter147 live regression checks: assistant web guard, CAD upload/reextract, PDF multipage upload."""

import io
import os
import tempfile

import ezdxf
import pytest
import requests
from PIL import Image
from pypdf import PdfReader, PdfWriter


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
PRO_EMAIL = "pro@construpilot.fr"
PRO_PASSWORD = "Pro2026!"


def _auth_headers() -> dict:
    assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": PRO_EMAIL, "password": PRO_PASSWORD},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    token = resp.json().get("token")
    assert token
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def ctx():
    headers = _auth_headers()
    created_plan_ids: list[str] = []
    yield {"headers": headers, "created_plan_ids": created_plan_ids}
    for plan_id in created_plan_ids:
        requests.delete(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=30)


def _create_conv(headers: dict) -> str:
    r = requests.post(f"{BASE_URL}/api/assistant/conversations", json={}, headers=headers, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["conversation_id"]


def _create_unitless_dxf_bytes() -> bytes:
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 0
    msp = doc.modelspace()
    msp.add_line((0, 0), (1000, 0))
    buff = io.StringIO()
    doc.write(buff)
    return buff.getvalue().encode("utf-8", errors="ignore")


def test_assistant_web_generic_topic_uses_sources_and_no_confidential_leak(ctx):
    headers = ctx["headers"]
    conv_id = _create_conv(headers)
    marker = "ITER147_SECRET_COMPANY"
    payload = {
        "conversation_id": conv_id,
        "text": (
            f"Recherche internet urbanisme. Ne cherche pas sur {marker}, 12 rue privée, "
            "mais donne des sources officielles techniques."
        ),
        "response_mode": "fast",
        "web_enabled": True,
        "plan_ids": [],
        "doc_ids": [],
        "attachments": [],
    }
    r = requests.post(f"{BASE_URL}/api/assistant/message", json=payload, headers=headers, timeout=120)
    assert r.status_code == 200, r.text
    body = r.json()
    actions = body.get("actions") or []
    web_action = next((a for a in actions if a.get("tool") == "search_technical_web"), None)
    assert web_action is not None, body
    result = web_action.get("result") or {}
    assert result.get("ok") is True
    assert result.get("sources"), result
    assert marker.lower() not in (result.get("query") or "").lower()


def test_assistant_web_disabled_blocks_tool_invocation(ctx):
    headers = ctx["headers"]
    put = requests.put(
        f"{BASE_URL}/api/assistant/settings",
        json={"learning_mode": "suggest", "web_enabled": False},
        headers=headers,
        timeout=30,
    )
    assert put.status_code == 200, put.text
    conv_id = _create_conv(headers)
    r = requests.post(
        f"{BASE_URL}/api/assistant/message",
        json={
            "conversation_id": conv_id,
            "text": "Fais une recherche internet urbanisme.",
            "response_mode": "fast",
            "web_enabled": True,
            "plan_ids": [],
            "doc_ids": [],
            "attachments": [],
        },
        headers=headers,
        timeout=90,
    )
    assert r.status_code == 200, r.text
    actions = r.json().get("actions") or []
    assert all(a.get("tool") != "search_technical_web" for a in actions)
    requests.put(
        f"{BASE_URL}/api/assistant/settings",
        json={"learning_mode": "suggest", "web_enabled": True},
        headers=headers,
        timeout=30,
    )


def test_cad_unit_required_then_retry_mm_and_reextract_after_duplicate(ctx):
    headers = ctx["headers"]
    dxf_bytes = _create_unitless_dxf_bytes()
    files = {"file": ("ITER147_unitless.dxf", dxf_bytes, "image/vnd.dxf")}
    r0 = requests.post(f"{BASE_URL}/api/takeoffs/upload", headers=headers, files=files, timeout=60)
    assert r0.status_code == 422
    assert "CAD_UNIT_REQUIRED" in str(r0.json().get("detail"))

    r1 = requests.post(
        f"{BASE_URL}/api/takeoffs/upload",
        headers=headers,
        files=files,
        data={"cad_unit": "mm"},
        timeout=120,
    )
    assert r1.status_code == 200, r1.text
    plan_id = r1.json()["plan_id"]
    ctx["created_plan_ids"].append(plan_id)

    gp = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=30)
    assert gp.status_code == 200, gp.text
    cad_units = (((gp.json() or {}).get("cad_import") or {}).get("units") or {})
    assert cad_units.get("name") == "mm"
    assert cad_units.get("source") == "user"

    dup = requests.post(f"{BASE_URL}/api/takeoffs/{plan_id}/duplicate", headers=headers, timeout=60)
    assert dup.status_code == 200, dup.text
    clone_id = dup.json()["plan_id"]
    ctx["created_plan_ids"].append(clone_id)

    deleted = requests.delete(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=30)
    assert deleted.status_code == 200
    ctx["created_plan_ids"].remove(plan_id)

    original_get = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=30)
    assert original_get.status_code == 404
    clone_get = requests.get(f"{BASE_URL}/api/takeoffs/{clone_id}", headers=headers, timeout=30)
    assert clone_get.status_code == 200

    reextract = requests.post(f"{BASE_URL}/api/takeoffs/{clone_id}/cotes/reextract", headers=headers, timeout=120)
    assert reextract.status_code == 200, reextract.text
    assert reextract.json().get("pages")


def test_public_dwg_upload_real_conversion(ctx):
    headers = ctx["headers"]
    path = "/app/integration/revision3/fixtures/public-line-2013.dwg"
    with open(path, "rb") as fh:
        files = {"file": ("ITER147_public-line-2013.dwg", fh, "application/acad")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", headers=headers, files=files, timeout=180)
    assert r.status_code == 200, r.text
    plan_id = r.json()["plan_id"]
    ctx["created_plan_ids"].append(plan_id)
    gp = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}", headers=headers, timeout=30)
    assert gp.status_code == 200
    cad = (gp.json() or {}).get("cad_import") or {}
    assert (cad.get("units") or {}).get("name") == "mm"
    assert ((cad.get("entity_counts") or {}).get("LINE") or 0) >= 1


def test_pdf_multipage_upload_rotation_fixture(ctx):
    headers = ctx["headers"]
    src = "/app/backend/tests/fixtures/houilles_plan.pdf"
    out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    out.close()
    reader = PdfReader(src)
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    page2 = reader.pages[1] if len(reader.pages) > 1 else reader.pages[0]
    page2.rotate(90)
    writer.add_page(page2)
    with open(out.name, "wb") as f:
        writer.write(f)

    with open(out.name, "rb") as fh:
        files = {"file": ("ITER147_houilles_2p_rotated.pdf", fh, "application/pdf")}
        r = requests.post(f"{BASE_URL}/api/takeoffs/upload", headers=headers, files=files, timeout=180)

    assert r.status_code == 200, r.text
    data = r.json()
    plan_id = data["plan_id"]
    ctx["created_plan_ids"].append(plan_id)
    assert data.get("page_count") == 2

    page = requests.get(f"{BASE_URL}/api/takeoffs/{plan_id}/page/1", headers=headers, timeout=30)
    assert page.status_code == 200, page.text
    assert page.json().get("image_png_b64")


def test_image_upload_duplicate_and_original_delete_keeps_clone(ctx):
    headers = ctx["headers"]
    buf = io.BytesIO()
    Image.new("RGB", (180, 120), color=(220, 220, 220)).save(buf, format="PNG")
    png_bytes = buf.getvalue()
    files = {"file": ("ITER147_plan_image.png", png_bytes, "image/png")}
    uploaded = requests.post(f"{BASE_URL}/api/takeoffs/upload", headers=headers, files=files, timeout=120)
    assert uploaded.status_code == 200, uploaded.text
    original = uploaded.json()["plan_id"]
    ctx["created_plan_ids"].append(original)
    assert uploaded.json().get("kind") == "image"

    dup = requests.post(f"{BASE_URL}/api/takeoffs/{original}/duplicate", headers=headers, timeout=60)
    assert dup.status_code == 200, dup.text
    clone = dup.json()["plan_id"]
    ctx["created_plan_ids"].append(clone)

    deleted = requests.delete(f"{BASE_URL}/api/takeoffs/{original}", headers=headers, timeout=30)
    assert deleted.status_code == 200
    ctx["created_plan_ids"].remove(original)

    clone_page = requests.get(f"{BASE_URL}/api/takeoffs/{clone}/page/0", headers=headers, timeout=30)
    assert clone_page.status_code == 200, clone_page.text
    assert clone_page.json().get("image_png_b64")
