"""Health check endpoints — `/api/health` e variantes.

Público, sem autenticação. Retorna estado mínimo (sem detalhes internos nem segredos).
Usado por smoke tests pós-deploy e load balancer.
"""
from fastapi import APIRouter

from core.db import db

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Verificação leve: ping ao Mongo + resposta rápida."""
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception:  # noqa: BLE001
        mongo_ok = False
    return {"status": "ok" if mongo_ok else "degraded", "mongo": mongo_ok}


@router.get("/healthz")
async def healthz() -> dict:
    """Alias curto compatível com convenções k8s."""
    return await health()
