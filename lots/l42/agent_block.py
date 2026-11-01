

# ====================================================================== Lot 42 : écran en direct, internet, autonomie
# Le site envoie un résumé de l'écran à chaque changement (data LiveKit, topic « screen », voir avatarScreenWatch.js).
# Il est injecté dans les instructions : l'assistante répond et décide sur ce que l'admin voit MAINTENANT,
# réagit seule aux erreurs / résultats / cartes de choix, et ne parle plus d'une page que l'admin a quittée.
import time  # noqa: E402

AUTONOMY = (
    "\nAUTONOMY: you are a fully autonomous operator. When the goal is clear, chain every step yourself (navigate, read, click, "
    "type, wait, check the result) until it is done; never stop half-way to ask 'what next?'. Report in one short sentence at each "
    "milestone. Only the irreversible / third-party actions listed in the rules still need a spoken yes.\n"
    "INTERNET: web_search gives you live internet answers with sources (news, regulations, prices, products, competitors, "
    "anything outside ConstruPilot). Use it whenever the answer depends on the outside world or on today's facts; say the source "
    "briefly. Never use it for ConstruPilot's own data (use the screen, the Assistant BTP or the API).\n"
    "DEMO AND PRESENTATION: when asked to present ConstruPilot, to test the demo or to show what it does, run it yourself from start "
    "to end without being asked step by step: open the page (/demo for the public demo, otherwise the real pages), look at the LIVE "
    "SCREEN, then go through the main features one by one — dashboard, Assistant BTP (send a real short request, e.g. pricing a "
    "bathroom, and comment the answer), plans & take-offs (/plan), quotes (/devis-editeur, /devis), invoices (/factures), site files "
    "(/chantiers), planning (/planning), studies (/structuro-bet, /renovation), autonomous pilot (/agents). For each: 1-2 sentences "
    "on what it does and the benefit for a construction company, then a real action on screen. When testing, note every error, "
    "empty page, slow or broken button you see, and give a short test report at the end (what works, what fails, where).\n"
)
SCREEN_HEADER = (
    "LIVE SCREEN — what the admin sees RIGHT NOW in the browser, updated automatically by the site at every change (page, typing, "
    "scrolling, messages, dialogs, errors, Assistant BTP progress). It is the truth about the present moment: (a) always ground your "
    "answers and decisions in it; 'this / here / isto / aqui / ça / ici' mean what is on it; (b) never talk about or act on a page the "
    "admin has left: if what you were going to say no longer matches the screen, drop it and adapt; (c) do NOT call ui_read just to "
    "know where the admin is — call it only to get element ids before clicking or typing; (d) if an error, a dialog, a finished result "
    "or a choice card appears, deal with it without waiting to be asked; (e) stay short and in sync with what is visible.\n"
)
WEB_MODEL = os.environ.get("AVATAR_WEB_MODEL") or "gpt-5-mini"


def render_screen(s: dict) -> str:
    out = [f"Page: {s.get('path', '?')} — {s.get('title', '')} (moved by {s.get('actor', 'admin')}, scroll {s.get('scroll', 0)}%)"]
    if s.get("headings"):
        out.append("Headings: " + " | ".join(s["headings"]))
    if s.get("dialog"):
        out.append(f"OPEN DIALOG: {s['dialog'].get('title') or ''} — {s['dialog'].get('text') or ''}")
    for a in s.get("alerts") or []:
        out.append(f"Message on screen ({a.get('type', 'info')}): {a.get('text', '')}")
    for e in s.get("errors") or []:
        out.append(f"Page error (JavaScript): {e}")
    if s.get("focused"):
        out.append(f"Admin is typing in '{s['focused'].get('field')}': {s['focused'].get('value') or ''}")
    if s.get("selection"):
        out.append(f"Admin selected the text: {s['selection']}")
    a = s.get("assistant")
    if a:
        state = "RUNNING" + (f" ({a.get('progress')})" if a.get("progress") else "") if a.get("running") else "idle"
        out.append(f"Assistant BTP: {state}, {a.get('messages', 0)} messages, pending choice questions: {a.get('choices', 0)}. "
                   f"Last answer: {a.get('last_answer') or '—'}")
    if s.get("visible"):
        out.append("Visible text: " + s["visible"])
    return "\n".join(out)[:4200]


