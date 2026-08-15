"""Documents pro — devis, factures, avoirs (modèle générique + éditeur).

- Devis vide OU importé depuis un plan/PC analysé par l'IA (lignes éditables).
- Modifiable même après envoi/signature.
- Base commune pour les factures et avoirs (étape suivante).
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pymongo import ReturnDocument

from core.db import db
from core.security import current_user

router = APIRouter(tags=["documents"], prefix="/documents")

DOC_TYPES = ("quote", "invoice", "credit_note")
PREFIX = {"quote": "DEV", "invoice": "FAC", "credit_note": "AV"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocLine(BaseModel):
    designation: str = ""
    unit: str = "u"
    qty: float = 1
    unit_price_ht: float = 0
    vat_rate: float = 10
    category: str = ""


class DocIn(BaseModel):
    doc_type: str = "quote"
    client_id: str | None = None
    title: str = ""
    lines: list[DocLine] = []
    notes: str = ""
    payment_terms: str = ""
    deposit_pct: float = Field(default=0, ge=0, le=100)
    status: str | None = None


def _compute_totals(lines: list[dict], deposit_pct: float = 0.0) -> dict:
    ht = 0.0
    tva_map: dict[float, float] = {}
    for ln in lines:
        line_ht = round((ln.get("qty") or 0) * (ln.get("unit_price_ht") or 0), 2)
        ht += line_ht
        rate = float(ln.get("vat_rate") or 0)
        tva_map[rate] = round(tva_map.get(rate, 0) + line_ht * rate / 100, 2)
    ht = round(ht, 2)
    tva = round(sum(tva_map.values()), 2)
    ttc = round(ht + tva, 2)
    deposit = round(ttc * (deposit_pct or 0) / 100, 2)
    return {
        "ht": ht,
        "tva_breakdown": {str(k): v for k, v in sorted(tva_map.items())},
        "tva": tva, "ttc": ttc,
        "deposit_pct": deposit_pct or 0, "deposit_amount": deposit,
        "remaining": round(ttc - deposit, 2),
    }


async def _client_snapshot(client_id: str | None, user: dict) -> dict | None:
    if not client_id:
        return None
    c = await db.clients.find_one(
        {"client_id": client_id, "user_id": user["user_id"]}, {"_id": 0})
    if not c:
        return None
    keys = ("client_id", "first_name", "last_name", "company", "email",
            "phone", "address", "postal_code", "city", "siret")
    return {k: c.get(k, "") for k in keys}


async def _next_number(user_id: str, doc_type: str) -> str:
    year = datetime.now(timezone.utc).year
    res = await db.doc_counters.find_one_and_update(
        {"user_id": user_id, "doc_type": doc_type, "year": year},
        {"$inc": {"seq": 1}},
        upsert=True, return_document=ReturnDocument.AFTER)
    return f"{PREFIX.get(doc_type, 'DOC')}-{year}-{res['seq']:04d}"


async def _get_owned(doc_id: str, user: dict) -> dict:
    doc = await db.pro_documents.find_one(
        {"doc_id": doc_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Document introuvable")
    return doc


@router.post("")
async def create_document(body: DocIn, user=Depends(current_user)) -> dict:
    dtype = body.doc_type if body.doc_type in DOC_TYPES else "quote"
    lines = [ln.model_dump() for ln in body.lines]
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": dtype,
        "number": None,
        "title": (body.title or "").strip()[:160],
        "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user),
        "status": body.status or "draft",
        "lines": lines,
        "notes": (body.notes or "").strip()[:2000],
        "payment_terms": (body.payment_terms or "").strip()[:300],
        "deposit_pct": body.deposit_pct or 0,
        "totals": _compute_totals(lines, body.deposit_pct),
        "issue_date": None,
        "due_date": None,
        "source": "manual",
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.post("/from-plan/{plan_id}")
async def document_from_plan(plan_id: str, client_id: str | None = None,
                             user=Depends(current_user)) -> dict:
    """Crée un devis modifiable à partir du métré IA du plan (lignes pré-remplies)."""
    from routes.plans_common import _build_quote_and_pdf
    quote, _ = await _build_quote_and_pdf(
        plan_id, user["user_id"], "std", "carrelage", True, True, True, True)
    lines = []
    for li in quote.get("line_items", []):
        qty = li.get("quantity") or 0
        pu = round((li.get("total") or 0) / qty, 2) if qty else (li.get("total") or 0)
        lines.append({
            "designation": li.get("name") or "",
            "unit": li.get("unit") or "u",
            "qty": round(qty, 2),
            "unit_price_ht": pu,
            "vat_rate": 10,
            "category": "Depuis plan IA",
        })
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": "quote",
        "number": None,
        "title": f"Devis — {quote.get('filename') or 'plan'}",
        "client_id": client_id,
        "client": await _client_snapshot(client_id, user),
        "status": "draft",
        "lines": lines,
        "notes": "",
        "payment_terms": "",
        "deposit_pct": 0,
        "totals": _compute_totals(lines, 0),
        "issue_date": None,
        "due_date": None,
        "source": "ai_plan",
        "plan_id": plan_id,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("")
async def list_documents(doc_type: str = "", client_id: str = "", status: str = "",
                         user=Depends(current_user)) -> dict:
    query: dict = {"user_id": user["user_id"]}
    if doc_type in DOC_TYPES:
        query["doc_type"] = doc_type
    if client_id:
        query["client_id"] = client_id
    if status:
        query["status"] = status
    docs = await db.pro_documents.find(query, {"_id": 0, "lines": 0}).sort(
        "created_at", -1).to_list(2000)
    return {"documents": docs, "count": len(docs)}


@router.get("/{doc_id}")
async def get_document(doc_id: str, user=Depends(current_user)) -> dict:
    return await _get_owned(doc_id, user)


@router.put("/{doc_id}")
async def update_document(doc_id: str, body: DocIn,
                          user=Depends(current_user)) -> dict:
    existing = await _get_owned(doc_id, user)
    lines = [ln.model_dump() for ln in body.lines]
    upd = {
        "title": (body.title or "").strip()[:160],
        "client_id": body.client_id,
        "client": await _client_snapshot(body.client_id, user),
        "lines": lines,
        "notes": (body.notes or "").strip()[:2000],
        "payment_terms": (body.payment_terms or "").strip()[:300],
        "deposit_pct": body.deposit_pct or 0,
        "totals": _compute_totals(lines, body.deposit_pct),
        "updated_at": _now(),
    }
    if body.status:
        upd["status"] = body.status
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]}, {"$set": upd})
    return await _get_owned(doc_id, user)


class StatusIn(BaseModel):
    status: str


@router.patch("/{doc_id}/status")
async def set_status(doc_id: str, body: StatusIn, user=Depends(current_user)) -> dict:
    await _get_owned(doc_id, user)
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": {"status": body.status, "updated_at": _now()}})
    return await _get_owned(doc_id, user)


@router.delete("/{doc_id}")
async def delete_document(doc_id: str, user=Depends(current_user)) -> dict:
    res = await db.pro_documents.delete_one(
        {"doc_id": doc_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Document introuvable")
    return {"ok": True}


@router.post("/{doc_id}/issue")
async def issue_document(doc_id: str, user=Depends(current_user)) -> dict:
    """Attribue un numéro définitif + date d'émission."""
    doc = await _get_owned(doc_id, user)
    number = doc.get("number") or await _next_number(user["user_id"], doc["doc_type"])
    await db.pro_documents.update_one(
        {"doc_id": doc_id, "user_id": user["user_id"]},
        {"$set": {"number": number, "issue_date": doc.get("issue_date") or _now(),
                  "updated_at": _now()}})
    return await _get_owned(doc_id, user)


@router.get("/{doc_id}/pdf")
async def document_pdf(doc_id: str, user=Depends(current_user)):
    from engines.pdf_docs import build_document_pdf
    from routes.plans_common import _resolve_branding
    from routes.reviews import get_reviews_for_user
    doc = await _get_owned(doc_id, user)
    # Numérote à la volée si besoin pour que le PDF porte un numéro.
    if not doc.get("number"):
        doc["number"] = await _next_number(user["user_id"], doc["doc_type"])
        await db.pro_documents.update_one(
            {"doc_id": doc_id, "user_id": user["user_id"]},
            {"$set": {"number": doc["number"], "issue_date": doc.get("issue_date") or _now()}})
        doc["issue_date"] = doc.get("issue_date") or _now()
    branding = await _resolve_branding(user["user_id"])
    reviews = await get_reviews_for_user(user["user_id"]) if doc["doc_type"] == "quote" else None
    pdf_bytes = build_document_pdf(doc, branding=branding, reviews=reviews)
    fname = f"{doc.get('number') or doc['doc_id']}.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
