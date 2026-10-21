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
from engines import ceo_blog, ceo_daily
from engines import emailer
from engines.ai import _complete, _json
from engines.expenses import cap
from engines.expenses.context import bind

log = logging.getLogger("ceo")
router = APIRouter(prefix="/ceo", tags=["ceo"], dependencies=[Depends(admin_user)])

SITE_URL = "https://construpilot.pt"


def _frontend() -> str:
    return (os.environ.get("FRONTEND_URL") or SITE_URL).rstrip("/")
CEO_IMAGE_COST_EUR = float(os.environ.get("CEO_IMAGE_COST_EUR", "0.05"))
AUDIENCE_LABEL = {"particuliers": "particulares (proprietários que fazem obras)",
                  "pros": "empreiteiros e empresas de construção"}
CREATIVE_ASPECT = {
    "flyer": "Cartaz vertical A4 (retrato, rácio 3:4), hierarquia clara título/subtítulo.",
    "social": "Visual quadrado 1:1 para as redes sociais (Instagram/Facebook).",
    "ad_banner": "Banner largo 16:9 para publicidade display.",
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
        return False, st.get("blocking_reason") or "teto de custos atingido"
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
    try:
        return await ceo_blog.generate_article(body.topic, body.keywords, body.audience,
                                               with_image=body.with_image,
                                               created_by=admin.get("user_id"), origin="manual")
    except ValueError:
        raise HTTPException(502, "Geração do artigo impossível, tente novamente.")


# ============================== Produção diária ==============================

class DailySettingsIn(BaseModel):
    enabled: bool | None = None
    count: int | None = Field(default=None, ge=0, le=30)
    auto_publish: bool | None = None
    max_auto_per_day: int | None = Field(default=None, ge=0, le=30)
    with_image: bool | None = None


@router.get("/daily")
async def daily_overview() -> dict:
    return {"settings": await ceo_daily.get_settings(), "stats": await ceo_daily.stats()}


@router.put("/daily/settings")
async def daily_settings(body: DailySettingsIn) -> dict:
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    return {"settings": await ceo_daily.save_settings(patch)}


class DailyRunIn(BaseModel):
    count: int | None = Field(default=None, ge=1, le=30)


@router.post("/daily/run")
async def daily_run(body: DailyRunIn, admin=Depends(admin_user)) -> dict:
    """Lança já uma produção (em segundo plano). Não conta para o lock do dia."""
    bind(admin)
    asyncio.create_task(ceo_daily.run_daily(force=True, count=body.count))
    return {"started": True, "count": body.count or (await ceo_daily.get_settings())["count"]}


@router.post("/blog/publish-today")
async def publish_today() -> dict:
    today = datetime.now(ceo_daily.LISBON).date().isoformat()
    now = _now()
    res = await db.autoseo_articles.update_many(
        {"source": "ceo_agent", "status": "draft", "daily_date": today},
        {"$set": {"status": "published", "published_at": now, "updated_at": now}})
    return {"published": res.modified_count}


# ============================== Redes sociais (Facebook, Instagram, LinkedIn) ==============================

class SocialSettingsIn(BaseModel):
    auto_share: bool | None = None
    networks: list[str] | None = None
    max_per_day: int | None = Field(default=None, ge=0, le=20)


@router.get("/social")
async def social_overview() -> dict:
    from engines import social_publish as sp
    posts = await db.social_posts.find({}, {"_id": 0}).sort("created_at", -1).to_list(20)
    return {"status": sp.status(), "settings": await sp.get_settings(), "posts": posts}


@router.put("/social/settings")
async def social_settings(body: SocialSettingsIn) -> dict:
    from engines import social_publish as sp
    return {"settings": await sp.save_settings({k: v for k, v in body.model_dump().items() if v is not None})}


@router.post("/social/share/{article_id}")
async def social_share(article_id: str, admin=Depends(admin_user)) -> dict:
    from engines import social_publish as sp
    bind(admin)
    art = await db.autoseo_articles.find_one({"autoseo_id": article_id, "status": "published"},
                                            {"_id": 0, "content_html": 0, "content_markdown": 0})
    if not art:
        raise HTTPException(404, "Artigo publicado não encontrado")
    return {"results": await sp.share_article(art)}


# ============================== Google Ads — piloto automático ==============================

class AdsSettingsIn(BaseModel):
    enabled: bool | None = None
    monthly_cap_eur: float | None = Field(default=None, ge=0, le=100000)
    max_daily_increase_pct: float | None = Field(default=None, ge=0, le=50)
    pause_cost_no_conv_eur: float | None = Field(default=None, ge=5, le=10000)
    min_daily_budget_eur: float | None = Field(default=None, ge=1, le=1000)
    activate_growth_campaigns: bool | None = None


@router.get("/ads")
async def ads_overview() -> dict:
    from growth import ads_autopilot as ap
    return await ap.overview()


@router.put("/ads/settings")
async def ads_settings(body: AdsSettingsIn) -> dict:
    from growth import ads_autopilot as ap
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if patch.get("enabled") and float(patch.get("monthly_cap_eur") or (await ap.get_settings())["monthly_cap_eur"] or 0) <= 0:
        raise HTTPException(400, "Defina primeiro o teto mensal (€) antes de ligar o piloto automático.")
    return {"settings": await ap.save_settings(patch)}


@router.post("/ads/run")
async def ads_run() -> dict:
    from growth import ads_autopilot as ap
    from growth.ads_connectors import ConnectorError
    try:
        return await ap.run(trigger="manual")
    except ConnectorError as e:
        raise HTTPException(400, str(e))


@router.post("/ads/stop")
async def ads_stop(admin=Depends(admin_user)) -> dict:
    from growth import ads_autopilot as ap
    from growth.ads_connectors import ConnectorError
    try:
        return await ap.kill_switch(admin.get("user_id") or "admin")
    except ConnectorError as e:
        raise HTTPException(400, str(e))


class CreativeIn(BaseModel):
    brief: str = Field(min_length=3)
    format: str = "flyer"
    audience: str = "particuliers"


@router.post("/creative")
async def creative(body: CreativeIn, admin=Depends(admin_user)) -> dict:
    bind(admin)
    ok, reason = await _budget_allows()
    if not ok:
        raise HTTPException(402, f'Limite de custos: {reason}')
    aud = AUDIENCE_LABEL.get(body.audience, AUDIENCE_LABEL["particuliers"])
    aspect = CREATIVE_ASPECT.get(body.format, CREATIVE_ASPECT["flyer"])
    prompt = (f'{aspect}\nMarca: ConstruPilot (SaaS de construção, Portugal). Público-alvo: {aud}.\nBrief : {body.brief}\nDesign moderno e limpo, paleta creme/verde profundo/cobre, com um toque discreto de azulejo português. Podes integrar um título e um subtítulo curtos em PORTUGUÊS EUROPEU, legíveis e bem compostos, mais um pequeno apelo à ação. Paginação profissional de nível de agência.')
    asset_id = "ast_" + secrets.token_hex(8)
    try:
        img_bytes, ctype = await ceo_media.generate_image(prompt, session_id=asset_id)
    except Exception as exc:  # noqa: BLE001
        log.error("CEO creative failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Geração do visual impossível, tente novamente.")
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
    "promo": (1, "um e-mail promocional (oferta / novidade), tom caloroso e direto, um único apelo à ação"),
    "newsletter": (1, "um e-mail de newsletter (notícias + 2-3 conselhos úteis), tom informativo e simpático"),
    "nurture": (3, "uma SEQUÊNCIA de 3 e-mails de acompanhamento (onboarding) a enviar em D+0, D+2 e D+5, cada um trazendo um valor concreto e incentivando suavemente a experimentar o produto"),
}
EMAIL_TYPE_LABEL = {"promo": "Promocional", "newsletter": "Newsletter", "nurture": "Sequência nurture"}


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
    system = (f'És responsável de CRM e-mail do ConstruPilot, um SaaS de construção para o mercado português. Escreves para os {aud}. E-mails de marketing claros, calorosos e eficazes, prontos a enviar. REGRA ABSOLUTA: não inventes NENHUMA estatística, NENHUM montante de apoio, NENHUMA percentagem de desconto, NENHUM prazo nem promessa de desempenho; mantém-te honesto e geral, convida a experimentar ou a verificar as informações oficiais. Escreve em português europeu.')
    prompt = (f'Tema da campanha: {body.topic}\nAudience : {aud}\nType : {brief}\n\nRedige o corpo em HTML semântico simples (<p>, <ul><li>, <strong>, <h2>) SEM <html>/<head>/<body> nem estilos inline. Cada e-mail deve propor 2 assuntos A/B e um pré-cabeçalho curto.\n\nResponde APENAS em JSON: {{"campaign_name":"...", "emails":[{{"step":1, "send_hint":"D+0", "subjects":["assunto A","assunto B"], "preheader":"...", "body_html":"...", "cta_label":"..."}}]}} — EXATAMENTE {count} e-mail(s) na tabela "emails".')
    raw = await _complete(system, prompt, feature="ceo_email")
    data = _json(raw, {})
    emails = data.get("emails") or []
    if not emails or not isinstance(emails, list):
        raise HTTPException(502, "Geração do e-mail impossível, tente novamente.")
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
    system = (f'És media buyer e copywriter publicitário do ConstruPilot (SaaS de construção, Portugal). Escreves para os {aud}. Produzes frases de impacto prontas a colar nas plataformas publicitárias. REGRA ABSOLUTA: não inventes NENHUM número, percentagem, preço nem promessa de resultado; nada de superlativos enganadores nem de menções regulamentadas. Escreve em português europeu.')
    prompt = (f'Brief : {body.brief}\nAudience : {aud}\n\nProduz variantes para 3 plataformas respeitando ESTRITAMENTE os limites de caracteres:\n- Google Ads: até 10 títulos (≤ 30 caracteres), 4 descrições (≤ 90 caracteres), 10 palavras-chave.\n- Meta (Facebook/Instagram): 3 textos principais (≈ 125 car.), 3 títulos (≤ 40 car.), 2 descrições (≤ 30 car.).\n- LinkedIn: 2 textos de introdução (≈ 150 car.), 2 títulos (≤ 70 car.).\n\nResponde APENAS em JSON: {{"campaign_name":"...", "google":{{"headlines":[...], "descriptions":[...], "keywords":[...]}}, "meta":{{"primary_texts":[...], "headlines":[...], "descriptions":[...]}}, "linkedin":{{"intro_texts":[...], "headlines":[...]}}}}')
    raw = await _complete(system, prompt, feature="ceo_ad")
    data = _json(raw, {})
    if not (data.get("google") or data.get("meta") or data.get("linkedin")):
        raise HTTPException(502, "Geração dos anúncios impossível, tente novamente.")
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
    system = (f'És argumentista publicitário de vídeo trilingue (francês, português, inglês) para o ConstruPilot, um SaaS de construção para o mercado português. Escreves para os {aud}. Produzes guiões curtos, ritmados e filmáveis. REGRA ABSOLUTA: não inventes NENHUM número, percentagem, preço nem promessa de resultado; mantém-te honesto e concreto.')
    prompt = (f"""Brief : {body.brief}\nAudience : {aud}\nDuração alvo: {body.duration} segundos.\n\nDivide em cenas (4 a 6). Para CADA cena, dá a voz-off em francês (fr), português europeu (pt) e inglês (en), uma descrição visual (visual) e o texto no ecrã (on_screen, em português europeu). Acrescenta um CTA final trilingue, o ambiente musical (music_mood) e EXATAMENTE 4 'storyboard_prompts' EM INGLÊS (descrições de imagens-chave, sem qualquer texto na imagem).\n\nResponde APENAS em JSON: {{"campaign_name":"...", "duration_seconds":30, "music_mood":"...", "scenes":[{{"n":1, "t_start":0, "t_end":4, "visual":"...", "fr":"...", "pt":"...", "en":"...", "on_screen":"..."}}], "cta":{{"fr":"...","pt":"...","en":"..."}}, "storyboard_prompts":["...","...","...","..."]}}""")
    raw = await _complete(system, prompt, feature="ceo_video")
    data = _json(raw, {})
    scenes = data.get("scenes") or []
    if not scenes or not isinstance(scenes, list):
        raise HTTPException(502, "Geração do guião impossível, tente novamente.")
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
        raise HTTPException(400, "Ação desconhecida")
    status = "approved" if action == "publish" else "rejected"
    res = await db.ceo_copy.update_one({"copy_id": copy_id},
                                       {"$set": {"status": status, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Conteúdo não encontrado")
    return {"status": status, "copy_id": copy_id}


# ============================== Envoi des campagnes e-mail (Resend) ==============================

def _render_email_html(em: dict, unsub_url: str | None) -> str:
    subject = (em.get("subjects") or ["ConstruPilot"])[0]
    return emailer.wrap_html(
        title=subject, body=em.get("body_html") or "",
        cta_url=SITE_URL, cta_label=em.get("cta_label") or "Descobrir ConstruPilot",
        unsubscribe_url=unsub_url)


async def _get_email_copy(copy_id: str) -> dict:
    doc = await db.ceo_copy.find_one({"copy_id": copy_id, "kind": "email"}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Campanha de e-mail não encontrada")
    emails = (doc.get("payload") or {}).get("emails") or []
    if not emails:
        raise HTTPException(400, "Esta campanha não contém nenhum e-mail.")
    return doc


class SendTestIn(BaseModel):
    to: str | None = None


@router.post("/email/{copy_id}/test")
async def email_send_test(copy_id: str, body: SendTestIn, admin=Depends(admin_user)) -> dict:
    doc = await _get_email_copy(copy_id)
    to = (body.to or admin.get("email") or "").strip()
    if not to:
        raise HTTPException(400, "Nenhum endereço de teste (indique o seu e-mail).")
    em = doc["payload"]["emails"][0]
    subject = (em.get("subjects") or ["ConstruPilot"])[0]
    html = _render_email_html(em, f"{_frontend()}/api/newsletter/unsubscribe?token=test")
    try:
        await emailer.send_email(to, f"[Test] {subject}", html, from_name="ConstruPilot")
    except Exception as exc:  # noqa: BLE001
        log.error("CEO email test failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Envio do teste impossível (verifique a configuração Resend).")
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
        raise HTTPException(400, "Aprove primeiro a campanha antes de a enviar.")
    if doc.get("send_status") == "sending":
        return {"status": "sending", "total": doc.get("send_total", 0), "already": True}
    total = await db.newsletter_subscribers.count_documents({"unsubscribed_at": None})
    if total == 0:
        raise HTTPException(400, "Nenhum subscritor ativo da newsletter a quem enviar.")
    asyncio.create_task(_run_email_campaign(copy_id))
    return {"status": "sending", "total": total}


@router.post("/blog/{article_id}/publish")
async def publish_blog(article_id: str) -> dict:
    res = await db.autoseo_articles.update_one(
        {"autoseo_id": article_id, "source": "ceo_agent"},
        {"$set": {"status": "published", "published_at": _now(), "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Rascunho não encontrado")
    return {"published": True, "article_id": article_id}


@router.post("/blog/{article_id}/reject")
async def reject_blog(article_id: str) -> dict:
    res = await db.autoseo_articles.update_one(
        {"autoseo_id": article_id, "source": "ceo_agent"},
        {"$set": {"status": "rejected", "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Rascunho não encontrado")
    return {"rejected": True, "article_id": article_id}


@router.post("/creative/{asset_id}/{action}")
async def review_asset(asset_id: str, action: str) -> dict:
    if action not in ("publish", "reject"):
        raise HTTPException(400, "Ação desconhecida")
    status = "approved" if action == "publish" else "rejected"
    res = await db.ceo_assets.update_one({"asset_id": asset_id},
                                         {"$set": {"status": status, "updated_at": _now()}})
    if not res.matched_count:
        raise HTTPException(404, "Visual não encontrado")
    return {"status": status, "asset_id": asset_id}


@router.get("/asset/{asset_id}")
async def asset_media(asset_id: str):
    doc = await db.ceo_assets.find_one({"asset_id": asset_id}, {"_id": 0, "storage_path": 1, "content_type": 1})
    if not doc or not doc.get("storage_path"):
        raise HTTPException(404, "Não encontrado")
    try:
        data, ctype = await run_in_threadpool(storage.get_object, doc["storage_path"])
    except Exception:  # noqa: BLE001
        raise HTTPException(404, "Média indisponível")
    return StreamingResponse(io.BytesIO(data), media_type=ctype or doc.get("content_type") or "image/png",
                             headers={"Cache-Control": "private, max-age=600"})


# ============================== Calendrier éditorial ==============================

# Thèmes saisonniers BTP par mois (1=janvier). Déterministe, pas d'appel IA.
_SEASONAL = {
    1: [("Reabilitação energética: por onde começar em 2026", "particuliers", ["reabilitação energética", "apoios"]),
        ("Isolamento do desvão: métodos e benefícios", "particuliers", ["isolamento", "desvão"])],
    2: [("Remodelar a casa de banho: orçamento e etapas", "particuliers", ["casa de banho", "remodelação"]),
        ("Orçamentos de construção: como orçamentar bem e depressa", "pros", ["orçamento", "orçamentar"])],
    3: [("Reabilitação de fachadas: quando e como", "particuliers", ["fachada", "reabilitação"]),
        ("Medição de plantas: ganhar tempo nas suas obras", "pros", ["medições", "plantas"])],
    4: [("Arranjar o terraço: orçamento e materiais", "particuliers", ["terraço", "exterior"]),
        ("Organizar o planeamento de uma obra", "pros", ["planeamento", "obra"])],
    5: [("Ampliação de moradia: licenciamento e custos", "particuliers", ["ampliação", "licenciamento"]),
        ("Faturação certificada AT: preparar-se", "pros", ["faturação certificada", "AT"])],
    6: [("Conforto de verão: climatização e ventilação", "particuliers", ["climatização", "conforto"]),
        ("Acompanhar a rentabilidade das suas obras", "pros", ["margem", "rentabilidade"])],
    7: [("Cobertura: diagnóstico antes do outono", "particuliers", ["cobertura", "diagnóstico"]),
        ("Gerir os subempreiteiros com tranquilidade", "pros", ["subempreitada", "obra"])],
    8: [("Regresso às obras: planear o seu projeto", "particuliers", ["obras", "planeamento"]),
        ("Preparar a carteira de encomendas de outono", "pros", ["angariação", "clientes"])],
    9: [("Isolamento antes do inverno: paredes e desvão", "particuliers", ["isolamento", "inverno"]),
        ("Comparar as plantas antes/depois de uma obra", "pros", ["comparar plantas", "trabalhos a mais"])],
    10: [("Aquecimento: bomba de calor ou caldeira?", "particuliers", ["bomba de calor", "aquecimento"]),
         ("Automatizar orçamentos com vários pisos", "pros", ["orçamentos", "automatização"])],
    11: [("Casa de banho: tendências e remodelação de inverno", "particuliers", ["casa de banho", "tendências"]),
         ("Fechar o ano: balanço e orçamento das obras", "pros", ["balanço", "orçamento"])],
    12: [("Preparar as obras para o novo ano", "particuliers", ["obras", "projeto"]),
         ("Objetivos comerciais de construção para o próximo ano", "pros", ["comercial", "objetivos"])],
}


@router.get("/calendar")
async def editorial_calendar() -> dict:
    now = datetime.now(timezone.utc)
    this_m = now.month
    next_m = 1 if this_m == 12 else this_m + 1
    months = [("Este mês", this_m), ("O próximo mês", next_m)]
    slots = []
    for label, m in months:
        for title, audience, kws in _SEASONAL.get(m, []):
            slots.append({"period": label, "month": m, "title": title,
                          "audience": audience, "keywords": kws,
                          "rationale": f'Tema sazonal para {AUDIENCE_LABEL[audience]}.'})
    return {"slots": slots, "generated_at": _now()}
