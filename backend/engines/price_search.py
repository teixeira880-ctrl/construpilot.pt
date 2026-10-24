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

# Coefficients de prix régionaux indicatifs (main-d'œuvre + matériaux) par grande zone.
DEPARTMENT_COEFF = [
    {"code": "IDF", "name": "Lisboa e Vale do Tejo (Lisboa, Setúbal, Santarém)", "coefficient": 1.15},
    {"code": "Norte", "name": "Norte (Porto, Braga, Viana do Castelo...)", "coefficient": 1.10},
    {"code": "AURA", "name": "Centro (Coimbra, Aveiro, Leiria, Viseu...)", "coefficient": 1.06},
    {"code": "NAQ", "name": "Algarve (Faro)", "coefficient": 1.02},
    {"code": "GES", "name": "Alentejo (Évora, Beja, Portalegre)", "coefficient": 1.00},
    {"code": "HDF", "name": "Madeira", "coefficient": 0.98},
    {"code": "BRE", "name": "Açores", "coefficient": 0.99},
    {"code": "OUTRO", "name": "Outro / Média nacional", "coefficient": 1.00},
]


SUPPLIERS = [
    # Retalhistas de bricolage e materiais de construção em Portugal (portes e prazos indicativos)
    {"key": "leroymerlin", "name": "Leroy Merlin", "domain": "leroymerlin.pt", "shipping": 19.9,
     "free_from": 300, "min_order": 0, "delivery_days": 3, "rating": 4.2, "stores": 20},
    {"key": "bricodepot", "name": "Brico Depôt", "domain": "bricodepot.pt", "shipping": 29.0,
     "free_from": 500, "min_order": 0, "delivery_days": 4, "rating": 3.9, "stores": 10},
    {"key": "aki", "name": "AKI", "domain": "aki.pt", "shipping": 19.9,
     "free_from": 250, "min_order": 0, "delivery_days": 4, "rating": 3.9, "stores": 30},
    {"key": "bricomarche", "name": "Bricomarché", "domain": "bricomarche.pt", "shipping": 19.9,
     "free_from": 300, "min_order": 0, "delivery_days": 5, "rating": 3.9, "stores": 50},
    {"key": "maxmat", "name": "Maxmat", "domain": "maxmat.pt", "shipping": 29.0,
     "free_from": 400, "min_order": 0, "delivery_days": 4, "rating": 4.0, "stores": 25},
    {"key": "obramat", "name": "Obramat", "domain": "obramat.pt", "shipping": 35.0,
     "free_from": 600, "min_order": 0, "delivery_days": 4, "rating": 4.0, "stores": 4},
    {"key": "bigmat", "name": "BigMat", "domain": "bigmat.pt", "shipping": 39.0,
     "free_from": 700, "min_order": 80, "delivery_days": 5, "rating": 3.9, "stores": 30},
    {"key": "amazon", "name": "Amazon", "domain": "amazon.es", "shipping": 0.0,
     "free_from": 29, "min_order": 0, "delivery_days": 3, "rating": 4.4, "stores": 0},
]
SUPPLIERS_BY_KEY = {s["key"]: s for s in SUPPLIERS}

