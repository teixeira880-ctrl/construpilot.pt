"""Rotas admin para o CRM lite — lista, filtra, actualiza estado, notas, exporta."""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Response

from core.db import db
from core.security import admin_user
from engines.activity_crm.export import to_csv, to_xlsx
from engines.activity_crm.models import (
    COLLECTION,
    ActivityPatch,
    Kind,
    NoteCreate,
    State,
    utc_now_iso,
)

router = APIRouter(prefix="/admin/activity", tags=["admin-activity"])


_ALLOWED_KINDS = {"contact", "quote", "ai_chat", "permit", "download", "calculation"}
_ALLOWED_STATES = {"novo", "em_curso", "respondido", "fechado"}


def _oid(id_: str) -> ObjectId:
    try:
        return ObjectId(id_)
    except (InvalidId, TypeError):
        raise HTTPException(400, "ID inválido")


def _serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


def _build_filter(
    kind: list[str] | None, state: list[str] | None,
    date_from: str | None, date_to: str | None,
    q: str | None, assigned_to: str | None,
) -> dict:
    f: dict = {}
    if kind:
        bad = [k for k in kind if k not in _ALLOWED_KINDS]
        if bad:
            raise HTTPException(400, f"kind inválido: {bad}")
        f["kind"] = {"$in": kind}
    if state:
        bad = [s for s in state if s not in _ALLOWED_STATES]
        if bad:
            raise HTTPException(400, f"state inválido: {bad}")
        f["state"] = {"$in": state}
    if date_from or date_to:
        rng: dict = {}
        if date_from:
            rng["$gte"] = date_from
        if date_to:
            rng["$lte"] = date_to
        f["created_at"] = rng
    if q:
        safe = re.escape(q.strip())
        f["$or"] = [
            {"user_email": {"$regex": safe, "$options": "i"}},
            {"user_name": {"$regex": safe, "$options": "i"}},
            {"summary": {"$regex": safe, "$options": "i"}},
        ]
    if assigned_to:
        f["assigned_to"] = assigned_to.lower()
    return f


@router.get("")
async def list_activity(
    kind: list[str] | None = Query(default=None),
    state: list[str] | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    assigned_to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    _admin=Depends(admin_user),
) -> dict:
    f = _build_filter(kind, state, date_from, date_to, q, assigned_to)
    total = await db[COLLECTION].count_documents(f)
    skip = (page - 1) * page_size
    cursor = db[COLLECTION].find(f).sort("created_at", -1).skip(skip).limit(page_size)
    items = [_serialize(d) async for d in cursor]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/stats")
async def stats_activity(_admin=Depends(admin_user)) -> dict:
    pipeline_kind = [{"$group": {"_id": "$kind", "n": {"$sum": 1}}}]
    pipeline_state = [{"$group": {"_id": "$state", "n": {"$sum": 1}}}]
    by_kind = {d["_id"]: d["n"] async for d in db[COLLECTION].aggregate(pipeline_kind)}
    by_state = {d["_id"]: d["n"] async for d in db[COLLECTION].aggregate(pipeline_state)}
    total = await db[COLLECTION].count_documents({})
    # últimos 7/30 dias (ISO lex compare funciona para ISO 8601 UTC)
    now = datetime.now(timezone.utc)
    def iso_ago(days: int) -> str:
        from datetime import timedelta
        return (now - timedelta(days=days)).isoformat()
    last7 = await db[COLLECTION].count_documents({"created_at": {"$gte": iso_ago(7)}})
    last30 = await db[COLLECTION].count_documents({"created_at": {"$gte": iso_ago(30)}})
    return {
        "total": total,
        "by_kind": by_kind,
        "by_state": by_state,
        "last_7_days": last7,
        "last_30_days": last30,
    }


