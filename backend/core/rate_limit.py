"""Rate limiting (slowapi) com chave user_id:plano → fallback IP + resposta PT-PT.

Uso:
    from core.rate_limit import limiter, rate_limit_handler, plan_limit_fn
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

    @router.post("/x")
    @limiter.limit("20/hour")
    async def endpoint(request: Request, ...): ...

Para limites dinâmicos por plano (Grátis vs Pro vs Business), usar:

    @limiter.limit(plan_limit_fn(free="20/hour", pro="60/hour", business="120/hour"))
    async def endpoint(request: Request, user=Depends(current_user_with_state)): ...

A chave da bucket inclui o plano, logo cada tier conta de forma independente.

Sub-bucket "web search" (soft fallback):
    from core.rate_limit import web_search_hit, web_search_remaining
    if web_search_hit(user_id, plan, "coach", max_per_hour=10):
        # ok, use web search
    else:
        # cair para Claude sem Perplexity + avisar na UI
"""
from __future__ import annotations

import os
import time
from collections import defaultdict
from threading import Lock

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


# ---------------------------------------------------------------------------
# Plano do utilizador
# ---------------------------------------------------------------------------
def user_plan(user: dict | None) -> str:
    """Devolve "business" | "pro" | "free" | "anon" com base no utilizador.

    Regras ConstruPilot:
      - `role == "admin"`                     → business (sem bloqueios)
      - `account_type == "particulier"`       → free
      - `account_type == "pro_business"`      → business
      - `account_type == "pro"`               → pro
      - demais casos (sem account_type)        → pro (compatibilidade histórica)
      - sem utilizador                         → anon (endpoints públicos)
    """
    if not user:
        return "anon"
    if user.get("role") == "admin":
        return "business"
    account_type = user.get("account_type")
    if account_type == "particulier":
        return "free"
    if account_type == "pro_business":
        return "business"
    if account_type == "pro":
        return "pro"
    # Default (contas antigas sem campo): tratar como pro (compat).
    return "pro"


def _user_or_ip_key(request: Request) -> str:
    """Chave por `user_id:plano`, fallback para IP remoto."""
    try:
        user = getattr(request.state, "user", None)
        if user:
            uid = user.get("user_id") or user.get("id") or user.get("email")
            if uid:
                return f"u:{uid}:p:{user_plan(user)}"
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


# ---------------------------------------------------------------------------
# Limites dinâmicos por plano
# ---------------------------------------------------------------------------
def plan_limit_fn(free: str, pro: str, business: str | None = None):
    """Factory para `@limiter.limit(...)` com valor dependente do plano.

    slowapi chama o callable com `key` quando este tem um parâmetro chamado
    `key` e `key_func` recebe `request`. Como `_user_or_ip_key` recebe
    `request`, basta inspeccionar o sufixo da chave retornada para decidir
    o limite. Se `business` não for fornecido, usa o limite `pro`.
    """
    _business = business or pro

    def _fn(key: str) -> str:
        if isinstance(key, str):
            if key.endswith(":p:business"):
                return _business
            if key.endswith(":p:pro"):
                return pro
            if key.endswith(":p:free"):
                return free
        # anon / fallback IP → aplica limite Grátis (mais apertado)
        return free

    return _fn


# ---------------------------------------------------------------------------
# Handler 429 PT-PT
# ---------------------------------------------------------------------------
_UPGRADE_URL = "/pricing"

