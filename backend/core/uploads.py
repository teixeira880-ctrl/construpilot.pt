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

ALLOWED_IMAGE = ["image/png", "image/jpeg", "image/webp", "image/gif"]
ALLOWED_DOCUMENT = ["application/pdf"]
ALLOWED_CAD = [
    "application/dxf", "image/vnd.dxf",
    "application/acad", "application/x-autocad",
    "application/octet-stream",  # muitos browsers enviam DWG/DXF assim
]
ALLOWED_IMPORT = ["text/csv", "application/vnd.ms-excel",
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"]
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
) -> UploadFile:
    """Valida content_type, tamanho e sanitiza filename.

    - 400 se content_type fora da whitelist.
    - 413 se > max_mb*1024*1024.
    - Mutação defensiva: `file.filename` passa a ser sanitizado.
    """
    allowed = allowed if allowed is not None else ALLOWED_ANY_SAFE
    max_mb = max_mb if max_mb is not None else _max_mb()
    ctype = (file.content_type or "").lower()
    if ctype not in [a.lower() for a in allowed]:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de ficheiro não permitido: '{ctype}'. "
                   f"Aceites: {', '.join(allowed)}",
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
