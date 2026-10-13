"""BabyLoveGrowth.ai — synchronisation SEO/blog (pull API + webhook push).

Les articles sont stockés dans `autoseo_articles` (même schéma que AutoSEO, `source: babylovegrowth`)
pour être rendus par /blog/{slug} et listés dans /blog sans changement côté frontend.
"""
import hmac
import logging
import os
import re
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from core.db import db
from core.security import admin_user
from routes.autoseo import SITE_URL, _download_and_store

router = APIRouter(tags=["babylovegrowth"])
logger = logging.getLogger(__name__)
SOURCE = "babylovegrowth"


def _cfg() -> tuple[str, str]:
    key = os.environ.get("BABYLOVEGROWTH_API_KEY")
    if not key:
        raise HTTPException(503, "BABYLOVEGROWTH_API_KEY non configurée")
    return key, (os.environ.get("BABYLOVEGROWTH_API_BASE") or "https://api.babylovegrowth.ai/api/integrations").rstrip("/")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s[:120] or "article"


def _faq_from_jsonld(faq: dict | None) -> list[dict]:
    out = []
    for q in ((faq or {}).get("mainEntity") or []):
        name = q.get("name")
        ans = (q.get("acceptedAnswer") or {}).get("text")
        if name and ans:
            out.append({"question": name, "answer": ans})
    return out


def _reading_minutes(html: str | None) -> int:
    words = len(re.sub(r"<[^>]+>", " ", html or "").split())
    return max(1, round(words / 200))


async def _upsert(article: dict, event: str) -> str:
    aid = f"blg-{article.get('id')}"
    slug = article.get("slug") or _slugify(article.get("title"))
    hero_src = article.get("hero_image_url") or article.get("featured_image")
    hero = await run_in_threadpool(_download_and_store, hero_src, aid, "hero")
    html = article.get("content_html") or article.get("content") or ""
    created = article.get("created_at") or article.get("publish_date") or _now()
    doc = {
        "autoseo_id": aid, "source": SOURCE, "last_event": event,
        "title": article.get("title"), "slug": slug,
        "published_url": f"{SITE_URL}/blog/{slug}",
        "meta_description": article.get("meta_description") or article.get("excerpt"),
        "excerpt": article.get("excerpt"),
        "content_html": html, "content_markdown": article.get("content_markdown"),
        "hero_image_url": f"/api/blog/media/{aid}/hero" if hero else hero_src,
        "hero_image_storage": hero["storage_path"] if hero else None,
        "hero_image_source": hero_src, "hero_image_alt": article.get("title"),
        "keywords": article.get("keywords") or article.get("tags") or [],
        "seed_keyword": article.get("seedKeyword"),
        "json_ld": article.get("jsonLd"),
        "faq_schema": _faq_from_jsonld(article.get("faqJsonLd")),
        "language_code": (article.get("languageCode") or "fr")[:5],
        "reading_minutes": _reading_minutes(html),
        "status": "published", "published_at": created, "created_at": created,
        "updated_at": _now(), "received_at": _now(),
    }
    res = await db.autoseo_articles.update_one({"autoseo_id": aid},
                                               {"$set": doc, "$setOnInsert": {"first_received_at": _now()}},
                                               upsert=True)
    if res.upserted_id is not None:
        try:
            from routes.newsletter import notify_new_article
            await notify_new_article(doc)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Newsletter notify failed for {slug}: {e}")
    return slug


async def sync_articles(force: bool = False) -> dict:
    """Pull paginé : récupère les articles absents (ou tous si force) et les publie."""
    key, base = _cfg()
    headers = {"X-API-Key": key, "Content-Type": "application/json"}
    known = {d["autoseo_id"] for d in await db.autoseo_articles.find(
        {"source": SOURCE}, {"_id": 0, "autoseo_id": 1}).to_list(5000)}
    created = skipped = errors = 0
    offset, limit = 0, 50
    async with httpx.AsyncClient(timeout=60) as c:
        while True:
            r = await c.get(f"{base}/v1/articles", headers=headers, params={"limit": limit, "offset": offset})
            if r.status_code == 401:
                raise HTTPException(401, "Clé API BabyLoveGrowth refusée")
            r.raise_for_status()
            items = r.json() or []
            for it in items:
                aid = f"blg-{it.get('id')}"
                if aid in known and not force:
                    skipped += 1
                    continue
                try:
                    full = await c.get(f"{base}/v1/articles/{it['id']}", headers=headers)
                    full.raise_for_status()
                    await _upsert(full.json(), "sync")
                    created += 1
                except Exception as e:  # noqa: BLE001
                    errors += 1
                    logger.error(f"BLG sync article {it.get('id')}: {e}")
            if len(items) < limit:
                break
            offset += limit
    res = {"created": created, "skipped": skipped, "errors": errors, "at": _now()}
    await db.app_settings.update_one({"key": "blg_last_sync"}, {"$set": {"key": "blg_last_sync", **res}}, upsert=True)
    return res


async def run_scheduled_sync():
    if not os.environ.get("BABYLOVEGROWTH_API_KEY"):
        return
    try:
        res = await sync_articles()
        if res["created"]:
            logger.info(f"BabyLoveGrowth: {res['created']} nouvel(aux) article(s) publié(s)")
    except Exception as e:  # noqa: BLE001
        logger.error(f"BabyLoveGrowth sync failed: {e}")


@router.get("/admin/babylovegrowth/status")
async def blg_status(_=Depends(admin_user)):
    last = await db.app_settings.find_one({"key": "blg_last_sync"}, {"_id": 0, "key": 0})
    count = await db.autoseo_articles.count_documents({"source": SOURCE})
    recent = await db.autoseo_articles.find(
        {"source": SOURCE}, {"_id": 0, "title": 1, "slug": 1, "published_at": 1, "language_code": 1,
                             "seed_keyword": 1, "hero_image_url": 1}).sort("published_at", -1).to_list(20)
    return {"configured": bool(os.environ.get("BABYLOVEGROWTH_API_KEY")),
            "webhook_url": f"{SITE_URL}/api/webhooks/babylovegrowth",
            "webhook_secret_set": bool(os.environ.get("BABYLOVEGROWTH_WEBHOOK_SECRET")),
            "count": count, "last_sync": last, "recent": recent}


@router.post("/admin/babylovegrowth/sync")
async def blg_sync(force: bool = False, _=Depends(admin_user)):
    try:
        return await sync_articles(force=force)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synchronisation impossible : {str(e)[:200]}")


@router.delete("/admin/babylovegrowth/articles/{slug}")
async def blg_delete(slug: str, _=Depends(admin_user)):
    r = await db.autoseo_articles.delete_one({"source": SOURCE, "slug": slug})
    return {"deleted": r.deleted_count}


@router.post("/webhooks/babylovegrowth")
async def blg_webhook(request: Request, authorization: str | None = Header(None)):
    """Push temps réel (Settings → Integrations → Webhook). Bearer = BABYLOVEGROWTH_WEBHOOK_SECRET."""
    secret = os.environ.get("BABYLOVEGROWTH_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Webhook non configuré")
    if not authorization or not hmac.compare_digest(authorization.strip(), f"Bearer {secret}"):
        raise HTTPException(401, "Invalid or missing authorization token")
    payload = await request.json()
    if not isinstance(payload, dict) or not payload.get("title"):
        return {"ok": True, "ignored": True}
    if payload.get("id") is None:
        payload["id"] = _slugify(payload.get("slug") or payload["title"])
    slug = await _upsert(payload, "webhook")
    return {"ok": True, "url": f"{SITE_URL}/blog/{slug}"}
