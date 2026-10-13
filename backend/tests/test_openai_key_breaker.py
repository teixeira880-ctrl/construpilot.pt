"""Disjoncteur clé OpenAI d'entreprise → repli clé Emergent (engines/llm_keys.py)."""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engines import llm_keys  # noqa: E402


class _Err(Exception):
    def __init__(self, msg, status_code=None):
        super().__init__(msg)
        self.status_code = status_code


def test_is_credit_error_markers():
    assert llm_keys.is_credit_error(_Err("You have no credits remaining. Add credits..."))
    assert llm_keys.is_credit_error(_Err("Error code: 429 - insufficient_quota", 429))
    assert llm_keys.is_credit_error(_Err("Incorrect API key provided", 401))
    assert not llm_keys.is_credit_error(_Err("Rate limit reached, retry in 2s", 429))
    assert not llm_keys.is_credit_error(_Err("Connection reset by peer"))


def test_studies_key_switches_to_emergent_when_disabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-company")
    monkeypatch.setenv("EMERGENT_LLM_KEY", "sk-emergent")
    monkeypatch.setitem(llm_keys._STATE, "disabled", False)
    assert llm_keys.studies_key("openai") == "sk-company"
    assert llm_keys.key_source() == "openai_direct"
    monkeypatch.setitem(llm_keys._STATE, "disabled", True)
    assert llm_keys.studies_key("openai") == "sk-emergent"
    assert llm_keys.key_source() == "emergent"
    assert llm_keys.status()["active"] is False


def test_note_openai_error_ignores_non_credit(monkeypatch):
    import asyncio
    monkeypatch.setenv("OPENAI_API_KEY", "sk-company")
    monkeypatch.setitem(llm_keys._STATE, "disabled", False)
    assert asyncio.run(llm_keys.note_openai_error(_Err("timeout"))) is False
    assert llm_keys._STATE["disabled"] is False