@router.get("/export")
async def export_activity(
    kind: list[str] | None = Query(default=None),
    state: list[str] | None = Query(default=None),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    format: Literal["csv", "xlsx"] = Query(default="csv"),
    _admin=Depends(admin_user),
) -> Response:
    f = _build_filter(kind, state, date_from, date_to, q, assigned_to=None)
    cursor = db[COLLECTION].find(f).sort("created_at", -1).limit(50000)
    docs = [d async for d in cursor]
    if format == "csv":
        data = to_csv(docs)
        return Response(
            content=data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="pedidos.csv"'},
        )
    try:
        data = to_xlsx(docs)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="pedidos.xlsx"'},
    )


@router.get("/{activity_id}")
async def get_activity(activity_id: str, _admin=Depends(admin_user)) -> dict:
    doc = await db[COLLECTION].find_one({"_id": _oid(activity_id)})
    if not doc:
        raise HTTPException(404, "Pedido não encontrado")
    return _serialize(doc)


@router.patch("/{activity_id}")
async def patch_activity(
    activity_id: str, patch: ActivityPatch, admin=Depends(admin_user),
) -> dict:
    oid = _oid(activity_id)
    doc = await db[COLLECTION].find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Pedido não encontrado")

    author = admin.get("email", "admin")
    now = utc_now_iso()
    update: dict = {"$set": {"updated_at": now}}
    pushes: list[dict] = []

    if patch.state is not None and patch.state != doc.get("state"):
        if patch.state not in _ALLOWED_STATES:
            raise HTTPException(400, "Estado inválido")
        update["$set"]["state"] = patch.state
        pushes.append({
            "from": doc.get("state"),
            "to": patch.state,
            "author": author,
            "created_at": now,
            "note": patch.note,
        })

    if patch.assigned_to is not None:
        update["$set"]["assigned_to"] = (patch.assigned_to or "").lower() or None

    if patch.note and patch.state is None:
        # Nota solta vai para internal_notes
        update.setdefault("$push", {})["internal_notes"] = {
            "author": author, "created_at": now, "text": patch.note,
        }

    if pushes:
        update.setdefault("$push", {})["state_history"] = {"$each": pushes}

    await db[COLLECTION].update_one({"_id": oid}, update)
    new_doc = await db[COLLECTION].find_one({"_id": oid})

    # Email automático (fail-soft; só se mudou estado e send_email não False)
    if pushes and patch.send_email is not False and not new_doc.get("no_email"):
        try:
            from engines.activity_crm.email_notifications import maybe_send_state_email
            await maybe_send_state_email(new_doc, new_state=patch.state,
                                         force=bool(patch.send_email))
        except Exception:
            # fail-soft, maybe_send_state_email ainda não implementado em AK.1
            pass

    return _serialize(new_doc)


@router.post("/{activity_id}/notes")
async def add_note(
    activity_id: str, note: NoteCreate, admin=Depends(admin_user),
) -> dict:
    oid = _oid(activity_id)
    doc = await db[COLLECTION].find_one({"_id": oid}, {"_id": 1})
    if not doc:
        raise HTTPException(404, "Pedido não encontrado")
    author = admin.get("email", "admin")
    now = utc_now_iso()
    await db[COLLECTION].update_one(
        {"_id": oid},
        {
            "$set": {"updated_at": now},
            "$push": {"internal_notes": {"author": author, "created_at": now, "text": note.text}},
        },
    )
    new_doc = await db[COLLECTION].find_one({"_id": oid})
    return _serialize(new_doc)


# ─── Admin bootstrap (índice TTL + text search) ───────────────────────────
async def ensure_indexes() -> None:
    """Idempotente — chamado no startup do server."""
    ttl_days = int(os.environ.get("ACTIVITY_LOG_TTL_DAYS", "365"))
    try:
        await db[COLLECTION].create_index("created_at")
        await db[COLLECTION].create_index("user_email")
        await db[COLLECTION].create_index("kind")
        await db[COLLECTION].create_index("state")
        # TTL só funciona com campo tipo Date no Mongo; `created_at` é ISO
        # string. Mantemos limpeza manual via cron / lifecycle externo.
        # Marcamos o valor desejado em meta para o cron ler.
        await db["_meta"].update_one(
            {"key": "customer_activity_ttl_days"},
            {"$set": {"value": ttl_days}},
            upsert=True,
        )
    except Exception:
        pass
