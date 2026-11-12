"""Bascule automatique entre fournisseurs IA (aucun appel réseau : fournisseurs simulés)."""
import asyncio

import pytest

from engines import ai
from engines.expenses import metering


class _Msg:
    def __init__(self, text, images=()):
        self.text = text
        self.file_contents = [type("C", (), {"image_base64": i})() for i in images]


def test_vision_analysis_switches_provider_when_preferred_one_fails(monkeypatch):
    calls = []

    async def single(system, text, images, provider, model, feature="misc"):
        calls.append(provider)
        if provider == "gemini":
            raise ConnectionError("gemini em baixo")
        return '{"lines": [], "notes": "ok via ' + provider + '"}'
    monkeypatch.setattr(ai, "_complete_vision_single", single)
    out = asyncio.run(ai._complete_vision("sys", "planta", ["img"], "gemini", "gemini-3.1-pro-preview", feature="rebar"))
    assert calls[0] == "gemini" and len(calls) == 2 and "ok via" in out


def test_vision_analysis_raises_clear_error_when_all_providers_fail(monkeypatch):
    async def single(*a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(ai, "_complete_vision_single", single)
    with pytest.raises(RuntimeError):
        asyncio.run(ai._complete_vision("sys", "planta", ["img"], "gemini", "gemini-3.1-pro-preview"))


def test_help_chat_falls_back_to_provider_chain(monkeypatch):
    class Broken:
        async def stream_message(self, *a, **k):
            raise ConnectionError("claude em baixo")
            yield  # noqa
    monkeypatch.setattr(ai, "_chat", lambda *a, **k: Broken())

    async def nolog(*a, **k):
        return None
    monkeypatch.setattr(ai, "_log_usage", nolog)

    async def complete(system, text, images=None, session_id=None, feature="misc"):
        assert feature == "help_chat"
        return "Resposta de reserva"
    monkeypatch.setattr(ai, "_complete", complete)
    assert asyncio.run(ai.help_assistant([], "como crio um orçamento?", "s1")) == "Resposta de reserva"


def test_metered_chat_failover_replays_text_and_images(monkeypatch):
    seen = {}

    async def failing_send(self, method, *a, **k):
        raise ConnectionError("fornecedor principal em baixo")
    monkeypatch.setattr(metering.MeteredChat, "_send", failing_send)

    async def single(system, text, images, provider, model, feature="misc"):
        seen.update(system=system, text=text, images=images, provider=provider, feature=feature)
        return '{"ok": true}'
    monkeypatch.setattr(ai, "_complete_vision_single", single)
    chat = metering.MeteredChat(api_key="k", session_id="s", system_message="SYS", expense_feature="plan_analysis",
                                failover=True).with_model("openai", "gpt-5.5")
    out = asyncio.run(chat.send_message(_Msg("lê a planta", ["IMG64"])))
    assert out == '{"ok": true}'
    assert seen["system"] == "SYS" and seen["text"] == "lê a planta" and seen["images"] == ["IMG64"]
    assert seen["provider"] != "openai" and seen["feature"] == "plan_analysis"


def test_metered_chat_without_failover_is_unchanged(monkeypatch):
    async def failing_send(self, method, *a, **k):
        raise ConnectionError("down")
    monkeypatch.setattr(metering.MeteredChat, "_send", failing_send)
    chat = metering.MeteredChat(api_key="k", session_id="s", system_message="SYS").with_model("openai", "gpt-5.5")
    with pytest.raises(ConnectionError):
        asyncio.run(chat.send_message(_Msg("x")))


def test_metered_chat_never_bypasses_budget_refusal(monkeypatch):
    from fastapi import HTTPException

    async def budget(self, method, *a, **k):
        raise HTTPException(402, "Orçamento IA esgotado")
    monkeypatch.setattr(metering.MeteredChat, "_send", budget)

    async def single(*a, **k):
        raise AssertionError("não deve contornar o orçamento")
    monkeypatch.setattr(ai, "_complete_vision_single", single)
    chat = metering.MeteredChat(api_key="k", session_id="s", failover=True).with_model("openai", "gpt-5.5")
    with pytest.raises(HTTPException):
        asyncio.run(chat.send_message(_Msg("x")))


def test_stairs_chat_switches_provider(monkeypatch):
    from stair_engine import assistant as st
    monkeypatch.setenv("EMERGENT_LLM_KEY", "k")
    used = []

    class FakeChat:
        def __init__(self, **k):
            pass

        def with_model(self, p, m):
            self.p = p
            used.append(p)
            return self

        def with_tools(self, *a, **k):
            return self

        def with_params(self, **k):
            return self

        async def send_message_with_tools(self, *a, **k):
            if self.p == "anthropic":
                raise ConnectionError("claude em baixo")
            return type("R", (), {"content": "Escada reta recomendada.", "tool_calls": None})()
    monkeypatch.setattr(st, "LlmChat", FakeChat)
    reply = asyncio.run(st.chat_with_assistant("c1", "escada para 2,80 m", []))
    assert used[0] == "anthropic" and len(used) >= 2
    assert reply.reply_text == "Escada reta recomendada." and not reply.metadata["model"].startswith("anthropic")
