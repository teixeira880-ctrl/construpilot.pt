"""Price Search Engine — connecteurs fournisseurs normalisés.

Deux modes :
 - TAVILY : recherche web temps réel si TAVILY_API_KEY est renseignée.
 - DEMO   : catalogue de démonstration (clairement identifié source="demo").
Les nouveaux connecteurs s'ajoutent dans SUPPLIERS sans modifier le reste de l'app.
"""
import os
import re
import hashlib
import logging
from datetime import datetime, timezone

import httpx

from core.db import db

log = logging.getLogger(__name__)

# Bornes de plausibilité pour les prix matériaux BTP (EUR).
# Rejette les micro-prix (unitaires vs pot 10L, croisillons vs sacs) et les paniers "totaux".
PRICE_MIN_EUR = 3.0
PRICE_MAX_EUR = 3000.0

SUPPLIERS = [
    {"key": "leroymerlin", "name": "Leroy Merlin", "domain": "leroymerlin.fr", "shipping": 29.9,
     "free_from": 300, "min_order": 0, "delivery_days": 3, "rating": 4.2, "stores": 140},
    {"key": "castorama", "name": "Castorama", "domain": "castorama.fr", "shipping": 24.9,
     "free_from": 250, "min_order": 0, "delivery_days": 4, "rating": 4.0, "stores": 100},
    {"key": "bricodepot", "name": "Brico Dépôt", "domain": "bricodepot.fr", "shipping": 39.0,
     "free_from": 500, "min_order": 0, "delivery_days": 5, "rating": 3.8, "stores": 120},
    {"key": "pointp", "name": "Point.P", "domain": "pointp.fr", "shipping": 45.0,
     "free_from": 800, "min_order": 100, "delivery_days": 4, "rating": 4.1, "stores": 900},
    {"key": "gedimat", "name": "Gedimat", "domain": "gedimat.fr", "shipping": 42.0,
     "free_from": 700, "min_order": 80, "delivery_days": 5, "rating": 4.0, "stores": 450},
    {"key": "bigmat", "name": "BigMat", "domain": "bigmat.fr", "shipping": 44.0,
     "free_from": 700, "min_order": 80, "delivery_days": 6, "rating": 3.9, "stores": 200},
    {"key": "lapeyre", "name": "Lapeyre", "domain": "lapeyre.fr", "shipping": 34.9,
     "free_from": 400, "min_order": 0, "delivery_days": 7, "rating": 3.7, "stores": 120},
    {"key": "manomano", "name": "ManoMano", "domain": "manomano.fr", "shipping": 19.9,
     "free_from": 200, "min_order": 0, "delivery_days": 4, "rating": 4.3, "stores": 0},
    {"key": "bricoman", "name": "Bricoman", "domain": "bricoman.fr", "shipping": 35.0,
     "free_from": 600, "min_order": 0, "delivery_days": 4, "rating": 4.0, "stores": 60},
    {"key": "amazon", "name": "Amazon", "domain": "amazon.fr", "shipping": 0.0,
     "free_from": 25, "min_order": 0, "delivery_days": 2, "rating": 4.4, "stores": 0},
]
SUPPLIERS_BY_KEY = {s["key"]: s for s in SUPPLIERS}

