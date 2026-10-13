"""Agent CEO (marketing) — mode supervisé.

L'agent GÉNÈRE des brouillons (articles de blog SEO, visuels/flyers) automatiquement, mais
rien n'est publié tant que l'administrateur ne l'a pas approuvé. La génération d'images
respecte le plafond de coûts global (engines/expenses/cap.py, poste « ai_api »).

Collections :
- autoseo_articles : les articles de blog (réutilise le rendu public existant ; source="ceo_agent",
  status="draft" tant que non approuvé, puis "published").
- ceo_assets       : les visuels/flyers générés (status draft/approved/rejected).
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from core.db import db
from core.security import admin_user
from engines import storage
from engines import ceo_media
from engines import emailer
from engines.ai import _complete, _json
from engines.expenses import cap
from engines.expenses.context import bind

log = logging.getLogger("ceo")
router = APIRouter(prefix="/ceo", tags=["ceo"], dependencies=[Depends(admin_user)])

SITE_URL = "https://construpilot.fr"


def _frontend() -> str:
    return (os.environ.get("FRONTEND_URL") or SITE_URL).rstrip("/")
CEO_IMAGE_COST_EUR = float(os.environ.get("CEO_IMAGE_COST_EUR", "0.05"))
AUDIENCE_LABEL = {"particuliers": "particuliers (propriétaires qui font des travaux)",
                  "pros": "artisans et entreprises du BTP"}
CREATIVE_ASPECT = {
    "flyer": "Affiche verticale A4 (portrait, ratio 3:4), hiérarchie claire titre/sous-titre.",
    "social": "Visuel carré 1:1 pour les réseaux sociaux (Instagram/Facebook).",
    "ad_banner": "Bannière large 16:9 pour une publicité display.",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _budget_allows() -> tuple[bool, str | None]:
    """Respecte le plafond 500 € : on bloque la génération d'images (non essentielle) uniquement
    si le plafond est réellement gelé (440 €) ou dépassé (500 €). Les images Nano Banana sont
    débitées sur la clé universelle Emergent (solde distinct), donc une source de coûts périmée
    ne doit pas bloquer la génération supervisée de brouillons."""
    try:
        st = await cap.status()
    except Exception:  # noqa: BLE001 -- si le module coût est indisponible, on n'empêche pas les brouillons
        return True, None
    if st.get("state") in ("exceeded", "frozen"):
        return False, st.get("blocking_reason") or "plafond de coûts atteint"
    return True, None


def _slugify(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[àâä]", "a", text); text = re.sub(r"[éèêë]", "e", text)
    text = re.sub(r"[îï]", "i", text); text = re.sub(r"[ôö]", "o", text)
    text = re.sub(r"[ûü]", "u", text); text = re.sub(r"ç", "c", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:70] or "article"


async def _unique_slug(base: str) -> str:
    slug = base
    if await db.autoseo_articles.find_one({"slug": slug}, {"_id": 1}):
        slug = f"{base}-{secrets.token_hex(3)}"
    return slug


# ============================== Génération ==============================

class BlogIn(BaseModel):
    topic: str = Field(min_length=3)
    keywords: list[str] = []
    audience: str = "particuliers"
    with_image: bool = True


@router.post("/blog/draft")
async def blog_draft(body: BlogIn, admin=Depends(admin_user)) -> dict:
    bind(admin)
    aud = AUDIENCE_LABEL.get(body.audience, AUDIENCE_LABEL["particuliers"])
    system = ("Tu es le rédacteur en chef SEO de ConstruPilot, un SaaS BTP français. "
              f"Tu écris pour les {aud}. Articles utiles, concrets et optimisés SEO. "
              "RÈGLE ABSOLUE : n'invente AUCUNE statistique chiffrée, AUCUN montant d'aide, "
              "AUCUNE norme ou référence réglementaire précise dont tu n'es pas certain ; "
              "reste général et honnête, invite à vérifier les montants officiels. Écris en français.")
    kw = ", ".join(body.keywords) if body.keywords else "(libre)"
    prompt = (f"Sujet : {body.topic}\nMots-clés cibles : {kw}\nAudience : {aud}\n\n"
              "Rédige un article de blog complet (600 à 900 mots) en HTML sémantique "
              "(<h2>, <h3>, <p>, <ul><li>) SANS <html>/<head>/<body> ni style inline. "
              "Intro accrocheuse, corps structuré, conclusion avec un appel à l'action vers ConstruPilot.\n\n"
              "Réponds UNIQUEMENT en JSON : {\"title\":..., \"slug\":... (court, en-minuscules-avec-tirets), "
              "\"meta_description\":... (max 155 caractères), \"keywords\":[...], \"content_html\":\"...\", "
              "\"hero_image_prompt\":\"description EN ANGLAIS pour générer une photo hero professionnelle "
              "(chantier/rénovation), sans aucun texte dans l'image\"}")
    raw = await _complete(system, prompt, feature="ceo_blog")
    data = _json(raw, {})
    if not data.get("content_html") or not data.get("title"):
        raise HTTPException(502, "Génération de l'article impossible, réessayez.")

    article_id = "ceo_" + secrets.token_hex(8)
    slug = await _unique_slug(_slugify(data.get("slug") or data["title"]))
    warnings: list[str] = []
    hero_storage = hero_url = None

    if body.with_image and (data.get("hero_image_prompt")):
        ok, reason = await _budget_allows()
        if not ok:
            warnings.append(f"Image hero non générée : {reason}")
        else:
            try:
                img_prompt = ("Professional editorial hero photograph for a French construction/renovation blog. "
                              f"{data['hero_image_prompt']}. Landscape 16:9, natural light, no text, no logo.")
                img_bytes, ctype = await ceo_media.generate_image(img_prompt, session_id=article_id)
                ext = "png" if "png" in ctype else "jpg"
                hero_storage = f"{storage.APP_NAME}/ceo/{article_id}/hero.{ext}"
                await run_in_threadpool(storage.put_object, hero_storage, img_bytes, ctype)
                hero_url = f"/api/blog/media/{article_id}/hero"
            except Exception as exc:  # noqa: BLE001
                log.error("CEO hero image failed (%s)", type(exc).__name__)
                warnings.append("Image hero non générée (erreur du générateur).")

    doc = {
        "autoseo_id": article_id, "source": "ceo_agent", "status": "draft",
        "title": data["title"], "slug": slug,
        "published_url": f"{SITE_URL}/blog/{slug}",
        "meta_description": (data.get("meta_description") or "")[:160],
        "content_html": data["content_html"], "content_markdown": None,
        "hero_image_url": hero_url, "hero_image_storage": hero_storage,
        "hero_image_alt": data.get("title"),
        "keywords": data.get("keywords") or body.keywords or [],
        "language_code": "fr", "audience": body.audience,
        "topic": body.topic,
        "created_at": _now(), "created_by": admin.get("user_id"),
        "published_at": None, "received_at": _now(),
    }
    await db.autoseo_articles.insert_one(dict(doc))
    doc.pop("_id", None)
    doc["warnings"] = warnings
    return doc


class CreativeIn(BaseModel):
    brief: str = Field(min_length=3)
    format: str = "flyer"
    audience: str = "particuliers"


@router.post("/creative")
async def creative(body: CreativeIn, admin=Depends(admin_user)) -> dict:
    bind(admin)
    ok, reason = await _budget_allows()
    if not ok:
        raise HTTPException(402, f"Plafond de coûts : {reason}")
    aud = AUDIENCE_LABEL.get(body.audience, AUDIENCE_LABEL["particuliers"])
    aspect = CREATIVE_ASPECT.get(body.format, CREATIVE_ASPECT["flyer"])
    prompt = (f"{aspect}\nMarque : ConstruPilot (SaaS BTP français). Cible : {aud}.\n"
              f"Brief : {body.brief}\n"
              "Design moderne et épuré, palette crème/vert profond/cuivre. "
              "Tu peux intégrer un titre et un sous-titre courts en FRANÇAIS, lisibles et bien composés, "
              "plus un petit appel à l'action. Mise en page professionnelle de niveau agence.")
    asset_id = "ast_" + secrets.token_hex(8)
    try:
        img_bytes, ctype = await ceo_media.generate_image(prompt, session_id=asset_id)
    except Exception as exc:  # noqa: BLE001
        log.error("CEO creative failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Génération du visuel impossible, réessayez.")
    ext = "png" if "png" in ctype else "jpg"
    path = f"{storage.APP_NAME}/ceo/assets/{asset_id}.{ext}"
    await run_in_threadpool(storage.put_object, path, img_bytes, ctype)
    doc = {"asset_id": asset_id, "kind": "creative", "format": body.format, "audience": body.audience,
           "brief": body.brief, "storage_path": path, "content_type": ctype, "status": "draft",
           "created_at": _now(), "created_by": admin.get("user_id")}
    await db.ceo_assets.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ============================== Campagnes e-mail ==============================

EMAIL_PLAN = {
    "promo": (1, "un e-mail promotionnel (offre / nouveauté), ton chaleureux et direct, un seul appel à l'action"),
    "newsletter": (1, "un e-mail newsletter (actualités + 2-3 conseils utiles), ton informatif et sympathique"),
    "nurture": (3, "une SÉQUENCE de 3 e-mails d'accompagnement (onboarding) à envoyer à J+0, J+2 et J+5, "
                   "chacun apportant une valeur concrète et poussant doucement vers l'essai du produit"),
}
EMAIL_TYPE_LABEL = {"promo": "Promotionnel", "newsletter": "Newsletter", "nurture": "Séquence nurture"}


class EmailIn(BaseModel):
    topic: str = Field(min_length=3)
    email_type: str = "promo"
    audience: str = "particuliers"


@router.post("/email/draft")
async def email_draft(body: EmailIn, admin=Depends(admin_user)) -> dict:
    bind(admin)
    aud = AUDIENCE_LABEL.get(body.audience, AUDIENCE_LABEL["particuliers"])
    etype = body.email_type if body.email_type in EMAIL_PLAN else "promo"
    count, brief = EMAIL_PLAN[etype]
    system = ("Tu es responsable CRM e-mail de ConstruPilot, un SaaS BTP français. "
              f"Tu écris pour les {aud}. Des e-mails marketing clairs, chaleureux et efficaces, prêts à envoyer. "
              "RÈGLE ABSOLUE : n'invente AUCUNE statistique chiffrée, AUCUN montant d'aide, AUCUN pourcentage de "
              "remise, AUCUNE date limite ni promesse de performance ; reste honnête et général, invite à essayer "
              "ou à vérifier les informations officielles. Écris en français.")
    prompt = (f"Sujet de la campagne : {body.topic}\nAudience : {aud}\nType : {brief}\n\n"
              "Rédige le corps en HTML sémantique simple (<p>, <ul><li>, <strong>, <h2>) SANS <html>/<head>/<body> "
              "ni style inline. Chaque e-mail doit proposer 2 objets A/B et un pré-header court.\n\n"
              "Réponds UNIQUEMENT en JSON : {\"campaign_name\":\"...\", \"emails\":["
              "{\"step\":1, \"send_hint\":\"J+0\", \"subjects\":[\"objet A\",\"objet B\"], "
              "\"preheader\":\"...\", \"body_html\":\"...\", \"cta_label\":\"...\"}]} "
              f"— EXACTEMENT {count} e-mail(s) dans le tableau \"emails\".")
    raw = await _complete(system, prompt, feature="ceo_email")
    data = _json(raw, {})
    emails = data.get("emails") or []
    if not emails or not isinstance(emails, list):
        raise HTTPException(502, "Génération de l'e-mail impossible, réessayez.")
    copy_id = "cpy_" + secrets.token_hex(8)
    doc = {
        "copy_id": copy_id, "kind": "email", "email_type": etype, "audience": body.audience,
        "topic": body.topic, "status": "draft",
        "campaign_name": data.get("campaign_name") or body.topic,
        "payload": {"emails": emails},
        "created_at": _now(), "created_by": admin.get("user_id"),
    }
    await db.ceo_copy.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ============================== Textes d'annonces (ad copy) ==============================

class AdIn(BaseModel):
    brief: str = Field(min_length=3)
    audience: str = "particuliers"


@router.post("/ad/draft")
async def ad_draft(body: AdIn, admin=Depends(admin_user)) -> dict:
    bind(admin)
    aud = AUDIENCE_LABEL.get(body.audience, AUDIENCE_LABEL["particuliers"])
    system = ("Tu es media buyer et copywriter publicitaire de ConstruPilot (SaaS BTP français). "
              f"Tu écris pour les {aud}. Tu produis des accroches prêtes à coller dans les régies publicitaires. "
              "RÈGLE ABSOLUE : n'invente AUCUN chiffre, pourcentage, prix ni promesse de résultat ; pas de "
              "superlatifs trompeurs ni de mentions réglementées. Écris en français.")
    prompt = (f"Brief : {body.brief}\nAudience : {aud}\n\n"
              "Produis des variantes pour 3 plateformes en respectant STRICTEMENT les limites de caractères :\n"
              "- Google Ads : jusqu'à 10 titres (≤ 30 caractères), 4 descriptions (≤ 90 caractères), 10 mots-clés.\n"
              "- Meta (Facebook/Instagram) : 3 textes principaux (≈ 125 car.), 3 titres (≤ 40 car.), 2 descriptions (≤ 30 car.).\n"
              "- LinkedIn : 2 textes d'introduction (≈ 150 car.), 2 titres (≤ 70 car.).\n\n"
              "Réponds UNIQUEMENT en JSON : {\"campaign_name\":\"...\", "
              "\"google\":{\"headlines\":[...], \"descriptions\":[...], \"keywords\":[...]}, "
              "\"meta\":{\"primary_texts\":[...], \"headlines\":[...], \"descriptions\":[...]}, "
              "\"linkedin\":{\"intro_texts\":[...], \"headlines\":[...]}}")
    raw = await _complete(system, prompt, feature="ceo_ad")
    data = _json(raw, {})
    if not (data.get("google") or data.get("meta") or data.get("linkedin")):
        raise HTTPException(502, "Génération des annonces impossible, réessayez.")
    copy_id = "cpy_" + secrets.token_hex(8)
    doc = {
        "copy_id": copy_id, "kind": "ad", "audience": body.audience, "brief": body.brief,
        "status": "draft", "campaign_name": data.get("campaign_name") or body.brief[:60],
        "payload": {k: data.get(k) or {} for k in ("google", "meta", "linkedin")},
        "created_at": _now(), "created_by": admin.get("user_id"),
    }
    await db.ceo_copy.insert_one(dict(doc))
    doc.pop("_id", None)
    return doc


# ============================== Roteiros de vídeo (trilingue + storyboard) ==============================

class VideoIn(BaseModel):
    brief: str = Field(min_length=3)
    audience: str = "particuliers"
    duration: int = 30


async def _run_storyboard(copy_id: str, prompts: list[str]) -> None:
    """Génère jusqu'à 4 images de storyboard en arrière-plan (Nano Banana), respecte le plafond."""
    ok, reason = await _budget_allows()
    if not ok:
        await db.ceo_copy.update_one({"copy_id": copy_id},
                                     {"$set": {"storyboard_warning": f"Images non générées : {reason}"}})
        return
    for i, p in enumerate(prompts[:4]):
        asset_id = "ast_" + secrets.token_hex(8)
        try:
            full = (f"Cinematic storyboard frame for a ConstruPilot (French construction SaaS) video ad. {p}. "
                    "Landscape 16:9, natural light, photorealistic, no text, no caption, no watermark.")
            img_bytes, ctype = await ceo_media.generate_image(full, session_id=asset_id)
            ext = "png" if "png" in ctype else "jpg"
            path = f"{storage.APP_NAME}/ceo/storyboard/{asset_id}.{ext}"
            await run_in_threadpool(storage.put_object, path, img_bytes, ctype)
            await db.ceo_assets.insert_one({
                "asset_id": asset_id, "kind": "storyboard", "copy_id": copy_id, "index": i,
                "brief": p, "storage_path": path, "content_type": ctype, "status": "draft",
                "created_at": _now()})
            await db.ceo_copy.update_one(
                {"copy_id": copy_id, "payload.storyboard.index": i},
                {"$set": {"payload.storyboard.$.asset_id": asset_id, "payload.storyboard.$.status": "ready",
                          "payload.storyboard.$.url": f"/api/ceo/asset/{asset_id}"}})
        except Exception as exc:  # noqa: BLE001
            log.error("CEO storyboard frame %s failed (%s)", i, type(exc).__name__)
            await db.ceo_copy.update_one(
                {"copy_id": copy_id, "payload.storyboard.index": i},
                {"$set": {"payload.storyboard.$.status": "error"}})


