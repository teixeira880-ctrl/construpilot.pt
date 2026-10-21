"""Couche IA modulaire (GPT-5.5 via Emergent LLM key)."""
import logging
import asyncio
import os
import json
import uuid
from datetime import datetime, timezone

from emergentintegrations.llm.chat import (UserMessage, ImageContent,
                                          TextDelta, StreamDone)
from engines.expenses.metering import MeteredChat as LlmChat

from core.db import db
from engines.catalog import PROJECT_TYPES, LOTS, FINISH_LEVELS

KEY = os.environ.get('EMERGENT_LLM_KEY', '')
logger = logging.getLogger(__name__)
PROVIDER, MODEL = "anthropic", "claude-sonnet-4-6"
# Fonctions avec images (analyse photo / devis scanné) → modèle vision (Claude via clé
# Emergent = texte uniquement)
VISION_PROVIDER, VISION_MODEL = "openai", "gpt-5.5"
# Coach IA (chat conversationnel) → Claude Sonnet 4.6 via la clé LLM universelle Emergent
CHAT_PROVIDER, CHAT_MODEL = "anthropic", "claude-sonnet-4-6"

# ---- Sélecteur de modèle IA (configurable par l'admin) ----
# Chaque palier expose un compromis qualité / vitesse / coût pour la génération de TEXTE
# (estimation Smart Project, coach IA, analyses). La vision reste sur VISION_MODEL.
AI_TEXT_MODELS = {
    "opus": {"provider": "anthropic", "model": "claude-opus-4-8",
             "label": "Claude Opus 4.8", "desc": "Qualidade máxima · mais lento · mais caro",
             "quality": 3, "speed": 1, "cost": 3},
    "sonnet": {"provider": "anthropic", "model": "claude-sonnet-4-6",
               "label": "Claude Sonnet 4.6", "desc": "Equilibrado · recomendado",
               "quality": 2, "speed": 2, "cost": 2},
    "haiku": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001",
              "label": "Claude Haiku 4.5", "desc": "Rápido e económico · qualidade inferior",
              "quality": 1, "speed": 3, "cost": 1},
    "gpt_astra": {"provider": "openai", "model": "gpt-6-astra",
                  "label": "ChatGPT · GPT-6 Astra", "desc": "Chave OpenAI da empresa · raciocínio máximo · mais lento",
                  "quality": 3, "speed": 1, "cost": 3},
    "gpt_terra": {"provider": "openai", "model": "gpt-5.6-terra",
                  "label": "ChatGPT · GPT-5.6 Terra", "desc": "Chave OpenAI da empresa · equilibrado · recomendado para o chat",
                  "quality": 2, "speed": 2, "cost": 2},
    "gpt_mini": {"provider": "openai", "model": "gpt-5.4-mini",
                 "label": "ChatGPT · GPT-5.4 Mini", "desc": "Chave OpenAI da empresa · rápido e económico",
                 "quality": 1, "speed": 3, "cost": 1},
    "gemini_pro": {"provider": "gemini", "model": "gemini-3.1-pro-preview",
                   "label": "Gemini 3.1 Pro", "desc": "Chave Emergent · qualidade elevada, muito bom em documentos longos e plantas",
                   "quality": 3, "speed": 2, "cost": 2},
    "gemini_flash": {"provider": "gemini", "model": "gemini-3.5-flash",
                     "label": "Gemini 3 Flash", "desc": "Chave Emergent · rápido e económico",
                     "quality": 1, "speed": 3, "cost": 1},
}
DEFAULT_TEXT_TIER = "sonnet"
_TEXT_TIER: str | None = None  # cache mémoire, chargé depuis db.app_settings au 1er appel


async def get_text_tier() -> str:
    global _TEXT_TIER
    if _TEXT_TIER is None:
        doc = await db.app_settings.find_one({"_id": "ai"})
        tier = (doc or {}).get("text_tier", DEFAULT_TEXT_TIER)
        _TEXT_TIER = tier if tier in AI_TEXT_MODELS else DEFAULT_TEXT_TIER
    return _TEXT_TIER


async def set_text_tier(tier: str) -> str:
    global _TEXT_TIER
    if tier not in AI_TEXT_MODELS:
        raise ValueError(f'nível desconhecido: {tier}')
    await db.app_settings.update_one({"_id": "ai"}, {"$set": {"text_tier": tier}}, upsert=True)
    _TEXT_TIER = tier
    return tier


# ---- Backend Gemini : clé LLM universelle Emergent (défaut) ou SDK Google natif ----
# "emergent" → appels Gemini via emergentintegrations. "native" → SDK google-genai
# (gemini-2.5) avec la clé Google de l'entreprise (GOOGLE_GEMINI_API_KEY).
DEFAULT_GEMINI_BACKEND = "emergent"
_GEMINI_BACKEND: str | None = None


async def get_gemini_backend() -> str:
    global _GEMINI_BACKEND
    if _GEMINI_BACKEND is None:
        doc = await db.app_settings.find_one({"_id": "ai"})
        val = (doc or {}).get("gemini_backend")
        if val in ("emergent", "native"):
            _GEMINI_BACKEND = val
        else:
            # Défaut : clé Google directe si elle est présente, sinon Emergent.
            from engines import gemini_native
            _GEMINI_BACKEND = "native" if gemini_native.native_available() else DEFAULT_GEMINI_BACKEND
    return _GEMINI_BACKEND


async def set_gemini_backend(backend: str) -> str:
    global _GEMINI_BACKEND
    if backend not in ("emergent", "native"):
        raise ValueError(f'backend desconhecido: {backend}')
    await db.app_settings.update_one({"_id": "ai"}, {"$set": {"gemini_backend": backend}}, upsert=True)
    _GEMINI_BACKEND = backend
    return backend


async def _use_native_gemini() -> bool:
    """True si le backend natif est sélectionné ET la clé Google est présente."""
    from engines import gemini_native
    return await get_gemini_backend() == "native" and gemini_native.native_available()


FALLBACK_TIER = "sonnet"  # palier Emergent utilisé quand la clé OpenAI de l'entreprise est désactivée


async def _text_provider_model() -> tuple[str, str]:
    from engines.llm_keys import openai_direct_active
    # Clé OpenAI de l'entreprise présente et active → devis, reformulation, traduction, classement, comptes rendus sur GPT-5.6 Terra
    if openai_direct_active() and os.environ.get("STUDIES_LIGHT_OVERRIDE", "1") != "0":
        return "openai", os.environ.get("STUDIES_MODEL_LIGHT", "gpt-5.6-terra")
    tier = await get_text_tier()
    cfg = AI_TEXT_MODELS[tier]
    if cfg["provider"] == "openai" and not openai_direct_active():
        cfg = AI_TEXT_MODELS[FALLBACK_TIER]
    return cfg["provider"], cfg["model"]


async def _openai_failed(exc: BaseException) -> tuple[str, str]:
    """Après un échec OpenAI direct : bascule sur la clé Emergent si crédit/clé en cause, sinon relance l'erreur."""
    from engines.llm_keys import note_openai_error
    if not await note_openai_error(exc):
        raise exc
    cfg = AI_TEXT_MODELS[FALLBACK_TIER]
    return cfg["provider"], cfg["model"]


async def _log_usage(feature: str, provider: str, model: str) -> None:
    """Incrémente le compteur d'appels IA (total par fonctionnalité/modèle + bucket journalier)."""
    try:
        now = datetime.now(timezone.utc)
        await db.ai_usage.update_one(
            {"feature": feature, "provider": provider, "model": model},
            {"$inc": {"calls": 1}, "$set": {"last_used": now.isoformat()}},
            upsert=True)
        day = now.date().isoformat()
        await db.ai_usage_daily.update_one(
            {"_id": day}, {"$inc": {"calls": 1}}, upsert=True)
    except Exception:
        pass


async def check_ai_budget() -> None:
    """Alerte email quand le nombre d'appels IA du mois approche (80 %) puis dépasse (100 %) le seuil admin.
    Chaque palier n'envoie qu'une fois par mois."""
    try:
        doc = await db.app_settings.find_one({"_id": "ai"}) or {}
        threshold = doc.get("budget_threshold")
        if not threshold or threshold <= 0:
            return
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        rows = await db.ai_usage_daily.find({"_id": {"$regex": f"^{month}"}}).to_list(40)
        total = sum(r.get("calls", 0) for r in rows)
        pct = total / threshold
        over = pct >= 1.0
        warn = pct >= 0.8
        if not warn:
            return
        # Palier à traiter : dépassement (100 %) prioritaire, sinon pré-alerte (80 %)
        if over and doc.get("budget_alert_month") != month:
            stage, flag = "over", "budget_alert_month"
        elif warn and not over and doc.get("budget_warn80_month") != month:
            stage, flag = "warn80", "budget_warn80_month"
        else:
            return
        email = doc.get("budget_email")
        if not email:
            admin = await db.users.find_one({"role": "admin"}, {"_id": 0, "email": 1})
            email = admin["email"] if admin else None
        if not email:
            return
        from engines.emailer import send_email
        if stage == "over":
            subject = f'⚠️ Orçamento IA ultrapassado — {total} chamadas em {month}'
            body = (f'<p>O número de chamadas IA do ConstruPilot para <b>{month}</b> atingiu <b>{total}</b>, ultrapassando o limiar configurado de <b>{threshold}</b> ({round(pct * 100)} %).</p>')
        else:
            subject = f'🔔 Orçamento IA a {round(pct * 100)} % — {total} chamadas em {month}'
            body = (f'<p>O número de chamadas IA do ConstruPilot para <b>{month}</b> atingiu <b>{total}</b>, ou seja <b>{round(pct * 100)} %</b> do limiar configurado de <b>{threshold}</b>. O limite aproxima-se.</p>')
        html = ("<p>Olá,</p>" + body
                + "<p>Pode ajustar este limiar, mudar de modelo IA ou recarregar a chave universal (Perfil → Gerir a subscrição → Chave universal → Adicionar saldo) a partir do back-office.</p><p>— ConstruPilot</p>")
        await send_email(email, subject, html)
        await db.app_settings.update_one({"_id": "ai"}, {"$set": {flag: month}}, upsert=True)
    except Exception:
        pass

