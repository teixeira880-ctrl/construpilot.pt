import asyncio, json, sys, types
import os
sys.path.insert(0, os.environ.get("AGENT_DIR", "/app/avatar_agent"))
import pytest
import agent as A


class FakeAgent:
    def __init__(self):
        self.instructions = "BASE"
        self.tools = []
        self.history = []
    async def update_tools(self, t): self.tools = t
    async def update_instructions(self, s): self.instructions = s; self.history.append(s)


class FakeSession:
    def __init__(self):
        self.current_agent = FakeAgent()
        self.agent_state, self.user_state = "listening", "listening"
        self.replies, self.interrupts = [], 0
    def generate_reply(self, instructions=""): self.replies.append(instructions)
    def interrupt(self): self.interrupts += 1


class FakeRoom:
    def __init__(self): self.handlers = {}
    def on(self, ev, fn): self.handlers[ev] = fn


def pkt(identity="admin-u1", **screen):
    data = {"type": "screen", "event": "change", "actor": "admin", "path": "/dashboard", "title": "CP", "visible": "Olá"}
    data.update(screen)
    return types.SimpleNamespace(topic="screen", participant=types.SimpleNamespace(identity=identity), data=json.dumps(data).encode())


async def setup():
    room, sess = FakeRoom(), FakeSession()
    sc = await A.attach_screen(types.SimpleNamespace(room=room), sess, "admin-u1")
    return room, sess, sc


async def settle(sc):
    for _ in range(30):
        await asyncio.sleep(0.05)
        if sc.task is None or sc.task.done():
            return


@pytest.mark.asyncio
async def test_screen_goes_into_instructions_and_web_tool_added():
    room, sess, sc = await setup()
    ag = sess.current_agent
    assert ag.instructions.startswith("BASE") and "AUTONOMY" in ag.instructions and A.web_search in ag.tools
    room.handlers["data_received"](pkt(path="/devis", title="Devis", visible="Devis n° 12 · Total 3 400 €"))
    await settle(sc)
    assert "LIVE SCREEN" in ag.instructions and "/devis" in ag.instructions and "3 400 €" in ag.instructions
    assert ag.instructions.startswith("BASE")


@pytest.mark.asyncio
async def test_other_participant_and_bad_payload_ignored():
    room, sess, sc = await setup()
    n = len(sess.current_agent.history)
    room.handlers["data_received"](pkt(identity="intrus", path="/x"))
    room.handlers["data_received"](types.SimpleNamespace(topic="screen", participant=None, data=b"{bad"))
    await asyncio.sleep(0.2)
    assert len(sess.current_agent.history) == n


@pytest.mark.asyncio
async def test_admin_navigation_interrupts_stale_speech_and_follows():
    room, sess, sc = await setup()
    sess.agent_state = "speaking"
    room.handlers["data_received"](pkt(event="navigate", actor="admin", path="/factures", title="Factures"))
    await settle(sc)
    assert sess.interrupts == 1 and len(sess.replies) == 1 and "/factures" in sess.replies[0]


@pytest.mark.asyncio
async def test_assistant_own_navigation_is_silent():
    room, sess, sc = await setup()
    room.handlers["data_received"](pkt(event="navigate", actor="assistant", path="/assistant"))
    await settle(sc)
    assert sess.replies == [] and sess.interrupts == 0


@pytest.mark.asyncio
async def test_alert_reacts_once_then_rate_limited():
    room, sess, sc = await setup()
    room.handlers["data_received"](pkt(event="alert", alerts=[{"type": "error", "text": "Erro ao guardar"}]))
    await settle(sc)
    room.handlers["data_received"](pkt(event="alert", alerts=[{"type": "error", "text": "Outro erro"}]))
    await settle(sc)
    assert len(sess.replies) == 1 and "Erro ao guardar" in sess.replies[0]


@pytest.mark.asyncio
async def test_no_reaction_while_admin_speaks_or_agent_busy():
    room, sess, sc = await setup()
    sess.user_state = "speaking"
    room.handlers["data_received"](pkt(event="alert", alerts=[{"type": "error", "text": "x"}]))
    await settle(sc)
    sess.user_state, sess.agent_state = "listening", "thinking"
    room.handlers["data_received"](pkt(event="assistant_done", assistant={"running": False, "last_answer": "ok"}))
    await settle(sc)
    assert sess.replies == []


@pytest.mark.asyncio
async def test_web_search(monkeypatch):
    calls = []
    class R:
        status_code = 200
        def json(self): return {"output_text": "IVA 23 % em Portugal. Fonte: portaldasfinancas.gov.pt"}
    class C:
        def __init__(self, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None): calls.append(json); return R()
    monkeypatch.setattr(A.httpx, "AsyncClient", C)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    fn = getattr(A.web_search, "__wrapped__", None) or A.web_search
    out = json.loads(await fn(None, "taxa de IVA em Portugal"))
    assert out["ok"] and "23 %" in out["answer"] and calls[0]["tools"] == [{"type": "web_search"}]
