"""Perplexity Agent API provider (migração Sonar → Agent API, 2026).

Endpoint: `POST https://api.perplexity.ai/v1/responses`
Model default: `perplexity/sonar` (via env `PERPLEXITY_MODEL`).

Diferenças chave vs Sonar API antigo:
  - `messages` → `input`
  - `max_tokens` → `max_output_tokens`
  - citações via tool `web_search`; `output[]` contém item `type:"search_results"`

Doc: https://docs.perplexity.ai/docs/agent-api/
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
    Citation,
)

logger = logging.getLogger("ai.perplexity")

ENV_KEY = "PERPLEXITY_API_KEY"
ENV_MODEL = "PERPLEXITY_MODEL"
DEFAULT_MODEL = "perplexity/sonar"
API_URL = "https://api.perplexity.ai/v1/responses"


class PerplexityProvider:
    name = "perplexity"

    def __init__(self, *, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or os.environ.get(ENV_KEY) or "").strip()
        if not self.api_key:
            raise AIProviderNotConfigured(self.name, ENV_KEY)
        raw = (model or os.environ.get(ENV_MODEL) or DEFAULT_MODEL).strip()
        # Compat: aceita "sonar-reasoning" antigo e normaliza
        if "/" not in raw:
            raw = f"perplexity/{raw.replace('-reasoning','').replace('-pro','') or 'sonar'}"
        self.model = raw

    async def ask(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,  # ignorado pela Agent API
        history: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        inp: list[dict[str, str]] = []
        if system:
            inp.append({"role": "system", "content": system})
        if history:
            for m in history:
                role = m.get("role")
                content = (m.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    inp.append({"role": role, "content": content})
        inp.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self.model,
            "input": inp,
            "max_output_tokens": max_tokens,
            "tools": [{"type": "web_search"}],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(API_URL, json=body, headers=headers)
        except httpx.TimeoutException as e:
            raise AIProviderError("Perplexity timeout.",
                                  provider=self.name, code="timeout", retriable=True) from e
        except httpx.HTTPError as e:
            raise AIProviderError(f"Perplexity HTTP error: {type(e).__name__}",
                                  provider=self.name, code="http_error", retriable=True) from e
        latency_ms = int((time.time() - t0) * 1000)

        if r.status_code >= 400:
            retriable = r.status_code in (408, 409, 429, 500, 502, 503, 504)
            raise AIProviderError(
                f"Perplexity {r.status_code}: {r.text[:200]}",
                provider=self.name, code=f"http_{r.status_code}",
                status_code=r.status_code, retriable=retriable,
            )

        try:
            data = r.json()
        except Exception as e:  # noqa: BLE001
            raise AIProviderError(f"Perplexity resposta não-JSON: {type(e).__name__}",
                                  provider=self.name, code="invalid_json", retriable=True) from e

        # Agent API: output[] array com items {type, ...}
        # - type="message" → content[].text (texto final)
        # - type="search_results" → results[].{url,title,snippet}
        text_parts: list[str] = []
        citations: list[Citation] = []
        output = data.get("output") or []
        for item in output:
            itype = item.get("type")
            if itype == "message":
                for c in (item.get("content") or []):
                    if c.get("type") in ("output_text", "text"):
                        t = c.get("text") or ""
                        if t:
                            text_parts.append(t)
            elif itype in ("search_results", "web_search_results", "citations"):
                for res in (item.get("results") or item.get("citations") or []):
                    citations.append(Citation(
                        url=res.get("url") or "",
                        title=res.get("title"),
                        snippet=res.get("snippet") or res.get("content"),
                    ))

        # Fallback top-level `citations` (algumas versões ainda devolvem)
        if not citations:
            for cit in (data.get("citations") or []):
                if isinstance(cit, str):
                    citations.append(Citation(url=cit))
                elif isinstance(cit, dict):
                    citations.append(Citation(
                        url=cit.get("url") or "", title=cit.get("title"),
                        snippet=cit.get("snippet"),
                    ))

        # Fallback output_text root (OpenAI-compat helper)
        text = "\n".join(text_parts).strip() or (data.get("output_text") or "").strip()

        u = data.get("usage") or {}
        usage = AIUsage(
            input_tokens=u.get("input_tokens", u.get("prompt_tokens", 0)) or 0,
            output_tokens=u.get("output_tokens", u.get("completion_tokens", 0)) or 0,
            total_tokens=u.get("total_tokens", 0) or 0,
        )

        return AIResponse(
            text=text, provider=self.name, model=data.get("model") or self.model,
            latency_ms=latency_ms, usage=usage, citations=citations,
            request_id=data.get("id"), stop_reason=data.get("status"),
        )

    async def ping(self) -> dict[str, Any]:
        try:
            r = await self.ask(prompt="What is RGEU?", system=None,
                               max_tokens=80, temperature=0.0)
            return {
                "ok": not r.is_empty, "provider": self.name,
                "model": r.model, "latency_ms": r.latency_ms,
                "citations": len(r.citations),
            }
        except AIProviderError as e:
            return {"ok": False, "provider": self.name, "error": e.code,
                    "detail": str(e)[:200]}
