"""Serve only approved presentation artefacts; private storage paths never leave the server."""
import asyncio
import hashlib
import os
import re
import tempfile
from pathlib import Path

from core.db import db
from engines import storage
from fastapi import HTTPException, Request
from starlette.responses import Response, StreamingResponse

CACHE = Path(tempfile.gettempdir()) / "construpilot-published-presentations"
MAX_BYTES = 160 * 1024 * 1024
_locks: dict[str, asyncio.Lock] = {}


def download_parts(record, target):
    parts = record.get("parts") or []
    if not parts or len(parts) > 20:
        raise ValueError("Invalid asset parts")
    fd, name = tempfile.mkstemp(prefix="download-", dir=CACHE)
    os.close(fd)
    temp = Path(name)
    count = 0
    sha = hashlib.sha256()
    try:
        with temp.open("wb") as stream:
            for part in parts:
                content, _content_type = storage.get_object(part)
                count += len(content)
                if count > record["byte_size"] or count > MAX_BYTES:
                    raise ValueError("Invalid asset size")
                sha.update(content)
                stream.write(content)
        if count != record["byte_size"] or sha.hexdigest() != record["sha256"]:
            raise ValueError("Asset checksum mismatch")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)


async def cached_asset(variant):
    record = await db.presentation_assets.find_one({"variant": variant, "published": True}, {"_id": 0})
    if not record:
        raise HTTPException(404, "Vidéo indisponible")
    digest = record.get("sha256", "")
    size = record.get("byte_size", 0)
    if not re.fullmatch(r"[a-f0-9]{64}", digest) or not 0 < size <= MAX_BYTES:
        raise HTTPException(503, "Métadonnées vidéo invalides")
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / f"{digest}.mp4"
    async with _locks.setdefault(variant, asyncio.Lock()):
        if not target.exists() or target.stat().st_size != size:
            try:
                await asyncio.to_thread(download_parts, record, target)
            except Exception as exc:
                raise HTTPException(503, "Vidéo temporairement indisponible") from exc
    return record, target


def byte_range(value, size):
    if not value:
        return 0, size - 1, False
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value) if len(value) < 90 else None
    if not match or not any(match.groups()):
        raise ValueError("Unsupported byte range")
    a, b = match.groups()
    if not a:
        suffix = int(b)
        if suffix <= 0:
            raise ValueError("Invalid suffix")
        return max(0, size - suffix), size - 1, True
    start, end = int(a), min(size - 1, int(b)) if b else size - 1
    if start >= size or end < start:
        raise ValueError("Range outside file")
    return start, end, True


def video_response(request: Request, record, file: Path):
    size = record["byte_size"]
    etag = '"' + record["sha256"] + '"'
    headers = {"Accept-Ranges": "bytes", "ETag": etag, "Cache-Control": "public, max-age=3600",
               "X-Content-Type-Options": "nosniff",
               "Content-Disposition": f'inline; filename="ConstruPilot-FR-{record["variant"]}.mp4"'}
    if request.headers.get("if-none-match") == etag and not request.headers.get("range"):
        return Response(status_code=304, headers=headers)
    requested = request.headers.get("range")
    if request.headers.get("if-range") not in (None, etag):
        requested = None
    try:
        start, end, partial = byte_range(requested, size)
    except ValueError:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"})
    length = end - start + 1
    headers["Content-Length"] = str(length)
    if partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if request.method == "HEAD":
        return Response(status_code=206 if partial else 200, media_type="video/mp4", headers=headers)

    def chunks():
        with file.open("rb") as stream:
            stream.seek(start)
            remaining = length
            while remaining:
                block = stream.read(min(256 * 1024, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block
    return StreamingResponse(chunks(), status_code=206 if partial else 200, media_type="video/mp4", headers=headers)