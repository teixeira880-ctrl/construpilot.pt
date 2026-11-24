"""24/11 : a cascata do Assistente nunca salta um degrau por falta de variável de modelo."""
from engines import assistant_fallback as F


def test_gemini_disponivel_sem_variavel_de_modelo(monkeypatch):
    monkeypatch.delenv("ASSISTANT_GEMINI_MODEL_FAST", raising=False)
    monkeypatch.setenv("EMERGENT_LLM_KEY", "x")
    monkeypatch.setattr(F, "_on", lambda pid: True)
    assert F.gemini_fallback_available()