BRAND = (
    "És o ConstruPilot, o especialista em obras da plataforma ConstruPilot. Respondes sempre em português europeu, de forma profissional, concreta e quantificada. Nunca incentivas um particular a intervir no gás, num quadro elétrico, numa parede resistente, na estrutura, no amianto, numa cobertura perigosa ou na impermeabilização estrutural: nesses casos recomendas explicitamente um profissional. Os preços e quantidades definitivos vêm do motor de cálculo ConstruPilot, não de ti: podes dar ordens de grandeza, mas convidas a utilizar o estimador."
)


def _chat(system: str, session_id: str | None = None,
          provider: str = PROVIDER, model: str = MODEL, feature: str = "ai") -> LlmChat:
    from engines.llm_keys import studies_key
    return LlmChat(api_key=studies_key(provider) or KEY, session_id=session_id or str(uuid.uuid4()),
                   system_message=system, expense_feature=feature).with_model(provider, model)


async def _openai_responses(system: str, prompt: str, model: str, images: list[str] | None = None, feature: str = "ai"):
    """Modèles ChatGPT via la clé OpenAI de l'entreprise (Responses API) — flux de deltas texte."""
    from engines.openai_studies import _client
    content = [{"type": "input_text", "text": prompt}] + [{"type": "input_image", "image_url": f"data:image/png;base64,{i}", "detail": "high"}
                                                          for i in (images or [])]
    client = _client()
    st = await client.responses.create(model=model, instructions=system, input=[{"role": "user", "content": content}], stream=True)
    async for ev in st:
        if ev.type == "response.output_text.delta":
            yield ev.delta
        elif ev.type == "response.completed":
            from engines.expenses.context import actor
            from engines.openai_studies import _log_usage
            await _log_usage(actor().get("user_id"), None, feature, model, ev.response.usage, None)


# Chaîne de repli : si un fournisseur échoue (erreur, quota, délai, réponse vide/tronquée) on passe au suivant, sans
# interrompre l'utilisateur. Le 1er maillon est le modèle configuré (clé OpenAI d'entreprise si active), puis la clé
# universelle Emergent (OpenAI → Claude → Gemini), puis Perplexity (texte uniquement).
FAILOVER_TEXT = [("openai", "gpt-5.4"), ("anthropic", "claude-sonnet-4-6"), ("gemini", "gemini-3.5-flash"), ("perplexity", "fast")]
FAILOVER_VISION = [("openai", "gpt-5.5"), ("gemini", "gemini-3.1-pro-preview"), ("anthropic", "claude-sonnet-4-6")]
PER_PROVIDER_TIMEOUT = float(os.environ.get("AI_PROVIDER_TIMEOUT_S", "150"))
MIN_ANSWER_CHARS = 2


async def _chain(images: bool) -> list[tuple[str, str]]:
    first = (VISION_PROVIDER, VISION_MODEL) if images else await _text_provider_model()
    chain = [first] + [c for c in (FAILOVER_VISION if images else FAILOVER_TEXT) if c != first]
    return chain


async def _perplexity_text(system: str, text: str, feature: str) -> str:
    from perplexity import AsyncPerplexity
    client = AsyncPerplexity(api_key=os.environ["PERPLEXITY_API_KEY"], max_retries=1, timeout=PER_PROVIDER_TIMEOUT)
    r = await client.responses.create(input=text, instructions=system, preset="fast", store=False, max_output_tokens=4000)
    return r.output_text or ""


async def renovation_extract(text: str, fields: list[dict]) -> dict:
    """Extrait des valeurs de champs à partir d'un texte libre (description) ou du texte
    d'un document (DPE/audit). N'EXTRAIT QUE ce qui est explicitement présent ; n'invente
    aucune valeur. Renvoie {path: value} limité aux champs connus/options autorisées."""
    if not (text or "").strip():
        return {}
    spec_lines = []
    for f in fields:
        opts = ("; options: " + " | ".join(f["options"])) if f.get("type") == "enum" and f.get("options") else ""
        spec_lines.append(f"- {f['path']} : {f['label']} ({f.get('type', 'text')}{(' ' + f['unit']) if f.get('unit') else ''}){opts}")
    system = (BRAND + " Extrais dados de edifícios para um questionário de reabilitação. Devolves APENAS os campos explicitamente presentes no texto. NÃO INVENTES NENHUM valor, nenhuma área, nenhum ano, nenhuma classe. Para um campo \'enum\', o valor TEM de ser exatamente uma das opções listadas, caso contrário ignora o campo. Para os números, devolve um número (separador decimal ponto). Responde APENAS em JSON: {\"fields\": {\"caminho\": valor, ...}}. Se nada, {\"fields\": {}}.")
    prompt = ("CAMPOS DISPONÍVEIS:\n" + "\n".join(spec_lines)
              + "\n\nTEXTO A ANALISAR:\n" + text[:6000]
              + "\n\nDevolve o JSON dos campos reconhecidos (sem inventar).")
    data = _json(await _complete(system, prompt, feature="reno_extract"), {"fields": {}})
    out = {}
    by_path = {f["path"]: f for f in fields}
    for path, val in (data.get("fields") or {}).items():
        f = by_path.get(path)
        if not f or val in (None, ""):
            continue
        if f.get("type") == "enum" and f.get("options") and val not in f["options"]:
            continue
        out[path] = val
    return out



async def web_answer(query: str) -> dict:
    """Recherche web (Perplexity) pour une question factuelle BTP. Renvoie texte + sources.
    N'est JAMAIS utilisé pour du calcul de métré/chiffrage (déterministe côté serveur)."""
    if not os.environ.get("PERPLEXITY_API_KEY"):
        return {"answer": "", "sources": [], "error": "Pesquisa web indisponível."}
    from perplexity import AsyncPerplexity
    system = (BRAND + " És o Assistente Construção, o assistente IA de obras do ConstruPilot. Responde de forma concisa, factual e acionável. Se deres preços, indica que são indicativos e datados. Cita as normas (NP EN, Eurocódigos, LNEC, RGEU) quando for pertinente. Propõe algumas opções quando for útil. Responde em português europeu.")
    client = AsyncPerplexity(api_key=os.environ["PERPLEXITY_API_KEY"], max_retries=1, timeout=PER_PROVIDER_TIMEOUT)
    try:
        r = await client.responses.create(input=query, instructions=system, preset="fast",
                                          store=False, max_output_tokens=1400)
        text = (r.output_text or "").strip()
        sources = []
        try:
            for item in (r.to_dict().get("output") or []):
                if isinstance(item, dict) and item.get("type") == "search_results" and item.get("results"):
                    for s in item["results"]:
                        url = s.get("url") or ""
                        if url:
                            sources.append({"url": url, "title": s.get("title") or url})
                    break
        except Exception:
            sources = []
        return {"answer": text, "sources": sources[:6], "price_suggestion": _extract_price(text)}
    except Exception as e:  # noqa: BLE001
        logger.error("web_answer failed: %s", e)
        return {"answer": "", "sources": [], "error": "Pesquisa web momentaneamente indisponível."}


def _extract_price(text: str) -> dict | None:
    """Extrait un prix unitaire représentatif (médiane) d'une réponse web, de façon
    déterministe (regex). Renvoie {amount, unit} ou None. Sert à PROPOSER un PU, jamais à l'imposer."""
    import re, statistics
    if not text:
        return None
    unit_map = [
        (r"m²|m2|/m\b", "m2"),
        (r"\bml\b|/ml|mètre linéaire|metre lineaire", "ml"),
        (r"/u\b|unité|unite|pièce|piece", "u"),
    ]
    for pat, unit in unit_map:
        vals = []
        for m in re.finditer(
                r"(\d{1,3}(?:[ .]\d{3})*(?:[.,]\d{1,2})?)\s*€\s*(?:ttc|ht)?\s*(?:/|par)?\s*(?:" + pat + ")",
                text, flags=re.IGNORECASE):
            raw = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
            try:
                v = float(raw)
            except ValueError:
                continue
            if 0 < v <= 100000:
                vals.append(v)
        if vals:
            return {"amount": round(statistics.median(vals), 2), "unit": unit}
    return None


async def _call_provider(provider: str, model: str, system: str, text: str, images: list[str] | None,
                         session_id: str | None, feature: str) -> str:
    from engines.llm_keys import openai_direct_active
    if provider == "perplexity":
        return await _perplexity_text(system, text, feature)
    if provider == "gemini" and await _use_native_gemini():
        from engines import gemini_native
        try:
            out = await gemini_native.complete(system, text, images,
                                               model=gemini_native.map_model(model))
            if (out or "").strip():
                return out
        except Exception as e:  # noqa: BLE001 — quota/erreur clé Google → repli
            logger.warning("gemini natif (texte) a échoué, repli : %s", type(e).__name__)
    # Claude en direct sur VOTRE clé Anthropic si présente (sinon repli plus bas).
    if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        from engines import anthropic_native
        try:
            out = await anthropic_native.complete(system, text, images, model=model)
            if (out or "").strip():
                return out
        except Exception as e:  # noqa: BLE001 — crédit/erreur clé Anthropic → repli
            logger.warning("claude natif a échoué, repli : %s", type(e).__name__)
    # Claude sans clé Anthropic directe → on utilise VOTRE clé OpenAI directe (pas la clé Emergent).
    if provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY") and openai_direct_active():
        provider, model = "openai", os.environ.get("STUDIES_MODEL_LIGHT", "gpt-5.6-terra")
    if provider == "openai" and openai_direct_active():
        return "".join([d async for d in _openai_responses(system, text, model, images=images, feature=feature)])
    # Dernier recours automatique : clé universelle Emergent (filet de sécurité).
    return await _stream_chat_text(system, text, images, session_id, provider, model, feature)


async def _learning_suffix(feature: str) -> str:
    """Bloc d'exemples de référence validés (few-shot admin) à ajouter au system prompt."""
    try:
        from engines import learning
        return await learning.learning_block(feature)
    except Exception:  # noqa: BLE001
        return ""