# Prix de référence de démonstration (€) par famille de produit
DEMO_CATALOG = [
    {"match": ["ba13", "placo", "plaque de platre", "plaque platre"], "label": "Plaque de plâtre BA13 250x120",
     "base": 7.60, "unit": "plaque"},
    {"match": ["hydrofuge", "hydro"], "label": "Plaque de plâtre BA13 hydrofuge 250x120", "base": 12.40, "unit": "plaque"},
    {"match": ["rail", "montant"], "label": "Rail / montant placo 48mm 3m", "base": 6.20, "unit": "barre"},
    {"match": ["suspente"], "label": "Suspente plafond (lot de 100)", "base": 42.00, "unit": "lot"},
    {"match": ["fourrure"], "label": "Fourrure F530 3m", "base": 5.10, "unit": "barre"},
    {"match": ["vis"], "label": "Vis TTPC 25mm (500)", "base": 11.90, "unit": "boîte"},
    {"match": ["bande"], "label": "Bande à joint papier 150m", "base": 6.40, "unit": "rouleau"},
    {"match": ["enduit"], "label": "Enduit à joint 25kg", "base": 17.50, "unit": "sac"},
    {"match": ["peinture"], "label": "Peinture murale mate blanche 10L", "base": 48.90, "unit": "pot 10L"},
    {"match": ["sous couche", "sous-couche", "primaire", "impression"], "label": "Sous-couche universelle 10L",
     "base": 39.90, "unit": "pot 10L"},
    {"match": ["carrelage"], "label": "Carrelage grès cérame 60x60", "base": 24.90, "unit": "m²"},
    {"match": ["colle carrelage", "colle"], "label": "Colle carrelage C2 25kg", "base": 15.20, "unit": "sac"},
    {"match": ["joint"], "label": "Joint carrelage 5kg", "base": 11.80, "unit": "sac"},
    {"match": ["croisillon"], "label": "Croisillons 3mm (250)", "base": 5.90, "unit": "boîte"},
    {"match": ["laine de verre", "laine"], "label": "Laine de verre 200mm R6.25", "base": 11.40, "unit": "m²"},
    {"match": ["laine de roche"], "label": "Laine de roche 100mm", "base": 12.90, "unit": "m²"},
    {"match": ["polystyrene", "polyuréthane", "polyurethane"], "label": "Panneau isolant PU 100mm", "base": 21.50, "unit": "m²"},
    {"match": ["pare vapeur", "pare-vapeur", "membrane"], "label": "Membrane pare-vapeur 75m²", "base": 79.00, "unit": "rouleau"},
    {"match": ["beton", "béton"], "label": "Béton prêt à l'emploi 35kg", "base": 5.40, "unit": "sac"},
    {"match": ["ciment"], "label": "Ciment CEM II 35kg", "base": 8.90, "unit": "sac"},
    {"match": ["sable"], "label": "Sable 0/4 35kg", "base": 3.60, "unit": "sac"},
    {"match": ["gravier"], "label": "Gravier 4/20 35kg", "base": 3.90, "unit": "sac"},
    {"match": ["treillis"], "label": "Treillis soudé ST25 3x2m", "base": 22.50, "unit": "panneau"},
    {"match": ["parquet"], "label": "Parquet stratifié clipsable chêne", "base": 18.90, "unit": "m²"},
    {"match": ["receveur", "douche"], "label": "Receveur de douche 90x90 extra-plat", "base": 189.00, "unit": "u"},
    {"match": ["robinet", "mitigeur"], "label": "Mitigeur lavabo chromé", "base": 79.00, "unit": "u"},
    {"match": ["wc", "toilette"], "label": "WC suspendu avec bâti-support", "base": 289.00, "unit": "u"},
    {"match": ["fenetre", "fenêtre"], "label": "Fenêtre PVC double vitrage 120x100", "base": 349.00, "unit": "u"},
    {"match": ["porte"], "label": "Bloc-porte intérieur 83cm", "base": 129.00, "unit": "u"},
    {"match": ["per", "multicouche", "tube"], "label": "Tube multicouche 16mm 50m", "base": 68.00, "unit": "couronne"},
    {"match": ["cable", "câble", "gaine"], "label": "Câble R2V 3G2.5 100m", "base": 89.00, "unit": "couronne"},
    {"match": ["adhesif", "adhésif", "ruban"], "label": "Adhésif de masquage 50m", "base": 4.20, "unit": "rouleau"},
    {"match": ["bache", "bâche"], "label": "Bâche de protection 4x5m", "base": 7.90, "unit": "u"},
    {"match": ["rouleau"], "label": "Rouleau peinture + manchon", "base": 12.50, "unit": "u"},
]


def _match_catalog(query: str):
    q = (query or "").lower()
    best = None
    for item in DEMO_CATALOG:
        for m in item["match"]:
            if m in q:
                if best is None or len(m) > best[0]:
                    best = (len(m), item)
    if best:
        return best[1]
    return {"label": query.strip().title() or "Produit", "base": 24.90, "unit": "u"}


def _seeded(query: str, supplier_key: str) -> float:
    """Pseudo-aléa déterministe pour la démo (non sécurité) — sha256 court."""
    h = hashlib.sha256(f"{query.lower()}|{supplier_key}".encode()).hexdigest()
    return int(h[:6], 16) / 0xFFFFFF


def demo_search(query: str, limit: int = 8) -> list[dict]:
    ref = _match_catalog(query)
    now = datetime.now(timezone.utc)
    out = []
    for s in SUPPLIERS[:limit]:
        r = _seeded(query, s["key"])
        price = round(ref["base"] * (0.82 + r * 0.42), 2)
        stock = ["En stock", "En stock", "Stock limité", "Sur commande"][int(r * 4) % 4]
        out.append({
            "supplier": s["name"], "supplier_key": s["key"], "product": ref["label"],
            "unit": ref["unit"], "price": price, "currency": "EUR",
            "shipping": s["shipping"], "free_shipping_from": s["free_from"],
            "min_order": s["min_order"], "delivery_days": s["delivery_days"],
            "stock": stock, "rating": s["rating"],
            "url": f"https://www.{s['domain']}/recherche?q={query.replace(' ', '+')}",
            "source": "demo", "checked_at": now.isoformat(),
        })
    out.sort(key=lambda x: x["price"])
    return out


