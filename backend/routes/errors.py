"""Client-side error logging.

Receives error reports from the frontend `ErrorBoundary` and writes them to
the Python logger (supervisor logs → visible in Emergent's deployed app logs).

Kept intentionally lightweight — no external Sentry dependency. Rate-limits
to 1 error per IP+message per 60s to avoid log floods.
"""
import hashlib
import logging
import time
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/errors", tags=["errors"])
logger = logging.getLogger("client_errors")

# Simple in-memory dedup cache : { (ip, msg_hash): last_ts }
_RECENT: dict[tuple[str, str], float] = {}
_DEDUP_WINDOW_S = 60.0
_MAX_CACHE = 500


class ClientErrorIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    stack: Optional[str] = Field(default=None, max_length=5000)
    url: Optional[str] = Field(default=None, max_length=500)
    user_agent: Optional[str] = Field(default=None, max_length=500)
    user_id: Optional[str] = Field(default=None, max_length=100)


def _dedup(ip: str, msg: str) -> bool:
    """Return True if this (ip, msg) was seen in the last dedup window."""
    now = time.time()
    key = (ip, hashlib.sha256(msg.encode("utf-8", "ignore")).hexdigest()[:16])
    # Expire old entries lazily
    if len(_RECENT) > _MAX_CACHE:
        cutoff = now - _DEDUP_WINDOW_S
        for k in [k for k, t in _RECENT.items() if t < cutoff]:
            _RECENT.pop(k, None)
    last = _RECENT.get(key)
    if last and (now - last) < _DEDUP_WINDOW_S:
        return True
    _RECENT[key] = now
    return False


@router.post("/client-log")
async def log_client_error(body: ClientErrorIn, request: Request):
    """Public endpoint (no auth) — logs a frontend runtime error.

    The ErrorBoundary POSTs here whenever `componentDidCatch` fires.
    """
    ip = (request.client.host if request.client else "unknown")[:40]
    if _dedup(ip, body.message):
        return {"ok": True, "deduped": True}
    logger.error(
        "CLIENT_ERROR | ip=%s | user=%s | url=%s | ua=%s | msg=%s | stack=%s",
        ip,
        body.user_id or "-",
        (body.url or "-")[:200],
        (body.user_agent or "-")[:150],
        body.message[:400],
        (body.stack or "-")[:2000],
    )
    return {"ok": True}
