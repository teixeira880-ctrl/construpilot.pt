"""Auditeur de cohérence des calculs.

Compare les PRIX UNITAIRES DE RÉFÉRENCE utilisés par les moteurs déterministes
(engines/calculators.py) au prix de MARCHÉ actuel en France, obtenu par recherche
web Perplexity (avec citations). Signale les écarts dépassant un seuil (défaut ±20 %).

Zéro hallucination : le prix de marché provient de Perplexity avec ses sources ;
si aucune valeur fiable n'est trouvée, l'article est marqué « indéterminé » (jamais
un chiffre inventé). Les quantités des moteurs restent déterministes et ne sont pas
auditées — seuls les prix de référence le sont, pour détecter une dérive.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import datetime, timezone

from core.db import db
from engines.expenses import cap
from perplexity_plus import client as pplx

log = logging.getLogger("calc_auditor")

DEFAULT_THRESHOLD_PCT = 20.0

# Prix de référence embarqués dans les moteurs déterministes (engines/calculators.py).
# Chaque entrée : code, libellé, prix moteur, unité, requête de marché (France).
REFERENCE_PRICES: list[dict] = [
    {"code": "paint_wall_l", "label": "Peinture murale mate (par litre)", "engine_price": 6.50,
     "unit": "L", "query": "prix moyen peinture murale acrylique mate blanche au litre France"},
    {"code": "tile_sqm", "label": "Carrelage grès cérame 60x60 (fourniture)", "engine_price": 28.00,
     "unit": "m²", "query": "prix moyen carrelage grès cérame 60x60 au m² fourniture France"},
    {"code": "concrete_m3", "label": "Béton prêt à l'emploi livré (toupie)", "engine_price": 135.00,
     "unit": "m³", "query": "prix moyen béton prêt à l'emploi livré toupie au m3 France"},
    {"code": "insulation_sqm", "label": "Laine de verre isolation (fourniture)", "engine_price": 12.00,
     "unit": "m²", "query": "prix moyen laine de verre isolation combles au m² fourniture France"},
    {"code": "drywall_plate", "label": "Plaque de plâtre BA13 250x120 (l'unité)", "engine_price": 7.50,
     "unit": "plaque", "query": "prix moyen plaque de plâtre BA13 250x120 l'unité France"},
    {"code": "block_parpaing", "label": "Parpaing creux 20x20x50 (l'unité)", "engine_price": 1.20,
     "unit": "u", "query": "prix moyen parpaing creux 20x20x50 à l'unité France"},
    {"code": "block_brique", "label": "Brique de construction terre cuite (l'unité)", "engine_price": 0.85,
     "unit": "u", "query": "prix moyen brique de construction terre cuite à l'unité France"},
    {"code": "cement_35kg", "label": "Ciment 35 kg (le sac)", "engine_price": 6.00,
     "unit": "sac 35 kg", "query": "prix moyen sac de ciment 35 kg France"},
    {"code": "mortar_glue_25kg", "label": "Mortier-colle joint mince 25 kg (le sac)", "engine_price": 15.00,
     "unit": "sac 25 kg", "query": "prix moyen mortier-colle carrelage sac 25 kg France"},
    {"code": "render_25kg", "label": "Enduit de façade monocouche 25 kg (le sac)", "engine_price": 12.00,
     "unit": "sac 25 kg", "query": "prix moyen enduit de façade monocouche sac 25 kg France"},
]

_SYSTEM = ("Tu es un acheteur BTP français. On te demande le PRIX MOYEN de détail actuel en France "
           "(TTC, grandes surfaces de bricolage et négoces de matériaux) pour un article et une unité précis. "
           "Donne un seul prix moyen représentatif. Si tu n'as pas de source fiable, mets price_eur à null. "
           "N'invente JAMAIS de valeur.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pplx_configured() -> bool:
    return pplx.configured()


def _parse_money(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).replace("\u202f", " ").replace(",", ".")
    m = re.search(r"\d{1,6}(?:\.\d+)?", s)
    return float(m.group(0)) if m else None


def _parse_answer(text: str) -> dict:
    """Extrait {price_eur, low_eur, high_eur, note} du JSON renvoyé par Perplexity."""
    raw = (text or "").strip()
    start, end = raw.find("{"), raw.rfind("}")
    data: dict = {}
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end + 1])
        except Exception:  # noqa: BLE001
            data = {}
    return {
        "price": _parse_money(data.get("price_eur")),
        "low": _parse_money(data.get("low_eur")),
        "high": _parse_money(data.get("high_eur")),
        "note": (str(data.get("note")) if data.get("note") else "")[:300],
    }


async def _audit_one(item: dict, threshold: float) -> dict:
    instructions = (_SYSTEM + " Réponds UNIQUEMENT en JSON : "
                    '{"price_eur": <nombre ou null>, "low_eur": <nombre ou null>, '
                    '"high_eur": <nombre ou null>, "note": "<courte précision>"}')
    question = f"Prix moyen actuel en France pour : {item['query']}. Unité attendue : {item['unit']}."
    out = {
        "code": item["code"], "label": item["label"], "unit": item["unit"],
        "engine_price": item["engine_price"], "market_price": None, "low": None, "high": None,
        "deviation_pct": None, "status": "undetermined", "note": "", "sources": [], "cost_usd": 0.0,
    }
    try:
        res = await pplx.ask(question=question, instructions=instructions,
                             search_context_size="low", max_results=6, preset="fast",
                             max_output_tokens=400)
    except Exception as exc:  # noqa: BLE001
        log.warning("calc_auditor pplx failed for %s (%s)", item["code"], type(exc).__name__)
        out["note"] = "Recherche de marché indisponible."
        return out
    parsed = _parse_answer(res.get("text") or "")
    out["cost_usd"] = float(res.get("cost_usd") or 0.0)
    out["note"] = parsed["note"]
    out["low"], out["high"] = parsed["low"], parsed["high"]
    out["sources"] = [{"url": c.get("url"), "title": c.get("title")}
                      for c in (res.get("citations") or [])[:5] if c.get("url")]
    market = parsed["price"]
    if market and market > 0 and item["engine_price"] > 0:
        out["market_price"] = round(market, 2)
        dev = (market - item["engine_price"]) / item["engine_price"] * 100
        out["deviation_pct"] = round(dev, 1)
        out["status"] = "ok" if abs(dev) <= threshold else "warning"
    return out


async def _create_run(triggered_by: str, threshold: float) -> str:
    audit_id = "cad_" + secrets.token_hex(8)
    await db.calc_audits.insert_one({
        "audit_id": audit_id, "triggered_by": triggered_by, "status": "running",
        "threshold_pct": threshold, "items": [], "summary": {},
        "started_at": _now(), "finished_at": None,
    })
    return audit_id


async def _load_overrides() -> dict:
    """Prix de référence corrigés (confirmés par l'admin) : code -> doc override."""
    rows = await db.price_overrides.find({}, {"_id": 0}).to_list(200)
    return {r["code"]: r for r in rows}


async def _execute_run(audit_id: str, threshold: float) -> dict:
    overrides = await _load_overrides()
    items: list[dict] = []
    try:
        for ref in REFERENCE_PRICES:
            ov = overrides.get(ref["code"])
            eff = dict(ref)
            if ov and ov.get("price"):
                eff["engine_price"] = float(ov["price"])
            it = await _audit_one(eff, threshold)
            if ov:
                it["overridden"] = True
                it["default_price"] = ref["engine_price"]
            items.append(it)
        summary = {
            "total": len(items),
            "ok": sum(1 for i in items if i["status"] == "ok"),
            "warning": sum(1 for i in items if i["status"] == "warning"),
            "undetermined": sum(1 for i in items if i["status"] == "undetermined"),
            "overridden": sum(1 for i in items if i.get("overridden")),
            "cost_usd": round(sum(i.get("cost_usd") or 0.0 for i in items), 4),
        }
        await db.calc_audits.update_one(
            {"audit_id": audit_id},
            {"$set": {"status": "done", "items": items, "summary": summary, "finished_at": _now()}})
        return {"audit_id": audit_id, "status": "done", "summary": summary}
    except Exception as exc:  # noqa: BLE001
        log.error("calc_auditor run %s failed (%s)", audit_id, type(exc).__name__)
        await db.calc_audits.update_one(
            {"audit_id": audit_id},
            {"$set": {"status": "error", "items": items,
                      "error": str(exc)[:200], "finished_at": _now()}})
        return {"audit_id": audit_id, "status": "error"}


async def apply_override(code: str, applied_by: str | None = None) -> dict:
    """Confirme un écart : le prix de marché de la dernière audit devient le prix de référence du auditeur."""
    ref = next((r for r in REFERENCE_PRICES if r["code"] == code), None)
    if not ref:
        raise ValueError("code inconnu")
    audit = await db.calc_audits.find_one({"status": "done"}, {"_id": 0}, sort=[("started_at", -1)])
    item = next((i for i in (audit or {}).get("items", []) if i["code"] == code), None)
    if not item or not item.get("market_price"):
        raise ValueError("aucun prix de marché à confirmer pour cet article")
    doc = {
        "code": code, "price": float(item["market_price"]), "unit": ref["unit"],
        "default_price": ref["engine_price"], "market_low": item.get("low"), "market_high": item.get("high"),
        "source_url": (item.get("sources") or [{}])[0].get("url"), "note": item.get("note"),
        "applied_by": applied_by, "applied_at": _now(),
    }
    await db.price_overrides.update_one({"code": code}, {"$set": doc}, upsert=True)
    return doc


async def revert_override(code: str) -> bool:
    res = await db.price_overrides.delete_one({"code": code})
    return bool(res.deleted_count)


async def list_overrides() -> list[dict]:
    return await db.price_overrides.find({}, {"_id": 0}).to_list(200)


async def run_audit(triggered_by: str = "admin", threshold: float = DEFAULT_THRESHOLD_PCT) -> dict:
    """Crée et exécute une audit complète (bloquant). Respecte le plafond de coûts."""
    if not pplx.configured():
        return {"status": "skipped", "reason": "Perplexity non configuré (PERPLEXITY_API_KEY)."}
    try:
        st = await cap.status()
        if st.get("state") in ("exceeded", "frozen"):
            return {"status": "skipped", "reason": st.get("blocking_reason") or "plafond de coûts atteint"}
    except Exception:  # noqa: BLE001
        pass
    audit_id = await _create_run(triggered_by, threshold)
    return await _execute_run(audit_id, threshold)


async def run_scheduled() -> None:
    """Appelé par le planificateur (quotidien). N'échoue jamais bruyamment."""
    try:
        await run_audit(triggered_by="scheduler")
    except Exception:  # noqa: BLE001
        log.exception("calc_auditor scheduled run crashed")


async def ensure_indexes() -> None:
    await db.calc_audits.create_index("audit_id", unique=True)
    await db.calc_audits.create_index([("started_at", -1)])
    await db.price_overrides.create_index("code", unique=True)
