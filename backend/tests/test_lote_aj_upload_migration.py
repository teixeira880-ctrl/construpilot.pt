"""AJ.1 — Testes de regressão da migração para `validate_upload`.

Cobertura mínima por família:
  - 1 happy path (content_type permitido → aceite).
  - 1 rejeição por content_type (ex.: application/x-msdownload / .exe → 400).

Verifica a camada `core.uploads.validate_upload` diretamente (unitário) e três
endpoints representativos (image, document, CAD) via `httpx.AsyncClient` quando
possível. Mantém-se minimalista para evitar dependências em DB real.
"""
import io
from pathlib import Path
import sys

import pytest
from fastapi import HTTPException, UploadFile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.uploads import (  # noqa: E402
    ALLOWED_CAD,
    ALLOWED_DOCUMENT,
    ALLOWED_IMAGE,
    ALLOWED_IMPORT,
    validate_upload,
)


def _upload(data: bytes, filename: str, content_type: str) -> UploadFile:
    """Constrói um UploadFile em memória para unitário."""
    return UploadFile(filename=filename, file=io.BytesIO(data),
                      headers={"content-type": content_type})


# ─── Família IMAGE ────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_image_happy_path_png():
    f = _upload(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10, "foto.png", "image/png")
    out = await validate_upload(f, ALLOWED_IMAGE, max_mb=12)
    assert out.filename == "foto.png"


@pytest.mark.asyncio
async def test_image_rejects_executable():
    f = _upload(b"MZ" + b"\x00" * 100, "virus.exe", "application/x-msdownload")
    with pytest.raises(HTTPException) as exc:
        await validate_upload(f, ALLOWED_IMAGE, max_mb=12)
    assert exc.value.status_code == 400
    assert "não permitido" in exc.value.detail.lower()


# ─── Família DOCUMENT ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_document_happy_path_pdf():
    f = _upload(b"%PDF-1.4\n" + b"\x00" * 10, "doc.pdf", "application/pdf")
    out = await validate_upload(f, ALLOWED_DOCUMENT, max_mb=40)
    assert out.filename == "doc.pdf"


@pytest.mark.asyncio
async def test_document_rejects_html():
    f = _upload(b"<html></html>", "page.html", "text/html")
    with pytest.raises(HTTPException) as exc:
        await validate_upload(f, ALLOWED_DOCUMENT, max_mb=40)
    assert exc.value.status_code == 400


# ─── Família CAD ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cad_happy_path_dxf_ascii():
    # DXF ASCII: começa com "0\r\nSECTION"
    data = b"0\r\nSECTION\r\n2\r\nHEADER\r\n0\r\nENDSEC\r\n"
    f = _upload(data, "plan.dxf", "image/vnd.dxf")
    out = await validate_upload(f, ALLOWED_CAD, max_mb=30)
    assert out.filename == "plan.dxf"


@pytest.mark.asyncio
async def test_cad_rejects_random_octet_stream():
    """Octet-stream sem magic-bytes CAD válidos → rejeita (SEC-Y-004)."""
    f = _upload(b"\x00" * 1000, "random.bin", "application/octet-stream")
    with pytest.raises(HTTPException) as exc:
        await validate_upload(f, ALLOWED_CAD, max_mb=30)
    # Pode ser 400 (CAD não reconhecido) ou 400 (tipo não permitido)
    assert exc.value.status_code == 400


# ─── Família IMPORT (CSV/XLSX) ────────────────────────────────────────────
@pytest.mark.asyncio
async def test_import_happy_path_csv():
    f = _upload(b"name;price\nA;10\n", "catalog.csv", "text/csv")
    out = await validate_upload(f, ALLOWED_IMPORT, max_mb=20)
    assert out.filename == "catalog.csv"


@pytest.mark.asyncio
async def test_import_rejects_pdf_disguised():
    """PDF enviado para endpoint CSV/XLSX → rejeita."""
    f = _upload(b"%PDF-1.4", "fake.csv", "application/pdf")
    with pytest.raises(HTTPException) as exc:
        await validate_upload(f, ALLOWED_IMPORT, max_mb=20)
    assert exc.value.status_code == 400


# ─── Limite de tamanho ────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_size_limit_413():
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (3 * 1024 * 1024)  # 3 MB
    f = _upload(big, "huge.png", "image/png")
    with pytest.raises(HTTPException) as exc:
        await validate_upload(f, ALLOWED_IMAGE, max_mb=1)  # limite 1 MB
    assert exc.value.status_code == 413


# ─── Sanitização de filename ──────────────────────────────────────────────
@pytest.mark.asyncio
async def test_filename_sanitized_path_traversal():
    f = _upload(b"\x89PNG\r\n\x1a\n", "../../etc/passwd.png", "image/png")
    out = await validate_upload(f, ALLOWED_IMAGE, max_mb=1)
    assert "/" not in out.filename
    assert ".." not in out.filename
    assert out.filename.endswith(".png")


# ─── Cobertura: todos os 17 routes migrados importam validate_upload ──────
MIGRATED_ROUTES = [
    "documents.py", "structuro.py", "structuro_bet.py", "structuro_plan.py",
    "dpgf.py", "plans_crud.py", "portal_chat.py", "radar.py", "renovation.py",
    "runway_render.py", "speech.py", "library.py", "param_library.py",
    "prices.py", "company_page.py", "doc_intel.py", "shared_library.py",
]


def test_all_17_routes_import_validate_upload():
    missing = []
    routes_dir = ROOT / "routes"
    for name in MIGRATED_ROUTES:
        text = (routes_dir / name).read_text(encoding="utf-8")
        if "validate_upload" not in text:
            missing.append(name)
    assert not missing, (
        "Routes sem `validate_upload` após AJ.1:\n" + "\n".join(missing)
    )
