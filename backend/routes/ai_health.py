"""Health check dos provedores IA (admin-only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.security import admin_user
from engines.ai_providers.router import ai_router

router = APIRouter(prefix="/admin", tags=["admin", "ai"],
                   dependencies=[Depends(admin_user)])


@router.get("/ai-health", summary="Estado dos provedores IA (Claude/OpenAI/Perplexity)")
async def ai_health(
    ping: bool = Query(False, description="Fazer chamada real leve a cada provedor"),
) -> dict:
    """Devolve estado dos 3 provedores + modelo configurado.

    `?ping=true` → faz 1 chamada mínima (consome ~5-50 tokens por provedor).
    """
    return await ai_router.health(ping=ping)


@router.post("/ai-reset", summary="Força recarregamento dos provedores (após rotação .env)")
async def ai_reset() -> dict:
    ai_router.reset()
    return {"ok": True, "message": "ai_router recarregado — próxima chamada relê .env."}
