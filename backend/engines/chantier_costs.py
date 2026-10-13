"""Budget, engagements et prévision explicite. Une donnée manquante n'est pas un zéro."""
from __future__ import annotations

import math
from fastapi import HTTPException
from core.db import db
from engines.chantier_scope import labor_scope, purchase_scope

ENGAGED = {"envoyé", "envoye", "sent", "confirmé", "confirme", "confirmed", "delivered", "livré"}
EXCLUDED_QUOTES = {"cancelled", "refused", "rejected", "archived"}


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) and abs(n) <= 1e12 else None
    except (TypeError, ValueError):
        return None


def item_amount(item):
    if item.get("price_missing") or item.get("price_source") in ("—", "unpriced", "missing"):
        return None
    # Recorded line totals refer to the supplier's billing unit. Do not multiply them again.
    for key in ("line_total", "total"):
        if item.get(key) is not None:
            n = number(item[key])
            return n if n is not None and n >= 0 else None
    price = number(item.get("unit_price") if item.get("unit_price") is not None else item.get("price"))
    quantity = item.get("priced_qty")
    if quantity is None:
        quantity = item.get("commandable_qty") if item.get("commandable_qty") is not None else item.get("qty")
    qty = number(quantity)
    return round(price * qty, 2) if price is not None and qty is not None and price >= 0 and qty >= 0 else None


def supplier_name(order):
    supplier = order.get("supplier")
    return (supplier.get("name") or supplier.get("company") or "Fournisseur") if isinstance(supplier, dict) else (supplier or "Fournisseur")


def _lot(category) -> str:
    """Normalise une catégorie de ligne de devis en nom de lot."""
    return (category or "").strip() or "Autres"


async def bounded(collection, query, limit):
    rows = await collection.find(query, {"_id": 0, "frozen_pdf_b64": 0, "facturx_pdf_b64": 0}).to_list(limit + 1)
    if len(rows) > limit:
        raise HTTPException(422, "Dossier trop volumineux pour ce calcul : réduisez le périmètre, aucun total partiel n'a été présenté")
    return rows


