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
    for p in ("claude", "openai", "gemini"):
        monkeypatch.setitem(reader.PROVIDERS, p, _fail())
    with pytest.raises(RuntimeError):
        asyncio.run(reader._default_llm("s", "t"))


def test_extract_json_closes_truncated():
    out = reader._extract_json('{"murs": [{"ep": 20, "h": 2.5}, {"ep": 20, "h": 2.7}], "niveaux": 3, "nom": "Villa')
    assert isinstance(out, dict) and len(out.get("murs", [])) >= 1


def test_extract_json_trailing_commas_and_fences():
    out = reader._extract_json('```json\n{"a": 1, "b": [1, 2,], }\n```')
    assert out["a"] == 1 and out["b"] == [1, 2]


def test_extract_json_surrounding_text():
    assert reader._extract_json('voici le relevé {"ok": true} fin')["ok"] is True
