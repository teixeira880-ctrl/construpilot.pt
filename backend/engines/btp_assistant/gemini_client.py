"""Cliente fino do Gemini SDK oficial (`google-genai`) para o Assistente BTP.

Decisões de design:
    * Usamos o SDK oficial (vs. REST manual do Fase 1b `GeminiProvider`)
      porque precisamos de:
        - Function calling MANUAL com controlo total sobre execução.
        - Streaming nativo (`generate_content_stream`).
        - Google Search grounding como `tool`.
        - Partes multimodais (imagem, PDF) via `types.Part`.
    * API key: `x-goog-api-key` injectado automaticamente pelo SDK via
      `api_key` do `Client`.
    * Modelo-base: `gemini-pro-latest` (análise/cálculo) e
      `gemini-flash-latest` (conversa rápida).
    * Nunca registamos a chave em logs.

Este módulo NÃO contém o System Prompt (ver `system_prompt.py`) nem as
funções (ver `tools/registry.py`). Apenas prepara `contents` e chama o
SDK.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, AsyncIterator

from google import genai
from google.genai import types as gtypes

from engines.btp_assistant.types import Attachment

logger = logging.getLogger("btp_assistant.gemini")

ENV_KEY = "GEMINI_API_KEY"
MODELO_PRO = "gemini-pro-latest"
MODELO_FLASH = "gemini-flash-latest"


def _client() -> genai.Client:
    """Devolve `Client` do SDK oficial. Nunca loga a chave."""
    api_key = os.environ.get(ENV_KEY, "").strip()
    if not api_key:
        raise RuntimeError(f"{ENV_KEY} ausente no ambiente.")
    return genai.Client(api_key=api_key)


def preparar_anexos_partes(anexos: list[Attachment]) -> list[gtypes.Part]:
    """Converte `Attachment`s em `types.Part` para passar ao Gemini.

    Suporta `image/*` e `application/pdf`. Outros tipos são ignorados
    com um aviso em log.
    """
    import base64
    out: list[gtypes.Part] = []
    for a in anexos:
        if a.kind == "outros":
            logger.warning(
                "anexo ignorado (mime não suportado): %s", a.mime_type,
            )
            continue
        try:
            raw = base64.b64decode(a.data_b64)
        except Exception as e:  # noqa: BLE001
            logger.warning("anexo %s base64 inválido: %s", a.filename, e)
            continue
        out.append(
            gtypes.Part.from_bytes(data=raw, mime_type=a.mime_type)
        )
    return out


def _construir_contents(
    *,
    historial: list[dict[str, Any]] | None,
    user_prompt: str,
    anexos: list[Attachment] | None,
) -> list[gtypes.Content]:
    """Monta `contents` do Gemini com historial + prompt + anexos."""
    contents: list[gtypes.Content] = []
    for turn in historial or []:
        role = turn.get("role")
        txt = (turn.get("text") or "").strip()
        if not txt:
            continue
        gem_role = "model" if role == "assistant" else "user"
        contents.append(
            gtypes.Content(role=gem_role, parts=[gtypes.Part.from_text(text=txt)])
        )

    partes_user: list[gtypes.Part] = []
    if anexos:
        partes_user.extend(preparar_anexos_partes(anexos))
    partes_user.append(gtypes.Part.from_text(text=user_prompt))
    contents.append(gtypes.Content(role="user", parts=partes_user))
    return contents


async def gerar_com_ferramentas(
    *,
    modelo: str,
    system: str,
    user_prompt: str,
    anexos: list[Attachment] | None = None,
    historial: list[dict[str, Any]] | None = None,
    function_declarations: list[dict[str, Any]] | None = None,
    tool_results: list[dict[str, Any]] | None = None,
    enable_google_search: bool = True,
    temperature: float = 0.2,
    max_output_tokens: int = 4096,
) -> gtypes.GenerateContentResponse:
    """Chamada síncrona (não-streaming). Devolve o response completo.

    * `function_declarations`: schemas das ferramentas (dict Gemini).
    * `tool_results`: resultados prévios para feedback loop (parts
      `function_response`). Se fornecido, acrescenta-se ao historial.
    * `enable_google_search`: adiciona Google Search como tool extra
      (Gemini permite combinar function calls + grounding).

    Nota: na SDK v2.17, Google Search e Function Declarations podem
    coexistir no mesmo `Tool.function_declarations`+`Tool.google_search`
    separados.
    """
    c = _client()
    contents = _construir_contents(
        historial=historial, user_prompt=user_prompt, anexos=anexos,
    )

    # Se temos tool_results, acrescentar ao historial como function_response
    if tool_results:
        for tr in tool_results:
            part = gtypes.Part.from_function_response(
                name=tr["name"],
                response=tr.get("response") or {},
            )
            contents.append(gtypes.Content(role="user", parts=[part]))

    tools: list[gtypes.Tool] = []
    if function_declarations:
        fdecls = [
            gtypes.FunctionDeclaration(**fd) for fd in function_declarations
        ]
        tools.append(gtypes.Tool(function_declarations=fdecls))
    if enable_google_search and not function_declarations:
        # Gemini permite Google Search OU function declarations na mesma
        # chamada em alguns modelos — para evitar incompatibilidades,
        # usamos search apenas quando NÃO há function declarations.
        tools.append(gtypes.Tool(google_search=gtypes.GoogleSearch()))

    config = gtypes.GenerateContentConfig(
        system_instruction=system,
        tools=tools or None,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )

    # SDK `aio` é async nativo
    return await c.aio.models.generate_content(
        model=modelo, contents=contents, config=config,
    )


async def gerar_stream(
    *,
    modelo: str,
    system: str,
    user_prompt: str,
    anexos: list[Attachment] | None = None,
    historial: list[dict[str, Any]] | None = None,
    enable_google_search: bool = True,
    temperature: float = 0.3,
    max_output_tokens: int = 4096,
) -> AsyncIterator[gtypes.GenerateContentResponse]:
    """Streaming nativo (sem function calling — para modo conversa).

    Devolve `AsyncIterator` que emite chunks com `.text` incremental.
    """
    c = _client()
    contents = _construir_contents(
        historial=historial, user_prompt=user_prompt, anexos=anexos,
    )
    tools: list[gtypes.Tool] = []
    if enable_google_search:
        tools.append(gtypes.Tool(google_search=gtypes.GoogleSearch()))

    config = gtypes.GenerateContentConfig(
        system_instruction=system,
        tools=tools or None,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    async for chunk in await c.aio.models.generate_content_stream(
        model=modelo, contents=contents, config=config,
    ):
        yield chunk


__all__ = [
    "MODELO_PRO",
    "MODELO_FLASH",
    "gerar_com_ferramentas",
    "gerar_stream",
    "preparar_anexos_partes",
]