@router.post("/video/draft")
async def video_draft(body: VideoIn, admin=Depends(admin_user)) -> dict:
    bind(admin)
    aud = AUDIENCE_LABEL.get(body.audience, AUDIENCE_LABEL["particuliers"])
    system = ("Tu es scénariste publicitaire vidéo trilingue (français, portugais, anglais) pour ConstruPilot, "
              f"un SaaS BTP français. Tu écris pour les {aud}. Tu produis des roteiros courts, rythmés et "
              "tournables. RÈGLE ABSOLUE : n'invente AUCUN chiffre, pourcentage, prix ni promesse de résultat ; "
              "reste honnête et concret.")
    prompt = (f"Brief : {body.brief}\nAudience : {aud}\nDurée cible : {body.duration} secondes.\n\n"
              "Découpe en scènes (4 à 6). Pour CHAQUE scène, donne la voix-off en français (fr), portugais (pt) "
              "et anglais (en), une description visuelle (visual) et le texte à l'écran (on_screen). "
              "Ajoute un CTA final trilingue, l'ambiance musicale (music_mood) et EXACTEMENT 4 'storyboard_prompts' "
              "EN ANGLAIS (descriptions d'images clés, sans aucun texte dans l'image).\n\n"
              "Réponds UNIQUEMENT en JSON : {\"campaign_name\":\"...\", \"duration_seconds\":30, "
              "\"music_mood\":\"...\", \"scenes\":[{\"n\":1, \"t_start\":0, \"t_end\":4, \"visual\":\"...\", "
              "\"fr\":\"...\", \"pt\":\"...\", \"en\":\"...\", \"on_screen\":\"...\"}], "
              "\"cta\":{\"fr\":\"...\",\"pt\":\"...\",\"en\":\"...\"}, \"storyboard_prompts\":[\"...\",\"...\",\"...\",\"...\"]}")
    raw = await _complete(system, prompt, feature="ceo_video")
    data = _json(raw, {})
    scenes = data.get("scenes") or []
    if not scenes or not isinstance(scenes, list):
        raise HTTPException(502, "Génération du roteiro impossible, réessayez.")
    prompts = [p for p in (data.get("storyboard_prompts") or []) if isinstance(p, str)][:4]
    copy_id = "cpy_" + secrets.token_hex(8)
    storyboard = [{"index": i, "prompt": prompts[i] if i < len(prompts) else "",
                   "status": "pending", "asset_id": None, "url": None} for i in range(len(prompts) or 4)]
    doc = {
        "copy_id": copy_id, "kind": "video", "audience": body.audience, "brief": body.brief,
        "status": "draft", "campaign_name": data.get("campaign_name") or body.brief[:60],
        "payload": {"duration_seconds": data.get("duration_seconds") or body.duration,
                    "music_mood": data.get("music_mood") or "", "scenes": scenes,
                    "cta": data.get("cta") or {}, "storyboard": storyboard},
        "created_at": _now(), "created_by": admin.get("user_id"),
    }
    await db.ceo_copy.insert_one(dict(doc))
    doc.pop("_id", None)
    if prompts:
        asyncio.create_task(_run_storyboard(copy_id, prompts))
    return doc


