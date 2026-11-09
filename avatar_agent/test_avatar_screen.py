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
    # Lot 44 : elle s'arrête mais ne commente pas la page ouverte par l'admin (l'écran à jour suffit)
    assert sess.interrupts == 1 and sess.replies == []


@pytest.mark.asyncio
async def test_assistant_own_navigation_is_silent():
    room, sess, sc = await setup()
    room.handlers["data_received"](pkt(event="navigate", actor="assistant", path="/assistant"))
    await settle(sc)
    assert sess.replies == [] and sess.interrupts == 0


@pytest.mark.asyncio
async def test_alert_reacts_once_then_rate_limited():
    room, sess, sc = await setup()
    room.handlers["data_received"](pkt(event="alert", actor="assistant", alerts=[{"type": "error", "text": "Erro ao guardar"}]))
    await settle(sc)
    room.handlers["data_received"](pkt(event="alert", actor="assistant", alerts=[{"type": "error", "text": "Outro erro"}]))
    await settle(sc)
    assert len(sess.replies) == 1 and "Erro ao guardar" in sess.replies[0]


@pytest.mark.asyncio
async def test_alert_after_admin_own_action_is_silent():
    room, sess, sc = await setup()
    room.handlers["data_received"](pkt(event="alert", actor="admin", alerts=[{"type": "error", "text": "x"}]))
    await settle(sc)
    assert sess.replies == []


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


# ---------------------------------------------------------------- Lot 43 : réactivité, actions groupées, langues
class FakeParticipant:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    async def perform_rpc(self, destination_identity, method, payload, response_timeout):
        self.calls.append((method, json.loads(payload)))
        a = self.answers.get(method)
        if isinstance(a, Exception):
            raise a
        return a if a is not None else '{"ok": true}'


def make_assistant(answers):
    room = types.SimpleNamespace(local_participant=FakeParticipant(answers))
    bridge = types.SimpleNamespace(base="https://construpilot.fr")
    return A.AdminAssistant(bridge, "fr", room, "admin-u1"), room.local_participant


def tool(fn):
    return getattr(fn, "__wrapped__", None) or fn


@pytest.mark.asyncio
async def test_ui_do_runs_in_one_rpc():
    ag, p = make_assistant({"ui.do": '{"ok": true, "done": 2}'})
    out = await tool(A.AdminAssistant.ui_do)(ag, None, '[{"navigate": "/devis"}, {"click": "Nouveau devis"}]')
    assert json.loads(out)["ok"] and p.calls == [("ui.do", {"steps": [{"navigate": "/devis"}, {"click": "Nouveau devis"}]})]


@pytest.mark.asyncio
async def test_ui_do_falls_back_step_by_step_on_old_clients():
    ag, p = make_assistant({"ui.do": RuntimeError("RpcError 1400: Method not supported at destination"),
                            "ui.read": '{"path": "/devis"}'})
    out = json.loads(await tool(A.AdminAssistant.ui_do)(ag, None, '[{"navigate": "/devis"}, {"click": "e4", "confirmed": true}]'))
    assert out["ok"] and [c[0] for c in p.calls] == ["ui.do", "ui.navigate", "ui.click", "ui.read"]
    assert p.calls[2][1] == {"id": "e4", "confirmed": True}


@pytest.mark.asyncio
async def test_ui_do_stops_at_failing_step_and_rejects_bad_json():
    ag, p = make_assistant({"ui.do": RuntimeError("unsupported"), "ui.click": '{"ok": false, "error": "introuvable"}'})
    out = json.loads(await tool(A.AdminAssistant.ui_do)(ag, None, '[{"click": "X"}, {"navigate": "/a"}]'))
    assert not out["ok"] and len(out["done"]) == 1
    assert not json.loads(await tool(A.AdminAssistant.ui_do)(ag, None, "pas du json"))["ok"]


@pytest.mark.asyncio
async def test_ui_point_degrades_gracefully():
    ag, _ = make_assistant({"ui.point": RuntimeError("Method not supported")})
    assert json.loads(await tool(A.AdminAssistant.ui_point)(ag, None, "Total TTC"))["ok"]


def test_languages_and_speed_rules_in_instructions():
    ag, _ = make_assistant({})
    assert "ACT FIRST" in ag.instructions and "ui_do" in ag.instructions
    assert "Spanish" in A.lang_text("es") and "THAT language" in A.lang_text("es")
    assert "Portugal" in A.lang_text("pt") and "Portugal" in A.lang_text("auto", "pt")
    assert "German" in A.greet_text("de") and A.greet_text("auto", "pt") == A.GREET["pt"]


