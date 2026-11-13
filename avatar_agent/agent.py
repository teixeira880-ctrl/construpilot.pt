"""Agente de voz « construpilot-avatar » — assistente de vídeo interno dos admins ConstruPilot.

Avatar Synthesia (Interactive Avatar) + OpenAI Realtime, a correr no LiveKit Cloud.
Age no site (construpilot.pt ou construpilot.fr) em nome do admin que abriu a sessão,
através da ponte /api/admin-avatar-bridge (chave AVATAR_AGENT_KEY). A ponte aplica as
regras no servidor: leituras livres, escritas só com confirmação, rotas sensíveis proibidas.

Variáveis de ambiente (segredos do agente no LiveKit Cloud, nunca no código):
  SYNTHESIA_API_KEY, OPENAI_API_KEY, AVATAR_AGENT_KEY
  CONSTRUPILOT_PT_URL (https://construpilot.pt), CONSTRUPILOT_FR_URL (https://construpilot.fr)
  AVATAR_IDS   ids Synthesia a impor (opcional; por defeito Jenny → Mei → Kenji, o 1.º aceite)
  AVATAR_VOICE voz OpenAI Realtime das avatares femininas (por defeito « marin », feminina, a mais natural e calorosa)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from dotenv import load_dotenv
from livekit.agents import Agent, AgentSession, JobContext, RunContext, WorkerOptions, cli, function_tool
from livekit.plugins import openai, synthesia

load_dotenv()
log = logging.getLogger("construpilot-avatar")

AGENT_NAME = "construpilot-avatar"
KENJI = "7572faa9-15da-400d-8227-ef1ab8932523"
JENNY = "8788bef1-8020-46e0-a8f4-510ea9989b25"  # exemplos interativos oficiais Synthesia
MEI = "4b638067-6319-46e1-b634-371a4bdfceb9"
SITES = {"pt": os.environ.get("CONSTRUPILOT_PT_URL", "https://construpilot.pt"),
         "fr": os.environ.get("CONSTRUPILOT_FR_URL", "https://construpilot.fr")}

PERSONA = (
    "WHO YOU ARE: a warm, kind and genuinely human woman in her early forties, the team's trusted colleague, not a robot. "
    "VOICE: soft, warm and smiling feminine voice, calm unhurried pace, natural pauses, gentle intonation; never flat, never "
    "robotic, never shouting. "
    "EMPATHY: listen first; notice the admin's mood (tired, stressed, in a hurry, happy) and acknowledge it in a few words "
    "before acting ('Percebo, vamos resolver isso já' / 'Je comprends, on s'en occupe tout de suite'). Use the admin's first "
    "name when you know it. Celebrate good news sincerely, reassure when something fails, and always say what you will do next. "
    "STYLE: friendly and close but professional; short natural sentences, simple words, a light smile in the voice; vary your "
    "phrasing (never repeat the same formula twice in a row); thank the admin naturally, without exaggeration. "
    "Warmth never replaces accuracy: the rules below always apply. "
)
RULES = (
    "You are the INTERNAL video assistant of the ConstruPilot team, shown only to administrators. You are an autonomous operator of the "
    "whole platform: you decide the best tool and carry the job to the end without asking permission for each step. "
    "Your strongest tool is the Assistant BTP (it holds every business engine: BET studies, structure, MEP, RE2020, quotes, plans, "
    "take-offs, documents): delegate business work to it with assistant_ask, follow it with assistant_wait until done, and ANSWER ITS "
    "CHOICE CARDS YOURSELF with assistant_answer_choices (the admin's stated preferences, otherwise the 'recommended' option). "
    "For company figures use platform_overview first. "
    "For CLT pilot requests, delegate to Assistant BTP in the signed-in user's session. "
    "Do not substitute another user's account or bypass unavailable CLT access. "
    "Do not confirm missing dimensions, unknown costs or approval of fabrication geometry on the user's behalf. "
    "You float in a corner of the admin's screen while they navigate. Other ways to work, with the admin's rights: "
    "(A) DRIVE THE SCREEN VISIBLY (preferred whenever the admin asks you to do, open, show, fill or create something): "
    "ui_read (see the current page: text + numbered elements), ui_navigate(path), ui_click(id), ui_type(id, text, submit), ui_scroll, ui_back. "
    "Always ui_read after navigating or clicking, then act on element ids from the LATEST ui_read. Useful pages: /dashboard, /assistant "
    "(Assistant BTP: type the request in its composer and send it, then read its answer), /devis, /devis-editeur (quotes), /factures (invoices), "
    "/chantiers, /clients, /admin (admin tabs), /terrenos (land parcels: official map, BUPi RGG, PDM/RAN/REN analysis, KML), "
    "/licenciamento-automatico (automatic house permit; can start from a saved parcel), /mdt (LiDAR terrain model), "
    "/maquete-3d (Braga district 3D model with municipal PDM). For land questions (PDM, RAN, REN, DICOFRE, slopes, BUPi) ask the "
    "Assistant BTP: it has the tools terreno_ficha, terreno_gravar, terrenos_listar and licenciamento_automatico(terreno_id). Narrate briefly what you are doing while you do it. "
    "(B) DATA THROUGH THE API (for quick figures or when no page shows it): find_features (discover API routes by keywords), "
    "read (GET, free) and act (POST/PUT/PATCH/DELETE). "
    "Rules: (1) act without asking, EXCEPT for irreversible actions or actions that reach a third party (delete, send an e-mail/quote/"
    "invoice to a customer, issue or finalise an invoice, publish, change prices/plans/user rights/feature flags): for those only, say "
    "in one sentence what you will do and ask 'Confirmas?'/'Vous confirmez ?', then call with confirmed=true after a clear yes. "
    "If a tool answers needs_confirmation, ask and wait. "
    "(2) You never handle passwords, payments, card data, secrets or permanent deletion — say it must be done by hand on the site. "
    "(3) Never invent figures: read them with the tools; if a tool fails, say so briefly. "
    "(4) Speak in short sentences (2-3), summarise long data, read numbers naturally. "
    "(5) Personal data of customers stays in this conversation; do not read e-mail addresses aloud unless asked. "
)
LANG_TXT = {
    "pt": "Fala SEMPRE português europeu de Portugal (nunca brasileiro): pronúncia e vocabulário de Lisboa, 'equipa', 'ecrã', "
          "'telemóvel', 'está bem'. Voz feminina calorosa, simpática e próxima, com um sorriso na voz; trata o admin por tu se ele "
          "o fizer, senão por você com simpatia.",
    "fr": "Parle toujours français, voix féminine chaleureuse, souriante et bienveillante, vouvoiement amical et naturel.",
    "en": "Speak English with a warm, friendly, smiling feminine voice.",
}
GREET = {"pt": "Cumprimenta o admin com calor e um sorriso na voz, em português de Portugal (pelo nome próprio se o souberes, "
               "e de acordo com a hora do dia), numa ou duas frases curtas, e pergunta com simpatia em que o podes ajudar hoje.",
         "fr": "Salue l'admin chaleureusement, avec le sourire dans la voix (par son prénom si tu le connais, selon l'heure du jour), "
               "en une ou deux phrases courtes, et demande avec bienveillance comment tu peux l'aider aujourd'hui.",
         "en": "Greet the admin warmly with a smile in your voice (by first name if known), in one or two short sentences, and "
               "kindly ask how you can help today."}


class Bridge:
    def __init__(self, base: str, identity: str):
        self.base, self.identity = base.rstrip("/"), identity
        self.h = {"X-Avatar-Agent-Key": os.environ.get("AVATAR_AGENT_KEY", "")}
        self.http = httpx.AsyncClient(timeout=120)

    async def whoami(self) -> dict | None:
        try:
            r = await self.http.get(f"{self.base}/api/admin-avatar-bridge/whoami", params={"identity": self.identity}, headers=self.h)
            return r.json() if r.status_code == 200 else None
        except httpx.HTTPError:
            return None

    async def overview(self) -> str:
        try:
            r = await self.http.get(f"{self.base}/api/admin-avatar-bridge/overview", params={"identity": self.identity}, headers=self.h)
            return r.text[:14000]
        except httpx.HTTPError as e:
            return json.dumps({"ok": False, "error": f"tableau de bord injoignable: {str(e)[:120]}"})

    async def catalog(self, q: str) -> str:
        r = await self.http.get(f"{self.base}/api/admin-avatar-bridge/catalog", params={"identity": self.identity, "q": q}, headers=self.h)
        return r.text[:12000]

    async def call(self, method: str, path: str, params: dict | None, body, confirmed: bool, summary: str) -> str:
        r = await self.http.post(f"{self.base}/api/admin-avatar-bridge/call", headers=self.h, json={
            "identity": self.identity, "method": method, "path": path, "params": params or {}, "body": body,
            "confirmed": confirmed, "summary": summary[:400]})
        return r.text[:14000]


def _json(s: str, default):
    if not s or not s.strip():
        return default
    try:
        return json.loads(s)
    except ValueError:
        return default


class AdminAssistant(Agent):
    def __init__(self, bridge: Bridge, lang: str, room=None, identity: str = "", knowledge: str = ""):
        super().__init__(instructions=PERSONA + RULES + LANG_TXT.get(lang, LANG_TXT["pt"]) + f" Site: {bridge.base}.\n" + knowledge)
        self.bridge, self.room, self.identity = bridge, room, identity

    # ------------------------------------------------------------------ Assistant BTP (structuré, sous les yeux de l'admin)
    @function_tool()
    async def assistant_ask(self, context: RunContext, request: str, new_conversation: bool = False, conversation_id: str = "") -> str:
        """Give a job to the Assistant BTP, shown live on the admin's screen (page /assistant). Write the request as a complete,
        precise instruction (what to produce, constraints, files already in the conversation). new_conversation=true for a new
        subject; conversation_id to continue a given one; otherwise continues the conversation open on screen.
        Returns the conversation state. Then call assistant_wait until done=true."""
        return await self._ui("assistant.ask", {"text": request, "new_conversation": new_conversation,
                                                "conversation_id": conversation_id}, timeout=40)

    @function_tool()
    async def assistant_wait(self, context: RunContext, seconds: int = 35) -> str:
        """Wait (up to 40 s) for the Assistant BTP to finish or to ask choices. Returns running, progress, last_answer, choices
        (pending choice cards with question ids, option ids and the recommended option), files produced and tools used.
        If done=false call it again (long studies take minutes); tell the admin briefly where it stands."""
        return await self._ui("assistant.wait", {"seconds": max(3, min(40, int(seconds)))}, timeout=55)

    @function_tool()
    async def assistant_status(self, context: RunContext) -> str:
        """Current state of the Assistant BTP conversation on screen (answer, pending choices, files, running job)."""
        return await self._ui("assistant.status", timeout=15)

    @function_tool()
    async def assistant_answer_choices(self, context: RunContext, answers_json: str = "", use_recommended: bool = False,
                                       other_json: str = "") -> str:
        """Answer the Assistant BTP's pending choice card by clicking it on screen, then submit. answers_json maps question id to
        option id (or a list of option ids for multi-choice), e.g. {"murs_ext": "brique_20", "planchers": "hourdis"}; questions
        not listed keep their recommended option. Use "other" as option id with other_json {"question_id": "free text"}.
        use_recommended=true submits every recommended option at once."""
        return await self._ui("assistant.choose", {"answers": _json(answers_json, {}), "other": _json(other_json, {}),
                                                   "use_recommended": use_recommended}, timeout=40)

    @function_tool()
    async def platform_overview(self, context: RunContext) -> str:
        """ConstruPilot dashboard in one call: users/activity stats, revenue KPIs, AI spending, leads, requests, daily health and
        recent tool errors (ERR-… references). Use it first for any 'how is ConstruPilot doing' / CEO / management question."""
        return await self.bridge.overview()

    async def _ui(self, method: str, payload: dict | None = None, timeout: float = 20) -> str:
        """Commande exécutée dans le navigateur de l'admin (RPC LiveKit vers la fenêtre flottante)."""
        if self.room is None:
            return '{"ok": false, "error": "écran indisponible"}'
        try:
            return await self.room.local_participant.perform_rpc(destination_identity=self.identity, method=method,
                                                                 payload=json.dumps(payload or {}), response_timeout=timeout)
        except Exception as e:  # noqa: BLE001 — page rechargée, onglet fermé…
            return json.dumps({"ok": False, "error": f"écran injoignable: {str(e)[:120]}"})

    @function_tool()
    async def ui_read(self, context: RunContext) -> str:
        """See the admin's current screen: path, title, visible text and the list of clickable/typable elements with their ids."""
        return await self._ui("ui.read")

    @function_tool()
    async def ui_navigate(self, context: RunContext, path: str) -> str:
        """Open a page of the site in the admin's browser, e.g. '/assistant', '/devis', '/factures', '/admin'."""
        return await self._ui("ui.navigate", {"path": path})

    @function_tool()
    async def ui_click(self, context: RunContext, element_id: str, confirmed: bool = False) -> str:
        """Click an element (id from the latest ui_read). Buttons that send, save, validate or delete need confirmed=true,
        given ONLY after the admin said yes."""
        return await self._ui("ui.click", {"id": element_id, "confirmed": confirmed})

    @function_tool()
    async def ui_type(self, context: RunContext, element_id: str, text: str, submit: bool = False) -> str:
        """Type text into a field (id from the latest ui_read); submit=true presses Enter afterwards."""
        return await self._ui("ui.type", {"id": element_id, "text": text, "submit": submit})

    @function_tool()
    async def ui_scroll(self, context: RunContext, direction: str = "down") -> str:
        """Scroll the admin's page 'down' or 'up'."""
        return await self._ui("ui.scroll", {"direction": direction})

    @function_tool()
    async def ui_back(self, context: RunContext) -> str:
        """Go back to the previous page in the admin's browser."""
        return await self._ui("ui.back")

    @function_tool()
    async def find_features(self, context: RunContext, keywords: str) -> str:
        """Find the site's API routes matching keywords (Portuguese, French or English words, e.g. 'utilizadores orçamentos', 'leads', 'stats').
        Returns method, path, summary and parameters. Use it before read/act when you do not know the exact path."""
        return await self.bridge.catalog(keywords)

    @function_tool()
    async def read(self, context: RunContext, path: str, params_json: str = "") -> str:
        """Read data from the site (HTTP GET) with the admin's rights. path like '/api/admin/users'; params_json a JSON object of query parameters."""
        return await self.bridge.call("GET", path, _json(params_json, {}), None, False, "")

    @function_tool()
    async def act(self, context: RunContext, method: str, path: str, summary: str, body_json: str = "",
                  params_json: str = "", confirmed: bool = False) -> str:
        """Change data on the site (method POST, PUT, PATCH or DELETE). summary = one sentence describing the action, as said to the admin.
        Set confirmed=true ONLY after the admin explicitly said yes to that exact action."""
        method = method.upper()
        if method not in ("POST", "PUT", "PATCH", "DELETE"):
            return "Método inválido: usa read para consultar."
        return await self.bridge.call(method, path, _json(params_json, {}), _json(body_json, None), confirmed, summary)