# ============================== Revue / approbation ==============================

@router.get("/drafts")
async def list_drafts() -> dict:
    blog = await db.autoseo_articles.find(
        {"source": "ceo_agent"}, {"_id": 0, "hero_image_storage": 0}
    ).sort("created_at", -1).to_list(100)
    assets = await db.ceo_assets.find(
        {}, {"_id": 0, "storage_path": 0}
    ).sort("created_at", -1).to_list(100)
    copies = await db.ceo_copy.find({}, {"_id": 0}).sort("created_at", -1).to_list(200)
    emails = [c for c in copies if c.get("kind") == "email"]
    ads = [c for c in copies if c.get("kind") == "ad"]
    videos = [c for c in copies if c.get("kind") == "video"]
    return {"blog": blog, "assets": assets, "emails": emails, "ads": ads, "videos": videos}


@router.post("/copy/{copy_id}/{action}")
async def review_copy(copy_id: str, action: str) -> dict:
    if action not in ("publish", "reject"):
        raise HTTPException(400, "Action inconnue")
    status = "approved" if action == "publish" else "rejected"
    res = await db.ceo_copy.update_one({"copy_id": copy_id},
                                       {"$set": {"status": status, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Contenu introuvable")
    return {"status": status, "copy_id": copy_id}


# ============================== Envoi des campagnes e-mail (Resend) ==============================

def _render_email_html(em: dict, unsub_url: str | None) -> str:
    subject = (em.get("subjects") or ["ConstruPilot"])[0]
    return emailer.wrap_html(
        title=subject, body=em.get("body_html") or "",
        cta_url=SITE_URL, cta_label=em.get("cta_label") or "Découvrir ConstruPilot",
        unsubscribe_url=unsub_url)


async def _get_email_copy(copy_id: str) -> dict:
    doc = await db.ceo_copy.find_one({"copy_id": copy_id, "kind": "email"}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Campagne e-mail introuvable")
    emails = (doc.get("payload") or {}).get("emails") or []
    if not emails:
        raise HTTPException(400, "Cette campagne ne contient aucun e-mail.")
    return doc


class SendTestIn(BaseModel):
    to: str | None = None


@router.post("/email/{copy_id}/test")
async def email_send_test(copy_id: str, body: SendTestIn, admin=Depends(admin_user)) -> dict:
    doc = await _get_email_copy(copy_id)
    to = (body.to or admin.get("email") or "").strip()
    if not to:
        raise HTTPException(400, "Aucune adresse de test (renseignez votre e-mail).")
    em = doc["payload"]["emails"][0]
    subject = (em.get("subjects") or ["ConstruPilot"])[0]
    html = _render_email_html(em, f"{_frontend()}/api/newsletter/unsubscribe?token=test")
    try:
        await emailer.send_email(to, f"[Test] {subject}", html, from_name="ConstruPilot")
    except Exception as exc:  # noqa: BLE001
        log.error("CEO email test failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Envoi du test impossible (vérifiez la configuration Resend).")
    return {"ok": True, "to": to}


async def _run_email_campaign(copy_id: str) -> None:
    doc = await db.ceo_copy.find_one({"copy_id": copy_id}, {"_id": 0})
    if not doc:
        return
    em = doc["payload"]["emails"][0]
    subject = (em.get("subjects") or ["ConstruPilot"])[0]
    subs = await db.newsletter_subscribers.find(
        {"unsubscribed_at": None}, {"_id": 0, "email": 1, "token": 1}).to_list(10000)
    total = len(subs)
    await db.ceo_copy.update_one({"copy_id": copy_id}, {"$set": {
        "send_status": "sending", "send_total": total, "send_count": 0, "send_failed": 0,
        "send_started_at": _now()}})
    sent = failed = 0
    for s in subs:
        unsub = f"{_frontend()}/api/newsletter/unsubscribe?token={s.get('token', '')}"
        try:
            await emailer.send_email(s["email"], subject, _render_email_html(em, unsub), from_name="ConstruPilot")
            sent += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            log.warning("CEO campaign send failed %s (%s)", s.get("email"), type(exc).__name__)
        if (sent + failed) % 10 == 0:
            await db.ceo_copy.update_one({"copy_id": copy_id},
                                         {"$set": {"send_count": sent, "send_failed": failed}})
    await db.ceo_copy.update_one({"copy_id": copy_id}, {"$set": {
        "send_status": "sent", "send_count": sent, "send_failed": failed, "sent_at": _now()}})
    await db.newsletter_sends.insert_one({
        "campaign_id": copy_id, "title": subject, "kind": "ceo_campaign",
        "sent": sent, "failed": failed, "sent_at": _now()})


@router.post("/email/{copy_id}/send")
async def email_send_campaign(copy_id: str) -> dict:
    doc = await _get_email_copy(copy_id)
    if doc.get("status") != "approved":
        raise HTTPException(400, "Approuvez d'abord la campagne avant de l'envoyer.")
    if doc.get("send_status") == "sending":
        return {"status": "sending", "total": doc.get("send_total", 0), "already": True}
    total = await db.newsletter_subscribers.count_documents({"unsubscribed_at": None})
    if total == 0:
        raise HTTPException(400, "Aucun abonné newsletter actif à qui envoyer.")
    asyncio.create_task(_run_email_campaign(copy_id))
    return {"status": "sending", "total": total}


@router.post("/blog/{article_id}/publish")
async def publish_blog(article_id: str) -> dict:
    res = await db.autoseo_articles.update_one(
        {"autoseo_id": article_id, "source": "ceo_agent"},
        {"$set": {"status": "published", "published_at": _now(), "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Brouillon introuvable")
    return {"published": True, "article_id": article_id}


@router.post("/blog/{article_id}/reject")
async def reject_blog(article_id: str) -> dict:
    res = await db.autoseo_articles.update_one(
        {"autoseo_id": article_id, "source": "ceo_agent"},
        {"$set": {"status": "rejected", "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Brouillon introuvable")
    return {"rejected": True, "article_id": article_id}


@router.post("/creative/{asset_id}/{action}")
async def review_asset(asset_id: str, action: str) -> dict:
    if action not in ("publish", "reject"):
        raise HTTPException(400, "Action inconnue")
    status = "approved" if action == "publish" else "rejected"
    res = await db.ceo_assets.update_one({"asset_id": asset_id},
                                         {"$set": {"status": status, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Visuel introuvable")
    return {"status": status, "asset_id": asset_id}


@router.get("/asset/{asset_id}")
async def asset_media(asset_id: str):
    doc = await db.ceo_assets.find_one({"asset_id": asset_id}, {"_id": 0, "storage_path": 1, "content_type": 1})
    if not doc or not doc.get("storage_path"):
        raise HTTPException(404, "Introuvable")
    try:
        data, ctype = await run_in_threadpool(storage.get_object, doc["storage_path"])
    except Exception:  # noqa: BLE001
        raise HTTPException(404, "Média indisponible")
    return StreamingResponse(io.BytesIO(data), media_type=ctype or doc.get("content_type") or "image/png",
                             headers={"Cache-Control": "private, max-age=600"})


# ============================== Calendrier éditorial ==============================

# Thèmes saisonniers BTP par mois (1=janvier). Déterministe, pas d'appel IA.
_SEASONAL = {
    1: [("Rénovation énergétique : par où commencer en 2026", "particuliers", ["rénovation énergétique", "aides"]),
        ("Isolation des combles : méthodes et bénéfices", "particuliers", ["isolation", "combles"])],
    2: [("Rénover sa salle de bain : budget et étapes", "particuliers", ["salle de bain", "rénovation"]),
        ("Devis BTP : comment chiffrer juste et vite", "pros", ["devis", "chiffrage"])],
    3: [("Ravalement de façade : quand et comment", "particuliers", ["façade", "ravalement"]),
        ("Métré de plans : gagner du temps sur vos chantiers", "pros", ["métré", "plans"])],
    4: [("Aménager sa terrasse : budget et matériaux", "particuliers", ["terrasse", "extérieur"]),
        ("Organiser le planning d'un chantier", "pros", ["planning", "chantier"])],
    5: [("Agrandissement de maison : permis et coûts", "particuliers", ["agrandissement", "permis"]),
        ("Facturation électronique : se préparer", "pros", ["facturation électronique", "factur-x"])],
    6: [("Confort d'été : climatisation et ventilation", "particuliers", ["climatisation", "confort"]),
        ("Suivre la rentabilité de ses chantiers", "pros", ["marge", "rentabilité"])],
    7: [("Toiture : diagnostic avant l'automne", "particuliers", ["toiture", "diagnostic"]),
        ("Gérer ses sous-traitants sereinement", "pros", ["sous-traitance", "chantier"])],
    8: [("Rentrée travaux : planifier son projet", "particuliers", ["travaux", "planification"]),
        ("Préparer son carnet de commandes d'automne", "pros", ["prospection", "leads"])],
    9: [("Isolation avant l'hiver : murs et combles", "particuliers", ["isolation", "hiver"]),
        ("Comparer les plans avant/après d'un chantier", "pros", ["comparaison plans", "avenant"])],
    10: [("Chauffage : pompe à chaleur ou chaudière ?", "particuliers", ["pompe à chaleur", "chauffage"]),
         ("Automatiser ses devis multi-niveaux", "pros", ["devis", "automatisation"])],
    11: [("Salle de bain : tendances et rénovation d'hiver", "particuliers", ["salle de bain", "tendances"]),
         ("Clôturer l'année : bilan et budget chantiers", "pros", ["bilan", "budget"])],
    12: [("Préparer ses travaux pour la nouvelle année", "particuliers", ["travaux", "projet"]),
         ("Objectifs commerciaux BTP pour l'année à venir", "pros", ["commercial", "objectifs"])],
}


@router.get("/calendar")
async def editorial_calendar() -> dict:
    now = datetime.now(timezone.utc)
    this_m = now.month
    next_m = 1 if this_m == 12 else this_m + 1
    months = [("Ce mois-ci", this_m), ("Le mois prochain", next_m)]
    slots = []
    for label, m in months:
        for title, audience, kws in _SEASONAL.get(m, []):
            slots.append({"period": label, "month": m, "title": title,
                          "audience": audience, "keywords": kws,
                          "rationale": f"Sujet saisonnier pour {AUDIENCE_LABEL[audience]}."})
    return {"slots": slots, "generated_at": _now()}
