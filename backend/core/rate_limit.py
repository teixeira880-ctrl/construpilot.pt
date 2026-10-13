"""Rate limiting global via slowapi.

- Backend mémoire par défaut ; passer ``REDIS_URL`` pour partager entre workers.
- Le limiteur est enregistré dans ``server.py`` (app.state.limiter + middleware).
- Les endpoints sensibles importent ``limiter`` et posent ``@limiter.limit("...")``.
"""
import os

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# ``memory://`` convient pour un seul worker ; en prod passer un Redis partagé.
_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")

def client_ip(request: Request) -> str:
    """IP réelle derrière l'ingress/Cloudflare : premier X-Forwarded-For (sinon IP de connexion).
    Sans cela, tous les visiteurs partageraient l'IP du proxy — et donc le même compteur."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.headers.get("cf-connecting-ip") or get_remote_address(request)


limiter = Limiter(
    key_func=client_ip,
    storage_uri=_STORAGE_URI,
    default_limits=["300/minute"],
    headers_enabled=True,
    enabled=os.environ.get("RATE_LIMIT_ENABLED", "1") != "0",  # RATE_LIMIT_ENABLED=0 : suites de tests massives uniquement
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Réponse JSON 429 uniforme (le client peut se fier à ``Retry-After``)."""
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Demasiados pedidos — aguarde alguns instantes.",
            "limit": str(exc.detail),
        },
    )
