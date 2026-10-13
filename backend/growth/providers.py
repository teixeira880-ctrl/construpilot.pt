"""AI providers used for visibility tests. Each connector returns the same normalized record; none is simulated by another."""
import asyncio
import os
import time

from growth.common import env

PROVIDER_LABELS = {
    "perplexity": "Perplexity Agent API (recherche web)",
    "openai": "API OpenAI (sans recherche web)",
    "gemini": "API Google Gemini (sans recherche web)",
    "anthropic": "API Anthropic Claude (sans recherche web)",
}
# Indicative USD per 1M tokens for cost ESTIMATES of Emergent-key calls (flagged « estimé » in the ledger).
EST_RATES = {"gpt-5.4": (1.25, 10.0), "gpt-5.4-mini": (0.25, 2.0), "gemini-3.5-flash": (0.30, 2.50), "gemini-3.1-pro": (2.0, 12.0),
             "claude-sonnet-4-6": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0)}
TEST_SYSTEM = {"fr": "Tu es un assistant généraliste. Réponds à la question de l'utilisateur en français, pour un utilisateur situé en France.",
               "pt": "És um assistente generalista. Responde à pergunta do utilizador em português de Portugal, para um utilizador situado em Portugal."}


def provider_status() -> dict:
    """Configuration state of each connector (no secret values)."""
    emergent = bool(env("EMERGENT_LLM_KEY"))
    return {
        "perplexity": {"configured": bool(env("PERPLEXITY_API_KEY")), "label": PROVIDER_LABELS["perplexity"], "web_search": True, "citations_observable": True, "env": "PERPLEXITY_API_KEY"},
        "openai": {"configured": emergent, "label": PROVIDER_LABELS["openai"], "web_search": False, "citations_observable": False, "env": "EMERGENT_LLM_KEY"},
        "gemini": {"configured": emergent, "label": PROVIDER_LABELS["gemini"], "web_search": False, "citations_observable": False, "env": "EMERGENT_LLM_KEY"},
        "anthropic": {"configured": emergent, "label": PROVIDER_LABELS["anthropic"], "web_search": False, "citations_observable": False, "env": "EMERGENT_LLM_KEY"},
    }


def estimate_test_cost(provider: str, model: str | None) -> float:
    if provider == "perplexity":
        return 0.006  # observed ≈ 0.004 $ with preset fast + 1 web_search; margin kept
    rate = EST_RATES.get(model or "", (2.0, 10.0))
    return round((900 * rate[0] + 500 * rate[1]) / 1_000_000, 6)


async def run_perplexity(question: str, lang: str, cfg: dict) -> dict:
    from perplexity import AsyncPerplexity
    client = AsyncPerplexity(api_key=os.environ["PERPLEXITY_API_KEY"], max_retries=0, timeout=90.0)
    payload = {"input": question, "instructions": TEST_SYSTEM[lang], "tools": [{"type": "web_search", "search_context_size": "low", "max_results": 10}],
               "store": False, "max_output_tokens": 700}
    if cfg.get("model"):
        payload["model"] = cfg["model"]
    else:
        payload["preset"] = cfg.get("preset") or "fast"
    t0 = time.monotonic()
    last = None
    for attempt in range(3):
        try:
            r = await client.responses.create(**payload)
            break
        except Exception as e:
            last = e
            status = getattr(e, "status_code", None)
            if status in (429, 500, 502, 503, 504) and attempt < 2:
                ra = (getattr(getattr(e, "response", None), "headers", None) or {}).get("retry-after")
                await asyncio.sleep(min(float(ra), 20) if ra and ra.replace(".", "").isdigit() else 2 ** attempt)
                continue
            raise
    else:
        raise last
    d = r.model_dump()
    citations = []
    for item in d.get("output") or []:
        if item.get("type") == "search_results":
            citations.extend({"url": x.get("url"), "title": x.get("title"), "snippet": x.get("snippet"), "kind": "search_result"} for x in item.get("results") or [])
        for part in item.get("content") or []:
            citations.extend({"url": a.get("url"), "title": a.get("title"), "kind": "url_citation"} for a in part.get("annotations") or [])
    usage = d.get("usage") or {}
    cost = ((usage.get("cost") or {}).get("total_cost")) or 0.0
    return {"text": r.output_text or "", "citations": citations, "model": d.get("model"), "web_search": True, "cost_usd": float(cost), "cost_estimated": False,
            "latency_ms": int((time.monotonic() - t0) * 1000), "status": d.get("status"), "geo_applied": "non disponible", "usage": {k: usage.get(k) for k in ("input_tokens", "output_tokens")},
            "raw_status": d.get("status")}


async def run_emergent(provider: str, question: str, lang: str, cfg: dict) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    model = cfg.get("model") or {"openai": "gpt-5.4", "gemini": "gemini-3.5-flash", "anthropic": "claude-sonnet-4-6"}[provider]
    chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"growth-test-{time.time_ns()}", system_message=TEST_SYSTEM[lang]).with_model(provider, model)
    t0 = time.monotonic()
    text = await chat.send_message(UserMessage(text=question))
    text = text if isinstance(text, str) else str(text)
    rate = EST_RATES.get(model, (2.0, 10.0))
    in_tok, out_tok = len(question) // 4 + 60, len(text) // 4
    return {"text": text, "citations": [], "model": model, "web_search": False, "cost_usd": round((in_tok * rate[0] + out_tok * rate[1]) / 1_000_000, 6), "cost_estimated": True,
            "latency_ms": int((time.monotonic() - t0) * 1000), "status": "completed", "geo_applied": "non applicable (aucune recherche web)", "usage": {"input_tokens": in_tok, "output_tokens": out_tok, "estimated": True}}


async def run_test(provider: str, question: str, lang: str, cfg: dict) -> dict:
    if provider == "perplexity":
        return await run_perplexity(question, lang, cfg)
    if provider in ("openai", "gemini", "anthropic"):
        return await run_emergent(provider, question, lang, cfg)
    raise ValueError("Fournisseur inconnu")