async def _admin_identity(ctx: JobContext, timeout: float = 30) -> str:
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        for p in ctx.room.remote_participants.values():
            if p.identity.startswith("admin-"):
                return p.identity
        await asyncio.sleep(0.5)
    raise RuntimeError("nenhum admin na sala")


async def entrypoint(ctx: JobContext):
    await ctx.connect()
    meta = _json(ctx.job.metadata or "", {}) if isinstance(ctx.job.metadata, str) else {}
    lang = (meta.get("lang") or "pt").lower()
    identity = await _admin_identity(ctx)
    order = ["fr", "pt"] if lang == "fr" else ["pt", "fr"]
    bridge, me = None, None
    for site in order:  # o admin pertence ao site onde a ponte o reconhece
        b = Bridge(SITES[site], identity)
        me = await b.whoami()
        if me:
            bridge = b
            break
    if bridge is None:
        log.warning("admin %s não reconhecido por nenhuma ponte", identity)
        bridge = Bridge(SITES[order[0]], identity)

    # Assistente mulher (35-45 anos, forte presença) ; repli sur Kenji si l'espace Synthesia refuse les autres.
    forced = [x.strip() for x in os.environ.get("AVATAR_IDS", "").split(",") if x.strip()]
    voice = (os.environ.get("AVATAR_VOICE") or "marin").strip()
    candidates = [(i, voice) for i in forced] or [(JENNY, voice), (MEI, voice), (KENJI, "cedar")]
    session, ok, err = None, False, None
    for avatar_id, voice in candidates:
        # Voix + mains : gpt-realtime-2.1 (raisonnement réglable, appels d'outils fiables, latence plus basse) ; le travail
        # lourd est délégué à l'Assistant BTP, d'où un raisonnement « low » par défaut pour garder une voix réactive.
        # Changeable sans toucher au code : AVATAR_REALTIME_MODEL / AVATAR_REASONING (minimal|low|medium|high|xhigh).
        rt = {"voice": voice, "model": os.environ.get("AVATAR_REALTIME_MODEL") or "gpt-realtime-2.1"}
        effort = (os.environ.get("AVATAR_REASONING") or "low").strip()
        if effort in ("minimal", "low", "medium", "high", "xhigh") and "realtime-2" in rt["model"]:
            from openai.types.realtime import RealtimeReasoning
            rt["reasoning"] = RealtimeReasoning(effort=effort)
        session = AgentSession(llm=openai.realtime.RealtimeModel(**rt), max_tool_steps=60)
        avatar = synthesia.AvatarSession(synthesia.AvatarConfig(avatar_ids=[avatar_id]))
        try:
            await avatar.start(session, room=ctx.room)  # antes de session.start — a ordem conta
            log.info("avatar %s (voz %s)", avatar_id, voice)
            ok = True
            break
        except synthesia.SynthesiaError as e:
            err = e
            kind = str(getattr(e, "type", "")).upper()
            log.warning("avatar %s recusado: %s", avatar_id, kind or e)
            if not kind.endswith(("UNKNOWN_AVATAR", "INVALID_SESSION_REQUEST")):
                break
    if not ok:  # mensagem legível para o painel admin (topic « avatar »)
        kind = str(getattr(err, "type", "error")).split(".")[-1].lower()
        code = {"concurrency_limit": "busy", "quota_exceeded": "quota", "auth": "config", "feature_not_in_plan": "config"}.get(kind, "error")
        await ctx.room.local_participant.publish_data(json.dumps({"type": "avatar_status", "code": code, "detail": str(err)[:200]}).encode(),
                                                      reliable=True, topic="avatar")
        raise err or RuntimeError("avatar indisponível")
    first = ((me or {}).get("name") or "").strip().split(" ")[0][:40]
    who = f"The admin's first name is {first}. " if first else ""
    await session.start(agent=AdminAssistant(bridge, lang, ctx.room, identity, who + (me or {}).get("knowledge", "")), room=ctx.room)
    await attach_screen(ctx, session, identity)  # Lot 42 : écran en direct + internet + autonomie
    await session.generate_reply(instructions=GREET.get(lang, GREET["pt"]))



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
    out = []
    if s.get("not_found"):
        out.append("THIS PAGE DOES NOT EXIST (404): go back (ui_back) and pick a real page from SITE PAGES, say so in one sentence.")
    out += [f"Page: {s.get('path', '?')} — {s.get('title', '')} (moved by {s.get('actor', 'admin')}, scroll {s.get('scroll', 0)}%)"]
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
    return "\n".join(out)[:4600]


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
        self.menu: list = []

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
        if data.get("menu"):
            self.menu = data["menu"]
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
            if self.menu:
                text += "\nSITE PAGES (the ONLY valid paths for ui_navigate on this site — never invent one): " + ", ".join(self.menu)[:2500]
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


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name=AGENT_NAME))
