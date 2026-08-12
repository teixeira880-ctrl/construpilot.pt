"""Affiliation fournisseurs : tracking clics + ID commissions.

Chaque supplier de `engines/price_search.SUPPLIERS` peut avoir des champs
`affiliate_enabled`, `affiliate_network`, `affiliate_id`, `commission_rate`,
`cookie_duration`, `tracking_template`.

Événements enregistrés en DB (`affiliate_events`) :
- affiliate_click      : utilisateur clique un lien fournisseur
- supplier_redirect    : redirection HTTP effective (via /r/aff/{...})
- purchase_reported    : reporting manuel/import CSV
- purchase_confirmed   : confirmé par le réseau d'affiliation
- commission_paid      : versement reçu

Public : la présence d'un partenariat commercial est indiquée via
`is_affiliate=True` dans les résultats de prix, avec `disclosure` "Lien partenaire".
"""
from datetime import datetime, timezone
from urllib.parse import quote

from core.db import db


def _now():
    return datetime.now(timezone.utc)


DEFAULT_AFFILIATE_CONFIG = [
    {"supplier_key": "leroymerlin", "affiliate_enabled": True,
     "affiliate_network": "awin", "affiliate_id": "1234-lm",
     "commission_rate": 0.03, "cookie_duration": 30,
     "tracking_template": "https://track.awin.com/awclick?mid=1234-lm&url={url}"},
    {"supplier_key": "manomano", "affiliate_enabled": True,
     "affiliate_network": "cj", "affiliate_id": "9876-mm",
     "commission_rate": 0.045, "cookie_duration": 45,
     "tracking_template": "https://www.anrdoezrs.net/click-9876-mm?url={url}"},
    {"supplier_key": "castorama", "affiliate_enabled": False,
     "affiliate_network": None, "affiliate_id": None,
     "commission_rate": 0.0, "cookie_duration": 0,
     "tracking_template": None},
]


async def seed_affiliate_configs():
    for cfg in DEFAULT_AFFILIATE_CONFIG:
        exists = await db.affiliate_configs.find_one({"supplier_key": cfg["supplier_key"]})
        if not exists:
            cfg["created_at"] = _now().isoformat()
            await db.affiliate_configs.insert_one(dict(cfg))


async def all_configs() -> list[dict]:
    return await db.affiliate_configs.find({}, {"_id": 0}).to_list(200)


async def config_map() -> dict:
    return {c["supplier_key"]: c for c in await all_configs()}


async def upsert_config(cfg: dict):
    cfg["updated_at"] = _now().isoformat()
    await db.affiliate_configs.update_one({"supplier_key": cfg["supplier_key"]},
                                          {"$set": cfg}, upsert=True)


async def enrich_prices(results: list[dict]) -> list[dict]:
    """Ajoute is_affiliate, disclosure, tracking_url à chaque résultat."""
    conf = await config_map()
    out = []
    for r in results:
        key = r.get("supplier_key")
        cfg = conf.get(key)
        if cfg and cfg.get("affiliate_enabled"):
            tracking = cfg.get("tracking_template") or ""
            tracking_url = tracking.replace("{url}", quote(r.get("url", ""), safe=""))
            r["is_affiliate"] = True
            r["affiliate_disclosure"] = "Lien partenaire — ConstruPilot peut recevoir une commission sur cet achat."
            r["tracking_url"] = tracking_url or r.get("url")
        else:
            r["is_affiliate"] = False
        out.append(r)
    return out


async def record_click(user_id: str | None, supplier_key: str, product_url: str,
                       query: str = "") -> str:
    ev = {
        "event": "affiliate_click",
        "user_id": user_id,
        "supplier_key": supplier_key,
        "product_url": product_url,
        "query": query,
        "at": _now().isoformat(),
    }
    result = await db.affiliate_events.insert_one(ev)
    return str(result.inserted_id)


async def record_redirect(user_id: str | None, supplier_key: str, product_url: str) -> None:
    await db.affiliate_events.insert_one({
        "event": "supplier_redirect",
        "user_id": user_id,
        "supplier_key": supplier_key,
        "product_url": product_url,
        "at": _now().isoformat(),
    })


async def stats(days: int = 30) -> dict:
    """Agrégats simples pour le dashboard admin."""
    from datetime import timedelta
    since = (_now() - timedelta(days=days)).isoformat()
    events = await db.affiliate_events.find({"at": {"$gte": since}}, {"_id": 0}).to_list(50000)
    by_supplier: dict = {}
    counts = {"affiliate_click": 0, "supplier_redirect": 0,
              "purchase_reported": 0, "purchase_confirmed": 0}
    revenue_cents = 0
    for e in events:
        counts[e["event"]] = counts.get(e["event"], 0) + 1
        k = e.get("supplier_key") or "unknown"
        s = by_supplier.setdefault(k, {"supplier_key": k, "clicks": 0, "redirects": 0,
                                       "purchases": 0, "gmv_cents": 0, "commission_cents": 0})
        if e["event"] == "affiliate_click":
            s["clicks"] += 1
        elif e["event"] == "supplier_redirect":
            s["redirects"] += 1
        elif e["event"] == "purchase_confirmed":
            s["purchases"] += 1
            s["gmv_cents"] += e.get("amount_cents", 0)
            s["commission_cents"] += e.get("commission_cents", 0)
            revenue_cents += e.get("commission_cents", 0)
    return {"days": days,
            "totals": counts,
            "revenue_cents": revenue_cents,
            "revenue_eur": round(revenue_cents / 100, 2),
            "by_supplier": list(by_supplier.values())}
