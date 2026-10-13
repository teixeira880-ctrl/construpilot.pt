"""Newsletter du blog : inscription sous chaque article, envoi automatique des nouveaux guides."""
import logging
import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.db import db
from core.security import admin_user

router = APIRouter(prefix="/newsletter", tags=["newsletter"])
logger = logging.getLogger(__name__)
SITE_URL = "https://construpilot.pt"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _frontend() -> str:
    return (os.environ.get("FRONTEND_URL") or SITE_URL).rstrip("/")


class SubscribeIn(BaseModel):
    email: str
    lang: str = "pt"
    source: str = ""


@router.post("/subscribe")
async def subscribe(body: SubscribeIn, request: Request):
    email = (body.email or "").strip().lower()
    if not EMAIL_RE.match(email) or email.endswith("@example.com"):
        raise HTTPException(400, "Endereço de email inválido")
    ip = (request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip")
          or (request.client.host if request.client else "") or "").split(",")[0].strip()
    recent = await db.rate_limits.count_documents({"key": f"nl:{ip}"})
    if recent >= 10:
        raise HTTPException(429, "Demasiadas tentativas, tente novamente dentro de alguns minutos")
    await db.rate_limits.insert_one({"key": f"nl:{ip}", "at": datetime.now(timezone.utc)})
    lang = "pt" if body.lang == "pt" else "pt"
    existing = await db.newsletter_subscribers.find_one({"email": email}, {"_id": 0})
    if existing and not existing.get("unsubscribed_at"):
        return {"ok": True, "already": True}
    token = secrets.token_urlsafe(24)
    await db.newsletter_subscribers.update_one(
        {"email": email},
        {"$set": {"email": email, "lang": lang, "token": token, "source": body.source[:60],
                  "unsubscribed_at": None, "subscribed_at": _now()},
         "$setOnInsert": {"created_at": _now()}}, upsert=True)
    try:
        from engines.emailer import send_email
        unsub = f"{_frontend()}/api/newsletter/unsubscribe?token={token}"
        if lang == "pt":
            subj, html = "Bem-vindo ao jornal ConstruPilot", (
                f"<p>Obrigado! Vai receber os nossos novos guias de construção e renovação.</p>"
                f"<p><a href='{_frontend()}/blog'>Ver o blog</a></p>"
                f"<p style='font-size:11px;color:#888'><a href='{unsub}'>Cancelar a subscrição</a></p>")
        else:
            subj, html = "Bem-vindo ao jornal ConstruPilot", (
                f"<p>Obrigado! Receberá os nossos novos guias de obras, preços e métodos logo que forem publicados.</p><p><a href='{_frontend()}/blog'>Découvrir le blog</a></p><p style='font-size:11px;color:#888'><a href='{unsub}'>Cancelar a subscrição</a></p>")
        await send_email(email, subj, html, from_name="ConstruPilot")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Newsletter welcome email failed for {email}: {e}")
    return {"ok": True}


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(token: str):
    r = await db.newsletter_subscribers.update_one({"token": token}, {"$set": {"unsubscribed_at": _now()}})
    msg = "Cancelou a subscrição do jornal ConstruPilot." if r.matched_count else "Ligação inválida ou já utilizada."
    return HTMLResponse(f"<html><body style='font-family:sans-serif;padding:40px;text-align:center'>"
                        f"<h2>{msg}</h2><a href='{_frontend()}/blog'>Retour au blog</a></body></html>")


@router.get("/admin/stats")
async def newsletter_stats(_=Depends(admin_user)):
    active = await db.newsletter_subscribers.count_documents({"unsubscribed_at": None})
    total = await db.newsletter_subscribers.count_documents({})
    sent = await db.newsletter_sends.find({}, {"_id": 0}).sort("sent_at", -1).to_list(10)
    return {"active": active, "total": total, "recent_sends": sent}


async def notify_new_article(article: dict) -> int:
    """Envia o artigo apenas aos subscritores PT confirmados.

    Comportamento: desativado por defeito via flag `BLG_NOTIFY_NEWSLETTER`.
    Quando ativo, só são contactados subscritores com `unsubscribed_at=None`,
    `confirmed_at` (duplo opt-in) definido e idioma `pt`.
    """
    if (os.environ.get("BLG_NOTIFY_NEWSLETTER", "false") or "").strip().lower() not in ("1", "true", "yes", "on"):
        logger.info("Newsletter notify skipped (BLG_NOTIFY_NEWSLETTER=false)")
        return 0
    slug = article.get("slug")
    if not slug or await db.newsletter_sends.find_one({"slug": slug}):
        return 0
    if not (article.get("language_code") or "").lower().startswith("pt"):
        return 0
    lang = "pt"
    subs = await db.newsletter_subscribers.find(
        {"unsubscribed_at": None, "lang": lang, "confirmed_at": {"$ne": None}},
        {"_id": 0, "email": 1, "token": 1}).to_list(10000)
    if not subs:
        return 0
    from engines.emailer import send_email
    url = f"{_frontend()}/blog/{slug}"
    hero = article.get("hero_image_url") or ""
    if hero.startswith("/"):
        hero = _frontend() + hero
    title = article.get("title") or "Novo artigo"
    excerpt = article.get("excerpt") or article.get("meta_description") or ""
    sent = 0
    for s in subs:
        unsub = f"{_frontend()}/api/newsletter/unsubscribe?token={s['token']}"
        cta = "Ler o artigo"
        html = (f"<div style='font-family:sans-serif;max-width:560px'>"
                + (f"<img src='{hero}' alt='' style='width:100%;border-radius:8px'/>" if hero else "")
                + f"<h2 style='margin:16px 0 8px'>{title}</h2><p style='color:#444'>{excerpt}</p><p><a href='{url}' style='background:#2ECC71;color:#fff;padding:10px 18px;border-radius:999px;text-decoration:none;font-weight:bold'>{cta}</a></p><p style='font-size:11px;color:#888'>ConstruPilot · <a href='{unsub}'>Cancelar a subscrição</a></p></div>")
        try:
            await send_email(s["email"], title, html, from_name="ConstruPilot")
            sent += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Newsletter send failed {s['email']}: {e}")
    await db.newsletter_sends.insert_one({"slug": slug, "title": title, "lang": lang, "sent": sent, "sent_at": _now()})
    return sent
