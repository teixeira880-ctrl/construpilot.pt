"""Y.4 — magic-bytes para ficheiros CAD (DWG/DXF/IFC)."""
import io
import sys
from pathlib import Path

import pytest
from fastapi import UploadFile, HTTPException

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.uploads import (
    _detect_cad_magic, validate_upload,
    ALLOWED_CAD, ALLOWED_DOCUMENT, ALLOWED_IMAGE,
)


def _mk_upload(filename: str, ctype: str, data: bytes) -> UploadFile:
    f = io.BytesIO(data)
    up = UploadFile(filename=filename, file=f)
    object.__setattr__(up, "_content_type", ctype)
    up.headers = {"content-type": ctype}
    return up


def test_y4_dwg_magic_detected():
    assert _detect_cad_magic(b"AC1032" + b"\x00" * 128) is True  # R2007
    assert _detect_cad_magic(b"AC1024" + b"\x00" * 128) is True  # R2010
    assert _detect_cad_magic(b"AC1040" + b"\x00" * 128) is True  # R2024


def test_y4_dxf_ascii_magic_detected():
    assert _detect_cad_magic(b"0\r\nSECTION\r\n...") is True
    assert _detect_cad_magic(b"0\nSECTION\nmoredata") is True
    assert _detect_cad_magic(b"999\nComment line\n0\nSECTION\n") is True


def test_y4_dxf_binary_magic_detected():
    assert _detect_cad_magic(b"AutoCAD Binary DXF\r\n\x1a\x00") is True


def test_y4_ifc_magic_detected():
    assert _detect_cad_magic(b"ISO-10303-21;\nHEADER;\n") is True


def test_y4_random_bytes_rejected():
    assert _detect_cad_magic(b"\x00" * 1024) is False
    assert _detect_cad_magic(b"GIF89a" + b"\x00" * 500) is False  # image, não CAD
    assert _detect_cad_magic(b"<?xml version='1.0'?>") is False
    assert _detect_cad_magic(b"") is False
    assert _detect_cad_magic(b"short") is False


@pytest.mark.asyncio
async def test_y4_octet_stream_cad_dwg_accepted():
    """DWG com octet-stream + magic bytes AC1032 → aceite."""
    up = _mk_upload("planta.dwg", "application/octet-stream",
                    b"AC1032" + b"\x00" * 500)
    out = await validate_upload(
        up, ALLOWED_CAD + ALLOWED_DOCUMENT + ALLOWED_IMAGE, max_mb=25,
    )
    assert out.filename == "planta.dwg"


@pytest.mark.asyncio
async def test_y4_octet_stream_without_cad_magic_rejected():
    """octet-stream + bytes aleatórios → 400 Formato CAD não reconhecido."""
    up = _mk_upload("fake.dwg", "application/octet-stream", b"\x00" * 1024)
    with pytest.raises(HTTPException) as exc:
        await validate_upload(
            up, ALLOWED_CAD + ALLOWED_DOCUMENT, max_mb=25,
        )
    assert exc.value.status_code == 400
    assert "CAD" in exc.value.detail


@pytest.mark.asyncio
async def test_y4_dxf_ascii_via_application_dxf_accepted():
    """DXF ASCII com content_type explícito application/dxf → aceite sem magic check."""
    up = _mk_upload("plan.dxf", "application/dxf",
                    b"0\r\nSECTION\r\n2\r\nHEADER\r\n")
    out = await validate_upload(up, ALLOWED_CAD, max_mb=25)
    assert out.filename == "plan.dxf"


@pytest.mark.asyncio
async def test_y4_octet_stream_rejected_when_cad_not_allowed():
    """Se CAD não está na whitelist do endpoint, octet-stream rejeitado direto."""
    up = _mk_upload("mystery.bin", "application/octet-stream",
                    b"AC1032" + b"\x00" * 500)
    with pytest.raises(HTTPException) as exc:
        await validate_upload(up, ALLOWED_DOCUMENT + ALLOWED_IMAGE, max_mb=25)
    assert exc.value.status_code == 400
