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
            raise HTTPException(422, "Identifiant de ligne inconnu ou dupliqué ; relire le devis.")
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
                       price_reference_label="Prix moyen estimé — à vérifier")
        else:
            keep = original and original.get("price_estimated") and all(original.get(k) == row[k] for k in ("designation", "unit", "description", "category"))
            if item.price_origin == "library" and keep:
                match = {k: original.get(k) for k in ("unit_price_ht", "price_source", "price_estimated", "price_reference", "price_reference_label")}
            else:
                match = find_price(item.designation, item.unit, sources) if item.price_origin == "library" else None
            row.update(match or {"price_source": "unpriced", "price_missing": True})
        lines.append(row)
    return lines
