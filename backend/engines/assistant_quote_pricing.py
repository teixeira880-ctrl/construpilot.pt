"""Use existing tenant-owned / entitled shared catalogues without extra LLM calls."""
import math
import unicodedata
from uuid import uuid4

from fastapi import HTTPException

from core.db import db


def unit_key(unit):
    value = unicodedata.normalize("NFKC", str(unit or "")).lower().strip()
    return {"m^2": "m2", "m^3": "m3", "m": "ml", "mètre": "ml", "metre": "ml",
            "unité": "u", "unite": "u", "pièce": "u", "piece": "u", "pc": "u"}.get(value, value)


async def price_sources(user):
    from routes.plans_analysis import _build_index
    from routes.shared_library import (
        _is_pro_business,
        get_shared_items_for_level,
        resolve_price_level,
    )

    profile = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "price_library_mode": 1, "lang": 1, "brand_country": 1}) or {}
    mode = profile.get("price_library_mode") or "shared_first"
    company = await db.library_items.find({"user_id": user["user_id"]}, {
        "_id": 0, "item_id": 1, "designation": 1, "unit": 1, "unit_price_ht": 1,
        "source": 1, "updated_at": 1}).to_list(5000)
    sources = [("company_library", company)]
    if mode != "company_only" and await _is_pro_business(user):
        level = await resolve_price_level(user["user_id"])
        lang = "pt" if profile.get("lang") == "pt" or profile.get("brand_country") == "PT" else "pt"
        shared = await get_shared_items_for_level(level, lang=lang)
        sources.append((f"shared_library_{level}", shared))
    if mode == "shared_first":
        sources.reverse()
    result = [(name, _build_index(rows)) for name, rows in sources if rows]
    # A private quotation is not consent to share its text/prices with other accounts.
    # Only the owner's catalogue and the explicitly entitled shared catalogue are used.
    return result


def find_price(designation, unit, sources):
    from routes.plans_analysis import _candidates

    for source, index in sources:
        # Unit equality is stricter than the older 'count' family: no forfait/u substitution.
        candidates = [(score, item) for score, item in _candidates({"designation": designation, "unit": unit}, index, same_unit=False, k=30)
                      if unit_key(item.get("unit")) == unit_key(unit)]
        if not candidates or candidates[0][0] < 0.75:
            continue
        score, item = candidates[0]
        price = item.get("unit_price_ht")
        if not isinstance(price, (float, int)) or not math.isfinite(price) or not 0 <= price <= 100_000_000:
            continue
        # Ambiguous alternatives with similar scores and different prices are not silently selected.
        if len(candidates) > 1 and score - candidates[1][0] < 0.08 and price != candidates[1][1].get("unit_price_ht"):
            continue
        return {"unit_price_ht": price, "price_source": source, "price_estimated": True,
                "price_reference": item.get("item_id") or f"{source}:{item.get('designation', '')}",
                "price_reference_label": item.get("designation", "")}
    return None


async def build_lines(body, user, previous=None):
    from routes.plans_common import _resolve_branding
    branding = await _resolve_branding(user["user_id"])
    default_vat = 20 if str((branding or {}).get("country") or "").upper() == "FR" else 23
    sources = await price_sources(user) if any(l.price_origin == "library" for l in body.lines) else []
    old_lines = {(r.get("line_id") or f"legacy:{i}"): r for i, r in enumerate((previous or {}).get("lines", []))}
    seen = set()
    lines = []
    for item in body.lines:
        original = old_lines.get(item.line_id)
        if item.line_id is not None and (original is None or item.line_id in seen):
            raise HTTPException(422, "Identificador de linha desconhecido ou duplicado; reler o orçamento.")
        if item.line_id:
            seen.add(item.line_id)
        vat = item.vat_rate if item.vat_rate is not None else body.vat_rate
        row = {"line_id": item.line_id or "ql_" + uuid4().hex[:16], "designation": item.designation, "description": item.description, "qty": item.quantity if item.quantity is not None else 0,
               "unit": item.unit, "unit_price_ht": 0, "cost_price_ht": (original or {}).get("cost_price_ht", 0), "category": item.lot,
               "vat_rate": vat if vat is not None else default_vat, "vat_assumed": vat is None,
               "quantity_missing": item.quantity is None, "price_missing": False, "price_estimated": False,
               "price_reference": "", "price_reference_label": ""}
        if item.price_origin == "user":
            row.update(unit_price_ht=item.unit_price, price_source="user_input")
        elif item.price_origin == "estimate":
            row.update(unit_price_ht=item.unit_price, price_source="assistant_estimate", price_estimated=True,
                       price_reference_label="Preço médio estimado — a verificar")
        else:
            keep = original and original.get("price_estimated") and all(original.get(k) == row[k] for k in ("designation", "unit", "description", "category"))
            if item.price_origin == "library" and keep:
                match = {k: original.get(k) for k in ("unit_price_ht", "price_source", "price_estimated", "price_reference", "price_reference_label")}
            else:
                match = find_price(item.designation, item.unit, sources) if item.price_origin == "library" else None
            row.update(match or {"price_source": "unpriced", "price_missing": True})
        lines.append(row)
    return lines


