"""Client Perplexity partagé + cache Mongo.

- Utilise le SDK ``perplexity`` déjà présent (perplexityai==0.43.5).
- Cache 24h sur (question, filtres, preset) dans ``db.perplexity_cache``.
- Utilisable en mode réponse unique ou en streaming SSE (:func:`stream`).

Env : ``PERPLEXITY_API_KEY`` obligatoire.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import AsyncIterator

from core.db import db

_CACHE_TTL_SECONDS = 24 * 3600


def _cache_key(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def ensure_indexes() -> None:
    """À appeler au startup — TTL 24 h sur les entrées de cache."""
    await db.perplexity_cache.create_index("key", unique=True)
    await db.perplexity_cache.create_index(
        "expires_at", expireAfterSeconds=0
    )


def configured() -> bool:
    return bool(os.environ.get("PERPLEXITY_API_KEY"))


def _client():
    from perplexity import AsyncPerplexity
    return AsyncPerplexity(
        api_key=os.environ["PERPLEXITY_API_KEY"],
        max_retries=0,
        timeout=120.0,
    )


def _extract_citations(dump: dict) -> list[dict]:
    citations: list[dict] = []
    seen: set[str] = set()
    for item in dump.get("output") or []:
        if item.get("type") == "search_results":
            for x in item.get("results") or []:
                url = x.get("url")
                if url and url not in seen:
                    seen.add(url)
                    citations.append({
                        "url": url,
                        "title": x.get("title"),
                        "snippet": x.get("snippet"),
                        "kind": "search_result",
                    })
        for part in item.get("content") or []:
            for a in part.get("annotations") or []:
                url = a.get("url")
                if url and url not in seen:
                    seen.add(url)
                    citations.append({
                        "url": url,
                        "title": a.get("title"),
                        "kind": "url_citation",
                    })
    return citations


def _build_payload(
    *,
    question: str,
    instructions: str,
    search_context_size: str = "medium",
    max_results: int = 8,
    domain_filter: list[str] | None = None,
    preset: str = "medium",
    model: str | None = None,
    max_output_tokens: int = 1200,
) -> dict:
    tool: dict = {
        "type": "web_search",
        "search_context_size": search_context_size,
        "max_results": max_results,
    }
    if domain_filter:
        tool["search_domain_filter"] = domain_filter
    payload: dict = {
        "input": question,
        "instructions": instructions,
        "tools": [tool],
        "store": False,
        "max_output_tokens": max_output_tokens,
    }
    if model:
        payload["model"] = model
    else:
        payload["preset"] = preset
    return payload


async def ask(
    *,
    question: str,
    instructions: str,
    search_context_size: str = "medium",
    max_results: int = 8,
    domain_filter: list[str] | None = None,
    preset: str = "medium",
    model: str | None = None,
    max_output_tokens: int = 1200,
    use_cache: bool = True,
) -> dict:
    """Appel unique (non streamé). Renvoie ``{text, citations, cost_usd, cached, ...}``."""
    payload = _build_payload(
        question=question,
        instructions=instructions,
        search_context_size=search_context_size,
        max_results=max_results,
        domain_filter=domain_filter,
        preset=preset,
        model=model,
        max_output_tokens=max_output_tokens,
    )
    key = _cache_key(payload)

    if use_cache:
        hit = await db.perplexity_cache.find_one({"key": key})
        if hit:
            return {**hit["response"], "cached": True}

    client = _client()
    t0 = time.monotonic()
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            r = await client.responses.create(**payload)
            break
        except Exception as e:  # pragma: no cover - dépend du SDK
            last_err = e
            status = getattr(e, "status_code", None)
            if status in (429, 500, 502, 503, 504) and attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    else:
        raise last_err  # type: ignore[misc]

    dump = r.model_dump()
    usage = dump.get("usage") or {}
    cost = ((usage.get("cost") or {}).get("total_cost")) or 0.0
    result = {
        "text": r.output_text or "",
        "citations": _extract_citations(dump),
        "model": dump.get("model"),
        "cost_usd": float(cost),
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "status": dump.get("status"),
        "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens")},
        "cached": False,
    }

    if use_cache:
        expires_at = datetime.fromtimestamp(
            time.time() + _CACHE_TTL_SECONDS, tz=timezone.utc
        )
        try:
            await db.perplexity_cache.update_one(
                {"key": key},
                {"$set": {
                    "key": key,
                    "response": {k: v for k, v in result.items() if k != "cached"},
                    "expires_at": expires_at,
                    "created_at": datetime.now(timezone.utc),
                }},
                upsert=True,
            )
        except Exception:  # pragma: no cover
            # Best-effort : le cache n'est jamais bloquant
            pass

    return result


async def stream(
    *,
    question: str,
    instructions: str,
    search_context_size: str = "medium",
    max_results: int = 8,
    domain_filter: list[str] | None = None,
    preset: str = "medium",
    model: str | None = None,
    max_output_tokens: int = 1200,
) -> AsyncIterator[dict]:
    """Streaming SSE-friendly. Émet :
        {"type": "delta", "text": "..."}
        {"type": "citations", "citations": [...]}
        {"type": "done", "cost_usd": ..., "usage": {...}}
    """
    payload = _build_payload(
        question=question,
        instructions=instructions,
        search_context_size=search_context_size,
        max_results=max_results,
        domain_filter=domain_filter,
        preset=preset,
        model=model,
        max_output_tokens=max_output_tokens,
    )
    payload["stream"] = True

    client = _client()
    t0 = time.monotonic()
    full_text_parts: list[str] = []
    last_dump: dict = {}

    # SDK perplexityai 0.43.x : pas de responses.stream() — create(stream=True) renvoie un itérateur d'événements.
    events = await client.responses.create(**payload)
    async for event in events:
        et = getattr(event, "type", None) or ""
        if et.endswith("output_text.delta"):
            delta = getattr(event, "delta", "") or ""
            if delta:
                full_text_parts.append(delta)
                yield {"type": "delta", "text": delta}
        elif et == "response.completed":
            resp = getattr(event, "response", None)
            if resp is not None:
                last_dump = resp.model_dump()

    citations = _extract_citations(last_dump)
    if citations:
        yield {"type": "citations", "citations": citations}

    usage = last_dump.get("usage") or {}
    cost = ((usage.get("cost") or {}).get("total_cost")) or 0.0
    yield {
        "type": "done",
        "text": "".join(full_text_parts),
        "cost_usd": float(cost),
        "model": last_dump.get("model"),
        "latency_ms": int((time.monotonic() - t0) * 1000),
        "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens")},
    }
