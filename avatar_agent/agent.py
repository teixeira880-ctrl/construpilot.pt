"""Agente de voz « construpilot-avatar » — assistente de vídeo interno dos admins ConstruPilot.

Avatar Synthesia (Interactive Avatar) + OpenAI Realtime, a correr no LiveKit Cloud.
Age no site (construpilot.pt ou construpilot.fr) em nome do admin que abriu a sessão,
através da ponte /api/admin-avatar-bridge (chave AVATAR_AGENT_KEY). A ponte aplica as
regras no servidor: leituras livres, escritas só com confirmação, rotas sensíveis proibidas.

Variáveis de ambiente (segredos do agente no LiveKit Cloud, nunca no código):
  SYNTHESIA_API_KEY, OPENAI_API_KEY, AVATAR_AGENT_KEY
  CONSTRUPILOT_PT_URL (https://construpilot.pt), CONSTRUPILOT_FR_URL (https://construpilot.fr)
  AVATAR_IDS   ids Synthesia separados por vírgula (1.º = ativo; por defeito Kenji)
  AVATAR_VOICE voz OpenAI Realtime (por defeito « marin »)
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
SITES = {"pt": os.environ.get("CONSTRUPILOT_PT_URL", "https://construpilot.pt"),
         "fr": os.environ.get("CONSTRUPILOT_FR_URL", "https://construpilot.fr")}

RULES = (
    "You are the INTERNAL video assistant of the ConstruPilot team, shown only to administrators in the admin area. "
    "You can act on the website with the admin's rights through your tools: find_features (discover API routes by keywords), "
    "read (GET, free) and act (POST/PUT/PATCH/DELETE). "
    "Rules: (1) before ANY action that changes data, say in one sentence exactly what you will do and ask 'Confirmas?'/'Vous confirmez ?'; "
    "call act with confirmed=true ONLY after a clear yes in the admin's last answer; otherwise call nothing. "
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
    def __init__(self, bridge: Bridge, lang: str):
        super().__init__(instructions=RULES + LANG_TXT.get(lang, LANG_TXT["pt"]) + f" Site: {bridge.base}.")
        self.bridge = bridge

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

    session = AgentSession(llm=openai.realtime.RealtimeModel(voice=os.environ.get("AVATAR_VOICE", "marin")))
    ids = [x.strip() for x in os.environ.get("AVATAR_IDS", KENJI).split(",") if x.strip()][:5]
    avatar = synthesia.AvatarSession(synthesia.AvatarConfig(avatar_ids=ids))
    try:
        await avatar.start(session, room=ctx.room)  # antes de session.start — a ordem conta
    except synthesia.SynthesiaError as e:  # mensagem legível para o painel admin (topic « avatar »)
        await ctx.room.local_participant.publish_data(json.dumps({"error": str(getattr(e, "type", "UNKNOWN")),
                                                                  "message": str(e)[:200]}), topic="avatar")
        raise
    await session.start(agent=AdminAssistant(bridge, lang), room=ctx.room)
    await session.generate_reply(instructions=GREET.get(lang, GREET["pt"]))


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name=AGENT_NAME))
