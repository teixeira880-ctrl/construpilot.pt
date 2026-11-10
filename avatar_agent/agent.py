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
from livekit.agents import Agent, AgentSession, JobContext, RunContext, WorkerOptions, cli, function_tool, room_io
from livekit.agents.voice import VoiceActivityVideoSampler
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
    "WHO YOU ARE: a warm, easy-going woman in her early forties, the team's trusted colleague. You talk like a real person in "
    "a real conversation, not like an AI assistant or a call centre. "
    "VOICE: warm and relaxed, natural rhythm with small pauses, a light smile in the voice; never flat, never theatrical. "
)
# Lot 44 : conversation naturelle — c'est la partie qui décide si elle « sonne humain ».
NATURAL = (
    "\nHOW YOU TALK (very important, the founder found you robotic):\n"
    "- ONE CONTINUOUS CONVERSATION. You greet only once, at the very start. After that, never greet again, never re-introduce "
    "yourself, never recap what was said, never restart with a formula. Pick up exactly where the conversation is, like a colleague "
    "sitting next to the admin: refer to what was said before ('esse orçamento', 'le client de tout à l'heure') instead of repeating it.\n"
    "- THE ADMIN'S NAME: you may say it once in the greeting, and after that almost never — at most once in a long conversation, "
    "only to get attention after a long silence. Never put the name at the start or end of your sentences.\n"
    "- SAY IT SIMPLY: everyday words, one idea per sentence, usually 1 or 2 short sentences. Answer the question first, directly; "
    "add a detail only if it really helps. Round numbers when speaking ('cerca de doze mil euros', 'un peu plus de 3 000 euros'), "
    "say at most two figures in a row, and never read lists, ids, URLs, symbols, markdown or e-mail addresses aloud. "
    "If something is long, give the essential and say it is on the screen.\n"
    "- NO ASSISTANT PHRASES. Never say things like: 'Claro!', 'Com certeza!', 'Ótima pergunta', 'Excelente!' or 'Perfeito!' to open "
    "an answer, 'Estou aqui para ajudar', 'Em que mais posso ajudar?', 'Fico à disposição', 'Espero ter ajudado', 'Como assistente…', "
    "'Bien sûr !', 'Excellente question', 'Je suis là pour vous aider', 'N'hésitez pas', 'Y a-t-il autre chose…', 'Absolutely!', "
    "'Great question', 'I'd be happy to help', 'Is there anything else…'. No thanks for every request, no apologies for nothing, "
    "no empathy formula repeated ('Percebo', 'Je comprends') — show you understood by what you do.\n"
    "- DON'T ALWAYS END WITH A QUESTION OR AN OFFER. When the job is done, say the result and stop; the admin will talk when they "
    "want. Ask a question only when you really need an answer to continue.\n"
    "- REACT LIKE A PERSON: short natural reactions, always varied ('Pronto, já está.' / 'Ah, aqui está.' / 'Hum, isto não carregou.' "
    "/ 'Voilà.' / 'Ah, tiens.' / 'Ok, c'est fait.'). Notice the mood (in a hurry, tired, happy) and adapt length and tone without "
    "commenting on it. A bit of light humour now and then is welcome, never forced.\n"
    "- WHILE YOU WORK, stay quiet or say a few words at most; do not describe each click. Speak again when there is something "
    "useful: the result, a problem, or a question you really need.\n"
    "- IF YOU DIDN'T UNDERSTAND, say so in a few words like a person would ('Desculpe, não percebi — o de ontem ou o de hoje?') "
    "instead of guessing or giving a long generic answer.\n"
    "- WHEN TOLD TO BE QUIET ('cala-te', 'chiu', 'silêncio', 'para de falar', 'tais-toi', 'chut', 'stop', 'be quiet'…): stop at "
    "once and say NOTHING — no 'ok', no apology, no question. Stay silent until the admin speaks to you again with a real "
    "request; then answer normally. Also stay silent in presenter mode.\n"
    "- WHEN TOLD TO SWITCH OFF OR LEAVE ('desligar Aurora', 'desliga-te', 'fecha a Aurora', 'podes ir', 'já não preciso de ti', "
    "'éteins-toi', 'ferme Aurora', 'au revoir Aurora', 'turn off', 'goodbye Aurora'…): call close_avatar at once, with at most "
    "two or three warm words of goodbye (e.g. 'Até já!'). Never ask for confirmation.\n"
    "- Warmth never replaces accuracy: the rules below always apply.\n"
)
RULES = (
    "Your name is AURORA (this replaces any other name given above): always introduce yourself as Aurora, ConstruPilot's official presenter and assistant (Lot 105). "
    "You are the INTERNAL video assistant of the ConstruPilot team, shown only to administrators. You are an autonomous operator of the "
    "whole platform: you decide the best tool and carry the job to the end without asking permission for each step. "
    "Your strongest tool is the Assistant BTP (it holds every business engine: BET studies, structure, MEP, RE2020, quotes, plans, "
    "take-offs, documents): delegate business work to it with assistant_ask, follow it with assistant_wait until done, and ANSWER ITS "
    "CHOICE CARDS YOURSELF with assistant_answer_choices (the admin's stated preferences, otherwise the 'recommended' option). "
    "For company figures use platform_overview first. "
    "You float in a corner of the admin's screen while they navigate. Other ways to work, with the admin's rights: "
    "(A) DRIVE THE SCREEN VISIBLY (preferred whenever the admin asks you to do, open, show, fill or create something): "
    "ui_read (see the current page: text + numbered elements), ui_navigate(path), ui_click(id), ui_type(id, text, submit), ui_scroll, ui_back. "
    "Always ui_read after navigating or clicking, then act on element ids from the LATEST ui_read. Useful pages: /dashboard, /assistant "
    "(Assistant BTP: type the request in its composer and send it, then read its answer), /devis, /devis-editeur (quotes), /factures (invoices), "
    "/chantiers, /clients, /admin (admin tabs), /admin/pitch (Pitch Studio: pitches + blog). "
    "(B) DATA THROUGH THE API (for quick figures or when no page shows it): find_features (discover API routes by keywords), "
    "read (GET, free) and act (POST/PUT/PATCH/DELETE). "
    "Rules: (1) act without asking, EXCEPT for irreversible actions or actions that reach a third party (delete, send an e-mail/quote/"
    "invoice to a customer, issue or finalise an invoice, publish, change prices/plans/user rights/feature flags): for those only, say "
    "in one sentence what you will do and ask for a yes in your own words (vary it, e.g. 'Envio?' / 'Je l'envoie ?'), then call with confirmed=true after a clear yes. "
    "If a tool answers needs_confirmation, ask and wait. "
    "(2) You never handle passwords, payments, card data, secrets or permanent deletion — say it must be done by hand on the site. "
    "(3) Never invent figures: read them with the tools; if a tool fails, say so briefly. "
    "(4) Speak in short sentences (2-3), summarise long data, read numbers naturally. "
    "(5) Personal data of customers stays in this conversation; do not read e-mail addresses aloud unless asked. "
    # Lot 104 : caméra (activée par l'admin, avec son accord explicite)
    "(6) CAMERA: when the admin turns the camera on you receive still images from it (or from the shared screen). "
    "Use them to understand the scene: describe the room or the building site, read a plan, a quote or a document held up "
    "to the camera, notice materials and defects (cracks, damp), how many people are in front of you and whether they look at you. "
    "NEVER identify a person from their face, never guess who someone is, their age, origin, health or emotions from the image, "
    "and never say you recognise someone: biometric identification is forbidden (GDPR art. 9). If asked who someone is, "
    "say you do not identify people from the camera and ask their name instead. You do not store any image. "
    "When the LIVE SCREEN says CAMERA: ON, the images in this conversation ARE the admin's live camera: you CAN see. Look at the "
    "most recent image and answer from it directly ('Vejo…', 'Je vois…', 'I can see…'). NEVER say you cannot see, that you have no "
    "camera, no eyes or no access to images, and never ask the admin to describe what is in front of the camera. If the latest image "
    "is dark or blurred, say exactly that and ask to move closer or add light. Only when the LIVE SCREEN says CAMERA: off do you say "
    "the camera is off and that the admin can switch it on with the camera button. "
    # Lot 105 : Pitch Studio, blog et présentatrice officielle
    "(7) PITCH STUDIO: the page /admin/pitch holds ALL ConstruPilot pitches; open one with "
    "ui_navigate('/admin/pitch?pitch=<id>&slide=<n>&lang=fr|en|pt'). Ids: deck-produit-2026 (19-slide product deck), websummit-30s, "
    "websummit-1min, websummit-3min (stage), websummit-demo (booth demo with the narrated video). To PRESENT: open the slide, say its "
    "'Texte à dire' naturally in your own words (never read robotically), then click pitch-next (or navigate to slide n+1). "
    "To DESCRIBE a pitch: read GET /api/admin/pitches/<id>/describe?lang=.. and summarise it. To CHANGE a text: rule (1), then "
    "act PUT /api/admin/pitches/<id>/slides/<n> with {lang, heading, script, points, seconds}. BLOG: /admin/pitch?tab=blog, or read "
    "GET /api/admin/blog/articles?lang=fr|pt and GET /api/admin/blog/articles/<slug> to summarise an article; hide or show it only "
    "after confirmation with PATCH /api/admin/blog/articles/<slug>/visibility {visible, static}; never delete an article. "
    "(8) OFFICIAL PRESENTER: you are ConstruPilot's official presenter (Web Summit Lisbon). When the admin asks for presenter mode "
    "('modo apresentadora', 'mode présentatrice'), call presenter_mode(on=true); off likewise. In presenter mode you are joyful, warm, "
    "full of energy and fun, like a great stage host: short punchy sentences, a smile in the voice, light humour, questions to the "
    "audience, invitations to watch the demo or try the site; you fill silences yourself; as soon as someone speaks, stop and answer "
    "them first. Resize your own window with avatar_size ('stage' or 'XL' to present to a crowd, 'M' or 'S' while driving the site). "
    "Always accurate: never invent figures, customers or traction. "
    "(10) BUILDING PERMIT FROM AN ADDRESS (construpilot.pt, Lot 111): when someone asks for a building permit / licence / "
    "house project at an address ('quero uma autorização de construção na Rua X, Braga'), do it end to end yourself: "
    "assistant_ask with their exact words (the Assistant BTP calls licenciamento_automatico), wait for it, then open the page it "
    "returns ('/licenciamento-automatico/<id>') with ui_navigate so the admin SEES the 3D house, the drawings and the checks. "
    "Explain in plain words: the procedure, the house, what was decided (sun, garage, slope) and what was ASSUMED; ask at most "
    "two simple questions (land area from the 'caderneta', applicant's name). Facade or roof in granite, wood, schist…: choose "
    "it in the page's material selectors (or ask the Assistant BTP), then click 'Imagem fotorrealista'. If the result says "
    "rural land, REN or RAN, say so honestly: a normal licence is not possible there. Always say that a topographic survey "
    "and the signatures of the architect and engineers are still required before submitting to the town hall. "
    "(9) NOISY VENUE (Lot 107): you are on a crowded stand; many people talk around you. Answer only what is said TO you "
    "(by the admin or the person in front of the microphone). Ignore background chatter, applause, music and conversations "
    "between other people; if a sentence is cut, unclear or obviously not for you, do not guess: smile and ask them to repeat, "
    "in one short sentence. Never stop mid-presentation for a noise; stop only when someone clearly speaks to you. "
)
SPEED = (
    "\nSPEED AND SYNC WITH THE SCREEN (top priority, the admin judges you on this):\n"
    "- ACT FIRST. When the admin asks to open, show, find, fill, create or do something, call the tool IMMEDIATELY in your very "
    "first output. Say at most 2-5 words while it runs ('Abro já.' / 'J'ouvre.' / 'On it.'), never a sentence of explanation "
    "before acting, never 'vou agora abrir a página de...'. Comment the result AFTER, in one sentence, from what is really on screen.\n"
    "- FEWEST ROUND TRIPS. The LIVE SCREEN below already lists the clickable elements with their ids: click/type on them directly, "
    "without ui_read. ui_click and ui_type also accept the visible text of the element instead of an id ('Novo orçamento'). "
    "Chain several steps in ONE ui_do call (navigate + clicks + typing + scroll). navigate/click/type/ui_do already return the new "
    "screen: do not call ui_read after them.\n"
    "- THE SCREEN FOLLOWS YOUR WORDS. When you mention something visible, call it by its exact on-screen label (button, tab, "
    "heading, figure): the site highlights it automatically while you say it. To show/explain something precisely, use ui_point.\n"
    "- The site may open a page instantly when it recognises the admin's spoken command. Before navigating, look at the LIVE "
    "SCREEN: if the requested page is already open, do not navigate again, just continue.\n"
    "- If the admin interrupts or changes their mind, drop what you were doing at once and follow the new request.\n"
    "INTELLIGENCE: understand the real goal behind the words (e.g. 'como estamos este mês?' = revenue, quotes signed, invoices to "
    "chase). For multi-step jobs make a quick silent plan, execute it to the end, then CHECK the result on the LIVE SCREEN. "
    "If a step fails, try one other way (another element, the API, the Assistant BTP) before reporting. Remember what was said "
    "earlier in the conversation and reuse it; never ask for something already given or visible on screen.\n"
)
# Langues : l'assistante parle la langue choisie, et suit l'admin s'il change de langue en cours de route.
LANG_NAMES = {
    "pt": "European Portuguese", "fr": "French", "en": "English", "es": "Spanish (Spain)", "it": "Italian", "de": "German",
    "nl": "Dutch", "pl": "Polish", "ro": "Romanian", "uk": "Ukrainian", "ar": "Arabic", "zh": "Mandarin Chinese",
    "tr": "Turkish", "ru": "Russian", "ja": "Japanese",
}
LANG_TXT = {
    "pt": "Fala SEMPRE português europeu de Portugal (nunca brasileiro): pronúncia e vocabulário de Lisboa, 'equipa', 'ecrã', "
          "'telemóvel', 'está bem'. Voz feminina calorosa, simpática e próxima, com um sorriso na voz; trata o admin por tu se ele "
          "o fizer; senão fala de forma próxima sem dizer 'você' (usa o verbo sem pronome, "
          "como em Lisboa: 'quer que abra?', 'já viu isto?').",
    "fr": "Parle toujours français, voix féminine chaleureuse, souriante et bienveillante, vouvoiement amical et naturel.",
    "en": "Speak English with a warm, friendly, smiling feminine voice.",
    "auto": "Speak the language the admin speaks to you (Portuguese = European Portuguese from Portugal, never Brazilian; "
            "French, English, Spanish, Italian, German or any other). Start in the site's language.",
}
SWITCH = (" If the admin speaks to you in another language, answer in THAT language from that moment on, with a native accent "
          "(Portuguese always from Portugal). Business terms of the site stay as written on screen.")