def test_live_screen_lists_clickable_elements():
    txt = A.render_screen({"path": "/devis", "elements": [{"id": "e3", "label": "Nouveau devis", "role": "button"},
                                                           {"id": "e4", "label": "Payé", "role": "checkbox", "checked": True}]})
    assert "[e3] Nouveau devis (button)" in txt and "[e4] Payé (checkbox) ✓" in txt


def test_realtime_model_accepts_fast_turn_detection():
    from openai.types.realtime.realtime_audio_input_turn_detection import SemanticVad
    from openai.types.realtime.realtime_audio_config_input import NoiseReduction
    A.openai.realtime.RealtimeModel(api_key="k", turn_detection=SemanticVad(type="semantic_vad", eagerness="high",
                                    create_response=True, interrupt_response=True), input_audio_noise_reduction=NoiseReduction(type="near_field"))


# ---------------------------------------------------------------- Lot 44 : conversation naturelle + « cala-te »
@pytest.mark.parametrize("t", ["Cala-te", "cala-te, por favor", "Aurora, silêncio!", "para", "pára de falar", "chiu",
                               "Tais-toi", "chut", "arrête de parler", "stop", "be quiet", "shut up", "cállate", "ok, para"])
def test_hush_detected(t):
    assert A.is_hush(t)


@pytest.mark.parametrize("t", ["para onde vamos?", "abre a página para o orçamento", "stop loss na fatura", "silêncio na obra é obrigatório?",
                               "Quanto faturei este mês?", "arrête le chantier de Lyon demain et préviens le client"])
def test_hush_not_triggered_by_normal_requests(t):
    assert not A.is_hush(t)


def test_hush_interrupts_and_silences_follow_up():
    calls = []
    sess = types.SimpleNamespace(interrupt=lambda force=False: calls.append(force),
                                 current_agent=types.SimpleNamespace(presenter=True))
    h = A.Hush(sess)
    h.on_transcript(types.SimpleNamespace(transcript="Cala-te", is_final=True))
    assert h.quiet and calls and sess.current_agent.presenter is False
    h.on_agent_state(types.SimpleNamespace(new_state="speaking"))   # la réponse automatique qui démarre est coupée
    assert len(calls) == 2
    h.on_transcript(types.SimpleNamespace(transcript="abre as faturas", is_final=True))
    assert not h.quiet


def test_natural_conversation_rules():
    ag, _ = make_assistant({})
    ins = ag.instructions
    assert "ONE CONTINUOUS CONVERSATION" in ins and "THE ADMIN'S NAME" in ins and "NO ASSISTANT PHRASES" in ins
    assert "Use the admin's first name when you know it" not in ins and "Narrate briefly" not in ins
    assert "Em que posso ajudar hoje" not in A.GREET["pt"].replace("Nada de 'Em que posso ajudar hoje?'", "")


def test_live_screen_shows_attached_files_fields_and_rest_of_page():
    txt = A.render_screen({"path": "/assistant", "visible": "Assistant BTP",
                           "attachments": {"files": [{"name": "devis-cuisine.pdf", "kind": "quote", "pages": 3, "text_read": True, "new": True},
                                                     {"name": "plan-rdc.dxf", "kind": "plan", "new": False}],
                                           "draft": "chiffre ceci", "uploading": False},
                           "fields": [{"field": "Client", "value": "Dupont"}, {"field": "Adresse", "value": "(vide)", "required": True}],
                           "beyond": "Total HT 12 400 €"})
    assert "ATTACHED FILES (2" in txt and "devis-cuisine.pdf" in txt and "NEW, not sent yet" in txt and "3 pages" in txt
    assert "already in the conversation context" in txt and "chiffre ceci" in txt
    assert "Client=Dupont" in txt and "(required)" in txt and "Total HT 12 400 €" in txt


def test_files_attached_is_a_reaction_and_close_tool_exists():
    assert "files_attached" in A.ScreenContext.REACT
    assert "close_avatar" in open(os.path.join(os.path.dirname(__file__), "agent.py"), encoding="utf-8").read()
    assert "ATTACHED FILE" in A.SCREEN_HEADER


def test_camera_state_is_on_the_live_screen():
    assert "CAMERA: ON" in A.render_screen({"path": "/", "camera": True})
    assert "CAMERA: off" in A.render_screen({"path": "/", "camera": False})
    assert "camera_on" in A.ScreenContext.REACT
