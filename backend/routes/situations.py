"""Facturation à l'avancement — situations de travaux (pack Business).

Une « situation » facture l'avancement cumulé d'un marché (devis/facture de
référence) : par ligne, un % d'avancement cumulé ; la situation facture le delta
depuis la situation précédente. Retenue de garantie optionnelle (retenue sur le
paiement, pas une remise → montant plein facturé, net à payer réduit).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from routes.documents import _compute_totals, _next_number, _now, _client_snapshot
from engines import emailer, activity

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
    await activity.log(user, "situation.create", "situation",
                       f"Situation n°{seq} — {marche_label}",
                       {"invoice_number": number, "total_ttc": totals["ttc"]})
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


@router.get("/{situation_id}/pdf")
async def situation_pdf(situation_id: str, user=Depends(current_user)):
    """Décompte de situation PDF (format maîtrise d'œuvre)."""
    from fastapi import Response
    from engines.situation_pdf import build_situation_pdf
    from routes.plans_common import _resolve_branding
    sit = await db.situations.find_one(
        {"situation_id": situation_id, "user_id": _uid(user)}, {"_id": 0})
    if not sit:
        raise HTTPException(404, "Situation introuvable")
    base = await db.pro_documents.find_one(
        {"doc_id": sit.get("marche_id"), "user_id": _uid(user)}, {"_id": 0, "client": 1})
    branding = await _resolve_branding(user["user_id"])
    pdf = build_situation_pdf(sit, branding, (base or {}).get("client"))
    fname = f"situation-{sit.get('seq')}-{sit.get('invoice_number') or situation_id}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
# ─────────────────────────  1. Avancement cumulé (dashboard marché)  ─────────────────────────

@router.get("/summary")
async def marche_summary(marche_id: str, user=Depends(current_user)):
    base = await _base_doc(marche_id, user)
    base_lines = base.get("lines") or []
    sits = await db.situations.find(
        {"user_id": _uid(user), "marche_id": marche_id}, {"_id": 0}).sort("seq", 1).to_list(500)
    last = sits[-1] if sits else None
    cumul = {int(k): float(v) for k, v in (last.get("cumul_pct") or {}).items()} if last else {}

    lines, total_contract, total_billed = [], 0.0, 0.0
    for i, bl in enumerate(base_lines):
        contract = round((bl.get("qty") or 0) * (bl.get("unit_price_ht") or 0), 2)
        pct = cumul.get(i, 0)
        billed = round(contract * pct / 100, 2)
        total_contract += contract
        total_billed += billed
        lines.append({"designation": bl.get("designation", f"Lot {i+1}"),
                      "contract_ht": contract, "cumul_pct": pct,
                      "billed_ht": billed, "remaining_ht": round(contract - billed, 2)})

    retention_held = round(sum(s.get("retention_amount", 0) for s in sits), 2)
    total_ttc = round(sum(s.get("total_ttc", 0) for s in sits), 2)
    return {
        "marche": {"doc_id": base["doc_id"], "number": base.get("number"),
                   "title": base.get("title"), "client": base.get("client"),
                   "reception_date": base.get("reception_date"),
                   "retention_released": base.get("retention_released", False)},
        "lines": lines,
        "totals": {
            "contract_ht": round(total_contract, 2),
            "billed_ht": round(total_billed, 2),
            "remaining_ht": round(total_contract - total_billed, 2),
            "pct_global": round(total_billed / total_contract * 100, 1) if total_contract else 0,
            "situations_count": len(sits),
            "billed_ttc": total_ttc,
            "retention_held": retention_held,
        },
        "situations": [{"seq": s["seq"], "invoice_number": s.get("invoice_number"),
                        "total_ttc": s.get("total_ttc"), "retention_amount": s.get("retention_amount"),
                        "created_at": s.get("created_at")} for s in sits],
    }


# ─────────────────────────  2. Retenue de garantie (levée à 1 an)  ─────────────────────────

class ReceptionIn(BaseModel):
    reception_date: str  # YYYY-MM-DD


def _plus_one_year(date_str: str) -> str:
    try:
        d = datetime.fromisoformat(date_str[:10])
        return d.replace(year=d.year + 1).date().isoformat()
    except Exception:
        return ""


@router.post("/{marche_id}/reception")
async def set_reception(marche_id: str, body: ReceptionIn, user=Depends(current_user)):
    base = await _base_doc(marche_id, user)
    release_due = _plus_one_year(body.reception_date)
    await db.pro_documents.update_one(
        {"doc_id": marche_id, "user_id": _uid(user)},
        {"$set": {"reception_date": body.reception_date[:10],
                  "retention_release_due": release_due,
                  "retention_released": base.get("retention_released", False)}})
    return {"reception_date": body.reception_date[:10], "retention_release_due": release_due}


@router.get("/retentions")
async def list_retentions(user=Depends(current_user)):
    """Retenues de garantie détenues par marché, avec échéance de libération (réception + 1 an)."""
    pipeline = [
        {"$match": {"user_id": _uid(user), "retention_amount": {"$gt": 0}}},
        {"$group": {"_id": "$marche_id", "held": {"$sum": "$retention_amount"},
                    "label": {"$first": "$marche_label"}}},
    ]
    groups = await db.situations.aggregate(pipeline).to_list(500)
    today = datetime.now(timezone.utc).date().isoformat()
    out = []
    for g in groups:
        base = await db.pro_documents.find_one(
            {"doc_id": g["_id"], "user_id": _uid(user)},
            {"_id": 0, "number": 1, "title": 1, "client": 1, "reception_date": 1,
             "retention_release_due": 1, "retention_released": 1, "retention_released_at": 1})
        base = base or {}
        due = base.get("retention_release_due")
        released = base.get("retention_released", False)
        status = "released" if released else ("held" if not due else ("due" if due <= today else "pending"))
        out.append({
            "marche_id": g["_id"], "label": base.get("number") or base.get("title") or g.get("label"),
            "client": base.get("client"), "held": round(g["held"], 2),
            "reception_date": base.get("reception_date"),
            "release_due": due, "released": released,
            "released_at": base.get("retention_released_at"), "status": status,
        })
    out.sort(key=lambda x: (x["released"], x.get("release_due") or "9999"))
    return out


@router.post("/retentions/{marche_id}/release")
async def release_retention(marche_id: str, user=Depends(current_user)):
    base = await _base_doc(marche_id, user)
    await db.pro_documents.update_one(
        {"doc_id": marche_id, "user_id": _uid(user)},
        {"$set": {"retention_released": True, "retention_released_at": _now()}})
    await activity.log(user, "retention.release", "retention",
                       base.get("number") or base.get("title") or marche_id)
    return {"ok": True, "released_at": _now()}


@router.post("/retentions/{marche_id}/remind")
async def remind_retention(marche_id: str, user=Depends(current_user)):
    base = await _base_doc(marche_id, user)
    client = base.get("client") or {}
    email = client.get("email")
    if not email:
        raise HTTPException(400, "Aucun e-mail client sur ce marché.")
    sits = await db.situations.find(
        {"user_id": _uid(user), "marche_id": marche_id, "retention_amount": {"$gt": 0}},
        {"_id": 0, "retention_amount": 1}).to_list(500)
    held = round(sum(s.get("retention_amount", 0) for s in sits), 2)
    label = base.get("number") or base.get("title") or marche_id
    due = base.get("retention_release_due") or "—"
    html = (f"<p>Bonjour,</p><p>La retenue de garantie du marché <b>{label}</b> "
            f"d'un montant de <b>{held:.2f} €</b> arrive à échéance de libération le <b>{due}</b>.</p>"
            f"<p>Nous vous remercions de bien vouloir procéder à sa libération.</p>"
            f"<p>Cordialement.</p>")
    sent = 0
    try:
        await emailer.send_email(email, f"Libération de retenue de garantie — {label}", html)
        sent = 1
    except Exception:
        sent = 0
    return {"emails_sent": sent, "held": held, "release_due": due, "to": email}


# ─────────────────────────  4. Compte prorata (réparti entre les lots)  ─────────────────────────

class ProrataIn(BaseModel):
    rate_pct: float = Field(default=0, ge=0, le=20)
    expenses: list[dict] = []  # [{label, amount}]


def _prorata_view(base: dict, cfg: dict) -> dict:
    lines = base.get("lines") or []
    total_ht = round(sum((l.get("qty") or 0) * (l.get("unit_price_ht") or 0) for l in lines), 2)
    expenses = cfg.get("expenses") or []
    manual_total = round(sum(float(e.get("amount") or 0) for e in expenses), 2)
    rate = float(cfg.get("rate_pct") or 0)
    rate_total = round(total_ht * rate / 100, 2)
    pot = round(manual_total + rate_total, 2)
    participants = []
    for i, l in enumerate(lines):
        lot_ht = round((l.get("qty") or 0) * (l.get("unit_price_ht") or 0), 2)
        share_pct = round(lot_ht / total_ht * 100, 2) if total_ht else 0
        participants.append({
            "designation": l.get("designation", f"Lot {i+1}"),
            "lot_ht": lot_ht, "share_pct": share_pct,
            "share_amount": round(pot * share_pct / 100, 2),
        })
    return {"rate_pct": rate, "expenses": expenses, "total_ht": total_ht,
            "rate_total": rate_total, "manual_total": manual_total, "pot": pot,
            "participants": participants}


@router.get("/{marche_id}/prorata")
async def get_prorata(marche_id: str, user=Depends(current_user)):
    base = await _base_doc(marche_id, user)
    cfg = await db.prorata.find_one(
        {"user_id": _uid(user), "marche_id": marche_id}, {"_id": 0}) or {"rate_pct": 0, "expenses": []}
    return _prorata_view(base, cfg)


@router.put("/{marche_id}/prorata")
async def save_prorata(marche_id: str, body: ProrataIn, user=Depends(current_user)):
    base = await _base_doc(marche_id, user)
    expenses = [{"label": str(e.get("label", ""))[:120], "amount": round(float(e.get("amount") or 0), 2)}
                for e in (body.expenses or [])]
    await db.prorata.update_one(
        {"user_id": _uid(user), "marche_id": marche_id},
        {"$set": {"rate_pct": body.rate_pct, "expenses": expenses, "updated_at": _now()}},
        upsert=True)
    return _prorata_view(base, {"rate_pct": body.rate_pct, "expenses": expenses})
