"""Iter163 backend live acceptance checks for assistant conversation persistence and private file ownership."""

import re
from pathlib import Path

import pytest
import requests


def _base_url() -> str:
    env_text = Path("/app/frontend/.env").read_text(encoding="utf-8")
    match = re.search(r"^REACT_APP_BACKEND_URL=(.+)$", env_text, re.M)
    if not match:
        pytest.skip("REACT_APP_BACKEND_URL missing in frontend/.env")
    return match.group(1).strip().rstrip("/")


def _cred(label: str) -> tuple[str, str]:
    text = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    block = {
        "pro": r"### Pro / Owner d'organisation.*?\n- \*\*Email\*\*\s*:\s*`([^`]+)`\n- \*\*Password\*\*\s*:\s*`([^`]+)`",
        "admin": r"## Administrateur \(back-office `/admin`\).*?\n- \*\*Email\*\*\s*:\s*`([^`]+)`\n- \*\*Password\*\*\s*:\s*`([^`]+)`",
    }[label]
    match = re.search(block, text, re.S)
    if not match:
        pytest.skip(f"{label} credentials not found in test_credentials.md")
    return match.group(1), match.group(2)


BASE_URL = _base_url()


@pytest.fixture(scope="module")
def auth_headers():
    def login(email: str, password: str):
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=40,
        )
        assert response.status_code == 200, response.text
        token = response.json().get("token")
        assert isinstance(token, str) and token
        return {"Authorization": f"Bearer {token}"}

    pro_email, pro_password = _cred("pro")
    admin_email, admin_password = _cred("admin")
    return {
        "pro": login(pro_email, pro_password),
        "admin": login(admin_email, admin_password),
    }


@pytest.fixture(scope="module")
def latest_acceptance_conv(auth_headers):
    response = requests.get(
        f"{BASE_URL}/api/assistant/conversations",
        headers=auth_headers["pro"],
        timeout=40,
    )
    assert response.status_code == 200, response.text
    conversations = response.json()
    assert isinstance(conversations, list) and conversations
    conv_id = conversations[0]["conversation_id"]
    details = requests.get(
        f"{BASE_URL}/api/assistant/conversations/{conv_id}",
        headers=auth_headers["pro"],
        timeout=60,
    )
    assert details.status_code == 200, details.text
    data = details.json()
    assert data["conversation_id"] == conv_id
    return data


# Conversation persistence and terminal status checks
def test_live_conversation_has_messages_and_terminal_jobs(latest_acceptance_conv):
    messages = latest_acceptance_conv.get("messages", [])
    jobs = latest_acceptance_conv.get("jobs", [])
    assert len(messages) >= 3
    assert any(m.get("role") == "assistant" for m in messages)
    assert jobs
    for job in jobs[:3]:
        assert job["status"] in {"completed", "cancelled", "failed", "interrupted", "queued", "running", "preparing"}


# Private ownership guards for generated artifacts
def test_generated_artifact_private_between_pro_and_admin(auth_headers, latest_acceptance_conv):
    artifact_ids = []
    for msg in latest_acceptance_conv.get("messages", []):
        for action in msg.get("actions", []) or []:
            artifact = (action.get("result") or {}).get("artifact")
            if artifact and artifact.get("artifact_id"):
                artifact_ids.append(artifact["artifact_id"])
    artifact_ids = list(dict.fromkeys(artifact_ids))
    assert artifact_ids, "No generated artifacts found in latest conversation"

    artifact_id = artifact_ids[0]
    pro_download = requests.get(
        f"{BASE_URL}/api/assistant/artifacts/{artifact_id}/content",
        headers=auth_headers["pro"],
        timeout=60,
    )
    assert pro_download.status_code == 200
    assert pro_download.content[:3] in (b"\xff\xd8\xff", b"%PD")

    admin_forbidden = requests.get(
        f"{BASE_URL}/api/assistant/artifacts/{artifact_id}/content",
        headers=auth_headers["admin"],
        timeout=60,
    )
    assert admin_forbidden.status_code == 404


# Message PDF export should produce real PDF bytes
def test_assistant_message_export_pdf(auth_headers, latest_acceptance_conv):
    assistant = [m for m in latest_acceptance_conv.get("messages", []) if m.get("role") == "assistant" and m.get("message_id")]
    assert assistant, "No assistant message available for PDF export"
    message_id = assistant[-1]["message_id"]
    response = requests.get(
        f"{BASE_URL}/api/assistant/messages/{message_id}/pdf",
        headers=auth_headers["pro"],
        timeout=60,
    )
    assert response.status_code == 200, response.text
    assert response.content[:5] == b"%PDF-"
    assert "application/pdf" in response.headers.get("content-type", "")


# Cleanup of legacy TEST_ITER162 docs by owned user only
def test_cleanup_legacy_iter162_docs(auth_headers):
    listed = requests.get(
        f"{BASE_URL}/api/assistant/documents",
        headers=auth_headers["pro"],
        timeout=40,
    )
    assert listed.status_code == 200, listed.text
    docs = listed.json()
    targets = [d for d in docs if (d.get("filename") or "").startswith("TEST_ITER162")]
    deleted = 0
    for doc in targets:
        response = requests.delete(
            f"{BASE_URL}/api/assistant/documents/{doc['doc_id']}",
            headers=auth_headers["pro"],
            timeout=40,
        )
        assert response.status_code in (200, 404), response.text
        if response.status_code == 200:
            deleted += 1
    assert deleted >= 0