# Prix de référence de démonstration (€) par famille de produit
DEMO_CATALOG = [
    {"match": ["pladur", "gesso cartonado", "ba13", "placo", "plaque de platre", "plaque platre"], "label": "Placa de gesso cartonado 13 mm 250x120",
     "base": 7.60, "unit": "placa"},
    {"match": ["hidrófuga", "hidrofuga", "hydrofuge", "hydro"], "label": "Placa de gesso cartonado hidrófuga 13 mm 250x120", "base": 12.40, "unit": "placa"},
    {"match": ["calha", "montante", "rail", "montant"], "label": "Calha / montante pladur 48 mm 3 m", "base": 6.20, "unit": "barra"},
    {"match": ["tirante", "suspente"], "label": "Tirante de teto (conjunto de 100)", "base": 42.00, "unit": "conjunto"},
    {"match": ["perfil f530", "fourrure"], "label": "Perfil F530 3 m", "base": 5.10, "unit": "barra"},
    {"match": ["parafuso", "vis"], "label": "Parafusos pladur 25 mm (500)", "base": 11.90, "unit": "caixa"},
    {"match": ["fita de juntas", "bande"], "label": "Fita de juntas em papel 150 m", "base": 6.40, "unit": "rolo"},
    {"match": ["massa", "enduit"], "label": "Massa de juntas 25 kg", "base": 17.50, "unit": "saco"},
    {"match": ["tinta", "peinture"], "label": "Tinta plástica mate branca interior 15 L", "base": 48.90, "unit": "balde"},
    {"match": ["primário", "primario", "sous couche", "sous-couche", "primaire", "impression"], "label": "Primário universal 15 L",
     "base": 39.90, "unit": "balde"},
    {"match": ["mosaico", "azulejo", "cerâmica", "ceramica", "porcelânico", "carrelage"], "label": "Mosaico de grés porcelânico 60x60", "base": 24.90, "unit": "m²"},
    {"match": ["cimento-cola", "cimento cola", "colle carrelage", "colle"], "label": "Cimento-cola C2 25 kg", "base": 15.20, "unit": "saco"},
    {"match": ["betume", "junta", "joint"], "label": "Betume de juntas 5 kg", "base": 11.80, "unit": "saco"},
    {"match": ["espaçador", "espacador", "croisillon"], "label": "Espaçadores 3 mm (250)", "base": 5.90, "unit": "caixa"},
    {"match": ["lã de vidro", "la de vidro", "laine de verre", "laine"], "label": "Lã de vidro 200 mm R6.25", "base": 11.40, "unit": "m²"},
    {"match": ["lã de rocha"], "label": "Lã de rocha 100 mm", "base": 12.90, "unit": "m²"},
    {"match": ["poliuretano", "xps", "eps", "esferovite", "polystyrene", "polyuréthane", "polyurethane"], "label": "Placa isolante PU 100 mm", "base": 21.50, "unit": "m²"},
    {"match": ["barreira pára-vapor", "para-vapor", "membrana", "pare vapeur", "pare-vapeur", "membrane"], "label": "Barreira pára-vapor 75 m²", "base": 79.00, "unit": "rolo"},
    {"match": ["betão", "betao", "beton", "béton"], "label": "Betão pronto 35 kg", "base": 5.40, "unit": "saco"},
    {"match": ["cimento", "ciment"], "label": "Cimento CEM II 35 kg", "base": 8.90, "unit": "saco"},
    {"match": ["areia", "sable"], "label": "Areia 0/4 35 kg", "base": 3.60, "unit": "saco"},
    {"match": ["brita", "gravilha", "gravier"], "label": "Brita 4/20 35 kg", "base": 3.90, "unit": "saco"},
    {"match": ["malha sol", "malha eletrossoldada", "treillis"], "label": "Malha eletrossoldada AQ38 3x2 m", "base": 22.50, "unit": "painel"},
    {"match": ["soalho", "flutuante", "parquet"], "label": "Soalho flutuante laminado carvalho", "base": 18.90, "unit": "m²"},
    {"match": ["base de duche", "duche", "receveur", "douche"], "label": "Base de duche 90x90 extraplana", "base": 189.00, "unit": "u"},
    {"match": ["torneira", "misturadora", "robinet", "mitigeur"], "label": "Misturadora de lavatório cromada", "base": 79.00, "unit": "u"},
    {"match": ["sanita", "wc", "toilette"], "label": "Sanita suspensa com estrutura", "base": 289.00, "unit": "u"},
    {"match": ["janela", "fenetre", "fenêtre"], "label": "Janela PVC vidro duplo 120x100", "base": 349.00, "unit": "u"},
    {"match": ["porta", "porte"], "label": "Porta interior completa 80 cm", "base": 129.00, "unit": "u"},
    {"match": ["multicamada", "tubo", "per", "multicouche", "tube"], "label": "Tubo multicamada 16 mm 50 m", "base": 68.00, "unit": "rolo"},
    {"match": ["cabo", "tubo vd", "cable", "câble", "gaine"], "label": "Cabo XV 3G2,5 100 m", "base": 89.00, "unit": "rolo"},
    {"match": ["fita adesiva", "fita de pintor", "adhesif", "adhésif", "ruban"], "label": "Fita de pintor 50 m", "base": 4.20, "unit": "rolo"},
    {"match": ["plástico de proteção", "lona", "bache", "bâche"], "label": "Plástico de proteção 4x5 m", "base": 7.90, "unit": "u"},
    {"match": ["rolo", "rouleau"], "label": "Rolo de pintura + manga", "base": 12.50, "unit": "u"},
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
    return {"label": query.strip().title() or "Produto", "base": 24.90, "unit": "u"}


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
        stock = ["Em stock", "Em stock", "Stock limitado", "Por encomenda"][int(r * 4) % 4]
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
        "query": f'{query} preço € Portugal',
        "search_depth": "basic", "topic": "general", "max_results": min(20, limit * 2),
        "country": "portugal",
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
            "product": (item.get("title") or "Produto")[:180], "unit": "u",
            "price": price, "currency": "EUR", "shipping": sup["shipping"],
            "free_shipping_from": sup["free_from"], "min_order": sup["min_order"],
            "delivery_days": sup["delivery_days"], "stock": "A verificar",
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


def _catalog_match(catalog, name, query):
    """Cherche un prix réel du catalogue par correspondance de nom (insensible casse)."""
    if not catalog:
        return None
    hay = f"{name} {query}".lower()
    for c in catalog:
        key = (c.get("name") or "").lower().strip()
        if key and (key in hay or hay in key):
            return c
    return None


def optimize_cart(items: list[dict], catalog: list[dict] | None = None,
                  coefficient: float = 1.0) -> dict:
    """items: [{query, quantity}] -> comparaison mono-fournisseur vs multi-fournisseurs.
    Si `catalog` (prix réels de l'utilisateur) contient une correspondance, ce prix prime.
    `coefficient` : ajustement régional appliqué aux prix estimés (démo), pas au catalogue."""
    coef = coefficient if coefficient and 0.5 <= coefficient <= 2.0 else 1.0
    per_item = []
    for it in items:
        offers = demo_search(it["query"], len(SUPPLIERS))
        if coef != 1.0:
            for o in offers:
                o["price"] = round(o["price"] * coef, 2)
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
        cat = _catalog_match(catalog, entry["name"], entry["query"])
        if cat:
            price = round(float(cat.get("price") or 0), 2)
            cost = round(price * entry["quantity"], 2)
            lines.append({"name": entry["name"], "query": entry["query"], "quantity": entry["quantity"],
                          "unit_price": price, "supplier": cat.get("supplier") or "O meu catálogo",
                          "supplier_key": "catalog", "total": cost,
                          "unit": cat.get("unit") or entry["offers"][0]["unit"],
                          "stock": True, "url": None, "source": "catalog"})
            by_supplier.setdefault("catalog", 0.0)
            by_supplier["catalog"] += cost
            continue
        best = min(entry["offers"], key=lambda o: o["price"])
        cost = round(best["price"] * entry["quantity"], 2)
        lines.append({"name": entry["name"], "query": entry["query"], "quantity": entry["quantity"],
                      "unit_price": best["price"], "supplier": best["supplier"],
                      "supplier_key": best["supplier_key"], "total": cost, "unit": best["unit"],
                      "stock": best["stock"], "url": best["url"], "source": "demo"})
        by_supplier.setdefault(best["supplier_key"], 0.0)
        by_supplier[best["supplier_key"]] += cost

    multi_products = round(sum(lines_i["total"] for lines_i in lines), 2)
    multi_shipping = 0.0
    baskets = []
    for key, amount in by_supplier.items():
        s = SUPPLIERS_BY_KEY.get(key)
        if s is None:  # ligne issue du catalogue perso (aucun frais de port)
            baskets.append({"supplier": "O meu catálogo", "supplier_key": key,
                            "products": round(amount, 2), "shipping": 0.0,
                            "total": round(amount, 2), "below_min_order": False})
            continue
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
                "name": f"{s['name']} - loja {i + 1}", "distance_km": d,
                "lat": round(lat + uniform(-0.08, 0.08), 5),
                "lng": round(lng + uniform(-0.08, 0.08), 5),
                "open_now": uniform(0, 1) > 0.25, "source": "demo",
            })
    out.sort(key=lambda x: x["distance_km"])
    return out
