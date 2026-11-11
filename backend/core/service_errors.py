"""Erreurs de services externes (IA, recherche, e-mail, paiement) : réponse claire au lieu d'un 500 nu.

Quand tous les fournisseurs IA échouent, ou qu'un service externe ne répond pas, l'utilisateur reçoit
un 503 JSON lisible (« réessayez ») au lieu de « Internal Server Error ». Les autres exceptions
restent des 500 (et sont journalisées comme avant).
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import Request
from fastapi.responses import JSONResponse, PlainTextResponse

logger = logging.getLogger(__name__)

MSG_UNAVAILABLE = "Serviço externo (IA, pesquisa ou envio) momentaneamente indisponível. Os seus dados estão guardados: tente novamente dentro de instantes."
MSG_NOT_CONFIGURED = "Serviço não configurado neste servidor. Contacte o suporte ConstruPilot."

_NET_CLASSES = ("APIConnectionError", "APITimeoutError", "RateLimitError", "ServiceUnavailableError",
                "InternalServerError", "ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError")
_UNAVAILABLE_HINTS = ("indisponível", "indisponible", "unavailable", "tous les fournisseurs", "todos os fornecedores")
_CONFIG_HINTS = ("não configurad", "non configur", "em falta", "manquant", "not initialized", "not configured")


def classify(exc: BaseException) -> str | None:
    name = type(exc).__name__
    if isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError)) or name in _NET_CLASSES:
        return "unavailable"
    if isinstance(exc, RuntimeError):
        msg = str(exc).lower()
        if any(h in msg for h in _UNAVAILABLE_HINTS):
            return "unavailable"
        if any(h in msg for h in _CONFIG_HINTS):
            return "not_configured"
    return None


async def service_error_handler(request: Request, exc: Exception):
    kind = classify(exc)
    path = getattr(request.url, "path", "?")
    if kind == "unavailable":
        logger.warning("external service unavailable path=%s err=%s: %s", path, type(exc).__name__, str(exc)[:300])
        return JSONResponse(status_code=503, content={"detail": MSG_UNAVAILABLE, "retryable": True},
                            headers={"Retry-After": "20"})
    if kind == "not_configured":
        logger.error("external service not configured path=%s err=%s", path, str(exc)[:300])
        return JSONResponse(status_code=503, content={"detail": MSG_NOT_CONFIGURED, "retryable": False})
    logger.exception("unhandled_exception path=%s", path, exc_info=exc)
    return PlainTextResponse("Internal Server Error", status_code=500)
