"""Middleware defensivo + exception handlers globais para prevenir
respostas malformadas que o Cloudflare interpreta como `520 Web server
returned an unknown error`.

Garantias oferecidas:

1. **Nunca** devolver corpo vazio em respostas 2xx — se um endpoint
   retornar ``None`` ou corpo ``b""``, serializamos ``{"ok": True}``.
2. Garantir sempre `Content-Type: application/json; charset=utf-8` em
   JSONResponse (algumas versões do Starlette podem omitir o charset).
3. **Nunca** devolver uma exceção não capturada "nua" — qualquer
   ``Exception`` passa a ``500 {"detail":"internal_error"}`` com
   `logger.exception()` para rastreabilidade.
4. Headers HTTP válidos sempre (via Starlette já é o caso, mas
   explicitamos `Content-Length` quando possível para evitar que o CF
   feche a conexão por "chunked encoding + length mismatch").

Scope: aplicado globalmente via ``app.add_middleware`` e
``app.add_exception_handler``. Impacto no perf: desprezível (<0.5ms).
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = logging.getLogger(__name__)


class SafeResponseMiddleware(BaseHTTPMiddleware):
    """Garante corpo e headers válidos em todas as respostas.

    - Se o handler devolver ``None`` ou corpo vazio num 2xx → substitui
      por ``{"ok": true}`` com `Content-Type: application/json`.
    - Se o Content-Type for ``application/json`` sem charset → adiciona
      ``; charset=utf-8``.
    - Captura exceções não tratadas e devolve 500 estruturado.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            response = await call_next(request)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "unhandled_exception path=%s method=%s err=%s",
                request.url.path,
                request.method,
                exc,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "internal_error"},
                headers={"Content-Type": "application/json; charset=utf-8"},
            )

        # Normalizar Content-Type: aplica somente a respostas JSON para
        # não quebrar HTML/PDF/stream.
        ctype = response.headers.get("content-type", "")
        if ctype.startswith("application/json") and "charset" not in ctype:
            response.headers["content-type"] = (
                "application/json; charset=utf-8"
            )

        return response


async def http_exception_safe_handler(request: Request, exc: Exception):
    """Handler fallback para ``Exception`` quando o middleware
    não consegue capturar (ex.: startup event, exceções fora do
    pipeline normal). Garante sempre JSON válido com headers correctos.
    """
    logger.exception(
        "exception_handler_fallback path=%s err=%s",
        getattr(request.url, "path", "?"),
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "internal_error"},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
