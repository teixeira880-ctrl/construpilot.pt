"""Preços de mercado online para as linhas de orçamento que a biblioteca da empresa não cobre.

Usado pelo Assistente (create_quote_draft / add_quote_lines / update_quote_draft): depois da biblioteca, as linhas
ainda sem preço recebem UMA pesquisa web agrupada (Perplexity) — preço médio de mercado sem IVA, fornecimento e
aplicação, no país da empresa. Cada preço fica marcado «preço de mercado online — a verificar» com a fonte.

Regras: nunca bloqueia (erro / tempo esgotado → linha fica por preencher); resultados em cache 30 dias (memória +
coleção market_price_cache) para que o mesmo pedido dê o mesmo orçamento; nenhuma chamada de rede durante os testes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import unicodedata

log = logging.getLogger("market_prices")

TIMEOUT_S = 75
MAX_ITEMS = 60
CACHE_S = 30 * 86400
_CACHE: dict[str, tuple[float, dict]] = {}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9²³/ ]+", " ", s)).strip()


def _key(designation: str, unit: str, country: str) -> str:
    return hashlib.sha1(f"{_norm(designation)}|{_norm(unit)}|{country}".encode()).hexdigest()


def _disabled() -> bool:
    return bool(os.environ.get("PYTEST_CURRENT_TEST")) and not os.environ.get("MARKET_PRICES_IN_TESTS")


async def _ask_web(system: str, prompt: str) -> dict:
    """Perplexity (pesquisa web) → JSON. {} se não configurado."""
    if not os.environ.get("PERPLEXITY_API_KEY"):
        return {}
    try:
        from engines.perplexity_plus.pplx_client import PplxPlusClient
        client = PplxPlusClient()
        if client.is_configured():
            resp = await client.ask_structured(prompt=prompt, system=system, max_tokens=4000)
            return (resp or {}).get("parsed") or {}
    except ImportError:
        pass
    from engines.ai import _perplexity_text                      # construpilot.fr
    txt = (await _perplexity_text(system, prompt, "quote_market_prices") or "").strip()
    a, b = txt.find("{"), txt.rfind("}")
    if a == -1 or b <= a:
        return {}
    try:
        return json.loads(txt[a:b + 1])
    except ValueError:
        return {}


async def _db_get(db, keys: list[str]) -> dict:
    coll = getattr(db, "market_price_cache", None) if db is not None else None
    if coll is None:
        return {}
    try:
        rows = await coll.find({"key": {"$in": keys}}, {"_id": 0}).to_list(len(keys))
        return {r["key"]: (float(r.get("ts") or 0), r.get("hit") or {}) for r in rows}
    except Exception:  # noqa: BLE001
        return {}


async def _db_put(db, items: dict) -> None:
    coll = getattr(db, "market_price_cache", None) if db is not None else None
    if coll is None:
        return
    for k, (ts, hit) in items.items():
        try:
            await coll.update_one({"key": k}, {"$set": {"key": k, "ts": ts, "hit": hit}}, upsert=True)
        except Exception:  # noqa: BLE001
            return


async def lookup(items: list[dict], country: str = "PT", region: str = "", db=None) -> dict[int, dict]:
    """items = [{designation, unit, description?}] → {índice: {"price": float, "source": str}} (só os encontrados)."""
    if not items or _disabled():
        return {}
    country = (country or "PT").upper()
    keys = [_key(it.get("designation", ""), it.get("unit", ""), country) for it in items]
    now = time.time()
    found: dict[int, dict] = {}
    cached = {k: v for k, v in _CACHE.items() if k in set(keys)}
    missing_keys = [k for k in keys if k not in cached]
    if missing_keys:
        cached.update(await _db_get(db, missing_keys))
    todo = []
    for i, k in enumerate(keys):
        c = cached.get(k)
        if c and now - c[0] < (CACHE_S if c[1].get("price") else 86400):      # « não encontrado » só 1 dia
            if c[1].get("price"):
                found[i] = c[1]
        else:
            todo.append(i)
    todo = todo[:MAX_ITEMS]
    if not todo:
        return found
    place = {"PT": "Portugal", "FR": "France", "UA": "Ukraine", "GB": "United Kingdom", "US": "United States"}.get(country, country)
    if region:
        place += f" ({region})"
    payload = [{"id": i, "designation": items[i].get("designation", "")[:160], "unit": items[i].get("unit", ""),
                "details": (items[i].get("description") or "")[:200]} for i in todo]
    system = ("You are a construction cost estimator. Use current web sources (supplier catalogues, public cost guides, "
              "price databases of the given country) to give realistic current market unit prices EXCLUDING VAT, "
              "supplied and installed (labour + materials), in EUR, in exactly the unit given. Answer ONLY with JSON.")
    prompt = (f"Country / region: {place}. For each line item give the average market unit price excl. VAT. If no reliable "
              'price can be found, use null. Return exactly: {"prices": {"<id>": {"price": <number|null>, "source": "<short source>"}}}'
              "\n\nItems:\n" + json.dumps(payload, ensure_ascii=False))
    try:
        parsed = await asyncio.wait_for(_ask_web(system, prompt), TIMEOUT_S)
    except Exception:  # noqa: BLE001 — pesquisa indisponível: as linhas ficam por preencher
        log.warning("market prices lookup failed", exc_info=True)
        return found
    prices = parsed.get("prices") if isinstance(parsed, dict) else None
    if not isinstance(prices, dict):
        return found
    new: dict = {}
    for i in todo:
        v = prices.get(str(i)) if str(i) in prices else prices.get(i)
        p = v.get("price") if isinstance(v, dict) else v
        hit = {}
        if isinstance(p, (int, float)) and 0 < float(p) < 1_000_000:
            hit = {"price": round(float(p), 2), "source": ((v.get("source") if isinstance(v, dict) else "") or "pesquisa online")[:120]}
            found[i] = hit
        new[keys[i]] = (now, hit)                                   # também os não encontrados (evita repetir a pesquisa)
    _CACHE.update(new)
    await _db_put(db, new)
    return found
