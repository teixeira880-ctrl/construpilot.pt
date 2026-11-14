"""14/11 (Martinho): o Assistente corre no Claude por defeito, com raciocínio; o OpenAI fica como recurso."""
from types import SimpleNamespace as NS

from engines import assistant_claude as ac
from engines import assistant_fallback as fb


def _claude_env(monkeypatch, key="ANTHROPIC_API_KEY"):
    monkeypatch.delenv("ASSISTANT_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("EMERGENT_LLM_KEY", raising=False)
    monkeypatch.setenv(key, "k")
    monkeypatch.setenv("ASSISTANT_CLAUDE_MODEL_FAST", "claude-fast")
    monkeypatch.setenv("ASSISTANT_CLAUDE_MODEL_THOROUGH", "claude-thorough")


def test_claude_principal_quando_configurado(monkeypatch):
    _claude_env(monkeypatch)
    assert fb.primary_provider() == "anthropic"
    _claude_env(monkeypatch, "EMERGENT_LLM_KEY")
    assert fb.primary_provider() == "anthropic"


def test_sem_claude_fica_openai_e_variavel_explicita_manda(monkeypatch):
    for k in ("ASSISTANT_PROVIDER", "ANTHROPIC_API_KEY", "EMERGENT_LLM_KEY", "ASSISTANT_CLAUDE_MODEL_FAST"):
        monkeypatch.delenv(k, raising=False)
    assert fb.primary_provider() == "openai"
    _claude_env(monkeypatch)
    monkeypatch.setenv("ASSISTANT_PROVIDER", "openai")
    assert fb.primary_provider() == "openai"
    monkeypatch.setenv("ASSISTANT_PROVIDER", "Gemini")
    assert fb.primary_provider() == "gemini"


def test_openai_como_recurso_do_claude(monkeypatch):
    _claude_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    assert fb.openai_failover_available()
    monkeypatch.delenv("OPENAI_API_KEY")
    assert not fb.openai_failover_available()


def test_raciocinio_ligado_por_modo_e_desligavel(monkeypatch):
    monkeypatch.delenv("ASSISTANT_CLAUDE_THINKING", raising=False)
    t = ac.thinking_params("thorough", {})["thinking"]
    f = ac.thinking_params("fast", {})["thinking"]
    assert t["type"] == "enabled" and t["budget_tokens"] > f["budget_tokens"] >= 1024
    assert ac.thinking_params("thorough", {"_claude_no_thinking": True}) == {}     # repetição sem raciocínio
    monkeypatch.setenv("ASSISTANT_CLAUDE_THINKING", "off")
    assert ac.thinking_params("thorough", {}) == {}


def test_erro_de_raciocinio_reconhecido():
    assert ac._is_thinking_error(Exception("messages.1: Expected `thinking` block but found `text`"))
    assert not ac._is_thinking_error(Exception("rate limit"))
    assert ac.MAX_STEPS >= 48
