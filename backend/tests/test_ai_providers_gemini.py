"""Testes do `GeminiProvider` e integração na cascata do router.

Cobre:
    * Formato correcto do payload (systemInstruction, inline_data,
      responseSchema).
    * Mapeamento de HTTP status → `AIProviderError` tipado.
    * Fallback no `coach_ask`: Gemini 429 → Claude; Gemini 401 → Claude.
    * Teste de integração REAL (`@pytest.mark.integration`) marcado para
      skip se `GEMINI_API_KEY` ausente.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.ai_providers.base import (  # noqa: E402
    AIProviderError,
    AIProviderNotConfigured,
    AIResponse,
)
from engines.ai_providers.gemini_provider import (  # noqa: E402
    GeminiProvider,
    _redact_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fake_httpx_response(status: int, body: dict) -> httpx.Response:
    import json as _json
    return httpx.Response(
        status_code=status,
        content=_json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("POST", "https://x"),
    )


def _ok_payload(text: str = "ok") -> dict:
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": text}]},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 2,
            "totalTokenCount": 7,
        },
        "modelVersion": "gemini-3.1-pro-preview",
    }


# ---------------------------------------------------------------------------
# Config / init
# ---------------------------------------------------------------------------
class TestInit:
    def test_sem_key_levanta_not_configured(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        with pytest.raises(AIProviderNotConfigured):
            GeminiProvider()

    def test_com_key_ok(self):
        p = GeminiProvider(api_key="AQ.fake")
        assert p.name == "gemini"
        assert p.model  # tem default

    def test_model_override(self):
        p = GeminiProvider(api_key="AQ.fake", model="gemini-flash-latest")
        assert p.model == "gemini-flash-latest"


class TestRedact:
    def test_redact_aq_key(self):
        assert _redact_key("erro com AQ.Ab8xYz123") == "erro com <REDACTED>"

    def test_redact_aizasy_key(self):
        assert _redact_key("fail AIzaSyFakekey123") == "fail <REDACTED>"

    def test_nao_altera_texto_sem_key(self):
        assert _redact_key("texto normal") == "texto normal"


# ---------------------------------------------------------------------------
# Build payload
# ---------------------------------------------------------------------------
class TestBuildContents:
    def test_system_vai_para_systemInstruction(self):
        # Teste indirecto via mock de httpx: inspeccionamos o payload enviado.
        p = GeminiProvider(api_key="AQ.fake")
        contents = p._build_contents(
            prompt="olá", history=None, image_data_uri=None,
        )
        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        assert contents[0]["parts"][-1]["text"] == "olá"

    def test_history_traduz_assistant_para_model(self):
        p = GeminiProvider(api_key="AQ.fake")
        contents = p._build_contents(
            prompt="agora",
            history=[
                {"role": "user", "content": "ola"},
                {"role": "assistant", "content": "resposta"},
            ],
            image_data_uri=None,
        )
        assert contents[0]["role"] == "user"
        assert contents[1]["role"] == "model"
        assert contents[-1]["parts"][-1]["text"] == "agora"

    def test_imagem_data_uri_vira_inline_data(self):
        p = GeminiProvider(api_key="AQ.fake")
        uri = "data:image/png;base64,iVBORw0KGgo="
        contents = p._build_contents(
            prompt="descreve", history=None, image_data_uri=uri,
        )
        parts = contents[0]["parts"]
        inline = next(p for p in parts if "inline_data" in p)
        assert inline["inline_data"]["mime_type"] == "image/png"
        assert inline["inline_data"]["data"] == "iVBORw0KGgo="


# ---------------------------------------------------------------------------
# ask() — mocks httpx
# ---------------------------------------------------------------------------
@pytest.mark.anyio
class TestAsk:
    async def test_resposta_200_devolve_ai_response(self):
        p = GeminiProvider(api_key="AQ.fake")

        async def _post(self, *a, **kw):
            return _fake_httpx_response(200, _ok_payload("ola"))

        with patch("httpx.AsyncClient.post", _post):
            r = await p.ask(prompt="x", system="sys", max_tokens=10, temperature=0.0)
        assert r.text == "ola"
        assert r.provider == "gemini"
        assert r.model == "gemini-3.1-pro-preview"
        assert r.usage.total_tokens == 7

    async def test_system_passa_via_systemInstruction(self):
        p = GeminiProvider(api_key="AQ.fake")
        captured: dict = {}

        async def _post(self, url, headers=None, json=None, **kw):
            captured["json"] = json
            captured["headers"] = headers
            return _fake_httpx_response(200, _ok_payload())

        with patch("httpx.AsyncClient.post", _post):
            await p.ask(prompt="x", system="PT-PT sys", max_tokens=5, temperature=0.0)

        assert "systemInstruction" in captured["json"]
        assert captured["json"]["systemInstruction"]["parts"][0]["text"] == "PT-PT sys"
        # Confirma header x-goog-api-key (não Authorization)
        assert captured["headers"]["x-goog-api-key"] == "AQ.fake"
        assert "Authorization" not in captured["headers"]

    async def test_response_schema_activa_json_mime(self):
        p = GeminiProvider(api_key="AQ.fake")
        captured: dict = {}

        async def _post(self, url, headers=None, json=None, **kw):
            captured["json"] = json
            return _fake_httpx_response(200, _ok_payload('{"a":1}'))

        with patch("httpx.AsyncClient.post", _post):
            await p.ask(
                prompt="x", system=None, max_tokens=5, temperature=0.0,
                response_schema={"type": "object", "properties": {"a": {"type": "integer"}}},
            )

        gen = captured["json"]["generationConfig"]
        assert gen["responseMimeType"] == "application/json"
        assert "responseSchema" in gen

    async def test_401_levanta_erro_nao_retriable(self):
        p = GeminiProvider(api_key="AQ.fake")

        async def _post(self, *a, **kw):
            return _fake_httpx_response(401, {
                "error": {"message": "API_KEY_SERVICE_BLOCKED",
                          "status": "UNAUTHENTICATED"}
            })

        with patch("httpx.AsyncClient.post", _post):
            with pytest.raises(AIProviderError) as exc:
                await p.ask(prompt="x", system=None, max_tokens=5, temperature=0.0)
        assert exc.value.status_code == 401
        assert exc.value.retriable is False

    async def test_429_levanta_erro_retriable(self):
        p = GeminiProvider(api_key="AQ.fake")

        async def _post(self, *a, **kw):
            return _fake_httpx_response(429, {"error": {"message": "rate limit"}})

        with patch("httpx.AsyncClient.post", _post):
            with pytest.raises(AIProviderError) as exc:
                await p.ask(prompt="x", system=None, max_tokens=5, temperature=0.0)
        assert exc.value.status_code == 429
        assert exc.value.retriable is True

    async def test_erro_response_redacta_chave(self):
        p = GeminiProvider(api_key="AQ.chaveSecreta123")

        async def _post(self, *a, **kw):
            return _fake_httpx_response(500, {
                "error": {"message": "falha com key AQ.chaveSecreta123 inside"}
            })

        with patch("httpx.AsyncClient.post", _post):
            try:
                await p.ask(prompt="x", system=None, max_tokens=5, temperature=0.0)
            except AIProviderError as e:
                assert "AQ.chaveSecreta123" not in str(e)
                assert "REDACTED" in str(e)

    async def test_timeout_levanta_retriable(self):
        p = GeminiProvider(api_key="AQ.fake", timeout=0.001)

        async def _post(self, *a, **kw):
            raise httpx.TimeoutException("timeout")

        with patch("httpx.AsyncClient.post", _post):
            with pytest.raises(AIProviderError) as exc:
                await p.ask(prompt="x", system=None, max_tokens=5, temperature=0.0)
        assert exc.value.retriable is True
        assert exc.value.code == "timeout"


# ---------------------------------------------------------------------------
# Router cascade: Gemini → Claude → OpenAI
# ---------------------------------------------------------------------------
@pytest.mark.anyio
class TestRouterCascade:
    """Verifica a cascata no `coach_ask` do router global.

    Importamos AIRouter fresco para controlar o lazy_load.
    """

    async def _make_router(self, *, gemini_ok=True, gemini_err=None,
                           claude_ok=True, openai_ok=True):
        from engines.ai_providers.router import AIRouter

        router = AIRouter()
        router._loaded = True  # bypass lazy_load

        class _Prov:
            def __init__(self, name, text="resposta", err=None, model="m"):
                self.name = name
                self.model = model
                self._text = text
                self._err = err
                self.ask = AsyncMock(side_effect=self._do)

            async def _do(self, **kw):
                if self._err:
                    raise self._err
                return AIResponse(text=self._text, provider=self.name,
                                  model=self.model)

        router._gemini = _Prov("gemini", err=gemini_err) if gemini_ok or gemini_err else None
        router._claude = _Prov("claude") if claude_ok else None
        router._openai_coach = _Prov("openai") if openai_ok else None
        router._perplexity = None
        return router

    async def test_gemini_ok_claude_nao_e_chamado(self):
        router = await self._make_router()
        r = await router.coach_ask(
            prompt="olá", system="sys", history=None,
            max_tokens=100, temperature=0.0, enrich_with_web=False,
        )
        assert r.provider == "gemini"
        assert router._claude.ask.await_count == 0
        assert router._openai_coach.ask.await_count == 0

    async def test_gemini_429_cai_para_claude(self):
        err = AIProviderError(
            "429", provider="gemini", code="http_429",
            status_code=429, retriable=True,
        )
        router = await self._make_router(gemini_ok=False, gemini_err=err)
        r = await router.coach_ask(
            prompt="olá", system="sys", history=None,
            max_tokens=100, temperature=0.0, enrich_with_web=False,
        )
        assert r.provider == "claude"
        assert router._gemini.ask.await_count == 1
        assert router._openai_coach.ask.await_count == 0

    async def test_gemini_401_cai_para_claude_sem_retry(self):
        err = AIProviderError(
            "401", provider="gemini", code="http_401",
            status_code=401, retriable=False,
        )
        router = await self._make_router(gemini_ok=False, gemini_err=err)
        r = await router.coach_ask(
            prompt="olá", system="sys", history=None,
            max_tokens=100, temperature=0.0, enrich_with_web=False,
        )
        assert r.provider == "claude"

    async def test_gemini_e_claude_falham_openai_ganha(self):
        err_g = AIProviderError("500", provider="gemini", code="x", retriable=True)
        router = await self._make_router(gemini_ok=False, gemini_err=err_g)
        # Força Claude a falhar também
        router._claude.ask = AsyncMock(side_effect=AIProviderError(
            "500", provider="claude", code="x", retriable=True,
        ))
        r = await router.coach_ask(
            prompt="olá", system="sys", history=None,
            max_tokens=100, temperature=0.0, enrich_with_web=False,
        )
        assert r.provider == "openai"
        assert router._openai_coach.ask.await_count == 1

    async def test_todos_falham_levanta_coach_unavailable(self):
        from engines.ai_providers.router import CoachUnavailableError
        err = AIProviderError("500", provider="x", code="x", retriable=True)
        router = await self._make_router(gemini_ok=False, gemini_err=err)
        router._claude.ask = AsyncMock(side_effect=err)
        router._openai_coach.ask = AsyncMock(side_effect=err)
        with pytest.raises(CoachUnavailableError):
            await router.coach_ask(
                prompt="x", system="sys", history=None,
                max_tokens=10, temperature=0.0, enrich_with_web=False,
            )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@pytest.mark.anyio
class TestHealth:
    async def test_health_inclui_gemini(self):
        from engines.ai_providers.router import AIRouter
        router = AIRouter()
        router._loaded = True
        router._gemini = None
        router._claude = None
        router._openai_coach = None
        router._perplexity = None
        out = await router.health(ping=False)
        assert "gemini" in out["providers"]
        assert out["primary"] == "gemini"
        assert out["fallback"] == "claude"
        assert out["fallback_2"] == "openai"


# ---------------------------------------------------------------------------
# Integração REAL (opt-in via -m integration)
# ---------------------------------------------------------------------------
@pytest.mark.integration
@pytest.mark.anyio
async def test_integration_ping_real_gemini():
    """Ping real ao Gemini. Skip se `GEMINI_API_KEY` ausente.

    Executar com: `pytest -m integration tests/test_ai_providers_gemini.py`
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        pytest.skip("GEMINI_API_KEY ausente — ping real pulado.")
    p = GeminiProvider()
    res = await p.ping()
    assert res["ok"] is True, f"Ping falhou: {res}"
    assert res["provider"] == "gemini"
    assert res["latency_ms"] >= 0
    # Latência típica Pro: 500-10000ms (tem thinking tokens)
    assert res["latency_ms"] < 30_000, "Ping demorou >30s — anormal"