async def compute_chantier_costs(chantier: dict, user_id: str, labor_rate: float | None = None) -> dict:
    cid = chantier["chantier_id"]
    settings = chantier.get("cost_settings") or {}
    rate = number(labor_rate if labor_rate is not None else settings.get("labor_rate"))
    if labor_rate is not None and (rate is None or rate < 0 or rate > 10000):
        raise HTTPException(422, "Taux horaire invalide")
    quotes = await bounded(db.pro_documents, {"user_id": user_id, "chantier_id": cid, "doc_type": "quote", "trashed_at": None}, 300)
    quotes = [q for q in quotes if q.get("status") not in EXCLUDED_QUOTES]
    signed = [q for q in quotes if q.get("status") == "signed" or q.get("signed") is True]
    selected = settings.get("quote_ids")
    invalid_selection = selected is not None and not set(selected).issubset({q["doc_id"] for q in quotes})
    ambiguous = selected is None and len(signed or quotes) > 1
    scope = [q for q in quotes if q["doc_id"] in selected] if selected is not None else ([] if ambiguous else signed or quotes)
    if invalid_selection:
        scope = []
    lots, invalid_lines = {}, 0
    for q in scope:
        for ln in q.get("lines") or []:
            if ln.get("kind", "line") != "line" or not (ln.get("designation") or "").strip():
                continue
            lot = (ln.get("category") or "").strip() or "Autres"
            g = lots.setdefault(lot, {"lot": lot, "vente_ht": 0.0, "cost_prev_ht": 0.0, "known": 0, "total": 0, "valid_sales": True})
            g["total"] += 1
            qty, pu, discount = number(ln.get("qty")), number(ln.get("unit_price_ht")), number(ln.get("discount_pct", 0))
            if ln.get("price_missing") or ln.get("quantity_missing") or qty is None or pu is None or discount is None or not 0 <= discount <= 100:
                invalid_lines += 1
                g["valid_sales"] = False
                continue
            g["vente_ht"] += round(qty * pu * (1 - discount / 100), 2)
            cost = number(ln.get("cost_price_ht"))
            if cost is not None and (cost > 0 or (cost == 0 and ln.get("cost_confirmed_zero") is True)):
                g["known"] += 1
                g["cost_prev_ht"] += round(qty * cost, 2)

    def margin(sale, cost, complete):
        m = round(sale - cost, 2) if complete else None
        return {"margin_ht": m, "margin_pct": round(m / sale * 100, 1) if m is not None and sale > 0 else None,
                "markup_pct": round(m / cost * 100, 1) if m is not None and cost > 0 else None}

    rows = []
    for lot, g in lots.items():
        complete = g["known"] == g["total"] and g["valid_sales"]
        rows.append({"lot": lot, "vente_ht": round(g["vente_ht"], 2) if g["valid_sales"] else None,
                     "cost_prev_ht": round(g["cost_prev_ht"], 2) if g["known"] else None,
                     "coverage": {"known": g["known"], "total": g["total"], "complete": complete},
                     **margin(g["vente_ht"], g["cost_prev_ht"], complete)})
    rows.sort(key=lambda r: -(r["vente_ht"] or 0))
    known, total = sum(g["known"] for g in lots.values()), sum(g["total"] for g in lots.values())
    sale, cost = sum(g["vente_ht"] for g in lots.values()), sum(g["cost_prev_ht"] for g in lots.values())
    budget_valid = bool(scope) and not invalid_lines
    complete = budget_valid and total > 0 and known == total
    totals = {"vente_ht": round(sale, 2) if budget_valid else None, "cost_prev_ht": round(cost, 2) if known else None,
              "coverage": {"known": known, "total": total, "complete": complete}, **margin(sale, cost, complete)}

    timesheets = await bounded(db.hr_timesheets, await labor_scope(db, chantier, user_id), 2000)
    hours_valid = hours_all = 0.0
    invalid_hours = pending_hours = 0
    lot_hours, labor_entries = {}, []
    for t in timesheets:
        h = number(t.get("hours"))
        if t.get("status") == "rejected":
            continue
        valid = h is not None and h >= 0
        if not valid and t.get("status") == "validated":
            invalid_hours += 1
        hours_all += h if valid else 0
        if t.get("status") == "validated" and valid:
            hours_valid += h
            lot = t.get("lot") or "__none__"
            lot_hours[lot] = lot_hours.get(lot, 0) + h
        elif t.get("status") != "validated":
            pending_hours += 1
        labor_entries.append({"entry_id": t.get("entry_id"), "worker_name": t.get("worker_name") or "—",
                              "date": str(t.get("clock_in") or "")[:10], "hours": round(h, 2) if valid else None,
                              "status": t.get("status"), "lot": t.get("lot")})
    labor_complete = not invalid_hours and not pending_hours and (hours_valid == 0 or rate is not None and rate > 0)
    labor_cost = round(hours_valid * rate, 2) if rate is not None and rate > 0 else (0 if hours_valid == 0 else None)
    labor = {"hours_validated": round(hours_valid, 2), "hours_total": round(hours_all, 2), "entries": len(labor_entries),
             "rate_used": rate, "cost_est": labor_cost, "complete": labor_complete, "pending_entries": pending_hours}

    purchase_query = await purchase_scope(db, chantier, user_id)
    linked_plan_ids = {pid for clause in purchase_query["$or"] for pid in clause.get("plan_ids", {}).get("$in", [])}
    orders = await bounded(db.material_orders, purchase_query, 200)
    priced_total = 0.0
    items_count = unpriced = engaged_count = ambiguous_orders = 0
    lot_purch, purchase_entries = {}, []
    for o in orders:
        engaged = o.get("status") in ENGAGED
        allocation_required = not o.get("chantier_id") and bool(set(o.get("plan_ids") or []) - linked_plan_ids)
        ambiguous_orders += allocation_required
        amounts = [None if allocation_required else item_amount(it) for it in o.get("items") or []]
        o_priced = bool(amounts) and all(a is not None for a in amounts)
        amount = round(sum(a for a in amounts if a is not None), 2)
        if engaged:
            engaged_count += 1
            items_count += len(amounts)
            unpriced += sum(a is None for a in amounts) + (not amounts)
            priced_total += amount
            lot = o.get("lot") or "__none__"
            g = lot_purch.setdefault(lot, {"amount": 0, "complete": True})
            g["amount"] += amount
            g["complete"] = g["complete"] and o_priced
        purchase_entries.append({"order_id": o["order_id"], "supplier": supplier_name(o), "items": len(amounts),
                                 "amount": amount if o_priced else None, "known_amount": amount, "engaged": engaged, "allocation_required": allocation_required,
                                 "status": o.get("status"), "lot": o.get("lot"), "delivery": o.get("delivery") or {},
                                 "delivery_version": o.get("delivery_version", 0)})
    purchases = {"orders": engaged_count, "all_orders": len(orders), "items": items_count,
                 "unpriced_items": unpriced, "complete": unpriced == 0, "priced_total": round(priced_total, 2)}
    for row in rows:
        h = lot_hours.get(row["lot"], 0)
        lp = lot_purch.get(row["lot"], {"amount": 0, "complete": True})
        lc = round(h * rate, 2) if rate is not None and rate > 0 else (0 if h == 0 else None)
        row.update(real_hours=round(h, 2), real_labor_ht=lc, real_purchases_ht=round(lp["amount"], 2),
                   real_cost_ht=round(lc + lp["amount"], 2) if lc is not None and lp["complete"] else None)
    real_known = round((labor_cost or 0) + priced_total, 2)
    remaining = number(settings.get("remaining_cost_ht"))
    forecast_ready = budget_valid and labor_complete and unpriced == 0 and remaining is not None and remaining >= 0
    final_cost = round(real_known + remaining, 2) if forecast_ready else None
    notes = []
    if ambiguous or invalid_selection:
        notes.append("Choisissez les devis à cumuler dans le budget : les versions et variantes ne sont jamais additionnées automatiquement.")
    if not complete and total:
        notes.append(f"{total - known} ligne(s) sans coût de revient vérifiable ; marge prévisionnelle indisponible.")
    if invalid_lines:
        notes.append("Des lignes contiennent des valeurs invalides : le total de vente est indisponible.")
    if not signed and scope:
        notes.append("Budget indicatif : aucun devis signé dans le dossier.")
    if not labor_complete:
        notes.append("Main d'œuvre incomplète : vérifier le taux horaire et les pointages en attente ou invalides.")
    if ambiguous_orders:
        notes.append("Une commande regroupe plusieurs dossiers : rattachez-la explicitement au dossier qui en porte le coût. Aucun montant commun n’est additionné automatiquement.")
    if unpriced:
        notes.append(f"{unpriced} ligne(s) ou commande(s) engagée(s) sans prix vérifiable.")
    notes.append("Coûts enregistrés = heures validées + commandes envoyées/confirmées. Les brouillons sont exclus. Le reste à engager doit exclure ces commandes, même non livrées.")
    return {"chantier_id": cid, "chantier_name": chantier.get("name"),
            "scope": {"quotes": len(quotes), "signed": len(signed), "using_signed_only": bool(scope) and all(q in signed for q in scope),
                      "selection_required": ambiguous or invalid_selection, "selected_ids": [q["doc_id"] for q in scope],
                      "available_quotes": [{"doc_id": q["doc_id"], "label": q.get("number") or q.get("title") or q["doc_id"], "status": q.get("status")} for q in quotes]},
            "budget_by_lot": rows, "totals": totals, "labor": labor, "purchases": purchases,
            "unaffected": {"labor_hours": round(lot_hours.get("__none__", 0), 2), "labor_cost": None,
                           "purchases_ht": round(lot_purch.get("__none__", {}).get("amount", 0), 2)},
            "labor_entries": labor_entries, "purchase_entries": purchase_entries, "lots": [r["lot"] for r in rows],
            "real_cost_known_ht": real_known, "cost_settings": settings, "cost_version": chantier.get("cost_version", 0),
            "forecast": {"complete": forecast_ready, "remaining_cost_ht": remaining, "final_cost_ht": final_cost,
                         "margin_ht": round(sale - final_cost, 2) if forecast_ready else None,
                         "over_budget_ht": round(final_cost - cost, 2) if forecast_ready and complete else None,
                         "basis": "engagements enregistrés + reste à engager renseigné", "inventory_complete": False}, "notes": notes}
