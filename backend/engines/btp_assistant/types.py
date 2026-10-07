"""Pydantic tipos do Assistente BTP (Fase A).

Contratos tipados para:
    * Eventos SSE (`AgentEvent`).
    * Chamadas e resultados de ferramentas (`ToolCall`, `ToolResult`).
    * Historial de conversa persistido em MongoDB.
    * Anexos (imagem/PDF) partilhados com o Gemini.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Reaproveitamos a definição de MissingDataRequest da camada semântica
# do Plans Pro (Fase 1) para ter UMA única representação em toda a app.
from engines.plans_pro.semantic.schemas import MissingDataRequest  # noqa: F401


class _Strict(BaseModel):
    """Pydantic base com `extra='forbid'` (nunca aceitamos campos extra)."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Anexos (imagem/PDF partilhados com Gemini)
# ---------------------------------------------------------------------------
class Attachment(_Strict):
    """Ficheiro que o utilizador anexou ao pedido."""

    filename: str = Field(description="Nome original do ficheiro.")
    mime_type: str = Field(
        description=(
            "MIME type. Aceites: 'image/jpeg', 'image/png', 'image/webp', "
            "'application/pdf'."
        ),
    )
    data_b64: str = Field(
        description="Conteúdo codificado em base64 (sem prefixo `data:`).",
    )

    @property
    def kind(self) -> Literal["image", "pdf", "outros"]:
        if self.mime_type.startswith("image/"):
            return "image"
        if self.mime_type == "application/pdf":
            return "pdf"
        return "outros"


# ---------------------------------------------------------------------------
# Function calling
# ---------------------------------------------------------------------------
class ToolCall(_Strict):
    """Uma chamada a uma ferramenta decidida pelo Gemini."""

    id: str = Field(description="Identificador local único (uuid curto).")
    name: str = Field(description="Nome da ferramenta (ex.: 'criar_orcamento').")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Argumentos decididos pelo Gemini (já tipados).",
    )
    requires_user_confirmation: bool = Field(
        default=False,
        description=(
            "True para acções potencialmente destrutivas que a UI deve "
            "apresentar ao utilizador antes de executar."
        ),
    )


class ToolResult(_Strict):
    """Resultado da execução de uma `ToolCall`."""

    tool_call_id: str = Field(description="ID da `ToolCall` correspondente.")
    status: Literal["ok", "error", "needs_user_confirmation", "needs_user_input"] = Field(
        description=(
            "'ok': executado com sucesso. "
            "'error': falha interna. "
            "'needs_user_confirmation': aguardar confirmação na UI. "
            "'needs_user_input': faltam dados (ver `missing_data`)."
        ),
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Dados devolvidos pela ferramenta (ex.: orcamento_id).",
    )
    user_message_pt: str = Field(
        description="Mensagem curta em PT-PT para o utilizador.",
    )
    missing_data: list[MissingDataRequest] = Field(
        default_factory=list,
        description="Perguntas a devolver ao utilizador quando `status='needs_user_input'`.",
    )


# ---------------------------------------------------------------------------
# Eventos SSE (streaming)
# ---------------------------------------------------------------------------
class AgentEvent(_Strict):
    """Evento Server-Sent (um por chunk de resposta do agente).

    Tipos:
        * `thinking`      — o modelo está a pensar / começou a chamada
        * `text_chunk`    — fragmento de resposta Markdown
        * `tool_call`     — Gemini decidiu chamar uma ferramenta
        * `tool_result`   — ferramenta executada
        * `missing_data`  — pedido explícito de dados ao utilizador
        * `final`         — fim do turno (payload = resumo completo)
        * `error`         — falha, mensagem em PT-PT
    """

    type: Literal[
        "thinking", "text_chunk", "tool_call", "tool_result",
        "missing_data", "final", "error",
    ]
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp_iso: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


class AgentResponse(_Strict):
    """Resposta síncrona (quando `stream=false`)."""

    conversation_id: str
    turn_id: str
    text_pt: str = Field(
        default="",
        description="Resposta completa Markdown em PT-PT.",
    )
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    missing_data: list[MissingDataRequest] = Field(default_factory=list)
    model_used: str = Field(description="ex.: 'gemini-pro-latest'.")
    mode: Literal["plano", "calculo", "conversa"]
    trace: dict[str, Any] = Field(
        default_factory=dict,
        description="Observabilidade: latências, tokens, grounding usado.",
    )


# ---------------------------------------------------------------------------
# Historial da conversa (MongoDB)
# ---------------------------------------------------------------------------
class ConversationTurn(_Strict):
    """Um turno (user → agent) persistido na colecção `btp_assistant_conversations`."""

    turn_id: str
    user_prompt: str
    attachments_meta: list[dict[str, Any]] = Field(
        default_factory=list,
        description="`{filename, mime_type, size_bytes}` — bytes NÃO persistidos.",
    )
    agent_response: dict[str, Any] = Field(
        default_factory=dict,
        description="Serializado de `AgentResponse`.",
    )
    created_at_iso: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


class ConversationHistory(_Strict):
    """Histórico completo da conversa."""

    conversation_id: str
    user_id: str
    turns: list[ConversationTurn] = Field(default_factory=list)
    created_at_iso: str
    updated_at_iso: str
