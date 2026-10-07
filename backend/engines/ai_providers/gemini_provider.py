"""Google Gemini provider (REST v1beta).

Design:
    * Formato da chave: `AQ.*` (novo) ou `AIzaSy*` (legado).
    * Header de autenticação: `x-goog-api-key: {key}` — NUNCA `Bearer`
      (Bearer é para OAuth2 e devolve 401 UNAUTHENTICATED).
    * Modelo default: `gemini-pro-latest` (alias que resolve para
      `gemini-3.1-pro-preview`; upgrade automático na GA).
    * Suporta:
        - `system` via `systemInstruction` (não via mensagem role=system).
        - Imagens via `inline_data` (parte base64) ou `image_url`
          (fornecido como data URI).
        - Structured output via `responseMimeType=application/json` +
          `responseSchema` passado em `kwargs['response_schema']`.
    * Mapeia respostas para `AIResponse` normalizado.
    * NUNCA faz log da chave — nem em stacktrace, nem em debug.

Compatibilidade `ai_router`:
    * Implementa `ask(prompt, system, max_tokens, temperature, history, **kwargs)`.
    * Implementa `ping()`.
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Any

import httpx

from engines.ai_providers.base import (
    AIProviderError,
    AIProviderNotConfigured,
    AIResponse,
    AIUsage,
)

logger = logging.getLogger("ai.gemini")

ENV_KEY = "GEMINI_API_KEY"
ENV_MODEL = "GEMINI_MODEL"
DEFAULT_MODEL = "gemini-pro-latest"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 60.0


def _redact_key(text: str) -> str:
    """Remove qualquer resquício da chave `AQ.*` ou `AIzaSy*` de textos."""
    text = re.sub(r"AQ\.[A-Za-z0-9_\-]+", "<REDACTED>", text)
    text = re.sub(r"AIzaSy[A-Za-z0-9_\-]+", "<REDACTED>", text)
    return text


class GeminiProvider:
    """Provedor Gemini (REST). Compatível com o contrato `ai_router`."""

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.api_key = (api_key or os.environ.get(ENV_KEY) or "").strip()
        self.model = (model or os.environ.get(ENV_MODEL) or DEFAULT_MODEL).strip()
        self.timeout = timeout
        if not self.api_key:
            raise AIProviderNotConfigured(self.name, ENV_KEY)

    # ------------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }

    def _url(self, model: str) -> str:
        return f"{BASE_URL}/models/{model}:generateContent"

    def _build_contents(
        self,
        *,
        prompt: str,
        history: list[dict[str, Any]] | None,
        image_data_uri: str | None,
    ) -> list[dict[str, Any]]:
        """Converte histórico + prompt + imagem para o formato Gemini.

        Gemini usa `role: "user" | "model"` (não `assistant`) e `parts`
        em vez de `content`.
        """
        contents: list[dict[str, Any]] = []
        if history:
            for m in history:
                role = m.get("role")
                txt = (m.get("content") or "").strip()
                if not txt:
                    continue
                gem_role = "model" if role == "assistant" else "user"
                contents.append({"role": gem_role, "parts": [{"text": txt}]})

        user_parts: list[dict[str, Any]] = []
        if image_data_uri and image_data_uri.startswith("data:"):
            # data:image/png;base64,<...>
            try:
                mime, b64 = image_data_uri.split(",", 1)
                mime = mime.replace("data:", "").split(";")[0] or "image/png"
                user_parts.append({
                    "inline_data": {"mime_type": mime, "data": b64},
                })
            except ValueError:
                logger.warning("gemini: image_data_uri mal formado — ignorado")
        user_parts.append({"text": prompt})
        contents.append({"role": "user", "parts": user_parts})
        return contents

    def _parse_response(
        self,
        payload: dict[str, Any],
        *,
        latency_ms: int,
    ) -> AIResponse:
        candidates = payload.get("candidates") or []
        if not candidates:
            raise AIProviderError(
                "Gemini sem candidates.",
                provider=self.name, code="empty_candidates", retriable=True,
            )
        cand = candidates[0]
        text_parts: list[str] = []
        for part in (cand.get("content") or {}).get("parts") or []:
            if "text" in part:
                text_parts.append(part["text"] or "")
        text = "".join(text_parts).strip()

        usage_meta = payload.get("usageMetadata") or {}
        usage = AIUsage(
            input_tokens=int(usage_meta.get("promptTokenCount") or 0),
            output_tokens=int(usage_meta.get("candidatesTokenCount") or 0),
            total_tokens=int(usage_meta.get("totalTokenCount") or 0),
        )
        return AIResponse(
            text=text,
            provider=self.name,
            model=payload.get("modelVersion") or self.model,
            latency_ms=latency_ms,
            usage=usage,
            request_id=payload.get("responseId") or None,
            stop_reason=cand.get("finishReason"),
        )

    # ------------------------------------------------------------------
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
        """Chama Gemini generateContent. Compatível com o contrato comum.

        kwargs reconhecidos:
            * `image_url`: data URI `data:image/png;base64,...` (traduzido
              para `inline_data`).
            * `response_schema`: dict JSON Schema para structured output
              (activa `responseMimeType=application/json`).
            * `json_mode`: bool — se True sem schema, força
              `responseMimeType=application/json` (sem schema).
            * `model`: override pontual do modelo.
        """
        model = (kwargs.get("model") or self.model).strip()
        image_data_uri = kwargs.get("image_url")
        response_schema = kwargs.get("response_schema")
        json_mode = bool(kwargs.get("json_mode"))

        contents = self._build_contents(
            prompt=prompt, history=history, image_data_uri=image_data_uri,
        )

        generation_config: dict[str, Any] = {
            "temperature": float(temperature),
            "maxOutputTokens": int(max_tokens),
        }
        if response_schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = response_schema
        elif json_mode:
            generation_config["responseMimeType"] = "application/json"

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    self._url(model),
                    headers=self._headers(),
                    json=payload,
                )
        except httpx.TimeoutException as e:
            raise AIProviderError(
                "Gemini timeout.", provider=self.name,
                code="timeout", retriable=True,
            ) from e
        except httpx.HTTPError as e:
            raise AIProviderError(
                f"Gemini HTTP error: {type(e).__name__}",
                provider=self.name, code="http_error", retriable=True,
            ) from e
        latency_ms = int((time.time() - t0) * 1000)

        if resp.status_code != 200:
            # Reportar erros tipados; redactar qualquer menção à chave
            try:
                err_json = resp.json()
                err_msg = err_json.get("error", {}).get("message", "")
            except ValueError:
                err_msg = resp.text[:300]
            err_msg = _redact_key(err_msg)[:300]
            retriable = resp.status_code in (408, 409, 425, 429, 500, 502, 503, 504)
            # 401/403 → não-retriable (chave inválida ou bloqueada)
            if resp.status_code in (401, 403):
                retriable = False
            raise AIProviderError(
                f"Gemini API {resp.status_code}: {err_msg}",
                provider=self.name,
                code=f"http_{resp.status_code}",
                status_code=resp.status_code,
                retriable=retriable,
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise AIProviderError(
                "Gemini: resposta não é JSON válido.",
                provider=self.name, code="invalid_json", retriable=True,
            ) from e

        return self._parse_response(data, latency_ms=latency_ms)

    # ------------------------------------------------------------------
    async def ping(self) -> dict[str, Any]:
        """Health check leve. Nota: Gemini Pro usa thinking tokens — pedimos
        `max_tokens=256` para dar margem suficiente ao modelo produzir
        o output textual depois do raciocínio interno.
        """
        try:
            r = await self.ask(
                prompt="ok", system="Responde apenas 'ok'.",
                max_tokens=256, temperature=0.0,
            )
            return {
                "ok": not r.is_empty,
                "provider": self.name,
                "model": r.model,
                "latency_ms": r.latency_ms,
            }
        except AIProviderError as e:
            return {
                "ok": False, "provider": self.name,
                "error": e.code,
                "detail": _redact_key(str(e))[:200],
            }


__all__ = ["GeminiProvider"]
