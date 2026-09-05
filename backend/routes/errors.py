"""Client-side error logging.

Receives error reports from the frontend `ErrorBoundary`, writes them to the
Python logger (supervisor logs → visible in Emergent's deployed app logs) AND
persists them to MongoDB with a 30-day TTL for the admin dashboard.

Kept intentionally lightweight — no external Sentry dependency. Rate-limits
to 1 error per IP+message per 60s to avoid log floods.
"""
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from core.db import db
from core.security import admin_user

router = APIRouter(prefix="/errors", tags=["errors"])
logger = logging.getLogger("client_errors")

# Simple in-memory dedup cache : { (ip, msg_hash): last_ts }
_RECENT: dict[tuple[str, str], float] = {}
_DEDUP_WINDOW_S = 60.0
_MAX_CACHE = 500

# Alert dedup — 1 email admin per unique message every 15 min
_ALERTED: dict[str, float] = {}
_ALERT_WINDOW_S = 15 * 60.0
_ADMIN_ALERT_EMAIL = "admin@construpilot.fr"


class ClientErrorIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    stack: Optional[str] = Field(default=None, max_length=5000)
    url: Optional[str] = Field(default=None, max_length=500)
    user_agent: Optional[str] = Field(default=None, max_length=500)
    user_id: Optional[str] = Field(default=None, max_length=100)


def _dedup(ip: str, msg: str) -> bool:
    """Return True if this (ip, msg) was seen in the last dedup window."""
    now = time.time()
    key = (ip, hashlib.sha256(msg.encode("utf-8", "ignore")).hexdigest()[:16])
    # Expire old entries lazily
    if len(_RECENT) > _MAX_CACHE:
        cutoff = now - _DEDUP_WINDOW_S
        for k in [k for k, t in _RECENT.items() if t < cutoff]:
            _RECENT.pop(k, None)
    last = _RECENT.get(key)
    if last and (now - last) < _DEDUP_WINDOW_S:
        return True
    _RECENT[key] = now
    return False


@router.post("/client-log")
async def log_client_error(body: ClientErrorIn, request: Request) -> dict:
    """Public endpoint (no auth) — logs a frontend runtime error.

    The ErrorBoundary POSTs here whenever `componentDidCatch` fires.
    """
    ip = (request.client.host if request.client else "unknown")[:40]
    if _dedup(ip, body.message):
        return {"ok": True, "deduped": True}
    logger.error(
        "CLIENT_ERROR | ip=%s | user=%s | url=%s | ua=%s | msg=%s | stack=%s",
        ip,
        body.user_id or "-",
        (body.url or "-")[:200],
        (body.user_agent or "-")[:150],
        body.message[:400],
        (body.stack or "-")[:2000],
    )
    # Persist to MongoDB for the admin dashboard
    now = datetime.now(timezone.utc)
    doc = {
        "created_at": now,
        "created_at_iso": now.isoformat(),
        "ip": ip,
        "user_id": body.user_id,
        "url": body.url,
        "user_agent": body.user_agent,
        "message": body.message[:400],
        "stack": (body.stack or "")[:2000],
    }
    try:
        await db.client_errors.insert_one(doc)
    except Exception as e:
        logger.warning(f"client_errors insert failed: {e}")
    # Email admin alert (best-effort, debounced 15 min per unique message)
    msg_key = hashlib.sha256(body.message.encode("utf-8", "ignore")).hexdigest()[:16]
    last_alert = _ALERTED.get(msg_key)
    if not last_alert or (time.time() - last_alert) > _ALERT_WINDOW_S:
        _ALERTED[msg_key] = time.time()
        # Prune old alert cache
        if len(_ALERTED) > 200:
            cutoff = time.time() - _ALERT_WINDOW_S
            for k, t in list(_ALERTED.items()):
                if t < cutoff:
                    _ALERTED.pop(k, None)
        try:
            from engines import emailer
            html = emailer.wrap_html(
                "🚨 Erreur client détectée",
                "<p>Une erreur JavaScript a été remontée par l'ErrorBoundary "
                "en production.</p>"
                f"<p><strong>Message :</strong> <code>{body.message[:400]}</code></p>"
                f"<p><strong>URL :</strong> {body.url or '—'}<br/>"
                f"<strong>User :</strong> {body.user_id or 'anonyme'}<br/>"
                f"<strong>IP :</strong> {ip}<br/>"
                f"<strong>UA :</strong> {(body.user_agent or '—')[:100]}</p>"
                + (f"<pre style='background:#f5f5f7;padding:12px;border-radius:4px;"
                   f"font-size:11px;overflow:auto;max-height:240px'>{body.stack[:1500]}</pre>"
                   if body.stack else "")
                + "<p style='color:#64748B;font-size:12px;margin-top:16px'>"
                "Prochaine alerte identique dans 15 min max (dédup).</p>",
                cta_url="https://construpilot.fr/admin",
                cta_label="Voir le dashboard Erreurs",
            )
            await emailer.send_email(_ADMIN_ALERT_EMAIL,
                                      f"🚨 [ConstruPilot] {body.message[:80]}", html)
            logger.info(f"Admin alert email sent for msg={body.message[:60]}")
        except Exception as e:
            logger.warning(f"admin alert email failed: {e}")
    return {"ok": True}


@router.get("/admin/list", dependencies=[Depends(admin_user)])
async def list_client_errors(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """Admin — liste les erreurs client des N dernières heures + agrégat par
    message pour identifier rapidement les patterns récurrents.
    """
    since = datetime.now(timezone.utc).timestamp() - hours * 3600
    since_dt = datetime.fromtimestamp(since, tz=timezone.utc)
    cursor = db.client_errors.find(
        {"created_at": {"$gte": since_dt}}, {"_id": 0},
    ).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(limit)
    # Aggregate by message → top-10 grouped
    agg_pipeline = [
        {"$match": {"created_at": {"$gte": since_dt}}},
        {"$group": {
            "_id": "$message",
            "count": {"$sum": 1},
            "last_seen": {"$max": "$created_at_iso"},
            "urls": {"$addToSet": "$url"},
            "affected_users": {"$addToSet": "$user_id"},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    top = await db.client_errors.aggregate(agg_pipeline).to_list(10)
    top = [{"message": t["_id"], "count": t["count"],
            "last_seen": t["last_seen"],
            "urls": [u for u in t.get("urls", []) if u][:5],
            "affected_users": len([u for u in t.get("affected_users", []) if u])}
           for t in top]
    return {
        "hours": hours,
        "total": len(items),
        "top_messages": top,
        "items": [{**i, "created_at": i.get("created_at_iso")} for i in items],
    }



@router.get("/admin/trend", dependencies=[Depends(admin_user)])
async def errors_trend(days: int = Query(14, ge=1, le=90)) -> dict:
    """Admin — tendance quotidienne des erreurs client (pour visualiser la baisse
    après un correctif, ex. WebGL)."""
    since_dt = datetime.fromtimestamp(
        datetime.now(timezone.utc).timestamp() - days * 86400, tz=timezone.utc)
    pipeline = [
        {"$match": {"created_at": {"$gte": since_dt}}},
        {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    rows = await db.client_errors.aggregate(pipeline).to_list(100)
    by_day = {r["_id"]: r["count"] for r in rows}
    out = []
    for i in range(days - 1, -1, -1):
        d = datetime.fromtimestamp(
            datetime.now(timezone.utc).timestamp() - i * 86400, tz=timezone.utc).strftime("%Y-%m-%d")
        out.append({"day": d, "count": by_day.get(d, 0)})
    total = sum(x["count"] for x in out)
    return {"days": days, "total": total, "series": out}