async def _complete(system: str, text: str, images: list[str] | None = None,
                    session_id: str | None = None, feature: str = "misc") -> str:
    from engines.llm_keys import key_source, note_openai_error
    system = system + await _learning_suffix(feature)
    errors = []
    for provider, model in await _chain(bool(images)):
        if provider == "perplexity" and (images or not os.environ.get("PERPLEXITY_API_KEY")):
            continue
        direct = provider == "openai" and key_source("openai") == "openai_direct"
        await _log_usage(feature, provider, model)
        try:
            out = await asyncio.wait_for(_call_provider(provider, model, system, text, images, session_id, feature), PER_PROVIDER_TIMEOUT)
            if len((out or "").strip()) >= MIN_ANSWER_CHARS:
                if errors:
                    logger.warning("ai failover %s → %s/%s ok après : %s", feature, provider, model, " | ".join(errors))
                return out
            errors.append(f'{provider}/{model}: resposta vazia')
        except Exception as e:  # noqa: BLE001
            errors.append(f"{provider}/{model}: {type(e).__name__}: {str(e)[:120]}")
            if direct:
                await note_openai_error(e)
                if key_source("openai") == "emergent":  # la clé d'entreprise vient d'être coupée → même modèle via Emergent
                    try:
                        out = await asyncio.wait_for(_stream_chat_text(system, text, images, session_id, provider, model, feature), PER_PROVIDER_TIMEOUT)
                        if len((out or "").strip()) >= MIN_ANSWER_CHARS:
                            return out
                    except Exception as e2:  # noqa: BLE001
                        errors.append(f"emergent/{model}: {type(e2).__name__}")
    logger.error("ai: tous les fournisseurs ont échoué (%s) : %s", feature, " | ".join(errors))
    raise RuntimeError("Serviço IA momentaneamente indisponível — tente novamente dentro de instantes")


async def _stream_chat_text(system, text, images, session_id, provider, model, feature) -> str:
    chat = _chat(system, session_id, provider, model, feature=feature)
    contents = [ImageContent(image_base64=i) for i in (images or [])]
    out = []
    async for ev in chat.stream_message(UserMessage(text=text, file_contents=contents or None)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)


async def stream_chat(history: list[dict], message: str, session_id: str, context: str = "") -> None:
    system = BRAND + (f'\n\nContexto do projeto do utilizador:\n{context}' if context else "")
    system += await _learning_suffix("coach")
    convo = "\n".join(f"{('Utilizador' if m['role'] == 'user' else 'ConstruPilot')}: {m['content']}"
                      for m in history[-10:])
    prompt = (f'Histórico da conversa:\n{convo}\n\nNova mensagem: {message}'
              if convo else message)
    from engines.llm_keys import key_source, note_openai_error
    emitted = False
    errors = []
    for provider, model in await _chain(False):
        if provider == "perplexity":
            continue
        direct = provider == "openai" and key_source("openai") == "openai_direct"
        await _log_usage("coach", provider, model)
        try:
            if direct:
                agen = _openai_responses(system, prompt, model, feature="coach")
            else:
                chat = _chat(system, session_id, provider, model, feature="coach")

                async def _gen(chat=chat):
                    async for ev in chat.stream_message(UserMessage(text=prompt)):
                        if isinstance(ev, TextDelta):
                            yield ev.content
                        elif isinstance(ev, StreamDone):
                            break
                agen = _gen()
            async for d in agen:
                if d:
                    emitted = True
                    yield d
            if emitted:
                return
            errors.append(f"{provider}/{model}: flux vide")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{provider}/{model}: {type(e).__name__}")
            if direct:
                await note_openai_error(e)
            if emitted:  # coupure en cours de réponse : on termine proprement sans doublonner
                logger.warning("ai stream interrompu après début de réponse : %s", errors[-1])
                return
    try:  # dernier recours : Perplexity en non-streamé
        if os.environ.get("PERPLEXITY_API_KEY"):
            out = await asyncio.wait_for(_perplexity_text(system, prompt, "coach"), PER_PROVIDER_TIMEOUT)
            if out.strip():
                yield out
                return
    except Exception as e:  # noqa: BLE001
        errors.append(f"perplexity: {type(e).__name__}")
    logger.error("ai stream: tous les fournisseurs ont échoué : %s", " | ".join(errors))
    yield "O serviço IA está momentaneamente indisponível. Tente novamente dentro de instantes."


# Chatbot d'aide public — meilleur modèle (Claude Opus 4.8) via la clé LLM universelle
HELP_PROVIDER, HELP_MODEL = "anthropic", "claude-opus-4-8"

# Aide contextuelle : route → libellé/description de page pour un support ciblé
_PAGE_HELP = {
    "/dashboard": "Painel (visão geral dos projetos e orçamentos)",
    "/estimation": "Estimador de obras (orçamentação rápida)",
    "/appro": "Análise técnica e Aprovisionamento (Aço, Impermeabilização, Cobertura, Redes)",
    "/plan": "Análise de plantas DWG/DXF/PDF, medição 2D e quantidades",
    "/devis": "Gestão de orçamentos",
    "/calculateurs": "Calculadoras (áreas, volumes, quantidades)",
    "/prix": "Pesquisa de preços de materiais",
    "/coach": "Coach IA obras",
    "/fonctionnalites": "Página Funcionalidades (apresentação particular e profissional)",
    "/tarifs": "Página Preços",
    "/equipe": "Gestão de equipa (Pro)",
    "/fournisseurs": "Os meus fornecedores (Pro)",
}

HELP_KB = "CONSTRUPILOT — base de conhecimento do produto.\n\nPARA PARTICULARES:\n- Estimador de obras: orçamentação instantânea (materiais + mão de obra) por tipo de projeto.\n- Smart Project: descreva «remodelar casa de banho 8 m²» e a IA gera capítulos, materiais e orçamento.\n- Análise de fotografia: envie uma fotografia de uma divisão/defeito, a IA dá pistas (sem certezas se os dados forem insuficientes).\n- Scanner de orçamentos: importe um orçamento PDF, a IA explica-o e verifica-o.\n- Calculadoras: áreas, volumes, quantidades (tinta, azulejo, betão…).\n- Pesquisa de preços, coach IA de obras, planeamento das fases da obra.\n- Segurança: para gás, eletricidade, paredes resistentes, estrutura, amianto, cobertura, a app recomenda sempre um profissional.\n\nPARA PROFISSIONAIS (oferta Pro / Owner):\n- Análise de plantas DWG/DXF/PDF: representação fiel (cotas, textos) e medição exata (paredes, lajes, escadas, vigas, pilares) através da extração das camadas e da implantação.\n- Medição de betão (estrutural) e orçamento detalhado por especialidade, margens, adiantamento.\n- Biblioteca de preços personalizada (mapas de quantidades): importe o seu Excel/PDF para substituir os preços IA.\n- Módulo «Análise técnica e Aprovisionamento IA» (página /appro), em separadores:\n  • Armaduras / Aço: extração dos varões A500 e malhas, lista, quantidades encomendáveis.\n  • Impermeabilização (cobertura em terraço): lista por camada → rolos/bidões/painéis.\n  • Cobertura (inclinada): telhas/ardósias/painel sandwich, subtelha, ripas, cumeeira, laró, caleiras.\n  • Redes: águas pluviais, residuais, abastecimento de água, telecomunicações, gás + medição das valas (escavação, areia, rede de sinalização, aterro, reposição).\n  Cada lista: orçamentação via catálogo do fornecedor ou biblioteca de preços, realce do elemento na planta, exportação CSV e nota de encomenda enviada por e-mail ao fornecedor.\n- Os meus fornecedores: livro de endereços + catálogo de preços por fornecedor.\n- Orçamentos online assináveis, adiantamento Stripe (30 %), planeamento Gantt, portal Pro, gestão de equipa, API, PWA móvel.\n\nPREÇOS / CONTA: ver a página Preços. Experiência com contas de demonstração disponíveis na página de início de sessão.\n"


async def help_assistant(history: list[dict], message: str, session_id: str,
                         page: str | None = None, provider: str | None = None,
                         model: str | None = None) -> str:
    """Chatbot d'aide (Claude Opus 4.8) : répond aux questions sur ConstruPilot."""
    system = (BRAND + "\n\nÉs o assistente de ajuda do ConstruPilot. Respondes APENAS sobre o ConstruPilot (as suas funcionalidades, como as utilizar, que oferta escolher), em português europeu. Sê conciso, claro e caloroso. Se te pedirem algo fora do tema, reconduz educadamente para o ConstruPilot. Baseia-te nestas informações:\n" + HELP_KB)
    page_ctx = _PAGE_HELP.get((page or "").rstrip("/"), None)
    if page_ctx:
        system += (f'\n\nCONTEXTO: o utilizador está atualmente na página «{page_ctx} » (URL {page}). Adapta a tua ajuda a esta página com prioridade, propõe a ação mais útil aqui, mas responde também à sua pergunta precisa.')
    convo = "\n".join(f"{('Utilizador' if m.get('role') == 'user' else 'Assistente')}: {m.get('content', '')}"
                      for m in (history or [])[-8:])
    prompt = (f'Conversation:\n{convo}\n\nNova mensagem: {message}' if convo else message)
    prov, mdl = provider or HELP_PROVIDER, model or HELP_MODEL
    await _log_usage("help_chat", prov, mdl)
    chat = _chat(system, session_id, prov, mdl, feature="help_chat")
    out = []
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)



GEMINI_PRO = ("gemini", "gemini-3.1-pro-preview")


async def _complete_vision(system: str, text: str, images: list[str],
                           provider: str, model: str, feature: str = "misc") -> str:
    """Appel vision avec modèle explicite (ex. Gemini 3.1 Pro pour plans techniques)."""
    system = system + await _learning_suffix(feature)
    # Chemin Gemini natif (SDK Google, facturation entreprise) si activé par l'admin
    if provider == "gemini" and await _use_native_gemini():
        from engines import gemini_native
        try:
            await _log_usage(feature, "gemini_native", gemini_native.map_model(model))
            out = await gemini_native.complete(system, text, images, model=gemini_native.map_model(model))
            if len((out or "").strip()) >= MIN_ANSWER_CHARS:
                return out
        except Exception as e:  # noqa: BLE001
            logger.warning("gemini natif (vision) a échoué, repli Emergent : %s", type(e).__name__)
    # Chemin OpenAI direct (clé entreprise) pour la vision
    if provider == "openai":
        from engines.llm_keys import openai_direct_active
        if openai_direct_active():
            try:
                out = "".join([d async for d in _openai_responses(system, text, model, images=images, feature=feature)])
                if len((out or "").strip()) >= MIN_ANSWER_CHARS:
                    return out
            except Exception as e:  # noqa: BLE001
                logger.warning("openai direct (vision) a échoué, repli : %s", type(e).__name__)
    # Chemin Claude natif (SDK Anthropic, clé entreprise) pour la vision
    if provider == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
        from engines import anthropic_native
        try:
            out = await anthropic_native.complete(system, text, images, model=model)
            if len((out or "").strip()) >= MIN_ANSWER_CHARS:
                return out
        except Exception as e:  # noqa: BLE001
            logger.warning("claude natif (vision) a échoué, repli Emergent : %s", type(e).__name__)
    await _log_usage(feature, provider, model)
    chat = _chat(system, None, provider, model, feature=feature)
    contents = [ImageContent(image_base64=i) for i in (images or [])]
    out = []
    async for ev in chat.stream_message(UserMessage(text=text, file_contents=contents or None)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)


