"""Prix du devis de l'étude BET : bibliothèque de l'entreprise d'abord, puis prix de marché en ligne, sinon référence.

Ordre pour chaque poste (clé de devis.PRICES) :
  1. bibliothèque de prix de l'entreprise (ou bibliothèque partagée à laquelle le compte a droit) — même moteur de
     correspondance que les orçamentos de l'Assistant (engines.assistant_quote_pricing) ;
  2. postes absents → UNE recherche en ligne groupée des prix de marché (Perplexity), bornée dans le temps ;
     chaque prix trouvé est contrôlé (entre 0,4× et 2,5× la référence, sinon rejeté) ;
  3. sinon prix de référence ConstruPilot.
Le résultat est écrit dans raw["_price_overrides"] ; devis.build_lines l'applique et l'origine de chaque prix est
affichée (commentaire Excel + alerte PRIX-01). Jamais bloquant : toute erreur → prix de référence.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging

log = logging.getLogger("bet.prices")

WEB_TIMEOUT_S = 90
MAX_WEB_ITEMS = 60


def reference_lines(raw: dict) -> list[dict]:
    """Lignes du devis avec les prix de référence (calcul à blanc, sans rendu)."""
    from . import devis, mep, pipeline, structure, timber
    trial = copy.deepcopy(raw)
    trial.pop("_price_overrides", None)
    m, an = pipeline.validate(trial)
    if m is None or any(a.get("level") == "bloquant" for a in an):
        return []
    r = structure.compute(m)
    tim = timber.compute(m, r["loads"])
    return devis.build_lines(m, r, tim, mep.electrical(m), mep.plumbing(m))


async def _library(db, uid: str, lines: list[dict]) -> dict:
    from engines.assistant_quote_pricing import find_price, price_sources
    user = await db.users.find_one({"user_id": uid}, {"_id": 0}) or {"user_id": uid}
    user.setdefault("user_id", uid)
    sources = await price_sources(user)
    if not sources:
        return {}
    out = {}
    for l in lines:
        if l["key"] in out:
            continue
        hit = find_price(l["label"], l["unit"].replace("³", "3").replace("²", "2"), sources)
        if hit and hit.get("unit_price_ht"):
            src = "company_library" if str(hit.get("price_source", "")).startswith("company") else "shared_library"
            out[l["key"]] = {"pu": float(hit["unit_price_ht"]), "src": src, "ref": hit.get("price_reference_label") or ""}
    return out


async def _market(lines: list[dict], country: str, region: str = "") -> dict:
    from engines.perplexity_plus.pplx_client import PplxPlusClient
    client = PplxPlusClient()
    if not client.is_configured():
        return {}
    items, seen = [], set()
    for l in lines:
        if l["key"] in seen:
            continue
        seen.add(l["key"])
        items.append({"key": l["key"], "designation": l["label"][:140], "unit": l["unit"], "reference_price_eur_ht": l["pu"]})
    items = items[:MAX_WEB_ITEMS]
    if not items:
        return {}
    place = {"PT": "Portugal", "FR": "France"}.get(country, country) + (f" ({region})" if region else "")
    system = ("You are a construction cost estimator. Use current web sources (supplier catalogues, price databases, "
              "public cost guides of the given country) to give realistic 2026 market unit prices, excluding VAT, supplied "
              "and installed (fourni-posé / fornecimento e aplicação). Answer ONLY with JSON.")
    prompt = (f"Country / region: {place}. For each item give the current average market unit price in EUR excl. VAT, "
              "same unit as given. If you cannot find a reliable price, use null. Return JSON exactly: "
              '{"prices": {"<key>": {"price": <number|null>, "source": "<short source name>"}}}.\n\nItems:\n'
              + json.dumps(items, ensure_ascii=False))
    resp = await asyncio.wait_for(client.ask_structured(prompt=prompt, system=system, max_tokens=4000), WEB_TIMEOUT_S)
    parsed = (resp or {}).get("parsed") or {}
    prices = parsed.get("prices") if isinstance(parsed, dict) else None
    if not isinstance(prices, dict):
        return {}
    ref = {i["key"]: i["reference_price_eur_ht"] for i in items}
    out = {}
    for k, v in prices.items():
        p = v.get("price") if isinstance(v, dict) else v
        if k not in ref or not isinstance(p, (int, float)) or p <= 0:
            continue
        if not (0.4 * ref[k] <= p <= 2.5 * ref[k]):            # prix aberrant : on garde la référence
            continue
        out[k] = {"pu": round(float(p), 2), "src": "market_web",
                  "ref": (v.get("source") if isinstance(v, dict) else "") or "recherche en ligne"}
    return out


async def resolve(raw: dict, db, uid: str, country: str) -> dict:
    """Remplit raw["_price_overrides"] et renvoie {"library": n, "market_web": n, "reference": n}."""
    try:
        lines = await asyncio.to_thread(reference_lines, raw)
    except Exception:  # noqa: BLE001
        log.warning("bet prices: reference lines failed", exc_info=True)
        return {}
    if not lines:
        return {}
    overrides: dict = {}
    try:
        overrides.update(await _library(db, uid, lines))
    except Exception:  # noqa: BLE001 — bibliothèque indisponible : on continue
        log.warning("bet prices: library lookup failed", exc_info=True)
    missing = [l for l in lines if l["key"] not in overrides]
    if missing:
        try:
            region = str((raw.get("project") or {}).get("city") or (raw.get("project") or {}).get("address") or "")[:80]
            overrides.update(await _market(missing, country, region))
        except Exception:  # noqa: BLE001 — recherche en ligne indisponible / trop lente : prix de référence
            log.warning("bet prices: market lookup failed", exc_info=True)
    raw["_price_overrides"] = overrides
    keys = {l["key"] for l in lines}
    return {"library": sum(1 for k in keys if overrides.get(k, {}).get("src") in ("company_library", "shared_library")),
            "market_web": sum(1 for k in keys if overrides.get(k, {}).get("src") == "market_web"),
            "reference": sum(1 for k in keys if k not in overrides)}
