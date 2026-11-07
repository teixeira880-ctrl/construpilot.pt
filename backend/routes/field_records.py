"""Visita à obra, registo diário e trabalhos adicionais pedidos pelo cliente.

- Cada registo pertence ao utilizador autenticado (`user_id`); nenhuma leitura cruza contas.
- Fotografias: mesma validação e armazenamento do módulo de acompanhamento (`routes.site._store_photos`).
- Registo diário: o servidor PROPÕE (`/parse`); só grava o que o utilizador confirma (`confirmed=true`).
- Trabalho adicional: cria um NOVO rascunho ligado ao orçamento original, que nunca é modificado.
"""
from __future__ import annotations

import asyncio
import io
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.db import db
from core.permissions import permissions_for
from core.security import current_user, pro_required
from engines import field_records as F

router = APIRouter(tags=["field-records"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_any(user: dict, features: tuple[str, ...]) -> None:
    perms = permissions_for(user)
    if not any(perms.get(f) is True for f in features):
        raise HTTPException(403, "A sua função não permite este acesso.")


async def visit_access(user=Depends(pro_required)):
    _require_any(user, ("chantier", "devis"))
    return user


async def daily_access(user=Depends(pro_required)):
    _require_any(user, ("chantier", "pointage"))
    return user


async def _owned_chantier(chantier_id: str | None, uid: str) -> str | None:
    if not chantier_id:
        return None
    if not await db.chantiers.find_one({"chantier_id": chantier_id, "user_id": uid}, {"_id": 0, "chantier_id": 1}):
        raise HTTPException(404, "Obra não encontrada")
    return chantier_id


async def _photos(photos: list[str], folder: str, uid: str) -> list[str]:
    from routes.site import _store_photos
    return await _store_photos(photos or [], folder, uid)


# --------------------------------------------------------------------------- visita à obra

class VisitIn(BaseModel):
    chantier_id: str | None = None
    title: str = Field("", max_length=160)
    address: str = Field("", max_length=300)
    client_name: str = Field("", max_length=160)
    visit_date: str = Field("", max_length=20)
    access: str = Field("", max_length=2000)
    demolitions: str = Field("", max_length=2000)
    protections: str = Field("", max_length=2000)
    notes: str = Field("", max_length=2000)
    measures: list[dict] = []
    questions: list[dict] = []
    photos: list[str] = []
    summary: str | None = Field(None, max_length=8000)  # resumo editado pelo utilizador


async def _build_visit(body: VisitIn, uid: str, existing_photos: list[str] | None = None) -> dict:
    try:
        v = F.clean_visit(body.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e))
    v["chantier_id"] = await _owned_chantier(body.chantier_id, uid)
    kept = [p for p in body.photos if isinstance(p, str) and "base64," not in p and p in (existing_photos or [])]
    new = await _photos([p for p in body.photos if isinstance(p, str) and "base64," in p], "visits", uid)
    v["photos"] = (kept + new)[:24]
    auto = F.visit_summary(v)
    v["to_confirm"] = auto["to_confirm"]
    v["summary"] = body.summary.strip() if body.summary and body.summary.strip() else auto["summary"]
    v["summary_edited"] = bool(body.summary and body.summary.strip() and body.summary.strip() != auto["summary"])
    return v


@router.post("/field/visits")
async def create_visit(body: VisitIn, user=Depends(visit_access)) -> dict:
    uid = user["user_id"]
    v = await _build_visit(body, uid)
    doc = {"visit_id": "vis_" + secrets.token_hex(6), "user_id": uid, **v, "created_at": _now(), "updated_at": _now()}
    await db.field_visits.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.put("/field/visits/{visit_id}")
async def update_visit(visit_id: str, body: VisitIn, user=Depends(visit_access)) -> dict:
    uid = user["user_id"]
    prev = await db.field_visits.find_one({"visit_id": visit_id, "user_id": uid}, {"_id": 0})
    if not prev:
        raise HTTPException(404, "Visita não encontrada")
    v = await _build_visit(body, uid, prev.get("photos"))
    await db.field_visits.update_one({"visit_id": visit_id, "user_id": uid}, {"$set": {**v, "updated_at": _now()}})
    return {**prev, **v}


@router.get("/field/visits")
async def list_visits(user=Depends(visit_access)) -> list:
    return await db.field_visits.find({"user_id": user["user_id"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)


@router.get("/field/visits/{visit_id}")
async def get_visit(visit_id: str, user=Depends(visit_access)) -> dict:
    v = await db.field_visits.find_one({"visit_id": visit_id, "user_id": user["user_id"]}, {"_id": 0})
    if not v:
        raise HTTPException(404, "Visita não encontrada")
    return v


@router.get("/field/file")
async def field_file(path: str, user=Depends(current_user)):
    uid = user["user_id"]
    if not (await db.field_visits.find_one({"user_id": uid, "photos": path}, {"_id": 0, "visit_id": 1})
            or await db.field_daily.find_one({"user_id": uid, "photos": path}, {"_id": 0, "log_id": 1})):
        raise HTTPException(404, "Imagem não encontrada")
    from engines import storage
    data, ct = await asyncio.to_thread(storage.get_object, path)
    return StreamingResponse(io.BytesIO(data), media_type=ct, headers={"Cache-Control": "private, no-store"})


# --------------------------------------------------------------------------- registo diário

class ParseIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=3000)


@router.post("/field/daily/parse")
async def parse_daily(body: ParseIn, user=Depends(daily_access)) -> dict:
    try:
        return F.parse_daily(body.text)
    except ValueError as e:
        raise HTTPException(422, str(e))


class DailyIn(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=64)
    confirmed: bool = False
    chantier_id: str | None = None
    date: str = Field("", max_length=20)
    workers: float | None = None
    hours: float | None = None
    work_done: list[str] = []
    missing_materials: list[dict] = []
    blockers: list[str] = []
    notes: str = Field("", max_length=2000)
    source_text: str = Field("", max_length=3000)
    photos: list[str] = []


@router.post("/field/daily")
async def create_daily(body: DailyIn, user=Depends(daily_access)) -> dict:
    if not body.confirmed:
        raise HTTPException(422, "Confirme o registo antes de o guardar.")
    uid = user["user_id"]
    prev = await db.field_daily.find_one({"user_id": uid, "request_id": body.request_id}, {"_id": 0})
    if prev:
        return {**prev, "duplicate": True}
    try:
        rec = F.clean_daily(body.model_dump())
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not (rec["work_done"] or rec["missing_materials"] or rec["blockers"] or rec["notes"]):
        raise HTTPException(422, "O registo está vazio: indique pelo menos um trabalho, falta ou nota.")
    rec["chantier_id"] = await _owned_chantier(body.chantier_id, uid)
    rec["photos"] = await _photos(body.photos, "daily", uid)
    doc = {"log_id": "dia_" + secrets.token_hex(6), "user_id": uid, "request_id": body.request_id,
           "author_name": user.get("name") or "", **rec, "created_at": _now()}
    await db.field_daily.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


@router.get("/field/daily")
async def list_daily(chantier_id: str = "", user=Depends(daily_access)) -> list:
    q = {"user_id": user["user_id"]}
    if chantier_id:
        q["chantier_id"] = chantier_id
    return await db.field_daily.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)


# --------------------------------------------------------------------------- trabalho adicional (alteração do cliente)

class ChangeLine(BaseModel):
    designation: str = Field(..., min_length=1, max_length=300)
    unit: str = Field("u", max_length=12)
    qty: float | None = Field(None, ge=0, le=1e7)
    unit_price_ht: float | None = Field(None, ge=0, le=1e7)


class ChangeIn(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=64)
    description: str = Field(..., min_length=3, max_length=2000)
    lines: list[ChangeLine] = Field(default_factory=list, max_length=200)
    delay_days: int | None = Field(None, ge=0, le=3650)


@router.post("/documents/{doc_id}/change-request")
async def create_change_request(doc_id: str, body: ChangeIn, user=Depends(current_user)) -> dict:
    from routes.documents import DocIn, DocLine, _get_owned, create_document
    uid = user["user_id"]
    done = await db.change_requests.find_one({"user_id": uid, "request_id": body.request_id}, {"_id": 0})
    if done:
        return {**done, "duplicate": True}
    original = await _get_owned(doc_id, user)
    if original.get("doc_type") != "quote":
        raise HTTPException(422, "Os trabalhos adicionais partem de um orçamento.")
    if not body.lines:
        raise HTTPException(422, "Indique pelo menos um trabalho adicional.")
    lines, to_confirm = [{"kind": "section", "title": "Trabalhos adicionais pedidos pelo cliente"}], []
    extra = 0.0
    for ln in body.lines:
        if ln.qty is None:
            to_confirm.append(f"Quantidade: {ln.designation}")
        if ln.unit_price_ht is None:
            to_confirm.append(f"Preço: {ln.designation}")
        extra += (ln.qty or 0) * (ln.unit_price_ht or 0)
        lines.append({"kind": "line", "line_kind": "ouvrage", "designation": ln.designation, "unit": ln.unit or "u",
                      "qty": ln.qty or 0, "unit_price_ht": ln.unit_price_ht or 0, "vat_rate": None,
                      "price_missing": ln.unit_price_ht is None, "quantity_missing": ln.qty is None})
    impact = F.change_impact(original.get("totals") or {}, extra, body.delay_days)
    ref = original.get("number") or original.get("title") or doc_id
    delay_txt = f"Impacto no prazo: +{impact['delay_days']} dia(s)." if impact["delay_known"] else "Impacto no prazo: por indicar."
    notes = (f"Trabalho adicional ao orçamento {ref}. Pedido do cliente: {body.description.strip()}\n"
             f"O orçamento {ref} mantém-se inalterado. {delay_txt}")
    if to_confirm:
        notes += "\nPor confirmar antes de enviar: " + "; ".join(to_confirm)
    new = await create_document(DocIn(
        doc_type="quote", client_id=original.get("client_id"), chantier_id=original.get("chantier_id"),
        title=f"Trabalho adicional — {original.get('title') or ref}"[:160], lines=[DocLine(**x) for x in lines],
        notes=notes[:2000], project_address=original.get("project_address") or "", status="draft"), user)
    await db.pro_documents.update_one({"doc_id": new["doc_id"], "user_id": uid},
                                      {"$set": {"source": "change_request", "amends_doc_id": doc_id}})
    rec = {"cr_id": "alt_" + secrets.token_hex(6), "user_id": uid, "request_id": body.request_id, "doc_id": doc_id,
           "new_doc_id": new["doc_id"], "description": body.description.strip(), "impact": impact,
           "to_confirm": to_confirm, "created_at": _now()}
    await db.change_requests.insert_one(dict(rec))
    rec.pop("_id", None)
    return rec


@router.get("/documents/{doc_id}/change-requests")
async def list_change_requests(doc_id: str, user=Depends(current_user)) -> list:
    from routes.documents import _get_owned
    await _get_owned(doc_id, user)
    return await db.change_requests.find({"user_id": user["user_id"], "doc_id": doc_id}, {"_id": 0}).sort("created_at", -1).to_list(100)
