"""Assistente BTP ConstruPilot — agente autónomo baseado em Gemini.

Substitui `engines/btp_solver/` (Fase A). Interpreta pedidos abertos
(texto, imagem, PDF), decide autonomamente que ferramenta usar via
Gemini Function Calling, acede à internet via Google Search grounding
e devolve resposta em Markdown PT-PT ou acções estruturadas (JSON).
"""
from engines.btp_assistant.types import (
    AgentEvent,
    AgentResponse,
    Attachment,
    ConversationHistory,
    ConversationTurn,
    MissingDataRequest,
    ToolCall,
    ToolResult,
)

__all__ = [
    "AgentEvent",
    "AgentResponse",
    "Attachment",
    "ConversationHistory",
    "ConversationTurn",
    "MissingDataRequest",
    "ToolCall",
    "ToolResult",
]