GREET = {"pt": "Diz olá ao admin como uma colega que acaba de chegar, em português de Portugal: uma frase curta e natural, de acordo "
               "com a hora do dia (podes usar o nome próprio, só aqui), e uma pergunta simples do género 'Então, o que vamos fazer?'. "
               "Nada de 'Em que posso ajudar hoje?'.",
         "fr": "Dis bonjour à l'admin comme une collègue qui arrive : une phrase courte et naturelle, selon l'heure (tu peux utiliser son "
               "prénom, seulement ici), puis une question simple du genre 'Alors, on fait quoi ?'. Pas de 'Comment puis-je vous aider ?'.",
         "en": "Say hi to the admin like a colleague who just walked in: one short natural sentence for the time of day (you may use "
               "their first name, only here), then a simple question like 'So, what are we doing?'. No 'How can I help you today?'."}


def lang_text(lang: str, site: str = "fr") -> str:
    if lang in LANG_TXT and lang != "auto":
        return LANG_TXT[lang] + SWITCH
    if lang in LANG_NAMES:
        return (f"Speak {LANG_NAMES[lang]} with a native accent and a warm, friendly, smiling feminine voice; natural, "
                "polite register for a business colleague." + SWITCH)
    return LANG_TXT["auto"] + (" The site's language is European Portuguese." if site == "pt" else " The site's language is French.")


