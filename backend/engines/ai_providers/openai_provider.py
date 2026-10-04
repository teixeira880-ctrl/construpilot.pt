"""OpenAI provider (Chat Completions API).

Models default:
  - Coach / plantas raciocínio: `OPENAI_MODEL_COACH` (default `gpt-4o`).
  - Visão (plantas raster): `OPENAI_MODEL_VISION` (default `gpt-4o`).
  - Operações rápidas: `OPENAI_MODEL_FAST` (default `gpt-4o-mini`).

Suporta JSON mode (`response_format={"type":"json_object"}`) via kwarg.
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

logger = logging.getLogger("ai.openai")

ENV_KEY = "OPENAI_API_KEY"
ENV_MODEL_COACH = "OPENAI_MODEL_COACH"
ENV_MODEL_FAST = "OPENAI_MODEL_FAST"
ENV_MODEL_VISION = "OPENAI_MODEL_VISION"


class OpenAIProvider:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        role: str = "coach",  # "coach" | "fast" | "vision"
    ):
        self.api_key = (api_key or os.environ.get(ENV_KEY) or "").strip()
        if not self.api_key:
            raise AIProviderNotConfigured(self.name, ENV_KEY)
        env_var = {
            "coach": ENV_MODEL_COACH,
            "fast": ENV_MODEL_FAST,
            "vision": ENV_MODEL_VISION,
        }.get(role, ENV_MODEL_COACH)
        default = {"fast": "gpt-4o-mini"}.get(role, "gpt-4o")
        self.model = (model or os.environ.get(env_var) or default).strip()
        self.role = role

    def _client(self):
        try:
            from openai import AsyncOpenAI
        except ImportError as e:
            raise AIProviderError(
                "SDK `openai` não instalado — adicionar a requirements.txt.",
                provider=self.name, code="sdk_missing", retriable=False,
            ) from e
        return AsyncOpenAI(api_key=self.api_key)

    async def ask(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        history: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        image_url: str | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        from openai import APIError, APIStatusError

        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        if history:
            for m in history:
                role = m.get("role")
                content = (m.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        if image_url:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            })
        else:
            messages.append({"role": "user", "content": prompt})

        call_kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            call_kwargs["response_format"] = {"type": "json_object"}

        t0 = time.time()
        client = self._client()
        try:
            resp = await client.chat.completions.create(**call_kwargs)
        except APIStatusError as e:
            status = getattr(e, "status_code", None)
            retriable = status in (408, 409, 425, 429, 500, 502, 503, 504)
            raise AIProviderError(
                f"OpenAI API {status}: {str(e)[:200]}",
                provider=self.name, code=f"http_{status}",
                status_code=status, retriable=retriable,
            ) from e
        except APIError as e:
            raise AIProviderError(
                f"OpenAI SDK error: {type(e).__name__}: {str(e)[:200]}",
                provider=self.name, code="sdk_error", retriable=True,
            ) from e
        except Exception as e:  # noqa: BLE001
            raise AIProviderError(
                f"OpenAI unexpected: {type(e).__name__}",
                provider=self.name, code="unexpected", retriable=True,
            ) from e
        latency_ms = int((time.time() - t0) * 1000)

        choice = (resp.choices or [None])[0]
        if choice is None:
            raise AIProviderError(
                "OpenAI resposta sem choices.",
                provider=self.name, code="empty_choices", retriable=True,
            )
        text = (choice.message.content or "").strip()
        stop_reason = choice.finish_reason

        u = resp.usage
        usage = AIUsage(
            input_tokens=getattr(u, "prompt_tokens", 0) or 0,
            output_tokens=getattr(u, "completion_tokens", 0) or 0,
            total_tokens=getattr(u, "total_tokens", 0) or 0,
        )

        return AIResponse(
            text=text,
            provider=self.name,
            model=resp.model or self.model,
            latency_ms=latency_ms,
            usage=usage,
            request_id=getattr(resp, "id", None),
            stop_reason=stop_reason,
        )

    async def ping(self) -> dict[str, Any]:
        try:
            r = await self.ask(prompt="OK", system="Reply 'ok'.",
                               max_tokens=5, temperature=0.0)
            return {
                "ok": not r.is_empty, "provider": self.name,
                "model": r.model, "latency_ms": r.latency_ms,
            }
        except AIProviderError as e:
            return {"ok": False, "provider": self.name, "error": e.code,
                    "detail": str(e)[:200]}