async def analyze_rebar(images: list[str]) -> dict:
    """Analyse IA d'un plan de ferraillage (Gemini 3.1 Pro vision) → bordereau acier.

    Retourne {scale_confidence, lines:[{diameter, ml, bars, spacing_cm, zone, confidence, bbox}],
    treillis:[{ref, panels, area_m2, confidence}], notes}. Chaque quantité porte une confiance 0..1.
    """
    if not images:
        return {"lines": [], "treillis": [], "scale_confidence": 0, "notes": "nenhuma imagem"}
    system = (BRAND + " És engenheiro de estruturas e medidor de betão armado, especialista na leitura de plantas de armaduras (fundações, paredes resistentes, pilares, vigas, lajes, escadas, lintéis).")
    prompt = (
        "Analisa esta planta de armaduras / betão armado e elabora o mapa de aço.\nIdentifica as armaduras A500 (varões Ø6, Ø8, Ø10, Ø12, Ø14, Ø16, Ø20, Ø25, Ø32 — designados HA6…HA32 no JSON), as malhas eletrossoldadas (ST25C, ST20, ST15C, AQ38…), mapas, referências, espaçamentos, estribos/cintas.\nDevolve APENAS este JSON:\n{ \"scale_detected\": string|null, \"scale_confidence\": number(0-1),\n  \"element_count\": number (número de elementos idênticos indicado na legenda, ex \"Número: 2\" → 2; caso contrário 1),\n  \"lines\": [ { \"diameter\": \"HA12\", \"ml\": number, \"bars\": number|null, \"spacing_cm\": number|null, \"zone\": string, \"confidence\": number(0-1), \"bbox\": [x1,y1,x2,y2] (normalizado 0-1, zona principal) } ],\n  \"treillis\": [ { \"ref\": \"ST25C\", \"panels\": number|null, \"area_m2\": number, \"confidence\": number(0-1), \"zone\": string } ],\n  \"notes\": string }\nRegras: NUNCA inventar um diâmetro ausente. Se uma quantidade for incerta, baixa a confidence (<0.6). Estima os ml o melhor possível a partir dos comprimentos, números de varões e espaçamentos visíveis. Não somes as malhas com os varões. Textos (zone, notes) em português europeu."
    )
    data = _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO, feature="rebar"),
                 {"lines": [], "treillis": [], "scale_confidence": 0, "notes": ""})
    return data


async def analyze_structure_plan(images: list[str], context_text: str = "") -> dict:
    """Lecture IA (Gemini 3 Pro) d'un plan de structure/gros œuvre → éléments typés.

    Produit le JSON `geometry` consommé par SemanticReasoningEngine : liste brute des
    semelles / poteaux / longrines / chaînages / murs, chacun avec cotes lues, repère,
    confiance (0..1) et drapeau a_verifier. N'invente JAMAIS de cote ni de matériau."""
    if not images:
        return {"elements": [], "murs": [], "raw_text": context_text, "notes": "nenhuma imagem"}
    system = (BRAND + " És medidor-verificador de betão armado especialista na leitura de plantas de fundações e estrutura (Eurocódigos com Anexos Nacionais portugueses). LÊS a planta, não inventas nada.")
    prompt = (
        "Analisa esta planta de estrutura e faz o inventário dos elementos.\nCruza os TEXTOS (cotas «60x30», marcas «3», «PP e=20», «parede 20», cotas de nível «Assentamento -1.30m») com a geometria para qualificar cada elemento.\n"
        + (f'\nTextos OCR já extraídos do PDF (fiáveis):\n{context_text[:3000]}\n' if context_text else "")
        + "\nDevolve APENAS este JSON (cotas em METROS; null se não legível — não adivinhes):\n{ \"scale_detected\": string|null, \"raw_text\": string,\n  \"elements\": [ { \"type\": \"semelle_isolee|semelle_filante|longrine|chainage|poteau\",\n      \"repere\": string|null, \"longueur_m\": number|null, \"largeur_m\": number|null,\n      \"hauteur_m\": number|null, \"nombre\": integer, \"source_cotes\": string|null,\n      \"confidence\": number(0-1), \"a_verifier\": boolean } ],\n  \"murs\": [ { \"repere\": string|null, \"materiau\": string, \"epaisseur_m\": number|null,\n      \"longueur_m\": number|null, \"hauteur_m\": number|null, \"confidence\": number(0-1),\n      \"a_verifier\": boolean } ],\n  \"notes\": string }\n(semelle_isolee = sapata isolada, semelle_filante = sapata contínua, longrine = viga de fundação, chainage = cinta, poteau = pilar.)\nRegras: nunca uma cota inventada; se uma dimensão for ilegível, põe null e a_verifier=true; não somes nada (o cálculo é feito noutro lado). Textos em português europeu."
    )
    data = _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO, feature="structuro"),
                 {"elements": [], "murs": [], "raw_text": context_text, "notes": ""})
    if not data.get("raw_text"):
        data["raw_text"] = context_text
    return data



async def analyze_waterproofing(images: list[str]) -> dict:
    """Analyse IA d'un plan/détail d'étanchéité toiture terrasse (Gemini 3.1 Pro)."""
    if not images:
        return {"layers": [], "surface_m2": 0, "perimeter_m": 0, "releve_h_m": 0.5,
                "system_type": "bicouche", "scale_confidence": 0, "notes": "nenhuma imagem"}
    system = (BRAND + " És medidor de impermeabilização especialista (cobertura em terraço): sistemas betuminosos SBS/APP, PVC, EPDM, remates, platibandas, águas pluviais.")
    prompt = (
        "Analisa esta planta/pormenor de impermeabilização de cobertura em terraço. Devolve APENAS este JSON:\n{ \"scale_detected\": string|null, \"scale_confidence\": number(0-1),\n  \"system_type\": \"monocouche\"|\"bicouche\",\n  \"surface_m2\": number, \"perimeter_m\": number, \"releve_h_m\": number,\n  \"layers\": [ { \"name\": string, \"present\": true } ] (camadas detetadas: betonilha de pendente, betonilha, primário, pára-vapor, isolamento, membrana 1, membrana 2, proteção),\n  \"singular\": [ { \"name\": string, \"unit\": string, \"qty\": number } ] (platibandas ml, tubos de queda/ralos u…),\n  \"regions\": [ { \"key\": \"surface\"|\"releve\", \"bbox\": [x1,y1,x2,y2] (normalizado 0-1) } ],\n  \"confidence\": number(0-1), \"notes\": string }\nEstima a área horizontal e o perímetro o melhor possível através da escala/cotas. Se incerto, baixa a confiança (<0.6). Não inventes camadas ausentes. Textos em português europeu."
    )
    return _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO,
                                         feature="waterproofing"),
                 {"layers": [], "surface_m2": 0, "perimeter_m": 0, "releve_h_m": 0.5,
                  "system_type": "bicouche", "scale_confidence": 0, "notes": ""})


async def analyze_roofing(images: list[str]) -> dict:
    """Analyse IA d'un plan de toiture en pente (Gemini 3.1 Pro) → surfaces + linéaires."""
    if not images:
        return {"surface_projetee_m2": 0, "pente_pct": 35, "roof_type": "4 pans",
                "faitage_ml": 0, "aretiers_ml": 0, "noues_ml": 0, "rives_ml": 0,
                "egout_ml": 0, "scale_confidence": 0, "notes": "nenhuma imagem"}
    system = (BRAND + " És medidor de coberturas/estruturas de cobertura especialista (coberturas inclinadas: telhas, ardósias, painel sandwich). Sabes ler uma planta de cobertura (rincões, larós, cumeeira, beirados, empenas) e estimar as áreas inclinadas.")
    prompt = (
        "Analisa esta planta de cobertura inclinada. Identifica o tipo (2 águas, 4 águas, uma água…), a área em planta projetada, a inclinação e os lineares de cumeeira, rincões, laró, beirados laterais e beirado inferior.\nDevolve APENAS este JSON:\n{ \"scale_detected\": string|null, \"scale_confidence\": number(0-1),\n  \"roof_type\": string, \"surface_projetee_m2\": number, \"pente_pct\": number,\n  \"faitage_ml\": number, \"aretiers_ml\": number, \"noues_ml\": number,\n  \"rives_ml\": number, \"egout_ml\": number,\n  \"regions\": [ { \"key\": \"couverture\"|\"faitage\"|\"aretiers\"|\"noues\"|\"rives\"|\"egout\", \"bbox\": [x1,y1,x2,y2] (normalizado 0-1) } ],\n  \"confidence\": number(0-1), \"notes\": string }\nEstima o melhor possível através da escala/cotas. A cumeeira é a aresta horizontal superior; os rincões são as arestas inclinadas salientes (tacaniças); os larós são as arestas reentrantes; o beirado inferior é o perímetro baixo (caleiras). Se incerto, baixa a confiança (<0.6). Não inventes valores: põe 0 se o elemento estiver ausente. Textos em português europeu."
    )
    return _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO,
                                         feature="roofing"),
                 {"surface_projetee_m2": 0, "pente_pct": 35, "roof_type": "4 pans",
                  "faitage_ml": 0, "aretiers_ml": 0, "noues_ml": 0, "rives_ml": 0,
                  "egout_ml": 0, "scale_confidence": 0, "notes": ""})


