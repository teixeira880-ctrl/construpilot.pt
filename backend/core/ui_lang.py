"""Língua da interface do pedido em curso (PT, EN, FR ou UK).

O frontend envia ``X-UI-Lang`` em todos os pedidos à API (lib/api.js). Este módulo guarda-a num
contexto (ContextVar) durante o pedido, para que:
  - as respostas de IA conversacionais (Assistente BTP, Coach, Assistente Construção) saiam na
    língua do ecrã — ``reply_language_instruction()``;
  - os PDF de documentos (orçamentos, faturas…) e os estudos sigam a língua do ecrã —
    ``current_doc_lang()``.

Sem cabeçalho (apps móveis antigas, webhooks, tarefas agendadas) nada muda: português.
"""
from __future__ import annotations

from contextvars import ContextVar

UI_LANGS = ("pt", "en", "fr", "uk")
DEFAULT = "pt"

LANG_NAMES = {
    "pt": "European Portuguese (Portugal)",
    "en": "English",
    "fr": "French (France)",
    "uk": "Ukrainian (українська)",
}

_ui_lang: ContextVar[str | None] = ContextVar("ui_lang", default=None)


def normalize(value: str | None) -> str | None:
    v = (value or "").strip().lower().replace("_", "-")[:5]
    v = v.split("-")[0]
    if v == "ua":
        v = "uk"
    return v if v in UI_LANGS else None


def current_ui_lang() -> str:
    """Língua do ecrã do pedido atual ("pt" se desconhecida)."""
    return _ui_lang.get() or DEFAULT


def explicit_ui_lang() -> str | None:
    """Língua enviada pelo ecrã, ou None se o pedido não a indicou."""
    return _ui_lang.get()


def current_doc_lang() -> str | None:
    """Língua para documentos gerados: a do ecrã quando não é o português; senão None
    (cada motor aplica a sua regra habitual, ex. português em Portugal)."""
    lang = _ui_lang.get()
    return lang if lang and lang != DEFAULT else None


def set_ui_lang(lang: str | None):
    return _ui_lang.set(normalize(lang))


def reply_language_instruction() -> str:
    """Sufixo para prompts de sistema conversacionais. Vazio em português (comportamento atual)."""
    lang = _ui_lang.get()
    if not lang or lang == DEFAULT:
        return ""
    name = LANG_NAMES[lang]
    return (
        "\n\nLANGUAGE OF THIS CONVERSATION — this rule overrides any earlier instruction about the reply "
        f"language: the user's interface is in {name}. Write every message to the user in {name}. "
        "Keep tool names, JSON keys, enum values, codes, numbers, units, currency and standard references "
        "(NP EN, Eurocode…) exactly as they are."
    )


class UILangMiddleware:
    """ASGI puro: lê ``X-UI-Lang`` e define o contexto durante todo o pedido (streaming incluído)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        lang = None
        for k, v in scope.get("headers") or []:
            if k == b"x-ui-lang":
                lang = normalize(v.decode("latin-1"))
                break
        token = _ui_lang.set(lang)
        try:
            return await self.app(scope, receive, send)
        finally:
            _ui_lang.reset(token)
