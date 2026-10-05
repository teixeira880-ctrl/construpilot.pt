"""Rate limiting (slowapi) com chave user_id → fallback IP + resposta PT-PT.

Uso:
    from core.rate_limit import limiter, rate_limit_handler
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    @router.post("/x")
    @limiter.limit("20/hour")
    async def endpoint(request: Request, ...): ...
"""
from __future__ import annotations

import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def _user_or_ip_key(request: Request) -> str:
    """Chave por `user_id` (JWT state), fallback para IP remoto."""
    try:
        user = getattr(request.state, "user", None)
        if user:
            uid = user.get("user_id") or user.get("id") or user.get("email")
            if uid:
                return f"u:{uid}"
    except Exception:
        pass
    return f"ip:{get_remote_address(request)}"


# Bypass em testes/env dev se RATE_LIMIT_DISABLED=1
_disabled = (os.environ.get("RATE_LIMIT_DISABLED") or "").lower() in {"1", "true", "yes"}

limiter = Limiter(
    key_func=_user_or_ip_key,
    enabled=not _disabled,
    headers_enabled=False,  # headers via SlowAPIMiddleware em server.py
)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Resposta HTTP 429 em PT-PT."""
    retry_after = int(getattr(exc, "retry_after", 0) or 60)
    limit_str = str(getattr(exc, "detail", "")) or "limite por hora"
    minutes = max(1, retry_after // 60)
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Atingiu o limite de pedidos ({limit_str}). "
                       f"Tente novamente em cerca de {minutes} min.",
            "retry_after_seconds": retry_after,
            "limit": limit_str,
        },
        headers={"Retry-After": str(retry_after)},
    )
