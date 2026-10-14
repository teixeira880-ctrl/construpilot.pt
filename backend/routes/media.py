"""Diffusion publique d'assets marketing (vidéo TikTok) depuis l'Object Storage.

Route /api/... : fiable sur preview ET en production (le storage est externe).
Supporte les requêtes Range pour la lecture/seek vidéo.
"""
import logging
import re

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool

from engines import storage

router = APIRouter(prefix="/media", tags=["media"])
log = logging.getLogger(__name__)

_TIKTOK_PATH = "marketing/construpilot_tiktok_v1.mp4"
_cache: bytes | None = None


async def _load() -> bytes | None:
    global _cache
    if _cache is None:
        try:
            data, _ = await run_in_threadpool(storage.get_object, _TIKTOK_PATH)
            _cache = data
        except Exception as exc:  # noqa: BLE001 — storage em falta ou erro externo não deve devolver 500
            log.warning("media.tiktok: carregamento indisponível (%s)", exc)
            return None
    return _cache


@router.get("/tiktok")
async def tiktok(request: Request):
    data = await _load()
    ct = "video/mp4"
    if not data:
        # Serviço indisponível → responde 200 com corpo vazio para não quebrar o <video> do frontend
        return Response(b"", media_type=ct, headers={
            "Content-Length": "0", "Accept-Ranges": "bytes",
            "X-Media-Configured": "false", "Cache-Control": "no-store"})
    total = len(data)
    rng = request.headers.get("range")
    if rng:
        m = re.match(r"bytes=(\d+)-(\d*)", rng)
        if m:
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else total - 1
            end = min(end, total - 1)
            chunk = data[start:end + 1]
            return Response(chunk, status_code=206, media_type=ct, headers={
                "Content-Range": f"bytes {start}-{end}/{total}",
                "Accept-Ranges": "bytes", "Content-Length": str(len(chunk)),
                "Cache-Control": "public, max-age=86400"})
    return Response(data, media_type=ct, headers={
        "Accept-Ranges": "bytes", "Content-Length": str(total),
        "Content-Disposition": "inline; filename=construpilot_tiktok.mp4",
        "Cache-Control": "public, max-age=86400"})
