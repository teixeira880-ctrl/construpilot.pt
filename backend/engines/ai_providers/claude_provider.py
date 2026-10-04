"""Anthropic Claude provider.

Model default: `claude-opus-5-5` (via env `CLAUDE_MODEL`).
Usa o SDK oficial `anthropic` com cliente async.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

from engines.ai_providers.base import (
    AIProviderError,
    AIProviderNotConfigured,
    AIResponse,
    AIUsage,
)

logger = logging.getLogger("ai.claude")

ENV_KEY = "ANTHROPIC_API_KEY"
ENV_MODEL = "CLAUDE_MODEL"
ENV_EFFORT = "CLAUDE_EFFORT"
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"  # para gerações 5.5+ que suportam output_config.effort
# Modelos recentes que exigem `output_config.effort` em vez de temperature/thinking clássicos.
_NEW_GEN_PREFIXES = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-5", "claude-sonnet-5")


class ClaudeProvider:
    name = "claude"

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or os.environ.get(ENV_KEY) or "").strip()
        self.model = (model or os.environ.get(ENV_MODEL) or DEFAULT_MODEL).strip()
        self.effort = (os.environ.get(ENV_EFFORT) or DEFAULT_EFFORT).strip().lower()
        if not self.api_key:
            raise AIProviderNotConfigured(self.name, ENV_KEY)

    @property
    def _is_new_gen(self) -> bool:
        """Opus/Sonnet 5+ exigem `output_config.effort` em vez de temperature."""
        return any(self.model.startswith(p) for p in _NEW_GEN_PREFIXES)

    def _client(self):
        # Import lazy: só carrega o SDK se o provedor for efetivamente usado.
        try:
            from anthropic import AsyncAnthropic
        except ImportError as e:
            raise AIProviderError(
                "SDK `anthropic` não instalado — adicionar a requirements.txt.",
                provider=self.name, code="sdk_missing", retriable=False,
            ) from e
        return AsyncAnthropic(api_key=self.api_key)

    async def ask(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        history: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        from anthropic import APIError, APIStatusError

        messages = []
        if history:
            for m in history:
                role = m.get("role")
                content = (m.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        client = self._client()
        # Modelos 5.5+ (opus/sonnet) usam `output_config.effort` e NÃO suportam temperature.
        # Para gerações anteriores: `temperature` continua a passar via extra_body.
        create_kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system or "",
            "messages": messages,
        }
        send_temperature = (temperature is not None) and not self._is_new_gen
        if self._is_new_gen:
            # Garantir resposta curta e sem thinking: effort low por default.
            create_kwargs["extra_body"] = {"output_config": {"effort": self.effort}}
        elif send_temperature:
            create_kwargs["extra_body"] = {"temperature": temperature}
        try:
            try:
                msg = await client.messages.create(**create_kwargs)
            except APIStatusError as e:
                detail = str(e).lower()
                if (getattr(e, "status_code", None) == 400 and send_temperature
                        and "temperature" in detail and "deprecat" in detail):
                    create_kwargs.pop("extra_body", None)
                    msg = await client.messages.create(**create_kwargs)
                else:
                    raise
        except APIStatusError as e:
            status = getattr(e, "status_code", None)
            retriable = status in (408, 409, 425, 429, 500, 502, 503, 504)
            raise AIProviderError(
                f"Claude API {status}: {str(e)[:200]}",
                provider=self.name, code=f"http_{status}",
                status_code=status, retriable=retriable,
            ) from e
        except APIError as e:
            raise AIProviderError(
                f"Claude SDK error: {type(e).__name__}: {str(e)[:200]}",
                provider=self.name, code="sdk_error", retriable=True,
            ) from e
        except Exception as e:  # noqa: BLE001
            raise AIProviderError(
                f"Claude unexpected: {type(e).__name__}",
                provider=self.name, code="unexpected", retriable=True,
            ) from e
        latency_ms = int((time.time() - t0) * 1000)

        text_parts: list[str] = []
        for block in msg.content or []:
            if getattr(block, "type", "") == "text":
                text_parts.append(getattr(block, "text", "") or "")
        text = "".join(text_parts).strip()

        usage = AIUsage(
            input_tokens=getattr(msg.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(msg.usage, "output_tokens", 0) or 0,
        )
        usage.total_tokens = usage.input_tokens + usage.output_tokens

        return AIResponse(
            text=text,
            provider=self.name,
            model=msg.model or self.model,
            latency_ms=latency_ms,
            usage=usage,
            request_id=getattr(msg, "id", None),
            stop_reason=msg.stop_reason,
        )

    async def ping(self) -> dict[str, Any]:
        """Health leve: 1 token, prompt mínimo. Latência típica < 1 s."""
        try:
            r = await self.ask(prompt="OK", system="Reply 'ok'.",
                               max_tokens=16, temperature=0.0)
            return {
                "ok": not r.is_empty, "provider": self.name,
                "model": r.model, "latency_ms": r.latency_ms,
            }
        except AIProviderError as e:
            return {"ok": False, "provider": self.name, "error": e.code,
                    "detail": str(e)[:200]}
