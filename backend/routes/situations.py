"""Facturation à l'avancement — situations de travaux (pack Business).

Une « situation » facture l'avancement cumulé d'un marché (devis/facture de
référence) : par ligne, un % d'avancement cumulé ; la situation facture le delta
depuis la situation précédente. Retenue de garantie optionnelle (retenue sur le
paiement, pas une remise → montant plein facturé, net à payer réduit).
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from routes.documents import _compute_totals, _next_number, _now, _client_snapshot

router = APIRouter(prefix="/situations", tags=["situations"])


def _uid(u):
    return u["user_id"]


async def _base_doc(marche_id: str, user: dict) -> dict:
    doc = await db.pro_documents.find_one(
        {"doc_id": marche_id, "user_id": _uid(user)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Marché introuvable")
    if not (doc.get("lines") or []):
        raise HTTPException(400, "Ce document n'a aucune ligne à facturer")
    return doc


@router.get("/marches")
async def list_marches(user=Depends(current_user)):
    """Devis & factures pouvant servir de base à des situations."""
    docs = await db.pro_documents.find(
        {"user_id": _uid(user), "doc_type": {"$in": ["quote", "invoice"]},
         "is_situation": {"$ne": True}},
        {"_id": 0, "doc_id": 1, "number": 1, "title": 1, "doc_type": 1,
         "client": 1, "totals": 1, "lines": 1}).sort("created_at", -1).to_list(500)
    out = []
    for d in docs:
        if not (d.get("lines") or []):
            continue
        out.append({"doc_id": d["doc_id"], "number": d.get("number"),
                    "title": d.get("title"), "doc_type": d.get("doc_type"),
                    "client": d.get("client"), "lines_count": len(d["lines"]),
                    "total_ht": (d.get("totals") or {}).get("ht", 0)})
    return out


@router.get("")
async def list_situations(marche_id: str = "", user=Depends(current_user)):
    q = {"user_id": _uid(user)}
    if marche_id:
        q["marche_id"] = marche_id
    return await db.situations.find(q, {"_id": 0}).sort("seq", 1).to_list(500)


class SitLineIn(BaseModel):
    idx: int
    pct: float = Field(ge=0, le=100)


class SituationIn(BaseModel):
    marche_id: str
    lines: list[SitLineIn]
    retention_pct: float = Field(default=0, ge=0, le=10)


@router.post("")
async def create_situation(body: SituationIn, user=Depends(current_user)):
    base = await _base_doc(body.marche_id, user)
    base_lines = base.get("lines") or []
    pct_map = {l.idx: l.pct for l in body.lines}

    # % cumulé précédent par ligne = celui de la dernière situation du marché.
    prev = await db.situations.find(
        {"user_id": _uid(user), "marche_id": body.marche_id},
        {"_id": 0, "seq": 1, "cumul_pct": 1}).sort("seq", -1).to_list(1)
    prev_pct: dict = {}
    if prev:
        prev_pct = {int(k): float(v) for k, v in (prev[0].get("cumul_pct") or {}).items()}
    seq = (prev[0]["seq"] + 1) if prev else 1

    sit_lines, inv_lines, cumul_map = [], [], {}
    for i, bl in enumerate(base_lines):
        contract_ht = round((bl.get("qty") or 0) * (bl.get("unit_price_ht") or 0), 2)
        cum = float(pct_map.get(i, prev_pct.get(i, 0)))
        pv = float(prev_pct.get(i, 0))
        if cum < pv:
            cum = pv  # l'avancement ne peut pas régresser
        delta = round(cum - pv, 2)
        sit_ht = round(contract_ht * delta / 100, 2)
        cumul_map[str(i)] = cum
        sit_lines.append({"idx": i, "designation": bl.get("designation", ""),
                          "contract_ht": contract_ht, "prev_pct": pv, "cumul_pct": cum,
                          "delta_pct": delta, "situation_ht": sit_ht,
                          "vat_rate": bl.get("vat_rate", 10), "unit": bl.get("unit", "u")})
        if sit_ht > 0:
            inv_lines.append({
                "designation": f"{bl.get('designation', '')} — avancement {delta:g}% (cumul {cum:g}%)",
                "unit": "u", "qty": 1, "unit_price_ht": sit_ht,
                "vat_rate": bl.get("vat_rate", 10), "category": f"Situation n°{seq}"})

    if not inv_lines:
        raise HTTPException(400, "Aucun avancement à facturer (delta nul sur toutes les lignes)")

    totals = _compute_totals(inv_lines, 0)
    retention_amount = round(totals["ht"] * (body.retention_pct or 0) / 100, 2)
    net_due = round(totals["ttc"] - retention_amount, 2)
    marche_label = base.get("number") or base.get("title") or base["doc_id"]

    note = f"Situation de travaux n°{seq} — marché {marche_label}."
    if retention_amount:
        note += (f" Retenue de garantie {body.retention_pct:g}% : -{retention_amount:.2f} € · "
                 f"Net à payer : {net_due:.2f} € TTC.")

    number = await _next_number(_uid(user), "invoice")
    inv = {
        "doc_id": "doc_" + secrets.token_hex(6), "user_id": _uid(user),
        "doc_type": "invoice", "number": number,
        "title": f"Situation n°{seq} — {base.get('title') or marche_label}",
        "client_id": base.get("client_id"),
        "client": await _client_snapshot(base.get("client_id"), user) or base.get("client"),
        "status": "draft", "lines": inv_lines, "notes": note,
        "payment_terms": base.get("payment_terms", ""), "deposit_pct": 0,
        "totals": totals, "issue_date": _now(), "due_date": None,
        "source": "situation", "is_situation": True, "marche_id": body.marche_id,
        "situation_seq": seq, "retention_pct": body.retention_pct or 0,
        "retention_amount": retention_amount, "net_due": net_due,
        "created_at": _now(), "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(inv))
    inv.pop("_id", None)

    sit = {
        "situation_id": "sit_" + secrets.token_hex(6), "user_id": _uid(user),
        "marche_id": body.marche_id, "marche_label": marche_label, "seq": seq,
        "lines": sit_lines, "cumul_pct": cumul_map,
        "total_ht": totals["ht"], "total_ttc": totals["ttc"],
        "retention_pct": body.retention_pct or 0, "retention_amount": retention_amount,
        "net_due": net_due, "invoice_doc_id": inv["doc_id"],
        "invoice_number": number, "created_at": _now(),
    }
    await db.situations.insert_one(dict(sit))
    sit.pop("_id", None)
    return sit


@router.delete("/{situation_id}")
async def delete_situation(situation_id: str, user=Depends(current_user)):
    sit = await db.situations.find_one(
        {"situation_id": situation_id, "user_id": _uid(user)}, {"_id": 0})
    if not sit:
        raise HTTPException(404, "Situation introuvable")
    await db.situations.delete_one({"situation_id": situation_id, "user_id": _uid(user)})
    if sit.get("invoice_doc_id"):
        await db.pro_documents.delete_one(
            {"doc_id": sit["invoice_doc_id"], "user_id": _uid(user)})
    return {"ok": True}
