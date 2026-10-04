"""Contrato comum para todos os provedores IA."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol


Role = Literal["user", "assistant", "system"]


@dataclass
class AIUsage:
    """Tokens consumidos (quando disponíveis)."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    @property
    def cost_hint(self) -> float:
        """Heurística muito grosseira (sem precisão), em USD."""
        return (self.input_tokens * 3 + self.output_tokens * 15) / 1_000_000


@dataclass
class Citation:
    """Citação de fonte (sobretudo Perplexity)."""
    url: str
    title: str | None = None
    snippet: str | None = None


@dataclass
class AIResponse:
    """Resposta normalizada entre provedores."""
    text: str
    provider: str           # "claude" | "openai" | "perplexity"
    model: str              # ID do modelo usado
    latency_ms: int = 0
    usage: AIUsage = field(default_factory=AIUsage)
    citations: list[Citation] = field(default_factory=list)
    request_id: str | None = None
    stop_reason: str | None = None
    raw: dict[str, Any] | None = None  # payload cru para debug

    @property
    def is_empty(self) -> bool:
        return not (self.text and self.text.strip())


class AIProviderError(RuntimeError):
    """Falha num provedor IA.

    `retriable`: True se faz sentido tentar o mesmo provedor outra vez
    (rate limit, timeout). False se devemos ir direto ao fallback
    (chave inválida, modelo inexistente, 4xx permanente).
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        code: str = "unknown_error",
        status_code: int | None = None,
        retriable: bool = False,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.status_code = status_code
        self.retriable = retriable
        self.details = details or {}

    def to_meta(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "code": self.code,
            "status_code": self.status_code,
            "retriable": self.retriable,
            "message": str(self)[:300],
            "details": self.details,
        }


class AIProviderNotConfigured(AIProviderError):
    """API key em falta ou mal formatada."""

    def __init__(self, provider: str, env_var: str):
        super().__init__(
            f"Variável {env_var} não definida — provedor {provider} desativado.",
            provider=provider, code="not_configured", retriable=False,
        )


class AIProvider(Protocol):
    """Interface comum (duck typing)."""
    name: str

    async def ask(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        history: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AIResponse: ...

    async def ping(self) -> dict[str, Any]:
        """Health check leve."""
        ...


__all__ = [
    "AIProvider", "AIResponse", "AIUsage", "Citation",
    "AIProviderError", "AIProviderNotConfigured", "Role",
]
