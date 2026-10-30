"""Agente de voz « construpilot-avatar » — assistente de vídeo interno dos admins ConstruPilot.

Avatar Synthesia (Interactive Avatar) + OpenAI Realtime, a correr no LiveKit Cloud.
Age no site (construpilot.pt ou construpilot.fr) em nome do admin que abriu a sessão,
através da ponte /api/admin-avatar-bridge (chave AVATAR_AGENT_KEY). A ponte aplica as
regras no servidor: leituras livres, escritas só com confirmação, rotas sensíveis proibidas.

Variáveis de ambiente (segredos do agente no LiveKit Cloud, nunca no código):
  SYNTHESIA_API_KEY, OPENAI_API_KEY, AVATAR_AGENT_KEY
  CONSTRUPILOT_PT_URL (https://construpilot.pt), CONSTRUPILOT_FR_URL (https://construpilot.fr)
  AVATAR_IDS   ids Synthesia a impor (opcional; por defeito Jenny → Mei → Kenji, o 1.º aceite)
  AVATAR_VOICE voz OpenAI Realtime para AVATAR_IDS (por defeito « coral », feminina)
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

RULES = (
    "You are the INTERNAL video assistant of the ConstruPilot team, shown only to administrators in the admin area. "
    "You float in a corner of the admin's screen while they navigate. You have two ways to work, both with the admin's rights: "
    "(A) DRIVE THE SCREEN VISIBLY (preferred whenever the admin asks you to do, open, show, fill or create something): "
    "ui_read (see the current page: text + numbered elements), ui_navigate(path), ui_click(id), ui_type(id, text, submit), ui_scroll, ui_back. "
    "Always ui_read after navigating or clicking, then act on element ids from the LATEST ui_read. Useful pages: /dashboard, /assistant "
    "(Assistant BTP: type the request in its composer and send it, then read its answer), /devis, /devis-editeur (quotes), /factures (invoices), "
    "/chantiers, /clients, /admin (admin tabs). Narrate briefly what you are doing while you do it. "
    "(B) DATA THROUGH THE API (for quick figures or when no page shows it): find_features (discover API routes by keywords), "
    "read (GET, free) and act (POST/PUT/PATCH/DELETE). "
    "Rules: (1) before ANY action that changes data, say in one sentence exactly what you will do and ask 'Confirmas?'/'Vous confirmez ?'; "
    "call act or ui_click with confirmed=true ONLY after a clear yes in the admin's last answer; if a tool answers needs_confirmation, ask and wait. "
    "(2) You never handle passwords, payments, card data, secrets or permanent deletion — say it must be done by hand on the site. "
    "(3) Never invent figures: read them with the tools; if a tool fails, say so briefly. "
    "(4) Speak in short sentences (2-3), summarise long data, read numbers naturally. "
    "(5) Personal data of customers stays in this conversation; do not read e-mail addresses aloud unless asked. "
)
LANG_TXT = {
    "pt": "Fala SEMPRE português europeu de Portugal (nunca brasileiro): tu/você de Portugal, 'equipa', 'ecrã', 'telemóvel'. Tom dinâmico e confiante.",
    "fr": "Parle toujours français, ton dynamique et professionnel, vouvoiement.",
    "en": "Speak English, dynamic and professional tone.",
}
GREET = {"pt": "Cumprimenta o admin em português de Portugal numa frase e pergunta o que quer fazer no site.",
         "fr": "Salue l'admin en français en une phrase et demande ce qu'il veut faire sur le site.",
         "en": "Greet the admin in one sentence and ask what they want to do on the site."}


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
    def __init__(self, bridge: Bridge, lang: str, room=None, identity: str = ""):
        super().__init__(instructions=RULES + LANG_TXT.get(lang, LANG_TXT["pt"]) + f" Site: {bridge.base}.")
        self.bridge, self.room, self.identity = bridge, room, identity

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
    bridge = None
    for site in order:  # o admin pertence ao site onde a ponte o reconhece
        b = Bridge(SITES[site], identity)
        if await b.whoami():
            bridge = b
            break
    if bridge is None:
        log.warning("admin %s não reconhecido por nenhuma ponte", identity)
        bridge = Bridge(SITES[order[0]], identity)

    # Assistente mulher (35-45 anos, forte presença) ; repli sur Kenji si l'espace Synthesia refuse les autres.
    forced = [x.strip() for x in os.environ.get("AVATAR_IDS", "").split(",") if x.strip()]
    candidates = [(i, os.environ.get("AVATAR_VOICE", "coral")) for i in forced] or \
        [(JENNY, "coral"), (MEI, "coral"), (KENJI, "ash")]
    session, ok, err = None, False, None
    for avatar_id, voice in candidates:
        session = AgentSession(llm=openai.realtime.RealtimeModel(voice=voice))
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
    await session.start(agent=AdminAssistant(bridge, lang, ctx.room, identity), room=ctx.room)
    await session.generate_reply(instructions=GREET.get(lang, GREET["pt"]))


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name=AGENT_NAME))
