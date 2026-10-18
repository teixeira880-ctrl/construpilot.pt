"""Adaptador do SDK Anthropic ao `AsyncLLMClient` protocol usado pelo loop.

Isolado para que:
    - CI use `MockLLMClient` sem instalar a chave Anthropic.
    - Preview/prod use este wrapper directamente com `ANTHROPIC_API_KEY`.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class AnthropicNotConfigured(RuntimeError):
    """Chave ANTHROPIC_API_KEY ausente. Levantado em vez de crashar o backend."""


class AnthropicClient:
    """Wrapper fino sobre `AsyncAnthropic.messages.create` que normaliza o
    output para o formato esperado pelo loop (dict com stop_reason/content/usage)."""

    def __init__(self) -> None:
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
        if not key:
            raise AnthropicNotConfigured(
                "ANTHROPIC_API_KEY não definido no ambiente."
            )
        from anthropic import AsyncAnthropic
        self._client = AsyncAnthropic(api_key=key)

    async def create_message(
        self,
        *,
        model: str,
        system: list[dict[str, Any]] | str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        msg = await self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        # Normaliza para dict puro — fácil de serializar e testar.
        content_norm: list[dict[str, Any]] = []
        for b in (msg.content or []):
            btype = getattr(b, "type", None)
            if btype == "text":
                content_norm.append({"type": "text", "text": getattr(b, "text", "")})
            elif btype == "tool_use":
                content_norm.append({
                    "type": "tool_use",
                    "id": getattr(b, "id", ""),
                    "name": getattr(b, "name", ""),
                    "input": getattr(b, "input", {}),
                })
        usage = getattr(msg, "usage", None)
        usage_dict: dict[str, int] = {
            "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
            "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0) if usage else 0,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) if usage else 0,
        }
        return {
            "stop_reason": getattr(msg, "stop_reason", "end_turn") or "end_turn",
            "content": content_norm,
            "usage": usage_dict,
        }


def is_anthropic_available() -> bool:
    return bool((os.environ.get("ANTHROPIC_API_KEY") or "").strip())
