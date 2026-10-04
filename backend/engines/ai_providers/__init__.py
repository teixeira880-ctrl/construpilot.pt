"""Provedores IA: Claude (primário), OpenAI (fallback), Perplexity (web search).

Uso:
    from engines.ai_providers.router import ai_router
    answer = await ai_router.coach_ask(prompt=..., system=..., ...)

Nenhum provedor é importado se a sua API key não estiver no env — permite
que o processo arranque mesmo sem chaves configuradas.
"""
from engines.ai_providers.base import (
    AIProviderError,
    AIProviderNotConfigured,
    AIResponse,
    AIUsage,
)

__all__ = ["AIProviderError", "AIProviderNotConfigured", "AIResponse", "AIUsage"]