async def analyze_vrd(images: list[str]) -> dict:
    """Analyse IA d'un plan VRD / plan masse (Gemini 3.1 Pro) → réseaux + tranchées."""
    if not images:
        return {"networks": [], "scale_confidence": 0, "notes": "nenhuma imagem"}
    system = (BRAND + " És medidor de redes especialista (arruamentos e redes): lês as plantas de implantação/redes e identificas os traçados de águas pluviais, águas residuais, abastecimento de água, telecomunicações/eletricidade e gás, com os seus comprimentos.")
    prompt = (
        "Analisa esta planta de redes exteriores / planta de implantação. Identifica cada rede traçada e estima o seu comprimento em metros, a largura e a profundidade da vala se indicadas.\nDevolve APENAS este JSON:\n{ \"scale_detected\": string|null, \"scale_confidence\": number(0-1),\n  \"networks\": [ { \"key\": \"EP\"|\"EU\"|\"AEP\"|\"telecom\"|\"gaz\", \"label\": string,\n    \"length_ml\": number, \"larg_m\": number|null, \"prof_m\": number|null,\n    \"confidence\": number(0-1), \"bbox\": [x1,y1,x2,y2] (normalizado 0-1, implantação do traçado) } ],\n  \"notes\": string }\n(EP = águas pluviais, EU = águas residuais, AEP = abastecimento de água.) Estima os comprimentos o melhor possível através da escala/cotas. Se uma rede estiver ausente, não a listes. Se incerto, baixa a confiança (<0.6). Não inventes redes. Textos em português europeu."
    )
    return _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO, feature="vrd"),
                 {"networks": [], "scale_confidence": 0, "notes": ""})


def _json(raw: str, fallback):
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find('{')
    end = raw.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass
    return fallback


async def plan_command(rooms: list[dict], walls: list[dict], command: str,
                       measurements: list[dict] | None = None,
                       history: list[dict] | None = None) -> dict:
    """Interprète une commande en langage naturel sur un plan et renvoie UNE action
    structurée (aperçu, sans appliquer). Utilisé par l'assistant IA du plan (P3).

    Actions possibles :
      rename_room            {room_id, new_name}
      delete_room            {room_id}
      set_room_surface       {room_id, surface_m2}
      set_room_height        {room_id, height_m}
      reclassify_wall        {wall_id, new_type}  new_type ∈ porteur|cloison|doublage
      rename_measurement     {measurement_id, new_label}
      delete_measurement     {measurement_id}
      set_measurement_height {measurement_id, wall_height_m}
      set_measurement_surface {measurement_id, surface_m2}  (fixe la surface m² d'une cote existante)
      adjust_measurement_surface {measurement_id, delta_m2}  (AJOUTE/DÉDUIT une surface ; delta négatif = déduction, ex trémie)
      set_measurement_length {measurement_id, length_m}     (fixe le linéaire ml d'une cote existante)
      set_measurement_poste  {measurement_id, poste}
      set_measurements_height_bulk {wall_height_m, filter}  (hauteur sur plusieurs murs ; filter=mot-clé du libellé, "" = tous)
      create_measurement     {measure_type, label, poste?, ...}  (crée une nouvelle cote : surface m² / linéaire ml / sous-plafond rampant)
      create_measurements_bulk {items:[{measure_type,...}, ...]}  (crée PLUSIEURS cotes d'un coup)
      duplicate_measurement  {measurement_id}  (duplique une cote existante)
      web_answer             {query}  (question factuelle → recherche web avec sources)
      assign_all_postes      {}  (classe automatiquement toutes les mesures non classées)
      estimate_page          {}  (chiffre toute la page et renvoie le total estimé)
      add_note               {text}
      none                   {}  (commande non comprise / hors périmètre)
    """
    rooms_ctx = [{"room_id": r.get("room_id"), "name": r.get("name"),
                  "surface_m2": r.get("surface_m2"),
                  "height_m": r.get("ceiling_height_m") or r.get("height_m")}
                 for r in (rooms or [])]
    walls_ctx = [{"wall_id": w.get("wall_id") or w.get("id"),
                  "wall_type": w.get("wall_type")} for w in (walls or [])][:60]
    meas_ctx = [{"measurement_id": m.get("measurement_id"),
                 "label": m.get("label"),
                 "kind": m.get("kind"),
                 "surface_m2": (m.get("wall_area_net_m2") if m.get("wall_area_net_m2") is not None
                                else m.get("area_m2")),
                 "length_m": m.get("length_m") if m.get("length_m") is not None else m.get("value_m"),
                 "wall_height_m": m.get("wall_height_m"),
                 "poste": m.get("poste")}
                for m in (measurements or [])][:80]
    system = (BRAND + " És o assistente de edição de uma planta de medição de construção. Convertes uma instrução do utilizador em UMA única ação JSON estrita. Uma planta contém DIVISÕES, PAREDES detetadas e MEDIÇÕES (cotas traçadas: áreas, lineares, paredes com altura). Age sobre o elemento mais pertinente. Responde APENAS em JSON, sem markdown.")
    hist_block = ""
    if history:
        turns = []
        for t in history[-6:]:
            u = (t.get("command") or "").strip()[:200]
            r = (t.get("result") or "").strip()[:160]
            mid = t.get("measurement_id")
            line = f"- Utilisateur : « {u} »"
            if r:
                line += f' → Feito: {r}'
            if mid:
                line += f" (measurement_id={mid})"
            turns.append(line)
        if turns:
            hist_block = (
                "CONVERSA RECENTE (para resolver as referências como «o», «a», «isso», «esta cota», «orçamenta-a» → retoma o measurement_id da última ronda em causa):\n"
                + "\n".join(turns) + "\n\n")
    prompt = (
        hist_block +
        f"""DIVISÕES da planta (room_id → nome, área m², altura m):\n{json.dumps(rooms_ctx, ensure_ascii=False)}\n\nPAREDES detetadas (wall_id → tipo):\n{json.dumps(walls_ctx, ensure_ascii=False)}\n\nMEDIÇÕES traçadas (measurement_id → designação, tipo, área m², linear ml, altura da parede m, artigo):\n{json.dumps(meas_ctx, ensure_ascii=False)}\n\nINSTRUÇÃO DO UTILIZADOR: «{command}»\n\nEscolhe a ação correspondente e devolve este esquema EXATO:\n{{\n  "action": "rename_room|delete_room|set_room_surface|set_room_height|reclassify_wall|rename_measurement|delete_measurement|set_measurement_height|set_measurement_surface|adjust_measurement_surface|set_measurement_length|set_measurement_poste|deduct_measurement_areas|set_measurements_height_bulk|create_measurement|create_measurements_bulk|duplicate_measurement|web_answer|assign_all_postes|estimate_page|add_note|none",\n  "params": {{ ... }},\n  "summary": "frase curta em português europeu que descreve o que vai ser feito",\n  "confidence": 0.0\n}}\nRegras: résous les noms de pièce/mesure vers leur id EXACT des listes. Pour set_room_surface, params={{room_id, surface_m2 (nombre)}}. Pour set_room_height, params={{room_id, height_m (nombre en mètres)}}. Pour reclassify_wall, params={{wall_id, new_type}}. Pour rename_measurement, params={{measurement_id, new_label}}. Pour delete_measurement, params={{measurement_id}}. Pour set_measurement_height (hauteur de mur d'une cote linéaire), params={{measurement_id, wall_height_m (nombre en mètres)}}. Pour FIXER la SURFACE d'une cote existante (ex «passe le carrelage à 28 m²», «mets la surface du sol à 30 m²») : set_measurement_surface, params={{measurement_id, surface_m2 (nombre)}}. Pour DÉDUIRE ou AJOUTER une surface à une cote existante (ex «déduis la trémie de 7,4 m² du plancher», «enlève 5 m² au sol», «ajoute 3 m² au carrelage») : adjust_measurement_surface, params={{measurement_id, delta_m2 (NÉGATIF pour déduire, ex -7.4 ; positif pour ajouter)}}. NE CALCULE JAMAIS le résultat toi-même : donne seulement le delta, le serveur fait la soustraction. Pour DÉDUIRE PLUSIEURS trémies/ouvertures d'un coup d'une même surface (ex «déduis 2 trémies de 1,5 m² et une de 4 m² du plancher», «enlève les 3 trémies de 2 m²») : deduct_measurement_areas, params={{measurement_id, areas:[1.5,1.5,4]}} — une valeur par trémie (développe «3 trémies de 2 m²» → [2,2,2]). Le serveur soustrait la somme ; ne calcule pas le total toi-même. Pour FIXER le LINÉAIRE d'une cote existante (ex «mets la cloison à 12 m») : set_measurement_length, params={{measurement_id, length_m (nombre)}}. Pour set_measurement_poste, params={{measurement_id, poste}}. Pour appliquer une MÊME hauteur à PLUSIEURS murs (ex «tous les murs façade à 2,70 m») : set_measurements_height_bulk, params={{wall_height_m (nombre), filter (mot-clé présent dans les libellés, ex «façade» ; chaîne vide si TOUS les murs)}}. Pour les MURS EXTÉRIEURS / de FAÇADE / PÉRIPHÉRIQUES (sans mot-clé précis), utilise set_measurements_height_bulk avec filter="__facade__". Pour CRÉER une nouvelle cote (ex «ajoute un sous-plafond avec rampant de 26% de 15 m² au sol», «ajoute une surface de 20 m² de carrelage», «ajoute un linéaire de 8 m de cloison») : create_measurement, params={{measure_type: "surface"|"linear"|"rampant", label (texte), poste (optionnel, clé du catalogue), area_m2 (si surface), length_m (si linear) + wall_height_m (optionnel, hauteur de mur en m), projected_area_m2 + slope_pct (si rampant : surface AU SOL projetée en m² et pente en %)}}. N'invente JAMAIS une valeur chiffrée absente : si l'utilisateur ne donne pas la surface/longueur/pente, action=none et demande la valeur manquante dans summary. Pour CRÉER PLUSIEURS cotes d'un coup (ex «ajoute 3 cloisons de 4 m», «crée 2 surfaces de 15 m² de carrelage et 1 plancher de 20 m²») : create_measurements_bulk, params={{items:[{{measure_type, label, poste?, area_m2|length_m|projected_area_m2+slope_pct}}, ...]}} — développe les quantités répétées en autant d'items (ex «3 cloisons de 4 m» → 3 items linear length_m=4). Pour DUPLIQUER une cote existante : duplicate_measurement, params={{measurement_id}}. Pour une QUESTION factuelle/informative qui nécessite une recherche Internet (prix indicatif d'un matériau, norme/DTU, produit, définition, fournisseur…) : web_answer, params={{query (pergunta clara em português europeu)}}. N'utilise JAMAIS web_answer pour calculer un métré ou un chiffrage (toujours déterministe). Pour classer/chiffrer automatiquement toutes les mesures sans poste (ex «chiffre tout», «classe toutes les mesures») : assign_all_postes, params={{}}. Pour CHIFFRER toute la page et donner le total (ex «chiffre toute la page», «estime la page», «combien ça coûte») : estimate_page, params={{}}. Si l'utilisateur parle d'une cote/mesure (mur, cloison, façade, plancher, carrelage…) choisis une action measurement_*. S'il parle d'une pièce, choisis une action room_*. Si l'instruction ne correspond à aucune action, action=none et summary explique pourquoi."""
    )
    raw = await _complete(system, prompt, feature="plan_command")
    data = _json(raw, {"action": "none", "params": {},
                       "summary": "Comando não compreendido.", "confidence": 0.0})
    if not isinstance(data, dict) or "action" not in data:
        return {"action": "none", "params": {}, "summary": "Comando não compreendido.", "confidence": 0.0}
    data.setdefault("params", {})
    data.setdefault("summary", "")
    data.setdefault("confidence", 0.5)
    return data



