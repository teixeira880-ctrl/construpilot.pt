"""Mocks do `AsyncLLMClient` para testes (sem rede, sem Claude live)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ScriptedResponse:
    """Uma resposta pré-definida devolvida pelo mock no turno N."""

    content: list[dict[str, Any]]
    stop_reason: str = "tool_use"
    usage: dict[str, int] = field(default_factory=lambda: {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    })


@dataclass
class MockLLMClient:
    """Cliente mock que devolve respostas pré-scriptadas em ordem.

    Após exaustar o script, devolve um `end_turn` neutro vazio.
    """

    script: list[ScriptedResponse] = field(default_factory=list)
    calls_received: list[dict[str, Any]] = field(default_factory=list)
    _index: int = 0

    async def create_message(
        self,
        *,
        model: str,
        system,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        self.calls_received.append({
            "model": model, "system": system, "tools": tools,
            "messages": messages, "max_tokens": max_tokens,
        })
        if self._index < len(self.script):
            resp = self.script[self._index]
            self._index += 1
            return {
                "stop_reason": resp.stop_reason,
                "content": resp.content,
                "usage": resp.usage,
            }
        return {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 10, "output_tokens": 5,
                      "cache_creation_input_tokens": 0,
                      "cache_read_input_tokens": 0},
        }


def tool_use_block(tool_use_id: str, name: str, input_: dict[str, Any]) -> dict[str, Any]:
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": input_}