# --- Lot 50 : filet de sécurité « catalogue ConstruPilot » ---
_CATALOG_KEYWORDS = [  # du plus spécifique au plus général ; mots sans accents, en minuscules
    ("salle_de_bain", ("salle de bain", "salle d'eau", "casa de banho", "instalacao sanitaria")),
    ("cuisine", ("cuisine", "cozinha")),
    ("menuiseries", ("fenetre", "porte-fenetre", "baie vitree", "menuiserie", "janela", "porta ", "caixilh")),
    ("ventilation", ("vmc", "ventilation", "ventilacao", "extracao")),
    ("dechets", ("dechet", "gravat", "benne", "evacuation", "entulho", "residuo")),
    ("demolition", ("demolition", "depose", "demoli", "remocao", "arrachage", "picagem")),
    ("placo", ("placo", "platre", "ba13", "cloison", "doublage", "faux plafond", "pladur", "gesso cartonado", "teto falso", "tecto falso")),
    ("isolation", ("isolation", "isolant", "laine de", "isolamento", "la de rocha", "la mineral")),
    ("peinture", ("peinture", "pintura")),
    ("carrelage", ("carrelage", "faience", "carreau", "gres cerame", "azulej", "ceramic", "porcelanico", "mosaico")),
    ("parquet", ("parquet", "sol souple", "vinyle", "stratifie", "lino", "soalho", "flutuante", "vinilico")),
    ("facade", ("facade", "ravalement", "enduit exterieur", "fachada", "capoto", "etics", "reboco exterior")),
    ("toiture", ("toiture", "couverture", "tuile", "telhado", "cobertura", "telha")),
    ("terrasse", ("terrasse", "terraco", "deck")),
    ("electricite", ("electricite", "electrique", "eletricidade", "eletrica")),
    ("plomberie", ("plomberie", "canalizacao", "canalisation")),
    ("chauffage", ("chauffage", "aquecimento")),
    ("climatisation", ("climatisation", "climatizacao", "ar condicionado")),
    ("maconnerie", ("maconnerie", "parpaing", "agglo", "alvenaria", "tijolo")),
    ("terrassement", ("terrassement", "fouille", "deblai", "escavacao", "movimento de terras")),
    ("fondations", ("fondation", "semelle", "sapata", "fundac")),
]


def _norm_txt(s):
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return " " + "".join(c for c in s if not unicodedata.combining(c)) + " "


def catalog_price(designation, unit, lot=""):
    """Prix « fourniture + pose, gamme standard » du catalogue ConstruPilot si le métier ET l'unité correspondent."""
    from engines.catalog import LOTS_BY_KEY
    text = _norm_txt(f"{designation} {lot}")
    for key, words in _CATALOG_KEYWORDS:
        if not any(w in text for w in words):
            continue
        item = LOTS_BY_KEY.get(key)
        if not item or unit_key(item.get("unit")) != unit_key(unit):
            continue
        price = round(float(item.get("mat_std", 0)) + float(item.get("labour", 0)), 2)
        if price <= 0:
            continue
        return {"unit_price_ht": price, "price_source": "construpilot_catalog", "price_estimated": True,
                "price_missing": False, "price_reference": f"catalog:{key}",
                "price_reference_label": 'Preço do catálogo ConstruPilot (fornecimento + aplicação, gama standard) — a verificar'}
    return None


_build_lines_lot50_base = build_lines


async def build_lines(body, user, previous=None):
    lines = await _build_lines_lot50_base(body, user, previous)
    for item, row in zip(body.lines, lines):
        if item.price_origin == "library" and row.get("price_missing"):
            match = catalog_price(row.get("designation"), row.get("unit"), row.get("category", ""))
            if match:
                row.update(match)
    return lines


# --- Lot 62 : même famille de travail entre la ligne et l'article de bibliothèque ---
_DEMOL_WORDS = ("demoli", "demol", "remoc", "remocao", "remover", "picagem", "levantamento de", "arranque",
                "depose", "arrachage", "enlevement", "curage", "decroutage")
_SITE_WORDS = ("estaleiro", "installation de chantier", "repli de chantier", "base vie", "base de vida")


def _work_family(text):
    t = " " + "".join(c for c in unicodedata.normalize("NFKD", str(text or "").lower())
                      if not unicodedata.combining(c)) + " "
    if any(w in t for w in _SITE_WORDS):
        return "site"
    if any(w in t for w in _DEMOL_WORDS):
        return "demolition"
    return "work"


_find_price_lot62_base = find_price


def find_price(designation, unit, sources):
    match = _find_price_lot62_base(designation, unit, sources)
    if match and _work_family(designation) != _work_family(match.get("price_reference_label")):
        return None
    return match


# --- Lote 65 : coefficient pays/região sur le prix catalogue (catalogue = prix France) ---
_catalog_price_lot65_base = catalog_price


def catalog_price(designation, unit, lot=""):
    m = _catalog_price_lot65_base(designation, unit, lot)
    if not m:
        return m
    try:
        from engines.estimation import region_coef
        coef = float(region_coef("PT", None))
    except Exception:  # noqa: BLE001
        coef = 0.68
    if 0 < coef < 1.5:
        m = dict(m)
        m["unit_price_ht"] = round(float(m["unit_price_ht"]) * coef, 2)
        m["price_reference_label"] = (m.get("price_reference_label") or "") + f" · coeficiente Portugal {coef:g}"
    return m