async def suggest_line_description(designation: str, context: str = "") -> str:
    """Génère une description professionnelle multi-lignes pour une ligne de devis BTP."""
    system = (BRAND + " Redige descrições de linhas de orçamento de construção, concisas, profissionais e vendáveis para um cliente, em português europeu.")
    prompt = (
        f'Redige a descrição detalhada de uma linha de orçamento de obras: «{designation} ».\n'
        + (f'Contexto do orçamento: {context}\n' if context else "")
        + "Dá 3 a 6 prestações curtas que descrevem o que está incluído (preparação do suporte, fornecimentos/materiais, execução, acabamentos, limpeza). Adaptado a um orçamento para o cliente, sem preço nem quantidade. Responde em texto simples, UMA prestação por linha, começando por «-», sem título nem introdução.")
    return await _complete(system, prompt, feature="quote_describe")


async def ocr_pages_to_text(images: list[str], batch: int = 4) -> str:
    """OCR de pages scannées (PNG base64) via le modèle vision → texte brut, dans l'ordre."""
    system = (BRAND + " És um motor de OCR especializado em documentos técnicos da construção (cadernos de encargos, mapas de quantidades, orçamentos). Transcreves fielmente o texto das páginas, sem resumir nem interpretar.")
    parts: list[str] = []
    for i in range(0, len(images), batch):
        chunk = images[i:i + batch]
        prompt = (f"Transcreve integralmente o texto destas {len(chunk)} página(s) digitalizada(s), por ordem. Conserva a numeração dos artigos, os títulos dos capítulos, as quantidades e unidades, as marcas e normas. Separa cada página por uma linha '--- page ---'. Responde apenas com o texto transcrito.")
        try:
            parts.append((await _complete(system, prompt, images=chunk, feature="cctp_ocr")).strip())
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).warning(f"OCR batch {i} failed: {e}")
    return "\n".join(parts).strip()



async def cctp_lines_from_text(text: str, lot_filter: str = "",
                               library_hints: list[str] | None = None) -> tuple[list[dict], str, list[dict]]:
    """Lit un CCTP (texte) et en extrait les ouvrages imposés + prescriptions (marques, normes, DTU).

    Retourne (lines, title, prescriptions). Prix à 0 (chiffrés ensuite via la bibliothèque).
    """
    system = (BRAND + " És orçamentista da construção: lês um caderno de encargos (cláusulas técnicas) e extrais os trabalhos a orçamentar, com os materiais, marcas e normas impostos, para preparar o orçamento de uma empresa.")
    scope = f'\nTrata APENAS o capítulo: «{lot_filter} ».' if lot_filter else ""
    lib_hint = ""
    if library_hints:
        lib_hint = ("\n\nBIBLIOTECA DE PREÇOS DA EMPRESA (designação (unidade)): quando um trabalho do caderno de encargos corresponder a um trabalho desta lista, retoma EXATAMENTE a sua designação e a sua unidade em «designation»/«unit» (as prescrições do caderno de encargos ficam em «description»). Caso contrário, mantém a designação do caderno de encargos.\n" + " ; ".join(library_hints[:450]))
    prompt = (
        "Eis o texto de um caderno de encargos (excerto). Identifica cada trabalho / prestação que a empresa deve orçamentar e as prescrições técnicas impostas." + scope + lib_hint +
        "\n\nCCTP :\n« " + (text or "").strip()[:60000] + "»\n\nDevolve APENAS este JSON:\n{ \"title\": \"título curto (operação / lote)\", \"lines\": [ { \"category\": \"nome do capítulo do caderno de encargos (ex. CAP. 03 - GESSO CARTONADO)\", \"article\": \"n.º do artigo do caderno de encargos se presente (ex. 3.2.1)\", \"designation\": \"designação curta do trabalho\", \"description\": \"prescrições impostas: materiais, marca/referência ou equivalente, espessuras, classificação, normas, execução (2 a 5 linhas separadas por mudanças de linha)\", \"unit\": \"u|m²|ml|m³|forfait|ens|kg|h\", \"qty\": número ou null se não indicado, \"imposed_materials\": [\"material ou marca imposto\", \"...\"] } ], \"prescriptions\": [ { \"theme\": \"ex. Normas / Segurança / Receção\", \"text\": \"prescrição geral\" } ] }\nRespeita a numeração e a ordem do caderno de encargos. Agrupa por capítulo. Não inventes preços. Até 60 linhas, em português europeu."
    )
    data = _json(await _complete(system, prompt, feature="cctp_read"), {"lines": []})
    units = ("u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L")
    lines: list[dict] = []
    for l in (data.get("lines") or [])[:60]:
        try:
            desig = str(l.get("designation") or "").strip()[:160]
            if not desig:
                continue
            art = str(l.get("article") or "").strip()[:20]
            desc = str(l.get("description") or "").strip()[:900]
            mats = [str(m).strip()[:80] for m in (l.get("imposed_materials") or []) if str(m).strip()][:8]
            if mats:
                desc = (desc + "\nImposto: " + " · ".join(mats)).strip()
            unit = str(l.get("unit") or "u").strip()
            qty = l.get("qty")
            lines.append({
                "designation": (f"{art} — " if art else "") + desig,
                "description": desc, "unit": unit if unit in units else "u",
                "qty": float(qty) if isinstance(qty, (int, float)) and qty > 0 else 1.0,
                "qty_from_cctp": isinstance(qty, (int, float)) and qty > 0,
                "unit_price_ht": 0, "vat_rate": 6,
                "category": str(l.get("category") or "").strip()[:80],
                "imposed_materials": mats,
            })
        except Exception:  # noqa: BLE001
            continue
    prescriptions = [{"theme": str(p.get("theme") or "")[:60], "text": str(p.get("text") or "")[:500]}
                     for p in (data.get("prescriptions") or [])[:20] if p.get("text")]
    return lines, str(data.get("title") or "").strip()[:120], prescriptions



async def quote_lines_from_text(transcript: str, images: list[str] | None = None,
                                library_hints: list[str] | None = None) -> tuple[list[dict], str]:
    """Transforme une description orale (transcription) + photos optionnelles en lignes de devis BTP.

    Retourne (lines, title). Les prix restent à 0 (chiffrés ensuite via la bibliothèque).
    """
    system = (BRAND + " Transformas a descrição oral de um profissional em linhas de orçamento de construção estruturadas e realistas (designações normalizadas, unidades e quantidades estimadas), em português europeu.")
    photo_hint = ("\n\nSão anexadas FOTOGRAFIAS da obra: usa-as para precisar as prestações (estado existente, materiais, áreas visíveis, condicionantes) e afinar as quantidades."
                  if images else "")
    lib_hint = ""
    if library_hints:
        lib_hint = ("\n\nBIBLIOTECA DE PREÇOS DISPONÍVEL (designação (unidade)): retoma EXATAMENTE estas designações e unidades sempre que um trabalho corresponder à prestação descrita (decompõe uma prestação global em trabalhos da biblioteca com quantidades coerentes, ex.: áreas em m², pontos elétricos à unidade). Só cria uma designação livre se nenhum trabalho servir.\n"
                    + " ; ".join(library_hints[:450]))
    prompt = (
        "A partir desta descrição de obra (transcrição de voz de um profissional)"
        + (" e das fotografias anexadas" if images else "")
        + f", gera as linhas de orçamento.\nDescrição: «{(transcript or '').strip()[:4000]} »"
        + photo_hint + lib_hint
        + "\n\nDevolve APENAS este JSON:\n{ \"title\": \"título curto do orçamento\", \"lines\": [ { \"designation\": \"designação curta do serviço\", \"description\": \"detalhe dos serviços incluídos (2 a 4 linhas separadas por mudanças de linha)\", \"unit\": \"u|m²|ml|m³|forfait|ens|h|j\", \"qty\": número, \"vat_rate\": 6 } ] }\nEstima quantidades plausíveis se não forem dadas. Não inventes preços. Textos em português europeu. "
        + ("3 a 20 linhas no máximo" if library_hints else "3 a 12 linhas no máximo") + ", em português europeu."
    )
    data = _json(await _complete(system, prompt, images=images, feature="quote_from_text"), {"lines": []})
    units = ("u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L")
    lines: list[dict] = []
    for l in (data.get("lines") or [])[:20]:
        try:
            lines.append({
                "designation": str(l.get("designation") or "").strip()[:160],
                "description": str(l.get("description") or "").strip()[:1000],
                "unit": l.get("unit") if l.get("unit") in units else "u",
                "qty": max(0.0, float(l.get("qty") or 1)),
                "unit_price_ht": 0.0,
                "vat_rate": float(l.get("vat_rate") or 10),
                "category": "",
            })
        except Exception:
            continue
    return lines, (data.get("title") or "").strip()[:160]


