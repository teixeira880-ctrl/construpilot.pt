"""Scheduled Growth work: periodic audits per project cadence and publication of scheduled, approved contents (no double publish)."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from core.db import db
from growth import content as ct
from growth.common import new_id, now_iso
from growth.crawler import run_audit

logger = logging.getLogger(__name__)


async def run_scheduled() -> dict:
    out = {"audits_started": 0, "published": 0, "publish_failed": 0}
    now = datetime.now(timezone.utc)
    for p in await db.growth_projects.find({}, {"_id": 0}).to_list(20):
        st = p.get("settings") or {}
        cadence = int(st.get("crawl_cadence_days") or 0)
        if cadence:
            last = await db.growth_audits.find_one({"project_id": p["project_id"], "status": {"$in": ["completed", "stopped", "running", "queued"]}}, {"_id": 0, "created_at": 1}, sort=[("created_at", -1)])
            if not last or datetime.fromisoformat(last["created_at"]) < now - timedelta(days=cadence):
                a = {"audit_id": new_id("aud"), "project_id": p["project_id"], "status": "queued", "max_pages": int(st.get("max_pages") or 50), "created_at": now_iso(), "created_by": "scheduler", "progress": 0, "pages_crawled": 0}
                await db.growth_audits.insert_one(dict(a))
                asyncio.create_task(run_audit(a["audit_id"]))
                out["audits_started"] += 1
        if st.get("publish_mode") == "auto":
            async for c in db.growth_contents.find({"project_id": p["project_id"], "status": "scheduled", "scheduled_for": {"$lte": now_iso()}}, {"_id": 0}):
                checks = c.get("checks") or {}
                if not checks.get("passed") or checks.get("checked_at", "") < c.get("updated_at", ""):
                    continue
                lock = await db.growth_contents.update_one({"content_id": c["content_id"], "publishing": {"$ne": True}}, {"$set": {"publishing": True}})
                if not lock.modified_count:
                    continue
                try:
                    res = await ct.publish(p, c, "scheduler")
                    await db.growth_contents.update_one({"content_id": c["content_id"]}, {"$set": {"status": "published", **res, "publishing": False}, "$push": {"publications": res}})
                    out["published"] += 1
                    from growth.marketing import on_published
                    asyncio.create_task(on_published(p, {**c, **res}))
                except Exception as e:
                    logger.warning("scheduled publish failed: %s", e)
                    await db.growth_contents.update_one({"content_id": c["content_id"]}, {"$set": {"status": "failed", "publish_error": str(e)[:300], "publishing": False}})
                    out["publish_failed"] += 1
    return out


async def recover_interrupted() -> dict:
    """Called at startup: tasks lost with the previous process are flagged so the UI can offer « Reprendre »."""
    a = await db.growth_audits.update_many({"status": {"$in": ["running", "queued"]}}, {"$set": {"status": "interrupted", "finished_at": now_iso(), "note": "Interrompido por um reinício do servidor — relance a auditoria."}})
    c = await db.growth_campaigns.update_many({"status": "running"}, {"$set": {"status": "interrupted", "note": "Interrompida por um reinício do servidor — «Retomar» continua sem refazer os testes já executados."}})
    return {"audits": a.modified_count, "campaigns": c.modified_count}