@function_tool()
async def web_search(context: RunContext, query: str) -> str:
    """Search the internet now (live web, with sources). Use for anything outside ConstruPilot: news, regulations, norms, prices,
    products, suppliers, competitors, weather, events. Write the query in the admin's language; returns a short answer + sources."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        return json.dumps({"ok": False, "error": "recherche internet indisponible (clé absente)"})
    body = {"model": WEB_MODEL, "tools": [{"type": "web_search"}], "input": query[:800], "max_output_tokens": 900,
            "instructions": "Answer in the language of the question, in at most 5 short sentences, factual and dated when relevant, "
                            "then list up to 3 sources (title + domain). Never invent a source."}
    if WEB_MODEL.startswith(("gpt-5", "o")):
        body["reasoning"] = {"effort": "low"}
    try:
        async with httpx.AsyncClient(timeout=45) as http:
            r = await http.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {key}"}, json=body)
            if r.status_code >= 400 and WEB_MODEL != "gpt-4.1-mini":  # modèle refusé : repli
                body.update(model="gpt-4.1-mini"); body.pop("reasoning", None)
                r = await http.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {key}"}, json=body)
        if r.status_code >= 400:
            return json.dumps({"ok": False, "error": f"recherche internet refusée (HTTP {r.status_code})"})
        d = r.json()
        text = d.get("output_text") or "".join(c.get("text", "") for o in d.get("output") or [] if o.get("type") == "message"
                                                for c in o.get("content") or [] if c.get("type") == "output_text")
        return json.dumps({"ok": True, "answer": text[:3000]}, ensure_ascii=False)
    except httpx.HTTPError as e:
        return json.dumps({"ok": False, "error": f"internet injoignable: {str(e)[:120]}"})


class ScreenContext:
    """Écran en direct → instructions de l'agent (dernier état gagnant, ≤ 1 mise à jour / 0,8 s) + réactions spontanées."""

    REACT = {"alert", "assistant_done", "assistant_choices", "navigate"}

    def __init__(self, room, session, identity: str):
        self.room, self.session, self.identity = room, session, identity
        self.agent = session.current_agent
        self.base = (self.agent.instructions or "") + AUTONOMY
        self.latest: dict | None = None
        self.last_text = ""
        self.last_push = 0.0
        self.last_react = 0.0
        self.task: asyncio.Task | None = None
        self.pending_event: dict | None = None

    async def start(self):
        await self.agent.update_tools(list(self.agent.tools) + [web_search])
        await self.agent.update_instructions(self.base)
        self.room.on("data_received", self._on_data)

    def _on_data(self, packet):
        if getattr(packet, "topic", "") != "screen":
            return
        p = getattr(packet, "participant", None)
        if p is not None and p.identity != self.identity:
            return
        try:
            data = json.loads(bytes(packet.data).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        self.latest = data
        if data.get("event") in self.REACT:
            self.pending_event = data
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self._flush())

    async def _flush(self):
        try:
            wait = 0.8 - (time.monotonic() - self.last_push)
            if wait > 0:
                await asyncio.sleep(wait)
            data = self.latest
            text = render_screen(data or {})
            if text != self.last_text:
                self.last_text, self.last_push = text, time.monotonic()
                await self.agent.update_instructions(self.base + "\n" + SCREEN_HEADER + text)
            ev, self.pending_event = self.pending_event, None
            if ev:
                await self._react(ev)
        except Exception:  # noqa: BLE001 — l'écran ne doit jamais faire tomber la session
            log.warning("écran en direct : mise à jour ignorée", exc_info=True)

    async def _react(self, ev: dict):
        kind, by_admin = ev.get("event"), ev.get("actor") == "admin"
        agent_state = getattr(self.session, "agent_state", "listening")
        user_state = getattr(self.session, "user_state", "listening")
        if user_state == "speaking" or time.monotonic() - self.last_react < 10:
            return
        if kind == "navigate":
            if not by_admin:
                return  # c'est l'assistante qui navigue : elle sait déjà où elle va
            if agent_state == "speaking":
                self.session.interrupt()  # elle parlait de l'ancienne page : on coupe, on suit l'admin
            elif agent_state == "thinking":
                return
            hint = ("The admin just opened another page themselves. In ONE short sentence, show you follow (name the page and what "
                    "it is for) and, if you were doing something for them, adapt it to this page. Do not repeat what you said before.")
        else:
            if agent_state in ("speaking", "thinking"):
                return  # elle travaille déjà (outil en cours) : l'écran à jour suffit
            hint = {"alert": "A message, dialog or error just appeared on the admin's screen. React now in one short sentence and, "
                             "if it is an error in what you are doing together, fix it or say what to do next.",
                    "assistant_done": "The Assistant BTP just finished on screen. Tell the admin the result in one or two sentences "
                                      "and do the next logical step of the current job yourself.",
                    "assistant_choices": "The Assistant BTP is asking choices on screen. Answer them yourself with "
                                         "assistant_answer_choices (admin's preferences, otherwise recommended) and say so briefly."}[kind]
        self.last_react = time.monotonic()
        self.session.generate_reply(instructions=hint + "\n" + SCREEN_HEADER + render_screen(ev))


async def attach_screen(ctx: JobContext, session: AgentSession, identity: str) -> ScreenContext | None:
    try:
        sc = ScreenContext(ctx.room, session, identity)
        await sc.start()
        return sc
    except Exception:  # noqa: BLE001
        log.warning("écran en direct indisponible", exc_info=True)
        return None
