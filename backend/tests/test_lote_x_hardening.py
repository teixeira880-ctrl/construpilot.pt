"""Tests do Lote X — hardening (SEC-X-001, SEC-X-002, SEC-X-003)."""
import os
import io
from pathlib import Path
from fastapi import UploadFile, HTTPException
import pytest

# Garante PYTHONPATH para core.*
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.uploads import (
    validate_upload, sanitize_filename, ALLOWED_IMAGE, ALLOWED_DOCUMENT
)


def _mk_upload(filename: str, ctype: str, size_bytes: int) -> UploadFile:
    data = b"X" * size_bytes
    f = io.BytesIO(data)
    up = UploadFile(filename=filename, file=f)
    up.headers = {"content-type": ctype}
    # Força content_type reconhecido pelo FastAPI (atributo público)
    object.__setattr__(up, "_content_type", ctype)
    return up


def test_sanitize_filename_removes_path_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/absolute/path/foo.pdf") == "foo.pdf"
    assert sanitize_filename("file with spaces & stuff.pdf") == "file_with_spaces___stuff.pdf"
    assert sanitize_filename("") == "ficheiro"
    assert sanitize_filename(None) == "ficheiro"
    long_name = "a" * 500 + ".txt"
    assert len(sanitize_filename(long_name)) <= 120


@pytest.mark.asyncio
async def test_validate_upload_accepts_png():
    up = _mk_upload("foto.png", "image/png", 1024)
    out = await validate_upload(up, ALLOWED_IMAGE)
    assert out.filename == "foto.png"


@pytest.mark.asyncio
async def test_validate_upload_rejects_exe():
    up = _mk_upload("malware.exe", "application/x-msdownload", 1024)
    with pytest.raises(HTTPException) as exc:
        await validate_upload(up, ALLOWED_IMAGE)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_upload_rejects_oversized():
    big = 25 * 1024 * 1024  # 25 MB > default 20 MB
    up = _mk_upload("huge.pdf", "application/pdf", big)
    with pytest.raises(HTTPException) as exc:
        await validate_upload(up, ALLOWED_DOCUMENT, max_mb=20)
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_validate_upload_sanitizes_path_traversal_filename():
    up = _mk_upload("../../etc/passwd", "application/pdf", 500)
    out = await validate_upload(up, ALLOWED_DOCUMENT)
    assert out.filename == "passwd"


@pytest.mark.asyncio
async def test_validate_upload_respects_max_mb_env(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    up = _mk_upload("doc.pdf", "application/pdf", 2 * 1024 * 1024)
    with pytest.raises(HTTPException) as exc:
        await validate_upload(up, ALLOWED_DOCUMENT)
    assert exc.value.status_code == 413


# ──────────────────────────────────────────────────────────────
# X.1 / X.2 — verificação estática do código (sem subir servidor)
# ──────────────────────────────────────────────────────────────

SERVER_SRC = (ROOT / "server.py").read_text()


def test_x1_second_admin_no_hardcoded_fallback():
    """Fallback 'CP-Admin-2026!' foi removido do código."""
    assert "CP-Admin-2026!" not in SERVER_SRC, \
        "Fallback hardcoded ainda presente em server.py"


def test_x1_second_admin_fail_closed_log_present():
    """Log informativo PT-PT presente quando SECOND_ADMIN_PASSWORD vazio."""
    assert "SECOND_ADMIN_PASSWORD não definida" in SERVER_SRC


def test_x2_provision_accounts_gated_by_seed_demo_data():
    """provision_accounts() só corre com SEED_DEMO_DATA=true."""
    # Deve existir uma linha que condiciona provision_accounts por SEED_DEMO_DATA.
    assert "SEED_DEMO_DATA" in SERVER_SRC
    assert "provision_accounts" in SERVER_SRC
    # A chamada a provision_accounts tem de estar depois da leitura da env var
    idx_env = SERVER_SRC.find('SEED_DEMO_DATA", "false"')
    idx_call = SERVER_SRC.find("await provision_accounts(")
    assert idx_env > 0 and idx_call > 0 and idx_env < idx_call, \
        "provision_accounts não está sob guard SEED_DEMO_DATA"


def test_x2_seed_log_portuguese():
    assert "Seed de contas de demonstração" in SERVER_SRC
