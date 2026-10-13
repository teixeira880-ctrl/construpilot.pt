"""Imputation de l'acompte déjà versé sur les factures d'avancement (situations).

Règle retenue : on n'impute que l'acompte **réellement encaissé** (paiements
enregistrés sur la facture d'acompte). L'acompte facturé mais non payé est
affiché à titre d'information mais jamais déduit.
"""
from __future__ import annotations

from core.db import db

MODES = ("none", "prorata", "full", "manual")


def _ht_by_rate(lines: list) -> dict[float, float]:
    res: dict[float, float] = {}
    for ln in lines or []:
        rate = float(ln.get("vat_rate") or 0)
        res[rate] = round(res.get(rate, 0) + (ln.get("qty") or 0) * (ln.get("unit_price_ht") or 0), 2)
    return res


async def deposit_state(user_id: str, marche_id: str) -> dict:
    """Acompte lié à un marché : facturé, encaissé, déjà imputé, disponible."""
    invs = await db.pro_documents.find(
        {"user_id": user_id, "doc_type": "invoice", "source": "deposit",
         "$or": [{"source_quote_id": marche_id}, {"parent_doc_id": marche_id}]},
        {"_id": 0, "doc_id": 1, "number": 1, "lines": 1, "totals": 1, "paid": 1,
         "status": 1}).to_list(50)

    invoiced_ht = invoiced_ttc = paid_ttc = 0.0
    paid_ht = 0.0
    paid_by_rate: dict[float, float] = {}
    for inv in invs:
        t = inv.get("totals") or {}
        ht, ttc = float(t.get("ht") or 0), float(t.get("ttc") or 0)
        paid = float(inv.get("paid") or 0)
        if inv.get("status") == "paid" and paid <= 0:
            paid = ttc
        paid = max(0.0, min(paid, ttc))
        invoiced_ht += ht
        invoiced_ttc += ttc
        paid_ttc += paid
        ratio = (paid / ttc) if ttc else 0.0
        paid_ht += round(ht * ratio, 2)
        for rate, rht in _ht_by_rate(inv.get("lines")).items():
            paid_by_rate[rate] = round(paid_by_rate.get(rate, 0) + rht * ratio, 2)

    used = await db.pro_documents.find(
        {"user_id": user_id, "deposit_imputed_ht": {"$gt": 0},
         "$or": [{"source_quote_id": marche_id}, {"marche_id": marche_id}]},
        {"_id": 0, "deposit_imputed_ht": 1}).to_list(500)
    imputed_ht = round(sum(float(u.get("deposit_imputed_ht") or 0) for u in used), 2)

    paid_ht = round(paid_ht, 2)
    return {
        "invoices": [{"doc_id": i["doc_id"], "number": i.get("number"),
                      "ttc": (i.get("totals") or {}).get("ttc", 0),
                      "paid": float(i.get("paid") or 0), "status": i.get("status")} for i in invs],
        "invoiced_ht": round(invoiced_ht, 2), "invoiced_ttc": round(invoiced_ttc, 2),
        "paid_ttc": round(paid_ttc, 2), "paid_ht": paid_ht,
        "paid_by_rate": paid_by_rate,
        "imputed_ht": imputed_ht,
        "available_ht": round(max(0.0, paid_ht - imputed_ht), 2),
        "unpaid_ttc": round(max(0.0, invoiced_ttc - paid_ttc), 2),
    }


def imputation_amount(mode: str, state: dict, cumul_ratio: float,
                      works_ht: float, manual_ht: float = 0.0) -> float:
    """Montant HT d'acompte à déduire sur cette situation.

    - prorata : l'acompte est résorbé au rythme de l'avancement cumulé du marché
    - full    : tout le solde d'acompte disponible est imputé maintenant
    - manual  : montant saisi, plafonné au disponible
    Jamais plus que le disponible, jamais plus que les travaux de la situation.
    """
    avail = float(state.get("available_ht") or 0)
    if mode == "none" or avail <= 0 or works_ht <= 0:
        return 0.0
    if mode == "full":
        want = avail
    elif mode == "manual":
        want = max(0.0, float(manual_ht or 0))
    else:
        target = round(float(state.get("paid_ht") or 0) * max(0.0, min(cumul_ratio, 1.0)), 2)
        want = target - float(state.get("imputed_ht") or 0)
    return round(max(0.0, min(want, avail, works_ht)), 2)


def deduction_lines(amount_ht: float, state: dict, label_suffix: str = "") -> list[dict]:
    """Lignes négatives « acompte déduit », réparties par taux de TVA de l'acompte."""
    if amount_ht <= 0:
        return []
    by_rate = {float(k): float(v) for k, v in (state.get("paid_by_rate") or {}).items() if float(v) > 0}
    if not by_rate:
        by_rate = {10.0: amount_ht}
    total = round(sum(by_rate.values()), 2) or 1
    multi = len(by_rate) > 1
    lines, allocated = [], 0.0
    items = sorted(by_rate.items())
    for i, (rate, base) in enumerate(items):
        part = round(amount_ht * base / total, 2)
        if i == len(items) - 1:
            part = round(amount_ht - allocated, 2)
        allocated = round(allocated + part, 2)
        if part <= 0:
            continue
        desig = "Acompte déjà versé — déduction"
        if label_suffix:
            desig += f" {label_suffix}"
        if multi:
            desig += f" — TVA {rate:g}%"
        lines.append({"designation": desig, "description": "", "unit": "forfait", "qty": 1,
                      "unit_price_ht": -part, "vat_rate": rate, "category": "Acompte déduit"})
    return lines
