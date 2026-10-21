"""Webhook AutoSEO (https://getautoseo.com) + rendu public des articles.

IMPORTANT : ce module ne crée QUE la nouvelle collection MongoDB `autoseo_articles`.
Il ne touche à aucune donnée / collection existante.

Endpoints :
- POST /api/webhooks/autoseo        : réception des articles (Bearer + HMAC optionnel, upsert)
- GET  /api/blog/autoseo            : liste des articles publiés (sans le corps)
- GET  /api/blog/autoseo/{slug}     : un article complet (content_html) pour le rendu
- GET  /api/blog/media/{id}/{kind}  : sert l'image (hero|infographic) stockée localement
"""
import hashlib
import hmac
import io
import json
import logging
import os
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from core.db import db
from engines import storage

router = APIRouter(tags=["autoseo"])
logger = logging.getLogger(__name__)

WEBHOOK_TOKEN = os.environ.get("AUTOSEO_WEBHOOK_TOKEN")
SITE_URL = "https://construpilot.pt"  # domaine canonical (identique au reste du code)

_EXT_BY_CTYPE = {
    "image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
    "image/webp": "webp", "image/gif": "gif", "image/avif": "avif",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _download_and_store(url: str | None, article_id, kind: str) -> dict | None:
    """Télécharge l'image distante et la stocke dans l'object storage (pas de hotlink)."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        ctype = (r.headers.get("Content-Type") or "image/jpeg").split(";")[0].strip().lower()
        ext = _EXT_BY_CTYPE.get(ctype, "jpg")
        path = f"{storage.APP_NAME}/autoseo/{article_id}/{kind}.{ext}"
        storage.put_object(path, r.content, ctype)
        return {"storage_path": path, "content_type": ctype}
    except Exception as e:  # ne bloque pas la publication si une image échoue
        logger.error(f"AutoSEO: échec téléchargement image {kind} ({url}): {e}")
        return None


@router.post("/webhooks/autoseo")
async def autoseo_webhook(
    request: Request,
    authorization: str | None = Header(None),
    x_autoseo_signature: str | None = Header(None),
):
    # 1) Bearer token — comparaison stricte, à temps constant
    if not WEBHOOK_TOKEN:
        raise HTTPException(status_code=503, detail="Webhook não configurado (AUTOSEO_WEBHOOK_TOKEN)")
    expected = f"Bearer {WEBHOOK_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization.strip(), expected):
        raise HTTPException(status_code=401, detail="Invalid or missing authorization token")

    raw = await request.body()  # bytes bruts du corps (requis pour la vérif HMAC)

    # 2) HMAC-SHA256 optionnel sur les octets bruts, secret = token
    if x_autoseo_signature:
        digest = hmac.new(WEBHOOK_TOKEN.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        sig = x_autoseo_signature.strip()
        if "=" in sig:  # tolère un préfixe éventuel "sha256=..."
            sig = sig.split("=", 1)[1]
        if not hmac.compare_digest(digest, sig):
            raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = payload.get("event")

    # 3) Ping de test — ne crée aucun article
    if event == "test":
        return {"url": f"{SITE_URL}/test"}

    try:
        article_id = payload.get("id")
        slug = payload.get("slug")
        if article_id is None or not slug:
            raise HTTPException(status_code=422, detail="Missing required field: id or slug")

        # 4) Téléchargement + stockage local des images (hors event loop)
        hero = await run_in_threadpool(_download_and_store, payload.get("heroImageUrl"), article_id, "hero")
        info = await run_in_threadpool(_download_and_store, payload.get("infographicImageUrl"), article_id, "infographic")

        media_base = f"{SITE_URL}/api/blog/media/{article_id}"
        doc = {
            "autoseo_id": article_id,
            "last_event": event,
            "title": payload.get("title"),
            "slug": slug,
            "published_url": payload.get("published_url") or f"{SITE_URL}/blog/{slug}",
            "meta_description": payload.get("metaDescription"),
            "content_html": payload.get("content_html"),
            "content_markdown": payload.get("content_markdown"),
            "hero_image_url": f"{media_base}/hero" if hero else None,
            "hero_image_storage": hero["storage_path"] if hero else None,
            "hero_image_source": payload.get("heroImageUrl"),
            "hero_image_alt": payload.get("heroImageAlt"),
            "infographic_image_url": f"{media_base}/infographic" if info else None,
            "infographic_image_storage": info["storage_path"] if info else None,
            "infographic_image_source": payload.get("infographicImageUrl"),
            "keywords": payload.get("keywords") or [],
            "meta_keywords": payload.get("metaKeywords"),
            "faq_schema": payload.get("faqSchema"),
            "language_code": payload.get("languageCode") or "fr",
            "source_article_id": payload.get("sourceArticleId"),
            "status": payload.get("status") or "published",
            "published_at": payload.get("publishedAt"),
            "updated_at": payload.get("updatedAt"),
            "created_at": payload.get("createdAt"),
            "received_at": _now_iso(),
        }

        # 5) UPSERT sur l'id AutoSEO → published & updated gérés de façon idempotente
        await db.autoseo_articles.update_one(
            {"autoseo_id": article_id},
            {"$set": doc, "$setOnInsert": {"first_received_at": _now_iso()}},
            upsert=True,
        )

        return {"url": f"{SITE_URL}/blog/{slug}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"AutoSEO webhook: erreur de traitement: {e}")
        # 500 → AutoSEO retentera la livraison
        raise HTTPException(status_code=500, detail="Internal processing error")


@router.get("/blog/autoseo")
async def list_autoseo_articles(lang: str | None = None, audience: str | None = None):
    q: dict = {"status": "published"}
    if lang:
        q["language_code"] = lang
    if audience in ("pros", "particuliers"):
        q["audience"] = audience
    docs = await db.autoseo_articles.find(
        q, {"_id": 0, "content_html": 0, "content_markdown": 0, "hero_image_storage": 0,
            "infographic_image_storage": 0}
    ).sort("published_at", -1).to_list(200)
    return {"articles": docs}


@router.get("/blog/autoseo/{slug}")
async def get_autoseo_article(slug: str):
    doc = await db.autoseo_articles.find_one(
        {"slug": slug}, {"_id": 0, "hero_image_storage": 0, "infographic_image_storage": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Article not found")
    return doc


@router.get("/blog/media/{article_id}/{kind}")
async def autoseo_media(article_id: str, kind: str):
    if kind not in ("hero", "infographic"):
        raise HTTPException(status_code=404, detail="Unknown media kind")
    field = "hero_image_storage" if kind == "hero" else "infographic_image_storage"
    ids: list = [article_id]
    if article_id.isdigit():
        ids.append(int(article_id))
    doc = await db.autoseo_articles.find_one({"autoseo_id": {"$in": ids}}, {"_id": 0, field: 1})
    path = doc and doc.get(field)
    if not path:
        raise HTTPException(status_code=404, detail="Media not found")
    try:
        data, ctype = await run_in_threadpool(storage.get_object, path)
    except Exception as e:
        logger.error(f"AutoSEO media fetch failed: {e}")
        raise HTTPException(status_code=404, detail="Media not available")
    return StreamingResponse(
        io.BytesIO(data), media_type=ctype,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/blog/sitemap.xml")
async def blog_sitemap():
    """Sitemap des articles dynamiques (AutoSEO + BabyLoveGrowth), référencé par /sitemap.xml (index)."""
    from fastapi.responses import Response
    from xml.sax.saxutils import escape
    docs = await db.autoseo_articles.find(
        {"status": "published"}, {"_id": 0, "slug": 1, "updated_at": 1, "published_at": 1,
                                  "hero_image_url": 1, "title": 1}
    ).sort("published_at", -1).to_list(5000)
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
             'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for d in docs:
        mod = (d.get("updated_at") or d.get("published_at") or "")[:10]
        img = d.get("hero_image_url") or ""
        if img.startswith("/"):
            img = SITE_URL + img
        parts.append("<url>")
        parts.append(f"<loc>{SITE_URL}/blog/{escape(d['slug'])}</loc>")
        if mod:
            parts.append(f"<lastmod>{mod}</lastmod>")
        parts.append("<changefreq>monthly</changefreq><priority>0.7</priority>")
        if img:
            parts.append(f"<image:image><image:loc>{escape(img)}</image:loc>"
                         f"<image:title>{escape(d.get('title') or '')}</image:title></image:image>")
        parts.append("</url>")
    parts.append("</urlset>")
    return Response("".join(parts), media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})