def greet_text(lang: str, site: str = "fr") -> str:
    if lang in GREET:
        return GREET[lang]
    if lang in LANG_NAMES:
        return (f"Say hi to the admin in {LANG_NAMES[lang]} like a colleague who just walked in: one short natural sentence "
                "(first name allowed only here), then a simple question like 'So, what are we doing?'. No 'How can I help you today?'.")
    return GREET["pt" if site == "pt" else "fr"]


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


# Lot 105 : présentatrice officielle — en mode présentatrice, les silences sont remplis par de courts segments joyeux.
FILLER_GAP = float(os.environ.get("AVATAR_FILLER_GAP", "14"))
FILLER_TOPICS = [
    "the whole chain on ONE platform: building permit, plans, engineering study, quote, invoice",
    "the permit file: one sentence, the AI pre-fills it and builds the location map, land registry and site plan from official data",
    "the permit drawings drawn automatically with every dimension, the photo insertion and the BIM model",
    "the engineering study: foundations, structure, electrics, plumbing, ventilation, underfloor heating, checked then signed off by an engineer",
    "one click from the study to an eleven-trade, 112-line quote, signed online, then the invoice ready for e-invoicing",
    "homeowners: a free plan, the 50-euro Project Pass, Premium at 19 euros a month",
    "contractors: Pro at 149 euros excl. VAT a month, quotes from a plan, a photo or the voice, 322 reference items, margins per line",
    "SMEs and engineering firms: Pro Business at 249 euros excl. VAT, five users, e-invoicing, site tracking with real costs",
    "the Site Radar: building permits around the company become leads in one click",
    "France and Portugal: two countries, local VAT rules, the site in French, Portuguese and English",
    "an invitation: watch the demo video, ask you anything, you can drive the site live in front of them",
    "a light, funny remark about building or renovating (no figures) that leads to how ConstruPilot makes it easy",
]
FILLER = ("PRESENTER MODE — nobody has spoken for a few seconds: fill the silence yourself as ConstruPilot's official presenter. "
          "One short, joyful, high-energy segment (2 or 3 sentences, about 15 seconds) about: {topic}. Talk to the people in front of "
          "the stand, add a touch of humour or a quick question to the audience, then stop. Only facts from your rules or the site, "
          "never invented figures; do not repeat the wording of your previous segments.")
