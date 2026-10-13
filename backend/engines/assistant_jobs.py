"""Mongo-backed serial conversation queues, independent of browser connections.

Queued work survives restarts. A lost in-flight lease is INTERRUPTED, not replayed:
tools may already have produced a billable image or a draft. Only explicit stop
cancels an active turn; later instructions stay queued without interrupting it.
"""
import asyncio
import hashlib
import json
import logging
import time
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from core.db import db
from engines.expenses.context import bind
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

log = logging.getLogger("assistant-jobs")
TERMINAL = {"completed", "cancelled", "interrupted", "failed"}
LEASE_SECONDS = 45


def public_job(job):
    return {key: job.get(key) for key in ("job_id", "conversation_id", "request_id", "sequence", "status", "created_at", "updated_at", "live", "error", "cancel_requested")}


async def owned_job(job_id, uid):
    job = await db.assistant_jobs.find_one({"job_id": job_id, "user_id": uid}, {"_id": 0})
    if not job:
        raise HTTPException(404, "Tratamento não encontrado.")
    return job


async def active_jobs(uid):
    """Small, owner-scoped status feed for navigation on any page."""
    fields = ("job_id", "conversation_id", "status", "created_at")
    cursor = db.assistant_jobs.find(
        {"user_id": uid, "status": {"$in": ["preparing", "queued", "running"]}},
        {"_id": 0, **{field: 1 for field in fields}},
    ).sort("created_at", 1).limit(50)
    return [{field: job.get(field) for field in fields} async for job in cursor]


async def enqueue(body, user):
    from routes.assistant import _allowed_doc, _allowed_plan, _allowed_project, _now
    uid = user["user_id"]
    if user.get("active") is False or user.get("company_active") is False:
        raise HTTPException(403, "Conta desativada.")
    conv = await db.assistant_convs.find_one({"conversation_id": body.conversation_id, "user_id": uid}, {"_id": 0})
    if not conv:
        raise HTTPException(404, "Conversa não encontrada.")
    if conv.get("project_id"):
        await _allowed_project(conv["project_id"], uid)
    body.request_id = body.request_id or uuid.uuid4().hex
    payload = body.model_dump()
    ident = "ajob_" + hashlib.sha256((uid + ":" + body.request_id).encode()).hexdigest()[:32]
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    old = await db.assistant_jobs.find_one({"job_id": ident, "user_id": uid}, {"_id": 0})
    if old:
        if old["payload_hash"] != digest:
            raise HTTPException(409, "Este identificador já corresponde a outro pedido.")
        return public_job(old)
    if await db.assistant_jobs.count_documents({"user_id": uid, "status": {"$in": ["queued", "running"]}}) >= 20:
        raise HTTPException(429, "20 pedidos pendentes: aguarde o fim de um tratamento.")
    attached, requested = [], set(body.attachments)
    try:
        for pid in body.plan_ids:
            plan = await _allowed_plan(pid, uid)
            if pid in requested:
                attached.append({"plan_id": pid, "filename": plan["filename"]})
        for did in body.doc_ids:
            doc = await _allowed_doc(did, uid, with_data=False)
            if did in requested:
                attached.append({"doc_id": did, "filename": doc["filename"], "kind": doc["kind"], "mime": doc["mime"]})
    except PermissionError as exc:
        raise HTTPException(403, "Anexo inacessível.") from exc
    if not requested.issubset(set(body.plan_ids + body.doc_ids)):
        raise HTTPException(422, "Falta um anexo no contexto.")
    counter = await db.assistant_convs.find_one_and_update({"conversation_id": body.conversation_id, "user_id": uid},
        {"$inc": {"turn_sequence": 1}}, return_document=ReturnDocument.AFTER, projection={"_id": 0, "turn_sequence": 1})
    now = _now()
    job = {"job_id": ident, "user_id": uid, "conversation_id": body.conversation_id, "request_id": body.request_id,
           "sequence": counter["turn_sequence"], "payload": payload, "payload_hash": digest, "status": "preparing", "created_at": now,
           "updated_at": now, "live": None, "error": None, "cancel_requested": False}
    try:
        await db.assistant_jobs.insert_one(dict(job))
    except DuplicateKeyError:
        old = await owned_job(ident, uid)
        if old["payload_hash"] != digest:
            raise HTTPException(409, "Identificador já utilizado.") from None
        return public_job(old)
    await db.assistant_msgs.update_one({"user_id": uid, "conversation_id": body.conversation_id, "request_id": body.request_id, "role": "user"}, {"$setOnInsert": {
        "message_id": "msg_" + uuid.uuid4().hex, "content": body.text, "attachments": attached, "created_at": now, "turn_seq": job["sequence"]}}, upsert=True)
    update = {"updated_at": now, "active_docs": body.doc_ids, "active_plans": body.plan_ids}
    if conv["title"] == "Nouvelle conversation":
        update["title"] = body.text[:60]
    await db.assistant_convs.update_one({"conversation_id": body.conversation_id, "user_id": uid}, {"$set": update})
    await db.assistant_jobs.update_one({"job_id": ident, "status": "preparing"}, {"$set": {"status": "queued"}})
    return public_job({**job, "status": "queued"})


