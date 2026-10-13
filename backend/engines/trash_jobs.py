"""Daily jobs around the recycle bin: full snapshot of quotes/invoices, and « purge in 3 days » alerts."""
import logging
import uuid
from datetime import datetime, timedelta, timezone

from core.db import db

logger = logging.getLogger(__name__)
SNAPSHOT_RETENTION_DAYS = 30
ALERT_DAYS_BEFORE_PURGE = 3
SNAPSHOT_TYPES = ("quote", "invoice", "credit_note")


def _now():
    return datetime.now(timezone.utc)


async def run_daily_snapshot() -> dict:
    """Copy every quote/invoice/credit note (lines included) into `document_snapshots`, one entry per doc and day."""
    day = _now().strftime("%Y-%m-%d")
    now_iso = _now().isoformat()
    count = 0
    async for doc in db.pro_documents.find({"doc_type": {"$in": SNAPSHOT_TYPES}}, {"_id": 0}):
        if not doc.get("doc_id") or not doc.get("user_id"):
            continue
        await db.document_snapshots.update_one(
            {"doc_id": doc["doc_id"], "day": day},
            {"$set": {"doc_id": doc["doc_id"], "user_id": doc["user_id"], "day": day, "taken_at": now_iso,
                      "doc_type": doc.get("doc_type"), "number": doc.get("number"), "title": doc.get("title"), "record": doc}},
            upsert=True)
        count += 1
    cutoff = (_now() - timedelta(days=SNAPSHOT_RETENTION_DAYS)).strftime("%Y-%m-%d")
    purged = await db.document_snapshots.delete_many({"day": {"$lt": cutoff}})
    await db.trash_jobs.update_one({"job": "snapshot"}, {"$set": {"job": "snapshot", "last_run": now_iso, "day": day, "documents": count, "purged_old": purged.deleted_count}}, upsert=True)
    logger.info("Daily document snapshot: %s documents, %s old entries purged", count, purged.deleted_count)
    return {"day": day, "documents": count, "purged_old": purged.deleted_count, "taken_at": now_iso}


async def latest_snapshot(user_id: str, doc_id: str | None = None, number: str | None = None) -> dict | None:
    """Most recent full copy of a document, looked up by id or by number."""
    ors = []
    if doc_id:
        ors.append({"doc_id": doc_id})
    if number:
        ors.append({"number": number})
    if not ors:
        return None
    return await db.document_snapshots.find_one({"user_id": user_id, "$or": ors}, {"_id": 0}, sort=[("day", -1)])


async def snapshot_status() -> dict:
    job = await db.trash_jobs.find_one({"job": "snapshot"}, {"_id": 0}) or {}
    return {**job, "retention_days": SNAPSHOT_RETENTION_DAYS, "total_entries": await db.document_snapshots.count_documents({})}


async def run_purge_alerts() -> dict:
    """One in-app notification per user when items in the bin will be erased within 3 days (each item alerted once)."""
    now = _now()
    limit = (now + timedelta(days=ALERT_DAYS_BEFORE_PURGE)).isoformat()
    per_user: dict[str, list] = {}
    async for it in db.trash_items.find({"purge_after": {"$lte": limit, "$gt": now.isoformat()}, "purge_alerted": {"$ne": True}}, {"_id": 0, "record": 0}):
        per_user.setdefault(it["user_id"], []).append(it)
    notified = 0
    for uid, items in per_user.items():
        soonest = min(it["purge_after"] for it in items)
        days = max(1, (datetime.fromisoformat(soonest) - now).days + (1 if (datetime.fromisoformat(soonest) - now).seconds else 0))
        labels = ", ".join(it["label"] for it in items[:3]) + (" …" if len(items) > 3 else "")
        msg = (f"{len(items)} élément(s) de la corbeille seront effacés définitivement dans {days} jour(s) : {labels}"
               if len(items) > 1 else f"« {items[0]['label']} » sera effacé définitivement de la corbeille dans {days} jour(s)")
        await db.notifications.insert_one({"notif_id": "n_" + uuid.uuid4().hex[:10], "user_id": uid, "type": "trash_purge", "url": "/corbeille",
                                           "message": msg, "items": [{"kind": it["kind"], "item_id": it["item_id"]} for it in items],
                                           "created_at": now.isoformat(), "read": False})
        await db.trash_items.update_many({"user_id": uid, "kind": {"$in": [it["kind"] for it in items]}, "item_id": {"$in": [it["item_id"] for it in items]}},
                                         {"$set": {"purge_alerted": True, "purge_alerted_at": now.isoformat()}})
        notified += 1
    await db.trash_jobs.update_one({"job": "purge_alerts"}, {"$set": {"job": "purge_alerts", "last_run": now.isoformat(), "users_notified": notified}}, upsert=True)
    return {"users_notified": notified, "items": sum(len(v) for v in per_user.values())}
