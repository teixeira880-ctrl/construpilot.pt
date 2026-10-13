"""Persistent per-department leases, staged snapshots, last-good data on source failures."""
import asyncio
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from core.db import db
from engines.radar_filters import FILTER_SCHEMA_VERSION
from engines.sitadel_client import SitadelClient, SitadelSourceError
from engines.sitadel_permits import merge_permits, official_permit, window_start
from pymongo import ReturnDocument, UpdateOne
from pymongo.errors import DuplicateKeyError, PyMongoError

log = logging.getLogger(__name__)
TASKS = set()
ACTIVE_DEPARTMENTS = set()
LIMIT = asyncio.Semaphore(2)
INITIAL_DEPARTMENTS = ["75", "77", "92", "93", "95"]


def now():
    return datetime.now(timezone.utc)


async def sync_department(department, lease_id):
    run_id = secrets.token_hex(12)
    published = False
    client = SitadelClient()
    try:
        async with LIMIT:
            communes = await client.communes(department)
            permits, sources, received, skipped = {}, [], 0, 0
            for kind, key in (("logements", "SITADEL_LOGEMENTS_RID"), ("locaux", "SITADEL_LOCAUX_RID")):
                rid = os.environ[key]
                meta = await client.metadata(rid)
                sources.append({"kind": kind, "rid": rid, "millesime": meta["millesime"],
                    "published_at": meta["published"], "coverage_end": meta.get("temporal_coverage", {}).get("end")})
                async for rows, page, total in client.pages(rid, meta, department, window_start()):
                    for row in rows:
                        permit = official_permit(row, meta, rid, kind, department, communes)
                        received += 1
                        if permit is None:
                            skipped += 1
                            continue
                        permits[permit["id"]] = merge_permits(permits.get(permit["id"]), permit)
                    await db.radar_sync.update_one({"_id": department, "lease_id": lease_id}, {"$set": {
                        "stage": f"{kind} · page {page}", "received": received,
                        "lease_until": (now() + timedelta(minutes=15)).isoformat()}})
            docs = [{**p, "ingest_run": run_id} for p in permits.values()]
            if docs:
                await db.radar_permits.bulk_write([UpdateOne({"_id": f'{run_id}:{p["id"]}'}, {"$set": p}, upsert=True) for p in docs], ordered=False)
            completed = now().isoformat()
            result = await db.radar_sync.update_one({"_id": department, "lease_id": lease_id}, {"$set": {
                "status": "ready", "active_run": run_id, "count": len(docs), "sources": sources,
                "last_success_at": completed, "last_checked_at": completed, "window_start": window_start(),
                "received": received, "skipped": skipped, "unlocated": sum(p["lat"] is None for p in docs),
                "filter_schema_version": FILTER_SCHEMA_VERSION,
                "error": None, "stage": "Terminé"}, "$unset": {"lease_until": ""}})
            if result.modified_count:
                published = True
                try:
                    await db.radar_permits.delete_many({"dep": department, "source.kind": "sitadel_official", "ingest_run": {"$ne": run_id}})
                except PyMongoError:
                    log.warning("Old SITADEL snapshot cleanup deferred for %s", department)
            else:
                await db.radar_permits.delete_many({"ingest_run": run_id})
    except Exception as exc:
        message = str(exc) if isinstance(exc, SitadelSourceError) else "Synchronisation interrompue. Les dernières données valides sont conservées."
        log.exception("SITADEL sync failed for department %s", department)
        if not published:
            await db.radar_permits.delete_many({"ingest_run": run_id})
        await db.radar_sync.update_one({"_id": department, "lease_id": lease_id}, {"$set": {
            "status": "error", "error": message, "last_checked_at": now().isoformat()}, "$unset": {"lease_until": ""}})
    finally:
        ACTIVE_DEPARTMENTS.discard(department)
        await client.close()


async def ensure_sync(departments, force=False):
    for dep in departments:
        if dep in ACTIVE_DEPARTMENTS:
            continue
        existing = await db.radar_sync.find_one({"_id": dep}, {"_id": 0})
        current = now()
        if existing:
            if existing.get("status") == "running" and existing.get("lease_until", "") > current.isoformat():
                continue
            # Normal refresh once daily; even explicit retry is rate-limited to once per minute.
            categories_outdated = existing.get("filter_schema_version") != FILTER_SCHEMA_VERSION
            minutes = 1 if force or categories_outdated or existing.get("status") == "error" else 24 * 60
            if existing.get("status") != "running" and existing.get("last_checked_at", "") > (current - timedelta(minutes=minutes)).isoformat():
                continue
        lease_id = secrets.token_hex(10)
        try:
            lease = await db.radar_sync.find_one_and_update({"_id": dep, "$or": [
                {"status": {"$ne": "running"}}, {"lease_until": {"$lte": current.isoformat()}}]}, {"$set": {
                "department": dep, "status": "running", "lease_id": lease_id,
                "lease_until": (current + timedelta(minutes=15)).isoformat(), "stage": "Connexion SDES",
                "error": None}}, upsert=True, return_document=ReturnDocument.AFTER, projection={"_id": 0})
        except DuplicateKeyError:
            continue
        if lease:
            ACTIVE_DEPARTMENTS.add(dep)
            task = asyncio.create_task(sync_department(dep, lease_id))
            TASKS.add(task)
            task.add_done_callback(TASKS.discard)


async def sync_status(departments):
    records = await db.radar_sync.find({"department": {"$in": departments}}, {"_id": 0, "lease_id": 0, "lease_until": 0, "active_run": 0}).to_list(None)
    indexed = {r["department"]: r for r in records}
    return {"departments": [indexed.get(d, {"department": d, "status": "not_loaded", "count": 0}) for d in departments],
        "source_name": "SDES · SITADEL", "source_url": os.environ["SITADEL_PORTAL_URL"],
        "window_start": window_start(), "window_end": datetime.now(timezone.utc).date().isoformat()}