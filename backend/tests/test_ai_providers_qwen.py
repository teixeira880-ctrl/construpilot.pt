"""Testes do `QwenProvider` (DashScope nativo, região UE) e integração.

Sem rede: usa `httpx.MockTransport`. O teste real (`-m integration`) só corre
se `DASHSCOPE_API_KEY` existir.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.ai_providers.base import (  # noqa: E402
    AIProviderError,
    AIProviderNotConfigured,
    AIResponse,
)
from engines.ai_providers.qwen_provider import (  # noqa: E402
    DEFAULT_BASE,
    MULTIMODAL_PATH,
    QwenProvider,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _ok_body(text="Olá"):
    return {
        "request_id": "req-1",
        "output": {"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": [{"text": text}]}}]},
        "usage": {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13},
    }


def _provider(handler, monkeypatch, **kw):
    monkeypatch.delenv("QWEN_BASE_URL", raising=False)
    monkeypatch.delenv("QWEN_MODEL", raising=False)
    return QwenProvider(api_key="sk-test", transport=httpx.MockTransport(handler), **kw)


def test_sem_chave_desativado(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(AIProviderNotConfigured):
        QwenProvider()


def test_payload_e_resposta(monkeypatch):
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=_ok_body("Parede LSF ok"))

    p = _provider(handler, monkeypatch)
    r = _run(p.ask(prompt="Analisa", system="És engenheiro.",
                   images=["https://exemplo.pt/planta.png"],
                   history=[{"role": "user", "content": "antes"},
                            {"role": "assistant", "content": "resposta"}]))
    assert isinstance(r, AIResponse)
    assert r.text == "Parede LSF ok" and r.provider == "qwen"
    assert r.usage.total_tokens == 13 and r.request_id == "req-1"
    assert seen["url"] == DEFAULT_BASE + MULTIMODAL_PATH
    assert seen["auth"] == "Bearer sk-test"
    b = seen["body"]
    assert b["model"] == "qwen3.8-max"
    assert b["parameters"]["result_format"] == "message"
    msgs = b["input"]["messages"]
    assert msgs[0] == {"role": "system", "content": [{"text": "És engenheiro."}]}
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[-1]["content"] == [{"image": "https://exemplo.pt/planta.png"},
                                   {"text": "Analisa"}]


def test_json_mode(monkeypatch):
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=_ok_body("{}"))

    _run(_provider(handler, monkeypatch).ask(prompt="x", json_mode=True))
    assert seen["body"]["parameters"]["response_format"] == {"type": "json_object"}


@pytest.mark.parametrize("status,retriable", [(429, True), (503, True),
                                              (401, False), (400, False)])
def test_erros_http(monkeypatch, status, retriable):
    def handler(req):
        return httpx.Response(status, json={"code": "Err", "message": "m",
                                            "request_id": "r"})

    with pytest.raises(AIProviderError) as ei:
        _run(_provider(handler, monkeypatch).ask(prompt="x"))
    assert ei.value.status_code == status and ei.value.retriable is retriable
    assert "sk-test" not in str(ei.value)  # chave nunca em mensagens


def test_sem_choices(monkeypatch):
    def handler(req):
        return httpx.Response(200, json={"output": {"choices": []}})

    with pytest.raises(AIProviderError) as ei:
        _run(_provider(handler, monkeypatch).ask(prompt="x"))
    assert ei.value.code == "empty_choices"


def test_router_usa_qwen_quando_os_outros_falham(monkeypatch):
    from engines.ai_providers.router import AIRouter, CoachUnavailableError

    def handler(req):
        return httpx.Response(200, json=_ok_body("resposta qwen"))

    router = AIRouter()
    router._loaded = True  # nenhum outro provedor configurado
    router._qwen = _provider(handler, monkeypatch)
    r = _run(router.coach_ask(prompt="p", system="s"))
    assert r.provider == "qwen" and r.text == "resposta qwen"

    router._qwen = None
    with pytest.raises(CoachUnavailableError):
        _run(router.coach_ask(prompt="p", system="s"))


def test_cross_check_inclui_qwen_so_com_chave(monkeypatch):
    from engines import cross_check as cc

    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    assert all(p != "qwen" for p, _, _ in cc._models())
    monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-test")
    assert any(p == "qwen" for p, _, _ in cc._models())
    monkeypatch.setenv("CROSS_CHECK_QWEN", "0")
    assert all(p != "qwen" for p, _, _ in cc._models())


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("DASHSCOPE_API_KEY"),
                    reason="DASHSCOPE_API_KEY ausente")
def test_integracao_real():
    r = _run(QwenProvider().ask(prompt="Responde só: ok", max_tokens=5,
                                temperature=0.0))
    assert not r.is_empty
