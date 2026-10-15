"""Validação centralizada de uploads (SEC-X-003).

Whitelist de content_type + max_size + sanitização de filename contra
path traversal / injection. Usar em todos os endpoints com UploadFile.

Uso típico:
    from core.uploads import validate_upload, ALLOWED_IMAGE
    @router.post("/upload")
    async def upload(file: UploadFile = File(...)):
        file = await validate_upload(file, ALLOWED_IMAGE)
        ...
"""
import os
import re
from pathlib import Path
from fastapi import HTTPException, UploadFile

ALLOWED_IMAGE = ["image/png", "image/jpeg", "image/webp", "image/gif",
                 "image/heic", "image/heif"]
ALLOWED_DOCUMENT = ["application/pdf"]
ALLOWED_CAD = [
    "application/dxf", "image/vnd.dxf",
    "application/acad", "application/x-autocad",
    "application/octet-stream",  # DWG/DXF/IFC — valida por magic-bytes
]


# ─── Magic-bytes para ficheiros CAD (SEC-Y-004) ────────────────────────────
# DWG: "AC" + 4 chars (versão, ex. "1032" para R2007, "1024" para R2010, etc.).
# DXF: ASCII começa com "0\r\nSECTION" (ou com comentários "999") OU começa com
#      binário "AutoCAD Binary DXF".
# IFC/STEP: "ISO-10303-21;" (ISO 10303 Part 21 / STEP).
_DWG_VERSIONS = {b"1012", b"1014", b"1015", b"1018", b"1021", b"1024", b"1027",
                 b"1032", b"1035", b"1040", b"1041"}

def _detect_cad_magic(raw: bytes) -> bool:
    """Devolve True se os primeiros bytes correspondem a DWG/DXF/IFC conhecidos."""
    if len(raw) < 8:
        return False
    head = raw[:1024]
    # DWG: começa com "AC" + 4 chars de versão
    if head[:2] == b"AC" and head[2:6] in _DWG_VERSIONS:
        return True
    # DXF binário
    if head.startswith(b"AutoCAD Binary DXF"):
        return True
    # DXF ASCII: começa com "0\r\nSECTION" ou "0\nSECTION" ou comentário "999"
    stripped = head.lstrip()
    if stripped.startswith(b"0\r\nSECTION") or stripped.startswith(b"0\nSECTION"):
        return True
    if stripped.startswith(b"999"):
        return True
    # IFC / STEP (ISO 10303-21 / 10303-28)
    if head.startswith(b"ISO-10303-"):
        return True
    return False
ALLOWED_IMPORT = ["text/csv", "application/vnd.ms-excel",
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
ALLOWED_OFFICE = [
    # Word
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Excel (variantes)
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel.sheet.macroenabled.12",
    # PowerPoint
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Texto
    "text/plain",
    "text/csv",
]
ALLOWED_AUDIO = ["audio/mpeg", "audio/wav", "audio/webm", "audio/ogg", "audio/mp4"]

# Whitelist combinada por defeito (uploads genéricos de documentos pro)
ALLOWED_ANY_SAFE = ALLOWED_IMAGE + ALLOWED_DOCUMENT

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]")

def _max_mb() -> int:
    try:
        return int(os.environ.get("MAX_UPLOAD_MB", "20"))
    except ValueError:
        return 20

def sanitize_filename(name: str | None) -> str:
    """Remove path components e caracteres perigosos. Blinda contra path traversal."""
    if not name:
        return "ficheiro"
    base = Path(name).name  # elimina ../ e absolute paths
    cleaned = _FILENAME_SAFE.sub("_", base).strip("._") or "ficheiro"
    return cleaned[:120]  # limita comprimento

async def validate_upload(
    file: UploadFile,
    allowed: list[str] | None = None,
    max_mb: int | None = None,
    override_content_type: str | None = None,
) -> UploadFile:
    """Valida content_type, tamanho e sanitiza filename.

    - 400 se content_type fora da whitelist.
    - 413 se > max_mb*1024*1024.
    - Mutação defensiva: `file.filename` passa a ser sanitizado.
    - `override_content_type`: usar quando o browser envia um mime genérico
      (ex. `application/octet-stream` para CAD) e o routing já determinou o
      mime real a partir da extensão. NÃO escreve de volta em `file.content_type`
      (que é read-only em Starlette ≥0.37).
    """
    allowed = allowed if allowed is not None else ALLOWED_ANY_SAFE
    max_mb = max_mb if max_mb is not None else _max_mb()
    effective_type = (override_content_type or file.content_type or "").lower()
    if effective_type not in [a.lower() for a in allowed]:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de ficheiro não permitido: '{effective_type}'. "
                   f"Aceites: {', '.join(allowed)}",
        )
    # SEC-Y-004: se o endpoint aceita CAD e o ficheiro vem com content-type
    # genérico 'application/octet-stream', confirma por magic-bytes.
    if (effective_type == "application/octet-stream"
            and any(a == "application/octet-stream" for a in ALLOWED_CAD)
            and any(a in ALLOWED_CAD for a in allowed)):
        try:
            pos = file.file.tell()
            head = file.file.read(1024)
            file.file.seek(pos)
        except Exception:
            head = b""
        if not _detect_cad_magic(head):
            raise HTTPException(
                status_code=400,
                detail="Formato CAD não reconhecido (DWG/DXF/IFC esperado).",
            )
    # Tamanho: tenta file.size (FastAPI>=0.95), senão lê o stream.
    size = getattr(file, "size", None)
    if size is None:
        try:
            pos = file.file.tell()
            file.file.seek(0, 2)
            size = file.file.tell()
            file.file.seek(pos)
        except Exception:
            size = 0
    limit = max_mb * 1024 * 1024
    if size and size > limit:
        raise HTTPException(
            status_code=413,
            detail=f"Ficheiro demasiado grande ({size // 1024 // 1024} MB). "
                   f"Limite: {max_mb} MB.",
        )
    file.filename = sanitize_filename(file.filename)
    return file