async def cancel_job(job_id, uid):
    job = await owned_job(job_id, uid)
    if job["status"] in TERMINAL:
        return public_job(job)
    update = {"cancel_requested": True, "updated_at": datetime.now(timezone.utc).isoformat()}
    if job["status"] in ("preparing", "queued"):
        update["status"] = "cancelled"
        await db.assistant_msgs.update_many({"user_id": uid, "request_id": job["request_id"], "role": "user"}, {"$set": {"cancelled": True}})
    # CAS: a queued job might have started between the read and the update.
    result = await db.assistant_jobs.update_one({"job_id": job_id, "user_id": uid, "status": job["status"]}, {"$set": update})
    if not result.matched_count:
        await db.assistant_jobs.update_one({"job_id": job_id, "user_id": uid, "status": "running"}, {"$set": {"cancel_requested": True}})
    return public_job(await owned_job(job_id, uid))


async def _finish(job, state, live, error=None):
    now = datetime.now(timezone.utc).isoformat()
    result = await db.assistant_jobs.update_one({"job_id": job["job_id"], "worker": job["worker"], "status": "running"}, {"$set": {
        "status": state, "live": live, "error": error, "updated_at": now}, "$unset": {"lease_until": ""}})
    if not result.matched_count:
        return
    await db.assistant_convs.update_one({"conversation_id": job["conversation_id"], "active_job_id": job["job_id"]}, {"$unset": {"active_job_id": "", "job_lease_until": ""}, "$set": {"updated_at": now}})
    if state in ("completed", "failed", "interrupted"):
        await db.notifications.update_one({"user_id": job["user_id"], "assistant_job_id": job["job_id"]}, {"$setOnInsert": {
            "notif_id": "n_assistant_" + job["job_id"],
            "type": "assistant", "title": "Réponse de l’assistant prête" if state == "completed" else "Traitement de l’assistant interrompu",
            "message": job["payload"]["text"][:100], "link": f'/assistant?conversation={job["conversation_id"]}',
            "read": False, "created_at": now}}, upsert=True)


async def run_job(job):
    from routes.assistant import MsgIn, _prepare, _run_chat
    user = await db.users.find_one({"user_id": job["user_id"]}, {"_id": 0, "password_hash": 0, "password": 0})
    if not user or user.get("active") is False or user.get("company_active") is False:
        await _finish(job, "failed", None, "Conta indisponível.")
        return
    bind(user)
    live = {"role": "assistant", "content": "", "actions": [], "sources": [], "status": "Análise em segundo plano…"}
    state = {"image_running": False, "last_save": 0., "error": None, "completed": False}

    async def consume():
        body = MsgIn(**job["payload"])
        prepared = await _prepare(body, user, turn_seq=job["sequence"])
        prepared[0]["_background_job_id"] = job["job_id"]
        async for event in _run_chat(body, user, stream=True, prepared=prepared):
            kind = event["type"]
            if kind == "delta":
                live["content"] += event["text"]
                live["status"] = None
            elif kind == "status":
                live["status"] = event["text"]
                if event.get("tool") == "create_downloadable_file":
                    state["image_running"] = True
            elif kind == "action":
                live["actions"].append(event["action"])
                state["image_running"] = False
            elif kind == "done":
                live.clear(); live.update(event["message"])
                state["completed"] = True
            elif kind == "error":
                state["error"] = event["error"]
            if time.monotonic() - state["last_save"] >= .7 or kind in ("action", "done", "error"):
                await db.assistant_jobs.update_one({"job_id": job["job_id"], "worker": job["worker"], "status": "running"},
                    {"$set": {"live": dict(live), "updated_at": datetime.now(timezone.utc).isoformat()}})
                state["last_save"] = time.monotonic()
            if kind == "action":
                fresh = await owned_job(job["job_id"], job["user_id"])
                if fresh.get("cancel_requested"):
                    raise asyncio.CancelledError()

    task = asyncio.create_task(consume())
    outcome = "failed"
    stopping_worker = False
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=2)
            fresh = await owned_job(job["job_id"], job["user_id"])
            if fresh["status"] != "running" or (fresh.get("cancel_requested") and not state["image_running"]):
                task.cancel()
            until = datetime.now(timezone.utc) + timedelta(seconds=LEASE_SECONDS)
            await db.assistant_jobs.update_one({"job_id": job["job_id"], "worker": job["worker"], "status": "running"}, {"$set": {"lease_until": until}})
            await db.assistant_convs.update_one({"active_job_id": job["job_id"]}, {"$set": {"job_lease_until": until}})
        await task
        outcome = "completed" if state["completed"] else "failed"
    except asyncio.CancelledError:
        stopping_worker = bool(asyncio.current_task().cancelling())
        outcome = "completed" if state["completed"] else "cancelled" if (await owned_job(job["job_id"], job["user_id"])).get("cancel_requested") else "interrupted"
        task.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await task
        if outcome != "completed" and (live["content"] or live["actions"]):
            partial = {**live, "message_id": "msg_" + uuid.uuid4().hex, "user_id": job["user_id"], "conversation_id": job["conversation_id"],
                       "request_id": job["request_id"], "turn_seq": job["sequence"], "interrupted": True, "status": None, "created_at": datetime.now(timezone.utc).isoformat()}
            await db.assistant_msgs.update_one({"user_id": job["user_id"], "request_id": job["request_id"], "role": "assistant"}, {"$setOnInsert": partial}, upsert=True)
        if outcome == "cancelled":
            await db.assistant_msgs.update_many({"user_id": job["user_id"], "request_id": job["request_id"], "role": "user"}, {"$set": {"cancelled": True}})
    except Exception as exc:  # noqa: BLE001 -- queue boundary: persist failure without logging private payloads
        log.error("Assistant job %s failed (%s)", job["job_id"], type(exc).__name__)
        state["error"] = "Tratamento não concluído. As suas peças e o seu pedido são conservados."
    finally:
        live["status"] = None
        await _finish(job, outcome, dict(live), state["error"])
    if stopping_worker:
        raise asyncio.CancelledError()