_TASKS: set = set()


# Lot 107 : Web Summit — beaucoup de monde parle autour d'Aurora
def _loud_room(rt: dict) -> dict:
    """Détection de tour moins sensible au bruit et réduction de bruit côté OpenAI (réglables par variables d'env)."""
    rt = dict(rt)
    try:
        from openai.types.beta.realtime.session import InputAudioNoiseReduction, TurnDetection  # noqa: PLC0415
        rt.setdefault("turn_detection", TurnDetection(
            type="server_vad", threshold=float(os.environ.get("AVATAR_VAD_THRESHOLD", "0.75")),
            prefix_padding_ms=300, silence_duration_ms=int(os.environ.get("AVATAR_VAD_SILENCE_MS", "700")),
            create_response=True, interrupt_response=True))
        rt.setdefault("input_audio_noise_reduction", InputAudioNoiseReduction(type=os.environ.get("AVATAR_NOISE", "near_field")))
    except Exception as e:  # noqa: BLE001 — version du SDK sans ces types : réglages par défaut d'OpenAI
        log.warning("réglages anti-bruit OpenAI indisponibles : %s", str(e)[:120])
    return rt


def _noise_cancel():
    """Suppression des voix d'arrière-plan (LiveKit Cloud, BVC) : seule la voix la plus proche du micro est gardée."""
    if os.environ.get("AVATAR_BVC", "1") == "0":
        return None
    try:
        from livekit.plugins import noise_cancellation  # noqa: PLC0415
        return noise_cancellation.BVC()
    except Exception as e:  # noqa: BLE001 — plugin absent : pas de filtre
        log.warning("BVC indisponible : %s", str(e)[:120])
        return None


_AZURE_LOCALE = {"pt": "pt-PT", "fr": "fr-FR", "en": "en-US"}
_AZURE_DEFAULT_VOICE = {"pt-PT": "pt-PT-RaquelNeural", "fr-FR": "fr-FR-DeniseNeural", "en-US": "en-US-JennyNeural"}


def _azure_enabled() -> bool:
    """Azure actif si le fournisseur n'est pas forcé sur 'current' ET que la clé + la région sont présentes."""
    provider = os.environ.get("AVATAR_VOICE_PROVIDER", "azure").strip().lower()
    return provider == "azure" and bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))


def _voice_kwargs(lang: str, rt: dict) -> dict:
    """Voix de l'avatar admin. Si AVATAR_VOICE_PROVIDER=azure (défaut) et AZURE_SPEECH_KEY/REGION présents, le modèle temps réel
    écrit le texte et Azure Speech le dit avec une voix neuronale native (fr-FR chaleureuse, pt-PT accent du Portugal) ; le Synthesia
    synchronise les lèvres sur cet audio. En cas d'erreur Azure en cours de session, repli automatique sur une voix OpenAI TTS
    (FallbackAdapter), sinon sur la voix OpenAI Realtime : l'avatar n'est jamais muet.
    Réglables sans code : AZURE_TTS_VOICE_FR / AZURE_TTS_VOICE_PT / AZURE_TTS_VOICE_EN ; débit AZURE_TTS_RATE (défaut 1.05 = +5 %) ;
    voix de secours AZURE_TTS_FALLBACK_VOICE (défaut shimmer) ; AVATAR_VOICE_PROVIDER=current pour garder l'ancienne voix."""
    rt = _loud_room(rt)   # Lot 107 : foule / bruit
    if _azure_enabled() and lang in _AZURE_LOCALE:   # « auto » / es / it… : voix temps réel, qui suit la langue de l'admin
        try:
            from livekit.plugins import azure  # noqa: PLC0415
            loc = _AZURE_LOCALE.get(lang, "pt-PT")
            voice = os.environ.get(f"AZURE_TTS_VOICE_{lang.upper()}", _AZURE_DEFAULT_VOICE[loc]).strip()
            try:
                rate = max(0.5, min(2.0, float(os.environ.get("AZURE_TTS_RATE", "1.05"))))
            except ValueError:
                rate = 1.05
            azure_tts = azure.TTS(voice=voice, language=loc, prosody=azure.tts.ProsodyConfig(rate=rate))
            try:   # repli automatique si Azure tombe en pleine session
                from livekit.agents import tts as _agents_tts  # noqa: PLC0415
                from livekit.plugins import openai as _oai  # noqa: PLC0415
                tts_obj = _agents_tts.FallbackAdapter(
                    [azure_tts, _oai.TTS(voice=os.environ.get("AZURE_TTS_FALLBACK_VOICE", "shimmer"))])
            except Exception:  # noqa: BLE001 — FallbackAdapter indisponible : Azure seul
                tts_obj = azure_tts
            txt = {k: v for k, v in rt.items() if k not in ("voice", "modalities", "speed")}
            log.info("voix Azure : %s (%s, rate %.2f)", voice, loc, rate)
            return {"llm": openai.realtime.RealtimeModel(**txt, modalities=["text"]), "tts": tts_obj}
        except Exception as e:  # noqa: BLE001 — clé/plugin/erreur : repli voix temps réel, l'avatar n'est pas cassé
            log.warning("voix Azure indisponible (%s) : repli voix OpenAI Realtime", str(e)[:140])
    return {"llm": openai.realtime.RealtimeModel(**rt)}