async def extract_document_from_pdf(text: str = "", images: list[str] | None = None) -> dict:
    """Extrait un devis/facture (venant d'un autre logiciel) en structure ConstruPilot.

    `text` = texte extrait du PDF (PDF natif) ; `images` = pages rendues en PNG b64 (scans).
    Retourne un dict : doc_type, number, issue_date, client{}, lines[], notes.
    """
    system = (BRAND + " Extrais os dados de um orçamento ou de uma fatura de construção (emitido por outro software) para os importar. Lês os contactos do CLIENTE (destinatário), o NÚMERO do documento tal como impresso, a DATA e TODAS as linhas de prestações com quantidades, unidades, preços unitários sem IVA e taxas de IVA.")
    body = (
        "Analisa este documento" + (" (texto extraído abaixo)" if text else " (ver as imagens/páginas anexadas)")
        + " e devolve APENAS este JSON, sem comentário:\n{ \"doc_type\": \"quote|invoice|credit_note\", \"number\": \"número EXATO tal como impresso no documento\", \"issue_date\": \"AAAA-MM-DD ou vazio\", \"client\": { \"first_name\": \"\", \"last_name\": \"\", \"company\": \"\", \"email\": \"\", \"phone\": \"\", \"address\": \"\", \"postal_code\": \"\", \"city\": \"\", \"siret\": \"\" }, \"lines\": [ { \"designation\": \"designação da prestação\", \"unit\": \"u|m²|ml|m³|forfait|ens|h|j|kg|L\", \"qty\": número, \"unit_price_ht\": número, \"vat_rate\": número } ], \"notes\": \"condições/pagamento eventuais\" }\nRegras: doc_type = \'invoice\' se for uma FATURA, \'credit_note\' se for uma NOTA DE CRÉDITO, caso contrário \'quote\' (ORÇAMENTO). O CLIENTE é o destinatário, NÃO a empresa emitente. Retoma o número EXATAMENTE (ex.: \'2024-045\', \'FT 2024/12\'). Preços unitários SEM IVA. Não inventes nada: deixa vazio se a informação estiver ausente. No campo siret, coloca o NIF/NIPC se existir."
    )
    if text:
        body += f'\n\n=== TEXTO DO DOCUMENTO ===\n{text[:12000]}'
    raw = await _complete(system, body, images=images or None, feature="doc_import")
    data = _json(raw, {})
    units = ("u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L")
    dt = data.get("doc_type")
    if dt not in ("quote", "invoice", "credit_note"):
        dt = "quote"
    lines: list[dict] = []
    for l in (data.get("lines") or [])[:200]:
        try:
            lines.append({
                "designation": str(l.get("designation") or "").strip()[:200],
                "description": "",
                "unit": l.get("unit") if l.get("unit") in units else "u",
                "qty": max(0.0, float(l.get("qty") or 0)),
                "unit_price_ht": max(0.0, float(l.get("unit_price_ht") or 0)),
                "vat_rate": float(l.get("vat_rate") if l.get("vat_rate") is not None else 20),
                "category": "Importado",
            })
        except Exception:
            continue
    cl = data.get("client") or {}
    client = {k: str(cl.get(k) or "").strip()[:200] for k in
              ("first_name", "last_name", "company", "email", "phone",
               "address", "postal_code", "city", "siret")}
    return {
        "doc_type": dt,
        "number": str(data.get("number") or "").strip()[:60],
        "issue_date": str(data.get("issue_date") or "").strip()[:10],
        "client": client,
        "lines": lines,
        "notes": str(data.get("notes") or "").strip()[:2000],
    }



def _analysis_prompt(description: str) -> str:
    """Construit le prompt JSON d'analyse (séparé pour lisibilité/testabilité)."""
    types = ", ".join(f"{p['key']}" for p in PROJECT_TYPES)
    lots = ", ".join(l["key"] for l in LOTS)
    finishes = ", ".join(f["key"] for f in FINISH_LEVELS)
    return f'Analisa esta descrição de projeto de obras e devolve este JSON:\n{{\n "project_type": "um de: {types}",\n "surface": número em m² (estima se ausente),\n "ceiling_height_m": número em metros (pé-direito; se mencionado na descrição utiliza-o, caso contrário 2.5 por defeito para uma moradia moderna, 2.6 para um apartamento, 2.7 a 3.0 para um edifício antigo),\n "levels": [\n    // Detalhe por piso APENAS se o edifício tiver vários níveis com pés-direitos diferentes\n    // (ex: moradia antiga R/C 2.60m + Piso 1 2.30m + sótão 1.80m).\n    // Caso contrário devolver uma lista vazia ou omitir.\n    {{"label": "RDC" | "R+1" | "R-1" | "combles" | "sous-sol", "surface_m2": número, "ceiling_height_m": número}}\n ],\n "building_type": "maison|appartement|commerce",\n "finish_level": "um de: {finishes}",\n "condition": "neuf|bon|moyen|vetuste|a_renover_totalement",\n "lots": ["clés parmi: {lots}"],\n "summary": "resumo do projeto em 2 frases, em português europeu",\n "questions": ["3 a 5 perguntas curtas e indispensáveis para afinar a orçamentação"],\n "risks": ["riscos ou pontos de atenção identificados"],\n "diy_advice": "o que o utilizador pode fazer sozinho e o que deve confiar a um profissional"\n}}\n\nDescrição: {description}'


def _clean_levels(levels: list) -> list[dict]:
    """Ne garde que les niveaux bien formés et bornés (1,5 m ≤ HSP ≤ 5 m)."""
    cleaned = []
    for lvl in levels or []:
        if not isinstance(lvl, dict):
            continue
        try:
            s = float(lvl.get("surface_m2") or 0)
            h = float(lvl.get("ceiling_height_m") or 0)
        except (TypeError, ValueError):
            continue
        if s > 0 and 1.5 <= h <= 5.0:
            cleaned.append({"label": str(lvl.get("label") or "niveau")[:20],
                            "surface_m2": round(s, 2),
                            "ceiling_height_m": round(h, 2)})
    return cleaned


def _normalize_analysis(data: dict, description: str) -> dict:
    """Applique défauts + bornes sur la réponse IA (parsing séparé de l'appel)."""
    defaults = {"project_type": "renovation_complete", "surface": 100,
                "ceiling_height_m": 2.5, "levels": [], "building_type": "maison",
                "finish_level": "standard", "condition": "moyen", "lots": [],
                "questions": [], "risks": [], "summary": description[:200],
                "diy_advice": ""}
    for k, v in defaults.items():
        data.setdefault(k, v)
    try:
        data["surface"] = float(data["surface"])
    except (TypeError, ValueError):
        data["surface"] = 100.0
    try:
        data["ceiling_height_m"] = max(2.0, min(5.0, float(data["ceiling_height_m"])))
    except (TypeError, ValueError):
        data["ceiling_height_m"] = 2.5
    data["levels"] = _clean_levels(data.get("levels"))
    return data


async def analyse_description(description: str) -> dict:
    system = BRAND + (
        "\nAnalisas uma descrição de projeto e devolves APENAS JSON válido, sem texto à volta. Textos em português europeu."
    )
    raw = await _complete(system, _analysis_prompt(description), feature="smart_project")
    return _normalize_analysis(_json(raw, {}), description)


async def analyse_photo(image_b64: str, note: str = "") -> dict:
    system = BRAND + "\nAnalisas uma fotografia de uma divisão e devolves APENAS JSON válido. Textos em português europeu."
    prompt = f"""Analisa esta fotografia de divisão/obra. As medidas são aproximadas e devem ser confirmadas.\nDevolve este JSON (textos em português europeu):\n{{\n "room_type": "tipo de divisão identificado",\n "estimated_dimensions": {{"length_m": número, "width_m": número, "height_m": número, "floor_area_m2": número}},\n "elements": {{"walls": "estado", "floor": "estado", "ceiling": "estado", "windows": número, "doors": número, "sanitary": "descrição"}},\n "general_condition": "neuf|bon|moyen|vetuste|a_renover_totalement",\n "recommended_works": [{{"lot": "chave do lote", "name": "nome", "reason": "porquê"}}],\n "risks": ["riscos visíveis"],\n "confidence": "low|medium|high",\n "notes": "comentário profissional"\n}}\nPrecisão do utilizador: {note or 'aucune'}"""
    raw = await _complete(system, prompt, images=[image_b64], feature="photo_analyse")
    data = _json(raw, {})
    data.setdefault("room_type", "Divisão")
    data.setdefault("estimated_dimensions", {"length_m": 3, "width_m": 3, "height_m": 2.5, "floor_area_m2": 9})
    data.setdefault("recommended_works", [])
    data.setdefault("risks", [])
    data.setdefault("confidence", "low")
    data["disclaimer"] = ("As dimensões obtidas da análise da fotografia são aproximadas. Confirme-as antes de qualquer cálculo definitivo.")
    return data


async def analyse_quote(text: str = "", image_b64: str | None = None,
                       reference: dict | None = None) -> dict:
    system = BRAND + "\nAnalisas um orçamento ou uma fatura de obras e devolves APENAS JSON válido. Textos em português europeu."
    ref = json.dumps(reference or {}, ensure_ascii=False)[:2000]
    prompt = f"""Analisa este orçamento / fatura de obras.\nPreços de referência ConstruPilot para comparação: {ref}\nDevolve este JSON (textos em português europeu):\n{{\n "company": "nome da empresa se visível",\n "total_ht": número ou null,\n "total_ttc": número ou null,\n "lines": [{{"label": "serviço", "quantity": número, "unit": "unidade", "unit_price": número, "total": número}}],\n "verdict": "bas|correct|eleve|tres_eleve",\n "verdict_label": "explicação curta do veredicto",\n "delta_vs_reference_pct": número (desvio estimado em % vs preço de referência),\n "missing_items": ["serviços potencialmente esquecidos"],\n "exclusions": ["exclusões detetadas"],\n "warranties": ["garantias mencionadas"],\n "negotiation_tips": ["conselhos de negociação"]\n}}\nTexto do orçamento: {text[:6000] or 'ver imagem'}"""
    raw = await _complete(system, prompt, images=[image_b64] if image_b64 else None,
                          feature="quote_scan")
    data = _json(raw, {})
    data.setdefault("verdict", "correct")
    data.setdefault("lines", [])
    data.setdefault("missing_items", [])
    data.setdefault("exclusions", [])
    data.setdefault("warranties", [])
    data.setdefault("negotiation_tips", [])
    return data