PRICE_RE = [r"(\d{1,5}(?:[ .]\d{3})?[,.]\d{2})\s*€", r"€\s*(\d{1,5}(?:[ .]\d{3})?[,.]\d{2})"]


def _parse_all_prices(text: str) -> list[float]:
    """Extrait TOUS les prix trouvés (€), pour pouvoir choisir le plus plausible."""
    seen = []
    for pat in PRICE_RE:
        for m in re.finditer(pat, text or "", re.I):
            raw = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
            try:
                seen.append(float(raw))
            except ValueError:
                continue
    return seen


def _pick_plausible_price(prices: list[float]) -> float | None:
    """Choisit un prix crédible : le plus petit >= PRICE_MIN_EUR et <= PRICE_MAX_EUR.

    Filtre les micro-prix (croisillons/vis, prix TTC/HT confondus) et les paniers
    "à partir de X €" invraisemblables. En cas d'ambiguïté, on privilégie le plus bas
    dans la plage — heuristique cohérente avec un comparateur de prix unitaire.
    """
    plausible = [p for p in prices if PRICE_MIN_EUR <= p <= PRICE_MAX_EUR]
    if not plausible:
        return None
    return min(plausible)


def _parse_price(text: str) -> float | None:
    return _pick_plausible_price(_parse_all_prices(text))


async def tavily_search(query: str, limit: int = 10) -> list[dict]:
    key = os.environ.get('TAVILY_API_KEY') or ''
    if not key:
        return []
    base_payload = {
        "query": f"{query} prix € France",
        "search_depth": "basic", "topic": "general", "max_results": min(20, limit * 2),
        "country": "france",
    }
    domains = [s["domain"] for s in SUPPLIERS]

    async def _call(payload: dict):
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post("https://api.tavily.com/search",
                                      headers={"Authorization": f"Bearer {key}"}, json=payload)
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as e:
            log.warning("tavily_http_error status=%s body=%s",
                        e.response.status_code, e.response.text[:200])
            return {"results": []}
        except Exception as e:
            log.warning("tavily_call_failed err=%s", str(e)[:200])
            return {"results": []}
    # 1er appel filtré sur les enseignes whitelistées
    data = await _call({**base_payload, "include_domains": domains})
    items = data.get("results") or []
    # 2e appel sans filtre si vide, pour élargir la couverture
    if not items:
        data = await _call(base_payload)
        items = data.get("results") or []
    now = datetime.now(timezone.utc)
    out = []
    for item in items:
        url = item.get("url", "")
        sup = next((s for s in SUPPLIERS if s["domain"] in url.lower()), None)
        if not sup:
            continue
        price = _parse_price(f"{item.get('title','')} {item.get('content','')}")
        out.append({
            "supplier": sup["name"], "supplier_key": sup["key"],
            "product": (item.get("title") or "Produit")[:180], "unit": "u",
            "price": price, "currency": "EUR", "shipping": sup["shipping"],
            "free_shipping_from": sup["free_from"], "min_order": sup["min_order"],
            "delivery_days": sup["delivery_days"], "stock": "À vérifier",
            "rating": sup["rating"], "url": url, "source": "web",
            "snippet": (item.get("content") or "")[:400], "checked_at": now.isoformat(),
        })
    out.sort(key=lambda x: x["price"] if x["price"] is not None else 1e9)
    return out[:limit]


async def search(query: str, limit: int = 10) -> dict:
    results = await tavily_search(query, limit)
    mode = "web"
    if not results:
        results = demo_search(query, limit)
        mode = "demo"
    now = datetime.now(timezone.utc)
    docs = [{
        "query": query.lower(), "supplier_key": r["supplier_key"], "product": r["product"],
        "price": r["price"], "source": r["source"], "checked_at": now.isoformat(),
    } for r in results if r.get("price")]
    if docs:
        await db.price_history.insert_many(docs)
    return {"query": query, "mode": mode, "checked_at": now.isoformat(), "results": results}


async def history(query: str) -> dict:
    rows = await db.price_history.find({"query": query.lower()}, {"_id": 0}).to_list(2000)
    prices = [r["price"] for r in rows if r.get("price")]
    current = prices[-1] if prices else None
    if not prices:
        return {"query": query, "points": [], "current": None}
    avg = sum(prices) / len(prices)
    return {
        "query": query, "points": rows[-60:], "current": round(current, 2),
        "avg_30d": round(avg, 2), "best": round(min(prices), 2), "worst": round(max(prices), 2),
        "evolution_pct": round((current - avg) / avg * 100, 1) if avg else 0,
    }


