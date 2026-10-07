"""Orquestrador de provedores: Claude (primário) → OpenAI (fallback) + Perplexity (web).

Decisões de design:
  - `coach_ask` tenta Claude. Se falhar com `retriable=True` ou devolver texto
    vazio, cai para OpenAI. Se ambos falharem, levanta `CoachUnavailableError`.
  - `needs_web_search` deteta palavras-chave de atualidade e chama Perplexity
    primeiro, injetando o output + citações no prompt do Claude.
  - Instâncias lazy: um provedor sem key não trava o processo; só não é usado.
  - `AI_PRIMARY_PROVIDER`/`AI_FALLBACK_PROVIDER` do env permitem overrides.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

from engines.ai_providers.base import (
    AIProviderError,
    AIProviderNotConfigured,
    AIResponse,
    Citation,
)

logger = logging.getLogger("ai.router")

# Palavras-chave que ativam Perplexity (web search prévia)
WEB_SEARCH_TRIGGERS = re.compile(
    r"\b("
    r"atualmente|hoje|última|últimas|recente|recentes|"
    r"preço|preços|cotação|cotações|inflação|iva atual|"
    r"notícia|notícias|nova lei|nova portaria|novo decreto|"
    r"em 202[4-9]|desde 202[4-9]|neste momento|agora"
    r")\b",
    re.IGNORECASE,
)


class CoachUnavailableError(RuntimeError):
    """Levantada quando TODOS os provedores Coach falham."""

    def __init__(
        self,
        message: str,
        *,
        primary_meta: dict,
        fallback_meta: dict | None = None,
    ):
        super().__init__(message)
        self.primary_meta = primary_meta
        self.fallback_meta = fallback_meta or {}


def needs_web_search(user_message: str) -> bool:
    return bool(WEB_SEARCH_TRIGGERS.search(user_message or ""))


class AIRouter:
    """Instancia provedores lazy — ignora os que faltam key."""

    def __init__(self):
        self._gemini = None
        self._claude = None
        self._openai_coach = None
        self._openai_fast = None
        self._openai_vision = None
        self._perplexity = None
        self._loaded = False

    def _lazy_load(self) -> None:
        if self._loaded:
            return
        # Gemini (NOVO PRIMÁRIO global para Coach/BTP/Plans Pro)
        try:
            from engines.ai_providers.gemini_provider import GeminiProvider
            self._gemini = GeminiProvider()
            logger.info("router: gemini ready (model=%s)", self._gemini.model)
        except AIProviderNotConfigured as e:
            logger.info("router: gemini not configured (%s)", e.code)
        except Exception as e:  # noqa: BLE001
            logger.warning("router: gemini init failed: %s", type(e).__name__)
        # Claude
        try:
            from engines.ai_providers.claude_provider import ClaudeProvider
            self._claude = ClaudeProvider()
            logger.info("router: claude ready")
        except AIProviderNotConfigured as e:
            logger.info("router: claude not configured (%s)", e.code)
        except Exception as e:  # noqa: BLE001
            logger.warning("router: claude init failed: %s", type(e).__name__)
        # OpenAI (coach + fast + vision)
        for role, attr in (("coach", "_openai_coach"),
                           ("fast", "_openai_fast"),
                           ("vision", "_openai_vision")):
            try:
                from engines.ai_providers.openai_provider import OpenAIProvider
                setattr(self, attr, OpenAIProvider(role=role))
            except AIProviderNotConfigured:
                pass
            except Exception as e:  # noqa: BLE001
                logger.warning("router: openai/%s init failed: %s", role, type(e).__name__)
        if self._openai_coach:
            logger.info("router: openai ready")
        # Perplexity
        try:
            from engines.ai_providers.perplexity_provider import PerplexityProvider
            self._perplexity = PerplexityProvider()
            logger.info("router: perplexity ready")
        except AIProviderNotConfigured:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning("router: perplexity init failed: %s", type(e).__name__)
        self._loaded = True

    def reset(self) -> None:
        """Força recarregamento (útil após rotação .env)."""
        self._gemini = None
        self._claude = self._openai_coach = self._openai_fast = None
        self._openai_vision = self._perplexity = None
        self._loaded = False

    # ------------------------------------------------------------------
    # Acessores públicos (podem devolver None se não configurado)
    # ------------------------------------------------------------------
    @property
    def gemini(self):
        self._lazy_load()
        return self._gemini

    @property
    def claude(self):
        self._lazy_load()
        return self._claude

    @property
    def openai_coach(self):
        self._lazy_load()
        return self._openai_coach

    @property
    def openai_fast(self):
        self._lazy_load()
        return self._openai_fast

    @property
    def openai_vision(self):
        self._lazy_load()
        return self._openai_vision

    @property
    def perplexity(self):
        self._lazy_load()
        return self._perplexity

    # ------------------------------------------------------------------
    # Coach: Claude → OpenAI
    # ------------------------------------------------------------------
    async def coach_ask(
        self,
        *,
        prompt: str,
        system: str,
        history: list[dict[str, Any]] | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.3,
        enrich_with_web: bool = False,
    ) -> AIResponse:
        """Coach com Claude primário, OpenAI fallback, Perplexity enrichment.

        Levanta `CoachUnavailableError` se ambos os provedores Coach falharem.
        """
        self._lazy_load()

        # 1. Web enrichment opcional (Perplexity primeiro)
        web_citations: list[Citation] = []
        web_snippet: str | None = None
        if enrich_with_web and self._perplexity:
            try:
                px = await self._perplexity.ask(
                    prompt=prompt, system=None,
                    max_tokens=400, temperature=0.1,
                )
                if not px.is_empty:
                    web_snippet = px.text[:1200]
                    web_citations = px.citations
                    logger.info("web enrichment ok: %d citations", len(web_citations))
            except AIProviderError as e:
                logger.info("web enrichment skipped: %s", e.code)

        enriched_prompt = prompt
        if web_snippet:
            enriched_prompt = (
                f"[CONTEXTO_WEB_RECENTE]\n{web_snippet}\n\n"
                f"[CITAÇÕES]\n" + "\n".join(f"- {c.url}" for c in web_citations[:5])
                + f"\n\n{prompt}"
            )

        primary_meta: dict[str, Any] = {}
        fallback_meta: dict[str, Any] = {}
        secondary_meta: dict[str, Any] = {}

        # 2. Primary: Gemini (novo, Fase 1b)
        if self._gemini:
            try:
                r = await self._gemini.ask(
                    prompt=enriched_prompt, system=system,
                    max_tokens=max_tokens, temperature=temperature,
                    history=history,
                )
                primary_meta = {
                    "provider": r.provider, "model": r.model,
                    "latency_ms": r.latency_ms, "ok": not r.is_empty,
                    "stop_reason": r.stop_reason,
                }
                if not r.is_empty:
                    if web_citations:
                        r.citations = web_citations
                    return r
                primary_meta["error"] = "empty_text"
            except AIProviderError as e:
                primary_meta = e.to_meta()
                logger.info(
                    "gemini failed: %s (retriable=%s)", e.code, e.retriable,
                )
        else:
            primary_meta = {"provider": "gemini", "error": "not_configured"}

        # 3. Fallback 1: Claude
        if self._claude:
            try:
                r = await self._claude.ask(
                    prompt=enriched_prompt, system=system,
                    max_tokens=max_tokens, temperature=temperature,
                    history=history,
                )
                secondary_meta = {
                    "provider": r.provider, "model": r.model,
                    "latency_ms": r.latency_ms, "ok": not r.is_empty,
                    "stop_reason": r.stop_reason,
                }
                if not r.is_empty:
                    if web_citations:
                        r.citations = web_citations
                    return r
                secondary_meta["error"] = "empty_text"
            except AIProviderError as e:
                secondary_meta = e.to_meta()
                logger.info("claude fallback failed: %s", e.code)
        else:
            secondary_meta = {"provider": "claude", "error": "not_configured"}

        # 4. Fallback 2: OpenAI
        if self._openai_coach:
            try:
                r = await self._openai_coach.ask(
                    prompt=enriched_prompt, system=system,
                    max_tokens=max_tokens, temperature=temperature,
                    history=history,
                )
                fallback_meta = {
                    "provider": r.provider, "model": r.model,
                    "latency_ms": r.latency_ms, "ok": not r.is_empty,
                    "stop_reason": r.stop_reason,
                }
                if not r.is_empty:
                    if web_citations:
                        r.citations = web_citations
                    return r
                fallback_meta["error"] = "empty_text"
            except AIProviderError as e:
                fallback_meta = e.to_meta()
                logger.warning("openai fallback failed: %s", e.code)
        else:
            fallback_meta = {"provider": "openai", "error": "not_configured"}

        # 5. Todos falharam
        raise CoachUnavailableError(
            "Coach IA indisponível (Gemini + Claude + OpenAI falharam).",
            primary_meta={**primary_meta, "secondary": secondary_meta},
            fallback_meta=fallback_meta,
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------
    async def health(self, *, ping: bool = False) -> dict[str, Any]:
        """Status dos 4 provedores. Se `ping=True`, faz chamada real leve."""
        self._lazy_load()
        out: dict[str, Any] = {
            "primary": os.environ.get("AI_PRIMARY_PROVIDER", "gemini"),
            "fallback": os.environ.get("AI_FALLBACK_PROVIDER", "claude"),
            "fallback_2": os.environ.get("AI_FALLBACK2_PROVIDER", "openai"),
            "web_search": os.environ.get("AI_WEB_SEARCH_PROVIDER", "perplexity"),
            "providers": {},
        }
        for name, inst in (
            ("gemini", self._gemini),
            ("claude", self._claude),
            ("openai", self._openai_coach),
            ("perplexity", self._perplexity),
        ):
            if not inst:
                out["providers"][name] = {"configured": False, "ok": False}
                continue
            entry: dict[str, Any] = {"configured": True, "model": inst.model}
            if ping:
                entry.update(await inst.ping())
            out["providers"][name] = entry
        return out


# Singleton global (lazy)
ai_router = AIRouter()


__all__ = [
    "ai_router", "AIRouter",
    "CoachUnavailableError", "needs_web_search",
]
