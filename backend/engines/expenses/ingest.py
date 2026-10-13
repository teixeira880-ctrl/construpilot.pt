"""Import only existing metadata. No provider operation is started here."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException

from core.db import db
from engines.expenses.store import now, upsert_event


def timestamp(value):
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


SOURCES = {
    "ai_usage": ["engine", "created", "user_id", "company_id", "kind", "model", "input_tokens", "output_tokens", "cached_input_tokens", "calls"],
    "cad_conversion_jobs": ["job_id", "user_id", "company_id", "created_at", "status", "workitem_id", "engine"],
    "runway_renders": ["render_id", "user_id", "company_id", "created_at", "status", "task_id", "kind", "duration", "model"],
    "radar_postal": ["postal_id", "user_id", "company_id", "created_at", "status", "envoi_id", "price", "mode"],
    "autoseo_articles": ["article_id", "created_at", "source", "published_at"],
}


async def refresh_local():
    from engines.expenses.store import indexes
    await indexes()
    await db.api_expense_sync.update_one({"_id": "local"}, {"$setOnInsert": {"initialized_at": now()}}, upsert=True)
    lease = uuid4().hex
    claim = await db.api_expense_sync.update_one({"_id": "local", "$or": [{"lease_until": {"$exists": False}}, {"lease_until": {"$lt": now()}}]},
        {"$set": {"lease": lease, "lease_until": now() + timedelta(minutes=5)}})
    if not claim.modified_count:
        raise HTTPException(409, "Synchronisation déjà en cours")
    counts, skipped, truncated, aggregate_calls = {}, 0, False, 0
    try:
        for collection, fields in SOURCES.items():
            projection = {"_id": 0, "source_id": {"$toString": "$_id"}, **{field: 1 for field in fields}}
            count = 0
            async for row in db[collection].aggregate([{"$project": projection}]):
                if count >= 50000:
                    truncated = True
                    break
                count += 1
                if collection == "ai_usage" and row.get("engine") != "openai_studies":
                    aggregate_calls += int(row.get("calls") or 0)
                    continue  # Cumulative legacy counters cannot truthfully be dated per month/user.
                date = timestamp(row.get("created") or row.get("created_at") or row.get("published_at"))
                if not date:
                    skipped += 1
                    continue
                common = {"occurred_at": date, "user_id": row.get("user_id"), "company_id": row.get("company_id"),
                          "state": str(row.get("status") or "observed")[:40]}
                if collection == "ai_usage":
                    await upsert_event(source="ai_usage", source_id=row["source_id"], provider="openai_direct",
                        feature=row.get("kind") or "ai", model=row.get("model", ""),
                        units={"calls": 1, **{k: row.get(k) for k in ("input_tokens", "output_tokens", "cached_input_tokens")}}, **common)
                elif collection == "cad_conversion_jobs":
                    if not row.get("workitem_id"):
                        continue
                    await upsert_event(source="cad_job", source_id=row["job_id"], provider="autodesk", feature="dwg_conversion",
                        model=row.get("engine", ""), units={"conversions": 1}, **common)
                elif collection == "runway_renders":
                    kind = row.get("kind", "image")
                    await upsert_event(source="runway", source_id=row["render_id"], provider="runway", feature=f"render_{kind}",
                        model=row.get("model", ""),
                        units={"calls": 1, "videos" if kind == "video" else "images": 1, "seconds": row.get("duration")}, **common)
                elif collection == "radar_postal":
                    quoted = (row.get("price") or {}).get("total_ttc") if row.get("status") in {"submitted", "unknown", "submitting"} else None
                    await upsert_event(source="postal", source_id=row.get("postal_id") or row["source_id"], provider="mercifacteur",
                        feature="postal_letter", model=row.get("mode", ""), units={"letters": 1, "pages": (row.get("price") or {}).get("pages")},
                        amount=quoted, currency="EUR", evidence="estimated" if quoted is not None else "unavailable", **common)
                elif row.get("source") == "babylovegrowth":
                    await upsert_event(source="seo_article", source_id=row.get("article_id") or row["source_id"], provider="babylovegrowth",
                        feature="seo_article", units={}, **common)
            counts[collection] = count
        result = {"last_synced_at": now(), "counts": counts, "skipped_undated": skipped,
                  "truncated": truncated, "legacy_calls_unallocated": aggregate_calls, "status": "partial" if truncated else "ok"}
        await db.api_expense_sync.update_one({"_id": "local", "lease": lease}, {"$set": result})
        return result
    finally:
        await db.api_expense_sync.update_one({"_id": "local", "lease": lease}, {"$unset": {"lease": "", "lease_until": ""}})