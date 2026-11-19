"""Qwen provider (Alibaba Cloud Model Studio / DashScope — região UE).

Chamada HTTP direta ao protocolo nativo DashScope (o mesmo que o SDK
`dashscope.MultiModalConversation.call` usa), via `httpx` já presente em
requirements.txt — zero dependência nova, compatível aarch64.

Endpoint : {QWEN_BASE_URL}/services/aigc/multimodal-generation/generation
Base UE  : https://eu-central-1.maas.qwencloudapi.com/api/v1 (default)
Auth     : Authorization: Bearer $DASHSCOPE_API_KEY  (só em Emergent Secrets)

Variáveis de ambiente:
  - DASHSCOPE_API_KEY   (obrigatória; sem ela o provedor fica desativado)
  - QWEN_BASE_URL       (opcional; default região UE Frankfurt)
  - QWEN_MODEL          (opcional; default `qwen3.8-max`)
  - QWEN_MODEL_FAST     (opcional; default `qwen3.8-27b`)
  - QWEN_TIMEOUT        (opcional; segundos, default 90)

Suporta texto + imagens (URL https ou data URL base64) — útil para plantas.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from engines.ai_providers.base import (
    AIProviderError,
    AIProviderNotConfigured,
    AIResponse,
    AIUsage,
)

logger = logging.getLogger("ai.qwen")

ENV_KEY = "DASHSCOPE_API_KEY"
ENV_BASE = "QWEN_BASE_URL"
ENV_MODEL = "QWEN_MODEL"
ENV_MODEL_FAST = "QWEN_MODEL_FAST"
ENV_TIMEOUT = "QWEN_TIMEOUT"

DEFAULT_BASE = "https://eu-central-1.maas.qwencloudapi.com/api/v1"
DEFAULT_MODEL = "qwen3.8-max"
DEFAULT_MODEL_FAST = "qwen3.8-27b"
MULTIMODAL_PATH = "/services/aigc/multimodal-generation/generation"

_RETRIABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _part_text(text: str) -> dict[str, Any]:
    return {"text": text}


def _content_text(content: Any) -> str:
    """Extrai texto de `message.content` (lista de partes ou string)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            p.get("text", "") for p in content if isinstance(p, dict)
        )
    return ""


class QwenProvider:
    name = "qwen"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        role: str = "main",  # "main" | "fast"
        transport: httpx.AsyncBaseTransport | None = None,  # testes
    ):
        self.api_key = (api_key or os.environ.get(ENV_KEY) or "").strip()
        if not self.api_key:
            raise AIProviderNotConfigured(self.name, ENV_KEY)
        if role == "fast":
            default_model = os.environ.get(ENV_MODEL_FAST) or DEFAULT_MODEL_FAST
        else:
            default_model = os.environ.get(ENV_MODEL) or DEFAULT_MODEL
        self.model = (model or default_model).strip()
        self.base_url = (
            base_url or os.environ.get(ENV_BASE) or DEFAULT_BASE
        ).strip().rstrip("/")
        try:
            self.timeout = float(os.environ.get(ENV_TIMEOUT) or 90)
        except ValueError:
            self.timeout = 90.0
        self.role = role
        self._transport = transport

    # ------------------------------------------------------------------
    def build_messages(
        self,
        *,
        prompt: str,
        system: str | None,
        history: list[dict[str, Any]] | None,
        images: list[str] | None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": [_part_text(system)]})
        for m in history or []:
            role = m.get("role")
            content = (m.get("content") or "").strip() if isinstance(
                m.get("content"), str) else ""
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": [_part_text(content)]})
        user_parts: list[dict[str, Any]] = [
            {"image": img} for img in (images or []) if img
        ]
        user_parts.append(_part_text(prompt))
        messages.append({"role": "user", "content": user_parts})
        return messages

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
        images: list[str] | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        imgs = list(images or [])
        if image_url:
            imgs.insert(0, image_url)

        parameters: dict[str, Any] = {
            "result_format": "message",
            "max_tokens": int(max_tokens),
            "temperature": float(temperature),
        }
        if json_mode:
            parameters["response_format"] = {"type": "json_object"}

        body = {
            "model": self.model,
            "input": {"messages": self.build_messages(
                prompt=prompt, system=system, history=history, images=imgs)},
            "parameters": parameters,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = self.base_url + MULTIMODAL_PATH

        t0 = time.time()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self._transport,
            ) as client:
                resp = await client.post(url, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise AIProviderError(
                "Qwen timeout.", provider=self.name, code="timeout",
                retriable=True,
            ) from e
        except httpx.HTTPError as e:
            raise AIProviderError(
                f"Qwen rede: {type(e).__name__}", provider=self.name,
                code="network", retriable=True,
            ) from e
        latency_ms = int((time.time() - t0) * 1000)

        try:
            payload = resp.json()
        except ValueError:
            payload = {}

        if resp.status_code >= 400:
            code = str(payload.get("code") or f"http_{resp.status_code}")
            msg = str(payload.get("message") or "")[:200]
            raise AIProviderError(
                f"Qwen API {resp.status_code} {code}: {msg}",
                provider=self.name, code=code, status_code=resp.status_code,
                retriable=resp.status_code in _RETRIABLE_STATUS,
                details={"request_id": payload.get("request_id")},
            )

        choices = ((payload.get("output") or {}).get("choices") or [])
        if not choices:
            raise AIProviderError(
                "Qwen resposta sem choices.", provider=self.name,
                code="empty_choices", retriable=True,
                details={"request_id": payload.get("request_id")},
            )
        choice = choices[0] or {}
        text = _content_text((choice.get("message") or {}).get("content")).strip()

        u = payload.get("usage") or {}
        inp = int(u.get("input_tokens") or 0)
        out = int(u.get("output_tokens") or 0)
        usage = AIUsage(
            input_tokens=inp, output_tokens=out,
            total_tokens=int(u.get("total_tokens") or (inp + out)),
        )
        return AIResponse(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=latency_ms,
            usage=usage,
            request_id=payload.get("request_id"),
            stop_reason=choice.get("finish_reason"),
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


__all__ = ["QwenProvider"]
