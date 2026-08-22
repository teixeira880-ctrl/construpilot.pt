"""Chiffrage générique d'un bordereau d'approvisionnement.

Source des prix unitaires (par priorité) :
  1. override manuel saisi par l'utilisateur
  2. catalogue de prix du fournisseur (supplier.price_list)
  3. bibliothèque de prix DPGF de l'entreprise (company_price_libraries)
  4. 0 (à compléter manuellement)
"""
import re
import unicodedata


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9 ]", " ", s.lower())


def _tokens(s: str) -> set:
    return {t for t in _norm(s).split() if len(t) > 2}


def _match_price(designation: str, catalog: list[dict]) -> tuple[float, str] | None:
    """Retourne (prix, libellé source) via recouvrement de mots-clés le plus fort."""
    dt = _tokens(designation)
    if not dt:
        return None
    best, best_score = None, 0
    for row in catalog:
        label = row.get("label") or row.get("designation") or ""
        price = row.get("price") if row.get("price") is not None else row.get("unit_price")
        try:
            price = float(price)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        rt = _tokens(label)
        if not rt:
            continue
        score = len(dt & rt)
        if score > best_score:
            best_score, best = score, (price, label)
    return best if best_score >= 1 else None


def price_items(items: list[dict], supplier: dict | None, dpgf: list[dict],
                overrides: dict | None = None) -> dict:
    """Chiffre chaque ligne. `overrides` = { index(str|int): prix }.

    Utilise commandable_qty si présent, sinon qty, pour le total ligne.
    """
    ov = {str(k): v for k, v in (overrides or {}).items()}
    supplier_cat = (supplier or {}).get("price_list") or []
    out = []
    grand_total = 0.0
    for i, it in enumerate(items):
        qty = it.get("commandable_qty")
        if qty in (None, ""):
            qty = it.get("qty") or 0
        try:
            qty = float(qty)
        except (TypeError, ValueError):
            qty = 0.0
        unit_price, source = 0.0, "—"
        if str(i) in ov and ov[str(i)] not in (None, ""):
            try:
                unit_price, source = float(ov[str(i)]), "manuel"
            except (TypeError, ValueError):
                pass
        if unit_price <= 0:
            m = _match_price(it.get("designation", ""), supplier_cat)
            if m:
                unit_price, source = m[0], "fournisseur"
        if unit_price <= 0:
            m = _match_price(it.get("designation", ""), dpgf)
            if m:
                unit_price, source = m[0], "DPGF"
        line_total = round(unit_price * qty, 2)
        grand_total += line_total
        out.append({**it, "priced_qty": qty, "unit_price": round(unit_price, 2),
                    "line_total": line_total, "price_source": source})
    return {"items": out, "grand_total": round(grand_total, 2)}
