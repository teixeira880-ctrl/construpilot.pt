"""A tradução automática passa ao degrau seguinte quando a chave Claude direta fica sem crédito (registo de 24/11)."""
import asyncio
import sys
import types


def test_i18n_cascata_claude_sem_credito_passa_a_emergent(monkeypatch):
    from routes import i18n_auto as M
    M._DEGRADADO.clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("EMERGENT_LLM_KEY", "y")

    class Erro(Exception):
        status_code = 400

    class Msgs:
        async def create(self, **kw):
            raise Erro("Your credit balance is too low to access the Anthropic API.")

    class Cli:
        def __init__(self, **kw):
            self.messages = Msgs()

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(AsyncAnthropic=Cli))

    class Chat:
        def __init__(self, **kw): pass
        def with_model(self, *a): return self
        async def send_message(self, m): return '{"0": "ok"}'

    fake = types.ModuleType("emergentintegrations.llm.chat")
    fake.LlmChat, fake.UserMessage = Chat, lambda text: text
    monkeypatch.setitem(sys.modules, "emergentintegrations.llm.chat", fake)
    assert asyncio.run(M._llm("s", "p", 100)) == '{"0": "ok"}'
    assert M._em_baixo("anthropic")             # a chave sem crédito fica de lado (sem repetir o erro a cada lote)
    assert asyncio.run(M._llm("s", "p", 100)) == '{"0": "ok"}'
    M._DEGRADADO.clear()


def test_i18n_openai_a_frente_quando_e_o_principal(monkeypatch):
    from routes import i18n_auto as M
    M._DEGRADADO.clear()
    monkeypatch.setenv("ASSISTANT_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "z")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    chamadas = []

    class Comp:
        async def create(self, **kw):
            chamadas.append("openai")
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{"0": "oa"}'))])

    class OCli:
        def __init__(self, **kw):
            self.chat = types.SimpleNamespace(completions=Comp())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(AsyncOpenAI=OCli))

    class ACli:
        def __init__(self, **kw):
            chamadas.append("anthropic")

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(AsyncAnthropic=ACli))
    assert asyncio.run(M._llm("s", "p", 100)) == '{"0": "oa"}' and chamadas == ["openai"]
    M._DEGRADADO.clear()
