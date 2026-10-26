import asyncio

import pytest

from engines.bet_core import reader


def _ok(txt):
    async def f(system, text, images=None, model=None, max_tokens=4096):
        return txt
    return f


def _fail(exc=None):
    async def f(system, text, images=None, model=None, max_tokens=4096):
        raise exc or RuntimeError("down")
    return f


def test_cascade_claude_to_openai(monkeypatch):
    monkeypatch.setitem(reader.PROVIDERS, "claude", _fail())
    monkeypatch.setitem(reader.PROVIDERS, "openai", _ok('{"ok":1}'))
    monkeypatch.setitem(reader.PROVIDERS, "gemini", _fail())
    out = asyncio.run(reader._default_llm("s", "t"))
    assert out == '{"ok":1}' and reader.LAST_PROVIDER[0] == "openai"


def test_cascade_to_gemini(monkeypatch):
    monkeypatch.setitem(reader.PROVIDERS, "claude", _fail())
    monkeypatch.setitem(reader.PROVIDERS, "openai", _fail())
    monkeypatch.setitem(reader.PROVIDERS, "gemini", _ok('{"g":1}'))
    out = asyncio.run(reader._default_llm("s", "t"))
    assert out == '{"g":1}' and reader.LAST_PROVIDER[0] == "gemini"


def test_cascade_skips_response_without_json(monkeypatch):
    monkeypatch.setitem(reader.PROVIDERS, "claude", _ok("désolé, pas de JSON ici"))
    monkeypatch.setitem(reader.PROVIDERS, "openai", _ok('{"ok":1}'))
    monkeypatch.setitem(reader.PROVIDERS, "gemini", _fail())
    out = asyncio.run(reader._default_llm("s", "t"))
    assert out == '{"ok":1}' and reader.LAST_PROVIDER[0] == "openai"


def test_cascade_all_fail_raises(monkeypatch):
    for p in ("claude", "openai", "gemini", "emergent"):
        monkeypatch.setitem(reader.PROVIDERS, p, _fail())
    with pytest.raises(RuntimeError):
        asyncio.run(reader._default_llm("s", "t"))


def test_cascade_emergent_rescues(monkeypatch):
    for p in ("claude", "openai", "gemini"):
        monkeypatch.setitem(reader.PROVIDERS, p, _fail())
    monkeypatch.setitem(reader.PROVIDERS, "emergent", _ok('{"e":1}'))
    out = asyncio.run(reader._default_llm("s", "t"))
    assert out == '{"e":1}' and reader.LAST_PROVIDER[0] == "emergent"


def test_ordre_reduit_garde_tous_les_replis(monkeypatch):
    monkeypatch.setenv("BET_LLM_ORDER", "openai")
    assert reader._provider_order() == ["openai", "claude", "gemini", "emergent"]


def test_extract_json_closes_truncated():
    out = reader._extract_json('{"murs": [{"ep": 20, "h": 2.5}, {"ep": 20, "h": 2.7}], "niveaux": 3, "nom": "Villa')
    assert isinstance(out, dict) and len(out.get("murs", [])) >= 1


def test_extract_json_trailing_commas_and_fences():
    out = reader._extract_json('```json\n{"a": 1, "b": [1, 2,], }\n```')
    assert out["a"] == 1 and out["b"] == [1, 2]


def test_extract_json_surrounding_text():
    assert reader._extract_json('voici le relevé {"ok": true} fin')["ok"] is True


def test_mensagem_clara_quando_todas_as_ia_falham(monkeypatch):
    monkeypatch.setitem(reader.PROVIDERS, "claude", _fail(RuntimeError("Error code: 401 invalid x-api-key")))
    monkeypatch.setitem(reader.PROVIDERS, "openai", _fail(RuntimeError("You have no credits remaining")))
    monkeypatch.setitem(reader.PROVIDERS, "gemini", _fail(RuntimeError("503 UNAVAILABLE high demand")))
    monkeypatch.setitem(reader.PROVIDERS, "emergent", _fail(RuntimeError("Budget has been exceeded")))
    with pytest.raises(reader.ProvidersDown) as e:
        asyncio.run(reader._default_llm("s", "t"))
    assert e.value.status == {"claude": "auth", "openai": "credits", "gemini": "overloaded", "emergent": "credits"}
    pt = reader.providers_message(e.value, "pt")
    assert "Claude : chave recusada" in pt and "OpenAI : sem créditos" in pt and "Gemini : sobrecarregado" in pt


def test_gemini_sobrecarregado_tenta_de_novo(monkeypatch):
    calls = []

    async def g(system, text, images=None, model=None, max_tokens=4096):
        calls.append(model)
        if len(calls) < 3:
            raise RuntimeError("503 UNAVAILABLE")
        return '{"ok":1}'
    monkeypatch.setattr(reader, "_gemini", g)

    async def nosleep(_s):
        return None
    monkeypatch.setattr(reader.asyncio if hasattr(reader, "asyncio") else asyncio, "sleep", nosleep)
    assert asyncio.run(reader._gemini_retry("s", "t")) == '{"ok":1}' and len(calls) == 3
