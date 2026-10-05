"""Cliente Perplexity Plus — expande o `ai_router.perplexity` com:
  - ask estruturado (compare, norms, materials)
  - streaming SSE para chat
  - cache MongoDB TTL 24h
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, AsyncIterator

import httpx

from engines.ai_providers.router import ai_router
from engines.perplexity_plus.pplx_cache import cache_get, cache_set, cache_key
from engines.perplexity_plus.pplx_presets import PRESETS, preset_system

logger = logging.getLogger("pplx_plus.client")

API_URL = "https://api.perplexity.ai/v1/responses"
STREAM_URL = "https://api.perplexity.ai/v1/responses"  # Agent API suporta stream=true


def _extract_json(text: str) -> dict | None:
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


class PplxPlusClient:
    """Wrapper específico Perplexity Plus."""

    def _api_key(self) -> str:
        return (os.environ.get("PERPLEXITY_API_KEY") or "").strip()

    def is_configured(self) -> bool:
        return bool(self._api_key()) and ai_router.perplexity is not None

    # ------------------------------------------------------------------
    # Modos estruturados: compare / norms / materials
    # ------------------------------------------------------------------
    async def ask_structured(
        self,
        *,
        prompt: str,
        system: str,
        max_tokens: int = 1500,
        use_cache: bool = True,
    ) -> dict:
        """Pergunta JSON-structured com cache."""
        key = cache_key("ask_structured", prompt, system, max_tokens)
        if use_cache:
            cached = await cache_get(key)
            if cached:
                return {**cached, "cache": "HIT"}

        if not ai_router.perplexity:
            raise RuntimeError("Perplexity não configurado.")
        r = await ai_router.perplexity.ask(
            prompt=prompt, system=system,
            max_tokens=max_tokens, temperature=0.1,
        )
        payload = {
            "text": r.text,
            "parsed": _extract_json(r.text),
            "citations": [
                {"url": c.url, "title": c.title, "snippet": c.snippet}
                for c in (r.citations or [])
            ],
            "model": r.model,
            "latency_ms": r.latency_ms,
            "usage": {
                "input_tokens": r.usage.input_tokens,
                "output_tokens": r.usage.output_tokens,
            } if r.usage else None,
        }
        if use_cache:
            await cache_set(key, payload)
        return {**payload, "cache": "MISS"}

    # ------------------------------------------------------------------
    # Streaming SSE para chat
    # ------------------------------------------------------------------
    async def stream_chat(
        self,
        *,
        message: str,
        system: str,
        history: list[dict] | None = None,
    ) -> AsyncIterator[dict]:
        """Devolve async iterator com {delta|citations|done}."""
        if not self.is_configured():
            yield {"error": "Perplexity não configurado."}
            return

        api_key = self._api_key()
        model = (os.environ.get("PERPLEXITY_MODEL") or "sonar").strip()
        if "/" not in model:
            model = f"perplexity/{model.replace('-reasoning','').replace('-pro','') or 'sonar'}"

        inp: list[dict] = []
        if system:
            inp.append({"role": "system", "content": system})
        if history:
            for m in history:
                role = m.get("role")
                content = (m.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    inp.append({"role": role, "content": content})
        inp.append({"role": "user", "content": message})

        body = {
            "model": model,
            "input": inp,
            "stream": True,
            "max_output_tokens": 1200,
            "tools": [{"type": "web_search"}],
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        collected_citations: list[dict] = []
        model_seen = model
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                async with client.stream("POST", STREAM_URL, json=body, headers=headers) as r:
                    if r.status_code >= 400:
                        detail = await r.aread()
                        yield {"error": f"Perplexity {r.status_code}", "detail": detail.decode()[:200]}
                        return
                    async for line in r.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            data = json.loads(payload)
                        except Exception:
                            continue
                        model_seen = data.get("model") or model_seen
                        # Agent API SSE events: `response.output_text.delta` + `response.completed`
                        etype = data.get("type") or ""
                        if etype.endswith("output_text.delta") or etype == "response.output_text.delta":
                            delta = data.get("delta") or data.get("text") or ""
                            if delta:
                                yield {"delta": delta}
                        elif "output_text" in etype and data.get("delta"):
                            yield {"delta": data["delta"]}
                        # Fallback: alguns servers mandam choices legacy
                        choices = data.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            content = delta.get("content") or ""
                            if content:
                                yield {"delta": content}
                        # Search results / citations in output[]
                        if etype == "response.completed" or data.get("output"):
                            for item in (data.get("response") or data).get("output", []) or []:
                                if item.get("type") in ("search_results", "web_search_results"):
                                    for res in (item.get("results") or []):
                                        collected_citations.append({
                                            "url": res.get("url") or "",
                                            "title": res.get("title"),
                                        })
                        cites = data.get("citations") or []
                        if cites and not collected_citations:
                            for c in cites:
                                if isinstance(c, str):
                                    collected_citations.append({"url": c})
                                elif isinstance(c, dict):
                                    collected_citations.append({
                                        "url": c.get("url") or "", "title": c.get("title"),
                                    })
        except httpx.HTTPError as e:
            yield {"error": f"HTTP {type(e).__name__}"}
            return

        yield {"citations": collected_citations, "model": model_seen, "done": True}


pplx_plus_client = PplxPlusClient()