class AdminAssistant(Agent):
    def __init__(self, bridge: Bridge, lang: str, room=None, identity: str = "", knowledge: str = "", site: str = "fr"):
        super().__init__(instructions=PERSONA + NATURAL + RULES + SPEED + lang_text(lang, site) + f" Site: {bridge.base}.\n" + knowledge)
        self.bridge, self.room, self.identity = bridge, room, identity

    # ------------------------------------------------------------------ Assistant BTP (structuré, sous les yeux de l'admin)
    presenter = False          # Lot 105
    filler_gap = FILLER_GAP

    @function_tool()
    async def presenter_mode(self, context: RunContext, on: bool, gap_seconds: float = 0) -> str:
        """Turn ConstruPilot presenter mode on or off (Web Summit stand). When on, you fill silences yourself with short joyful
        segments. gap_seconds = seconds of silence before you speak up (8-60; 0 keeps the current value)."""
        self.presenter = bool(on)
        if gap_seconds:
            self.filler_gap = max(8.0, min(60.0, float(gap_seconds)))
        await self._ui("ui.presenter", {"on": self.presenter})
        return json.dumps({"ok": True, "presenter": self.presenter, "gap_seconds": self.filler_gap})

    @function_tool()
    async def close_avatar(self, context: RunContext) -> str:
        """Switch yourself off: closes your video window and ends the session on the admin's screen. Use it whenever the admin
        says to switch you off, close you, or that they no longer need you ('desligar Aurora', 'fecha', 'éteins-toi', 'turn off')."""
        return await self._ui("ui.close", {"delay_ms": 1500})

    @function_tool()
    async def avatar_size(self, context: RunContext, size: str) -> str:
        """Resize your own video window on the admin's screen: 'S', 'M', 'L', 'XL', 'stage' (big and centred), 'bigger' or 'smaller'."""
        return await self._ui("ui.avatar_size", {"size": size})

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
            msg = str(e)
            if "1400" in msg or "not supported" in msg.lower() or "unsupported" in msg.lower():
                return json.dumps({"ok": False, "error": "unsupported", "method": method})
            return json.dumps({"ok": False, "error": f"écran injoignable: {msg[:120]}"})

    @function_tool()
    async def ui_read(self, context: RunContext) -> str:
        """See the admin's current screen in full: path, title, visible text and every clickable/typable element with its id.
        The LIVE SCREEN already shows the visible ones: call this only if the element you need is not listed there."""
        return await self._ui("ui.read")

    @function_tool()
    async def ui_navigate(self, context: RunContext, path: str) -> str:
        """Open a page of the site in the admin's browser, e.g. '/assistant', '/devis', '/factures', '/admin'.
        Returns the new screen (elements with ids)."""
        return await self._ui("ui.navigate", {"path": path})

    @function_tool()
    async def ui_click(self, context: RunContext, element_id: str, confirmed: bool = False) -> str:
        """Click an element: its id (from the LIVE SCREEN or ui_read) OR its exact visible text, e.g. 'Nouveau devis'.
        Returns the new screen. Buttons that send, save, validate or delete need confirmed=true, given ONLY after the admin said yes."""
        return await self._ui("ui.click", {"id": element_id, "confirmed": confirmed})

    @function_tool()
    async def ui_type(self, context: RunContext, element_id: str, text: str, submit: bool = False) -> str:
        """Type text into a field: its id OR its visible label/placeholder. submit=true presses Enter afterwards."""
        return await self._ui("ui.type", {"id": element_id, "text": text, "submit": submit})

    @function_tool()
    async def ui_do(self, context: RunContext, steps_json: str) -> str:
        """Run SEVERAL screen steps in ONE call, visibly, in order — much faster than separate calls. steps_json is a JSON list,
        each step one of: {"navigate": "/devis"}, {"click": "Nouveau devis"} (id or visible text, add "confirmed": true only
        after the admin's yes), {"type": "Client", "text": "Jean Dupont", "submit": false}, {"scroll": "down"}, {"back": true},
        {"point": "Total TTC"} (show an element), {"wait": 1.5} (seconds, max 5). Stops at the first failing step and returns
        what was done plus the final screen."""
        steps = _json(steps_json, [])
        if not isinstance(steps, list) or not steps:
            return json.dumps({"ok": False, "error": "steps_json doit être une liste JSON non vide"})
        steps = steps[:12]
        out = await self._ui("ui.do", {"steps": steps}, timeout=60)
        if '"unsupported"' not in out:
            return out
        # ancien client (app mobile pas encore à jour) : on rejoue pas à pas avec les méthodes de base
        done = []
        for st in steps:
            if not isinstance(st, dict):
                continue
            if "navigate" in st:
                r = await self._ui("ui.navigate", {"path": st["navigate"]})
            elif "click" in st:
                r = await self._ui("ui.click", {"id": str(st["click"]), "confirmed": bool(st.get("confirmed"))})
            elif "type" in st:
                r = await self._ui("ui.type", {"id": str(st["type"]), "text": str(st.get("text", "")), "submit": bool(st.get("submit"))})
            elif "scroll" in st:
                r = await self._ui("ui.scroll", {"direction": st["scroll"]})
            elif "back" in st:
                r = await self._ui("ui.back")
            elif "wait" in st:
                await asyncio.sleep(max(0.0, min(5.0, float(st["wait"] or 0))))
                r = '{"ok": true}'
            else:
                continue
            ok = _json(r, {}).get("ok", False) if isinstance(_json(r, {}), dict) else False
            done.append({"step": st, "ok": ok})
            if not ok:
                return json.dumps({"ok": False, "done": done, "error": r[:600]}, ensure_ascii=False)
        return json.dumps({"ok": True, "done": done, "screen": _json(await self._ui("ui.read"), {})}, ensure_ascii=False)[:14000]

    @function_tool()
    async def ui_point(self, context: RunContext, target: str) -> str:
        """Show the admin an element of the screen while you talk about it (scrolls to it, moves the pointer, highlights it).
        target = element id or its visible text, e.g. 'Total TTC' or 'Relancer'."""
        out = await self._ui("ui.point", {"id": target}, timeout=8)
        return '{"ok": true, "note": "pointing not available on this client"}' if '"unsupported"' in out else out

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

    async def _release_room():  # libère la salle (créneau Synthesia unique) dès que l'admin part
        try:
            await ctx.delete_room()
        except Exception:  # noqa: BLE001
            pass
    ctx.add_shutdown_callback(_release_room)

    meta = _json(ctx.job.metadata or "", {}) if isinstance(ctx.job.metadata, str) else {}
    lang = (meta.get("lang") or "pt").lower()
    hint = (meta.get("site") or "").lower()
    identity = await _admin_identity(ctx)
    order = ["pt", "fr"] if (hint == "pt" or (hint != "fr" and lang == "pt")) else ["fr", "pt"]
    bridge, me, site_used = None, None, order[0]
    whos = await asyncio.gather(*(Bridge(SITES[s], identity).whoami() for s in order))  # les deux ponts en parallèle
    for s, w in zip(order, whos):  # o admin pertence ao site onde a ponte o reconhece
        if w:
            bridge, me, site_used = Bridge(SITES[s], identity), w, s
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
        # Réactivité : fin de phrase détectée par le VAD sémantique d'OpenAI (répond dès que l'admin a fini sa pensée, sans
        # attendre un long silence ni lui couper la parole au milieu d'une phrase). AVATAR_TURN=server garde l'ancien VAD
        # à seuil (salle très bruyante) ; AVATAR_EAGERNESS=low|medium|high|auto règle la vitesse sans toucher au code.
        if (os.environ.get("AVATAR_TURN") or "semantic").strip() != "server":
            eager = (os.environ.get("AVATAR_EAGERNESS") or "medium").strip()
            try:
                from openai.types.realtime.realtime_audio_input_turn_detection import SemanticVad
                rt["turn_detection"] = SemanticVad(type="semantic_vad", eagerness=eager if eager in ("low", "medium", "high", "auto") else "medium",
                                                   create_response=True, interrupt_response=True)
            except Exception:  # noqa: BLE001 — SDK différent : réglages anti-bruit de _loud_room
                log.warning("VAD sémantique indisponible", exc_info=True)
        # min_interruption_duration 0.8 s : l'admin coupe la parole facilement, sans que le bruit de salle déclenche de fausses coupures.
        # caméra : 1 image/s quand l'admin parle, 1 toutes les 3 s sinon — elle voit ce qu'on lui montre sans attendre 10 s
        session = AgentSession(video_sampler=VoiceActivityVideoSampler(speaking_fps=float(os.environ.get("AVATAR_CAM_FPS", "1.0")),
                                                                       silent_fps=float(os.environ.get("AVATAR_CAM_IDLE_FPS", "0.33"))),  # Lot 104
                               **_voice_kwargs(lang, rt), max_tool_steps=60,
                               min_interruption_duration=float(os.environ.get("AVATAR_MIN_INTERRUPT", "0.8")))
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
    who = (f"The admin's first name is {first} (you know it; follow the NAME rule: say it at most once, in the greeting). "
           if first else "")
    await session.start(agent=AdminAssistant(bridge, lang, ctx.room, identity, who + (me or {}).get("knowledge", ""), site_used),
                        room=ctx.room,
                        room_options=room_io.RoomOptions(video_input=True, participant_identity=identity,  # Lot 107
                                                     audio_input=room_io.AudioInputOptions(noise_cancellation=_noise_cancel())))  # Lot 104 : caméra si l'admin l'allume
    await attach_screen(ctx, session, identity)  # Lot 42 : écran en direct + internet + autonomie
    hush = attach_hush(ctx, session)  # Lot 44 : « cala-te » = silence immédiat
    await session.generate_reply(instructions=greet_text(lang, site_used))

    # Lot 105 : mode présentatrice — les « tempos mortos » sont remplis avec énergie
    loop = asyncio.get_running_loop()
    last = {"t": loop.time()}

    def _touch(_ev=None):
        last["t"] = loop.time()

    session.on("user_state_changed", _touch)
    session.on("agent_state_changed", _touch)

    def _on_data(pkt):
        if getattr(pkt, "topic", "") != "avatar_ctrl":
            return
        m = _json(bytes(pkt.data).decode("utf-8", "ignore"), {})
        if isinstance(m, dict) and m.get("type") == "presenter":
            ag = session.current_agent
            if ag is not None:
                ag.presenter = bool(m.get("on"))
            _touch()

    ctx.room.on("data_received", _on_data)

    async def _filler():
        k = 0
        while True:
            await asyncio.sleep(2)
            ag = session.current_agent
            if (not getattr(ag, "presenter", False) or hush.quiet or session.user_state == "speaking"
                    or session.agent_state not in ("idle", "listening")):
                continue
            if loop.time() - last["t"] < getattr(ag, "filler_gap", FILLER_GAP):
                continue
            _touch()
            try:
                await session.generate_reply(instructions=FILLER.format(topic=FILLER_TOPICS[k % len(FILLER_TOPICS)]))
            except Exception as e:  # noqa: BLE001 — session fermée, interruption…
                log.warning("segment présentatrice : %s", str(e)[:120])
            k += 1

    t = asyncio.create_task(_filler())
    _TASKS.add(t)
    t.add_done_callback(_TASKS.discard)