def optimize_cart(items: list[dict]) -> dict:
    """items: [{query, quantity}] -> comparaison mono-fournisseur vs multi-fournisseurs."""
    per_item = []
    for it in items:
        offers = demo_search(it["query"], len(SUPPLIERS))
        per_item.append({"query": it["query"], "quantity": it.get("quantity", 1),
                         "name": it.get("name") or offers[0]["product"], "offers": offers})

    single = []
    for s in SUPPLIERS:
        total = 0.0
        ok = True
        for entry in per_item:
            off = next((o for o in entry["offers"] if o["supplier_key"] == s["key"]), None)
            if not off:
                ok = False
                break
            total += off["price"] * entry["quantity"]
        if not ok:
            continue
        ship = 0.0 if total >= s["free_from"] else s["shipping"]
        single.append({"supplier": s["name"], "supplier_key": s["key"], "products": round(total, 2),
                       "shipping": ship, "total": round(total + ship, 2),
                       "delivery_days": s["delivery_days"],
                       "below_min_order": total < s["min_order"]})
    single.sort(key=lambda x: x["total"])

    # multi-fournisseur : meilleur prix par ligne
    by_supplier = {}
    lines = []
    for entry in per_item:
        best = min(entry["offers"], key=lambda o: o["price"])
        cost = round(best["price"] * entry["quantity"], 2)
        lines.append({"name": entry["name"], "query": entry["query"], "quantity": entry["quantity"],
                      "unit_price": best["price"], "supplier": best["supplier"],
                      "supplier_key": best["supplier_key"], "total": cost, "unit": best["unit"],
                      "stock": best["stock"], "url": best["url"]})
        by_supplier.setdefault(best["supplier_key"], 0.0)
        by_supplier[best["supplier_key"]] += cost

    multi_products = round(sum(lines_i["total"] for lines_i in lines), 2)
    multi_shipping = 0.0
    baskets = []
    for key, amount in by_supplier.items():
        s = SUPPLIERS_BY_KEY[key]
        ship = 0.0 if amount >= s["free_from"] else s["shipping"]
        multi_shipping += ship
        baskets.append({"supplier": s["name"], "supplier_key": key, "products": round(amount, 2),
                        "shipping": ship, "total": round(amount + ship, 2),
                        "below_min_order": amount < s["min_order"]})
    multi_total = round(multi_products + multi_shipping, 2)
    best_single = single[0] if single else None
    savings = round((best_single["total"] - multi_total), 2) if best_single else 0.0
    return {
        "lines": lines, "single_supplier_options": single[:5],
        "best_single": best_single,
        "multi_supplier": {"products": multi_products, "shipping": round(multi_shipping, 2),
                           "total": multi_total, "baskets": baskets,
                           "suppliers_count": len(baskets)},
        "savings": savings,
        "savings_pct": round(savings / best_single["total"] * 100, 1) if best_single and best_single["total"] else 0,
        "mode": "demo",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def stores_nearby(lat: float, lng: float, radius_km: int = 20) -> list[dict]:
    """Return a stable-per-location list of nearby stores (demo mode).

    Uses SHA-256 as a deterministic pseudo-random source seeded by
    (lat, lng, radius). Zero security risk — no `random` module involved,
    and the output is idempotent for a given input.
    """
    seed_bytes = f"{lat:.4f}:{lng:.4f}:{radius_km}".encode()

    def _stream() -> None:
        counter = 0
        while True:
            h = hashlib.sha256(seed_bytes + counter.to_bytes(4, "big")).digest()
            # Yield 4 floats in [0, 1) from each 32-byte digest
            for i in range(0, 32, 8):
                yield int.from_bytes(h[i:i + 8], "big") / 2**64
            counter += 1

    src = _stream()
    def uniform(a, b):
        return a + (b - a) * next(src)

    out = []
    for s in SUPPLIERS:
        if s["stores"] == 0:
            continue
        n = 1 if radius_km <= 5 else (2 if radius_km <= 20 else 3)
        for i in range(n):
            d = round(uniform(1.0, radius_km), 1)
            out.append({
                "supplier": s["name"], "supplier_key": s["key"],
                "name": f"{s['name']} - agence {i + 1}", "distance_km": d,
                "lat": round(lat + uniform(-0.08, 0.08), 5),
                "lng": round(lng + uniform(-0.08, 0.08), 5),
                "open_now": uniform(0, 1) > 0.25, "source": "demo",
            })
    out.sort(key=lambda x: x["distance_km"])
    return out