async def compare_quotes(quotes: list[dict]) -> dict:
    system = BRAND + "\nComparas vários orçamentos e devolves APENAS JSON válido. Textos em português europeu."
    prompt = f'Compara estes orçamentos de obras e devolve este JSON:\n{{\n "ranking": [{{"company": "nome", "total": número, "score": 0-100, "comment": "análise"}}],\n "best_value": "nome da empresa com a melhor relação qualidade/preço",\n "differences": ["diferenças importantes de prestações, quantidades ou materiais"],\n "missing_items": ["elementos esquecidos por alguns orçamentos"],\n "recommendation": "recomendação final ConstruPilot"\n}}\nOrçamentos: {json.dumps(quotes, ensure_ascii=False)[:8000]}'
    raw = await _complete(system, prompt, feature="quote_compare")
    data = _json(raw, {})
    data.setdefault("ranking", [])
    data.setdefault("differences", [])
    data.setdefault("missing_items", [])
    return data


async def project_advice(estimation: dict) -> str:
    system = BRAND
    slim = {
        "type": estimation.get("project_type_name"), "surface": estimation.get("surface"),
        "finition": estimation.get("finish_level_name"), "total": estimation.get("total_avg"),
        "lots": [{"nom": l["name"], "total": l["total"], "difficulté": l["difficulty_label"]}
                 for l in estimation.get("lots", [])],
    }
    prompt = ("Redige recomendações profissionais ConstruPilot para esta obra, em português europeu (6 a 10 tópicos curtos: ordem dos trabalhos, pontos de atenção, poupanças possíveis, o que é possível fazer sozinho). Sem títulos markdown, apenas tópicos \'- \'.\n"
              + json.dumps(slim, ensure_ascii=False))
    return await _complete(system, prompt, feature="project_advice")


async def extract_price_library(images: list[str]) -> list[dict]:
    """Extrait les lignes tarifaires d'un bordereau de prix PDF (images base64).

    Retourne [{"designation": str, "unit": str, "unit_price": number, "ref": str}].
    """
    if not images:
        return []
    system = (BRAND + " És um assistente de extração de tabelas de preços da construção. Lês tabelas de preços (designação, unidade, preço unitário sem IVA) em imagens de documentos e devolves APENAS JSON válido.")
    prompt = (
        "Extrai TODAS as linhas de preços visíveis nestas páginas de tabela de preços (fornecimentos/prestações com um preço unitário).\nDevolve APENAS este JSON: { \"lines\": [ { \"designation\": str, \"unit\": str, \"unit_price\": número, \"ref\": str } ] }\n- designation = designação da prestação/produto.\n- unit = unidade (m2, ml, u, h, vg…) ou \"\" se ausente.\n- unit_price = preço unitário sem IVA em euros (número, sem símbolo).\n- ref = código/referência do artigo se presente, caso contrário \"\".\nIgnora os títulos de secção, subtotais e linhas sem preço."
    )
    data = _json(await _complete(system, prompt, images=images[:12],
                                 feature="price_library"), {"lines": []})
    out = []
    for row in (data.get("lines") or []):
        try:
            pu = float(row.get("unit_price") or 0)
        except Exception:
            continue
        des = str(row.get("designation") or "").strip()
        if not des or pu <= 0:
            continue
        out.append({
            "designation": des[:300],
            "unit": str(row.get("unit") or "").strip()[:20],
            "unit_price": round(pu, 2),
            "ref": str(row.get("ref") or "").strip()[:40],
        })
    return out


async def price_dpgf_lines(items: list[dict], context: str = "") -> list[float]:
    """Estime un prix unitaire HT (€, fournitures + pose, France) par ligne de DPGF/BPU.

    items: [{"designation": str, "unit": str, "qty": number}]
    context: prescriptions CCTP / consignes du pro à respecter (optionnel).
    Retourne une liste de prix unitaires alignée sur items (0 si inconnu).
    """
    if not items:
        return []
    system = (BRAND + " És medidor-orçamentista da construção. Estimas preços unitários sem IVA realistas (fornecimento + aplicação, preços Portugal 2026) para linhas de um mapa de quantidades. Devolves APENAS JSON válido.")
    slim = [{"i": n, "designation": (it.get("designation") or "")[:180],
             "unit": it.get("unit") or "u"} for n, it in enumerate(items[:200])]
    prompt = (
        "Estima o preço unitário sem IVA (€) de cada linha deste mapa de quantidades de construção (preços Portugal 2026).\n"
        + (f'Prescrições técnicas a respeitar (caderno de encargos / instruções):\n{context[:4000]}\n\n' if context else "")
        + f'Linhas: {json.dumps(slim, ensure_ascii=False)}\n\nDevolve APENAS este JSON: {{ "prices": [ {{ "i": índice, "pu": número }} ] }}\npu = preço unitário sem IVA realista de fornecimento+aplicação para a unidade dada. Põe 0 se a linha não for orçamentável (título, subtotal, texto).'
    )
    data = _json(await _complete(system, prompt, feature="dpgf_pricing"), {"prices": []})
    out = [0.0] * len(items)
    for row in (data.get("prices") or []):
        try:
            i = int(row.get("i"))
            if 0 <= i < len(out):
                out[i] = max(0.0, float(row.get("pu") or 0))
        except Exception:
            continue
    return out



async def dpgf_directives(instructions: str, lots: list[str]) -> dict:
    """Traduit les consignes du pro en directives structurées pour le chiffrage DPGF.

    Ex. « ne chiffre pas le carrelage et le parquet, marge 12 %, peinture Dulux »
    → exclusions, coefficients et notes techniques.
    """
    text = (instructions or "").strip()
    if not text:
        return {"exclude_keywords": [], "exclude_lots": [], "margin_pct": 0,
                "lot_margins": {}, "notes": []}
    system = (BRAND + " Convertes as instruções de um profissional em diretivas de orçamentação. Devolves APENAS JSON válido, sem comentário.")
    prompt = (
        f'Instruções do profissional: «{text[:2000]}»\nCapítulos presentes no mapa: {json.dumps(lots[:60], ensure_ascii=False)}\n\nDevolve APENAS este JSON: {{\n  "exclude_keywords": ["palavras-chave dos trabalhos a NÃO orçamentar"],\n  "exclude_lots": ["designações exatas de capítulos a não orçamentar"],\n  "margin_pct": número (coeficiente global em %, 0 se não indicado),\n  "lot_margins": {{ "designação do capítulo": percentagem }},\n  "notes": ["prescrições a respeitar (marcas, materiais, execução)"]\n}}\nPalavras-chave em minúsculas, no singular, tal como aparecem nas designações (ex.: «azulejo», «soalho»). Não inventes exclusões nem margens não pedidas.'
    )
    data = _json(await _complete(system, prompt, feature="dpgf_directives"), {})
    return {
        "exclude_keywords": [str(x)[:60] for x in (data.get("exclude_keywords") or [])][:40],
        "exclude_lots": [str(x)[:80] for x in (data.get("exclude_lots") or [])][:20],
        "margin_pct": float(data.get("margin_pct") or 0),
        "lot_margins": {str(k)[:80]: float(v or 0) for k, v in (data.get("lot_margins") or {}).items()},
        "notes": [str(x)[:300] for x in (data.get("notes") or [])][:30],
    }


async def cctp_prescriptions(cctp_text: str, lots: list[str]) -> dict:
    """Extrait du CCTP les prescriptions qui impactent le chiffrage."""
    text = (cctp_text or "").strip()
    if len(text) < 200:
        return {"summary": "", "prescriptions": []}
    system = (BRAND + " És orçamentista da construção. Lês um caderno de encargos e extrais as prescrições que mudam o preço ou o descritivo dos trabalhos. Devolves APENAS JSON válido.")
    prompt = (
        f'Capítulos do mapa: {json.dumps(lots[:60], ensure_ascii=False)}\n\nExcerto do caderno de encargos:\n{text[:60000]}\n\nDevolve APENAS este JSON: {{\n  "summary": "síntese em 3 frases das exigências principais",\n  "prescriptions": [ {{ "lot": "designação do capítulo em causa ou vazio",\n     "keywords": ["palavras-chave dos trabalhos em causa"],\n     "text": "prescrição concreta (material, marca, espessura, execução, norma)",\n     "price_impact_pct": número (impacto estimado no preço unitário, 0 se neutro) }} ]\n}}\nNo máximo 40 prescrições, as mais estruturantes. price_impact_pct entre -20 e 40.'
    )
    data = _json(await _complete(system, prompt, feature="dpgf_cctp"), {})
    out = []
    for p in (data.get("prescriptions") or [])[:40]:
        impact = float(p.get("price_impact_pct") or 0)
        out.append({"lot": str(p.get("lot") or "")[:80],
                    "keywords": [str(k)[:60] for k in (p.get("keywords") or [])][:12],
                    "text": str(p.get("text") or "")[:500],
                    "price_impact_pct": max(-20.0, min(40.0, impact))})
    return {"summary": str(data.get("summary") or "")[:800], "prescriptions": out}


async def cctp_missing_works(cctp_text: str, designations: list[str]) -> list[dict]:
    """Ouvrages décrits au CCTP mais absents du bordereau (oublis de chiffrage)."""
    text = (cctp_text or "").strip()
    if len(text) < 200:
        return []
    system = (BRAND + " És orçamentista da construção. Comparas um caderno de encargos com o mapa de quantidades e assinalas os trabalhos descritos mas não orçamentados. Devolves APENAS JSON válido.")
    prompt = (
        f'Excerto do caderno de encargos:\n{text[:50000]}\n\nDesignações presentes no mapa: {json.dumps(designations[:300], ensure_ascii=False)}\n\nDevolve APENAS este JSON: {{ "missing": [ {{ "lot": "capítulo em causa ou vazio",\n  "designation": "trabalho em falta, designação do mapa de quantidades",\n  "unit": "m2 | ml | m3 | u | forfait", "reason": "onde é exigido no caderno de encargos" }} ] }}\nMáximo 15 omissões, apenas trabalhos realmente ausentes do mapa de quantidades e realmente exigidos pelo caderno de encargos. Ignora as cláusulas administrativas. Textos em português europeu.'
    )
    data = _json(await _complete(system, prompt, feature="dpgf_gaps"), {})
    out = []
    for m in (data.get("missing") or [])[:15]:
        desig = str(m.get("designation") or "").strip()
        if len(desig) < 3:
            continue
        out.append({"lot": str(m.get("lot") or "")[:80], "designation": desig[:300],
                    "unit": str(m.get("unit") or "u")[:12],
                    "reason": str(m.get("reason") or "")[:300]})
    return out