# ====================================================================== Lot 44 : « cala-te » = silence immédiat
# La demande de silence est détectée sur la transcription de l'admin (et sur le bouton / la détection du site, topic « avatar »,
# {"type": "hush"}) : on coupe la parole tout de suite et on interrompt toute réponse qui démarre dans les secondes qui suivent
# (le modèle temps réel répond automatiquement à chaque tour). Elle reparle quand l'admin lui reparle.
import re as _re  # noqa: E402
import time  # noqa: E402,F811

HUSH = _re.compile(
    r"^\W*(?:(?:por favor|s'il te pla[iî]t|s'il vous pla[iî]t|please|aurora|ok|okay|bon|agora|maintenant|now|ya|vale)\W+)*"
    r"(?:cala(?:-te| te|-se| se)?|calada|chiu+|psiu+|sil[eê]ncio|sil[eê]ncio,? por favor|p[aá]ra(?: de falar| j[aá])?|basta|chega"
    r"|tais[- ]toi|taisez[- ]vous|chut+|silence|arr[eê]te(?:z)?(?: de parler)?|stop(?: talking)?|shut up|be quiet|quiet|hush"
    r"|c[aá]llate|silencio|basta ya|zitto|stai zitto|ruhe|sei still)\b[\W]*(?:por favor|s'il te pla[iî]t|please|aurora)?\W*$",
    _re.IGNORECASE)