_PLAN_LABEL_PT = {
    "free": "Grátis",
    "pro": "Pro",
    "business": "Pro Business",
    "anon": "Visitante",
}


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Resposta HTTP 429 em PT-PT com contexto (plano actual, link de upgrade)."""
    retry_after = int(getattr(exc, "retry_after", 0) or 60)
    limit_str = str(getattr(exc, "detail", "")) or "limite por hora"
    minutes = max(1, retry_after // 60)

    user = getattr(request.state, "user", None)
    plan = user_plan(user)
    plan_label = _PLAN_LABEL_PT.get(plan, plan)

    if plan == "business":
        message = (
            f"Atingiu o limite do plano Pro Business ({limit_str}). "
            f"Aguarde cerca de {minutes} min e tente novamente."
        )
    elif plan == "pro":
        message = (
            f"Atingiu o limite do plano Pro ({limit_str}). "
            f"Faça upgrade para Pro Business para o dobro de pedidos "
            f"ou aguarde cerca de {minutes} min."
        )
    else:
        message = (
            f"Atingiu o limite de pedidos do plano Grátis ({limit_str}). "
            f"Faça upgrade para Pro (99 €/mês) para subir o limite "
            f"ou aguarde cerca de {minutes} min."
        )

    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": message,
            "retry_after_seconds": retry_after,
            "retry_after_minutes": minutes,
            "limit": limit_str,
            "current_plan": plan,
            "current_plan_label": plan_label,
            "upgrade_url": _UPGRADE_URL,
        },
        headers={"Retry-After": str(retry_after)},
    )


# ---------------------------------------------------------------------------
# Sub-bucket "web search" (soft fallback)
# ---------------------------------------------------------------------------
# Contador in-memory por (user_id, plan, flow). Para prod multi-réplica,
# migrar para Redis.
_web_bucket: dict[str, list[float]] = defaultdict(list)
_web_lock = Lock()
_WEB_WINDOW_SECONDS = 3600  # 1 h


def _web_key(user_id: str, plan: str, flow: str) -> str:
    return f"u:{user_id}:p:{plan}:f:{flow}:w"


def _prune(key: str, now: float) -> None:
    cutoff = now - _WEB_WINDOW_SECONDS
    _web_bucket[key] = [t for t in _web_bucket[key] if t > cutoff]


def web_search_hit(user_id: str, plan: str, flow: str, max_per_hour: int) -> bool:
    """Tenta consumir um pedido web-search. Devolve ``True`` se permitido.

    Se devolver ``False``, o chamador deve cair para resposta sem Perplexity
    e sinalizar ao utilizador (não é um 429, é soft-fallback).
    """
    key = _web_key(user_id, plan, flow)
    now = time.time()
    with _web_lock:
        _prune(key, now)
        if len(_web_bucket[key]) >= max_per_hour:
            return False
        _web_bucket[key].append(now)
        return True


def web_search_remaining(user_id: str, plan: str, flow: str, max_per_hour: int) -> int:
    """Pedidos web-search restantes na janela de 1 h para este utilizador/flow."""
    key = _web_key(user_id, plan, flow)
    now = time.time()
    with _web_lock:
        _prune(key, now)
        return max(0, max_per_hour - len(_web_bucket[key]))


def web_search_reset_seconds(user_id: str, plan: str, flow: str) -> int:
    """Segundos até ao próximo slot libertar (soft).

    Devolve 0 se ainda houver slots livres.
    """
    key = _web_key(user_id, plan, flow)
    now = time.time()
    with _web_lock:
        _prune(key, now)
        if not _web_bucket[key]:
            return 0
        oldest = _web_bucket[key][0]
        return max(0, int(_WEB_WINDOW_SECONDS - (now - oldest)))


# ---------------------------------------------------------------------------
# Limites por flow (export para rotas e frontend)
# ---------------------------------------------------------------------------
# Totais já aplicados via @limiter.limit(plan_limit_fn(...))
# Web-search sub-bucket (soft limit, aplicado em código):
WEB_LIMITS = {
    "coach": {"free": 10, "pro": 40, "business": 80},
    "btp_solver": {"free": 5, "pro": 20, "business": 40},
}

TOTAL_LIMITS = {
    "coach": {"free": 20, "pro": 60, "business": 120},
    "btp_solver": {"free": 10, "pro": 40, "business": 80},
}


def flow_limits(flow: str, plan: str) -> dict:
    """Devolve limites atuais para expor na resposta (``X-RateLimit-*`` + JSON)."""
    return {
        "total_per_hour": TOTAL_LIMITS.get(flow, {}).get(plan, 0),
        "web_per_hour": WEB_LIMITS.get(flow, {}).get(plan, 0),
    }
