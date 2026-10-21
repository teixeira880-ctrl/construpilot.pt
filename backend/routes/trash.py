"""Generic recycle bin: deleted records of any kind are moved to `trash_items` (restorable 30 days), then purged."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException

from core.security import current_user, admin_user as require_admin
from core.db import db
from engines.trash_jobs import latest_snapshot, run_daily_snapshot, run_purge_alerts, snapshot_status

router = APIRouter(prefix="/trash", tags=["trash"])
RETENTION_DAYS = 30

# kind → (collection, id field, label builder)
KINDS = {
    "document": ("pro_documents", "doc_id", lambda d: f"{ {'quote': 'Orçamento', 'invoice': 'Fatura', 'credit_note': 'Nota de crédito'}.get(d.get('doc_type'), d.get('doc_type', 'Documento'))} {d.get('number') or ''} — {d.get('title') or d.get('client_name') or ''}".strip(" —")),
    "project": ("projects", "project_id", lambda d: f"Projeto {d.get('name') or d.get('title') or ''}".strip()),
    "client": ("clients", "client_id", lambda d: f"Cliente {d.get('name') or d.get('company') or d.get('email') or ''}".strip()),
    "conversation": ("assistant_convs", "conversation_id", lambda d: f"Conversation {d.get('title') or ''}".strip()),
    "plan": ("plans_takeoff", "plan_id", lambda d: f"Planta {d.get('filename') or d.get('name') or ''}".strip()),
}
# Kinds kept in their own collection with a `trashed_at` flag (records too large to copy); the bin holds only a stub.
SOFT_KINDS = {"plan"}


def _now():
    return datetime.now(timezone.utc)


async def trash_record(kind: str, doc: dict, user_id: str, extra: dict | None = None) -> dict:
    """Move a record into the bin (the caller deletes it from its collection, except SOFT_KINDS which are flagged here)."""
    coll, id_field, label = KINDS[kind]
    now = _now()
    record = doc
    if kind in SOFT_KINDS:
        record = {k: doc.get(k) for k in (id_field, "user_id", "filename", "name", "page_count", "rooms_count", "created_at")}
        await db[coll].update_one({id_field: doc[id_field], "user_id": user_id}, {"$set": {"trashed_at": now.isoformat()}})
    item = {"kind": kind, "item_id": doc[id_field], "user_id": user_id, "label": label(doc)[:160], "deleted_at": now.isoformat(),
            "purge_after": (now + timedelta(days=RETENTION_DAYS)).isoformat(), "record": record, **(extra or {})}
    await db.trash_items.update_one({"kind": kind, "item_id": doc[id_field], "user_id": user_id}, {"$set": item, "$unset": {"purge_alerted": "", "purge_alerted_at": ""}}, upsert=True)
    return {"ok": True, "trashed": True, "kind": kind, "item_id": doc[id_field], "restorable_until": item["purge_after"]}


async def _purge_soft(kind: str, item_id: str, user_id: str):
    if kind == "plan":
        from engines.plan_sources import delete_plan_sources
        await db.plans_takeoff.delete_one({"plan_id": item_id, "user_id": user_id})
        await delete_plan_sources(db, item_id, user_id)
    elif kind == "conversation":
        await db.assistant_msgs.delete_many({"conversation_id": item_id, "user_id": user_id})


async def restore_record(kind: str, item_id: str, user_id: str) -> dict:
    coll, id_field, _ = KINDS[kind]
    item = await db.trash_items.find_one({"kind": kind, "item_id": item_id, "user_id": user_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Elemento não encontrado na reciclagem")
    record = item["record"]
    restored_from = "trash"
    if kind in SOFT_KINDS:
        res = await db[coll].update_one({id_field: item_id, "user_id": user_id}, {"$unset": {"trashed_at": ""}})
        if not res.matched_count:
            raise HTTPException(410, "O conteúdo deste elemento já não existe")
    else:
        if kind == "document" and item.get("partial"):
            snap = await latest_snapshot(user_id, record.get("doc_id"), record.get("number"))
            if snap:
                record = {**snap["record"], "doc_id": item_id, "user_id": user_id}
                restored_from = f"snapshot:{snap['day']}"
        await db[coll].update_one({id_field: item_id, "user_id": user_id}, {"$setOnInsert": record}, upsert=True)
        if kind == "conversation":
            await db.assistant_msgs.update_many({"conversation_id": item_id, "user_id": user_id}, {"$unset": {"trashed": ""}})
    await db.trash_items.delete_one({"kind": kind, "item_id": item_id, "user_id": user_id})
    return {"ok": True, "kind": kind, "item_id": item_id, "restored_from": restored_from, "partial": bool(item.get("partial")) and restored_from == "trash",
            "record": {k: record.get(k) for k in (id_field, "status", "number", "title", "name", "filename")}}


async def _purge_expired(user_id: str | None = None):
    q = {"purge_after": {"$lt": _now().isoformat()}}
    if user_id:
        q["user_id"] = user_id
    async for it in db.trash_items.find(q, {"_id": 0, "record": 0}):
        await _purge_soft(it["kind"], it["item_id"], it["user_id"])
    await db.trash_items.delete_many(q)


@router.get("")
async def list_trash(kind: str = "", user=Depends(current_user)) -> dict:
    await _purge_expired(user["user_id"])
    query = {"user_id": user["user_id"]}
    if kind in KINDS:
        query["kind"] = kind
    items = await db.trash_items.find(query, {"_id": 0, "record.lines": 0, "record.pages": 0}).sort("deleted_at", -1).to_list(500)
    for it in items:
        rec = it.pop("record", None) or {}
        if it["kind"] == "document" and it.get("partial"):
            snap = await latest_snapshot(user["user_id"], rec.get("doc_id"), rec.get("number"))
            it["full_backup"] = bool(snap)
            it["full_backup_day"] = snap["day"] if snap else None
    return {"items": items, "count": len(items), "retention_days": RETENTION_DAYS, "alert_days_before_purge": 3}


@router.post("/{kind}/{item_id}/restore")
async def restore(kind: str, item_id: str, user=Depends(current_user)) -> dict:
    if kind not in KINDS:
        raise HTTPException(400, "Tipo desconhecido")
    return await restore_record(kind, item_id, user["user_id"])


@router.post("/restore-all")
async def restore_all(user=Depends(current_user)) -> dict:
    """Restaure tous les éléments récupérables de la corbeille en un clic."""
    await _purge_expired(user["user_id"])
    items = await db.trash_items.find(
        {"user_id": user["user_id"]}, {"_id": 0, "kind": 1, "item_id": 1}).to_list(1000)
    restored, failed = 0, 0
    for it in items:
        try:
            await restore_record(it["kind"], it["item_id"], user["user_id"])
            restored += 1
        except Exception:
            failed += 1
    return {"ok": True, "restored": restored, "failed": failed}


@router.delete("/{kind}/{item_id}")
async def purge(kind: str, item_id: str, user=Depends(current_user)) -> dict:
    res = await db.trash_items.delete_one({"kind": kind, "item_id": item_id, "user_id": user["user_id"]})
    if not res.deleted_count:
        raise HTTPException(404, "Elemento não encontrado na reciclagem")
    await _purge_soft(kind, item_id, user["user_id"])
    return {"ok": True, "purged": True}


@router.delete("")
async def empty_trash(user=Depends(current_user)) -> dict:
    async for it in db.trash_items.find({"user_id": user["user_id"]}, {"_id": 0, "record": 0}):
        await _purge_soft(it["kind"], it["item_id"], user["user_id"])
    res = await db.trash_items.delete_many({"user_id": user["user_id"]})
    return {"ok": True, "purged": res.deleted_count}


@router.get("/snapshots/status")
async def snapshots_status(user=Depends(current_user)) -> dict:
    return await snapshot_status()


@router.post("/snapshots/run")
async def snapshots_run(user=Depends(require_admin)) -> dict:
    return await run_daily_snapshot()


@router.post("/alerts/run")
async def alerts_run(user=Depends(require_admin)) -> dict:
    return await run_purge_alerts()


@router.post("/deadline-reminders/run")
async def deadline_reminders_run(user=Depends(require_admin)) -> dict:
    from engines.deadline_reminders import run_deadline_reminders
    return await run_deadline_reminders()


@router.post("/recover-history")
async def recover_history(user=Depends(current_user)) -> dict:
    """Documents hard-deleted before the bin existed. Rebuilt FULLY from the daily snapshot when one exists, otherwise PARTIALLY from the
    activity log and the sending log (number/title, client, total, signature flag) — flagged « partial »."""
    import uuid
    uid = user["user_id"]
    live = {d["doc_id"] async for d in db.pro_documents.find({"user_id": uid}, {"doc_id": 1})}
    in_trash = {t["item_id"] async for t in db.trash_items.find({"user_id": uid, "kind": "document"}, {"item_id": 1})}
    created = []
    # 1) full copies from the daily snapshot
    seen_snap = set()
    async for snap in db.document_snapshots.find({"user_id": uid}, {"_id": 0}).sort("day", -1):
        did = snap["doc_id"]
        if did in seen_snap or did in live or did in in_trash:
            continue
        seen_snap.add(did)
        rec = snap["record"]
        await trash_record("document", rec, uid, {"doc_type": rec.get("doc_type"), "status": rec.get("status"), "recovered_from": ["snapshot"], "snapshot_day": snap["day"]})
        in_trash.add(did)
        created.append({"doc_id": did, "label": KINDS["document"][2](rec), "partial": False})
    # 2) partial copies from the sending log / activity log
    sends = await db.quote_sends.find({"user_id": uid}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    by_doc = {}
    for s in sends:
        if s.get("doc_id") and s["doc_id"] not in live and s["doc_id"] not in in_trash:
            by_doc.setdefault(s["doc_id"], s)
    acts = await db.activity_log.find({"$or": [{"actor_id": uid}, {"user_id": uid}], "action": "document.delete"}, {"_id": 0}).sort("created_at", -1).to_list(500)
    seen_labels = set()
    for doc_id, s in by_doc.items():
        subject = s.get("subject") or ""
        number = next((w for w in subject.replace("—", " ").split() if w.upper().startswith(("DEV-", "FAC-", "AV-"))), None)
        act = next((a for a in acts if a.get("label") and (a["label"] == number or a["label"] in subject)), None)
        record = {"doc_id": doc_id, "user_id": uid, "doc_type": "invoice" if (number or "").upper().startswith("FAC-") else "quote", "number": number, "title": subject[:160] or "Documento recuperado",
                  "client_name": s.get("client_name"), "client_email": s.get("client_email"), "status": "signed" if s.get("signed") else "sent",
                  "totals": {"ttc": s.get("total_ttc")} if s.get("total_ttc") is not None else {}, "lines": [], "issue_date": (s.get("created_at") or "")[:10],
                  "created_at": s.get("created_at"), "source": "recovered_from_history",
                  "notes": "Documento reconstituído parcialmente a partir do histórico de envio: montante e cliente retomados, conteúdo detalhado não recuperável."}
        extra = {"partial": True, "recovered_from": ["quote_sends"] + (["activity_log"] if act else []), "deleted_at_hint": (act or {}).get("created_at"), "status": record["status"], "doc_type": record["doc_type"]}
        await trash_record("document", record, uid, extra)
        created.append({"doc_id": doc_id, "label": record["title"], "partial": True})
        if act:
            seen_labels.add(act["label"])
    live_docs = [x async for x in db.pro_documents.find({"user_id": uid}, {"number": 1, "title": 1})]
    for a in acts:
        label = a.get("label")
        if not label or label in seen_labels:
            continue
        seen_labels.add(label)
        if any(label == d.get("number") or label == d.get("title") for d in live_docs):
            continue
        if await db.trash_items.find_one({"user_id": uid, "kind": "document", "$or": [{"record.number": label}, {"record.title": label}]}):
            continue
        doc_id = f"doc_rec_{uuid.uuid4().hex[:10]}"
        is_number = label.upper().startswith(("DEV-", "FAC-", "AV-"))
        record = {"doc_id": doc_id, "user_id": uid, "doc_type": "invoice" if label.upper().startswith("FAC-") else "quote", "number": label if is_number else None, "title": label if not is_number else f'Documento {label}',
                  "status": "draft", "totals": {}, "lines": [], "created_at": a.get("created_at"), "source": "recovered_from_history",
                  "notes": "Documento reconstituído a partir do registo de atividade: apenas o título é conhecido, conteúdo e montantes não recuperáveis."}
        await trash_record("document", record, uid, {"partial": True, "recovered_from": ["activity_log"], "deleted_at_hint": a.get("created_at"), "status": "draft", "doc_type": record["doc_type"]})
        created.append({"doc_id": doc_id, "label": label, "partial": True})
    full = sum(1 for c in created if not c["partial"])
    return {"ok": True, "recovered": len(created), "full": full, "partial": len(created) - full, "items": created,
            "note": "Os documentos presentes na cópia de segurança diária são reconstituídos integralmente (linhas incluídas); os outros, apagados antes da reciclagem, apenas conservam o título, o cliente, o montante c/ IVA e o estado de assinatura."}