async def claim_next(worker):
    now = datetime.now(timezone.utc)
    expired = await db.assistant_jobs.find({"status": "running", "lease_until": {"$lt": now}}, {"_id": 0}).to_list(20)
    for old in expired:
        await _finish(old, "interrupted", old.get("live"), "Ligação do tratamento perdida. Nenhum reinício automático para evitar uma ação em duplicado.")
    await db.assistant_jobs.update_many({"status": "preparing", "created_at": {"$lt": (now - timedelta(minutes=2)).isoformat()}},
        {"$set": {"status": "failed", "error": "Demande non mise en file. Réessayez explicitement."}})
    queued = await db.assistant_jobs.find({"status": "queued"}, {"_id": 0}).sort("created_at", 1).to_list(50)
    for candidate in queued:
        # A lower sequence that is still preparing must not be overtaken.
        prior = await db.assistant_jobs.find_one({"conversation_id": candidate["conversation_id"], "sequence": {"$lt": candidate["sequence"]}, "status": {"$in": ["preparing", "queued", "running"]}}, {"_id": 1})
        if prior:
            continue
        until = now + timedelta(seconds=LEASE_SECONDS)
        locked = await db.assistant_convs.find_one_and_update({"conversation_id": candidate["conversation_id"], "user_id": candidate["user_id"],
            "$or": [{"active_job_id": {"$exists": False}}, {"job_lease_until": {"$lt": now}}]},
            {"$set": {"active_job_id": candidate["job_id"], "job_lease_until": until}}, projection={"_id": 0})
        if not locked:
            continue
        claimed = await db.assistant_jobs.find_one_and_update({"job_id": candidate["job_id"], "status": "queued"},
            {"$set": {"status": "running", "worker": worker, "lease_until": until, "updated_at": now.isoformat()}}, return_document=ReturnDocument.AFTER, projection={"_id": 0})
        if claimed:
            return claimed
        await db.assistant_convs.update_one({"active_job_id": candidate["job_id"]}, {"$unset": {"active_job_id": "", "job_lease_until": ""}})


async def worker_loop():
    worker = uuid.uuid4().hex
    while True:
        try:
            job = await claim_next(worker)
            if job:
                await run_job(job)
            else:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Assistant queue worker failed")
            await asyncio.sleep(3)


async def start_workers():
    await db.assistant_jobs.create_index("job_id", unique=True)
    await db.assistant_jobs.create_index([("conversation_id", 1), ("sequence", 1)])
    await db.assistant_jobs.create_index([("user_id", 1), ("status", 1), ("created_at", 1)])
    await db.assistant_msgs.create_index([("user_id", 1), ("conversation_id", 1), ("role", 1), ("request_id", 1)], unique=True, partialFilterExpression={"request_id": {"$type": "string"}})
    await db.assistant_artifacts.create_index("artifact_id", unique=True)
    return [asyncio.create_task(worker_loop()) for _ in range(2)]