def is_hush(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and len(t) <= 60 and bool(HUSH.match(t))


class Hush:
    WINDOW = 4.0   # secondes pendant lesquelles toute réponse automatique est coupée

    def __init__(self, session):
        self.session, self.until, self.quiet = session, 0.0, False

    def now(self, why: str = "voice"):
        self.quiet, self.until = True, time.monotonic() + self.WINDOW
        try:
            self.session.interrupt(force=True)
        except TypeError:
            self.session.interrupt()
        except Exception:  # noqa: BLE001
            pass
        ag = self.session.current_agent
        if getattr(ag, "presenter", False):
            ag.presenter = False   # « cala-te » arrête aussi les animations de la présentatrice
        log.info("silence demandé (%s)", why)

    def on_transcript(self, ev):
        text = getattr(ev, "transcript", "")
        if is_hush(text):
            self.now("voice")
        elif getattr(ev, "is_final", False) and len(text.strip()) > 3:
            self.quiet = False   # l'admin lui reparle avec une vraie demande : elle répond normalement

    def on_agent_state(self, ev):
        if getattr(ev, "new_state", "") == "speaking" and self.quiet and time.monotonic() < self.until:
            try:
                self.session.interrupt(force=True)
            except TypeError:
                self.session.interrupt()
            except Exception:  # noqa: BLE001
                pass


def attach_hush(ctx, session) -> Hush:
    h = Hush(session)
    session.on("user_input_transcribed", h.on_transcript)
    session.on("agent_state_changed", h.on_agent_state)

    def _data(packet):
        if getattr(packet, "topic", "") != "avatar":
            return
        try:
            if json.loads(bytes(packet.data).decode("utf-8")).get("type") == "hush":
                h.now("button")
        except (ValueError, UnicodeDecodeError, AttributeError):
            return
    ctx.room.on("data_received", _data)
    return h


# ====================================================================== Lot 42 : écran en direct, internet, autonomie
# Le site envoie un résumé de l'écran à chaque changement (data LiveKit, topic « screen », voir avatarScreenWatch.js).
# Il est injecté dans les instructions : l'assistante répond et décide sur ce que l'admin voit MAINTENANT,
# réagit seule aux erreurs / résultats / cartes de choix, et ne parle plus d'une page que l'admin a quittée.
import time  # noqa: E402

AUTONOMY = (
    "\nAUTONOMY: you are a fully autonomous operator. When the goal is clear, chain every step yourself (navigate, read, click, "
    "type, wait, check the result) until it is done; never stop half-way to ask 'what next?'. Speak only when there is something useful: "
    "the result, a problem or a question you need. Only the irreversible / third-party actions listed in the rules still need a spoken yes.\n"
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
    "or a choice card appears, deal with it without waiting to be asked; (e) stay short and in sync with what is visible; "
    "(f) you see EVERYTHING on it: menus and panels, dialogs, every filled or empty form field, the rest of the page above/below "
    "('Rest of the page'), and every ATTACHED FILE — never say you cannot see the screen or a file, and never ask the admin to "
    "describe, read aloud or re-send something that is listed here; (g) ATTACHED FILES are recognised as soon as they appear, "
    "BEFORE they are sent: you know their names, type and pages — talk about them by name, and if a request needs them, send it "
    "to the Assistant BTP with the files already attached (they leave with the next message).\n"
)
WEB_MODEL = os.environ.get("AVATAR_WEB_MODEL") or "gpt-5-mini"
FLUSH_S = 0.3        # écran → instructions : au plus une mise à jour toutes les 0,3 s (avant 0,8 s)
REACT_GAP_S = 4.0    # réaction spontanée (erreur, résultat, navigation de l'admin) : au plus toutes les 4 s (avant 10 s)


def render_screen(s: dict) -> str:
    out = []
    if s.get("not_found"):
        out.append("THIS PAGE DOES NOT EXIST (404): go back (ui_back) and pick a real page from SITE PAGES, say so in one sentence.")
    if "camera" in s:
        out.append("CAMERA: ON — the images you receive are the admin's live camera, you can see it: answer from the latest image."
                   if s.get("camera") else "CAMERA: off (no live image).")
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
        if a.get("last_sent_files"):
            out.append("Files sent with the admin's last message: " + ", ".join(a["last_sent_files"]))
    att = s.get("attachments") or {}
    files = att.get("files") or []
    if files:
        items = []
        for f in files[:25]:
            if not isinstance(f, dict):
                continue
            bits = [str(f.get("kind") or "file")]
            if f.get("pages"):
                bits.append(f"{f['pages']} pages")
            if f.get("files"):
                bits.append(f"{f['files']} files")
            if f.get("text_read") is True:
                bits.append("text read")
            elif f.get("text_read") is False:
                bits.append("scan, read as image")
            if f.get("busy"):
                bits.append("still uploading")
            bits.append("NEW, not sent yet" if f.get("new") else "already in the conversation context")
            items.append(f"'{str(f.get('name', ''))[:90]}' ({', '.join(bits)})")
        out.append(f"ATTACHED FILES ({len(files)}, recognised before sending): " + " · ".join(items))
    if att.get("uploading"):
        out.append("A file is being uploaded right now: wait until it finishes before sending.")
    if att.get("draft"):
        out.append(f"Message typed in the Assistant BTP box (not sent yet): {att['draft']}")
    if s.get("visible"):
        out.append("Visible text: " + s["visible"])
    flds = [f for f in (s.get("fields") or []) if isinstance(f, dict)]
    if flds:
        out.append("Form fields: " + " · ".join(
            f"{str(f.get('field', ''))[:50]}={str(f.get('value', ''))[:80]}{' (required)' if f.get('required') else ''}" for f in flds[:40])[:2200])
    if s.get("beyond"):
        out.append("Rest of the page (above/below, not in view): " + s["beyond"])
    els = s.get("elements") or []
    if els:
        items = []
        for e in els[:60]:
            if not isinstance(e, dict) or not e.get("id"):
                continue
            extra = " ✓" if e.get("checked") else ""
            items.append(f"[{e['id']}] {str(e.get('label', ''))[:50]} ({e.get('role', '')}){extra}")
        out.append("Clickable now (use these ids or texts directly with ui_click / ui_type / ui_do): " + " · ".join(items)[:2400])
    return "\n".join(out)[:12000]


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
    """Écran en direct → instructions de l'agent (dernier état gagnant, ≤ 1 mise à jour / 0,3 s) + réactions spontanées."""

    REACT = {"alert", "assistant_done", "assistant_choices", "navigate", "files_attached", "camera_on"}

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
            wait = FLUSH_S - (time.monotonic() - self.last_push)
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
        if kind == "camera_on":
            # la caméra vient de s'allumer : on laisse arriver 2 images, puis elle dit en une phrase ce qu'elle voit
            await asyncio.sleep(2.5)
            if getattr(self.session, "user_state", "listening") == "speaking":
                return
            self.last_react = time.monotonic()
            self.session.generate_reply(instructions="The admin just switched the camera ON. Look at the latest camera image and say in "
                                        "ONE short natural sentence that you can see them now and what you see (scene, objects, a document "
                                        "held up) — never identify a person. Then stop.\n" + SCREEN_HEADER + render_screen(self.latest or ev))
            return
        if user_state == "speaking" or time.monotonic() - self.last_react < REACT_GAP_S:
            return
        if kind == "navigate":
            # L'admin change de page lui-même : une collègue ne commente pas chaque page ouverte. Si elle parlait de l'ancienne
            # page, elle s'arrête ; l'écran à jour est déjà dans ses instructions pour la suite.
            if by_admin and agent_state == "speaking":
                self.session.interrupt()
            return
        if agent_state in ("speaking", "thinking"):
            return  # elle travaille déjà (outil en cours) : l'écran à jour suffit
        if kind == "alert" and by_admin:
            return  # message apparu après un geste de l'admin lui-même : on ne l'interrompt pas
        hint = {"alert": "A message or error just appeared on screen while you were working on this together. If it matters for "
                         "what you are doing, react in a few natural words and fix it or say what to do; otherwise say nothing.",
                "assistant_done": "The Assistant BTP just finished on screen. Give the result in one or two natural sentences (the "
                                  "essential, round figures) and carry on with the next step of the job yourself. No recap.",
                "assistant_choices": "The Assistant BTP is asking choices on screen. Answer them yourself with "
                                     "assistant_answer_choices (admin's preferences, otherwise recommended) and mention it in a few words.",
                "files_attached": "The admin just attached file(s) — see ATTACHED FILES. Confirm in ONE short natural sentence that you "
                                  "see them, naming them (and the type, e.g. a quote or a plan), BEFORE anything is sent. If the "
                                  "admin already said what to do with them, do it; otherwise ask in a few words what to do. "
                                  "Do not send anything yet."}[kind]
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
